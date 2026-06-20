"""ResourceService 单元测试。"""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def resource_service():
    """创建测试用的 ResourceService。"""
    from devcontext.services.resource import ResourceService
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(":memory:")
    store.init_db()
    with tempfile.TemporaryDirectory() as tmp:
        resources_dir = Path(tmp) / ".devContextMemo" / "resources"
        service = ResourceService(store, resources_dir)
        yield service
        store.close()


def _create_temp_md(content: str, suffix: str = ".md") -> str:
    """创建临时 MD 文件返回路径。"""
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


def test_add_resource_creates_record(resource_service):
    """Verify adding a resource creates DB record."""
    path = _create_temp_md("# Test PRD\n\nThis is a test requirement.\n\n## Section\n\nContent.\n")
    result = resource_service.add(path, resource_type="requirements")
    assert result["resource_id"].startswith("res_")
    assert result["type"] == "requirements"
    assert result["blocks"] >= 1


def test_add_resource_detects_duplicate(resource_service):
    """Verify duplicate content is detected by hash."""
    path = _create_temp_md("# Test\n\nContent.\n")
    resource_service.add(path, resource_type="requirements")
    result2 = resource_service.add(path, resource_type="requirements")
    assert result2["status"] == "unchanged"


def test_add_resource_rejects_large_file(resource_service):
    """Verify files > 100MB are rejected."""
    path = _create_temp_md("")
    os.truncate(path, 101 * 1024 * 1024)
    with pytest.raises(ValueError, match="too large"):
        resource_service.add(path)


def test_list_resources(resource_service):
    """Verify listing resources returns correct records."""
    path = _create_temp_md("# API Spec\n\n## GET /users\n\nReturns list of users.\n")
    resource_service.add(path, resource_type="api")
    resources = resource_service.list()
    assert len(resources) >= 1
    assert resources[0]["type"] == "api"


def test_search_resources_finds_content(resource_service):
    """Verify FTS5 search finds matching blocks."""
    path = _create_temp_md("# Payment Module\n\n支付模块支持微信支付和支付宝。\n")
    resource_service.add(path, resource_type="requirements")
    results = resource_service.search("微信支付")
    assert len(results) >= 1


def test_remove_resource_soft_delete(resource_service):
    """Verify soft delete marks deleted_at but keeps data."""
    path = _create_temp_md("# Test\n\nContent.\n")
    result = resource_service.add(path, resource_type="design")
    assert resource_service.remove(result["resource_id"]) is True
    resource = resource_service.get(result["resource_id"])
    assert resource is not None
    assert resource["deleted_at"] is not None


def test_type_inference_from_filename(resource_service):
    """Verify type is inferred from filename keywords."""
    assert resource_service._infer_type(Path("/some/path/prd-v1.0.md")) == "requirements"
    assert resource_service._infer_type(Path("/some/path/api-design.md")) == "api"
    assert resource_service._infer_type(Path("/some/path/schema.sql")) == "schema"
    assert resource_service._infer_type(Path("/some/path/unknown.txt")) == "design"


def test_chunk_markdown_creates_typed_blocks(resource_service):
    """Verify semantic chunking produces correctly typed blocks."""
    path = _create_temp_md("""# Introduction

This is a description of the project. It has multiple sentences.

## API

```python
def hello():
    print("world")
```

- Item 1
- Item 2
""")
    blocks = resource_service._chunk_markdown(Path(path))
    types = [b["type"] for b in blocks]
    assert "heading" in types
    assert "paragraph" in types
    assert "code" in types
