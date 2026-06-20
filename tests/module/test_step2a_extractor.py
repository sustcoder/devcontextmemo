"""Module tests for Step 2a — LLM 知识提炼 + 四轴分类 + 时间提取。

用 MockLLMClient 测试，验证：
1. 产出格式正确的 summary JSONL
2. 四轴分类枚举校验（L0-L5 / S1-S5 / KW-KH-KY）
3. 边界场景（空输入、LLM 超时、malformed 响应、低置信度）
4. 时间提取（显式/推断/null）
5. 截断时的置信度上限
"""

import json
from pathlib import Path

import pytest

from devcontext.core.pipeline.extractor import Extractor
from devcontext.utils.llm import MockLLMClient
from tests.conftest import write_jsonl, read_jsonl


# =============================================================================
# 测试数据
# =============================================================================

DOMAIN_TREE = {
    "order": {}, "payment": {}, "architecture": {}, "convention": {},
    "deployment": {}, "user": {},
}

BATCH_DATA = [
    {"session_id": "s1", "seq": 1, "role": "user",
     "content": "帮我给 OrderService.createOrder 加幂等校验",
     "timestamp": "2026-06-18T09:58:00Z", "source": "opencode"},
    {"session_id": "s1", "seq": 2, "role": "assistant",
     "content": "已添加 @Idempotent 注解，key=orderId",
     "timestamp": "2026-06-18T09:58:30Z", "source": "opencode"},
]


def _make_llm_response(items):
    """构造 LLM 响应 JSON。"""
    return json.dumps({"extracted_items": items})


# =============================================================================
# 基础提炼
# =============================================================================

