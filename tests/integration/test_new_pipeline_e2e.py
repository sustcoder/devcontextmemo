"""集成测试 — 新架构全链路端到端（PollingCollector → BatchWriter → Steps 2-6 → knowledge）。

覆盖：
- Step 0: PollingCollector + OpenCodeSQLiteAdapter 从 mock SQLite 采集
- Step 1: BatchWriter 回调模式攒批落盘
- Step 2a: Extractor（mock LLM）知识提炼
- Step 2b: EntityExtractor（mock LLM）实体提取
- Step 3: Validator 签名验证
- Step 4: Deduplicator 重复检测
- Step 5: Writer 写入 MD + DB
- 验证: knowledge 目录中 MD 文件内容正确
"""

import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from devcontext.core.adapters.opencode_sqlite import OpenCodeSQLiteAdapter
from devcontext.core.collectors.polling import PollingCollector, DEFAULT_WATERMARK_FILE
from devcontext.core.pipeline.batcher import BatchWriter
from devcontext.core.pipeline.deduplicator import Deduplicator
from devcontext.core.pipeline.entity_extractor import EntityExtractor
from devcontext.core.pipeline.extractor import Extractor
from devcontext.core.pipeline.validator import Validator
from devcontext.core.pipeline.writer import Writer
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore
from devcontext.utils.llm import MockLLMClient


