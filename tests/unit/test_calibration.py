"""Unit tests for calibration engine — LLM 语义对比 + V6/V11/V12/V18 修补。"""

import datetime as dt
import json
from pathlib import Path

import pytest

from devcontext.core.calibration import (
    CalibrationEngine,
    CalibrationEvent,
    CalibrationResult,
    CONSISTENT,
    INCONSISTENT,
    UNCERTAIN,
    HIGH_CERTAINTY_THRESHOLD,
    UNCERTAIN_ACCUMULATION_THRESHOLD,
    EVIDENCE_DISCOUNT_BY_UNCERTAIN,
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
        "concept_tags": '["#OrderService"]',
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


@pytest.fixture
def tmp_project(tmp_path):
    """创建临时项目（MD 文件 + 代码文件）。"""
    md_file = tmp_path / "knowledge" / "order" / "test.md"
    md_file.parent.mkdir(parents=True)
    md_file.write_text("---\nid: k1\n---\nOrderService 使用幂等校验", encoding="utf-8")
    code_file = tmp_path / "src" / "OrderService.java"
    code_file.parent.mkdir(parents=True)
    code_file.write_text("public class OrderService {}", encoding="utf-8")
    return tmp_path, md_file, code_file


# =============================================================================
# LLM 语义对比
# =============================================================================

class TestSemanticCompare:
    """LLM 语义对比。"""

    def test_consistent_result_parsed(self, db_store, tmp_project):
        tmp, md, code = tmp_project
        llm = MockLLMClient(response=json.dumps({
            "verdict": "consistent", "certainty": 0.90, "explanation": "代码未变"
        }))
        engine = CalibrationEngine(db_store, llm, project_root=tmp)
        result = engine.semantic_compare("知识内容", "代码内容")
        assert result["verdict"] == CONSISTENT
        assert result["certainty"] == 0.90

    def test_inconsistent_result_parsed(self, db_store, tmp_project):
        tmp, md, code = tmp_project
        llm = MockLLMClient(response=json.dumps({
            "verdict": "inconsistent", "certainty": 0.85,
            "explanation": "代码已改为DB唯一索引",
            "inconsistency_point": "幂等实现方式"
        }))
        engine = CalibrationEngine(db_store, llm, project_root=tmp)
        result = engine.semantic_compare("知识", "代码")
        assert result["verdict"] == INCONSISTENT
        assert "inconsistency_point" in result

    def test_uncertain_result_parsed(self, db_store, tmp_project):
        tmp, md, code = tmp_project
        llm = MockLLMClient(response=json.dumps({
            "verdict": "uncertain", "certainty": 0.50, "explanation": "逻辑太分散"
        }))
        engine = CalibrationEngine(db_store, llm, project_root=tmp)
        result = engine.semantic_compare("知识", "代码")
        assert result["verdict"] == UNCERTAIN

    def test_malformed_llm_output_fallback(self, db_store, tmp_project):
        tmp, md, code = tmp_project
        llm = MockLLMClient(response="not json")
        engine = CalibrationEngine(db_store, llm, project_root=tmp)
        result = engine.semantic_compare("知识", "代码")
        assert result["verdict"] == UNCERTAIN


# =============================================================================
# V18 certainty 分流
# =============================================================================

class TestCertaintySplit:
    """V18: certainty 分流（高确定度 → T18 废弃，低确定度 → T12 STALE）。"""

    def test_high_certainty_inconsistent_deprecated(self, db_store, tmp_project):
        """T18: 高确定度 INCONSISTENT → deprecated。"""
        tmp, md, code = tmp_project
        _insert_knowledge(db_store.get_connection(), id="k1", uri=str(md))
        llm = MockLLMClient(response=json.dumps({
            "verdict": "inconsistent", "certainty": 0.90, "explanation": "代码已变"
        }))
        engine = CalibrationEngine(db_store, llm, project_root=tmp)
        event = CalibrationEvent("E1", changed_files=["src/OrderService.java"])
        results = engine.trigger(event)
        r = [x for x in results if x.knowledge_id == "k1"][0]
        assert r.verdict == INCONSISTENT
        assert r.new_status == "deprecated"  # T18
        # DB 验证
        row = db_store.get_connection().execute(
            "SELECT status, deprecation_reason FROM knowledge_index WHERE id='k1'"
        ).fetchone()
        assert row[0] == "deprecated"
        assert row[1] == "direct_contradiction"

    def test_low_certainty_inconsistent_stale(self, db_store, tmp_project):
        """T12+V11: 低确定度 INCONSISTENT → stale(suspicious)。"""
        tmp, md, code = tmp_project
        _insert_knowledge(db_store.get_connection(), id="k1", uri=str(md), confidence=0.80)
        llm = MockLLMClient(response=json.dumps({
            "verdict": "inconsistent", "certainty": 0.60, "explanation": "可能不一致"
        }))
        engine = CalibrationEngine(db_store, llm, project_root=tmp)
        event = CalibrationEvent("E1", changed_files=["src/OrderService.java"])
        results = engine.trigger(event)
        r = [x for x in results if x.knowledge_id == "k1"][0]
        assert r.verdict == INCONSISTENT
        assert r.new_status == "stale"  # T12
        assert r.new_code_verified == 0  # V11 即时标记
        # confidence 折扣
        assert r.new_confidence is not None
        assert r.new_confidence < 0.80  # ×0.80


# =============================================================================
# V6 UNCERTAIN 三级响应
# =============================================================================

class TestUncertainResponse:
    """V6: UNCERTAIN 三级响应。"""

    def test_first_uncertain_suspected_stale(self, db_store, tmp_project):
        """V6 级 1: 首次 UNCERTAIN → suspected_stale。"""
        tmp, md, code = tmp_project
        _insert_knowledge(db_store.get_connection(), id="k1", uri=str(md), stale_check_count=0)
        llm = MockLLMClient(response=json.dumps({
            "verdict": "uncertain", "certainty": 0.50, "explanation": "不确定"
        }))
        engine = CalibrationEngine(db_store, llm, project_root=tmp)
        event = CalibrationEvent("E1", changed_files=["src/OrderService.java"])
        results = engine.trigger(event)
        r = [x for x in results if x.knowledge_id == "k1"][0]
        assert r.verdict == UNCERTAIN
        assert r.new_status == "stale"  # V6 级 1

    def test_accumulated_uncertain_to_staging(self, db_store, tmp_project):
        """V6 级 2: 累积 ≥3 次 → staging。"""
        tmp, md, code = tmp_project
        _insert_knowledge(db_store.get_connection(), id="k1", uri=str(md),
                           stale_check_count=UNCERTAIN_ACCUMULATION_THRESHOLD - 1)
        llm = MockLLMClient(response=json.dumps({
            "verdict": "uncertain", "certainty": 0.50, "explanation": "不确定"
        }))
        engine = CalibrationEngine(db_store, llm, project_root=tmp)
        event = CalibrationEvent("E1", changed_files=["src/OrderService.java"])
        results = engine.trigger(event)
        r = [x for x in results if x.knowledge_id == "k1"][0]
        assert r.new_status == "staged"  # V6 级 2


# =============================================================================
# V12 evidence 折扣
# =============================================================================

class TestEvidenceDiscount:
    """V12: suspected_stale 的 evidence 折扣。"""

    def test_evidence_discount_by_uncertain_count(self):
        assert EVIDENCE_DISCOUNT_BY_UNCERTAIN[0] == 1.0
        assert EVIDENCE_DISCOUNT_BY_UNCERTAIN[1] == 1.0
        assert EVIDENCE_DISCOUNT_BY_UNCERTAIN[2] == 0.80
        assert EVIDENCE_DISCOUNT_BY_UNCERTAIN[3] == 0.60


# =============================================================================
# CONSISTENT 恢复
# =============================================================================

class TestConsistentRecovery:
    """CONSISTENT 时恢复 STALE → ACTIVE（T15）。"""

    def test_stale_to_active_on_consistent(self, db_store, tmp_project):
        tmp, md, code = tmp_project
        _insert_knowledge(db_store.get_connection(), id="k1", uri=str(md), status="stale")
        llm = MockLLMClient(response=json.dumps({
            "verdict": "consistent", "certainty": 0.90, "explanation": "代码未变"
        }))
        engine = CalibrationEngine(db_store, llm, project_root=tmp)
        event = CalibrationEvent("E1", changed_files=["src/OrderService.java"])
        results = engine.trigger(event)
        r = [x for x in results if x.knowledge_id == "k1"][0]
        assert r.verdict == CONSISTENT
        assert r.new_status == "active"  # T15 恢复


# =============================================================================
# find_related_knowledge
# =============================================================================

class TestFindRelated:
    """查找关联知识。"""

    def test_no_related_returns_empty(self, db_store):
        engine = CalibrationEngine(db_store, MockLLMClient("{}"))
        assert engine.find_related_knowledge([]) == []

    def test_finds_by_concept_tags(self, db_store, tmp_project):
        tmp, md, code = tmp_project
        _insert_knowledge(db_store.get_connection(), id="k1", uri=str(md))
        engine = CalibrationEngine(db_store, MockLLMClient("{}"), project_root=tmp)
        related = engine.find_related_knowledge(["src/OrderService.java"])
        assert len(related) >= 1
        assert related[0]["id"] == "k1"
