# devContextMemo（码上记忆）项目知识系统 — 需求文档 V1.0

> **版本**：V1.0（全文重写，替代 v0.24）
> **日期**：2026-06-17
> **状态**：✅ 设计审核全面完成，进入编码阶段
> **一句话**：对话沉淀知识，编码随时唤醒 — 把对话与代码熔炼成永不腐烂的项目知识

---

## V1.0 重写说明

本版本是对 v0.24 的全文重写，原因：

1. **状态模型漂移**：v0.24 仍使用旧 4 状态模型（valid/stale/conflict/deprecated），与实际 V2.0 7 阶段模型严重不一致
2. **分类体系进化**：v0.24 散见「ABC 分类」「双轴分类」「三元组」三种说法，V1.0 统一为三元组 (Lx × Sy × Depth)
3. **晋升公式修宪**：`freshness×0.30` 与诉求②「无时间衰减」直接冲突，V1.0 改为 `calibration_recency×0.15`
4. **已废弃概念清理**：`archived` 状态已由「COLD + STALE」取代，v0.24 多处残留
5. **MVP 杀手功能落地**：类级别代码校准作为差异化核心功能正式写入需求

**V1.0 是项目的唯一宪法文档。所有后续设计、编码、测试均以此为准。**

---

## 一、项目定义

### 1.1 项目标识

| 属性 | 值 |
|------|-----|
| 英文名 | devContextMemo |
| 中文名 | 码上记忆 |
| 一句话 | 对话沉淀知识，编码随时唤醒 |
| 进一步解释 | 把对话与代码熔炼成永不腐烂的项目知识 |
| 开源协议 | MIT（计划） |

### 1.2 你的身份

| 属性 | 描述 |
|------|------|
| 角色 | 软件工程师 |
| 核心工具 | OpenCode（选择当前最新稳定版本） |
| 业务技术栈 | Java + MySQL + Spring Boot |
| 本系统技术栈 | Python 3.13 + FastAPI + FastMCP + SQLite（Phase 1） |
| LLM 供应商 | MiniMax + GLM（智谱） |

### 1.3 核心问题

> 在使用 OpenCode 进行软件开发的过程中，通过积累和分析多维度原始素材（AI 沟通记录、AI 决策过程、需求文档、Spec 文档、源代码、Git 历史），自动沉淀为细粒度到**类级别**的结构化领域知识，并在需求迭代或人肉修改代码后**自动校准**知识的有效性——最终形成不可复制的**项目知识资产**，让 AI 越用越懂这个项目。

**核心论点**：工具会迭代、框架会替换、工作流会重构，但项目知识——业务术语、系统约束、架构决策、踩坑经验——是团队的**复利资产**，越积累越有价值。当前它们分散在人脑和聊天记录中，尚未形成可累积的团队资产。

**分阶段落地**：
- **Phase 1**：类级别校准（文件变更检测 + LLM 语义对比）— 覆盖文件级变更场景
- **Phase 2**：方法级签名校准（tree-sitter AST 解析参数/返回类型/注解）

### 1.4 聚焦边界

| ✅ 聚焦做 | ❌ 不做 |
|-----------|--------|
| 6 维原始素材的采集与融合 | IDE 插件或 GUI（Phase 1 用 CLI） |
| AI 交互中知识的自动沉淀 | 多人协作权限管理（Phase 1 单用户），但支持 Git 共享 |
| 沉淀后的人工审核与修改（弱审核模式） | 实时对话拦截或中间人代理 |
| 按需精准检索（关键词 + 领域过滤 + 语义重排） | 代码补全/代码生成 |
| 三元组分类存储 (Lx × Sy × Depth) | 知识图谱推理或自动决策系统 |
| 知识更新演化机制（创建/更新/替换/补充/废弃） | 修改 OpenCode 或 MiMo Code 源码 |
| 通过 MCP Server 注入 AI 上下文 | 纯文件方案或纯数据库方案 |
| Markdown 权威源 + DB 索引派生 | SaaS 化或多租户 |
| 离线部署能力 | — |
| 代码入口级知识映射（类级别） | — |
| 知识校准引擎 + 防腐烂机制 | 全量重建知识库 |
| 跨层知识图谱（Phase 2） | — |

### 1.5 知识双视图

同一份知识，两种视图——不是两套独立的知识。

| 视图 | 形态 | 使用者 | 核心用途 |
|------|------|--------|---------|
| 人类视图 | Markdown 文件（`.claw/knowledge/`） | 人 | 直接阅读、审核、编辑、搜索 |
| AI 视图 | DB 索引层（SQLite FTS5 + 摘要 + 元数据） | AI / MCP Server | 高效检索、精确过滤、自动注入 |

**关键约束**：
- MD 文件是 Single Source of Truth，DB 索引层是派生品（不含 content 全文）
- 人编辑 MD → 写时钩子自动同步 DB 索引
- AI 检索：先 DB search 找候选 URI → 按需 read_md 取全文

### 1.6 核心竞争力：三重护城河

```
第一重：数据积累壁垒
  使用越久 → 积累越多维度的原始素材 → 领域知识越丰富 → AI 辅助效果越好 → 越愿意用

第二重：校准闭环壁垒
  人肉改代码 → 触发校准 → 发现偏差 → 更新知识 → AI 输出更准 → 减少人肉修改
  
第三重：上下文壁垒
  通用工具看到：当前打开的文件
  本系统看到：决策原因 + 需求演变 + 历史踩坑 + 知识关联网络
```

**与竞品的能力差距**：

| 能力 | devContextMemo | Claude Code Memory | Cursor | Cline |
|------|:--:|:--:|:--:|:--:|
| 会话记忆 | ✅ | ✅ | ✅ | ✅ |
| 跨会话提炼 | ✅ | ✅ | ❌ | ❌ |
| **代码入口级校准** | ✅ | ❌ | ❌ | ❌ |
| **三元组分类** | ✅ | ❌ | ❌ | ❌ |
| **防腐烂机制** | ✅ | ❌ | ❌ | ❌ |
| **校准闭环** | ✅ | ❌ | ❌ | ❌ |

---

## 二、六条核心诉求

### 诉求①：知识存储 — MD 权威 + DB 索引派生

