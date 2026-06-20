"""Global test fixtures and configuration for devContextMemo."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# =============================================================================
# Directory & Path Fixtures
# =============================================================================

@pytest.fixture
def tmp_workspace():
    """Create a temporary workspace directory with .devContextMemo/ and .devcontext/raw/ structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / ".devContextMemo" / "knowledge").mkdir(parents=True)
        (root / ".devContextMemo" / "staging").mkdir(parents=True)
        (root / ".devContextMemo" / "deprecated").mkdir(parents=True)
        (root / ".devcontext" / "raw" / "test-project").mkdir(parents=True)
        yield root


@pytest.fixture
def tmp_staging(tmp_workspace):
    """Return path to .devContextMemo/staging/."""
    return tmp_workspace / ".devContextMemo" / "staging"


@pytest.fixture
def tmp_knowledge(tmp_workspace):
    """Return path to .devContextMemo/knowledge/."""
    return tmp_workspace / ".devContextMemo" / "knowledge"


@pytest.fixture
def tmp_raw(tmp_workspace):
    """Return path to .devcontext/raw/test-project/."""
    return tmp_workspace / ".devcontext" / "raw" / "test-project"


# =============================================================================
# Mock Data Fixtures — Raw Session (Step 0 output)
# =============================================================================

@pytest.fixture
def mock_raw_session_jsonl():
    """A single raw session JSONL (Step 0 output format)."""
    return [
        {"session_id": "sess-001", "seq": 1, "role": "user", "content": "如何实现支付流程？", "timestamp": "2025-06-18T10:00:00Z", "source": "opencode"},
        {"session_id": "sess-001", "seq": 2, "role": "assistant", "content": "支付流程使用状态机模式，OrderService 负责编排。", "timestamp": "2025-06-18T10:01:00Z", "source": "opencode"},
        {"session_id": "sess-001", "seq": 3, "role": "user", "content": "超时时间是多少？", "timestamp": "2025-06-18T10:02:00Z", "source": "opencode"},
        {"session_id": "sess-001", "seq": 4, "role": "assistant", "content": "默认超时 30 秒，可在 application.yml 中配置。", "timestamp": "2025-06-18T10:03:00Z", "source": "opencode"},
    ]


@pytest.fixture
def mock_raw_session_empty():
    """An empty session (no messages)."""
    return []


@pytest.fixture
def mock_raw_session_single_message():
    """A session with a single short message."""
    return [
        {"session_id": "sess-002", "seq": 1, "role": "user", "content": "hello", "timestamp": "2025-06-18T11:00:00Z", "source": "opencode"},
    ]


# =============================================================================
# Mock Data Fixtures — Batch JSONL (Step 1 output)
# =============================================================================

@pytest.fixture
def mock_batch_jsonl(mock_raw_session_jsonl):
    """A batch JSONL (Step 1 output format)."""
    return mock_raw_session_jsonl  # Step 1 just repackages, same format


@pytest.fixture
def mock_batch_jsonl_empty():
    """An empty batch."""
    return []


# =============================================================================
# Mock Data Fixtures — Summary JSONL (Step 2a output)
# =============================================================================

@pytest.fixture
def mock_summary_jsonl():
    """A summary JSONL with classification + time extraction (Step 2a output format)."""
    return [
        {
            "session_id": "sess-001",
            "knowledge_text": "支付流程使用状态机模式，由 OrderService 负责编排",
            "lx": "L2", "sy": "S3", "depth": "KH", "domain": "order",
            "confidence": 0.88,
            "occurred_at": "2025-06-18T10:01:00Z",
            "source_messages": [2],
        },
        {
            "session_id": "sess-001",
            "knowledge_text": "支付超时默认 30 秒，可在 application.yml 中配置",
            "lx": "L3", "sy": "S4", "depth": "KW", "domain": "order",
            "confidence": 0.92,
            "occurred_at": "2025-06-18T10:03:00Z",
            "source_messages": [4],
        },
    ]


@pytest.fixture
def mock_summary_low_confidence():
    """A summary with low confidence (should go to PENDING_REVIEW)."""
    return [
        {
            "session_id": "sess-003",
            "knowledge_text": "某个不确定的优化建议",
            "lx": "L1", "sy": "S5", "depth": "KH", "domain": "order",
            "confidence": 0.45,
            "occurred_at": None,
            "source_messages": [1],
        },
    ]


