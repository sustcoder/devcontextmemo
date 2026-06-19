"""知识注入服务 — 三层注入路由 + AGENTS.md 生成。

三层注入架构（knowledge-delivery.yaml）：
    L1: AGENTS.md 恒常注入（S1/S2 + KW，每次会话自动，≤4K tokens）
    L2: get_knowledge 按需检索（S1/S2 + KH/KY, S3/S4 + 任意 Depth）
    L3: get_experience 经验检索（S5 + 任意 Depth）

注入路由推导表：
    S1/S2 + KW → L1（恒常注入）
    S1/S2 + KH/KY → L2（按需检索）
    S3/S4 + 任意 Depth → L2（按需检索）
    S5 + 任意 Depth → L3（经验检索）

Token 截断策略（L1 预算 4K）：
    优先级 1: S1-KW（原则级，不可截断）
    优先级 2: L0-S2-KW（全局架构，至少 3 条）
    优先级 3: L1-S2-KW（领域架构，按校准时效降序）

设计依据：``domain/knowledge-delivery.yaml``
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from devcontext.storage.search import SearchEngine, SearchResult
from devcontext.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)

# Token 预算
L1_TOKEN_BUDGET = 4096

# 三层注入
LAYER_L1 = "L1"
LAYER_L2 = "L2"
LAYER_L3 = "L3"

# Token 估算（简化：1 中文字 ≈ 1 token）
CHARS_PER_TOKEN = 2


class InjectionLayer:
    """注入层级。"""

    L1 = LAYER_L1
    L2 = LAYER_L2
    L3 = LAYER_L3


class InjectionService:
    """知识注入服务。

    Args:
        sqlite_store: SQLiteStore 实例。
        search_engine: SearchEngine 实例。
        knowledge_dir: 知识目录（AGENTS.md 输出位置）。
    """

    def __init__(
        self,
        sqlite_store: SQLiteStore,
        search_engine: SearchEngine,
        knowledge_dir: str | Path | None = None,
    ) -> None:
        self.db = sqlite_store
        self.search = search_engine
        self.knowledge_dir = Path(knowledge_dir) if knowledge_dir else Path(".devContextMemo")

    @staticmethod
    def route(stability: str, depth: str) -> str:
        """注入路由推导。

        根据稳定性 + 深度推导注入层级。

        Args:
            stability: 稳定性 S1-S5。
            depth: 深度 KW/KH/KY。

        Returns:
            注入层级 L1/L2/L3。

        Raises:
            ValueError: 参数非法。
        """
        if stability not in ("S1", "S2", "S3", "S4", "S5"):
            raise ValueError(f"Invalid stability: {stability}")
        if depth not in ("KW", "KH", "KY"):
            raise ValueError(f"Invalid depth: {depth}")

        # L1: S1/S2 + KW
        if stability in ("S1", "S2") and depth == "KW":
            return LAYER_L1

        # L2: S1/S2 + KH/KY, S3/S4 + 任意
        if stability in ("S1", "S2", "S3", "S4"):
            return LAYER_L2

        # L3: S5
        return LAYER_L3

    def generate_agents_md(self) -> Path:
        """生成 AGENTS.md 草稿（L1 恒常注入内容）。

        收集 S1/S2 + KW 知识，按 Token 截断策略生成 Markdown。

        Returns:
            生成的草稿文件路径（.devContextMemo/staging/AGENTS.knowledge.draft.md）。
        """
        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT id, title, domain, uri, confidence, granularity, stability, depth, "
            "last_calibrated_at FROM knowledge_index "
            "WHERE status IN ('active', 'cold') "
            "AND stability IN ('S1', 'S2') AND depth = 'KW' "
            "ORDER BY stability ASC, last_calibrated_at DESC"
        ).fetchall()

        # Token 截断
        content_lines: list[str] = ["# 项目知识（自动生成）\n"]
        token_used = 200  # 标题预留
        truncated_count = 0

        for row in rows:
            kid, title, domain, uri, confidence, granularity, stability, depth, last_cal = row
            # 读取 MD 正文（截取摘要）
            summary = self._read_summary(uri)
            line = (
                f"## {title}\n- 稳定性: {stability} | 深度: {depth} | 领域: {domain}\n- {summary}\n"
            )
            line_tokens = len(line) // CHARS_PER_TOKEN

            if token_used + line_tokens > L1_TOKEN_BUDGET:
                truncated_count += 1
                continue

            content_lines.append(line)
            token_used += line_tokens

        if truncated_count > 0:
            content_lines.append(f"\n<!-- 已截断 {truncated_count} 条知识 -->\n")

        # 写入草稿
        draft_dir = self.knowledge_dir / "staging"
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = draft_dir / "AGENTS.knowledge.draft.md"
        draft_path.write_text("\n".join(content_lines), encoding="utf-8")

        logger.info("Generated AGENTS.md draft: %d items, ~%d tokens", len(rows), token_used)
        return draft_path

    def build_l2_response(
        self, results: list[SearchResult], max_tokens: int = 2048
    ) -> dict[str, Any]:
        """构建 L2 按需检索响应。

        Args:
            results: 搜索结果列表。
            max_tokens: 最大 token 数。

        Returns:
            L2 响应 dict：
            - ``items``: 知识摘要列表
            - ``total``: 总数
            - ``truncated``: 是否截断
            - ``layer``: "L2"
        """
        items: list[dict[str, Any]] = []
        token_used = 0
        for r in results:
            summary = self._read_summary(r.uri)
            item = {
                "id": r.id,
                "title": r.title,
                "domain": r.domain,
                "confidence": r.confidence,
                "snippet": r.snippet,
                "uri": r.uri,
                "summary": summary[:500],
            }
            item_tokens = len(summary) // CHARS_PER_TOKEN
            if token_used + item_tokens > max_tokens:
                break
            items.append(item)
            token_used += item_tokens

        return {
            "items": items,
            "total": len(items),
            "truncated": len(items) < len(results),
            "layer": LAYER_L2,
        }

    def build_l3_response(self, query: str, max_tokens: int = 1024) -> dict[str, Any]:
        """构建 L3 经验检索响应。

        L3 仅检索 S5 知识。

        Args:
            query: 搜索查询。
            max_tokens: 最大 token 数。

        Returns:
            L3 响应 dict。
        """
        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT id, title, domain, uri, confidence FROM knowledge_index "
            "WHERE status IN ('active', 'cold') AND stability = 'S5' "
            "AND (title LIKE ? OR domain LIKE ?) "
            "ORDER BY confidence DESC LIMIT 10",
            [f"%{query}%", f"%{query}%"],
        ).fetchall()

        items: list[dict[str, Any]] = []
        token_used = 0
        for row in rows:
            summary = self._read_summary(row[3])
            item = {
                "id": row[0],
                "title": row[1],
                "domain": row[2],
                "confidence": row[4],
                "summary": summary[:300],
            }
            item_tokens = len(summary) // CHARS_PER_TOKEN
            if token_used + item_tokens > max_tokens:
                break
            items.append(item)
            token_used += item_tokens

        return {
            "items": items,
            "total": len(items),
            "layer": LAYER_L3,
        }

    @staticmethod
    def _read_summary(uri: str, max_chars: int = 500) -> str:
        """从 MD 文件读取摘要。"""
        if not uri:
            return ""
        path = Path(uri)
        if not path.exists():
            return ""
        content = path.read_text(encoding="utf-8")
        # 提取 frontmatter 之后的正文
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                body = parts[2].strip()
                return body[:max_chars]
        return content[:max_chars]
