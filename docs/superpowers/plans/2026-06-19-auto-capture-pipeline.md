# Auto-Capture + Pipeline Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement automatic conversation capture (Step 0) and full pipeline orchestration (Steps 0→6), turning devContextMemo into a self-running daemon with multi-source polling support.

**Architecture:** Two-layer collector design: `PollingCollector` (strategy) → `CollectorAdapter` (data source). Multiple adapters (OpenCode SQLite, FileSystem, GenericSQLite) plug into the same polling loop. `PipelineService` orchestrates the callback chain: collector → BatchWriter → Steps 2-6.

**Tech Stack:** Python 3.13, asyncio, SQLite (read-only external), Typer CLI, pytest + mock, yaml (PyYAML), pathlib

---

## Task 1: Define CleanMessage Data Contract

**Files:**
- Create: `src/devcontext/core/collectors/__init__.py`
- Create: `src/devcontext/core/collectors/base.py`

- [ ] **Step 1: Create collectors package __init__.py**

```python
# src/devcontext/core/collectors/__init__.py
"""采集策略层 — 缓冲 + 去噪 + 回调，不绑定轮询或 Hook。"""

from devcontext.core.collectors.base import BaseCollector, CleanMessage

__all__ = ["BaseCollector", "CleanMessage"]
```

- [ ] **Step 2: Write failing tests for CleanMessage**

```python
# tests/unit/test_clean_message.py
"""Unit tests for CleanMessage data contract."""

from devcontext.core.collectors.base import CleanMessage


class TestCleanMessage:
    """CleanMessage data contract tests."""

    def test_required_fields(self):
        msg = CleanMessage(
            session_id="abc123",
            role="user",
            content="hello world",
            timestamp=1718809200.0,
            source="opencode",
        )
        assert msg.session_id == "abc123"
        assert msg.role == "user"
        assert msg.content == "hello world"
        assert msg.timestamp == 1718809200.0
        assert msg.source == "opencode"
        assert msg.metadata == {}

    def test_default_metadata(self):
        msg = CleanMessage(
            session_id="s1",
            role="assistant",
            content="response",
            timestamp=1718809200.0,
            source="comate",
        )
        assert msg.metadata == {}

    def test_custom_metadata(self):
        msg = CleanMessage(
            session_id="s1",
            role="tool",
            content="result",
            timestamp=1718809200.0,
            source="opencode",
            metadata={"tools": ["read"], "reasoning": "..."},
        )
        assert msg.metadata["tools"] == ["read"]

    def test_type_annotations(self):
        """Verify dataclass fields are correctly typed."""
        msg = CleanMessage(
            session_id="test",
            role="system",
            content="prompt",
            timestamp=1718809200.0,
            source="filesystem",
            metadata={"extra": 123},
        )
        assert isinstance(msg.session_id, str)
        assert isinstance(msg.role, str)
        assert isinstance(msg.content, str)
        assert isinstance(msg.timestamp, float)
        assert isinstance(msg.source, str)
```

- [ ] **Step 3: Run test to verify failure**

Run: `pytest tests/unit/test_clean_message.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devcontext.core.collectors'`

- [ ] **Step 4: Implement CleanMessage and BaseCollector stub**

```python
# src/devcontext/core/collectors/base.py
"""采集策略基类 + CleanMessage 数据契约。"""

from dataclasses import dataclass, field
from typing import Callable


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

    def __init__(self, adapter):
        self.adapter = adapter
        self.buffer: list[CleanMessage] = []
        self.on_buffer_ready: Callable | None = None

    def _strip_noise(self, content: str) -> str:
        """三层剥壳：移除 system-reminder / relevant-memories / subagent-context。

        Args:
            content: 原始消息正文。

        Returns:
            去噪后的消息正文。
        """
        import re

        patterns = [
            r"<system-reminder>.*?</system-reminder>",
            r"<relevant-memories>.*?</relevant-memories>",
            r"<openviking-context>.*?</openviking-context>",
            r"\[Subagent Context\].*?\[/Subagent Context\]",
        ]
        for pattern in patterns:
            content = re.sub(pattern, "", content, flags=re.DOTALL)
        return content.strip()

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
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/unit/test_clean_message.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add src/devcontext/core/collectors/ tests/unit/test_clean_message.py
git commit -m "feat(collectors): add CleanMessage dataclass and BaseCollector stub"
```

---

## Task 2: Extend BaseAdapter with Polling Methods

**Files:**
- Modify: `src/devcontext/core/adapters/base.py`

- [ ] **Step 1: Write failing test for incremental_query on adapter**

```python
# tests/unit/test_adapter_polling.py
"""Unit tests for polling methods on BaseAdapter."""

from devcontext.core.adapters.base import BaseAdapter


class _PollingAdapter(BaseAdapter):
    """Test adapter implementing incremental_query."""

    @property
    def source_name(self):
        return "test_polling"

    def collect(self, source_path=None):
        return []

    def normalize(self, raw_record):
        return raw_record

    def incremental_query(self, watermarks):
        return [
            {"session_id": "s1", "seq": 3, "role": "user",
             "content": "new message", "timestamp": "2026-06-19T10:00:00Z",
             "source": "test_polling"},
        ]


class _MinimalAdapter(BaseAdapter):
    """Test adapter NOT implementing incremental_query."""

    @property
    def source_name(self):
        return "test_minimal"

    def collect(self, source_path=None):
        return []

    def normalize(self, raw_record):
        return raw_record


class TestAdapterPolling:
    """Tests for polling methods on BaseAdapter."""

    def test_incremental_query_returns_messages(self):
        adapter = _PollingAdapter()
        results = adapter.incremental_query({})
        assert len(results) == 1
        assert results[0]["content"] == "new message"

    def test_fetch_full_defaults_to_incremental(self):
        adapter = _PollingAdapter()
        results = adapter.fetch_full()
        assert len(results) == 1

    def test_incremental_query_not_implemented_by_default(self):
        adapter = _MinimalAdapter()
        try:
            adapter.incremental_query({})
            assert False, "Should have raised NotImplementedError"
        except NotImplementedError:
            pass

    def test_fetch_full_not_implemented_by_default(self):
        adapter = _MinimalAdapter()
        try:
            adapter.fetch_full()
            assert False, "Should have raised NotImplementedError"
        except NotImplementedError:
            pass

    def test_validate_connection_defaults_true(self):
        adapter = _MinimalAdapter()
        assert adapter.validate_connection() is True
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_adapter_polling.py -v`
Expected: FAIL — `AttributeError: 'BaseAdapter' object has no attribute 'incremental_query'`

- [ ] **Step 3: Add polling methods to BaseAdapter**

```python
# In src/devcontext/core/adapters/base.py, add after normalize() method:

    def incremental_query(self, watermarks: dict) -> list[dict[str, Any]]:
        """增量查询：按 watermark 拉取新消息。

        Args:
            watermarks: {source_name: last_checkpoint} 水位线字典。

        Returns:
            新消息列表，每条消息为 dict[str, Any]。

        Raises:
            NotImplementedError: 子类必须实现。
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
```

Note: Add these imports at the top of `base.py`:
```python
from typing import Any
```
(If not already present.)

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_adapter_polling.py -v`
Expected: 5 PASS

- [ ] **Step 5: Verify existing tests still pass**

Run: `pytest tests/unit/ tests/module/ -x --timeout=30 -q`
Expected: All existing tests pass (the new methods have default implementations that don't break anything).

- [ ] **Step 6: Commit**

```bash
git add src/devcontext/core/adapters/base.py tests/unit/test_adapter_polling.py
git commit -m "feat(adapters): add incremental_query/fetch_full/validate_connection to BaseAdapter"
```

---

## Task 3: Add incremental_query to OpenCodeAdapter

**Files:**
- Modify: `src/devcontext/core/adapters/opencode.py`

- [ ] **Step 1: Write failing test for OpenCodeAdapter incremental_query**

Create file `tests/unit/test_opencode_incremental.py`:

```python
# tests/unit/test_opencode_incremental.py
"""Tests for OpenCodeAdapter incremental_query."""

