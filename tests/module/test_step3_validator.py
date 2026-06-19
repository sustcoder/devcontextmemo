"""Module tests for Step 3 — 签名 + code_verified 设置。"""

import json
from pathlib import Path

import pytest

from devcontext.core.pipeline.validator import Validator
from tests.conftest import write_jsonl, read_jsonl


def _make_knowledge_record(**overrides):
    base = {
        "session_id": "s1",
        "knowledge_text": "OrderService.createOrder 需要幂等校验",
        "granularity": "L3", "stability": "S4", "depth": "KH", "domain": "order",
        "confidence": 0.87, "occurred_at": "2026-06-18T09:58:00Z",
        "source_messages": [1], "status": "staged",
        "entities": [{"name": "OrderService", "type": "class", "file": "src/OrderService.java"}],
        "relations": [],
    }
    base.update(overrides)
    return base


class TestValidatorBasic:
    """基础验证流程。"""

    def test_adds_hash_fields(self, tmp_path):
        rec = _make_knowledge_record()
        path = tmp_path / "knowledge_s1.jsonl"
        write_jsonl(path, [rec])
        out = Validator(tmp_path).process(path)
        results = read_jsonl(out)
        assert "content_hash" in results[0]
        assert "semantic_hash" in results[0]
        assert "code_verified" in results[0]

    def test_content_hash_is_64_hex(self, tmp_path):
        rec = _make_knowledge_record()
        path = tmp_path / "knowledge_s1.jsonl"
        write_jsonl(path, [rec])
        out = Validator(tmp_path).process(path)
        results = read_jsonl(out)
        assert len(results[0]["content_hash"]) == 64
        int(results[0]["content_hash"], 16)  # valid hex

    def test_semantic_hash_is_16_hex(self, tmp_path):
        rec = _make_knowledge_record()
        path = tmp_path / "knowledge_s1.jsonl"
        write_jsonl(path, [rec])
        out = Validator(tmp_path).process(path)
        results = read_jsonl(out)
        assert len(results[0]["semantic_hash"]) == 16
        int(results[0]["semantic_hash"], 16)

    def test_preserves_input_fields(self, tmp_path):
        rec = _make_knowledge_record()
        path = tmp_path / "knowledge_s1.jsonl"
        write_jsonl(path, [rec])
        out = Validator(tmp_path).process(path)
        results = read_jsonl(out)
        for field in ("session_id", "knowledge_text", "granularity", "stability",
                      "depth", "domain", "confidence", "occurred_at",
                      "source_messages", "status", "entities", "relations"):
            assert results[0][field] == rec[field]


class TestCodeVerified:
    """code_verified 设置。"""

    def test_code_verified_1_with_file_entity(self, tmp_path):
        rec = _make_knowledge_record(
            entities=[{"name": "Foo", "type": "class", "file": "src/Foo.java"}]
        )
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        results = read_jsonl(Validator(tmp_path).process(path))
        assert results[0]["code_verified"] == 1

    def test_code_verified_0_without_file(self, tmp_path):
        rec = _make_knowledge_record(
            entities=[{"name": "Foo", "type": "class"}]  # 无 file
        )
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        results = read_jsonl(Validator(tmp_path).process(path))
        assert results[0]["code_verified"] == 0

    def test_code_verified_0_empty_entities(self, tmp_path):
        rec = _make_knowledge_record(entities=[])
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec])
        results = read_jsonl(Validator(tmp_path).process(path))
        assert results[0]["code_verified"] == 0


class TestHashConsistency:
    """哈希一致性。"""

    def test_identical_text_same_hash(self, tmp_path):
        rec1 = _make_knowledge_record()
        rec2 = _make_knowledge_record()
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec1, rec2])
        results = read_jsonl(Validator(tmp_path).process(path))
        assert results[0]["content_hash"] == results[1]["content_hash"]

    def test_whitespace_normalized(self, tmp_path):
        rec1 = _make_knowledge_record(knowledge_text="hello world")
        rec2 = _make_knowledge_record(knowledge_text="hello  world")
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec1, rec2])
        results = read_jsonl(Validator(tmp_path).process(path))
        assert results[0]["content_hash"] == results[1]["content_hash"]

    def test_different_text_different_hash(self, tmp_path):
        rec1 = _make_knowledge_record(knowledge_text="知识A")
        rec2 = _make_knowledge_record(knowledge_text="知识B完全不同")
        path = tmp_path / "k.jsonl"
        write_jsonl(path, [rec1, rec2])
        results = read_jsonl(Validator(tmp_path).process(path))
        assert results[0]["content_hash"] != results[1]["content_hash"]


class TestValidatorEdgeCases:
    """边界场景。"""

    def test_empty_file_raises(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        write_jsonl(path, [])
        with pytest.raises(ValueError, match="empty"):
            Validator(tmp_path).process(path)

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Validator(tmp_path).process(tmp_path / "nonexistent.jsonl")
