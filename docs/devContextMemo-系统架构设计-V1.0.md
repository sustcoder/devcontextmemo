# devContextMemo 系统架构设计 V1.0

> **日期**：2026-06-17
> **状态**：编码实现前最后一轮设计交付
> **关联文档**：需求文档 V1.0、决策总账 V1.0、数据写入流水线详细设计 V1.0

---

## 一、系统分层架构

devContextMemo 采用七层架构，从上到下：

```
┌──────────────────────────────────────────────────────────┐
│                    交互层 (Interaction Layer)             │
│    MCP Server │ REST API │ CLI (init/review/dream/status) │
├──────────────────────────────────────────────────────────┤
│                    服务层 (Service Layer)                 │
│  知识检索 │ 流水线编排 │ 审核流程 │ 主动扫描 │ 知识注入   │
├──────────────────────────────────────────────────────────┤
│                  管理引擎层 (Management Engine)            │
│  晋升评估│修剪规则│冲突检测│校准引擎│冷启动│数据健康│
├──────────────────────────────────────────────────────────┤
│                    存储层 (Storage Layer)                  │
│  MD 文件操作 │ SQLite 索引 │ FTS5 搜索 │ 原子写入          │
├──────────────────────────────────────────────────────────┤
│                   处理层 (Processing Layer)                │
│  攒批 │ 提炼 │ 实体提取 │ 关系提取 │ 验证 │ 去重 │ 签名   │
├──────────────────────────────────────────────────────────┤
│                    接收层 (Receiver Layer)                 │
│  适配器 │ 统一格式标准化 │ 原始会话存储 │ 多源聚合        │
├──────────────────────────────────────────────────────────┤
│                   基础设施层 (Infrastructure)              │
│  配置管理│LLM API│日志│监控│进程管理│安全扫描│
└──────────────────────────────────────────────────────────┘
```

### 各层职责

| 层 | 核心模块 | 职责 |
|----|---------|------|
| **交互层** | MCP Server、REST API、CLI | 对接外部系统（OpenCode/人/Git），提供查询、写入、审核入口 |
| **服务层** | KnowledgeService、PipelineService、ReviewService、DreamService、InjectionService | 编排业务流程，连接交互层与管理引擎层 |
| **管理引擎层** | PromotionEngine、PruningEngine、ConflictDetector、CalibrationEngine、ColdStartEngine、DataHealthEngine | 知识生命周期管理核心算法 |
| **存储层** | MarkdownStore、SQLiteStore、SearchEngine、AtomicWriter | 数据持久化与检索，MD 权威 + DB 索引派生 |
| **处理层** | Batcher、Extractor、EntityExtractor、RelationExtractor、Validator、Deduplicator | 8 Step 写入流水线的核心步骤 |
| **接收层** | OpenCodeAdapter、ComateAdapter、CursorAdapter、RawSessionStore | 多数据源适配 + 原始会话统一存储 |
| **基础设施层** | Config、LLMClient、Logger、ProcessManager、SecurityScanner | 贯穿各层的横切关注点 |

---

## 二、模块划分与职责

### 2.1 模块全景图

```
src/coderecall/
├── main.py                        # 应用入口（FastAPI + FastMCP 挂载）
├── config.py                      # 全局配置（pydantic-settings）
│
├── core/                          # 核心业务逻辑
│   ├── adapters/                  # 数据源适配器（统一接收层）
│   │   ├── base.py                # 适配器基类（接口定义）
│   │   ├── opencode.py            # OpenCode SQLite 适配器
│   │   ├── comate.py              # Comate 适配器
│   │   └── cursor.py              # Cursor 适配器
│   ├── pipeline/                  # 8 Step 写入流水线
│   │   ├── receiver.py            # Step 0: 统一接收（适配器路由 + 原始存储）
│   │   ├── batcher.py             # Step 1: JSONL 攒批
│   │   ├── extractor.py           # Step 2a: LLM 知识提炼 + 分类 + 时间提取
│   │   ├── entity_extractor.py    # Step 2b: 实体 + 关系提取
│   │   ├── validator.py           # Step 3: 签名 + 语义验证
│   │   ├── deduplicator.py        # Step 4: Jaccard + 语义去重
│   │   ├── writer.py              # Step 5: MD → DB 原子写入
│   │   └── consolidator.py        # Step 6: 晋升 + 修剪 + 巩固
│   ├── calibration.py             # 校准引擎（类级别代码校准 + 触发事件匹配）
│   ├── conflict.py                # 冲突检测引擎（L0-L5 检测 + 仲裁）
│   ├── promotion.py               # 晋升评估（V2.1 公式 + 滞回机制）
│   ├── pruning.py                 # 修剪规则（三层体系 + 容量管理）
│   ├── health.py                  # 数据健康引擎（7 类数据校正）
│   └── init.py                    # 冷启动引擎（项目扫描 → LLM 骨架生成）
│
├── models/                        # 数据模型（SQLModel）
│   ├── knowledge.py               # KnowledgeItem 模型
│   ├── source.py                  # Source 溯源模型
│   ├── category.py                # Category 分类模型
│   └── enums.py                   # 状态枚举（Depth / Status / Evidence）
│
├── schemas/                       # API 请求/响应 Schema（Pydantic）
│   ├── knowledge.py               # KnowledgeCreate / Update / Response
│   └── search.py                  # SearchRequest / SearchResponse
│
├── services/                      # 业务逻辑层
│   ├── knowledge.py               # 知识 CRUD + 检索编排
│   ├── pipeline.py                # 流水线编排（Step 0→6 全链路）
│   ├── review.py                  # 审核流程管理
│   ├── dream.py                   # 主动扫描（代码变更 → 知识校准）
│   └── injection.py               # 知识注入服务（AGENTS.md 生成 + 三层注入路由）
│
├── storage/                       # 存储层
│   ├── markdown.py                # MD 文件读写 + Frontmatter 解析
│   ├── sqlite.py                  # SQLite 连接池 + WAL 模式 + 事务
│   ├── search.py                  # FTS5 全文搜索 + 语义重排
│   └── atomic.py                  # 原子写入（MD first → DB second）
│
├── mcp/                           # MCP Server 层
│   ├── server.py                  # FastMCP 实例 + FastAPI 挂载
│   ├── tools.py                   # Tool 函数（search / review / dream / config）
│   └── resources.py               # Resource 模板（knowledge://{id}）
│
├── api/                           # REST API 层
│   ├── deps.py                    # 依赖注入（get_db / get_config）
│   └── routes/
│       ├── knowledge.py           # /api/knowledge/* 端点
│       └── health.py              # /api/health 健康检查
│
├── cli/                           # CLI 命令层
│   ├── app.py                     # Typer 应用入口
│   ├── init.py                    # dev init 命令（冷启动）
│   ├── review.py                  # dev review 命令
│   ├── dream.py                   # dev dream 命令
│   ├── config.py                  # devContextMemo config 命令
│   └── status.py                  # dev status 命令
│
└── utils/                         # 工具函数
    ├── hash.py                    # 内容签名（SHA-256）+ 语义签名
    ├── diff.py                    # 文件 Diff + AST 解析
    ├── llm.py                     # LLM API 封装（MiniMax + GLM）
    ├── security.py                # 安全扫描器（提示注入/凭据/Unicode 检测）
    └── path.py                    # 路径校验（realpath + 遍历防护）
```

