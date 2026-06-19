"""通用 SQLite 适配器 — 通过配置接入任意 AI 工具数据库。"""

import sqlite3
from pathlib import Path
from typing import Any

from devcontext.core.adapters.base import BaseAdapter


class GenericSQLiteAdapter(BaseAdapter):
    """通用 SQLite 数据源适配器。

    通过 source_name + db_path + query_template 配置即可接入
    Cursor、Comate 等工具的 SQLite 数据库，无需写新适配器。

    Attributes:
        source_name: 数据源标识（如 "cursor", "comate"）。
        db_path: SQLite 数据库路径。
        query_template: 增量查询 SQL 模板（含 ? 占位符）。
        id_column: 水位线字段名（默认 "id"）。
    """

    def __init__(
        self,
        source_name: str,
        db_path: str,
        query_template: str,
        id_column: str = "id",
    ):
        """初始化适配器。

        Args:
            source_name: 数据源标识。
            db_path: SQLite 数据库文件路径。
            query_template: SQL 查询模板，用 ? 占位符绑定 watermark 值。
            id_column: 用作水位线的列名。
        """
        self._source_name = source_name
        self.db_path = db_path
        self.query_template = query_template
        self.id_column = id_column

    @property
    def source_name(self) -> str:
        """数据源标识。"""
        return self._source_name

    def collect(self, source_path=None) -> list[dict[str, Any]]:
        """全量采集：委托给 fetch_full。"""
        return self.fetch_full()

    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        """标准化原始记录。

        Args:
            raw_record: 数据库行 dict。

        Returns:
            标准化字典。
        """
        return {
            "session_id": raw_record.get(
                "conversation_id", raw_record.get("session_id", "")
            ),
            "role": raw_record.get("role", "user"),
            "content": raw_record.get("content", ""),
            "timestamp": raw_record.get(
                "created_at", raw_record.get("timestamp", "1970-01-01T00:00:00Z")
            ),
            "source": self.source_name,
        }

    def incremental_query(self, watermarks: dict[str, Any]) -> list[dict[str, Any]]:
        """增量查询：按 watermark 拉取新记录。

        Args:
            watermarks: {source_name_last_id: checkpoint} 水位线。

        Returns:
            标准化后的记录列表。
        """
        last_id = watermarks.get("checkpoint", 0)

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA query_only = ON")
        conn.row_factory = sqlite3.Row

        rows = conn.execute(self.query_template, (last_id,)).fetchall()
        conn.close()

        return [self.normalize(dict(row)) for row in rows]

    def validate_connection(self) -> bool:
        """检查数据库文件是否存在。"""
        return Path(self.db_path).expanduser().exists()
