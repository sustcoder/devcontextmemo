"""MCP Resource 模板 — knowledge://{id} 等。

提供 MCP Resource URI 模板，AI 可通过 URI 直接读取知识内容。
"""

from __future__ import annotations

from typing import Any

from devcontext.services.knowledge import KnowledgeService
from devcontext.storage.sqlite import SQLiteStore


def read_knowledge_resource(
    knowledge_service: KnowledgeService,
    knowledge_id: str,
) -> dict[str, Any]:
    """读取 knowledge://{id} resource。

    MCP Resource URI 格式：``knowledge://kw-20260614-001``

    Args:
        knowledge_service: KnowledgeService 实例。
        knowledge_id: 知识 ID。

    Returns:
        Resource 内容 dict：
        - ``uri``: resource URI
        - ``mime_type``: "text/markdown"
        - ``content``: MD 文件完整内容
        - ``metadata``: 知识元数据
    """
    record = knowledge_service.get_by_id(knowledge_id)
    if not record:
        return {
            "uri": f"knowledge://{knowledge_id}",
            "mime_type": "text/markdown",
            "content": None,
            "error": f"knowledge '{knowledge_id}' not found",
        }

    uri_path = record.get("uri", "")
    content = None
    if uri_path:
        from pathlib import Path

        path = Path(uri_path)
        if path.exists():
            content = path.read_text(encoding="utf-8")

    return {
        "uri": f"knowledge://{knowledge_id}",
        "mime_type": "text/markdown",
        "content": content,
        "metadata": {
            "id": record["id"],
            "title": record["title"],
            "domain": record.get("domain", ""),
            "status": record.get("status", ""),
            "confidence": record.get("confidence", 0.0),
        },
    }


def list_knowledge_resources(
    sqlite_store: SQLiteStore,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    """列出可用的 knowledge:// resource。

    Args:
        sqlite_store: SQLiteStore 实例。
        domain: 领域过滤（None 列全部）。

    Returns:
        Resource URI 列表。
    """
    conn = sqlite_store.get_connection()
    if domain:
        rows = conn.execute(
            "SELECT id, title, domain FROM knowledge_index "
            "WHERE status IN ('active', 'cold') AND domain = ? "
            "ORDER BY title",
            [domain],
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, title, domain FROM knowledge_index "
            "WHERE status IN ('active', 'cold') ORDER BY title"
        ).fetchall()

    return [
        {
            "uri": f"knowledge://{row[0]}",
            "title": row[1],
            "domain": row[2],
            "mime_type": "text/markdown",
        }
        for row in rows
    ]