### 2.2 模块依赖关系

**核心约束**：
- 上层可以依赖下层，下层不能依赖上层
- 管理引擎层可以调用存储层，但不能调用服务层
- 处理层可以调用基础设施层，但不能调用存储层（通过服务层协调）

```
交互层      ──→ 服务层 ──→ 管理引擎层 ──→ 存储层
  │                          │
  └────────── 基础设施层 ←───┘
                 ↑
              处理层
                 ↑
              接收层
```

---

## 三、核心数据流

### 3.1 写入流水线（Step 0 → Step 6）

```
[OpenCode / Comate / Cursor 多数据源]
        │
        ▼
┌─────────────────┐
│ Step 0: 接收    │  ← receiver.py + adapters/
│ 适配器标准化    │     各源输出统一 JSONL 格式
│ 原始会话存储    │     ~/.devcontext/raw/<project>/
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 1: 攒批    │  ← batcher.py
│ JSONL 批量写入  │     session_id + 防重
│ batch_log       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 2a: 提炼   │  ← extractor.py  ← LLM (MiniMax/GLM)
│ 知识条目生成    │     domain + 三元组分类(Lx/Sy/Depth)
│ DRAFT 状态      │     + code_verified 预标记 + occurred_at 提取
└────────┬────────┘
         │
    ┌────▼────────────────────────────────┐
    │ 分类子流程（同一次 LLM 调用）：     │
    │ 1. LLM Prompt: 输入知识文本 +       │
    │    domain_tree → 输出 {lx, sy,      │
    │    depth, domain, confidence}        │
    │ 2. confidence ≥0.85: 直接应用       │
    │    0.70~0.85: 标记 uncertain_class  │
    │    <0.70: PENDING_REVIEW 人工审核   │
    │ 3. 分类结果写入 knowledge_items     │
    │    Step 6 用 route() 决定注入层级   │
    └─────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Step 2b: 提取   │  ← entity_extractor.py  ← LLM (MiniMax/GLM)
│ 实体提取        │     人名/技术概念/模块/文件等实体识别
│ 关系提取        │     depends_on / contains / implements 等
│ 归一化去重      │     参考 Hindsight Entity Normalization
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 3: 验证    │  ← validator.py
│ 签名比对        │     content_hash + semantic_hash
│ 语义冲突检测    │     code_verified 设置
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 4: 去重    │  ← deduplicator.py
│ Jaccard 相似度  │     top_similar_id + UPDATE_CANDIDATE
│ 语义去重        │     死代码检测
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 5: 写入    │  ← writer.py  ← atomic.py
│ MD → DB 原子写入│     ① MD 写入 + fsync
│ STAGED 状态     │     ② DB 索引更新
│                 │     ③ 失败回滚 MD
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Step 6: 巩固    │  ← consolidator.py
│ 晋升评估        │     V2.1 公式 + CANDIDATE 滞回
│ 修剪规则        │     三层体系 + 容量检查
│ 冲突检测        │     L0-L5 检测 + 仲裁
│ 知识校准        │     类级别代码校准
│ supplement 合并 │     补充 → 主条目
└─────────────────┘
```

### 3.2 三层知识注入架构（核心价值交付路径）

devContextMemo 的知识注入分为三个层次，按触发方式、Token 成本和信息密度区分。这是 devContextMemo 区别于其他知识管理工具的核心能力——不是「存了就行」，而是「在正确的时间用正确的成本把正确的知识注入 AI 上下文」。

#### Layer 1：AGENTS.md 恒常注入（每次会话自动）

```
[OpenCode 会话启动]
        │
        ▼
┌──────────────────────┐
│ 读取 .devContextMemo/           │  ← 项目根目录下的 AGENTS.knowledge.md
│ AGENTS.knowledge.md   │     OpenCode 原生支持的 AGENTS.md 机制
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ L1 注入路由过滤      │  ← injection.py: route_to_l1()
│ 仅 S1/S2 + KW 知识   │     Token 预算 ≤ 4K
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ AI 上下文自动加载    │  ← 无需 LLM 决策
│ 含在系统 prompt 中   │     零额外 Token 成本
└──────────────────────┘
```

**触发条件**：
- 每次会话启动，OpenCode 自动读取项目根目录的 AGENTS.md
- devContextMemo 维护 `.devContextMemo/AGENTS.knowledge.md`（动态知识注入文件）
- 当 S1/S2 KW 知识累计 ≥ 3 条新增/变更时，自动生成 AGENTS.md 草稿，通过 `dev review` 人工确认后生效

**内容约束**：
- 仅注入 S1（极稳定）+ S2（稳定）× KW（是什么）类知识
- Token 预算 ≤ 4K（通过渐进截断控制）

#### Layer 2：MCP Tool `get_knowledge(domain, query, max_tokens)` 按需检索

```
[LLM 判断需要领域知识]
        │
        ▼
┌──────────────────────┐
│ MCP Tool 调用        │  ← MCP Tool: get_knowledge
│ domain + query       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ FTS5 全文搜索        │  ← search.py
│ 候选列表 top-k        │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 语义重排             │  ← search.py + LLM
│ 相关性打分           │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ L2 注入路由过滤      │  ← injection.py: route_to_l2()
│ S1/S2+KH/KY + S3/S4  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 返回 URI 列表 + 摘要 │  ← MCP Tool 响应
│ ~1-3K tokens / call  │
└──────────────────────┘
```

**触发条件**：LLM 判断需要领域知识时主动调用 MCP Tool

**内容范围**：
- S1/S2 + KH（怎么做）/ KY（为什么）类知识
- S3/S4 + 任意 Depth

#### Layer 3：MCP Tool `get_experience(query, max_tokens)` 经验检索

```
[事件触发 / LLM 判断需要历史经验]
        │
        ▼
┌──────────────────────┐
│ MCP Tool 调用        │  ← MCP Tool: get_experience
│ 经验关键词查询       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 经验库检索           │  ← search.py
│ S5 + 任意 Depth      │     低优先级检索
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 返回经验摘要         │  ← MCP Tool 响应
│ ~0.5-1.5K / call     │     仅在 L1/L2 无法满足时启用
└──────────────────────┘
```

