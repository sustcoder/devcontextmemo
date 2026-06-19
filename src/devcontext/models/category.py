"""分类模型 — 三元组 (granularity, stability, depth) + domain 树。

提供知识条目的分类数据结构，用于 Step 2 提炼层的分类输出和校验。
Pydantic 模型（非 SQLModel table），不映射 DB 表。

权威来源：
- ``docs/devContextMemo-项目知识系统-需求文档-V1.0.md`` §三 三元组分类
- ``docs/devContextMemo-SQLite-Schema-详细设计-V1.1.md`` §2.1 三元组字段
"""

from pydantic import BaseModel, field_validator
from typing import Any

from devcontext.models.enums import (
    VALID_DEPTHS,
    VALID_GRANULARITIES,
    VALID_STABILITIES,
    is_valid_domain,
)


class Category(BaseModel):
    """知识三元组分类 (granularity, stability, depth) + domain。

    三元组是知识条目的核心分类维度，配合 domain 形成完整定位。

    Attributes:
        granularity: 粒度 L0-L5。
        stability: 稳定性 S1-S5。
        depth: 深度 KW/KH/KY。
        domain: 领域，如 "order"/"auth"。
        sub_domain: 子领域，如 "oauth2"（可选）。

    Examples:
        >>> cat = Category(granularity="L2", stability="S3", depth="KH", domain="order")
        >>> cat.is_valid({"order": {}})
        True
    """

    granularity: str
    stability: str
    depth: str
    domain: str
    sub_domain: str | None = None

    @field_validator("granularity")
    @classmethod
    def _validate_granularity(cls, v: str) -> str:
        """校验粒度值合法（L0-L5）。"""
        if v not in VALID_GRANULARITIES:
            raise ValueError(
                f"Invalid granularity {v!r}, must be one of {sorted(VALID_GRANULARITIES)}"
            )
        return v

    @field_validator("stability")
    @classmethod
    def _validate_stability(cls, v: str) -> str:
        """校验稳定性值合法（S1-S5）。"""
        if v not in VALID_STABILITIES:
            raise ValueError(f"Invalid stability {v!r}, must be one of {sorted(VALID_STABILITIES)}")
        return v

    @field_validator("depth")
    @classmethod
    def _validate_depth(cls, v: str) -> str:
        """校验深度值合法（KW/KH/KY）。"""
        if v not in VALID_DEPTHS:
            raise ValueError(f"Invalid depth {v!r}, must be one of {sorted(VALID_DEPTHS)}")
        return v

    def is_valid(self, domain_tree: dict[str, Any]) -> bool:
        """检查 domain 是否在领域树中注册。

        Args:
            domain_tree: 领域树字典，键为领域名。

        Returns:
            True 如果 domain 在 domain_tree 中。
        """
        return is_valid_domain(self.domain, domain_tree)

    def to_triple(self) -> tuple[str, str, str]:
        """返回三元组元组 (granularity, stability, depth)。

        Returns:
            三元组，如 ("L2", "S3", "KH")。
        """
        return (self.granularity, self.stability, self.depth)
