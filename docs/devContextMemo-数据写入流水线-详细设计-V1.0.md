# devContextMemo 数据写入流水线 — 详细设计 V1.0

> **版本**：V1.1  
> **日期**：2026-06-15（更新） / 2026-06-14（初版）  
> **设计参考**：MiMo Code dream（Phase 0-5 巩固流程）、OpenViking（两阶段提交 + 多层过滤）、Mem0 V3（纯增量 + 确定性去重）  
> **继承自**：v0.18 §8.10 已有草案（三层目录 + 草稿状态机 + 死信队列）  
> **回答的问题**：一条对话记录从 OpenCode 到 devContextMemo 知识库的完整旅程是什么？  
> **V1.1 新增**：第十章「真实数据流走查」——用一个完整场景演示每步的输入/产出/数据形态

---

## 一、整体架构：六步流水线

```
┌──────────────────────────────────────────────────────────────┐
│                    devContextMemo 数据写入流水线                   │
├──────┬───────────────────────────────────────────────────────┤
│Step 0│ 采集 —— OpenCode Hook → 对话 JSONL 缓冲区              │
│      │   借鉴 OpenViking afterTurn 增量捕获                   │
├──────┼───────────────────────────────────────────────────────┤
│Step 1│ 攒批 —— Token 阈值触发 / session.idle 触发             │
│      │   借鉴 OpenViking commit_token_threshold (6000)        │
├──────┼───────────────────────────────────────────────────────┤
│Step 2│ 提炼 —— LLM ADD-only 提取知识条目                     │
│      │   借鉴 Mem0 V3 "LLM 只做提取，不做存储决策"             │
├──────┼───────────────────────────────────────────────────────┤
│Step 3│ 验证 —— 对照 raw trajectory SQLite 校验                 │
│      │   借鉴 MiMo Code Phase 3 "raw trajectory 是唯一真相源"  │
├──────┼───────────────────────────────────────────────────────┤
│Step 4│ 去重 —— MD5 哈希 + 语义相似度                          │
│      │   借鉴 Mem0 V3 Phase 5 确定性去重                       │
├──────┼───────────────────────────────────────────────────────┤
│Step 5│ 写入 —— MD 权威源 + DB 索引派生                        │
│      │   继承 v0.18 三层目录 + 借鉴 OpenViking MD 权威源模式   │
├──────┼───────────────────────────────────────────────────────┤
│Step 6│ 巩固 —— 合并重复 + 修剪低信号（dev dream）             │
│      │   借鉴 MiMo Code Phase 4-5                              │
└──────┴───────────────────────────────────────────────────────┘
```

### 1.1 设计原则（从三系统提炼）

| # | 原则 | 来源 | 理由 |
|---|------|------|------|
| **P1** | LLM 只做提取，不做存储决策（ADD-only） | Mem0 V3 | LLM 搞混 ADD/UPDATE/DELETE |
| **P2** | Raw trajectory 是唯一验证源 | MiMo Code | 对话记录不可篡改 |
| **P3** | MD 权威源 + DB 可随时重建 | OpenViking + v0.18 | 人可审核 + Git 版本管理 |
| **P4** | 同步归档 + 异步加工 | OpenViking | 主流程不阻塞 |
| **P5** | 确定性算法替代 LLM 判断 | Mem0 V3 | MD5/哈希比 LLM 更可靠 |
| **P6** | 优雅降级 | Mem0 V3 | 批量→逐条，失败→跳过 |
| **P7** ⚡ | DB 写操作串行化 | 审查 P1-1 修复 | SQLite 单写者限制 + asyncio.Queue 单消费者 |

---

## 二、Step 0：采集层

> 📎 **细化设计文档**：`devContextMemo-流水线-Step0-采集层-细化设计-V1.0.md`  
> （含函数签名、数据结构、完整 SQL、配置参数、异常处理、测试场景、Step 1 契约）

### 2.1 数据源

来自 OpenCode SQLite 数据库，通过 Hook `message.updated` + `session.idle` 采集：

| 采集字段 | 来源 | 用途 |
|---------|------|------|
| `session_id` | `session.id` | 会话标识 |
| `directory` | `session.directory` | 项目路径 |
| `role` | `message.data.role` | user/assistant/system |
| `text` | `part.data.text`（type="text"） | 对话内容 |
| `tool_name` | `part.data.tool`（type="tool"） | 工具名称（read/edit/write/bash） |
| `tool_input` | `part.data.state.input` | 工具调用参数 |
| `tool_output` | `part.data.state.output` | 工具执行结果 |
| `reasoning` | `part.data.text`（type="reasoning"） | LLM 思考链（可选） |
| `timestamp` | `part.time_created` | 时间戳 |

### 2.2 采集触发

```
message.updated 钩子 → 增量追加到缓冲区
     ↓
token_count >= 6000 或 session.idle
     ↓
触发 Step 1 攒批
```

### 2.3 防噪声：三层剥壳

```
原始消息
  → ① 剥离 <system-reminder> 块
  → ② 剥离 <openviking-context> / <relevant-memories> 块  
  → ③ 剥离 [Subagent Context] 块
  → 纯净消息
```

**为何不在此层做关键词过滤？** Phase 1 选择全量采集，不做采集预分类。理由：关键词过滤可能在采集层误丢弃有价值的上下文（如工具调用链中的关键信息）。Phase 2 再加采集层轻量预分类。

---

## 三、Step 1：攒批层

