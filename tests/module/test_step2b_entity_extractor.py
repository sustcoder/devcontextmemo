"""Module tests for Step 2b — LLM 实体 + 关系提取。

用 MockLLMClient 测试，验证：
1. 产出格式正确的 knowledge JSONL（含 entities/relations）
2. 实体类型/关系类型枚举校验
3. 实体去重
4. 关系 source 必须在 entities 中
5. summary 字段完整保留
6. LLM 失败时优雅降级为空实体
"""

import json
from pathlib import Path

import pytest

from devcontext.core.pipeline.entity_extractor import EntityExtractor
from devcontext.utils.llm import MockLLMClient
from tests.conftest import write_jsonl, read_jsonl


# =============================================================================
# 测试数据
# =============================================================================

SUMMARY_DATA = [
    {
        "session_id": "s1",
        "knowledge_text": "OrderService.createOrder 需要幂等校验，使用 @Idempotent 注解，key=orderId",
        "granularity": "L3", "stability": "S4", "depth": "KH", "domain": "order",
        "confidence": 0.87, "occurred_at": "2026-06-18T09:58:00Z",
        "source_messages": [1], "status": "staged",
    },
    {
        "session_id": "s1",
        "knowledge_text": "交易超时统一 30 秒",
        "granularity": "L3", "stability": "S4", "depth": "KW", "domain": "order",
        "confidence": 0.78, "occurred_at": "2026-06-18T09:58:30Z",
        "source_messages": [2], "status": "staged",
    },
]


def _make_entity_response(entities, relations):
    return json.dumps({"entities": entities, "relations": relations})


# =============================================================================
# 基础提取
# =============================================================================

class TestEntityExtractorBasic:
    """基础实体关系提取。"""

    def test_produces_knowledge_with_entities(self, tmp_path):
        resp = _make_entity_response(
            [{"name": "OrderService", "type": "class", "file": "src/OrderService.java"}],
            [{"source": "OrderService", "target": "Idempotent", "type": "uses"}],
        )
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [SUMMARY_DATA[0]])
        extractor = EntityExtractor(MockLLMClient(resp), tmp_path)
        out = extractor.process(summary)

        assert out.exists()
        results = read_jsonl(out)
        assert len(results) == 1
        assert "entities" in results[0]
        assert "relations" in results[0]
        assert len(results[0]["entities"]) == 1
        assert results[0]["entities"][0]["name"] == "OrderService"
        assert results[0]["entities"][0]["type"] == "class"
        assert results[0]["entities"][0]["file"] == "src/OrderService.java"

    def test_preserves_summary_fields(self, tmp_path):
        """summary 字段完整保留。"""
        resp = _make_entity_response([], [])
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [SUMMARY_DATA[0]])
        extractor = EntityExtractor(MockLLMClient(resp), tmp_path)
        results = read_jsonl(extractor.process(summary))

        for field in ("session_id", "knowledge_text", "granularity", "stability",
                      "depth", "domain", "confidence", "occurred_at",
                      "source_messages", "status"):
            assert field in results[0]
            assert results[0][field] == SUMMARY_DATA[0][field]

    def test_empty_entities_allowed(self, tmp_path):
        """LLM 返回空实体是合法的。"""
        resp = _make_entity_response([], [])
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [SUMMARY_DATA[0]])
        extractor = EntityExtractor(MockLLMClient(resp), tmp_path)
        results = read_jsonl(extractor.process(summary))
        assert results[0]["entities"] == []
        assert results[0]["relations"] == []

    def test_one_output_per_input(self, tmp_path):
        """每条 input 产生恰好一条 output。"""
        counter = {"n": 0}
        resps = [
            _make_entity_response([{"name": "A", "type": "class"}], []),
            _make_entity_response([{"name": "B", "type": "method"}], []),
        ]
        def fn(msgs):
            i = counter["n"]; counter["n"] += 1
            return resps[i] if i < len(resps) else resps[-1]
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, SUMMARY_DATA)
        extractor = EntityExtractor(MockLLMClient(response_func=fn), tmp_path)
        results = read_jsonl(extractor.process(summary))
        assert len(results) == 2


