"""资源服务 — Resource Track CRUD + 语义分块 + FTS5 搜索。

提供资源的增删改查、语义分块（markdown-it-py AST）、FTS5 索引同步。

Spec 依据：``docs/superpowers/specs/2026-06-19-Phase1-数据源偏离度调研与修复方案-V1.0.md`` §6.1-6.3
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from devcontext.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)

_MAX_RESOURCE_SIZE = 100 * 1024 * 1024

_RESOURCE_TYPES = frozenset({"requirements", "specs", "design", "api", "schema"})

_TYPE_INFERENCE: dict[str, str] = {
    "prd": "requirements",
    "requirement": "requirements",
    "spec": "specs",
    "api": "api",
    "design": "design",
    "arch": "design",
    "schema": "schema",
    ".sql": "schema",
    ".prisma": "schema",
}


class ResourceService:
    """资源轨服务。

    Args:
        sqlite_store: SQLiteStore 实例。
        resources_dir: .devContextMemo/resources/ 目录路径。
    """

    def __init__(self, sqlite_store: SQLiteStore, resources_dir: str | Path) -> None:
        """初始化资源服务。

        Args:
            sqlite_store: SQLiteStore 实例。
            resources_dir: .devContextMemo/resources/ 目录路径。
        """
        self.db = sqlite_store
        self.resources_dir = Path(resources_dir)

    def add(
        self,
        source_path: str | Path,
        resource_type: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """添加资源（复制 → 分块 → 索引）。

        Args:
            source_path: 源文件路径。
            resource_type: 显式指定类型，None 则自动推断。
            reason: 添加原因（触发知识提炼，Phase 1 仅记录）。

        Returns:
            {"resource_id": "...", "type": "...", "content_hash": "...", "blocks": N}

        Raises:
            FileNotFoundError: 源文件不存在。
            ValueError: 文件过大 / 类型非法。
        """
        source = Path(source_path).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        if not source.is_file():
            raise ValueError(f"Source must be a file: {source}")

        size = source.stat().st_size
        if size > _MAX_RESOURCE_SIZE:
            raise ValueError(
                f"File too large: {size / 1024 / 1024:.1f}MB (max 100MB)"
            )

        if resource_type is None:
            resource_type = self._infer_type(source)
        if resource_type not in _RESOURCE_TYPES:
            raise ValueError(
                f"Invalid resource type: {resource_type!r}. "
                f"Must be one of {sorted(_RESOURCE_TYPES)}"
            )

        content = source.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()[:16]

        conn = self.db.get_connection()
        existing = conn.execute(
            "SELECT resource_id FROM resources WHERE content_hash = ? AND deleted_at IS NULL",
            [content_hash],
        ).fetchone()
        if existing:
            return {
                "resource_id": existing[0],
                "type": resource_type,
                "content_hash": content_hash,
                "blocks": 0,
                "status": "unchanged",
                "message": "Resource with identical content already exists",
            }

        resource_id = f"res_{content_hash}"

        target_dir = self.resources_dir / resource_type
        target_dir.mkdir(parents=True, exist_ok=True)
        target_name = source.name
        target_path = target_dir / target_name
        counter = 1
        while target_path.exists():
            stem = source.stem
            target_path = target_dir / f"{stem}_{counter}{source.suffix}"
            counter += 1
        target_path.write_bytes(content)

        blocks = self._chunk_markdown(target_path)
        title = self._extract_title(target_path)

        now = self._now_iso()
        uri = str(target_path.relative_to(self.resources_dir.parent))
        conn.execute(
            """INSERT INTO resources (resource_id, uri, type, source_path, content_hash,
               version, title, block_count, added_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            [
                resource_id,
                uri,
                resource_type,
                str(source),
                content_hash,
                title,
                len(blocks),
                now,
                now,
            ],
        )

        for idx, block in enumerate(blocks):
            block_id = f"blk_{hashlib.sha256(block['content'].encode()).hexdigest()[:16]}"
            block_hash = hashlib.sha256(block["content"].encode()).hexdigest()[:16]
            conn.execute(
                """INSERT INTO resource_blocks (block_id, resource_id, block_type,
                   block_index, content, content_hash, parent_block_id, extra_meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    block_id,
                    resource_id,
                    block["type"],
                    idx,
                    block["content"],
                    block_hash,
                    block.get("parent_block_id"),
                    json.dumps(block.get("metadata", {}), ensure_ascii=False),
                ],
            )
            if self.db.fts_available:
                try:
                    conn.execute(
                        "INSERT INTO resource_blocks_fts "
                        "(block_id, resource_id, block_type, content) "
                        "VALUES (?, ?, ?, ?)",
                        [block_id, resource_id, block["type"], block["content"]],
                    )
                except Exception:
                    pass

        conn.commit()

        return {
            "resource_id": resource_id,
            "type": resource_type,
            "content_hash": content_hash,
            "blocks": len(blocks),
            "title": title,
            "uri": uri,
        }

    def list(self, resource_type: str | None = None) -> list[dict[str, Any]]:
        """列出所有资源。

        Args:
            resource_type: 类型过滤（可选）。

        Returns:
            资源元数据列表。
        """
        conn = self.db.get_connection()
        if resource_type:
            rows = conn.execute(
                "SELECT * FROM resources WHERE type = ? AND deleted_at IS NULL "
                "ORDER BY added_at DESC",
                [resource_type],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM resources WHERE deleted_at IS NULL ORDER BY added_at DESC"
            ).fetchall()
        columns = [d[0] for d in conn.execute("SELECT * FROM resources LIMIT 0").description]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def get(self, resource_id: str) -> dict[str, Any] | None:
        """获取资源元数据（含块列表）。

        Args:
            resource_id: 资源 ID。

        Returns:
            资源记录 dict，或 None。
        """
        conn = self.db.get_connection()
        columns = [d[0] for d in conn.execute("SELECT * FROM resources LIMIT 0").description]
        row = conn.execute(
            "SELECT * FROM resources WHERE resource_id = ?", [resource_id]
        ).fetchone()
        if not row:
            return None
        result = dict(zip(columns, row, strict=False))
        result["blocks"] = self.get_blocks(resource_id)
        return result

    def get_blocks(self, resource_id: str) -> list[dict[str, Any]]:
        """获取资源的所有块。

        Args:
            resource_id: 资源 ID。

        Returns:
            块记录列表。
        """
        conn = self.db.get_connection()
        columns = [
            d[0] for d in conn.execute("SELECT * FROM resource_blocks LIMIT 0").description
        ]
        rows = conn.execute(
            "SELECT * FROM resource_blocks WHERE resource_id = ? ORDER BY block_index",
            [resource_id],
        ).fetchall()
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def search(
        self, query: str, resource_type: str | None = None, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """FTS5 全文搜索资源块。

        Args:
            query: 搜索关键词。
            resource_type: 类型过滤。
            top_k: 返回条数。

        Returns:
            匹配的块列表（含资源元数据）。
        """
        conn = self.db.get_connection()
        try:
            if resource_type:
                rows = conn.execute(
                    """SELECT rbf.block_id, rbf.resource_id, rbf.block_type, rbf.content,
                              r.type as resource_type, r.title, r.uri, r.source_path
                       FROM resource_blocks_fts rbf
                       JOIN resource_blocks rb ON rbf.block_id = rb.block_id
                       JOIN resources r ON rb.resource_id = r.resource_id
                       WHERE resource_blocks_fts MATCH ? AND r.type = ? AND r.deleted_at IS NULL
                       ORDER BY rank LIMIT ?""",
                    [query, resource_type, top_k],
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT rbf.block_id, rbf.resource_id, rbf.block_type, rbf.content,
                              r.type as resource_type, r.title, r.uri, r.source_path
                       FROM resource_blocks_fts rbf
                       JOIN resource_blocks rb ON rbf.block_id = rb.block_id
                       JOIN resources r ON rb.resource_id = r.resource_id
                       WHERE resource_blocks_fts MATCH ? AND r.deleted_at IS NULL
                       ORDER BY rank LIMIT ?""",
                    [query, top_k],
                ).fetchall()
            results = [dict(row) for row in rows]
            if results:
                return results
            return self._fallback_search(query, resource_type, top_k)
        except Exception:
            return self._fallback_search(query, resource_type, top_k)

    def remove(self, resource_id: str) -> bool:
        """软删除资源。

        Args:
            resource_id: 资源 ID。

        Returns:
            True 如果删除成功。
        """
        conn = self.db.get_connection()
        now = self._now_iso()
        conn.execute(
            "UPDATE resources SET deleted_at = ? WHERE resource_id = ? AND deleted_at IS NULL",
            [now, resource_id],
        )
        conn.commit()
        return conn.total_changes > 0

    def get_links(self, resource_id: str) -> list[dict[str, Any]]:
        """获取资源→知识链接。

        Args:
            resource_id: 资源 ID。

        Returns:
            链接记录列表。
        """
        conn = self.db.get_connection()
        columns = [
            d[0]
            for d in conn.execute("SELECT * FROM resource_knowledge_links LIMIT 0").description
        ]
        rows = conn.execute(
            "SELECT * FROM resource_knowledge_links WHERE resource_id = ? ORDER BY created_at",
            [resource_id],
        ).fetchall()
        return [dict(zip(columns, row, strict=False)) for row in rows]

    @staticmethod
    def _chunk_markdown(file_path: Path) -> list[dict[str, Any]]:
        """使用 markdown-it-py 对 MD 文件进行语义分块。

        5 类原子块：heading / paragraph / table / code / list。

        Args:
            file_path: MD 文件路径。

        Returns:
            分块列表，每个块含 type/content/metadata。
        """
        from markdown_it import MarkdownIt

        md = MarkdownIt("commonmark", {"breaks": True, "html": False})
        content = file_path.read_text(encoding="utf-8")
        tokens = md.parse(content)

        blocks: list[dict[str, Any]] = []
        text_buffer: list[str] = []
        current_section: list[str] = []

        def _flush_text() -> None:
            if text_buffer:
                text = " ".join(text_buffer).strip()
                if text and not _is_boilerplate(text):
                    blocks.append(
                        {
                            "type": "paragraph",
                            "content": text,
                            "metadata": {"section_path": list(current_section)},
                        }
                    )
                text_buffer.clear()

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token.type == "heading_open":
                _flush_text()
                level = int(token.tag[1])
                # Trim current_section to this heading level
                while len(current_section) >= level:
                    current_section.pop()
                i += 1
                if i < len(tokens):
                    content_token = tokens[i]
                    heading_text = content_token.content.strip()
                    current_section.append(heading_text)
                    if heading_text and not _is_boilerplate(heading_text):
                        blocks.append(
                            {
                                "type": "heading",
                                "content": heading_text,
                                "metadata": {"section_path": list(current_section[:-1])},
                            }
                        )
                i += 1  # skip heading_close
                continue

            if token.type == "fence":
                _flush_text()
                code = token.content.strip()
                if code:
                    blocks.append(
                        {
                            "type": "code",
                            "content": code,
                            "metadata": {
                                "section_path": list(current_section),
                                "code_lang": token.info or "",
                            },
                        }
                    )

            elif token.type == "inline":
                text_buffer.append(token.content)

            elif token.type in ("softbreak", "hardbreak"):
                text_buffer.append(" ")

            i += 1

        _flush_text()
        return blocks

    def _fallback_search(
        self, query: str, resource_type: str | None, top_k: int
    ) -> list[dict[str, Any]]:
        """FTS5 不可用时的 LIKE 降级搜索。

        Args:
            query: 搜索查询字符串。
            resource_type: 资源类型过滤，None 表示不过滤。
            top_k: 返回结果数上限。

        Returns:
            匹配的资源块列表。
        """
        conn = self.db.get_connection()
        like_query = f"%{query}%"
        if resource_type:
            rows = conn.execute(
                """SELECT rb.block_id, rb.resource_id, rb.block_type, rb.content,
                          r.type as resource_type, r.title, r.uri, r.source_path
                   FROM resource_blocks rb
                   JOIN resources r ON rb.resource_id = r.resource_id
                   WHERE rb.content LIKE ? AND r.type = ? AND r.deleted_at IS NULL
                   LIMIT ?""",
                [like_query, resource_type, top_k],
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT rb.block_id, rb.resource_id, rb.block_type, rb.content,
                          r.type as resource_type, r.title, r.uri, r.source_path
                   FROM resource_blocks rb
                   JOIN resources r ON rb.resource_id = r.resource_id
                   WHERE rb.content LIKE ? AND r.deleted_at IS NULL
                   LIMIT ?""",
                [like_query, top_k],
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _infer_type(source: Path) -> str:
        """从文件名推断资源类型。

        Args:
            source: 源文件路径。

        Returns:
            推断的资源类型字符串。
        """
        name_lower = source.name.lower()
        for keyword, rtype in _TYPE_INFERENCE.items():
            if keyword in name_lower:
                return rtype
        parent = source.parent.name.lower()
        for keyword, rtype in _TYPE_INFERENCE.items():
            if keyword in parent:
                return rtype
        return "design"

    @staticmethod
    def _extract_title(file_path: Path) -> str | None:
        """提取文档 H1 标题。

        Args:
            file_path: 文档文件路径。

        Returns:
            H1 标题文本，或 None。
        """
        content = file_path.read_text(encoding="utf-8")
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return None

    @staticmethod
    def _now_iso() -> str:
        """返回当前 UTC 时间 ISO 8601 字符串。

        Returns:
            当前 UTC 时间的 ISO 8601 字符串。
        """
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()


def _is_boilerplate(text: str) -> bool:
    """检查是否为样板措辞（不进入分块）。

    Args:
        text: 待检查文本。

    Returns:
        True 如果 text 匹配样板措辞模式。
    """
    boilerplate_patterns = [
        "本文档描述了",
        "如右图所示",
        "修订记录",
        "版本历史",
        "目录",
        "Table of Contents",
        "TOC",
    ]
    return any(p in text for p in boilerplate_patterns)
