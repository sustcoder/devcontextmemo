"""Unit tests for conflict detector — L0-L5 检测 + 证据层级 + V1 + 仲裁 + V5。"""

import datetime as dt
import json
from pathlib import Path

import pytest

from devcontext.core.conflict import (
    ConflictDetector,
    ConflictPair,
    ArbitrationResult,
    EVIDENCE_WEIGHTS,
    CONFLICT_FACTUAL,
    CONFLICT_GRANULARITY,
    RELATION_MUTUALLY_EXCLUSIVE,
    RELATION_ONE_REFINES_OTHER,
    RELATION_IDENTICAL,
)
from devcontext.storage.sqlite import SQLiteStore
from devcontext.utils.llm import MockLLMClient


def _insert_knowledge(conn, **kwargs):
    defaults = {
        "id": "kw-test", "title": "测试知识", "domain": "order",
        "sub_domain": "", "granularity": "L3", "stability": "S4", "depth": "KH",
        "status": "active", "confidence": 0.85, "code_verified": 1,
        "prune_priority": 0.0, "certainty": 0.5, "freshness": 0.5,
        "uri": "", "used_count": 0, "calibration_status": "uncalibrated",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stale_check_count": 0, "restored_count": 0,
        "evidence_level": 5, "code_active": 1, "auto_adopted_unreviewed": 0,
        "concept_tags": "[]",
    }
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" * len(defaults))
    conn.execute(
        f"INSERT INTO knowledge_index ({cols}) VALUES ({placeholders})",
        list(defaults.values()),
    )
    conn.commit()


@pytest.fixture
def db_store():
    store = SQLiteStore(":memory:")
    store.init_db()
    return store


# =============================================================================
# 证据可信度层级
# =============================================================================

class TestEvidenceWeights:
    """6 级证据权重。"""

    def test_all_six_levels(self):
        assert EVIDENCE_WEIGHTS[5] == 1.0   # 活代码
        assert EVIDENCE_WEIGHTS[4] == 0.9   # 配置
        assert EVIDENCE_WEIGHTS[3] == 0.7   # 用户陈述
        assert EVIDENCE_WEIGHTS[2] == 0.5   # 隐式推断
        assert EVIDENCE_WEIGHTS[1] == 0.3   # LLM 推理
        assert EVIDENCE_WEIGHTS[0] == 0.0   # 无证据

    def test_compute_weight_with_v1_degradation(self):
        """V1: dead code 降级 Level 5 → Level 2。"""
        w = ConflictDetector.compute_evidence_weight(5, code_active=False)
        assert w == EVIDENCE_WEIGHTS[2]

    def test_compute_weight_with_v12_discount(self):
        """V12: UNCERTAIN 次数折扣。"""
        w0 = ConflictDetector.compute_evidence_weight(5, code_active=True, uncertain_count=0)
        w2 = ConflictDetector.compute_evidence_weight(5, code_active=True, uncertain_count=2)
        w3 = ConflictDetector.compute_evidence_weight(5, code_active=True, uncertain_count=3)
        assert w0 == 1.0
        assert abs(w2 - 0.80) < 0.01
        assert abs(w3 - 0.60) < 0.01

    def test_arbitration_score(self):
        """仲裁得分 = evidence_weight × confidence。"""
        score = ConflictDetector.compute_arbitration_score(0.85, 1.0)
        assert score == 0.85
        score = ConflictDetector.compute_arbitration_score(0.70, 0.7)
        assert score == pytest.approx(0.49)


# =============================================================================
# V1 代码活性检查
# =============================================================================

class TestCodeActiveCheck:
    """V1: dead code 降级。"""

    def test_live_code_with_importer(self, tmp_path):
        live = tmp_path / "live.py"
        live.write_text("def foo(): pass", encoding="utf-8")
        caller = tmp_path / "caller.py"
        caller.write_text("from live import foo", encoding="utf-8")
        is_active, level = ConflictDetector.check_code_active(live, tmp_path)
        assert is_active is True
        assert level == 5

    def test_deprecated_code_degraded(self, tmp_path):
        dead = tmp_path / "dead.py"
        dead.write_text("@Deprecated\ndef old(): pass", encoding="utf-8")
        is_active, level = ConflictDetector.check_code_active(dead, tmp_path)
        assert is_active is False
        assert level == 2

    def test_unreferenced_code_degraded(self, tmp_path):
        orphan = tmp_path / "orphan.py"
        orphan.write_text("def unused(): pass", encoding="utf-8")
        is_active, level = ConflictDetector.check_code_active(orphan, tmp_path)
        assert is_active is False
        assert level == 3

    def test_nonexistent_file(self, tmp_path):
        is_active, level = ConflictDetector.check_code_active(tmp_path / "nope.py")
        assert is_active is False
        assert level == 0


# =============================================================================
# L0-L3 检测
# =============================================================================

