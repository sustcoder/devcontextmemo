# devContextMemo 深度设计：知识更新 · 冲突检测 · 冲突解决

> **触发**：用户提出核心问题——「如何做知识的更新、如何检测冲突、如何解决冲突。这关乎知识内容是否保真。」
> **原则**：第一性原理出发，不受已有设计约束；真实调研同类方案并引证；输出可落地的设计决策
> **日期**：2026-06-16
> **版本**：V1.7（修补 V11：INCONSISTENT 时旧知识即时标记 + V12：suspected_stale 的 evidence_level 折扣 + V13：V5 降级前间接验证检查）
> **关联文档**：
> - `devContextMemo-流水线-Step4-去重层-细化设计-V1.0.md`（3 层判别 + 4 类动作）
> - `devContextMemo-流水线-Step5-写入层-细化设计-V1.0.md`（3 目录 + 绿色通道）
> - `devContextMemo-目录划分-晋升规则-修改检测-深度调研-V1.0.md`（晋升公式 + 冷知识保护）

---

## 〇、问题陈述

> 「我们如何做知识的更新、如何检测冲突、如何解决冲突。这个关乎我们最后的知识内容是否保真。」

拆解为三个核心问题：

| 问题 | 本质 | 当前设计覆盖度 |
|------|------|:---:|
| **Q1: 更新** | 知识什么时候需要更新？谁来更新？更新后如何保证质量？ | ~40%（只覆盖「新知识到来时 MERGE」一条路径） |
| **Q2: 冲突检测** | 怎么知道两条知识互相矛盾？能否在冲突发生前预警？ | ~30%（只检测新知识 vs 已有知识，不检测已有之间的冲突） |
| **Q3: 冲突解决** | 矛盾了怎么判？凭 confidence？凭证据？凭时间？ | ~20%（只有 confidence 比大小 + 人工裁决，缺乏证据权重） |

> **目标**：把这三个覆盖率从 30-40% 提升到 ≥80%，给出可落地的完整方案。

---

## 〇.五、设计依据：同类系统调研（V1.1 新增）

> 用户要求：「关键决策可有依据可循？是否先调研下？」

以下是针对 4 个关键决策方向的调研结果，每个都有可验证的参考来源。

### 调研 1：知识库内部矛盾检测 —— KnowledgeBase Guardian

