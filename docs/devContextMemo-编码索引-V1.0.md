# devContextMemo 编码索引 V1.0

> **本文档目的**：告诉 AI（和开发者）写代码时该查哪些文档、以什么顺序查、哪些是权威来源、哪些是参考资料。
> **放在这里的原因**：上下文压缩后会丢失文档位置记忆，本文档是「恢复状态的 3 个文件」之一。

---

## 一、文档用途分类（编码视角）

| 分类 | 颜色 | 含义 | 编码时是否需要读 |
|------|:----:|------|:--:|
| 🔴 **宪法文档** | 红 | 需求的最终权威，任何设计/代码与之冲突以它为准 | ✅ 必读（写每个模块前） |
| 🔵 **决策总账** | 蓝 | 所有技术决策的最终记录，防止重复讨论 | ✅ 必读（不确定「为什么这么做」时） |
| 🟢 **权威设计** | 绿 | 详细设计文档，直接指导编码 | ✅ 必读（写对应模块时） |
| 🟡 **接口定义** | 黄 | MCP Tool / SQLite Schema，编码的「契约」 | ✅ 必读（写接口/存储层时） |
| 🟣 **审核报告** | 紫 | 记录设计缺陷和修复历史，防止犯同样错误 | ⚠️ 选读（遇到诡异 bug 或设计矛盾时） |
| ⚫ **参考资料** | 灰 | 调研报告、历史版本、竞品分析，不直接指导编码 | ❌ 不读（除非需要背景） |

---

## 二、核心文档清单（按优先级排序）

### 🔴 宪法文档（2 个）

| 文档 | 核心内容 | 编码时怎么用 |
|------|---------|--------------|
| `devContextMemo-项目知识系统-需求文档-V1.0.md` | 6 大诉求 + 31 条功能需求 + 8 Step 流水线 + 状态模型 + 三元组分类 | 写任何模块前，先确认「这个模块是为了满足哪条需求？」 |
| `devContextMemo-决策总账-V1.0.md` | D1-D69 全部决策的最终状态 | 不确定「为什么用 SQLite 而不是 PostgreSQL？」时查 D1-D5 |

### 🔵 决策记录（1 个，与宪法重复但更精炼）

| 文档 | 与宪法文档的区别 |
|------|----------------|
| `devContextMemo-决策总账-V1.0.md` | 只有决策结论，没有需求背景——适合「快速确认某决策的最终状态」 |

### 🟢 权威设计文档（7 个细化设计 + 1 个架构设计）

| 文档 | 覆盖的模块 | 编码时读哪几节 |
|------|------------|----------------|
| `design/devContextMemo-系统架构设计-V1.0.md` | 全部模块 | **§2 模块全景图**（目录结构）<br>**§3 关键数据流**（端到端流程）<br>**§4 核心引擎设计**（算法逻辑）<br>**§8 AI-Friendly 合规性改造** |
| `design/devContextMemo-数据写入流水线-详细设计-V1.0.md` | `core/pipeline/` 全部 8 个 Step | **全部**（8 Step 流水线完整设计，含 Step 0→6 的数据格式、接口契约、状态流转） |
| `design/devContextMemo-知识更新-冲突检测-冲突解决-深度设计-V1.0.md` | `core/calibration.py` + `core/conflict.py` | **全部**（7 条更新路径 + L0-L5 冲突检测 + 仲裁机制） |
| `design/devContextMemo-晋升生命周期-设计-V2.0.md` | `core/promotion.py` | **§3 公式 V2.1**（confidence×0.70 + anchor_bonus×0.15 + calibration_recency×0.15）<br>**§4 滞回机制**（0.82 进 / 0.80 出） |
| `design/devContextMemo-修剪规则-完整设计-V1.0.md` | `core/pruning.py` | **§3 三层体系**<br>**§4 27 条状态跃迁** |
| `design/devContextMemo-原子写入与路径校验-设计-V1.0.md` | `storage/markdown.py` + `storage/sqlite.py` | **§3 MD→DB 写入顺序**<br>**§4 realpath 防路径遍历** |
| `design/devContextMemo-测试方案-V1.0.md` | 全部模块 | **§四 契约模板**<br>**§七 测试用例清单（~140 条）**<br>**tests/ 目录** 含真实测试代码 |