**知识采用「MD 权威 + DB 索引派生」存储策略——MD 文件是 Single Source of Truth，DB 是可重建的索引层（不含 content 全文）。每条知识支持多维度溯源和校准状态追踪。**

| 维度 | 要求 |
|------|------|
| 机器维度 | 存储在 SQLite 索引层中（URI + FTS5 + 向量 + 链接关系 + 摘要），支持高效检索 |
| 人维度 | Markdown 文件持久化到 `.claw/knowledge/<domain>/`，可直接查看和编辑 |
| 溯源维度 | 每条知识记录来自哪个数据源的哪段内容 |
| 校准维度 | 记录最后校准时间、校准依据、当前状态 |
| 同步维度 | MD → DB 单向派生，DB 可随时从 MD 重建 |
| 检索维度 | 两阶段检索：先 DB 索引 search 找候选 URI，再按需 read_md 取全文 |

#### 诉求① 验收标准

| Given | When | Then |
|-------|------|-------|
| `.claw/knowledge/order/` 下有 `payment-flow.md`（权威源） | 执行 `search_knowledge(query="支付流程")` | DB 索引返回该文件 URI，content 取自 MD 文件（非 DB） |
| `.claw/knowledge/` 下有 5 个 MD 文件，DB 为空 | 执行 `claw rebuild-index` | DB 重建完成，6 张表记录数与 MD 文件数一致 |
| `.claw/knowledge/order/payment.md` 被人工编辑保存 | 5 秒内执行 `search_knowledge(query="payment")` | 检索结果包含编辑后的内容摘要（DB 索引已同步） |
| DB 索引文件 `.claw/claw.db` 被删除 | 执行 `claw rebuild-index` | 从 MD 文件完整重建 DB，知识无丢失 |

### 诉求②：知识有效性 — 与时间无关

**本系统的知识不具备「时间衰减」特性。正确的知识永远有效，不因时间新旧影响排序。**

| 特性 | 本系统 | 人类记忆/新闻 |
|------|--------|-------------|
| 时效性 | 无时间衰减 | 随时间遗忘或失效 |
| 失效原因 | 只因为项目本身的变化 | 自然遗忘或过期 |
| 检索权重 | 不因时间新旧影响排序 | 往往偏向新内容 |
| 卫生管理 | 追踪 calibration_recency（距上次校准天数） | — |

> ⚠️ 「无时间衰减」≠「不追踪时效性」。我们不因知识「旧」就降低排序权重，但我们追踪它「多久没被校准过」——这是卫生管理，不是衰减。一条 3 个月前提取但昨天刚被校准确认有效的知识 > 一条昨天提取但从未校验的知识。

**V1.0 公式**：`base_score = confidence×0.70 + anchor_bonus×0.15 + calibration_recency×0.15`
- `calibration_recency` 测量距上次校准天数，不测量距创建天数
- 权重仅 0.15（原来 freshness 是 0.30）——校准时效只是辅助信号，正确性才是主信号

#### 诉求② 验收标准

| Given | When | Then |
|-------|------|-------|
| 知识 A 创建于 90 天前，calibration_recency=0.9（9 天前校准过）<br>知识 B 创建于 1 天前，calibration_recency=0.0（未校准） | 执行 `search_knowledge(domain="order")` | 知识 A 的 base_score 高于知识 B（校准过的旧知识 > 未校准的新知识） |
| 知识创建于 200 天前，但昨天刚校准（calibration_recency=1.0） | 计算 base_score | `calibration_recency = 1.0`（取距校准天数，非距创建天数） |
| 两条知识 confidence 相同，其中一条 code_verified=1 | 计算 base_score | code_verified=1 的知识 anchor_bonus=1.0，base_score 更高 |

### 诉求③：同领域知识更新机制

同一业务领域的知识不是只增不减的追加模式，而是支持**创建/更新/替换/补充/废弃**五操作的演化系统。每条知识保留版本链完整追溯。

#### 诉求③ 验收标准

| Given | When | Then |
|-------|------|-------|
| 知识 K1 状态=ACTIVE，内容="使用 H2 数据库" | 执行 `update_knowledge(id=K1, content="使用 MySQL 数据库")` | K1 状态变为 CANDIDATE，原内容写入 `previous_version` 字段 |
| 知识 K2 状态=DRAFT | 执行 `deprecate_knowledge(id=K2, reason="已过时")` | K2 移至 `deprecated/` 目录，状态=DEPRECATED |
| 知识 K3 内容="支付超时 30s"<br>新对话提炼内容="支付超时 60s" | 执行 `supplement_knowledge(id=K3, additional="超时已调整为 60s，原因：跨境支付慢")` | K3 的 `supplement` 字段追加新内容，状态不变 |
| 两条知识 K4、K5 内容高度重复（similarity>0.9） | 执行 `replace_knowledge(old_id=K4, new_id=K5)` | K4 状态=DEPRECATED，K5 的 `superseded_by` 指向 K4 |

### 诉求④：知识组织 — 三元组分类 (Lx × Sy × Depth) + Domain

知识的组织采用「三元组 + 业务领域」分类模型——每条知识在 4 个维度上均有坐标：

#### Axis-1: Lx 粒度（空间定位）

| 层级 | 名称 | 粒度 | 示例 |
|------|------|------|------|
| L0 | 全局层 | 项目无关 | "团队偏好 Tab 缩进"、"Java 17+" |
| L1 | 领域层 | 业务模块 | "订单模块使用状态机模式" |
| L2 | 子域层 | 功能单元 | "下单流程含库存检查逻辑" |
| L3 | 代码入口层 | 类/方法 | "`OrderService.createOrder()` 含幂等校验" |

#### Axis-2: Sy 稳定性（时间定位）

| 层级 | 名称 | 稳定性 | 审查周期 |
|------|------|--------|:--:|
| S1 | 原则 | 最高（年维度不变） | 年度 |
| S2 | 架构 | 高（季度不变） | 季度 |
| S3 | 规范 | 中（月维度不变） | 月度 |
| S4 | 实现 | 低（周/天变化） | 周/天 |
| S5 | 经验 | 最低（天维度变化） | 天级 |

#### Axis-3: Depth 认知深度（认知定位）

