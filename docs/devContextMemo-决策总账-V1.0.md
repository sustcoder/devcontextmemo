# devContextMemo 决策总账

> **用途**：所有技术决策的最终权威记录。任何后续设计、实现、审核均以此为准。
> **规则**：①每个决策只有一个最终状态 ②若结论反转，旧结论被显式标记为「已替代」③新决策从 D57 起续编
> **更新原则**：决策确认后立即写入本文件，不可靠对话上下文记忆。

---

## 〇、决策演化路径（关键反转记录）

| 决策 | 6/16 结论 | 6/17 发现 | 6/17 最终结论 | 反转原因 |
|:--:|------|------|------|------|
| **晋升公式权重** | 参数调优报告：全部建议维持 | CC1 宪法式批判：freshness×0.30 违反「无时间衰减」核心承诺 | **改为 calibration_recency** | 6/16 从数学自洽性分析（公式内部逻辑正确），6/17 从宪法原则追溯（需求文档明文承诺无时间衰减）——后者是更高优先级约束 |
| **需求文档版本** | v0.24 当前版本（仍需修订） | CC3 版本漂移：v0.24 仍用 4 状态旧模型 | **全文重写为 V1.0** | 6/16 认为是增量修订，6/17 发现 24 次增量已导致文档内部历史层与当前层无法区分 |
| **MVP 产品定位** | 功能清单导向（6 步流水线完成度） | MA5 差异化危机：80% 与 Claude Code Memory 重叠 | **类级别校准作为杀手功能** | 6/16 未做竞品定位分析，6/17 多角色对抗检查补全 |

---

## 一、架构与基础技术选型（D1-D6）

| # | 决策 | 最终结论 | 日期 |
|:--:|------|------|:--:|
| D1 | 技术栈 | Python 全栈（FastAPI + FastMCP） | 2026-06-07 |
| D2 | 数据库 Phase 1 | SQLite（6 表 Schema V1.2） | 2026-06-10 |
| D3 | 架构路线 | 路线 A（外部独立构建，不 Fork MiMo Code） | 2026-06-11 |
| D4 | AGENTS.md 同步链 | 方案 D（核心动态分离） | 2026-06-12 |
| D5 | KW/KH/KY 分类链 | 路线 A（三元组 Lx×Sy×Depth） | 2026-06-12 |
| D6 | 数据写入流水线 | 六步流水线（采集→解析→签名→分类→存储→注入） | 2026-06-13 |

---

## 二、存储与文件组织（D7-D15）

| # | 决策 | 最终结论 | 日期 |
|:--:|------|------|:--:|
| D7 | MD 权威源 + DB 索引 | 双写模式，MD 是 Single Source of Truth | 2026-06-13 |
| D8 | 目录结构 | `.devContextMemo/staging/` + `.devContextMemo/knowledge/<domain>/` + `.devContextMemo/deprecated/` | 2026-06-13 |
| D9 | Domain 定义 | 业务领域（订单/支付/架构/规范），与 Depth 正交 | 2026-06-14 |
| D10 | 知识分类维度 | **4 维**：Lx（粒度）× Sy（稳定性）× Depth（KH/KW/KY）+ Domain（业务领域） | 2026-06-14 |
| D11 | 废弃「archived」 | 统一用 COLD（保护）+ STALE（缓冲），archived 不再使用 | 2026-06-15 |
| D12 | 晋升目录规则 V2.0 | base_score 决定 staging/knowledge/deprecated 分流 | 2026-06-15 |
| D13 | 绿色通道 | confidence ≥ 0.95 直接进入 knowledge/ | 2026-06-15 |
| D14 | 修剪规则三层体系 | Layer1 质量下限 → Layer2 使用频率 → Layer3 代码锚点 | 2026-06-16 |
| D15 | 容量管理 | 软上限 500（提示）/ 硬上限 2000（强制修剪） | 2026-06-16 |

---

## 三、晋升生命周期（D16-D30）

