# devContextMemo 测试方案 V1.0

> **日期**：2026-06-18
> **触发**：基于爱奇艺 AQE 质量门禁左移文章（契约化/状态机/风险分级/证据模型）
> **关联文档**：需求文档 V1.0、系统架构设计 V1.0、编码索引 V1.0、LLM 分类基准测试设计 V1.0

---

## 一、设计理念：测试左移到开发阶段

### 1.1 为什么测试必须左移

devContextMemo 的核心挑战不是「代码写不完」，而是「写出来的东西对不对」。知识加工链路有 8 个 Step，每个 Step 都可能产生不可见的质量衰减：

- **LLM 分类偏差**：分类准确率未达到 80% 阈值
- **实体提取遗漏**：关键实体未被识别
- **去重误判**：语义相似但实际不同的知识被合并
- **写入一致性**：MD 与 DB 索引不同步

如果测试全部放在「写完再测」，问题暴露晚、修复成本高。AQE 的核心洞察同样适用 devContextMemo：

> **左移的本质，是把验证能力前置到开发活动内部，让每次变更都能尽早进入可执行的验证闭环。**

### 1.2 从 AQE 借鉴的四个核心原则

| AQE 原则 | devContextMemo 映射 |
|----------|-------------------|
| **契约化**：把测试用例写成 AI 可执行的结构 | 每个 Step 的输入/输出/断言写成 YAML 契约，LLM 可读、CI 可执行 |
| **状态机**：每条用例是事务，证据不足不能 PASS | 流水线每个 Step 的输出有明确的 PASS/FAIL/BLOCK 判定 |
| **风险分级**：L1 快速验证 / L2 标准 / L3 强门禁 | 纯代码重构=快速，单 Step 逻辑+类级别校准=标准，LLM Prompt+数据格式+跨层图谱=强验证 |
| **证据驱动**：任何判定必须有可追溯证据 | 测试输出必须包含日志/trace/LLM 响应/snapshot 等证据 |

---

## 二、Step 间依赖分析与解耦策略

### 2.1 当前依赖链（全量审核）

```
Step 0 (接收)  ──文件──► Step 1 (攒批)  ──文件──► Step 2a (提炼)  ──文件──► Step 2b (实体)
       ↓ 强依赖              ↓ 强依赖               ↓ 强依赖               ↓ 强依赖
  raw JSONL              batch_*.jsonl          summary_*.jsonl         knowledge_*.jsonl
                                                                              │
  Step 6 (巩固) ◄──数据── Step 5 (写入) ◄──文件── Step 4 (去重) ◄──文件── Step 3 (验证)
       ↓ 强依赖              ↓ 强依赖               ↓ 强依赖               ↓ 强依赖
  DB 查询/更新            MD + SQLite            top_similar_id          content_hash
```

### 2.2 依赖矩阵（× = 有依赖，数字 = 依赖强度 1-5）

| 下游\上游 | Step 0 | Step 1 | Step 2a | Step 2b | Step 3 | Step 4 | Step 5 | Step 6 |
|-----------|:------:|:------:|:-------:|:-------:|:------:|:------:|:------:|:------:|
| **Step 0** | - | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **Step 1** | ×5 | - | 0 | 0 | 0 | 0 | 0 | 0 |
| **Step 2a** | 0 | ×5 | - | 0 | 0 | 0 | 0 | 0 |
| **Step 2b** | 0 | 0 | ×5 | - | 0 | 0 | 0 | 0 |
| **Step 3** | 0 | 0 | 0 | ×5 | - | 0 | 0 | 0 |
| **Step 4** | 0 | 0 | 0 | 0 | ×5 | - | 0 | 0 |
| **Step 5** | 0 | 0 | 0 | 0 | 0 | ×5 | - | 0 |
| **Step 6** | 0 | 0 | 0 | 0 | 0 | 0 | ×4 | - |

> **依赖强度说明**：5=输出文件是下游唯一输入（强串行）；4=需要下游输出作为查询条件但可用 mock 替代；3=可选依赖（如分类结果可被下游消费但不强制）；0=无依赖。

### 2.3 依赖分类