> 📎 **细化设计文档**：`devContextMemo-流水线-Step1-攒批层-细化设计-V1.0.md`
> （含函数签名、数据结构、token 计数、JSONL 序列化、异常处理、测试场景、Step 2 契约）
> **待办**：TODO-1.1 `_status` WAL 兼容 / TODO-1.2 定时器生命周期 / TODO-1.3 tiktoken 降级 / TODO-1.4 超时参数合理性

### 3.1 触发条件（任一满足）

| 条件 | 含义 | 优先级 |
|------|------|:---:|
| `session.idle` 事件 | 会话完成/空闲 | 主触发 |
| `token_count >= 6000` | 消息积累到阈值 | 补充触发 |
| 每日定时扫描 | 兜底未处理的 session | 兜底触发 |

### 3.2 攒批输出格式

```jsonl
{
  "session_id": "sess_abc123",
  "directory": "/path/to/project",
  "message_count": 24,
  "token_count": 6230,
  "captured_at": "2026-06-14T10:00:00Z",
  "messages": [
    {
      "role": "user",
      "content": "帮我给 OrderService.createOrder 加幂等校验",
      "timestamp": "2026-06-14T09:58:00Z"
    },
    {
      "role": "assistant",
      "content": "好的，我先看看现有实现",
      "tools": [
        {"tool": "read", "input": {"file": "src/OrderService.java"}, "output": "..."},
        {"tool": "write", "input": {"file": "src/OrderService.java", "content": "@Idempotent..."}, "output": {"success": true}}
      ],
      "reasoning": "用户要求在 OrderService.createOrder 添加幂等校验...",
      "timestamp": "2026-06-14T09:58:30Z"
    }
  ]
}
```

> **关键**：保留 `tools[].input/output` 字段——这是 Step 3 验证和后续代码级校准所需的证据链。

### 3.3 落盘位置

```
.devContextMemo/staging/2026-06-14/sess_abc123/messages.jsonl
.devContextMemo/staging/2026-06-14/sess_abc123/_meta.yaml   # session 元数据
```

---

## 四、Step 2：提炼层（核心）

> 📎 **细化设计文档**：`devContextMemo-流水线-Step2-提炼层-细化设计-V1.0.md`
> （含完整 System Prompt + User Prompt 模板、JSON 三层解析容错、重试退避、死信队列、截断算法、测试场景）
> **待办**：TODO-2.1 LLM 模型切换 / TODO-2.2 AGENTS.md 读取路径 / TODO-2.3 response_format 兼容性 / TODO-2.5 提炼并发控制

### 4.1 设计原则：LLM 只做 ADD

借鉴 Mem0 V3 的核心教训：**不要让 LLM 同时做提取 + 分类 + 去重决策**。

devContextMemo 的提炼层职责拆分：

| 谁来做 | 做什么 | 为什么 |
|--------|--------|--------|
| **LLM** | 从对话中提取知识条目 + 给三元组标签 | LLM 擅长语义理解 |
| **确定性算法** | MD5 去重 + 冲突检测 | 算法比 LLM 更可靠 |
| **系统** | 写入 MD + 派生 DB 索引 | 确定性操作 |

### 4.2 LLM 提取 Prompt 结构

```
System Prompt:
  你是 devContextMemo 的知识提炼器。你的职责是：
  1. 从对话记录中提取可复用的项目知识
  2. 为每条知识标注 Lx（粒度）、Sy（稳定性）、Depth（认知深度）
  3. ⚠️ 只提取 ADD，不做 UPDATE/DELETE——去重由系统算法处理

  提取标准：
  - 用户明确陈述的约束/规范/决策（含关键词：always, never, must, 必须, 统一）
  - 跨 session 重复出现的信息（同一概念被多次提及）
  - 代码变更中体现的模式（从 tools 字段中的 write/edit 操作提取）
  - ⚠️ 不提取：AI 的建议/推荐（未经用户确认）、纯代码生成、简单问答

  输出 JSON 格式：
  {
    "extracted_items": [
      {
        "content": "OrderService.createOrder() 需要幂等校验，key=orderId",
        "Lx": "L3",
        "Sy": "S4", 
        "Depth": "KH",
        "confidence": 0.87,
        "evidence": "user explicitly stated + code was modified"
      }
    ]
  }
```

### 4.3 提取的输入上下文 ⚡ P0 修复（F2-4 + PB-2）

```
┌──────────────────────────────────┐
│  提炼 LLM 接收的上下文            │
├──────────────────────────────────┤
│  1. 最近 3 个 session 的 messages │
│  2. 当前项目的 AGENTS.md（已注入） │
│  3. 已有知识的标题列表（防重复提取）│
│  ⚠️ 不传：已有知识的完整正文       │
│    （防止 LLM 因上下文过长而漏提取）│
└──────────────────────────────────┘

⚡ Context 上限控制（P0 修复 — FMEA F2-4 + 性能 PB-2）：

  规则：
  • 硬上限：32K tokens（约 24K 中文字 / 16K 英文单词）
  • 超出时的截断策略：
    - 优先保留最近的消息（时间倒序）
    - 保留所有 tools 字段（write/edit 的 input/output 是验证证据）
    - 在 prompt 头部追加截断提示：
      "[注意：以下内容已截断，仅包含最近 N 条消息。
       如需完整上下文，请将本次标记为 needs_review]"
  • 截断后的 confidence 惩罚：
    - 自动降低本次提炼置信度上限至 0.80（不可达 0.85 自动晋升阈值）
    - 理由：信息不完整可能导致误提取

  实现伪代码：
  ┌───────────────────────────────────────┐
  │ messages = load_recent_sessions(3)     │
  │ tokens = count_tokens(messages)        │
  │ if tokens > MAX_CONTEXT (32000):       │
  │   messages = truncate_oldest(          │
  │     messages, keep_tools=True,         │
  │     target_tokens=28000  // 留4K余量   │
  │   )                                    │
  │   context_truncated = True              │
  │   max_confidence_cap = 0.80            │
  └───────────────────────────────────────┘
```