| # | 决策 | 最终结论 | 日期 |
|:--:|------|------|:--:|
| D16 | 状态模型 | 7 阶段 + 3 子阶段（DRAFT→STAGED→PENDING_REVIEW→CANDIDATE→ACTIVE→STALE→DEPRECATED→DELETED） | 2026-06-15 |
| D17 | STALE 3 子阶段 | suspicious / confirmed / deep，累积折扣 | 2026-06-15 |
| D18 | CANDIDATE 滞回 | 0.82 进 / 0.80 出（V23 锁分机制加持） | 2026-06-16 |
| D19 | T14 无锚点衰减窗口 | 90 天 → STALE(suspicious)，温和提醒 | 2026-06-16 |
| D20 | 无锚点知识保障 | max=0.80 → PENDING_REVIEW（不被永久卡住） | 2026-06-15 |
| D21 | 晋升公式（⚠️ 已替代） | ~~confidence×0.50 + freshness×0.30 + anchor_bonus×0.20~~ | ~~2026-06-15~~ |
| → **D57** | **晋升公式 V2.1（现行）** | **confidence×0.70 + anchor_bonus×0.15 + calibration_recency×0.15** | **2026-06-17** |
| D22 | 晋升 12 条跃迁 | T1-T12 完整定义 | 2026-06-15 |
| D23 | 修剪 11 条跃迁 | T11/T11-b/T12/T13/T14/T18/T19/T22/T23/T24/T25 | 2026-06-16 |
| D24 | 校验 3 条跃迁 | V23 锁分 / V24 / V25 | 2026-06-16 |
| D25 | 冲突 1 条跃迁 | 知识冲突自动降级 | 2026-06-16 |
| D26 | T11-b COLD→STALE | COLD > 365 天 → STALE | 2026-06-16 |
| D27 | T22 DRAFT→DEPRECATED | DRAFT > 90 天 → DEPRECATED | 2026-06-16 |
| D28 | T25 低频→STALE | prune_priority ≥ 0.70 | 2026-06-16 |
| D29 | T21 差异化清理 | low_quality/stale_draft 14d，其他 reason 30d | 2026-06-16 |
| D30 | 总计 27 条跃迁 | 晋升 12 + 修剪 11 + 校验 3 + 冲突 1 | 2026-06-16 |

---

## 四、知识保真体系（D31-D46）

| # | 决策 | 最终结论 | 日期 |
|:--:|------|------|:--:|
| D31 | 更新路径 | 7 条（新对话矛盾/代码变更/用户纠错/已有间矛盾/自然过时/精炼取代/Git合并冲突） | 2026-06-16 |
| D32 | 冲突检测 | 5 层 L0-L5（哈希→语义→矛盾→交叉扫描→代码一致→人工校准） | 2026-06-16 |
| D33 | 冲突分类 | 6 类（事实/时效/范围/粒度/隐式/人为），每类不同策略 | 2026-06-16 |
| D34 | 证据权重 | 6 级（Level 5 活代码 1.0 → Level 0 无证据 0.0），含活性检查+环境区分+怀疑折扣 | 2026-06-16 |
| D35 | 仲裁机制 | evidence_weight × confidence 差值 ≥ 0.30 自动采用（可配置+日志验证） | 2026-06-16 |
| D36 | 安全兜底 | quarantined/ 30 天隔离 + N 次无人确认降级 + UNCERTAIN 三级响应 | 2026-06-16 |
| D37 | 知识巩固引擎 | 完整借鉴 MiMo Code dream（验证+合并+修剪+手动触发） | 2026-06-13 |
| D38 | 对照源数据验证 | 验证对话记录 + 代码 + 文档所有源数据 | 2026-06-13 |
| D39 | 自动合并+修剪 | 合并重复项 + 修剪低信号条目 | 2026-06-13 |
| D40 | dev dream 命令 | 手动触发知识巩固 | 2026-06-13 |
| D41 | 软上限数量 | 500 条（~128K tokens，留 3.9× 余量） | 2026-06-16 |
| D42 | 硬上限数量 | 2000 条（~512K tokens，超过注入窗口必须修剪） | 2026-06-16 |
| D43 | dev review 翻页 | keyboard 翻页交互，支持 skips/accept-all | 2026-06-16 |
| D44 | dev review 布局 | 两栏（左侧条目 + 右侧详情） | 2026-06-16 |
| D45 | dev review 新手引导 | 首次运行显示欢迎页 | 2026-06-16 |
| D46 | dev review 帮助页 | 按 `?` 弹出 | 2026-06-16 |

