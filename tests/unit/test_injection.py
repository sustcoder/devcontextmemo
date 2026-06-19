"""Unit tests for InjectionService — 三层路由 + L2/L3 响应。"""

import datetime as dt
from pathlib import Path

import pytest

from devcontext.services.injection import InjectionService, InjectionLayer, LAYER_L1, LAYER_L2, LAYER_L3
from devcontext.storage.search import SearchEngine
from devcontext.storage.sqlite import SQLiteStore


def _insert(conn, store, kid, title, stability="S4", depth="KH", domain="order", **kwargs):
    defaults = {
        "id": kid, "title": title, "domain": domain, "sub_domain": "",
        "granularity": "L3", "stability": stability, "depth": depth,
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


@pytest.fixture
def search_engine(db_store):
    return SearchEngine(db_store)


@pytest.fixture
def injection_service(db_store, search_engine, tmp_path):
    return InjectionService(db_store, search_engine, knowledge_dir=tmp_path)


# =============================================================================
# 路由推导
# =============================================================================

class TestRoute:
    """注入路由推导表。"""

    def test_s1_kw_routes_to_l1(self):
        assert InjectionService.route("S1", "KW") == LAYER_L1

    def test_s2_kw_routes_to_l1(self):
        assert InjectionService.route("S2", "KW") == LAYER_L1

    def test_s1_kh_routes_to_l2(self):
        assert InjectionService.route("S1", "KH") == LAYER_L2

    def test_s2_ky_routes_to_l2(self):
        assert InjectionService.route("S2", "KY") == LAYER_L2

    def test_s3_any_routes_to_l2(self):
        assert InjectionService.route("S3", "KW") == LAYER_L2
        assert InjectionService.route("S3", "KH") == LAYER_L2

    def test_s4_any_routes_to_l2(self):
        assert InjectionService.route("S4", "KY") == LAYER_L2

    def test_s5_any_routes_to_l3(self):
        assert InjectionService.route("S5", "KW") == LAYER_L3
        assert InjectionService.route("S5", "KY") == LAYER_L3

    def test_invalid_stability_rejected(self):
        with pytest.raises(ValueError):
            InjectionService.route("S9", "KW")

    def test_invalid_depth_rejected(self):
        with pytest.raises(ValueError):
            InjectionService.route("S1", "KZ")


# =============================================================================
# L2 响应
# =============================================================================

class TestL2Response:
    """L2 按需检索响应。"""

    def test_l2_response_structure(self, db_store, injection_service):
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "幂等校验方案")
        search = SearchEngine(db_store)
        results = search.search("幂等")
        resp = injection_service.build_l2_response(results)
        assert resp["layer"] == LAYER_L2
        assert "items" in resp
        assert "total" in resp
        assert "truncated" in resp

    def test_l2_response_respects_max_tokens(self, db_store, injection_service):
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "幂等校验方案")
        search = SearchEngine(db_store)
        results = search.search("幂等")
        resp = injection_service.build_l2_response(results, max_tokens=10)  # 极小预算
        # 应该截断或空
        assert resp["total"] <= len(results)


# =============================================================================
# L3 响应
# =============================================================================

class TestL3Response:
    """L3 经验检索响应。"""

    def test_l3_response_structure(self, db_store, injection_service):
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "旧版缓存策略", stability="S5")
        resp = injection_service.build_l3_response("缓存")
        assert resp["layer"] == LAYER_L3
        assert "items" in resp

    def test_l3_only_returns_s5(self, db_store, injection_service):
        """L3 仅返回 S5 知识。"""
        conn = db_store.get_connection()
        _insert(conn, db_store, "k1", "旧版缓存策略", stability="S5")
        _insert(conn, db_store, "k2", "新版缓存策略", stability="S1")
        resp = injection_service.build_l3_response("缓存")
        for item in resp["items"]:
            assert item["id"] == "k1"  # 只有 S5


# =============================================================================
# generate_agents_md
# =============================================================================