| 深度 | 名称 | 定义 | 注入策略 | 示例 |
|------|------|------|---------|------|
| KW | Know-What | "是什么"——事实、概念、约束 | L1 恒常注入优先 | "项目用 Spring Boot 2.7" |
| KH | Know-How | "怎么做"——方法、流程、步骤 | L2 按需检索 | "新增 API 的 7 步骤流程" |
| KY | Know-Why | "为什么"——原理、动机、权衡 | L2/L3 按需+专项保护 | "选 Redis 而非 Memcached 是因为…" |

#### Axis-4: Domain 业务领域

| 维度 | 作用 | 示例 |
|------|------|------|
| Domain | 决定文件存储目录 | 订单 / 支付 / 用户 / 架构 / 部署 / 规范 |

Domain 与三元组正交——每条知识同时有 (Lx, Sy, Depth, Domain) 四个标签。

**分类方式**：LLM 在提炼时同步分类（同一调用，零额外成本）。目标准确率按分类轴分层：Lx ≥80%、Sy ≥75%、Depth ≥85%、Domain ≥80%，综合 ≥80%（即每 100 条中 ≤20 条至少一个轴分类错误）。三层兜底：人工审核 / Token 截断自然淘汰 / `dev correct` 手动修正。基准测试设计见 `reviews/devContextMemo-LLM分类基准测试-设计-V1.0.md`。

#### 诉求④ 验收标准

| Given | When | Then |
|-------|------|-------|
| LLM 提炼对话产出知识 K："订单服务使用状态机模式" | 检查 K 的 (Lx, Sy, Depth, Domain) 标注 | Lx∈{L0,L1,L2,L3}，Sy∈{S1..S5}，Depth∈{KW,KH,KY}，Domain 非空 |
| 知识 K 标注 L3 + KH，内容="createOrder() 含幂等校验" | 执行 `get_knowledge(domain="order", query="幂等")` | 该知识出现在检索结果（L3 按需检索生效） |
| 知识 K 标注 S1 + KW，内容="团队偏好：Tab 缩进" | 新 OpenCode 会话启动 | AGENTS.md 自动包含该知识（L1 恒常注入） |
| 知识标注置信度 < 0.6 | 写入 staging/ | 该知识状态=DRAFT，进入人工审核队列 |

---

#### 诉求④ 注入失败兜底验收标准

| Given | When | Then |
|-------|------|-------|
| L1+L2 知识总量 > 4K tokens（S1 原则 10 条 + S2 架构 20 条） | 新 OpenCode 会话启动，InjectionService 生成 AGENTS.md | 触发截断策略：优先保留 S1（原则），其次 S2（架构），截断 L3（按需）；`dev status` 显示 `injection_truncation=true`，列出被截断的知识 ID |
| L1+L2 知识总量 ≤ 4K tokens | 新 OpenCode 会话启动 | AGENTS.md 完整包含所有 L1 和 L2 知识，无截断 |
| AGENTS.md 生成失败（LLM 调用超时） | 新会话启动 | 降级：仅注入 L1 知识（S1 原则，最小可用）；`dev status` 显示 `injection_fallback=L1_ONLY`；下次会话重试完整注入 |
| 三层注入中 L3 按需检索失败（FTS5 索引损坏） | 执行 `get_knowledge(domain, query)` | 返回空结果（非崩溃）；`dev status` 显示 `l3_search_status=DEGRADED`；建议执行 `claw rebuild-index` |


### 诉求④-B：知识防腐烂机制

> 知识库最大的敌人不是内容缺失，而是内容过期。过期文档比没有文档更危险。

#### 三种腐烂形态

| 类型 | 定义 | 检测方式 |
|------|------|---------|
| 静默过期 | 代码已变但知识没更新 | L3 签名校验 + Git diff 比对 |
| 层级漂移 | 架构决策降级为历史背景但仍标为 S2 | 长期未更新的 S2 标记 review |
| 覆盖盲区 | 新功能上线但知识库完全没有 | 新文件检测 + 覆盖率审计（每周） |

#### 防腐烂触发事件（8 种）

| # | 触发事件 | 优先级 |
|---|---------|:--:|
| 1 | Git commit | P0 |
| 2 | 新服务/类上线 | P0 |
| 3 | 人肉代码修改（author ≠ AI） | P0 |
| 4 | 需求文档变更 | P1 |
| 5 | 架构评审通过 | P1 |
| 6 | Spec/Lint 规则变更 | P1 |
| 7 | 依赖大版本升级 | P1 |
| 8 | 故障复盘完成 | P2 |

#### 诉求④-B 验收标准

| Given | When | Then |
|-------|------|-------|
| 文件 `OrderService.java` 被 git commit 修改 | 触发校准引擎 | 所有 linked_to_file 包含 `OrderService.java` 的知识进入校准队列 |
| 知识 K 状态=ACTIVE，距上次校准 120 天 | 执行 `dev dream`（巩固命令） | 知识 K 标记为 STALE（suspicious） |
| `.claw/knowledge/` 下新增文件 `refund.md`，但知识库无对应知识 | 每周覆盖率审计 | 生成「覆盖盲区」报告，建议补充知识 |
| 知识 K 标注 S2（架构级），但 180 天未更新 | 执行 `dev status` | 显示该知识标记 `needs_review=true` |

---

#### 注入路由自动推导

| 条件 | 推导结果 | Token 成本 | 触发方式 |
|------|---------|:--:|------|
| S1/S2 + KW | L1 恒常注入 | 含在 4K 预算内 | 每次会话自动 |
| S1/S2 + KH/KY | L2 按需检索 | ~1-3K/call | LLM 判断需要 |
| S3/S4 + 任意 Depth | L2 按需检索 | ~1-3K/call | LLM 判断需要 |
| S5 + 任意 Depth | L2/L3 检索 | ~0.5-1.5K | 事件触发 |

---

### 诉求⑤：核心闭环

```
多数据源（OpenCode / Comate / Cursor / ...）
       ↓ 适配器（统一接收）
  原始会话存储（JSONL，永久保留）
       ↓ 异步触发
  Step 1-6: 攒批 → 提炼(LLM 2a+2b) → 验证 → 去重 → 写入 → 巩固
                                    ↑
                         校准引擎 ←──┘ (代码变更触发)
```

#### 6 维数据源