### 🟢 领域聚合文档（AI-Friendly 结构化，3 个）

> 按领域聚合的 YAML 文件，覆盖多个模块的 Service Card + 不变量 + 依赖拓扑。AI 做跨模块需求变更时必读。

| 文档 | 覆盖的模块 | 编码时怎么用 |
|------|------------|--------------|
| `domain/knowledge-lifecycle.yaml` | ColdStart → Pipeline → Promotion → Pruning → Health | 改生命周期相关模块前读：invariants（不变量）不能破坏 |
| `domain/knowledge-quality.yaml` | CalibrationEngine + ConflictDetector | 改校准/冲突逻辑前读：trigger_events + update_paths |
| `domain/knowledge-delivery.yaml` | InjectionService + SearchEngine + MCP Tools | 改注入/检索/API 前读：routing_table + tool_schemas |

### 🟡 接口定义文档（2 个）

| 文档 | 覆盖的接口 | 编码时读哪几节 |
|------|------------|----------------|
| `design/devContextMemo-MCP-Tool接口-详细设计-V1.1.md` | MCP Server 全部 12 个 Tool | **§3 Tool 清单**（名称 + 参数 + 返回值）<br>**§4 JSON Schema 示例** |
| `design/devContextMemo-SQLite-Schema-详细设计-V1.2.md` | SQLite 全部 6 张表 | **§3 建表语句**（含索引）<br>**§4 版本迁移脚本** |

### 🟡 AI-Friendly 结构化文件（3 个，机器可读）

> 这些文件是 AI 理解架构的「最快路径」，编码前建议先读 `architecture.yaml`。

| 文档 | 内容 | 编码时怎么用 |
|------|------|--------------|
| `architecture.yaml` | 全局架构地图（业务域/分层/核心链路/数据所有权/依赖规则） | 任何跨模块任务开头必读；改动依赖关系时对照 `dependency_rules` |
| `knowledge-state-machine.yaml` | 知识状态机（7 状态 + 迁移规则 + 不变量） | 写 `core/pipeline/` 或 `core/promotion.py` 前读；改状态迁移逻辑时对照 `transitions` |
| `service-card.schema.yaml` | Service Card 标准模板 + CI 检查规则 | 新建模块时对照模板填写；CI 自动校验 `domain/*.yaml` 是否合规 |

### 🟣 审核报告（5 个，选读）

| 文档 | 什么时候读 |
|------|-----------|
| `reviews/devContextMemo-宪法式批判验证报告-V1.0.md` | 设计大规模重构前（防止犯同样的宪法级错误） |
| `reviews/devContextMemo-多角色对抗检查验证报告-V1.0.md` | 同上 |
| `reviews/devContextMemo-设计文档交叉审核-V1.0.md` | 发现设计与需求矛盾时（查 P0/P1 修复记录） |
| `reviews/devContextMemo-三合一终审报告-V1.0.md` | 编码前最后确认（看「编码阶段待补清单」） |
| `reviews/devContextMemo-⚠️项深层审计报告-V1.0.md` | 遇到「这个边界情况要不要处理？」时（查 11 项深审结论） |

### ⚫ 参考资料（不读）

> `archive/` 目录下的所有文档、`AI-News/`、调研报告——**编码时不需要读**。

---

## 三、编码查阅表（按模块）

> **如何使用**：写 `xxx.py` 时，查本表找到对应的「权威设计文档」和「接口定义文档」，按表格中的章节读。

