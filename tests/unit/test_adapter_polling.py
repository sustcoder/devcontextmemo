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