| 依赖段 | 依赖类型 | 是否可解耦 | 解耦方案 |
|--------|---------|:--:|------|
| **0→1** | 文件格式依赖（raw JSONL → batch JSONL） | ⚠️ 不可完全解耦 | 格式稳定后 mock raw JSONL 即可独立测试 Step 1 |
| **1→2a** | 文件格式依赖（batch JSONL → summary JSONL） | ⚠️ 不可完全解耦 | 格式稳定后 mock batch JSONL 即可独立测试 Step 2a |
| **2a→2b** | **语义依赖**：2b 需要 2a 的 knowledge_text + classification 才能做实体提取 | ❌ 不可解耦 | 2b 天然依赖 2a 的语义输出，但 2a 输出格式稳定后可用 mock 独立测试 2b |
| **2b→3** | 文件格式依赖（knowledge JSONL → 验证） | ⚠️ 不可完全解耦 | mock knowledge JSONL 即可独立测试 Step 3 |
| **3→4** | 文件格式依赖（knowledge JSONL → 去重） | ⚠️ 不可完全解耦 | mock knowledge JSONL 即可独立测试 Step 4 |
| **4→5** | 文件格式 + 数据一致性依赖（knowledge JSONL → MD + SQLite） | ⚠️ 不可完全解耦 | mock knowledge JSONL + mock DB 即可独立测试 Step 5 |
| **5→6** | 数据级依赖（需要 DB 中有记录才能查询/更新） | ✅ 可大幅降低 | 用 SQLite :memory: 预置数据，**无需经过 Step 5** 即可独立测试 Step 6 |

### 2.4 关键发现

1. **Step 0→1→2a→2b→3→4→5 是纯文件链式依赖**：上游输出文件 = 下游输入文件，但每个 Step 内部逻辑对上游是**黑盒**的——只要文件格式稳定，每个 Step 可完全独立测试。

2. **唯一真正的强耦合点在 Step 5→6**：Step 6（巩固）需要查询 SQLite 中 Step 5 写入的记录来做晋升/修剪/合并。但这不是不可解耦的——用 SQLite :memory: 预置测试数据即可。

3. **当前集成测试的设计过度耦合了**：把 Step 0→1、1→2a→2b、2b→3→4、4→5→6 分别作为集成测试段测试是对的，但每个段内部不需要全部真实运行——只需验证数据格式兼容性即可。

### 2.5 解耦建议：数据契约接口（Data Contract Interface）

在每个 Step 的模块定义中，显式声明一个 `validate_input(data)` 函数，该函数：
- 接受上游输出格式的数据
- 返回 `(bool, error_msg)` 
- **不依赖上游模块的 import**——只校验数据格式

这样：
- **模块测试**时：用 mock 数据调用 `step.process(mock_input)`，验证输出格式
- **集成测试**时：只测试「上游真实输出能否通过下游的 validate_input」——这是唯一的集成点

---

## 三、测试分层策略（修订版）

### 3.1 测试金字塔（修订后）

```
          ┌──────────┐
          │  E2E     │  全链路真实运行（仅 Phase 1 收尾 + Phase 2）
          │  ~12 条  │  触发方式：手动 / CI nightly
          ├──────────┤
          │  集成    │  仅测试 Step 间数据契约兼容性（validate_input 通过）
          │  ~30 条  │  触发方式：CI pre-merge（数据格式变更时自动触发）
          │          │  含需求对齐的跨模块测试（校准/生命周期/防腐烂/校正）
          ├──────────┤
          │  模块    │  每个 Step 的完整功能测试（用 mock 上游数据）
          │  ~42 条  │  触发方式：CI pre-merge（对应模块代码变更时）
          ├──────────┤
          │  单元    │  纯函数/纯逻辑（无 I/O、无 LLM、无 DB）
          │  ~55 条  │  触发方式：pre-commit hook
          └──────────┘
```

### 3.2 四层测试定义（修订版）

| 层级 | 测试对象 | 对外依赖 | 证据要求 | 门禁级别 |
|------|---------|:--:|------|:--:|
| **单元测试** | 纯函数（hash, promotion 公式, state machine, 枚举校验） | **零依赖**（无 I/O/LLM/DB/文件系统） | 断言结果 | L1 快速 |
| **模块测试** | 单个 Step 完整功能（含 LLM 调用、文件 I/O、DB 操作） | 仅 mock 上游数据格式 | 输入+输出+LLM 响应+置信度 | L2 标准 |
| **集成测试** | Step 间数据契约兼容性（validate_input） + 引擎联动 + 跨模块流程 | 上游模块真实输出 | 数据格式校验结果 | L2 标准 |
| **E2E 测试** | 全链路真实运行（接收→注入）+ 冷启动 | 全部真实 | 全链路日志 + snapshot 对比 | L3 强门禁 |

---

## 四、核心创新：可执行契约测试（AQE 契约化思想落地）

### 4.1 契约模板

每个 Step 定义一份 YAML 契约文件，AI 和 CI 均可读取执行：