---

## 五、流水线与实施（D47-D56）

| # | 决策 | 最终结论 | 日期 |
|:--:|------|------|:--:|
| D47 | Step 0 采集层 | 对话记录采集 + crash-recovery + 嵌套标签 | 2026-06-15 |
| D48 | Step 1 攒批层 | JSONL + session_id + batch_start_at + _flushed 防重 | 2026-06-15 |
| D49 | Step 2 提炼层 | LLM 提炼 + domain/concept_tags/code_verified/certainty | 2026-06-15 |
| D50 | Step 3 验证层 | code_verified 设置 + NOT_APPLICABLE + Jaccard + 工厂方法 | 2026-06-15 |
| D51 | Step 4 去重层 | top_similar_id + UPDATE_CANDIDATE + 死代码清理 | 2026-06-16 |
| D52 | Step 5 写入层 | 全面对齐 V2.0 状态模型 | 2026-06-16 |
| D53 | Step 6 巩固层 | V2.0 晋升公式 + 修剪规则 + supplement 合并 | 2026-06-16 |
| D54 | MCP Tool 接口 | 6 个 tool（query/save/update/delete/list/review） | 2026-06-15 |
| D55 | SQLite Schema | 6 表 + FTS5 全文索引 | 2026-06-15 |
| D56 | dev review JSON Schema | DRAFT 语义 + 翻页 + skip + accept-all | 2026-06-16 |

---

## 六、2026-06-17 双重验证新增决策（D57-D62）

### D57 晋升公式修宪（2026-06-17）

**问题**：晋升公式 `freshness×0.30` 按创建时间线性衰减，违反核心诉求②「正确知识永远有效，不因时间新旧影响排序」。

**替代决策 D21**：参数调优报告（2026-06-16）曾建议维持 `0.50/0.30/0.20`，但该分析仅从数学自洽性出发，未追溯宪法原则。

**最终决定**：
```
base_score = confidence × 0.70 + anchor_bonus × 0.15 + calibration_recency × 0.15
```
- `calibration_recency`：距上次校准天数（非创建天数），正确知识永不受罚
- confidence 权重从 0.50→0.70，锚点从 0.20→0.15，校准时效仅作辅助信号

**关联影响**：
- 晋升生命周期设计 V2.0 → V2.1
- 知识保真体系路径⑤（自然过时）自动补上主动提醒缺口
- 参数调优报告 §3（公式权重）标记为「已被 D57 替代」
- 晋升参数调优报告 §3（公式权重）标记为「已替代」

### D58 需求文档全文重写（2026-06-17）

**问题**：v0.24 经历 24 次增量修订，内部形成「历史层」与「当前层」并存：4 状态旧模型、ABC 分类、archived 状态已废弃但仍残留。

**最终决定**：全文重写为 `devContextMemo-项目知识系统-需求文档-V1.0.md`，统一使用：
- V2.1 晋升公式
- 7 阶段 + 3 子阶段状态模型
- 4 维分类（Lx × Sy × Depth + Domain）
- 类级别校准作为 MVP 杀手功能

### D59 类级别校准作为 MVP 杀手功能（2026-06-17）

**问题**：MVP 80% 功能与 Claude Code Memory 重叠，缺乏差异化。

**最终决定**：类级别代码入口校准作为 devContextMemo 核心差异化功能。

**3 个约束**：
1. 校准结果定位为辅助信号（不做自动裁判，精确度~65%）
2. 知识创建时要求 precision_level ≥ L2（至少具体到方法名或行为）
3. 支持 `linked_to_files` 多文件关联（避免跨类行为假阳性）

**实施范围**：Phase 1 做到类级别（文件 git diff 触发），方法名存 DB 不拆 MD 文件。

### D60 原子写入顺序修正（2026-06-17）

**问题**：原设计 DB 先写 → MD 后写，进程崩溃时 MD 可能不完整且 DB 无法从 MD 重建。

