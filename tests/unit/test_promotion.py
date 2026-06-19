"""Unit tests for promotion engine — V2.1 formula and hysteresis rules."""

import datetime as dt

import pytest

from devcontext.core.promotion import (
    CANDIDATE_ENTER_THRESHOLD,
    CANDIDATE_EXIT_THRESHOLD,
    GREEN_CHANNEL_THRESHOLD,
    W_ANCHOR_BONUS,
    W_CALIBRATION_RECENCY,
    W_CONFIDENCE,
    calculate_base_score,
    compute_anchor_bonus,
    compute_calibration_recency,
    evaluate_promotion,
    evaluate_stale_transition,
    restore_from_stale,
)


class TestPromotionFormula:
    """base_score = confidence × 0.70 + anchor_bonus × 0.15 + calibration_recency × 0.15"""

    def test_max_score_all_perfect(self):
        score = calculate_base_score(1.0, 1.0, 1.0)
        assert score == pytest.approx(1.0)

    def test_min_score_all_zero(self):
        score = calculate_base_score(0.0, 0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_mid_range_values(self):
        score = calculate_base_score(0.85, 1.0, 0.5)
        expected = 0.85 * 0.70 + 1.0 * 0.15 + 0.5 * 0.15
        assert score == pytest.approx(expected)

    def test_confidence_dominates_score(self):
        high_conf = calculate_base_score(0.95, 0.0, 0.0)
        low_conf = calculate_base_score(0.50, 1.0, 1.0)
        assert high_conf > low_conf

    def test_no_anchor_max_score_capped(self):
        """无锚点 max = 0.85（0.70 + 0 + 0.15）。"""
        score = calculate_base_score(1.0, 0.0, 1.0)
        assert score == pytest.approx(0.85)

    def test_calibrated_old_beats_uncalibrated_new(self):
        """校准过的旧知识 > 未校准的新知识（诉求②）。"""
        score_a = calculate_base_score(0.85, 0.0, 1.0 - 9 / 180)
        score_b = calculate_base_score(0.85, 0.0, 0.0)
        assert score_a > score_b

    def test_negative_confidence_rejected(self):
        with pytest.raises(ValueError):
            calculate_base_score(-0.1, 0.0, 0.0)

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValueError):
            calculate_base_score(1.5, 0.0, 0.0)


class TestCalibrationRecency:
    """校准时效计算。"""

    def test_never_calibrated_is_zero(self):
        assert compute_calibration_recency(None) == 0.0

    def test_recently_calibrated_high(self):
        recent = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        assert compute_calibration_recency(recent) > 0.99

    def test_old_calibration_low(self):
        old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=200)
        assert compute_calibration_recency(old) == 0.0

    def test_calibrated_yesterday(self):
        yesterday = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
        recency = compute_calibration_recency(yesterday)
        assert recency == pytest.approx(1.0 - 1 / 180)


class TestAnchorBonus:
    """代码锚点加分。"""

    def test_with_anchor(self):
        assert compute_anchor_bonus(1) == 1.0

    def test_without_anchor(self):
        assert compute_anchor_bonus(0) == 0.0


class TestPromotionHysteresis:
    """CANDIDATE 滞回：0.82 进 / 0.80 出。"""

    def test_staged_to_candidate_at_threshold(self):
        result = evaluate_promotion(CANDIDATE_ENTER_THRESHOLD, "staged")
        assert result["new_status"] == "candidate"
        assert result["transition"] == "T3"

    def test_staged_to_candidate_above_threshold(self):
        result = evaluate_promotion(0.90, "staged")
        assert result["new_status"] == "candidate"

    def test_staged_to_pending_review_mid_range(self):
        result = evaluate_promotion(0.70, "staged")
        assert result["new_status"] == "pending_review"
        assert result["transition"] == "T4"

    def test_staged_to_draft_low_score(self):
        result = evaluate_promotion(0.50, "staged")
        assert result["new_status"] == "draft"
        assert result["transition"] == "T5"

    def test_candidate_stays_at_81(self):
        """0.81 >= 0.80 → 保留 candidate（滞回）。"""
        result = evaluate_promotion(0.81, "candidate")
        assert result["new_status"] == "candidate"

    def test_candidate_drops_below_exit(self):
        """0.79 < 0.80 → 回退 pending_review。"""
        result = evaluate_promotion(0.79, "candidate")
        assert result["new_status"] == "pending_review"

    def test_candidate_to_active_with_locked_score(self):
        """T6: 有 locked_score >= 0.80 → active。"""
        result = evaluate_promotion(0.78, "candidate", locked_score=0.83)
        assert result["new_status"] == "active"
        assert result["transition"] == "T6"

    def test_candidate_locked_score_below_exit(self):
        """T6: locked_score < 0.80 → 回退。"""
        result = evaluate_promotion(0.85, "candidate", locked_score=0.78)
        assert result["new_status"] == "pending_review"


class TestGreenChannel:
    """绿色通道（T2）。"""

    def test_green_channel_high_confidence(self):
        result = evaluate_promotion(0.90, "staged", confidence=0.96)
        assert result["new_status"] == "active"
        assert result["green_channel"] is True
        assert result["transition"] == "T2"

    def test_no_green_channel_below_threshold(self):
        result = evaluate_promotion(0.90, "staged", confidence=0.94)
        assert result["green_channel"] is False


class TestStaleSubPhase:
    """STALE 子阶段累积折扣。"""

    def test_suspicious_first_entry(self):
        result = evaluate_stale_transition(0, 0.80, 0.80)
        assert result["new_stale_count"] == 1
        assert result["new_sub_phase"] == "suspicious"
        assert abs(result["new_confidence"] - 0.64) < 0.01
        assert result["should_deprecate"] is False

    def test_confirmed_second_entry(self):
        result = evaluate_stale_transition(1, 0.64, 0.80)
        assert result["new_stale_count"] == 2
        assert result["new_sub_phase"] == "confirmed"
        assert abs(result["new_confidence"] - 0.48) < 0.01
        assert result["should_deprecate"] is False

    def test_deep_triggers_deprecate(self):
        result = evaluate_stale_transition(2, 0.48, 0.80)
        assert result["new_stale_count"] == 3
        assert result["new_sub_phase"] == "deep"
        assert result["should_deprecate"] is True


class TestRestoreFromStale:
    """STALE → ACTIVE 恢复（T15）。"""

    def test_restore_resets_stale_fields(self):
        result = restore_from_stale(0.80)
        assert result["new_status"] == "active"
        assert result["new_confidence"] == 0.80
        assert result["new_stale_count"] == 0
        assert result["new_sub_phase"] is None
