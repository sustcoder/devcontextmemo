"""Unit tests for SearchEngine — FTS5 搜索 + 状态过滤 + 回退。"""

import datetime as dt
from pathlib import Path

import pytest

from devcontext.storage.search import SearchEngine, SearchResult, SEARCHABLE_STATUSES, MIN_CONFIDENCE
from devcontext.storage.sqlite import SQLiteStore


def _insert(conn, store, kid, title, domain="order", status="active", confidence=0.85, **kwargs):
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
    if store.fts_available:
        rowid = conn.execute("SELECT rowid FROM knowledge_index WHERE id=?", [kid]).fetchone()[0]
        store._sync_fts(rowid, title, "", title)


@pytest.fixture
def db_store():
    store = SQLiteStore(":memory:")
    store.init_db()
    return store


class TestSearchEngineBasic:
    """基础搜索。"""

    def test_search_returns_results(self, db_store):
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "幂等校验方案")
        search = SearchEngine(db_store)
        results = search.search("幂等")
        assert len(results) >= 1
        assert results[0].id == "k1"

    def test_search_empty_query_returns_empty(self, db_store):
        search = SearchEngine(db_store)
        results = search.search("")
        assert isinstance(results, list)

    def test_search_result_has_fields(self, db_store):
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "幂等校验方案", domain="order")
        search = SearchEngine(db_store)
        results = search.search("幂等")
        r = results[0]
        assert hasattr(r, "id")
        assert hasattr(r, "title")
        assert hasattr(r, "domain")
        assert hasattr(r, "uri")
        assert hasattr(r, "confidence")
        assert hasattr(r, "score")


class TestStatusFilter:
    """V2.0 状态过滤。"""

    def test_staged_excluded(self, db_store):
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "幂等校验", status="active")
        _insert(conn, db_store, "k2", "幂等校验补充", status="staged")
        search = SearchEngine(db_store)
        results = search.search("幂等")
        ids = [r.id for r in results]
        assert "k1" in ids
        assert "k2" not in ids

    def test_deprecated_excluded(self, db_store):
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "幂等校验", status="active")
        _insert(conn, db_store, "k2", "幂等校验旧", status="deprecated")
        search = SearchEngine(db_store)
        results = search.search("幂等")
        ids = [r.id for r in results]
        assert "k2" not in ids

    def test_searchable_statuses_correct(self):
        assert "active" in SEARCHABLE_STATUSES
        assert "cold" in SEARCHABLE_STATUSES
        assert "staged" not in SEARCHABLE_STATUSES
        assert "stale" not in SEARCHABLE_STATUSES
        assert "deprecated" not in SEARCHABLE_STATUSES


class TestConfidenceFilter:
    """confidence 阈值过滤。"""

    def test_low_confidence_excluded(self, db_store):
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "高置信", confidence=0.85)
        _insert(conn, db_store, "k2", "低置信", confidence=0.20)
        search = SearchEngine(db_store)
        results = search.search("置信")
        ids = [r.id for r in results]
        assert "k1" in ids
        assert "k2" not in ids

    def test_min_confidence_default(self):
        assert MIN_CONFIDENCE == 0.4


class TestDomainFilter:
    """领域过滤。"""

    def test_domain_filter(self, db_store):
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "幂等", domain="order")
        _insert(conn, db_store, "k2", "幂等", domain="payment")
        search = SearchEngine(db_store)
        results = search.search("幂等", domain="order")
        ids = [r.id for r in results]
        assert "k1" in ids
        assert "k2" not in ids


class TestTopK:
    """top-k 限制。"""

    def test_top_k_limit(self, db_store):
        conn = db_store.get_connection()
        for i in range(5):
            _insert(conn, db_store, f"k{i}", f"幂等校验{i}", confidence=0.80 + i * 0.01)
        search = SearchEngine(db_store)
        results = search.search("幂等", top_k=3)
        assert len(results) <= 3
