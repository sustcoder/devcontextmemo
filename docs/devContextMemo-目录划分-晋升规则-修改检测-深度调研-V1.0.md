# devContextMemo 深度调研：目录划分 · 晋升规则 · 知识修改检测

> **触发**：用户推翻状态字段方案，改为物理目录 + 晋升规则漏洞审查 + 修改场景全链路设计
> **原则**：第一性原理出发，不拘泥于已有设计；真实调研同类方案并引证；结果存档
> **日期**：2026-06-16
> **版本**：V1.1（+ 第四部分：时间衰减冷知识保护 + staging→knowledge 晋升触发流程）

---

## 第一部分：知识库物理目录划分方案

### 1.1 用户需求翻译

> 「改为通过文件夹去区分，这样在人工审核的时候可以快速的找到需要查看的文件夹」

核心约束：**人眼扫一眼目录结构，就知道该去哪个文件夹干活**。不允许通过读 YAML frontmatter 来定位。

### 1.2 调研：同类系统的目录划分惯例

| 系统 | 目录结构 | 划分逻辑 | 参考价值 |
|------|---------|---------|:------:|
| **Git** | `working-tree/` → `staging-area/` → `.git/objects/` | 物理隔离三种状态：未追踪、暂存、已提交 | ⭐⭐⭐ 暂存区概念 |
| **Jekyll** | `_drafts/` vs `_posts/` | 物理隔离草稿和已发布内容 | ⭐⭐ 草稿/已发布二分 |
| **Hugo** | 全部在 `content/`，靠 `draft: true` | 单一目录 + 元数据 | ⭐（用户已否决） |
| **WordPress** | `wp_post_status` 字段（draft/pending/publish/trash） | 数据库字段 | ⭐（用户已否决） |
| **Obsidian** | 用户自定义文件夹，无强制生命周期 | 完全自由 | ⭐ 灵活但无约束 |
| **Notion** | 数据库属性 `Status` 驱动视图过滤 | 逻辑视图而非物理目录 | ⭐（用户已否决） |
| **Aether 内容审核** | 无目录概念（内存状态机），但状态流转清晰：Pending → Scanning → Decision → AutoApproved/InReview/Rejected | 状态驱动而非目录驱动 | ⭐⭐⭐ 状态机参考 |

> **参考源**：Aether content moderation pipeline（`github.com/rhoninl/Aether/blob/main/docs/design/content-moderation-pipeline.md`，CC0 许可）

### 1.3 从第一性原理推导

**知识的本质状态只有三种**：

| 状态 | 本质 | 人需要做什么 | 自动化能做什么 |
|------|------|-------------|--------------|
| **待确认** | 「我还不确定这条知识对不对」 | **人工审核**（核心使用场景） | 自动排序（按 confidence）、自动标记相似条目 |
| **已采纳** | 「这条知识是正确的，可以用」 | 偶尔浏览、修改 | 自动注入上下文、自动校准 |
| **已废弃** | 「这条知识曾经对，现在不对了」 | 确认删除、恢复误删 | 自动触发（代码变更校验失败）、自动归档 |

**三态 = 三目录**。这就是最小完备集合——不需要第四个。

### 1.4 建议方案：三目录结构

```
.devContextMemo/
├── staging/                    ← 🔴 待确认：需要人工审核的知识
│   ├── 20260616-订单幂等校验方案.md
│   ├── 20260616-限流策略设计.md
│   └── 20260615-N+1查询优化规范.md
│
├── knowledge/                  ← 🟢 已采纳：活跃使用的知识
│   ├── 订单/
│   │   ├── 订单状态机设计.md
│   │   └── 幂等校验方案.md       ← 从 staging 晋升来的
│   ├── 支付/
│   │   └── 回调处理规范.md
│   ├── 架构/
│   │   └── 微服务拆分原则.md
│   └── 规范/
│       └── API命名约定.md
│
└── deprecated/                 ← ⚫ 已废弃：曾经有效但已过时
    └── 旧版缓存策略.md
```

### 1.5 三个目录的生命周期流转