**最终决定**：改为 MD 先写（temp → rename 原子操作）→ DB 后写，MD 写入失败则 DB 不更新。

**关联影响**：Step 5 写入层 V1.3 → V1.4。

### D61 LLM 分类基准测试（2026-06-17）

**问题**：LLM 分类「80% 准确率够用」假设从未在 GLM/MiniMax 模型上验证。

**最终决定**：编码前完成基准测试。
- 50 条标注数据集（真实项目知识片段）
- 3 模型测试（GLM-5.2 / MiniMax / DeepSeek）
- 4 轴指标（Depth / Domain / Lx / Sy）

### D62 第一优先级排期（2026-06-17）

**问题**：双重验证发现 22 项待办，需排优先级。

**最终决定**：
- **编码前**（5 项）：D57/D58/D59/D60/D61 —— 设计层面修正，不改就写错
- **编码中**（5 项）：FTS5 参数化绑定 / 路径穿越校验 / OpenCode Schema 校验 / MD 链接约定 / /health 端点 —— 实施层面加固，顺手带上
- **Phase 2**（12 项）：弱审核信息安全悖论 / 存档 / CLI 命令 / Codex / 敏感信息过滤 / 备份灾难恢复 / 开源文档等

---

## 六点五、2026-06-17 编码前设计阶段新增决策（D63-D64）

### D63 项目结构（2026-06-17）

**问题**：编码实现前需要确定 Python 项目目录结构。

**最终决定**：src-layout + setuptools，8 模块结构：

```
src/coderecall/
├── core/        # 核心业务逻辑（pipeline/calibration/conflict/promotion/pruning）
├── models/      # SQLModel 数据模型
├── schemas/     # Pydantic API Schema
├── services/    # 业务逻辑编排
├── storage/     # MD + SQLite 存储层
├── mcp/         # FastMCP Server
├── api/         # REST API 路由
├── cli/         # Typer CLI 命令
└── utils/       # 工具函数
```

**来源**：Python 项目结构调研报告 V1.0 §六

### D64 CLI 框架（2026-06-17）

**问题**：devContextMemo 需要 CLI 命令（dev review/dream/status/config），需选定框架。

**最终决定**：Typer（≥0.12.0）。

**理由**：FastAPI 同作者，类型提示原生支持，异步支持，嵌套命令。

**来源**：Python 项目结构调研报告 V1.0 §五

### D65 编码索引文档（2026-06-17）

**问题**：项目有 70+ 份文档，编码时 AI/开发者不知道该查哪份文档、以什么顺序查、哪些是权威来源、哪些是参考资料。

**最终决定**：创建 `devContextMemo-编码索引-V1.0.md`，放在项目根目录，作为「未来的我」的查阅地图。

**索引内容**：
1. **文档用途分类**（宪法/决策/权威设计/接口定义/审核/参考）
2. **编码查阅表**（按模块列出：写 XX 模块时，读 YY 文档的 ZZ 章节）
3. **上下文压缩自救指南**（只读 3 个文件就能恢复 90% 状态）
4. **文档冲突处理规则**（优先级：需求文档 V1.0 > 决策总账 > 系统架构设计 > 各 Step 细化设计）

**来源**：用户提问「你怎么知道写代码时该用哪些文档」触发

---

## 六点六、2026-06-18 编码阶段新增决策（D66-D68）

### D66 cold → active 不直连（2026-06-18）

**问题**：V2.0 跃迁总表中 cold 只能 → stale(T13) / deprecated（无直接路径），但「冷知识被重新使用」语义上可能需要直接回 active。

**分析**：
- cold 的定义是「正确但低频使用」（code_verified=1 保护中），实质是 active 的子态
- 如果被重新使用，修剪扫描下次运行时 used_count 上升 → 自动恢复为 active（T11 逆向，表中未明列但逻辑自洽）
- 冷知识重新使用的场景极少触发，不值得为此改跃迁表

**最终决定**：严格按 V2.0 走，cold → active 无直接跃迁。冷知识重新激活走 T11 逆向路径（修剪扫描自动识别）。**记录为已知设计偏离，Phase 4 Step 6 修剪规则实现时处理。**

