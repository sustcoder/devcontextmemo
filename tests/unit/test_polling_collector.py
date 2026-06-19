"""Unit tests for PollingCollector."""

import time

from devcontext.core.adapters.base import BaseAdapter
from devcontext.core.collectors.base import CleanMessage
from devcontext.core.collectors.polling import PollingCollector


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
        results = collector._poll_once()
        assert len(results) == 1
        assert isinstance(results[0], CleanMessage)
        assert results[0].content == "hello"

    def test_buffer_flush_on_message_limit(self):
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
        msg = CleanMessage(
            session_id="s1", role="user",
            content="hello\n<system-reminder>ignore this</system-reminder>\nworld",
            timestamp=time.time(), source="mock",
        )
        result = collector._strip_noise(msg)
        assert "system-reminder" not in result.content
        assert "hello" in result.content
        assert "world" in result.content

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
        assert collector.watermarks.get("checkpoint") == 5
