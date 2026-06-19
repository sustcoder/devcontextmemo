# devContextMemo MCP Tool 接口 — 行业调研与详细设计 V1.1

> **版本**：V1.1（🆕 补齐 id/offset 参数 + 字段统一命名 + scope 独立校验 + FTS5 手动同步 + suggestion 结构化——V38/V42/V43/V44/V45/V47/V48）  
> **日期**：2026-06-16（V1.1 修订）  
> **调研对象**：OpenViking（6 工具）、Mem0（11 工具）、MemPalace（19 工具）  
> **回答的问题**：devContextMemo 的 `query_knowledge` / `write_knowledge` / `calibrate_knowledge` 三个 Tool 的精确参数、返回值、错误码应该怎么设计？

---

## 一、三系统 Tool 接口横向对比

### 1.1 OpenViking — 6 个专用工具

| 工具 | 方向 | 核心参数 | 返回值 |
|------|:---:|---------|--------|
| `openviking_read` | 读 | `uri`, `level` (L0/L1/L2) | 分层返回内容 |
| `openviking_search` | 检索 | `query`, `filters` | 语义搜索结果列表 |
| `openviking_list` | 列目录 | `uri` | 目录下的资源列表 |
| `openviking_grep` | 搜索 | `pattern` (关键词/正则) | 匹配的 URI 列表 |
| `openviking_memory_commit` | 写 | `force_commit` (bool) | task_id |
| `openviking_add_resource` | 写 | `uri`, `content` | resource_id |

---

### 1.2 Mem0 — 11 个 MCP 工具

| 工具 | 方向 | 核心参数 |
|------|:---:|---------|
| `add_memory` | 写 | `user_id`, `agent_id`, `text`/`messages` |
| `search_memories` | 检索 | `query`, `filters`, `limit` |
| `get_memories` | 列 | `filters`, `page`, `page_size` |
| `get_memory` | 读 | `memory_id` |
| `update_memory` | 改 | `memory_id`, `text` |
| `delete_memory` | 删 | `memory_id` |

---

### 1.3 MemPalace — 19 个 MCP 工具

| 类别 | 代表工具 | 特征 |
|------|---------|------|
| **搜索**（5 个） | `mempalace_search`, `kg_query`, `traverse` | 语义搜索 + 知识图谱遍历 |
| **写入**（2 个） | `diary_write`, `kg_add` | 日记写入 + 事实三元组 |
| **浏览**（6 个） | `list_wings`, `list_rooms` | 宫殿结构浏览 |
| **管理**（6 个） | `kg_invalidate`, 删除/清理 | 失效而非删除 |

---

### 1.4 三系统对比总结

| 维度 | OpenViking | Mem0 | MemPalace | **devContextMemo 应借鉴** |
|------|:---:|:---:|:---:|------|
| **Tool 数量** | 6 | 11 | 19 | **3（Phase 1 极简）** |
| **读-写分离** | ✅ 4读+2写 | ✅ CRUD完整 | ✅ 5搜+2写 | ✅ 借鉴 OpenViking |
| **分层返回** | ✅ L0/L1/L2 | ❌ | ❌ | ✅ L0 摘要先行 |
| **异步写入** | ✅ 返回 task_id | ❌ | ❌ | ✅ 借鉴 OpenViking |
| **事件审计** | ✅ memory_diff | ✅ list_events | ❌ | Phase 1 不必要 |
| **实体管理** | ❌ | ✅ entities | ✅ kg | Phase 1 不必要 |
| **知识图谱** | ❌ | ❌ | ✅ kg_add/query | Phase 2+ |

---

## 二、devContextMemo MCP Tool 设计

### 2.1 设计原则

**Phase 1 只做 3 个 Tool**——不是功能不够，而是少即是多。

| 原则 | 理由 |
|------|------|
| **3 个 Tool，不是 6 个** | OpenViking 的 6 个是因为它有"资源/记忆/技能"三类上下文。devContextMemo 只有"项目知识"一类，不需要目录浏览工具 |
| **读-写分离** | 借鉴 OpenViking：query 是读，write 是写，calibrate 是系统触发 |
| **分层返回** | 借鉴 OpenViking L0/L1/L2：先返回摘要，AI 觉得需要再请求详情 |
| **异步写入** | 借鉴 OpenViking：write 返回 task_id，不阻塞 AI 对话 |