**关联影响**：晋升生命周期 V2.1 跃迁表无需修改，Phase 4 实现时在 `pruning.py` 中补充 cold→active 恢复逻辑。

### D67 字段名全量对齐 Schema V1.2（2026-06-18）

**问题**：测试契约（YAML）、conftest.py mock 数据、Step 5 设计文档 §4.1 INSERT SQL 使用的字段名与 SQLite Schema V1.2 实际列名不一致。

| 位置 | 使用字段名 | Schema 实际列名 |
|------|-----------|----------------|
| conftest.py mock | `lx, sy, knowledge_text` | `granularity, stability`（无 knowledge_text） |
| 测试契约 YAML | `lx, sy, content_hash` | `granularity, stability, content_md5` |
| Step 5 §4.1 INSERT | `Lx, Sy, content_md5` | `granularity, stability`（无 content_md5） |

**最终决定**：**全量对齐 Schema V1.2 列名**（Schema 是数据事实的权威源）。
- `lx` → `granularity`
- `sy` → `stability`
- `knowledge_text` → 删除（P1 原则：DB 不含全文，从 MD 读取）
- `content_hash` → 对齐 Step 5 实际使用的 `content_md5`

**同步范围**：conftest.py + 测试契约 YAML + Step 5 设计文档 §4.1 INSERT SQL。

**关联影响**：Step 5 设计文档 V1.3 §4.1 INSERT SQL 需修正列名，与 Schema V1.2 完全一致。

### D68 Phase 2 SQLModel 仅定义类 + DDL（2026-06-18）

**问题**：Phase 2 的 SQLModel 实现范围不明确——仅定义类 + init_db DDL，还是连基础 CRUD 方法一起实现？

**分析**：
1. Phase 2 定位是基础设施（建表、建连接、建模型），CRUD 是业务逻辑，属于 Phase 4
2. Step 5 Writer 有自己的事务逻辑（先 MD 后 DB、dirty 标记、ROLLBACK），不是简单 `insert()` 能覆盖
3. 过早写 CRUD 会导致 Phase 4 重构或绕过它，接口腐化

**最终决定**：**Phase 2 仅交付 SQLModel 类定义 + `init_db()` DDL 函数**。CRUD 方法留给 Phase 4 Step 5 Writer 实现时按需添加。

**Phase 2 交付物**：
- `models.py`：SQLModel 类定义（8 张表）
- `database.py`：`init_db()` 建表 + 建索引 + PRAGMA 设置
- `conftest.py` 修正：mock 数据对齐 Schema 字段名（D67）

**关联影响**：编码索引 Phase 2 模块定义无需修改，CRUD 不在此阶段范围内。

---

## 六点七、2026-06-18 Phase 3 启动决策（D69-D71）

### D69 Phase 3 DB 同步范围：仅映射不写入（2026-06-18）

**问题**：编码索引说 Phase 3 验证「能写入 MD 文件 + 同步到 DB」，但 D68 已决定 Phase 2 仅 DDL 无 CRUD。Phase 3 的 DB 同步如何界定？

**分析**：
1. 原子写入设计 V1.0 明确写入顺序 MD → DB，MD 是 SSoT
2. Phase 3 交付的是 `storage/markdown.py`，不是 `core/pipeline/writer.py`
3. Phase 2 没有 CRUD 方法，Phase 3 自己用裸 sqlite3 写 DB 会导致 Phase 4 两个写入路径不一致

**最终决定**：**Phase 3 只做纯 MD 操作**（markdown.py 写/读/解析 MD + YAML frontmatter + 原子写入工具），提供 `to_db_dict(md_path, frontmatter) → dict` 映射方法供 Phase 4 调用。**不实际写 DB。**

`to_db_dict()` 返回的 dict 字段名对齐 Schema V1.2 列名（D67），Phase 4 Writer 拿到后一行 INSERT 即可。

**关联影响**：编码索引 Phase 3 验证标准从「能写入 MD 文件 + 同步到 DB」修正为「能写入 MD 文件 + 提供 DB 映射」。

### D70 绿色通道路由：调用方决策（2026-06-18）

