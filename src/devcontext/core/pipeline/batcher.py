"""Step 1: 攒批 — 原始存储按 session 分批 → JSONL 缓冲。

职责：
1. 扫描 ``raw_dir/`` 下的 ``session_*.jsonl`` 文件
2. 对未 flush 的 session 攒批（token 计数阈值触发 / 全量打包）
3. 写入 ``staging_dir/`` 的 ``batch_{timestamp}.jsonl`` + ``_meta.yaml``
4. 标记已 flush 的 session（防止重复攒批）

触发条件（设计文档 §3.1）：
- ``token_count >= 6000``（阈值触发）
- 全量模式（扫描所有未 flush 的 session）

token 计数策略（Phase 4a 简化版）：
- 中文约 1 token/字符，英文约 1 token/4 字符
- 取折中：``len(content) / 2``（中英混合估算）
- 后续可替换为 tiktoken 精确计数

设计依据：``docs/devContextMemo-数据写入流水线-详细设计-V1.0.md`` §三（Step 1）
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from devcontext.core.collectors.base import CleanMessage

logger = logging.getLogger(__name__)

# token 阈值（设计文档 §3.1：6000）
TOKEN_THRESHOLD = 6000

# session 文件名模式
_SESSION_FILE_PATTERN = re.compile(r"^session_(.+)\.jsonl$")


class Batcher:
    """Step 1 攒批器。

    扫描 raw session JSONL，按 token 阈值或全量模式攒批，
    输出 batch JSONL + _meta.yaml 到 staging 目录。

    Args:
        raw_dir: 原始会话存储目录（Step 0 输出）。
        staging_dir: 攒批输出目录（Step 2 输入）。
        token_threshold: 触发攒批的 token 阈值。
    """

    def __init__(
        self,
        raw_dir: str | Path,
        staging_dir: str | Path,
        token_threshold: int = TOKEN_THRESHOLD,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.staging_dir = Path(staging_dir)
        self.token_threshold = token_threshold

    def process(self, *, flush_all: bool = False) -> list[Path]:
        """扫描 raw 目录，攒批未 flush 的 session。

        Args:
            flush_all: True 表示全量模式（忽略 token 阈值，打包所有未 flush session）。
                       False 表示仅当某 session 的 token 数达到阈值时才攒批。

        Returns:
            生成的 batch JSONL 文件路径列表（可能为空）。
        """
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        session_files = self._find_session_files()
        if not session_files:
            logger.info("No session files found in %s", self.raw_dir)
            return []

        flushed = self._load_flushed_sessions()
        batch_paths: list[Path] = []

        for session_id, session_path in session_files:
            if session_id in flushed:
                continue

            records = self._read_jsonl(session_path)
            if not records:
                continue

            token_count = sum(self._count_tokens(r.get("content", "")) for r in records)

            # 判断是否触发攒批
            should_batch = flush_all or token_count >= self.token_threshold
            if not should_batch:
                logger.debug(
                    "Session %s has %d tokens (< %d threshold), skipping",
                    session_id,
                    token_count,
                    self.token_threshold,
                )
                continue

            records.sort(key=lambda r: r.get("seq", 0))
            batch_path = self._write_batch(session_id, records, token_count)
            batch_paths.append(batch_path)
            flushed.add(session_id)
            self._mark_flushed(session_id)

            logger.info(
                "Batched session %s: %d messages, %d tokens → %s",
                session_id,
                len(records),
                token_count,
                batch_path,
            )

        return batch_paths

    def _find_session_files(self) -> list[tuple[str, Path]]:
        """扫描 raw_dir，返回 (session_id, path) 列表。

        Returns:
            (session_id, file_path) 元组列表，按 session_id 排序。
        """
        if not self.raw_dir.exists():
            return []
        result: list[tuple[str, Path]] = []
        for f in sorted(self.raw_dir.iterdir()):
            m = _SESSION_FILE_PATTERN.match(f.name)
            if m and f.is_file():
                result.append((m.group(1), f))
        return result

    def _load_flushed_sessions(self) -> set[str]:
        """加载已 flush 的 session ID 集合。

        通过扫描 staging_dir 下的 ``_meta.yaml`` 文件提取已处理的 session_id。

        Returns:
            已 flush 的 session_id 集合。
        """
        flushed: set[str] = set()
        if not self.staging_dir.exists():
            return flushed
        for meta_file in self.staging_dir.glob("*_meta.yaml"):
            try:
                meta = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
                if isinstance(meta, dict) and meta.get("session_id"):
                    flushed.add(meta["session_id"])
            except (yaml.YAMLError, OSError) as e:
                logger.warning("Failed to read meta file %s: %s", meta_file, e)
        return flushed

    def _mark_flushed(self, session_id: str) -> None:
        """标记 session 为已 flush（通过 _meta.yaml 隐式完成，此处无需额外操作）。

        ``_write_batch`` 已经写了 ``_meta.yaml``，``_load_flushed_sessions``
        下次扫描时会自动识别。此方法保留用于未来扩展（如写 DB batch_log）。
        """
        # Phase 4a：_meta.yaml 即 flush 标记，无需额外操作
        # Phase 4c 可在此 INSERT batch_log 表
        pass

    @staticmethod
    def _count_tokens(text: str) -> int:
        """估算文本的 token 数（简化版）。

        中文约 1 token/字符，英文约 1 token/4 字符。
        取折中值 ``len(text) / 2`` 作为中英混合估算。

        Args:
            text: 文本内容。

        Returns:
            估算的 token 数。
        """
        return max(1, len(text) // 2)

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        """读取 JSONL 文件。

        Args:
            path: JSONL 文件路径。

        Returns:
            记录列表。
        """
        records: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def _write_batch(
        self,
        session_id: str,
        records: list[dict[str, Any]],
        token_count: int,
    ) -> Path:
        """写入 batch JSONL + _meta.yaml。

        Args:
            session_id: 会话 ID。
            records: 消息记录列表。
            token_count: 总 token 数。

        Returns:
            batch JSONL 文件路径。
        """
        timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        batch_id = f"batch-{session_id}-{timestamp}"
        batch_path = self.staging_dir / f"{batch_id}.jsonl"
        meta_path = self.staging_dir / f"{batch_id}_meta.yaml"

        # 写 batch JSONL
        with open(batch_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # 写 _meta.yaml
        meta = {
            "batch_id": batch_id,
            "session_id": session_id,
            "message_count": len(records),
            "token_count": token_count,
            "captured_at": dt.datetime.now().isoformat(),
            "status": "staged",
        }
        meta_path.write_text(
            yaml.dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        return batch_path


class BatchWriter:
    """回调模式攒批器 — 从内存 Buffer 直接接收消息并落盘。

    与现有 Batcher（文件扫描模式）互补：
    - BatchWriter：daemon 自动采集主路径（回调驱动）
    - Batcher：CLI 手动触发 / 历史数据迁移（目录扫描）

    Attributes:
        staging_dir: 批次输出目录。
        token_threshold: token 阈值（默认 6000）。
        max_age_minutes: 批次最大存活时间。
    """

    def __init__(
        self,
        staging_dir: str | Path,
        token_threshold: int = 6000,
        max_age_minutes: int = 30,
    ):
        """初始化攒批器。

        Args:
            staging_dir: 批次输出目录。
            token_threshold: token 阈值。
            max_age_minutes: 批次最大存活时间（分钟）。
        """
        self.staging_dir = Path(staging_dir)
        self.token_threshold = token_threshold
        self.max_age_minutes = max_age_minutes
        self._buffers: dict[str, dict] = {}
        self.on_batch_ready: Callable | None = None

    def _count_tokens(self, text: str) -> int:
        """简化 token 估算：len(text) // 2。

        Args:
            text: 消息正文。

        Returns:
            估算 token 数。
        """
        return len(text) // 2

    def on_messages(
        self,
        messages: list[CleanMessage],
        session_id: str,
        force: bool = False,
    ) -> Path | None:
        """接收消息并攒批。

        Args:
            messages: CleanMessage 列表。
            session_id: 会话 ID。
            force: 强制落盘，忽略 token 阈值。

        Returns:
            批次目录路径（如果触发落盘），否则 None。
        """
        if session_id not in self._buffers:
            self._buffers[session_id] = {
                "messages": [],
                "token_count": 0,
                "started_at": time.time(),
                "source": messages[0].source if messages else "unknown",
            }

        buf = self._buffers[session_id]
        for msg in messages:
            buf["token_count"] += self._count_tokens(msg.content)

        buf["messages"].extend(messages)

        if force or buf["token_count"] >= self.token_threshold:
            return self._flush_batch(session_id)

        return None

    def _flush_batch(self, session_id: str) -> Path:
        """落盘一个批次。

        Args:
            session_id: 会话 ID。

        Returns:
            批次目录路径。
        """
        buf = self._buffers.pop(session_id)

        date_str = time.strftime("%Y-%m-%d", time.localtime())
        batch_dir = self.staging_dir / date_str / session_id
        batch_dir.mkdir(parents=True, exist_ok=True)

        # Write messages.jsonl
        messages_path = batch_dir / "messages.jsonl"
        with open(messages_path, "w", encoding="utf-8") as f:
            for msg in buf["messages"]:
                record = {
                    "session_id": msg.session_id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "source": msg.source,
                }
                if msg.metadata:
                    record.update(msg.metadata)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Write _meta.yaml
        meta = {
            "session_id": session_id,
            "source": buf["source"],
            "batch_created": time.time(),
            "message_count": len(buf["messages"]),
            "token_count": buf["token_count"],
            "message_file": "messages.jsonl",
            "trigger_reason": (
                "token_threshold"
                if buf["token_count"] >= self.token_threshold
                else "message_count"
            ),
            "status": "ready",
        }
        meta_path = batch_dir / "_meta.yaml"
        with open(meta_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False)

        # Trigger downstream callback
        if self.on_batch_ready:
            self.on_batch_ready(batch_dir)

        return batch_dir