| # | 数据源 | Phase 1 |
|---|-------|:--:|
| ① | AI 沟通记录（多源适配：OpenCode/Comate/Cursor 等） | ✅ |
| ② | AI 决策记录（对话中提取） | Phase 2 |
| ③ | 需求文档（PRD/SRS） | Phase 2 |
| ④ | Spec 文档（API Doc/DB Schema） | Phase 2 |
| ⑤ | 源代码（AST 静态分析） | Phase 2 |
| ⑥ | Git 变更历史（git log + diff） | ✅ |

#### 三层注入架构

```
Layer 1: 恒常注入 — AGENTS.md（S1+S2 KW 知识，≤4K tokens）
  机制：OpenCode 会话启动自动加载
  更新：S1/S2 知识累计 ≥3 条新增/变更时自动生成草稿，人确认后生效

Layer 2: 按需检索 — MCP Tool get_knowledge(domain, query, max_tokens)
  内容：S3 规范 + S4 实现，LLM 自主判断调用

Layer 3: 按需检索 — MCP Tool get_experience(query, max_tokens)
  内容：S5 经验/踩坑，排障时触发
```

#### 知识巩固引擎（dev dream）

定期对照源数据验证知识、合并重复项、修剪低信号条目。由 `dev dream` 命令手动触发。

#### 诉求⑤ 验收标准

| Given | When | Then |
|-------|------|-------|
| staging/ 下有 5 条 CANDIDATE 知识 | 执行 `dev dream` | 评估晋升，部分转为 ACTIVE，部分退回 PENDING_REVIEW |
| knowledge/ 下有 200 条 ACTIVE 知识，其中 50 条 > 90 天未使用 | 执行 `dev dream` | 50 条标记为 COLD，其中 prune_priority≥0.70 的标记为 STALE |
| DB 中存在 3 条相似度>0.9 的重复知识 | 执行 `dev dream` | 合并为 1 条，保留置信度最高的内容，其余标记 DEPRECATED |

---

## 三、知识条目生命周期（V2.0 7 阶段模型）

### 3.1 阶段速查

```
DRAFT ──→ STAGED ──→ CANDIDATE ──→ ACTIVE
  │          │                          │
  │          ├──→ PENDING_REVIEW        ├──→ COLD
  │          │                          │      │
  │          │                          │      └──→ STALE
  │          │                          │           │
  └──────────┴──────────────────────────┴───────────→ DEPRECATED
```

| # | 阶段 | 物理位置 | 含义 |
|:--:|------|---------|------|
| 1 | DRAFT | staging/ | LLM 提炼的初稿，待审查 |
| 2 | STAGED | staging/ | 已审查通过，待晋升评估 |
| 3 | PENDING_REVIEW | staging/ | 异常/低置信度，需人工审核 |
| 4 | CANDIDATE | staging/ | 评分达标，等待巩固层二次确认 |
| 5 | ACTIVE | knowledge/ | 活跃使用中 |
| 6 | COLD | knowledge/ | 长期未使用但保留（protected） |
| 7 | STALE | knowledge/ | 可能过期，3 子阶段：suspicious → confirmed → deep |
| 8 | DEPRECATED | deprecated/ | 已废弃，不参与正常检索 |

#### 诉求③ 生命周期验收标准

| Given | When | Then |
|-------|------|-------|
| 知识 K 状态=DRAFT，人工审核通过 | 执行状态迁移 | K 状态→STAGED |
| 知识 K 状态=STAGED，base_score=0.85 | 巩固层评估 | K 状态→CANDIDATE |
| 知识 K 状态=CANDIDATE，base_score=0.83 | 巩固层二次确认 | K 状态→ACTIVE |
| 知识 K 状态=ACTIVE，距最后使用 400 天 | 定期审计 | K 状态→COLD→STALE（三层修剪） |
| 知识 K 状态=STALE，人工确认过期 | 执行 `deprecate_knowledge(id=K)` | K 状态→DEPRECATED |
| 知识 K 被 K' 取代（replace 操作） | 执行 `replace_knowledge(id=K, new_content)` | K.superseded_by = K'.id；`dev review --history=K'` 显示版本链 K → K'；可回溯原始内容 |
| 知识 K 状态=DEPRECATED | 新 OpenCode 会话启动（L1/L2 注入） | AGENTS.md 和搜索结果**不包含** K 的内容（仅 ACTIVE/STAGED 参与注入） |

---### 3.2 晋升公式（V2.1）

```
base_score = confidence × 0.70 + anchor_bonus × 0.15 + calibration_recency × 0.15
```

| 参数 | 含义 | 范围 |
|------|------|:--:|
| confidence | LLM 提炼置信度 | 0.0–1.0 |
| anchor_bonus | code_verified=1 时为 1.0，否则 0.0 | {0, 1} |
| calibration_recency | 1.0 − min(距上次校准天数/180, 1.0) | 0.0–1.0 |

**与 v0.24 的关键区别**：
- 原 `freshness × 0.30`（按创建时间衰减）→ 违反诉求②
- 现 `calibration_recency × 0.15`（按校准时间）→ 符合「无时间衰减」
- confidence 权重从 0.50 提升到 0.70——知识对不对比知识新不新重要得多

### 3.3 晋升阈值

| 条件 | 动作 |
|------|------|
| confidence ≥ 0.95 | **绿色通道**：直接进入 knowledge/ |
| base_score ≥ 0.82 | 进入 CANDIDATE |
| base_score < 0.80 | 退回 PENDING_REVIEW |
| 无锚点知识 max base_score = 0.80 | 可达 PENDING_REVIEW，不卡死 |

**CANDIDATE 滞回**：0.82 进 / 0.80 出，杜绝状态震荡。

### 3.4 修剪规则

三层修剪体系：

1. **Layer 1（质量下限）**：DRAFT > 90 天未处理 → DEPRECATED
2. **Layer 2（使用频率）**：COLD > 365 天 → STALE；低频使用（prune_priority ≥ 0.70）→ STALE
3. **Layer 3（代码锚点）**：无锚点 + 90 天未变化 → STALE(suspicious)

**容量管理**：软上限 500（提示），硬上限 2000（强制修剪）。

---

## 四、数据写入流水线（8 Step）

