"""Cursor 适配器 — 最小实现（预留接口）。

Cursor 的对话日志导出格式待调研，当前提供骨架实现。
实际采集逻辑在确定 Cursor 数据源格式后补充。
"""

from __future__ import annotations

from typing import Any

from devcontext.core.adapters.base import BaseAdapter


class CursorAdapter(BaseAdapter):
    """Cursor 对话日志适配器（最小实现）。

    Args:
        source_path: Cursor 数据源路径。
    """

    def __init__(self, source_path: str = "") -> None:
        self._source_path = source_path

    @property
    def source_name(self) -> str:
        return "cursor"

    def collect(self, source_path: str | None = None) -> list[dict[str, Any]]:
        """采集 Cursor 对话记录（待实现）。

        Raises:
            NotImplementedError: Cursor 数据源格式待确定。
        """
        raise NotImplementedError(
            "Cursor adapter is not yet implemented — " "data source format needs to be determined."
        )

    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        """标准化单条记录（待实现）。"""
        return {
            "session_id": raw_record.get("session_id", ""),
            "seq": raw_record.get("seq", 0),
            "role": raw_record.get("role", "user"),
            "content": raw_record.get("content", ""),
            "timestamp": raw_record.get("timestamp", ""),
            "source": self.source_name,
        }
