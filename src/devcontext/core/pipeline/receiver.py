"""Step 0: 统一接收 — 适配器路由 + 原始会话存储。

职责：
1. 通过适配器从数据源采集对话日志（OpenCode SQLite / Comate JSON / Cursor）
2. 三层剥壳：剥离 system-reminder / relevant-memories / subagent-context 噪声块
3. 按 session 分组，写入 ``raw_dir/session_{session_id}.jsonl``

输出格式（统一 JSONL，每行一条消息）：
    {"session_id": "...", "seq": 1, "role": "user", "content": "...",
     "timestamp": "...", "source": "opencode"}

设计依据：``docs/devContextMemo-数据写入流水线-详细设计-V1.0.md`` §二（Step 0）
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from devcontext.core.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

# 三层剥壳的正则模式（剥离注入的上下文噪声）
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    # ① <system-reminder>...</system-reminder>
    re.compile(r"<system-reminder>.*?</system-reminder>", re.DOTALL | re.IGNORECASE),
    # ② <relevant-memories>...</relevant-memories> / <openviking-context>...</openviking-context>
    re.compile(
        r"<(?:relevant-memories|openviking-context)>.*?</(?:relevant-memories|openviking-context)>",
        re.DOTALL | re.IGNORECASE,
    ),
    # ③ [Subagent Context]...[/Subagent Context]（或到行尾）
    re.compile(
        r"\[Subagent Context\].*?(?:\[/Subagent Context\]|(?=\n\n|\Z))", re.DOTALL | re.IGNORECASE
    ),
]

# 必填字段
_REQUIRED_FIELDS = ("session_id", "seq", "role", "content", "timestamp", "source")

# 合法 role
_VALID_ROLES = {"user", "assistant", "system", "tool"}


class Receiver:
    """Step 0 统一接收器。

    通过适配器采集对话日志，剥壳去噪后写入 raw session JSONL。

    Args:
        adapter: 数据源适配器实例。
        raw_dir: 原始会话存储目录（如 ``~/.devcontext/raw/<project>/``）。
    """

    def __init__(self, adapter: BaseAdapter, raw_dir: str | Path) -> None:
        self.adapter = adapter
        self.raw_dir = Path(raw_dir)

    def receive(self, source_path: str | None = None) -> list[Path]:
        """采集 + 剥壳 + 落盘。

        Args:
            source_path: 数据源路径（传给 adapter.collect）。

        Returns:
            写入的 JSONL 文件路径列表（每个 session 一个文件）。

        Raises:
            ValueError: 采集的记录缺少必填字段。
        """
        raw_records = self.adapter.collect(source_path)
        if not raw_records:
            logger.info("No records collected from %s", self.adapter.source_name)
            return []

        # 标准化
        records = self.adapter.normalize_all(raw_records)

        # 剥壳
        for rec in records:
            rec["content"] = self._strip_noise(rec.get("content", ""))

        # 校验
        self._validate_records(records)

        # 按 session 分组
        sessions: dict[str, list[dict[str, Any]]] = {}
        for rec in records:
            sid = rec["session_id"]
            if sid not in sessions:
                sessions[sid] = []
            sessions[sid].append(rec)

        # 按 seq 排序并写入
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        output_paths: list[Path] = []
        for session_id, msgs in sessions.items():
            msgs.sort(key=lambda m: m.get("seq", 0))
            output_path = self.raw_dir / f"session_{session_id}.jsonl"
            self._write_jsonl(output_path, msgs)
            output_paths.append(output_path)
            logger.info(
                "Wrote %d messages to %s for session %s",
                len(msgs),
                output_path,
                session_id,
            )

        return output_paths

    @staticmethod
    def _strip_noise(content: str) -> str:
        """三层剥壳——移除 system-reminder / relevant-memories / subagent-context 块。

        Args:
            content: 原始消息内容。

        Returns:
            清理后的内容（可能为空字符串）。
        """
        cleaned = content
        for pattern in _NOISE_PATTERNS:
            cleaned = pattern.sub("", cleaned)
        # 折叠多余空行
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    @staticmethod
    def _validate_records(records: list[dict[str, Any]]) -> None:
        """校验采集记录的必填字段 + role 合法性。

        Args:
            records: 标准化后的记录列表。

        Raises:
            ValueError: 缺少必填字段或 role 非法。
        """
        for i, rec in enumerate(records):
            missing = [f for f in _REQUIRED_FIELDS if not rec.get(f)]
            if missing:
                raise ValueError(f"Record {i} missing required fields: {missing}")
            if rec["role"] not in _VALID_ROLES:
                raise ValueError(
                    f"Record {i} has invalid role: {rec['role']!r} "
                    f"(must be one of {sorted(_VALID_ROLES)})"
                )
            if not isinstance(rec["seq"], int) or rec["seq"] < 1:
                raise ValueError(
                    f"Record {i} has invalid seq: {rec['seq']!r} (must be positive int)"
                )

    @staticmethod
    def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
        """将记录列表写入 JSONL 文件。

        Args:
            path: 目标文件路径。
            records: 记录列表。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