#### 注入路由推导表（injection.py 核心逻辑）

| 条件 | 推导结果 | Token 成本 | 触发方式 |
|------|---------|:--:|------|
| S1/S2 + KW | L1 恒常注入 | 含在 4K 预算内 | 每次会话自动 |
| S1/S2 + KH/KY | L2 按需检索 | ~1-3K/call | LLM 判断需要 |
| S3/S4 + 任意 Depth | L2 按需检索 | ~1-3K/call | LLM 判断需要 |
| S5 + 任意 Depth | L2/L3 检索 | ~0.5-1.5K | 事件触发 |

#### AGENTS.md 生成流程（InjectionService 子功能）

```
[知识条目变更（新增/更新 ≥3 条 S1/S2 KW）]
        │
        ▼
┌──────────────────────┐
│ 触发 AGENTS.md 草稿  │  ← injection.py: generate_agents_md()
│ 收集符合条件的知识   │     S1/S2 + KW, ≤4K tokens
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ LLM 汇总生成 Markdown│  ← LLM (MiniMax/GLM)
│ 结构化 + 精简        │     保留核心事实，去除冗余
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 写入 .devContextMemo/staging/  │  ← 暂存为 AGENTS.knowledge.draft.md
│ 触发 dev review     │     人工审核确认
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 审核通过后           │  ← 移动至 .devContextMemo/AGENTS.knowledge.md
│ 下次会话生效         │     OpenCode 自动加载
└──────────────────────┘
```

### 3.3 校准闭环流

```
[Git Diff 触发]
        │
        ▼
┌──────────────────────┐
│ 检测代码变更        │  ← git watcher / dev dream
│ 文件 + 行级 diff     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 查找关联知识        │  ← calibration.py
│ code_entry_id 匹配   │     类级别映射
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ LLM 语义对比        │  ← calibration.py + LLM
│ 旧知识 vs 新代码    │     知识有效性判断
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ 更新知识状态        │  ← conflict.py + promotion.py
│ 保持/标记过时/冲突  │     自动处理或提交审核
└──────────────────────┘
```

---

## 四、核心引擎设计

### 4.1 校准引擎（CalibrationEngine）

**职责**：当检测到可能使现有知识过时的事件时，查找关联知识并通过 LLM 语义对比判断知识有效性。

**输入**：触发事件（见下方矩阵）
**输出**：关联知识的有效性判定（VALID / UNCERTAIN / CONFLICT）

**8 种触发事件矩阵**：

| # | 触发事件 | 优先级 | Phase | 检测逻辑 | 检测粒度 |
|:--:|------|:--:|:--:|------|:--:|
| E1 | Git commit | P0 | Phase 1 | git watcher 监听 post-commit hook，解析变更文件列表 | 文件级 → 类级别 |
| E2 | 新服务/模块上线 | P0 | Phase 1 | 新文件检测 + 目录结构变更 | 模块级 |
| E3 | 人肉修改（author ≠ AI） | P0 | Phase 1 | Git author 检查 + 变更量阈值（>50 行） | 文件级 |
| E4 | 需求文档变更 | P1 | Phase 1 | `.devContextMemo/knowledge/requirement/` 下 MD 文件的 content_hash 变更 | 知识条目级 |
| E5 | 架构评审通过 | P1 | Phase 2 | 架构文档状态变更（STAGED → STABLE 跃迁） | 领域级 |
| E6 | Spec 接口变更 | P1 | Phase 2 | API 定义文件 diff + OpenAPI schema 比对 | 接口级 |
| E7 | 依赖版本升级 | P1 | Phase 2 | `pyproject.toml` / `package.json` diff + 版本号变更检测 | 依赖级 |
| E8 | 故障复盘结论 | P2 | Phase 2 | 手动触发 `dev dream --scope=incident` | 领域级 |

**处理流程**（以 E1 Git commit 为例）：
1. 解析 Git diff，提取变更文件的类名
2. 在 SQLite 中查找 `code_entry_id` 匹配的知识条目
3. 提取旧知识内容 + 新代码上下文
4. LLM 语义对比（知识描述 vs 代码实际行为）
5. 三类判定：VALID / UNCERTAIN / CONFLICT
6. 更新 knowledge_items 的 calibration 字段

**Phase 1 覆盖范围**：E1（Git commit）+ E3（人肉修改），E2/E4 作为二期快速跟进

**约束**（D59）：
- 类级别校准是辅助信号，不直接改变知识状态
- 精度需 ≥ L2（可对比的语义粒度）
- 多文件关联时聚合判断

**两种触发模式**（共用同一个 CalibrationEngine 实例）：
1. **主动触发**（写入流水线 Step 6）：知识条目刚写入后执行校准，验证新知识是否与现有代码一致
2. **被动触发**（git watcher / dev dream）：检测到代码文件变更后查找关联知识执行校准

### 4.2 冲突检测引擎（ConflictDetector）

**五层检测 L0-L5**：
- **L0**：SHA-256 内容哈希 → 精确匹配
- **L1**：语义签名哈希 → 语义相似检测
- **L2**：LLM 矛盾检测 → 同领域知识一致性
- **L3**：交叉扫描 → 全库一致性检查
- **L4**：代码一致性 → 知识 vs 代码对比
- **L5**：人工校准 → 最终仲裁

**仲裁机制**：
- `evidence_weight × confidence` 差值 ≥ 0.30 → 自动采用
- 否则 → 标记 CONFLICT + 人工审核

### 4.3 晋升引擎（PromotionEngine）

**V2.1 公式**：
`base_score = confidence×0.70 + anchor_bonus×0.15 + calibration_recency×0.15`

**关键规则**：
- DRAFT（已提炼未入库） → CANDIDATE（审核区）
- CANDIDATE 滞回：0.82 进 / 0.80 出
- 无锚点 max=0.80 → PENDING_REVIEW（不被永久卡住）
- T14 无锚点 90天 → STALE(suspicious)
- STABLE（正式知识，长期存在）

### 4.4 修剪引擎（PruningEngine）

**三层体系**：
- **Layer 1**：质量下限（stale_draft > 90天 → DEPRECATED）
- **Layer 2**：使用频率（COLD > 365天 → STALE，prune_priority ≥ 0.70）
- **Layer 3**：代码锚点（ORPHAN → STALE，DEAD → DEPRECATED）

**容量管理**：
- 软上限 500（提示清理）
- 硬上限 2000（强制修剪）

### 4.5 冷启动引擎（ColdStartEngine）— P0-1 修复

**职责**：在项目首次接入 devContextMemo 时，自动扫描项目结构并通过 LLM 生成初始知识骨架，降低人工初始化的摩擦。