### 4.3-A 提炼结果格式校验（🆕 V1.1 新增）

```
LLM 返回 → JSON 解析
  ├─ 解析失败 → 重试（最多 3 次，指数退避 10s→30s→90s）
  │              → 重试时追加提示："上次输出格式错误，请严格按 JSON schema 返回"
  ├─ JSON 合法但缺少必填字段 → 重试（同机制）
  ├─ 3 次均失败 → 写入死信队列，标记 task 失败
  └─ 校验通过 → 进入验证层（Step 3）
```

**校验规则**：
- `extracted_items` 字段必须存在且为数组
- 每条 item 的 `content` 非空，`Lx`/`Sy`/`Depth` 在枚举值范围内
- `confidence` 为 0-1 之间的数值
- 空数组 `[]` 允许——表示本次无知识可提炼（正常情况，不报错）

### 4.4 提炼置信度与晋升规则

| 置信度 | 处理方式 | 设计理由 |
|:---:|---------|---------|
| **≥ 0.85** | 自动晋升 → 写入 formal knowledge | 高置信度，直接生效 |
| **0.6 ~ 0.84** | 标记 `needs_review` → 下次 dev dream 时人工确认 | 中等置信度，需要人过一眼 |
| **< 0.6** | 写入草稿区 → 不计入 DB 索引 → 人处理 | 低置信度，不入正式知识库 |

> **v0.18 已有设计**（保留）：`confidence < 0.6` 标记 `needs_human`，入人工审核队列。

---

## 五、Step 3：验证层

> 📎 **细化设计文档**：`devContextMemo-流水线-Step3-验证层-细化设计-V1.0.md`
> （含代码变更验证/原文模糊匹配算法、confidence 五档修正规则、DB 锁降级、批量查询优化）
> **待办**：TODO-3.1 验证成本收益平衡 / TODO-3.2 跨 session 验证

### 5.1 为什么需要验证？

借鉴 MiMo Code Phase 3：

| 风险 | 示例 | 后果 |
|------|------|------|
| LLM 提炼了未发生的操作 | 提炼出"已添加幂等校验"，但实际 write 操作被 rejection | 错误知识持续误导 |
| 用户随口提及但未执行 | "应该用 Redis 做缓存"，但最终没用 | 知识描述了一个未实施的决定 |
| Memory files 过时 | 3 天前的 memory 说用 OAuth2，但代码已改为 JWT | 代码级知识过时 |

### 5.2 验证方式

```
提炼出的知识 → 查询 OpenCode SQLite 对应 session
  ├─ 知识提到"代码被修改"？
  │   → 检查 part.type="tool" + tool="write/edit" 的 tool_output.success
  │   → tool_output.success = false → 降级 confidence
  │
  ├─ 知识提到"用户说了X"？
  │   → 搜索原文中是否包含 X
  │   → 原文不包含 → 降级 confidence
  │
  ├─ 知识提到"决定用Y"？
  │   → 搜索原文中的 "决定/选择/改为" 上下文
  │   → 确认 Y 确实是被决定的那个选项
  │
  └─ 没有任何原始证据？
      → 标记 status = "unverified"，不自动晋升
```

### 5.3 验证 SQL（借鉴 MiMo Code）

```sql
-- 验证知识中提到的代码变更是否真实发生
SELECT p.id,
       json_extract(p.data, '$.tool') as tool,
       json_extract(p.data, '$.state.input.file') as file,
       json_extract(p.data, '$.state.output.success') as success
FROM part p
JOIN message m ON m.id = p.message_id
WHERE m.session_id = :session_id
  AND json_extract(p.data, '$.type') = 'tool'
  AND json_extract(p.data, '$.tool') IN ('write', 'edit')
ORDER BY p.time_created DESC;
```

### 5.3-B ⚡ OpenCode SQLite 访问控制（P0 修复 — 审查 P1-4）

**问题**：Step 3 验证需要只读查询 OpenCode 的 SQLite。如果 OpenCode 正在写
入（用户正在对话），WAL 锁可能导致我们的查询阻塞或超时。

**方案：busy_timeout + 超时降级**

```
OpenCode DB 连接配置（只读模式）：
  PRAGMA busy_timeout = 3000;    -- 等待锁释放最多 3 秒
  PRAGMA query_only = 1;         -- 强制只读（安全兜底）
  PRAGMA journal_mode = WAL;     -- 与 OpenCode 保持一致

超时降级策略：
  ┌──────────────────────────────────────┐
  │ try:                                  │
  │   result = execute_verify_sql(session)│
  │ except OperationalError as e:         │
  │   if "locked" in str(e):             │
  │     # OpenCode 正在写入，等待超时     │
  │     log.warning(                     │
  │       f"OpenCode DB locked, "        │
  │       f"skipping verify for {id}")   │
  │     confidence_penalty = -0.15       │
  │     verification_status = "skipped"  │
  │     # 不阻断主流程，知识仍可写入      │
  │     # 标记 unverified 即可            │
  │   else:                               │
  │     raise  # 其他错误正常抛出          │
  └──────────────────────────────────────┘

设计理由：
  • 验证是"锦上添花"不是"必不可少"——跳过验证 ≠ 知识丢失
  • unverified 标记的知识仍会写入，只是不自动晋升到 ≥0.85
  • 下次 dev dream 或 calibrate(full) 时可以补验证
```

