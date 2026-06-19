# devContextMemo 修剪规则 — 完整设计 V1.1

> **触发**：用户要求「修剪规则完整设计」（晋升参数调优后第 ⑦ 项），后经审核发现 11 项漏洞，全面修补
> **定位**：将散落在 5 个文档中的修剪/清理/淘汰规则统一为一份完整的修剪规则文档
> **日期**：2026-06-16
> **版本**：V1.1（修补 V25-V35 全部 11 项漏洞）
> **关联文档**：
> - `devContextMemo-晋升生命周期-设计-V2.0.md`（晋升端，含 T11/T14/T16/T19/T21）
> - `devContextMemo-数据写入流水线-详细设计-V1.0.md` §8.3（三种修剪规则，MiMo Code Phase 5 借鉴）
> - `devContextMemo-流水线-Step6-巩固层-细化设计-V1.0.md`（修剪触发起始设计）
> - `devContextMemo-TOP5待办-决策辅助分析-V1.0.md`（used_count 更新时机）
> - `devContextMemo-目录划分-晋升规则-修改检测-深度调研-V1.0.md`（冷知识保护初始设计）
> - `devContextMemo-晋升参数调优-分析报告-V1.0.md`（V2.0 参数）

---

## 设计原则

| # | 原则 | 含义 |
|:--:|------|------|
| 1 | **晋升看质量，修剪看使用** | 晋升评分只含 confidence + freshness + anchor_bonus；修剪（淘汰/降级/归档）只看 used_count + last_used_at + code_verified + confidence 下限 |
| 2 | **COLD 是保护盾，不是特权** | code_verified=1 → 不受低频惩罚。但锚点断裂后→进入 STALE 缓冲路径 |
| 3 | **渐进式降级，不突然删除** | ACTIVE → COLD → STALE → DEPRECATED → 删除，每个阶段都是可逆的 |
| 4 | **人工审核权优先** | PENDING_REVIEW 不自动修剪；DEPRECATED 阶段可人工恢复 |
| 5 | **软上限提示，硬上限截断** | Phase 1 500 条软上限（提示 + 建议清理），DEPRECATED 30 天硬删除 |
| 6 | **修剪频率 = 7 天** | 与 Step 6 auto-dream 同步，不产生额外的扫描负担 |
| 7 | **修剪结果对人可见** | 每次修剪生成 report，列出被降级/废弃/删除的知识清单 |

---

## 一、修剪信号模型

### 1.1 五维信号

修剪决策依赖 5 条信号：

| 信号 | 含义 | 对修剪的影响 |
|------|------|:----------:|
| **used_count** | 知识被检索/注入的次数 | 核心淘汰指标：低使用 = 候选修剪 |
| **last_used_at** | 最后一次被使用的时间 | 时间衰减：久未使用 = 优先级升高 |
| **code_verified** | 知识是否有代码锚点（0/1） | 保护因子：code_verified=1 → COLD 保护 |
| **confidence** | LLM 对知识正确性的置信度 | 下限过滤：低于阈值直接废弃（不依赖使用频率） |
| **age** | 知识创建至今的天数 | 时间窗口：新知识即使没用也有保护期 |

### 1.2 used_count 更新机制

> 已决策：Phase 1 用方案 A（查询即计数）。细节参见 `devContextMemo-TOP5待办-决策辅助分析-V1.0.md` §TODO-6.3。

```
每次 MCP Tool query 命中时:
  UPDATE knowledge_entries
  SET used_count = used_count + 1,
      last_used_at = NOW()
  WHERE id = :knowledge_id
```

**去抖动**：Phase 1 不处理（每次命中都计数），Phase 2 引入 `session_id` 去重。

**已知缺陷**：方案 A 下同一会话重复注入会过度计数。承认此缺陷，Phase 1 容忍，Phase 2 通过 injection_log 解决。

### 1.3 信号优先级（冲突裁决）— V1.1 补充

当多条修剪规则同时命中一条知识时：

```
高优先级 ────────────────────────────────→ 低优先级

冲突裁决（T17） > 校验失败高确定度（T18） > 低置信度下限（T19/T22） > 使用频率修剪（T25） > 时间衰减修剪（T14, T11, T11-b）

其中：T11（ACTIVE→COLD）属保护规则，优先级最低，可被任何降级规则覆盖
     T11-b（COLD→STALE）属时间衰减修剪，优先级的「时间衰减」层
     T24（建议清理）属告警，不改变状态，不参与优先级裁决
```

> 例如：一条知识 used_count=50 被频繁使用，但 Step 3 检测到 HIGH certainty INCONSISTENT → T18 → 直接 DEPRECATED。使用频率不能对抗正确性。

---

## 二、修剪规则分层

