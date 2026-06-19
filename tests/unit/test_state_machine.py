"""状态机测试 — 覆盖 ALLOWED_TRANSITIONS 的全部有效转换和无效转换。

测试策略：
- 遍历 ALLOWED_TRANSITIONS 矩阵，逐条验证有效转换返回 True
- 验证已明确定义的无效转换返回 False
- 验证跨状态无效转换（如 cold→active、draft→staged）返回 False
"""

import pytest

from devcontext.models.enums import (
    ALLOWED_TRANSITIONS,
    KnowledgeStatus,
    is_valid_transition,
)


# =============================================================================
# 有效转换（从 ALLOWED_TRANSITIONS 矩阵自动生成）
# =============================================================================


def _all_allowed_pairs():
    """生成所有 (from_status, to_status) 允许转换对。"""
    pairs = []
    for src, targets in ALLOWED_TRANSITIONS.items():
        for tgt in targets:
            pairs.append((src, tgt))
    return pairs


class TestValidTransitions:
    """覆盖 ALLOWED_TRANSITIONS 中全部有效转换。"""

    @pytest.mark.parametrize(
        "from_status,to_status", _all_allowed_pairs()
    )
    def test_allowed_transition_returns_true(self, from_status, to_status):
        """逐条验证 ALLOWED_TRANSITIONS 中的转换返回 True。"""
        assert is_valid_transition(from_status, to_status) is True, (
            f"Expected {from_status}→{to_status} to be valid"
        )


# =============================================================================
# 显式无效转换
# =============================================================================


_INVALID_PAIRS = [
    # 跨级跳跃（禁止）
    ("draft", "staged"),
    ("cold", "active"),
    ("staged", "cold"),
    ("candidate", "cold"),
    ("pending_review", "cold"),
    ("draft", "cold"),
    ("active", "candidate"),
    ("active", "pending_review"),
    ("active", "draft"),
    ("pending_review", "candidate"),
    ("pending_review", "draft"),
    ("draft", "candidate"),
    ("draft", "pending_review"),
    ("cold", "candidate"),
    ("cold", "pending_review"),
    ("cold", "draft"),
    ("stale", "candidate"),
    ("stale", "pending_review"),
    ("stale", "draft"),
    ("stale", "cold"),
    # deprecated 仅可回 staged
    ("deprecated", "active"),
    ("deprecated", "candidate"),
    ("deprecated", "pending_review"),
    ("deprecated", "draft"),
    ("deprecated", "cold"),
    ("deprecated", "stale"),
    # candidate 不可回 staged
    ("candidate", "staged"),
    # pending_review 不可回 staged
    ("pending_review", "staged"),
    # active 不可回 staged
    ("active", "staged"),
]


class TestInvalidTransitions:
    """验证明确禁止的转换返回 False。"""

    @pytest.mark.parametrize("from_status,to_status", _INVALID_PAIRS)
    def test_invalid_transition_returns_false(self, from_status, to_status):
        """逐条验证无效转换返回 False。"""
        assert is_valid_transition(from_status, to_status) is False, (
            f"Expected {from_status}→{to_status} to be INVALID"
        )


# =============================================================================
# 关键路径测试
# =============================================================================


class TestKeyPaths:
    """验证关键生命周期路径的转换正确性。"""

    def test_full_lifecycle_path(self):
        """标准生命周期: staged → candidate → active → stale → deprecated → staged。"""
        assert is_valid_transition("staged", "candidate")
        assert is_valid_transition("candidate", "active")
        assert is_valid_transition("active", "stale")
        assert is_valid_transition("stale", "deprecated")
        assert is_valid_transition("deprecated", "staged")

    def test_green_channel_path(self):
        """绿色通道 (T2): staged → active（confidence ≥ 0.95）。"""
        assert is_valid_transition("staged", "active")

    def test_review_path(self):
        """审核路径: staged → pending_review → active。"""
        assert is_valid_transition("staged", "pending_review")
        assert is_valid_transition("pending_review", "active")

    def test_cold_to_deprecated_path(self):
        """冷却路径: active → cold → stale → deprecated。"""
        assert is_valid_transition("active", "cold")
        assert is_valid_transition("cold", "stale")
        assert is_valid_transition("stale", "deprecated")

    def test_stale_resurrection_path(self):
        """过时复活: stale → active。"""
        assert is_valid_transition("stale", "active")

    def test_draft_to_active_path(self):
        """草稿晋升: draft → active。"""
        assert is_valid_transition("draft", "active")


# =============================================================================
# Writer 初始状态验证
# =============================================================================


class TestWriterInitialStatus:
    """验证 Writer 写入的状态在状态机中是合法的。"""

    def test_candidate_is_valid_initial_status(self):
        """管道自动提取的知识应从 candidate 开始。"""
        assert "candidate" in ALLOWED_TRANSITIONS
        # candidate 可以转为 active
        assert "active" in ALLOWED_TRANSITIONS["candidate"]

    def test_staged_can_reach_active(self):
        """staged 可以通过绿色通道直达 active。"""
        assert "active" in ALLOWED_TRANSITIONS["staged"]


# =============================================================================
# 防御性测试
# =============================================================================


class TestDefensive:
    """边界情况测试。"""

    def test_same_status_is_always_valid(self):
        """同状态转换始终合法。"""
        for s in KnowledgeStatus:
            assert is_valid_transition(s.value, s.value)

    def test_unknown_status_returns_false(self):
        """不存在的状态返回 False。"""
        assert is_valid_transition("imaginary", "active") is False
        assert is_valid_transition("active", "imaginary") is False

    def test_deprecated_cycle(self):
        """deprecated 只能回到 staged，不可自循环到其他。"""
        assert is_valid_transition("deprecated", "staged")
        assert is_valid_transition("deprecated", "deprecated")
        assert not is_valid_transition("deprecated", "active")
        assert not is_valid_transition("deprecated", "candidate")
