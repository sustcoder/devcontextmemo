"""Tests for OpenCodeSQLiteAdapter."""

import sqlite3

import pytest

from devcontext.core.adapters.opencode_sqlite import OpenCodeSQLiteAdapter


@pytest.fixture
def opencode_db(tmp_path):
    """Create a minimal OpenCode-style SQLite database."""
    db_path = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE conversation(id TEXT PRIMARY KEY, title TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE message(id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE part(id TEXT PRIMARY KEY, message_id TEXT, type TEXT, content TEXT, tool_name TEXT, created_at TEXT)")
    conn.execute("INSERT INTO conversation(id, title, created_at) VALUES ('c1', 'S', '2026-06-19T10:00:00Z')")
    conn.execute("INSERT INTO message(id, conversation_id, role, created_at) VALUES ('msg1', 'c1', 'user', '2026-06-19T10:00:00Z')")
    conn.execute("INSERT INTO part(id, message_id, type, content, tool_name, created_at) VALUES ('p1', 'msg1', 'text', 'hello', NULL, '2026-06-19T10:00:00Z')")
    conn.commit()
    conn.close()
    yield db_path


class TestOpenCodeSQLiteAdapter:
    """OpenCodeSQLiteAdapter tests."""

    def test_source_name(self, opencode_db):
        """source_name should return 'opencode'."""
        adapter = OpenCodeSQLiteAdapter(str(opencode_db))
        assert adapter.source_name == "opencode"

    def test_collect_works(self, opencode_db):
        """collect() should return at least one message."""
        adapter = OpenCodeSQLiteAdapter(str(opencode_db))
        results = adapter.collect()
        assert len(results) >= 1

    def test_incremental_query(self, opencode_db):
        """incremental_query should return messages with session_id."""
        adapter = OpenCodeSQLiteAdapter(str(opencode_db))
        results = adapter.incremental_query({"checkpoint": "0"})
        assert len(results) >= 1
        assert "session_id" in results[0]

    def test_normalize_output(self, opencode_db):
        """Normalized output should contain required fields."""
        adapter = OpenCodeSQLiteAdapter(str(opencode_db))
        results = adapter.collect()
        assert "session_id" in results[0]
        assert "role" in results[0]
        assert "source" in results[0]
        assert results[0]["source"] == "opencode"

    def test_validate_connection_true_when_db_exists(self, opencode_db):
        """validate_connection should return True when db file exists."""
        adapter = OpenCodeSQLiteAdapter(str(opencode_db))
        assert adapter.validate_connection() is True

    def test_validate_connection_false_when_db_missing(self):
        """validate_connection should return False when db file is missing."""
        adapter = OpenCodeSQLiteAdapter("/nonexistent/path.db")
        assert adapter.validate_connection() is False
