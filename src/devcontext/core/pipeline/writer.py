"""Step 5: MD → DB 原子写入。

职责：
1. 读取 knowledge JSONL（Step 4 输出，含 hash + dedup 字段）
2. 对每条知识：
   - 生成 knowledge_id（kw-{date}-{seq}）
   - 绿色通道决策：confidence ≥ 0.95 → write_to_knowledge，否则 → write_to_staging
   - 调用 MarkdownStore 写 MD 文件（MD first）
   - 调用 to_db_dict 映射 + INSERT knowledge_index（DB second）
   - FTS5 同步（如果 SQLiteStore 可用）
3. 返回 WriteResult 列表（含 knowledge_id/md_path/db_success/status）

写入顺序（Phase 3 原子写入设计）：
MD first → DB second
- MD 写成功后 DB 失败 → MD 完整保留，下次 mtime 检测重建索引
- MD 写失败 → 不写 DB，返回失败

设计依据：
- ``docs/devContextMemo-原子写入与路径校验-设计-V1.0.md`` §二
- ``docs/devContextMemo-目录划分-晋升规则-修改检测-深度调研-V1.0.md`` §4.2（绿色通道）
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any

from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)

# 绿色通道阈值（confidence ≥ 0.95 → 直接写 knowledge/）
GREEN_CHANNEL_THRESHOLD = 0.95


class WriteResult:
    """单条知识写入结果。

    Attributes:
        knowledge_id: 知识 ID。
        md_path: MD 文件路径（写入成功时）。
        md_success: MD 是否写入成功。
        db_success: DB 是否写入成功。
        status: 写入后状态（staged/draft）。
        target: 写入目标（staging/knowledge）。
        error: 错误信息（失败时）。
    """

    def __init__(
        self,
        knowledge_id: str,
        md_path: str | None = None,
        md_success: bool = False,
        db_success: bool = False,
        status: str = "staged",
        target: str = "staging",
        error: str = "",
    ) -> None:
        self.knowledge_id = knowledge_id
        self.md_path = md_path
        self.md_success = md_success
        self.db_success = db_success
        self.status = status
        self.target = target
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "md_path": self.md_path,
            "md_success": self.md_success,
            "db_success": self.db_success,
            "status": self.status,
            "target": self.target,
            "error": self.error,
        }


class Writer:
    """Step 5 写入器。

    将去重后的知识写入 MD 文件 + DB 索引（MD first → DB second）。

    Args:
        markdown_store: MarkdownStore 实例。
        sqlite_store: SQLiteStore 实例（可选，None 则跳过 DB 写入）。
    """

    def __init__(
        self,
        markdown_store: MarkdownStore,
        sqlite_store: SQLiteStore | None = None,
    ) -> None:
        self.md_store = markdown_store
        self.db_store = sqlite_store
        self._id_counter = 0

    def process(self, knowledge_path: str | Path) -> list[WriteResult]:
        """处理 knowledge JSONL，写入 MD + DB。

        Args:
            knowledge_path: knowledge JSONL 文件路径（Step 4 输出）。

        Returns:
            WriteResult 列表（每条知识一个）。

        Raises:
            FileNotFoundError: 文件不存在。
        """
        knowledge_path = Path(knowledge_path)
        if not knowledge_path.exists():
            raise FileNotFoundError(f"Knowledge file not found: {knowledge_path}")

        records = self._read_jsonl(knowledge_path)
        results: list[WriteResult] = []

        for rec in records:
            # 跳过完全重复
            if rec.get("is_duplicate"):
                logger.info("Skipping duplicate: %s", rec.get("knowledge_text", "")[:50])
                continue
            result = self._write_one(rec)
            results.append(result)

        logger.info("Wrote %d knowledge items", len(results))
        return results

    def _write_one(self, record: dict[str, Any]) -> WriteResult:
        """写入单条知识（MD first → DB second）。

        Args:
            record: knowledge 记录。

        Returns:
            WriteResult。
        """
        knowledge_id = self._generate_id()
        confidence = float(record.get("confidence", 0.0))
        now = dt.datetime.now().isoformat()

        # 构建 MD record（Phase 3 frontmatter 字段）
        md_record = {
            "id": knowledge_id,
            "title": self._derive_title(record.get("knowledge_text", "")),
            "domain": record.get("domain", ""),
            "sub_domain": "",
            "granularity": record.get("granularity", "L2"),
            "stability": record.get("stability", "S3"),
            "depth": record.get("depth", "KH"),
            "status": record.get("status", "candidate"),
            "confidence": confidence,
            "code_verified": record.get("code_verified", 0),
            "concept_tags": self._extract_concept_tags(record),
            "source_session": record.get("session_id"),
            "created_at": now,
            "updated_at": now,
            "content": record.get("knowledge_text", ""),
        }

        # 绿色通道决策
        use_green_channel = confidence >= GREEN_CHANNEL_THRESHOLD

        # Step 1: MD first
        try:
            if use_green_channel:
                md_path = self.md_store.write_to_knowledge(md_record)
                target = "knowledge"
            else:
                md_path = self.md_store.write_to_staging(md_record)
                target = "staging"
        except Exception as e:
            logger.error("MD write failed for %s: %s", knowledge_id, e)
            return WriteResult(
                knowledge_id=knowledge_id,
                md_success=False,
                error=f"MD write failed: {e}",
            )

        # Step 2: DB second（如果 SQLiteStore 可用）
        db_success = False
        if self.db_store is not None:
            try:
                db_record = self.md_store.to_db_dict(md_record, md_path)
                self._insert_db(db_record)
                db_success = True
                # FTS5 同步
                if self.db_store.fts_available:
                    self.db_store._sync_fts(
                        rowid=self._get_rowid(knowledge_id),
                        title=md_record["title"],
                        keywords=",".join(md_record.get("concept_tags") or []),
                        summary=record.get("knowledge_text", "")[:200],
                    )
            except Exception as e:
                # DB 写失败：MD 已完整保留，下次 mtime 检测重建索引
                logger.error(
                    "DB write failed for %s, MD intact at %s: %s",
                    knowledge_id,
                    md_path,
                    e,
                )

        return WriteResult(
            knowledge_id=knowledge_id,
            md_path=str(md_path),
            md_success=True,
            db_success=db_success,
            status=md_record["status"],
            target=target,
        )

    def _generate_id(self) -> str:
        """生成知识 ID：kw-{YYYYMMDD}-{seq}。"""
        self._id_counter += 1
        date_str = dt.datetime.now().strftime("%Y%m%d")
        return f"kw-{date_str}-{self._id_counter:03d}"

    @staticmethod
    def _derive_title(text: str) -> str:
        """从知识文本派生标题（取前 30 字符）。"""
        text = text.strip().replace("\n", " ")
        return text[:30] + ("..." if len(text) > 30 else "")

    @staticmethod
    def _extract_concept_tags(record: dict[str, Any]) -> list[str]:
        """从记录提取 concept_tags（基于 entities 名称）。"""
        entities = record.get("entities", [])
        return [f"#{e['name']}" for e in entities if isinstance(e, dict) and e.get("name")][:5]

    def _insert_db(self, db_record: dict[str, Any]) -> None:
        """INSERT knowledge_index 记录。"""
        conn = self.db_store.get_connection()
        columns = ", ".join(db_record.keys())
        placeholders = ", ".join("?" * len(db_record))
        conn.execute(
            f"INSERT OR REPLACE INTO knowledge_index ({columns}) VALUES ({placeholders})",
            list(db_record.values()),
        )
        conn.commit()

    def _get_rowid(self, knowledge_id: str) -> int:
        """查询 knowledge_id 对应的 rowid。"""
        conn = self.db_store.get_connection()
        row = conn.execute(
            "SELECT rowid FROM knowledge_index WHERE id = ?",
            [knowledge_id],
        ).fetchone()
        return row[0] if row else 0

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        """读取 JSONL 文件。"""
        records: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