```yaml
# Step 2a 提炼契约示例
contract:
  step: step2a_extract
  version: "1.0"

  input:
    source: batch_*.jsonl
    format: |
      {"session_id": "uuid", "seq": 1, "role": "user", "content": "...", "timestamp": "..."}

  preconditions:
    - batch_*.jsonl 存在且非空
    - LLM API 可用（MiniMax 或 GLM）
    - domain_tree 已加载

  output:
    format: summary_*.jsonl
    required_fields: [session_id, knowledge_text, lx, sy, depth, domain, confidence, occurred_at]
    status: DRAFT

  assertions:
    classification:
      - each(knowledge).confidence >= 0  # 不要求 ≥0.85（低置信度走人工审核）
      - each(knowledge).lx in [L0, L1, L2, L3]
      - each(knowledge).sy in [S1, S2, S3, S4, S5]
      - each(knowledge).depth in [KW, KH, KY]
      - each(knowledge).domain in domain_tree.keys()
    time_extraction:
      - each(knowledge).occurred_at is valid ISO8601 or null
    count:
      - len(output) <= len(input)  # 提炼不会增加条目数

  evidence:
    required:
      - llm_request_log   # LLM 请求的完整 prompt + response
      - summary_file      # 输出的 summary_*.jsonl
      - token_usage       # 本次调用消耗的 token 数

  failure_modes:
    BLOCK: [LLM API 不可用, domain_tree 未加载, batch 文件损坏]
    FAIL: [输出格式不合法, 必填字段缺失, 枚举值越界]
    PASS: [所有断言通过 + 证据完整]
```

### 4.2 8 个 Step 的契约清单

| Step | 契约文件 | 核心断言 | 风险级别 |
|------|---------|------|:--:|
| **Step 0 接收** | `contracts/step0_receiver.yaml` | 输出统一 JSONL 格式、source 字段正确、session_id 唯一 | low |
| **Step 1 攒批** | `contracts/step1_batcher.yaml` | batch_*.jsonl 格式正确、_flushed=false、防重 | low |
| **Step 2a 提炼** | `contracts/step2a_extractor.yaml` | 四轴分类合法、occurred_at 合法、confidence 在 [0,1] | **high** |
| **Step 2b 提取** | `contracts/step2b_entity.yaml` | entities 非空、relations 有 source/target/type、实体归一化 | **high** |
| **Step 3 验证** | `contracts/step3_validator.yaml` | content_hash 更新、semantic_hash 非空、code_verified 布尔 | medium |
| **Step 4 去重** | `contracts/step4_deduplicator.yaml` | top_similar_id 格式、Jaccard 阈值在 [0,1] | medium |
| **Step 5 写入** | `contracts/step5_writer.yaml` | MD 文件存在、DB 记录同步、content_hash 一致 | **high** |
| **Step 6 巩固** | `contracts/step6_consolidator.yaml` | base_score 计算正确、状态迁移合法、修剪触发条件正确 | **high** |

### 4.3 契约测试的执行状态机（借鉴 AQE §05）

```
         ┌─────────┐
         │  START  │
         └────┬────┘
              │
         ┌────▼────┐  前置条件不满足
         │ PREPARE ├──────────────► BLOCK
         └────┬────┘
              │ 前置条件满足
         ┌────▼────┐  执行异常/超时
         │ EXECUTE ├──────────────► BLOCK
         └────┬────┘
              │ 执行完成
         ┌────▼────┐  断言失败
         │ ASSERT  ├──────────────► FAIL (+ 证据)
         └────┬────┘
              │ 断言通过
         ┌────▼────┐  证据不完整
         │ EVIDENCE├──────────────► BLOCK
         └────┬────┘
              │ 证据完整
         ┌────▼────┐
         │  PASS   │  (+ 完整证据包)
         └─────────┘
```

**关键约束**：
- 证据缺失 **不能** 写 PASS
- BLOCK 不等同于 FAIL——BLOCK 是环境/前置问题，FAIL 是业务逻辑问题
- 每个 BLOCK/FAIL 必须携带归因（环境/数据/工具/逻辑）

---

## 五、风险分级门禁（借鉴 AQE §07）

### 5.1 devContextMemo 的风险模型

| 维度 | 高风险 | 中风险 | 低风险 |
|------|--------|--------|--------|
| **业务影响** | 写入流水线核心（Step 2a/2b/5/6）<br>分类准确率 < 80%<br>知识注入路由错误 | 去重/验证逻辑（Step 3/4）<br>类级别校准<br>冷启动 | 配置管理<br>CLI 工具<br>日志格式 |
| **变更复杂度** | 跨 Step 数据格式变更<br>LLM Prompt 模板变更<br>跨层图谱变更 | 单 Step 逻辑变更<br>新增适配器<br>类级别校准阈值调整 | 文案修改<br>依赖版本补丁升级 |
| **AI 参与度** | LLM 分类 Prompt 修改<br>实体提取 Prompt 修改<br>深度反思 Prompt 修改 | 类级别校准（辅助信号，不做自动裁判）<br>方法签名校准 | 纯代码重构（hash/promotion/pruning/conflict 公式调整） |

### 5.2 三级门禁

