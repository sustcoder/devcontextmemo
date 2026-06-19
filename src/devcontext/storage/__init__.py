"""存储层 — 数据持久化与检索。

MD 权威 + DB 索引派生。
包含：
- markdown.py: MD 文件读写 + Frontmatter 解析（三目录：staging/knowledge/deprecated）
- sqlite.py: SQLite 连接池 + WAL 模式 + 7 张表 DDL + FTS5
- search.py: FTS5 全文搜索 + 语义重排
- atomic.py: 原子写入（MD first → DB second）+ 路径穿越校验
"""

from .atomic import (
    PathTraversalError,
    atomic_write_md,
    sanitize_path_segment,
    validate_safe_path,
)
from .markdown import MarkdownStore
from .sqlite import SQLiteStore

__all__ = [
    "MarkdownStore",
    "SQLiteStore",
    "PathTraversalError",
    "atomic_write_md",
    "sanitize_path_segment",
    "validate_safe_path",
]