**触发方式**：
- CLI 命令：`dev init` → 交互式冷启动向导
- 程序入口：`core/init.py: ColdStartEngine`

**处理流程**：
1. **项目扫描**：遍历项目目录，识别技术栈（Python/Java/Node.js）、框架（FastAPI/SpringBoot）、目录结构
2. **代码分析**：采样关键文件（入口文件、配置文件、核心模块），提取类名/函数签名/注解
3. **LLM 骨架生成**：将扫描结果发送给 LLM，生成：
   - S1 KW：项目定位、技术栈、核心模块列表
   - S2 KW：架构约定、编码规范、依赖清单
   - Domain 划分：识别业务领域（如支付/订单/用户）
4. **人工审核**：生成 DRAFT 状态的 `.devContextMemo/staging/` 知识文件，通过 `dev review` 确认
5. **AGENTS.md 生成**：审核通过后自动生成 `.devContextMemo/AGENTS.knowledge.md`

**安全约束**：
- 仅扫描项目目录内文件（`realpath` 校验，拒绝目录遍历）
- 跳过 `.git`、`node_modules`、`.venv` 等目录
- 不对代码内容做 LLM 外传（本地预处理：提取签名、脱敏密钥）

### 4.6 知识注入服务（InjectionService）— P0-2/P0-5 修复

**职责**：管理三层知识注入的完整生命周期，是 devContextMemo「知识 → AI 上下文」的核心价值交付路径。

**模块位置**：`services/injection.py`

**核心功能**：

| 功能 | 方法 | 触发条件 | 输出 |
|------|------|------|------|
| 注入路由推导 | `route(lx, sy, depth) → L1/L2/L3` | 知识条目分类完成后 | 注入层级标记 |
| AGENTS.md 生成 | `generate_agents_md()` | S1/S2 KW 累计 ≥ 3 条新增/变更 | `AGENTS.knowledge.draft.md` |
| L1 恒常注入维护 | `update_l1_injection()` | AGENTS.md 草稿审核通过 | 替换 `.devContextMemo/AGENTS.knowledge.md` |
| L2 检索响应构建 | `build_l2_response(results)` | `get_knowledge` Tool 调用 | URI 列表 + 摘要 |
| L3 经验响应构建 | `build_l3_response(results)` | `get_experience` Tool 调用 | 经验摘要 |

**注入路由推导逻辑**：
```python
def route(lx: StabilityLevel, sy: StabilityLevel, depth: Depth) -> InjectionLayer:
    if lx in (S1, S2) and depth == Depth.KW:
        return InjectionLayer.L1   # 恒常注入
    elif lx in (S1, S2) and depth in (Depth.KH, Depth.KY):
        return InjectionLayer.L2   # 按需检索
    elif lx in (S3, S4):
        return InjectionLayer.L2   # 按需检索
    elif lx == S5:
        return InjectionLayer.L3   # 经验检索
```

**AGENTS.md 生成约束**：
- Token 预算 ≤ 4K（通过渐进截断控制）
- 仅含 S1/S2 + KW 知识
- LLM 汇总时将多条知识条目合并为结构化的 Markdown
- 草稿路径：`.devContextMemo/staging/AGENTS.knowledge.draft.md`
- 生效路径：`.devContextMemo/AGENTS.knowledge.md`（人工审核确认后移动）

**Token 截断策略（需求 R21 三层兜底）**：

当 S1/S2+KW 知识总量超过 4K 预算时，按优先级截断：

| 优先级 | 知识类型 | 策略 |
|:--:|------|------|
| 1 | S1-KW（原则级） | 不可截断，全部保留 |
| 2 | L0-S2-KW（全局架构） | 至少保留 3 条，超出按 calibration_recency 降序 |
| 3 | L1-S2-KW（领域架构） | 按 calibration_recency 降序截断 |

截断末尾追加注释标记被截断条目数。

**dev correct 命令接口（需求 R21 三层兜底第三层）**：

```bash
dev correct <knowledge_id> --lx L2 --sy S3 --depth KH --domain payment
```

执行后果链：
1. 更新 knowledge_items 的 (lx, sy, depth, domain) 字段
2. `InjectionService.route()` 重新计算注入层级
3. 若注入层级变化（L1↔L2）：标记 AGENTS.md 待重新生成
4. 记录到 `calibration_history`：reason=manual_correction，operator=user

### 4.7 安全扫描器（SecurityScanner）— P0-3 修复

**职责**：所有写入知识库的内容在持久化前通过三层安全扫描，防止恶意或敏感内容污染知识库。

**模块位置**：`utils/security.py: SecurityScanner`

**三层检测**：

| 层 | 检测内容 | 方法 | 动作 |
|:--:|------|------|------|
| L1 | 提示注入 | 模式匹配（已知注入模式库） | 拒绝写入 + 记录安全事件 |
| L2 | 凭据泄露 | 正则匹配（API Key / Token / Password 特征） | 拒绝写入 + 脱敏建议 + 记录安全事件 |
| L3 | Unicode 不可见字符 | Unicode 类别检测（零宽字符/控制字符） | 拒绝写入 |

**执行时机**：Step 3 验证层（`validator.py`）写入前调用 `SecurityScanner.scan(content)`

**安全事件日志**：
- 记录到 SQLite 独立表 `security_events`
- 包含：时间戳、检测层、触发内容摘要（脱敏后）、来源文件、建议动作

**已知注入模式库**（Phase 1 内置）：
- `"ignore all previous instructions"` 变体
- `"you are now DAN"` 变体
- `"system: override"` 模式
- 中文注入变体（如"忽略上述指令"）

### 4.8 数据健康引擎（DataHealthEngine）— P0-4 修复

**职责**：定期检查知识库的数据质量，自动发现并修复 7 类数据问题，防止腐败数据注入 AI 上下文。

**模块位置**：`core/health.py: DataHealthEngine`

**触发方式**：
- `dev dream` 命令的子步骤（每次主动扫描附带）
- 可配置的定时任务（Phase 2）

**7 类数据校正**：

| # | 问题类型 | 严重度 | 检测逻辑 | 修复策略 |
|:--:|------|:--:|------|------|
| H1 | MD-DB 索引漂移 | 🔴 高 | 遍历 MD 文件，对比 DB 中的 content_hash | 重建 DB 索引 |
| H2 | 多版本冲突 | 🔴 高 | 同一 code_entry_id 存在多条 ACTIVE 知识 | 触发冲突检测 → 仲裁 |
| H3 | 索引漂移 | 🟡 中 | FTS5 索引与知识内容不一致 | 重建 FTS5 索引 |
| H4 | 知识过期 | 🟡 中 | 校准引擎判定 UNCERTAIN 超过 30 天的条目 | 标记 DEPRECATED |
| H5 | 冗余知识 | 🟢 低 | Jaccard > 0.85 的两条知识（非 supplement 关系） | 合并建议 + 人工确认 |
| H6 | 领域树失效 | 🟡 中 | 引用的 domain 在 domain_tree 中不存在 | 标记 UNCERTAIN 待重新分类 |
| H7 | 引用断裂 | 🟢 低 | 引用的 knowledge_id / source_id 不存在 | 标记引用为 BROKEN_REF |

