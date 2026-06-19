"""Unit tests for PipelineService orchestration."""

from unittest.mock import MagicMock

import pytest

from devcontext.services.pipeline import PipelineService


class TestPipelineService:
    """PipelineService tests."""

    def test_registers_callback_chain(self):
        """PipelineService should wire callbacks during init."""
        mock_collector = MagicMock()
        mock_collector.adapter.source_name = "mock"
        mock_collector.on_buffer_ready = None
        mock_batch_writer = MagicMock()
        mock_batch_writer.on_batch_ready = None
        mock_batch_writer.on_messages = MagicMock()

        pipeline = PipelineService(
            collectors=[mock_collector],
            batch_writer=mock_batch_writer,
        )
        assert mock_collector.on_buffer_ready is not None
        assert mock_batch_writer.on_batch_ready is not None

    def test_capture_calls_poll_once(self):
        """capture() should call _poll_once on each collector that has it."""
        mock_collector = MagicMock()
        mock_collector.adapter.source_name = "mock"
        mock_collector._poll_once = MagicMock(return_value=[])
        mock_batch_writer = MagicMock()
        mock_batch_writer.on_batch_ready = None

        pipeline = PipelineService(
            collectors=[mock_collector],
            batch_writer=mock_batch_writer,
        )
        pipeline.capture(dry_run=True)
        mock_collector._poll_once.assert_called_once()

    def test_on_messages_delegates_to_batch_writer(self):
        """_on_messages should delegate to batch_writer.on_messages."""
        mock_collector = MagicMock()
        mock_batch_writer = MagicMock()
        mock_batch_writer.on_batch_ready = None
        mock_batch_writer.on_messages = MagicMock(return_value=None)

        from devcontext.core.collectors.base import CleanMessage

        pipeline = PipelineService(
            collectors=[mock_collector],
            batch_writer=mock_batch_writer,
        )
        messages = [
            CleanMessage(session_id="s1", role="user", content="test",
                         timestamp=123.0, source="mock"),
        ]
        pipeline._on_messages(messages)
        mock_batch_writer.on_messages.assert_called_once()