### 5.4 验证结果对 confidence 的影响

| 验证结果 | 对 confidence 的影响 | 处理 |
|---------|:---:|------|
| ✅ 找到对应工具调用 + success=true | 不变 | 正常晋升 |
| ⚠️ 找到对应工具调用 + success=false | -0.3 | 重新走 `< 0.6` 逻辑 |
| ❌ 未找到任何对应工具调用 | -0.15 | 标记 `unverified` |

---

## 六、Step 4：去重层

> 📎 **细化设计文档**：`devContextMemo-流水线-Step4-去重层-细化设计-V1.0.md`
> （含 MD5 标准化算法、embedding 生成+余弦相似度、批量查询优化、降级策略）
> **待办**：TODO-4.1 embedding 模型选择 / TODO-4.2 暴力遍历性能上限

### 6.1 设计原则：确定性优先

```
借鉴 Mem0 V3：LLM 不做去重决策，确定性算法做。

去重流程：
  新知识 content
    → ① MD5 哈希 → 在已有知识库中查相同哈希
        └─ 找到 → skip（重复）
    → ② embedding cosine similarity ≥ 0.95 → 标记 merge 候选
        └─ 下次 dev dream 时 LLM 做最终合并决策
    → ③ 都不匹配 → 新知识，正常写入
```

### 6.2 何时做 LLM 合并？

**不在提炼时做，在 dev dream 巩固时做。**

理由：提炼时做合并意味着这个 LLM 调用既要提取新知识、又要判断与已有知识的关系——复杂度高且容易出错。更好的做法是提炼时只 ADD，巩固时（每 7 天或手动 dev dream）再批量处理合并。

---

## 七、Step 5：写入层

> 📎 **细化设计文档**：`devContextMemo-流水线-Step5-写入层-细化设计-V1.0.md`
> （含 YAML frontmatter 生成、MD 原子写入、先 DB 后 MD 事务、dirty 标记修复、OpenViking MemoryFile 移植对照）
> **待办**：TODO-5.1 Git 自动提交 / TODO-5.2 staging/draft 目录组织 / TODO-5.3 rebuild-db 命令

### 7.1 文件落盘（继承 v0.18 三层目录）

```
.devContextMemo/
├── knowledge/                     # 【正式层】MD 权威源
│   └── {domain}/{subdomain}.md    # 例: auth/oauth2-refresh-token.md
│
├── staging/                       # 【草稿层】（Git 追踪，保留 30 天）
│   └── {date}/{session_id}/
│       ├── messages.jsonl         # Step 1 攒批产物
│       └── _meta.yaml
│
└── index/                         # 【索引层】（.gitignore，可随时从 MD 重建）
    └── devContextMemo.db                    # SQLite: FTS5 + URI + 元数据
```

### 7.2 知识条目 MD 格式（更新版）

```yaml
---
id: kw-20260614-001
title: "OrderService.createOrder() 幂等校验 key=orderId"
Lx: L3
Sy: S4
Depth: KH
confidence: 0.87
status: valid

source:
  session: sess_abc123
  extracted_at: 2026-06-14T10:30:00Z

calibration:
  last_verified_at: 2026-06-14T10:30:00Z
  verified_against: ["session:sess_abc123", "code:src/OrderService.java"]

evidence:
  - type: user_statement
    content: "帮我给 OrderService.createOrder 加幂等校验"
  - type: tool_execution
    tool: write
    file: src/OrderService.java
    success: true
---

## 内容

OrderService.createOrder() 方法需要幂等校验，
使用 @Idempotent 注解，幂等 key 为 orderId（非 transactionId）。
```

### 7.3 DB 索引同步（继承 v0.18）⚡ P0 修复

**核心设计决策（P0 修复：审查一致性-A + F5-1）**：

```
双写顺序：先 DB → 后 MD（不是先 MD 后 DB）

理由：
  • DB 是事务性的（可原子回滚），MD 文件写入不是
  • DB 写失败 = 整个操作失败（状态干净）
  • MD 写失败 = DB 有记录但 content 暂缺（可通过 rebuild-db 修复）

回写流程：
  Step 5 写入:
    ① INSERT INTO knowledge_index (DB) ── 失败 → 整个写入失败 ❌
    ② Write MD file (文件系统)    ── 失败 → 标记 DB dirty ⚠️
       → 不抛异常（DB 有元数据记录，query 可找到 URI）
       → 下次 rebuild-db 或 calibrate(quick) 时自动修复
    ③ FTS5 触发器自动同步          ── 失败 → 记录日志（低概率，rebuild 可修）
```

**F5-2 MD 写入失败重试机制（P0 修复）**：
```
MD 文件写入失败处理：
  → 重试 1 次（间隔 2 秒）
  → 仍失败 → 标记 knowledge_index.dirty = true
  → 告警日志："MD write failed for {id}, DB index intact, marked dirty"
  → 返回 task_status = "degraded"（非完全失败）
```

```
MD 写入 → 触发 DB 索引同步
  → INSERT OR REPLACE INTO knowledge_index
      (id, title, Lx, Sy, Depth, confidence, keywords, uri, updated_at)
  → 不含 content 全文
  → DB 可随时从 MD 重建（devContextMemo rebuild-db --from-md）
```

### 7.4 DB 写串行化架构 ⚡ P0 修复（审查 P1-1）

