"""适配器基类 — 接口定义。

所有数据源适配器必须实现本接口，输出统一 JSONL 格式。

统一 JSONL 格式（每行一个 dict）：
    {
        "session_id": "sess_abc",
        "seq": 1,
        "role": "user" | "assistant" | "system" | "tool",
        "content": "消息正文",
        "timestamp": "2026-06-18T10:00:00Z",
        "source": "opencode" | "comate" | "cursor" | "manual",
        "tools": [...],          # optional
        "reasoning": "...",      # optional
        "metadata": {...}        # optional
    }
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """数据源适配器抽象基类。

    将 AI 编程工具的对话日志转换为统一 JSONL 格式。
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据源标识（opencode/comate/cursor）。"""
        ...

    @abstractmethod
    def collect(self, source_path: str) -> list[dict[str, Any]]:
        """从数据源采集原始会话记录。

        Args:
            source_path: 数据源路径或标识符（SQLite 文件路径 / JSON 文件路径）。

        Returns:
            统一 JSONL 格式的会话记录列表（按 session_id, seq 排序）。
        """
        ...

    @abstractmethod
    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        """将单条原始记录标准化为统一格式。

        Args:
            raw_record: 原始记录。

        Returns:
            标准化后的记录，含 session_id/seq/role/content/timestamp/source。
        """
        ...

    def normalize_all(self, raw_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """批量标准化（默认逐条调用 normalize，子类可覆写优化）。

        Args:
            raw_records: 原始记录列表。

        Returns:
            标准化后的记录列表。
        """
        return [self.normalize(r) for r in raw_records]

    def incremental_query(self, watermarks: dict) -> list[dict[str, Any]]:
        """增量查询：按 watermark 拉取新消息。

        Args:
            watermarks: {source_name: last_checkpoint} 水位线字典。

        Returns:
            新消息列表，每条消息为 dict[str, Any]。

        Raises:
            NotImplementedError: 子类可覆写。
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement incremental_query"
        )

    def fetch_full(self) -> list[dict[str, Any]]:
        """全量查询：冷启动或手动触发时使用。

        默认调用 incremental_query({})。

        Returns:
            全部消息列表。
        """
        return self.incremental_query({})

    def validate_connection(self) -> bool:
        """检查数据源是否可访问。

        Returns:
            True 如果数据源可访问。
        """
        return True
