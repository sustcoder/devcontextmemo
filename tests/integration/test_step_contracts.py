"""Integration tests — Step-to-Step data contract compatibility (validate_input).

These tests verify that each Step's real output can be consumed by the next Step's
validate_input() function. They do NOT test full pipeline execution — that's what
module tests and E2E tests cover.
"""

import pytest
from pathlib import Path

from tests.conftest import write_jsonl


class TestStep0ToStep1Contract:
    """Step 0 (Receiver) output → Step 1 (Batcher) validate_input."""

    def test_receiver_output_passes_batcher_validation(self, tmp_workspace, mock_raw_session_jsonl):
        """Real receiver output format should pass batcher's validate_input."""
        from src.pipeline.batcher import Batcher

        raw_path = tmp_workspace / ".devcontext" / "raw" / "test-project" / "session_sess-001.jsonl"
        write_jsonl(raw_path, mock_raw_session_jsonl)

        batcher = Batcher()
        # validate_input should accept the format
        is_valid, error = batcher.validate_input(mock_raw_session_jsonl)
        assert is_valid, f"Batcher rejected valid receiver output: {error}"

    def test_empty_receiver_output_blocked_by_batcher(self, tmp_workspace):
        """Empty receiver output should be blocked by batcher validate_input."""
        from src.pipeline.batcher import Batcher

        batcher = Batcher()
        is_valid, error = batcher.validate_input([])
        assert not is_valid, "Batcher should reject empty input"
        assert error is not None


class TestStep1ToStep2aContract:
    """Step 1 (Batcher) output → Step 2a (Extractor) validate_input."""

    def test_batcher_output_passes_extractor_validation(self, tmp_workspace, mock_batch_jsonl):
        """Real batcher output format should pass extractor's validate_input."""
        from src.pipeline.extractor import Extractor

        extractor = Extractor(llm_client=None, domain_tree={})
        is_valid, error = extractor.validate_input(mock_batch_jsonl)
        assert is_valid, f"Extractor rejected valid batch: {error}"

    def test_missing_required_fields_rejected(self, tmp_workspace):
        """Batch with missing required fields should be rejected."""
        from src.pipeline.extractor import Extractor

        bad_data = [{"session_id": "sess-001"}]  # missing role, content, etc.
        extractor = Extractor(llm_client=None, domain_tree={})
        is_valid, error = extractor.validate_input(bad_data)
        assert not is_valid


class TestStep2aToStep2bContract:
    """Step 2a (Extractor) output → Step 2b (Entity Extractor) validate_input."""

    def test_summary_output_passes_entity_validation(self, tmp_workspace, mock_summary_jsonl):
        """Real summary output should pass entity extractor's validate_input."""
        from src.pipeline.entity_extractor import EntityExtractor

        extractor = EntityExtractor(llm_client=None)
        is_valid, error = extractor.validate_input(mock_summary_jsonl)
        assert is_valid, f"EntityExtractor rejected valid summary: {error}"


class TestStep2bToStep3Contract:
    """Step 2b (Entity Extractor) output → Step 3 (Validator) validate_input."""

    def test_knowledge_with_entities_passes_validator(self, tmp_workspace, mock_knowledge_jsonl):
        """Knowledge with entities should pass validator's validate_input."""
        from src.pipeline.validator import Validator

        validator = Validator()
        is_valid, error = validator.validate_input(mock_knowledge_jsonl)
        assert is_valid, f"Validator rejected valid knowledge: {error}"

    def test_knowledge_without_entities_passes_validator(self, tmp_workspace, mock_knowledge_no_entities):
        """Knowledge without entities should also pass validator (entities optional)."""
        from src.pipeline.validator import Validator

        validator = Validator()
        is_valid, error = validator.validate_input(mock_knowledge_no_entities)
        assert is_valid, f"Validator rejected knowledge without entities: {error}"


class TestEmptyUpstreamBoundary:
    """Upstream output is empty → downstream validate_input should BLOCK, not crash."""

    def test_empty_batch_blocked_by_extractor(self):
        from src.pipeline.extractor import Extractor
        extractor = Extractor(llm_client=None, domain_tree={})
        is_valid, error = extractor.validate_input([])
        assert not is_valid

    def test_empty_summary_blocked_by_entity_extractor(self):
        from src.pipeline.entity_extractor import EntityExtractor
        extractor = EntityExtractor(llm_client=None)
        is_valid, error = extractor.validate_input([])
        assert not is_valid

    def test_empty_knowledge_blocked_by_validator(self):
        from src.pipeline.validator import Validator
        validator = Validator()
        is_valid, error = validator.validate_input([])
        assert not is_valid