**问题**：SQLite 同一时刻只允许一个写操作。MVP 流水线中存在多处 DB 写入：
- staging_queue INSERT（Step 0-1）
- knowledge_index INSERT/UPDATE（Step 5）
- dead_letter INSERT（失败时）
- calibration_log INSERT（验证时）

**方案：asyncio.Queue + 单消费者 Worker**

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Step 0-1    │    │ Step 5       │    │ 其他写入源       │
│ (采集/攒批) │    │ (写入索引)   │    │ (校准/死信等)    │
└──────┬──────┘    └──────┬───────┘    └────────┬────────┘
       │                  │                     │
       ▼                  ▼                     ▼
  ┌────────────────────────────────────────────────────┐
  │              db_write_queue (asyncio.Queue)         │
  │              maxsize = 200 (背压控制)               │
  └──────────────────────┬─────────────────────────────┘
                         │
                         ▼  单消费者（串行执行）
  ┌────────────────────────────────────────────────────┐
  │              db_writer_worker (async loop)          │
  │                                                      │
  │  while True:                                        │
  │    task = await db_write_queue.get()                 │
  │    try:                                              │
  │      await execute_db_write(task)                    │
  │      # 所有写操作在同一 SQLite 连接上串行执行        │
  │    except DBError as e:                              │
  │      log.error(f"DB write failed: {e}")             │
  │      task.callback(False, error=e)                   │
  │    finally:                                          │
  │      db_write_queue.task_done()                      │
  └────────────────────────────────────────────────────┘
```

**关键参数**：
| 参数 | 值 | 理由 |
|------|-----|------|
| queue_maxsize | 200 | 背压：队列满时生产者 await，防止内存无限增长 |
| 连接数 | 1 | 单连接 = 天然串行，无需额外锁 |
| 超时 | 无（阻塞等待）| 写入操作本身 < 10ms，不会长时间阻塞 |
| 错误处理 | callback 通知调用方 | 调用方可决定重试或放弃 |

**写入吞吐预估**：
- 单次 INSERT：~0.5-2ms（本地 SQLite + WAL）
- 峰值吞吐：~500-2000 writes/sec
- MVP 实际需求：< 50 writes/sec（远低于上限）

---

## 八、Step 6：巩固层

> 📎 **细化设计文档**：`devContextMemo-流水线-Step6-巩固层-细化设计-V1.0.md`
> （含合并算法（LLM 判断 + 执行）、三种修剪规则、晋升条件、dirty 修复、MiMo Code dream.txt Phase 0→5 移植对照）
> **待办**：TODO-6.1 dev dream CLI 命令 / TODO-6.2 自动巩固调度器 / TODO-6.3 used_count 更新时机 / TODO-6.4 合并 LLM 成本

### 8.1 触发方式

| 方式 | 时机 | 做什么 |
|------|------|--------|
| **dev dream**（手动） | 用户主动触发 | 合并重复项 + 修剪低信号 + 提升 maturity |
| **auto-dream**（自动） | 每 7 天 | 同上 |
| **事件驱动** | 每次提炼完成后（异步） | 仅做 MD5 去重核验 |

### 8.2 合并规则

```
知识 A 和知识 B 语义相似度 ≥ 0.95
  → LLM 判断是否为同一知识
  → 是：合并（保留更完整的 content + 更新 evidence 列表）
  → 否：保留两条
```

### 8.3 修剪规则（借鉴 MiMo Code Phase 5）

```
  used_count = 0 且 last_used_at < 90 天 → 标记 deprecated
  confidence < 0.4                        → 标记 deprecated  
  updated_at < 180 天 且 last_used_at < 180 天 → 标记 archived
```

---

## 九、完整时序图

```
OpenCode              devContextMemo                   LLM
   │                      │                          │
   │── message.updated ──→│ (Step 0: 增量采集)        │
   │                      │                          │
   │── session.idle ─────→│ (Step 1: 攒批)            │
   │                      │   token >= 6000?         │
   │                      │                          │
   │                      │── 发送对话上下文 ────────→│ (Step 2: 提炼)
   │                      │←── 知识条目+三元组 ──────│
   │                      │                          │
   │                      │── SQLite 只读查询 ──────→│ (Step 3: 验证)
   │                      │←── 验证结果              │
   │                      │                          │
   │                      │ (Step 4: MD5 去重)       │
   │                      │   confidence >= 0.85?    │
   │                      │      ├─ 是 → 晋升       │
   │                      │      └─ 否 → staging     │
   │                      │                          │
   │                      │ (Step 5: 写入 MD + DB)   │
   │                      │                          │
   │                      │ (Step 6: 巩固/异步)      │
   │                      │                          │
```

---

## 十、真实数据流走查：一条知识从对话到落盘的全过程

> 以下用一个真实场景，逐步展示每条数据在各步骤中「长什么样」。  
> 场景：用户在 `~/projects/order-system` 项目中，要求给 `OrderService.createOrder()` 加幂等校验。

---

### 10.1 原始对话（OpenCode 中发生的事）

```
用户: 「帮我给 OrderService.createOrder 加幂等校验」
 AI:  「好的，我先看看现有实现。」
      [调用 read → src/OrderService.java]
      [调用 write → src/OrderService.java，写入 @Idempotent(key="orderId")，success=true]
 AI:  「已添加 @Idempotent 注解，key=orderId。注意不要用 transactionId，因为同一订单可能有多笔交易。」
用户: 「对了，交易超时时间统一用 30 秒，不要用默认的 10 秒。」
 AI:  「明白。这个规范我会记住。」
