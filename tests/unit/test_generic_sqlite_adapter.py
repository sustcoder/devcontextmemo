"""Tests for GenericSQLiteAdapter."""

import sqlite3

import pytest

from devcontext.core.adapters.generic_sqlite import GenericSQLiteAdapter


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE msgs (id INTEGER PRIMARY KEY, content TEXT, role TEXT)")
    conn.execute("INSERT INTO msgs (id, content, role) VALUES (1, 'hello', 'user')")
    conn.execute("INSERT INTO msgs (id, content, role) VALUES (2, 'world', 'assistant')")
    conn.commit()
    conn.close()
    return str(db_path)


class TestGenericSQLiteAdapter:
    """GenericSQLiteAdapter tests."""

    def test_source_name(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="cursor",
            db_path=test_db,
            query_template="SELECT id, content, role FROM msgs WHERE id > ?",
            id_column="id",
        )
        assert adapter.source_name == "cursor"

    def test_collect_works(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="cursor",
            db_path=test_db,
            query_template="SELECT id, content, role FROM msgs WHERE id > ?",
        )
        results = adapter.collect()
        assert len(results) == 2

    def test_incremental_query(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="cursor",
            db_path=test_db,
            query_template="SELECT id, content, role FROM msgs WHERE id > ?",
            id_column="id",
        )
        results = adapter.incremental_query({"cursor_last_id": 0})
        assert len(results) == 2

    def test_incremental_respects_watermark(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="cursor",
            db_path=test_db,
            query_template="SELECT id, content, role FROM msgs WHERE id > ?",
            id_column="id",
        )
        results = adapter.incremental_query({"cursor_last_id": 1})
        assert len(results) == 1
        assert results[0]["content"] == "world"

    def test_normalize(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="comate",
            db_path=test_db,
            query_template="SELECT id, content, role FROM msgs WHERE id > ?",
        )
        raw = {"id": 1, "content": "hello", "role": "user"}
        result = adapter.normalize(raw)
        assert result["source"] == "comate"
        assert result["content"] == "hello"
        assert result["role"] == "user"

    def test_validate_connection(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="test", db_path=test_db,
            query_template="SELECT 1",
        )
        assert adapter.validate_connection() is True

    def test_validate_connection_missing(self):
        adapter = GenericSQLiteAdapter(
            source_name="test", db_path="/nonexistent/test.db",
            query_template="SELECT 1",
        )
        assert adapter.validate_connection() is False
