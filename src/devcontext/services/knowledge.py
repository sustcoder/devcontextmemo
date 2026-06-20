"""知识服务 — CRUD + 检索编排。

提供知识五操作的统一入口：
    create: 新建知识（写入 MD + DB）
    update: 更新知识（旧版本 → deprecated，新版本 → staging）
    replace: 替换知识（直接覆盖，保留修订链）
    supplement: 追加补充（不修改原文）
    deprecate: 废弃知识（→ deprecated/）

检索编排：
    get_by_id / list_by_domain / search（委托 SearchEngine）

设计依据：``docs/devContextMemo-知识更新-冲突检测-冲突解决-深度设计-V1.0.md`` §一
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from devcontext.models.enums import is_valid_transition
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.search import SearchEngine, SearchResult
from devcontext.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识服务。

    Args:
        sqlite_store: SQLiteStore 实例。
        markdown_store: MarkdownStore 实例。
        search_engine: SearchEngine 实例。
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        markdown_store: MarkdownStore,
        search_engine: SearchEngine,
    ) -> None:
        self.db = sqlite_store
        self.md = markdown_store
        self.search_engine = search_engine

    # ==================================================================
    # 检索
    # ==================================================================

    def get_by_id(self, knowledge_id: str) -> dict[str, Any] | None:
        """按 ID 获取知识。

        Args:
            knowledge_id: 知识 ID。

        Returns:
            知识记录 dict，或 None。
        """
        conn = self.db.get_connection()
        columns = [d[0] for d in conn.execute("SELECT * FROM knowledge_index LIMIT 0").description]
        row = conn.execute("SELECT * FROM knowledge_index WHERE id = ?", [knowledge_id]).fetchone()
        if not row:
            return None
        return dict(zip(columns, row, strict=False))

    def list_by_domain(self, domain: str, status: str | None = None) -> list[dict[str, Any]]:
        """按领域列出知识。

        Args:
            domain: 领域。
            status: 状态过滤（None 不限）。

        Returns:
            知识记录列表。
        """
        conn = self.db.get_connection()
        columns = [d[0] for d in conn.execute("SELECT * FROM knowledge_index LIMIT 0").description]
        if status:
            rows = conn.execute(
                "SELECT * FROM knowledge_index WHERE domain = ? AND status = ? ORDER BY created_at",
                [domain, status],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_index WHERE domain = ? ORDER BY created_at",
                [domain],
            ).fetchall()
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def search(self, query: str, **kwargs: Any) -> list[SearchResult]:
        """全文搜索（委托 SearchEngine）。"""
        return self.search_engine.search(query, **kwargs)

    # ==================================================================
    # 五操作
    # ==================================================================

    def create(self, record: dict[str, Any]) -> str:
        """新建知识。

        Args:
            record: 知识记录（含 knowledge_text/granularity/stability/depth/domain/confidence）。

        Returns:
            新建的 knowledge_id。
        """
        import datetime as _dt

        kid = f"kw-{_dt.datetime.now().strftime('%Y%m%d')}-{record.get('_seq', '001')}"
        now = _dt.datetime.now(_dt.UTC).isoformat()

        md_record = {
            "id": kid,
            "title": record.get("title", record.get("knowledge_text", "")[:30]),
            "domain": record.get("domain", ""),
            "sub_domain": record.get("sub_domain", ""),
            "granularity": record.get("granularity", "L2"),
            "stability": record.get("stability", "S3"),
            "depth": record.get("depth", "KH"),
            "knowledge_type": record.get("knowledge_type", "fact"),
            "status": "staged",
            "confidence": record.get("confidence", 0.5),
            "code_verified": record.get("code_verified", 0),
            "concept_tags": record.get("concept_tags", []),
            "source_session": record.get("source_session"),
            "created_at": now,
            "updated_at": now,
            "content": record.get("knowledge_text", ""),
        }

        # 绿色通道决策
        confidence = float(record.get("confidence", 0.5))
        if confidence >= 0.95:
            md_path = self.md.write_to_knowledge(md_record)
        else:
            md_path = self.md.write_to_staging(md_record)

        # 写 DB
        db_record = self.md.to_db_dict(md_record, md_path)
        self._insert_db(db_record)

        logger.info("Created knowledge %s → %s", kid, md_path)
        return kid

    def update(self, knowledge_id: str, new_content: str, reason: str = "") -> str:
        """更新知识（保留旧版本）。

        旧版本 → deprecated/（superseded_by），新版本 → staging/。

        Args:
            knowledge_id: 旧知识 ID。
            new_content: 新内容。
            reason: 更新原因。

        Returns:
            新版本的 knowledge_id。
        """
        old = self.get_by_id(knowledge_id)
        if not old:
            raise ValueError(f"Knowledge not found: {knowledge_id}")

        # 旧版本废弃
        self.deprecate(knowledge_id, reason=f"superseded: {reason}")

        # 创建新版本
        new_record = dict(old)
        new_record["knowledge_text"] = new_content
        new_record["confidence"] = old.get("confidence", 0.5)
        new_id = self.create(new_record)

        # 更新修订链
        conn = self.db.get_connection()
        conn.execute(
            "UPDATE knowledge_index SET superseded_by = ?, successor_id = ? WHERE id = ?",
            [new_id, new_id, knowledge_id],
        )
        conn.commit()

        return new_id

    def replace(self, knowledge_id: str, new_content: str) -> None:
        """替换知识（直接覆盖 MD 文件）。

        Args:
            knowledge_id: 知识 ID。
            new_content: 新内容。
        """
        record = self.get_by_id(knowledge_id)
        if not record:
            raise ValueError(f"Knowledge not found: {knowledge_id}")
        uri = record.get("uri", "")
        if uri:
            path = __import__("pathlib").Path(uri)
            if path.exists():
                # 保留 frontmatter，替换正文
                content = path.read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    new_full = f"{parts[0]}---{parts[1]}---\n\n{new_content}\n"
                    path.write_text(new_full, encoding="utf-8")
                else:
                    path.write_text(new_content, encoding="utf-8")

    def supplement(self, knowledge_id: str, supplement_text: str) -> None:
        """追加补充（不修改原文）。

        Args:
            knowledge_id: 知识 ID。
            supplement_text: 补充内容。
        """
        record = self.get_by_id(knowledge_id)
        if not record:
            raise ValueError(f"Knowledge not found: {knowledge_id}")
        uri = record.get("uri", "")
        if uri:
            path = __import__("pathlib").Path(uri)
            if path.exists():
                with open(path, "a", encoding="utf-8") as f:
                    f.write(
                        f"\n\n---\n\n## 补充 ({dt.datetime.now().strftime('%Y-%m-%d')})\n\n{supplement_text}\n"
                    )

    def deprecate(self, knowledge_id: str, reason: str = "") -> None:
        """废弃知识。

        Args:
            knowledge_id: 知识 ID。
            reason: 废弃原因。
        """
        record = self.get_by_id(knowledge_id)
        if not record:
            raise ValueError(f"Knowledge not found: {knowledge_id}")

        current_status = record["status"]
        if not is_valid_transition(current_status, "deprecated"):
            raise ValueError(f"Invalid transition: {current_status} → deprecated")

        conn = self.db.get_connection()
        now = dt.datetime.now(dt.UTC).isoformat()
        conn.execute(
            "UPDATE knowledge_index SET status = 'deprecated', "
            "deprecation_reason = ?, updated_at = ? WHERE id = ?",
            [reason or "manual", now, knowledge_id],
        )
        conn.commit()

        # 文件移动到 deprecated/
        uri = record.get("uri", "")
        if uri:
            path = __import__("pathlib").Path(uri)
            if path.exists():
                dest = self.md.deprecated_dir / path.name
                self.md.deprecated_dir.mkdir(parents=True, exist_ok=True)
                try:
                    path.rename(dest)
                    conn.execute(
                        "UPDATE knowledge_index SET uri = ? WHERE id = ?",
                        [str(dest), knowledge_id],
                    )
                    conn.commit()
                except OSError as e:
                    logger.error("Failed to move %s: %s", path, e)

    def _insert_db(self, db_record: dict[str, Any]) -> None:
        """INSERT knowledge_index 记录。"""
        conn = self.db.get_connection()
        cols = ", ".join(db_record.keys())
        placeholders = ", ".join("?" * len(db_record))
        conn.execute(
            f"INSERT OR REPLACE INTO knowledge_index ({cols}) VALUES ({placeholders})",
            list(db_record.values()),
        )
        conn.commit()
