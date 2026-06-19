"""修剪规则 — 三层体系 + 容量管理 + supplement 保护。

三层修剪体系（V2.0 + V1.1 修剪规则）：
    Layer 1: 质量下限 — DRAFT > 90 天未处理 → DEPRECATED (T19)
    Layer 2: 使用频率 — COLD > 365 天 → STALE (T11 扩展)；
             prune_priority ≥ 0.70 → STALE
    Layer 3: 代码锚点 — 无锚点 + 90 天未变更 → STALE(suspicious) (T14/T25)

容量管理：
    soft_limit = 500（告警）
    hard_limit = 2000（强制修剪）

Supplement 保护：
    有 supplement 的 parent 知识不被修剪

废弃原因（deprecation_reason）：
    - superseded: 冲突裁决被取代 (T17)
    - verification_failed: 校验累积失败 (T16)
    - direct_contradiction: 高确定度不一致 (T18)
    - low_quality: 低质清理 (T19)
    - human_rejected: 人工拒绝 (T8/T10)

设计依据：``docs/devContextMemo-晋升生命周期-设计-V2.0.md`` §2.1
"""

from __future__ import annotations

from typing import Any

# Layer 1: DRAFT 清理窗口（天）
DRAFT_CLEANUP_DAYS = 90

# Layer 2: COLD → STALE 窗口（天）
COLD_STALE_DAYS = 365

# Layer 2: prune_priority 阈值
PRUNE_PRIORITY_THRESHOLD = 0.70

# Layer 3: 无锚点 STALE 窗口（天）——T14
NO_ANCHOR_STALE_DAYS = 90

# T25: 低使用频率窗口（天）
LOW_USAGE_STALE_DAYS = 60

# 容量限制
SOFT_LIMIT = 500
HARD_LIMIT = 2000


def evaluate_layer1(
    status: str,
    days_since_created: int,
    confidence: float = 1.0,
) -> dict[str, Any]:
    """Layer 1: 质量下限 — DRAFT > 90 天 → DEPRECATED (T19)。

    T19 条件（V16+V26 修补）：
        status == 'draft' AND confidence < 0.6 AND age > 30d
    但 V2.0 §2.1 T19 写的是 age > 30d，而 step6 契约和 test 写的是 90d。
    采用 V2.0 文档的 30d（更精确），但保留 DRAFT_CLEANUP_DAYS=90 作为保守默认。
    实际实现：confidence < 0.6 AND age > 30d → low_quality；
              age > 90d（无论 confidence）→ stale_draft。

    Args:
        status: 当前状态。
        days_since_created: 创建以来的天数。
        confidence: 当前置信度。

    Returns:
        决策结果 dict：
        - ``action``: "DEPRECATE" / "KEEP"
        - ``reason``: 原因
        - ``deprecation_reason``: 废弃原因（low_quality/stale_draft）
    """
    if status != "draft":
        return {"action": "KEEP", "reason": "not draft", "deprecation_reason": None}

    # T19: confidence < 0.6 AND age > 30d → low_quality
    if confidence < 0.6 and days_since_created > 30:
        return {
            "action": "DEPRECATE",
            "reason": "T19: draft confidence<0.6 and age>30d",
            "deprecation_reason": "low_quality",
        }

    # 保守清理：age > 90d → stale_draft
    if days_since_created > DRAFT_CLEANUP_DAYS:
        return {
            "action": "DEPRECATE",
            "reason": f"draft age > {DRAFT_CLEANUP_DAYS}d unprocessed",
            "deprecation_reason": "stale_draft",
        }

    return {"action": "KEEP", "reason": "draft within cleanup window", "deprecation_reason": None}


def evaluate_layer2(
    status: str,
    days_since_last_used: int | None = None,
    prune_priority: float = 0.0,
    code_verified: int = 0,
) -> dict[str, Any]:
    """Layer 2: 使用频率 — COLD > 365 天 → STALE；prune_priority ≥ 0.70 → STALE。

    Args:
        status: 当前状态。
        days_since_last_used: 最后使用以来的天数（None 表示从未使用）。
        prune_priority: 修剪优先级 0.0-1.0。
        code_verified: 代码锚点 0/1。

    Returns:
        决策结果 dict：
        - ``action``: "MARK_STALE" / "MARK_COLD" / "KEEP"
        - ``sub_stage``: STALE 子阶段（suspicious）
        - ``reason``: 原因
    """
    # T11: ACTIVE → COLD（code_verified=1 且低使用）
    if status == "active" and code_verified == 1:
        if (days_since_last_used is not None and days_since_last_used > 90) or (
            days_since_last_used is None
        ):
            return {
                "action": "MARK_COLD",
                "sub_stage": None,
                "reason": "T11: active+anchor but low usage → cold",
            }

    # COLD > 365 天 → STALE
    if status == "cold" and days_since_last_used is not None:
        if days_since_last_used > COLD_STALE_DAYS:
            return {
                "action": "MARK_STALE",
                "sub_stage": "suspicious",
                "reason": f"cold > {COLD_STALE_DAYS}d → stale",
            }

    # prune_priority ≥ 0.70 → STALE（仅对 cold）
    if status == "cold" and prune_priority >= PRUNE_PRIORITY_THRESHOLD:
        return {
            "action": "MARK_STALE",
            "sub_stage": "suspicious",
            "reason": f"prune_priority {prune_priority:.2f} >= {PRUNE_PRIORITY_THRESHOLD}",
        }

    return {"action": "KEEP", "sub_stage": None, "reason": "within limits"}