class TestGenerateAgentsMd:
    """generate_agents_md — L1 恒常注入 AGENTS.md 草稿生成。"""

    def _make_md_file(self, tmp_path: Path, kid: str, content: str) -> Path:
        """创建 MD 文件并返回路径。"""
        path = tmp_path / f"{kid}.md"
        path.write_text(f"---\ntitle: {kid}\n---\n\n{content}\n", encoding="utf-8")
        return path

    def test_generates_draft_file(self, db_store, search_engine, tmp_path):
        """基本功能：生成 AGENTS.knowledge.draft.md 草稿。"""
        conn = db_store.get_connection()

        # 创建 MD 文件
        md1 = self._make_md_file(tmp_path, "k1", "幂等校验是企业级服务的基础保障。")
        md2 = self._make_md_file(tmp_path, "k2", "使用分布式锁确保多实例幂等。")

        _insert(conn, db_store, "k1", "幂等校验方案", stability="S1", depth="KW",
                domain="order", uri=str(md1), status="active")
        _insert(conn, db_store, "k2", "分布式锁设计", stability="S2", depth="KW",
                domain="order", uri=str(md2), status="active")

        svc = InjectionService(db_store, search_engine, knowledge_dir=tmp_path)
        draft_path = svc.generate_agents_md()

        assert draft_path.exists()
        content = draft_path.read_text(encoding="utf-8")
        assert "# 项目知识" in content
        assert "幂等校验方案" in content
        assert "分布式锁设计" in content

    def test_filters_s1_s2_kw_only(self, db_store, search_engine, tmp_path):
        """仅包含 S1/S2 + KW 知识，排除其他 stability/depth。"""
        conn = db_store.get_connection()

        # 应包含
        md1 = self._make_md_file(tmp_path, "k1", "S1-KW 内容。")
        _insert(conn, db_store, "k1", "S1-KW知识", stability="S1", depth="KW",
                domain="arch", uri=str(md1), status="active")

        # 不应包含
        md2 = self._make_md_file(tmp_path, "k2", "S3-KW 内容。")
        md3 = self._make_md_file(tmp_path, "k3", "S1-KH 内容。")
        _insert(conn, db_store, "k2", "S3-KW知识", stability="S3", depth="KW",
                domain="arch", uri=str(md2), status="active")
        _insert(conn, db_store, "k3", "S1-KH知识", stability="S1", depth="KH",
                domain="arch", uri=str(md3), status="active")

        svc = InjectionService(db_store, search_engine, knowledge_dir=tmp_path)
        draft_path = svc.generate_agents_md()

        content = draft_path.read_text(encoding="utf-8")
        assert "S1-KW知识" in content
        assert "S3-KW知识" not in content
        assert "S1-KH知识" not in content

    def test_excludes_deprecated_and_staged(self, db_store, search_engine, tmp_path):
        """排除非 active/cold 状态的知识。"""
        conn = db_store.get_connection()

        md1 = self._make_md_file(tmp_path, "k1", "active 知识。")
        md2 = self._make_md_file(tmp_path, "k2", "deprecated 知识。")

        _insert(conn, db_store, "k1", "active知识", stability="S1", depth="KW",
                domain="order", uri=str(md1), status="active")
        _insert(conn, db_store, "k2", "deprecated知识", stability="S1", depth="KW",
                domain="order", uri=str(md2), status="deprecated")

        svc = InjectionService(db_store, search_engine, knowledge_dir=tmp_path)
        draft_path = svc.generate_agents_md()

        content = draft_path.read_text(encoding="utf-8")
        assert "active知识" in content
        assert "deprecated知识" not in content

    def test_token_truncation_indicated(self, db_store, search_engine, tmp_path):
        """Token 超预算时标注截断信息。"""
        conn = db_store.get_connection()

        # 插入大量知识以触发 Token 截断
        long_text = "A" * 2000
        for i in range(25):
            md = self._make_md_file(tmp_path, f"k{i}", long_text)
            _insert(conn, db_store, f"k{i}", f"知识{i}", stability="S1", depth="KW",
                    domain="order", uri=str(md), status="active")

        svc = InjectionService(db_store, search_engine, knowledge_dir=tmp_path)
        draft_path = svc.generate_agents_md()

        content = draft_path.read_text(encoding="utf-8")
        assert "已截断" in content

    def test_empty_knowledge_generates_header_only(self, db_store, search_engine, tmp_path):
        """无 S1/S2+KW 知识时只生成标题。"""
        conn = db_store.get_connection()
        md1 = self._make_md_file(tmp_path, "k1", "S3 内容。")
        _insert(conn, db_store, "k1", "S3知识", stability="S3", depth="KY",
                domain="order", uri=str(md1), status="active")

        svc = InjectionService(db_store, search_engine, knowledge_dir=tmp_path)
        draft_path = svc.generate_agents_md()

        content = draft_path.read_text(encoding="utf-8")
        assert "# 项目知识" in content
        assert "稳定性:" not in content  # 无实际知识条目