| 要写的模块 | 先读这些文档（按优先级） | 核心章节 |
|-----------|----------------------|---------|
| **`cli/init.py`** | ① 系统架构设计 §4.5 ColdStartEngine<br>② 需求文档 §四.1 冷启动 | 扫描逻辑 + LLM 骨架生成 Prompt |
| **`core/adapters/base.py`** | ① 系统架构设计 §4.0 统一接收层<br>② 需求文档 §四.1 适配器层设计 | 适配器接口定义 + 统一 JSONL 格式 |
| **`core/adapters/opencode.py`** | ① 系统架构设计 §4.0<br>② 需求文档 §四 | OpenCode SQLite → 统一 JSONL 转换 |
| **`core/adapters/comate.py`** | ① 系统架构设计 §4.0<br>② 需求文档 §四 | Comate 导出 JSON → 统一 JSONL 转换 |
| **`core/pipeline/receiver.py`** | ① 数据写入流水线设计（Step 0）<br>② 系统架构设计 §3.1<br>③ 需求文档 §四 | 适配器路由 + 原始会话存储 |
| **`core/pipeline/batcher.py`** | ① 数据写入流水线设计（Step 1）<br>② 需求文档 §四 | JSONL 格式 + `_flushed` 防重 |
| **`core/pipeline/extractor.py`** | ① 数据写入流水线设计（Step 2a）<br>② 需求文档 §三 三元组分类 | LLM Prompt 模板 + domain/concept_tags 提取 + occurred_at 时间提取 |
| **`core/pipeline/entity_extractor.py`** | ① 数据写入流水线设计（Step 2b）<br>② 系统架构设计 §3.1<br>③ 需求文档 §四 | 实体提取 + 关系提取 + 实体归一化 |
| **`core/pipeline/validator.py`** | ① 数据写入流水线设计（Step 3）<br>② 原子写入设计 §3 | 签名验证 + code_verified 设置 |
| **`core/pipeline/deduplicator.py`** | ① 数据写入流水线设计（Step 4）<br>② 需求文档 §四 | Jaccard + 语义去重 + top_similar_id |
| **`core/pipeline/writer.py`** | ① 数据写入流水线设计（Step 5）<br>② 原子写入设计 §3 | MD→DB 顺序 + realpath 校验 |
| **`core/pipeline/consolidator.py`** | ① 数据写入流水线设计（Step 6）<br>② 晋升生命周期设计 V2.0<br>③ 修剪规则完整设计 | 晋升公式 + 修剪触发 |
| **`core/calibration.py`** | ① 系统架构设计 §4.1 校准引擎<br>② 知识更新-冲突检测-冲突解决-深度设计<br>③ `domain/knowledge-quality.yaml` | 8 种触发事件 + 校准逻辑 + 不变量 |
| **`core/conflict.py`** | ① 知识更新-冲突检测-冲突解决-深度设计<br>② `domain/knowledge-quality.yaml` | L0-L5 冲突检测 + 仲裁机制 |
| **`core/promotion.py`** | ① 晋升生命周期设计 V2.0（全部）<br>② `knowledge-state-machine.yaml`<br>③ `domain/knowledge-lifecycle.yaml` | 公式 V2.1 + 滞回 + STALE 折扣 + 状态机不变量 |
| **`core/pruning.py`** | ① 修剪规则完整设计（全部）<br>② `domain/knowledge-lifecycle.yaml` | 三层体系 + 27 跃迁 + 容量管理 |
| **`core/health.py`** | ① 系统架构设计 §4.7 DataHealthEngine<br>② `domain/knowledge-lifecycle.yaml` | 9 类数据校正 + 分级修复 + invariants |
| **`services/injection.py`** | ① 系统架构设计 §4.6 InjectionService<br>② 需求文档 §四.3 三层注入<br>③ `domain/knowledge-delivery.yaml` | 注入路由推导 + AGENTS.md 生成 + routing_table |
| **`services/knowledge.py`** | ① 系统架构设计 §3.2 检索注入流<br>② MCP Tool 接口设计<br>③ `domain/knowledge-delivery.yaml` | 知识检索 + 五操作 + tool_schemas |
| **`services/review.py`** | ① `archive/devContextMemo-devContextMemo-review-交互原型设计-V1.2.md` | 审核流程 + JSON Schema |
| **`mcp/server.py`** | ① MCP Tool 接口设计（全部）<br>② `domain/knowledge-delivery.yaml` | 12 个 Tool 的 JSON Schema + tool_schemas |
| **`storage/markdown.py`** | ① SQLite Schema 设计 §3<br>② 原子写入设计 §3<br>③ 目录划分设计<br>④ `architecture.yaml`（data_ownership） | MD 路径规则 + 原子写入顺序 + 数据所有权 |
| **`storage/sqlite.py`** | ① SQLite Schema 设计（全部）<br>② `architecture.yaml`（data_ownership）<br>③ `knowledge-state-machine.yaml` | 6 张表 + 索引 + 版本迁移 + 状态机约束 |
| **`utils/security.py`** | ① 系统架构设计 §4.8 SecurityScanner<br>② `domain/knowledge-quality.yaml` | 三层检测（提示注入/凭据泄露/Unicode） |

