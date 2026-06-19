"""Integration tests for engine cross-module workflows.

These tests verify that engine modules (promotion, pruning, conflict, health)
work together correctly when triggered by events.
"""

import pytest


class TestPromotionPruningIntegration:
    """Promotion engine + Pruning engine integration."""

    def test_promoted_then_pruned_flow(self, mock_db_records):
        """After promotion evaluation, pruning rules should apply to stale items."""
        from src.core.promotion import evaluate_batch
        from src.core.pruning import evaluate_batch_pruning

        # First: evaluate promotion
        promotion_results = evaluate_batch(mock_db_records)
        assert len(promotion_results) == len(mock_db_records)

        # Then: evaluate pruning on the same records
        pruning_results = evaluate_batch_pruning(mock_db_records)
        assert len(pruning_results) == len(mock_db_records)

        # COLD item (k-005) should trigger pruning
        cold_items = [r for r in pruning_results if r["id"] == "k-005"]
        assert len(cold_items) > 0


class TestConflictDetectionFlow:
    """Conflict detection cross-module integration."""

    def test_duplicate_detection_triggers_conflict(self):
        """Two items with same top_similar_id should be in same conflict_group."""
        from src.core.conflict import assign_conflict_groups

        items = [
            {"id": "k-001", "top_similar_id": "k-existing", "jaccard_score": 0.95},
            {"id": "k-002", "top_similar_id": "k-existing", "jaccard_score": 0.92},
        ]
        result = assign_conflict_groups(items)

        # Both should be in the same conflict group
        assert result[0]["conflict_group"] == result[1]["conflict_group"]
        assert result[0]["conflict_group"] is not None

    def test_no_conflict_when_different_targets(self):
        """Items with different top_similar_id should not share conflict group."""
        from src.core.conflict import assign_conflict_groups

        items = [
            {"id": "k-001", "top_similar_id": "k-a", "jaccard_score": 0.95},
            {"id": "k-002", "top_similar_id": "k-b", "jaccard_score": 0.93},
        ]
        result = assign_conflict_groups(items)

        assert result[0]["conflict_group"] != result[1]["conflict_group"]


class TestHealthCheckIntegration:
    """Data health check integration."""

    def test_md_db_drift_detection(self):
        """When MD content_hash != DB content_hash, health check should detect drift."""
        from src.core.health import detect_md_db_drift

        records = [
            {"id": "k-001", "md_content_hash": "abc123", "db_content_hash": "def456"},
            {"id": "k-002", "md_content_hash": "xyz789", "db_content_hash": "xyz789"},
        ]
        drift_items = detect_md_db_drift(records)

        assert len(drift_items) == 1
        assert drift_items[0]["id"] == "k-001"
