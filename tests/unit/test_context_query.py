"""ContextQueryEngine 单元测试。"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_knowledge_service():
    mock = MagicMock()
    mock.search.return_value = []
    return mock


@pytest.fixture
def mock_resource_service():
    mock = MagicMock()
    mock.search.return_value = []
    mock.list.return_value = []
    return mock


@pytest.fixture
def engine(mock_knowledge_service, mock_resource_service):
    from devcontext.services.context_query import ContextQueryEngine
    return ContextQueryEngine(mock_knowledge_service, mock_resource_service)


def test_query_returns_empty_on_no_results(engine):
    result = engine.query("nothing matches this")
    assert result.total == 0
    assert result.memories == []
    assert result.resources == []


def test_query_returns_memory_results(engine, mock_knowledge_service):
    from devcontext.storage.search import SearchResult
    mock_knowledge_service.search.return_value = [
        SearchResult(id="kw-001", title="Test", domain="test", uri="test.md",
                     confidence=0.8, score=0.9, snippet="test snippet")
    ]
    result = engine.query("test query")
    assert result.total >= 1
    assert len(result.memories) >= 1
    assert result.memories[0]["track"] == "memory"


def test_query_fallback_to_resource_when_memory_empty(engine, mock_resource_service):
    mock_resource_service.search.return_value = [
        {"block_id": "blk-001", "resource_id": "res-001", "block_type": "paragraph",
         "content": "test content", "resource_type": "requirements", "title": "PRD",
         "uri": "resources/requirements/test.md", "source_path": "/tmp/test.md"}
    ]
    result = engine.query("test query", min_confidence=0.9)
    assert result.fallback_level == 2
    assert len(result.resources) >= 1
    assert result.resources[0]["track"] == "resource"


def test_query_single_track_memory(engine, mock_knowledge_service):
    from devcontext.storage.search import SearchResult
    mock_knowledge_service.search.return_value = [
        SearchResult(id="kw-001", title="Test", domain="test", uri="test.md",
                     confidence=0.8, score=0.9, snippet="test")
    ]
    results = engine.query_single_track("test", track="memory")
    assert len(results) >= 1
    assert results[0]["track"] == "memory"


def test_query_single_track_resource(engine, mock_resource_service):
    mock_resource_service.search.return_value = [
        {"block_id": "blk-001", "resource_id": "res-001", "block_type": "paragraph", "content": "test"}
    ]
    results = engine.query_single_track("test", track="resource")
    assert len(results) >= 1


def test_query_single_track_invalid(engine):
    with pytest.raises(ValueError, match="Unknown track"):
        engine.query_single_track("test", track="invalid")
