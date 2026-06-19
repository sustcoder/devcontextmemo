"""Unit tests for CleanMessage data contract and BaseCollector."""

from devcontext.core.collectors.base import BaseCollector, CleanMessage


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


class TestBaseCollector:
    """BaseCollector buffer management and noise stripping tests."""

    def test_strip_noise_removes_system_reminder(self):
        """_strip_noise should remove <system-reminder> blocks."""
        collector = BaseCollector(adapter=None)
        msg = CleanMessage(
            session_id="s1",
            role="assistant",
            content="real content\n<system-reminder>noise</system-reminder>\nmore content",
            timestamp=0.0,
            source="test",
        )
        result = collector._strip_noise(msg)
        assert "<system-reminder>" not in result.content
        assert "<system-reminder>" not in result.content
        assert "real content" in result.content
        assert "more content" in result.content
        assert "noise" not in result.content

    def test_strip_noise_removes_relevant_memories(self):
        """_strip_noise should remove <relevant-memories> blocks."""
        collector = BaseCollector(adapter=None)
        msg = CleanMessage(
            session_id="s1",
            role="assistant",
            content="keep this\n<relevant-memories>old memories</relevant-memories>\nkeep too",
            timestamp=0.0,
            source="test",
        )
        result = collector._strip_noise(msg)
        assert "<relevant-memories>" not in result.content
        assert "keep this" in result.content
        assert "keep too" in result.content

    def test_strip_noise_removes_subagent_context(self):
        """_strip_noise should remove [Subagent Context]...[/Subagent Context] blocks."""
        collector = BaseCollector(adapter=None)
        msg = CleanMessage(
            session_id="s1",
            role="assistant",
            content="before\n[Subagent Context]\nsubagent stuff\n[/Subagent Context]\nafter",
            timestamp=0.0,
            source="test",
        )
        result = collector._strip_noise(msg)
        assert "[Subagent Context]" not in result.content
        assert "before" in result.content
        assert "after" in result.content

    def test_strip_noise_strips_whitespace(self):
        """_strip_noise should strip leading/trailing whitespace from content."""
        collector = BaseCollector(adapter=None)
        msg = CleanMessage(
            session_id="s1",
            role="user",
            content="  \n  hello world  \n  ",
            timestamp=0.0,
            source="test",
        )
        result = collector._strip_noise(msg)
        assert result.content == "hello world"

    def test_strip_noise_returns_same_message_object(self):
        """_strip_noise should return the same object with cleaned content."""
        collector = BaseCollector(adapter=None)
        original_content = (
            "important code\n"
            "<system-reminder>internal note</system-reminder>\n"
            "more code"
        )
        msg = CleanMessage(
            session_id="abc",
            role="assistant",
            content=original_content,
            timestamp=1718809200.0,
            source="opencode",
        )
        result = collector._strip_noise(msg)
        assert result is msg
        assert result.session_id == "abc"
        assert result.role == "assistant"
        assert result.source == "opencode"
        assert "important code" in result.content
        assert "more code" in result.content

    def test_check_buffer_by_message_count(self):
        """_check_buffer should return True when message count >= max_messages."""
        collector = BaseCollector(adapter=None)
        collector.buffer = [
            CleanMessage(
                session_id=f"s{i}",
                role="user",
                content="x",
                timestamp=0.0,
                source="test",
            )
            for i in range(200)
        ]
        assert collector._check_buffer(max_messages=200, max_tokens=99999) is True

    def test_check_buffer_by_token_threshold(self):
        """_check_buffer should return True when estimated token count >= max_tokens."""
        collector = BaseCollector(adapter=None)
        collector.buffer = [
            CleanMessage(
                session_id="s1",
                role="user",
                content="x" * 12000,
                timestamp=0.0,
                source="test",
            )
        ]
        assert collector._check_buffer(max_messages=99999, max_tokens=6000) is True

    def test_check_buffer_not_triggered(self):
        """_check_buffer should return False when neither threshold is met."""
        collector = BaseCollector(adapter=None)
        collector.buffer = [
            CleanMessage(
                session_id="s1",
                role="user",
                content="hello",
                timestamp=0.0,
                source="test",
            )
        ]
        assert collector._check_buffer(max_messages=200, max_tokens=6000) is False

    def test_flush_buffer_returns_and_clears(self):
        """_flush_buffer should return all messages and clear the buffer."""
        collector = BaseCollector(adapter=None)
        msgs = [
            CleanMessage(
                session_id="s1",
                role="user",
                content="a",
                timestamp=0.0,
                source="test",
            ),
            CleanMessage(
                session_id="s2",
                role="assistant",
                content="b",
                timestamp=0.0,
                source="test",
            ),
        ]
        collector.buffer = list(msgs)
        flushed = collector._flush_buffer()
        assert flushed == msgs
        assert collector.buffer == []

    def test_emit_calls_callback(self):
        """_emit should invoke on_buffer_ready with messages."""
        captured: list[list[CleanMessage]] = []

        def callback(msgs: list[CleanMessage]) -> None:
            captured.append(msgs)

        collector = BaseCollector(adapter=None)
        collector.on_buffer_ready = callback
        msgs = [
            CleanMessage(
                session_id="s1",
                role="user",
                content="test",
                timestamp=0.0,
                source="test",
            )
        ]
        collector._emit(msgs)
        assert len(captured) == 1
        assert captured[0] is msgs

    def test_emit_no_callback_safe(self):
        """_emit should not raise when on_buffer_ready is None."""
        collector = BaseCollector(adapter=None)
        collector._emit([])
