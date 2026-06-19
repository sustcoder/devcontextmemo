"""Unit tests for state machine invariants and enum validation (V1.1).

适配 V2.0 晋升生命周期 8 态小写状态 + L0-L5 粒度 + devcontext 包路径。
"""

import pytest


class TestKnowledgeStateMachine:
    """State machine invariants — illegal transitions must be rejected (V2.0 T 表)."""

    def test_staged_to_candidate_is_legal(self):
        """staged → candidate 合法（T3 晋升评估）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("staged", "candidate") is True

    def test_staged_to_pending_review_is_legal(self):
        """staged → pending_review 合法（T4 人工审核）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("staged", "pending_review") is True

    def test_staged_to_draft_is_legal(self):
        """staged → draft 合法（T5 低分深入确认）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("staged", "draft") is True

    def test_candidate_to_active_is_legal(self):
        """candidate → active 合法（T6 锁定首轮 score 确认）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("candidate", "active") is True

    def test_candidate_to_pending_review_is_legal(self):
        """candidate → pending_review 合法（T3_exit 滞回回退）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("candidate", "pending_review") is True

    def test_pending_review_to_active_is_legal(self):
        """pending_review → active 合法（T7 人工采纳）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("pending_review", "active") is True

    def test_draft_to_active_is_legal(self):
        """draft → active 合法（T9 人工深入确认采纳）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("draft", "active") is True

    def test_active_to_cold_is_legal(self):
        """active → cold 合法（T11 休眠保护）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("active", "cold") is True

    def test_active_to_stale_is_legal(self):
        """active → stale 合法（T12/T14/T25）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("active", "stale") is True

    def test_cold_to_stale_is_legal(self):
        """cold → stale 合法（T13 锚点断裂）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("cold", "stale") is True

    def test_stale_to_active_is_legal(self):
        """stale → active 合法（T15 重新校验通过）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("stale", "active") is True

    def test_deprecated_to_staged_is_legal(self):
        """deprecated → staged 合法（T20 人工恢复）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("deprecated", "staged") is True

    def test_any_to_deprecated_is_legal(self):
        """任意状态 → deprecated 合法（手动废弃）。"""
        from devcontext.models.enums import is_valid_transition
        for status in ["staged", "candidate", "pending_review", "draft",
                       "active", "cold", "stale"]:
            assert is_valid_transition(status, "deprecated") is True, \
                f"{status} → deprecated should be legal"

    def test_deprecated_to_any_is_illegal(self):
        """deprecated → 非 staged 状态非法（仅可 T20 恢复）。"""
        from devcontext.models.enums import is_valid_transition
        for status in ["candidate", "pending_review", "draft",
                       "active", "cold", "stale"]:
            assert is_valid_transition("deprecated", status) is False, \
                f"deprecated → {status} should be illegal"

    def test_self_transition_is_legal(self):
        """同状态 → 同状态合法（no-op 语义）。"""
        from devcontext.models.enums import is_valid_transition
        for status in ["staged", "candidate", "pending_review", "draft",
                       "active", "cold", "stale", "deprecated"]:
            assert is_valid_transition(status, status) is True, \
                f"{status} → {status} (self) should be legal"

    def test_draft_to_staged_is_illegal(self):
        """draft → staged 非法（V2.0 T 表无此跃迁；draft 仅可→active/deprecated）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("draft", "staged") is False

    def test_cold_to_active_is_illegal(self):
        """cold → active 非法（必须经 cold→stale→active 完整路径，V2.0 T 表）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("cold", "active") is False

    def test_draft_to_candidate_is_illegal(self):
        """draft → candidate 非法（V2.0 T 表无此跃迁）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("draft", "candidate") is False

    def test_draft_to_pending_review_is_illegal(self):
        """draft → pending_review 非法（V2.0 T 表无此跃迁）。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("draft", "pending_review") is False

    def test_unknown_status_is_illegal(self):
        """未知状态值返回 False。"""
        from devcontext.models.enums import is_valid_transition
        assert is_valid_transition("unknown", "active") is False
        assert is_valid_transition("active", "unknown") is False


class TestEnumValidation:
    """Enum value validation for granularity, stability, depth, domain (V1.1)."""

    def test_valid_granularity_values(self):
        """L0-L5 全部合法（V1.1 扩展，原 V1.0 仅 L0-L3）。"""
        from devcontext.models.enums import is_valid_lx
        for val in ["L0", "L1", "L2", "L3", "L4", "L5"]:
            assert is_valid_lx(val) is True, f"{val} should be valid"

    def test_invalid_granularity_values(self):
        """非法粒度值被拒绝。"""
        from devcontext.models.enums import is_valid_lx
        for val in ["L6", "L7", "", "X1", None, "l0", "l5"]:
            assert is_valid_lx(val) is False, f"{val!r} should be invalid"

    def test_valid_stability_values(self):
        """S1-S5 全部合法。"""
        from devcontext.models.enums import is_valid_sy
        for val in ["S1", "S2", "S3", "S4", "S5"]:
            assert is_valid_sy(val) is True, f"{val} should be valid"

    def test_invalid_stability_values(self):
        """非法稳定性值被拒绝。"""
        from devcontext.models.enums import is_valid_sy
        for val in ["S0", "S6", "", None, "s1"]:
            assert is_valid_sy(val) is False, f"{val!r} should be invalid"

    def test_valid_depth_values(self):
        """KW/KH/KY 全部合法。"""
        from devcontext.models.enums import is_valid_depth
        for val in ["KW", "KH", "KY"]:
            assert is_valid_depth(val) is True, f"{val} should be valid"

    def test_invalid_depth_values(self):
        """非法深度值被拒绝。"""
        from devcontext.models.enums import is_valid_depth
        for val in ["KX", "kw", "", None, "KY2"]:
            assert is_valid_depth(val) is False, f"{val!r} should be invalid"

    def test_valid_domain_values(self):
        """domain 在领域树中时合法。"""
        from devcontext.models.enums import is_valid_domain
        domain_tree = {"order": {}, "payment": {}, "user": {}}
        for val in ["order", "payment", "user"]:
            assert is_valid_domain(val, domain_tree) is True

    def test_invalid_domain_values(self):
        """domain 不在领域树中或为空时非法。"""
        from devcontext.models.enums import is_valid_domain
        domain_tree = {"order": {}, "payment": {}}
        for val in ["shopping_cart", "", None]:
            assert is_valid_domain(val, domain_tree) is False


class TestStatusEnum:
    """KnowledgeStatus 枚举完整性。"""

    def test_eight_statuses(self):
        """V1.1 共 8 个状态（V1.0 是 7 个）。"""
        from devcontext.models.enums import KnowledgeStatus
        statuses = list(KnowledgeStatus)
        assert len(statuses) == 8

    def test_status_values_lowercase(self):
        """所有状态值为小写字符串。"""
        from devcontext.models.enums import KnowledgeStatus
        for s in KnowledgeStatus:
            assert s.value == s.value.lower()
            assert s.value == s.value.strip()

    def test_pending_review_exists(self):
        """V1.1 新增 pending_review 状态。"""
        from devcontext.models.enums import KnowledgeStatus
        assert KnowledgeStatus.PENDING_REVIEW.value == "pending_review"

    def test_no_valid_status(self):
        """V1.0 的 valid 状态在 V1.1 中不存在（被 active 取代）。"""
        from devcontext.models.enums import KnowledgeStatus, VALID_STATUSES
        assert "valid" not in VALID_STATUSES
        assert "active" in VALID_STATUSES
