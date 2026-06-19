"""Module tests for Step 6 — 巩固（晋升 + 修剪 + 文件移动）。"""

import datetime as dt
from pathlib import Path

import pytest

from devcontext.core.pipeline.consolidator import Consolidator, ConsolidationReport
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore


def _insert_knowledge(conn, **kwargs):
    """插入一条知识记录。"""
    defaults = {
        "id": "kw-test-001", "title": "测试知识", "domain": "order",
        "sub_domain": "", "granularity": "L3", "stability": "S4", "depth": "KH",
        "status": "staged", "confidence": 0.85, "code_verified": 1,
        "prune_priority": 0.0, "certainty": 0.5, "freshness": 0.5,
        "uri": "", "used_count": 0, "calibration_status": "uncalibrated",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stale_check_count": 0, "restored_count": 0,
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
def md_store(tmp_path):
    return MarkdownStore(
        staging_dir=tmp_path / "staging",
        knowledge_dir=tmp_path / "knowledge",
        deprecated_dir=tmp_path / "deprecated",
    )


# =============================================================================
# 晋升
# =============================================================================

class TestConsolidatorPromotion:
    """晋升评估。"""

    def test_staged_to_candidate(self, db_store):
        conn = db_store.get_connection()
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        _insert_knowledge(conn, id="k1", status="staged", confidence=0.90,
                           code_verified=1, last_calibrated_at=now)
        report = Consolidator(db_store).process()
        status = conn.execute("SELECT status FROM knowledge_index WHERE id='k1'").fetchone()[0]
        assert status == "candidate"
        assert report.promotions >= 1

    def test_staged_to_pending_review(self, db_store):
        conn = db_store.get_connection()
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        _insert_knowledge(conn, id="k1", status="staged", confidence=0.90,
                           code_verified=0, last_calibrated_at=now)
        Consolidator(db_store).process()
        status = conn.execute("SELECT status FROM knowledge_index WHERE id='k1'").fetchone()[0]
        assert status == "pending_review"

    def test_staged_to_draft(self, db_store):
        conn = db_store.get_connection()
        _insert_knowledge(conn, id="k1", status="staged", confidence=0.40,
                           code_verified=0, last_calibrated_at=None)
        Consolidator(db_store).process()
        status = conn.execute("SELECT status FROM knowledge_index WHERE id='k1'").fetchone()[0]
        assert status == "draft"

    def test_candidate_locks_score(self, db_store):
        """T3: 进入 candidate 时锁定 score。"""
        conn = db_store.get_connection()
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        _insert_knowledge(conn, id="k1", status="staged", confidence=0.90,
                           code_verified=1, last_calibrated_at=now)
        Consolidator(db_store).process()
        locked = conn.execute(
            "SELECT locked_promotion_score FROM knowledge_index WHERE id='k1'"
        ).fetchone()[0]
        assert locked is not None and locked >= 0.82


# =============================================================================
# 修剪
# =============================================================================

class TestConsolidatorPruning:
    """修剪评估。"""

    def test_draft_old_deprecated(self, db_store):
        conn = db_store.get_connection()
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=100)).isoformat()
        _insert_knowledge(conn, id="k1", status="draft", confidence=0.50,
                           created_at=old, code_verified=0)
        Consolidator(db_store).process()
        row = conn.execute(
            "SELECT status, deprecation_reason FROM knowledge_index WHERE id='k1'"
        ).fetchone()
        assert row[0] == "deprecated"
        assert row[1] is not None

    def test_active_to_cold(self, db_store):
        """T11: active + anchor + 未使用 → cold。"""
        conn = db_store.get_connection()
        _insert_knowledge(conn, id="k1", status="active", confidence=0.90,
                           code_verified=1, used_count=0, last_used_at=None)
        Consolidator(db_store).process()
        status = conn.execute("SELECT status FROM knowledge_index WHERE id='k1'").fetchone()[0]
        assert status == "cold"

    def test_no_anchor_old_to_stale(self, db_store):
        """T14: 无锚点 + age>90d → stale。"""
        conn = db_store.get_connection()
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=100)).isoformat()
        _insert_knowledge(conn, id="k1", status="active", confidence=0.80,
                           code_verified=0, created_at=old, used_count=5,
                           last_used_at=old)
        Consolidator(db_store).process()
        row = conn.execute(
            "SELECT status, stale_sub_phase, flag FROM knowledge_index WHERE id='k1'"
        ).fetchone()
        assert row[0] == "stale"
        assert row[1] == "suspicious"

    def test_stale_deep_to_deprecated(self, db_store):
        """T16: stale_check_count >= 3 → deprecated。"""
        conn = db_store.get_connection()
        _insert_knowledge(conn, id="k1", status="stale", confidence=0.32,
                           code_verified=0, stale_check_count=3)
        Consolidator(db_store).process()
        row = conn.execute(
            "SELECT status, deprecation_reason FROM knowledge_index WHERE id='k1'"
        ).fetchone()
        assert row[0] == "deprecated"
        assert row[1] == "verification_failed"


