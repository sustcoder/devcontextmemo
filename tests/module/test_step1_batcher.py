"""Module tests for Step 1 — 攒批（token 阈值 + _flushed 防重 + JSONL 输出）。"""

import json
from pathlib import Path

import pytest
import yaml

from devcontext.core.pipeline.batcher import Batcher


def _write_session(raw_dir: Path, session_id: str, records: list[dict]) -> Path:
    """写入一个 session JSONL 文件。"""
    p = raw_dir / f"session_{session_id}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


# =============================================================================
# 基础攒批
# =============================================================================

class TestBatcherBasic:
    """基础攒批流程。"""

    def test_threshold_triggers_batch(self, tmp_path):
        """token 超阈值时触发攒批。"""
        records = [
            {"session_id": "big", "seq": i, "role": "user",
             "content": "x" * 4000, "timestamp": f"t{i}", "source": "opencode"}
            for i in range(1, 5)
        ]
        _write_session(tmp_path / "raw", "big", records)
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging", token_threshold=6000)
        paths = batcher.process(flush_all=False)
        assert len(paths) == 1
        assert paths[0].exists()

    def test_below_threshold_skipped(self, tmp_path):
        """token 不足阈值时跳过（非全量模式）。"""
        records = [
            {"session_id": "small", "seq": 1, "role": "user",
             "content": "hello", "timestamp": "t", "source": "opencode"},
        ]
        _write_session(tmp_path / "raw", "small", records)
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging", token_threshold=6000)
        paths = batcher.process(flush_all=False)
        assert len(paths) == 0

    def test_flush_all_batches_everything(self, tmp_path):
        """全量模式打包所有未 flush session。"""
        records = [
            {"session_id": "small", "seq": 1, "role": "user",
             "content": "hi", "timestamp": "t", "source": "opencode"},
        ]
        _write_session(tmp_path / "raw", "small", records)
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging", token_threshold=6000)
        paths = batcher.process(flush_all=True)
        assert len(paths) == 1

    def test_empty_raw_dir_returns_empty(self, tmp_path):
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging")
        assert batcher.process(flush_all=True) == []

    def test_no_session_files_returns_empty(self, tmp_path):
        (tmp_path / "raw").mkdir(parents=True)
        (tmp_path / "raw" / "not_a_session.txt").write_text("x")
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging")
        assert batcher.process(flush_all=True) == []


# =============================================================================
# _flushed 防重
# =============================================================================

class TestFlushedDedup:
    """_flushed 防重机制。"""

    def test_already_flushed_session_skipped(self, tmp_path):
        """已 flush 的 session 不会被重复攒批。"""
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "x" * 8000, "timestamp": "t", "source": "opencode"},
            {"session_id": "s1", "seq": 2, "role": "user",
             "content": "y" * 8000, "timestamp": "t2", "source": "opencode"},
        ]
        _write_session(tmp_path / "raw", "s1", records)
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging", token_threshold=6000)

        # 第一次：触发
        paths1 = batcher.process(flush_all=False)
        assert len(paths1) == 1

        # 第二次：已 flush，不触发
        paths2 = batcher.process(flush_all=False)
        assert len(paths2) == 0

    def test_multiple_sessions_independent_flush(self, tmp_path):
        """多个 session 独立 flush。"""
        _write_session(tmp_path / "raw", "s1", [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "x" * 8000, "timestamp": "t", "source": "opencode"},
            {"session_id": "s1", "seq": 2, "role": "user",
             "content": "y" * 8000, "timestamp": "t2", "source": "opencode"},
        ])
        _write_session(tmp_path / "raw", "s2", [
            {"session_id": "s2", "seq": 1, "role": "user",
             "content": "small", "timestamp": "t", "source": "opencode"},
        ])

        batcher = Batcher(tmp_path / "raw", tmp_path / "staging", token_threshold=6000)

        # 非全量：只有 s1 触发
        paths1 = batcher.process(flush_all=False)
        assert len(paths1) == 1
        assert "s1" in paths1[0].name

        # 全量：s2 触发
        paths2 = batcher.process(flush_all=True)
        assert len(paths2) == 1
        assert "s2" in paths2[0].name

        # 再全量：都已 flush
        paths3 = batcher.process(flush_all=True)
        assert len(paths3) == 0


# =============================================================================
# 输出格式
# =============================================================================

class TestBatchOutputFormat:
    """batch JSONL + _meta.yaml 格式。"""

    def test_batch_jsonl_valid(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": i, "role": "user",
             "content": "x" * 4000, "timestamp": f"t{i}", "source": "opencode"}
            for i in range(1, 5)
        ]
        _write_session(tmp_path / "raw", "s1", records)
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging", token_threshold=6000)
        paths = batcher.process(flush_all=False)

        lines = paths[0].read_text(encoding="utf-8").strip().split("\n")
        parsed = [json.loads(l) for l in lines]
        assert len(parsed) == 4
        for rec in parsed:
            assert "session_id" in rec
            assert "seq" in rec
            assert "role" in rec
            assert "content" in rec
            assert "timestamp" in rec
            assert "source" in rec

    def test_meta_yaml_has_required_fields(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "x" * 13000, "timestamp": "t", "source": "opencode"},
        ]
        _write_session(tmp_path / "raw", "s1", records)
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging", token_threshold=6000)
        batcher.process(flush_all=False)

        meta_files = list((tmp_path / "staging").glob("*_meta.yaml"))
        assert len(meta_files) == 1
        meta = yaml.safe_load(meta_files[0].read_text(encoding="utf-8"))
        assert "batch_id" in meta
        assert "session_id" in meta
        assert meta["session_id"] == "s1"
        assert "message_count" in meta
        assert meta["message_count"] == 1
        assert "token_count" in meta
        assert meta["token_count"] >= 6000
        assert "captured_at" in meta
        assert meta["status"] == "staged"

    def test_messages_ordered_by_seq_in_batch(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 3, "role": "user",
             "content": "x" * 5000, "timestamp": "t3", "source": "opencode"},
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "x" * 5000, "timestamp": "t1", "source": "opencode"},
            {"session_id": "s1", "seq": 2, "role": "user",
             "content": "x" * 5000, "timestamp": "t2", "source": "opencode"},
        ]
        _write_session(tmp_path / "raw", "s1", records)
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging", token_threshold=6000)
        paths = batcher.process(flush_all=False)

        lines = paths[0].read_text(encoding="utf-8").strip().split("\n")
        seqs = [json.loads(l)["seq"] for l in lines]
        assert seqs == [1, 2, 3]

    def test_batch_filename_contains_session_id(self, tmp_path):
        records = [
            {"session_id": "mysession", "seq": 1, "role": "user",
             "content": "x" * 13000, "timestamp": "t", "source": "opencode"},
        ]
        _write_session(tmp_path / "raw", "mysession", records)
        batcher = Batcher(tmp_path / "raw", tmp_path / "staging", token_threshold=6000)
        paths = batcher.process(flush_all=False)
        assert "mysession" in paths[0].name
