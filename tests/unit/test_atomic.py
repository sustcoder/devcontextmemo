"""Unit tests for storage/atomic.py — 路径校验 + 原子写入。"""

import os
import stat
from pathlib import Path

import pytest

from devcontext.storage.atomic import (
    PathTraversalError,
    atomic_write_md,
    sanitize_path_segment,
    validate_safe_path,
)


# =============================================================================
# sanitize_path_segment
# =============================================================================

class TestSanitizePathSegment:
    """单段路径清理。"""

    def test_plain_text_unchanged(self):
        assert sanitize_path_segment("order") == "order"

    def test_removes_path_separators(self):
        assert sanitize_path_segment("a/b\\c") == "abc"

    def test_removes_dot_dot(self):
        # ".." 被移除，只剩其他字符
        assert sanitize_path_segment("order/../etc") == "orderetc"

    def test_empty_returns_empty(self):
        assert sanitize_path_segment("") == ""

    def test_null_byte_removed(self):
        assert sanitize_path_segment("order\x00evil") == "orderevil"

    def test_whitespace_preserved_then_stripped(self):
        assert sanitize_path_segment("  order  ") == "order"


# =============================================================================
# validate_safe_path
# =============================================================================

class TestValidateSafePath:
    """路径穿越校验（§3.3 表格行为）。"""

    def test_simple_relative_path(self, tmp_path):
        base = tmp_path / "knowledge"
        base.mkdir()
        result = validate_safe_path(base, "order")
        assert result == (base / "order").resolve()

    def test_nested_relative_path(self, tmp_path):
        base = tmp_path / "knowledge"
        base.mkdir()
        result = validate_safe_path(base, "order/payment")
        assert result == (base / "order" / "payment").resolve()

    def test_dot_dot_resolved_within_base(self, tmp_path):
        """order/../payment resolve 后仍在 base 内 → 合法（§3.3 表格）。"""
        base = tmp_path / "knowledge"
        base.mkdir()
        result = validate_safe_path(base, "order/../payment")
        assert result == (base / "payment").resolve()

    def test_traversal_outside_base_rejected(self, tmp_path):
        base = tmp_path / "knowledge"
        base.mkdir()
        with pytest.raises(PathTraversalError):
            validate_safe_path(base, "../../etc")

    def test_pure_dot_dot_rejected(self, tmp_path):
        base = tmp_path / "knowledge"
        base.mkdir()
        with pytest.raises(PathTraversalError):
            validate_safe_path(base, "..")

    def test_empty_input_rejected(self, tmp_path):
        base = tmp_path / "knowledge"
        base.mkdir()
        with pytest.raises(PathTraversalError):
            validate_safe_path(base, "")

    def test_whitespace_only_input_rejected(self, tmp_path):
        base = tmp_path / "knowledge"
        base.mkdir()
        with pytest.raises(PathTraversalError):
            validate_safe_path(base, "   ")

    def test_symlink_escape_rejected(self, tmp_path):
        """符号链接逃逸也应被拒。"""
        base = tmp_path / "knowledge"
        base.mkdir()
        # 创建指向 base 外的符号链接
        link = base / "escape"
        target = tmp_path / "secret"
        target.mkdir()
        try:
            os.symlink(target, link)
        except OSError:
            pytest.skip("symlink not supported")
        with pytest.raises(PathTraversalError):
            validate_safe_path(base, "escape/../secret")


# =============================================================================
# atomic_write_md
# =============================================================================

class TestAtomicWriteMd:
    """原子写入。"""

    def test_successful_write(self, tmp_path):
        target = tmp_path / "test.md"
        ok = atomic_write_md(target, "# hello\n", max_retries=2)
        assert ok is True
        assert target.read_text(encoding="utf-8") == "# hello\n"

    def test_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "deep" / "nested" / "dir" / "test.md"
        ok = atomic_write_md(target, "content", max_retries=1)
        assert ok is True
        assert target.exists()

    def test_no_tmp_residual_on_success(self, tmp_path):
        target = tmp_path / "test.md"
        atomic_write_md(target, "content", max_retries=1)
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert not tmp_files

    def test_overwrite_existing(self, tmp_path):
        target = tmp_path / "test.md"
        atomic_write_md(target, "old", max_retries=1)
        atomic_write_md(target, "new", max_retries=1)
        assert target.read_text(encoding="utf-8") == "new"

    def test_unicode_content(self, tmp_path):
        target = tmp_path / "test.md"
        content = "# 订单幂等校验\n\n中文内容测试 🎯"
        atomic_write_md(target, content, max_retries=1)
        assert target.read_text(encoding="utf-8") == content

    def test_retry_on_failure_then_success(self, tmp_path, monkeypatch):
        """第一次失败，重试成功。"""
        target = tmp_path / "test.md"
        call_count = {"n": 0}
        original_replace = os.replace

        def flaky_replace(src, dst):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise OSError("simulated failure")
            return original_replace(src, dst)

        monkeypatch.setattr(os, "replace", flaky_replace)
        ok = atomic_write_md(target, "content", max_retries=3)
        assert ok is True
        assert call_count["n"] == 2

    def test_all_retries_exhausted(self, tmp_path, monkeypatch):
        """所有重试都失败返回 False。"""
        target = tmp_path / "test.md"

        def always_fail(*args, **kwargs):
            raise OSError("persistent failure")

        monkeypatch.setattr(os, "replace", always_fail)
        ok = atomic_write_md(target, "content", max_retries=2)
        assert ok is False

    def test_tmp_cleaned_up_on_failure(self, tmp_path, monkeypatch):
        """失败后临时文件被清理。"""
        target = tmp_path / "test.md"

        def always_fail(*args, **kwargs):
            raise OSError("failure")

        monkeypatch.setattr(os, "replace", always_fail)
        atomic_write_md(target, "content", max_retries=1)
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert not tmp_files
