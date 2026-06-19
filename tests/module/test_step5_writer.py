"""Module tests for Step 5 — MD → DB 原子写入（绿色通道 + MD first → DB second）。"""

import json
from pathlib import Path

import pytest

from devcontext.core.pipeline.writer import Writer, WriteResult, GREEN_CHANNEL_THRESHOLD
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore
from tests.conftest import write_jsonl


def _make_knowledge_record(confidence=0.87, **overrides):
    base = {
        "session_id": "s1",
        "knowledge_text": "OrderService.createOrder 需要幂等校验",
        "granularity": "L3", "stability": "S4", "depth": "KH", "domain": "order",
        "confidence": confidence, "occurred_at": "2026-06-18T09:58:00Z",
        "source_messages": [1], "status": "staged",
        "entities": [{"name": "OrderService", "type": "class", "file": "src/OrderService.java"}],
        "relations": [],
        "content_hash": "a" * 64, "semantic_hash": "b" * 16, "code_verified": 1,
        "top_similar_id": None, "jaccard_score": 0.0, "is_duplicate": False,
    }
    base.update(overrides)
    return base


@pytest.fixture
def md_store(tmp_path):
    return MarkdownStore(
        staging_dir=tmp_path / "staging",
        knowledge_dir=tmp_path / "knowledge",
        deprecated_dir=tmp_path / "deprecated",
    )


@pytest.fixture
def db_store():
    store = SQLiteStore(":memory:")
    store.init_db()
    return store


# =============================================================================
# 绿色通道
# =============================================================================

class TestGreenChannel:
    """绿色通道（confidence >= 0.95 → knowledge/）。"""

    def test_high_confidence_writes_to_knowledge(self, tmp_path, md_store, db_store):
        rec = _make_knowledge_record(confidence=0.97)
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        writer = Writer(md_store, db_store)
        results = writer.process(path)
        assert len(results) == 1
        assert results[0].target == "knowledge"
        assert "knowledge" in results[0].md_path
        assert "order" in results[0].md_path

    def test_low_confidence_writes_to_staging(self, tmp_path, md_store, db_store):
        rec = _make_knowledge_record(confidence=0.78)
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        writer = Writer(md_store, db_store)
        results = writer.process(path)
        assert len(results) == 1
        assert results[0].target == "staging"
        assert "staging" in results[0].md_path


# =============================================================================
# 原子写入
# =============================================================================

class TestAtomicity:
    """MD first → DB second。"""

    def test_md_success_db_success(self, tmp_path, md_store, db_store):
        rec = _make_knowledge_record()
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        writer = Writer(md_store, db_store)
        results = writer.process(path)
        assert results[0].md_success is True
        assert results[0].db_success is True
        assert Path(results[0].md_path).exists()

    def test_md_success_without_db(self, tmp_path, md_store):
        """SQLiteStore=None 时只写 MD。"""
        rec = _make_knowledge_record()
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        writer = Writer(md_store, sqlite_store=None)
        results = writer.process(path)
        assert results[0].md_success is True
        assert results[0].db_success is False
        assert Path(results[0].md_path).exists()

    def test_db_record_matches_md(self, tmp_path, md_store, db_store):
        rec = _make_knowledge_record(confidence=0.97)
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        writer = Writer(md_store, db_store)
        results = writer.process(path)

        conn = db_store.get_connection()
        db_rec = conn.execute(
            "SELECT id, domain, confidence, code_verified, uri FROM knowledge_index"
        ).fetchone()
        assert db_rec[0] == results[0].knowledge_id
        assert db_rec[1] == "order"
        assert db_rec[2] == 0.97
        assert db_rec[3] == 1
        assert db_rec[4] == results[0].md_path


# =============================================================================
# 重复跳过
# =============================================================================

class TestDuplicateSkip:
    """is_duplicate=True 的记录被跳过。"""

    def test_duplicate_skipped(self, tmp_path, md_store, db_store):
        recs = [
            _make_knowledge_record(knowledge_text="知识A", is_duplicate=False),
            _make_knowledge_record(knowledge_text="知识B", is_duplicate=True),
        ]
        path = tmp_path / "k.jsonl"
        write_jsonl(path, recs)
        writer = Writer(md_store, db_store)
        results = writer.process(path)
        assert len(results) == 1  # 只有第1条写入


# =============================================================================
# WriteResult
# =============================================================================

class TestWriteResult:
    """WriteResult 结构。"""

    def test_result_has_all_fields(self, tmp_path, md_store, db_store):
        rec = _make_knowledge_record()
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        writer = Writer(md_store, db_store)
        results = writer.process(path)
        d = results[0].to_dict()
        for field in ("knowledge_id", "md_path", "md_success", "db_success",
                      "status", "target", "error"):
            assert field in d

    def test_knowledge_id_format(self, tmp_path, md_store, db_store):
        rec = _make_knowledge_record()
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        writer = Writer(md_store, db_store)
        results = writer.process(path)
        assert results[0].knowledge_id.startswith("kw-")


# =============================================================================
# 边界场景
# =============================================================================

class TestWriterEdgeCases:
    """边界场景。"""

    def test_empty_file_returns_empty(self, tmp_path, md_store, db_store):
        path = tmp_path / "empty.jsonl"
        write_jsonl(path, [])
        writer = Writer(md_store, db_store)
        results = writer.process(path)
        assert results == []

    def test_file_not_found_raises(self, tmp_path, md_store, db_store):
        writer = Writer(md_store, db_store)
        with pytest.raises(FileNotFoundError):
            writer.process(tmp_path / "nonexistent.jsonl")
