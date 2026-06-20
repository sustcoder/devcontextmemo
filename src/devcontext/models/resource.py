"""资源轨数据模型 — SQLModel 类（resources + resource_blocks + 链接表）。

对应 specs §6.2 资源轨 DB Schema 的 5 张表。
"""

from sqlmodel import Field, SQLModel


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


class Resource(SQLModel, table=True):
    """资源元数据表 — resources。

    Attributes:
        resource_id: 资源 ID，如 "res_a1b2c3d4"。
        uri: 资源在 .devContextMemo/ 下的相对路径。
        type: 资源类型 requirements|specs|design|api|schema。
        source_path: 原始文件路径（用户视角）。
        content_hash: SHA-256 哈希，用于增量检测。
        version: 版本号。
        title: 文档标题（H1）。
        block_count: 语义分块数量。
        added_at: 添加时间 ISO 8601。
        updated_at: 更新时间 ISO 8601。
        deleted_at: 软删除时间（NULL=未删除）。
        extra_meta: JSON 扩展元数据。
    """

    __tablename__ = "resources"

    resource_id: str = Field(primary_key=True)
    uri: str = Field(nullable=False, unique=True)
    type: str = Field(nullable=False)
    source_path: str = Field(nullable=False)
    content_hash: str = Field(nullable=False)
    version: int = Field(default=1, nullable=False)
    title: str | None = Field(default=None)
    block_count: int = Field(default=0, nullable=False)
    added_at: str = Field(default_factory=_now_iso, nullable=False)
    updated_at: str = Field(default_factory=_now_iso, nullable=False)
    deleted_at: str | None = Field(default=None)
    extra_meta: str = Field(default="{}", nullable=False)


class ResourceBlock(SQLModel, table=True):
    """资源原子块表 — resource_blocks。

    Attributes:
        block_id: 块 ID，如 "blk_a1b2c3d4"。
        resource_id: 所属资源 ID。
        block_type: heading|paragraph|table|code|list。
        block_index: 在文档中的顺序。
        content: 块原文。
        content_hash: 块级 SHA-256。
        parent_block_id: 嵌套父块 ID（可选）。
        extra_meta: JSON 扩展（行号、代码语言、章节路径）。
    """

    __tablename__ = "resource_blocks"

    block_id: str = Field(primary_key=True)
    resource_id: str = Field(nullable=False, foreign_key="resources.resource_id")
    block_type: str = Field(nullable=False)
    block_index: int = Field(nullable=False)
    content: str = Field(nullable=False)
    content_hash: str = Field(nullable=False)
    parent_block_id: str | None = Field(default=None)
    extra_meta: str = Field(default="{}", nullable=False)


class ResourceKnowledgeLink(SQLModel, table=True):
    """资源↔知识链接表 — resource_knowledge_links。

    Attributes:
        link_id: 链接 ID，如 "lnk_a1b2c3d4"。
        resource_id: 资源 ID。
        block_id: 关联到的具体块（可选）。
        knowledge_id: 知识 ID。
        link_type: derived_from|references|contradicts|updates。
        confidence: 链接置信度 0-1。
        created_at: 创建时间。
        created_by: 提取方式 llm_extraction|manual|git_hook。
    """

    __tablename__ = "resource_knowledge_links"

    link_id: str = Field(primary_key=True)
    resource_id: str = Field(nullable=False, foreign_key="resources.resource_id")
    block_id: str | None = Field(default=None)
    knowledge_id: str = Field(nullable=False, foreign_key="knowledge_index.id")
    link_type: str = Field(nullable=False)
    confidence: float = Field(default=1.0, nullable=False)
    created_at: str = Field(default_factory=_now_iso, nullable=False)
    created_by: str | None = Field(default=None)


class KnowledgeKnowledgeLink(SQLModel, table=True):
    """知识↔知识关系表 — knowledge_knowledge_links。

    Attributes:
        link_id: 链接 ID。
        knowledge_id_a: 源知识 ID。
        knowledge_id_b: 目标知识 ID。
        relation: merged_from|superseded_by|contradicts。
        occurred_at: LLM 判定时间戳。
        created_at: 创建时间。
        created_by: 判定方式（默认 llm_dream）。
    """

    __tablename__ = "knowledge_knowledge_links"

    link_id: str = Field(primary_key=True)
    knowledge_id_a: str = Field(nullable=False, foreign_key="knowledge_index.id")
    knowledge_id_b: str = Field(nullable=False, foreign_key="knowledge_index.id")
    relation: str = Field(nullable=False)
    occurred_at: str = Field(default_factory=_now_iso, nullable=False)
    created_at: str = Field(default_factory=_now_iso, nullable=False)
    created_by: str = Field(default="llm_dream", nullable=False)