@pytest.fixture
def mock_summary_no_time():
    """A summary where time cannot be inferred."""
    return [
        {
            "session_id": "sess-004",
            "knowledge_text": "团队很久以前用过 MongoDB",
            "lx": "L0", "sy": "S5", "depth": "KY", "domain": "architecture",
            "confidence": 0.70,
            "occurred_at": None,
            "source_messages": [1],
        },
    ]


@pytest.fixture
def mock_summary_implicit_time():
    """A summary with implicit time reference (LLM should infer)."""
    return [
        {
            "session_id": "sess-005",
            "knowledge_text": "上周修复了支付回调的并发 bug",
            "lx": "L3", "sy": "S5", "depth": "KH", "domain": "order",
            "confidence": 0.85,
            "occurred_at": "2025-06-11T00:00:00Z",  # inferred as ~7 days ago
            "source_messages": [1],
        },
    ]


# =============================================================================
# Mock Data Fixtures — Knowledge JSONL (Step 2b output)
# =============================================================================

@pytest.fixture
def mock_knowledge_jsonl():
    """Knowledge JSONL with entities + relations (Step 2b output format)."""
    return [
        {
            "session_id": "sess-001",
            "knowledge_text": "支付流程使用状态机模式，由 OrderService 负责编排",
            "lx": "L2", "sy": "S3", "depth": "KH", "domain": "order",
            "confidence": 0.88,
            "occurred_at": "2025-06-18T10:01:00Z",
            "entities": [
                {"name": "OrderService", "type": "class", "file": "src/order/OrderService.java"},
                {"name": "状态机模式", "type": "pattern"},
            ],
            "relations": [
                {"source": "OrderService", "target": "状态机模式", "type": "implements"},
                {"source": "OrderService", "target": "支付流程", "type": "handles"},
            ],
        },
        {
            "session_id": "sess-001",
            "knowledge_text": "支付超时默认 30 秒，可在 application.yml 中配置",
            "lx": "L3", "sy": "S4", "depth": "KW", "domain": "order",
            "confidence": 0.92,
            "occurred_at": "2025-06-18T10:03:00Z",
            "entities": [
                {"name": "application.yml", "type": "config_file", "file": "src/main/resources/application.yml"},
            ],
            "relations": [],
        },
    ]


@pytest.fixture
def mock_knowledge_no_entities():
    """Knowledge JSONL with no entities extracted."""
    return [
        {
            "session_id": "sess-006",
            "knowledge_text": "团队偏好使用 Tab 缩进",
            "lx": "L0", "sy": "S1", "depth": "KW", "domain": "convention",
            "confidence": 0.95,
            "occurred_at": "2025-06-18T09:00:00Z",
            "entities": [],
            "relations": [],
        },
    ]


# =============================================================================
# Mock Data Fixtures — DB Records (for Step 5/6 testing)
# =============================================================================

@pytest.fixture
def mock_db_records():
    """Pre-populated DB records for Step 6 consolidation testing.

    V1.1 对齐：状态名小写 8 态 + 字段名对齐 schema（granularity/stability/depth/title）。
    """
    return [
        {
            "id": "k-001", "status": "draft", "confidence": 0.88, "code_verified": 0,
            "last_calibrated_at": None, "created_at": "2025-03-01T00:00:00Z",
            "granularity": "L2", "stability": "S3", "depth": "KH", "domain": "order",
            "title": "支付流程使用状态机模式",
        },
        {
            "id": "k-002", "status": "staged", "confidence": 0.92, "code_verified": 1,
            "last_calibrated_at": "2025-06-15T00:00:00Z", "created_at": "2025-02-01T00:00:00Z",
            "granularity": "L3", "stability": "S4", "depth": "KW", "domain": "order",
            "title": "支付超时默认 30 秒",
        },
        {
            "id": "k-003", "status": "active", "confidence": 0.95, "code_verified": 1,
            "last_calibrated_at": "2024-06-01T00:00:00Z", "created_at": "2024-01-01T00:00:00Z",
            "granularity": "L0", "stability": "S1", "depth": "KW", "domain": "convention",
            "title": "团队偏好使用 Tab 缩进",
        },
        {
            "id": "k-004", "status": "active", "confidence": 0.82, "code_verified": 0,
            "last_calibrated_at": "2025-06-10T00:00:00Z", "created_at": "2025-01-01T00:00:00Z",
            "granularity": "L2", "stability": "S3", "depth": "KH", "domain": "order",
            "title": "退款流程需要 3 步审批",
        },
        {
            "id": "k-005", "status": "cold", "confidence": 0.75, "code_verified": 0,
            "last_calibrated_at": "2024-01-01T00:00:00Z", "created_at": "2023-06-01T00:00:00Z",
            "granularity": "L3", "stability": "S5", "depth": "KH", "domain": "payment",
            "title": "旧版支付网关使用 SOAP 协议",
        },
    ]