| 门禁级别 | 触发条件 | 验证深度 | 证据要求 |
|:--:|------|------|------|
| **L1 快速门禁** | 低风险变更<br>纯代码重构（hash/promotion/pruning/conflict 公式调整） | 单元测试 + lint + type check | 测试通过/失败状态 |
| **L2 标准门禁** | 中风险变更<br>单 Step 逻辑修改<br>类级别校准阈值调整 | L1 + 契约测试 + 集成测试 | L1 证据 + LLM 响应日志 + 中间状态 trace |
| **L3 强门禁** | 高风险变更<br>LLM Prompt 修改<br>数据格式变更<br>跨层图谱变更 | L2 + E2E 测试 + 分类基准测试 | L2 证据 + 全链路 snapshot + 分类准确率报告 |

### 5.3 门禁与 CI 集成

```
Git Push / PR
      │
      ▼
┌─────────────┐
│ 风险判定    │  ← 分析 diff 范围 → 输出 gate_level
└──────┬──────┘
       │
  ┌────▼────┬──────────┬──────────┐
  │   L1    │    L2    │    L3    │
  │         │          │          │
  │ pre-    │ L1 +     │ L2 +     │
  │ commit  │ 契约测试 │ E2E 测试 │
  │ hook    │ + 集成   │ + 基准   │
  └────┬────┴────┬─────┴────┬─────┘
       │         │          │
       ▼         ▼          ▼
  ┌─────────────────────────────┐
  │  门禁判定（规则引擎）       │
  │  PASS → merge 允许          │
  │  FAIL → 阻断 + 证据报告     │
  │  BLOCK → 环境问题，通知     │
  └─────────────────────────────┘
```

---

## 六、证据模型（借鉴 AQE §06）

### 6.1 五类证据

| 证据类型 | 包含内容 | 适用场景 |
|------|------|------|
| **功能证据** | 断言结果、输入/输出文件、状态迁移记录 | 所有测试层级 |
| **数据证据** | LLM 请求/响应日志、token 消耗、SQLite 查询结果 | 契约测试 + 集成测试 |
| **过程证据** | 流水线 trace_id、Step 间中间状态、时间戳 | E2E 测试 |
| **环境证据** | Python 版本、LLM 模型版本、OS、SQLite 版本 | L3 强门禁 |
| **治理证据** | 失败归因、阻塞原因、复验入口、分类准确率趋势 | 持续改进 |

### 6.2 证据存储

```
.devcontext/test-evidence/    # 与 .devContextMemo/ 分离，不参与 git
├── {date}/
│   ├── {test_run_id}/
│   │   ├── evidence.yaml       # 证据清单（结构化）
│   │   ├── llm_request_*.json  # LLM 请求日志
│   │   ├── snapshots/          # 输入/输出文件快照
│   │   ├── trace.json          # 全链路 trace
│   │   └── report.md           # 可读报告
```

---

## 七、测试用例清单（按测试层级）

### 7.1 单元测试（~55 条）—— 零外部依赖

> **原则**：纯函数、纯逻辑，无 I/O、无 LLM 调用、无 DB 操作、无文件系统。所有输入通过函数参数传入，输出通过返回值断言。

| 模块 | 测试数量 | 核心场景 | 为何是纯函数 |
|------|:--:|------|------|
| `utils/hash.py` | 5 | content_hash 确定性、semantic_hash 区分度、空输入、Unicode、大文本 | 纯算法，输入→输出 |
| `utils/path.py` | 4 | realpath 校验、目录遍历防护、符号链接处理 | 路径字符串操作（不实际访问文件系统时） |
| `core/promotion.py` | 8 | 公式 V2.1 计算、滞回边界 (0.80/0.82)、STALE 折扣、T14 规则、边界值（0/1/负数） | 数学公式，纯计算 |
| `core/pruning.py` | 6 | 三层体系触发条件判断、容量上限计算、supplement 保护逻辑 | 规则引擎，输入条目→输出决策 |
| `core/conflict.py` | 6 | L0-L5 各层检测判定、仲裁阈值 0.30 计算、证据权重 | 判定逻辑，纯规则 |
| `core/health.py` | 5 | H1-H9 检测逻辑判定、自动修复 vs 人工确认分类 | 规则引擎 |
| `models/knowledge_item.py` | 4 | 状态机不变量（如 DRAFT→STALE 非法）、枚举值校验、必填字段校验 | 数据模型校验 |
| `storage/atomic.py` | 4 | MD→DB 顺序校验、回滚逻辑状态机、fsync 确认逻辑 | 原子性逻辑（不实际写文件时） |
| `adapters/format_validator.py` | 5 | 统一 JSONL 格式校验（session_id/seq/role/content/timestamp/source）、各适配器输出格式合规性 | 数据格式校验 |
| `utils/enum_validator.py` | 3 | Lx/Sy/Depth/Domain 枚举值合法性校验 | 枚举映射表 |
| `core/route.py` | 5 | Lx×Sy×Depth 三元组→注入层级（L1/L2/L3）路由判定 | 路由规则，纯判定 |
| **合计** | **~55** | | |