```
┌───────────────────────────────────────────────────────────────────────┐
│                         修剪规则三层体系                                │
│                                                                       │
│  Layer 1: 质量下限（confidence-based）                                 │
│    → 无论使用频率，低质量知识直接淘汰                                    │
│    → T19: DRAFT + confidence<0.6 + age>30d + used_count=0              │
│                                                                       │
│  Layer 2: 使用频率（used_count-based）                                 │
│    → 低频使用 + 长时间未访问 = 候选修剪                                  │
│    → 保护：code_verified=1 → COLD 保护                                  │
│    → 保护：age < 保护期 → 新知识不受低频惩罚                             │
│                                                                       │
│  Layer 3: 代码锚点（code_verified-based）                               │
│    → 代码变更 → 触发一致性检查 → STALE 或 DEPRECATED                    │
│    → T12/T13/T14/T16/T18 均依赖此层                                     │
│                                                                       │
│  最终清理: DEPRECATED 30 天后物理删除                                   │
│    → T21: 不可逆的最后一步                                              │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 三、按位置细分修剪规则

### 3.1 staging/ 修剪（维护临时目录的洁净）

staging/ 中的知识尚未晋升到 knowledge/，不应按「使用频率」修剪（它们根本没有使用机会）。staging/ 只按**质量和时间**修剪。

```
┌──────────────────────────────────────────────────────────┐
│ staging/ 修剪规则表                                       │
├──────────┬────────────────────────┬─────────────────────┤
│ 目标阶段  │ 触发条件                  │ 动作                 │
├──────────┼────────────────────────┼─────────────────────┤
│ DRAFT    │ confidence < 0.6        │ 已覆盖：T19          │
│          │ AND age > 30d           │ → DEPRECATED        │
│          │ [used_count=0 冗余已移除  │ （V26 修补）         │
│          │  staging/ 中始终为 0]    │                     │
├──────────┼────────────────────────┼─────────────────────┤
│ DRAFT    │ age > 90d               │ 🆕 T22:             │
│          │ (任一 confidence)       │ → DEPRECATED        │
│          │                          │ 标记='stale_draft'  │
├──────────┼────────────────────────┼─────────────────────┤
│ STAGED   │ age > 14d               │ 🆕 T23:             │
│ (未被评估)│ (Step 6 尚未首次评估)    │ → 提升优先级          │
│          │                          │ 标记='overdue_eval' │
│          │                          │ ⚠️ 不移除！           │
├──────────┼────────────────────────┼─────────────────────┤
│ PENDING_ │ 永久保留                  │ 不自动修剪            │
│ REVIEW   │                          │ （V16 已决策）         │
├──────────┼────────────────────────┼─────────────────────┤
│ CANDIDATE│ 同晋升规则 T6             │ 晋升 or 回退          │
│          │                          │ ⚠️ 不修剪，等晋升      │
└──────────┴────────────────────────┴─────────────────────┘
```

**新增跃迁**：

| # | 从 → 到 | 触发条件 | 触发点 | 自动化 | 动作 |
|:--:|---------|---------|:------:|:-----:|------|
| **T22** | DRAFT → DEPRECATED | age > 90d（无 confidence 限制） | 修剪扫描 | 🤖 自动 | 标记 reason='stale_draft' |
| **T23** | STAGED → 警告 | age > 14d 且未首次评估 | 修剪扫描 | 🤖 自动 | 标记 overdue_eval，置顶 staging/ 列表 |

> **T22 设计依据**：DRAFT 阶段的知识本质上是「质量不足以自动采纳」。即使 confidence 不低（0.40-0.65），如果 90 天无人深入确认，说明人对这条知识不感兴趣——应该清理腾空间。
>
> **T23 设计依据**：STAGED 超过 14 天未被 Step 6 评估，说明巩固调度出了问题（不是知识质量问题）。不修剪，而是告警提示用户「评估队列积压」。

### 3.2 knowledge/ 修剪（核心：使用频率淘汰）

knowledge/ 中的知识已经过质量验证（晋升或绿色通道），修剪核心是**使用频率**。V2.0 晋升生命周期已定义了从 ACTIVE 出发的以下下降路径：

```
ACTIVE ────────→ COLD (code_verified=1, used_count<3)  ← T11
ACTIVE ────────→ STALE(suspicious) (T12/T14)           ← T12/T14
ACTIVE ────────→ DEPRECATED (T17/T18)                  ← T17/T18
COLD ──────────→ STALE(suspicious) (锚点断裂)           ← T13
STALE(deep) ──→ DEPRECATED (T16)                       ← T16
```

**这是晋升端的设计。修剪端需要补充的是：COLD 知识在什么条件下应该升级到「候选修剪」？**

#### 3.2.1 COLD 的保护与修剪边界

```
COLD 条件（V1.1 修补 - V35）:
  code_verified = 1 AND (used_count < 3 OR last_used_at IS NULL OR last_used_at < NOW() - INTERVAL 90 DAYS)

