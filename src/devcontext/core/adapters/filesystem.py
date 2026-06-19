"""文件系统适配器 — 轮询模式文件夹扫描."""

import json
from pathlib import Path
from typing import Any

from devcontext.core.adapters.base import BaseAdapter


class FileSystemAdapter(BaseAdapter):
    """文件夹扫描适配器.

    递归遍历指定路径，按 glob 模式匹配文件，
    fingerprint（size+mtime）去重，返回标准化消息.

    Attributes:
        scan_paths: 扫描路径列表.
        file_patterns: 文件类型过滤 glob 模式列表.
    """

    def __init__(
        self,
        scan_paths: list[str],
        file_patterns: list[str] | None = None,
    ):
        """初始化适配器.

        Args:
            scan_paths: 要扫描的目录路径列表.
            file_patterns: glob 文件类型过滤模式.
        """
        self.scan_paths = scan_paths
        self.file_patterns = file_patterns or ["*.jsonl", "*.md", "*.yaml"]
        self._seen_files: set[str] = set()

    @property
    def source_name(self) -> str:
        """数据源标识."""
        return "filesystem"

    def collect(self, source_path=None) -> list[dict[str, Any]]:
        """全量采集：委托给 fetch_full."""
        return self.fetch_full()

    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        """标准化原始记录（文件内容已为 CleanMessage 格式，直接透传）."""
        return raw_record

    def incremental_query(self, watermarks: dict[str, Any]) -> list[dict[str, Any]]:
        """增量查询：按 last_scan_time 扫描新文件.

        Args:
            watermarks: {"last_scan_time": float} 上次扫描时间戳.

        Returns:
            新文件的消息列表.
        """
        last_scan = float(watermarks.get("checkpoint", 0))
        results = []

        for scan_path in self.scan_paths:
            p = Path(scan_path).expanduser().resolve()
            if not p.exists():
                continue
            for filepath in p.rglob("*"):
                if not filepath.is_file():
                    continue
                if not self._match_pattern(filepath):
                    continue

                fp = self._fingerprint(filepath)
                if fp in self._seen_files:
                    continue
                if filepath.stat().st_mtime <= last_scan:
                    continue

                self._seen_files.add(fp)
                try:
                    results.extend(self._read_as_messages(filepath))
                except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                    continue

        return results

    def _match_pattern(self, filepath: Path) -> bool:
        """检查文件路径是否匹配任一 glob 模式."""
        name = filepath.name
        return any(
            filepath.match(p) or name.endswith(p.lstrip("*"))
            for p in self.file_patterns
        )

    def _fingerprint(self, filepath: Path) -> str:
        """生成文件 fingerprint：size + mtime."""
        st = filepath.stat()
        return f"{st.st_size}:{st.st_mtime}"

    def _read_as_messages(self, filepath: Path) -> list[dict[str, Any]]:
        """读取文件内容为消息列表."""
        if filepath.suffix == ".jsonl":
            messages = []
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        msg.setdefault("source", self.source_name)
                        messages.append(msg)
                    except json.JSONDecodeError:
                        continue
            return messages

        content = filepath.read_text(encoding="utf-8")
        return [{
            "session_id": filepath.parent.name or "filesystem",
            "role": "system",
            "content": content,
            "timestamp": filepath.stat().st_mtime,
            "source": self.source_name,
        }]

    def validate_connection(self) -> bool:
        """检查至少一个扫描路径存在."""
        return any(
            Path(p).expanduser().exists()
            for p in self.scan_paths
        )
