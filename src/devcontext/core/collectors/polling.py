"""轮询采集策略 — 定时轮询线程 + Watermark 管理。"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from devcontext.core.collectors.base import BaseCollector, CleanMessage

logger = logging.getLogger(__name__)

DEFAULT_WATERMARK_FILE = Path.home() / ".devContextMemo" / "watermarks.json"


class WatermarkStore:
    """水位线持久化 — JSON 文件存储。

    路径：~/.devContextMemo/watermarks.json
    """

    @staticmethod
    def load(filepath: Path | None = None) -> dict:
        """加载水位线。

        Args:
            filepath: 水位线文件路径，默认 ~/.devContextMemo/watermarks.json。

        Returns:
            水位线字典。
        """
        path = filepath or DEFAULT_WATERMARK_FILE
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    @staticmethod
    def save(source_name: str, watermarks: dict, filepath: Path | None = None):
        """持久化水位线（进程安全）。

        Args:
            source_name: 数据源名称。
            watermarks: 水位线字典。
            filepath: 水位线文件路径。
        """
        import fcntl

        path = filepath or DEFAULT_WATERMARK_FILE
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "a+", encoding="utf-8") as f:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.seek(0)
                existing = {}
                try:
                    existing = json.loads(f.read() or "{}")
                except (json.JSONDecodeError, OSError):
                    pass

                existing[source_name] = watermarks

                f.seek(0)
                f.truncate()
                f.write(
                    json.dumps(existing, indent=2, ensure_ascii=False)
                )
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


class PollingCollector(BaseCollector):
    """定时轮询采集器 — Phase 1 唯一采集策略。

    Attributes:
        adapter: 数据源适配器。
        poll_interval_ms: 轮询间隔（毫秒）。
        watermarks: 水位线字典 {adapter.source_name: checkpoint}。
        max_buffer_messages: 缓冲区最大消息数。
        max_buffer_tokens: 缓冲区最大 token 数。
    """

    def __init__(
        self,
        adapter: Any,
        poll_interval_ms: int = 500,
        max_buffer_messages: int = 200,
        max_buffer_tokens: int = 6000,
    ):
        """初始化轮询采集器。

        Args:
            adapter: 数据源适配器（实现 CollectorAdapter 接口）。
            poll_interval_ms: 轮询间隔。
            max_buffer_messages: 缓冲区消息数阈值。
            max_buffer_tokens: 缓冲区 token 数阈值。
        """
        super().__init__(adapter)
        self.poll_interval_ms = poll_interval_ms
        self.max_buffer_messages = max_buffer_messages
        self.max_buffer_tokens = max_buffer_tokens
        self.watermarks: dict = WatermarkStore.load().get(
            adapter.source_name, {}
        )
        self._running = False
        self._task: asyncio.Task | None = None

    def _check_buffer(self, max_messages=None, max_tokens=None) -> bool:
        """检查缓冲区，默认使用实例阈值。

        Args:
            max_messages: 最大消息数阈值（None 则用 self.max_buffer_messages）。
            max_tokens: 最大 token 阈值（None 则用 self.max_buffer_tokens）。

        Returns:
            True 如果缓冲区应触发 flush。
        """
        return super()._check_buffer(
            max_messages=max_messages if max_messages is not None else self.max_buffer_messages,
            max_tokens=max_tokens if max_tokens is not None else self.max_buffer_tokens,
        )

    def _poll_once(self) -> list[CleanMessage]:
        """执行一次轮询（同步，供测试用）。

        Returns:
            本轮采集到的 CleanMessage 列表。
        """
        try:
            raw_messages = self.adapter.incremental_query(self.watermarks)
        except Exception:
            logger.warning(
                "poll failed for source=%s, retry next cycle",
                self.adapter.source_name,
                exc_info=True,
            )
            return []

        results = []
        for raw in raw_messages:
            normalized = self.adapter.normalize(raw)
            clean = CleanMessage(
                session_id=normalized.get("session_id", ""),
                role=normalized.get("role", "user"),
                content=normalized.get("content", ""),
                timestamp=self._parse_timestamp(
                    normalized.get("timestamp", 0)
                ),
                source=normalized.get("source", self.adapter.source_name),
            )
            cleaned = self._strip_noise(clean)
            results.append(cleaned)

        self.buffer.extend(results)
        self._update_watermarks(raw_messages)
        return results

    def _update_watermarks(self, raw_messages: list[dict]):
        """更新水位线：取最后一条消息的 ID 或时间戳。"""
        if not raw_messages:
            return
        last = raw_messages[-1]
        self.watermarks["checkpoint"] = last.get("id") or str(time.time())

    def _parse_timestamp(self, ts) -> float:
        """将时间戳转换为 float（Unix 时间）。"""
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, str):
            try:
                from datetime import datetime

                return datetime.fromisoformat(
                    ts.replace("Z", "+00:00")
                ).timestamp()
            except (ValueError, TypeError):
                return time.time()
        return time.time()

    async def start(self) -> asyncio.Task:
        """启动后台轮询 task。

        Returns:
            asyncio Task 对象。
        """
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        return self._task

    async def _poll_loop(self):
        """后台轮询循环。"""
        while self._running:
            try:
                await asyncio.to_thread(self._poll_once)
            except Exception:
                logger.warning(
                    "poll_loop error for source=%s",
                    self.adapter.source_name,
                    exc_info=True,
                )

            if self._check_buffer():
                flushed = self._flush_buffer()
                self._emit(flushed)

            await asyncio.sleep(self.poll_interval_ms / 1000)

    async def stop(self):
        """停止轮询并持久化水位线。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self.buffer:
            self._emit(self._flush_buffer())

        self._persist_watermarks()

    def _persist_watermarks(self):
        """持久化水位线到 WatermarkStore。"""
        WatermarkStore.save(
            self.adapter.source_name,
            dict(self.watermarks),
        )