**问题**：绿色通道（confidence ≥ 0.95 → knowledge/，否则 → staging/）的决策放在 markdown.py 内部还是由调用方决定？

**分析**：
1. V2.0 跃迁 T1/T2 明确：绿色通道是 Step 5 Writer 的决策，不是存储层的决策
2. Step 5 设计 V1.3 §6.1：`write_one()` 中根据 confidence 选择目标目录
3. markdown.py 是存储层，不应承担业务规则（单一职责）

**最终决定**：**调用方决策**。MarkdownStore 提供 `write_to_staging(content)` 和 `write_to_knowledge(domain, content)` 两个方法，Phase 4 Writer 根据 confidence 选择调用哪个。markdown.py 内部不做阈值判断。

**关联影响**：markdown.py 接口设计需提供两个写入方法（而非一个带参数的路由方法）。

### D71 MD frontmatter 字段：14 个（2026-06-18）

**问题**：Schema V1.2 的 knowledge_index 有 25+ 字段，Step 5 设计 §3.1 的 frontmatter 示例约 12 个字段，调研文档 §3.6 仅 5 个字段。Phase 3 实现 frontmatter 时选哪个范围？

**分析**：
- 25+ 字段一步到位：prune_priority/certainty/freshness/embedding 此时无值，写了也是 NULL
- 仅 11 个基础字段：漏了 code_verified/concept_tags/source_session，Phase 3 能拿到的数据不存，Phase 4 得回头补
- Phase 3 实际能填的字段 = 基础身份字段 + Step 2 已产出的分类字段

**最终决定**：**14 个字段**：

| 分类 | 字段 |
|------|------|
| 身份 | id, title, uri, created_at, updated_at |
| 分类 | granularity, stability, depth, domain |
| 状态 | status, confidence |
| 来源 | source_session |
| 扩展 | code_verified, concept_tags |

**Phase 5/6 按需补充**：prune_priority, certainty, freshness, embedding, calibration_status, used_count, last_used_at 等。

**关联影响**：`to_db_dict()` 返回 14 个字段的 dict，markdown.py 的 YAML frontmatter 生成也以这 14 个字段为准。

---

## 六点八、2026-06-18 Phase 4 启动决策（D72-D75）

### D72 Phase 4 拆 3 子 Phase（2026-06-18）

**问题**：Phase 4 规模巨大（6 个 Step + 3 个 adapter + utils/llm + utils/hash + 6 份契约重写）。如何拆分？

**分析**：
1. 编码索引 Phase 4 覆盖 `core/pipeline/` 全部 8 个 Step（Step 0→6）
2. 按自然依赖边界可拆为：4a(采集+攒批+适配器，不依赖 LLM) / 4b(LLM 提炼 Step 2a+2b，依赖 LLM 和 4a 输出) / 4c(验证+去重+写入 Step 3-5，依赖 4b 输出)
3. 每组的验收标准独立可测——4a 可用 mock 消息测试，4b 需要 LLM 但可独立迭代 Prompt，4c 依赖上游格式稳定后测试

**最终决定**：**Phase 4 拆为 3 个子 Phase**。
- **4a**：`adapters/` + `utils/llm.py` + `utils/hash.py` + Step 0(receiver.py) + Step 1(batcher.py)
- **4b**：Step 2a(extractor.py) + Step 2b(entity_extractor.py)
- **4c**：Step 3(validator.py) + Step 4(deduplicator.py) + Step 5(writer.py) + 端到端测试

**关联影响**：编码索引 Phase 4 定义从「Step 0→6」修正为「Step 0→5」（Step 6 归 Phase 5，见 D73）。

---

### D73 Step 6 consolidator 归 Phase 5（2026-06-18）

**问题**：Step 6 的契约明确依赖 promotion V2.1 公式 + pruning 规则。编码索引将 promotion.py/pruning.py 列为 Phase 5。Step 6 归哪个 Phase？

