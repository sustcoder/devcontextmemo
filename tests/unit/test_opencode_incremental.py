"""Tests for OpenCodeAdapter incremental_query."""

import json
import sqlite3

import pytest

from devcontext.core.adapters.opencode import OpenCodeAdapter


@pytest.fixture
def opencode_db(tmp_path):
    """Create a minimal OpenCode-style SQLite database."""
    db_path = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS session (
            id TEXT PRIMARY KEY, directory TEXT, time_created TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS message (
            id TEXT PRIMARY KEY, session_id TEXT, data TEXT, time_created TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS part (
            id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
            data TEXT, time_created TEXT
        )"""
    )
    conn.commit()
    conn.close()
    yield db_path


def _insert_message(conn, msg_id, session_id, role, created_at):
    conn.execute(
        "INSERT INTO message(id, session_id, data, time_created) VALUES (?, ?, ?, ?)",
        (msg_id, session_id, json.dumps({"role": role}), created_at),
    )


def _insert_part(conn, part_id, message_id, session_id, part_type, content, created_at):
    conn.execute(
        "INSERT INTO part(id, message_id, session_id, data, time_created) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            part_id,
            message_id,
            session_id,
            json.dumps({"type": part_type, "text": content}),
            created_at,
        ),
    )


class TestOpenCodeIncremental:
    """Tests for incremental_query on OpenCodeAdapter."""

    def test_incremental_returns_new_messages(self, opencode_db):
        conn = sqlite3.connect(str(opencode_db))
        conn.execute(
            "INSERT INTO session(id, directory, time_created) "
            "VALUES ('c1', '/tmp', '2026-06-19T10:00:00Z')"
        )
        _insert_message(conn, "msg1", "c1", "user", "2026-06-19T10:00:00Z")
        _insert_message(conn, "msg2", "c1", "assistant", "2026-06-19T10:00:05Z")
        _insert_message(conn, "msg3", "c1", "user", "2026-06-19T10:00:10Z")
        _insert_part(conn, "p1", "msg1", "c1", "text", "hello", "2026-06-19T10:00:00Z")
        _insert_part(conn, "p2", "msg2", "c1", "text", "hi there", "2026-06-19T10:00:05Z")
        _insert_part(conn, "p3", "msg3", "c1", "text", "more text", "2026-06-19T10:00:10Z")
        conn.commit()
        conn.close()

        adapter = OpenCodeAdapter(str(opencode_db))
        results = adapter.incremental_query({"checkpoint": "0"})
        assert len(results) == 3
        assert results[0]["session_id"] == "c1"
        assert results[0]["role"] == "user"
        assert "hello" in results[0]["content"]

    def test_incremental_respects_watermark(self, opencode_db):
        conn = sqlite3.connect(str(opencode_db))
        conn.execute(
            "INSERT INTO session(id, directory, time_created) "
            "VALUES ('c1', '/tmp', '2026-06-19T10:00:00Z')"
        )
        _insert_message(conn, "msg1", "c1", "user", "2026-06-19T10:00:00Z")
        _insert_message(conn, "msg2", "c1", "assistant", "2026-06-19T10:00:05Z")
        _insert_part(conn, "p1", "msg1", "c1", "text", "old", "2026-06-19T10:00:00Z")
        _insert_part(conn, "p2", "msg2", "c1", "text", "new", "2026-06-19T10:00:05Z")
        conn.commit()
        conn.close()

        adapter = OpenCodeAdapter(str(opencode_db))
        results = adapter.incremental_query({"checkpoint": "msg1"})
        assert len(results) == 1
        assert results[0]["content"] == "new"

    def test_empty_db_returns_empty(self, opencode_db):
        adapter = OpenCodeAdapter(str(opencode_db))
        results = adapter.incremental_query({"checkpoint": "0"})
        assert results == []
