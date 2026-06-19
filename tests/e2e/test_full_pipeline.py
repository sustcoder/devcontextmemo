"""End-to-End tests — Step 0→6 全流水线 + 性能基准 + 崩溃恢复。

Phase 4c: Step 0→5 全流水线（mock LLM）
Phase 5: Step 6 consolidator 集成
Phase 10: 批量写入 + 性能基准 + 崩溃恢复
"""

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pytest

from devcontext.core.adapters.base import BaseAdapter
from devcontext.core.pipeline.batcher import Batcher
from devcontext.core.pipeline.deduplicator import Deduplicator
from devcontext.core.pipeline.entity_extractor import EntityExtractor
from devcontext.core.pipeline.extractor import Extractor
from devcontext.core.pipeline.receiver import Receiver
from devcontext.core.pipeline.validator import Validator
from devcontext.core.pipeline.writer import Writer
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore
from devcontext.utils.llm import MockLLMClient
from tests.conftest import write_jsonl, read_jsonl


DOMAIN_TREE = {
    "order": {}, "payment": {}, "architecture": {}, "convention": {},
}


class _MockAdapter(BaseAdapter):
    """测试用 mock 适配器，返回预设对话。"""

    def __init__(self, records):
        self._records = records

    @property
    def source_name(self):
        return "opencode"

    def collect(self, source_path=None):
        return list(self._records)

    def normalize(self, raw_record):
        return raw_record


def _make_conversation():
    """构造一段 mock 对话。"""
    return [
        {"session_id": "e2e-001", "seq": 1, "role": "user",
         "content": "帮我给 OrderService.createOrder 加幂等校验",
         "timestamp": "2026-06-18T09:58:00Z", "source": "opencode"},
        {"session_id": "e2e-001", "seq": 2, "role": "assistant",
         "content": "已添加 @Idempotent 注解，key=orderId。注意不要用 transactionId。",
         "timestamp": "2026-06-18T09:58:30Z", "source": "opencode"},
    ]


def _make_extractor_response():
    """Step 2a mock LLM 响应。"""
    return json.dumps({
        "extracted_items": [
            {
                "content": "OrderService.createOrder 需要幂等校验，使用 @Idempotent 注解，key=orderId",
                "granularity": "L3", "stability": "S4", "depth": "KH", "domain": "order",
                "confidence": 0.97,  # 绿色通道
                "occurred_at": "2026-06-18T09:58:00Z",
                "source_messages": [1, 2],
            },
        ]
    })


def _make_entity_response():
    """Step 2b mock LLM 响应。"""
    return json.dumps({
        "entities": [
            {"name": "OrderService", "type": "class", "file": "src/OrderService.java"},
            {"name": "createOrder", "type": "method"},
            {"name": "Idempotent", "type": "pattern"},
        ],
        "relations": [
            {"source": "OrderService", "target": "Idempotent", "type": "uses"},
        ],
    })


