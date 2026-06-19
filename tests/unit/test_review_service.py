"""Unit tests for ReviewService — approve/reject/restore + 文件移动。"""

import datetime as dt
from pathlib import Path

import pytest

from devcontext.services.review import ReviewService, ReviewResult
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore


def _insert(conn, kid, status="pending_review", uri="", **kwargs):
    defaults = {
        "id": kid, "title": "待审核知识", "domain": "order", "sub_domain": "",
        "granularity": "L3", "stability": "S4", "depth": "KH",
        "status": status, "confidence": 0.75, "code_verified": 0,
        "prune_priority": 0.0, "certainty": 0.5, "freshness": 0.5,
        "uri": uri, "used_count": 0, "calibration_status": "uncalibrated",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stale_check_count": 0, "restored_count": 0,
        "evidence_level": 3, "code_active": 1, "auto_adopted_unreviewed": 0,
        "concept_tags": "[]",
    }
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" * len(defaults))
    conn.execute(f"INSERT INTO knowledge_index ({cols}) VALUES ({placeholders})", list(defaults.values()))
    conn.commit()


@pytest.fixture
def review_service(tmp_path):
    db = SQLiteStore(":memory:")
    db.init_db()
    md = MarkdownStore(
        staging_dir=tmp_path / "staging",
        knowledge_dir=tmp_path / "knowledge",
        deprecated_dir=tmp_path / "deprecated",
    )
    return ReviewService(db, md)


def _create_md(tmp_path, name="test.md"):
    """创建一个临时 MD 文件。"""
    p = tmp_path / "staging" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nid: test\n---\ncontent", encoding="utf-8")
    return p


# =============================================================================
# list_pending
# =============================================================================

class TestListPending:
    """列出待审核。"""

    def test_lists_pending_review_and_draft(self, review_service):
        conn = review_service.db.get_connection()
        _insert(conn, "k1", status="pending_review")
        _insert(conn, "k2", status="draft")
        _insert(conn, "k3", status="active")
        pending = review_service.list_pending()
        ids = [r["id"] for r in pending]
        assert "k1" in ids
        assert "k2" in ids
        assert "k3" not in ids

    def test_filter_by_status(self, review_service):
        conn = review_service.db.get_connection()
        _insert(conn, "k1", status="pending_review")
        _insert(conn, "k2", status="draft")
        drafts = review_service.list_pending(status="draft")
        assert len(drafts) == 1
        assert drafts[0]["status"] == "draft"


# =============================================================================
# approve
# =============================================================================

class TestApprove:
    """采纳。"""

    def test_approve_pending_review(self, review_service, tmp_path):
        conn = review_service.db.get_connection()
        md = _create_md(tmp_path)
        _insert(conn, "k1", status="pending_review", uri=str(md))
        result = review_service.approve("k1")
        assert result.success is True
        assert result.new_status == "active"
        # 文件移动
        assert not md.exists()
        assert result.moved_to is not None
        assert "knowledge" in result.moved_to

    def test_approve_draft(self, review_service, tmp_path):
        conn = review_service.db.get_connection()
        md = _create_md(tmp_path, "draft.md")
        _insert(conn, "k1", status="draft", uri=str(md))
        result = review_service.approve("k1")
        assert result.success is True
        assert result.new_status == "active"

    def test_approve_nonexistent_fails(self, review_service):
        result = review_service.approve("nonexistent")
        assert result.success is False
        assert "not found" in result.error

    def test_approve_invalid_transition(self, review_service):
        conn = review_service.db.get_connection()
        _insert(conn, "k1", status="deprecated")
        result = review_service.approve("k1")
        assert result.success is False
        assert "invalid transition" in result.error


# =============================================================================
# reject
# =============================================================================

class TestReject:
    """拒绝。"""

    def test_reject_pending_review(self, review_service, tmp_path):
        conn = review_service.db.get_connection()
        md = _create_md(tmp_path)
        _insert(conn, "k1", status="pending_review", uri=str(md))
        result = review_service.reject("k1")
        assert result.success is True
        assert result.new_status == "deprecated"
        assert "deprecated" in result.moved_to
        # DB 记录原因
        record = review_service.db.get_connection().execute(
            "SELECT deprecation_reason FROM knowledge_index WHERE id='k1'"
        ).fetchone()
        assert record[0] == "human_rejected"

    def test_reject_with_custom_reason(self, review_service, tmp_path):
        conn = review_service.db.get_connection()
        md = _create_md(tmp_path)
        _insert(conn, "k1", status="draft", uri=str(md))
        result = review_service.reject("k1", reason="incorrect")
        assert result.success is True
        record = review_service.db.get_connection().execute(
            "SELECT deprecation_reason FROM knowledge_index WHERE id='k1'"
        ).fetchone()
        assert record[0] == "incorrect"


# =============================================================================
# restore
# =============================================================================

class TestRestore:
    """恢复。"""

    def test_restore_deprecated(self, review_service, tmp_path):
        conn = review_service.db.get_connection()
        md = tmp_path / "deprecated" / "test.md"
        md.parent.mkdir(parents=True)
        md.write_text("---\nid: k1\n---\ncontent", encoding="utf-8")
        _insert(conn, "k1", status="deprecated", uri=str(md),
                deprecation_reason="human_rejected")
        result = review_service.restore("k1")
        assert result.success is True
        assert result.new_status == "staged"
        # restored_count +1
        record = review_service.db.get_connection().execute(
            "SELECT restored_count FROM knowledge_index WHERE id='k1'"
        ).fetchone()
        assert record[0] == 1

    def test_restore_superseded_not_counted(self, review_service, tmp_path):
        """V24: superseded 原因恢复不计 restored_count。"""
        conn = review_service.db.get_connection()
        md = tmp_path / "deprecated" / "test.md"
        md.parent.mkdir(parents=True)
        md.write_text("---\nid: k1\n---\ncontent", encoding="utf-8")
        _insert(conn, "k1", status="deprecated", uri=str(md),
                deprecation_reason="superseded", restored_count=0)
        result = review_service.restore("k1")
        assert result.success is True
        record = review_service.db.get_connection().execute(
            "SELECT restored_count FROM knowledge_index WHERE id='k1'"
        ).fetchone()
        assert record[0] == 0  # 不计数

    def test_restore_invalid_transition(self, review_service):
        conn = review_service.db.get_connection()
        _insert(conn, "k1", status="active")
        result = review_service.restore("k1")
        assert result.success is False
        assert "invalid transition" in result.error
