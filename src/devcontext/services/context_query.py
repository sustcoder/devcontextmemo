"""上下文查询引擎 — 双轨并行检索 + 三级回退。

Facade 层：合并 KnowledgeService（记忆轨）和 ResourceService（资源轨）的检索结果，
按 track 优先级排序，支持三级回退（L1 记忆 → L2 资源段落 → L3 完整资源）。

Spec 依据：``docs/superpowers/specs/2026-06-19-Phase1-数据源偏离度调研与修复方案-V1.0.md`` §6.4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextBundle:
    """双轨查询结果包。

    Attributes:
        memories: 记忆轨结果（知识条目）。
        resources: 资源轨结果（资源块）。
        total: 合并去重后的总数。
        fallback_level: 实际使用的回退层级（1/2/3）。
    """

    memories: list[dict[str, Any]] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    fallback_level: int = 1


class ContextQueryEngine:
    """上下文查询引擎 Facade。

    双轨并行检索，合并排序，三级回退。

    Args:
        knowledge_service: KnowledgeService 实例。
        resource_service: ResourceService 实例。
    """

    def __init__(self, knowledge_service, resource_service) -> None:
        self.knowledge = knowledge_service
        self.resource = resource_service

    def query(
        self,
        question: str,
        top_k_knowledge: int = 5,
        top_k_resource: int = 3,
        layers: list[int] | None = None,
        min_confidence: float = 0.5,
        domain: str | None = None,
    ) -> ContextBundle:
        """双轨并行检索，返回合并后的上下文包。

        Args:
            question: 查询问题。
            top_k_knowledge: 记忆轨返回条数（默认 5）。
            top_k_resource: 资源轨返回条数（默认 3）。
            layers: 限定检索层级 [1,2,3]，None 表示全部。
            min_confidence: 记忆轨最低置信度阈值。
            domain: 领域过滤。

        Returns:
            ContextBundle，含 memories + resources + fallback_level。
        """
        if layers is None:
            layers = [1, 2, 3]

        bundle = ContextBundle()

        # === L1: 记忆轨检索 ===
        if 1 in layers:
            try:
                knowledge_results = self.knowledge.search(
                    question,
                    domain=domain,
                    top_k=top_k_knowledge,
                    confidence_min=min_confidence,
                )
                if knowledge_results:
                    for r in knowledge_results:
                        bundle.memories.append({
                            "id": r.id,
                            "title": r.title,
                            "domain": r.domain,
                            "summary": r.snippet or r.title,
                            "uri": r.uri,
                            "confidence": r.confidence,
                            "score": r.score,
                            "track": "memory",
                        })
            except Exception as e:
                logger.warning("Memory track query failed: %s", e)

        # === L2: 资源轨检索（始终与 L1 并行查询） ===
        if 2 in layers:
            try:
                resource_results = self.resource.search(question, top_k=top_k_resource)
                if resource_results:
                    for r in resource_results:
                        bundle.resources.append({
                            "block_id": r["block_id"],
                            "resource_id": r["resource_id"],
                            "block_type": r["block_type"],
                            "content": r["content"],
                            "resource_type": r.get("resource_type"),
                            "title": r.get("title"),
                            "uri": r.get("uri"),
                            "source_path": r.get("source_path"),
                            "track": "resource",
                        })
                    # 记忆轨无命中时标记回退到 L2
                    if not bundle.memories:
                        bundle.fallback_level = 2
            except Exception as e:
                logger.warning("Resource track query failed: %s", e)

        # === L3: 完整资源文件（兜底） ===
        if 3 in layers and not bundle.memories and not bundle.resources:
            try:
                all_resources = self.resource.list()
                for res in all_resources:
                    if question.lower() in (res.get("title", "") or "").lower():
                        blocks = self.resource.get_blocks(res["resource_id"])
                        bundle.resources.extend([
                            {
                                "block_id": b["block_id"],
                                "resource_id": b["resource_id"],
                                "block_type": b["block_type"],
                                "content": b["content"],
                                "track": "resource",
                                "title": res.get("title"),
                                "uri": res.get("uri"),
                            }
                            for b in blocks
                        ])
                if bundle.resources:
                    bundle.fallback_level = 3
            except Exception as e:
                logger.warning("Full resource fallback failed: %s", e)

        bundle.total = len(bundle.memories) + len(bundle.resources)
        return bundle

    def query_single_track(self, question: str, track: str = "memory", **kwargs) -> list[dict[str, Any]]:
        """单轨查询（兼容已有调用方）。

        Args:
            question: 查询问题。
            track: "memory" 或 "resource"。
            **kwargs: 传递给对应 service 的额外参数。

        Returns:
            搜索结果列表。
        """
        if track == "memory":
            results = self.knowledge.search(question, **kwargs)
            return [
                {
                    "id": r.id, "title": r.title, "domain": r.domain,
                    "summary": r.snippet or r.title, "uri": r.uri,
                    "confidence": r.confidence, "score": r.score, "track": "memory",
                }
                for r in results
            ]
        elif track == "resource":
            return self.resource.search(question, **kwargs)
        else:
            raise ValueError(f"Unknown track: {track!r}. Use 'memory' or 'resource'.")
