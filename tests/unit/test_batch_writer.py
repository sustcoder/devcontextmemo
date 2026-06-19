"""Tests for BatchWriter callback-mode batch writing."""

import json
import time
from pathlib import Path

import pytest
import yaml

from devcontext.core.collectors.base import CleanMessage
from devcontext.core.pipeline.batcher import BatchWriter


def make_messages(session_id, count, base_content="msg"):
    """Create CleanMessage list."""
    return [
        CleanMessage(
            session_id=session_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"{base_content} {i}",
            timestamp=time.time() + i,
            source="opencode",
        )
        for i in range(count)
    ]


class TestBatchWriter:
    """BatchWriter tests."""

    def test_writes_batch_when_token_threshold_reached(self, tmp_path):
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        writer = BatchWriter(staging_dir, token_threshold=100)
        messages = make_messages("s1", 5, "x" * 100)
        batch_path = writer.on_messages(messages, "s1")
        assert batch_path is not None
        assert batch_path.exists()
        assert (batch_path / "messages.jsonl").exists()
        assert (batch_path / "_meta.yaml").exists()

    def test_skips_below_threshold(self, tmp_path):
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        writer = BatchWriter(staging_dir, token_threshold=6000)
        messages = make_messages("s1", 2, "hello")
        batch_path = writer.on_messages(messages, "s1")
        assert batch_path is None

    def test_meta_yaml_format(self, tmp_path):
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        writer = BatchWriter(staging_dir, token_threshold=100)
        messages = make_messages("s2", 5, "x" * 100)
        batch_path = writer.on_messages(messages, "s2")
        meta = yaml.safe_load((batch_path / "_meta.yaml").read_text())
        assert meta["session_id"] == "s2"
        assert meta["source"] == "opencode"
        assert meta["message_count"] == 5
        assert meta["status"] == "ready"
        assert "batch_created" in meta
        assert "token_count" in meta

    def test_messages_jsonl_content(self, tmp_path):
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        writer = BatchWriter(staging_dir, token_threshold=100)
        messages = make_messages("s3", 2, "hello world " * 20)
        batch_path = writer.on_messages(messages, "s3")
        with open(batch_path / "messages.jsonl") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == 2
        assert lines[0]["session_id"] == "s3"
        assert lines[0]["content"].startswith("hello world hello world")
        assert lines[0]["content"].endswith(" 0")
        assert lines[1]["content"].endswith(" 1")

    def test_callback_invoked_on_flush(self, tmp_path):
        staging_dir = tmp_path / "staging"
        staging_dir.mkdir()
        callback_called = []
        writer = BatchWriter(staging_dir, token_threshold=100)
        writer.on_batch_ready = lambda path: callback_called.append(str(path))
        messages = make_messages("s4", 5, "x" * 100)
        batch_path = writer.on_messages(messages, "s4")
        assert batch_path is not None
        assert len(callback_called) == 1
        assert str(batch_path) in callback_called[0]