---

## 四、上下文压缩自救指南

> **场景**：会话太长触发上下文压缩，AI 丢失了「当前在写哪个模块、读到哪份文档」的状态。
> **解决方案**：**只读以下 3 个文件**，就能恢复 90% 的状态。

### 恢复状态的 3 个文件（按读取顺序）

| 顺序 | 文件 | 能恢复什么状态 |
|:----:|------|----------------|
| 1 | **`devContextMemo-编码索引-V1.0.md`**（本文件） | 文档体系全貌 + 当前模块对应的权威文档 + AI-Friendly 结构化文件位置 |
| 2 | **`devContextMemo-决策总账-V1.0.md`** | 所有技术决策的最终状态（防止重复讨论） |
| 3 | **`devContextMemo-项目知识系统-需求文档-V1.0.md`** §一-§四 | 核心诉求 + 功能需求（防止偏离目标） |

### AI-Friendly 结构化文件（上下文压缩后额外恢复，按需读取）

| 文件 | 能恢复什么状态 |
|------|----------------|
| **`architecture.yaml`** | 全局架构地图：分层/核心链路/数据所有权/依赖规则 |
| **`knowledge-state-machine.yaml`** | 知识状态机：7 状态 + 迁移规则 + 不变量（可生成代码校验逻辑） |
| **`service-card.schema.yaml`** | Service Card 标准模板：字段定义 + CI 检查规则 |
| **`domain/knowledge-lifecycle.yaml`** | 生命周期领域：pipeline/promotion/pruning/health 聚合 Card + invariants |
| **`domain/knowledge-quality.yaml`** | 质量保障领域：calibration/conflict 聚合 Card + trigger_events |
| **`domain/knowledge-delivery.yaml`** | 交付领域：injection/search/MCP Tools 聚合 Card + routing_table |

### 不需要恢复的状态（可以丢）

- 审核报告细节（P0/P1 修复过程）—— 已经闭环，不需要回溯
- 调研报告结论 —— 决策总账已定稿，不需要重新调研
- 历史版本（v0.1-v0.24）—— 需求文档 V1.0 是最终版本

---

## 五、编码顺序建议（基于依赖关系）

> **为什么是这个顺序**：被依赖的模块先写，避免「写 A 时发现需要 B，但 B 还没定义」的循环依赖。