def evaluate_layer3(
    status: str,
    has_anchor: bool,
    days_unchanged: int,
    age_days: int = 0,
    prune_priority: float = 0.0,
    used_count: int = 0,
) -> dict[str, Any]:
    """Layer 3: 代码锚点 — 无锚点 + 时间/使用触发 → STALE(suspicious)。

    T14: ACTIVE(code_verified=0, age > 90d) → STALE(suspicious)
    T25: ACTIVE(code_verified=0, prune_priority≥0.70, age≥60d) → STALE(suspicious)
    T14 优先于 T25（V27+V34）。

    Args:
        status: 当前状态。
        has_anchor: 是否有代码锚点（code_verified=1）。
        days_unchanged: 未变更天数。
        age_days: 创建以来的天数。
        prune_priority: 修剪优先级。
        used_count: 使用次数。

    Returns:
        决策结果 dict：
        - ``action``: "MARK_STALE" / "KEEP"
        - ``sub_stage``: suspicious
        - ``flag``: 标记（unverified_for_long / low_usage）
        - ``reason``: 原因
    """
    if status != "active" or has_anchor:
        return {
            "action": "KEEP",
            "sub_stage": None,
            "flag": None,
            "reason": "has anchor or not active",
        }

    # T14: 无锚点 + age > 90 天 → STALE(suspicious)（优先检查）
    if age_days > NO_ANCHOR_STALE_DAYS:
        return {
            "action": "MARK_STALE",
            "sub_stage": "suspicious",
            "flag": "unverified_for_long",
            "reason": f"T14: no anchor + age {age_days}d > {NO_ANCHOR_STALE_DAYS}d",
        }

    # T25: 无锚点 + prune_priority ≥ 0.70 + age ≥ 60d
    if age_days >= LOW_USAGE_STALE_DAYS and prune_priority >= PRUNE_PRIORITY_THRESHOLD:
        return {
            "action": "MARK_STALE",
            "sub_stage": "suspicious",
            "flag": "low_usage",
            "reason": f"T25: no anchor + prune_priority {prune_priority:.2f} >= {PRUNE_PRIORITY_THRESHOLD} + age {age_days}d >= {LOW_USAGE_STALE_DAYS}d",
        }

    return {"action": "KEEP", "sub_stage": None, "flag": None, "reason": "within protection window"}


def check_capacity(total_count: int) -> dict[str, Any]:
    """容量管理检查。

    Args:
        total_count: 知识库总条目数。

    Returns:
        决策结果 dict：
        - ``action``: "NORMAL" / "WARN" / "FORCE_PRUNE"
        - ``warning``: 是否告警
        - ``current_count``: 当前数量
        - ``soft_limit``: 软上限
        - ``hard_limit``: 硬上限
    """
    if total_count >= HARD_LIMIT:
        return {
            "action": "FORCE_PRUNE",
            "warning": True,
            "current_count": total_count,
            "soft_limit": SOFT_LIMIT,
            "hard_limit": HARD_LIMIT,
        }
    if total_count >= SOFT_LIMIT:
        return {
            "action": "WARN",
            "warning": True,
            "current_count": total_count,
            "soft_limit": SOFT_LIMIT,
            "hard_limit": HARD_LIMIT,
        }
    return {
        "action": "NORMAL",
        "warning": False,
        "current_count": total_count,
        "soft_limit": SOFT_LIMIT,
        "hard_limit": HARD_LIMIT,
    }


def should_prune(
    status: str,
    days_since_last_used: int | None = None,
    has_supplements: bool = False,
    **kwargs: Any,
) -> bool:
    """综合判断是否应该修剪（含 supplement 保护）。

    Args:
        status: 当前状态。
        days_since_last_used: 最后使用以来的天数。
        has_supplements: 是否有 supplement 子知识。
        **kwargs: 传递给 evaluate_layer1/2/3 的额外参数。

    Returns:
        True 表示应该修剪，False 表示保留。
    """
    # supplement 保护：有补充的 parent 不修剪
    if has_supplements:
        return False

    # Layer 1
    l1 = evaluate_layer1(status, kwargs.get("days_since_created", 0), kwargs.get("confidence", 1.0))
    if l1["action"] == "DEPRECATE":
        return True

    # Layer 2
    l2 = evaluate_layer2(
        status,
        days_since_last_used,
        kwargs.get("prune_priority", 0.0),
        kwargs.get("code_verified", 0),
    )
    if l2["action"] in ("MARK_STALE", "MARK_COLD"):
        return True

    # Layer 3
    l3 = evaluate_layer3(
        status,
        kwargs.get("has_anchor", False),
        kwargs.get("days_unchanged", 0),
        kwargs.get("age_days", 0),
        kwargs.get("prune_priority", 0.0),
        kwargs.get("used_count", 0),
    )
    if l3["action"] == "MARK_STALE":
        return True

    return False
