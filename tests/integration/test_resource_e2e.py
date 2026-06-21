"""资源轨端到端集成测试 — CLI 导入 spec 文件 → 全链路验证。

覆盖 3 个场景：
1. 导入真实 spec 文档 → 验证 DB 存储 + 语义分块 + FTS5 搜索 + 文件落地
2. 双轨并行检索 → 记忆轨 + 资源轨同时命中 / 三级回退
3. 去重 + 软删除降级 → unchanged 检测 / deleted_at / 删除后检索降级

测试数据：``docs/superpowers/specs/2026-06-19-Phase1-数据源偏离度调研与修复方案-V1.0.md``

隔离策略：
- SQLite :memory: 零副作用
- tempfile.TemporaryDirectory 隔离文件系统
- 不依赖 .devContextMemo/ 已有数据
"""

import os
import tempfile
from pathlib import Path

import pytest


# =============================================================================
# 测试文档路径
# =============================================================================

SPEC_FILE = Path(__file__).parent.parent.parent / (
    "docs/superpowers/specs/2026-06-19-Phase1-数据源偏离度调研与修复方案-V1.0.md"
)


@pytest.fixture
def spec_file():
    """验证 spec 文件存在。"""
    if not SPEC_FILE.exists():
        pytest.skip(f"Spec file not found: {SPEC_FILE}")
    return SPEC_FILE


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_store():
    """创建内存 SQLiteStore 并初始化全部表。"""
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(":memory:")
    store.init_db()
    yield store
    store.close()


@pytest.fixture
def resource_service(db_store, tmp_path):
    """创建 ResourceService 实例。"""
    from devcontext.services.resource import ResourceService

    resources_dir = tmp_path / ".devContextMemo" / "resources"
    return ResourceService(db_store, resources_dir)


@pytest.fixture
def context_engine(db_store, tmp_path):
    """创建 ContextQueryEngine（双轨检索）。"""
    from devcontext.services.context_query import ContextQueryEngine
    from devcontext.services.knowledge import KnowledgeService
    from devcontext.services.resource import ResourceService
    from devcontext.storage.markdown import MarkdownStore
    from devcontext.storage.search import SearchEngine

    md_knowledge = tmp_path / ".devContextMemo" / "knowledge"
    md_staging = tmp_path / ".devContextMemo" / "staging"
    md_deprecated = tmp_path / ".devContextMemo" / "deprecated"
    md_store = MarkdownStore(md_staging, md_knowledge, md_deprecated)
    search_engine = SearchEngine(db_store)

    knowledge_service = KnowledgeService(db_store, md_store, search_engine)

    resources_dir = tmp_path / ".devContextMemo" / "resources"
    resource_svc = ResourceService(db_store, resources_dir)

    return ContextQueryEngine(knowledge_service, resource_svc)


# =============================================================================
# 场景 1：导入 spec 文档 → 全链路验证
# =============================================================================