```
                    Step 5 写入
                         │
                         ▼
              ┌─────────────────┐
              │    staging/     │  ← 所有新知识都先到这里
              │  (confidence    │
              │   0.6 ~ 1.0)    │
              └───────┬─────────┘
                      │
          ┌───────────┼───────────┐
          │           │           │
    confidence≥0.85   │    confidence<0.6
    AND used≥10       │    AND age>30d
    (Step6 自动)      │    AND used=0
          │           │           │
          ▼           ▼           ▼
   ┌──────────┐  人工审核    ┌──────────┐
   │knowledge/│  (devContextMemo       │ 删除     │
   │  自动晋升 │   review)    │ (静默)   │
   └────┬─────┘      │       └──────────┘
        │       ┌────┴────┐
        │       │         │
        │    接受 ✅   拒绝 ❌
        │       │         │
        │       ▼         ▼
        │  knowledge/   删除
        │  (人工采纳)   (或保留在
        │              deprecated/)
        │
        │  代码变更校验失败 (Step 3)
        │  或 Step 6 修剪
        │
        ▼
   ┌──────────┐
   │deprecated/│  ← 人工可恢复 → staging/
   └──────────┘
```

### 1.6 staging/ 的文件命名

> 为什么用日期前缀而不是标题？因为 staging 是临时的，日期前缀方便按时间排序，快速找到「今天新产生的」知识。

```
staging/20260616-订单幂等校验方案.md
staging/20260616-限流策略设计.md
staging/20260615-N+1查询优化规范.md
```

晋升到 knowledge/ 后去掉日期前缀：

```
knowledge/订单/幂等校验方案.md
```

### 1.7 knowledge/ 的子目录组织

按领域（domain）分，对应我们需求文档中的「领域层次化树」：

```
knowledge/
├── 架构/       ← 系统架构、技术选型
├── 订单/       ← 订单域
├── 支付/       ← 支付域
├── 规范/       ← 编码规范、API 约定
├── 安全/       ← 安全策略
└── 运维/       ← 部署、监控
```

领域由 Step 2（LLM 提炼）自动分类，人可以在 `dev review` 时修正。

### 1.8 对比：三目录 vs 四/五目录

| 方案 | 目录数 | 目录列表 | 人找起来复杂度 | 推荐 |
|:----:|:-----:|---------|:------------:|:---:|
| **三目录** | 3 | staging / knowledge / deprecated | ⭐ 一眼看到 staging → 知道去哪审核 | ✅ |
| 四目录 | 4 | draft / staging / knowledge / deprecated | ⭐⭐ draft vs staging 区别模糊 | ❌ |
| 五目录 | 5 | draft / staging / verified / mature / deprecated | ⭐⭐⭐ 太多，需要读文档才能理解 | ❌ |

> **结论**：三目录是物理目录区分方案的最小完备集合。多于三个会造成人的认知负担（「draft 和 staging 有什么区别？」），少于三个无法区分生命周期。

### 1.9 需要你确认

| # | 决策点 | 建议 |
|:--:|--------|------|
| 1 | 三目录（staging / knowledge / deprecated）？ | ✅ 推荐 |
| 2 | staging 文件用日期前缀命名？ | ✅ 推荐 |
| 3 | knowledge/ 子目录按领域（domain）分？ | ✅ 推荐 |
| 4 | 拒绝的知识保留还是直接删除？ | 建议保留 7 天再清理（防误删） |

---

## 第二部分：晋升规则的漏洞分析与加固

### 2.1 当前晋升规则回顾

```
当前设计（Step 6 巩固层）:

晋升为 mature:
  条件: used_count ≥ 10 AND confidence ≥ 0.85

降级为 deprecated:
  条件: 代码变更校验失败 (Step 3) OR used_count=0 AND age > 30d

人工审核 (pending_review):
  条件: 0.6 ≤ confidence < 0.85
```

### 2.2 第一性原理分析：what could go wrong?

**漏洞 1：自信度通胀（Confidence Inflation）**

LLM 输出的 confidence 分数没有校准基准。如果 LLM 倾向打高分（比如 80% 的知识都给 0.9+），那 `confidence ≥ 0.85` 这道门槛形同虚设。

> **参考**：Aether 内容审核管道的做法——Auto-Approve 要求「高置信度 AND Clean」双重条件，且 `DecisionEngine` 的阈值可配置。我们的 confidence 也应该有**外部验证**（Step 3 代码校验的结果）来修正。

**漏洞 2：used_count 悖论（用户已指出）**

错误知识可能被频繁检索（因为匹配了常见查询模式），used_count 反而更高。这是 `used_count` 作为质量指标的根本缺陷。

