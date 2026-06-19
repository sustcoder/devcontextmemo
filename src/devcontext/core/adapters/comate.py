"""Comate 适配器 — JSON 导出 → 统一 JSONL 转换。

从 Comate 导出的 JSON 文件读取对话日志，转换为统一 JSONL 格式。

Comate JSON 导出格式（预期）：
    {
        "sessions": [
            {
                "id": "sess_abc",
                "messages": [
                    {"role": "user", "content": "...", "timestamp": "..."},
                    ...
                ]
            }
        ]
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devcontext.core.adapters.base import BaseAdapter


class ComateAdapter(BaseAdapter):
    """Comate JSON 导出适配器。

    Args:
        json_path: Comate 导出的 JSON 文件路径。
    """

    def __init__(self, json_path: str | Path) -> None:
        self.json_path = str(json_path)

    @property
    def source_name(self) -> str:
        return "comate"

    def collect(self, source_path: str | None = None) -> list[dict[str, Any]]:
        """从 Comate JSON 导出文件采集会话记录。

        Args:
            source_path: 可选，覆盖 json_path。

        Returns:
            统一 JSONL 格式的记录列表。

        Raises:
            FileNotFoundError: 文件不存在。
            json.JSONDecodeError: JSON 解析失败。
        """
        path = source_path or self.json_path
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        sessions = data.get("sessions", [])
        records: list[dict[str, Any]] = []

        for session in sessions:
            session_id = session.get("id", "")
            messages = session.get("messages", [])
            for seq, msg in enumerate(messages, start=1):
                records.append(
                    self.normalize(
                        {
                            "session_id": session_id,
                            "seq": seq,
                            "role": msg.get("role", "user"),
                            "content": msg.get("content", ""),
                            "timestamp": msg.get("timestamp", ""),
                        }
                    )
                )

        return records

    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        """标准化单条记录。

        Args:
            raw_record: 原始记录。

        Returns:
            统一格式记录。
        """
        return {
            "session_id": raw_record.get("session_id", ""),
            "seq": raw_record.get("seq", 0),
            "role": raw_record.get("role", "user"),
            "content": raw_record.get("content", ""),
            "timestamp": raw_record.get("timestamp", ""),
            "source": self.source_name,
        }