DOMAIN_TREE = {
    "order": {},
    "payment": {},
    "architecture": {},
    "convention": {},
}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_opencode_db(tmp_path):
    """创建模拟 OpenCode SQLite 数据库（真实 schema）。"""
    db_path = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE session (id TEXT PRIMARY KEY, project_id TEXT, "
        "parent_id TEXT, time_created INTEGER, time_updated INTEGER, title TEXT)"
    )
    conn.execute(
        "CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, "
        "time_created INTEGER, time_updated INTEGER, data TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, "
        "session_id TEXT, time_created INTEGER, time_updated INTEGER, "
        "data TEXT NOT NULL)"
    )

    now = int(time.time() * 1000)
    session_id = "ses_test_e2e_001"
    conn.execute(
        "INSERT INTO session(id, project_id, time_created, time_updated, title) "
        "VALUES (?, 'test', ?, ?, 'Test Session')",
        (session_id, now, now),
    )

    messages = [
        ("msg_test_001", session_id, now, now + 100,
         '{"role":"user","agent":"build","model":{"providerID":"deepseek","modelID":"deepseek-v4-pro"}}'),
        ("msg_test_002", session_id, now + 1000, now + 1100,
         '{"role":"assistant","agent":"build","model":{"providerID":"deepseek","modelID":"deepseek-v4-pro"}}'),
        ("msg_test_003", session_id, now + 2000, now + 2100,
         '{"role":"user","agent":"build","model":{"providerID":"deepseek","modelID":"deepseek-v4-pro"}}'),
        ("msg_test_004", session_id, now + 3000, now + 3100,
         '{"role":"assistant","agent":"build","model":{"providerID":"deepseek","modelID":"deepseek-v4-pro"}}'),
    ]
    conn.executemany(
        "INSERT INTO message VALUES (?, ?, ?, ?, ?)", messages
    )

    parts = [
        ("prt_test_001", "msg_test_001", session_id, now, now,
         '{"type":"text","text":"帮我给 OrderService.createOrder 加幂等校验"}'),
        ("prt_test_002", "msg_test_002", session_id, now + 1000, now + 1000,
         '{"type":"text","text":"已添加 @Idempotent 注解，key 使用 orderId + requestId。注意幂等记录表用 Redis。\\n```java\\n@Idempotent(key = \\"#order.orderId + #requestId\\")\\npublic Order createOrder(Order order) {\\n    return orderRepository.save(order);\\n}\\n```"}'),
        ("prt_test_003", "msg_test_003", session_id, now + 2000, now + 2000,
         '{"type":"text","text":"那如果 Redis 挂了怎么办，有降级方案吗"}'),
        ("prt_test_004", "msg_test_004", session_id, now + 3000, now + 3000,
         '{"type":"text","text":"可以配置 fallback 到 MySQL，在 application.yml 中设置：\\n```yaml\\nidempotent:\\n  storage: redis\\n  fallback: mysql\\n  ttl: 3600\\n```"}'),
    ]
    conn.executemany(
        "INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)", parts
    )

    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def workspace_dirs(tmp_path):
    """创建知识库目录结构。"""
    dirs = {
        "staging": tmp_path / "staging",
        "knowledge": tmp_path / "knowledge",
        "deprecated": tmp_path / "deprecated",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def _make_extractor_response():
    """Step 2a mock LLM 响应 — 提炼出一条知识。"""
    return json.dumps({
        "extracted_items": [
            {
                "content": "OrderService.createOrder 需要幂等校验，使用 @Idempotent 注解，key=orderId+requestId，Redis 做主存储，MySQL 做降级 fallback，TTL 3600 秒",
                "granularity": "L3",
                "stability": "S4",
                "depth": "KH",
                "domain": "order",
                "confidence": 0.97,
                "occurred_at": "2026-06-19T10:00:00Z",
                "source_messages": [1, 2, 3, 4],
            },
        ]
    })


def _make_entity_response():
    """Step 2b mock LLM 响应 — 提取实体和关系。"""
    return json.dumps({
        "entities": [
            {"name": "OrderService", "type": "class", "file": "src/OrderService.java"},
            {"name": "@Idempotent", "type": "pattern", "file": "src/OrderService.java"},
            {"name": "createOrder", "type": "method", "file": "src/OrderService.java"},
        ],
        "relations": [
            {"source": "OrderService", "target": "@Idempotent", "type": "uses"},
            {"source": "createOrder", "target": "OrderService", "type": "belongs_to"},
        ],
    })


# =============================================================================
# Tests
# =============================================================================


class TestFullPipelineIntegration:
    """全链路集成测试：采集 → 提炼 → 写入 knowledge。"""

    def test_full_pipeline_produces_knowledge_md(
        self, mock_opencode_db, workspace_dirs, tmp_path
    ):
        """端到端：SQLite → PollingCollector → BatchWriter → Steps 2-6 → knowledge MD。"""
        staging = workspace_dirs["staging"]
        knowledge = workspace_dirs["knowledge"]
        deprecated = workspace_dirs["deprecated"]

        # 使用测试专用水位线文件，避免跨测试污染
        watermark_file = tmp_path / "test_watermarks.json"

        # === Step 0: 采集 ===
        adapter = OpenCodeSQLiteAdapter(mock_opencode_db)
        collector = _make_collector(adapter, watermark_file)
        messages = collector._poll_once()
        assert len(messages) == 4, f"Expected 4 messages, got {len(messages)}"

        # === Step 1: 攒批 ===
        batch_writer = BatchWriter(str(staging), token_threshold=100)
        # 强制落盘（ignore threshold for test）
        flushed = collector._flush_buffer()
        by_session: dict[str, list] = {}
        for msg in flushed:
            by_session.setdefault(msg.session_id, []).append(msg)
        batch_dirs = []
        for session_id, batch in by_session.items():
            bp = batch_writer.on_messages(batch, session_id, force=True)
            if bp:
                batch_dirs.append(bp)
        assert len(batch_dirs) == 1, "Should have 1 batch directory"

        batch_dir = batch_dirs[0]
        assert (batch_dir / "messages.jsonl").exists()
        assert (batch_dir / "_meta.yaml").exists()

        # 验证 _meta.yaml
        meta = yaml.safe_load((batch_dir / "_meta.yaml").read_text())
        assert meta["status"] == "ready"
        assert meta["message_count"] == 4
        assert meta["source"] == "opencode"

        # === Step 2a: 提炼 ===
        llm = MockLLMClient(_make_extractor_response())
        extractor = Extractor(llm, DOMAIN_TREE, str(staging))
        summary_path = extractor.process(batch_dir / "messages.jsonl")
        summaries = _read_jsonl(summary_path)
        assert len(summaries) == 1
        assert summaries[0]["knowledge_text"].startswith("OrderService")
        assert summaries[0]["confidence"] == 0.97
        assert summaries[0]["granularity"] == "L3"

        # === Step 2b: 实体提取 ===
        entity_llm = MockLLMClient(_make_entity_response())
        entity_extractor = EntityExtractor(entity_llm, str(staging))
        knowledge_path = entity_extractor.process(summary_path)
        knowledge_items = _read_jsonl(knowledge_path)
        assert len(knowledge_items) == 1
        assert len(knowledge_items[0]["entities"]) == 3
        assert knowledge_items[0]["entities"][0]["name"] == "OrderService"

        # === Step 3: 验证 ===
        validator = Validator(str(staging))
        validated_path = validator.process(knowledge_path)
        validated = _read_jsonl(validated_path)
        assert len(validated[0]["content_hash"]) == 64  # SHA-256
        assert validated[0]["code_verified"] == 1  # 有 file 实体

        # === Step 4: 去重 ===
        deduplicator = Deduplicator(str(staging), existing_records=[])
        deduped_path = deduplicator.process(validated_path)
        deduped = _read_jsonl(deduped_path)
        assert deduped[0]["is_duplicate"] is False

        # === Step 5: 写入 ===
        md_store = MarkdownStore(
            str(staging), str(knowledge), str(deprecated)
        )
        db_store = SQLiteStore(":memory:")
        db_store.init_db()
        writer = Writer(md_store, db_store)
        results = writer.process(deduped_path)

        # === 验证 knowledge 目录输出 ===
        assert len(results) == 1
        result = results[0]
        assert result.md_success is True
        assert result.md_path is not None

        # 检查 MD 文件存在且内容正确
        md_file = Path(result.md_path)
        assert md_file.exists()
        md_content = md_file.read_text(encoding="utf-8")
        assert "OrderService.createOrder" in md_content
        assert "@Idempotent" in md_content or "Idempotent" in md_content
        assert "granularity: L3" in md_content or "L3" in md_content
        assert "domain: order" in md_content or "order" in md_content

        # 检查目录结构
        knowledge_files = list(Path(knowledge).rglob("*.md"))
        assert len(knowledge_files) >= 1

    def test_polling_collector_with_real_adapter(
        self, mock_opencode_db, workspace_dirs, tmp_path
    ):
        """验证 PollingCollector + OpenCodeSQLiteAdapter 数据流完整性。"""
        adapter = OpenCodeSQLiteAdapter(mock_opencode_db)
        watermark_file = tmp_path / "test_watermarks_1.json"
        collector = _make_collector(adapter, watermark_file)
        messages = collector._poll_once()

        assert len(messages) == 4
        for msg in messages:
            assert msg.session_id == "ses_test_e2e_001"
            assert msg.role in ("user", "assistant")
            assert msg.source == "opencode"
            assert isinstance(msg.timestamp, float)
            assert len(msg.content) > 0

    def test_incremental_respects_watermark(
        self, mock_opencode_db, workspace_dirs, tmp_path
    ):
        """验证增量采集：首次采集全部，二次采集为 0。"""
        adapter = OpenCodeSQLiteAdapter(mock_opencode_db)
        watermark_file = tmp_path / "test_watermarks_2.json"
        collector = _make_collector(adapter, watermark_file)

        # 首次采集
        first = collector._poll_once()
        assert len(first) == 4

        # 二次采集（无新数据）
        collector.buffer.clear()
        second = collector._poll_once()
        assert len(second) == 0

    def test_batch_writer_and_pipeline_integration(
        self, mock_opencode_db, workspace_dirs, tmp_path
    ):
        """验证 BatchWriter 和 PipelineService 集成：采集 → 落盘。"""
        from devcontext.services.pipeline import PipelineService
        from unittest.mock import MagicMock

        staging = workspace_dirs["staging"]

        adapter = OpenCodeSQLiteAdapter(mock_opencode_db)
        watermark_file = tmp_path / "test_watermarks_3.json"
        collector = _make_collector(adapter, watermark_file)

        # Mock Steps 2-6
        mock_extractor = MagicMock()
        mock_extractor.process.return_value = Path("/fake/summary.jsonl")

        batch_writer = BatchWriter(str(staging), token_threshold=100)

        pipeline = PipelineService(
            collectors=[collector],
            batch_writer=batch_writer,
            extractor=mock_extractor,
        )

        # 手动采集 + 落盘
        result = pipeline.capture(dry_run=False)
        assert result["collectors"]["opencode"]["messages_found"] == 4
        assert "batch_path" in result["collectors"]["opencode"]

        # 验证 staging 落盘
        batch_dir = Path(result["collectors"]["opencode"]["batch_path"])
        assert (batch_dir / "messages.jsonl").exists()
        assert (batch_dir / "_meta.yaml").exists()


# =============================================================================
# Helpers
# =============================================================================


def _make_collector(adapter, watermark_file: Path) -> PollingCollector:
    """创建使用测试专用水位线文件的 PollingCollector。"""
    with patch(
        "devcontext.core.collectors.polling.DEFAULT_WATERMARK_FILE",
        watermark_file,
    ):
        return PollingCollector(adapter)


def _read_jsonl(path: Path) -> list[dict]:
    """读取 JSONL 文件。"""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