> **参考**：YouTube 推荐系统不只用点击次数，而是用**观看时长**（implicit feedback）作为更强的信号。对应到我们：应该用「知识被注入后用户是否修正了它」作为反向信号。

**漏洞 3：冷启动死锁**

新知识 used_count=0，永远无法自动晋升到 mature。即使 confidence=0.95 的完美知识，也要等被检索 10 次。

> **修复**：加一条「confidence ≥ 0.95 → 直接晋升」的绿色通道。

**漏洞 4：回音室效应**

一条知识被晋升到 mature → 注入上下文更频繁 → used_count 增长更快 → 更难被修剪 → 即使后来被证明错误，它仍然霸占着 mature 状态。

> **修复**：mature 知识仍然需要定期重新校验（Step 3 代码校验不是一次性的）。每次关联代码变更时，mature 知识的 confidence 应该被重新评估。

**漏洞 5：时间衰减缺失**

知识在创建时正确，但 6 个月后可能过时。当前设计用 `last_used_at` 做修剪，但没有主动衰减 `confidence`。

> **参考**：Bloomfire KM Cycle 中的「Knowledge Maintenance」阶段——知识需要定期重新验证。对应到我们：超过 90 天未校验的 mature 知识，confidence 应自动打折（×0.9）直到下次校验通过。

**漏洞 6：信号单一**

只用 `used_count` + `confidence` 两个信号。缺少：
- **修改频率**：被校准引擎修正过多少次？
- **冲突次数**：被其他知识挑战过多少次？
- **来源质量**：来自 code review 还是闲聊？

> **参考**：Elasticsearch 的 `_score` 不是单一信号，而是 TF-IDF + field length norm + boost 的乘积。我们的晋升评分也应该是多信号加权。

### 2.3 加固方案：多信号晋升评分

```
晋升评分 = (confidence × 0.4)                             # LLM 原始信心
         + (min(used_count / 10, 1.0) × 0.2)             # 使用频率（封顶）
         + (code_verified × 0.2)                          # 代码校验（0 或 1）
         + (1.0 - min(correction_count / 3, 1.0) × 0.1)  # 修正惩罚（被修正越多越扣分）
         - (time_decay × 0.1)                             # 时间衰减（>90天未校验开始扣分）

晋升阈值:
  评分 ≥ 0.80  →  自动晋升到 knowledge/
  0.50 ≤ 评分 < 0.80  →  留在 staging/，等人审核
  评分 < 0.50  →  标记为高风险，优先人工审核
```

### 2.4 新字段

需要在 `knowledge_index` 表新增：

| 字段 | 类型 | 说明 |
|------|------|------|
| `correction_count` | INT DEFAULT 0 | 被校准引擎修正的次数（反向质量信号） |
| `last_verified_at` | TIMESTAMP | 最后一次代码校验通过的时间 |
| `code_verified` | BOOLEAN DEFAULT 0 | 当前代码校验状态（关联代码未变更=1） |
| `promotion_score` | FLOAT | 综合晋升评分（每次 Step 6 运行时重新计算） |

### 2.5 新增的自动操作

| 操作 | 触发条件 | 动作 |
|------|---------|------|
| 🟢 **快速晋升** | confidence ≥ 0.95（跳过 used_count 门槛） | staging/ → knowledge/ |
| 🔵 **自动晋升** | 评分 ≥ 0.80 | staging/ → knowledge/ |
| 🟡 **置信度衰减** | last_verified_at > 90 天（mature 知识也衰减） | confidence × 0.9 |
| 🔴 **主动降级** | 代码变更校验失败 | knowledge/ → deprecated/ |
| 🔴 **低质清理** | confidence < 0.6 AND used_count=0 AND age > 30d | 删除 |

### 2.6 需要你确认

| # | 决策点 | 建议 |
|:--:|--------|------|
| 1 | 引入多信号评分替代纯 used_count+confidence？ | ✅ 推荐 |
| 2 | 新字段（correction_count / last_verified_at / code_verified / promotion_score）？ | ✅ 推荐 |
| 3 | 绿色通道：confidence≥0.95 直接晋升？ | ✅ 推荐 |
| 4 | 90 天未校验的 mature 知识 confidence 打折？ | ✅ 推荐 |

---