**来源**：[datarootsio/knowledgebase_guardian](https://github.com/datarootsio/knowledgebase_guardian)（GitHub 开源）

| 维度 | 他们的做法 | 对我们的启示 |
|------|-----------|-------------|
| **检测机制** | 新文档写入 → 向量检索 top-K 最相似已有文档 → LLM 逐条比对是否矛盾 | ✅ 架构同我们的 Step 4（新 vs 已有） |
| **矛盾判断** | 完全依赖 LLM 语义判断，无规则引擎 | ✅ 验证 LLM 判断矛盾是可行的（不是妄想） |
| **处理方式** | 矛盾 = 拒绝写入（除非 `--force-extend`） | ⚠️ 他们选择「阻止」而非「标记冲突」——太粗暴 |
| **局限性** | ① 只检测新 vs 已有，不扫描已有之间 ② 分块处理导致同一文档的部分块被接受、部分被拒绝 | 🔴 **盲区正是我们要解决的**——他们只有 L1 检测，我们补 L3（交叉扫描） |
| **结论** | 这证明「LLM 语义比对 + 向量相似度」的矛盾检测范式是可行的 | **我们的 L3 交叉扫描是对此范式的自然扩展** |

> 📎 **关键引用**：KnowledgeBase Guardian 明确声明——「假设初始向量存储中的所有文档都是无矛盾的」。这个假设在实际生产中不成立——这正是我们需要 L3 交叉扫描的原因。

---

### 调研 2：代码-文档语义一致性检查 —— METAMON

**来源**：[METAMON: Finding Inconsistencies between Program Documentation and Behavior using Metamorphic LLM Queries](https://www.themoonlight.io/zh/review/metamon-finding-inconsistencies-between-program-documentation-and-behavior-using-metamorphic-llm-queries)（ICSE 2025）

| 维度 | 他们的做法 | 对我们的启示 |
|------|-----------|-------------|
| **解决的问题** | 程序文档（Javadoc）描述与代码实际行为不一致——和我们的场景完美重合 | ✅ 行业共识：文档-代码一致性是真实痛点 |
| **核心方法** | ① EvoSuite 生成回归测试（捕获代码真实行为）② 用元变关系（Metamorphic Relations）构造多组对比提示 ③ LLM 判断行为是否与文档一致 | ✅ **代码行为可以自动化捕获，LLM 可以做语义对比** |
| **评测数据** | 9,482 对代码-文档对，精确度 0.72，召回率 0.48 | ⚠️ 精确度可以（误判率 28%），但召回率有限（漏检 52%）——说明完全自动检测仍有盲区 |
| **元变关系的价值** | 同一函数的正负输入应产生对应关系——通过这种关系交叉验证 LLM 判断可靠性 | 📌 可借鉴：我们也可以用代码变更前后的行为变化作为交叉验证 |
| **对我们 L4 的支持** | **METAMON 证明了：用 LLM 判断「代码行为 vs 文档描述」是否一致是可行的** | ✅ 我们的 L4（知识-代码语义一致性检查）有学术支撑 |

> 📎 **关键引用**：METAMON 的 5 步流程——选取文档 → 捕捉行为 → 构造元变提示 → 查询 LLM → 评分——与我们设计的 L4 流程（检测代码变更 → 读取当前代码 → LLM 语义对比 → CONSISTENT/INCONSISTENT）**在架构上高度吻合**。

---

### 调研 3：冲突类型分类 + 不同策略解决 —— Weave

**来源**：[Ataraxy-Labs/weave](https://github.com/Ataraxy-Labs/weave)（Apache-2.0/MIT）

| 维度 | 他们的做法 | 对我们的启示 |
|------|-----------|-------------|
| **核心思想** | Git 的「行级合并」把独立修改误判为冲突 → 用 tree-sitter 做「实体级合并」 | ✅ **不是所有冲突都是冲突——需要先分类再处理** |
| **冲突分类** | ① 不同实体被修改 → 自动解决 ② 同一实体被双方修改 → 才报冲突 ③ 一方修改一方删除 → 明确提示 | ✅ 我们的 6 类冲突分类（事实/时效/范围/粒度/隐式/人为）遵循相同原则 |
| **效果数据** | 减少 95% 虚假冲突；31 个真实合并场景中 100% 干净合并（Git 仅 48%） | ✅ 分类+分策处理 = 显著降低误报率 |
| **零回归设计** | 在 git/git、Flask、CPython、Go 等大型仓库回放测试，零回归——不会产生比 Git 更差的结果 | 📌 我们的设计也应该保证：自动解决的结果不能比人工审核前更差 |
| **冲突标记增强** | 当确实冲突时，标记 `<<<<<<< ours — function 'process' (双方均修改)`——告诉开发者哪个实体、什么类型、为什么冲突 | 📌 我们的冲突标记也应包含：冲突类型 + 证据来源 + 置信度 |

> 📎 **关键引用**：Weave 证明了「先分类、再按类型选择策略」的设计范式是工程上可行的，且有量化的效果提升。我们的 6 类冲突 + 6 条解决分支直接借鉴了这个思路。

---

### 调研 4：知识融合中的证据权重 —— Detect-Then-Resolve (CRDL)

**来源**：[Detect-Then-Resolve: Enhancing Knowledge Graph Conflict Resolution with LLM](https://www.mdpi.com/2227-7390/12/15/2318)（Mathematics 2024）

| 维度 | 他们的做法 | 对我们的启示 |
|------|-----------|-------------|
| **核心挑战** | 知识图谱融合时，外部三元组与已有 KG 产生冲突，需要判定哪个是真相 | ✅ 和我们「新知识 vs 已有知识」的场景一致 |
| **方法** | ① 冲突检测：针对不同关系类型/属性类型（一对一 vs 非一对一）实施精准过滤 ② LLM 注入上下文信息进行裁决 | ✅ **冲突先分类（关系类型），再 LLM 裁决** |
| **关键洞察** | 不同类型的关系需要不同的冲突过滤策略——一对一关系（如出生日期）的冲突处理，与一对多关系（如职业）完全不同 | 📌 **验证了我们的冲突类型分类的必要性**——事实冲突和范围冲突需要不同的处理策略 |
| **LLM 的角色** | 在检测阶段做精准过滤，在解决阶段做语义裁决——LLM 不是一招鲜，而是在不同阶段承担不同职责 | ✅ 我们的设计吻合：L2 用 LLM 判断矛盾类型，L3 用 LLM 做交叉扫描，L4 用 LLM 做语义一致性 |

> 📎 **关键引用**：CRDL 的 Detect-Then-Resolve 两阶段范式，支持了我们「不是所有冲突都交 LLM 解决，也不是所有冲突都不交 LLM 解决」的设计立场。

---

### 调研 5：多版本并发控制（MVCC）作为修订基础 —— CouchDB

**来源**：CouchDB MVCC 机制（Apache 2.0）+ Git 内容寻址

| 维度 | 他们的做法 | 对我们的启示 |
|------|-----------|-------------|
| **CouchDB MVCC** | 每次写操作带 `_rev` 版本号；冲突时保留所有版本，应用层选择 winner；旧版本永不丢失 | ✅ 直接对应我们的修订链设计——每次更新保留旧版本到 deprecated/ |
| **Git 内容寻址** | 每个 blob 由内容 SHA 唯一标识；修改 = 新 blob + 新 tree + 新 commit，旧 blob 保留可查 | ✅ 知识修改也应该是「新版本取代旧版本」而非「原地覆盖」 |
| **核心原则** | **保留历史 > 覆盖历史**——可追溯、可回滚是知识保真的底线 | ✅ 我们的设计：旧版本 → deprecated/，新版本 → knowledge/，DB 中 superseded_by 链 |

> 📎 **关键引用**：CouchDB 的 MVCC 和 Git 的内容寻址共同证明——在需要保证数据一致性的系统中，**多版本保留不是开销，是安全网**。

---

### 调研结论：4 个关键决策的可信度评估

| 关键决策 | 支撑依据 | 可信度 |
|---------|---------|:---:|
| **L3 交叉扫描**（已有知识间矛盾检测） | KnowledgeBase Guardian 验证了 LLM 判断矛盾的可行性；其「只检测新 vs 已有」的局限正是我们要补的 | ⭐⭐⭐⭐ 高 |
| **L4 代码语义一致性**（代码变更后 LLM 检查） | METAMON（ICSE 2025）直接验证了此方法，精度 0.72 | ⭐⭐⭐⭐⭐ 很高 |
| **冲突类型分类 + 分策解决** | Weave 减少 95% 虚假冲突的量化证据；CRDL 对不同关系类型用不同策略的理论支撑 | ⭐⭐⭐⭐⭐ 很高 |
| **证据可信度层级** | CRDL 的「精准过滤策略」思路 + KG 融合领域普遍共识（权威来源 > 不可靠来源）| ⭐⭐⭐ 中高 |
| **修订链/多版本保留** | CouchDB MVCC + Git 内容寻址——两个被广泛验证的工程实践 | ⭐⭐⭐⭐⭐ 很高 |

> **结论**：4 个关键决策全部有可验证的参考依据，不是凭空设计。其中 L4（代码语义一致性）和冲突类型分类（Weave 范式）有最强的量化支撑。

---

## 第一部分：知识更新的全景图

### 1.1 知识需要更新的 7 种场景

当前设计只覆盖了场景 ①。实际上知识可能因为以下任何原因需要更新：

```
知识需要更新的触发源：

① 新对话产生矛盾信息 ────→ Step 4 检测 MERGE_CANDIDATE ──── ✅ 已覆盖
② 关联代码变更            → Step 3 校验失败 ──────────→ ⚠️ 部分覆盖（检测到但不知怎么修）
③ 用户手动纠错            → 用户在 UI 中说「这条错了」──→ ❌ 未覆盖
④ 两条已有知识互相矛盾    → 后台扫描发现 ──────────→ ❌ 未覆盖
⑤ 知识自然过时            → 时间衰减 ──────────────→ ⚠️ 部分覆盖（只衰减不主动修正）
⑥ 知识被更精确的版本取代  → 更精确的同类知识出现 ──→ ⚠️ 部分覆盖（MERGE 但无 precision 比较）
⑦ 上下文环境变化          → 框架版本升级 / 架构重构 ──→ ❌ 未覆盖
```

### 1.2 每条更新路径的设计

#### 路径 ①：新对话产生矛盾信息（已覆盖）

```
流程: Step 4 检测 cosine ≥ 0.95 → MERGE_CANDIDATE
      → 字段级合并或人工裁决

缺口: 无。当前设计足够。
```

#### 路径 ②：关联代码变更导致知识过期（部分覆盖，需补全）

**当前状态**：Step 3 的代码校验能检测到「关联代码变更了」，但只标记 `verify_status = failed`。

**缺口**：标记 failed 之后怎么办？

```
建议补全流程：

Step 3 检测到代码变更
  → 标记 verify_status = 'stale'（而非直接 failed）
  → 触发「知识-代码一致性检查」：
      ┌─────────────────────────────────────────────┐
      │  1. 读取当前代码上下文（文件内容 + diff）     │
      │  2. 读取旧知识内容                           │
      │  3. LLM 判断：知识描述与代码现状是否一致？     │
      │     ├─ 一致 → 更新 verify_status = 'verified' │
      │     │         更新 last_verified_at           │
      │     ├─ 不一致 → 分两种情况：                   │
      │     │   ├─ 代码是对的 → 知识需要更新           │
      │     │   │   → 生成 UPDATE_CANDIDATE             │
      │     │   │   → 写入 staging/，标记来源='code_change'
      │     │   └─ 代码可能是错的 → 标记待确认         │
      │     │       → 标记 status='conflict_with_code'  │
      │     │       → 提示用户确认                      │
      │     └─ 无法判断 → 标记 'needs_review'          │
      └─────────────────────────────────────────────┘
```

**关键设计**：代码变更 ≠ 知识错误。需要 LLM 做一次「语义对比」——代码仍然可能符合知识描述（比如重构了实现但 API 和行为没变）。

#### 路径 ③：用户手动纠错（需新建）

**场景**：用户在审查知识时发现错误，直接说「这条不对」。

**设计方案**：

```
dev-context-memo-dream --fix kw-20260614-001 --reason "端口号不是8080，是8081"

→ 系统：
  1. 读取旧知识 kw-20260614-001
  2. 创建修正版本：
     - 旧知识 → deprecated/kw-20260614-001.md（保留原版可追溯）
     - 新知识 → staging/20260616-<修正后标题>.md
     - YAML 标记：
       supersedes: kw-20260614-001
       fix_reason: "用户手动修正：端口号不是8080，是8081"
       revision: <旧revision + 1>
  3. 更新 DB：
     - 旧记录 status → 'superseded'
     - 旧记录 successor_id → 新记录 ID
     - 新记录 source = 'manual_fix'
```

**为什么不直接修改原文件？** 保留修订历史 = 可追溯 = 可回滚。用户可能改错了，需要能回到上一版。

#### 路径 ④：两条已有知识互相矛盾（需新建——这是本次讨论的核心）

这个在下一部分「冲突检测」中详细展开。这里先给出概要：

**场景**：两条知识都在 knowledge/ 中，一条说「缓存用 Redis」，另一条说「缓存用 Memcached」。它们都通过了验证，但互相矛盾。

**设计方向**：
- 定期扫描（`dev-context-memo-dream` 执行时顺便做）
- 对同一 domain 下的知识做 pairwise cosine 比较
- 高相似度 + LLM 判断矛盾 → 标记 conflict_with
- 按证据权重自动裁决或推人工

#### 路径 ⑤：知识自然过时（需补全）

**当前状态**：有 time_decay 机制，但只会降 confidence，不会主动触发更新。

**缺口**：一条知识 confidence 从 0.9 衰减到 0.6，但它仍然存在，内容没变——用户不知道它已经不可靠了。

```
建议补全：

当 confidence 因 time_decay 降至 < 0.6 时：
  → 自动标记 status = 'stale'
  → 在 dev-context-memo-dream 报告中列出：
    「以下知识已超过 180 天未重新验证，建议确认是否仍然有效：
      - 订单幂等校验方案 (confidence: 0.85 → 0.58, 上次验证: 2025-12-01)」
  → 用户可选择：
    - 「确认仍然有效」→ 重新校验，confidence 恢复
    - 「已过时」→ 移入 deprecated/
    - 「需要修正」→ 触发路径 ③
```

#### 路径 ⑥：被更精确版本取代（部分覆盖，需细化）

**场景**：已有知识「使用 Redis 做缓存」，新知识「使用 Redis Cluster 6.2 做缓存，3 主 3 从」。

当前 MERGE 会尝试字段级合并——但这不合理。新知识是旧知识的**精确化**，不是补充。

```
建议区分：

MERGE_CANDIDATE 时 LLM 增加一个判断维度：
  「新知识是旧知识的更精确版本吗？」

  是 → PRECISION_UPGRADE
       - 旧知识移入 deprecated/，标记 superseded_by
       - 新知识继承旧知识的 entry_point 和关联关系
       - 在 revision_history 中记录升级

  否（补充信息）→ 追加模式（当前设计）
  否（互相矛盾）→ 冲突处理（路径 ④ 或人工）
```

#### 路径 ⑦：上下文环境变化（需新建，Phase 2 考虑）

**场景**：项目从 Spring Boot 2.x 升级到 3.x，大量 API 规范变了。

这是最难处理的场景——影响范围广，涉及多条知识。Phase 1 暂不做自动处理，但预留机制：

```
Phase 2 设计方向：
- 用户在 dev-context-memo-dream 中声明「上下文变更」：Spring Boot 2.x → 3.x
- 系统扫描所有 mention 了 Spring Boot 的知识
- 逐条标记 'context_changed'，提示人工复核
```

### 1.3 更新全景汇总

```
                    知识更新的 7 条路径

    ① 新对话矛盾 ─────────────────→ MERGE_CANDIDATE ──→ ✅ 已覆盖
    ② 代码变更   ──→ Stale Check ──→ UPDATE/conflict ──→ ⚠️ 需补全 LLM 语义对比
    ③ 用户纠错   ──→ Manual Fix ───→ supersede ────────→ ❌ 需新建
    ④ 已有矛盾   ──→ Cross-scan ───→ conflict_with ────→ ❌ 需新建（核心）
    ⑤ 自然过时   ──→ Stale flag ───→ 人工确认 ─────────→ ⚠️ 需补全主动提示
    ⑥ 精确取代   ──→ PRECISION_UPGRADE ────────────────→ ⚠️ 需补全判断维度
    ⑦ 环境变化   ──→ context_changed ──────────────────→ ❌ Phase 2
```

### 1.4 A2 决策修正：用户手动修改 MD 文件的处理（V1.2 落地）

> **触发**：用户质疑——「如果用户手动改了 md 文件怎么办？」

**两条路径**：

```
路径 A（主动修改）：用户通过命令修改
  dev-context-memo-dream --fix kw-20260614-001 --reason "端口是8081不是8080"
  → 系统创建修正版本：旧→deprecated/，新→staging/，DB 链串联
  → 行为同路径③（用户手动纠错）

路径 B（被动检测）：用户直接在 IDE 改了文件，dream 执行时发现
  dream Phase 1（扫描）增加完整性校验：
  
  对 knowledge/ 和 staging/ 下每个 .md 文件：
    1. 计算当前文件 MD5
    2. 与 DB 中 content_hash 对比
    
    匹配 → 跳过（未被手动修改）
    不匹配 → 🚩 文件被手动修改了
      
      a. 查 revision_history，最后一次 action 是 'manual_edit'？
         YES → 正常（上次 dream 已记录）
         NO  → 进入检测流程
      
      b. 用 git diff 获取变更摘要
      c. 提示用户：
         「⚠️ xxx.md 被手动修改。
          变更摘要：【端口号从 8080 → 8081】
          建议操作：
            [1] 记录为合法修正（更新 hash，追加 revision_history）
            [2] 回滚到上一个 dream 版本（从 Git 或 deprecated/ 恢复）
            [3] 稍后处理（本次跳过此文件）」
      
      d. 用户选 [1] → 视为合法修改，同步 DB
         YAML 追加: revision_history:
           - version: N+1
             action: manual_edit
             change: "端口号从 8080 → 8081"
             reason: "用户手动修改"
      
      e. 用户选 [2] → git checkout 恢复或从 deprecated/ 恢复上一版
```

**设计原则**：不阻止用户直接改文件（尊重用户工具习惯），但在 dream 时检测 + 让用户确认。通过 git diff 拿变更摘要降低认知成本。

---

## 第二部分：冲突检测——不只是「来了新知识」

### 2.1 当前检测机制的覆盖盲区

```
当前 Step 4 的检测范围：

检查范围:  新候选知识 K_new  vs  已有知识库
检查方式:  MD5 + cosine 相似度
检查时机:  仅当新知识到达时

盲区 1 ──→ 两条已有知识互相矛盾，但从未被同时检测
            例: knowledge/订单/ 下有 A 和 B，A 说「用 Redis」，B 说「用 Memcached」
            它们分两次不同会话写入，写入时互不知道对方存在

盲区 2 ──→ 知识仍然「正确」但关联代码已经变了
            例: 知识说「OrderService.createOrder() 返回 Order 对象」
            但代码重构后返回的是 OrderResult
            Step 3 检测到代码变更，但没有判断「知识是否需要更新」

盲区 3 ──→ 新知识与已有知识表述不同但事实一致（假冲突）
            例: 知识 A「缓存过期时间 300 秒」vs 新知识 B「缓存过期 5 分钟」
            cosine ≈ 0.92，标记 UPDATE_CANDIDATE，但实际上不需要更新
```

### 2.2 三层检测架构（扩展版）

把「新知识到达时的检测」扩展为「持续的知识一致性检测」：

```
┌──────────────────────────────────────────────────────────────┐
│                    知识保真检测矩阵                             │
├──────────────┬──────────────────┬──────────────────────────┤
│   检测时机    │   检测对象        │   检测方法                  │
├──────────────┼──────────────────┼──────────────────────────┤
│  写入时      │  K_new vs K_old   │  MD5 + cosine + LLM 判别   │  ← 当前已有
│  (实时)      │  (单条 vs 单条)   │                            │
├──────────────┼──────────────────┼──────────────────────────┤
│  dream 执行  │  K_i vs K_j       │  domain 内 pairwise cosine │  ← 🆕 已有间检测
│  (周期性)    │  (同 domain 内)   │  + LLM 矛盾判断             │
├──────────────┼──────────────────┼──────────────────────────┤
│  代码变更时  │  K vs Code        │  LLM 语义一致性检查         │  ← 🆕 知识-代码
│  (事件触发)  │  (知识 vs 代码)   │                            │    一致性
├──────────────┼──────────────────┼──────────────────────────┤
│  用户审核时  │  K vs Human       │  人工判断                   │  ← 🆕 人工校准
│  (按需)      │  (知识 vs 人)     │                            │
└──────────────┴──────────────────┴──────────────────────────┘
```

### 2.3 🆕 检测机制 A：已有知识间的交叉扫描

这是盲区 1 的核心解决方案。

#### 为什么需要？

```
场景还原：
  周一：AI 从对话中提炼出「缓存方案用 Redis」
       → confidence=0.82 → 写入 staging/
  
  周三：另一场对话中，用户说「我们不用 Redis，用 Memcached」
       → AI 提炼出「缓存方案用 Memcached」
       → confidence=0.78 → 写入 staging/
  
  周五：dev-context-memo-dream 执行
       → 两条分别评估，都晋升到 knowledge/（单条评分都够）
       → 但它们互相矛盾！系统现在不知道。
```

#### 设计方案

```
dev-context-memo-dream 执行时新增 Phase 2.5（在晋升之后、报告之前）：

Phase 2.5: 跨知识一致性扫描（V1.4 修补 V2：新增 concept_tags 条件）

1. 扫描范围筛选——只扫描满足以下任一条件的 pair：
   a. 共享 entry_point（两条知识指向同一代码文件/函数）
   b. 共享 topic 标签（LLM 提炼时自动打的 subject 标签相同）
   c. cosine ≥ 0.95（极高相似度，几乎肯定是同一话题）
   d. 共享 ≥2 个 concept_tags + cosine ≥ 0.75
      （concept_tags 是比 topic 更抽象的概念标签，如 #缓存架构 #中间件选型。
       只共享 1 个太宽泛不触发，共享 ≥2 个才纳入。
       同时要求 cosine ≥ 0.75 过滤掉概念相同但内容完全不相关的 pair。）
   e. 已被人工标记 conflict_with 的知识对（被动扫描）

   🆕 condition d 的价值（V2 修补）：
     解决「Redis 和 Memcached 同属缓存架构、可能互相矛盾，
     但 entry_point 不同、topic 标签不同、cosine 不够高」的漏检问题。
     举例：knowledge/缓存/用户会话缓存.md 和 knowledge/缓存/热点数据缓存.md
     → 共享 concept_tags: ["缓存架构", "中间件选型"]
     → 触发扫描 → LLM 比对 → 发现选型冲突

2. 对每个候选冲突对，调用 LLM 判断关系（V1.4 修补 V3：四分类→五分类）：
   
   输入: K_A 的 content + K_B 的 content + concept_tags + evidence_level
   提示: 「请判断知识 A 和知识 B 的关系，选择以下之一：

   1. mutually_exclusive — 两者不能同时为真
      （如端口是 8080 vs 端口是 8081）
   2. one_refines_other  — 一条是另一条的精确化/细化/扩展
      （如 A=「用 Redis」B=「用 Redis Cluster 6.2 3主3从」）
   3. compatible_with_condition — 两者在特定条件下可以同时为真
      （如 A=「主库是 PostgreSQL」B=「主库是 MySQL，PG 做读副本」）
   4. complementary       — 内容互补，不矛盾，建议合并
      （如 A=「超时 30 秒」B=「重试 3 次」）
   5. identical           — 语义相同，仅表述不同

   🆕 为什么改为五分类：
     原「contradict」过于粗糙——把「绝对互斥」和「有条件兼容」都装进去了。
     典型误判：A=「PostgreSQL 做主库」vs B=「MySQL 做主库 + PG 读副本」
     → 原判 contradict → 仲裁 → A 被废弃，但 PG 仍是读副本的事实丢失了
     → 新判 compatible_with_condition → 保留两条件为范围冲突处理」
   
   输出: 
   {
     "relation": "mutually_exclusive" | "one_refines_other" | "compatible_with_condition" | "complementary" | "identical",
     "explanation": "判定依据（必填，用于后续人工审核）",
     "contradiction_point": "矛盾点（仅 mutually_exclusive 时必填）",
     "condition": "兼容条件（仅 compatible_with_condition 时必填）",
     "refinement_direction": "A_refines_B 或 B_refines_A（仅 one_refines_other 时必填）",
     "recommended_action": "arbitrate" | "supersede_old" | "add_condition" | "merge_fields" | "discard_new"
   }

3. 处理结果：
   ┌──────────────────────────────────────────────────────────────┐
   │ mutually_exclusive →                                          │
   │   标记两条知识 conflict_with = 对方 ID                          │
   │   写入 YAML: conflict_with: kw-xxx                             │
   │   进入证据仲裁流程（第三部分）——用 evidence_weight × confidence   │
   │                                                                │
   │ one_refines_other →                                            │
   │   一条是另一条的精炼版本                                        │
   │   粗 → deprecated，细 → knowledge                               │
   │   🆕 不走仲裁（不是矛盾，是升级）                                │
   │                                                                │
   │ compatible_with_condition →                                    │
   │   保留两条，补充条件说明                                         │
   │   走范围冲突处理——通用规则 + 例外/条件补充                        │
   │   🆕 示例：「主库：MySQL。历史遗留：PG 读副本（逐步迁移中）」     │
   │   🆕 不走仲裁（两者可共存）                                      │
   │                                                                │
   │ complementary →                                                 │
   │   内容互补，建议字段级合并                                        │
   │   合并后写入 staging/，旧的合并到 deprecated/                     │
   │                                                                │
   │ identical →                                                     │
   │   语义相同，仅表述不同                                            │
   │   丢弃新知识，刷新旧知识 last_verified_at 时间戳                   │
   └──────────────────────────────────────────────────────────────┘
```

### 2.3.1 V10 修补：字段级合并的语义消歧

> **漏洞**：字段级合并只看字段名，不看字段语义。同名字段可能指代完全不同的概念，合并会产生错误。
>
> **风险量化**：R=8（概率中 × 影响严重）。字段同名是常见现象，但多数情况下确实同一概念，只有少数需要特殊处理。

**场景 1：同名 + 不同领域**
```
知识 A（订单服务）：timeout: 30     （30 秒，订单超时）
知识 B（支付服务）：timeout: 30min  （30 分钟，支付超时）
→ 合并取高 confidence 方 → 「订单 timeout = 30min」← 错误
```

**场景 2：同名 + 不同概念**
```
知识 A（DB 配置）：max_connections: 100   （连接池大小）
知识 B（Kafka）：  max_connections: 10    （consumer 连接数）
→ 合并产生范围 → 「10-100」← 完全错误
```

**修补——规则引擎消歧（不调 LLM）**：

```
Step 3a：字段语义消歧（规则引擎）
  
  对于同名字段 K_A.field 和 K_B.field：
  
  1. 取两条知识的 concept_tags：
     A.tags: ["#订单", "#超时"]
     B.tags: ["#支付", "#超时"]
  
  2. 计算交集，判定：
  
     ┌──────────────────────────────────────────────────────────┐
     │ 共享 ≥ 2 个 concept_tags → same_concept                  │
     │   → 正常合并流程                                          │
     │                                                          │
     │ 共享 1 个 concept_tag → ambiguous                         │
     │   → 数值量级差 > 10x → different_domain（不合并）          │
     │   → 数值量级差 < 10x → same_domain_different_unit        │
     │     → 归一化后合并（如 30s vs 30000ms → 30s）             │
     │                                                          │
     │ 共享 0 个 concept_tags → different_domain                │
     │   → 字段加 domain 前缀区分：                              │
     │      order_timeout: 30                                   │
     │      payment_timeout: 30min                              │
     └──────────────────────────────────────────────────────────┘

Step 3b：兜底——无法判定时标记 needs_review，推人工
```

**为什么用规则引擎而非 LLM**：字段消歧是高频操作；95% 的同名字段确实同一概念，不值得为 5% 调 LLM；concept_tags 已被 V2 修补加固，覆盖率足够。**与 V2 的协同**：V2 的 concept_tags 为 V10 提供了基础设施，没有 V2，V10 就得调 LLM 做语义消歧。

```
```

#### 性能考量

```
同 domain 内 pairwise 比较的复杂度：

假设 domain 下有 N 条知识：
- embedding 比较：O(N²) 次 cosine 运算
  - N=50  → 1225 次 → 毫秒级
  - N=200 → 19900 次 → 仍在可接受范围
  - N=1000 → 499500 次 → 需要限制（只比较最近修改的）

- LLM 调用：仅对 cosine ≥ 0.85 的 pair 调用
  - 实际命中率预计 < 5%（同一 domain 下多数知识不相关）
  - N=200，阈值对 ≈ 20 对 → 20 次 LLM 调用

Phase 1 策略：
- 限制 pairwise 范围为「最近 90 天内修改过的知识」
- 限制单次扫描最多 50 次 LLM 调用
- 超出的标记为「待下次扫描」
```

### 2.4 🆕 检测机制 B：知识-代码语义一致性

这是盲区 2 的核心解决方案。

#### 当前 Step 3 的问题

```
Step 3 当前逻辑：
  「关联代码的 MD5 变了 → verify_status = failed」

问题：
  1. 代码重构（行为不变但结构变了）→ MD5 变了 → 误报
  2. 代码注释改了 → MD5 变了 → 误报
  3. 关联文件新增 import → MD5 变了 → 误报

MD5 只能判断「变了」，不能判断「知识是否仍然正确」。
```

#### 设计方案

```
Step 3 改进（V2.0）：

当检测到关联代码文件 MD5 变更时：

  不是直接标记 failed，而是触发「语义一致性检查」：

  输入:
    - 旧知识内容（「OrderService.createOrder() 返回 Order 对象」）
    - 变更后的代码片段（read_file 获取当前代码）
    - 代码 diff（git diff 关联文件）
  
  LLM 判断（一次调用）:
  
  「以下是知识条目描述的代码行为：
    【知识内容】
    
    以下是关联代码的当前版本：
    【代码片段】
    
    以下是代码变更 diff：
    【diff】
    
    请判断：知识描述是否仍然与代码现状一致？
    
    - 如果一致（代码重构但行为不变）：回答 CONSISTENT
    - 如果不一致（代码行为已改变）：回答 INCONSISTENT
      并指出：知识中哪一句描述不再正确？代码现在的正确行为是什么？
    - 如果无法确定：回答 UNCERTAIN」
  
  结果处理:
    CONSISTENT → 更新 last_verified_at, code_verified=1
    INCONSISTENT → 自动生成修正建议（UPDATE_CANDIDATE）
                   写入 staging/，标记 source='code_change'
                   🆕 V11：同时标记旧知识 status = 'suspected_stale'
                   （防止在人工确认前旧知识仍被正常注入）
    UNCERTAIN → 🆕 V6 修补：多层次兜底（不再只是标记 needs_review）
```

### 2.4.1 🆕 V6 修补：UNCERTAIN 的多层次兜底

> **漏洞**：LLM 返回 UNCERTAIN 时，旧知识仍然停留在 knowledge/ 中，照常被注入到 AI 对话中。但实际上代码已经变了，LLM 不确定只是因为逻辑太分散——旧知识很可能已经错了。
>
> **风险量化**：R=9（概率中 × 影响可靠性）。METAMON 精度 0.72 意味着 28% 的检查可能误判或返回 UNCERTAIN。UNCERTAIN 不是稀有事件。

**场景走查回顾**（来自审核报告场景 1）：

```
knowledge/订单/幂等校验方案.md
  content：「使用 Redis SETNX 实现订单幂等」
  evidence_level=5, code_verified=1

开发者在一次对话中重构了 OrderService：
  - Redis SETNX 逻辑被拆到了 3 个文件中
  - OrderService.java、DistributedLock.java、LockConfig.java 都变了
  - 代码实质改为 DB 唯一索引，但逻辑太分散

Step 3 LLM 语义一致性检查：
  → 返回 UNCERTAIN（逻辑太分散，无法从 diff 判断行为是否一致）
  → 旧行为：标记 needs_review，knowledge/ 中不动
  → 实际后果：代码已改为 DB 唯一索引，但旧知识仍在注入「用 Redis SETNX」
```

**修补——UNCERTAIN 的三级响应**：

```
级 1：即时响应——注入时附带警告标记

  知识在 knowledge/ 中不动，但注入时附带：
  
    「⚠️ 此知识的关联代码已变更，但系统无法确认是否仍然正确。
     （上次代码校验返回 UNCERTAIN，2026-06-16）
     请在使用时自行验证。」
  
  → DB 中设置 status = 'suspected_stale'（在 knowledge/ 中但状态可疑）
  → 注入时的 token 排序权重降低 20%（排在已确认的知识之后）


级 2：累积升级——同一条知识连续 UNCERTAIN

  同一条知识连续 N 次 UNCERTAIN（N 可配置，默认 3）：
    → 从 knowledge/ 移到 staging/
    → 标记 source = 'uncertain_accumulated'
    → dream 报告明确提示：
      「⚠️ 以下知识连续 3 次代码校验返回 UNCERTAIN，
       已移至 staging/ 待人工复核：
       - kw-xxx「Redis SETNX 幂等校验方案」
         关联代码：OrderService.java 已变更
         建议：手动检查代码后确认或重写」


级 3：长期未验证——UNCERTAIN + 30 天未处理

  suspected_stale 状态超过 30 天无人处理：
    → confidence_penalty = -0.25
    → 如果 confidence 跌落至 < 0.4 → 移入 staging/
    → dream 报告：「以下知识长期处于可疑状态，建议确认」
```

**🆕 V12 修补：suspected_stale 的 evidence_level 折扣**

> **漏洞**：V6 修补了 UNCERTAIN 的状态标记和注入行为，但 suspected_stale 知识的 evidence_level 未降级。一条 Level 5 的 suspected_stale 知识在仲裁时仍能以权重 1.0 参与比较，可能压制真正正确的知识。
>
> **风险量化**：R=10（概率中等 × 影响严重）。suspected_stale + Level 5 = 「看起来权威但实际上不可信」——在仲裁中会产生最危险的误导。

**场景回放**：

```
知识 A：suspected_stale, evidence_level=5, confidence=0.90
  「使用 Redis SETNX 做幂等」（实际代码已不用 Redis）
  → 得分 = 1.0 × 0.90 = 0.90

新知识 B：user_statement, evidence_level=3, confidence=0.75
  「使用 DB 唯一索引做幂等」（用户说的，还没被代码验证）
  → 得分 = 0.7 × 0.75 = 0.525

如果 A 和 B 被判定为 mutually_exclusive：
  差值 = 0.375 → A 胜出 ← 错误！
  但 A 的代码证据已经不可信了（LLM 都 UNCERTAIN 了）
```

**修补——suspected_stale 折扣系数**：

```
evidence_level 折扣规则：

  UNCERTAIN 次数         evidence_weight 折扣        相当于
  ─────────────────────────────────────────────────────────
  首次 suspected_stale    不打折（保守）               Level 5
  第 2 次 UNCERTAIN       × 0.80                      Level 4+
  第 3 次 UNCERTAIN       × 0.60                      Level 3+
  第 4+ 次 UNCERTAIN      × 0.40                      Level 2+

例：Level 5 知识第 3 次 UNCERTAIN
  → 实际 weight = 1.0 × 0.60 = 0.60（等同于 Level 4 的 weight）

第 3 次 UNCERTAIN 不仅移入 staging/，也折扣 evidence_weight。
两者互补：staging 控制注入行为，折扣控制仲裁行为。
```

**与 V11 的协同**：

```
V11 和 V12 共同处理「知识已被质疑但尚未确认」的窗口期：

  V11：INCONSISTENT → suspected_stale → 即时标记（防止注入旧知识）
  V12：suspected_stale → evidence 折扣（防止仲裁中假权威）

  两者覆盖了两个不同的使用场景：注入（V11）和仲裁（V12）
```

```
```

```
V5 和 V6 共同覆盖了「系统做了判断但人不看」的两个场景：

  V5：系统做了自动裁决（差值≥0.30）→ 人没看 → 降级
  V6：系统做了不确定判定（UNCERTAIN）→ 人没看 → 升级为 staging

  两者用的「N 次无人处理」机制是一致的——统一用 auto_adopted_unreviewed 计数器。
```

### 2.4.2 🆕 V11 修补：INCONSISTENT 时旧知识即时标记

> **漏洞**：路径② INCONSISTENT → UPDATE_CANDIDATE 被写入 staging/ 后，旧知识仍在 knowledge/ 中未被标记。在下一次 dream 执行前（可能是几小时到几天），AI 注入时仍会正常注入已过时的旧知识。
>
> **风险量化**：R=9（概率中等 × 影响可靠性）。代码行为已改变但知识未更新，这段窗口期的每次注入都是错的。

**场景回放**：

```
knowledge/限流/网关限流配置.md
  内容：「限流阈值 500 QPS」
  evidence_level=5, code_verified=1, confidence=0.85

代码变更：阈值 500 → 1000
  → LLM 语义检查：INCONSISTENT
  → UPDATE_CANDIDATE 生成：「限流阈值 1000 QPS」→ staging/
  
旧行为：旧知识不动 → 下次 dream 前仍注入「500 QPS」
新行为：旧知识立即标记 suspected_stale → 注入时附带 ⚠️ 警告
```

**修补——一行改动**：

```
INCONSISTENT 结果处理增加一步：

  INCONSISTENT → 自动生成 UPDATE_CANDIDATE → staging/
               → 旧知识 status = 'suspected_stale'
               → 注入时附带：「⚠️ 此知识对应的代码已变更，修正建议待人工确认」

这复用 V6 的 suspected_stale 标记机制，不需要新增状态码。
```

**为什么之前没发现**：V6 只修补了 UNCERTAIN 路径，遗漏了 INCONSISTENT 路径。两者都面临同一个问题——「知识已被质疑，但在人工确认前仍在正常注入」。

```
```

### 2.5 🆕 检测机制 C：假冲突过滤

这是盲区 3 的解决方案。

```
问题：cosine ≥ 0.85 但实际不矛盾

例: 「Redis 超时设为 300ms」vs「Redis 超时设为 0.3s」
    LLM 视角：单位不同但数值等价。cosine 可能 0.88。
    当前设计会标记 UPDATE_CANDIDATE，但不需要更新。

解决方案：在 LLM 判断前增加一层「规范化比较」

  对每条知识的内容做 unit normalization:
  - 时间单位统一：全部转为秒
  - 大小单位统一：全部转为字节
  - 数值格式统一：「五分钟」→「5分钟」
  
  → 规范化后如果内容一致 → 视为 EXACT_MATCH（尽管原始文本不同）
  → 进入 MD5 归一化层（§6.1 Step 4 设计）

这实际上是 MD5 归一化的增强版——在计算 MD5 之前先做语义上的内容归一化。
```

### 2.6 冲突检测的完整架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        冲突检测完整架构                               │
├──────────────┬──────────────┬────────────────┬─────────────────────┤
│   检测层       │   触发时机    │   检测范围       │   检测方法            │
├──────────────┼──────────────┼────────────────┼─────────────────────┤
│ L0: 内容哈希  │ 写入时        │ K_new vs K_all   │ MD5 (增强归一化)     │
│ L1: 语义相似  │ 写入时        │ K_new vs K_all   │ cosine similarity   │
│ L2: 矛盾判断  │ 写入时+dream  │ K_new vs K_sim   │ LLM 五分类判定（V1.4）│
│ L3: 交叉扫描  │ dream 执行    │ K_i vs K_j       │ pairwise cosine+LLM │
│              │              │ (同 domain)      │                     │
│ L4: 代码一致  │ 代码变更      │ K vs Code        │ LLM 语义对比         │
│ L5: 人工校准  │ 用户审核      │ K vs Human       │ 人工判断             │
└──────────────┴──────────────┴────────────────┴─────────────────────┘
```

---

## 第三部分：冲突解决——不只是「比 confidence」

### 3.1 当前设计的不足

```
当前 MERGE_CANDIDATE 矛盾处理：

  新旧矛盾 + 新 confidence > 旧 → 替换
  新旧矛盾 + 旧 confidence > 新 → 保留
  新旧矛盾 + confidence 接近 → 人工裁决

问题：
  1. confidence 是 LLM 自评的——不客观
  2. 没有考虑「证据质量」——代码证据 vs 口头陈述谁更可信？
  3. 没有考虑「时效性」——3 天前的知识 vs 3 个月前的知识
  4. 没有考虑「来源可信度」——code execution 的证据 vs user_statement
```

### 3.2 冲突的类型学

在解决冲突之前，先要分清楚冲突是什么类型的。不同类型的冲突需要完全不同的解决策略。

```
冲突类型分类：

类型 A: 事实冲突（Factual Contradiction）
  例: A 说「端口是 8080」, B 说「端口是 8081」
  特征: 两者不能同时为真
  策略: 需要证据仲裁——代码 > 配置 > 用户陈述 > LLM 推理
  
类型 B: 时效冲突（Temporal Conflict）
  例: A 说「v1 使用 Redis」, B 说「v2 已迁到 Kafka」
  特征: 两者在不同时间点都是正确的
  策略: 保留两者，标注适用版本范围。A 不废弃，但标记「适用 v1」

类型 C: 范围冲突（Scope Conflict）
  例: A 说「所有 API 返回 JSON」, B 说「文件下载 API 返回 Stream」
  特征: B 是 A 的特例/例外
  策略: A 补充例外说明，B 保留为独立条目。A 的 confidence 不降低。

类型 D: 粒度冲突（Granularity Conflict）
  例: A 说「缓存用 Redis」, B 说「缓存用 Redis Cluster 6.2，3 主 3 从」
  特征: B 是 A 的细化
  策略: A → deprecated (superseded_by=B)。不视为矛盾。

类型 E: 隐式冲突（Implicit Contradiction）
  例: A 说「使用乐观锁」, B 在同一场景说「使用悲观锁」
  特征: 表面上不矛盾（都是锁），但锁策略互斥
  策略: 需要 LLM 深度理解领域知识才能判断。标记人工审核。

类型 F: 人为冲突（Human Error）
  例: 用户说「这个 API 已经废弃了」但代码显示仍然在用
  特征: 知识来源冲突——人 vs 代码
  策略: 代码是 ground truth。标记 conflict_with_code，提示用户确认。
```

### 3.3 证据权重体系

判断冲突哪方正确，不能只靠 confidence。需要建立证据的可信度层级。

```
证据可信度层级（Evidence Credibility Ladder）：

Level 5: 可执行的代码事实 ──────────── 权重 1.0
  - 来源: tool_execution (成功的代码写入/运行)
  - 特征: 代码不会撒谎。如果代码说 return OrderResult，那就是 OrderResult。
  - 校验方式: 读文件验证代码存在且内容一致

Level 4: 可验证的配置/文档 ──────────── 权重 0.9
  - 来源: 项目配置文件、README、API 文档
  - 特征: 可被读取验证，但不一定是最新版本
  - 校验方式: 读文件验证内容一致

Level 3: 用户明确陈述 ──────────────── 权重 0.7
  - 来源: user_statement（用户的原话）
  - 特征: 用户可能有误，但通常知道自己在说什么
  - 校验方式: 无法直接校验——只能交叉验证

Level 2: 用户隐式推断 ──────────────── 权重 0.5
  - 来源: conversation_context（从对话中推断）
  - 特征: 用户没有明确说，但行为暗示了
  - 校验方式: 需要多个会话的交叉验证

Level 1: LLM 推理 ──────────────────── 权重 0.3
  - 来源: LLM 从代码/文档中推断的
  - 特征: LLM 可能幻觉
  - 校验方式: Step 3 代码校验是唯一防线

Level 0: 无证据 ────────────────────── 权重 0.0
  - 来源: LLM 凭空生成
  - 处理: confidence 直接打 5 折
```

#### 🆕 V1 修补：代码活性检查（防止 dead code 冒充权威）

> **漏洞**：代码证据可能是 dead code——`@Deprecated` 方法、从未被调用的类、开发分支的残骸——但它们仍然可以获得 Level 5 的证据权重，压倒正确的用户陈述。
>
> **风险量化**：R=15（概率中 × 影响严重），一旦 dead code 被当作「权威真相源」，正确的用户知识会被仲裁掉。

**检查机制**：

```
在为一条知识分配 Level 5（可执行代码事实）之前，必须验证该代码的「活性」：

活性检查项（三选一）：
  ① @Deprecated / @Obsolete / 注释标记「废弃」
     → 直接降级为 Level 2（等于用户隐式推断）
       理由：废弃代码是人留下的历史注释，不是生产环境的 ground truth

  ② 代码可达性——entry_point 指向的函数/方法在生产代码路径中被调用
     检查方式（Phase 1 简化版）：
       → grep entry_point 函数名在非测试文件中出现的次数
       → 调用次数 ≥ 1（排除自身定义） → 活代码 → Level 5 ✅
       → 调用次数 = 0 → 可能是 dead code → 降级为 Level 3（等于用户陈述）
       原因：函数存在但没有调用者，可能是未使用的工具代码
     
     Phase 2 增强（可选）：
       → 用 IDE 的 LSP 做 call hierarchy 分析
       → 判断调用链路是否可达 main/controller/handler

  ③ 代码在最近 N 天内被修改过（N 可配置，默认 90）
     → 活代码 → Level 5 ✅
     → 超过 90 天未修改 → 仍需通过可达性检查
       原因：长期未改的不一定是 dead code，但需要额外验证
```

**证据层级修正**：

```
Level 5（原）：可执行的代码事实 → 权重 1.0
Level 5（新）：活代码事实（通过活性检查）→ 权重 1.0
                └─ 未通过活性检查 → 降级为：

废弃代码 (@Deprecated/注释标记) → Level 2（权重 0.5）「历史遗留，不确定是否仍然有效」
可达性未知 (无调用者)          → Level 3（权重 0.7）「代码存在但未被调用，可能不是主路径」
```

**举例**：

```
场景：知识 A 引用 UserService.oldLogin() 作为「登录流程」的证据

活性检查：
  ① oldLogin() → 有 @Deprecated 注解 → ❌ 活性失败
  → evidence_level 降为 2（权重 0.5）
  → 加权分 = 0.5 × 0.85 = 0.425

知识 B（用户陈述）：
  evidence_level = 3（权重 0.7），confidence = 0.70
  → 加权分 = 0.7 × 0.70 = 0.49

→ B 胜出 ✅（而非靠 dead code 的 A 压倒 B）
```

**设计原则**：代码是 ground truth，但 **dead code 不是 ground truth**——它是 left truth。活性检查把「代码」细分为「活代码」和「死代码」，只有活代码有资格充当最高证据。

#### 🆕 V7 修补：配置文件的环境区分

> **漏洞**：配置文件 evidence_level 一刀切为 Level 4（权重 0.9），不区分环境。测试环境的配置和生产的配置被当做同等证据比较，可能让测试环境的错误配置压制生产环境的正确知识。
>
> **风险量化**：R=8（概率中 × 影响严重）。多环境项目（几乎全部企业级项目）必然触发此问题。

**场景回放**：
```
application.yml（默认配置）：
  port: 8888
  → evidence_level=4, weight=0.9

application-prod.yml（生产环境）：
  port: 8080
  → evidence_level=4, weight=0.9

两条配置都被采集为证据，但系统不知道哪个是生产环境。
如果 application.yml 恰好是测试环境的端口：
  → 生产环境证据和测试环境证据同级比较 → 仲裁逻辑丧失正确性
```

**修补：evidence 采集时增加 env 标识**：

```
evidence 结构扩展：

```yaml
evidence:
  source: "application-prod.yml"
  type: "config_file"
  level: 4                    # 初始分配
  env: "production"           # 🆕 环境标识
  env_confidence: 0.95        # 环境标识的可信度
```

**环境检测逻辑（Phase 1：文件名启发式）**：

```
1. 文件名模式匹配：

   application-{profile}.yml/application-{profile}.properties
   → profile 即环境：
     - prod / production / prd        → env = "production"
     - test                           → env = "test"
     - dev / development              → env = "dev"
     - 无后缀（application.yml）       → env = "unknown"

2. 环境折扣系数（env_discount）：

   | 环境         | env_discount | 说明                        |
   |-------------|:-----------:|----------------------------|
   | production  |    0.00     | 生产环境，不打折               |
   | unknown     |    0.15     | 默认配置，环境不确定，轻微打折    |
   | test        |    0.25     | 测试环境，中等打折              |
   | dev         |    0.40     | 开发环境，大幅打折              |

3. 证据权重修正：

   实际 weight = max(level_weight × (1 - env_discount), 0.30)

   例：
   - 生产配置：0.9 × (1 - 0.00) = 0.90
   - 未知配置：0.9 × (1 - 0.15) = 0.765
   - 测试配置：0.9 × (1 - 0.25) = 0.675
   - 开发配置：0.9 × (1 - 0.40) = 0.540
```

**Phase 2 增强（可选）**：

```
内容启发式（当文件名无法判断环境时）：
  - 配置中有 spring.profiles.active=prod → env="production"
  - 配置中数据库 URL 指向 test-db → env="test"
  - docker-compose.yml → env 通过文件名或内容推断
```

**设计原则**：文件在哪儿比文件写什么更诚实。Phase 1 只用文件名检测覆盖 80% 的场景（Spring Boot 约定），Phase 2 再做内容检测补全剩余 20%。

#### 证据权重的使用

```
当两条知识矛盾时，不是比 confidence，而是比 evidence_weight × confidence：

  知识 A: confidence=0.85, evidence_level=5 (代码证据)
          evidence_weight × confidence = 1.0 × 0.85 = 0.85

  知识 B: confidence=0.95, evidence_level=2 (LLM 推断)
          evidence_weight × confidence = 0.5 × 0.95 = 0.475

  → A 胜出，尽管 confidence 更低。因为 A 有代码背书。
```

### 3.4 冲突解决决策树（完整版）

```
收到冲突对 (K_A, K_B) = (旧知识, 新知识或另一条已有知识)

Step 1: 类型判断（LLM）
  ┌─ 问题：「K_A 和 K_B 的冲突属于什么类型？」
  │
  ├─ 事实冲突 → 进入 Step 2a（证据仲裁）
  ├─ 时效冲突 → 进入 Step 2b（版本标注）
  ├─ 范围冲突 → 进入 Step 2c（例外补充）
  ├─ 粒度冲突 → 进入 Step 2d（精炼取代）
  ├─ 隐式冲突 → 进入 Step 2e（人工确认）
  └─ 人为冲突 → 进入 Step 2f（代码优先）

Step 2a: 事实冲突 → 证据仲裁
  ┌─────────────────────────────────────────────┐
  │ 计算加权可信度：                              │
  │   score(K) = max_evidence_level(K) × confidence(K) │
  │                                              │
  │   score(K_A) vs score(K_B):                  │
  │    差值 ≥ 0.30 → 自动采用得分高的             │
  │    差值 0.10~0.30 → 自动采用 + 通知用户复核   │
  │    差值 < 0.10 → 人工裁决（推送给用户）        │
  │                                              │
  │  (V9: 所有阈值可配置，见 §3.4.1)              │
  │                                              │
  │  如果两条 score 都 < 0.4：                   │
  │    → 两条都标记低可信，进入 staging/ 待审核     │
  └─────────────────────────────────────────────┘

### 3.4.1 V9 修补：仲裁阈值的可配置化与数据验证

> **漏洞**：`evidence_weight × confidence` 差值 0.30 这个阈值未经任何数据验证。太松产生误判（S=5），太紧产生人工堆积。
>
> **风险量化**：R=15（概率中等 × 影响严重）。阈值是仲裁系统的「总闸」。

**阈值敏感度分析**：

```
假设实际数据差值分布：
  差值 0.00-0.10:  40% → 人工（不管阈值设多少）
  差值 0.10-0.20:  25% → 人工
  差值 0.20-0.30:  15% → 临界区（阈值设在这附近影响最大）
  差值 0.30-0.40:  12% → 阈值=0.30时自动；阈值=0.40时人工
  差值 0.40-0.50:   5% → 阈值=0.30时自动；阈值=0.50时人工
  差值 0.50+:        3% → 几乎总是自动

  阈值 0.30: 自动 20% vs 人工 80%
  阈值 0.50: 自动 3%  vs 人工 97% ← 人工堆积
  目标：自动正确率 ≥ 95% 的前提下，自动比例最大化
```

**修补——三步走**：

```
第一步：可配置化

```yaml
# config.yaml
arbitration:
  auto_adopt_threshold: 0.30    # 自动采用（可调）
  manual_review_threshold: 0.10  # 必须人工
  dual_discard_threshold: 0.40  # 双方得分都低于此 → 废弃
```

第二步：仲裁日志

每条仲裁记录写入 arbitration_log 表：
  - 旧/新知识的 evidence_level、evidence_weight、confidence、score
  - 差值、采取的 action、使用的阈值
  - 人工裁决后回填 user_decision

```python
db.insert("arbitration_log", {
    "old_id": "kw-001", "new_id": "kw-002",
    "old_score": 0.765, "new_score": 0.546,
    "difference": 0.219,
    "action": "manual_required",
    "threshold": 0.30,
    "user_decision": None  # 等人工后回填
})
```

第三步：30 天后调参

对比「如果当时自动采用会选谁」vs「用户最终选了谁」：
  - 用户选择与自动方向一致率 ≥ 95% → 阈值可下调
  - 一致率 60-80% → 阈值需上调
  - 找到让自动正确率 ≥ 95% 的最大差值阈值
```

**关键：与 V5 配套**——V9 确保阈值经验证（准入质量），V5 确保偶尔漏判有兜底（出口审计）。

Step 2b: 时效冲突 → 版本标注
  ┌─────────────────────────────────────────────┐
  │ 保留两条，在 YAML 中标注适用版本：             │
  │                                              │
  │   K_A: applicable_versions: ["v1.x"]         │
  │   K_B: applicable_versions: ["v2.x"]         │
  │                                              │
  │  在内容中自动添加版本标签：                    │
  │   K_A 末尾追加:                               │
  │     > ⚠️ 此知识适用于 v1.x。v2.x 起已迁移到    │
  │     > Kafka，详见 kw-xxx。                    │
  └─────────────────────────────────────────────┘

Step 2c: 范围冲突 → 例外补充
  ┌─────────────────────────────────────────────┐
  │ 保留 A（通用规则），补充例外说明：             │
  │                                              │
  │   A 的 YAML 新增:                             │
  │     exceptions:                              │
  │       - "文件下载 API 返回 Stream"             │
  │       - ref: kw-xxx                          │
  │                                              │
  │   B 保持不变（作为例外的独立说明）              │
  └─────────────────────────────────────────────┘

Step 2d: 粒度冲突 → 精炼取代
  ┌─────────────────────────────────────────────┐
  │ 粗粒度 → deprecated/                          │
  │   superseded_by = 细粒度.id                    │
  │                                              │
  │ 细粒度 → knowledge/                           │
  │   supersedes = 粗粒度.id                      │
  │   revision_history 记录精炼                    │
  └─────────────────────────────────────────────┘

Step 2e: 隐式冲突 → 人工确认
  ┌─────────────────────────────────────────────┐
  │ 两条都标记 conflict_with = 对方 ID             │
  │ dream 报告中高亮显示：                         │
  │   「⚠️ 隐式冲突：                                     │
  │    kw-001 说使用乐观锁，kw-002 说使用悲观锁     │
  │    两者在同一场景下互斥，请确认正确的策略。」    │
  │                                              │
  │ 用户需要手动选择一个解决方式：                  │
  │   - 保留 A，废弃 B                            │
  │   - 保留 B，废弃 A                            │
  │   - 两者各有适用场景，需要进一步细化            │
  └─────────────────────────────────────────────┘

Step 2f: 人为冲突 → 代码优先
  ┌─────────────────────────────────────────────┐
  │ 用户说「API 已废弃」但代码显示在用：           │
  │                                              │
  │   标记知识 status = 'conflict_with_code'      │
  │   提示用户：「您说 API 已废弃，但代码中仍在调用。 │
  │              是否确认？如果是，是否需要删除代码？」│
  │                                              │
  │   不自动废弃——等用户确认。                     │
  │   代码是事实，但用户可能是对的（因为代码还没改） │
  └─────────────────────────────────────────────┘
```

### 3.5 冲突解决的安全边界

```
不自动执行的操作（必须人工确认）：

✗ 废弃 code_verified=1 的知识（代码证明它是对的）
✗ 覆盖人工审核过的知识（用户确认过的，除非有新代码证据）
✗ 删除有被引用关系的知识（可能被其他知识引用）
✗ 自动合并两条 confidence 接近的矛盾知识

可以自动执行的操作：

✓ MD5 完全匹配 → 丢弃重复（零风险）
✓ 代码证据权重明显更高的 → 自动采用（误判率极低）
✓ 粒度冲突：粗 → deprecated（可追溯可恢复）
✓ 时效冲突：加版本标注（不丢信息）
✓ 范围冲突：补充例外（不丢信息）

自动执行但有通知的操作：

⚠ 证据仲裁差值 0.10~0.30 → 自动采用，但通知用户可撤销
⚠ MERGE_CANDIDATE 字段级合并 → 自动合并，但保留旧版本在 deprecated/
```

### 3.6 🆕 V5 修补：自动采用的兜底机制

> **漏洞**：证据仲裁差值 ≥ 0.30 自动采用后，通知被用户忽略。被废弃的旧知识在 deprecated/ 中 7 天自动清理。4 个月后如果发现自动采用错了，原始知识已不可恢复。
>
> **风险量化**：R=16（概率高 × 影响严重）。自动采用 + 静默通知 + 限期清理 = 错误知识的「完美消失路径」。

**场景回放**：
```
kw-001（evidence_level=4, confidence=0.85）：「限流阈值 500 QPS」
kw-002（evidence_level=5, confidence=0.82）：「限流阈值 1000 QPS」

时间推移 + 自然衰减后，差值超过 0.30 → 自动采用 kw-002：
  → 通知：「已自动采用 kw-002，kw-001 已移至 deprecated/」
  → 用户没看通知
  → 7 天后 deprecated/ 清理，kw-001 消失

2 个月后新同事问「限流阈值多少」：
  → AI 注入 kw-002（1000 QPS）
  → 但实际上 1000 QPS 是某同事随口说的，从未上线
  → 生产事故
```

**三层兜底方案**：

```
层 1：注入时附带「可信度警告」

  自动采用的知识在注入时，附带特殊标记：
  
    「⚠️ 此知识由系统自动裁决（得分差 0.31）。
     被替代的知识: kw-001（点击查看原始内容）」
  
  → 让使用者知道「这条不一定是最终真理」
  → 点击可直接查看被废的旧版本


层 2：被自动替代的知识进入 quarantined/（隔离区），而非直接进 deprecated/

  目录策略：
    ┌────────────────────────────────────────────────────────┐
    │ deprecated/    正常废弃知识，保留 7 天 → 自动清理        │
    │ quarantined/   自动裁决而被替代的知识，保留 30 天          │
    │                30 天内无人撤销 → 用户沉默 = 默认确认       │
    │                30 天后 → 移入 deprecated/（再 7 天清理）   │
    └────────────────────────────────────────────────────────┘
  
  为什么叫 quarantined/（隔离区）？—— 这些知识是被系统裁决「有罪」的，
  但还没经过人工陪审团确认。隔离观察期比普通废弃期长 4 倍。


层 3：多次无人确认 → 降级

  同一条知识被自动采用后，如果连续 N 次 dream 无人处理：
    
    第 1 次 dream：标记 auto_adopted_unreviewed = 1
    第 2 次 dream：auto_adopted_unreviewed = 2  → 移到 dream 报告顶部加闪烁
    第 3 次 dream：auto_adopted_unreviewed = 3  → 检查间接验证 → 降级或放行
  

🆕 V13 修补：层 3.1——降级前检查间接验证

> **漏洞**：V5 降级机制只看「用户是否看了 dream 报告」，不看「知识是否在系统中被间接验证」。如果自动裁决本身是对的，知识被同事代码 review 确认了，但只因无人点开 dream 报告就被降级——造成不必要的回滚。
>
> **风险量化**：R=6（概率低 × 影响中等）。间接验证不是常态，但一旦触发降级回滚正确知识，后果是信心损伤。

**场景回放**：

```
T0: 自动采用 kw-002 (Kafka, evidence_level=5, confidence=0.85)
T1: dream 1 → unreviewed = 1
T2: dream 2 → unreviewed = 2
    但同时另一位同事提交了 Kafka 配置的 PR 并得到了 review 通过
T3: dream 3 → unreviewed = 3 → 旧行为：降级！
    
但实际上 Kafka 方案是对的，只是没人看 dream 报告而已。
```

**修补——降级前检查三条间接验证信号**：

```
if auto_adopted_unreviewed >= 3:
    # 🆕 V13：检查间接验证
    indirect_checks = [
        检查 1: 同一 entry_point 的代码在过去 30 天有其他人提交过,
        检查 2: 此知识被另一个校验通过（CONSISTENT）的知识引用,
        检查 3: entry_point 代码的 git blame 显示有多人贡献过（≥2人）
    ]
    
    if any(indirect_checks):
        # 视为「沉默确认」——不降级
        kw_new.note = "自动采用后未被直接审核，但获得间接验证（检查项: X, Y）"
        kw_new.auto_adopted_unreviewed = 0  # 重置计数器
        kw_new.status = "active"             # 恢复正常状态
    else:
        # 真正降级——既无人看，也无间接验证
        kw_new.confidence -= 0.15
        kw_old.status = "revived"
        dream_report.priority_alert("自动采用已降级，请人工确认")
```

**间接验证信号的可靠性**：

| 检查项 | 信号强度 | 说明 |
|--------|:-------:|------|
| entry_point 有人提交 | 中等 | 代码还在活跃中，间接佐证正在使用 |
| 被 CONSISTENT 知识引用 | 强 | 另一个通过代码校验的知识交叉验证了它 |
| git blame ≥ 2人 | 弱 | 多人关注但未必是确认 |

任一信号触发即放行。保守策略：多放行少误伤。

```
```

**修补后的 3.5 安全边界增加**：
```
可以自动执行但有保护的操作：

✓ 证据仲裁差值 ≥ 0.30 → 自动采用
   ├─ 被废知识 → quarantined/（非 deprecated/）
   ├─ 注入时附带 warning 标记
   └─ N 次无人确认 → 降级

✓ 证据仲裁差值 0.10~0.30 → 自动采用 + 通知可撤销
   └─ 同上三层保护
```

---

## 第四部分：知识更新的安全性

### 4.1 更新 ≠ 覆盖

```
错误做法：直接修改 knowledge/ 下的 MD 文件
  → 如果改错了，旧版本丢失，无法恢复

正确做法：保留修订链

  每次更新：
    1. 旧版本 → deprecated/<旧文件名>_v<N>.md
    2. 新版本 → staging/ 或 knowledge/（根据 confidence）
    3. DB 中旧记录 status → 'superseded', successor_id → 新记录 ID
    4. DB 中新记录 supersedes → 旧记录 ID, revision → 旧 revision + 1

  回滚：
    用户执行 dev-context-memo-dream --rollback kw-xxx
    → 找到 superseded 的旧记录
    → 旧记录 status → 'valid'，新记录 → 'superseded'
    → 文件也反向移动
```

### 4.2 更新操作的原子性

```
知识更新的 ACID 要求：

Atomicity:
  MD 文件移动 + DB 状态更新 必须在同一个事务边界内
  → 先更新 DB（事务性），再移动文件
  → 文件移动失败 → DB 回滚
  → DB 更新失败 → 文件不移动

Consistency:
  更新后 DB 中的 file_path 必须指向实际文件位置
  superseded 链不能形成循环
  → 更新前校验 file_path 存在
  → 更新后校验 superseded 链无环

Isolation:
  同一时间只有一个 dream 进程在运行
  → 用文件锁 .devContextMemo/.dream.lock 防止并发

Durability:
  更新结果必须持久化
  → DB 写入后 fsync
  → 文件 rename 后确保父目录 sync
```

### 4.3 更新影响分析

```
当一条知识被更新时，需要检查：

1. 被引用关系：
   - 其他知识是否引用了被更新的这条？
   → 查询 DB: SELECT * FROM knowledge_index WHERE references @> kw-xxx
   → 如果有引用者 → 提示用户：「以下知识引用了被更新的内容，可能需要同步更新」

2. 领域影响：
   - 同一 domain 下是否有相关知识可能受影响？
   → 对同 domain 知识重新计算 cosine 相似度
   → 高相似度的标记「可能受此更新影响」

3. 入口点影响：
   - 知识的 entry_point 是否仍然有效？
   → 检查 entry_point 指向的代码文件是否存在
   → 如果文件被删除 → 标记 entry_point 失效
```

---

## 第五部分：决策点汇总

### 需要你确认的核心决策

#### 决策组 A：更新路径（新增）✅ 已确认

| # | 决策点 | 状态 | 修正说明 |
|:--:|--------|:---:|------|
| A1 | 路径②代码变更后的 LLM 语义一致性检查？ | ✅ 通过 | 🆕 V1.6：UNCERTAIN 多层次兜底——suspected_stale + 累积升级（V6）；🆕 V1.7：INCONSISTENT 时旧知识即时标记（V11）；suspected_stale 的 evidence 折扣（V12） |
| A2 | 路径③用户手动纠错：保留旧版本 + 创建修正版本（不直接修改）？ | ✅ 通过 | **修正**：① 支持 `dream --fix` 命令修改 ② dream 执行时检测手动修改（hash 不匹配 → git diff 摘要 → 用户确认） |
| A3 | 路径⑥精炼取代：新知识是旧知识的更精确版本时，旧→deprecated？ | ✅ 通过 | — |
| A4 | 路径⑤自然过时：confidence 跌落至 <0.6 时主动提示用户？ | ✅ 通过 | **修正**：阈值可配置（config.yaml），Phase 1 只 flag 不自动操作。code_verified=1 保护冷知识 |

#### 决策组 B：冲突检测（新增）✅ 已确认

| # | 决策点 | 状态 | 修正说明 |
|:--:|--------|:---:|------|
| B1 | dream 执行时对已有知识做交叉扫描？ | ✅ 通过 | **修正**：扫描范围——共享 entry_point / topic / cosine ≥ 0.95 / concept_tags(≥2个+cosine≥0.75) / 人工标记。🆕 V1.4 新增 concept_tags 条件（V2）；🆕 V1.6 字段合并增加语义消歧（V10，复用 concept_tags） |
| B2 | 代码变更后做 LLM 语义一致性检查（而非只看 MD5）？ | ✅ 通过 | — |
| B3 | 增强内容归一化（时间/大小单位统一）以过滤假冲突？ | ✅ 通过 | — |

#### 决策组 C：冲突解决（新增）✅ 已确认

| # | 决策点 | 状态 |
|:--:|--------|:---:|
| C1 | 引入证据可信度层级（代码 > 配置 > 用户陈述 > LLM 推理）？ | ✅ 通过 | 🆕 V1.5：代码活性检查（dead code 降级）；🆕 V1.6：配置文件环境区分（env discount） |
| C2 | 冲突类型分类（事实/时效/范围/粒度/隐式/人为）各走不同策略？ | ✅ 通过 |
| C3 | 证据仲裁差值 ≥0.30 自动采用，<0.10 人工裁决？ | ✅ 通过 | 🆕 V1.6：阈值可配置化 + 仲裁日志 + 30 天调参（V9）；自动采用兜底 quarantined/ + 降级（V5）；🆕 V1.7：降级前间接验证检查（V13） |
| C4 | 代码证据优先于用户陈述（冲突时标 conflict_with_code 等确认）？ | ✅ 通过 |

#### 决策组 D：更新安全（新增）✅ 已确认

| # | 决策点 | 状态 |
|:--:|--------|:---:|
| D1 | 每次更新保留旧版本在 deprecated/（修订链）？ | ✅ 通过 |
| D2 | dream 执行时加文件锁防并发？ | ✅ 通过 |
| D3 | 更新后检查被引用关系并提示受影响的知识？ | ✅ 通过（Phase 1 只检测+提示，不自动联动） |

### 暂缓决策

| # | 内容 | 理由 |
|:--:|------|------|
| — | 路径⑦上下文环境变化的自动处理 | Phase 2 |
| — | Phase 2.5 pairwise 扫描的完整性能优化 | Phase 1 先用限制策略，Phase 2 优化 |
| — | 证据权重的具体数值校准 | 需要实际运行后根据误判率调参 |

### 新增决策（V1.3）✅ 已确认

| # | 决策点 | 状态 |
|:--:|--------|:---:|
| E1 | YAML frontmatter 合并后由 dream 强制重算 | ✅ 通过 |
| E2 | 新增 `dream --reconcile` 子命令处理正文冲突 | ✅ 通过 | 🆕 V1.5 修补：增加合并后校验层——对抗性 LLM 审查 auto_mergeable 结果，校验失败降级为 manual_required |
| E3 | 冲突无法自动合并时保留两条到 staging/ | ✅ 通过 |

---

## 第五部分：多人协作场景——Git 知识合并冲突（V1.3 新增）

> **触发**：用户提出——「A 研发在自己电脑上沉淀的知识通过 Git 提交到仓库。B 研发更新。A 和 B 都改了同一个内容，如何解决冲突？」

### 5.1 问题还原

```
时间线：

  A 的机器                          B 的机器
  ─────────                        ─────────
  dream 执行                        dream 执行
  → 更新 knowledge/订单/幂等.md      → 更新 knowledge/订单/幂等.md
  → 改端口 8080→8081                → 改重试次数 3→5
  → git commit & push ✅            → git commit
                                    → git pull ← 💥 冲突！
```

这是 Git 同仓管理的必然结果：知识文件和人一样，多人并行修改同一个文件就会冲突。问题不复杂，但处理不好会导致知识破损。

### 5.2 分层解决方案

不引入重量级机制（如 CRDT），用 Git 原生能力 + dream 智能辅助，分三层处理。

#### 5.2.1 第一层：Git 的自然合并

Git 的三路合并对 Markdown 按行处理。如果两人改的是不同段落，Git 能自动合并，无需人工介入。

```
A 改的是第 12 行：port: 8081
B 改的是第 25 行：retry: 5

→ Git 自动合并成功 ✅（无冲突标记）
→ 合并后的文件需要 dream 做一次完整性校验
```

**当前设计的保护**：dream 执行时检测 hash 不匹配（这就是 A2 中设计的完整性校验），发现文件被合并过 → 提示用户确认 → 更新 DB。

#### 5.2.2 第二层：YAML Frontmatter 的合并规则

即使正文没有冲突，YAML frontmatter 也一定冲突——两个人都改了同一个文件，revision_history、version、modified_at 必然不同。

Git 对 YAML 的处理是按行文本合并，可能产生三种结果：

| 情况 | Git 表现 | 后果 |
|------|---------|------|
| **A 加了一行 revision，B 加了一行** | 自动合并（不同行） ✅ | 两行都保留，但 version 可能乱 |
| **A 和 B 改了同一行 version** | 冲突标记 `<<<<<<<` | 需要人工解决 |
| **两人改了 YAML 不同字段** | 自动合并 ⚠️ | Git 认为没冲突，但语义可能错 |

**设计**：无论 Git 是否报告冲突，dream 在检测到文件 hash 变化后，强制重新计算 YAML frontmatter：

```yaml
# 合并后的 YAML frontmatter（由 dream 重新生成）

revision_history:
  - version: 3                    # 合并后的版本：max(A.v, B.v) + 1
    date: 2026-06-16
    action: merged
    change: "合并 A 的修改（端口 8080→8081）和 B 的修改（重试次数 3→5）"
    merged_from: [2a, 2b]        # 指向两个来源版本

  - version: 2a                   # A 的修改
    date: 2026-06-16
    action: update
    change: "端口号从 8080 改为 8081"
    author: A

  - version: 2b                   # B 的修改
    date: 2026-06-16
    action: update
    change: "重试次数从 3 改为 5"
    author: B

  - version: 1
    date: 2026-06-10
    action: create
    change: "初始创建"

confidence: 0.86                  # max(A.confidence, B.confidence)
                                  # 理由：两人都确认了，取更高值是保守策略
modified_at: 2026-06-16T15:30:00
content_hash: <重新计算>
```

**关键规则**：

| 字段 | 合并策略 | 理由 |
|------|---------|------|
| `version` | `max(A.v, B.v) + 1` | 单调递增，不丢失版本 |
| `revision_history` | 合并两列表，去重，追加 merge 条目 | 完整追溯 |
| `confidence` | `max(A.c, B.c)` | 保守——至少有一人确认过 |
| `evidence_level` | `max(A.e, B.e)` | 保留最高证据等级 |
| `entry_points` | 合并去重 | 两人的代码锚点都保留 |
| `content_hash` | 重新计算 | 必须和合并后的文件一致 |

#### 5.2.3 第三层：正文冲突 → LLM 辅助合并

当 A 和 B 改了同一段内容（Git 标记了 `<<<<<<<` 冲突），需要语义级合并。

```
Git 冲突标记：

<<<<<<< HEAD (A 的版本)
## 解决方案
使用 Redis SETNX 实现分布式锁，超时 30 秒。
=======
## 解决方案
使用数据库唯一索引实现幂等校验，无需 Redis。
>>>>>>> origin/main (B 的版本)
```

**这种情况不能靠 YAML 规则自动处理——A 和 B 的方案完全互斥。** dream 提供 `--reconcile` 模式：

```bash
# B 在自己的机器上执行
dev-context-memo-dream --reconcile knowledge/订单/幂等校验方案.md
```

**reconcile 流程**：

```
1. 识别 Git 冲突标记，提取三个版本：
   - base: 共同祖先（git merge-base）
   - ours: 当前分支的版本（A）
   - theirs: 合并进来的版本（B）

2. 提取两份修改摘要（每人改了什么）：
   A: [端口号 8080→8081] + [方案从 Redis SETNX 改为数据库唯一索引]
   B: [重试次数 3→5]

3. LLM 分析冲突性质：
   
   输入：base / ours / theirs 三版内容 + 两份修改摘要
   提示：「以下是同一知识文件的两个并行修改版本。
         A 的修改：{A_changes}
         B 的修改：{B_changes}
         
         请判断：
         1. 两人的修改是否存在实质性矛盾？
         2. 如果矛盾，哪方的方案有更强的证据支撑？
         3. 如果不矛盾，如何合并两份修改？
         
         注意：如果 A 和 B 的方案在逻辑上互斥，不要强行合并，
         应标记为需要人工裁决。」
   
   输出：
   {
     "conflict_type": "factual_conflict",    // 或 "independent"（独立修改）
     "verdict": "manual_required",            // 或 "auto_mergeable"
     "suggested_resolution": "A 和 B 的幂等方案完全互斥（Redis vs 数据库）。
                             建议保留两条为独立方案，等待人工选择。",
     "merged_content": null                   // 不可自动合并时为 null
   }

4. 根据 LLM 判断结果：
   ┌─────────────────────────────────────────────────────┐
   │ verdict = "auto_mergeable"                          │
   │ → 生成合并版本，写入 knowledge/                       │
   │ → 旧版 → deprecated/                                │
   │                                                     │
   │ verdict = "manual_required"                         │
   │ → 保留冲突标记在文件中，但增强标记：                    │
   │                                                     │
   │   <<<<<<< A 的方案（代码证据: OrderService.java,       │
   │           evidence_level=5, confidence=0.78）         │
   │   使用 Redis SETNX 实现分布式锁                       │
   │   =======                                            │
   │   使用数据库唯一索引实现幂等校验                        │
   │   >>>>>>> B 的方案（用户陈述,                          │
   │           evidence_level=3, confidence=0.82）         │
   │                                                     │
   │   → 同时写入 staging/ 一条待裁决记录                   │
   │   → dream 报告中高亮提示                               │
   └─────────────────────────────────────────────────────┘

5. 🆕 V4 修补：合并后校验层（auto_mergeable 时强制执行）

   > **漏洞**：当 verdict = auto_mergeable 时，LLM 直接产出 merged_content 并写入 knowledge/。
   > 但 LLM 可能拼接出「语法正确、逻辑矛盾」的混合方案——
   > 例如 A 说读副本用 PostgreSQL、B 说读副本用 MySQL，
   > LLM 可能在合并时把两者都写上：「读副本：PostgreSQL 和 MySQL（双活）」——
   > 这在代码里可能根本不可行。
   > 
   > **风险量化**：R=15（概率中 × 影响严重），错误合并一旦写入 knowledge/ 就成为「权威知识」，
   > 后续所有引用它的知识都会被污染。

   **校验流程**：

   ```
   当 verdict = auto_mergeable 时，不直接写入。增加一步：

   a. 将 merged_content 和一个反向 prompt 一起送给 LLM：

      「以下是一份合并后的知识文档。
       请扮演一个挑剔的审查者，找出其中所有潜在问题：
       1. 是否存在自相矛盾的描述？（两个地方说了相反的话）
       2. 是否存在与原始两份修改冲突的内容？
          A 的原始修改：{A_changes}
          B 的原始修改：{B_changes}
       3. 是否存在不可行的组合？
          （如同时用两个互斥的中间件做同一件事）
       4. 合并结果是否遗漏了任一方的有效信息？

       如果发现任何问题，输出具体的问题描述。
       如果完全没问题，输出 "PASS"。」

   b. 根据校验结果：

      ┌─────────────────────────────────────────────────┐
      │ 校验返回 "PASS" →                                  │
      │   ✅ merged_content 写入 knowledge/                │
      │   ✅ 旧版 → deprecated/                            │
      │                                                   │
      │ 校验发现问题（如自相矛盾/丢失信息）→                 │
      │   ⚠️ 不自动写入                                     │
      │   → 标注校验发现的问题                               │
      │   → 降级为 manual_required                         │
      │   → 增强 Git 冲突标记（附校验发现的问题）              │
      │   → 两条原始方案写入 staging/                        │
      │   → dream 报告高亮提示：                             │
      │      「⚠️ A 和 B 的方案自动合并失败。                  │
      │       校验发现问题：合并方案声称同时用 PG 和 MySQL     │
      │       做读副本（双活），但在同一代码路径中不可行。」     │
      └─────────────────────────────────────────────────┘

   c. 校验失败后的 fallback 策略：

      不重试（反复重试 LLM 不会产生更好的结果）。
      直接降级为 manual_required——两个原始方案写入 staging/，
      等人工裁决。
   ```

   **关键设计**：
   - 校验不是简单重跑一次合并——是用一个**对抗性角色**（挑剔的审查者）去挑战合并结果
   - 校验失败 = 自动合并不可信 = 推人工（绝不强行写入）
   - 这比「不做校验直接写入」多了 1 次 LLM 调用的成本，但换来了「不会把逻辑矛盾写入知识库」的安全保障
```

**关键设计**：LLM 不替人做最终决定。当两人方案互斥时，增强 Git 冲突标记（附上证据来源），让人做出知情决策。

### 5.3 为什么不引入 CRDT

| 维度 | CRDT | Git + dream reconcile |
|------|------|----------------------|
| 适用场景 | 实时多人协同编辑 | 偶尔的 Git 合并冲突（异步） |
| 复杂度 | 需要 Yjs/Automerge 类库，100-200KB | 零依赖，用 Git 已有能力 |
| 元数据开销 | 实际数据的 2-3 倍 | 仅 YAML 几行 |
| 墓碑问题 | 大量编辑后文件膨胀 | 不存在（Git 历史管理） |
| 冲突解决 | 自动合并（数学规则） | LLM 增强 + 人工裁决 |
| 适合 devContextMemo？ | ❌ 太重 | ✅ 精准匹配需求 |

devContextMemo 不是 Google Docs——不是两个人同时编辑同一行。冲突是偶发的、异步的，Git 的三路合并 + dream 的智能辅助足以应对。

### 5.4 决策组 E：多人协作（V1.3 新增，待确认）

| # | 决策点 | 建议 |
|:--:|--------|------|
| **E1** | YAML frontmatter 在合并后由 dream 强制重算（而非信任 Git 文本合并）？ | ✅ 推荐——Git 不理解 YAML 语义，dream 必须兜底 |
| **E2** | 新增 `dream --reconcile` 子命令处理正文冲突，LLM 辅助但不自动裁决？ | ✅ 推荐——LLM 分析 + 增强标记 + 人工拍板 |
| **E3** | 冲突无法自动合并时，保留两条方案到 staging/，由人工选择？ | ✅ 推荐——不被自动合并掩盖矛盾 |

---

## 附录 A：同类系统参考

| 系统 | 冲突检测机制 | 解决策略 | 参考价值 |
|------|------------|---------|:------:|
| **Git merge** | 三路合并——base vs ours vs theirs，逐行 diff | 自动合并无冲突行，冲突行标记 `<<<<<<<` 让人解决 | ⭐⭐⭐ 三路合并思想可借鉴到知识合并 |
| **Google Knowledge Graph** | 多源冲突——sameAs 关系 + 置信度评分 | 以最多权威来源一致的信息为准，低置信的保留为备选 | ⭐⭐ 多源仲裁 |
| **Wikipedia** | 编辑冲突——同一段落被两人修改 | 后提交者看到冲突页面，手动选择保留哪个版本 | ⭐⭐ 人工裁决最后防线 |
| **CouchDB** | MVCC——每次写带 `_rev`，冲突时保留所有版本 | 应用层选择 winner，但所有版本保留可查 | ⭐⭐⭐ 多版本并发控制 = 我们的修订链 |
| **CRDT (Conflict-free Replicated Data Types)** | 数据结构自带合并规则（如 Last-Write-Wins Register） | 自动合并，不需要冲突检测 | ⭐⭐ LWW Register 思路：代码证据 = last write |

## 附录 B：本设计对现有文档的影响

如果上述决策通过，需要更新以下文件：

| 文件 | 更新内容 |
|------|---------|
| Step 3（验证层） | 代码变更检测从「MD5 → failed」改为「MD5 → LLM 语义一致性检查 → CONSISTENT/INCONSISTENT/UNCERTAIN」 |
| Step 4（去重层） | 新增内容归一化（L0.5）层；新增 PRECISION_UPGRADE 动作类型；新增 concept_tags 条件（修补 V2）|
| Step 5（写入层） | 新增用户手动纠错路径（路径③）；新增修订链机制；UNCERTAIN 兜底标记（修补 V6）|
| Step 6（巩固层） | 新增 Phase 2.5 交叉扫描（含 concept_tags 扩展条件）；新增冲突类型分发逻辑；新增更新影响分析；自动采用降级机制（修补 V5）|
| 主流水线文档 | 新增「证据可信度体系」章节（含代码活性检查，修补 V1）；新增「冲突解决决策树」章节 |
| SQLite Schema | 新增字段：superseded_by / successor_id / conflict_with / evidence_level / code_active / concept_tags |
| --reconcile | 新增合并后校验层（修补 V4）|

## 附录 C：审核发现（2026-06-16）

> 详见 `devContextMemo-知识保真体系-审核报告-V1.0.md`

**P0 必须修补（4 项）**：
1. V1：代码证据活性检查——识别 dead code（R=15）
2. V2：交叉扫描增加 concept_tags 条件（R=16）
3. V3：LLM 矛盾判断增加中间分类 compatible_with_condition
4. V4：--reconcile 增加合并后校验层（R=15）