**执行策略**：
- H1/H3：自动修复，无需人工确认（DB 从 MD 重建是无损操作）
- H2/H4/H6：自动标记 + 触发 `dev review` 审核
- H5/H7：仅生成报告，不自动执行（需要人工判断语义等价）

**H8: 层级漂移检测（需求 R23）**：
- 检测逻辑：S2 知识距上次校准 > 180 天 AND 关联代码距上次 commit ≤ 30 天
- 判定：代码活跃但知识未校准 → 层级漂移嫌疑 → 标记 PENDING_REVIEW
- 30 天无人处理 → 自动降级为 S3 + 更新注入路由
- 注：如果关联代码本身也 180 天未变更 → 稳定性高 → 不漂移

**H9: 覆盖盲区检测（需求 R23）**：
- 触发：`dev dream --scope=coverage` 或每周自动
- 检测：遍历项目文件树 → 排除 node_modules/vendor/.git 等 → 计算未关联 L3 knowledge 的文件占比
- 阈值：未覆盖文件 > 总文件数 × 30% → 输出警告报告
- 输出：未覆盖文件列表 + LLM 批量扫描建议（可选执行）

---

### 4.9 知识操作引擎（KnowledgeOperationEngine）— R15 修复

**职责**：提供知识五操作（创建/更新/替换/补充/废弃）的统一入口，确保操作语义一致，避免与其他引擎产生隐式耦合。

**模块位置**：`services/knowledge.py: KnowledgeOperationEngine`

**五操作定义**：

| 操作 | 方法签名 | 前置条件 | 后置效果 | 引擎联动 |
|------|------|------|------|------|
| **create** | `create(content, lx, sy, depth, domain)` → id | 去重检查 + 安全扫描 | DRAFT→staging/ | Step 5 writer + Step 6 consolidator |
| **update** | `update(id, new_content)` → snapshot_id | content_hash ≠ 旧 hash | 创建快照 + content_hash 更新 | VersionChain.create_snapshot() |
| **replace** | `replace(id, new_content, lx?, sy?, depth?)` | 旧知识标记 DEPRECATED | 新知识 CANDIDATE 从头晋升 | PromotionEngine 重置评分 |
| **supplement** | `supplement(id, supplement_text)` | 主知识必须存在 | 创建 supplement 关系 + 主知识 hash 更新 | PruningEngine 保护主知识 |
| **deprecate** | `deprecate(id, reason)` | 无 | DEPRECATED→deprecated/ | CalibrationEngine 校准关联知识 |

**关键约束**：
- 所有操作通过 `services/knowledge.py` 统一入口，禁止各引擎直接调用 writer
- `update` vs `replace` 的核心区别：update 维持原 (Lx, Sy, Depth) 坐标不变；replace 可改变坐标，旧知识 DEPRECATED
- `supplement` 不改变主知识的独立完整性，修剪时被 supplement 关联的主知识不可被修剪

---

### 4.10 版本链管理（VersionChain）— R16 修复

**职责**：管理知识的完整版本演化历史，为冲突检测、校准引擎和审核追溯提供时间维度数据。

**模块位置**：`core/versioning.py: VersionChain`

**快照策略**：

| 规则 | 值 |
|------|-----|
| 创建时机 | 每次 `knowledge_items.content_hash` 变更前 |
| 版本链结构 | `snapshot_id → superseded_by → next_snapshot_id`（单向链表） |
| ACTIVE/COLD 保留策略 | 保留全部快照 |
| DEPRECATED 保留策略 | 30 天后仅保留最后一个快照 |

**knowledge_snapshots 核心字段**：
- `superseded_by`：替代本版本的 snapshot_id（NULL = 当前版本）
- `snapshot_reason`：CREATE / UPDATE / REPLACE / SUPPLEMENT
- `snapshot_at`：快照时间戳

**跨引擎使用规则**：
- **ConflictEngine L4 验证**：读取当前 ACTIVE 版本 content（而非最新快照）
- **知识演化追溯**：通过 `superseded_by` 链回溯完整变更历史
- **PromotionEngine**：知识被 `replace` 后，新知识重置评分从 CANDIDATE 开始

---

### 5.1 运行时依赖

| 依赖 | 版本 | 用途 | 必要性 |
|------|------|------|:--:|
| FastAPI | ≥0.110.0 | Web 框架 + REST API | 必须 |
| FastMCP | ≥2.0.0 | MCP Server 框架 | 必须 |
| uvicorn | ≥0.29.0 | ASGI 服务器 | 必须 |
| SQLAlchemy + SQLModel | ≥2.0 | ORM + 数据模型 | 必须 |
| aiosqlite | ≥0.20.0 | SQLite 异步驱动 | 必须 |
| httpx | ≥0.27.0 | HTTP 客户端（LLM API 调用） | 必须 |
| pydantic-settings | ≥2.2.0 | 配置管理 | 推荐 |
| openai | ≥1.30.0 | LLM API 客户端（兼容 MiniMax/GLM） | 必须 |

### 5.2 开发工具依赖

| 依赖 | 版本 | 用途 | 必要性 |
|------|------|------|:--:|
| typer | ≥0.12.0 | CLI 框架 | 必须 |
| rich | ≥13.7.0 | CLI 美化输出 | 推荐 |
| pytest + pytest-asyncio | ≥8.0 | 测试框架 | 必须 |
| black | ≥24.0 | 代码格式化 | 推荐 |
| ruff | ≥0.4.0 | 代码检查 | 推荐 |
| mypy | ≥1.10 | 类型检查 | 推荐 |
| pre-commit | ≥3.7.0 | Git hooks | 推荐 |

### 5.3 外部系统依赖

| 系统 | 用途 | 替代方案 |
|------|------|---------|
| MiniMax API | LLM 知识提炼 + 冲突检测 | GLM API |
| GLM API | LLM 语义对比 + 检索重排 | MiniMax API |
| OpenCode 本地数据 | 对话日志采集 | — |
| Git | 代码变更追踪 | — |

---

## 六、部署拓扑（Phase 1 单机版）

