# Graph Report - devContextMemo  (2026-06-19)

## Corpus Check
- 102 files · ~94,103 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1556 nodes · 3871 edges · 50 communities detected
- Extraction: 46% EXTRACTED · 54% INFERRED · 0% AMBIGUOUS · INFERRED: 2100 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]

## God Nodes (most connected - your core abstractions)
1. `SQLiteStore` - 340 edges
2. `MarkdownStore` - 210 edges
3. `SearchEngine` - 108 edges
4. `MockLLMClient` - 104 edges
5. `Extractor` - 85 edges
6. `Batcher` - 82 edges
7. `EntityExtractor` - 80 edges
8. `Validator` - 75 edges
9. `Consolidator` - 72 edges
10. `Writer` - 65 edges

## Surprising Connections (you probably didn't know these)
- `db_store()` --calls--> `SQLiteStore`  [INFERRED]
  tests/unit/test_conflict.py → src/devcontext/storage/sqlite.py
- `db_store()` --calls--> `SQLiteStore`  [INFERRED]
  tests/unit/test_search.py → src/devcontext/storage/sqlite.py
- `db_store()` --calls--> `SQLiteStore`  [INFERRED]
  tests/unit/test_injection.py → src/devcontext/storage/sqlite.py
- `search_engine()` --calls--> `SearchEngine`  [INFERRED]
  tests/unit/test_injection.py → src/devcontext/storage/search.py
- `Unit tests for CLI commands — init/status/config/review/dream。` --uses--> `SQLiteStore`  [INFERRED]
  tests/unit/test_cli.py → src/devcontext/storage/sqlite.py

