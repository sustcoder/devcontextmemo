"""Markdown 文件存储 — 读写 + Frontmatter 解析。

知识条目的 MD 文件权威存储（SSoT）。DB 索引派生自 MD。

三目录设计（依据 ``docs/devContextMemo-目录划分-晋升规则-修改检测-深度调研-V1.0.md``）：
- ``staging/``    ← 待审核知识，日期前缀命名（``YYYYMMDD-{title}.md``）
- ``knowledge/``  ← 已采纳知识，按领域子目录（``{domain}/{title}.md``）
- ``deprecated/`` ← 已废弃知识

写入顺序（依据 ``docs/devContextMemo-原子写入与路径校验-设计-V1.0.md``）：
MD first → DB second。本模块仅负责 MD 原子写入，DB 同步由 Phase 4 Writer 调用
``to_db_dict()`` 映射后实现。

Frontmatter 字段（14 个，Q3 决策「基础 + Phase 3 前瞻」）：
id, title, domain, sub_domain, granularity, stability, depth, status,
confidence, code_verified, concept_tags, source_session, created_at, updated_at
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import yaml

from .atomic import (
    atomic_write_md,
    sanitize_path_segment,
    validate_safe_path,
)

# Frontmatter 必填字段（写入时校验）
_REQUIRED_FIELDS = (
    "id",
    "title",
    "granularity",
    "stability",
    "depth",
    "status",
    "confidence",
    "created_at",
    "updated_at",
)

# 全部受管理的 frontmatter 字段（有序，用于稳定输出）
_MANAGED_FIELDS = (
    "id",
    "title",
    "domain",
    "sub_domain",
    "granularity",
    "stability",
    "depth",
    "knowledge_type",       # Phase 1
    "status",
    "confidence",
    "code_verified",
    "concept_tags",
    "decision_detail",      # Phase 1 (JSON string)
    "source_session",
    "created_at",
    "updated_at",
)

# 文件名最大长度（不含 .md 后缀）
_FILENAME_MAX_LEN = 60

# 非法文件名字符（Windows + POSIX 交集 + 安全考虑）
_FILENAME_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class MarkdownStore:
    """Markdown 知识文件存储。

    负责知识的 MD 文件原子写入、读取与 frontmatter 解析。
    不直接操作 DB——调用方通过 ``to_db_dict()`` 获取 DB 映射后自行写入。

    Args:
        staging_dir: staging 目录路径（待审核知识）。
        knowledge_dir: knowledge 目录路径（已采纳知识，按 domain 子目录）。
        deprecated_dir: deprecated 目录路径（已废弃知识）。
    """

    def __init__(
        self,
        staging_dir: str | Path,
        knowledge_dir: str | Path,
        deprecated_dir: str | Path,
    ) -> None:
        self.staging_dir = Path(staging_dir)
        self.knowledge_dir = Path(knowledge_dir)
        self.deprecated_dir = Path(deprecated_dir)

    # ------------------------------------------------------------------
    # 公开写入接口
    # ------------------------------------------------------------------

    def write_to_staging(self, record: dict[str, Any]) -> Path:
        """写入 staging 目录（待审核知识）。

        文件名格式：``YYYYMMDD-{title}.md``（日期前缀方便按时间排序）。

        Args:
            record: 知识记录，必须包含 ``_REQUIRED_FIELDS`` + ``content``（正文）。

        Returns:
            写入的 MD 文件绝对路径。

        Raises:
            ValueError: 缺少必填字段或 content 为空。
            PathTraversalError: title 包含路径穿越。
        """
        self._validate_record(record)
        title = record["title"]
        filename = self._build_staging_filename(title)
        # staging 直接在 staging_dir 下，无子目录
        safe_path = validate_safe_path(self.staging_dir, filename)
        md_content = self._build_md_content(record, safe_path)
        if not atomic_write_md(safe_path, md_content):
            raise OSError(f"Failed to write MD file (retries exhausted): {safe_path}")
        return safe_path

    def write_to_knowledge(self, record: dict[str, Any]) -> Path:
        """写入 knowledge 目录（已采纳知识，按 domain 子目录）。

        文件名格式：``{domain}/{title}.md``。

        Args:
            record: 知识记录，必须包含 ``_REQUIRED_FIELDS`` + ``content`` + ``domain``。

        Returns:
            写入的 MD 文件绝对路径。

        Raises:
            ValueError: 缺少必填字段/domain/content 为空。
            PathTraversalError: domain 或 title 包含路径穿越。
        """
        self._validate_record(record)
        domain = record.get("domain", "").strip()
        if not domain:
            raise ValueError("write_to_knowledge requires non-empty 'domain'")
        title = record["title"]
        filename = self._build_knowledge_filename(domain, title)
        # knowledge/{domain}/{title}.md，基目录为 knowledge_dir
        safe_path = validate_safe_path(self.knowledge_dir, filename)
        md_content = self._build_md_content(record, safe_path)
        if not atomic_write_md(safe_path, md_content):
            raise OSError(f"Failed to write MD file (retries exhausted): {safe_path}")
        return safe_path

    # ------------------------------------------------------------------
    # 公开读取接口
    # ------------------------------------------------------------------

    def read(self, md_path: str | Path) -> dict[str, Any]:
        """读取 MD 文件并解析 frontmatter + 正文。

        Args:
            md_path: MD 文件路径。

        Returns:
            知识记录 dict，包含全部 frontmatter 字段 + ``content``（正文）。
            ``concept_tags`` 解析为 list，``code_verified`` 解析为 int。

        Raises:
            FileNotFoundError: 文件不存在。
            ValueError: frontmatter 格式错误。
        """
        path = Path(md_path)
        if not path.exists():
            raise FileNotFoundError(f"MD file not found: {path}")
        raw = path.read_text(encoding="utf-8")
        frontmatter, body = self._parse_frontmatter(raw)
        record = dict(frontmatter)
        record["content"] = body
        # 类型规范化
        if "code_verified" in record and record["code_verified"] is not None:
            record["code_verified"] = int(record["code_verified"])
        if "concept_tags" in record and isinstance(record["concept_tags"], str):
            try:
                record["concept_tags"] = json.loads(record["concept_tags"])
            except (json.JSONDecodeError, TypeError):
                # frontmatter 可能已是 list（yaml 解析）
                pass
        if "confidence" in record and record["confidence"] is not None:
            record["confidence"] = float(record["confidence"])
        return record

    # ------------------------------------------------------------------
    # DB 映射
    # ------------------------------------------------------------------

    def to_db_dict(self, record: dict[str, Any], md_path: str | Path) -> dict[str, Any]:
        """将知识记录映射为 ``knowledge_index`` 表的 dict。

        供 Phase 4 Writer 调用，将 MD record 转换为 DB INSERT 参数。
        不含 ``used_count`` / ``last_used_at`` / ``last_calibrated_at`` /
        ``calibration_status`` / ``embedding`` / ``prune_priority`` /
        ``certainty`` / ``freshness``——这些字段由后续 Phase 按需填充。

        Args:
            record: 知识记录（含 frontmatter 字段 + content）。
            md_path: MD 文件路径（用于填充 ``uri``）。

        Returns:
            knowledge_index 表字段映射 dict。
        """
        concept_tags = record.get("concept_tags")
        if concept_tags is None:
            concept_tags_json: str | None = None
        elif isinstance(concept_tags, (list, tuple)):
            concept_tags_json = json.dumps(list(concept_tags), ensure_ascii=False)
        else:
            # 已是字符串
            concept_tags_json = str(concept_tags)

        return {
            "id": record["id"],
            "title": record["title"],
            "domain": record.get("domain", ""),
            "sub_domain": record.get("sub_domain", ""),
            "granularity": record["granularity"],
            "stability": record["stability"],
            "depth": record["depth"],
            "knowledge_type": record.get("knowledge_type"),
            "decision_detail": record.get("decision_detail"),
            "status": record["status"],
            "confidence": float(record.get("confidence", 0.0)),
            "code_verified": int(record.get("code_verified", 0)),
            "concept_tags": concept_tags_json,
            "source_session": record.get("source_session"),
            "uri": str(md_path),
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }

    # ------------------------------------------------------------------
    # 内部：记录校验与内容构建
    # ------------------------------------------------------------------

    def _validate_record(self, record: dict[str, Any]) -> None:
        """校验记录必填字段 + content 非空。"""
        missing = [f for f in _REQUIRED_FIELDS if not record.get(f)]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
        content = record.get("content", "")
        if not content or not str(content).strip():
            raise ValueError("record content must be non-empty")

    def _build_md_content(self, record: dict[str, Any], md_path: Path) -> str:
        """构建完整 MD 内容（frontmatter + 正文）。

        Args:
            record: 知识记录。
            md_path: 目标路径（用于填充 uri 字段）。

        Returns:
            完整 MD 字符串。
        """
        frontmatter = self._build_frontmatter(record, md_path)
        body = str(record.get("content", "")).strip()
        return f"---\n{frontmatter}---\n\n{body}\n"

    def _build_frontmatter(self, record: dict[str, Any], md_path: Path) -> str:
        """构建 YAML frontmatter 字符串（有序，14 字段）。

        只输出非 None 的字段，保持 frontmatter 简洁。

        Args:
            record: 知识记录。
            md_path: 目标路径（uri 字段）。

        Returns:
            YAML frontmatter 文本（含末尾换行，不含 ``---`` 分隔符）。
        """
        data: dict[str, Any] = {}
        for field in _MANAGED_FIELDS:
            val = record.get(field)
            if val is None:
                continue
            data[field] = val
        # uri 由实际写入路径决定
        data["uri"] = str(md_path)
        # concept_tags 统一为 list（yaml 可读）
        if "concept_tags" in data and isinstance(data["concept_tags"], str):
            try:
                data["concept_tags"] = json.loads(data["concept_tags"])
            except (json.JSONDecodeError, TypeError):
                pass
        # 有序输出，不排序键，不用 flow style（list 用 block 形式）
        yaml_text = yaml.dump(
            data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        )
        return yaml_text  # type: ignore[no-any-return]

    def _parse_frontmatter(self, raw: str) -> tuple[dict[str, Any], str]:
        """解析 MD 文本的 frontmatter 与正文。

        Args:
            raw: MD 文件原始文本。

        Returns:
            (frontmatter_dict, body_str)。

        Raises:
            ValueError: frontmatter 格式错误（缺少 ``---`` 分隔或 YAML 解析失败）。
        """
        if not raw.startswith("---"):
            raise ValueError("MD file must start with '---' frontmatter delimiter")
        # 分割：---\n<yaml>\n---\n<body>
        parts = raw.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Malformed frontmatter: missing closing '---'")
        yaml_text = parts[1]
        body = parts[2].lstrip("\n")
        try:
            frontmatter = yaml.safe_load(yaml_text) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Failed to parse frontmatter YAML: {e}") from e
        if not isinstance(frontmatter, dict):
            raise ValueError("Frontmatter must be a YAML mapping")
        return frontmatter, body

    # ------------------------------------------------------------------
    # 内部：文件名生成
    # ------------------------------------------------------------------

    def _build_staging_filename(self, title: str) -> str:
        """生成 staging 文件名：``YYYYMMDD-{safe_title}.md``。

        Args:
            title: 知识标题。

        Returns:
            文件名（不含目录）。
        """
        date_prefix = dt.datetime.now().strftime("%Y%m%d")
        safe_title = self._safe_filename_segment(title)
        return f"{date_prefix}-{safe_title}.md"

    def _build_knowledge_filename(self, domain: str, title: str) -> str:
        """生成 knowledge 相对路径：``{domain}/{safe_title}.md``。

        Args:
            domain: 领域目录名。
            title: 知识标题。

        Returns:
            相对 knowledge_dir 的路径（含 domain 子目录）。
        """
        safe_domain = self._safe_filename_segment(domain)
        safe_title = self._safe_filename_segment(title)
        return f"{safe_domain}/{safe_title}.md"

    @staticmethod
    def _safe_filename_segment(text: str) -> str:
        """将任意文本转为安全的文件名段。

        移除非法字符、折叠空白、截断长度。

        Args:
            text: 原始文本。

        Returns:
            安全的文件名段（不含扩展名）。
        """
        # 先 sanitize 去掉路径分隔符和控制字符
        seg = sanitize_path_segment(text)
        # 替换文件名非法字符为下划线
        seg = _FILENAME_INVALID_CHARS.sub("_", seg)
        # 折叠连续空白为单下划线
        seg = re.sub(r"\s+", "_", seg).strip("_")
        if not seg:
            seg = "untitled"
        # 截断
        if len(seg) > _FILENAME_MAX_LEN:
            seg = seg[:_FILENAME_MAX_LEN].rstrip("_")
        return seg