```
┌──────────────────────────────────────────┐
│              用户的开发机器               │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │         devContextMemo Process         │  │
│  │  ┌──────────────────────────────┐  │  │
│  │  │    uvicorn (ASGI Server)     │  │  │
│  │  │  ┌────────────────────────┐  │  │  │
│  │  │  │   FastAPI App          │  │  │  │
│  │  │  │  ┌──────────────────┐  │  │  │  │
│  │  │  │  │  FastMCP Server  │  │  │  │  │
│  │  │  │  │  (SSE Transport) │  │  │  │  │
│  │  │  │  └──────────────────┘  │  │  │  │
│  │  │  └────────────────────────┘  │  │  │
│  │  └──────────────────────────────┘  │  │
│  │              │                     │  │
│  │              ▼                     │  │
│  │  ┌──────────────────────────────┐  │  │
│  │  │     SQLite Database          │  │  │
│  │  │     (WAL mode)               │  │  │
│  │  └──────────────────────────────┘  │  │
│  │              │                     │  │
│  │              ▼                     │  │
│  │  ┌──────────────────────────────┐  │  │
│  │  │  .devContextMemo/knowledge/ (MD 文件)  │  │  │
│  │  │  .devContextMemo/staging/   (待审核)   │  │  │
│  │  │  .devContextMemo/deprecated/ (已废弃)  │  │  │
│  │  └──────────────────────────────┘  │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │         OpenCode Process           │  │
│  │  ←── MCP SSE Connection ──→        │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │         项目 Git 仓库               │  │
│  │  ←── .devContextMemo/knowledge/ 同仓管理 ──→  │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

**启动方式**（Phase 1）：
```bash
# 方式 1：独立启动
devContextMemo serve --host 127.0.0.1 --port 9020

# 方式 2：CLI 命令
dev init       # 冷启动：扫描项目 → LLM 生成初始知识骨架
dev review     # 审核交互（DRAFT → STAGED 确认）
dev dream      # 主动扫描（代码变更 → 校准 + 数据健康检查）
dev status     # 状态查看（知识库概览）
devContextMemo config     # 配置管理
```

---

## 七、设计决策索引

| 决策 | 内容 | 来源 |
|------|------|------|
| D1 | 架构路线 A：外部独立构建 | 技术决策记录 |
| D2 | Python 全栈（FastAPI + FastMCP） | 技术决策记录 |
| D3 | SQLite（Phase 1） | 技术决策记录 |
| D4 | MD 权威 + DB 索引派生 | 需求文档 §2.1 |
| D5 | 8 Step 写入流水线（含 Step 0 统一接收 + Step 2a/2b 拆分） | 需求文档 §四 |
| D57 | 晋升公式 V2.1（0.70/0.15/0.15） | 决策总账 V1.0 |
| D59 | 类级别校准 + 3 约束 | 类级别校准调研 V1.0 |
| D60 | 原子写入（MD first → DB second） | 原子写入设计 V1.0 |
| D63 | 项目结构：src-layout + setuptools | Python 项目结构调研报告 §六 |
| D64 | CLI 框架：Typer | Python 项目结构调研报告 §五 |
| D65 | 实体提取与图关系：Phase 1 实施，参考 Hindsight Entity Normalization | 技术决策记录 |
| D67 | 自动时间提取：Step 2a 提炼 Prompt 增加 occurred_at 字段提取 | 技术决策记录 |
| D68 | 统一接收层：适配器模式 + 原始会话存储 | 技术决策记录 |
| D69 | Step 2 拆分为 2a+2b：借鉴 OpenChronicle Compression Funnel | 技术决策记录 |

## 八、AI-Friendly 合规性改造 ⭐ 新增 2026-06-18

> 依据：《后端架构 AI-Friendly 的标准与路径》（刘瑞洲，阿里技术）
> 目标：让 devContextMemo 的代码架构可被 AI Agent 无痛苦理解、修改、扩展

### 8.1 改造总览

| # | AI-Friendly 维度 | 现状 | 改造动作 | 交付物 |
|:--:|------|:--:|------|---------|
| 1 | Architecture Facts Clarity | ❌ 仅有设计文档描述 | 新建结构化架构地图 | `architecture.yaml` |
| 2 | Architecture Map | ❌ 缺失 | 定义全局地图文件格式 | `architecture.yaml` |
| 3 | System/Service Card | ❌ 缺失 | 定义标准 Card 模板 + 各模块填空 | `service-card.yaml`（模板）+ 各模块 Card |
| 4 | 领域模型显式化 | ⚠️ 有描述但非机器可读 | 知识状态机 YAML 化 | `knowledge-state-machine.yaml` |
| 5 | Skill-Based 工程能力 | ✅ 写入流水线六步已结构化 | 无需改造 | — |
| 6 | Harness Augmentation | ✅ 写入流水线含验证/审计层 | 无需改造 | — |
| 7 | Test-Gated AI Development | ⚠️ 有测试规划但缺架构级测试 | 补充架构验证测试条目 | §8.4 |
| 8 | AI-Observable Architecture | ⚠️ Logger 存在但不结构化 | 定义 log schema | `observability.yaml` |
| 9 | Tiered Access Control | ⚠️ Phase 2+ 规划中 | 需求文档占位 | 决策 D66 |
| 10 | Code Navigation Framework | ✅ 模块全景图 + 稳定目录约定 | 无需改造 | — |
| 11 | Docs/Architecture as Code | ✅ MD 权威源 + DB 索引 | 无需改造 | — |
| 12 | 从 Copilot 到 Operator | ℹ️ 路线参考，非改造项 | — | — |

### 8.2 Architecture Map（`architecture.yaml`）

文件位置：`.devContextMemo/architecture.yaml`（参与 CI 检查）

```yaml
# devContextMemo Architecture Map V1.0
# 机器可读的全局架构地图，供 AI Agent 装载上下文
schema_version: "1.0"

system:
  name: devContextMemo
  chinese_name: 码上记忆
  phase: 1  # 单机版
  tech_stack:
    language: Python 3.13
    web_framework: FastAPI
    mcp_framework: FastMCP
    database: SQLite (WAL mode)
    search: FTS5
    llm: [MiniMax, GLM]

business_domains:
  - name: knowledge_management
    description: 知识生命周期管理（采集→提炼→验证→去重→写入→巩固）
    core_services: [pipeline, calibration, promotion, pruning, health]
  - name: knowledge_retrieval
    description: 知识检索与注入（MCP Tool + AGENTS.md）
    core_services: [injection, search]
  - name: source_collection
    description: 原始素材采集（OpenCode 日志 + Git Diff）
    core_services: [collector, git_watcher]