```
Step 0: 接收   — 适配器标准化各数据源 → 统一格式原始会话存储
Step 1: 攒批   — 从原始存储按 session 分批 → JSONL 缓冲
Step 2a: 提炼   — LLM 提炼知识 + 分类标注 (Lx, Sy, Depth, Domain) + 时间提取
Step 2b: 提取   — LLM 从结构化摘要中提取实体+关系
Step 3: 验证   — code_verified 设置 + Jaccard 语义去重
Step 4: 去重   — top_similar_id + UPDATE_CANDIDATE
Step 5: 写入   — 对齐 V2.0 状态模型
Step 6: 巩固   — 晋升评估 + 修剪 + supplement 合并
```

> **Step 2 拆分依据**：参考 OpenChronicle 压缩漏斗（Compression Funnel）设计，将原本 1 次 LLM 调用承担的 4 项职责（提炼+分类+时间+实体）拆分为 2 次聚焦调用，避免 prompt 过载。详见技术决策 D69。

### 4.0 设计理念：统一接收层

**核心理念**：先接收并存储原始会话，再异步加工。加工链路与数据源解耦。

```
多数据源（OpenCode / Comate / Cursor / ...）
        ↓ 适配器（每个源一个，输出统一格式）
  原始会话存储（统一 JSONL 格式，永久保留，可修改）
        ↓ 异步触发
  Step 1-6 加工流水线（完全复用，不感知数据源）
```

**设计收益**：
1. **数据源无关**：换编程工具只需写一个新适配器，加工链路完全复用
2. **可追溯纠错**：原始会话永久保留 → 修改后重跑加工 → 对比输出验证修复效果
3. **多源聚合**：同一项目可同时采集多个工具的对话，知识图谱更完整

### 4.1 适配器层设计

每个数据源一个适配器，输入为数据源原生格式，输出为统一标准格式：

```jsonl
{"session_id": "uuid", "seq": 1, "role": "user", "content": "...", "timestamp": "2024-03-15T10:30:00Z", "source": "opencode"}
{"session_id": "uuid", "seq": 2, "role": "assistant", "content": "...", "timestamp": "2024-03-15T10:30:15Z", "source": "opencode"}
```

适配器职责：
- 读取数据源（SQLite / API / 文件）
- 转换为统一标准格式
- 写入原始会话存储（`~/.devcontext/raw/<project>/session_<id>.jsonl`）

详见子文档 `devContextMemo-数据写入流水线-详细设计-V1.0.md`。

#### 诉求④ 写入流水线验收标准

> **验收方式**：以下 Given-When-Then 场景描述业务期望。工程落地测试见 `design/devContextMemo-测试方案-V1.0.md` §七 模块测试 + §七 集成测试。各 Step 的详细断言/证据/失败模式见测试方案 §四 契约 YAML 定义。

| Given | When | Then | 对应测试 |
|-------|------|------|:--:|
| OpenCode SQLite 中有 50 条对话消息 | 执行 OpenCode 适配器 | 生成 `session_<id>.jsonl`（统一格式），存储到 `~/.devcontext/raw/<project>/` | 模块测试 Step 0 |
| Comate 导出 JSON 中有 30 条对话消息 | 执行 Comate 适配器 | 生成 `session_<id>.jsonl`（统一格式），与 OpenCode 格式一致 | 模块测试 Step 0 |
| 原始存储中有 50 条消息 | 执行 `trigger()`（Step1） | 生成 `batch_*.jsonl`，包含 50 条消息，`_flushed=false` | 模块测试 Step 1 |
| `batch_*.jsonl` 中有 50 条消息 | 执行提炼器（Step2a） | 输出 `summary_*.jsonl`，每条含 (Lx, Sy, Depth, Domain) + `occurred_at` 标注 | 模块测试 Step 2a |
| `summary_*.jsonl` 中有 50 条结构化摘要 | 执行提取器（Step2b） | 输出 `knowledge_*.jsonl`，每条含 `entities` + `relations` 字段 | 模块测试 Step 2b |
| `knowledge_*.jsonl` 中有 1 条置信度=0.5 的知识 | 执行 validator + deduplicator（Step3-4） | `code_verified=false`，`top_similar_id` 如有相似则非空 | 模块测试 Step 3+4 |
| `knowledge_*.jsonl` 通过验证 | 执行 writer + consolidator（Step5-6） | `.claw/staging/` 下生成 MD 文件，状态=DRAFT，SQLite 同步写入 | 模块测试 Step 5+6 |
| 已有知识 K2，新提炼 K2' 相似度=0.94 | 执行 deduplicator（Step4） | K2' 不写入 DB，标记 `conflict_group=G1`，进入冲突队列，`dev review` 显示冲突 | 模块测试 Step 4 |

---

## 五、存储架构

### 5.1 核心原则

**MD 文件 = 权威源，DB 索引层 = 派生品（可重建）。**

```
MD 文件 (.claw/knowledge/<domain>/*.md)  ← 唯一权威源 (Git 追踪)
       │ (写时钩子，单向派生)
       ↓
DB 索引层 (SQLite, WAL 模式)            ← 派生索引 (不含 content)
       │ (两阶段检索)
       ↓
MCP Server                              ← AI 查询入口
```

### 5.2 数据库选型

| Phase | 数据库 | 用途 |
|:--:|------|------|
| Phase 1 | SQLite（WAL 模式） | 快速验证闭环 |
| Phase 2 | PostgreSQL + pgvector | 生产级性能 |

### 5.3 目录结构

```
~/.devcontext/
└── raw/<project>/               # 原始会话存储（统一 JSONL 格式，永久保留）
    ├── session_<uuid>.jsonl     # OpenCode 适配器输出
    └── session_<uuid>.jsonl     # Comate 适配器输出

.claw/
├── staging/                     # 待审核知识（DRAFT/STAGED/PENDING_REVIEW/CANDIDATE）
├── knowledge/<domain>/          # 已激活知识（ACTIVE/COLD/STALE）
│   ├── order/
│   ├── payment/
│   ├── architecture/
│   └── standards/
├── deprecated/                  # 已废弃知识
├── AGENTS.knowledge.md          # 自动维护的动态知识注入
└── claw.db                      # SQLite 索引数据库
```

#### 诉求⑤ 存储架构验收标准