# =============================================================================
# 实体校验
# =============================================================================

class TestEntityValidation:
    """实体类型校验。"""

    def test_all_entity_types_valid(self, tmp_path):
        """14 种实体类型全部合法。"""
        entities = [
            {"name": t, "type": t}
            for t in ("class", "interface", "method", "function", "module",
                      "file", "config_file", "pattern", "concept", "tool",
                      "service", "database", "api", "other")
        ]
        resp = _make_entity_response(entities, [])
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [SUMMARY_DATA[0]])
        extractor = EntityExtractor(MockLLMClient(resp), tmp_path)
        results = read_jsonl(extractor.process(summary))
        assert len(results[0]["entities"]) == 14

    def test_duplicate_entities_deduplicated(self, tmp_path):
        """同名实体去重。"""
        resp = _make_entity_response(
            [{"name": "Foo", "type": "class"},
             {"name": "Foo", "type": "class"},
             {"name": "Bar", "type": "method"}],
            [],
        )
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [SUMMARY_DATA[0]])
        extractor = EntityExtractor(MockLLMClient(resp), tmp_path)
        results = read_jsonl(extractor.process(summary))
        assert len(results[0]["entities"]) == 2

    def test_empty_entity_name_rejected(self, tmp_path):
        """空实体名拒绝（降级为空）。"""
        resp = _make_entity_response([{"name": "", "type": "class"}], [])
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [SUMMARY_DATA[0]])
        extractor = EntityExtractor(MockLLMClient(resp), tmp_path)
        results = read_jsonl(extractor.process(summary))
        # 3 次重试失败 → 降级为空
        assert results[0]["entities"] == []


# =============================================================================
# 关系校验
# =============================================================================

class TestRelationValidation:
    """关系类型校验。"""

    def test_all_relation_types_valid(self, tmp_path):
        """10 种关系类型全部合法。"""
        entities = [{"name": f"E{i}", "type": "class"} for i in range(10)]
        relations = [
            {"source": f"E{i}", "target": f"E{(i+1) % 10}", "type": t}
            for i, t in enumerate(
                ("extends", "implements", "uses", "depends_on", "handles",
                 "configures", "belongs_to", "triggers", "calls", "references")
            )
        ]
        resp = _make_entity_response(entities, relations)
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [SUMMARY_DATA[0]])
        extractor = EntityExtractor(MockLLMClient(resp), tmp_path)
        results = read_jsonl(extractor.process(summary))
        assert len(results[0]["relations"]) == 10

    def test_relation_source_not_in_entities_rejected(self, tmp_path):
        """关系 source 不在 entities 中 → 降级为空。"""
        resp = _make_entity_response(
            [{"name": "Foo", "type": "class"}],
            [{"source": "Bar", "target": "Foo", "type": "uses"}],
        )
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [SUMMARY_DATA[0]])
        extractor = EntityExtractor(MockLLMClient(resp), tmp_path)
        results = read_jsonl(extractor.process(summary))
        assert results[0]["entities"] == []
        assert results[0]["relations"] == []


# =============================================================================
# 优雅降级
# =============================================================================

class TestGracefulDegradation:
    """LLM 失败时的优雅降级。"""

    def test_malformed_json_degrades_to_empty(self, tmp_path):
        """LLM 返回非 JSON → 3 次重试后降级为空实体。"""
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [SUMMARY_DATA[0]])
        extractor = EntityExtractor(MockLLMClient("not json"), tmp_path)
        results = read_jsonl(extractor.process(summary))
        assert results[0]["entities"] == []
        assert results[0]["relations"] == []

    def test_empty_summary_produces_empty_output(self, tmp_path):
        summary = tmp_path / "summary_s1.jsonl"
        write_jsonl(summary, [])
        extractor = EntityExtractor(MockLLMClient("{}"), tmp_path)
        out = extractor.process(summary)
        assert out.exists()