service_layering:
  - layer: interaction      # 对外交互层
    responsibilities: [MCP Tool 暴露, REST API, CLI 命令]
  - layer: service         # 业务流程编排层
    responsibilities: [知识检索编排, 流水线编排, 审核流程, 主动扫描, 知识注入]
  - layer: management      # 核心算法层
    responsibilities: [晋升评估, 修剪规则, 冲突检测, 校准引擎, 冷启动, 数据健康]
  - layer: storage         # 持久化层
    responsibilities: [MD 文件操作, SQLite 索引, FTS5 搜索, 原子写入]
  - layer: processing      # 写入流水线处理层
    responsibilities: [攒批, 提炼, 实体提取, 关系提取, 验证, 去重, 签名, 语义分析]
  - layer: receiver        # 统一接收层
    responsibilities: [多源适配, 统一格式标准化, 原始会话存储, 多源聚合]
  - layer: infrastructure  # 横切层
    responsibilities: [配置管理, LLM API, 日志, 监控, 进程管理, 安全扫描]

core_chains:
  - name: write_pipeline
    description: 多源会话 → 结构化知识 → 实体关系 → 持久化 → 晋升
    steps: [receiver, batcher, extractor, entity_extractor, validator, deduplicator, writer, consolidator]
    is_sync: true  # 攒批触发，非实时
  - name: calibration_loop
    description: Git Diff 触发 → 查找关联知识 → LLM 语义对比 → 更新状态
    trigger: [git_commit, manual_edit]
    is_sync: false  # 异步被动触发
  - name: injection_chain
    description: AI 请求知识 → FTS5 搜索 → 语义重排 → 返回
    trigger: [mcp_tool_call]
    is_sync: true

data_ownership:
  raw_sessions:
    owner: receiver layer (adapters/)
    path: ~/.devcontext/raw/<project>/
    access: read_write (permanent retention)
  markdown_files:
    owner: storage layer (markdown.py)
    path: .devContextMemo/knowledge/
    access: read_write
  sqlite_index:
    owner: storage layer (sqlite.py)
    path: .devContextMemo/devcontextmemo.db
    access: read_write (via ORM only)
  fts5_index:
    owner: storage layer (search.py)
    access: read_write (derived from MD, rebuildable)
  staging_area:
    owner: pipeline service
    path: .devContextMemo/staging/
    access: read_write (DRAFT entries only)

dependency_rules:
  - rule: 上层可依赖下层，下层不可依赖上层
  - rule: management 层可调用 storage 层，不可调用 service 层
  - rule: processing 层通过 service 层协调，不可直接调用 storage 层
  - rule: infrastructure 层被所有层依赖，不依赖任何业务层

legacy_modules: []  # Phase 1 无遗留模块

future_direction:
  phase_2: 多项目支持 + Web UI + 权限分级
  phase_3: 多 Agent 协作 + 云端同步
```

### 8.3 Service Card 标准模板 + 核心模块填空

**标准模板** `.devContextMemo/service-card.schema.yaml`：

```yaml
# Service Card Schema — 每个核心模块一张
schema_version: "1.0"
module:
  name:  # 模块名（对应 Python 文件名或类名）
  layer:  # 所属层（interaction/service/management/storage/processing/collection/infrastructure）
  file_path:  # 代码文件路径
  responsibilities:  # 3-7 条核心职责
  depends_on:  # 依赖的下游模块（列表）
  depended_by:  # 被哪些上游模块依赖（列表）
  data_owned:  # 本模块直接写的数据（表/文件/缓存 key）
  data_readonly:  # 本模块只读不写的数据
  key_functions:  # 核心函数/方法签名
  risk_level:  # low / medium / high
  test_entry:  # 单测命令
  integration_test_entry:  # 集成测试命令
  change_constraints:  # 哪些不能随便改
```

**核心模块 Service Card 示例（CalibrationEngine）**：

```yaml
schema_version: "1.0"
module:
  name: CalibrationEngine
  layer: management
  file_path: src/devcontextmemo/core/calibration.py
  responsibilities:
    - 接收触发事件（E1-E8），查找关联知识
    - 通过 LLM 语义对比判断知识有效性（VALID/UNCERTAIN/CONFLICT）
    - 更新 knowledge_items 的 calibration 字段
    - 支持主动触发（写入流水线 Step 6）和被动触发（git watcher）
  depends_on:
    - storage/sqlite.py  # 读取 knowledge_items
    - storage/markdown.py  # 读取知识内容
    - utils/llm.py  # LLM 语义对比
    - models/knowledge.py  # KnowledgeItem 模型
  depended_by:
    - services/pipeline.py  # Step 6 主动校准
    - cli/dream.py  # dev dream 被动校准
  data_owned:
    - table: knowledge_items (calibration 字段更新)
    - table: calibration_history (写入校准历史)
  data_readonly:
    - table: knowledge_items (读取 content, code_entry_id)
    - table: sources
  key_functions:
    - "trigger(event: CalibrationEvent) -> CalibrationResult"
    - "find_related_knowledge(code_entry_id: str) -> List[KnowledgeItem]"
    - "semantic_compare(old_content: str, new_code: str) -> ValidityJudgment"
  risk_level: medium  # 误判会导致知识错误标记
  test_entry: pytest tests/core/test_calibration.py
  integration_test_entry: pytest tests/integration/test_calibration_pipeline.py
  change_constraints:
    - LLM prompt 模板变更需人工 review（影响校准准确率）
    - 判定阈值（VALID/UNCERTAIN/CONFLICT）变更需 A/B 验证
    - 新增触发事件类型需同步更新 §4.1 触发事件矩阵
```

> **后续动作**：编码阶段每个核心模块交付时，必须同步交付对应 Service Card YAML，CI 检查是否存在。

### 8.4 知识状态机（机器可读版）

文件位置：`.devContextMemo/knowledge-state-machine.yaml`

```yaml
# devContextMemo 知识状态机 V1.0
# 机器可读，可生成代码校验逻辑和测试用例
schema_version: "1.0"

states:
  - name: DRAFT
    description: 刚提炼，未入库
    is_terminal: false
    allowed_next: [STAGED, DEPRECATED]
  - name: STAGED
    description: 已写入 MD + DB，待审核
    is_terminal: false
    allowed_next: [CANDIDATE, DEPRECATED]
  - name: CANDIDATE
    description: 审核区，可晋升
    is_terminal: false
    allowed_next: [VALID, STALE, DEPRECATED]
    entry_condition: "base_score >= 0.82"
  - name: VALID
    description: 正式知识，可被注入
    is_terminal: false
    allowed_next: [STALE, DEPRECATED, COLD]
  - name: STALE
    description: 可疑过期，需校准
    is_terminal: false
    allowed_next: [VALID, DEPRECATED]
    auto_trigger:
      - condition: calibration_overdue > 180d (S3/S4) or > 365d (S1/S2)
        action: mark STALE
  - name: COLD
    description: 长期未使用，降级存储
    is_terminal: false
    allowed_next: [VALID, STALE, DEPRECATED]
    auto_trigger:
      - condition: no retrieval in 365d
        action: mark COLD
  - name: DEPRECATED
    description: 已废弃，不可注入
    is_terminal: true
    allowed_next: []