## 第三部分：知识修改场景——如何判别？如何更新 MD？

### 3.1 问题定义

当一条「新提取的知识候选」进入 Step 4（去重层）时，系统需要回答：

> 这条知识是**全新的**，还是**对已有一条知识的修改/更新**？

如果是修改，需要回答子问题：
- 修改了哪个已有条目？
- 修改了什么内容？
- MD 文件如何更新？（全量重写？字段级合并？）

### 3.2 调研：同类系统如何处理「修改检测」

| 系统 | 如何判别是修改 | 如何更新文件 | 参考价值 |
|------|--------------|-------------|:------:|
| **Git** | 内容寻址——同一路径+内容 SHA 不同 = 修改。`git diff` 找变更范围 | 全量重写 blob，用 tree diff 展示变更 | ⭐⭐⭐ 内容寻址 |
| **OpenViking** | URI 匹配——读磁盘上已存在的文件，如果存在 = 修改。`is_edit()` 标记 | **全量重写**——读取旧文件 → 按 `merge_op` 逐字段合并 → 写回完整内容。系统管理的字段（created_at 等）自动保留 | ⭐⭐⭐ 字段级合并 |
| **Wikipedia** | 页面标题匹配——同一标题的新编辑 = 修订版本（revision）。存储完整 diff | 保存完整修订历史，当前版本 = 应用所有 diff 后的结果 | ⭐⭐ 修订历史 |
| **Notion** | 同一 `page_id` 的新写入 = 修改 | Block 级增量更新 | ⭐ 粒度太细 |
| **Obsidian** | 同一文件路径 = 同一笔记 | 全量覆盖（用户手动或用插件自动合并） | ⭐ 依赖人工 |

> **参考源**：
> - OpenViking `memory-updater.py` 第 636-740 行 `_apply_upsert()` 方法（AGPL 许可）
> - Git 内容寻址原理（`git-scm.com/docs`）

### 3.3 从第一性原理推导判别策略

**知识的「身份」由什么决定？**

不是文件名，不是标题，不是路径——而是**它所描述的知识内容**。两条知识如果描述同一件事（同一个架构决策、同一条编码规范），它们就是同一个知识的不同版本。

因此，判别策略应该用**语义层面**的匹配，而非文件系统层面的匹配。

### 3.4 建议方案：三层判别 + 四类动作

#### 判别层（Step 4 去重层内完成）

```
输入: 新候选知识 K_new
已有知识库: {K_existing_1, K_existing_2, ...}

判别流程:
┌─────────────────────────────────────────────────────┐
│  Layer 1: MD5 标准化内容哈希                          │
│  ──────────────────────────────────────              │
│  content_normalized = normalize(K_new.content)        │
│  hash = md5(content_normalized)                       │
│  IF hash IN db.content_hashes:                        │
│      → EXACT_MATCH (完全重复，丢弃)                    │
│      RETURN                                          │
├─────────────────────────────────────────────────────┤
│  Layer 2: Embedding 余弦相似度                        │
│  ──────────────────────────────────────              │
│  emb_new = embed(K_new.content)                      │
│  FOR each emb_existing IN db:                         │
│      sim = cosine(emb_new, emb_existing)              │
│      IF sim ≥ 0.95:                                   │
│          → MERGE_CANDIDATE (同一知识的不同表述)         │
│      ELIF sim ≥ 0.85:                                 │
│          → UPDATE_CANDIDATE (相关知识的补充/修正)        │
│      ELSE:                                            │
│          → NEW_KNOWLEDGE (全新知识)                    │
└─────────────────────────────────────────────────────┘
```

#### 四类动作

| 判别结果 | 阈值 | 含义 | MD 文件处理策略 |
|---------|:---:|------|---------------|
| **EXACT_MATCH** | MD5 = | 完全重复 | ❌ 丢弃，不写入任何文件 |
| **MERGE_CANDIDATE** | cosine ≥ 0.95 | 同一知识的不同表述 | 🔀 **字段级合并**：调用 LLM 对比新旧两版，逐字段决定「替换/追加/保留」，写回 knowledge/ 或 staging/ |
| **UPDATE_CANDIDATE** | 0.85 ≤ cosine < 0.95 | 相关知识的补充或修正 | ✏️ **追加模式**：在原文件末尾追加 `## 补充 (2026-06-16)` 章节，保留原文不变。在 staging/ 生成更新通知 |
| **NEW_KNOWLEDGE** | cosine < 0.85 | 全新知识 | ✨ **新建文件**：写入 staging/ |