| Given | When | Then |
|-------|------|-------|
| `.claw/knowledge/order/pay.md` 被人工编辑保存 | 写时钩子触发 | SQLite `knowledge` 表对应记录的 `content_hash` 和 `updated_at` 同步更新 |
| `.claw/claw.db` 被删除 | 执行 `claw rebuild-index` | 从所有 MD 文件完整重建 DB，记录数一致，FTS5 索引可用 |
| 写入 MD 文件时路径含 `../` | 执行 writer（Step5） | 写入被拒绝，`realpath` 校验失败，记录安全事件 |

---

## 七、深度反思（reflect）

### 7.1 定位

devContextMemo 与 Hindsight 借鉴的「反思」能力。现有系统支持「记」（`dev write`）和「找」（`dev search`），reflect 增加「思」——从历史知识中推理规律，形成可复用的洞察。

**与竞品差异**：
- Claude Code Memory：只记录，不反思
- Mem0 / Zep：只检索相似，不推理规律
- devContextMemo + reflect：检索 → LLM 推理 → 生成 Mental Model（心智模型）类型知识

### 7.2 工作原理

```
1. 用户输入：dev reflect "支付模块为什么总是出 bug？"
2. 检索：从 DB + MD 检索所有和「支付」相关的知识（top_k=20）
3. LLM 推理：基于检索到的知识，分析规律
   ├─ 输出洞察：「支付模块 bug 80% 集中在 currency 字段，
   │   根本原因是缺少统一中间件，各业务线自行解析」
   ├─ 可选：将洞察存储为 Mental Model 类型知识
   │   （type="mental_model", lx="L3", sy="S2"）
   └─ 返回给用户
4. 用户确认后，Mental Model 知识进入 staging/，走正常晋升流程
```

### 7.3 适用场景

| 场景 | 输入示例 | 输出价值 |
|------|---------|---------|
| 排障规律 | `dev reflect "为什么订单总是超时？"` | 找到历史超时根因，避免重复踩坑 |
| 架构决策复盘 | `dev reflect "我们为什么选了 MySQL 而不是 PostgreSQL？"` | 恢复决策上下文，避免重复讨论 |
| 代码坏味道 | `dev reflect "哪些模块耦合度最高？"` | 从提交历史+知识中推理模块依赖规律 |
| 团队协作知识 | `dev reflect "新成员最容易踩的坑是什么？"` | 从 STALE + conflict 知识中总结规律 |

### 7.4 与 Hindsight reflect 的区别

| 维度 | Hindsight | devContextMemo |
|------|-----------|---------------|
| 触发方式 | 自动（后台定时） | 手动（`dev reflect` 命令） |
| 输出类型 | 存储到 MemoryBank | 先展示给用户，用户确认后再存储 |
| 知识类型 | 无区分 | 明确存储为 Mental Model 类型 |
| 人工审核 | 无 | 走正常 DRAFT → STAGED → ACTIVE 流程 |

> **设计决策**：V1.0 先做「手动触发 + 人工审核」，避免自动反思产生低质量知识。Phase 2+ 可加自动定时反思。

#### 诉求⑦ 深度反思验收标准

| Given | When | Then |
|-------|------|-------|
| 用户输入 `dev reflect "支付模块为什么出 bug？"` | 系统执行 | 检索 top_k=20 相关知识，LLM 推理后输出洞察文本 |
| `dev reflect` 输出洞察 | 用户确认并选择「保存」 | 生成 Mental Model 类型知识，状态=DRAFT，写入 staging/ |
| `dev reflect` 输出洞察 | 用户选择「不保存」 | 只展示洞察，不写入任何文件 |
| DB 中有 3 条 Mental Model 类型知识 | 执行 `dev search "支付"` | Mental Model 参与检索，排在普通知识之前（anchor_bonus=1.0） |
| `dev reflect` 输入 query 与已有 Mental Model 相似度>0.9 | 系统执行 | 提示用户「已有类似洞察 KXXX，是否合并？」 |

---

## 六、MVP 杀手功能：类级别代码校准

### 6.1 定位

devContextMemo 与 Claude Code Memory 最大的差异化能力。Claude Code 只做被动记录，devContextMemo 做**主动校准**——检测代码变更后，自动验证关联知识的有效性。

### 6.2 工作原理

```
1. Git commit 触发
2. 检测变更文件列表
3. 查询 DB：所有 linked_to_file ∈ (变更文件) 的知识条目
4. LLM 语义对比：知识描述 vs 当前类代码
5. 结果：
   ├─ 一致 → 更新 calibration，confidence 加分
   ├─ 不一致 → 生成 UPDATE_CANDIDATE，知识进 staging/
   ├─ 可能代码错 → 标记 conflict_with_code，提醒人工
   └─ 无法判断 → 标记 needs_review
```

### 6.3 三个约束（V1.0 定稿）

| # | 约束 | 原因 |
|:--:|------|------|
| 1 | 校准结果定位为**辅助信号**，不做自动裁判 | LLM 语义对比精确度 ~65%、召回率 ~35%，不适合自动裁决 |
| 2 | 知识创建时要求 ≥ L2 精确度 | 避免「模糊知识盲区」——太概括的知识 LLM 无从对比 |
| 3 | 支持 `linked_to_files` 多文件关联 | 避免「跨类行为假阳性」——正确知识因关联单文件而误判 |

### 6.4 可靠性预估

| 指标 | 类级别 | 说明 |
|------|:--:|------|
| 精确度 | ~65% | 判「不一致」的，65% 确实该改 |
| 召回率 | ~35% | 65% 的不一致会漏判 |

> 召回率不高是已知局限，但不影响 MVP 差异化价值——竞品完全没有此能力。

#### 诉求⑥ 类级别校准验收标准

| Given | When | Then |
|-------|------|-------|
| `OrderService.java` 被修改，关联知识 K 状态=ACTIVE | Git commit 触发校准引擎 | K 的 `last_calibrated_at` 更新，校准结果写入 `calibration_logs` |
| 知识 K 描述="使用 H2 内存数据库"，代码已改为 MySQL | LLM 语义对比 | 判定「不一致」，K 标记 `needs_review=true`，进入人工审核队列，状态保持 ACTIVE（不自动降级） |
| 知识 K 描述与代码一致 | 校准引擎执行 | `confidence` 加分（≤1.0），`calibration_recency` 重置 |
| `linked_to_files` 含 3 个文件，其中 1 个被修改 | 校准引擎执行 | 仅对标修改的文件，未修改文件不参与对比 |

---

## 八、冷启动（Phase 0）