@pytest.mark.e2e
class TestFullPipelineStep0to5:
    """完整流水线 Step 0→5。"""

    def test_full_pipeline_writes_md_and_db(self, tmp_path):
        """端到端：对话 → receiver → batcher → extractor → entity → validator → dedup → writer。"""
        # 目录
        raw_dir = tmp_path / "raw"
        staging_dir = tmp_path / "staging"
        md_staging = tmp_path / ".devContextMemo" / "staging"
        md_knowledge = tmp_path / ".devContextMemo" / "knowledge"
        md_deprecated = tmp_path / ".devContextMemo" / "deprecated"

        # === Step 0: Receiver ===
        adapter = _MockAdapter(_make_conversation())
        receiver = Receiver(adapter, raw_dir)
        session_files = receiver.receive()
        assert len(session_files) == 1
        assert session_files[0].name == "session_e2e-001.jsonl"

        # === Step 1: Batcher（全量模式）===
        batcher = Batcher(raw_dir, staging_dir, token_threshold=6000)
        batch_files = batcher.process(flush_all=True)
        assert len(batch_files) == 1

        # === Step 2a: Extractor ===
        extractor_llm = MockLLMClient(_make_extractor_response())
        extractor = Extractor(extractor_llm, DOMAIN_TREE, staging_dir)
        summary_path = extractor.process(batch_files[0])
        summaries = read_jsonl(summary_path)
        assert len(summaries) == 1
        assert summaries[0]["knowledge_text"].startswith("OrderService")
        assert summaries[0]["confidence"] == 0.97

        # === Step 2b: EntityExtractor ===
        entity_llm = MockLLMClient(_make_entity_response())
        entity_extractor = EntityExtractor(entity_llm, staging_dir)
        knowledge_path = entity_extractor.process(summary_path)
        knowledge = read_jsonl(knowledge_path)
        assert len(knowledge) == 1
        assert len(knowledge[0]["entities"]) == 3
        assert knowledge[0]["entities"][0]["file"] == "src/OrderService.java"

        # === Step 3: Validator ===
        validator = Validator(staging_dir)
        validated_path = validator.process(knowledge_path)
        validated = read_jsonl(validated_path)
        assert len(validated[0]["content_hash"]) == 64
        assert validated[0]["code_verified"] == 1  # 有 file 实体

        # === Step 4: Deduplicator（空知识库）===
        deduplicator = Deduplicator(staging_dir, existing_records=[])
        deduped_path = deduplicator.process(validated_path)
        deduped = read_jsonl(deduped_path)
        assert deduped[0]["is_duplicate"] is False

        # === Step 5: Writer ===
        md_store = MarkdownStore(md_staging, md_knowledge, md_deprecated)
        db_store = SQLiteStore(":memory:")
        db_store.init_db()
        writer = Writer(md_store, db_store)
        results = writer.process(deduped_path)

        # 验证写入结果
        assert len(results) == 1
        r = results[0]
        assert r.md_success is True
        assert r.db_success is True
        assert r.target == "knowledge"  # confidence=0.97 绿色通道
        assert r.knowledge_id.startswith("kw-")

        # MD 文件存在且在 knowledge/order/ 下
        md_path = Path(r.md_path)
        assert md_path.exists()
        assert "order" in str(md_path)
        assert "knowledge" in str(md_path)

        # MD frontmatter 有 15 字段
        md_content = md_path.read_text(encoding="utf-8")
        for field in ("id:", "title:", "domain:", "granularity:", "stability:",
                      "depth:", "status:", "confidence:", "code_verified:",
                      "concept_tags:", "source_session:", "created_at:",
                      "updated_at:", "uri:"):
            assert field in md_content

        # DB 有 1 条记录
        conn = db_store.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM knowledge_index").fetchone()[0]
        assert count == 1

        db_rec = conn.execute(
            "SELECT id, title, domain, confidence, code_verified, uri FROM knowledge_index"
        ).fetchone()
        assert db_rec[0] == r.knowledge_id
        assert "OrderService" in db_rec[1]
        assert db_rec[2] == "order"
        assert db_rec[3] == 0.97
        assert db_rec[4] == 1
        assert db_rec[5] == str(md_path)

    def test_full_pipeline_low_confidence_to_staging(self, tmp_path):
        """confidence < 0.95 → 写入 staging/ 而非 knowledge/。"""
        raw_dir = tmp_path / "raw"
        staging_dir = tmp_path / "staging"
        md_staging = tmp_path / ".devContextMemo" / "staging"
        md_knowledge = tmp_path / ".devContextMemo" / "knowledge"
        md_deprecated = tmp_path / ".devContextMemo" / "deprecated"

        # Step 0-1
        adapter = _MockAdapter(_make_conversation())
        Receiver(adapter, raw_dir).receive()
        batcher = Batcher(raw_dir, staging_dir)
        batch_files = batcher.process(flush_all=True)

        # Step 2a（低 confidence）
        low_resp = json.dumps({
            "extracted_items": [{
                "content": "某个普通规范",
                "granularity": "L2", "stability": "S3", "depth": "KH", "domain": "convention",
                "confidence": 0.70, "occurred_at": None, "source_messages": [1],
            }]
        })
        extractor = Extractor(MockLLMClient(low_resp), DOMAIN_TREE, staging_dir)
        summary_path = extractor.process(batch_files[0])

        # Step 2b
        entity_extractor = EntityExtractor(
            MockLLMClient(json.dumps({"entities": [], "relations": []})), staging_dir
        )
        knowledge_path = entity_extractor.process(summary_path)

        # Step 3-4
        validated_path = Validator(staging_dir).process(knowledge_path)
        deduped_path = Deduplicator(staging_dir).process(validated_path)

        # Step 5
        md_store = MarkdownStore(md_staging, md_knowledge, md_deprecated)
        db_store = SQLiteStore(":memory:")
        db_store.init_db()
        writer = Writer(md_store, db_store)
        results = writer.process(deduped_path)

        assert len(results) == 1
        assert results[0].target == "staging"  # 低 confidence → staging
        assert "staging" in results[0].md_path