### 2.1-B ⚡ 全局输入校验

**domain 参数白名单校验（防路径穿越）**：

```
适用范围：query_knowledge.domain / write_knowledge（推断 domain 时）

校验规则：
  • 正则：^[a-z0-9_-]{1,64}$
  • 仅允许小写字母、数字、下划线、连字符
  • 不允许：大写字母、空格、/ \ . .. 等路径字符

校验失败 → 返回 400 "invalid domain: only [a-z0-9_-] allowed, got '{input}'"
```

**🆕 V1.1: scope 参数独立校验（V44 修复）**：

```
适用范围：calibrate_knowledge.scope

校验正则：^(all|domain:[a-z0-9_-]{1,64}|id:kw-[a-z0-9-]+)$

说明：
  • scope 不直接复用 domain 白名单——domain:auth 含冒号，与 domain 正则冲突
  • 支持三种格式：all / domain:<name> / id:kw-<id>
  • domain 部分仍做白名单校验（提取冒号后的部分）

校验失败 → 返回 400 "invalid scope format: must be 'all', 'domain:<name>', or 'id:kw-<xxx>'"
```

**其他边界校验（汇总自契约审查）**：

| 参数 | 来源 Tool | 校验规则 | 错误码 |
|------|----------|---------|--------|
| `limit` | query | 1 ≤ limit ≤ 20 | 400 |
| `offset` | query | 🆕 V1.1: ≥ 0 | 400 |
| `content` | write | 0 < len ≤ 10000 | 400 |
| `session_id` | write | 非空，格式 `sess_` + alphanum | 404（不存在时） |
| `depth` | query | KW/KH/KY 或空 | 400 |
| `stability_min` | query | S1-S5 或空 | 400 |
| `mode` | calibrate | quick/full | 400 |
| `scope` | calibrate | 🆕 V1.1: 独立正则校验 | 400 |

---

### 2.2 Tool 1：`query_knowledge`（🆕 V1.1 修订）

**功能**：AI 根据当前任务需求，检索相关项目知识。

```
Tool: query_knowledge
方向: devContextMemo → AI

Input:
  query         string  可选  自然语言查询，如"鉴权怎么做的？"（与 id 互斥）
  id            string  可选  知识 ID（与 query 互斥，按 ID 精确查询）🆕 V1.1（V38 修复）
  domain        string  可选  限定领域，如"auth"/"order"
  depth         string  可选  限定认知深度，"KW"/"KH"/"KY"
  stability_min string  可选  最低稳定性，如"S3"（只返回 S3 及以上）
  limit         int     可选  返回条数，默认 5，最大 20
  offset        int     可选  翻页偏移，默认 0 🆕 V1.1（V45 修复）
  include_full  bool    可选  是否返回完整正文，默认 false（仅返回 L0 摘要）

校验规则：
  • query 和 id 必须提供其一，且不可同时提供
  • query 为空且 id 也为空 → 400 "either query or id is required"
  • query 和 id 同时提供 → 400 "query and id are mutually exclusive"

Output:
  {
    "items": [
      {
        "id": "kw-20260614-001",
        "title": "OAuth2 鉴权使用 HMAC-SHA256 签名",
        "domain": "auth",                                         🆕 V1.1
        "granularity": "L1",        ← 🆕 V1.1: 原名 Lx（V43）
        "stability": "S2",          ← 🆕 V1.1: 原名 Sy
        "depth": "KW",              ← 🆕 V1.1: 原名 Depth
        "summary": "项目使用 HMAC-SHA256 做 API 签名验证，密钥存储在 config/auth.yaml",
        "uri": ".devContextMemo/knowledge/auth/oauth2.md",
        "confidence": 0.92,
        "code_verified": 1,         🆕 V1.1（V40 补齐）
        "prune_priority": 0.15,     🆕 V1.1
        "concept_tags": ["#HMAC","#鉴权","#SHA256"],  🆕 V1.1
        "last_calibrated_at": "2026-06-14"
      }
    ],
    "total": 3,
    "has_more": false,
    "next_offset": null,            🆕 V1.1: 下一页的 offset（has_more=true 时非 null）
    "next_action": {                🆕 V1.1: 结构化建议替代静态 suggestion（V48 修复）
      "tool": "query_knowledge",
      "hint": "如需某条知识的完整内容，请用 id 参数 + include_full=true",
      "params_example": { "id": "kw-20260614-001", "include_full": true }
    }
  }

🆕 V1.1: 空结果处理（V42 修复）
  删除 404 错误码——查询无结果是正常响应。
  空结果返回 200：
  {
    "items": [],
    "total": 0,
    "has_more": false,
    "next_offset": null,
    "next_action": { "hint": "未找到相关知识，可以尝试扩大搜索范围或添加新知识" }
  }

⚡ MD 文件缺失时的降级策略：
  当 include_full=true 但目标 MD 文件不存在或不可读时：
  • 不返回 404 错误（知识存在于 DB 索引中）
  • 改为降级返回：
    - 保留 L0 summary 字段（来自 DB/FTS5）
    - 新增 source_missing: true 标记
    - content 字段设为 null

Error Codes:
  400 - query 和 id 均未提供，或同时提供
  400 - 其他参数校验失败
  500 - 检索服务异常
```

