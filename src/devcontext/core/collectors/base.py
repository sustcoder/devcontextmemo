"""采集策略基类 + CleanMessage 数据契约。"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CleanMessage:
    """采集器标准化输出，全流水线统一数据格式。

    Attributes:
        session_id: 会话标识（来自 adapter 的 normalize）。
        role: 消息角色（user/assistant/system/tool）。
        content: 消息正文（已去噪）。
        timestamp: Unix 时间戳。
        source: 数据源名称（对应 adapter.source_name）。
        metadata: 扩展字段（tools、reasoning 等）。
    """

    session_id: str
    role: str
    content: str
    timestamp: float
    source: str
    metadata: dict = field(default_factory=dict)


class BaseCollector:
    """采集策略基类 — 不绑定轮询或 Hook。

    仅提供缓冲管理 + 去噪 + 回调通知。子类实现 start/stop。
    """

    def __init__(self, adapter: Any):
        self.adapter: Any = adapter
        self.buffer: list[CleanMessage] = []
        self.on_buffer_ready: Callable[[list[CleanMessage]], None] | None = None

    def _strip_noise(self, msg: CleanMessage) -> CleanMessage:
        """三层剥壳：移除 system-reminder / relevant-memories / subagent-context。

        Args:
            msg: 待去噪的 CleanMessage。

        Returns:
            去噪后的同一 CleanMessage 对象（content 已清洗）。
        """
        patterns = [
            r"<system-reminder>.*?</system-reminder>",
            r"<relevant-memories>.*?</relevant-memories>",
            r"<openviking-context>.*?</openviking-context>",
            r"\[Subagent Context\].*?\[/Subagent Context\]",
        ]
        cleaned = msg.content
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL)
        msg.content = cleaned.strip()
        return msg

    def _check_buffer(self, max_messages: int = 200, max_tokens: int = 6000) -> bool:
        """检查缓冲区是否达到触发阈值。

        Args:
            max_messages: 最大消息数阈值。
            max_tokens: 最大 token 阈值（简化估算：len(content)//2）。

        Returns:
            True 如果缓冲区应触发 flush。
        """
        if len(self.buffer) >= max_messages:
            return True
        total_tokens = sum(len(m.content) // 2 for m in self.buffer)
        return total_tokens >= max_tokens

    def _flush_buffer(self) -> list[CleanMessage]:
        """清空缓冲区并返回所有消息。

        Returns:
            被清空的消息列表。
        """
        flushed = list(self.buffer)
        self.buffer.clear()
        return flushed

    def _emit(self, messages: list[CleanMessage]) -> None:
        """触发 on_buffer_ready 回调。

        Args:
            messages: 触发回调的消息列表。
        """
        if self.on_buffer_ready:
            self.on_buffer_ready(messages)

    def start(self):
        """启动采集器（子类实现）。"""
        raise NotImplementedError

    def stop(self):
        """停止采集器（子类实现）。"""
        raise NotImplementedError