# =============================================================================
# Phase 10: 完整 Step 0→6 + 批量 + 性能 + 崩溃恢复
# =============================================================================

def _run_pipeline_step0_to_5(tmp_path, conversations, extractor_responses, entity_responses):
    """运行 Step 0→5 流水线，返回 (db_store, md_store, writer_results)。"""
    raw_dir = tmp_path / "raw"
    staging_dir = tmp_path / "staging"
    md_staging = tmp_path / ".devContextMemo" / "staging"
    md_knowledge = tmp_path / ".devContextMemo" / "knowledge"
    md_deprecated = tmp_path / ".devContextMemo" / "deprecated"

    all_results = []
    db_store = SQLiteStore(":memory:")
    db_store.init_db()
    md_store = MarkdownStore(md_staging, md_knowledge, md_deprecated)
    writer = Writer(md_store, db_store)

    for conv, ext_resp, ent_resp in zip(conversations, extractor_responses, entity_responses):
        # Step 0
        adapter = _MockAdapter(conv)
        Receiver(adapter, raw_dir).receive()
        # Step 1
        batcher = Batcher(raw_dir, staging_dir)
        batch_files = batcher.process(flush_all=True)
        # Step 2a
        extractor = Extractor(MockLLMClient(ext_resp), DOMAIN_TREE, staging_dir)
        summary_path = extractor.process(batch_files[0])
        # Step 2b
        entity_extractor = EntityExtractor(MockLLMClient(ent_resp), staging_dir)
        knowledge_path = entity_extractor.process(summary_path)
        # Step 3
        validated_path = Validator(staging_dir).process(knowledge_path)
        # Step 4
        deduped_path = Deduplicator(staging_dir).process(validated_path)
        # Step 5
        results = writer.process(deduped_path)
        all_results.extend(results)

    return db_store, md_store, all_results


@pytest.mark.e2e
class TestFullPipelineStep0to6:
    """完整 Step 0→6 流水线（含 consolidator）。"""

    def test_step6_consolidator_promotes_staged(self, tmp_path):
        """Step 0→5 写入 staged 知识 → Step 6 consolidator 晋升。"""
        conv = [_make_conversation()]
        ext_resp = [json.dumps({"extracted_items": [{
            "content": "中等置信知识", "granularity": "L3", "stability": "S4",
            "depth": "KH", "domain": "order", "confidence": 0.70,
            "occurred_at": None, "source_messages": [1],
        }]})]
        ent_resp = [json.dumps({"entities": [], "relations": []})]

        db_store, md_store, results = _run_pipeline_step0_to_5(
            tmp_path, conv, ext_resp, ent_resp
        )
        assert len(results) == 1
        assert results[0].target == "staging"  # confidence=0.70 < 0.95

        # Step 6: consolidator
        from devcontext.core.pipeline.consolidator import Consolidator
        consolidator = Consolidator(db_store, md_store)
        report = consolidator.process()
        assert report.total_scanned >= 1
        assert report.promotions >= 1  # staged → pending_review/draft

        # DB 状态已更新
        conn = db_store.get_connection()
        status = conn.execute("SELECT status FROM knowledge_index").fetchone()[0]
        assert status != "staged"  # 已被评估

    def test_step6_consolidator_prunes_old_draft(self, tmp_path):
        """Step 6 对老 DRAFT 知识触发修剪。"""
        import datetime as dt
        db_store = SQLiteStore(":memory:")
        db_store.init_db()
        conn = db_store.get_connection()

        # 插入一条 100 天前的 DRAFT
        old_date = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=100)).isoformat()
        conn.execute(
            "INSERT INTO knowledge_index (id, title, domain, sub_domain, granularity, "
            "stability, depth, status, confidence, code_verified, prune_priority, "
            "certainty, freshness, uri, used_count, calibration_status, created_at, "
            "updated_at, stale_check_count, restored_count, evidence_level, code_active, "
            "auto_adopted_unreviewed) VALUES "
            "('kw-old', '旧知识', 'order', '', 'L3', 'S4', 'KH', 'draft', 0.50, 0, "
            "0, 0.5, 0.5, '', 0, 'uncalibrated', ?, ?, 0, 0, 3, 1, 0)",
            [old_date, old_date],
        )
        conn.commit()

        from devcontext.core.pipeline.consolidator import Consolidator
        consolidator = Consolidator(db_store)
        report = consolidator.process()

        assert report.pruned >= 1
        status = conn.execute("SELECT status FROM knowledge_index WHERE id='kw-old'").fetchone()[0]
        assert status == "deprecated"