COLD 效果: 不受低频惩罚、confidence 不衰减、不参与修剪

但是！COLD 不是永久保护伞。以下条件触发修剪：
```

**V1.1 关键修补（V35）**：T11 原先只检查 total `used_count < 3`，未考虑「热后冷」的情况：一条知识 used_count=15 但 last_used_at=155 天前，它永远满足不了 `used<3`，永远 ACTIVE，永远不下沉。修补后增加 `last_used_at > 90d` 条件——即使 used_count 高，如果 90 天内一次都没被使用，也进入 COLD 休眠。90 天窗口匹配项目迭代节奏（~3 个 sprint），足以区分「持续活跃」和「热度已过」。`last_used_at IS NULL` 处理从未被使用的知识（创建时 last_used_at=NULL）。

```
┌──────────────────────────────────────────────────────────────┐
│ COLD 退出路径（修剪视角）— V1.1 修补                            │
├──────────┬──────────────────────────────────┬────────────────┤
│ T13      │ code_verified → 0（锚点断裂）     │ → STALE        │
│          │                                  │ （同晋升生命周期）│
├──────────┼──────────────────────────────────┼────────────────┤
│ T11-b    │ age > 365d AND used_count = 0    │ 🆕 → STALE     │
│          │ (一年未用 + 零引用)               │ (suspicious)   │
├──────────┼──────────────────────────────────┼────────────────┤
│ T24      │ soft limit 触发                  │ 🆕 建议清理     │
│          │ 总 knowledge/ > 500              │ 报告 + 排序     │
└──────────┴──────────────────────────────────┴────────────────┘
```

**新增跃迁**：

| # | 从 → 到 | 触发条件 | 触发点 | 自动化 | 动作 |
|:--:|---------|---------|:------:|:-----:|------|
| **T11-b** | COLD → STALE(suspicious) | code_verified=1 AND used_count=0 AND cold_duration_days > 365d | 修剪扫描 | 🤖 自动 | 标记 stale_sub_phase='suspicious'，flag='cold_long_unused' |
| **T24** | COLD → 列表告警 | used_count 最低的 max(ceil(COLD_count × 20%), min(10, COLD_count)) 条，至少 1 条（V31 修补） | 软上限触发时 | 🤖 自动 | 生成清理建议列表，不自动操作 |

> **T11-b 设计依据**：COLD 的保护来自 code_verified=1（代码锚点证明知识正确）。但当知识一年完全没有被检索引用时，说明它虽然正确但对项目当前工作流价值极低。进入 STALE(suspicious) 是温和提醒——不是直接废弃，而是 90 天缓冲（T16 路径）。
>
> **T24 设计依据**：软上限（500 条）触发时，不自动删除，而是按 used_count 排序，最低 20% 列入建议清理清单，用户决策。这是「修剪端与晋升端的对称」——晋升有 PENDING_REVIEW 人工通道，修剪也应有建议清理人工通道。

#### 3.2.2 使用频率修剪阈值（核心参数）

knowledge/ 中 code_verified=0 的知识，没有 COLD 保护，使用频率是唯一保护：

```
修剪公式（knowledge/，code_verified=0）— V1.1 修补:

prune_priority = (1 - freshness) × 0.60 + (1 - used_count_normalized) × 0.40

freshness = max(0, 1 - days_since_last_used / 180)
used_count_normalized = min(used_count / 5, 1.0)  # 使用 5 次以上 = 「常用」

T25 触发条件（V25 修补）:
  prune_priority ≥ 0.70 AND age ≥ 60d  ← 新增最小 age 保护
```

**V1.1 修补说明（V25）**：T25 原先缺少新建知识保护期。30 天零使用的新知识直接进入 STALE(suspicious)，造成「越新越不被用 → 越不被用越可疑」的恶性循环。修补后增加 `age ≥ 60d` 最小保护——60 天内零使用的知识不触发 T25，给新知识足够的「被发现」窗口。60 天 ≈ 2 个月 ≈ 6 个 sprint，覆盖大部分项目的冷启动期。

**V1.1 修补说明（V27-V34）**：T14 和 T25 在 used=0+age≥90d 时重叠触发。设计明确的执行顺序：
```
修剪扫描执行顺序:
  1️⃣ T14 先检查（code_verified=0 + age>90d → STALE, flag='unverified_for_long'）
  2️⃣ T25 补充检查（仅对 T14 未命中的条目: prune_priority≥0.70 + age≥60d → STALE, flag='low_usage'）
  3️⃣ 若 T14 已命中 → 跳过 T25（避免 flag 归属冲突）