transitions:
  - from: CANDIDATE
    to: VALID
    trigger: promotion_evaluation
    condition: "base_score >= 0.82 and human_approved"
  - from: CANDIDATE
    to: CANDIDATE  # 滞回，不退化
    trigger: promotion_evaluation
    condition: "0.80 <= base_score < 0.82"
  - from: VALID
    to: STALE
    trigger: calibration_event
    condition: "calibration_result == UNCERTAIN and stale_duration > threshold"
  - from: STALE
    to: VALID
    trigger: recalibration
    condition: "calibration_result == VALID"
  - from: ANY
    to: DEPRECATED
    trigger: manual_deprecate or replace_operation
    condition: "operator confirms"

invariants:
  - "同一 (code_entry_id, domain) 组合最多只能有 1 条 NON-DEPRECATED 知识"
  - "VALID 状态知识的 base_score 必须 >= 0.82"
  - "DEPRECATED 状态知识不得出现在任何注入层级"
  - "CANDIDATE 状态知识不得被注入（L1/L2/L3 均跳过）"
```

### 8.5 可观测性结构化（Log Schema）

文件位置：`.devContextMemo/observability.yaml`（Phase 1 定义 schema，Phase 2 接入）

```yaml
# devContextMemo 可观测性 Schema V1.0
schema_version: "1.0"

log_format:
  required_fields:
    - name: timestamp
      type: ISO8601
      description: 日志时间
    - name: trace_id
      type: UUID
      description: 全链路追踪 ID（一次_pipeline 执行 / 一次 MCP Tool 调用）
    - name: module
      type: string
      description: 产生日志的模块名（如 pipeline/calibration/injection）
    - name: action
      type: string
      description: 正在执行的操作（如 extract/validate/deduplicate）
    - name: status
      type: enum [START, SUCCESS, FAIL, SKIP]
      description: 操作状态
    - name: knowledge_id
      type: string
      description: 关联的知识 ID（如适用）
    - name: error_code
      type: string
      description: 错误码（SUCCESS 时为 null）

  optional_fields:
    - name: duration_ms
      type: int
      description: 操作耗时
    - name: token_usage
      type: int
      description: LLM 调用消耗 token 数
    - name: file_path
      type: string
      description: 关联的文件路径

error_codes:
  PROMOTION_E0: 晋升评估失败（base_score 计算异常）
  CONFLICT_L0: 内容哈希冲突（精确重复）
  CONFLICT_L2: LLM 矛盾检测冲突
  CALIBRATION_E0: 校准引擎 LLM 调用失败
  SECURITY_L1: 提示注入检测命中
  SECURITY_L2: 凭据泄露检测命中
  PIPELINE_E0: 流水线 Step N 执行失败
  INJECTION_E0: 注入路由推导失败

operation_log_schema:
  table: operation_logs
  fields:
    - [trace_id, UUID, PK]
    - [module, TEXT]
    - [action, TEXT]
    - [status, TEXT]
    - [knowledge_id, TEXT]
    - [error_code, TEXT]
    - [created_at, DATETIME]
  retention_days: 90
```

### 8.6 架构级测试（新增到 §八 下一步工作）

在原有 §八 下一步工作基础上，补充架构约束测试条目：

```yaml
# 架构级测试清单（追加到 §八）
architecture_tests:
  - test: test_layer_dependency_direction
    description: 验证上层不反向依赖下层（用 ast 解析 import）
    tool: pytest + 自定义 lint
    blocking: true
  - test: test_management_not_depend_service
    description: management 层不直接调用 service 层
    tool: pytest + importlib
    blocking: true
  - test: test_data_ownership
    description: 只有 owner 模块可写对应数据（静态检查）
    tool: 自定义 lint rule
    blocking: false  # Phase 2
  - test: test_state_machine_validity
    description: 所有状态迁移符合 knowledge-state-machine.yaml
    tool: pytest + state machine validator
    blocking: true
```

### 8.7 改造实施优先级

| 优先级 | 交付物 | 阶段 |
|:--:|------|------|
| P0 | `architecture.yaml` | 编码前（本迭代） |
| P0 | `knowledge-state-machine.yaml` | 编码前（本迭代） |
| P0 | `service-card.schema.yaml` | 编码前（本迭代） |
| P1 | 各核心模块 Service Card | 编码中（每个模块交付时） |
| P1 | `observability.yaml` + Logger 结构化改造 | Phase 1 编码 |
| P2 | 架构级测试 | Phase 1 测试阶段 |
| P3 | 权限分级 L0-L5 | Phase 2 |

---

## 九、设计决策索引（更新）

| 决策 | 内容 | 来源 |
|------|------|------|
| D70 | AI-Friendly 合规性改造（Architecture Map + Service Card + 状态机 YAML 化） | 本节 §8 |
| D71 | 知识状态机机器可读化（knowledge-state-machine.yaml 参与 CI） | 本节 §8.4 |
| D72 | 架构级测试纳入下一步工作 | 本节 §8.6 |

---

## 十、下一步工作（原 §八 更新）

1. **交付 AI-Friendly 结构化文件**（P0）：`architecture.yaml` + `knowledge-state-machine.yaml` + `service-card.schema.yaml`
2. **创建项目骨架**：按 §二 结构创建目录和 pyproject.toml
3. **定义编码规范**：.ruff.toml + .pre-commit-config.yaml + observability.yaml 日志格式约束
4. **基础设施编码**：SecurityScanner → LLMClient → Config → Logger（含结构化字段）
5. **数据模型编码**：按 SQLite Schema V1.2 创建 SQLModel 类 + 状态机校验逻辑（从 YAML 生成）
6. **核心引擎编码**：ColdStartEngine → CalibrationEngine → ConflictDetector → PromotionEngine → PruningEngine → DataHealthEngine
7. **适配器编码**：base.py → opencode.py → comate.py
8. **流水线编码**：Step 0（接收）→ Step 1（攒批）→ Step 2a（提炼）→ Step 2b（实体）→ Step 3-6 顺序实现
9. **注入层编码**：InjectionService（AGENTS.md 生成 + 三层路由）
9. **MCP Server 编码**：Tools（get_knowledge / get_experience / search）+ Resources
10. **CLI 编码**：dev init / review / dream / status / config
11. **架构级测试编码**：test_layer_dependency_direction + test_state_machine_validity
12. **集成测试**：端到端流程验证
13. **各模块交付时同步交付 Service Card YAML**（CI 检查）