@pytest.mark.e2e
class TestBatchWrite:
    """批量写入测试。"""

    def test_write_10_knowledge_items(self, tmp_path):
        """批量写入 10 条知识（混合高/低 confidence）。"""
        conversations = []
        extractor_responses = []
        entity_responses = []

        for i in range(10):
            conversations.append([{
                "session_id": f"sess-{i}", "seq": 1, "role": "user",
                "content": f"知识条目 {i}", "timestamp": "2026-06-18T10:00:00Z",
                "source": "opencode",
            }])
            confidence = 0.97 if i % 3 == 0 else 0.70  # 1/3 绿色通道
            extractor_responses.append(json.dumps({"extracted_items": [{
                "content": f"知识内容 {i}", "granularity": "L3", "stability": "S4",
                "depth": "KH", "domain": "order", "confidence": confidence,
                "occurred_at": None, "source_messages": [1],
            }]}))
            entity_responses.append(json.dumps({"entities": [], "relations": []}))

        db_store, md_store, results = _run_pipeline_step0_to_5(
            tmp_path, conversations, extractor_responses, entity_responses
        )

        assert len(results) == 10
        green = [r for r in results if r.target == "knowledge"]
        staging = [r for r in results if r.target == "staging"]
        assert len(green) >= 3  # 1/3 绿色通道
        assert len(staging) >= 6

        # DB 有 10 条
        conn = db_store.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM knowledge_index").fetchone()[0]
        assert count == 10

    def test_batch_write_all_md_files_exist(self, tmp_path):
        """批量写入后所有 MD 文件存在。"""
        conversations = []
        extractor_responses = []
        entity_responses = []

        for i in range(5):
            conversations.append([{
                "session_id": f"sess-{i}", "seq": 1, "role": "user",
                "content": f"知识 {i}", "timestamp": "2026-06-18T10:00:00Z",
                "source": "opencode",
            }])
            extractor_responses.append(json.dumps({"extracted_items": [{
                "content": f"知识内容 {i}", "granularity": "L2", "stability": "S3",
                "depth": "KH", "domain": "order", "confidence": 0.97,
                "occurred_at": None, "source_messages": [1],
            }]}))
            entity_responses.append(json.dumps({"entities": [], "relations": []}))

        db_store, md_store, results = _run_pipeline_step0_to_5(
            tmp_path, conversations, extractor_responses, entity_responses
        )

        for r in results:
            assert Path(r.md_path).exists()


