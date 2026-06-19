"""晋升评估 — V2.1 公式 + 滞回机制 + STALE 子阶段。

公式（V2.1 修宪 — 2026-06-17）：
    promotion_score = confidence × 0.70 + anchor_bonus × 0.15 + calibration_recency × 0.15

    anchor_bonus:
        if code_verified == 1: anchor_bonus = 1.0
        else: anchor_bonus = 0.0

    calibration_recency = 1.0 - min(days_since_last_calibration / 180, 1.0)

滞回机制（V21 修补）：
    CANDIDATE 进入门槛 0.82，退出门槛 0.80（0.02 缓冲区防震荡）

STALE 子阶段（V20 修补）：
    suspicious (count=1) → confidence × 0.80
    confirmed  (count=2) → confidence × 0.60
    deep       (count=3) → confidence × 0.40 → 触发 T16 废弃

绿色通道（T2）：
    confidence ≥ 0.95 → 直接 ACTIVE（Step 5 写入时判断，与评分公式独立）

设计依据：``docs/devContextMemo-晋升生命周期-设计-V2.0.md``
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# V2.1 公式权重
W_CONFIDENCE = 0.70
W_ANCHOR_BONUS = 0.15
W_CALIBRATION_RECENCY = 0.15

# 滞回阈值（V21）
CANDIDATE_ENTER_THRESHOLD = 0.82
CANDIDATE_EXIT_THRESHOLD = 0.80
PENDING_REVIEW_LOWER = 0.65

# 绿色通道阈值（T2）
GREEN_CHANNEL_THRESHOLD = 0.95

# STALE 子阶段置信度折扣（V19 累积模型）
STALE_DISCOUNTS = {1: 0.80, 2: 0.60, 3: 0.40}

# 校准时效窗口（天）
CALIBRATION_WINDOW_DAYS = 180


def calculate_base_score(
    confidence: float,
    anchor_bonus: float,
    calibration_recency: float,
) -> float:
    """计算 V2.1 晋升评分。

    Args:
        confidence: LLM 置信度 0.0-1.0。
        anchor_bonus: 代码锚点加分（code_verified=1 → 1.0，否则 0.0）。
        calibration_recency: 校准时效 0.0-1.0。

    Returns:
        晋升评分 0.0-1.0。

    Raises:
        ValueError: 参数超出 [0, 1] 范围。
    """
    for name, val in [
        ("confidence", confidence),
        ("anchor_bonus", anchor_bonus),
        ("calibration_recency", calibration_recency),
    ]:
        if not (0.0 <= val <= 1.0):
            raise ValueError(f"{name} must be in [0, 1], got {val}")
    return (
        confidence * W_CONFIDENCE
        + anchor_bonus * W_ANCHOR_BONUS
        + calibration_recency * W_CALIBRATION_RECENCY
    )


def compute_calibration_recency(
    last_calibrated_at: str | dt.datetime | None,
    now: dt.datetime | None = None,
) -> float:
    """计算校准时效。

    校准时效 = 1.0 - min(days_since_last_calibration / 180, 1.0)
    从未校准 → 0.0；刚刚校准 → ≈1.0。

    Args:
        last_calibrated_at: 最后校准时间（ISO 8601 字符串/datetime/None）。
        now: 当前时间（测试用），None 则用当前时间。

    Returns:
        校准时效 0.0-1.0。
    """
    if last_calibrated_at is None:
        return 0.0
    if now is None:
        now = dt.datetime.now(dt.UTC)
    if isinstance(last_calibrated_at, str):
        last_calibrated_at = dt.datetime.fromisoformat(last_calibrated_at.replace("Z", "+00:00"))
    if last_calibrated_at.tzinfo is None:
        last_calibrated_at = last_calibrated_at.replace(tzinfo=dt.UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.UTC)
    days_since = (now - last_calibrated_at).days
    return 1.0 - min(max(days_since, 0) / CALIBRATION_WINDOW_DAYS, 1.0)


def compute_anchor_bonus(code_verified: int) -> float:
    """计算代码锚点加分。

    Args:
        code_verified: 0 或 1。

    Returns:
        1.0（有锚点）或 0.0（无锚点）。
    """
    return 1.0 if code_verified == 1 else 0.0


def evaluate_promotion(
    base_score: float,
    current_status: str,
    confidence: float | None = None,
    locked_score: float | None = None,
) -> dict[str, Any]:
    """评估单条知识的晋升决策。

    根据 V2.0 跃迁规则 T3/T4/T5/T6 判断新状态。

    Args:
        base_score: V2.1 公式计算的评分。
        current_status: 当前状态（staged/candidate/pending_review/draft/active 等）。
        confidence: 原始置信度（用于绿色通道判断）。
        locked_score: CANDIDATE 锁定的首轮分数（T6 二次确认用）。

    Returns:
        决策结果 dict：
        - ``new_status``: 新状态
        - ``green_channel``: 是否触发绿色通道
        - ``transition``: 跃迁编号（T2/T3/T4/T5/T6/None）
        - ``should_move_file``: 是否需要移动文件
        - ``reason``: 决策原因
    """
    result: dict[str, Any] = {
        "new_status": current_status,
        "green_channel": False,
        "transition": None,
        "should_move_file": False,
        "reason": "",
    }

    # 绿色通道（T2）——仅在 staged 且 confidence ≥ 0.95 时触发
    if (
        confidence is not None
        and confidence >= GREEN_CHANNEL_THRESHOLD
        and current_status == "staged"
    ):
        result.update(
            new_status="active",
            green_channel=True,
            transition="T2",
            should_move_file=True,
            reason="green_channel: confidence >= 0.95",
        )
        return result

    # 滞回机制：当前是 CANDIDATE 时
    if current_status == "candidate":
        # T6 优先：有 locked_score → 用锁定分数判断（V23：忽略 time_decay）
        if locked_score is not None:
            if locked_score >= CANDIDATE_EXIT_THRESHOLD:
                result.update(
                    new_status="active",
                    transition="T6",
                    should_move_file=True,
                    reason=f"candidate→active: locked score {locked_score:.3f} >= {CANDIDATE_EXIT_THRESHOLD}",
                )
            else:
                result.update(
                    new_status="pending_review",
                    transition=None,
                    reason=f"candidate→pending_review: locked score {locked_score:.3f} < {CANDIDATE_EXIT_THRESHOLD}",
                )
            return result
        # 无 locked_score：用当前 score 判断滞回
        if base_score < CANDIDATE_EXIT_THRESHOLD:
            result.update(
                new_status="pending_review",
                transition=None,
                reason=f"candidate→pending_review: score {base_score:.3f} < {CANDIDATE_EXIT_THRESHOLD} (hysteresis exit)",
            )
            return result
        # 保留 CANDIDATE（等下次确认或人工）
        result.update(
            reason=f"candidate stays: score {base_score:.3f} >= {CANDIDATE_EXIT_THRESHOLD}"
        )
        return result

    # 首次评估（T3/T4/T5）：仅对 staged 状态
    if current_status == "staged":
        if base_score >= CANDIDATE_ENTER_THRESHOLD:
            result.update(
                new_status="candidate",
                transition="T3",
                reason=f"staged→candidate: score {base_score:.3f} >= {CANDIDATE_ENTER_THRESHOLD}",
            )
        elif base_score >= PENDING_REVIEW_LOWER:
            result.update(
                new_status="pending_review",
                transition="T4",
                reason=f"staged→pending_review: {PENDING_REVIEW_LOWER} <= score {base_score:.3f} < {CANDIDATE_EXIT_THRESHOLD}",
            )
        else:
            result.update(
                new_status="draft",
                transition="T5",
                reason=f"staged→draft: score {base_score:.3f} < {PENDING_REVIEW_LOWER}",
            )

    return result


def evaluate_stale_transition(
    current_stale_count: int,
    current_confidence: float,
    original_confidence: float,
) -> dict[str, Any]:
    """评估 STALE 子阶段跃迁（T12→T16 路径）。

    STALE 置信度累积折扣（V19）：
        suspicious (count=1) → ×0.80
        confirmed  (count=2) → ×0.60
        deep       (count=3) → ×0.40 → 触发 T16 废弃

    Args:
        current_stale_count: 当前 stale_check_count（0/1/2）。
        current_confidence: 当前 confidence 值。
        original_confidence: 原始 confidence 值（恢复时用）。

    Returns:
        决策结果 dict：
        - ``new_stale_count``: 新的 stale_check_count
        - ``new_sub_phase``: 新子阶段（suspicious/confirmed/deep）
        - ``new_confidence``: 折扣后的 confidence
        - ``should_deprecate``: 是否触发 T16 废弃
    """
    new_count = current_stale_count + 1
    discount = STALE_DISCOUNTS.get(new_count, 0.40)
    new_confidence = original_confidence * discount
    should_deprecate = new_count >= 3

    if new_count == 1:
        sub_phase = "suspicious"
    elif new_count == 2:
        sub_phase = "confirmed"
    else:
        sub_phase = "deep"

    return {
        "new_stale_count": new_count,
        "new_sub_phase": sub_phase,
        "new_confidence": round(new_confidence, 4),
        "should_deprecate": should_deprecate,
    }


def restore_from_stale(original_confidence: float) -> dict[str, Any]:
    """STALE → ACTIVE 恢复（T15）。

    Args:
        original_confidence: 恢复到的原始 confidence 值。

    Returns:
        恢复结果 dict：
        - ``new_status``: "active"
        - ``new_confidence``: 原始 confidence
        - ``new_stale_count``: 0（重置）
        - ``new_sub_phase``: None
    """
    return {
        "new_status": "active",
        "new_confidence": original_confidence,
        "new_stale_count": 0,
        "new_sub_phase": None,
    }