**V1.0→V1.1 变更摘要**：

| 变更 | 旧值 | 新值 | 漏洞 |
|------|------|------|:---:|
| + id 参数 | — | string（与 query 互斥） | V38 |
| + offset 参数 | — | int（默认 0） | V45 |
| + next_offset | — | int/null（翻页用） | V45 |
| 字段命名 | Lx/Sy/Depth | granularity/stability/depth | V43 |
| + domain/概念标签等 | — | 补齐 V2.0 字段 | V40 |
| 错误码 | 404-无相关知识 | 删除 404 | V42 |
| suggestion | 静态字符串 | next_action 结构化 | V48 |

---

### 2.3 Tool 2：`write_knowledge`（🆕 V1.1 修订）

**功能**：AI 判断"这段对话值得记住"，主动调用写入。

```
Tool: write_knowledge
方向: AI → devContextMemo

Input:
  content      string  必填  知识正文（最大 10000 字符）
  session_id   string  必填  OpenCode session ID（来源追溯）
  Lx           string  可选  粒度 L0-L5，不填由系统推断
  Sy           string  可选  稳定性 S1-S5，不填由系统推断
  Depth        string  可选  认知深度 KW/KH/KY，不填由系统推断
  priority     string  可选  "normal" / "high"，默认 normal

⚡ 输入校验规则：
  • content 非空且长度 ≤ 10000 字符
  • content 仅做长度校验，不做内容过滤（质量由 Step 2 提炼 LLM 判断）

Output:
  {
    "task_id": "write-20260614-003",
    "status": "accepted",
    "message": "已入队，将在异步提炼后自动确认。task_id: write-20260614-003",
    "estimated_time": "pending (typically 30-120s, depends on LLM latency)"  🆕 V1.1（V47 修复）
  }

Error Codes:
  400 - content 为空
  400 - content 超过最大长度（10000 字符）
  400 - Lx/Sy/Depth 值非法
  409 - 相同 content 的写入任务已存在
  500 - 入队失败
```

**V1.0→V1.1 变更**：`estimated_time` 从 `"~30s"` → `"pending (typically 30-120s, depends on LLM latency)"`（V47）

---

### 2.4 Tool 3：`calibrate_knowledge`（🆕 V1.1 修订）

**功能**：系统/用户触发，检查知识是否过时。

```
Tool: calibrate_knowledge
方向: 双向（系统定时 + AI 主动）

Input:
  scope        string  可选  校准范围
                             格式: "all" / "domain:<name>" / "id:kw-<xxx>"
                             校验: 🆕 V1.1 独立正则（V44 修复）
  mode         string  可选  "quick"(仅 mtime) / "full"(代码验证)，默认 quick
  since        string  可选  仅校准该时间后未校验的知识，如"7d"

🆕 V1.1: scope 独立校验
  SCOPE_PATTERN = re.compile(r'^(all|domain:[a-z0-9_-]{1,64}|id:kw-[a-z0-9-]+)$')
  scope 不直接复用 domain 白名单正则——因为 "domain:auth" 含冒号

Output:
  {
    "stale_items": [
      {
        "id": "kw-20260601-002",
        "title": "OrderService 使用 Redis 缓存",
        "calibration_result": "stale",    🆕 V1.1: 原名 current_status（避免与 V2.0 status 混淆）
        "reason": "源文件已变更但知识未更新（src/OrderService.java mtime 变更）",
        "last_verified_at": "2026-06-01",
        "next_action": {                  🆕 V1.1: 结构化建议
          "tool": "dev review",
          "hint": "建议人工确认或运行 dev review 审核这条知识",
          "params_example": { "id": "kw-20260601-002" }
        }
      }
    ],
    "total_stale": 2,
    "total_checked": 156
  }

Error Codes:
  400 - scope 格式非法（不符合三种格式之一）
  400 - mode 非法
  500 - 校准服务异常
```