class TestImportSpecDocument:
    """AC-R01-03: 导入真实 spec 文档，验证存储 + 分块 + 搜索。"""

    def test_resource_record_created_in_db(self, spec_file, resource_service):
        """resource_id 生成正确 + resources 表有记录。"""
        result = resource_service.add(str(spec_file))

        assert result["resource_id"].startswith("res_")
        assert result["resource_id"] == f"res_{result['content_hash']}"
        assert len(result["content_hash"]) == 16

    def test_resource_type_auto_inferred_as_specs(self, spec_file, resource_service):
        """type 从目录名 specs/ 自动推断为 specs。"""
        result = resource_service.add(str(spec_file))
        assert result["type"] == "specs"

    def test_title_extracted_from_h1(self, spec_file, resource_service):
        """文档 H1 标题正确提取。"""
        result = resource_service.add(str(spec_file))
        assert result["title"] == "devContextMemo Phase 1 数据源偏离度调研与修复方案"

    def test_block_count_meets_threshold(self, spec_file, resource_service):
        """931 行文档 → 分块数 ≥ 30（heading/paragraph/table/code/list）。"""
        result = resource_service.add(str(spec_file))
        assert result["blocks"] >= 30, (
            f"Expected ≥ 30 blocks for 931-line spec, got {result['blocks']}"
        )

    def test_all_four_block_types_present(self, spec_file, resource_service):
        """分块类型包含 heading/paragraph/table/code 全部 4 类。"""
        result = resource_service.add(str(spec_file))
        blocks = resource_service.get_blocks(result["resource_id"])

        block_types = {b["block_type"] for b in blocks}
        required = {"heading", "paragraph", "table", "code"}
        missing = required - block_types
        assert not missing, (
            f"Missing block types: {missing}. Found: {sorted(block_types)}"
        )

    def test_file_copied_to_resources_dir(self, spec_file, resource_service):
        """文件落地到 .devContextMemo/resources/specs/ 下。"""
        result = resource_service.add(str(spec_file))

        uri = result["uri"]
        assert uri.startswith("resources/specs/"), f"Unexpected uri: {uri}"

        file_path = resource_service.resources_dir.parent / uri
        assert file_path.exists(), f"File not found at {file_path}"
        assert file_path.read_text(encoding="utf-8").startswith("# devContextMemo")

    def test_fts5_search_finds_expected_keyword(self, spec_file, resource_service):
        """"双轨制" 在文档中出现 10 次，FTS5 搜索应命中 ≥ 3。"""
        resource_service.add(str(spec_file))

        results = resource_service.search("双轨制")
        assert len(results) >= 3, (
            f"FTS5 search for '双轨制' returned {len(results)} blocks, expected ≥ 3"
        )

    def test_fts5_search_on_hindsight(self, spec_file, resource_service):
        """"Hindsight" 是特有术语，搜索应命中。"""
        resource_service.add(str(spec_file))

        results = resource_service.search("Hindsight")
        assert len(results) >= 1, (
            f"FTS5 search for 'Hindsight' returned {len(results)} blocks, expected ≥ 1"
        )


# =============================================================================
# 场景 2：双轨并行检索
# =============================================================================


class TestDualTrackQuery:
    """AC-S01-03: 记忆轨 + 资源轨同时命中 / 三级回退。"""

    def _insert_knowledge(self, db_store, knowledge_id, title, domain, text):
        """直接 INSERT 一条知识到 knowledge_index + knowledge_fts。"""
        import datetime as dt

        now = dt.datetime.now(dt.UTC).isoformat()
        conn = db_store.get_connection()
        conn.execute(
            """INSERT INTO knowledge_index
               (id, title, domain, sub_domain, granularity, stability, depth,
                status, confidence, code_verified, prune_priority, certainty,
                freshness, uri, used_count, calibration_status, created_at,
                updated_at, stale_check_count, restored_count, evidence_level,
                code_active, auto_adopted_unreviewed, knowledge_type)
               VALUES (?, ?, ?, '', 'L1', 'S2', 'KY', 'active',
                       0.85, 1, 0.0, 0.5, 0.5, '', 0, 'uncalibrated',
                       ?, ?, 0, 0, 5, 1, 0, ?)""",
            [knowledge_id, title, domain, now, now, "decision"],
        )
        if db_store.fts_available:
            row = conn.execute(
                "SELECT rowid FROM knowledge_index WHERE id=?", [knowledge_id]
            ).fetchone()
            if row:
                db_store._sync_fts(row[0], title, "", text[:200])
        conn.commit()

    def test_both_tracks_return_results_for_shared_keyword(
        self, spec_file, context_engine, db_store, resource_service
    ):
        """查询"双轨制"：记忆轨有决策知识 + 资源轨有 spec 段落。"""
        # 预植入决策知识
        self._insert_knowledge(
            db_store,
            knowledge_id="kw-e2e-001",
            title="双轨制架构决策",
            domain="architecture",
            text="双轨制是记忆轨+资源轨并行存储、交叉检索、显式链接的架构",
        )

        # 导入 spec（含"双轨制"10 处）
        resource_service.add(str(spec_file))

        bundle = context_engine.query("双轨制", top_k_knowledge=5, top_k_resource=5)
        assert len(bundle.memories) >= 1, "Memory track should return knowledge"
        assert len(bundle.resources) >= 1, "Resource track should return spec blocks"
        assert bundle.fallback_level == 1, (
            "Memory track hit should keep fallback at L1"
        )

    def test_resource_only_keyword_triggers_l2_fallback(
        self, spec_file, context_engine, db_store, resource_service
    ):
        """查询"OpenViking"：记忆轨无匹配 → 回退到 L2 资源轨。"""
        # 导入 spec（"OpenViking" 只出现在 spec 中，不在记忆轨）
        resource_service.add(str(spec_file))

        bundle = context_engine.query("OpenViking", top_k_knowledge=5, top_k_resource=5)
        assert len(bundle.memories) == 0, (
            "Memory track should have no match for 'OpenViking'"
        )
        assert len(bundle.resources) >= 1, (
            "Resource track should find 'OpenViking' in spec"
        )
        assert bundle.fallback_level == 2, (
            "Empty memory track should trigger L2 fallback"
        )

    def test_single_track_memory_query_works(self, context_engine, db_store):
        """单轨查询（memory）兼容已有调用方。"""
        self._insert_knowledge(
            db_store,
            knowledge_id="kw-e2e-002",
            title="测试知识",
            domain="test",
            text="这是一条测试知识",
        )
        results = context_engine.query_single_track("测试", track="memory")
        assert len(results) >= 1
        assert results[0]["track"] == "memory"

    def test_single_track_resource_query_works(self, spec_file, context_engine, resource_service):
        """单轨查询（resource）正常返回资源块。"""
        resource_service.add(str(spec_file))
        results = context_engine.query_single_track("双轨制", track="resource")
        assert len(results) >= 1


