"""采集策略层 — 缓冲 + 去噪 + 回调，不绑定轮询或 Hook。"""

from devcontext.core.collectors.base import BaseCollector, CleanMessage
from devcontext.core.collectors.polling import PollingCollector, WatermarkStore

__all__ = ["BaseCollector", "CleanMessage", "PollingCollector", "WatermarkStore"]
