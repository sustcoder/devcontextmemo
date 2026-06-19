"""Unit tests for SQLiteStore — 建库、表结构、FTS5、触发器、PRAGMA。

验证 Schema V1.1 的 7 张表 + FTS5 虚拟表 + 索引 + 触发器 + PRAGMA 配置。
"""

import os
import tempfile

import pytest

from devcontext.storage.sqlite import SQLiteStore


@pytest.fixture
def memory_store():
    """内存数据库 SQLiteStore（每次测试新建，自动关闭）。"""
    store = SQLiteStore(":memory:")
    store.init_db()
    yield store
    store.close()


@pytest.fixture
def file_store():
    """文件数据库 SQLiteStore（验证 WAL 模式）。"""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        store = SQLiteStore(db_path)
        store.init_db()
        yield store
        store.close()


class TestTableCreation:
    """建表与表结构验证。"""

    def test_all_seven_tables_created(self, memory_store):
        """init_db 后应存在 7 张表（含 FTS5 虚拟表）。"""
        tables = memory_store.list_tables()
        expected = {
            "knowledge_index",
            "knowledge_fts",
            "calibration_log",
            "staging_queue",
            "dead_letter",
            "collector_watermark",
            "batch_log",
        }
        assert set(tables) == expected
        assert len(tables) == 7

    def test_init_db_idempotent(self, memory_store):
        """init_db 幂等：重复调用不报错。"""
        memory_store.init_db()
        memory_store.init_db()
        tables = memory_store.list_tables()
        assert len(tables) == 7

    def test_knowledge_index_columns(self, memory_store):
        """knowledge_index 表含 V1.1 全部字段。"""
        conn = memory_store.get_connection()
        cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_index)").fetchall()}
        required = {
            "id", "title", "domain", "sub_domain",
            "granularity", "stability", "depth",
            "status", "confidence",
            "code_verified", "prune_priority", "concept_tags",
            "certainty", "freshness", "embedding", "uri",
            "used_count", "last_used_at",
            "last_calibrated_at", "calibration_status",
            "source_session", "created_at", "updated_at",
        }
        missing = required - cols
        assert not missing, f"knowledge_index 缺失字段: {missing}"

    def test_knowledge_index_no_content_hash(self, memory_store):
        """V1.1 schema 严格无 content_hash 字段（用户决策 Q2）。"""
        conn = memory_store.get_connection()
        cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_index)").fetchall()}
        assert "content_hash" not in cols

    def test_knowledge_index_no_keywords_summary(self, memory_store):
        """knowledge_index 无 keywords/summary（这些存于 FTS5，由 Step 5 同步）。"""
        conn = memory_store.get_connection()
        cols = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_index)").fetchall()}
        assert "keywords" not in cols
        assert "summary" not in cols


class TestFTS5:
    """FTS5 虚拟表验证。"""

    def test_fts5_available(self, memory_store):
        """FTS5 应可用（Python 内置 sqlite3 通常编译了 FTS5）。"""
        assert memory_store.fts_available is True

    def test_fts5_table_is_virtual(self, memory_store):
        """knowledge_fts 应为虚拟表。"""
        conn = memory_store.get_connection()
        row = conn.execute(
            "SELECT type FROM sqlite_master WHERE name='knowledge_fts'"
        ).fetchone()
        assert row[0] == "table"

    def test_fts5_external_content(self, memory_store):
        """knowledge_fts 为自包含表（非外部内容表，因 keywords/summary 不在 knowledge_index）。"""
        conn = memory_store.get_connection()
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='knowledge_fts'"
        ).fetchone()[0]
        # V1.1 原设计为外部内容表，但因 knowledge_index 无 keywords/summary 列，
        # 改为自包含表（不带 content= 参数）
        assert "content='knowledge_index'" not in sql

    def test_fts5_unicode61_tokenizer(self, memory_store):
        """FTS5 使用 unicode61 分词器（CJK 支持）。"""
        conn = memory_store.get_connection()
        sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE name='knowledge_fts'"
        ).fetchone()[0]
        assert "unicode61" in sql
        assert "remove_diacritics 2" in sql

    def test_fts5_sync_insert(self, memory_store):
        """_sync_fts 能插入 FTS5 索引。"""
        conn = memory_store.get_connection()
        # 先在 knowledge_index 插一行
        conn.execute(
            "INSERT INTO knowledge_index (id, title, granularity, stability, depth, "
            "status, uri, created_at, updated_at) "
            "VALUES ('k1', '支付流程', 'L0', 'S1', 'KW', 'staged', '/t.md', '2026', '2026')"
        )
        conn.commit()
        rowid = conn.execute(
            "SELECT rowid FROM knowledge_index WHERE id='k1'"
        ).fetchone()[0]
        memory_store._sync_fts(rowid, "支付流程", "支付,状态机", "支付流程摘要")
        # FTS5 查询验证
        result = conn.execute(
            "SELECT title FROM knowledge_fts WHERE knowledge_fts MATCH '支付'"
        ).fetchall()
        assert len(result) == 1
        assert result[0][0] == "支付流程"

    def test_fts5_sync_update(self, memory_store):
        """_sync_fts 能更新 FTS5 索引（upsert 语义）。"""
        conn = memory_store.get_connection()
        conn.execute(
            "INSERT INTO knowledge_index (id, title, granularity, stability, depth, "
            "status, uri, created_at, updated_at) "
            "VALUES ('k1', '旧标题', 'L0', 'S1', 'KW', 'staged', '/t.md', '2026', '2026')"
        )
        conn.commit()
        rowid = conn.execute(
            "SELECT rowid FROM knowledge_index WHERE id='k1'"
        ).fetchone()[0]
        memory_store._sync_fts(rowid, "旧标题", "kw1", "summary1")
        memory_store._sync_fts(rowid, "新标题", "kw2", "summary2")
        result = conn.execute(
            "SELECT title FROM knowledge_fts WHERE knowledge_fts MATCH '新标题'"
        ).fetchall()
        assert len(result) == 1
        # 旧标题不应再命中
        old_result = conn.execute(
            "SELECT title FROM knowledge_fts WHERE knowledge_fts MATCH '旧标题'"
        ).fetchall()
        assert len(old_result) == 0


