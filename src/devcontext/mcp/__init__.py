"""MCP Server 层 — Tool 注册 + Resource 定义。

暴露给 OpenCode 等 AI 编程工具的知识检索接口。

Phase 8（V1.1）：3 个 Tool（query_knowledge/write_knowledge/calibrate_knowledge）。
不依赖 fastmcp 框架，用纯函数 + MCPServer 注册表模式。
"""

from devcontext.mcp.resources import list_knowledge_resources, read_knowledge_resource
from devcontext.mcp.server import TOOL_REGISTRY, MCPServer
from devcontext.mcp.tools import (
    ToolResponse,
    ValidationError,
    calibrate_knowledge,
    query_knowledge,
    write_knowledge,
)

__all__ = [
    "MCPServer",
    "TOOL_REGISTRY",
    "ToolResponse",
    "ValidationError",
    "calibrate_knowledge",
    "query_knowledge",
    "write_knowledge",
    "read_knowledge_resource",
    "list_knowledge_resources",
]