## Communities

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (148): dream_command(), dev dream 命令 — 主动扫描（巩固 + 校准）。  用法：     dev dream [--dry-run] [--scope SCOPE], dev dream：巩固（晋升+修剪）+ 校准。, init_command(), dev init 命令 — 冷启动（创建 .devContextMemo/ 目录 + 初始化 DB）。  用法：     dev init [--force], 冷启动：创建 .devContextMemo/ 目录结构 + 初始化 SQLite 数据库。, dev review 命令 — 审核交互（list/approve/reject/restore）。  用法：     dev review list [--s, 恢复知识（deprecated → staged）。 (+140 more)

### Community 1 - "Community 1"
Cohesion: 0.02
Nodes (102): Exception, MCP Server 层 — Tool 注册 + Resource 定义。  暴露给 OpenCode 等 AI 编程工具的知识检索接口。  Phase 8（V, list_knowledge_resources(), MCP Resource 模板 — knowledge://{id} 等。  提供 MCP Resource URI 模板，AI 可通过 URI 直接读取知识内, 读取 knowledge://{id} resource。      MCP Resource URI 格式：``knowledge://kw-20260614, 列出可用的 knowledge:// resource。      Args:         sqlite_store: SQLiteStore 实例。, read_knowledge_resource(), MCPServer (+94 more)

### Community 2 - "Community 2"
Cohesion: 0.04
Nodes (95): BaseAdapter, 数据源适配器抽象基类。      将 AI 编程工具的对话日志转换为统一 JSONL 格式。, CursorAdapter, Cursor 适配器 — 最小实现（预留接口）。  Cursor 的对话日志导出格式待调研，当前提供骨架实现。 实际采集逻辑在确定 Cursor 数据源格式后补, Cursor 对话日志适配器（最小实现）。      Args:         source_path: Cursor 数据源路径。, 采集 Cursor 对话记录（待实现）。          Raises:             NotImplementedError: Cursor 数据, BaseAdapter, _make_conversation() (+87 more)

### Community 3 - "Community 3"
Cohesion: 0.03
Nodes (75): ABC, normalize(), 适配器基类 — 接口定义。  所有数据源适配器必须实现本接口，输出统一 JSONL 格式。  统一 JSONL 格式（每行一个 dict）：     {, 批量标准化（默认逐条调用 normalize，子类可覆写优化）。          Args:             raw_records: 原始记录列表。, CalibrationEngine, CalibrationEvent, CalibrationResult, 校准引擎 — 代码变更触发 + LLM 语义对比 + V6/V11/V12 修补。  职责： 1. 监听 8 种触发事件（E1-E8），最核心是 E1（git (+67 more)

### Community 4 - "Community 4"
Cohesion: 0.03
Nodes (76): BaseModel, Enum, Category, 知识三元组分类 (granularity, stability, depth) + domain。      三元组是知识条目的核心分类维度，配合 domain, 检查 domain 是否在领域树中注册。          Args:             domain_tree: 领域树字典，键为领域名。, 返回三元组元组 (granularity, stability, depth)。          Returns:             三元组，如 ("L, Depth, Granularity (+68 more)

### Community 5 - "Community 5"
Cohesion: 0.03
Nodes (42): atomic_write_md(), PathTraversalError, 原子写入与路径校验 — MD first → DB second 的基础设施。  提供： - ``PathTraversalError``：路径穿越攻击异常 -, 原子写入 MD 文件：tmp → fsync → rename。      实现 §2.2 的原子写入协议：     1. 确保父目录存在     2. 写入临, 路径穿越攻击尝试。      当用户输入拼接路径后逃逸出基目录时抛出。, 清理单段路径输入。      移除路径分隔符、空字节、控制字符，保留可读字符。     用于单个目录名或文件名组件的预处理。      Args:, 校验用户输入拼接后不会逃逸出 ``base_dir``。      采用「直接 resolve + 前缀校验」策略（不预先清理 ``..``），     这样, sanitize_path_segment() (+34 more)

### Community 6 - "Community 6"
Cohesion: 0.03
Nodes (47): OpenCodeAdapter, OpenCode 适配器 — SQLite → 统一 JSONL 转换。  从 OpenCode（CodeBuddy）本地 SQLite 数据库提取对话日志。, 标准化单条记录（OpenCode 已在 collect 中完成标准化）。          Args:             raw_record: 原始记录, OpenCode SQLite 对话日志适配器。      读取 OpenCode 的 SQLite 数据库，将 session + message + par, 从 OpenCode SQLite 采集所有会话记录。          Args:             source_path: 可选，覆盖 db_pat, config_get(), dev config 命令 — 配置管理。  用法：     dev config get [KEY]     dev config set KEY VALUE, _create_test_opencode_db() (+39 more)

### Community 7 - "Community 7"
Cohesion: 0.06
Nodes (34): _make_llm_response(), Module tests for Step 2a — LLM 知识提炼 + 四轴分类 + 时间提取。  用 MockLLMClient 测试，验证： 1. 产出, LLM 返回空数组表示无知识可提炼（正常情况）。, 无法推断时间时 occurred_at 为 null。, 对话超 32K token 时截断，confidence 上限 0.80。, TestExtractorBasic, TestExtractorEdgeCases, TestExtractorTimeExtraction (+26 more)

### Community 8 - "Community 8"
Cohesion: 0.04
Nodes (33): calculate_base_score(), compute_anchor_bonus(), compute_calibration_recency(), evaluate_promotion(), evaluate_stale_transition(), 晋升评估 — V2.1 公式 + 滞回机制 + STALE 子阶段。  公式（V2.1 修宪 — 2026-06-17）：     promotion_scor, 计算代码锚点加分。      Args:         code_verified: 0 或 1。      Returns:         1.0（有锚点, 评估单条知识的晋升决策。      根据 V2.0 跃迁规则 T3/T4/T5/T6 判断新状态。      Args:         base_score: (+25 more)

### Community 9 - "Community 9"
Cohesion: 0.05
Nodes (40): L1: 语义签名相似检测。          Args:             new_knowledge: 新知识记录。          Returns:, Step 4: Jaccard + 语义去重。  职责： 1. 读取 knowledge JSONL（Step 3 输出，含 content_hash/sema, 处理 knowledge JSONL，添加去重字段。          Args:             knowledge_path: knowledge, 对单条记录去重。          Args:             record: knowledge 记录（含 content_hash/semantic, _read_jsonl(), _write_jsonl(), Step 3: 签名 + 语义验证 + code_verified 设置。  职责： 1. 读取 knowledge JSONL（Step 2b 输出） 2., 处理 knowledge JSONL，添加 hash + code_verified 字段。          Args:             knowle (+32 more)

### Community 10 - "Community 10"
Cohesion: 0.06
Nodes (24): check_capacity(), evaluate_layer1(), evaluate_layer2(), evaluate_layer3(), 修剪规则 — 三层体系 + 容量管理 + supplement 保护。  三层修剪体系（V2.0 + V1.1 修剪规则）：     Layer 1: 质量下限, Layer 2: 使用频率 — COLD > 365 天 → STALE；prune_priority ≥ 0.70 → STALE。      Args:, Layer 3: 代码锚点 — 无锚点 + 时间/使用触发 → STALE(suspicious)。      T14: ACTIVE(code_verifie, 容量管理检查。      Args:         total_count: 知识库总条目数。      Returns:         决策结果 dict (+16 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (24): db_store(), _make_knowledge_record(), md_store(), Module tests for Step 5 — MD → DB 原子写入（绿色通道 + MD first → DB second）。, is_duplicate=True 的记录被跳过。, 绿色通道（confidence >= 0.95 → knowledge/）。, MD first → DB second。, SQLiteStore=None 时只写 MD。 (+16 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (8): Unit tests for injection routing — Lx × Sy × Depth → L1/L2/L3., L2 按需检索: S1/S2 + KH/KY., L3 按需+专项保护: everything else., L1+L2 > 4K tokens → truncation: S1 priority > S2 > drop L3., TestRouteToL1, TestRouteToL2, TestRouteToL3, TestTruncationStrategy

### Community 13 - "Community 13"
Cohesion: 0.12
Nodes (11): Integration tests for engine cross-module workflows.  These tests verify that en, Promotion engine + Pruning engine integration., After promotion evaluation, pruning rules should apply to stale items., Conflict detection cross-module integration., Two items with same top_similar_id should be in same conflict_group., Items with different top_similar_id should not share conflict group., Data health check integration., When MD content_hash != DB content_hash, health check should detect drift. (+3 more)

### Community 14 - "Community 14"
Cohesion: 0.18
Nodes (10): _build_record(), _format_conversation(), Step 2a: LLM 知识提炼 — 分类 + 时间提取。  职责： 1. 读取 batch JSONL（Step 1 输出） 2. 构造 Prompt →, 构建 LLM User Prompt。          包含对话记录 + 已有领域树（供 domain 分类参考）。         若 token 超限则截, 调用 LLM 提炼知识（含重试 + 校验）。          Args:             user_prompt: User Prompt 文本。, 解析 + 校验 LLM 输出。          Args:             content: LLM 返回的 JSON 字符串。, 处理 batch JSONL，输出 summary JSONL。          Args:             batch_path: batch JS, _read_jsonl() (+2 more)

### Community 15 - "Community 15"
Cohesion: 0.15
Nodes (8): _count_tokens(), Step 1: 攒批 — 原始存储按 session 分批 → JSONL 缓冲。  职责： 1. 扫描 ``raw_dir/`` 下的 ``session_*, 扫描 raw_dir，返回 (session_id, path) 列表。          Returns:             (session_id,, 加载已 flush 的 session ID 集合。          通过扫描 staging_dir 下的 ``_meta.yaml`` 文件提取已处理的, 标记 session 为已 flush（通过 _meta.yaml 隐式完成，此处无需额外操作）。          ``_write_batch`` 已经写了, 写入 batch JSONL + _meta.yaml。          Args:             session_id: 会话 ID。, 扫描 raw 目录，攒批未 flush 的 session。          Args:             flush_all: True 表示全量模式, _read_jsonl()

### Community 16 - "Community 16"
Cohesion: 0.22
Nodes (7): _build_prompt(), Step 2b: 实体 + 关系提取。  职责： 1. 读取 summary JSONL（Step 2a 输出） 2. 对每条知识调用 LLM 提取实体（cla, 处理 summary JSONL，输出 knowledge JSONL。          Args:             summary_path: su, 对单条知识提取实体 + 关系（含重试）。          Args:             summary: summary 记录。          Re, 解析 + 校验 LLM 输出。          Args:             content: LLM 返回的 JSON 字符串。          R, _read_jsonl(), _write_jsonl()

### Community 17 - "Community 17"
Cohesion: 0.22
Nodes (5): ComateAdapter, Comate 适配器 — JSON 导出 → 统一 JSONL 转换。  从 Comate 导出的 JSON 文件读取对话日志，转换为统一 JSONL 格式。, Comate JSON 导出适配器。      Args:         json_path: Comate 导出的 JSON 文件路径。, 从 Comate JSON 导出文件采集会话记录。          Args:             source_path: 可选，覆盖 json_pat, 标准化单条记录。          Args:             raw_record: 原始记录。          Returns:

### Community 18 - "Community 18"
Cohesion: 0.38
Nodes (5): Step 0: 统一接收 — 适配器路由 + 原始会话存储。  职责： 1. 通过适配器从数据源采集对话日志（OpenCode SQLite / Comate, 采集 + 剥壳 + 落盘。          Args:             source_path: 数据源路径（传给 adapter.collect）。, _strip_noise(), _validate_records(), _write_jsonl()

### Community 19 - "Community 19"
Cohesion: 0.5
Nodes (3): load_fixture(), Shared test fixtures as JSON files for contract tests.  These files provide stan, Load a JSON fixture file.

### Community 20 - "Community 20"
Cohesion: 0.5
Nodes (3): BaseSettings, 全局配置管理 — pydantic-settings。  从环境变量和配置文件加载应用配置。, Settings

### Community 21 - "Community 21"
Cohesion: 0.5
Nodes (3): 应用入口 — FastAPI + FastMCP 挂载。  启动 devContextMemo 服务。, 启动 devContextMemo 服务（占位）。, serve()

### Community 22 - "Community 22"
Cohesion: 0.5
Nodes (3): callback(), CLI 应用入口 — Typer 实例 + 5 个命令注册。  命令：     dev init: 冷启动（创建 .devContextMemo/ + 初始化, devContextMemo 知识管理 CLI。

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): devContextMemo（码上记忆）— AI 编程工具对话知识管理系统。  把 AI 编程工具的对话熔炼成结构化项目知识，通过 MCP Tool 按需注入

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): 数据健康引擎 — 9 类数据校正。  H1: MD-DB 索引漂移  H2: 多版本冲突  H3: FTS5 索引漂移 H4: 知识过期       H5: 冗

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (1): 冷启动引擎 — 项目扫描 → LLM 骨架生成。  在项目首次接入时，扫描项目结构并通过 LLM 生成初始知识骨架， 降低人工初始化的摩擦。

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): 8 Step 写入流水线 — 对话日志 → 结构化知识 → 持久化 → 晋升。  Step 0: receiver      — 统一接收（适配器路由 + 原始

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (1): 多数据源适配器（统一接收层）。  将 OpenCode、Comate、Cursor 等 AI 编程工具的对话日志 转换为统一的 JSONL 格式，存入原始会话存

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): 安全扫描器 — 三层检测。  L1: 提示注入检测（模式匹配） L2: 凭据泄露检测（正则匹配） L3: Unicode 不可见字符检测

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (1): 工具函数层 — 贯穿各层的横切关注点。  包含： - hash.py: 内容签名（SHA-256）+ 语义签名 - diff.py: 文件 Diff + AST

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): 文件 Diff — 文件差异解析 + AST 分析。

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (1): 路径校验 — realpath + 遍历防护。  防止路径遍历攻击，确保所有文件操作在项目目录范围内。

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (1): API 请求/响应 Schema — Pydantic 模型定义。

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (1): 检索 Schema — Pydantic 请求/响应模型。

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): 知识操作 Schema — Pydantic 请求/响应模型。

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): 依赖注入 — get_db / get_config 等。

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): REST API 层 — FastAPI 路由 + 依赖注入。

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): /api/knowledge/* 端点 — 知识 CRUD API。

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): 业务逻辑层 — 编排业务流程，连接交互层与管理引擎层。  包含： - knowledge.py: 知识 CRUD + 检索编排 - pipeline.py: 流

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): 主动扫描服务 — 代码变更 → 知识校准。  监听 Git 变更，触发校准引擎和数据健康检查。

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): 流水线编排服务 — Step 0→6 全链路。  协调 8 Step 写入流水线的执行顺序与数据传递。

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): 验证单条记录：计算 hash + 设置 code_verified。          Args:             record: knowledge

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): 估算文本的 token 数（简化版）。          中文约 1 token/字符，英文约 1 token/4 字符。         取折中值 ``len

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): 读取 JSONL 文件。          Args:             path: JSONL 文件路径。          Returns:

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): 数据源标识（opencode/comate/cursor）。

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): 从数据源采集原始会话记录。          Args:             source_path: 数据源路径或标识符（SQLite 文件路径 / JS

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): 将单条原始记录标准化为统一格式。          Args:             raw_record: 原始记录。          Returns:

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): 调用 LLM 对话接口。          Args:             messages: OpenAI 格式的消息列表。             mo

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): FTS5 是否可用（init_db 后才有意义）。

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): 将任意文本转为安全的文件名段。          移除非法字符、折叠空白、截断长度。          Args:             text: 原始文本

## Knowledge Gaps
- **176 isolated node(s):** `Unit tests for pruning engine — 3-layer system and capacity management.`, `Layer 1: 质量下限 — DRAFT 清理。`, `T19: confidence < 0.6 AND age > 30d → low_quality。`, `T11: active + code_verified=1 + 未使用 → cold。`, `T14: 无锚点 + age > 90d → STALE(suspicious)。` (+171 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 23`** (2 nodes): `devContextMemo（码上记忆）— AI 编程工具对话知识管理系统。  把 AI 编程工具的对话熔炼成结构化项目知识，通过 MCP Tool 按需注入`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (2 nodes): `数据健康引擎 — 9 类数据校正。  H1: MD-DB 索引漂移  H2: 多版本冲突  H3: FTS5 索引漂移 H4: 知识过期       H5: 冗`, `health.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (2 nodes): `冷启动引擎 — 项目扫描 → LLM 骨架生成。  在项目首次接入时，扫描项目结构并通过 LLM 生成初始知识骨架， 降低人工初始化的摩擦。`, `init.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (2 nodes): `8 Step 写入流水线 — 对话日志 → 结构化知识 → 持久化 → 晋升。  Step 0: receiver      — 统一接收（适配器路由 + 原始`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (2 nodes): `多数据源适配器（统一接收层）。  将 OpenCode、Comate、Cursor 等 AI 编程工具的对话日志 转换为统一的 JSONL 格式，存入原始会话存`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (2 nodes): `security.py`, `安全扫描器 — 三层检测。  L1: 提示注入检测（模式匹配） L2: 凭据泄露检测（正则匹配） L3: Unicode 不可见字符检测`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (2 nodes): `__init__.py`, `工具函数层 — 贯穿各层的横切关注点。  包含： - hash.py: 内容签名（SHA-256）+ 语义签名 - diff.py: 文件 Diff + AST`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (2 nodes): `diff.py`, `文件 Diff — 文件差异解析 + AST 分析。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (2 nodes): `path.py`, `路径校验 — realpath + 遍历防护。  防止路径遍历攻击，确保所有文件操作在项目目录范围内。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (2 nodes): `API 请求/响应 Schema — Pydantic 模型定义。`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (2 nodes): `检索 Schema — Pydantic 请求/响应模型。`, `search.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (2 nodes): `知识操作 Schema — Pydantic 请求/响应模型。`, `knowledge.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (2 nodes): `依赖注入 — get_db / get_config 等。`, `deps.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (2 nodes): `REST API 层 — FastAPI 路由 + 依赖注入。`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (2 nodes): `/api/knowledge/* 端点 — 知识 CRUD API。`, `knowledge.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (2 nodes): `业务逻辑层 — 编排业务流程，连接交互层与管理引擎层。  包含： - knowledge.py: 知识 CRUD + 检索编排 - pipeline.py: 流`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (2 nodes): `主动扫描服务 — 代码变更 → 知识校准。  监听 Git 变更，触发校准引擎和数据健康检查。`, `dream.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (2 nodes): `流水线编排服务 — Step 0→6 全链路。  协调 8 Step 写入流水线的执行顺序与数据传递。`, `pipeline.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `验证单条记录：计算 hash + 设置 code_verified。          Args:             record: knowledge`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `估算文本的 token 数（简化版）。          中文约 1 token/字符，英文约 1 token/4 字符。         取折中值 ``len`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `读取 JSONL 文件。          Args:             path: JSONL 文件路径。          Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `数据源标识（opencode/comate/cursor）。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `从数据源采集原始会话记录。          Args:             source_path: 数据源路径或标识符（SQLite 文件路径 / JS`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `将单条原始记录标准化为统一格式。          Args:             raw_record: 原始记录。          Returns:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `调用 LLM 对话接口。          Args:             messages: OpenAI 格式的消息列表。             mo`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `FTS5 是否可用（init_db 后才有意义）。`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `将任意文本转为安全的文件名段。          移除非法字符、折叠空白、截断长度。          Args:             text: 原始文本`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SQLiteStore` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.350) - this node is a cross-community bridge._
- **Why does `MarkdownStore` connect `Community 0` to `Community 1`, `Community 2`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.182) - this node is a cross-community bridge._
- **Why does `Consolidator` connect `Community 2` to `Community 0`, `Community 8`, `Community 10`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Are the 330 inferred relationships involving `SQLiteStore` (e.g. with `Global test fixtures and configuration for devContextMemo.` and `Create a temporary workspace directory with .devContextMemo/ and .devcontext/raw`) actually correct?**
  _`SQLiteStore` has 330 INFERRED edges - model-reasoned connections that need verification._
- **Are the 197 inferred relationships involving `MarkdownStore` (e.g. with `Global test fixtures and configuration for devContextMemo.` and `Create a temporary workspace directory with .devContextMemo/ and .devcontext/raw`) actually correct?**
  _`MarkdownStore` has 197 INFERRED edges - model-reasoned connections that need verification._
- **Are the 103 inferred relationships involving `SearchEngine` (e.g. with `TestSearchEngineBasic` and `TestStatusFilter`) actually correct?**
  _`SearchEngine` has 103 INFERRED edges - model-reasoned connections that need verification._
- **Are the 99 inferred relationships involving `MockLLMClient` (e.g. with `TestEvidenceWeights` and `TestCodeActiveCheck`) actually correct?**
  _`MockLLMClient` has 99 INFERRED edges - model-reasoned connections that need verification._