@pytest.mark.e2e
@pytest.mark.slow
class TestPerformanceBenchmark:
    """性能基准测试（100 条知识写入）。"""

    def test_100_knowledge_write_under_30_seconds(self, tmp_path):
        """100 条知识写入 < 30 秒（mock LLM，无真实 API 调用）。

        编码索引要求 < 5 分钟（含真实 LLM），mock 模式应远快于此。
        """
        import time

        conversations = []
        extractor_responses = []
        entity_responses = []

        for i in range(100):
            conversations.append([{
                "session_id": f"sess-{i}", "seq": 1, "role": "user",
                "content": f"性能测试知识条目 {i} " + "x" * 200,
                "timestamp": "2026-06-18T10:00:00Z", "source": "opencode",
            }])
            extractor_responses.append(json.dumps({"extracted_items": [{
                "content": f"知识内容 {i}", "granularity": "L3", "stability": "S4",
                "depth": "KH", "domain": "order", "confidence": 0.80,
                "occurred_at": None, "source_messages": [1],
            }]}))
            entity_responses.append(json.dumps({"entities": [], "relations": []}))

        start = time.time()
        db_store, md_store, results = _run_pipeline_step0_to_5(
            tmp_path, conversations, extractor_responses, entity_responses
        )
        elapsed = time.time() - start

        assert len(results) == 100
        assert elapsed < 30.0, f"100 条写入耗时 {elapsed:.1f}s，超过 30s 阈值"

        # DB 有 100 条
        conn = db_store.get_connection()
        count = conn.execute("SELECT COUNT(*) FROM knowledge_index").fetchone()[0]
        assert count == 100

    def test_sqlite_query_100_records_under_1_second(self, tmp_path):
        """100 条记录的 SQLite 查询 < 1 秒。"""
        import time
        from devcontext.storage.search import SearchEngine

        db_store = SQLiteStore(":memory:")
        db_store.init_db()
        conn = db_store.get_connection()

        for i in range(100):
            now = dt.datetime.now(dt.timezone.utc).isoformat() if 'dt' in dir() else "2026-06-18"
            conn.execute(
                "INSERT INTO knowledge_index (id, title, domain, sub_domain, granularity, "
                "stability, depth, status, confidence, code_verified, prune_priority, "
                "certainty, freshness, uri, used_count, calibration_status, created_at, "
                "updated_at, stale_check_count, restored_count, evidence_level, code_active, "
                "auto_adopted_unreviewed) VALUES "
                f"('kw-{i:03d}', '知识{i}', 'order', '', 'L3', 'S4', 'KH', 'active', "
                f"0.85, 1, 0, 0.5, 0.5, '', 0, 'uncalibrated', '2026-06-18', '2026-06-18', "
                "0, 0, 5, 1, 0)"
            )
        conn.commit()

        search = SearchEngine(db_store)

        start = time.time()
        for _ in range(10):
            results = search.search("知识", top_k=20)
        elapsed = time.time() - start

        assert elapsed < 1.0, f"10 次查询耗时 {elapsed:.2f}s"
        db_store.close()

    def test_fts5_search_latency(self, tmp_path):
        """FTS5 搜索延迟 < 100ms（单次）。"""
        import time
        from devcontext.storage.search import SearchEngine

        db_store = SQLiteStore(":memory:")
        db_store.init_db()
        conn = db_store.get_connection()

        for i in range(50):
            conn.execute(
                "INSERT INTO knowledge_index (id, title, domain, sub_domain, granularity, "
                "stability, depth, status, confidence, code_verified, prune_priority, "
                "certainty, freshness, uri, used_count, calibration_status, created_at, "
                "updated_at, stale_check_count, restored_count, evidence_level, code_active, "
                "auto_adopted_unreviewed) VALUES "
                f"('kw-{i:03d}', '知识{i}', 'order', '', 'L3', 'S4', 'KH', 'active', "
                f"0.85, 1, 0, 0.5, 0.5, '', 0, 'uncalibrated', '2026-06-18', '2026-06-18', "
                "0, 0, 5, 1, 0)"
            )
            if db_store.fts_available:
                rowid = conn.execute("SELECT rowid FROM knowledge_index WHERE id=?", [f"kw-{i:03d}"]).fetchone()[0]
                db_store._sync_fts(rowid, f"知识{i}", "", f"知识{i}")
        conn.commit()

        search = SearchEngine(db_store)
        start = time.time()
        results = search.search("知识", top_k=10)
        elapsed = time.time() - start

        assert elapsed < 0.1, f"FTS5 搜索耗时 {elapsed*1000:.0f}ms"
        assert len(results) > 0
        db_store.close()