### 7.2 需求对齐测试（~30 条）—— 覆盖需求文档 Given-When-Then 验收标准

> **原则**：需求文档中每一条 Given-When-Then 验收标准，必须有对应的测试用例。本节按诉求组织，标注对应测试层级。

#### 7.2.1 诉求① 存储架构（4 条 → 模块测试）

| # | Given | When | Then | 测试层级 |
|:--:|------|------|------|:--:|
| 1 | `.devContextMemo/knowledge/order/` 下有 `payment-flow.md` | `search_knowledge(query="支付流程")` | DB 索引返回 URI，content 取自 MD 非 DB | 模块（Step 5 写入） |
| 2 | `.devContextMemo/knowledge/` 下 5 个 MD，DB 为空 | `devContextMemo rebuild-index` | DB 重建完成，记录数 = MD 数 | 集成（rebuild 流程） |
| 3 | `payment.md` 被人工编辑保存 | 写时钩子触发 | SQLite 对应记录的 `content_hash` 和 `updated_at` 同步更新 | 模块（Step 5 写入） |
| 4 | DB 文件被删除 | `devContextMemo rebuild-index` | 从 MD 完整重建，知识无丢失 | 集成（rebuild 流程） |

#### 7.2.2 诉求② 无时间衰减（3 条 → 单元测试）

| # | Given | When | Then | 测试层级 |
|:--:|------|------|------|:--:|
| 5 | 知识 A 90 天前创建，9 天前校准；知识 B 1 天前创建，未校准 | 计算 base_score | A 的 base_score > B（校准过的旧知识 > 未校准的新知识） | 单元（promotion 公式） |
| 6 | 知识 200 天前创建，昨天校准 | 计算 base_score | `calibration_recency = 1.0`（取距校准天数，非距创建天数） | 单元（promotion 公式） |
| 7 | 两条知识 confidence 相同，其中一条 code_verified=1 | 计算 base_score | code_verified=1 的知识 anchor_bonus=1.0，base_score 更高 | 单元（promotion 公式） |

#### 7.2.3 诉求③ 生命周期 + 知识更新（9 条 → 模块+集成）

| # | Given | When | Then | 测试层级 |
|:--:|------|------|------|:--:|
| 8 | 知识 K 状态=DRAFT，人工审核通过 | 状态迁移 | K→STAGED | 模块（Step 6 巩固） |
| 9 | 知识 K 状态=STAGED，base_score=0.85 | 巩固层评估 | K→CANDIDATE | 模块（Step 6 巩固） |
| 10 | 知识 K 状态=CANDIDATE，base_score=0.83 | 二次确认 | K→ACTIVE | 模块（Step 6 巩固） |
| 11 | 知识 K 状态=ACTIVE，距最后使用 400 天 | 定期审计 | K→COLD→STALE（三层修剪） | 模块（Step 6 巩固） |
| 12 | 知识 K 状态=STALE，人工确认过期 | `deprecate_knowledge(id=K)` | K→DEPRECATED | 集成（deprecate 流程） |
| 13 | 知识 K 被 K' 取代 | `replace_knowledge(id=K, new_content)` | K.superseded_by = K'.id，版本链 K→K' 可回溯 | 集成（replace 流程） |
| 14 | 知识 K 状态=DEPRECATED | 新会话启动 L1/L2 注入 | AGENTS.md 和搜索结果不包含 K | 模块（注入路由） |
| 15 | K1 状态=ACTIVE，内容="使用 H2 数据库" | `update_knowledge(id=K1, content="使用 MySQL")` | K1→CANDIDATE，原内容写入 previous_version | 集成（update 流程） |
| 16 | K3 内容="支付超时 30s"，新提炼="支付超时 60s" | `supplement_knowledge(id=K3, additional="已调整60s")` | K3 supplement 追加新内容，状态不变 | 集成（supplement 流程） |

#### 7.2.4 诉求④ 分类 + 注入兜底（6 条 → 模块测试）

| # | Given | When | Then | 测试层级 |
|:--:|------|------|------|:--:|
| 17 | LLM 提炼产出知识 K | 检查 (Lx, Sy, Depth, Domain) | 四轴枚举值均合法，Domain 非空 | 模块（Step 2a 提炼） |
| 18 | 知识 K 标注 L3+KH | `get_knowledge(domain="order", query="幂等")` | K 出现在检索结果（L3 按需检索生效） | 模块（注入路由） |
| 19 | 知识 K 标注 S1+KW | 新会话启动 | AGENTS.md 自动包含 K（L1 恒常注入） | 模块（注入路由） |
| 20 | 知识标注置信度 < 0.6 | 写入 staging/ | 状态=DRAFT，进入人工审核队列 | 模块（Step 2a 提炼） |
| 21 | L1+L2 知识 > 4K tokens | 生成 AGENTS.md | 触发截断策略，优先保留 S1→S2→截断 L3 | 模块（注入路由） |
| 22 | AGENTS.md 生成失败（LLM 超时） | 新会话启动 | 降级仅注入 L1，status 显示 injection_fallback=L1_ONLY | 模块（注入路由） |

