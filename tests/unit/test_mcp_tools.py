"""Unit tests for MCP Tools — query_knowledge / write_knowledge / calibrate_knowledge。"""

import datetime as dt
import json
from pathlib import Path

import pytest

from devcontext.mcp.tools import (
    ValidationError,
    calibrate_knowledge,
    query_knowledge,
    write_knowledge,
)
from devcontext.mcp.server import MCPServer
from devcontext.mcp.resources import read_knowledge_resource, list_knowledge_resources
from devcontext.services.knowledge import KnowledgeService
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.search import SearchEngine
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
        "concept_tags": '["#test"]',
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
def knowledge_service(tmp_path):
    db = SQLiteStore(":memory:")
    db.init_db()
    md = MarkdownStore(
        staging_dir=tmp_path / "staging",
        knowledge_dir=tmp_path / "knowledge",
        deprecated_dir=tmp_path / "deprecated",
    )
    search = SearchEngine(db)
    return KnowledgeService(db, md, search), db


# =============================================================================
# query_knowledge
# =============================================================================

class TestQueryKnowledgeSearch:
    """query_knowledge 搜索。"""

    def test_search_returns_results(self, knowledge_service):
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "k1", "幂等校验方案")
        resp = query_knowledge(ks, query="幂等")
        assert resp.data["total"] >= 1
        assert resp.data["items"][0]["id"] == "k1"

    def test_search_has_next_action(self, knowledge_service):
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "k1", "幂等校验方案")
        resp = query_knowledge(ks, query="幂等")
        assert "next_action" in resp.data

    def test_search_by_id(self, knowledge_service):
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "k1", "幂等校验方案")
        resp = query_knowledge(ks, id="k1")
        assert resp.data["total"] == 1
        assert resp.data["items"][0]["id"] == "k1"

    def test_empty_results_no_error(self, knowledge_service):
        """空结果返回 200（V42 修复）。"""
        ks, db = knowledge_service
        resp = query_knowledge(ks, query="不存在的知识xxx")
        assert resp.data["total"] == 0
        assert resp.data["items"] == []
        assert "hint" in resp.data["next_action"]

    def test_include_full_source_missing(self, knowledge_service):
        """include_full 但 MD 不存在 → 降级（V1.1）。"""
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "k1", "幂等校验方案")
        resp = query_knowledge(ks, id="k1", include_full=True)
        item = resp.data["items"][0]
        assert item.get("source_missing") is True
        assert item.get("content") is None