### 3.5 MERGE_CANDIDATE 的字段级合并策略

> **参考**：OpenViking `_apply_upsert()` 的 merge_op 模式（`merge_op.py`，AGPL 许可）

```python
# 每个字段有自己的合并策略
FIELD_MERGE_STRATEGY = {
    "title":        "REPLACE_IF_BETTER",   # LLM 判断哪个标题更好
    "content":      "MERGE_SECTIONS",      # 按章节合并，新章节追加
    "confidence":   "MAX",                 # 取新旧中较高的 confidence
    "evidence":     "APPEND",              # 追加新的证据来源
    "tags":         "UNION",               # 合并标签集合
    "entry_point":  "REPLACE",             # 替换关联的代码入口
    "created_at":   "PRESERVE",            # 保留原始创建时间
    "modified_at":  "UPDATE",              # 更新修改时间为现在
    "revision":     "INCREMENT",           # 修订版本号 +1
    "revision_note": "APPEND_REASON",      # 追加本次修订的原因
}
```

### 3.6 MD 文件的修订记录

每次修改在 YAML frontmatter 中记录：

```yaml
---
title: "订单幂等校验方案"
confidence: 0.88
status: merged
revision: 3
revision_history:
  - version: 1
    date: "2026-06-10"
    action: created
    source: "Step 2 提炼自 session #a1b2c3"
  - version: 2
    date: "2026-06-14"
    action: updated
    source: "Step 4 合并候选 (cosine=0.96)"
    change: "补充了并发场景下的幂等处理策略"
  - version: 3
    date: "2026-06-16"
    action: verified
    source: "Step 3 代码校验通过 (OrderService.java 未变更)"
```

### 3.7 冲突处理

当 MERGE_CANDIDATE 发现新旧知识**矛盾**时（LLM 判断两段内容互相矛盾）：

| 场景 | 处理 |
|------|------|
| 新旧矛盾，新 confidence 更高 | 替换旧知识，标记旧版本为 deprecated |
| 新旧矛盾，旧 confidence 更高 | 保留旧知识，新知识降级为 UPDATE_CANDIDATE |
| 新旧矛盾，confidence 接近 | **不自动合并**——两条都保留在 staging/，标记 `conflict_with=<对方ID>`，等人工裁决 |

### 3.8 UPDATE_CANDIDATE 的追加模式

> 为什么不直接修改原文？因为原文已经过人工审核，直接改可能破坏已有确认的质量。追加模式 = 保留原文的权威性，同时增补新信息。

```markdown
# 订单幂等校验方案

（原文内容不变，人工审核确认过的）

---

## 补充 (2026-06-16, from session #x9y8z7)

在并发场景下，orderId 可能仍不够唯一。建议搭配时间窗口限制（
同一 orderId 在 5 秒内只允许创建一次）。详见 OrderService.createOrder()
的幂等校验逻辑。

---
```

追加的内容有独立的 YAML frontmatter 标记 `status: supplement`，Step 6 巩固时会提示合并。

### 3.9 需要你确认

| # | 决策点 | 建议 |
|:--:|--------|------|
| 1 | 三层判别（MD5 → cosine 0.95 → cosine 0.85）？ | ✅ 推荐 |
| 2 | 四类动作（EXACT_MATCH / MERGE / UPDATE / NEW）？ | ✅ 推荐 |
| 3 | 字段级合并策略（REPLACE_IF_BETTER / MERGE_SECTIONS / APPEND / PRESERVE）？ | ✅ 推荐 |
| 4 | UPDATE_CANDIDATE 用追加模式（不修改原文）？ | ✅ 推荐 |
| 5 | 矛盾时人工裁决（不自动合并）？ | ✅ 推荐 |

---

## 第四部分：用户追问澄清（V1.1 新增）

> 用户反馈两个关键问题：①时间衰减如何保护有效但没人调用的冷知识？② staging/ 的知识什么时候进入 knowledge/？

### 4.1 Q1：时间衰减 vs 冷知识保护

#### 漏洞走查

一条知识描述了「支付超时应急回滚预案」。这个场景平均每 3 个月才触发一次，但回滚步骤至今仍然正确（关联的 `PaymentRollback.java` 代码从未变更）。

