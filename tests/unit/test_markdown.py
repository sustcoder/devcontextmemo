"""Unit tests for storage/markdown.py — MarkdownStore 写入/读取/映射。"""

import json
from pathlib import Path

import pytest

from devcontext.storage.atomic import PathTraversalError
from devcontext.storage.markdown import MarkdownStore


# =============================================================================
# write_to_staging
# =============================================================================

class TestWriteToStaging:
    """staging 目录写入（日期前缀命名）。"""

    def test_creates_md_file(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_staging(dict(sample_knowledge_record))
        assert path.exists()
        assert path.suffix == ".md"

    def test_filename_has_date_prefix(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_staging(dict(sample_knowledge_record))
        # YYYYMMDD- 8 位日期 + 短横线
        name = path.name
        assert len(name) >= 9 and name[8] == "-"
        # 日期部分应为数字
        assert name[:8].isdigit()

    def test_writes_to_staging_dir(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_staging(dict(sample_knowledge_record))
        assert path.parent == markdown_store.staging_dir.resolve()

    def test_creates_staging_dir_if_missing(self, tmp_path, sample_knowledge_record):
        store = MarkdownStore(
            staging_dir=tmp_path / "staging",
            knowledge_dir=tmp_path / "knowledge",
            deprecated_dir=tmp_path / "deprecated",
        )
        assert not (tmp_path / "staging").exists()
        path = store.write_to_staging(dict(sample_knowledge_record))
        assert path.exists()
        assert (tmp_path / "staging").exists()


# =============================================================================
# write_to_knowledge
# =============================================================================

class TestWriteToKnowledge:
    """knowledge 目录写入（按 domain 子目录）。"""

    def test_creates_md_file(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        assert path.exists()
        assert path.suffix == ".md"

    def test_writes_to_domain_subdir(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        assert path.parent == (markdown_store.knowledge_dir / "order").resolve()

    def test_creates_domain_dir(self, markdown_store, sample_knowledge_record):
        assert not markdown_store.knowledge_dir.exists()
        markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        assert (markdown_store.knowledge_dir / "order").exists()

    def test_empty_domain_rejected(self, markdown_store, sample_knowledge_record):
        record = dict(sample_knowledge_record)
        record["domain"] = ""
        with pytest.raises(ValueError, match="domain"):
            markdown_store.write_to_knowledge(record)

    def test_missing_domain_rejected(self, markdown_store, sample_knowledge_record):
        record = dict(sample_knowledge_record)
        del record["domain"]
        with pytest.raises(ValueError, match="domain"):
            markdown_store.write_to_knowledge(record)


# =============================================================================
# read
# =============================================================================

class TestRead:
    """MD 文件读取与 frontmatter 解析。"""

    def test_read_returns_all_frontmatter_fields(
        self, markdown_store, sample_knowledge_record
    ):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        for field in (
            "id", "title", "domain", "sub_domain", "granularity", "stability",
            "depth", "knowledge_type", "status", "confidence", "code_verified",
            "concept_tags", "source_session", "created_at", "updated_at", "uri",
        ):
            assert field in rec, f"missing field: {field}"

    def test_read_returns_content(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        assert "content" in rec
        assert "幂等校验" in rec["content"]

    def test_read_parses_concept_tags_as_list(
        self, markdown_store, sample_knowledge_record
    ):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        assert rec["concept_tags"] == ["#幂等", "#createOrder"]

    def test_read_parses_code_verified_as_int(
        self, markdown_store, sample_knowledge_record
    ):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        assert rec["code_verified"] == 1
        assert isinstance(rec["code_verified"], int)

    def test_read_parses_confidence_as_float(
        self, markdown_store, sample_knowledge_record
    ):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        assert rec["confidence"] == pytest.approx(0.88)
        assert isinstance(rec["confidence"], float)

    def test_read_nonexistent_file_raises(self, markdown_store, tmp_path):
        with pytest.raises(FileNotFoundError):
            markdown_store.read(tmp_path / "nope.md")

    def test_read_malformed_frontmatter_raises(self, markdown_store, tmp_path):
        bad = tmp_path / "bad.md"
        bad.write_text("no frontmatter here", encoding="utf-8")
        with pytest.raises(ValueError, match="frontmatter"):
            markdown_store.read(bad)


# =============================================================================
# to_db_dict
# =============================================================================

class TestToDbDict:
    """record → knowledge_index 表映射。"""

    def test_contains_all_schema_fields(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        db = markdown_store.to_db_dict(rec, path)
        # schema V1.1 knowledge_index 的 Phase 3 字段子集
        for field in (
            "id", "title", "domain", "sub_domain", "granularity", "stability",
            "depth", "status", "confidence", "code_verified", "concept_tags",
            "source_session", "uri", "created_at", "updated_at",
        ):
            assert field in db, f"missing DB field: {field}"

    def test_concept_tags_serialized_as_json_string(
        self, markdown_store, sample_knowledge_record
    ):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        db = markdown_store.to_db_dict(rec, path)
        assert isinstance(db["concept_tags"], str)
        assert json.loads(db["concept_tags"]) == ["#幂等", "#createOrder"]

    def test_uri_is_md_path(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        db = markdown_store.to_db_dict(rec, path)
        assert db["uri"] == str(path)

    def test_confidence_is_float(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        db = markdown_store.to_db_dict(rec, path)
        assert isinstance(db["confidence"], float)

    def test_code_verified_is_int(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        db = markdown_store.to_db_dict(rec, path)
        assert isinstance(db["code_verified"], int)

    def test_none_concept_tags_becomes_null(
        self, markdown_store, sample_knowledge_record
    ):
        record = dict(sample_knowledge_record)
        record["concept_tags"] = None
        path = markdown_store.write_to_knowledge(record)
        rec = markdown_store.read(path)
        db = markdown_store.to_db_dict(rec, path)
        assert db["concept_tags"] is None


# =============================================================================
# round-trip
# =============================================================================

class TestRoundTrip:
    """write → read → to_db_dict 一致性。"""

    def test_staging_round_trip(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_staging(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        assert rec["id"] == sample_knowledge_record["id"]
        assert rec["title"] == sample_knowledge_record["title"]
        assert rec["domain"] == sample_knowledge_record["domain"]

    def test_knowledge_round_trip(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        rec = markdown_store.read(path)
        db = markdown_store.to_db_dict(rec, path)
        assert db["id"] == sample_knowledge_record["id"]
        assert db["title"] == sample_knowledge_record["title"]
        assert db["domain"] == sample_knowledge_record["domain"]


# =============================================================================
# 路径校验集成 + 输入校验
# =============================================================================

class TestPathSecurityIntegration:
    """MarkdownStore 与 atomic.py 路径校验的集成。"""

    def test_traversal_title_sanitized(self, markdown_store, sample_knowledge_record):
        """title 含 ../ 被清理为安全文件名（不抛错）。"""
        record = dict(sample_knowledge_record)
        record["title"] = "../../etc/passwd"
        path = markdown_store.write_to_knowledge(record)
        assert path.exists()
        assert path.parent == (markdown_store.knowledge_dir / "order").resolve()

    def test_empty_content_rejected(self, markdown_store, sample_knowledge_record):
        record = dict(sample_knowledge_record)
        record["content"] = ""
        with pytest.raises(ValueError, match="content"):
            markdown_store.write_to_staging(record)

    def test_whitespace_content_rejected(self, markdown_store, sample_knowledge_record):
        record = dict(sample_knowledge_record)
        record["content"] = "   \n\t  "
        with pytest.raises(ValueError, match="content"):
            markdown_store.write_to_staging(record)

    def test_missing_required_field_rejected(
        self, markdown_store, sample_knowledge_record
    ):
        record = dict(sample_knowledge_record)
        del record["id"]
        with pytest.raises(ValueError, match="required"):
            markdown_store.write_to_staging(record)


# =============================================================================
# frontmatter 格式
# =============================================================================

class TestFrontmatterFormat:
    """frontmatter 格式与字段完整性。"""

    def test_starts_with_frontmatter_delimiter(
        self, markdown_store, sample_knowledge_record
    ):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---\n")

    def test_has_closing_delimiter(self, markdown_store, sample_knowledge_record):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        content = path.read_text(encoding="utf-8")
        # frontmatter 以 --- 开头，后续应有第二个 ---
        assert content.count("---") >= 2

    def test_all_managed_fields_present(
        self, markdown_store, sample_knowledge_record
    ):
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        content = path.read_text(encoding="utf-8")
        for field in (
            "id:", "title:", "domain:", "sub_domain:", "granularity:",
            "stability:", "depth:", "knowledge_type:", "status:", "confidence:",
            "code_verified:", "concept_tags:", "source_session:", "created_at:",
            "updated_at:", "uri:",
        ):
            assert field in content, f"frontmatter missing: {field}"

    def test_status_uses_lowercase_v11(
        self, markdown_store, sample_knowledge_record
    ):
        """status 字段使用 V1.1 小写状态值。"""
        path = markdown_store.write_to_knowledge(dict(sample_knowledge_record))
        content = path.read_text(encoding="utf-8")
        assert "status: staged" in content

    def test_frontmatter_includes_knowledge_type(
        self, markdown_store, sample_knowledge_record
    ):
        """Verify frontmatter output includes knowledge_type field."""
        record = dict(sample_knowledge_record)
        record["knowledge_type"] = "decision"
        path = markdown_store.write_to_staging(record)
        content = path.read_text(encoding="utf-8")
        assert "knowledge_type: decision" in content