| 阶段 | 模块 | 依赖 | 验证方式 |
|------|------|------|---------|
| **Phase 1** | `pyproject.toml` + 目录骨架 | 无 | 能 `pip install -e .` 成功 |
| **Phase 2** | `storage/sqlite.py` + `models/` | Phase 1 | 能创建 SQLite 数据库 + 6 张表 |
| **Phase 3** | `storage/markdown.py` | Phase 2 | 能写入 MD 文件 + 同步到 DB |
| **Phase 4** | `core/pipeline/`（Step 0→6 含 Step 2a+2b） | Phase 3 | 端到端写入一条知识（多源接收 → DRAFT → CANDIDATE） |
| **Phase 5** | `core/promotion.py` + `core/pruning.py` | Phase 4 | 写入 10 条知识后触发晋升 + 修剪 |
| **Phase 6** | `core/calibration.py` + `core/conflict.py` | Phase 5 | 模拟代码变更 → 触发校准 → 检测冲突 |
| **Phase 7** | `services/`（injection + knowledge + review） | Phase 6 | 调用 MCP Tool 能检索到知识 |
| **Phase 8** | `mcp/server.py` | Phase 7 | OpenCode 能调用 `search_knowledge` |
| **Phase 9** | `cli/`（init + review + dream + config + status） | Phase 8 | 命令行能完成冷启动 + 审核流程 |
| **Phase 10** | 集成测试 + 性能优化 | Phase 9 | 100 条知识写入 < 5 分钟 |

---

## 六、文档冲突处理规则

> **场景**：两份文档对同一个问题的描述不一致（例如需求文档说「三层注入」，但某份旧设计文档说「检索注入流」）。

**处理优先级**（高→低）：

1. 🥇 **`devContextMemo-项目知识系统-需求文档-V1.0.md`** —— 最高优先级，任何文档与之冲突以它为准
2. 🥈 **`devContextMemo-决策总账-V1.0.md`** —— 决策结论的权威来源
3. 🥉 **`architecture.yaml`** —— 架构分层/依赖规则/数据所有权的机器可读权威
4. 🏅 **`knowledge-state-machine.yaml`** —— 状态机不变量/迁移规则的权威（优先于任何文字描述）
5. 🏆 **`domain/*.yaml`** —— 领域聚合 Service Card 的权威（覆盖单个模块文档）
6. 🔷 **`design/devContextMemo-系统架构设计-V1.0.md`** —— 设计细节的权威来源
7. 🔹 **各 Step 细化设计文档** —— 流水线实现细节
8. ❌ **`archive/` 下的所有文档** —— 已过时，仅作历史参考

**发现冲突时的操作**：
1. 先确认哪份是权威文档（按上述优先级）
2. 如果权威文档本身有矛盾 → 在决策总账中新建一条决策记录（D70+）
3. 如果非权威文档过时 → 标记为 `⚠️ 已过时，以需求文档 V1.0 为准`，不要删除（保留历史追溯能力）

---

## 七、编码规范快速参考

> 完整规范见 `design/devContextMemo-编码规范-V1.0.md`，这里只列「每次写代码都要看」的规则。

### 必须遵守（3 条）

| 规则 | 工具自动检查 | 人工检查 |
|------|:------------:|:--------:|
| 函数/方法必须有 Google Style docstring | ❌ | ✅ |
| 变量名必须是小写 + 下划线（snake_case） | ✅ Ruff | — |
| 常量必须是大写 + 下划线（UPPER_SNAKE） | ✅ Ruff | — |

### 强烈建议（2 条）

| 规则 | 原因 |
|------|------|
| 每个函数 ≤ 50 行 | 可读性 + 可测试性 |
| 每个文件 ≤ 500 行 | 模块化，避免「上帝类」 |

### Commit 规范

```
<type>(<scope>): <subject>

示例：
feat(pipeline): 实现 Step2 提炼层 LLM 调用逻辑
fix(conflict): 修复 L3 语义矛盾检测的分数计算错误
docs(architecture): 补充校准引擎 8 种触发事件
```

---

## 八、源码参考（对照实现）