**分析**：
1. 编码索引 Phase 4 定义为「端到端写入一条知识」——Step 6 是异步巩固，不在写入链路
2. 编码索引 Phase 5 定义为「写入 10 条知识后触发晋升 + 修剪」——正是 Step 6 的职责
3. Step 6 契约 preconditions 明确要求「promotion formula V2.1 is loaded + pruning rules are loaded」
4. Step 6 细化设计 V1.2 对齐文档就是晋升生命周期 V2.0 + 修剪规则 V1.0
5. Phase 4 内实现最小版 consolidator + 硬编码阈值 → Phase 5 再抽象 = 重复开发

**最终决定**：**Step 6 归 Phase 5**，与 promotion.py/pruning.py 同批实现。Phase 4 只到 Step 5 写入。Phase 4 验收标准：「一条知识从多源到落盘」——这不需要 Step 6。

**关联影响**：编码索引 Phase 4 模块列表移除 consolidator.py（移入 Phase 5）。

---

### D74 content_hash/semantic_hash 仅作 JSONL 中间态（2026-06-18）

**问题**：Step 3 validator 的 content_hash/semantic_hash 与 Schema V1.1 冲突（knowledge_index 表无任何 hash 字段）。如何处理？

**分析**：
1. Schema V1.1 的 knowledge_index 表无任何 hash 字段（确认：grep 结果为 0 匹配）
2. D67 已决定字段名全量对齐 Schema，但 Schema 本身也没有 content_md5 列
3. content_hash（SHA-256）和 semantic_hash（SimHash）的用途是 Step 3→4 流转——Step 4 去重需要对比已有知识的 hash
4. 这两个 hash 存在 JSONL 中间态即可，不需要持久化到 DB

**最终决定**：**content_hash/semantic_hash 仅作 JSONL 中间态**（Step 3→4 流转用），不落 DB。Step 4 去重时从 JSONL 读 hash，不查 DB 的 hash 列。DB 的 knowledge_index 表不加任何 hash 字段。

**关联影响**：Step 3 的 Candidate dataclass 保留 content_hash/semantic_hash 字段，Step 5 Writer 写 DB 时不携带这两个字段。

---

### D75 去重算法：SimHash + Jaccard + 预留 embedding 接口（2026-06-18）

**问题**：三方说法不一致——流水线设计说 MD5+cosine(embedding)、契约说 Jaccard+semantic_hash、Schema 有 embedding 列但 Phase 4 无 embedding 模型。选哪个？

**分析**：
1. Phase 4 MVP 必须能独立运行——不能依赖一个尚未接入的 embedding 模型（embo-01）
2. SimHash + Jaccard 是纯确定性算法——不需要外部服务，适合 Phase 4 自包含测试
3. 测试契约是测试的权威源——契约说 Jaccard，代码应该实现 Jaccard
4. 但 embedding/cosine 是更强的语义去重手段——Phase 5/6 接入后应平滑升级

**最终决定**：**SimHash + Jaccard + 预留 embedding 接口**。

| 算法 | Phase 4 | Phase 5/6 |
|------|:--:|:--:|
| MD5 精确去重 | ✅ 完全实现 | — |
| SimHash 语义签名 | ✅ 完全实现 | — |
| Jaccard 相似度 | ✅ 完全实现 | — |
| cosine 相似度 | ❌ 接口预留（`cosine_enabled=False`） | ✅ 接入 embedding 模型后开启 |

**关联影响**：Deduplicator 配置保留 `cosine_enabled` 开关，默认 False。Phase 5/6 接入 embedding 模型后改为 True 即可，无需重构 Deduplicator。

---

## 六点九、2026-06-18 Phase 5 Schema 迁移决策（D76）

### D76 Schema V1.3：补充 V2.0 §8 的 7 个字段（2026-06-18）

**问题**：V2.0 §8 要求 knowledge_index 表补充 7 个字段（stale_sub_phase/stale_check_count/stale_entered_at/deprecation_reason/restored_count/locked_promotion_score/flag），但 D68 决定 Phase 2 仅 DDL 不写 CRUD。Phase 5 的 promotion/pruning 依赖这些字段。如何处理？