```

### 10.2 原始数据在 OpenCode SQLite 中的形态

OpenCode 将对话以 `message` + `part` 两张表存储。Step 0 读到的是这样的原始数据（简化表示）：

```json
// message 表（一条 user 消息 + 一条 assistant 消息 + 一条 user 消息）
[
  {
    "id": "msg_001", "session_id": "sess_X9k2", "role": "user",
    "parts": [
      {"type": "text", "data": {"text": "帮我给 OrderService.createOrder 加幂等校验"}, "time": "09:58:00"}
    ]
  },
  {
    "id": "msg_002", "session_id": "sess_X9k2", "role": "assistant",
    "parts": [
      {"type": "text",     "data": {"text": "好的，我先看看现有实现。"}, "time": "09:58:05"},
      {"type": "tool",     "data": {"tool": "read", "state": {"input": {"file": "src/OrderService.java"}, "output": "public class OrderService { ... }"}}, "time": "09:58:06"},
      {"type": "reasoning","data": {"text": "用户要求在 createOrder 方法上加幂等校验..."}, "time": "09:58:10"},
      {"type": "tool",     "data": {"tool": "write", "state": {"input": {"file": "src/OrderService.java", "content": "@Idempotent(key=\"orderId\") ..."}, "output": {"success": true}}}, "time": "09:58:15"},
      {"type": "text",     "data": {"text": "已添加 @Idempotent 注解，key=orderId。注意不要用 transactionId，因为同一订单可能有多笔交易。"}, "time": "09:58:20"}
    ]
  },
  {
    "id": "msg_003", "session_id": "sess_X9k2", "role": "user",
    "parts": [
      {"type": "text", "data": {"text": "对了，交易超时时间统一用 30 秒，不要用默认的 10 秒。"}, "time": "09:59:00"}
    ]
  }
]
```

---

### 10.3 Step 0：采集 —— 剥离噪声

**输入**：OpenCode SQLite 的 3 条 message 原始数据  
**动作**：Hook `message.updated` 监听新消息 → 三层剥壳 → 写入内存缓冲区

```
原始 messages（含 system-reminder / subagent 上下文块）
  → ① 剥离 <system-reminder> 块（OpenCode 注入的提示）
  → ② 剥离 injected context 块（如 <relevant-memories>）
  → ③ 剥离 [Subagent Context] 块
  → 干净的消息列表
```

**产出物**：内存缓冲区中的干净消息（尚未落盘，等待 Step 1 攒批）

```
缓冲区结构（内存）:
{
  "session_id": "sess_X9k2",
  "directory": "~/projects/order-system",
  "messages": [msg_001(cleaned), msg_002(cleaned), msg_003(cleaned)],
  "token_count": 2150,
  "last_message_at": "09:59:00"
}
```

> ⚠️ 此时还未落盘，只是追加到内存缓冲区。消息不够阈值（6000 tokens），不触发 Step 1。

---

### 10.4 Step 1：攒批 —— 触发 + 落盘

**触发**：用户结束对话 → OpenCode 发出 `session.idle` 事件  
**动作**：累计 token 数 ≥ 6000 或 session 空闲 → 将缓冲区的消息打包成 JSONL 文件

```
触发条件: session.idle（会话结束，即使 token 只有 2150 < 6000 也触发）

缓冲区 → 序列化为 JSONL + 元数据 YAML
```

**产出物**：

📄 `.devContextMemo/staging/2026-06-14/sess_X9k2/messages.jsonl`
```jsonl
{"role":"user","content":"帮我给 OrderService.createOrder 加幂等校验","timestamp":"2026-06-14T09:58:00Z","source":"msg_001"}
{"role":"assistant","content":"好的，我先看看现有实现。","tools":[{"tool":"read","input":{"file":"src/OrderService.java"},"output":"public class OrderService { ... }"}],"reasoning":"用户要求在 createOrder 方法上加幂等校验...","timestamp":"2026-06-14T09:58:05Z","source":"msg_002"}
{"role":"assistant","content":"已添加 @Idempotent 注解，key=orderId。注意不要用 transactionId，因为同一订单可能有多笔交易。","tools":[{"tool":"write","input":{"file":"src/OrderService.java","content":"@Idempotent(key=\"orderId\") ..."},"output":{"success":true}}],"timestamp":"2026-06-14T09:58:15Z","source":"msg_002"}
{"role":"user","content":"对了，交易超时时间统一用 30 秒，不要用默认的 10 秒。","timestamp":"2026-06-14T09:59:00Z","source":"msg_003"}
```

📄 `.devContextMemo/staging/2026-06-14/sess_X9k2/_meta.yaml`
```yaml
session_id: sess_X9k2
directory: ~/projects/order-system
message_count: 4
token_count: 2150
captured_at: 2026-06-14T10:00:00Z
status: staged
```

> 落盘完成。缓冲区的内存副本可以释放。

---

### 10.5 Step 2：提炼 —— LLM 从对话中提取知识

**输入**：`messages.jsonl`（4 条消息） + 当前项目 AGENTS.md（作为上下文） + 已有知识标题列表（防重复）  
**动作**：构造 Prompt → 调用 LLM → 解析 JSON 输出

**发送给 LLM 的 Prompt（简化版）**：

```
你是一个知识提炼器。从以下对话中提取可复用的项目知识。

[注意：以下内容包含 4 条消息，2450 tokens，未截断]

【对话记录】
user(09:58): 帮我给 OrderService.createOrder 加幂等校验
assistant(09:58): 好的，我先看看现有实现。[tools: read→OrderService.java, write→OrderService.java @Idempotent(key="orderId")]
assistant(09:58): 已添加 @Idempotent 注解，key=orderId。注意不要用 transactionId...
user(09:59): 对了，交易超时时间统一用 30 秒，不要用默认的 10 秒。