@pytest.mark.e2e
class TestCrashRecovery:
    """崩溃恢复测试。"""

    def test_md_written_db_failed_md_intact(self, tmp_path):
        """MD 写成功 + DB 失败 → MD 文件完整保留。"""
        md_store = MarkdownStore(
            staging_dir=tmp_path / "staging",
            knowledge_dir=tmp_path / "knowledge",
            deprecated_dir=tmp_path / "deprecated",
        )
        # DB 不可用（传 None）
        writer = Writer(md_store, sqlite_store=None)

        record = {
            "session_id": "crash-001",
            "knowledge_text": "崩溃恢复测试知识",
            "granularity": "L3", "stability": "S4", "depth": "KH",
            "domain": "order", "confidence": 0.80,
            "entities": [], "relations": [],
            "content_hash": "a" * 64, "semantic_hash": "b" * 16,
            "code_verified": 0, "top_similar_id": None,
            "jaccard_score": 0.0, "is_duplicate": False,
            "occurred_at": None, "source_messages": [1], "status": "staged",
        }

        batch_path = tmp_path / "crash.jsonl"
        import json as _json
        with open(batch_path, "w", encoding="utf-8") as f:
            f.write(_json.dumps(record, ensure_ascii=False) + "\n")

        results = writer.process(batch_path)
        assert len(results) == 1
        assert results[0].md_success is True
        assert results[0].db_success is False  # DB 不可用
        # MD 文件存在
        assert Path(results[0].md_path).exists()

    def test_rebuild_db_from_md(self, tmp_path):
        """从 MD 文件重建 DB 索引（MD 是 SSoT）。"""
        md_store = MarkdownStore(
            staging_dir=tmp_path / "staging",
            knowledge_dir=tmp_path / "knowledge",
            deprecated_dir=tmp_path / "deprecated",
        )
        db_store = SQLiteStore(":memory:")
        db_store.init_db()

        # 写入知识
        writer = Writer(md_store, db_store)
        record = {
            "session_id": "rebuild-001",
            "knowledge_text": "重建测试知识",
            "granularity": "L3", "stability": "S4", "depth": "KH",
            "domain": "order", "confidence": 0.97,
            "entities": [{"name": "Foo", "type": "class", "file": "src/Foo.java"}],
            "relations": [],
            "content_hash": "a" * 64, "semantic_hash": "b" * 16,
            "code_verified": 1, "top_similar_id": None,
            "jaccard_score": 0.0, "is_duplicate": False,
            "occurred_at": None, "source_messages": [1], "status": "staged",
        }
        batch_path = tmp_path / "rebuild.jsonl"
        import json as _json
        with open(batch_path, "w", encoding="utf-8") as f:
            f.write(_json.dumps(record, ensure_ascii=False) + "\n")

        results = writer.process(batch_path)
        kid = results[0].knowledge_id
        md_path = results[0].md_path

        # 模拟 DB 丢失（新 DB）
        db_store2 = SQLiteStore(":memory:")
        db_store2.init_db()

        # 从 MD 重建
        rec = md_store.read(md_path)
        db_record = md_store.to_db_dict(rec, md_path)
        conn = db_store2.get_connection()
        cols = ", ".join(db_record.keys())
        placeholders = ", ".join("?" * len(db_record))
        conn.execute(
            f"INSERT INTO knowledge_index ({cols}) VALUES ({placeholders})",
            list(db_record.values()),
        )
        conn.commit()

        # 验证重建
        row = conn.execute("SELECT id, title, domain FROM knowledge_index").fetchone()
        assert row[0] == kid
        assert "重建" in row[1]
        assert row[2] == "order"

    def test_dry_run_no_side_effects(self, tmp_path):
        """dry-run 模式不修改 DB 和文件。"""
        import datetime as _dt
        db_store = SQLiteStore(":memory:")
        db_store.init_db()
        conn = db_store.get_connection()

        old_date = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=100)).isoformat()
        conn.execute(
            "INSERT INTO knowledge_index (id, title, domain, sub_domain, granularity, "
            "stability, depth, status, confidence, code_verified, prune_priority, "
            "certainty, freshness, uri, used_count, calibration_status, created_at, "
            "updated_at, stale_check_count, restored_count, evidence_level, code_active, "
            "auto_adopted_unreviewed) VALUES "
            "('kw-dry', 'dry-run 测试', 'order', '', 'L3', 'S4', 'KH', 'draft', 0.50, 0, "
            "0, 0.5, 0.5, '', 0, 'uncalibrated', ?, ?, 0, 0, 3, 1, 0)",
            [old_date, old_date],
        )
        conn.commit()

        from devcontext.core.pipeline.consolidator import Consolidator
        consolidator = Consolidator(db_store, dry_run=True)
        report = consolidator.process()

        # 报告有评估结果
        assert report.total_scanned == 1
        # 但 DB 未修改
        status = conn.execute("SELECT status FROM knowledge_index WHERE id='kw-dry'").fetchone()[0]
        assert status == "draft"  # 未变
