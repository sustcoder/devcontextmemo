"""OpenCode 适配器 — SQLite → 统一 JSONL 转换。

从 OpenCode（CodeBuddy）本地 SQLite 数据库提取对话日志。

OpenCode SQLite schema（真实）：
- ``session`` 表：id, directory, time_created
- ``message`` 表：id, session_id, data（JSON，含 role 字段）, time_created
- ``part`` 表：id, message_id, session_id, data（JSON，含 type/text 字段）, time_created

part.data.type 可能值：text / tool / reasoning
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from devcontext.core.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)


class OpenCodeAdapter(BaseAdapter):
    """OpenCode SQLite 对话日志适配器。

    读取 OpenCode 的 SQLite 数据库，将 session + message + part 三表
    联合查询，输出统一 JSONL 格式。

    使用 json_extract 提取 JSON data 列中的 role/type 字段，
    兼容真实 OpenCode（CodeBuddy）数据库 schema。

    Args:
        db_path: OpenCode SQLite 数据库路径。
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    @property
    def source_name(self) -> str:
        return "opencode"

    def collect(self, source_path: str | None = None) -> list[dict[str, Any]]:
        """从 OpenCode SQLite 采集所有会话记录。

        Args:
            source_path: 可选，覆盖 db_path。

        Returns:
            统一 JSONL 格式的记录列表（按 session_id, time 排序）。

        Raises:
            sqlite3.Error: 数据库不可访问。
        """
        db_path = source_path or self.db_path
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            # 只读模式安全查询
            conn.execute("PRAGMA query_only = 1;")
            conn.execute("PRAGMA busy_timeout = 3000;")

            rows = conn.execute("""
                SELECT
                    s.id           as session_id,
                    s.directory    as directory,
                    json_extract(m.data, '$.role')  as role,
                    json_extract(p.data, '$.type')  as part_type,
                    p.data         as part_data,
                    p.time_created as timestamp,
                    m.id           as message_id
                FROM session s
                JOIN message m ON m.session_id = s.id
                JOIN part p ON p.message_id = m.id
                WHERE json_extract(p.data, '$.type') IN ('text', 'tool', 'reasoning')
                ORDER BY s.id, p.time_created
                """).fetchall()
        finally:
            conn.close()

        # 按 message_id 聚合 parts → 合并为单条消息
        messages: dict[str, dict[str, Any]] = {}
        seq_counter: dict[str, int] = {}

        for row in rows:
            session_id = row["session_id"]
            msg_key = row["message_id"]

            if msg_key not in messages:
                if session_id not in seq_counter:
                    seq_counter[session_id] = 0
                seq_counter[session_id] += 1
                messages[msg_key] = {
                    "session_id": session_id,
                    "seq": seq_counter[session_id],
                    "role": row["role"],
                    "content": "",
                    "timestamp": row["timestamp"],
                    "source": self.source_name,
                    "tools": [],
                    "reasoning": "",
                    "metadata": {"directory": row["directory"]},
                }

            part_data = json.loads(row["part_data"]) if row["part_data"] else {}
            part_type = row["part_type"]

            if part_type == "text":
                text = part_data.get("text", "")
                if messages[msg_key]["content"]:
                    messages[msg_key]["content"] += "\n" + text
                else:
                    messages[msg_key]["content"] = text
            elif part_type == "tool":
                tool_entry = {
                    "tool": part_data.get("tool", ""),
                    "input": part_data.get("state", {}).get("input", {}),
                    "output": part_data.get("state", {}).get("output", {}),
                }
                messages[msg_key]["tools"].append(tool_entry)
            elif part_type == "reasoning":
                messages[msg_key]["reasoning"] = part_data.get("text", "")

        # 清理空 tools/reasoning 字段
        result = list(messages.values())
        for msg in result:
            if not msg["tools"]:
                del msg["tools"]
            if not msg["reasoning"]:
                del msg["reasoning"]

        return result

    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        """标准化单条记录（OpenCode 已在 collect 中完成标准化）。

        Args:
            raw_record: 原始记录。

        Returns:
            补全必填字段的记录。
        """
        return {
            "session_id": raw_record.get("session_id", ""),
            "seq": raw_record.get("seq", 0),
            "role": raw_record.get("role", "user"),
            "content": raw_record.get("content", ""),
            "timestamp": raw_record.get("timestamp", ""),
            "source": self.source_name,
            **{
                k: v for k, v in raw_record.items() if k in ("tools", "reasoning", "metadata") and v
            },
        }