#### 7.2.5 诉求④-B 防腐烂（4 条 → 集成测试）

| # | Given | When | Then | 测试层级 |
|:--:|------|------|------|:--:|
| 23 | `OrderService.java` 被 git commit 修改 | 触发校准引擎 | 所有 linked_to_file 包含该文件的知识进入校准队列 | 集成（校准触发） |
| 24 | 知识 K 状态=ACTIVE，距上次校准 120 天 | 执行 `dev dream` | K 标记为 STALE（suspicious） | 集成（dream 流程） |
| 25 | `.devContextMemo/knowledge/` 新增 `refund.md`，无对应知识 | 每周覆盖率审计 | 生成「覆盖盲区」报告 | 集成（health-check） |
| 26 | 知识 K 标注 S2，180 天未更新 | 执行 `dev status` | 显示 `needs_review=true` | 集成（status 流程） |

#### 7.2.6 诉求⑥ 类级别校准（4 条 → 集成测试）

| # | Given | When | Then | 测试层级 |
|:--:|------|------|------|:--:|
| 27 | `OrderService.java` 被修改，关联知识 K 状态=ACTIVE | Git commit 触发校准 | `last_calibrated_at` 更新，结果写入 calibration_logs | 集成（校准触发） |
| 28 | 知识 K 描述="使用 H2"，代码已改 MySQL | LLM 语义对比 | 判定不一致，K 标记 needs_review=true，状态保持 ACTIVE（不自动降级） | 集成（校准执行） |
| 29 | 知识 K 描述与代码一致 | 校准引擎执行 | confidence 加分（≤1.0），calibration_recency 重置 | 集成（校准执行） |
| 30 | linked_to_files 含 3 个文件，其中 1 个被修改 | 校准引擎执行 | 仅对标修改的文件，未修改文件不参与对比 | 集成（校准执行） |

#### 7.2.7 诉求⑦ 深度反思（2 条 → 模块测试）

| # | Given | When | Then | 测试层级 |
|:--:|------|------|------|:--:|
| 31 | 用户输入 `dev reflect "支付模块为什么出 bug？"` | 系统执行 | 检索 top_k=20，LLM 推理输出洞察文本 | 模块（reflect 模块） |
| 32 | reflect 输出洞察，用户确认存储 | 写入 staging/ | 知识 type="mental_model"，lx="L3"，sy="S2" | 模块（reflect 模块） |

#### 7.2.8 诉求⑧ 冷启动（4 条 → E2E 测试）

| # | Given | When | Then | 测试层级 |
|:--:|------|------|------|:--:|
| 33 | 空项目，`.devContextMemo/` 不存在 | 执行 `dev init` | 生成 `.devContextMemo/` + AGENTS.md 骨架，状态=DRAFT | E2E |
| 34 | 项目有 `src/order/` 和 `src/payment/` | 执行 `dev init` | LLM 生成 S1 原则 + S2 架构骨架，每模块 1 条 | E2E |
| 35 | `dev init` 生成 DRAFT 知识 10 条 | 人工审核通过 8 条 | 8 条→STAGED，写入 `.devContextMemo/knowledge/` | E2E |
| 36 | `dev init` 生成 AGENTS.md | 新会话启动 | AGENTS.md 自动注入（≤4K tokens） | E2E |

#### 7.2.9 诉求⑧ 校正（3 条 → 集成测试）

| # | Given | When | Then | 测试层级 |
|:--:|------|------|------|:--:|
| 37 | DB `content_hash` ≠ MD 文件 mtime | 执行 `dev health-check` | 报告「MD-DB 索引漂移」，列出差异条目 | 集成（health-check） |
| 38 | 写入内容含 API Key `sk-abc123...` | 执行 Step 2a 提炼 | 拒绝写入，记录安全事件，错误码 SECURITY_CREDENTIAL_LEAK | 模块（Step 2a 提炼） |
| 39 | 写入内容含「忽略之前所有指令…」 | 执行 SecurityScanner | 拒绝写入，标记 prompt_injection，不进入 DB | 模块（Step 2a 提炼） |
| 40 | 2 条 knowledge 的 top_similar_id 互指 | 执行 `dev dream` | 检测为多版本冲突，标记 conflict_group，入审核队列 | 集成（dream 流程） |

> **注意**：#38/#39 为安全扫描测试（需求文档 §九），仅覆盖提炼层的拒绝逻辑。完整安全扫描的深度测试不在本方案范围内。

### 7.3 模块测试（~40 条）—— mock 上游数据，验证单 Step 完整功能