| 信号 | 值 | 来源 |
|------|:--:|------|
| `confidence` | 0.85 | LLM 提炼时评为「明确有效」 |
| `used_count` | 2 | 3 个月内仅 2 次查询命中 |
| `code_verified` | 1 | `PaymentRollback.java` 未变更 |
| `time_decay` | 0.3 | 90 天未重新校验 |

**套用原始公式**：
```
promotion_score = 0.85×0.4 + 0.2×0.2 + 1.0×0.2 - 0×0.1 - 0.3×0.1
                = 0.34 + 0.04 + 0.20 - 0 - 0.03
                = 0.55
```

→ **0.55 < 0.80 阈值，一条完全正确、代码验证过的冷知识被排在了晋升线的底端**。如果系统自动修剪，它会被误删。

#### 根因：两个惩罚信号指向同一类知识

| 惩罚信号 | 度量的是 | 对于「正确但冷门」的知识 | 是否合理？ |
|---------|---------|------------------------|:--------:|
| `used_count` 低 | 场景触发频率 | 低 → 必然被惩罚 | ❌ 不合理——冷场景 ≠ 知识质量差 |
| `time_decay` 高 | 知识新鲜度 | 高 → 必然被惩罚 | ⚠️ 部分合理——但代码未变更时不应惩罚 |

`used_count` 低 + `time_decay` 高 = **冷知识双重暴击**。

#### 修复：code_verified 作为衰减抑制器

> **核心原则**：如果关联代码没变，知识就不需要「重新验证」。代码 = 知识的锚点。

```
修正后的 time_decay 计算：

if code_verified == 1:
    time_decay = 0          # 代码未变更 → 知识仍然有效 → 不衰减
else:
    time_decay = min(days_since_last_verified / 180, 1.0)
```

重算上面那条应急回滚知识：
```
promotion_score = 0.85×0.4 + 0.2×0.2 + 1.0×0.2 - 0 - 0
                = 0.34 + 0.04 + 0.20
                = 0.58
```

仍然 < 0.80。因为 `used_count` 只贡献了 0.04——冷知识在 used_count 这条信号上天然吃亏。

#### 更深层的修复：晋升与修剪解耦

`used_count` 不应该参与「晋升」评分，它是「修剪」的信号。

| 机制 | used_count 的角色 | 原因 |
|------|------------------|------|
| **晋升评分** | **移除 used_count 项** | 冷知识不应该因为没人调用而被压在 staging/ 里不让晋升 |
| **修剪规则** | **保留 used_count 项** | 低频 + 低质量 + 代码已变更 → 候选删除 |

**修正后的晋升公式（V1.1）**：

```
晋升评分 = confidence × 0.50           # LLM 初始质量评价
         + code_verified × 0.30        # 代码锚点（抑制衰减）
         + (1.0 - time_decay) × 0.20   # 时间新鲜度（code_verified=1 时此项=0.20，无衰减）

晋升阈值:
  评分 ≥ 0.80  →  staging/ → knowledge/  (自动)
  0.65 ≤ 评分 < 0.80  →  保留 staging/，标记「可审核」
  评分 < 0.65  →  保留 staging/，标记「需人工确认」
```

**修剪规则（V1.1——独立于晋升）**：

| 条件 | 动作 |
|------|------|
| `used_count < 3` AND `confidence < 0.6` AND `code_verified = 0` AND `age > 30d` | → 候选删除（标记 deprecated/） |
| `used_count < 3` AND `code_verified = 1` | → 🛡️ **保护**——不移除。冷但正确，留着。 |
| `used_count < 3` AND `confidence ≥ 0.8` AND `code_verified = 0` | → 降级为「待校验」，不移除 |
| `used_count = 0` AND `confidence < 0.5` AND `age > 60d` | → 自动删除（低质 + 未使用 + 过老） |

> 📎 **参考**：Bloomfire KM Cycle 中 Maintain 阶段的「knowledge audit」不像 SEO 那样只看点击量——只看知识本身是否仍然准确。对应到这里就是 `code_verified`。

> ⚠️ **注意**：晋升规则的完整讨论（多信号权重调优、绿色通道细节、成熟知识降级条件）用户已说「等后续再深入讨论」。此处仅修复了已识别的冷知识惩罚漏洞。