# =============================================================================
# 场景 3：去重 + 软删除降级
# =============================================================================


class TestDedupAndSoftDelete:
    """AC-R04-05 + AC-S04: 去重检测 + 软删除 + 检索降级。"""

    def test_duplicate_import_returns_unchanged(self, spec_file, resource_service):
        """同一文件导入两次 → 第二次返回 unchanged。"""
        result1 = resource_service.add(str(spec_file))
        assert "status" not in result1 or result1.get("status") != "unchanged"

        result2 = resource_service.add(str(spec_file))
        assert result2["status"] == "unchanged"
        assert result2["resource_id"] == result1["resource_id"]
        assert "already exists" in result2.get("message", "")

    def test_db_has_only_one_record_after_dedup(self, spec_file, resource_service):
        """去重后 DB 中只有 1 条 resources 记录。"""
        resource_service.add(str(spec_file))
        resource_service.add(str(spec_file))

        all_resources = resource_service.list()
        assert len(all_resources) == 1

    def test_soft_delete_sets_deleted_at(self, spec_file, resource_service):
        """软删除后 deleted_at 非空，但记录保留。"""
        result = resource_service.add(str(spec_file))
        resource_id = result["resource_id"]

        removed = resource_service.remove(resource_id)
        assert removed is True

        resource = resource_service.get(resource_id)
        assert resource is not None, "Record should still exist after soft delete"
        assert resource["deleted_at"] is not None, "deleted_at should be set"

    def test_list_excludes_soft_deleted(self, spec_file, resource_service):
        """resource.list() 不返回已软删除资源。"""
        result = resource_service.add(str(spec_file))
        resource_service.remove(result["resource_id"])

        all_resources = resource_service.list()
        resource_ids = {r["resource_id"] for r in all_resources}
        assert result["resource_id"] not in resource_ids

    def test_search_excludes_soft_deleted_resource_blocks(
        self, spec_file, resource_service, context_engine
    ):
        """已删除资源的块不应出现在检索结果中。"""
        result = resource_service.add(str(spec_file))
        resource_id = result["resource_id"]

        # 删除前搜索应命中
        before = resource_service.search("双轨制")
        assert len(before) >= 3

        # 软删除
        resource_service.remove(resource_id)

        # 删除后双轨检索不返回已删除资源
        bundle = context_engine.query("双轨制", top_k_resource=10)
        for r in bundle.resources:
            assert r["resource_id"] != resource_id, (
                f"Deleted resource {resource_id} should not appear"
            )

    def test_soft_delete_is_reversible(self, spec_file, resource_service):
        """软删除不删除物理文件，记录可通过 deleted_at=NULL 恢复。"""
        result = resource_service.add(str(spec_file))
        resource_id = result["resource_id"]

        resource_service.remove(resource_id)

        # 验证物理文件仍存在
        uri = result["uri"]
        file_path = resource_service.resources_dir.parent / uri
        assert file_path.exists(), "Physical file should still exist after soft delete"

        # 验证分块记录仍存在
        blocks = resource_service.get_blocks(resource_id)
        assert len(blocks) >= 30, "Blocks should be preserved after soft delete"
