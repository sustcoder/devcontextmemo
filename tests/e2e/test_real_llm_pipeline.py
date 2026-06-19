"""真实 LLM 端到端测试 — 完整流水线（Step 0→6）。

需要配置 API Key（MiniMax 或 GLM）：
    export DEVCONTEXT_LLM_API_KEY="your-api-key"
    export DEVCONTEXT_LLM_BASE_URL="https://api.minimax.chat/v1"
    export DEVCONTEXT_LLM_MODEL="MiniMax-Text-01"

未配置 API Key 时自动跳过。
"""

import json
import os
import pathlib
from typing import Any

import pytest

from devcontext.config import settings
from devcontext.core.adapters.base import BaseAdapter
from devcontext.core.pipeline.batcher import Batcher
from devcontext.core.pipeline.consolidator import Consolidator
from devcontext.core.pipeline.deduplicator import Deduplicator
from devcontext.core.pipeline.entity_extractor import EntityExtractor
from devcontext.core.pipeline.extractor import Extractor
from devcontext.core.pipeline.receiver import Receiver
from devcontext.core.pipeline.validator import Validator
from devcontext.core.pipeline.writer import Writer
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore
from devcontext.utils.llm import OpenAICompatibleClient
from tests.conftest import read_jsonl


class _MockAdapter(BaseAdapter):
    """测试用 Mock 适配器，继承 BaseAdapter 以获得 normalize_all。"""

    source_name = "opencode"

    def __init__(self, content: str, session_id: str = "real-001", assistant: str = "") -> None:
        self._content = content
        self._session_id = session_id
        self._assistant_content = assistant

    def collect(self, source_path: str | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = [{
            "session_id": self._session_id, "seq": 1, "role": "user",
            "content": self._content,
            "timestamp": "2026-06-18T10:00:00Z", "source": "opencode",
        }]
        if self._assistant_content:
            records.append({
                "session_id": self._session_id, "seq": 2, "role": "assistant",
                "content": self._assistant_content,
                "timestamp": "2026-06-18T10:00:30Z", "source": "opencode",
            })
        return records

    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        return raw_record


def _api_key_configured() -> bool:
    """检查是否配置了 LLM API Key。"""
    return bool(os.environ.get("DEVCONTEXT_LLM_API_KEY") or settings.llm_api_key)


def _make_real_client() -> OpenAICompatibleClient:
    """创建真实 LLM 客户端。"""
    return OpenAICompatibleClient(
        api_key=os.environ.get("DEVCONTEXT_LLM_API_KEY", settings.llm_api_key),
        base_url=os.environ.get("DEVCONTEXT_LLM_BASE_URL", settings.llm_base_url),
        model=os.environ.get("DEVCONTEXT_LLM_MODEL", settings.llm_model),
        timeout=60.0,
        max_retries=2,
    )


DOMAIN_TREE = {"order": {}, "payment": {}, "architecture": {}, "convention": {}}


skip_if_no_api_key = pytest.mark.skipif(
    not _api_key_configured(),
    reason="LLM API Key 未配置（设置 DEVCONTEXT_LLM_API_KEY 环境变量）",
)


@pytest.mark.e2e
@pytest.mark.slow
class TestRealLLMEndToEnd:
    """真实 LLM 端到端流水线测试。"""

    @skip_if_no_api_key
    def test_real_extractor_with_llm(self, tmp_path):
        """真实 LLM Step 2a：提取知识摘要。"""
        raw_dir = tmp_path / "raw"
        staging_dir = tmp_path / "staging"

        # Step 0: Receiver
        adapter = _MockAdapter(
            content="OrderService.createOrder 必须进行幂等校验，使用 @Idempotent 注解，key 为 orderId，不能使用 transactionId",
            session_id="real-001",
            assistant="已添加幂等校验逻辑，使用 Redis 分布式锁确保同一 orderId 不会被重复处理",
        )
        receiver = Receiver(adapter, raw_dir)
        receiver.receive()

        # Step 1: Batcher
        batcher = Batcher(raw_dir, staging_dir, token_threshold=6000)
        batch_files = batcher.process(flush_all=True)

        # Step 2a: Extractor (真实 LLM)
        llm = _make_real_client()
        extractor = Extractor(llm, DOMAIN_TREE, staging_dir)
        summary_path = extractor.process(batch_files[0])

        summaries = read_jsonl(summary_path)
        assert len(summaries) >= 1
        assert "knowledge_text" in summaries[0]
        assert "confidence" in summaries[0]
        assert 0.0 <= summaries[0]["confidence"] <= 1.0

    @skip_if_no_api_key
    def test_real_entity_extractor_with_llm(self, tmp_path):
        """真实 LLM Step 2b：提取实体和关系。"""
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        # 创建 Step 2a 的输出
        summary_path = staging_dir / "batch_step2a_test.jsonl"
        summary_path.write_text(
            json.dumps({
                "knowledge_text": "OrderService.addOrder 需要分布式锁确保幂等",
                "granularity": "L3", "stability": "S4", "depth": "KH",
                "domain": "order", "confidence": 0.85,
                "occurred_at": None, "source_messages": [1],
            }, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Step 2b: EntityExtractor (真实 LLM)
        llm = _make_real_client()
        entity_extractor = EntityExtractor(llm, staging_dir)
        knowledge_path = entity_extractor.process(summary_path)

        knowledge = read_jsonl(knowledge_path)
        assert len(knowledge) >= 1
        if "entities" in knowledge[0]:
            assert isinstance(knowledge[0]["entities"], list)
        if "relations" in knowledge[0]:
            assert isinstance(knowledge[0]["relations"], list)

    @skip_if_no_api_key
    def test_real_full_pipeline_step0_to_5(self, tmp_path):
        """真实 LLM 完整流水线 Step 0→5（单会话）。"""
        raw_dir = tmp_path / "raw"
        staging_dir = tmp_path / "staging"
        md_staging = tmp_path / ".devContextMemo" / "staging"
        md_knowledge = tmp_path / ".devContextMemo" / "knowledge"
        md_deprecated = tmp_path / ".devContextMemo" / "deprecated"

        # Step 0: Receiver
        adapter = _MockAdapter("支付回调接口必须验证签名，使用 HMAC-SHA256 算法，签名 key 从配置中心获取，不可硬编码", "real-full-001")
        receiver = Receiver(adapter, raw_dir)
        receiver.receive()

        # Step 1: Batcher
        batcher = Batcher(raw_dir, staging_dir, token_threshold=6000)
        batch_files = batcher.process(flush_all=True)
        assert len(batch_files) == 1

        # Step 2a: Extractor (真实 LLM)
        llm = _make_real_client()
        extractor = Extractor(llm, DOMAIN_TREE, staging_dir)
        summary_path = extractor.process(batch_files[0])
        summaries = read_jsonl(summary_path)
        assert len(summaries) >= 1

        # Step 2b: EntityExtractor (真实 LLM)
        entity_extractor = EntityExtractor(llm, staging_dir)
        knowledge_path = entity_extractor.process(summary_path)

        # Step 3: Validator
        validated_path = Validator(staging_dir).process(knowledge_path)
        validated = read_jsonl(validated_path)
        assert len(validated[0]["content_hash"]) == 64

        # Step 4: Deduplicator
        deduplicator = Deduplicator(staging_dir, existing_records=[])
        deduped_path = deduplicator.process(validated_path)
        deduped = read_jsonl(deduped_path)
        assert deduped[0]["is_duplicate"] is False

        # Step 5: Writer
        md_store = MarkdownStore(md_staging, md_knowledge, md_deprecated)
        db_store = SQLiteStore(":memory:")
        db_store.init_db()
        writer = Writer(md_store, db_store)
        results = writer.process(deduped_path)

        # 验证写入
        assert len(results) == 1
        assert results[0].md_success is True
        assert results[0].db_success is True
        assert results[0].knowledge_id.startswith("kw-")
        assert pathlib.Path(results[0].md_path).exists()

    @skip_if_no_api_key
    def test_real_pipeline_with_consolidator(self, tmp_path):
        """真实 LLM 全流水线 Step 0→6（含 consolidator 晋升）。"""
        raw_dir = tmp_path / "raw"
        staging_dir = tmp_path / "staging"
        md_staging = tmp_path / ".devContextMemo" / "staging"
        md_knowledge = tmp_path / ".devContextMemo" / "knowledge"
        md_deprecated = tmp_path / ".devContextMemo" / "deprecated"

        # Step 0-1
        adapter = _MockAdapter("Redis 缓存 key 统一使用项目前缀 app_name: 并设置 TTL 为 3600 秒，采用 lazy+active 双过期策略", "real-006")
        receiver = Receiver(adapter, raw_dir)
        receiver.receive()
        batch_files = Batcher(raw_dir, staging_dir).process(flush_all=True)

        # Step 2 (真实 LLM)
        llm = _make_real_client()
        summary_path = Extractor(llm, DOMAIN_TREE, staging_dir).process(batch_files[0])
        knowledge_path = EntityExtractor(llm, staging_dir).process(summary_path)

        # Step 3-5
        validated_path = Validator(staging_dir).process(knowledge_path)
        deduped_path = Deduplicator(staging_dir).process(validated_path)

        md_store = MarkdownStore(md_staging, md_knowledge, md_deprecated)
        db_store = SQLiteStore(":memory:")
        db_store.init_db()
        writer = Writer(md_store, db_store)
        results = writer.process(deduped_path)
        assert len(results) == 1

        # Step 6: Consolidator
        consolidator = Consolidator(db_store, md_store)
        report = consolidator.process()
        assert report.total_scanned >= 1
        # 检查状态（consolidator 可能因 confidence 阈值未晋升）
        conn = db_store.get_connection()
        status = conn.execute(
            "SELECT status FROM knowledge_index WHERE id=?",
            [results[0].knowledge_id],
        ).fetchone()[0]
        assert status in ("active", "cold", "draft", "pending_review", "staged"), f"Unexpected status: {status}"