> **原则**：每个 Step 用 mock 数据（符合上游输出格式的预制 JSONL/数据）作为输入，验证本 Step 的完整功能链路（含 LLM 调用、文件 I/O、DB 操作）。**不依赖上游模块的 import**。

| Step | 测试数量 | 关键验证点 | mock 输入来源 |
|------|:--:|------|------|
| **Step 0 接收** | 4 | OpenCode 适配器输出格式、Comate 适配器输出格式、异常数据源错误处理、空数据源 | mock SQLite / mock API 响应 |
| **Step 1 攒批** | 3 | JSONL 格式正确、`_flushed` 防重、空 raw 目录处理 | mock raw JSONL 文件 |
| **Step 2a 提炼** | 8 | 四轴分类合法性、occurred_at 格式、confidence 范围、边界输入（空消息/超长消息/纯代码/多语言混排）、LLM 超时处理、LLM 返回格式不合法处理 | mock batch JSONL |
| **Step 2b 提取** | 6 | 实体识别、关系类型（extends/implements/uses/depends_on）、实体归一化去重、空实体处理、LLM 超时处理 | mock summary JSONL（含 knowledge_text） |
| **Step 3 验证** | 4 | content_hash 更新、semantic_hash 计算、code_verified 设置 | mock knowledge JSONL |
| **Step 4 去重** | 4 | Jaccard 相似度计算、top_similar_id 设置、冲突组识别、死代码检测 | mock knowledge JSONL + mock DB 已有记录 |
| **Step 5 写入** | 6 | MD 文件完整性、DB 同步、content_hash 一致性（MD vs DB）、路径校验、写入失败回滚、空内容拒绝 | mock knowledge JSONL |
| **Step 6 巩固** | 5 | base_score 计算、状态迁移、修剪触发、supplement 合并 | mock DB（SQLite :memory: 预置数据，**无需经过 Step 5**） |
| **合计** | **~40** | | |

> **Step 6 独立测试关键**：Step 6 只需要 DB 中有知识记录即可运行，与 Step 0-5 完全解耦。用 SQLite :memory: 预置测试数据（含各种状态/分数的知识条目），Step 6 可完全独立测试。

### 7.4 集成测试（~15 条）—— 仅测试数据契约兼容性

> **原则**：不测试完整的端到端流程，只验证「上游真实输出能否通过下游的 validate_input()」。这大幅降低了集成测试的复杂度和运行成本。

| 集成边界 | 测试数量 | 验证点 | 为何只需测这个 |
|------|:--:|------|------|
| **Step 0 → Step 1** | 2 | 适配器真实输出的 JSONL 能否通过 Step 1 的 validate_input() | 其余都是各自模块的事 |
| **Step 1 → Step 2a** | 2 | batch JSONL 真实输出能否通过 Step 2a 的 validate_input() | 同上 |
| **Step 2a → Step 2b** | 2 | summary JSONL 真实输出能否通过 Step 2b 的 validate_input() | 同上 |
| **Step 2b → Step 3** | 2 | knowledge JSONL（含 entities/relations）能否通过 Step 3 的 validate_input() | 同上 |
| **Step 3 → Step 4** | 1 | 验证后的 knowledge JSONL 能否通过 Step 4 的 validate_input() | 同上 |
| **Step 4 → Step 5** | 1 | 去重后的 knowledge JSONL 能否通过 Step 5 的 validate_input() | 同上 |
| **Step 5 → Step 6** | 1 | Step 5 写入的 DB 记录能否被 Step 6 正确查询（schema 兼容性） | 同上 |
| **校准引擎联动** | 2 | Git commit → 校准触发 → 冲突检测触发（事件链连通性） | 事件触发链 |
| **注入路由联动** | 2 | L1/L2/L3 路由 + AGENTS.md 生成（格式兼容性） | 输出格式 |
| **合计** | **~15** | | |

> **对比原方案**：集成测试从 ~30 条缩减到 ~15 条。砍掉的是「Step 连续处理链路」测试——这些在模块测试中已用 mock 覆盖，在集成测试中重复验证没有额外价值。集成测试只做一件事：**确保数据能在 Step 间流动**。

### 7.5 E2E 测试（~12 条）