**分析**：
1. D68 约束的是「Phase 2 不写 CRUD 方法」，不是「Schema 永不演进」。Schema 从 V1.1→V1.2→V1.3 是设计文档驱动的正常版本演进
2. 7 个字段中 4 个（stale_sub_phase/stale_check_count/stale_entered_at/locked_promotion_score）不持久化会导致功能逻辑错误：
   - stale_sub_phase：STALE 3 子阶段行为不同（折扣 0.80/0.60/0.40），不持久化无法知道当前子阶段
   - stale_check_count：T16 要求累积 3 次才 → DEPRECATED，不持久化每次都是第 1 次 → 永远不到第 3 次
   - stale_entered_at：T14/T16/T25 依赖「进入 STALE 后过了多少天」，不持久化无法计算
   - locked_promotion_score：T6 要求 CANDIDATE 二次确认用首轮锁定分数，不持久化会因 freshness 衰减导致震荡
3. 另 3 个字段（deprecation_reason/restored_count/flag）不持久化虽不致命但会导致功能退化（无法按原因恢复、无法标记特殊状态）

**最终决定**：**Phase 5 补充全部 7 个字段，作为 Schema V1.3 迁移**。

迁移文件：`storage/migrations/v1_3_add_v2_fields.py`

```sql
ALTER TABLE knowledge_index ADD COLUMN stale_sub_phase TEXT;
ALTER TABLE knowledge_index ADD COLUMN stale_check_count INTEGER DEFAULT 0;
ALTER TABLE knowledge_index ADD COLUMN stale_entered_at TEXT;
ALTER TABLE knowledge_index ADD COLUMN deprecation_reason TEXT;
ALTER TABLE knowledge_index ADD COLUMN restored_count INTEGER DEFAULT 0;
ALTER TABLE knowledge_index ADD COLUMN locked_promotion_score REAL;
ALTER TABLE knowledge_index ADD COLUMN flag TEXT;
```

**设计理由**：
- 全部字段有合理 DEFAULT 值（NULL/0），对已有数据无影响
- SQLite 的 ALTER TABLE ADD COLUMN 是 O(1) 操作（只改 schema 元数据，不重写表）
- Phase 2 的 SQLModel 类定义需同步更新（新增这 7 个字段的 Column 定义）

**关联影响**：Schema 文档版本从 V1.2 → V1.3。Phase 2 models.py 需补充这 7 个字段的 Column 定义（Phase 5 迁移时更新，或提前更新但 Phase 5 之前不写入）。

---

## 七、已替代决策索引

| 原决策 | 替代决策 | 替代原因 |
|:--:|:--:|------|
| D21 晋升公式 V2.0 (0.50/0.30/0.20) | **D57** V2.1 (0.70/0.15/0.15) | 违反「无时间衰减」宪法原则 |
| 参数调优报告 §3 公式权重分析 | **D57** | 仅从数学自洽性分析，未追溯宪法原则 |

---

## 八、决策状态速查

- ✅ **已定稿，不可逆转**：D1-D6（架构/技术栈）、D16-D17（状态模型）、D31-D36（知识保真）
- ✅ **已定稿，编码实现即可**：D7-D15（存储/组织）、D22-D30（跃迁规则）、D47-D56（流水线）、D59（杀手功能）、D60（原子写入）
- ✅ **新定稿，替代旧决策**：D57（晋升公式）、D58（需求文档）
- ✅ **新定稿，编码前设计阶段**：D61（基准测试）、D62（类级别校准）、D63（项目结构）、D64（CLI框架）、**D65（编码索引）**
- ✅ **新定稿，编码阶段决策**：D66（cold→active不直连）、D67（字段名全量对齐Schema）、D68（Phase2仅DDL）、D69（Phase3仅MD映射不写DB）、D70（绿色通道调用方决策）、D71（frontmatter 14字段）、D72（Phase4拆3子Phase）、D73（Step6归Phase5）、D74（hash仅JSONL中间态）、D75（SimHash+Jaccard+预留embedding）、D76（Schema V1.3补充7字段）
- ✅ **编码前提条件全部满足** —— 可进入编码实现阶段

---

> **版本**：V1.0 | **创建日期**：2026-06-17 | **最后更新**：2026-06-18（新增 D66-D76）
> **下次更新时机**：任一决策发生变更或新增决策时立即更新
