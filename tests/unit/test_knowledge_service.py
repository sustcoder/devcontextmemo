"""Unit tests for KnowledgeService — CRUD + 检索。"""

import datetime as dt
from pathlib import Path

import pytest

from devcontext.services.knowledge import KnowledgeService
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.search import SearchEngine
from devcontext.storage.sqlite import SQLiteStore


def _insert(conn, kid, title="测试知识", domain="order", status="active", confidence=0.85, **kwargs):
    defaults = {
        "id": kid, "title": title, "domain": domain, "sub_domain": "",
        "granularity": "L3", "stability": "S4", "depth": "KH",
        "status": status, "confidence": confidence, "code_verified": 1,
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
    conn.execute(f"INSERT INTO knowledge_index ({cols}) VALUES ({placeholders})", list(defaults.values()))
    conn.commit()


@pytest.fixture
def service(tmp_path):
    db = SQLiteStore(":memory:")
    db.init_db()
    md = MarkdownStore(
        staging_dir=tmp_path / "staging",
        knowledge_dir=tmp_path / "knowledge",
        deprecated_dir=tmp_path / "deprecated",
    )
    search = SearchEngine(db)
    return KnowledgeService(db, md, search)


class TestGetById:
    """get_by_id。"""

    def test_existing_record(self, service):
        conn = service.db.get_connection()
        _insert(conn, "k1", "幂等校验")
        record = service.get_by_id("k1")
        assert record is not None
        assert record["id"] == "k1"
        assert record["title"] == "幂等校验"

    def test_nonexistent_returns_none(self, service):
        assert service.get_by_id("nonexistent") is None


class TestListByDomain:
    """list_by_domain。"""

    def test_lists_by_domain(self, service):
        conn = service.db.get_connection()
        _insert(conn, "k1", "知识A", domain="order")
        _insert(conn, "k2", "知识B", domain="order")
        _insert(conn, "k3", "知识C", domain="payment")
        records = service.list_by_domain("order")
        assert len(records) == 2
        assert all(r["domain"] == "order" for r in records)

    def test_filter_by_status(self, service):
        conn = service.db.get_connection()
        _insert(conn, "k1", "知识A", domain="order", status="active")
        _insert(conn, "k2", "知识B", domain="order", status="draft")
        active = service.list_by_domain("order", status="active")
        assert len(active) == 1
        assert active[0]["status"] == "active"


class TestCreate:
    """create。"""

    def test_creates_knowledge(self, service):
        kid = service.create({
            "knowledge_text": "测试知识内容",
            "domain": "order",
            "granularity": "L3", "stability": "S4", "depth": "KH",
            "confidence": 0.80,
        })
        assert kid.startswith("kw-")
        record = service.get_by_id(kid)
        assert record is not None
        assert record["domain"] == "order"

    def test_green_channel_writes_to_knowledge(self, service):
        """confidence ≥ 0.95 → knowledge/。"""
        kid = service.create({
            "knowledge_text": "高置信知识",
            "domain": "order",
            "granularity": "L3", "stability": "S4", "depth": "KH",
            "confidence": 0.97,
        })
        record = service.get_by_id(kid)
        assert "knowledge" in record["uri"]

    def test_low_confidence_writes_to_staging(self, service):
        """confidence < 0.95 → staging/。"""
        kid = service.create({
            "knowledge_text": "普通知识",
            "domain": "order",
            "granularity": "L3", "stability": "S4", "depth": "KH",
            "confidence": 0.70,
        })
        record = service.get_by_id(kid)
        assert "staging" in record["uri"]


class TestDeprecate:
    """deprecate。"""

    def test_deprecate_active(self, service):
        conn = service.db.get_connection()
        _insert(conn, "k1", "测试", status="active")
        service.deprecate("k1", reason="test")
        record = service.get_by_id("k1")
        assert record["status"] == "deprecated"
        assert record["deprecation_reason"] == "test"

    def test_deprecate_invalid_transition_raises(self, service):
        """deprecate 固定迁移到 deprecated，V2.0 T 表中任意状态→deprecated 合法。
        这里测 is_valid_transition 的非法路径（deprecated→active）。"""
        from devcontext.models.enums import is_valid_transition
        # deprecated → active 非法（V2.0 T 表 deprecated 只能 →staged）
        assert is_valid_transition("deprecated", "active") is False

    def test_nonexistent_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.deprecate("nonexistent")


class TestUpdate:
    """update — 保留旧版本，生成新版本。"""

    def test_update_creates_new_version(self, service):
        """旧版本 → deprecated，新版本 → staging。"""
        conn = service.db.get_connection()
        _insert(conn, "k1", "旧知识", status="active")

        new_id = service.update("k1", "新知识内容", reason="内容过时")

        assert new_id.startswith("kw-")
        assert new_id != "k1"

        # 旧版本已废弃
        old = service.get_by_id("k1")
        assert old["status"] == "deprecated"
        assert old["deprecation_reason"].startswith("superseded:")

        # 新版本存在
        new = service.get_by_id(new_id)
        assert new is not None

    def test_update_preserves_domain(self, service):
        """新版本保留原 domain。"""
        conn = service.db.get_connection()
        _insert(conn, "k1", "旧知识", domain="payment", status="active")

        new_id = service.update("k1", "新知识内容")
        new = service.get_by_id(new_id)
        assert new["domain"] == "payment"

    def test_update_nonexistent_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.update("nonexistent", "新内容")

    def test_update_sets_superseded_by(self, service):
        """旧记录的 superseded_by 指向新版本。"""
        conn = service.db.get_connection()
        _insert(conn, "k1", "旧知识", status="active")

        new_id = service.update("k1", "新知识内容")
        old = service.get_by_id("k1")
        assert old["superseded_by"] == new_id


class TestReplace:
    """replace — 直接覆盖 MD 文件。"""

    def test_replace_overwrites_file_content(self, service, tmp_path):
        """替换后文件内容为新内容。"""
        # 先 create 一条知识
        kid = service.create({
            "knowledge_text": "原始内容",
            "domain": "order",
            "granularity": "L3", "stability": "S4", "depth": "KH",
            "confidence": 0.80,
            "_seq": "010",
        })
        record = service.get_by_id(kid)
        uri = record["uri"]

        service.replace(kid, "替换后的新内容")

        # 文件内容已更新
        content = Path(uri).read_text(encoding="utf-8")
        assert "替换后的新内容" in content

    def test_replace_nonexistent_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.replace("nonexistent", "新内容")


class TestSupplement:
    """supplement — 追加补充，不修改原文。"""

    def test_supplement_appends_to_file(self, service, tmp_path):
        """原内容保留，新内容追加在末尾。"""
        kid = service.create({
            "knowledge_text": "原始内容",
            "domain": "order",
            "granularity": "L3", "stability": "S4", "depth": "KH",
            "confidence": 0.80,
            "_seq": "011",
        })
        record = service.get_by_id(kid)
        uri = record["uri"]

        original = Path(uri).read_text(encoding="utf-8")

        service.supplement(kid, "补充说明：此方案仅适用于单体架构")

        updated = Path(uri).read_text(encoding="utf-8")
        assert "原始内容" in updated
        assert "补充说明：此方案仅适用于单体架构" in updated
        # 原文段在补充段之前
        assert updated.index("原始内容") < updated.index("补充说明")

    def test_supplement_includes_date_header(self, service, tmp_path):
        """补充内容带有日期标题。"""
        kid = service.create({
            "knowledge_text": "原始内容",
            "domain": "order",
            "granularity": "L3", "stability": "S4", "depth": "KH",
            "confidence": 0.80,
            "_seq": "012",
        })
        record = service.get_by_id(kid)
        uri = record["uri"]

        service.supplement(kid, "补充内容")
        updated = Path(uri).read_text(encoding="utf-8")
        assert "## 补充" in updated

    def test_supplement_nonexistent_raises(self, service):
        with pytest.raises(ValueError, match="not found"):
            service.supplement("nonexistent", "补充")
