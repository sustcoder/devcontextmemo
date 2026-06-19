"""Module tests for Step 4 — Jaccard 去重 + top_similar_id。"""

import json
from pathlib import Path

import pytest

from devcontext.core.pipeline.deduplicator import Deduplicator
from tests.conftest import write_jsonl, read_jsonl


def _make_record(knowledge_text="测试知识", content_hash=None, **overrides):
    base = {
        "session_id": "s1",
        "knowledge_text": knowledge_text,
        "granularity": "L2", "stability": "S3", "depth": "KH", "domain": "order",
        "confidence": 0.8, "occurred_at": None, "source_messages": [1],
        "status": "staged", "entities": [], "relations": [],
        "content_hash": content_hash or "a" * 64,
        "semantic_hash": "b" * 16,
        "code_verified": 0,
    }
    base.update(overrides)
    return base


class TestDeduplicatorBasic:
    """基础去重流程。"""

    def test_adds_dedup_fields(self, tmp_path):
        rec = _make_record()
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        out = Deduplicator(tmp_path).process(path)
        results = read_jsonl(out)
        assert "top_similar_id" in results[0]
        assert "jaccard_score" in results[0]
        assert "is_duplicate" in results[0]

    def test_no_existing_all_new(self, tmp_path):
        rec = _make_record()
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        out = Deduplicator(tmp_path, existing_records=[]).process(path)
        results = read_jsonl(out)
        assert results[0]["top_similar_id"] is None
        assert results[0]["is_duplicate"] is False

    def test_preserves_input_fields(self, tmp_path):
        rec = _make_record()
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        out = Deduplicator(tmp_path).process(path)
        results = read_jsonl(out)
        for field in ("session_id", "knowledge_text", "content_hash", "code_verified"):
            assert results[0][field] == rec[field]


class TestExactMatch:
    """content_hash 精确匹配。"""

    def test_exact_hash_match_is_duplicate(self, tmp_path):
        existing = [{"id": "kw-old-001", "knowledge_text": "测试知识",
                      "content_hash": "a" * 64}]
        rec = _make_record(content_hash="a" * 64)
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        out = Deduplicator(tmp_path, existing_records=existing).process(path)
        results = read_jsonl(out)
        assert results[0]["is_duplicate"] is True
        assert results[0]["top_similar_id"] == "kw-old-001"
        assert results[0]["jaccard_score"] == 1.0

    def test_different_hash_not_duplicate(self, tmp_path):
        existing = [{"id": "kw-old-001", "knowledge_text": "完全不同",
                      "content_hash": "x" * 64}]
        rec = _make_record(content_hash="a" * 64)
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        out = Deduplicator(tmp_path, existing_records=existing).process(path)
        results = read_jsonl(out)
        assert results[0]["is_duplicate"] is False


class TestJaccardSimilarity:
    """Jaccard 相似度。"""

    def test_high_similarity_marks_similar(self, tmp_path):
        existing = [{"id": "kw-old-001", "knowledge_text": "订单幂等校验方案"}]
        rec = _make_record(knowledge_text="订单幂等校验方案")
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        out = Deduplicator(tmp_path, existing_records=existing).process(path)
        results = read_jsonl(out)
        assert results[0]["jaccard_score"] >= 0.90
        assert results[0]["is_duplicate"] is True

    def test_low_similarity_no_match(self, tmp_path):
        existing = [{"id": "kw-old-001", "knowledge_text": "部署配置管理"}]
        rec = _make_record(knowledge_text="订单幂等校验方案")
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        out = Deduplicator(tmp_path, existing_records=existing).process(path)
        results = read_jsonl(out)
        assert results[0]["jaccard_score"] <= 0.30
        assert results[0]["top_similar_id"] is None

    def test_jaccard_score_in_range(self, tmp_path):
        existing = [{"id": "kw-old-001", "knowledge_text": "订单幂等校验"}]
        rec = _make_record(knowledge_text="订单幂等校验方案细节")
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        out = Deduplicator(tmp_path, existing_records=existing).process(path)
        results = read_jsonl(out)
        assert 0.0 <= results[0]["jaccard_score"] <= 1.0


class TestDeduplicatorEdgeCases:
    """边界场景。"""

    def test_empty_file_raises(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        write_jsonl(path, [])
        with pytest.raises(ValueError, match="empty"):
            Deduplicator(tmp_path).process(path)

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Deduplicator(tmp_path).process(tmp_path / "nonexistent.jsonl")
