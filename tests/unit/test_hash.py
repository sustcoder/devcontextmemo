"""Unit tests for hash utilities — pure functions, zero dependencies."""

import pytest


class TestContentHash:
    """content_hash: SHA-256 deterministic hashing."""

    def test_deterministic_same_input_same_output(self):
        """Same input always produces the same content_hash."""
        from src.utils.hash import content_hash
        text = "支付流程使用状态机模式"
        assert content_hash(text) == content_hash(text)

    def test_different_inputs_different_outputs(self):
        """Different inputs produce different content_hash."""
        from src.utils.hash import content_hash
        h1 = content_hash("支付流程使用状态机模式")
        h2 = content_hash("退款流程需要3步审批")
        assert h1 != h2

    def test_empty_input_handled(self):
        """Empty string produces a valid hash, not an error."""
        from src.utils.hash import content_hash
        result = content_hash("")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_unicode_input_handled(self):
        """Unicode characters (Chinese, emoji) are hashed correctly."""
        from src.utils.hash import content_hash
        text = "支付超时 ⏱️ 默认 30 秒 🚀"
        result = content_hash(text)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_large_text_handled(self):
        """Large text (10KB+) produces a valid hash."""
        from src.utils.hash import content_hash
        text = "支付流程" * 5000  # ~25KB
        result = content_hash(text)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_whitespace_sensitive(self):
        """Leading/trailing whitespace affects hash (content-sensitive)."""
        from src.utils.hash import content_hash
        h1 = content_hash("支付流程")
        h2 = content_hash(" 支付流程 ")
        assert h1 != h2


class TestSemanticHash:
    """semantic_hash: SimHash for near-duplicate detection."""

    def test_identical_texts_same_semantic_hash(self):
        """Identical texts produce identical semantic_hash."""
        from src.utils.hash import semantic_hash
        text = "支付流程使用状态机模式"
        assert semantic_hash(text) == semantic_hash(text)

    def test_similar_texts_similar_hash(self):
        """Semantically similar texts have similar SimHash values."""
        from src.utils.hash import semantic_hash, hamming_distance
        h1 = semantic_hash("支付流程使用状态机模式")
        h2 = semantic_hash("支付流程采用状态机模式")
        # Hamming distance should be small for similar texts
        dist = hamming_distance(h1, h2)
        assert dist < 10, f"Hamming distance {dist} too large for similar texts"

    def test_different_texts_different_hash(self):
        """Unrelated texts have very different SimHash values."""
        from src.utils.hash import semantic_hash, hamming_distance
        h1 = semantic_hash("支付流程使用状态机模式")
        h2 = semantic_hash("团队偏好使用Tab缩进")
        dist = hamming_distance(h1, h2)
        assert dist > 10, f"Hamming distance {dist} too small for unrelated texts"

    def test_empty_input_handled(self):
        """Empty string produces a valid semantic_hash."""
        from src.utils.hash import semantic_hash
        result = semantic_hash("")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_normalization_removes_noise(self):
        """Normalization removes punctuation and lowercases before hashing."""
        from src.utils.hash import semantic_hash
        h1 = semantic_hash("支付流程!!!使用状态机模式...")
        h2 = semantic_hash("支付流程使用状态机模式")
        # After normalization they should be very similar
        from src.utils.hash import hamming_distance
        dist = hamming_distance(h1, h2)
        assert dist < 8