> **目的**：以下开源项目源码已下载到本地，编码时可对照参考实现细节。
> **路径**：所有源码目录位于 `~/WorkBuddy/devContextMemo/` 下，以 `collection-` 或 `openchronicle-source` 为前缀。
> **使用方式**：写某个模块时，先查「三、编码查阅表」找到权威设计文档，再查下表找到参考源码。

### 8.1 参考源码总表

| 源码路径 | 语言 | 参考模块 | 参考价值 | 关键文件 |
|---------|:---:|---------|---------|---------|
| **devContextMemospring/memory/** | Python | `storage/markdown.py` `storage/sqlite.py` `core/pipeline/writer.py` | 记忆存储、MD 文件管理、双写模式、FTS5 检索 | `store.py`（MD+DB 双写）、`consolidator.py`（巩固合并）、`scan.py`（增量扫描）、`context.py`（上下文注入） |
| **devContextMemospring/memory/types.py** | Python | `models/` | 记忆条目数据模型定义 | `MemoryEntry` / `MemoryQueryResult` 数据类 |
| **devContextMemospring/memory/tools.py** | Python | `mcp/server.py` | MCP Tool 注册模式 | `search_memory` / `write_memory` 工具实现 |
| **openchronicle-source/src/openchronicle/store/** | Python | `storage/sqlite.py` `storage/markdown.py` | SQLite + MD 双存储、FTS 全文搜索 | `entries.py`（条目 CRUD）、`files.py`（MD 文件操作）、`fts.py`（FTS5 全文搜索）、`index_md.py`（MD 索引） |
| **openchronicle-source/src/openchronicle/writer/** | Python | `core/pipeline/extractor.py` `core/pipeline/consolidator.py` | LLM 驱动的知识提取与分类 | `classifier.py`（分类器）、`session_reducer.py`（会话归约）、`agent.py`（写入代理） |
| **openchronicle-source/src/openchronicle/session/** | Python | `core/pipeline/receiver.py` `core/pipeline/batcher.py` | 会话管理 + 攒批机制 | `manager.py`（会话管理器）、`store.py`（会话存储）、`tick.py`（时间片） |
| **openchronicle-source/src/openchronicle/timeline/** | Python | `core/pipeline/batcher.py` `core/promotion.py` | 时间线聚合 + 增量处理 | `aggregator.py`（聚合器）、`store.py`（时间线存储） |
| **devContextMemospring/skill/** | Python | `mcp/server.py` | 技能注册与执行模式（可参考做 Tool 注册） | `loader.py`（技能加载）、`executor.py`（技能执行）、`tools.py`（技能工具） |
| **devContextMemospring/plugin/** | Python | `mcp/server.py` | 插件系统模式（可参考做适配器扩展） | `loader.py`（插件加载）、`store.py`（插件存储）、`types.py`（类型定义） |
| **devContextMemospring/task/** | Python | `core/promotion.py` `core/pruning.py` | 后台任务管理（dream/修剪等异步任务） | `store.py`（任务存储）、`tools.py`（任务工具）、`types.py`（任务类型） |
| **devContextMemospring/compaction.py** | Python | `core/pruning.py` | 上下文压缩/修剪算法 | 压缩策略实现 |
| **devContextMemospring/config.py** | Python | `cli/config.py` | 配置管理（YAML 驱动） | 配置加载 + 环境变量覆写 |
| **devContextMemospring/cloudsave.py** | Python | `storage/markdown.py` | 云存储同步（可参考做 Git 自动 commit） | 文件同步逻辑 |
| **devContextMemospring/tests/** | Python | `tests/` | 测试用例参考 | `test_memory.py`、`test_compaction.py`、`test_mcp.py` |
| **openchronicle-source/tests/** | Python | `tests/` | 测试用例参考（pytest 风格） | `test_store.py`、`test_classifier.py`、`test_writer_agent.py` |
| **devContextMemo-code/src/** | Python | `cli/` `mcp/server.py` | CLI 命令实现 + MCP 工具模式 | `commands.py`（命令注册）、`tools.py`（工具定义）、`Tool.py`（工具基类） |

### 8.2 按模块速查

| devContextMemo 模块 | 优先看这些源码 |
|---------------------|----------------|
| `storage/markdown.py` | `openchronicle-source/src/openchronicle/store/files.py` + `entries.py` + `devContextMemospring/memory/store.py` |
| `storage/sqlite.py` | `openchronicle-source/src/openchronicle/store/entries.py` + `fts.py` + `devContextMemospring/memory/store.py` |
| `core/pipeline/writer.py` | `devContextMemospring/memory/store.py`（双写逻辑） + `openchronicle-source/src/openchronicle/writer/agent.py` |
| `core/pipeline/extractor.py` | `openchronicle-source/src/openchronicle/writer/classifier.py` + `session_reducer.py` |
| `core/pipeline/consolidator.py` | `devContextMemospring/memory/consolidator.py` + `openchronicle-source/src/openchronicle/writer/agent.py` |
| `core/pipeline/receiver.py` | `openchronicle-source/src/openchronicle/session/manager.py` |
| `core/pipeline/batcher.py` | `openchronicle-source/src/openchronicle/timeline/aggregator.py` + `session/tick.py` |
| `core/promotion.py` | `devContextMemospring/memory/consolidator.py` + `openchronicle-source/src/openchronicle/timeline/aggregator.py` |
| `core/pruning.py` | `devContextMemospring/compaction.py` |
| `mcp/server.py` | `devContextMemospring/memory/tools.py` + `devContextMemospring/skill/tools.py` + `devContextMemospring/mcp/tools.py` |
| `cli/` | `devContextMemo-code/src/commands.py` + `devContextMemospring/config.py` |
| `tests/` | `openchronicle-source/tests/` + `devContextMemospring/tests/`（pytest 风格参考） |

### 8.3 源码目录全路径速查

```
~/WorkBuddy/devContextMemo/collection-claude-code-source-code/
├── devContextMemospring/              # devContextMemoSpring Python 实现（记忆/技能/任务/插件/MCP）
│   ├── memory/              # 记忆系统核心
│   ├── skill/               # 技能注册与执行
│   ├── task/                # 后台任务管理
│   ├── plugin/              # 插件系统
│   ├── mcp/                 # MCP 客户端
│   ├── multi_agent/         # 多 Agent 协作
│   └── tests/               # 测试用例
├── devContextMemo-code/src/           # devContextMemo Code Python CLI 实现
│   ├── commands.py          # CLI 命令注册
│   ├── tools.py             # 工具定义
│   ├── Tool.py              # 工具基类
│   └── ...
├── memory/                  # 独立记忆模块（与 devContextMemospring/memory 类似）
├── skill/                   # 独立技能模块
├── multi_agent/             # 独立多 Agent 模块
├── claude-code-source-code/ # Claude Code TypeScript 源码（原始）
├── original-source-code/    # 原始 TypeScript 源码（参考）
└── docs/                    # 架构文档 + PR 记录

~/WorkBuddy/devContextMemo/openchronicle-source/src/openchronicle/
├── store/                   # SQLite + MD 双存储引擎
├── writer/                  # LLM 驱动的知识写入（分类器 + 归约器）
├── session/                 # 会话管理
├── timeline/                # 时间线聚合
├── capture/                 # 屏幕截图捕获
├── mcp/                     # MCP 服务端
└── prompts/                 # Prompt 模板
```

---

*文档版本*：V1.4  
*创建时间*：2026-06-17  
*更新时间*：2026-06-18（新增 §八「源码参考」+ 修复 8 个不存在文件引用）  
*下次更新*：新增模块时同步更新「三、编码查阅表」+ 「二、核心文档清单」+ 「八、源码参考」