import sqlite3
from pathlib import Path

import pytest

from devcontext.core.adapters.opencode import OpenCodeAdapter


@pytest.fixture
def opencode_db(tmp_path):
    """Create a minimal OpenCode-style SQLite database."""
    db_path = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS conversation (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS message (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            role TEXT,
            created_at TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS part (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            type TEXT,
            content TEXT,
            tool_name TEXT,
            created_at TEXT
        )"""
    )
    conn.commit()
    conn.close()
    yield db_path
    # cleanup: db_path.unlink(missing_ok=True)


class TestOpenCodeAdapterIncremental:
    """Tests for incremental_query on OpenCodeAdapter."""

    def test_incremental_returns_new_messages(self, opencode_db):
        conn = sqlite3.connect(str(opencode_db))
        conn.executemany(
            "INSERT INTO conversation(id, title, created_at) VALUES (?, ?, ?)",
            [("conv1", "Test Session", "2026-06-19T10:00:00Z")],
        )
        conn.executemany(
            "INSERT INTO message(id, conversation_id, role, created_at) VALUES (?, ?, ?, ?)",
            [
                ("msg1", "conv1", "user", "2026-06-19T10:00:00Z"),
                ("msg2", "conv1", "assistant", "2026-06-19T10:00:05Z"),
                ("msg3", "conv1", "user", "2026-06-19T10:00:10Z"),
            ],
        )
        conn.executemany(
            "INSERT INTO part(id, message_id, type, content, tool_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("p1", "msg1", "text", "hello", None, "2026-06-19T10:00:00Z"),
                ("p2", "msg2", "text", "hi there", None, "2026-06-19T10:00:05Z"),
                ("p3", "msg3", "text", "more text", None, "2026-06-19T10:00:10Z"),
            ],
        )
        conn.commit()
        conn.close()

        adapter = OpenCodeAdapter(str(opencode_db))
        results = adapter.incremental_query({"last_message_id": 0})
        assert len(results) == 3

    def test_incremental_respects_watermark(self, opencode_db):
        conn = sqlite3.connect(str(opencode_db))
        conn.executemany(
            "INSERT INTO conversation(id, title, created_at) VALUES (?, ?, ?)",
            [("conv1", "Test", "2026-06-19T10:00:00Z")],
        )
        conn.executemany(
            "INSERT INTO message(id, conversation_id, role, created_at) VALUES (?, ?, ?, ?)",
            [
                ("msg1", "conv1", "user", "2026-06-19T10:00:00Z"),
                ("msg2", "conv1", "assistant", "2026-06-19T10:00:05Z"),
            ],
        )
        conn.executemany(
            "INSERT INTO part(id, message_id, type, content, tool_name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("p1", "msg1", "text", "old", None, "2026-06-19T10:00:00Z"),
                ("p2", "msg2", "text", "new", None, "2026-06-19T10:00:05Z"),
            ],
        )
        conn.commit()
        conn.close()

        adapter = OpenCodeAdapter(str(opencode_db))
        results = adapter.incremental_query({"last_message_id": 1})
        assert len(results) == 1
        assert results[0]["content"] == "new"

    def test_empty_db_returns_empty(self, opencode_db):
        adapter = OpenCodeAdapter(str(opencode_db))
        results = adapter.incremental_query({"last_message_id": 0})
        assert results == []
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_opencode_incremental.py -v`
Expected: FAIL — `NotImplementedError: OpenCodeAdapter does not implement incremental_query`

- [ ] **Step 3: Implement incremental_query on OpenCodeAdapter**

Add to `src/devcontext/core/adapters/opencode.py`, after `normalize` method:

```python
    def incremental_query(self, watermarks: dict) -> list[dict[str, Any]]:
        """增量查询：按 watermark 拉取新消息。

        Args:
            watermarks: {"last_message_id": int} 水位线字典。

        Returns:
            新消息列表。
        """
        import sqlite3

        last_id = int(watermarks.get("last_message_id", 0))
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """SELECT
                m.id,
                m.conversation_id,
                m.role,
                m.created_at,
                GROUP_CONCAT(p.type || ':' || p.content, '\n') AS parts
            FROM message m
            JOIN (
                SELECT DISTINCT conversation_id
                FROM message
                WHERE id > ?
                ORDER BY id
            ) active ON m.conversation_id = active.conversation_id
            LEFT JOIN part p ON p.message_id = m.id
            WHERE m.id > ?
            GROUP BY m.id
            ORDER BY m.id""",
            (last_id, last_id),
        ).fetchall()

        conn.close()

        raw_records = []
        for row in rows:
            record = dict(row)
            record["session_id"] = record.pop("conversation_id")
            record["seq"] = int(record["id"].replace("msg", "").replace("-", ""), 16) % 10000
            record["parts"] = record.get("parts") or ""
            raw_records.append(record)

        return [self.normalize(r) for r in raw_records]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_opencode_incremental.py -v`
Expected: 3 PASS

- [ ] **Step 5: Verify existing OpenCodeAdapter tests still pass**

Run: `pytest tests/integration/test_opencode_adapter.py -v --timeout=30`
(If this test uses a real DB and fails due to missing DB, that's acceptable — skip if needed.)

- [ ] **Step 6: Commit**

```bash
git add src/devcontext/core/adapters/opencode.py tests/unit/test_opencode_incremental.py
git commit -m "feat(opencode): add incremental_query with watermark support"
```

---

## Task 4: Create OpenCodeSQLiteAdapter

**Files:**
- Create: `src/devcontext/core/adapters/opencode_sqlite.py`

Note: This is a thin wrapper that reuses OpenCodeAdapter's incremental_query but conforms explicitly to the CollectorAdapter pattern expected by PollingCollector. It inherits from BaseAdapter.

- [ ] **Step 1: Write test**

```python
# tests/unit/test_opencode_sqlite_adapter.py
"""Tests for OpenCodeSQLiteAdapter."""

import sqlite3

import pytest

from devcontext.core.adapters.opencode_sqlite import OpenCodeSQLiteAdapter


@pytest.fixture
def opencode_db(tmp_path):
    db_path = tmp_path / "opencode.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE conversation(id TEXT PRIMARY KEY, title TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE message(id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE part(id TEXT PRIMARY KEY, message_id TEXT, type TEXT, content TEXT, tool_name TEXT, created_at TEXT)")
    conn.execute("INSERT INTO conversation(id, title, created_at) VALUES ('c1', 'S', '2026-06-19T10:00:00Z')")
    conn.execute("INSERT INTO message(id, conversation_id, role, created_at) VALUES ('msg1', 'c1', 'user', '2026-06-19T10:00:00Z')")
    conn.execute("INSERT INTO part(id, message_id, type, content, tool_name, created_at) VALUES ('p1', 'msg1', 'text', 'hello', NULL, '2026-06-19T10:00:00Z')")
    conn.commit()
    conn.close()
    yield db_path


class TestOpenCodeSQLiteAdapter:
    """OpenCodeSQLiteAdapter tests."""

    def test_source_name(self, opencode_db):
        adapter = OpenCodeSQLiteAdapter(str(opencode_db))
        assert adapter.source_name == "opencode"

    def test_incremental_query(self, opencode_db):
        adapter = OpenCodeSQLiteAdapter(str(opencode_db))
        results = adapter.incremental_query({"last_message_id": 0})
        assert len(results) >= 1
        assert "session_id" in results[0]

    def test_normalize_output(self, opencode_db):
        adapter = OpenCodeSQLiteAdapter(str(opencode_db))
        results = adapter.incremental_query({"last_message_id": 0})
        normalized = adapter.normalize(results[0])
        assert "session_id" in normalized
        assert "role" in normalized
        assert "source" in normalized
```

- [ ] **Step 2: Run test verifying failure**

Run: `pytest tests/unit/test_opencode_sqlite_adapter.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement OpenCodeSQLiteAdapter**

```python
# src/devcontext/core/adapters/opencode_sqlite.py
"""OpenCode SQLite 适配器 — 轮询模式增量采集。"""

from typing import Any

from devcontext.core.adapters.base import BaseAdapter


class OpenCodeSQLiteAdapter(BaseAdapter):
    """OpenCode SQLite 数据源适配器。

    通过只读 SQLite 连接增量拉取 OpenCode 对话记录。

    Attributes:
        db_path: OpenCode SQLite 数据库路径。
        source_name: 固定为 "opencode"。
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    @property
    def source_name(self) -> str:
        return "opencode"

    def collect(self, source_path=None) -> list[dict[str, Any]]:
        """全量采集（委托给 fetch_full）。"""
        return self.fetch_full()

    def normalize(self, raw_record: dict) -> dict[str, Any]:
        """标准化原始记录。

        Args:
            raw_record: 包含 session_id, role, content, timestamp, source 的字典。

        Returns:
            标准化字典。
        """
        return {
            "session_id": raw_record.get("session_id", ""),
            "role": raw_record.get("role", "user"),
            "content": raw_record.get("content", ""),
            "timestamp": raw_record.get("timestamp", "1970-01-01T00:00:00Z"),
            "source": raw_record.get("source", self.source_name),
        }

    def incremental_query(self, watermarks: dict) -> list[dict[str, Any]]:
        """增量查询：从 OpenCode SQLite 拉取新消息。

        Args:
            watermarks: {"last_message_id": int} 水位线。

        Returns:
            标准化后的消息列表。
        """
        import sqlite3

        last_id = int(watermarks.get("last_message_id", 0))
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """SELECT
                m.id,
                m.conversation_id AS session_id,
                m.role,
                m.created_at AS timestamp,
                GROUP_CONCAT(p.type || ':' || COALESCE(p.content, ''), '\n') AS parts
            FROM message m
            JOIN (SELECT DISTINCT conversation_id FROM message WHERE id > ?) a
              ON m.conversation_id = a.conversation_id
            LEFT JOIN part p ON p.message_id = m.id
            WHERE m.id > ?
            GROUP BY m.id
            ORDER BY m.id""",
            (last_id, last_id),
        ).fetchall()
        conn.close()

        results = []
        for row in rows:
            record = dict(row)
            record["content"] = record.get("parts") or ""
            record["source"] = self.source_name
            results.append(self.normalize(record))

        return results
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_opencode_sqlite_adapter.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/devcontext/core/adapters/opencode_sqlite.py tests/unit/test_opencode_sqlite_adapter.py
git commit -m "feat(adapters): add OpenCodeSQLiteAdapter for polling mode"
```

---

## Task 5: Create FileSystemAdapter

**Files:**
- Create: `src/devcontext/core/adapters/filesystem.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_filesystem_adapter.py
"""Tests for FileSystemAdapter."""

import json
import time
from pathlib import Path

import pytest

from devcontext.core.adapters.filesystem import FileSystemAdapter


@pytest.fixture
def scan_dir(tmp_path):
    """Create a directory with test files."""
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    sub = scan_dir / "subdir"
    sub.mkdir()

    # Write some .jsonl files
    messages = [
        {"session_id": "s1", "role": "user", "content": "hello",
         "timestamp": "2026-06-19T10:00:00Z", "source": "filesystem"},
        {"session_id": "s1", "role": "assistant", "content": "hi",
         "timestamp": "2026-06-19T10:00:05Z", "source": "filesystem"},
    ]
    f1 = scan_dir / "session_s1.jsonl"
    with open(f1, "w") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")

    # Write a .md file that should be skipped if not in patterns
    f2 = scan_dir / "README.md"
    f2.write_text("# README")

    yield scan_dir


class TestFileSystemAdapter:
    """FileSystemAdapter tests."""

    def test_source_name(self):
        adapter = FileSystemAdapter([], ["*.jsonl"])
        assert adapter.source_name == "filesystem"

    def test_scans_jsonl_files(self, scan_dir):
        adapter = FileSystemAdapter([str(scan_dir)], ["*.jsonl"])
        results = adapter.incremental_query({"last_scan_time": 0})
        assert len(results) >= 2

    def test_fingerprint_dedup(self, scan_dir):
        adapter = FileSystemAdapter([str(scan_dir)], ["*.jsonl"])
        first = adapter.incremental_query({"last_scan_time": 0})
        second = adapter.incremental_query({"last_scan_time": time.time() + 60})
        assert len(first) >= 2
        assert len(second) == 0  # No new files modified after current time

    def test_mtime_filtering(self, scan_dir):
        adapter = FileSystemAdapter([str(scan_dir)], ["*.jsonl"])
        results = adapter.incremental_query({"last_scan_time": time.time() + 3600})
        assert len(results) == 0  # All files older than watermark

    def test_normalize_passthrough(self):
        adapter = FileSystemAdapter([], ["*.jsonl"])
        raw = {"session_id": "s1", "role": "user", "content": "hello",
               "timestamp": "2026-06-19T10:00:00Z", "source": "filesystem"}
        result = adapter.normalize(raw)
        assert result == raw
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_filesystem_adapter.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement FileSystemAdapter**

```python
# src/devcontext/core/adapters/filesystem.py
"""文件系统适配器 — 轮询模式文件夹扫描。"""

import json
from pathlib import Path
from typing import Any


from devcontext.core.adapters.base import BaseAdapter


class FileSystemAdapter(BaseAdapter):
    """文件夹扫描适配器。

    递归遍历指定路径，按 glob 模式匹配文件，
    fingerprint（size+mtime）去重，返回标准化消息。

    Attributes:
        scan_paths: 扫描路径列表。
        file_patterns: 文件类型过滤 glob 模式列表。
        seen_files: 已扫描文件的 fingerprint 集合。
    """

    def __init__(self, scan_paths: list[str], file_patterns: list[str] | None = None):
        self.scan_paths = scan_paths
        self.file_patterns = file_patterns or ["*.jsonl", "*.md", "*.yaml"]
        self._seen_files: set[str] = set()

    @property
    def source_name(self) -> str:
        return "filesystem"

    def collect(self, source_path=None) -> list[dict[str, Any]]:
        """全量采集。"""
        return self.fetch_full()

    def normalize(self, raw_record: dict) -> dict[str, Any]:
        """标准化原始记录（文件内容已为 CleanMessage 格式，直接透传）。"""
        return raw_record

    def incremental_query(self, watermarks: dict) -> list[dict[str, Any]]:
        """增量查询：按 last_scan_time 扫描新文件。

        Args:
            watermarks: {"last_scan_time": float} 上次扫描时间戳。

        Returns:
            新文件的消息列表。
        """
        last_scan = float(watermarks.get("last_scan_time", 0))
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
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

        return results

    def _match_pattern(self, filepath: Path) -> bool:
        """检查文件路径是否匹配任一 glob 模式。"""
        name = filepath.name
        return any(filepath.match(p) or name.endswith(p.lstrip("*")) for p in self.file_patterns)

    def _fingerprint(self, filepath: Path) -> str:
        """生成文件 fingerprint：size + mtime。"""
        st = filepath.stat()
        return f"{st.st_size}:{st.st_mtime}"

    def _read_as_messages(self, filepath: Path) -> list[dict[str, Any]]:
        """读取文件内容为消息列表。

        JSONL 文件逐行解析，Markdown/YAML 作为单条消息。
        """
        if filepath.suffix == ".jsonl":
            messages = []
            with open(filepath, "r", encoding="utf-8") as f:
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

        # Non-JSONL: read whole file as single message
        content = filepath.read_text(encoding="utf-8")
        return [{
            "session_id": filepath.parent.name or "filesystem",
            "role": "system",
            "content": content,
            "timestamp": filepath.stat().st_mtime,
            "source": self.source_name,
            "filename": filepath.name,
        }]

    def validate_connection(self) -> bool:
        """检查至少一个扫描路径存在。"""
        return any(Path(p).expanduser().exists() for p in self.scan_paths)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_filesystem_adapter.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/devcontext/core/adapters/filesystem.py tests/unit/test_filesystem_adapter.py
git commit -m "feat(adapters): add FileSystemAdapter for folder scanning"
```

---

## Task 6: Create GenericSQLiteAdapter

**Files:**
- Create: `src/devcontext/core/adapters/generic_sqlite.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_generic_sqlite_adapter.py
"""Tests for GenericSQLiteAdapter."""

import sqlite3

import pytest

from devcontext.core.adapters.generic_sqlite import GenericSQLiteAdapter


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE msgs (id INTEGER PRIMARY KEY, content TEXT, role TEXT)")
    conn.execute("INSERT INTO msgs (id, content, role) VALUES (1, 'hello', 'user')")
    conn.execute("INSERT INTO msgs (id, content, role) VALUES (2, 'world', 'assistant')")
    conn.commit()
    conn.close()
    return str(db_path)


class TestGenericSQLiteAdapter:
    """GenericSQLiteAdapter tests."""

    def test_source_name(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="cursor",
            db_path=test_db,
            query_template="SELECT id, content, role FROM msgs WHERE id > ?",
            id_column="id",
        )
        assert adapter.source_name == "cursor"

    def test_incremental_query(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="cursor",
            db_path=test_db,
            query_template="SELECT id, content, role FROM msgs WHERE id > ?",
            id_column="id",
        )
        results = adapter.incremental_query({"cursor_last_id": 0})
        assert len(results) == 2

    def test_incremental_respects_watermark(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="cursor",
            db_path=test_db,
            query_template="SELECT id, content, role FROM msgs WHERE id > ?",
            id_column="id",
        )
        results = adapter.incremental_query({"cursor_last_id": 1})
        assert len(results) == 1
        assert results[0]["content"] == "world"

    def test_normalize(self, test_db):
        adapter = GenericSQLiteAdapter(
            source_name="comate",
            db_path=test_db,
            query_template="SELECT id, content, role FROM msgs WHERE id > ?",
            id_column="id",
        )
        raw = {"id": 1, "content": "hello", "role": "user"}
        result = adapter.normalize(raw)
        assert result["source"] == "comate"
        assert result["content"] == "hello"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_generic_sqlite_adapter.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement GenericSQLiteAdapter**

```python
# src/devcontext/core/adapters/generic_sqlite.py
"""通用 SQLite 适配器 — 通过配置接入任意 AI 工具数据库。"""

import sqlite3
from typing import Any

from devcontext.core.adapters.base import BaseAdapter


class GenericSQLiteAdapter(BaseAdapter):
    """通用 SQLite 数据源适配器。

    通过 source_name + db_path + query_template 配置即可接入
    Cursor、Comate 等工具的 SQLite 数据库，无需写新适配器。

    Attributes:
        source_name: 数据源标识（如 "cursor", "comate"）。
        db_path: SQLite 数据库路径。
        query_template: 增量查询 SQL 模板（含 ? 占位符）。
        id_column: 水位线字段名（默认 "id"）。
    """

    def __init__(
        self,
        source_name: str,
        db_path: str,
        query_template: str,
        id_column: str = "id",
    ):
        self._source_name = source_name
        self.db_path = db_path
        self.query_template = query_template
        self.id_column = id_column

    @property
    def source_name(self) -> str:
        return self._source_name

    def collect(self, source_path=None) -> list[dict[str, Any]]:
        """全量采集。"""
        return self.fetch_full()

    def normalize(self, raw_record: dict) -> dict[str, Any]:
        """标准化原始记录。

        Args:
            raw_record: 数据库行 dict。

        Returns:
            标准化字典。
        """
        return {
            "session_id": raw_record.get("conversation_id", raw_record.get("session_id", "")),
            "role": raw_record.get("role", "user"),
            "content": raw_record.get("content", ""),
            "timestamp": raw_record.get("created_at", raw_record.get("timestamp", "1970-01-01T00:00:00Z")),
            "source": self.source_name,
            "raw": {k: v for k, v in raw_record.items() if k not in {"session_id", "role", "content", "created_at", "timestamp"}},
        }

    def incremental_query(self, watermarks: dict) -> list[dict[str, Any]]:
        """增量查询：按 watermark 拉取新记录。

        Args:
            watermarks: {source_name_last_id: checkpoint} 水位线。

        Returns:
            标准化后的记录列表。
        """
        watermark_key = f"{self.source_name}_last_id"
        last_id = watermarks.get(watermark_key, 0)

        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(self.query_template, (last_id,)).fetchall()
        conn.close()

        return [self.normalize(dict(row)) for row in rows]

    def validate_connection(self) -> bool:
        """检查数据库文件是否存在。"""
        return Path(self.db_path).expanduser().exists()
```

Add the import at the top:
```python
from pathlib import Path
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_generic_sqlite_adapter.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/devcontext/core/adapters/generic_sqlite.py tests/unit/test_generic_sqlite_adapter.py
git commit -m "feat(adapters): add GenericSQLiteAdapter for config-based SQLite sources"
```

---

## Task 7: Implement PollingCollector

**Files:**
- Modify: `src/devcontext/core/collectors/base.py` (BaseCollector already created in Task 1)
- Create: `src/devcontext/core/collectors/polling.py`

- [ ] **Step 1: Update BaseCollector (add type annotation fix)**

The `_strip_noise` method in Task 1 uses `import re` inside the method. Move the import to the top of the file:

```python
# src/devcontext/core/collectors/base.py — add at top:
import re
```

And update `_strip_noise` to use the module-level import:

```python
    def _strip_noise(self, content: str) -> str:
        """三层剥壳：移除 system-reminder / relevant-memories / subagent-context。"""
        patterns = [
            r"<system-reminder>.*?</system-reminder>",
            r"<relevant-memories>.*?</relevant-memories>",
            r"<openviking-context>.*?</openviking-context>",
            r"\[Subagent Context\].*?\[/Subagent Context\]",
        ]
        for pattern in patterns:
            content = re.sub(pattern, "", content, flags=re.DOTALL)
        return content.strip()
```

- [ ] **Step 2: Write failing test for PollingCollector**

```python
# tests/unit/test_polling_collector.py
"""Unit tests for PollingCollector."""

import time
from pathlib import Path

import pytest

from devcontext.core.collectors.base import CleanMessage
from devcontext.core.collectors.polling import PollingCollector
from devcontext.core.adapters.base import BaseAdapter


class _MockPollingAdapter(BaseAdapter):
    """Mock adapter returning controlled messages."""

    def __init__(self):
        self._messages = []
        self._call_count = 0

    @property
    def source_name(self):
        return "mock"

    def collect(self, source_path=None):
        return list(self._messages)

    def normalize(self, raw_record):
        return raw_record

    def incremental_query(self, watermarks):
        self._call_count += 1
        batch = self._messages[:]
        self._messages.clear()
        return batch

    def seed(self, messages):
        self._messages = list(messages)


class TestPollingCollector:
    """PollingCollector tests."""

    def test_collects_from_adapter(self):
        adapter = _MockPollingAdapter()
        adapter.seed([
            {"session_id": "s1", "role": "user", "content": "hello",
             "timestamp": time.time(), "source": "mock"},
        ])
        collector = PollingCollector(adapter, poll_interval_ms=100)

        # Single poll cycle (not the full loop)
        results = collector._poll_once()
        assert len(results) == 1
        assert results[0].content == "hello"

    def test_buffer_flush_on_limit(self):
        adapter = _MockPollingAdapter()
        collector = PollingCollector(adapter, poll_interval_ms=100, max_buffer_messages=2)
        collector.buffer = [
            CleanMessage(session_id="s1", role="user", content="x" * 100,
                         timestamp=time.time(), source="mock"),
            CleanMessage(session_id="s1", role="assistant", content="y" * 100,
                         timestamp=time.time(), source="mock"),
        ]
        assert collector._check_buffer() is True

    def test_buffer_no_flush_below_limit(self):
        adapter = _MockPollingAdapter()
        collector = PollingCollector(adapter, poll_interval_ms=100, max_buffer_messages=200)
        collector.buffer = [
            CleanMessage(session_id="s1", role="user", content="short",
                         timestamp=time.time(), source="mock"),
        ]
        assert collector._check_buffer() is False

    def test_strip_noise_removes_system_reminder(self):
        adapter = _MockPollingAdapter()
        collector = PollingCollector(adapter)
        cleaned = collector._strip_noise(
            "hello\n<system-reminder>ignore this</system-reminder>\nworld"
        )
        assert "system-reminder" not in cleaned
        assert "hello" in cleaned
        assert "world" in cleaned

    def test_callback_invoked(self):
        callback_called = []

        def cb(messages):
            callback_called.append(len(messages))

        adapter = _MockPollingAdapter()
        collector = PollingCollector(adapter)
        collector.on_buffer_ready = cb
        collector.buffer = [
            CleanMessage(session_id="s1", role="user", content="msg",
                         timestamp=time.time(), source="mock"),
        ]
        collector._emit(list(collector.buffer))
        assert len(callback_called) == 1
        assert callback_called[0] == 1

    def test_watermark_updated_after_poll(self):
        adapter = _MockPollingAdapter()
        adapter.seed([
            {"id": 5, "session_id": "s1", "role": "user", "content": "hello",
             "timestamp": time.time(), "source": "mock"},
        ])
        collector = PollingCollector(adapter)
        collector._poll_once()
        assert collector.watermarks.get("mock") == 5
```

- [ ] **Step 3: Run test to verify failure**

Run: `pytest tests/unit/test_polling_collector.py -v`
Expected: FAIL — ModuleNotFoundError for `polling` module

- [ ] **Step 4: Implement PollingCollector**

```python
# src/devcontext/core/collectors/polling.py
"""轮询采集策略 — 定时轮询线程 + Watermark 管理。"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Callable

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
        """持久化水位线。

        Args:
            source_name: 数据源名称。
            watermarks: 水位线字典。
            filepath: 水位线文件路径。
        """
        path = filepath or DEFAULT_WATERMARK_FILE
        path.parent.mkdir(parents=True, exist_ok=True)

        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

        existing[source_name] = watermarks
        path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


class PollingCollector(BaseCollector):
    """定时轮询采集器 — Phase 1 唯一采集策略。

    Attributes:
        adapter: 数据源适配器（CollectorAdapter 接口）。
        poll_interval_ms: 轮询间隔（毫秒）。
        watermarks: 水位线字典 {adapter.source_name: checkpoint}。
        max_buffer_messages: 缓冲区最大消息数。
        max_buffer_tokens: 缓冲区最大 token 数。
    """

    def __init__(
        self,
        adapter,
        poll_interval_ms: int = 500,
        max_buffer_messages: int = 200,
        max_buffer_tokens: int = 6000,
    ):
        super().__init__(adapter)
        self.poll_interval_ms = poll_interval_ms
        self.max_buffer_messages = max_buffer_messages
        self.max_buffer_tokens = max_buffer_tokens
        self.watermarks: dict = WatermarkStore.load().get(adapter.source_name, {})
        self._running = False
        self._task: asyncio.Task | None = None

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
                content=self._strip_noise(normalized.get("content", "")),
                timestamp=self._parse_timestamp(normalized.get("timestamp", 0)),
                source=normalized.get("source", self.adapter.source_name),
                metadata={k: v for k, v in normalized.items()
                          if k not in {"session_id", "role", "content", "timestamp", "source"}},
            )
            results.append(clean)

        self.buffer.extend(results)
        self._update_watermarks(raw_messages)
        return results

    def _update_watermarks(self, raw_messages: list[dict]):
        """更新水位线：取最后一条消息的 ID 或时间戳。"""
        if not raw_messages:
            return
        last = raw_messages[-1]
        new_watermark = last.get("id") or str(time.time())
        self.watermarks[self.adapter.source_name] = new_watermark

    def _parse_timestamp(self, ts) -> float:
        """将时间戳转换为 float（Unix 时间）。"""
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, str):
            try:
                from datetime import datetime
                return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
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
            await asyncio.to_thread(self._poll_once)

            if self._check_buffer(
                max_messages=self.max_buffer_messages,
                max_tokens=self.max_buffer_tokens,
            ):
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

        # Flush remaining buffer
        if self.buffer:
            self._emit(self._flush_buffer())

        # Persist watermarks
        WatermarkStore.save(self.adapter.source_name, dict(self.watermarks))
```

- [ ] **Step 5: Update collectors __init__.py**

```python
# src/devcontext/core/collectors/__init__.py
"""采集策略层 — 缓冲 + 去噪 + 回调，不绑定轮询或 Hook。"""

from devcontext.core.collectors.base import BaseCollector, CleanMessage
from devcontext.core.collectors.polling import PollingCollector, WatermarkStore

__all__ = ["BaseCollector", "CleanMessage", "PollingCollector", "WatermarkStore"]
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/unit/test_polling_collector.py -v`
Expected: 6 PASS

- [ ] **Step 7: Commit**

```bash
git add src/devcontext/core/collectors/ tests/unit/test_polling_collector.py
git commit -m "feat(collectors): add PollingCollector with async poll loop and WatermarkStore"
```

---

## Task 8: Add BatchWriter to batcher.py

**Files:**
- Modify: `src/devcontext/core/pipeline/batcher.py`

- [ ] **Step 1: Write failing test for BatchWriter**

```python
# tests/unit/test_batch_writer.py
"""Tests for BatchWriter callback-mode batch writing."""

import json
import time
from pathlib import Path

import pytest
import yaml

from devcontext.core.collectors.base import CleanMessage
from devcontext.core.pipeline.batcher import BatchWriter


@pytest.fixture
def staging_dir(tmp_path):
    d = tmp_path / "staging"
    d.mkdir()
    return d


def make_messages(session_id, count, base_content="msg"):
    """Create CleanMessage list."""
    return [
        CleanMessage(
            session_id=session_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"{base_content} {i}",
            timestamp=time.time() + i,
            source="opencode",
        )
        for i in range(count)
    ]


class TestBatchWriter:
    """BatchWriter tests."""

    def test_writes_batch_when_token_threshold_reached(self, staging_dir):
        writer = BatchWriter(staging_dir, token_threshold=100)
        messages = make_messages("s1", 5, "x" * 100)  # ~50 tokens each, 5 * 50 = 250 > 100

        batch_path = writer.on_messages(messages, "s1")
        assert batch_path is not None
        assert batch_path.exists()
        assert (batch_path / "messages.jsonl").exists()
        assert (batch_path / "_meta.yaml").exists()

    def test_skips_below_threshold(self, staging_dir):
        writer = BatchWriter(staging_dir, token_threshold=6000)
        messages = make_messages("s1", 2, "hello")  # small token count

        batch_path = writer.on_messages(messages, "s1")
        assert batch_path is None  # Buffered, not written yet

    def test_meta_yaml_format(self, staging_dir):
        writer = BatchWriter(staging_dir, token_threshold=100)
        messages = make_messages("s2", 5, "x" * 100)

        batch_path = writer.on_messages(messages, "s2")
        meta = yaml.safe_load((batch_path / "_meta.yaml").read_text())

        assert meta["session_id"] == "s2"
        assert meta["source"] == "opencode"
        assert meta["message_count"] == 5
        assert meta["status"] == "ready"
        assert "batch_created" in meta
        assert "token_count" in meta

    def test_messages_jsonl_content(self, staging_dir):
        writer = BatchWriter(staging_dir, token_threshold=100)
        messages = make_messages("s3", 2, "hello world")

        batch_path = writer.on_messages(messages, "s3")
        with open(batch_path / "messages.jsonl") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 2
        assert lines[0]["session_id"] == "s3"
        assert lines[0]["content"] == "hello world 0"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_batch_writer.py -v`
Expected: FAIL — `ImportError: cannot import name 'BatchWriter'`

- [ ] **Step 3: Implement BatchWriter**

Add to `src/devcontext/core/pipeline/batcher.py` (at the end of the file):

```python
class BatchWriter:
    """回调模式攒批器 — 从内存 Buffer 直接接收消息并落盘。

    与现有 Batcher（文件扫描模式）互补：
    - BatchWriter：daemon 自动采集主路径（回调驱动）
    - Batcher：CLI 手动触发 / 历史数据迁移（目录扫描）

    Attributes:
        staging_dir: 批次输出目录。
        token_threshold: token 阈值（默认 6000）。
    """

    def __init__(
        self,
        staging_dir: str | Path,
        token_threshold: int = 6000,
        max_age_minutes: int = 30,
    ):
        self.staging_dir = Path(staging_dir)
        self.token_threshold = token_threshold
        self.max_age_minutes = max_age_minutes
        self._buffers: dict[str, dict] = {}
        self.on_batch_ready: Callable | None = None

    def _count_tokens(self, text: str) -> int:
        """简化 token 估算：len(text) // 2。"""
        return len(text) // 2

    def on_messages(
        self,
        messages: list[CleanMessage],
        session_id: str,
    ) -> Path | None:
        """接收消息并攒批。

        Args:
            messages: CleanMessage 列表。
            session_id: 会话 ID。

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

        if buf["token_count"] >= self.token_threshold:
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
                f.write(json.dumps({
                    "session_id": msg.session_id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "source": msg.source,
                    **{k: v for k, v in msg.metadata.items()},
                }, ensure_ascii=False) + "\n")

        # Write _meta.yaml
        meta = {
            "session_id": session_id,
            "source": buf["source"],
            "batch_created": time.time(),
            "message_count": len(buf["messages"]),
            "token_count": buf["token_count"],
            "message_file": "messages.jsonl",
            "trigger_reason": "token_threshold" if buf["token_count"] >= self.token_threshold else "message_count",
            "status": "ready",
        }
        meta_path = batch_dir / "_meta.yaml"
        with open(meta_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(meta, f, allow_unicode=True, sort_keys=False)

        # Trigger downstream callback
        if self.on_batch_ready:
            self.on_batch_ready(batch_dir)

        return batch_dir
```

Add imports at the top of batcher.py (merge with existing imports):
```python
import json
import time
from pathlib import Path
from typing import Callable

import yaml

from devcontext.core.collectors.base import CleanMessage
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_batch_writer.py -v`
Expected: 4 PASS

- [ ] **Step 5: Verify existing Batcher tests still pass**

Run: `pytest tests/module/test_step1_batcher.py -v`
Expected: All existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/devcontext/core/pipeline/batcher.py tests/unit/test_batch_writer.py
git commit -m "feat(batcher): add BatchWriter callback-mode batch writer"
```

---

## Task 9: Implement PipelineService

**Files:**
- Modify: `src/devcontext/services/pipeline.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_pipeline_service.py
"""Unit tests for PipelineService orchestration."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from devcontext.services.pipeline import PipelineService
from devcontext.core.collectors.base import CleanMessage


@pytest.fixture
def mock_collector():
    c = MagicMock()
    c.adapter.source_name = "mock"
    c.on_buffer_ready = None
    c.start = MagicMock()
    c.stop = MagicMock()
    return c


@pytest.fixture
def mock_batch_writer():
    w = MagicMock()
    w.on_batch_ready = None
    w.on_messages = MagicMock(return_value=None)
    return w


class TestPipelineService:
    """PipelineService tests."""

    def test_registers_callback_chain(self, mock_collector, mock_batch_writer):
        pipeline = PipelineService(
            collectors=[mock_collector],
            batch_writer=mock_batch_writer,
        )
        # Collector's on_buffer_ready should point to batch_writer.on_messages
        assert mock_collector.on_buffer_ready is not None

    def test_start_starts_all_collectors(self, mock_collector, mock_batch_writer):
        pipeline = PipelineService(
            collectors=[mock_collector],
            batch_writer=mock_batch_writer,
        )
        pipeline._start_collectors()
        mock_collector.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_stops_all_collectors(self, mock_collector, mock_batch_writer):
        pipeline = PipelineService(
            collectors=[mock_collector],
            batch_writer=mock_batch_writer,
        )
        pipeline._stop_collectors()
        mock_collector.stop.assert_called_once()
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unit/test_pipeline_service.py -v`
Expected: FAIL — (stub has no PipelineService class)

- [ ] **Step 3: Implement PipelineService**

```python
# src/devcontext/services/pipeline.py
"""流水线编排服务 — 多 collector 调度 + 回调链 + 生命周期管理。"""

import asyncio
import logging
from pathlib import Path

from devcontext.core.collectors.polling import PollingCollector

logger = logging.getLogger(__name__)


class PipelineService:
    """流水线编排服务。

    持有所有 Step 实例，注册回调链，管理 start/stop 生命周期。

    Attributes:
        collectors: 采集器列表（≥1 个）。
        batch_writer: 攒批器（BatchWriter）。
        extractor: Step 2a 知识提炼器。
        entity_extractor: Step 2b 实体提取器。
        validator: Step 3 验证器。
        deduplicator: Step 4 去重器。
        writer: Step 5 写入器。
        consolidator: Step 6 巩固器。
    """

    def __init__(
        self,
        collectors: list,
        batch_writer,
        extractor=None,
        entity_extractor=None,
        validator=None,
        deduplicator=None,
        writer=None,
        consolidator=None,
    ):
        self.collectors = collectors
        self.batch_writer = batch_writer
        self.extractor = extractor
        self.entity_extractor = entity_extractor
        self.validator = validator
        self.deduplicator = deduplicator
        self.writer = writer
        self.consolidator = consolidator

        self._register_callbacks()
        self._running = False

    def _register_callbacks(self):
        """注册回调链：Step 0 → Step 1 → Step 2-6。"""
        for collector in self.collectors:
            collector.on_buffer_ready = self._on_messages

        self.batch_writer.on_batch_ready = self._on_batch_ready

    def _on_messages(self, messages: list) -> None:
        """Step 0 缓冲区满回调 → Step 1 攒批。

        Args:
            messages: CleanMessage 列表。
        """
        if not messages:
            return

        session_id = messages[0].session_id
        batch_path = self.batch_writer.on_messages(messages, session_id)
        if batch_path:
            logger.info("batch flushed: %s (%d messages)", batch_path, len(messages))

    def _on_batch_ready(self, batch_path: Path) -> None:
        """Step 1 批次就绪回调 → Step 2-6 顺序执行。

        Args:
            batch_path: 批次目录路径。
        """
        logger.info("processing batch: %s", batch_path)

        try:
            # Step 2a: Extract
            if self.extractor:
                summary_path = self.extractor.process(batch_path)
                logger.info("extraction done: %s", summary_path)

            # Step 2b: Entity extraction
            if self.entity_extractor:
                knowledge_path = self.entity_extractor.process(summary_path)
                logger.info("entity extraction done: %s", knowledge_path)

            # Step 3: Validate
            if self.validator:
                validated_path = self.validator.process(knowledge_path)
                logger.info("validation done: %s", validated_path)

            # Step 4: Dedup
            if self.deduplicator:
                deduped_path = self.deduplicator.process(knowledge_path)
                logger.info("dedup done: %s", deduped_path)

            # Step 5: Write
            if self.writer:
                results = self.writer.process(knowledge_path)
                logger.info("write done: %d items", len(results))

            # Step 6: Consolidate
            if self.consolidator:
                report = self.consolidator.process()
                logger.info("consolidation done: promoted=%d pruned=%d",
                            report.promoted_count, report.pruned_count)

        except Exception:
            logger.error("pipeline failed for batch: %s", batch_path, exc_info=True)

    def _start_collectors(self):
        """启动所有采集器。"""
        for collector in self.collectors:
            if hasattr(collector, 'start'):
                collector.start()

    def _stop_collectors(self):
        """停止所有采集器。"""
        for collector in self.collectors:
            if hasattr(collector, 'stop'):
                collector.stop()

    async def start(self):
        """启动编排服务（后台运行）。"""
        self._running = True
        self._start_collectors()
        logger.info("PipelineService started with %d collector(s)", len(self.collectors))

    async def stop(self):
        """停止编排服务。"""
        self._running = False
        self._stop_collectors()
        logger.info("PipelineService stopped")

    def capture(self, *, dry_run: bool = False) -> dict:
        """手动触发一次完整采集（调试/兜底用）。

        Args:
            dry_run: 预览模式，不实际写入。

        Returns:
            采集结果摘要。
        """
        results = {
            "dry_run": dry_run,
            "collectors": {},
        }

        for collector in self.collectors:
            source = collector.adapter.source_name
            try:
                if isinstance(collector, PollingCollector):
                    messages = collector._poll_once()
                    results["collectors"][source] = {
                        "messages_found": len(messages),
                        "watermarks": dict(collector.watermarks),
                    }
            except Exception as e:
                results["collectors"][source] = {"error": str(e)}

        return results

```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unit/test_pipeline_service.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/devcontext/services/pipeline.py tests/unit/test_pipeline_service.py
git commit -m "feat(services): implement PipelineService with callback chain and multi-collector support"
```

---

## Task 10: Implement serve() in main.py

**Files:**
- Modify: `src/devcontext/main.py`

- [ ] **Step 1: Implement serve()**

```python
# src/devcontext/main.py
"""devContextMemo — 码上记忆 daemon 入口。

启动后自动采集对话知识并串联全链路流水线（Steps 0-6）。
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def serve():
    """启动 devContextMemo daemon。

    创建采集器 + 攒批器 + 流水线编排，并发运行采集和 MCP 服务。
    """
    from devcontext.config import settings
    from devcontext.core.collectors.polling import PollingCollector
    from devcontext.core.adapters.opencode_sqlite import OpenCodeSQLiteAdapter
    from devcontext.core.adapters.filesystem import FileSystemAdapter
    from devcontext.core.pipeline.batcher import BatchWriter
    from devcontext.services.pipeline import PipelineService

    # 创建采集器（多个数据源可同时运行）
    collectors = []

    # OpenCode SQLite 适配器
    if settings.opencode_db_path:
        collectors.append(
            PollingCollector(
                adapter=OpenCodeSQLiteAdapter(
                    db_path=settings.opencode_db_path,
                ),
                poll_interval_ms=settings.poll_interval_ms,
                max_buffer_messages=settings.buffer_max_messages,
                max_buffer_tokens=settings.buffer_max_tokens,
            )
        )

    # 文件系统适配器
    if settings.filesystem_scan_paths:
        collectors.append(
            PollingCollector(
                adapter=FileSystemAdapter(
                    scan_paths=settings.filesystem_scan_paths,
                    file_patterns=settings.filesystem_file_patterns,
                ),
                poll_interval_ms=settings.poll_interval_ms,
                max_buffer_messages=settings.buffer_max_messages,
                max_buffer_tokens=settings.buffer_max_tokens,
            )
        )

    if not collectors:
        logger.warning("no data sources configured, daemon will idle")
        return

    # 创建攒批器
    batch_writer = BatchWriter(
        staging_dir=settings.staging_dir,
        token_threshold=settings.batch_token_threshold,
        max_age_minutes=settings.batch_max_age_minutes,
    )

    # 创建编排服务
    pipeline = PipelineService(
        collectors=collectors,
        batch_writer=batch_writer,
        # Steps 2-6 are optional for serve() — they run on batch_ready callback
        # Add them when full pipeline integration is needed:
        # extractor=Extractor(...),
        # entity_extractor=EntityExtractor(...),
        # validator=Validator(...),
        # deduplicator=Deduplicator(...),
        # writer=Writer(...),
        # consolidator=Consolidator(...),
    )

    # 并发运行：采集 + MCP 服务（如果配置了）
    async def _run():
        tasks = [pipeline.start()]
        # MCP server can be added later:
        # from devcontext.mcp.server import MCPServer
        # mcp = MCPServer(...)
        # tasks.append(mcp.serve())
        await asyncio.gather(*tasks)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("shutting down...")
        asyncio.run(pipeline.stop())


if __name__ == "__main__":
    serve()
```

- [ ] **Step 2: Verify the module imports correctly**

Run: `python -c "from devcontext.main import serve; print('serve imported OK')"`
Expected: `serve imported OK`

- [ ] **Step 3: Commit**

```bash
git add src/devcontext/main.py
git commit -m "feat(main): implement serve() daemon entry with multi-source collector setup"
```

---

## Task 11: Extend config.py Settings

**Files:**
- Modify: `src/devcontext/config.py`

- [ ] **Step 1: Add new config fields**

In `src/devcontext/config.py`, add to `Settings` class:

```python
    # 采集配置
    opencode_db_path: str = "~/.opencode/opencode.db"
    poll_interval_ms: int = 500
    buffer_max_messages: int = 200
    buffer_max_tokens: int = 6000

    # 攒批配置
    batch_token_threshold: int = 6000
    batch_max_age_minutes: int = 30

    # 文件系统采集配置
    filesystem_scan_paths: list[str] = []
    filesystem_file_patterns: list[str] = ["*.jsonl", "*.md", "*.yaml"]

    # 通用 SQLite 数据源配置
    generic_sqlite_sources: list[dict] = []
```

The full updated `Settings` class should now look like:

```python
class Settings(BaseSettings):
    """Application settings loaded from environment (DEVCONTEXT_ prefix)."""
    model_config = SettingsConfigDict(
        env_prefix="DEVCONTEXT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 数据库
    db_path: str = ".devContextMemo/devcontextmemo.db"

    # LLM
    llm_provider: str = "minimax"
    llm_model: str = "abab6.5s-chat"
    llm_api_key: str = ""
    llm_base_url: str = ""

    # 服务器
    host: str = "127.0.0.1"
    port: int = 9020

    # 目录
    knowledge_dir: str = ".devContextMemo/knowledge"
    staging_dir: str = ".devContextMemo/staging"
    deprecated_dir: str = ".devContextMemo/deprecated"
    quarantined_dir: str = ".devContextMemo/quarantined"
    raw_dir: str = "~/.devcontext/raw"

    # 仲裁阈值
    arbitration_auto_adopt_threshold: float = 0.30
    arbitration_manual_review_threshold: float = 0.10
    arbitration_dual_discard_threshold: float = 0.40

    # 采集配置
    opencode_db_path: str = "~/.opencode/opencode.db"
    poll_interval_ms: int = 500
    buffer_max_messages: int = 200
    buffer_max_tokens: int = 6000

    # 攒批配置
    batch_token_threshold: int = 6000
    batch_max_age_minutes: int = 30

    # 文件系统采集配置
    filesystem_scan_paths: list[str] = []
    filesystem_file_patterns: list[str] = ["*.jsonl", "*.md", "*.yaml"]

    # 通用 SQLite 数据源配置
    generic_sqlite_sources: list[dict] = []
```

- [ ] **Step 2: Verify settings load correctly**

Run: `python -c "from devcontext.config import settings; print('poll_interval_ms:', settings.poll_interval_ms); print('opencode_db_path:', settings.opencode_db_path)"`
Expected: `poll_interval_ms: 500` and `opencode_db_path: ~/.opencode/opencode.db`

- [ ] **Step 3: Commit**

```bash
git add src/devcontext/config.py
git commit -m "feat(config): add polling, batching, and multi-source collection settings"
```

---

## Task 12: Add devcontext capture CLI command

**Files:**
- Modify: `src/devcontext/cli/app.py`

- [ ] **Step 1: Add capture command**

In `src/devcontext/cli/app.py`, add the imports:

```python
from devcontext.config import settings
from devcontext.core.collectors.polling import PollingCollector
from devcontext.core.adapters.opencode_sqlite import OpenCodeSQLiteAdapter
from devcontext.core.adapters.filesystem import FileSystemAdapter
from devcontext.core.pipeline.batcher import BatchWriter
from devcontext.services.pipeline import PipelineService
```

Add the command:

```python
@app.command("capture")
def capture_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview mode, no actual writes"),
):
    """手动触发一次完整采集。

    无参数时执行实际采集并写入知识库。
    --dry-run 预览模式：仅显示会采集多少数据，不实际写入。
    """
    collectors = []

    if settings.opencode_db_path:
        from pathlib import Path
        if Path(settings.opencode_db_path).expanduser().exists():
            collectors.append(
                PollingCollector(
                    adapter=OpenCodeSQLiteAdapter(
                        db_path=settings.opencode_db_path,
                    ),
                    poll_interval_ms=settings.poll_interval_ms,
                )
            )

    if settings.filesystem_scan_paths:
        collectors.append(
            PollingCollector(
                adapter=FileSystemAdapter(
                    scan_paths=settings.filesystem_scan_paths,
                    file_patterns=settings.filesystem_file_patterns,
                ),
            )
        )

    if not collectors:
        typer.echo("No data sources configured or available.")
        typer.echo("  Configure opencode_db_path or filesystem_scan_paths in settings.")
        raise typer.Exit(code=1)

    batch_writer = BatchWriter(
        staging_dir=settings.staging_dir,
        token_threshold=settings.batch_token_threshold,
    )

    pipeline = PipelineService(
        collectors=collectors,
        batch_writer=batch_writer,
    )

    if dry_run:
        typer.echo("=== DRY RUN (preview mode) ===")

    result = pipeline.capture(dry_run=dry_run)

    for source, info in result["collectors"].items():
        if "error" in info:
            typer.echo(f"  [{source}] ERROR: {info['error']}")
        else:
            typer.echo(f"  [{source}] Found {info['messages_found']} new messages")
            typer.echo(f"  [{source}] Watermarks: {info['watermarks']}")

    if not dry_run:
        typer.echo("Capture complete.")
```

- [ ] **Step 2: Verify CLI registers the command**

Run: `python -m devcontext.cli.app capture --help`
Expected: Help text for capture command with `--dry-run` option.

- [ ] **Step 3: Test dry-run mode**

Run: `python -m devcontext.cli.app capture --dry-run`
Expected: Either "No data sources configured" or dry-run output showing collector results.

- [ ] **Step 4: Commit**

```bash
git add src/devcontext/cli/app.py
git commit -m "feat(cli): add devcontext capture command with --dry-run support"
```

---

## Task 13: Final Integration Verification

- [ ] **Step 1: Run all existing tests to verify no regressions**

```bash
pytest tests/unit/ tests/module/ -x --timeout=30 -q
```

Expected: All previously passing tests still pass. New test files may fail if they need DB setup — that's OK for now.

- [ ] **Step 2: Run new tests**

```bash
pytest tests/unit/test_clean_message.py tests/unit/test_adapter_polling.py tests/unit/test_opencode_incremental.py tests/unit/test_opencode_sqlite_adapter.py tests/unit/test_filesystem_adapter.py tests/unit/test_generic_sqlite_adapter.py tests/unit/test_polling_collector.py tests/unit/test_batch_writer.py tests/unit/test_pipeline_service.py -v
```

Expected: All tests pass (OpenCode incremental tests may skip if no real DB).

- [ ] **Step 3: Verify ruff lint**

```bash
ruff check src/devcontext/core/collectors/ src/devcontext/core/adapters/opencode_sqlite.py src/devcontext/core/adapters/filesystem.py src/devcontext/core/adapters/generic_sqlite.py src/devcontext/services/pipeline.py src/devcontext/main.py src/devcontext/config.py src/devcontext/cli/app.py
```

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "feat(pipeline): complete auto-capture + pipeline orchestration implementation"
```

---

## Architecture Summary

```
src/devcontext/
├── core/
│   ├── adapters/
│   │   ├── base.py              # +incremental_query, +fetch_full, +validate_connection
│   │   ├── opencode.py          # +incremental_query()
│   │   ├── opencode_sqlite.py   # NEW: OpenCodeSQLiteAdapter
│   │   ├── filesystem.py        # NEW: FileSystemAdapter
│   │   └── generic_sqlite.py    # NEW: GenericSQLiteAdapter
│   ├── collectors/              # NEW package
│   │   ├── __init__.py
│   │   ├── base.py              # CleanMessage + BaseCollector
│   │   └── polling.py           # PollingCollector + WatermarkStore
│   └── pipeline/
│       └── batcher.py           # +BatchWriter
├── services/
│   └── pipeline.py              # PipelineService (was stub)
├── main.py                      # serve() (was stub)
├── cli/
│   └── app.py                   # +capture command
└── config.py                    # +polling/batch/fs config
```

### Files NOT modified:
- `extractor.py`, `entity_extractor.py`, `validator.py`, `deduplicator.py`, `writer.py`, `consolidator.py`
- Existing `Batcher` class preserved
- Existing `Receiver` class preserved
- Existing `OpenCodeAdapter`, `ComateAdapter`, `CursorAdapter` preserved
