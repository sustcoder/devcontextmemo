"""Unit tests for pruning engine — 3-layer system and capacity management."""

import pytest

from devcontext.core.pruning import (
    DRAFT_CLEANUP_DAYS,
    HARD_LIMIT,
    LOW_USAGE_STALE_DAYS,
    NO_ANCHOR_STALE_DAYS,
    PRUNE_PRIORITY_THRESHOLD,
    SOFT_LIMIT,
    check_capacity,
    evaluate_layer1,
    evaluate_layer2,
    evaluate_layer3,
    should_prune,
)


class TestPruningLayer1:
    """Layer 1: 质量下限 — DRAFT 清理。"""

    def test_draft_over_90_days_deprecated(self):
        result = evaluate_layer1("draft", 95)
        assert result["action"] == "DEPRECATE"

    def test_draft_under_90_days_keep(self):
        result = evaluate_layer1("draft", 45)
        assert result["action"] == "KEEP"

    def test_draft_exactly_90_days_boundary(self):
        result = evaluate_layer1("draft", 90)
        assert result["action"] == "KEEP"

    def test_draft_low_confidence_30_days_deprecated(self):
        """T19: confidence < 0.6 AND age > 30d → low_quality。"""
        result = evaluate_layer1("draft", 35, confidence=0.5)
        assert result["action"] == "DEPRECATE"
        assert result["deprecation_reason"] == "low_quality"

    def test_draft_high_confidence_30_days_keep(self):
        result = evaluate_layer1("draft", 35, confidence=0.7)
        assert result["action"] == "KEEP"

    def test_non_draft_not_affected(self):
        for status in ["staged", "candidate", "active", "cold", "stale"]:
            result = evaluate_layer1(status, 200)
            assert result["action"] == "KEEP"


class TestPruningLayer2:
    """Layer 2: 使用频率。"""

    def test_cold_over_365_days_stale(self):
        result = evaluate_layer2("cold", 400)
        assert result["action"] == "MARK_STALE"

    def test_cold_under_365_days_keep(self):
        result = evaluate_layer2("cold", 200)
        assert result["action"] == "KEEP"

    def test_high_prune_priority_triggers_stale(self):
        result = evaluate_layer2("cold", 10, prune_priority=0.75)
        assert result["action"] == "MARK_STALE"

    def test_active_with_anchor_low_usage_to_cold(self):
        """T11: active + code_verified=1 + 未使用 → cold。"""
        result = evaluate_layer2("active", None, code_verified=1)
        assert result["action"] == "MARK_COLD"

    def test_active_with_anchor_recent_usage_keep(self):
        result = evaluate_layer2("active", 10, code_verified=1)
        assert result["action"] == "KEEP"


class TestPruningLayer3:
    """Layer 3: 代码锚点。"""

    def test_no_anchor_over_90_days_suspicious(self):
        """T14: 无锚点 + age > 90d → STALE(suspicious)。"""
        result = evaluate_layer3("active", False, 95, age_days=95)
        assert result["action"] == "MARK_STALE"
        assert result["sub_stage"] == "suspicious"
        assert result["flag"] == "unverified_for_long"

    def test_with_anchor_not_pruned(self):
        result = evaluate_layer3("active", True, 200, age_days=200)
        assert result["action"] == "KEEP"

    def test_under_90_days_not_pruned(self):
        result = evaluate_layer3("active", False, 45, age_days=45)
        assert result["action"] == "KEEP"

    def test_t25_low_usage_suspicious(self):
        """T25: 无锚点 + prune_priority≥0.70 + age≥60d → STALE。"""
        result = evaluate_layer3("active", False, 65, age_days=65, prune_priority=0.75)
        assert result["action"] == "MARK_STALE"
        assert result["flag"] == "low_usage"

    def test_t14_priority_over_t25(self):
        """T14 优先于 T25（age > 90d 时 T14 先命中）。"""
        result = evaluate_layer3("active", False, 100, age_days=100, prune_priority=0.80)
        assert result["action"] == "MARK_STALE"
        assert result["flag"] == "unverified_for_long"  # T14 的 flag


class TestCapacityManagement:
    """容量管理。"""

    def test_under_soft_limit_normal(self):
        result = check_capacity(300)
        assert result["action"] == "NORMAL"
        assert result["warning"] is False

    def test_soft_limit_warning(self):
        result = check_capacity(520)
        assert result["action"] == "WARN"
        assert result["warning"] is True

    def test_hard_limit_force_prune(self):
        result = check_capacity(2100)
        assert result["action"] == "FORCE_PRUNE"
        assert result["warning"] is True

    def test_exactly_soft_limit_warns(self):
        result = check_capacity(SOFT_LIMIT)
        assert result["action"] == "WARN"

    def test_exactly_hard_limit_force_prune(self):
        result = check_capacity(HARD_LIMIT)
        assert result["action"] == "FORCE_PRUNE"


class TestSupplementProtection:
    """Supplement 保护。"""

    def test_supplement_parent_protected(self):
        result = should_prune("cold", 500, has_supplements=True)
        assert result is False

    def test_no_supplement_can_prune(self):
        result = should_prune("cold", 500, has_supplements=False)
        assert result is True

    def test_supplement_protects_from_layer1(self):
        result = should_prune("draft", 100, has_supplements=True,
                               days_since_created=100, confidence=0.5)
        assert result is False
