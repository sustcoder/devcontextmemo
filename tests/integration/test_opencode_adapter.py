"""OpenCodeAdapter 集成测试 — 真实 SQLite 数据库采集验证。

测试内容：
1. 用合成 SQLite 数据库（模拟真实 OpenCode schema）验证采集流程
2. 用真实 OpenCode 数据库（如果存在）验证端到端采集
"""

import json
import sqlite3
import time
from pathlib import Path

import pytest

from devcontext.core.adapters.opencode import OpenCodeAdapter

# 真实 OpenCode 数据库路径
_REAL_OPENCODE_DB = Path.home() / ".local/share/opencode/opencode.db"


def _create_test_opencode_db(db_path: str) -> None:
    """创建模拟真实 OpenCode schema 的 SQLite 数据库并填充测试数据。"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL;")

    # 创建表（与真实 OpenCode schema 一致）
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session (
            id TEXT PRIMARY KEY,
            directory TEXT,
            time_created INTEGER
        );
        CREATE TABLE IF NOT EXISTS message (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            data TEXT,
            time_created INTEGER
        );
        CREATE TABLE IF NOT EXISTS part (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            session_id TEXT,
            data TEXT,
            time_created INTEGER
        );
    """)

    now = int(time.time() * 1000)

    # 插入测试会话
    conn.execute(
        "INSERT INTO session (id, directory, time_created) VALUES (?, ?, ?)",
        ("sess-001", "/Users/test/project", now),
    )

    # 插入消息（role 在 JSON data 中）
    conn.execute(
        "INSERT INTO message (id, session_id, data, time_created) VALUES (?, ?, ?, ?)",
        ("msg-001", "sess-001", json.dumps({"role": "user", "model": "claude"}), now),
    )
    conn.execute(
        "INSERT INTO message (id, session_id, data, time_created) VALUES (?, ?, ?, ?)",
        ("msg-002", "sess-001", json.dumps({"role": "assistant", "model": "claude"}), now + 1000),
    )

    # 插入 parts（type 和 text 在 JSON data 中）
    conn.execute(
        "INSERT INTO part (id, message_id, session_id, data, time_created) VALUES (?, ?, ?, ?, ?)",
        ("p-001", "msg-001", "sess-001",
         json.dumps({"type": "text", "text": "帮我写一个幂等校验函数"}),
         now),
    )
    conn.execute(
        "INSERT INTO part (id, message_id, session_id, data, time_created) VALUES (?, ?, ?, ?, ?)",
        ("p-002", "msg-002", "sess-001",
         json.dumps({"type": "text", "text": "已实现 @Idempotent 注解校验"}),
         now + 1000),
    )
    conn.execute(
        "INSERT INTO part (id, message_id, session_id, data, time_created) VALUES (?, ?, ?, ?, ?)",
        ("p-003", "msg-002", "sess-001",
         json.dumps({"type": "reasoning", "text": "分析了幂等校验的最佳实践"}),
         now + 1500),
    )

    conn.commit()
    conn.close()