---

### 4.2 Q2：staging/ 的知识什么时候进入 knowledge/？

#### 当前设计缺口

Step 5（写入层）和 Step 6（巩固层）之间的衔接存在模糊地带：

- Step 5 说「写入 MD 文件」→ 但没说明写到 staging/ 还是 knowledge/
- Step 6 说「dev-context-memo-dream 巩固」→ 但没说明它是 promotion 的唯一触发点

#### 完整流程（V1.1 明确后）

```
┌─────────────────────────────────────────────────────────────────┐
│                    Step 5（写入层）写入阶段                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  confidence ≥ 0.95 ?                                            │
│    ├── YES → 直接写入 knowledge/<domain>/<名称>.md               │
│    │         绿色通道：几乎确定正确的知识跳过人工审核               │
│    │         （符合「弱审核，默认生效」原则）                       │
│    │                                                             │
│    └── NO  → 写入 staging/20260616-<名称>.md                     │
│              confidence < 0.95 的所有知识先进 staging/            │
│              等待 dev-context-memo-dream 评估后晋升                │
│                                                                 │
│  同时：所有知识（无论路径）写入 SQLite knowledge_index 表          │
│        表中 file_path 字段记录实际物理路径                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│           Step 6（巩固层）dev-context-memo-dream                   │
│           唯一触发点：用户主动运行该命令                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 扫描 staging/ 目录下所有 .md 文件                             │
│  2. 对每个文件：                                                  │
│     a. 读取 YAML frontmatter + 知识正文                           │
│     b. 计算晋升评分（§4.1 修正后公式）                              │
│     c. 检查修剪规则（§4.1）                                       │
│  3. 决策：                                                       │
│     ├── 评分 ≥ 0.80  →  文件移动：staging/ → knowledge/<domain>/   │
│     │                    去掉日期前缀                              │
│     │                    更新 DB: file_path + status='verified'   │
│     │                                                             │
│     ├── 0.65 ≤ 评分 < 0.80  →  保留 staging/                      │
│     │                          更新 DB: status='pending_review'   │
│     │                          提示：「以下 X 条知识可审核」         │
│     │                                                             │
│     ├── 评分 < 0.65  →  保留 staging/                             │
│     │                   更新 DB: status='draft'                   │
│     │                   提示：「以下 Y 条知识需人工确认」             │
│     │                                                             │
│     └── 命中修剪规则  →  移动文件：staging/ → deprecated/           │
│                         更新 DB: status='deprecated'              │
│                                                                 │
│  4. 输出报告：                                                    │
│     本次晋升: 3 条  │  可审核: 5 条  │  需确认: 2 条  │  清理: 1 条  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| **晋升的唯一触发点** | `dev-context-memo-dream` | 不自动晋升——用户控制节奏。但绿色通道（≥0.95）是例外，直接写 knowledge/ |
| **绿色通道阈值** | confidence ≥ 0.95 | 提取自 Aether：双条件 Auto-Approve 的上限。0.95 意味着「几乎确定」——即便事后发现错误，代价也低 |
| **DB 同步** | 文件移动时更新 `file_path` + `status` | DB 是索引，文件是源。文件路径变了，DB 跟着变。保证 `entry_point` → `file_path` 的查找不中断 |
| **--dry-run 模式** | 预览不移动文件 | 符合 `dev-context-memo-dream --dry-run` 的预期行为——先看评分，满意再执行 |

#### 你问的「新建文件写入 staging/ 什么时候进入 knowledge」

> **答案**：如果你不主动运行 `dev-context-memo-dream`，它永远待在 staging/——除非 confidence ≥ 0.95（绿色通道直接在 Step 5 写入时跳过 staging）。

**日常节奏建议**：
```
编码会话结束 → AI 为您生成了一条知识（confidence=0.82）
  → 自动写入 staging/20260616-订单幂等校验方案.md

你什么时候有空 → 运行 dev-context-memo-dream
  → 系统告诉你：「订单幂等校验方案 评分=0.86 → 建议晋升」
  → 你按回车确认 → staging/ → knowledge/订单/
```

或者你偷懒：
```
编码一周后 → 积了 15 条 staging/
  → 运行 dev-context-memo-dream
  → 系统批量评估 15 条，自动晋升 8 条，提醒你审核 5 条，建议清理 2 条