class TestQueryKnowledgeValidation:
    """query_knowledge 参数校验。"""

    def test_query_and_id_mutually_exclusive(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            query_knowledge(ks, query="x", id="y")
        assert e.value.code == 400

    def test_either_query_or_id_required(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            query_knowledge(ks)
        assert e.value.code == 400

    def test_invalid_domain_rejected(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            query_knowledge(ks, query="x", domain="../etc")
        assert e.value.code == 400

    def test_invalid_limit_rejected(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            query_knowledge(ks, query="x", limit=100)
        assert e.value.code == 400

    def test_invalid_depth_rejected(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            query_knowledge(ks, query="x", depth="KZ")
        assert e.value.code == 400


# =============================================================================
# write_knowledge
# =============================================================================

class TestWriteKnowledge:
    """write_knowledge 写入。"""

    def test_write_returns_task_id(self, knowledge_service):
        ks, db = knowledge_service
        resp = write_knowledge(ks, content="测试知识", session_id="sess-001")
        assert resp.data["status"] == "accepted"
        assert resp.data["task_id"].startswith("write-")
        assert "estimated_time" in resp.data

    def test_empty_content_rejected(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            write_knowledge(ks, content="", session_id="s1")
        assert e.value.code == 400

    def test_oversized_content_rejected(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            write_knowledge(ks, content="x" * 10001, session_id="s1")
        assert e.value.code == 400

    def test_missing_session_id_rejected(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            write_knowledge(ks, content="test", session_id="")
        assert e.value.code == 400

    def test_invalid_granularity_rejected(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            write_knowledge(ks, content="test", session_id="s1", granularity="L9")
        assert e.value.code == 400


# =============================================================================
# calibrate_knowledge
# =============================================================================

class TestCalibrateKnowledge:
    """calibrate_knowledge 校准。"""

    def test_calibrate_all_scope(self, knowledge_service):
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "k1", "测试")
        resp = calibrate_knowledge(db, scope="all", mode="quick")
        assert "stale_items" in resp.data
        assert resp.data["total_checked"] >= 1

    def test_calibrate_domain_scope(self, knowledge_service):
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "k1", "测试", domain="order")
        _insert(db.get_connection(), db, "k2", "测试2", domain="payment")
        resp = calibrate_knowledge(db, scope="domain:order")
        assert resp.data["total_checked"] == 1

    def test_calibrate_id_scope(self, knowledge_service):
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "kw-001", "测试")
        resp = calibrate_knowledge(db, scope="id:kw-001")
        assert resp.data["total_checked"] == 1

    def test_invalid_scope_rejected(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            calibrate_knowledge(db, scope="invalid")
        assert e.value.code == 400

    def test_invalid_mode_rejected(self, knowledge_service):
        ks, db = knowledge_service
        with pytest.raises(ValidationError) as e:
            calibrate_knowledge(db, mode="invalid")
        assert e.value.code == 400

    def test_never_calibrated_is_stale(self, knowledge_service):
        """从未校准的知识标记为 stale。"""
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "kw-001", "测试", last_calibrated_at=None)
        resp = calibrate_knowledge(db, scope="id:kw-001")
        assert resp.data["total_stale"] == 1
        assert resp.data["stale_items"][0]["reason"] == "never calibrated"


# =============================================================================
# MCPServer
# =============================================================================

class TestMCPServer:
    """MCPServer 注册与调用。"""

    def test_list_tools_returns_three(self, tmp_path):
        server = MCPServer(
            db_path=":memory:",
            knowledge_dir=str(tmp_path / "knowledge"),
            staging_dir=str(tmp_path / "staging"),
            deprecated_dir=str(tmp_path / "deprecated"),
        )
        tools = server.list_tools()
        assert len(tools) == 3
        names = {t["name"] for t in tools}
        assert names == {"query_knowledge", "write_knowledge", "calibrate_knowledge"}
        server.close()

    def test_call_tool_calibrate(self, tmp_path):
        server = MCPServer(
            db_path=":memory:",
            knowledge_dir=str(tmp_path / "knowledge"),
            staging_dir=str(tmp_path / "staging"),
            deprecated_dir=str(tmp_path / "deprecated"),
        )
        result = server.call_tool("calibrate_knowledge", scope="all")
        assert "total_checked" in result
        server.close()

    def test_call_unknown_tool_raises(self, tmp_path):
        server = MCPServer(
            db_path=":memory:",
            knowledge_dir=str(tmp_path / "knowledge"),
            staging_dir=str(tmp_path / "staging"),
            deprecated_dir=str(tmp_path / "deprecated"),
        )
        with pytest.raises(ValueError):
            server.call_tool("unknown")
        server.close()

    def test_validate_host_rejects_external(self):
        with pytest.raises(SystemExit):
            MCPServer.validate_host("0.0.0.0")

    def test_validate_host_accepts_localhost(self):
        MCPServer.validate_host("127.0.0.1")  # 不抛异常

    def test_call_tool_returns_error_on_validation(self, tmp_path):
        server = MCPServer(
            db_path=":memory:",
            knowledge_dir=str(tmp_path / "knowledge"),
            staging_dir=str(tmp_path / "staging"),
            deprecated_dir=str(tmp_path / "deprecated"),
        )
        result = server.call_tool("query_knowledge")  # 缺 query/id
        assert "error" in result
        assert result["code"] == 400
        server.close()


# =============================================================================
# Resources
# =============================================================================

class TestResources:
    """MCP Resource。"""

    def test_read_knowledge_resource(self, knowledge_service):
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "k1", "资源测试")
        res = read_knowledge_resource(ks, "k1")
        assert res["uri"] == "knowledge://k1"
        assert res["mime_type"] == "text/markdown"
        assert "metadata" in res

    def test_read_nonexistent_resource(self, knowledge_service):
        ks, db = knowledge_service
        res = read_knowledge_resource(ks, "nonexistent")
        assert "error" in res

    def test_list_knowledge_resources(self, knowledge_service):
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "k1", "资源A")
        _insert(db.get_connection(), db, "k2", "资源B")
        resources = list_knowledge_resources(db)
        assert len(resources) >= 2
        assert all(r["uri"].startswith("knowledge://") for r in resources)

    def test_list_resources_filter_by_domain(self, knowledge_service):
        ks, db = knowledge_service
        _insert(db.get_connection(), db, "k1", "A", domain="order")
        _insert(db.get_connection(), db, "k2", "B", domain="payment")
        resources = list_knowledge_resources(db, domain="order")
        assert all(r["domain"] == "order" for r in resources)
