"""FastMCP Server — Tool 注册 + 127.0.0.1 绑定。

暴露 3 个 MCP Tool 给 AI 编程工具（OpenCode 等）：
    query_knowledge: 检索知识
    write_knowledge: 写入知识
    calibrate_knowledge: 校准知识

安全配置（V1.1 §6）：
    - 强制绑定 127.0.0.1（禁止 0.0.0.0）
    - domain 参数白名单
    - content 长度限制

设计依据：``docs/devContextMemo-MCP-Tool接口-行业调研与详细设计-V1.1.md``

注意：Phase 8 不依赖 fastmcp 框架（cryptography 编译失败），
改为纯函数 + 手动注册模式。Tool 函数在 mcp/tools.py 中实现，
本模块负责创建服务实例 + 注册 + 启动入口。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from devcontext.config import settings
from devcontext.mcp.tools import (
    ToolResponse,
    ValidationError,
    calibrate_knowledge,
    query_knowledge,
    write_knowledge,
)
from devcontext.services.injection import InjectionService
from devcontext.services.knowledge import KnowledgeService
from devcontext.services.review import ReviewService
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.search import SearchEngine
from devcontext.storage.sqlite import SQLiteStore

logger = logging.getLogger(__name__)

# MCP Tool 注册表
TOOL_REGISTRY: dict[str, dict[str, Any]] = {}


class MCPServer:
    """MCP Server 实例。

    管理 SQLiteStore + 各 Service + Tool 注册。
    不依赖 fastmcp 框架，用纯函数 + 注册表模式。

    Args:
        db_path: SQLite 数据库路径（默认用 config）。
        knowledge_dir: 知识目录（默认用 config）。
        staging_dir: staging 目录。
        deprecated_dir: deprecated 目录。
    """

    def __init__(
        self,
        db_path: str | None = None,
        knowledge_dir: str | None = None,
        staging_dir: str | None = None,
        deprecated_dir: str | None = None,
    ) -> None:
        # 初始化存储层
        self.db = SQLiteStore(db_path or settings.db_path)
        self.db.init_db()

        # 初始化 MD 存储
        self.md_store = MarkdownStore(
            staging_dir=staging_dir or settings.staging_dir,
            knowledge_dir=knowledge_dir or settings.knowledge_dir,
            deprecated_dir=deprecated_dir or settings.deprecated_dir,
        )

        # 初始化服务层
        self.search_engine = SearchEngine(self.db)
        self.knowledge_service = KnowledgeService(self.db, self.md_store, self.search_engine)
        self.injection_service = InjectionService(
            self.db, self.search_engine, knowledge_dir or settings.knowledge_dir
        )
        self.review_service = ReviewService(self.db, self.md_store)

        # 注册 Tool
        self._register_tools()

    def _register_tools(self) -> None:
        """注册 3 个 MCP Tool。"""
        TOOL_REGISTRY["query_knowledge"] = {
            "description": "检索知识（FTS5 + 分层返回）",
            "handler": self._handle_query,
            "parameters": {
                "query": {"type": "string", "required": False, "description": "自然语言查询"},
                "id": {
                    "type": "string",
                    "required": False,
                    "description": "知识 ID（与 query 互斥）",
                },
                "domain": {"type": "string", "required": False},
                "depth": {"type": "string", "required": False, "enum": ["KW", "KH", "KY"]},
                "stability_min": {
                    "type": "string",
                    "required": False,
                    "enum": ["S1", "S2", "S3", "S4", "S5"],
                },
                "limit": {"type": "integer", "required": False, "default": 5, "min": 1, "max": 20},
                "offset": {"type": "integer", "required": False, "default": 0},
                "include_full": {"type": "boolean", "required": False, "default": False},
            },
        }
        TOOL_REGISTRY["write_knowledge"] = {
            "description": "写入知识（异步入队）",
            "handler": self._handle_write,
            "parameters": {
                "content": {"type": "string", "required": True, "max_length": 10000},
                "session_id": {"type": "string", "required": True},
                "granularity": {"type": "string", "required": False},
                "stability": {"type": "string", "required": False},
                "depth": {"type": "string", "required": False},
                "priority": {"type": "string", "required": False, "default": "normal"},
            },
        }
        TOOL_REGISTRY["calibrate_knowledge"] = {
            "description": "校准知识（检查是否过时）",
            "handler": self._handle_calibrate,
            "parameters": {
                "scope": {"type": "string", "required": False, "default": "all"},
                "mode": {
                    "type": "string",
                    "required": False,
                    "default": "quick",
                    "enum": ["quick", "full"],
                },
                "since": {"type": "string", "required": False},
            },
        }

    def call_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """调用 MCP Tool。

        Args:
            tool_name: Tool 名称（query_knowledge/write_knowledge/calibrate_knowledge）。
            **kwargs: Tool 参数。

        Returns:
            Tool 响应 dict。

        Raises:
            ValueError: Tool 不存在。
            ValidationError: 参数校验失败。
        """
        if tool_name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool: {tool_name}")

        handler = TOOL_REGISTRY[tool_name]["handler"]
        try:
            response = handler(**kwargs)
            return response.to_dict()  # type: ignore[no-any-return]
        except ValidationError as e:
            return {"error": e.message, "code": e.code}

    def list_tools(self) -> list[dict[str, Any]]:
        """列出已注册的 Tool。"""
        return [
            {"name": name, "description": info["description"], "parameters": info["parameters"]}
            for name, info in TOOL_REGISTRY.items()
        ]

    # ==================================================================
    # Tool 处理器（薄封装，委托给 mcp/tools.py 纯函数）
    # ==================================================================

    def _handle_query(self, **kwargs: Any) -> ToolResponse:
        return query_knowledge(self.knowledge_service, **kwargs)

    def _handle_write(self, **kwargs: Any) -> ToolResponse:
        return write_knowledge(self.knowledge_service, **kwargs)

    def _handle_calibrate(self, **kwargs: Any) -> ToolResponse:
        return calibrate_knowledge(self.db, **kwargs)

    # ==================================================================
    # 安全检查
    # ==================================================================

    @staticmethod
    def validate_host(host: str) -> None:
        """验证 host 绑定（强制 127.0.0.1）。

        Args:
            host: 绑定地址。

        Raises:
            SystemExit: 如果 host 不是 127.0.0.1。
        """
        if host != "127.0.0.1":
            logger.critical("Security: MCP host must be 127.0.0.1, got %s", host)
            sys.exit(1)

    def close(self) -> None:
        """关闭数据库连接。"""
        self.db.close()