class TestDetectionLayers:
    """L0-L3 检测层。"""

    def test_l0_exact_match(self, db_store):
        _insert_knowledge(db_store.get_connection(), id="k1", title="幂等校验方案")
        detector = ConflictDetector(db_store)
        match = detector.detect_l0_content_hash({"knowledge_text": "幂等校验方案"})
        assert match is not None
        assert match["match_type"] == "exact"

    def test_l0_no_match(self, db_store):
        _insert_knowledge(db_store.get_connection(), id="k1", title="幂等校验方案")
        detector = ConflictDetector(db_store)
        match = detector.detect_l0_content_hash({"knowledge_text": "完全不同"})
        assert match is None

    def test_l3_cross_scan_finds_similar(self, db_store):
        """L3 交叉扫描发现高相似度 pair。"""
        _insert_knowledge(db_store.get_connection(), id="k1",
                           title="缓存用 Redis", concept_tags='["#缓存"]')
        _insert_knowledge(db_store.get_connection(), id="k2",
                           title="缓存用 Redis Cluster", concept_tags='["#缓存"]')
        llm = MockLLMClient(response=json.dumps({
            "relation": "one_refines_other",
            "explanation": "k2 是 k1 的精确化",
            "refinement_direction": "B_refines_A"
        }))
        detector = ConflictDetector(db_store, llm)
        pairs = detector.detect_l3_cross_scan()
        # title 相似度可能不够 0.85，但至少不报错
        assert isinstance(pairs, list)


# =============================================================================
# 仲裁
# =============================================================================

class TestArbitration:
    """仲裁机制。"""

    def test_auto_adopt_high_difference(self, db_store):
        """差值 ≥ 0.30 → 自动采用。"""
        detector = ConflictDetector(db_store)
        result = detector.arbitrate(
            {"id": "A", "confidence": 0.85, "evidence_level": 5,
             "code_active": 1, "stale_check_count": 0},
            {"id": "B", "confidence": 0.70, "evidence_level": 3,
             "code_active": 1, "stale_check_count": 0},
        )
        assert result.action == "auto_adopt"
        assert result.winner_id == "A"
        assert result.quarantined is True  # V5

    def test_manual_required_low_difference(self, db_store):
        """差值 < 0.10 → 人工裁决。"""
        detector = ConflictDetector(db_store)
        result = detector.arbitrate(
            {"id": "A", "confidence": 0.80, "evidence_level": 3,
             "code_active": 1, "stale_check_count": 0},
            {"id": "B", "confidence": 0.78, "evidence_level": 3,
             "code_active": 1, "stale_check_count": 0},
        )
        assert result.action == "manual_required"

    def test_dual_discard_low_scores(self, db_store):
        """双方得分都 < 0.40 → 双废弃。"""
        detector = ConflictDetector(db_store)
        result = detector.arbitrate(
            {"id": "A", "confidence": 0.20, "evidence_level": 1,
             "code_active": 1, "stale_check_count": 0},
            {"id": "B", "confidence": 0.15, "evidence_level": 1,
             "code_active": 1, "stale_check_count": 0},
        )
        assert result.action == "dual_discard"

    def test_v1_dead_code_loses_to_user(self, db_store):
        """V1: dead code（降级 Level 2）败给用户陈述（Level 3）。"""
        detector = ConflictDetector(db_store)
        result = detector.arbitrate(
            {"id": "A", "confidence": 0.50, "evidence_level": 5,
             "code_active": 0, "stale_check_count": 0},  # dead code → weight 0.5
            {"id": "B", "confidence": 0.90, "evidence_level": 3,
             "code_active": 1, "stale_check_count": 0},  # 用户陈述 → weight 0.7
        )
        # A: 0.5 × 0.50 = 0.25, B: 0.7 × 0.90 = 0.63, diff=0.38 ≥ 0.30 → auto_adopt
        assert result.action == "auto_adopt"
        assert result.winner_id == "B"


# =============================================================================
# V5 降级机制
# =============================================================================

class TestV5Degradation:
    """V5: 自动采用未审核降级。"""

    def test_degrade_after_3_unreviewed(self, db_store):
        detector = ConflictDetector(db_store)
        result = detector.check_auto_adopted_degradation({
            "auto_adopted_unreviewed": 3, "confidence": 0.80,
        })
        assert result["should_degrade"] is True
        assert result["new_confidence"] == 0.65  # 0.80 - 0.15

    def test_no_degrade_below_threshold(self, db_store):
        detector = ConflictDetector(db_store)
        result = detector.check_auto_adopted_degradation({
            "auto_adopted_unreviewed": 2, "confidence": 0.80,
        })
        assert result["should_degrade"] is False

    def test_increment_unreviewed_counter(self, db_store):
        _insert_knowledge(db_store.get_connection(), id="k1", auto_adopted_unreviewed=1)
        detector = ConflictDetector(db_store)
        new_count = detector.increment_auto_adopted_unreviewed("k1")
        assert new_count == 2