| 场景 | 验证点 |
|------|------|
| OpenCode 会话 → 知识注入 全链路 | SQLite 读取 → 8 Step → AGENTS.md 生成 |
| Comate 会话 → 知识注入 全链路 | 验证多源适配 |
| 代码变更 → 校准 → 知识更新 | Git commit → 校准引擎 → 知识状态更新 |
| 知识过期 → 修剪 → 清理 | 时间推进模拟 → STALE → DEPRECATED |
| 冷启动：空项目 init | dev init → `.devContextMemo/` + AGENTS.md 骨架 |
| 冷启动：多模块扫描 | `src/order/` + `src/payment/` → S1+S2 骨架生成 |
| 冷启动：审核通过 → STAGED | DRAFT 10 条 → 审核通过 8 条 → STAGED |
| 冷启动：AGENTS.md 自动注入 | `dev init` 生成的 AGENTS.md → 新会话注入 ≤4K |
| 冲突检测 → 仲裁 → 修复 | 模拟冲突 → 人工仲裁 → 状态更新 |
| 校正：MD-DB 索引漂移修复 | health-check → 检测漂移 → 列出差异 |
| 崩溃恢复 | 写入中途 kill → 重启 → 数据一致性 |
| 多源聚合 | OpenCode + Comate 同时采集 → 知识融合 |

---

## 八、LLM 分类基准测试（已有设计，此处整合）

> 详见 `reviews/devContextMemo-LLM分类基准测试-设计-V1.0.md`

| 分类轴 | 最低准确率 | 验证方法 |
|------|:--:|------|
| Lx（粒度） | 80% | 50 条标注数据，对比 LLM 输出 vs ground_truth |
| Sy（稳定性） | 75% | 同上 |
| Depth（认知深度） | 85% | 同上 |
| Domain（业务领域） | 80% | 同上 |
| **综合** | **≥ 80%** | 每 100 条 ≤ 20 条至少一个轴分类错误 |

**触发时机**：
- LLM Prompt 模板变更 → L3 强门禁自动运行
- 每周定期运行 → 生成准确率趋势报告

---

## 九、实施优先级

### 测试工具选型

| 工具 | 用途 | 版本要求 |
|------|------|------|
| **pytest** | 测试框架 | ≥ 8.0 |
| **pytest-asyncio** | 异步测试支持（Step 2a/2b LLM 调用） | ≥ 0.23 |
| **pytest-mock** | mock 框架（mock 上游数据 + LLM API + 文件系统） | ≥ 3.12 |
| **coverage** | 代码覆盖率 | ≥ 7.0 |
| **SQLite :memory:** | 集成测试 + Step 6 独立测试的数据库 | 内置（Python 3.11+） |
| **YAML 契约执行器** | 自定义 pytest plugin：读取 YAML 契约 → 执行 → 收集证据 | 编码阶段实现（`tests/contract_runner.py`） |

> **LLM Mock 策略**：模块测试中 LLM 调用通过 `pytest-mock` 拦截 `llm_client.chat()` 方法，返回预制 JSON 响应。每种场景（正常/超时/格式错误/低置信度）预制 1 个 fixture。基准测试才使用真实 LLM 调用。

### Phase 1（编码阶段同步）

| 优先级 | 内容 | 说明 |
|:--:|------|------|
| P0 | 单元测试框架搭建（pytest + pytest-asyncio + coverage） | 编码前完成 |
| P0 | 8 个 Step 契约 YAML 定义 | 编码前完成（契约驱动开发） |
| P0 | Step 5 写入契约测试（最高风险） | 写 writer.py 时同步 |
| P0 | Step 2a 提炼契约测试（最高风险） | 写 extractor.py 时同步 |
| P1 | Step 2b 提取契约测试 | 写 entity_extractor.py 时同步 |
| P1 | 各模块单元测试 | 随编码交付 |
| P1 | LLM 分类基准测试执行 | 写完 Step 2a 后立即验证 |
| P2 | 集成测试 | 模块间联调时 |
| P2 | E2E 测试 | Phase 1 收尾 |

### Phase 2（精加工阶段）

| 优先级 | 内容 |
|:--:|------|
| P2 | CI 门禁集成（L1/L2/L3 自动判定） |
| P2 | 分类准确率趋势监控 |
| P3 | 证据模型完善（全链路 trace） |
| P3 | 性能基准测试 |

---

## 十、与 AQE 的映射总结

| AQE 概念 | devContextMemo 落地 | 状态 |
|------|------|:--:|
| 可执行契约 DSL | 8 个 Step 的 YAML 契约文件 | 📋 本文定义 |
| 执行状态机 | 每个契约测试的 PREPARE→EXECUTE→ASSERT→EVIDENCE→PASS/FAIL/BLOCK | 📋 本文定义 |
| 风险分级门禁 (L1/L2/L3) | 业务影响 × 变更复杂度 × AI 参与度 → L1/L2/L3 | 📋 本文定义 |
| 证据模型（5 类） | 功能/数据/过程/环境/治理证据 | 📋 本文定义 |
| Harness 运行框架 | CI pipeline + pytest 框架 | 🔜 Phase 2 |
| Planner Agent（风险识别） | 人工判定 + diff 分析脚本 | 🔜 Phase 2 |
| Specialist Subagents | 单元/契约/集成/E2E 各层独立执行 | 📋 本文定义 |
| 落地指标 | 分类准确率/BLOCK 原因分布/报告有效率 | 📋 本文定义 |