【已有知识标题】（不要重复提取）：
- （空，首次对话）

请输出 JSON：{"extracted_items": [...]}
```

**LLM 返回**：
```json
{
  "extracted_items": [
    {
      "content": "OrderService.createOrder() 需要幂等校验，使用 @Idempotent 注解，key=orderId（非 transactionId）",
      "Lx": "L3", "Sy": "S4", "Depth": "KH",
      "confidence": 0.87,
      "evidence": "user explicitly requested + code was modified via write tool"
    },
    {
      "content": "交易超时时间统一为 30 秒，不使用默认 10 秒",
      "Lx": "L3", "Sy": "S4", "Depth": "KH",
      "confidence": 0.78,
      "evidence": "user explicitly stated as constraint"
    }
  ]
}
```

**产出物**：2 条提炼结果（暂存内存，尚未落知识库）

| # | content | confidence | 状态 |
|---|---------|:---:|------|
| ① | 幂等校验 key=orderId | 0.87 | → 进入 Step 3 验证 |
| ② | 超时时间 30 秒 | 0.78 | → 进入 Step 3 验证 |

---

### 10.6 Step 3：验证 —— 对照原始数据交叉校验

**输入**：Step 2 的 2 条提炼结果 + OpenCode SQLite 原始数据  
**动作**：逐条对照原始对话，检查证据链是否完整

**对第①条（幂等校验）的验证**：

```
知识 claims: 「代码被修改，加了 @Idempotent(key="orderId")」
  → 查询 OpenCode SQLite:
     SELECT * FROM part WHERE session_id='sess_X9k2'
       AND json_extract(data,'$.tool')='write'
       AND json_extract(data,'$.state.input.file')='src/OrderService.java'
  → 找到 1 条记录: success=true ✅
  → 原文匹配: 用户说了「帮我给 OrderService.createOrder 加幂等校验」✅

结果: verified ✅  confidence 保持 0.87
```

**对第②条（超时 30 秒）的验证**：

```
知识 claims: 「交易超时统一 30 秒」
  → 查询 OpenCode SQLite:
     SELECT * FROM part WHERE session_id='sess_X9k2'
       AND type='tool' AND tool IN ('write','edit')
  → 没有 write/edit 对应超时配置的文件 ❌
  → 原文匹配: 用户确实说了「交易超时时间统一用 30 秒」✅

结果: unverified ⚠️  confidence: 0.78 → 0.63（扣 0.15）
     理由: 用户在对话中提出但未实际修改代码（只有口头声明，无工具执行证据）
```

**产出物**：修正后的提炼结果

| # | content | confidence | verify_status |
|---|---------|:---:|------|
| ① | 幂等校验 key=orderId | 0.87 | verified |
| ② | 超时时间 30 秒 | 0.63 | unverified |

---

### 10.7 Step 4：去重 —— 检查是否已有相同知识

**输入**：2 条验证过的提炼结果 + 已有知识库  
**动作**：MD5 哈希 + cosine 相似度双重检查

```
对第①条: MD5("OrderService.createOrder() 幂等校验...") = a3f8c2e1...
  → 查询 knowledge_index: 无相同 MD5 ✅（新知识）
  → embedding cosine 查询: 最高相似度 0.42（远低于 0.95 阈值）✅
  → 结论: 新知识，正常写入

对第②条: MD5("交易超时时间统一为 30 秒...") = d4b9f1a7...
  → 查询 knowledge_index: 无相同 MD5 ✅（新知识）
  → embedding cosine 查询: 最高相似度 0.88（低于 0.95 阈值）✅
  → 结论: 新知识，正常写入
```

**产出物**：2 条确认不重复的知识，进入写入层

---

### 10.8 Step 5：写入 —— 落 MD 权威源 + DB 索引

**输入**：2 条去重后的知识  
**动作**：先写 DB → 再写 MD 文件（P0 修复：DB 事务可回滚 → MD 写入容错）

**产出物①：MD 文件（2 个）**

📄 `.devContextMemo/knowledge/coding-standards/order-create-idempotent.md`
```yaml
---
id: kw-20260614-001
title: "OrderService.createOrder() 幂等校验 key=orderId"
Lx: L3
Sy: S4
Depth: KH
confidence: 0.87
status: valid
domain: coding-standards

source:
  session: sess_X9k2
  extracted_at: 2026-06-14T10:30:00Z

calibration:
  last_verified_at: 2026-06-14T10:30:00Z
  verified_against:
    - "session:sess_X9k2"
    - "code:src/OrderService.java"

evidence:
  - type: user_statement
    content: "帮我给 OrderService.createOrder 加幂等校验"
  - type: tool_execution
    tool: write
    file: src/OrderService.java
    success: true
---

## 内容

OrderService.createOrder() 方法需要幂等校验，
使用 @Idempotent 注解，幂等 key 为 orderId（非 transactionId）。
```

📄 `.devContextMemo/knowledge/coding-standards/transaction-timeout-30s.md`
```yaml
---
id: kw-20260614-002
title: "交易超时时间统一为 30 秒"
Lx: L3
Sy: S4
Depth: KH
confidence: 0.63
status: unverified
domain: coding-standards

source:
  session: sess_X9k2
  extracted_at: 2026-06-14T10:30:00Z

calibration:
  last_verified_at: 2026-06-14T10:30:00Z
  verified_against:
    - "session:sess_X9k2"

evidence:
  - type: user_statement
    content: "交易超时时间统一用 30 秒，不要用默认的 10 秒"