```
T14 惩罚「长期不验证」（age>90d），T25 惩罚「长期不查询」（prune_priority≥0.70）。当 used=0+age≥90d 时 T14 先命中（age 条件直接满足），T25 不再检查。当 used≥1 时 T14 仍可能触发但 T25 通常不触发（prune_priority 低于阈值），形成真正的互补而非重叠。

```
prune_priority ≥ 0.70 → T25: 候选修剪
```

| 场景 | used_count | last_used_at | age | freshness | used_norm | score | age≥60d? | T25? |
|------|:---------:|:----------:|:---:|:---------:|:---------:|:-----:|:--------:|:----:|
| 偶尔用 | 2 | 30d 前 | 60d | 0.833 | 0.40 | 0.70 | ✅ | ✅ 边界 |
| 低频 | 1 | 90d 前 | 120d | 0.50 | 0.20 | 0.65 | ✅ | ❌ 安全 |
| 新知识+零使用 | 0 | N/A | 30d | 0.833 | 0.00 | 0.70 | ❌ | ❌ 受 age 保护 |
| 从未用过+够老 | 0 | N/A | 180d | 0.00 | 0.00 | 1.00 | ✅ | ✅ 强烈 |
| 常用 | 5+ | 7d 前 | 60d | 0.961 | 1.00 | 0.02 | ✅ | ❌ 安全 |
| 低频但新 | 1 | 14d 前 | 30d | 0.922 | 0.20 | 0.33 | ❌ | ❌ 受 age 保护 |

**新增跃迁**：

| # | 从 → 到 | 触发条件 | 触发点 | 自动化 | 动作 |
|:--:|---------|---------|:------:|:-----:|------|
| **T25** | ACTIVE(code_verified=0) → STALE(suspicious) | prune_priority ≥ 0.70 AND age ≥ 60d | 修剪扫描 | 🤖 自动 | 标记 stale_sub_phase='suspicious'，flag='low_usage' |

> **V1.1 修补说明（V25+V27+V34）**：
> - **T14 和 T25 的执行顺序**：T14 先检查（age>90d），若命中则 T25 跳过（避免 flag 归属冲突）
> - **T14 惩罚什么**：「长期不验证」——code_verified=0 的知识 90 天无代码锚点重新校验
> - **T25 惩罚什么**：「长期不查询」——使用频率极低，且知识已存在足够长时间（≥60d）
> - 两条规则在 used=0+age≥90d 时由 T14 包揽（T25 不触发）；在 used≥1+age≥90d 时 T14 独享（prune_priority 不达标）。**真正的互补在 used≥1 时成立**。

#### 3.2.3 修剪优先级排序（给 dev dream 人工审核用）

当 `prune_priority ≥ 0.70` 触发后，系统生成排序列表：

```
排序 = prune_priority（降序）

同等 prune_priority 下的次级排序:
  1. last_used_at（升序——越久越靠前）
  2. confidence（升序——越不靠谱越靠前）
  3. age（降序——越老越靠前）

前 10 条标记为「强烈建议修剪」
```

### 3.3 deprecated/ 修剪（最终清理）

deprecated/ 的唯一规则——T21：

```
条件: 处于 DEPRECATED 且 deprecation_age ≥ 30 天
动作: 物理删除 .md 文件 + 软删除 DB 记录（status='deleted'）
恢复窗口: 30 天
```

**不可恢复阶段**：物理删除后 DB 记录标记 `status='deleted'` 保留不实际移除。用户如需恢复，需要从 Git 历史还原文件 + 手动恢复 DB 记录。

**DEPRECATED 类型与清理行为**：

| deprecation_reason | T21 行为 | 说明 |
|:-------------------|:--------:|------|
| superseded（T17 冲突裁决） | 正常 30 天清理 | 被新版本取代 |
| direct_contradiction（T18） | 正常 30 天清理 | 校验直接失败 |
| verification_failed（T16） | 正常 30 天清理 | 累积校验失败 |
| low_quality（T19） | **缩短 14 天清理** | 低质量知识不值得长保留 |
| human_rejected（T8/T10） | 正常 30 天清理 | 人工判断不应长期保留 |
| stale_draft（T22） | **缩短 14 天清理** | 长期未确认的草稿 |

> **缩短清理窗口（14 天）的设计依据**：low_quality 和 stale_draft 本就没有质量背书，30 天保留窗口过于慷慨。14 天在「防误删」和「清理效率」间取平衡。

---

## 四、硬上限与软上限

### 4.1 软上限（500 条 — 提示）

```
当 knowledge/ + staging/ 条目总数 > 500:
  1. 生成清理建议报告（按 prune_priority 排序的 knowledge/ 条目 + DRAFT 条目）
  2. 在 dev review 界面顶部显示告警横幅
  3. 不自动执行任何删除或移动