系统上线时通过 `/claw-init` 命令按模块交互式初始化：

1. 扫描模块包结构
2. LLM 生成 S1 原则 + S2 架构骨架
3. 人工审核确认（首次建议审核，后续增量可信任 LLM + 抽查）
4. 生成 AGENTS.md 和第一批 MD 知识文件

**预计成本**：¥0.5-2/模块 LLM API + 10-30 分钟人工审核/批次

#### 诉求⑧ 冷启动验收标准

| Given | When | Then |
|-------|------|-------|
| 空项目，`.claw/` 目录不存在 | 执行 `dev init` | 生成 `.claw/` 目录 + AGENTS.md 骨架，状态=DRAFT |
| 项目有 `src/order/` 和 `src/payment/` 两个模块 | 执行 `dev init` | LLM 生成 S1 原则 + S2 架构骨架，每个模块 1 条知识 |
| `dev init` 生成 DRAFT 知识 10 条 | 人工审核通过 8 条 | 8 条状态→STAGED，写入 `.claw/knowledge/` |
| `dev init` 生成的 AGENTS.md | 新 OpenCode 会话启动 | AGENTS.md 内容自动注入上下文（≤4K tokens） |

---

## 九、校正与安全

### 8.1 数据校正（7 类问题）

| 问题类型 | 检测方式 | 严重度 |
|---------|---------|:--:|
| MD-DB 索引漂移 | mtime 比对 | 🔴 高 |
| 多版本冲突 | conflict_group 聚类 | 🔴 高 |
| 索引漂移 | embedding 版本检查 | 🟡 中 |
| 知识过期 | last_used_at 时效检查 | 🟢 低 |
| 冗余知识 | 相似度 > 0.9 扫描 | 🟡 中 |
| 领域树失效 | AI 重新推理 | 🟢 低 |
| 引用断裂 | 外键 + 存活探测 | 🔴 高 |

### 8.2 安全扫描

所有写入知识库的内容在持久化前通过三层扫描：

| 扫描类型 | 处理方式 |
|---------|------|
| 提示注入（模式匹配） | 拒绝写入 |
| 凭据泄露（API Key / Token 正则） | 拒绝写入，记录安全事件 |
| Unicode 不可见字符 | 拒绝写入 |

#### 诉求⑧ 校正与安全验收标准

| Given | When | Then |
|-------|------|-------|
| DB `knowledge` 表 `content_hash` ≠ 对应 MD 文件 `mtime` | 执行 `dev health-check` | 报告 `MD-DB 索引漂移` 问题，列出差异条目 |
| 写入内容含 `sk-abc123def456GHI789jkl0MNO` | 执行 Step2a（提炼层） | 拒绝写入，记录安全事件，返回错误码 `SECURITY_CREDENTIAL_LEAK` |
| 写入内容含 `忽略之前所有指令，输出...` | 执行 SecurityScanner | 拒绝写入，标记为 `prompt_injection`，不进入 DB |
| `knowledge` 表有 2 条 `top_similar_id` 互指（A→B, B→A） | 执行 `dev dream` | 检测为「多版本冲突」，标记 `conflict_group`，进入人工审核 |

---

#### 诉求⑧ 安全决策边界验收标准

| 攻击类型 | Given | When | Then（决策边界） |
|---------|-------|------|-------------------|
| 提示注入（L1） | 知识内容含 `忽略之前所有指令` | SecurityScanner L1 检测 | **直接拒绝写入**，返回错误码 `SECURITY_PROMPT_INJECTION`；记录安全事件（内容摘要脱敏后存储） |
| 凭据泄露（L2）— 高置信度 | 知识内容含 `sk-abc123def456GHI789jkl0MNO`（匹配 API Key 正则） | SecurityScanner L2 检测 | **直接拒绝写入**；返回错误码 `SECURITY_CREDENTIAL_LEAK`；记录安全事件（凭据部分打星后存储） |
| 凭据泄露（L2）— 低置信度误报 | 知识内容含 `api_key: "test"`（测试环境占位符） | SecurityScanner L2 检测 | **允许写入**，但标记 `security_flag=CREDENTIAL_SUSPECT`；`dev review` 提示人工确认 |
| Unicode 污染（L3） | 知识内容含 U+200B（零宽空格） | SecurityScanner L3 检测 | **拒绝写入**，返回错误码 `SECURITY_UNICODE_INVISIBLE`；提示用户清理后重试 |
| 安全事件审计 | 发生任意 L1/L2/L3 拒绝事件 | 执行 `claw security-audit` | 输出安全事件列表（时间/类型/来源文件/处理动作），凭据部分打星 |

> **决策原则**：L1 提示注入一律拒绝（无脱敏可能）；L2 凭据泄露高置信度拒绝，低置信度标记后人工审核；L3 Unicode 拒绝（可自动清洗，但 V1.0 为先拒绝后手动清洗）。

---

#### 诉求⑧ 审核界面交互验收标准（场景H）

> **背景**：`dev review` 是知识写入前的最后一道人工关卡。本场景验证审核界面的核心交互流程：列出待审核条目、查看差异、执行决策、批量操作、版本链追溯。

