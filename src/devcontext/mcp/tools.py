"""MCP Tool 函数 — query_knowledge / write_knowledge / calibrate_knowledge。

Phase 1 只做 3 个 Tool（V1.1 设计）：
    query_knowledge: AI 检索知识（FTS5 + 分层返回 L0 摘要 / include_full 完整正文）
    write_knowledge: AI 写入知识（异步入队，返回 task_id）
    calibrate_knowledge: 校准知识（检查是否过时）

输入校验（V1.1 §2.1-B）：
    domain: ^[a-z0-9_-]{1,64}$
    scope: ^(all|domain:[a-z0-9_-]{1,64}|id:kw-[a-z0-9-]+)$
    limit: 1 ≤ limit ≤ 20
    offset: ≥ 0
    content: 0 < len ≤ 10000

设计依据：``docs/devContextMemo-MCP-Tool接口-行业调研与详细设计-V1.1.md``
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from devcontext.services.knowledge import KnowledgeService
from devcontext.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)

# 校验正则
DOMAIN_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
SCOPE_PATTERN = re.compile(r"^(all|domain:[a-z0-9_-]{1,64}|id:kw-[a-z0-9-]+)$")
DEPTH_VALUES = {"KW", "KH", "KY"}
STABILITY_VALUES = {"S1", "S2", "S3", "S4", "S5"}

# 限制
MIN_LIMIT = 1
MAX_LIMIT = 20
MAX_CONTENT_LENGTH = 10000


class ValidationError(Exception):
    """输入校验失败。"""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ToolResponse:
    """Tool 统一响应。"""

    def __init__(self, data: dict[str, Any], status: int = 200) -> None:
        self.data = data
        self.status = status

    def to_dict(self) -> dict[str, Any]:
        return self.data


# =============================================================================
# 输入校验
# =============================================================================


def _validate_domain(domain: str | None) -> None:
    """校验 domain 参数。"""
    if domain is not None and not DOMAIN_PATTERN.match(domain):
        raise ValidationError(
            400,
            f"invalid domain: only [a-z0-9_-] allowed, got '{domain}'",
        )


def _validate_scope(scope: str | None) -> None:
    """校验 scope 参数。"""
    if scope is not None and not SCOPE_PATTERN.match(scope):
        raise ValidationError(
            400,
            "invalid scope format: must be 'all', 'domain:<name>', or 'id:kw-<xxx>'",
        )


def _validate_limit(limit: int | None) -> int:
    """校验 limit 参数。"""
    if limit is None:
        return 5
    if not (MIN_LIMIT <= limit <= MAX_LIMIT):
        raise ValidationError(400, f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}")
    return limit


def _validate_offset(offset: int | None) -> int:
    """校验 offset 参数。"""
    if offset is None:
        return 0
    if offset < 0:
        raise ValidationError(400, "offset must be >= 0")
    return offset


def _validate_depth(depth: str | None) -> None:
    """校验 depth 参数。"""
    if depth is not None and depth not in DEPTH_VALUES:
        raise ValidationError(400, f"depth must be one of {sorted(DEPTH_VALUES)}")


def _validate_stability(stability_min: str | None) -> None:
    """校验 stability_min 参数。"""
    if stability_min is not None and stability_min not in STABILITY_VALUES:
        raise ValidationError(400, f"stability_min must be one of {sorted(STABILITY_VALUES)}")


def _validate_content(content: str) -> None:
    """校验 content 参数。"""
    if not content or not content.strip():
        raise ValidationError(400, "content must be non-empty")
    if len(content) > MAX_CONTENT_LENGTH:
        raise ValidationError(
            400,
            f"content exceeds max length ({MAX_CONTENT_LENGTH} chars)",
        )


# =============================================================================
# Tool 1: query_knowledge
# =============================================================================


def query_knowledge(
    knowledge_service: KnowledgeService,
    *,
    query: str | None = None,
    id: str | None = None,
    domain: str | None = None,
    depth: str | None = None,
    stability_min: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    include_full: bool = False,
) -> ToolResponse:
    """检索知识。

    query 和 id 必须提供其一，且不可同时提供。
    query → FTS5 搜索；id → 精确查询。
    include_full=false 返回 L0 摘要；include_full=true 返回完整正文。

    Args:
        knowledge_service: KnowledgeService 实例。
        query: 自然语言查询（与 id 互斥）。
        id: 知识 ID（与 query 互斥）。
        domain: 领域过滤。
        depth: 深度过滤。
        stability_min: 最低稳定性。
        limit: 返回条数（默认 5，最大 20）。
        offset: 翻页偏移（默认 0）。
        include_full: 是否返回完整正文。

    Returns:
        ToolResponse，data 含 items/total/has_more/next_offset/next_action。

    Raises:
        ValidationError: 参数校验失败。
    """
    # query 和 id 互斥校验
    if not query and not id:
        raise ValidationError(400, "either query or id is required")
    if query and id:
        raise ValidationError(400, "query and id are mutually exclusive")

    # 参数校验
    _validate_domain(domain)
    _validate_depth(depth)
    _validate_stability(stability_min)
    limit = _validate_limit(limit)
    offset = _validate_offset(offset)

    # 按 ID 精确查询
    if id:
        record = knowledge_service.get_by_id(id)
        if not record:
            return ToolResponse(
                {
                    "items": [],
                    "total": 0,
                    "has_more": False,
                    "next_offset": None,
                    "next_action": {"hint": f"knowledge with id '{id}' not found"},
                }
            )
        item = _record_to_item(record, include_full)
        return ToolResponse(
            {
                "items": [item],
                "total": 1,
                "has_more": False,
                "next_offset": None,
                "next_action": (
                    {
                        "tool": "query_knowledge",
                        "hint": "use include_full=true to get full content",
                        "params_example": {"id": id, "include_full": True},
                    }
                    if not include_full
                    else None
                ),
            }
        )

    # FTS5 搜索
    results = knowledge_service.search(
        query,
        domain=domain,
        depth=depth,
        stability_min=stability_min,
        top_k=limit + offset,
        confidence_min=0.4,
    )

    # 翻页
    paginated = results[offset : offset + limit]
    has_more = offset + limit < len(results)
    next_offset = offset + limit if has_more else None

    items = [_search_result_to_item(r, knowledge_service, include_full) for r in paginated]

    return ToolResponse(
        {
            "items": items,
            "total": len(items),
            "has_more": has_more,
            "next_offset": next_offset,
            "next_action": (
                {
                    "tool": "query_knowledge",
                    "hint": (
                        "use id + include_full=true for full content"
                        if items
                        else "no results, try broader query"
                    ),
                    "params_example": (
                        {"id": items[0]["id"], "include_full": True} if items else None
                    ),
                }
                if items
                else {"hint": "未找到相关知识，可以尝试扩大搜索范围或添加新知识"}
            ),
        }
    )


# =============================================================================
# Tool 2: write_knowledge
# =============================================================================


def write_knowledge(
    knowledge_service: KnowledgeService,
    *,
    content: str,
    session_id: str,
    granularity: str | None = None,
    stability: str | None = None,
    depth: str | None = None,
    priority: str = "normal",
) -> ToolResponse:
    """写入知识（异步入队）。

    Args:
        knowledge_service: KnowledgeService 实例。
        content: 知识正文（最大 10000 字符）。
        session_id: 来源 session ID。
        granularity: 粒度 L0-L5（可选，系统推断）。
        stability: 稳定性 S1-S5（可选）。
        depth: 深度 KW/KH/KY（可选）。
        priority: 优先级 normal/high。

    Returns:
        ToolResponse，data 含 task_id/status/message/estimated_time。

    Raises:
        ValidationError: 参数校验失败。
    """
    _validate_content(content)
    if not session_id:
        raise ValidationError(400, "session_id is required")

    if granularity and granularity not in {"L0", "L1", "L2", "L3", "L4", "L5"}:
        raise ValidationError(400, f"invalid granularity: {granularity}")
    if stability and stability not in STABILITY_VALUES:
        raise ValidationError(400, f"invalid stability: {stability}")
    if depth and depth not in DEPTH_VALUES:
        raise ValidationError(400, f"invalid depth: {depth}")

    # 创建知识
    record = {
        "knowledge_text": content,
        "source_session": session_id,
        "granularity": granularity or "L2",
        "stability": stability or "S3",
        "depth": depth or "KH",
        "confidence": 0.5,  # 默认中等置信度，待 Step 2 提炼
        "domain": "uncategorized",  # 待 Step 2 分类
    }
    kid = knowledge_service.create(record)

    return ToolResponse(
        {
            "task_id": f"write-{kid}",
            "status": "accepted",
            "message": f"已入队，将在异步提炼后自动确认。task_id: write-{kid}",
            "estimated_time": "pending (typically 30-120s, depends on LLM latency)",
        }
    )


# =============================================================================
# Tool 3: calibrate_knowledge
# =============================================================================


def calibrate_knowledge(
    sqlite_store: SQLiteStore,
    *,
    scope: str = "all",
    mode: str = "quick",
    since: str | None = None,
) -> ToolResponse:
    """校准知识（检查是否过时）。

    Args:
        sqlite_store: SQLiteStore 实例。
        scope: 校准范围（all / domain:<name> / id:kw-<xxx>）。
        mode: 校准模式（quick/full）。
        since: 仅校准该时间后未校验的知识。

    Returns:
        ToolResponse，data 含 stale_items/total_stale/total_checked。

    Raises:
        ValidationError: 参数校验失败。
    """
    _validate_scope(scope)
    if mode not in ("quick", "full"):
        raise ValidationError(400, f"mode must be 'quick' or 'full', got '{mode}'")

    conn = sqlite_store.get_connection()
    columns = [d[0] for d in conn.execute("SELECT * FROM knowledge_index LIMIT 0").description]

    # 根据 scope 构建查询
    if scope == "all":
        rows = conn.execute(
            "SELECT * FROM knowledge_index WHERE status IN ('active', 'cold', 'stale') "
            "ORDER BY last_calibrated_at ASC NULLS FIRST"
        ).fetchall()
    elif scope.startswith("domain:"):
        domain_name = scope.split(":", 1)[1]
        rows = conn.execute(
            "SELECT * FROM knowledge_index WHERE domain = ? "
            "AND status IN ('active', 'cold', 'stale') "
            "ORDER BY last_calibrated_at ASC NULLS FIRST",
            [domain_name],
        ).fetchall()
    else:  # id:kw-xxx
        kid = scope.split(":", 1)[1]
        rows = conn.execute("SELECT * FROM knowledge_index WHERE id = ?", [kid]).fetchall()

    records = [dict(zip(columns, row, strict=False)) for row in rows]
    total_checked = len(records)

    # 识别 stale 项（简化：last_calibrated_at 为空或超过 90 天）
    import datetime as dt

    now = dt.datetime.now(dt.UTC)
    stale_items: list[dict[str, Any]] = []

    for rec in records:
        last_cal = rec.get("last_calibrated_at")
        is_stale = False
        reason = ""

        if not last_cal:
            is_stale = True
            reason = "never calibrated"
        else:
            try:
                cal_dt = dt.datetime.fromisoformat(last_cal.replace("Z", "+00:00"))
                if cal_dt.tzinfo is None:
                    cal_dt = cal_dt.replace(tzinfo=dt.UTC)
                days_since = (now - cal_dt).days
                if days_since > 90:
                    is_stale = True
                    reason = f"last calibrated {days_since} days ago"
            except (ValueError, TypeError):
                is_stale = True
                reason = "invalid last_calibrated_at"

        if is_stale:
            stale_items.append(
                {
                    "id": rec["id"],
                    "title": rec["title"],
                    "calibration_result": "stale",
                    "reason": reason,
                    "last_verified_at": last_cal,
                    "next_action": {
                        "tool": "dev review",
                        "hint": "建议人工确认或运行 dev review 审核这条知识",
                        "params_example": {"id": rec["id"]},
                    },
                }
            )

    return ToolResponse(
        {
            "stale_items": stale_items,
            "total_stale": len(stale_items),
            "total_checked": total_checked,
        }
    )


# =============================================================================
# 辅助函数
# =============================================================================


def _record_to_item(record: dict[str, Any], include_full: bool) -> dict[str, Any]:
    """将 DB 记录转为响应 item。"""
    item: dict[str, Any] = {
        "id": record["id"],
        "title": record["title"],
        "domain": record.get("domain", ""),
        "granularity": record.get("granularity", ""),
        "stability": record.get("stability", ""),
        "depth": record.get("depth", ""),
        "summary": "",
        "uri": record.get("uri", ""),
        "confidence": record.get("confidence", 0.0),
        "code_verified": record.get("code_verified", 0),
        "prune_priority": record.get("prune_priority", 0.0),
        "concept_tags": json.loads(record["concept_tags"]) if record.get("concept_tags") else [],
        "last_calibrated_at": record.get("last_calibrated_at"),
    }

    if include_full:
        uri = record.get("uri", "")
        if uri:
            path = Path(uri)
            if path.exists():
                content = path.read_text(encoding="utf-8")
                # 提取 frontmatter 之后的正文
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        item["content"] = parts[2].strip()
                    else:
                        item["content"] = content
                else:
                    item["content"] = content
                item["source_missing"] = False
            else:
                item["content"] = None
                item["source_missing"] = True
        else:
            item["content"] = None
            item["source_missing"] = True

    return item


def _search_result_to_item(
    result: Any,
    knowledge_service: KnowledgeService,
    include_full: bool,
) -> dict[str, Any]:
    """将 SearchResult 转为响应 item。"""
    item: dict[str, Any] = {
        "id": result.id,
        "title": result.title,
        "domain": result.domain,
        "uri": result.uri,
        "confidence": result.confidence,
        "summary": result.snippet or result.title,
        "score": result.score,
    }

    if include_full:
        uri = result.uri
        if uri:
            path = Path(uri)
            if path.exists():
                content = path.read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        item["content"] = parts[2].strip()
                    else:
                        item["content"] = content
                else:
                    item["content"] = content
                item["source_missing"] = False
            else:
                item["content"] = None
                item["source_missing"] = True
        else:
            item["content"] = None
            item["source_missing"] = True

    return item


# =============================================================================
# Phase 1 双轨制：资源 Tool（resource_add / resource_search / resource_get_context）
# =============================================================================


def resource_add(
    resource_service,  # ResourceService（避免循环导入，Any 类型标注亦可）
    *,
    path: str,
    type: str | None = None,
    reason: str | None = None,
) -> ToolResponse:
    """添加文档资源（需求/Spec/设计文档）。

    Args:
        resource_service: ResourceService 实例。
        path: 源文件绝对路径。
        type: 资源类型 requirements|specs|design|api|schema（可选，自动推断）。
        reason: 添加原因（触发知识提炼）。

    Returns:
        ToolResponse，data 含 resource_id/type/content_hash/blocks/title/uri。
    """
    if not path or not path.strip():
        raise ValidationError(400, "path is required")
    if type is not None and type not in ("requirements", "specs", "design", "api", "schema"):
        raise ValidationError(400, f"invalid type: {type}")

    from pathlib import Path as _Path

    src = _Path(path).expanduser()
    if not src.exists():
        return ToolResponse(
            {
                "error": f"File not found: {path}",
                "resource_id": None,
            },
            status=404,
        )

    try:
        result = resource_service.add(str(src), resource_type=type, reason=reason)
        return ToolResponse(
            {
                "resource_id": result["resource_id"],
                "type": result["type"],
                "content_hash": result["content_hash"],
                "blocks": result["blocks"],
                "title": result.get("title"),
                "uri": result.get("uri"),
                "status": result.get("status", "created"),
            }
        )
    except ValueError as e:
        return ToolResponse({"error": str(e), "resource_id": None}, status=400)


def resource_search(
    resource_service,  # ResourceService
    *,
    query: str,
    type: str | None = None,
    top_k: int = 5,
) -> ToolResponse:
    """搜索资源块。

    Args:
        resource_service: ResourceService 实例。
        query: 搜索关键词。
        type: 资源类型过滤（可选）。
        top_k: 返回条数（默认 5，最大 20）。

    Returns:
        ToolResponse，data 含 items/total。
    """
    if not query or not query.strip():
        raise ValidationError(400, "query is required")
    if top_k < 1 or top_k > 20:
        raise ValidationError(400, "top_k must be between 1 and 20")
    if type is not None and type not in ("requirements", "specs", "design", "api", "schema"):
        raise ValidationError(400, f"invalid type: {type}")

    results = resource_service.search(query, resource_type=type, top_k=top_k)

    return ToolResponse(
        {
            "items": results,
            "total": len(results),
        }
    )


def resource_get_context(
    resource_service,  # ResourceService
    *,
    resource_id: str,
    section: str | None = None,
) -> ToolResponse:
    """读取资源原文段落。

    Args:
        resource_service: ResourceService 实例。
        resource_id: 资源 ID。
        section: 章节标题过滤（可选，如 "3.1 API 接口"）。

    Returns:
        ToolResponse，data 含 resource/blocks/total_blocks。
    """
    if not resource_id or not resource_id.strip():
        raise ValidationError(400, "resource_id is required")

    resource = resource_service.get(resource_id)
    if not resource:
        return ToolResponse(
            {"error": f"Resource not found: {resource_id}"}, status=404
        )

    blocks = resource.get("blocks", [])
    if section:
        blocks = [
            b
            for b in blocks
            if section.lower() in (b.get("extra_meta", "{}") or "{}").lower()
            or section.lower() in b.get("content", "").lower()
        ]

    return ToolResponse(
        {
            "resource": {
                "resource_id": resource["resource_id"],
                "type": resource["type"],
                "title": resource.get("title"),
                "uri": resource.get("uri"),
                "source_path": resource.get("source_path"),
                "added_at": resource.get("added_at"),
            },
            "blocks": blocks[:20],
            "total_blocks": len(blocks),
            "truncated": len(blocks) > 20,
        }
    )
