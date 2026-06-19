"""Module tests for Step 0 — 统一接收（适配器路由 + 三层剥壳 + 原始存储）。"""

import json
from pathlib import Path

import pytest

from devcontext.core.adapters.base import BaseAdapter
from devcontext.core.pipeline.receiver import Receiver


# =============================================================================
# 测试用假适配器
# =============================================================================

class _FakeAdapter(BaseAdapter):
    """测试用假适配器，返回预设记录。"""

    def __init__(self, records, name="fake"):
        self._records = records
        self._name = name

    @property
    def source_name(self):
        return self._name

    def collect(self, source_path=None):
        return list(self._records)

    def normalize(self, raw_record):
        return raw_record


# =============================================================================
# 基础流程
# =============================================================================

class TestReceiverBasic:
    """基础接收流程。"""

    def test_single_session_written(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "hello", "timestamp": "2026-06-18T10:00:00Z", "source": "fake"},
            {"session_id": "s1", "seq": 2, "role": "assistant",
             "content": "hi", "timestamp": "2026-06-18T10:00:05Z", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        paths = receiver.receive()
        assert len(paths) == 1
        assert paths[0].name == "session_s1.jsonl"
        assert paths[0].exists()

    def test_multiple_sessions_separate_files(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "a", "timestamp": "t1", "source": "fake"},
            {"session_id": "s2", "seq": 1, "role": "user",
             "content": "b", "timestamp": "t2", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        paths = receiver.receive()
        assert len(paths) == 2
        names = {p.name for p in paths}
        assert "session_s1.jsonl" in names
        assert "session_s2.jsonl" in names

    def test_empty_input_returns_empty(self, tmp_path):
        receiver = Receiver(_FakeAdapter([]), tmp_path / "raw")
        assert receiver.receive() == []

    def test_output_is_valid_jsonl(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "test", "timestamp": "2026-06-18T10:00:00Z", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        paths = receiver.receive()
        lines = paths[0].read_text(encoding="utf-8").strip().split("\n")
        parsed = [json.loads(l) for l in lines]
        assert len(parsed) == 1
        assert parsed[0]["session_id"] == "s1"


# =============================================================================
# 三层剥壳
# =============================================================================

class TestNoiseStripping:
    """噪声块剥离。"""

    def test_system_reminder_removed(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "正常内容<system-reminder>你是AI助手</system-reminder>后续内容",
             "timestamp": "t", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        receiver.receive()
        lines = (tmp_path / "raw" / "session_s1.jsonl").read_text(encoding="utf-8").strip().split("\n")
        content = json.loads(lines[0])["content"]
        assert "<system-reminder>" not in content
        assert "正常内容" in content
        assert "后续内容" in content

    def test_relevant_memories_removed(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "<relevant-memories>旧记忆</relevant-memories>实际问题",
             "timestamp": "t", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        receiver.receive()
        lines = (tmp_path / "raw" / "session_s1.jsonl").read_text(encoding="utf-8").strip().split("\n")
        content = json.loads(lines[0])["content"]
        assert "<relevant-memories>" not in content
        assert "实际问题" in content

    def test_openviking_context_removed(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "<openviking-context>注入上下文</openviking-context>真实问题",
             "timestamp": "t", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        receiver.receive()
        lines = (tmp_path / "raw" / "session_s1.jsonl").read_text(encoding="utf-8").strip().split("\n")
        content = json.loads(lines[0])["content"]
        assert "<openviking-context>" not in content
        assert "真实问题" in content

    def test_subagent_context_removed(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "[Subagent Context]子代理数据[/Subagent Context]\n\n真正内容",
             "timestamp": "t", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        receiver.receive()
        lines = (tmp_path / "raw" / "session_s1.jsonl").read_text(encoding="utf-8").strip().split("\n")
        content = json.loads(lines[0])["content"]
        assert "[Subagent Context]" not in content
        assert "真正内容" in content

    def test_multiple_noise_blocks_removed(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "<system-reminder>a</system-reminder>x<relevant-memories>b</relevant-memories>y",
             "timestamp": "t", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        receiver.receive()
        lines = (tmp_path / "raw" / "session_s1.jsonl").read_text(encoding="utf-8").strip().split("\n")
        content = json.loads(lines[0])["content"]
        assert "x" in content and "y" in content
        assert "system-reminder" not in content
        assert "relevant-memories" not in content


# =============================================================================
# 校验
# =============================================================================

class TestReceiverValidation:
    """记录校验。"""

    def test_missing_required_field_rejected(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "user", "content": "x"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        with pytest.raises(ValueError, match="required"):
            receiver.receive()

    def test_invalid_role_rejected(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 1, "role": "bot",
             "content": "x", "timestamp": "t", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        with pytest.raises(ValueError, match="role"):
            receiver.receive()

    def test_invalid_seq_rejected(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 0, "role": "user",
             "content": "x", "timestamp": "t", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        with pytest.raises(ValueError, match="seq"):
            receiver.receive()

    def test_messages_ordered_by_seq(self, tmp_path):
        records = [
            {"session_id": "s1", "seq": 3, "role": "user",
             "content": "third", "timestamp": "t3", "source": "fake"},
            {"session_id": "s1", "seq": 1, "role": "user",
             "content": "first", "timestamp": "t1", "source": "fake"},
            {"session_id": "s1", "seq": 2, "role": "user",
             "content": "second", "timestamp": "t2", "source": "fake"},
        ]
        receiver = Receiver(_FakeAdapter(records), tmp_path / "raw")
        receiver.receive()
        lines = (tmp_path / "raw" / "session_s1.jsonl").read_text(encoding="utf-8").strip().split("\n")
        contents = [json.loads(l)["content"] for l in lines]
        assert contents == ["first", "second", "third"]