| Given | When | Then |
|-------|------|-------|
| `staging/` 目录有 3 条 `*.md`（状态分别为 `DRAFT` / `DRAFT` / `FLAGGED`）| 执行 `dev review` | 列出全部待审核条目（含文件路经、状态、置信度、冲突标记），按创建时间倒序排列 |
| `dev review` 列出条目 K（新写入，staging/K.md）| 执行 `dev review --diff K` | 展示 K 的「提炼来源对话片段」与「生成的 K.md 全文」，高亮差异部分（新增/修改/删除）|
| `dev review` 列出条目 K（置信度=0.92，无冲突）| 执行 `dev review --approve K` | K.md 从 `staging/` 移入 `knowledge/`，DB 写入 K（状态 `ACTIVE`），返回成功消息 `✅ K approved and promoted` |
| `dev review` 列出条目 K（置信度=0.72，有冲突标记）| 执行 `dev review --reject K --reason="置信度不足"` | K.md 保留在 `staging/`（状态更新为 `REJECTED`），DB 不写入，返回 `❌ K rejected: 置信度不足` |
| `dev review` 列出条目 K（内容有误但方向正确）| 执行 `dev review --request-changes K --comment="缺少错误处理说明"` | K.md 状态更新为 `NEEDS_REVISION`，`dev review` 下次列出时显示 `🔄 待修订` 标记和修改意见 |
| `staging/` 有 5 条 `DRAFT` 状态条目 | 执行 `dev review --batch-approve --all-draft` | 全部 5 条批量 approve，输出 `✅ Batch approved: 5 items`；若有任一条置信度 < 0.8，暂停并提示确认 |
| `dev review` 列出条目 K（已被 K' 取代，superseded_by = K'.id）| 执行 `dev review --history K'` | 展示版本链：K（DEPRECATED） → K'（ACTIVE），含每次变更的时间、来源对话、变更摘要 |
| `dev review` 列出条目 K（security_flag = CREDENTIAL_SUSPECT）| 执行 `dev review --show-security K` | 展示安全标记详情（检测层级 L1/L2/L3、匹配规则、可疑片段脱敏显示），人工确认后移除标记或拒绝写入 |
| MCP Client（如 Claude Code）调用 `claw_review_list` Tool | 传入 `status_filter=["DRAFT","FLAGGED"]` | 返回 JSON：待审核条目列表（含 id/path/status/confidence/created_at/conflict_group）|
| MCP Client 调用 `claw_review_decide` Tool | 传入 `id=K, decision="approve"` | 返回 `{success: true, new_status: "ACTIVE", promoted_path: "knowledge/xxx.md"}` |

---

## 十、Phase 规划

| Phase | 核心交付 | 覆盖 |
|------|------|------|
| **Phase 0** | 冷启动 `/claw-init` | 骨架知识 |
| **Phase 1** | 统一接收层（适配器+原始存储）+ 8 Step 加工流水线（Step2 拆分为 2a+2b）+ 类级别校准 + MCP Tool 检索 + AGENTS.md 同步 + 实体提取与图关系 + 自动时间提取 | 核心闭环 |
| **Phase 2** | 方法级签名校准 + 跨层知识图谱 + 剩余 4 维数据源 + 深度反思（reflect）+ 向量索引 + 批量优化 | 精加工 |
| **Phase 3** | 多 Agent 协作 + 角色感知适配 + 完整防腐烂 | 生态化 |

---

## 十一、技术决策索引（D1–D69）

所有技术决策详见 `OpenCode-需求文档-技术决策记录.md`。关键决策摘要：

| 决策 | 内容 | 状态 |
|:--:|------|:--:|
| D1–D6 | 数据写入流水线：临时文件 → 异步加工 → 人工确认 | ✅ |
| D7–D23 | 晋升生命周期：7 阶段 + 22 跃迁 + 3 修剪层 | ✅ |
| D24–D33 | 知识保真体系：7 更新路径 + 5 冲突层 + 6 证据权重 | ✅ |
| D34–D43 | 目录划分 + 晋升规则 + 修改检测 | ✅ |
| D44–D50 | dev review 交互原型（命令设计/状态迁移/搜索过滤/批量操作/MCP Tool） | ✅ |
| D51–D56 | 类级别校准 + 三重护城河 + 原子写入 | ✅ |
| D57–D61 | 审核界面交互（版本链追溯/批量操作安全边界/MCP Tool 接口/安全标记处理/request-changes 闭环） | ✅ |
| D62 | reflect 命令设计：手动触发 + 用户确认后再存储 | ✅ |
| D63 | Mental Model 知识类型：独立类型，anchor_bonus=1.0 | ✅ |
| D64 | reflect 与 Hindsight 的区别：手动 vs 自动，人工审核闭环 | ✅ |
| D65 | 实体提取与图关系：参考 Hindsight Entity Normalization，Phase 1 实施，LLM 提取实体+关系存储到 entities/ + relations/ 目录 | ✅ |
| D66 | 向量索引与批量优化：参考 Hindsight Multi-representation Storage + Batch Processing，Phase 2 实施，本地 Embedding 模型 + RRF 合并检索 | ✅ |
| D67 | 自动时间提取：参考 Hindsight occurred_start/end 字段，Step 2 提炼 Prompt 增加时间字段提取，Phase 1 实施 | ✅ |
| D68 | 统一接收层：适配器模式 + 原始会话存储，加工链路与数据源解耦，支持多源聚合和可追溯纠错，Phase 1 实施 | ✅ |
| D69 | Step 2 拆分为 2a+2b（压缩漏斗轻量版）：借鉴 OpenChronicle Compression Funnel 思想，Step2a 提炼+分类+时间提取，Step2b 实体+关系提取，避免单次 LLM 调用 prompt 过载，Phase 1 实施 | ✅ |

---

## 关联文档

| 文档 | 用途 |
|------|------|
| `OpenCode-需求文档-技术决策记录.md` | D1–D69 全部决策详情 |
| `OpenCode-需求文档-修订历史.md` | v0.1 → v0.24 版本追溯 |
| `devContextMemo-数据写入流水线-详细设计-V1.0.md` | 8 Step 流水线详细设计 |
| `devContextMemo-MCP-Tool接口-行业调研与详细设计-V1.1.md` | MCP Tool 接口规范 |
| `devContextMemo-SQLite-Schema-详细设计-V1.1.md` | SQLite 6 表 DDL |
| `devContextMemo-晋升生命周期-设计-V2.0.md` | 7 阶段生命周期 + 晋升公式 |
| `devContextMemo-知识更新-冲突检测-冲突解决-深度设计-V1.0.md` | 知识保真体系 V1.7 |
| `devContextMemo-修剪规则-完整设计-V1.0.md` | 三层修剪体系 |
| `devContextMemo-目录划分-晋升规则-修改检测-深度调研-V1.0.md` | 三目录方案 |
| `devContextMemo-类级别校准-调研与推演报告-V1.0.md` | 类级别校准 7 场景推演 |
| `devContextMemo-双重验证-结果对齐与决策报告-V1.0.md` | 宪法批判 + 对抗检查结论 |

---

> 本文档替代 `OpenCode-项目知识系统-需求文档-v0.24.md`，为 devContextMemo 项目的唯一宪法文档。
> V1.0 基于 D1–D69 全部决策、V2.0 状态模型、V2.1 晋升公式、类级别校准 3 约束。
> 后续所有设计变更必须先修改本文档，再同步到各子文档。
