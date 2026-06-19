"""审核流程管理 — PENDING_REVIEW/DRAFT → ACTIVE/DEPRECATED 确认。

管理知识条目的审核工作流：
    list_pending: 列出待审核知识（pending_review / draft）
    approve: 采纳（→ active，文件移到 knowledge/）
    reject: 拒绝（→ deprecated，文件移到 deprecated/）
    restore: 恢复（deprecated → staged，文件移回 staging/）

设计依据：``docs/devContextMemo-晋升生命周期-设计-V2.0.md`` T7-T10/T20
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any

from devcontext.models.enums import is_valid_transition
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)


class ReviewResult:
    """审核操作结果。

    Attributes:
        knowledge_id: 知识 ID。
        action: 审核动作（approve/reject/restore）。
        new_status: 新状态。
        moved_to: 文件移动目标（None 表示未移动）。
        success: 是否成功。
        error: 错误信息（失败时）。
    """

    def __init__(
        self,
        knowledge_id: str,
        action: str,
        new_status: str,
        moved_to: str | None = None,
        success: bool = True,
        error: str = "",
    ) -> None:
        self.knowledge_id = knowledge_id
        self.action = action
        self.new_status = new_status
        self.moved_to = moved_to
        self.success = success
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "action": self.action,
            "new_status": self.new_status,
            "moved_to": self.moved_to,
            "success": self.success,
            "error": self.error,
        }


class ReviewService:
    """审核服务。

    Args:
        sqlite_store: SQLiteStore 实例。
        markdown_store: MarkdownStore 实例。
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        markdown_store: MarkdownStore,
    ) -> None:
        self.db = sqlite_store
        self.md = markdown_store

    def list_pending(self, status: str | None = None) -> list[dict[str, Any]]:
        """列出待审核知识。

        Args:
            status: 限定状态（None 则列出 pending_review + draft）。

        Returns:
            待审核知识列表（按 confidence 降序）。
        """
        conn = self.db.get_connection()
        columns = [d[0] for d in conn.execute("SELECT * FROM knowledge_index LIMIT 0").description]
        if status:
            rows = conn.execute(
                "SELECT * FROM knowledge_index WHERE status = ? ORDER BY confidence DESC",
                [status],
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM knowledge_index WHERE status IN ('pending_review', 'draft') "
                "ORDER BY confidence DESC"
            ).fetchall()
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def approve(self, knowledge_id: str) -> ReviewResult:
        """采纳知识（→ active）。

        T7: PENDING_REVIEW → ACTIVE
        T9: DRAFT → ACTIVE

        文件从 staging/ 移到 knowledge/{domain}/。

        Args:
            knowledge_id: 知识 ID。

        Returns:
            ReviewResult。
        """
        record = self._get_record(knowledge_id)
        if not record:
            return ReviewResult(
                knowledge_id, "approve", "", success=False, error="knowledge not found"
            )

        current = record["status"]
        if not is_valid_transition(current, "active"):
            return ReviewResult(
                knowledge_id,
                "approve",
                current,
                success=False,
                error=f"invalid transition: {current} → active",
            )

        # 更新 DB
        self._update_status(knowledge_id, "active")

        # 文件移动：staging → knowledge/{domain}/
        moved_to = self._move_file(
            record, self.md.knowledge_dir / record.get("domain", "uncategorized")
        )

        return ReviewResult(
            knowledge_id=knowledge_id,
            action="approve",
            new_status="active",
            moved_to=moved_to,
        )

    def reject(self, knowledge_id: str, reason: str = "human_rejected") -> ReviewResult:
        """拒绝知识（→ deprecated）。

        T8: PENDING_REVIEW → DEPRECATED
        T10: DRAFT → DEPRECATED

        文件从 staging/ 移到 deprecated/。

        Args:
            knowledge_id: 知识 ID。
            reason: 拒绝原因。

        Returns:
            ReviewResult。
        """
        record = self._get_record(knowledge_id)
        if not record:
            return ReviewResult(
                knowledge_id, "reject", "", success=False, error="knowledge not found"
            )

        current = record["status"]
        if not is_valid_transition(current, "deprecated"):
            return ReviewResult(
                knowledge_id,
                "reject",
                current,
                success=False,
                error=f"invalid transition: {current} → deprecated",
            )

        # 更新 DB
        now = dt.datetime.now(dt.UTC).isoformat()
        conn = self.db.get_connection()
        conn.execute(
            "UPDATE knowledge_index SET status = 'deprecated', "
            "deprecation_reason = ?, updated_at = ? WHERE id = ?",
            [reason, now, knowledge_id],
        )
        conn.commit()

        # 文件移动：staging → deprecated/
        moved_to = self._move_file(record, self.md.deprecated_dir)

        return ReviewResult(
            knowledge_id=knowledge_id,
            action="reject",
            new_status="deprecated",
            moved_to=moved_to,
        )

    def restore(self, knowledge_id: str) -> ReviewResult:
        """恢复知识（deprecated → staged）。

        T20: DEPRECATED → STAGED

        文件从 deprecated/ 移回 staging/。
        restored_count +1（V24：superseded 原因恢复不计数）。

        Args:
            knowledge_id: 知识 ID。

        Returns:
            ReviewResult。
        """
        record = self._get_record(knowledge_id)
        if not record:
            return ReviewResult(
                knowledge_id, "restore", "", success=False, error="knowledge not found"
            )

        current = record["status"]
        if not is_valid_transition(current, "staged"):
            return ReviewResult(
                knowledge_id,
                "restore",
                current,
                success=False,
                error=f"invalid transition: {current} → staged",
            )

        # V24: superseded 原因恢复不计数 restored_count
        deprecation_reason = record.get("deprecation_reason", "")
        now = dt.datetime.now(dt.UTC).isoformat()
        if deprecation_reason != "superseded":
            conn = self.db.get_connection()
            conn.execute(
                "UPDATE knowledge_index SET status = 'staged', "
                "restored_count = restored_count + 1, "
                "deprecation_reason = NULL, updated_at = ? WHERE id = ?",
                [now, knowledge_id],
            )
            conn.commit()
        else:
            self._update_status(knowledge_id, "staged")

        # 文件移动：deprecated → staging/
        moved_to = self._move_file(record, self.md.staging_dir)

        return ReviewResult(
            knowledge_id=knowledge_id,
            action="restore",
            new_status="staged",
            moved_to=moved_to,
        )

    # ==================================================================
    # 内部工具
    # ==================================================================

    def _get_record(self, knowledge_id: str) -> dict[str, Any] | None:
        """获取知识记录。"""
        conn = self.db.get_connection()
        columns = [d[0] for d in conn.execute("SELECT * FROM knowledge_index LIMIT 0").description]
        row = conn.execute("SELECT * FROM knowledge_index WHERE id = ?", [knowledge_id]).fetchone()
        return dict(zip(columns, row, strict=False)) if row else None

    def _update_status(self, knowledge_id: str, new_status: str) -> None:
        """更新状态。"""
        conn = self.db.get_connection()
        now = dt.datetime.now(dt.UTC).isoformat()
        conn.execute(
            "UPDATE knowledge_index SET status = ?, updated_at = ? WHERE id = ?",
            [new_status, now, knowledge_id],
        )
        conn.commit()

    def _move_file(self, record: dict[str, Any], dest_dir: Path) -> str | None:
        """移动 MD 文件。

        Args:
            record: 知识记录。
            dest_dir: 目标目录。

        Returns:
            新文件路径，或 None（移动失败/文件不存在）。
        """
        uri = record.get("uri", "")
        if not uri:
            return None
        src = Path(uri)
        if not src.exists():
            logger.warning("MD file not found for move: %s", src)
            return None

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        try:
            src.rename(dest)
            # 更新 DB uri
            conn = self.db.get_connection()
            conn.execute(
                "UPDATE knowledge_index SET uri = ? WHERE id = ?",
                [str(dest), record["id"]],
            )
            conn.commit()
            logger.info("Moved %s → %s", src, dest)
            return str(dest)
        except OSError as e:
            logger.error("Failed to move %s: %s", src, e)
            return None