---

## 内容

交易超时时间统一配置为 30 秒，不使用系统默认的 10 秒。
```

**产出物②：DB 索引记录（SQLite `knowledge_index` 表，2 行）**

```
┌──────────────────┬───────────────────────────────┬────┬────┬───────┬────────────┬──────────────────────────────────────┐
│ id               │ title                        │ Lx │ Sy │ Depth │ confidence │ uri                                  │
├──────────────────┼───────────────────────────────┼────┼────┼───────┼────────────┼──────────────────────────────────────┤
│ kw-20260614-001  │ OrderService.createOrder()... │ L3 │ S4 │ KH    │ 0.87       │ .devContextMemo/knowledge/coding-standards/o...│
│ kw-20260614-002  │ 交易超时时间统一为 30 秒      │ L3 │ S4 │ KH    │ 0.63       │ .devContextMemo/knowledge/coding-standards/t...│
└──────────────────┴───────────────────────────────┴────┴────┴───────┴────────────┴──────────────────────────────────────┘
```

**两条知识的命运分歧**：

| 知识 | confidence | 处理 |
|------|:---:|------|
| ① 幂等校验 | **0.87** ≥ 0.85 | ✅ **自动晋升** — 立即生效，下次查询就能命中 |
| ② 超时 30 秒 | **0.63** < 0.85 | ⚠️ 标记 `unverified`，写入草稿队列 — 等下次 `dev dream` 人工审核 |

---

### 10.9 Step 6：巩固（异步，不在此次写入中触发）

Step 6 在 7 天后（或手动 `dev dream`）才运行。届时它会：

```
扫描知识库 → 发现第②条（超时 30 秒，confidence=0.63，unverified）
  → 提示用户: 「以下知识需要确认：交易超时时间统一为 30 秒」
  → 用户确认 → 手动改 confidence 为 0.90 → 晋升
  → 用户否认 → 标记 deprecated

扫描知识库 → 检查重复
  → 假设 3 天后又有一次对话产生「超时 30 秒」的知识
  → cosine ≥ 0.95 → LLM 判断是否为同一条
  → 是 → 合并 evidence 列表，保留较完整的 content
```

---

### 10.10 走查总结：一条对话的 6 次蜕变

```
原始对话（3 条 message）
  │
  ▼ Step 0  剥壳 ──→ 干净消息（内存缓冲区）
  ▼ Step 1  攒批 ──→ messages.jsonl + _meta.yaml（落盘 staging/）
  ▼ Step 2  提炼 ──→ 2 条 JSON 知识条目（LLM 输出，暂存内存）
  │                   ① 幂等校验 (0.87)   ② 超时 30s (0.78)
  ▼ Step 3  验证 ──→ 回查原始数据
  │                   ① verified (0.87)   ② unverified (0.63)
  ▼ Step 4  去重 ──→ MD5 + cosine 双重检查
  │                   ① 不重复 ✅         ② 不重复 ✅
  ▼ Step 5  写入 ──→ MD 文件 × 2 + DB 索引行 × 2
  │                   ① 自动晋升生效      ② 待审核草稿
  ▼ Step 6  巩固 ──→（7 天后异步运行，处理合并/修剪/人工确认）
```

**关键观察**：
- 同一个对话产出了 2 条知识，但质量不等——验证层筛选出了未落地的口头声明（超时 30s）
- `confidence` 贯穿全流程：从 LLM 初始评分（0.87/0.78）→ 验证修正（0.87/0.63）→ 晋升门槛判断
- 从原始对话到落盘，信息被逐层浓缩：3 条 message（~500 字）→ 2 条 knowledge（~80 字）→ 2 个 MD 文件 + 2 行 DB

---

## 十一、与 v0.18 草案的差异对照（原第十章）

| 维度 | v0.18 草案 | 新设计 | 变更原因 |
|------|-----------|--------|---------|
| **采集** | ❌ 未定义 | ✅ Step 0 + Step 1 | OpenViking 实践经验 |
| **提炼** | LLM 自行判断 | LLM ADD-only | Mem0 V3 经验教训 |
| **验证** | ❌ 无 | ✅ Step 3 对照 raw trajectory | MiMo Code 核心创新 |
| **去重** | ❌ 无 | ✅ Step 4 MD5 + 语义 | Mem0 V3 Phase 5 |
| **写入** | 草稿 → LLM 提炼 → 晋升 | 提炼 → 验证 → 去重 → 写入 | 流程重排 |
| **晋升门槛** | pending → confirmed | confidence ≥ 0.85 自动晋升 | 减少人工摩擦 |
| **巩固** | ❌ 无 | ✅ Step 6 dev dream | MiMo Code Phase 4-5 |
| **防噪声** | ❌ 无 | ✅ Step 0 三层剥壳 | OpenViking §14 |

---

## 十二、待确认项

| # | 决策点 | 选项 | 建议 | 影响 |
|---|--------|------|------|------|
| **D4** | confidence ≥ 0.85 自动晋升 | a) 保持自动晋升 b) 仍需人工确认 | **a**——0.85 阈值已是高置信度，加验证层后误判率更低 |
| **D5** | Step 6 巩固（dev dream）默认频率 | a) 7 天 b) 30 天 c) 手动 | **a**——对齐 MiMo Code，7 天足够积累一次有意义的巩固 |
| **D6** | staging 目录保留天数 | a) 7 天 b) 30 天 c) 不自动清理 | **b**——v0.18 已定 30 天，对齐已有决策 |

---

*设计完成时间：2026-06-14*