```

### 4.2 硬上限（2000 条 — 强制修剪）— V1.1 修补

```
当 knowledge/ + staging/ 条目总数 > 2000:
  1. 自动修剪 DRAFT + confidence < 0.4 + used_count = 0 的条目 → DEPRECATED
     (V29 修补：增加 used_count=0 保护，有使用记录的 DRAFT 不因硬上限被紧急删除)
  2. 自动清理 DEPRECATED > 30d 的条目（T21）
  3. 生成报告，逐条列出被自动修剪的内容

  ⚠️ 已删除旧第 2 条「used_count=0 AND last_used_at > 365d」(V30 修补)
  理由：此条件已被 T11-b(365d) 和 T25(fresh=0) 全覆盖，硬上限前这些条目早已进入 STALE
```

> **V1.1 修补说明（V29）**：硬上限 DRAFT 修剪保留 `used_count=0` 条件——有使用记录的 DRAFT（说明在 staging/ 预览中被频繁引用）不应被紧急删除。硬上限的场景是「知识库严重膨胀」，只应清理「低质量+从没人看过」的条目。
>
> **V1.1 修补说明（V30）**：删除硬上限第 2 条。当 `used_count=0 + last_used_at > 365d` 时，该条目已被 T11-b（code_verified=1 → COLD→STALE）或 T25（code_verified=0 → STALE）覆盖，不需要在硬上限中重复处理。删除去重逻辑。

> **硬上限的设计依据**：2000 条 ≈ 512K tokens 的注入窗口（假设每条 256 tokens）。超过此规模将迫使 AI 做显著的相关性裁剪，损害注入质量。Phase 2 可调此参数。

---

## 五、修剪执行时间表

```
┌──────────┬──────────────────────┬──────────────────────────────────┐
│ 频率      │ 触发                  │ 执行内容                           │
├──────────┼──────────────────────┼──────────────────────────────────┤
│ 每 7 天   │ Step 6 auto-dream    │ 全量修剪扫描：                      │
│          │                      │ - staging/ → T19/T22/T23          │
│          │                      │ - knowledge/ → T11-b/T24/T25       │
│          │                      │ - deprecated/ → T21               │
│          │                      │ - 软上限检查 + 报告生成             │
├──────────┼──────────────────────┼──────────────────────────────────┤
│ 手动      │ dev dream           │ 同上（用户主动触发）                │
├──────────┼──────────────────────┼──────────────────────────────────┤
│ 事件驱动  │ 每次新知识写入后       │ 仅检查硬上限（2000 条）             │
│          │                      │ 超过 → 强制修剪                     │
└──────────┴──────────────────────┴──────────────────────────────────┘
```

---

## 六、修剪报告格式

每次修剪扫描生成 `devContextMemo_prune_report_YYYYMMDD.md`：

```markdown
# devContextMemo 修剪报告 — 2026-06-23

## 统计
| 指标 | 数量 |
|------|:---:|
| 总知识条目 | 587 |
| COLD 保护中 | 42 |
| staging/ 待审 | 23 |
| 本次标记 DEPRECATED | 5 |
| 本次物理删除（T21） | 3 |
| 建议清理（T24） | 12 |

## 标记 DEPRECATED
| 知识 | 原因 | 修剪前状态 | 恢复截止 |
|------|------|:--------:|:------:|
| 旧版缓存策略.md | low_quality (T19) | DRAFT | 2026-07-07 |
| 单机限流方案.md | verification_failed (T16) | STALE(deep) | 2026-07-23 |
| ... | ... | ... | ... |

## 物理删除（T21 — 不可恢复）
| 知识 | 废弃原因 | 废弃日期 |
|------|---------|:------:|
| 初版架构设计.md | superseded | 2026-05-20 |
| ... | ... | ... |

## 建议清理（T24 — 需你决策）
| 知识 | used_count | 最后使用 | 已冷天数 |
|------|:---------:|:------:|:------:|
| 测试环境配置.md | 0 | 2025-12-01 | 205 |
| ... | ... | ... | ... |