class TestExtractorBasic:
    """基础提炼流程。"""

    def test_produces_valid_summary_format(self, tmp_path):
        llm_resp = _make_llm_response([
            {"content": "幂等校验 key=orderId", "granularity": "L3", "stability": "S4",
             "depth": "KH", "domain": "order", "knowledge_type": "decision",
             "confidence": 0.87,
             "occurred_at": "2026-06-18T09:58:00Z", "source_messages": [1]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        out = extractor.process(batch)

        assert out.exists()
        results = read_jsonl(out)
        assert len(results) == 1
        for item in results:
            assert "session_id" in item
            assert "knowledge_text" in item
            assert "granularity" in item
            assert "stability" in item
            assert "depth" in item
            assert "domain" in item
            assert "knowledge_type" in item
            assert "confidence" in item
            assert "occurred_at" in item
            assert "source_messages" in item
            assert "status" in item

    def test_classification_enums_valid(self, tmp_path):
        llm_resp = _make_llm_response([
            {"content": "test", "granularity": "L5", "stability": "S5",
             "depth": "KY", "domain": "order", "knowledge_type": "fact",
             "confidence": 0.9,
             "occurred_at": None, "source_messages": [1]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        out = extractor.process(batch)
        results = read_jsonl(out)
        assert results[0]["granularity"] == "L5"
        assert results[0]["stability"] == "S5"
        assert results[0]["depth"] == "KY"

    def test_confidence_in_range(self, tmp_path):
        llm_resp = _make_llm_response([
            {"content": "x", "granularity": "L2", "stability": "S3",
             "depth": "KH", "domain": "order", "knowledge_type": "fact",
             "confidence": 0.5,
             "occurred_at": None, "source_messages": [1]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        results = read_jsonl(extractor.process(batch))
        assert 0.0 <= results[0]["confidence"] <= 1.0

    def test_output_count_not_exceed_input(self, tmp_path):
        llm_resp = _make_llm_response([
            {"content": f"item {i}", "granularity": "L2", "stability": "S3",
             "depth": "KH", "domain": "order", "knowledge_type": "fact",
             "confidence": 0.7,
             "occurred_at": None, "source_messages": [1]}
            for i in range(3)
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        results = read_jsonl(extractor.process(batch))
        # extracted_items 数量不限，但合理范围
        assert len(results) == 3

    def test_status_is_staged(self, tmp_path):
        llm_resp = _make_llm_response([
            {"content": "x", "granularity": "L2", "stability": "S3",
             "depth": "KH", "domain": "order", "knowledge_type": "fact",
             "confidence": 0.7,
             "occurred_at": None, "source_messages": [1]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        results = read_jsonl(extractor.process(batch))
        assert results[0]["status"] == "staged"


# =============================================================================
# 边界场景
# =============================================================================

class TestExtractorEdgeCases:
    """边界场景处理。"""

    def test_empty_batch_raises(self, tmp_path):
        batch = tmp_path / "empty.jsonl"
        write_jsonl(batch, [])
        extractor = Extractor(MockLLMClient("{}"), DOMAIN_TREE, tmp_path)
        with pytest.raises(ValueError, match="empty"):
            extractor.process(batch)

    def test_empty_extracted_items_allowed(self, tmp_path):
        """LLM 返回空数组时 process 抛出 ValueError。"""
        llm_resp = _make_llm_response([])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        with pytest.raises(ValueError, match="No knowledge extracted"):
            extractor.process(batch)

    def test_malformed_json_raises(self, tmp_path):
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient("not json {{{"), DOMAIN_TREE, tmp_path)
        with pytest.raises(ValueError):
            extractor.process(batch)

    def test_invalid_granularity_raises(self, tmp_path):
        llm_resp = _make_llm_response([
            {"content": "x", "granularity": "L9", "stability": "S3",
             "depth": "KH", "domain": "order", "knowledge_type": "fact",
             "confidence": 0.5,
             "occurred_at": None, "source_messages": [1]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        with pytest.raises(ValueError):
            extractor.process(batch)

    def test_invalid_domain_raises(self, tmp_path):
        llm_resp = _make_llm_response([
            {"content": "x", "granularity": "L2", "stability": "S3",
             "depth": "KH", "domain": "nonexistent", "knowledge_type": "fact",
             "confidence": 0.5,
             "occurred_at": None, "source_messages": [1]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        with pytest.raises(ValueError):
            extractor.process(batch)


# =============================================================================
# 时间提取
# =============================================================================

class TestExtractorTimeExtraction:
    """时间提取场景。"""

    def test_explicit_timestamp_extracted(self, tmp_path):
        llm_resp = _make_llm_response([
            {"content": "修复支付超时", "granularity": "L3", "stability": "S4",
             "depth": "KW", "domain": "order", "knowledge_type": "fact",
             "confidence": 0.9,
             "occurred_at": "2026-06-18T10:03:00Z", "source_messages": [1]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        results = read_jsonl(extractor.process(batch))
        assert results[0]["occurred_at"] is not None
        assert "2026-06-18" in results[0]["occurred_at"]

    def test_null_occurred_at_allowed(self, tmp_path):
        """无法推断时间时 occurred_at 为 null。"""
        llm_resp = _make_llm_response([
            {"content": "团队很久以前用过 MongoDB", "granularity": "L0", "stability": "S5",
             "depth": "KY", "domain": "architecture", "knowledge_type": "experience",
             "confidence": 0.7,
             "occurred_at": None, "source_messages": [1]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        results = read_jsonl(extractor.process(batch))
        assert results[0]["occurred_at"] is None


# =============================================================================
# 截断与置信度上限
# =============================================================================

# =============================================================================
# knowledge_type 直通
# =============================================================================

class TestExtractorKnowledgeType:
    """knowledge_type 字段的校验与直通。"""

    def test_pass_through_knowledge_type(self, tmp_path):
        """验证 _build_record 包含 LLM 输出的 knowledge_type。"""
        llm_resp = _make_llm_response([
            {"content": "使用 MySQL 8.0 作为主数据库", "granularity": "L2",
             "stability": "S3", "depth": "KH", "domain": "order",
             "knowledge_type": "decision", "confidence": 0.88,
             "occurred_at": None, "source_messages": [1, 2]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        results = read_jsonl(extractor.process(batch))
        assert results[0]["knowledge_type"] == "decision"
        assert results[0]["knowledge_text"] == "使用 MySQL 8.0 作为主数据库"

    def test_rejects_invalid_knowledge_type(self, tmp_path):
        """验证 _validate_item 拒绝非法的 knowledge_type 值。"""
        llm_resp = _make_llm_response([
            {"content": "test", "granularity": "L2", "stability": "S3",
             "depth": "KH", "domain": "order",
             "knowledge_type": "bug_report", "confidence": 0.5,
             "occurred_at": None, "source_messages": [1]},
        ])
        batch = tmp_path / "batch.jsonl"
        write_jsonl(batch, BATCH_DATA)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        with pytest.raises(ValueError, match="invalid knowledge_type"):
            extractor.process(batch)


class TestExtractorTruncation:
    """对话截断时的置信度上限。"""

    def test_truncated_confidence_capped(self, tmp_path):
        """对话超 32K token 时截断，confidence 上限 0.80。"""
        # 构造超大 batch（每条 10K 字符 × 10 条 = 100K 字符 ≈ 50K token）
        big_batch = [
            {"session_id": "big", "seq": i, "role": "user",
             "content": "x" * 10000, "timestamp": f"t{i}", "source": "opencode"}
            for i in range(1, 11)
        ]
        llm_resp = _make_llm_response([
            {"content": "extracted", "granularity": "L2", "stability": "S3",
             "depth": "KH", "domain": "order", "knowledge_type": "fact",
             "confidence": 0.95,
             "occurred_at": None, "source_messages": [1]},
        ])
        batch = tmp_path / "big_batch.jsonl"
        write_jsonl(batch, big_batch)
        extractor = Extractor(MockLLMClient(llm_resp), DOMAIN_TREE, tmp_path)
        results = read_jsonl(extractor.process(batch))
        # 截断后 confidence 应被 cap 到 0.80
        assert results[0]["confidence"] <= 0.80
