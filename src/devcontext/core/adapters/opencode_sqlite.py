"""OpenCode SQLite 适配器 — 轮询模式增量采集。

专为 PollingCollector 设计，封装 OpenCode SQLite 数据库的读写操作。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from devcontext.core.adapters.base import BaseAdapter


class OpenCodeSQLiteAdapter(BaseAdapter):
    """OpenCode SQLite 数据源适配器。

    通过只读 SQLite 连接查询 OpenCode 对话记录。
    继承 BaseAdapter，实现 collect/normalize/incremental_query。

    Attributes:
        db_path: OpenCode SQLite 数据库路径。
    """

    def __init__(self, db_path: str):
        """初始化适配器。

        Args:
            db_path: SQLite 数据库文件路径。
        """
        self.db_path = db_path

    @property
    def source_name(self) -> str:
        """数据源标识。"""
        return "opencode"

    def collect(self, source_path: str | None = None) -> list[dict[str, Any]]:
        """全量采集：委托给 fetch_full。

        Args:
            source_path: 数据源路径（未使用）。

        Returns:
            标准化后的消息列表。
        """
        return self.fetch_full()

    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        """标准化原始记录为统一格式。

        Args:
            raw_record: 原始数据库行记录。

        Returns:
            标准化字典（session_id, role, content, timestamp, source, id）。
        """
        return {
            "session_id": raw_record.get("session_id", ""),
            "role": raw_record.get("role", "user"),
            "content": raw_record.get("content", ""),
            "timestamp": raw_record.get("timestamp", "1970-01-01T00:00:00Z"),
            "source": raw_record.get("source", self.source_name),
            "id": raw_record.get("id", ""),
        }

    def incremental_query(self, watermarks: dict[str, Any]) -> list[dict[str, Any]]:
        """增量查询：按 watermark 拉取新消息。

        使用只读连接查询 OpenCode SQLite，仅返回 message.id > watermark 的记录。

        Args:
            watermarks: {"last_message_id": str} 水位线。

        Returns:
            标准化后的新消息列表。
        """
        import sqlite3

        last_id = str(watermarks.get("checkpoint", "0"))
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA query_only = ON")
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """SELECT
                m.id,
                m.conversation_id AS session_id,
                m.role,
                m.created_at AS timestamp,
                GROUP_CONCAT(
                    p.type || ':' || COALESCE(p.content, ''), '\n'
                ) AS parts
            FROM message m
            JOIN (
                SELECT DISTINCT conversation_id
                FROM message
                WHERE id > ?
            ) a ON m.conversation_id = a.conversation_id
            LEFT JOIN part p ON p.message_id = m.id
            WHERE m.id > ?
            GROUP BY m.id
            ORDER BY m.id""",
            (last_id, last_id),
        ).fetchall()
        conn.close()

        results = []
        for row in rows:
            record = dict(row)
            record["seq"] = len(results) + 1
            record["source"] = self.source_name
            record["content"] = record.get("parts") or ""
            results.append(self.normalize(record))

        return results

    def validate_connection(self) -> bool:
        """检查数据库文件是否存在。

        Returns:
            True 如果 db_path 指向的文件存在。
        """
        return Path(self.db_path).expanduser().exists()