## 评估队列告警（T23）
| 知识 | STAGED 天数 |
|------|:----------:|
| 20260604-事务隔离级别.md | 19 |
```

---

## 七、与晋升生命周期的一致性验证

| 晋升生命周期跃迁 | 修剪规则文档 | 关系 |
|:--------------:|-----------|------|
| T11（ACTIVE→COLD） | §3.2.1 COLD 保护边界 | 修剪端补充了 COLD 的退出条件 |
| T14（ACTIVE→STALE） | §3.2.2 T25 | T25 是 T14 的使用频率维度互补 |
| T16（STALE→DEPRECATED） | §3.3 | 不修改——通过晋升生命周期已定义 |
| T19（DRAFT→DEPRECATED） | §3.1 | 补充 T22（90d 兜底） |
| T21（自动清理） | §3.3 | 补充按 deprecation_reason 差异化清理窗口 |

---

## 八、散落规则统一对照表

| 旧位置 | 旧规则 | 本文统一后 |
|--------|--------|:--------:|
| `数据写入流水线` §8.3 | `used_count=0 AND last_used_at<90d → DEPRECATED` | → T25（prune_priority≥0.70 → STALE，不是直接 DEPRECATED） |
| `数据写入流水线` §8.3 | `confidence<0.4 → DEPRECATED` | → T19（仅 DRAFT） |
| `数据写入流水线` §8.3 | `updated_at<180d AND last_used_at<180d → ARCHIVED` | → 废弃「archived」概念，统一用 COLD（保护）和 STALE（缓冲） |
| `Step6 巩固层` 配置 | `unused_days_threshold: 90` | → 保留，用于 T25 freshness 参数 |
| `Step6 巩固层` 配置 | `archived_days_threshold: 180` | → 废弃「archived」，等价 COLD 保护上限 365d |
| `Step6 巩固层` 配置 | `max_knowledge_count: 500` | → 保留为软上限 |
| `Step6 巩固层` 配置 | `auto_run_interval_days: 7` | → 保留，修剪扫描频率 |

> **「archived」概念废弃说明**：V1.0 设计中的「archived」意图是「180 天未用→归档」，但 COLD 机制（code_verified 保护）已经覆盖了这个需求——正确的低频知识应 COLD 保护，错误的低频知识应 STALE→DEPRECATED。引入第三个状态「archived」只会增加复杂度却不增加区分度。

---

## 九、新增 DB 字段（补充 T11-b / T22 / T23 / T25）

| 字段 | 类型 | 说明 |
|------|------|------|
| `prune_priority` | DECIMAL(3,2) | 修剪优先级分数（T25 计算） |
| `cold_duration_days` | INT | 处于 COLD 状态的天数（用于 T11-b） |
| `overdue_eval` | INT DEFAULT 0 | 是否超过 14 天未被首次评估（T23） |

---

## 十、边界场景处理

### 10.1 全部知识都受 COLD 保护（无修剪动作）

> **场景**：100% 的 knowledge/ 条目 code_verified=1。
>
> **处理**：修剪报告显示「0 条目需修剪，所有知识均有代码锚点保护」。不执行修剪。**这是健康的——说明项目代码质量高，知识全有锚点验证。**

### 10.2 用户撤销了修剪

> **场景**：T21 物理删除后，用户从 Git 恢复了文件。
>
> **处理**：DB 中 `status='deleted'` 的记录保留。用户需运行 `devContextMemo repair` 手动重新索引（将 status 改回 ACTIVE/COLD）。系统不自动反悔——物理删除意味着用户确认过 30 天窗口。

### 10.3 修剪与晋升在同一次 auto-dream 中执行

> **执行顺序**：晋升（staging→knowledge）→ 修剪（knowledge→STALE/DEPRECATED）→ 清理（DEPRECATED→删除）
>
> **原因**：先晋升再修剪——避免「刚晋升就被修剪」的尴尬窗口。

### 10.4 大语言模型知识（如编码规范）被误修剪

> **场景**：一条「团队使用 Prettier 格式化」的编码规范——无代码锚点，3 个月只被检索了 1 次 → T25 score=0.70 → STALE(suspicious)。
>
> **处理**：进入 STALE 不是终点——有 90 天缓冲（T16 路径）等待恢复。用户被提醒后可以手动标记为「永久保留」或添加代码锚点关联。

### 10.5 修剪在大型 monorepo 中的性能

> **场景**：1000+ 条 knowledge 的修剪扫描。
>
> **处理**：修剪规则全部基于 DB 字段（used_count, last_used_at, code_verified, confidence, age），无需读 MD 文件内容。单次修剪扫描 O(N)，1000 条目在 SQLite 中 ~10ms。不会成为瓶颈。

### 10.6 COLD→STALE 后 confidence 的语义矛盾（V32 — Phase 2 处理）

> **场景**：知识 X（code_verified=1, confidence=0.85）因 T11-b 进入 STALE(suspicious)，confidence 被打折到 0.68。
>
> **矛盾**：code_verified=1 说「正确」，confidence=0.68 说「不太可信」——两个信号冲突。
>
> **V1.1 决策**：Phase 1 保留当前行为（STALE 统一打折扣），Phase 2 收集数据后决定方案：
> - 方案 A：T11-b 进入 STALE 时不打折，用独立的 `relevance_score` 控制检索排序
> - 方案 B：T11-b 进入 STALE 时将 code_verified 置为 0（「长期不用=脱离上下文」）
>
> **当前缓解**：STALE(suspicious) 的折扣最温和（×0.80），confidence=0.85→0.68 仍在可检索范围内。且进入 STALE 后 90 天缓冲期内用户有机会手动标记「永久保留」。

### 10.7 PENDING_REVIEW 滞留无降级路径（场景 7 发现 — Phase 2 处理）

> **场景**：用户忽略了 3 条 PENDING_REVIEW 条目，滞留 180 天无人审核。
>
> **当前行为**：V16 已决策「永久保留」——不自动修剪也不自动降级。
>
> **潜在问题**：审核队列永远阻塞，知识质量取决于人的注意力。
>
> **V1.1 决策**：Phase 1 保持 V16 的「永久保留」策略（人工审核权优先）。Phase 2 可考虑增加超长 TTL（如 365 天未审→降级 DRAFT + 二次告警），但 Phase 1 不实现。

### 10.8 热后冷知识无下降路径（V35 — V1.1 已修补）

> **场景**（来自场景 3 走查）：知识 X（used_count=15, last_used_at=155 天前, code_verified=1）
>
> **V1.0 行为**：used_count≥3 → T11 不触发 → 永远 ACTIVE。靠「历史荣耀」护身的僵尸。
>
> **V1.1 修补**：T11 条件改为 `used_count < 3 OR last_used_at > 90d`。知识 X 的 last_used_at=155d → 触发 T11 → COLD → 总保护期 365d+90d 缓冲 → ~575d 后触发 T16 → DEPRECATED。

---

## 十一、决策矩阵（全部已确认 ✅）

| # | 决策点 | 确认值 | 状态 |
|:--:|--------|:-----:|:----:|
| D1 | 软上限数量 | 500 条 | ✅ 已确认 |
| D2 | 硬上限数量 | 2000 条 | ✅ 已确认 |
| D3 | T25 修剪阈值 | prune_priority ≥ 0.70 | ✅ 已确认 |
| D4 | T11-b 冷窗口 | cold_duration_days > 365d | ✅ 已确认（V28 修正） |
| D5 | T22 DRAFT 长尾窗口 | 90 天 | ✅ 已确认（兜底规则） |
| D6 | T23 STAGED 评估警告 | 14 天 | ✅ 已确认（2 次调度周期） |
| D7 | low_quality / stale_draft 清理窗口 | 14 天 | ✅ 已确认 |
| D8 | 修剪频率 | 7 天 | ✅ 已确认（Step 6 auto-dream 同步） |
| D9 | 废弃「archived」概念 | Y | ✅ 已确认（COLD + STALE 替代） |

### 新增决策（V1.1 修补确定）

| # | 决策点 | 确认值 | 说明 |
|:--:|--------|:-----:|------|
| D10 | T25 最小 age 保护 | **60 天** | V25 修补——新知识不被过早修剪 |
| D11 | T11 COLD 条件 | **used<3 OR last_used>90d** | V35 修补——热后冷知识有下降路径 |
| D12 | T11-b age 语义 | **cold_duration_days** | V28 修补——自进入 COLD 以来的天数 |
| D13 | T14/T25 执行顺序 | **T14 优先，命中即跳过 T25** | V27 修补——flag 归属明确 |
| D14 | T24 下限保护 | **max(ceil(20%), min(10, N)), 至少 1 条** | V31 修补——COLD 很少时也有意义 |
| D15 | 硬上限 DRAFT 保护 | **保留 used_count=0 条件** | V29 修补——有使用记录的 DRAFT 不被紧急删除 |
| D16 | 硬上限第 2 条 | **删除** | V30 修补——与 T11-b/T25 完全重叠 |
| D17 | T19 used_count=0 | **移除冗余条件（标注）** | V26 修补——staging/ 中始终为 0 |

> 确认日期：2026-06-16。所有参数 Phase 1 落地后根据实际运行数据再评估调整。

---

## 十二、完整跃迁规则汇总（晋升 + 修剪）— V1.1

为便于后续编码实现，将所有跃迁规则（晋升生命周期 22 条 + 修剪 5 条 + 告警 1 条）汇总：

| # | 从 → 到 | 分类 | 触发 | 触发点 | 自动化 |
|:--:|---------|:---:|------|:------:|:-----:|
| T1 | RAW → STAGED | 写入 | confidence<0.95 | Step 5 | 🤖 |
| T2 | RAW → ACTIVE | 写入 | confidence≥0.95 | Step 5 | 🤖 |
| T3 | STAGED → CANDIDATE | 晋升 | score≥0.82 | Step 6 | 🤖 |
| T4 | STAGED → PENDING_REVIEW | 晋升 | 0.65≤score<0.80 | Step 6 | 🤖 |
| T5 | STAGED → DRAFT | 晋升 | score<0.65 | Step 6 | 🤖 |
| T6 | CANDIDATE → ACTIVE | 晋升 | 锁定首轮 score≥0.80 | Step 6 | 🤖 |
| T7 | PENDING_REVIEW → ACTIVE | 晋升 | 人工确认 | dev review | 👤 |
| T8 | PENDING_REVIEW → DEPRECATED | 晋升 | 人工拒绝 | dev review | 👤 |
| T9 | DRAFT → ACTIVE | 晋升 | 人工确认 | dev review | 👤 |
| T10 | DRAFT → DEPRECATED | 晋升 | 人工拒绝 | dev review | 👤 |
| **T11** | **ACTIVE → COLD** | **修剪** | **code_verified=1, (used<3 OR last_used>90d) V35** | **修剪扫描** | **🤖** |
| **T11-b** | **COLD → STALE(suspicious)** | **修剪** | **used=0, cold_duration_days>365d V28** | **修剪扫描** | **🤖** |
| T12 | ACTIVE → STALE(suspicious) | 校验 | INCONSISTENT+低确定度 | Step 3 | 🤖 |
| T13 | COLD → STALE(suspicious) | 校验 | code_verified→0 | Step 3 | 🤖 |
| T14 | ACTIVE → STALE(suspicious) | 修剪 | code_verified=0, age>90d | 修剪扫描 | 🤖 |
| T15 | STALE(any) → ACTIVE | 校验 | 重新校验通过 | Step 3 | 🤖 |
| T16 | STALE(deep) → DEPRECATED | 修剪 | 累积3次/超90d | 修剪扫描 | 🤖 |
| T17 | ACTIVE → DEPRECATED | 冲突 | 冲突裁决失败 | Step 4 | 🤖 |
| T18 | ACTIVE → DEPRECATED | 校验 | INCONSISTENT+高确定度 | Step 3 | 🤖 |
| **T19** | **DRAFT → DEPRECATED** | **修剪** | **conf<0.6, age>30d V26** | **修剪扫描** | **🤖** |
| T20 | DEPRECATED → STAGED | 恢复 | 人工恢复 | dev review | 👤 |
| T21 | DEPRECATED → 删除 | 清理 | age≥30d(14d) | 清理 | 🤖 |
| T22 | DRAFT → DEPRECATED | 修剪 | age>90d | 修剪扫描 | 🤖 |
| T23 | STAGED → 警告 | 告警 | age>14d 未评估 | 修剪扫描 | 🤖 |
| **T24** | **COLD → 建议列表** | **告警 V33** | **软上限+最低20%** | **修剪扫描** | **🤖** |
| **T25** | **ACTIVE → STALE(suspicious)** | **修剪** | **prune_priority≥0.70, age≥60d V25** | **修剪扫描** | **🤖** |

**总计**：28 条规则（晋升 12 + 修剪 11 + 校验 3 + 冲突 1 + **告警 2**）
> V1.1 变更（以 **粗体** 标注）：T11/T11-b/T19/T25 的条件修正；T24 从「修剪跃迁」改为「告警」（V33）；新增告警分类。

**T14/T25 执行顺序（V27+V34）**：
```
修剪扫描中，按以下顺序检查：
  → T14 先检查（code_verified=0, age>90d）
    若命中 → 标记 STALE(suspicious), flag='unverified_for_long'，跳过 T25
  → T25 补充检查（T14 未命中的条目）
    条件: code_verified=0, prune_priority≥0.70, age≥60d
    命中 → 标记 STALE(suspicious), flag='low_usage'
```

---

## 十三、下一步

| # | 议题 | 状态 |
|:--:|------|:----:|
| ⑧ | dev review 交互原型 | 待讨论 |
| 🔜 | V2.0 文档同步（T25 汇总 + T21 差异化窗口） | 待执行 |
| 🔜 | 编码实现准备（MVP Phase 1） | 待启动 |
| 🔜 | 端到端走查（V1.1 修补后完整生命周期 × 修剪规则） | 待执行 |

---

## 十四、修订历史

| 版本 | 日期 | 变更 |
|:---:|------|------|
| V1.0 | 2026-06-16 | 初版：三层体系 + 5 条新跃迁 + 27 条规则汇总 + 9 决策确认 |
| V1.1 | 2026-06-16 | 11 项漏洞修补（V25-V35）：T11 热后冷路径、T25 60d 保护、T19 冗余移除、T11-b 语义澄清、T14/T25 执行顺序、硬上限修正、T24 下限保护、分类澄清、Phase 2 预留项 |