@pytest.fixture
def db_store():
    """In-memory SQLiteStore with all 7 tables initialized (Phase 2)."""
    from devcontext.storage.sqlite import SQLiteStore
    store = SQLiteStore(":memory:")
    store.init_db()
    yield store
    store.close()


# =============================================================================
# Mock LLM Client
# =============================================================================

@pytest.fixture
def mock_llm_client():
    """Mock LLM client that returns a valid classification response."""
    client = MagicMock()
    client.chat.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "knowledge_items": [
                        {
                            "knowledge_text": "支付流程使用状态机模式",
                            "lx": "L2", "sy": "S3", "depth": "KH", "domain": "order",
                            "confidence": 0.88,
                            "occurred_at": "2025-06-18T10:01:00Z",
                        }
                    ]
                })
            }
        }],
        "usage": {"total_tokens": 150, "prompt_tokens": 100, "completion_tokens": 50},
    }
    return client


@pytest.fixture
def mock_llm_client_low_confidence():
    """Mock LLM client that returns low-confidence classification."""
    client = MagicMock()
    client.chat.return_value = {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "knowledge_items": [
                        {
                            "knowledge_text": "不确定的优化建议",
                            "lx": "L1", "sy": "S5", "depth": "KH", "domain": "order",
                            "confidence": 0.45,
                            "occurred_at": None,
                        }
                    ]
                })
            }
        }],
        "usage": {"total_tokens": 100, "prompt_tokens": 70, "completion_tokens": 30},
    }
    return client


@pytest.fixture
def mock_llm_client_timeout():
    """Mock LLM client that raises a timeout."""
    client = MagicMock()
    client.chat.side_effect = TimeoutError("LLM API timeout after 30s")
    return client


@pytest.fixture
def mock_llm_client_malformed():
    """Mock LLM client that returns malformed JSON."""
    client = MagicMock()
    client.chat.return_value = {
        "choices": [{
            "message": {
                "content": "not valid json {{{"
            }
        }],
        "usage": {"total_tokens": 50},
    }
    return client


# =============================================================================
# Domain Tree Fixture
# =============================================================================

@pytest.fixture
def mock_domain_tree():
    """Mock domain tree used by Step 2a classifier."""
    return {
        "order": {"name": "订单", "parent": None},
        "payment": {"name": "支付", "parent": "order"},
        "user": {"name": "用户", "parent": None},
        "architecture": {"name": "架构", "parent": None},
        "convention": {"name": "规范", "parent": None},
        "deployment": {"name": "部署", "parent": None},
    }


# =============================================================================
# Helper Functions
# =============================================================================

def write_jsonl(path: Path, data: list):
    """Write a list of dicts as JSONL to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list:
    """Read a JSONL file and return list of dicts."""
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


# =============================================================================
# Markdown Store Fixture (Phase 3)
# =============================================================================

@pytest.fixture
def markdown_store(tmp_path):
    """MarkdownStore with temporary staging/knowledge/deprecated directories."""
    from devcontext.storage.markdown import MarkdownStore
    store = MarkdownStore(
        staging_dir=tmp_path / "staging",
        knowledge_dir=tmp_path / "knowledge",
        deprecated_dir=tmp_path / "deprecated",
    )
    return store


@pytest.fixture
def sample_knowledge_record():
    """Sample knowledge record for MD write/read tests (V1.1 fields)."""
    return {
        "id": "kw-20260618-001",
        "title": "订单幂等校验方案",
        "domain": "order",
        "sub_domain": "idempotency",
        "granularity": "L2",
        "stability": "S3",
        "depth": "KH",
        "knowledge_type": "fact",
        "status": "staged",
        "confidence": 0.88,
        "code_verified": 1,
        "concept_tags": ["#幂等", "#createOrder"],
        "source_session": "sess-abc",
        "created_at": "2026-06-18T10:00:00Z",
        "updated_at": "2026-06-18T10:00:00Z",
        "content": "# 订单幂等校验\n\n使用 orderId + token 双重校验防止重复下单。",
    }
