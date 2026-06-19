"""devcontext models 包 — 数据模型与状态机定义。

导出所有公开的 SQLModel 表模型、Pydantic 模型、枚举和校验函数。
"""

from devcontext.models.category import Category
from devcontext.models.enums import (
    ALLOWED_TRANSITIONS,
    VALID_DEPTHS,
    VALID_GRANULARITIES,
    VALID_STABILITIES,
    VALID_STATUSES,
    Depth,
    Granularity,
    KnowledgeStatus,
    Stability,
    is_valid_depth,
    is_valid_domain,
    is_valid_lx,
    is_valid_status,
    is_valid_sy,
    is_valid_transition,
)
from devcontext.models.knowledge import CalibrationLog, KnowledgeIndex
from devcontext.models.source import (
    BatchLog,
    CollectorWatermark,
    DeadLetter,
    StagingQueue,
)

__all__ = [
    # 枚举
    "KnowledgeStatus",
    "Granularity",
    "Stability",
    "Depth",
    # 合法值集合
    "VALID_STATUSES",
    "VALID_GRANULARITIES",
    "VALID_STABILITIES",
    "VALID_DEPTHS",
    # 迁移矩阵
    "ALLOWED_TRANSITIONS",
    # 校验函数
    "is_valid_transition",
    "is_valid_status",
    "is_valid_lx",
    "is_valid_sy",
    "is_valid_depth",
    "is_valid_domain",
    # SQLModel 表模型
    "KnowledgeIndex",
    "CalibrationLog",
    "StagingQueue",
    "DeadLetter",
    "CollectorWatermark",
    "BatchLog",
    # Pydantic 模型
    "Category",
]