```

#### 需要你确认

| # | 决策点 | 建议 |
|:--:|--------|------|
| 1 | 绿色通道 confidence ≥ 0.95 直接写 knowledge/，其他全进 staging/？ | ✅ 符合「弱审核，默认生效」 |
| 2 | `dev-context-memo-dream` 作为唯一 promotion 触发点？ | ✅ 用户控制节奏 |
| 3 | 文件移动时 DB 同步更新 `file_path`？ | ✅ 必须——否则查询断链 |

---

## 附录 A：本次调研参考来源

| # | 来源 | 引用内容 | 许可/公开性 |
|:--:|------|---------|:---------:|
| 1 | **Aether Content Moderation Pipeline** (`github.com/rhoninl/Aether/blob/main/docs/design/content-moderation-pipeline.md`) | 审核状态机设计（6阶段：Pending→Scanning→Decision→AutoApproved/InReview/Rejected）、双条件 Auto-Approve、申诉回路、非对称安全策略 | CC0 许可 |
| 2 | **OpenViking memory-updater.py** (`OpenViking-source/memory-updater.py` 第 636-740 行) | `_apply_upsert()` 的字段级合并策略、`merge_op` 工厂模式、系统管理元数据保留机制 | AGPL-3.0 |
| 3 | **Git 内容寻址** (`git-scm.com/docs`) | 内容哈希作为文件唯一标识、tree diff 检测变更范围 | 开源 |
| 4 | **Bloomfire Knowledge Management Cycle** (`bloomfire.com/blog/knowledge-management-cycle/`) | 知识生命周期五阶段：Create→Validate→Store→Share→Maintain，Maintain 阶段的定期重新验证 | 公开文章 |
| 5 | **YouTube 推荐系统** (公开论文) | 隐式反馈（观看时长 > 点击次数）作为质量信号 | 公开 |
| 6 | **Elasticsearch _score** | 多信号加权（TF-IDF + field norm + boost）而非单一指标 | 开源 |
| 7 | **Jekyll 目录结构** (`jekyllrb.com/docs/structure/`) | `_drafts/` vs `_posts/` 物理目录分离模式 | MIT 许可 |

## 附录 B：用户已确认 / 待确认汇总

### ✅ 已确认（本轮）

| 部分 | 决策 | 状态 |
|------|------|:--:|
| 目录 | 三目录（staging/ / knowledge/ / deprecated/） | ✅ |
| 目录 | staging/ 日期前缀命名 | ✅ |
| 目录 | knowledge/ 按领域分子目录 | ✅ |
| 目录 | 拒绝的知识保留 7 天 | ✅ |
| Q2 | 绿色通道 confidence ≥ 0.95 → 直接写 knowledge/ | ✅ |
| Q2 | `dev-context-memo-dream` 作为 promotion 触发点 | ✅ |
| Q2 | 文件移动时 DB 同步更新 | ✅ |

### ⏸️ 暂缓（用户要求后续深入讨论）

| 部分 | 内容 | 状态 |
|------|------|:--:|
| 晋升 | 多信号评分权重调优 | ⏸️ |
| 晋升 | 绿色通道细节 | ⏸️ |
| 晋升 | 成熟知识降级条件 | ⏸️ |

### 🔜 待确认（来自 V1.0）

| # | 决策点 | 建议 |
|:--:|--------|------|
| 1 | 修改检测的三层判别（MD5 → cosine 0.95 → cosine 0.85）？ | ✅ 推荐 |
| 2 | 四类动作（EXACT_MATCH / MERGE / UPDATE / NEW）？ | ✅ 推荐 |
| 3 | 字段级合并策略？ | ✅ 推荐 |
| 4 | UPDATE_CANDIDATE 用追加模式？ | ✅ 推荐 |
| 5 | 矛盾时人工裁决？ | ✅ 推荐 |

## 附录 C：下一步行动

1. 用户确认附录 B 中「待确认」的 5 个修改检测决策点
2. 更新 Step 4（去重层）细化设计：加入三层判别 + 四类动作
3. 更新 Step 5（写入层）细化设计：加入 staging/ 目录方案 + 绿色通道 + 字段级合并
4. 更新 Step 6（巩固层）细化设计：加入 staging→knowledge 晋升流程 + 修剪保护规则
5. 更新 Step 2、Step 3 设计文件中的相关引用