# =============================================================================
# Dry Run
# =============================================================================

class TestConsolidatorDryRun:
    """dry_run 模式。"""

    def test_dry_run_no_db_changes(self, db_store):
        conn = db_store.get_connection()
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        _insert_knowledge(conn, id="k1", status="staged", confidence=0.90,
                           code_verified=1, last_calibrated_at=now)
        report = Consolidator(db_store, dry_run=True).process()
        # DB 状态不变
        status = conn.execute("SELECT status FROM knowledge_index WHERE id='k1'").fetchone()[0]
        assert status == "staged"
        # 但报告有评估结果
        assert report.total_scanned == 1
        assert len(report.details) == 1


# =============================================================================
# 报告
# =============================================================================

class TestConsolidationReport:
    """巩固报告。"""

    def test_report_has_all_fields(self, db_store):
        conn = db_store.get_connection()
        _insert_knowledge(conn, id="k1")
        report = Consolidator(db_store).process()
        d = report.to_dict()
        for field in ("total_scanned", "promotions", "pruned", "stale_marked",
                       "cold_marked", "moved_files", "errors", "details"):
            assert field in d

    def test_empty_db_zero_scanned(self, db_store):
        report = Consolidator(db_store).process()
        assert report.total_scanned == 0
        assert report.promotions == 0


# =============================================================================
# 文件移动
# =============================================================================

class TestFileMove:
    """文件移动。"""

    def test_candidate_to_active_moves_file(self, db_store, md_store, tmp_path):
        """candidate→active 时文件从 staging→knowledge/。"""
        conn = db_store.get_connection()
        # 创建 staging MD 文件
        staging_dir = md_store.staging_dir
        staging_dir.mkdir(parents=True, exist_ok=True)
        md_file = staging_dir / "test.md"
        md_file.write_text("---\nid: k1\n---\ncontent", encoding="utf-8")

        now = dt.datetime.now(dt.timezone.utc).isoformat()
        _insert_knowledge(conn, id="k1", status="candidate", confidence=0.90,
                           code_verified=1, last_calibrated_at=now,
                           locked_promotion_score=0.85, uri=str(md_file))
        Consolidator(db_store, md_store).process()

        # 文件应移到 knowledge/order/
        dest = md_store.knowledge_dir / "order" / "test.md"
        assert dest.exists()
        assert not md_file.exists()

        # DB uri 更新
        uri = conn.execute("SELECT uri FROM knowledge_index WHERE id='k1'").fetchone()[0]
        assert "knowledge" in uri and "order" in uri

    def test_deprecated_moves_file(self, db_store, md_store, tmp_path):
        """→deprecated 时文件移到 deprecated/。"""
        conn = db_store.get_connection()
        knowledge_dir = md_store.knowledge_dir / "order"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        md_file = knowledge_dir / "old.md"
        md_file.write_text("---\nid: k1\n---\ncontent", encoding="utf-8")

        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=100)).isoformat()
        _insert_knowledge(conn, id="k1", status="draft", confidence=0.50,
                           created_at=old, code_verified=0, uri=str(md_file))
        Consolidator(db_store, md_store).process()

        dest = md_store.deprecated_dir / "old.md"
        assert dest.exists()
        assert not md_file.exists()