class TestOpenCodeAdapterSynthetic:
    """用合成数据库验证 OpenCodeAdapter 采集逻辑。"""

    def test_collect_returns_all_messages(self, tmp_path):
        """采集应返回所有消息记录。"""
        db_path = str(tmp_path / "test_opencode.db")
        _create_test_opencode_db(db_path)

        adapter = OpenCodeAdapter(db_path)
        records = adapter.collect()

        assert len(records) == 2  # msg-001 + msg-002（parts 已聚合）

    def test_collect_preserves_roles(self, tmp_path):
        """采集应正确保留 user/assistant 角色。"""
        db_path = str(tmp_path / "test_opencode.db")
        _create_test_opencode_db(db_path)

        adapter = OpenCodeAdapter(db_path)
        records = adapter.collect()

        roles = {r["role"] for r in records}
        assert "user" in roles
        assert "assistant" in roles

    def test_collect_aggregates_text_parts(self, tmp_path):
        """多个 text part 应聚合到同一条消息的 content 字段。"""
        db_path = str(tmp_path / "test_opencode.db")
        _create_test_opencode_db(db_path)

        # 添加第二个 text part 到 msg-002
        conn = sqlite3.connect(db_path)
        now = int(time.time() * 1000)
        conn.execute(
            "INSERT INTO part (id, message_id, session_id, data, time_created) VALUES (?, ?, ?, ?, ?)",
            ("p-004", "msg-002", "sess-001",
             json.dumps({"type": "text", "text": "补充分页参数"}),
             now + 2000),
        )
        conn.commit()
        conn.close()

        adapter = OpenCodeAdapter(db_path)
        records = adapter.collect()

        # msg-002 应该有两条 text part 合并
        assistant_msg = [r for r in records if r["role"] == "assistant"][0]
        assert "已实现" in assistant_msg["content"]
        assert "补充分页" in assistant_msg["content"]

    def test_collect_extracts_reasoning(self, tmp_path):
        """reasoning part 应提取到 reasoning 字段。"""
        db_path = str(tmp_path / "test_opencode.db")
        _create_test_opencode_db(db_path)

        adapter = OpenCodeAdapter(db_path)
        records = adapter.collect()

        assistant_msg = [r for r in records if r["role"] == "assistant"][0]
        assert "reasoning" in assistant_msg
        assert "最佳实践" in assistant_msg["reasoning"]

    def test_collect_includes_metadata(self, tmp_path):
        """每条记录应包含 metadata.directory。"""
        db_path = str(tmp_path / "test_opencode.db")
        _create_test_opencode_db(db_path)

        adapter = OpenCodeAdapter(db_path)
        records = adapter.collect()

        for r in records:
            assert "metadata" in r
            assert r["metadata"]["directory"] == "/Users/test/project"

    def test_collect_sets_source_name(self, tmp_path):
        """每条记录的 source 应为 'opencode'。"""
        db_path = str(tmp_path / "test_opencode.db")
        _create_test_opencode_db(db_path)

        adapter = OpenCodeAdapter(db_path)
        records = adapter.collect()

        for r in records:
            assert r["source"] == "opencode"

    def test_collect_empty_db_returns_empty_list(self, tmp_path):
        """空数据库应返回空列表。"""
        db_path = str(tmp_path / "test_opencode.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS session (id TEXT, directory TEXT, time_created INTEGER);
            CREATE TABLE IF NOT EXISTS message (id TEXT, session_id TEXT, data TEXT, time_created INTEGER);
            CREATE TABLE IF NOT EXISTS part (id TEXT, message_id TEXT, session_id TEXT, data TEXT, time_created INTEGER);
        """)
        conn.commit()
        conn.close()

        adapter = OpenCodeAdapter(db_path)
        records = adapter.collect()
        assert records == []

    def test_normalize_completes_missing_fields(self, tmp_path):
        """normalize 应补全缺失的必填字段。"""
        db_path = str(tmp_path / "test_opencode.db")
        _create_test_opencode_db(db_path)

        adapter = OpenCodeAdapter(db_path)
        records = adapter.collect()
        normalized = adapter.normalize(records[0])

        assert "session_id" in normalized
        assert "seq" in normalized
        assert "role" in normalized
        assert "content" in normalized
        assert "timestamp" in normalized
        assert "source" in normalized


@pytest.mark.slow
class TestOpenCodeAdapterRealDB:
    """用真实 OpenCode SQLite 数据库验证采集（如果有）。"""

    @pytest.fixture(autouse=True)
    def check_db_exists(self):
        if not _REAL_OPENCODE_DB.exists():
            pytest.skip("Real OpenCode database not found at ~/.local/share/opencode/opencode.db")

    def test_real_collect_does_not_crash(self):
        """真实数据库采集不抛异常。"""
        adapter = OpenCodeAdapter(_REAL_OPENCODE_DB)
        records = adapter.collect()
        # 只验证不崩溃，记录数量取决于实际数据
        assert isinstance(records, list)

    def test_real_collect_has_valid_schema(self):
        """真实数据库采集中每条记录都有必填字段。"""
        adapter = OpenCodeAdapter(_REAL_OPENCODE_DB)
        records = adapter.collect()
        if not records:
            pytest.skip("No records in OpenCode database")

        for r in records:
            assert "session_id" in r
            assert "seq" in r
            assert "role" in r
            assert isinstance(r["seq"], int)
            assert isinstance(r["role"], str)
            assert "content" in r or "tools" in r or "reasoning" in r

    def test_real_collect_roles_are_valid(self):
        """真实数据库采集的角色是合法值。"""
        adapter = OpenCodeAdapter(_REAL_OPENCODE_DB)
        records = adapter.collect()
        if not records:
            pytest.skip("No records in OpenCode database")

        valid_roles = {"user", "assistant", "system", "tool"}
        for r in records:
            assert r["role"] in valid_roles, f"Invalid role: {r['role']}"

    def test_real_collect_sessions_are_grouped(self):
        """真实数据库采集的记录按 session_id 分组有序。"""
        adapter = OpenCodeAdapter(_REAL_OPENCODE_DB)
        records = adapter.collect()
        if not records:
            pytest.skip("No records in OpenCode database")

        # 同一 session 的 seq 应连续
        sessions: dict[str, list[int]] = {}
        for r in records:
            sessions.setdefault(r["session_id"], []).append(r["seq"])

        for sid, seqs in sessions.items():
            assert seqs == sorted(set(seqs)), f"Session {sid[:8]} has duplicate seq numbers"
