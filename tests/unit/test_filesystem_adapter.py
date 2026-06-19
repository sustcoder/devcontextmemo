"""Tests for FileSystemAdapter."""

import json
import time

import pytest

from devcontext.core.adapters.filesystem import FileSystemAdapter


@pytest.fixture
def scan_dir(tmp_path):
    """Create a scan directory with .jsonl and .md files."""
    d = tmp_path / "scan"
    d.mkdir()
    sub = d / "subdir"
    sub.mkdir()

    messages = [
        {"session_id": "s1", "role": "user", "content": "hello",
         "timestamp": "2026-06-19T10:00:00Z", "source": "filesystem"},
        {"session_id": "s1", "role": "assistant", "content": "hi",
         "timestamp": "2026-06-19T10:00:05Z", "source": "filesystem"},
    ]
    f1 = d / "session_s1.jsonl"
    with open(f1, "w") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")

    f2 = d / "README.md"
    f2.write_text("# README")
    yield d


class TestFileSystemAdapter:
    """FileSystemAdapter tests."""

    def test_source_name(self):
        """source_name returns 'filesystem'."""
        adapter = FileSystemAdapter([], ["*.jsonl"])
        assert adapter.source_name == "filesystem"

    def test_scans_jsonl_files(self, scan_dir):
        """incremental_query scans .jsonl files and returns messages."""
        adapter = FileSystemAdapter([str(scan_dir)], ["*.jsonl"])
        results = adapter.incremental_query({"checkpoint": 0})
        assert len(results) >= 2

    def test_fingerprint_dedup(self, scan_dir):
        """Second incremental_query returns no new messages (fingerprint dedup)."""
        adapter = FileSystemAdapter([str(scan_dir)], ["*.jsonl"])
        first = adapter.incremental_query({"checkpoint": 0})
        second = adapter.incremental_query({"checkpoint": time.time() + 60})
        assert len(first) >= 2
        assert len(second) == 0

    def test_mtime_filtering(self, scan_dir):
        """incremental_query with future checkpoint returns no results."""
        adapter = FileSystemAdapter([str(scan_dir)], ["*.jsonl"])
        results = adapter.incremental_query({"checkpoint": time.time() + 3600})
        assert len(results) == 0

    def test_normalize_passthrough(self):
        """Normalize passes through records unchanged."""
        adapter = FileSystemAdapter([], ["*.jsonl"])
        raw = {"session_id": "s1", "role": "user", "content": "hello",
               "timestamp": "2026-06-19T10:00:00Z", "source": "filesystem"}
        result = adapter.normalize(raw)
        assert result == raw

    def test_validate_connection(self):
        """validate_connection returns False for nonexistent paths."""
        adapter = FileSystemAdapter(["/nonexistent"], ["*.jsonl"])
        assert adapter.validate_connection() is False
