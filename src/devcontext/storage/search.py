"""FTS5 全文搜索 + BM25 排序 + 候选 top-k 过滤。

提供知识检索能力，返回 top-k 候选 + 相关性打分。

V2.0 状态过滤（对齐 schema V1.1 §2.3）：
    可检索状态：active, cold, pending_review, draft, candidate
    排除状态：staged（未审核）, stale（即将删除）, deprecated（已废弃）
    confidence ≥ 0.4（低质知识不注入）

设计依据：``docs/devContextMemo-SQLite-Schema-详细设计-V1.1.md`` §2.3
"""

from __future__ import annotations

import logging
from typing import Any

from devcontext.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)

# 可检索的 V2.0 状态（对齐 schema V1.1 §2.3）
SEARCHABLE_STATUSES = ("active", "cold", "pending_review", "draft", "candidate")

# 最低 confidence 阈值
MIN_CONFIDENCE = 0.4

# 默认 top-k
DEFAULT_TOP_K = 10


class SearchResult:
    """单条搜索结果。

    Attributes:
        id: 知识 ID。
        title: 标题。
        domain: 领域。
        uri: MD 文件路径。
        confidence: 置信度。
        score: BM25 相关性得分。
        snippet: 匹配片段。
    """

    def __init__(
        self,
        id: str,
        title: str,
        domain: str,
        uri: str,
        confidence: float,
        score: float,
        snippet: str = "",
    ) -> None:
        self.id = id
        self.title = title
        self.domain = domain
        self.uri = uri
        self.confidence = confidence
        self.score = score
        self.snippet = snippet

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "domain": self.domain,
            "uri": self.uri,
            "confidence": self.confidence,
            "score": round(self.score, 4),
            "snippet": self.snippet,
        }


class SearchEngine:
    """FTS5 全文搜索引擎。

    Args:
        sqlite_store: SQLiteStore 实例（需已 init_db）。
    """

    def __init__(self, sqlite_store: SQLiteStore) -> None:
        self.db = sqlite_store

    def search(
        self,
        query: str,
        *,
        domain: str | None = None,
        depth: str | None = None,
        stability_min: str | None = None,
        top_k: int = DEFAULT_TOP_K,
        confidence_min: float = MIN_CONFIDENCE,
    ) -> list[SearchResult]:
        """FTS5 全文搜索 + BM25 排序。

        Args:
            query: 搜索查询（FTS5 MATCH 语法）。
            domain: 领域过滤（None 不限）。
            depth: 深度过滤（KW/KH/KY，None 不限）。
            stability_min: 稳定性下限（S1-S5，None 不限）。
            top_k: 返回前 K 条。
            confidence_min: 最低置信度。

        Returns:
            SearchResult 列表（按 score 降序）。
        """
        if not self.db.fts_available:
            logger.warning("FTS5 not available, falling back to LIKE search")
            return self._fallback_search(query, domain, top_k, confidence_min)

        conn = self.db.get_connection()

        # 构建 SQL（对齐 schema V1.1 §2.3）
        sql = """
            SELECT k.id, k.title, k.domain, k.uri, k.confidence,
                   k.granularity, k.stability, k.depth,
                   bm25(knowledge_fts) as score,
                   snippet(knowledge_fts, 0, '<b>', '</b>', '...', 32) as snippet
            FROM knowledge_fts
            JOIN knowledge_index k ON k.rowid = knowledge_fts.rowid
            WHERE knowledge_fts MATCH ?
              AND k.status IN ({})
              AND k.confidence >= ?
        """.format(", ".join("?" * len(SEARCHABLE_STATUSES)))

        params: list[Any] = [query, *SEARCHABLE_STATUSES, confidence_min]

        if domain:
            sql += " AND k.domain = ?"
            params.append(domain)
        if depth:
            sql += " AND k.depth = ?"
            params.append(depth)
        if stability_min:
            sql += self._stability_clause(stability_min)
            params.extend(self._stability_values(stability_min))

        sql += " ORDER BY score DESC LIMIT ?"
        params.append(top_k * 3)  # 过采样 3 倍

        try:
            rows = conn.execute(sql, params).fetchall()
        except Exception as e:
            logger.error("FTS5 search failed: %s, falling back", e)
            return self._fallback_search(query, domain, top_k, confidence_min)

        # FTS5 对 CJK 分词有限，返回空时回退到 LIKE
        if not rows:
            logger.debug("FTS5 returned empty for %r, falling back to LIKE", query)
            return self._fallback_search(query, domain, top_k, confidence_min)

        results: list[SearchResult] = []
        for row in rows:
            results.append(
                SearchResult(
                    id=row[0],
                    title=row[1],
                    domain=row[2],
                    uri=row[3],
                    confidence=row[4],
                    score=row[8] if row[8] is not None else 0.0,
                    snippet=row[9] if row[9] else "",
                )
            )

        # 相对阈值过滤：topScore × 0.15 以下丢弃，第 1 名永远保留
        if results:
            top_score = results[0].score
            threshold = top_score * 0.15
            filtered = [r for r in results if r.score >= threshold or r is results[0]]
            results = filtered[:top_k]

        return results

    def _fallback_search(
        self, query: str, domain: str | None, top_k: int, confidence_min: float
    ) -> list[SearchResult]:
        """LIKE 回退搜索（FTS5 不可用或 CJK 分词失败时）。

        对 CJK 文本，FTS5 的 unicode61 分词器不按字分词，
        导致 MATCH 查询返回空。此方法用 LIKE 做回退。
        score 设为 1.0（保证相对阈值过滤不丢弃结果）。
        """
        conn = self.db.get_connection()
        sql = """
            SELECT id, title, domain, uri, confidence
            FROM knowledge_index
            WHERE status IN ({})
              AND confidence >= ?
              AND (title LIKE ? OR domain LIKE ?)
        """.format(", ".join("?" * len(SEARCHABLE_STATUSES)))
        params = [*SEARCHABLE_STATUSES, confidence_min, f"%{query}%", f"%{query}%"]
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        sql += " ORDER BY confidence DESC LIMIT ?"
        params.append(top_k)
        rows = conn.execute(sql, params).fetchall()
        return [SearchResult(r[0], r[1], r[2], r[3], r[4], 1.0, r[1]) for r in rows]

    @staticmethod
    def _stability_clause(stability_min: str) -> str:
        """构建稳定性过滤 SQL。"""
        values = SearchEngine._stability_values(stability_min)
        placeholders = ", ".join("?" * len(values))
        return f" AND k.stability IN ({placeholders})"

    @staticmethod
    def _stability_values(stability_min: str) -> list[str]:
        """根据 stability_min 返回包含的稳定性值列表。"""
        all_stabilities = ["S1", "S2", "S3", "S4", "S5"]
        try:
            idx = all_stabilities.index(stability_min)
            return all_stabilities[: idx + 1]
        except ValueError:
            return all_stabilities
