"""资源操作 Schema — Pydantic 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResourceAddRequest(BaseModel):
    """add_resource 请求 Schema。"""

    path: str = Field(..., description="源文件路径")
    type: str | None = Field(
        None,
        description="资源类型: requirements|specs|design|api|schema",
    )
    reason: str | None = Field(None, description="添加原因（触发知识提炼）")


class ResourceAddResponse(BaseModel):
    """add_resource 响应 Schema。"""

    resource_id: str
    type: str
    content_hash: str
    blocks: int
    title: str | None = None
    uri: str | None = None
    status: str = "created"
    message: str | None = None