**V1.0→V1.1 变更**：`scope` 独立正则校验（V44）+ `current_status` → `calibration_result`（避免与 V2.0 status 混淆）+ `suggestion` → `next_action` 结构化（V48）

---

## 三、三 Tool 协作时序（🆕 V1.1 修订）

```
AI 想知道"鉴权怎么做的？"
        │
        ▼
    query_knowledge("鉴权", domain="auth")
        │
        ▼ 返回 [摘要1, 摘要2]
        │
    AI 觉得摘要 1 信息不够
        │
        ▼
    query_knowledge(id="kw-xxx", include_full=true)  ← 🆕 V1.1: 用 id 而非内联 filter
        │
        ▼ 返回完整正文 + code_verified + concept_tags
        │
    AI 发现问题——这份知识 3 周没校准了
        │
        ▼
    calibrate_knowledge(scope="id:kw-xxx", mode="quick")
        │
        ▼ 返回 {calibration_result: "stale", reason: "..."}
        │
    AI 告知用户："这份鉴权方案的知识可能过时了，建议确认"
```

---

## 四、与调研系统的差异对照

| 维度 | devContextMemo 的选择 | 理由 |
|------|------------------|------|
| **Tool 数量** | 3 个 | Phase 1 极简，够用即可 |
| **不做 CRUD 全套** | 无 update/delete/entities | 代码知识不需要实体管理，去重由系统自动做 |
| **异步写入** | ✅ 借鉴 OpenViking | 主流程不阻塞 |
| **分层返回** | ✅ 借鉴 OpenViking | Token 友好 |
| **校准独立** | ✅ 独有 | 其他系统无自动校准能力 |
| **不做目录浏览** | ❌ 无 list/traverse | devContextMemo 无 wing/room 结构，FTS5 检索即可 |

---

## 五、实施优先级

| 阶段 | 内容 | 产出 |
|:---:|------|------|
| **Week 4** | query_knowledge + write_knowledge 实现 | 读-写链路通 |
| **Week 5** | calibrate_knowledge 实现 | 校准链路通 |
| **Phase 2** | query_knowledge 支持向量检索 | pgvector 切换 |

---

## 六、MCP Server 安全配置

### 6.1 网络绑定

```
⚌ 强制绑定 127.0.0.1

禁止绑定 0.0.0.0 或外部 IP 地址。
devContextMemo 是本地开发工具，仅允许本机进程（AI 编程助手）连接。

FastMCP 启动配置：
  uvicorn.run(app, host="127.0.0.1", port=8910)

启动时校验：
  if config.mcp.host != "127.0.0.1":
      log.critical("Security: MCP host must be 127.0.0.1")
      sys.exit(1)
```

### 6.2 完整安全 Checklist

| # | 检查项 | 状态 | 说明 |
|---|--------|:---:|------|
| SEC-1 | MCP 绑定 127.0.0.1 | ✅ | 禁止外网访问 |
| SEC-2 | domain 参数白名单 | ✅ | `^[a-z0-9_-]{1,64}$` |
| SEC-3 | content 长度限制 | ✅ | ≤ 10000 字符 |
| SEC-4 | API Key 环境变量 | ⏳ 待编码 | 不硬编码、不写入日志 |
| SEC-5 | devContextMemo.db 文件权限 600 | ⏳ 待编码 | 仅所有者可读写 |
| SEC-6 | staging/*.jsonl .gitignore | ⏳ 待编码 | 敏感对话不入库 |

---

*设计完成时间：2026-06-14（V1.0）→ 2026-06-16（V1.1 修补）*