class TestTriggers:
    """触发器验证。"""

    def test_ki_updated_at_trigger_exists(self, memory_store):
        """ki_updated_at 触发器存在。"""
        conn = memory_store.get_connection()
        triggers = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='ki_updated_at'"
        ).fetchall()]
        assert len(triggers) == 1

    def test_ki_updated_at_auto_updates(self, memory_store):
        """UPDATE knowledge_index 时 updated_at 自动刷新。"""
        conn = memory_store.get_connection()
        conn.execute(
            "INSERT INTO knowledge_index (id, title, granularity, stability, depth, "
            "status, uri, created_at, updated_at) "
            "VALUES ('k1', 't', 'L0', 'S1', 'KW', 'staged', '/t.md', '2026-01-01', '2026-01-01')"
        )
        conn.commit()
        # UPDATE 不显式改 updated_at
        conn.execute("UPDATE knowledge_index SET confidence=0.5 WHERE id='k1'")
        conn.commit()
        updated = conn.execute(
            "SELECT updated_at FROM knowledge_index WHERE id='k1'"
        ).fetchone()[0]
        assert updated != "2026-01-01", "updated_at 触发器未工作"

    def test_ki_ad_delete_trigger_exists(self, memory_store):
        """ki_ad DELETE 触发器存在（FTS5 删除同步）。"""
        conn = memory_store.get_connection()
        triggers = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='ki_ad'"
        ).fetchall()]
        assert len(triggers) == 1

    def test_batch_log_updated_trigger_exists(self, memory_store):
        """batch_log_updated 触发器存在。"""
        conn = memory_store.get_connection()
        triggers = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name='batch_log_updated'"
        ).fetchall()]
        assert len(triggers) == 1


class TestPragmas:
    """PRAGMA 配置验证。"""

    def test_foreign_keys_on(self, memory_store):
        """foreign_keys 始终开启。"""
        conn = memory_store.get_connection()
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_synchronous_normal(self, memory_store):
        """synchronous = NORMAL（WAL 下安全且性能好）。"""
        conn = memory_store.get_connection()
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # 1 = NORMAL

    def test_cache_size_64mb(self, memory_store):
        """cache_size = -64000（64MB）。"""
        conn = memory_store.get_connection()
        assert conn.execute("PRAGMA cache_size").fetchone()[0] == -64000

    def test_wal_mode_file_db(self, file_store):
        """文件数据库 journal_mode = WAL。"""
        conn = file_store.get_connection()
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    def test_wal_skipped_memory_db(self, memory_store):
        """内存数据库跳过 WAL（WAL 不支持 :memory:）。"""
        conn = memory_store.get_connection()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "memory"  # :memory: 默认 journal_mode


class TestIndexes:
    """索引验证。"""

    def test_knowledge_index_indexes_count(self, memory_store):
        """knowledge_index 至少 12 个索引（V1.1 schema 定义）。"""
        conn = memory_store.get_connection()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_ki_%'"
        ).fetchall()
        assert len(indexes) >= 12

    def test_calibration_log_indexes(self, memory_store):
        """calibration_log 有 2 个索引。"""
        conn = memory_store.get_connection()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_cl_%'"
        ).fetchall()
        assert len(indexes) == 2

    def test_staging_queue_indexes(self, memory_store):
        """staging_queue 有 2 个索引。"""
        conn = memory_store.get_connection()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_sq_%'"
        ).fetchall()
        assert len(indexes) == 2

    def test_batch_log_indexes(self, memory_store):
        """batch_log 有 2 个索引。"""
        conn = memory_store.get_connection()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_bl_%'"
        ).fetchall()
        assert len(indexes) == 2
