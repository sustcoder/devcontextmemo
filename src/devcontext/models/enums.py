"""状态枚举与状态机校验 — V2.0 晋升生命周期对齐版。

定义知识条目的 8 态状态枚举（小写，对齐 SQLite Schema V1.1）、
三元组分类枚举（L0-L5 / S1-S5 / KW-KH-KY）、V2.0 T1-T25 跃迁迁移矩阵，
以及对应的合法性校验函数。

权威来源：
- `docs/devContextMemo-晋升生命周期-设计-V2.0.md` §一 阶段定义 + §二 跃迁总表
- `docs/devContextMemo-SQLite-Schema-详细设计-V1.1.md` §2.1 status 字段
- `knowledge-state-machine.yaml` V1.1
"""

from enum import Enum
from typing import Any

# =============================================================================
# 知识状态枚举（8 态，小写，对齐 V2.0 + Schema V1.1）
# =============================================================================


class KnowledgeStatus(str, Enum):
    """知识条目的 8 个逻辑阶段（V2.0 晋升生命周期）。

    RAW 不落 DB（仅 Step 2→Step 5 流水线内存态），故不纳入此枚举。
    DB 的 status 字段存储枚举的 value（小写字符串）。

    Attributes:
        STAGED: 已写入 staging/，等待首次评估（T1）。
        CANDIDATE: 评分 ≥ 0.82（滞回上限），建议晋升（T3）。
        PENDING_REVIEW: 0.65 ≤ score < 0.80，建议人工审核（T4）。
        DRAFT: score < 0.65，需人工深入确认（T5）。
        ACTIVE: 活跃使用的可信知识，位于 knowledge/（T2/T6/T7/T9）。
        COLD: 正确但低频，code_verified=1 保护中（T11）。
        STALE: 关联代码可能已变更，含 3 个子阶段（T12/T13/T14/T25）。
        DEPRECATED: 已失效，位于 deprecated/，仅可 T20 人工恢复。
    """

    STAGED = "staged"
    CANDIDATE = "candidate"
    PENDING_REVIEW = "pending_review"
    DRAFT = "draft"
    ACTIVE = "active"
    COLD = "cold"
    STALE = "stale"
    DEPRECATED = "deprecated"


# 所有合法的 DB 状态值集合（用于校验）
VALID_STATUSES: frozenset[str] = frozenset(s.value for s in KnowledgeStatus)


# =============================================================================
# 三元组分类枚举
# =============================================================================


class Granularity(str, Enum):
    """知识粒度 L0-L5（V1.1 扩展，原 V1.0 仅 L0-L3）。

    Attributes:
        L0: 项目级概述（架构总览、技术栈）。
        L1: 模块级（某子系统的设计）。
        L2: 组件级（某类/服务的职责）。
        L3: 函数/方法级（具体实现细节）。
        L4: 代码块级（关键算法片段）。
        L5: 行级（特定配置项、魔法数字）。
    """

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class Stability(str, Enum):
    """知识稳定性 S1-S5（S1 最稳定，S5 最易变）。

    Attributes:
        S1: 几乎不变（架构决策、核心不变量）。
        S2: 很少变（领域模型、接口契约）。
        S3: 偶尔变（业务规则、流程编排）。
        S4: 经常变（实现细节、配置项）。
        S5: 频繁变（临时方案、调试笔记）。
    """

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"


class Depth(str, Enum):
    """知识深度 KW/KH/KY。

    Attributes:
        KW: What — 是什么（事实、定义）。
        KH: How — 怎么做（方法、流程）。
        KY: Why — 为什么（原因、决策依据）。
    """

    KW = "KW"
    KH = "KH"
    KY = "KY"


# 合法值集合（用于校验）
VALID_GRANULARITIES: frozenset[str] = frozenset(g.value for g in Granularity)
VALID_STABILITIES: frozenset[str] = frozenset(s.value for s in Stability)
VALID_DEPTHS: frozenset[str] = frozenset(d.value for d in Depth)


# =============================================================================
# Phase 1 双轨制：知识类型 + 资源/链接枚举
# =============================================================================


class KnowledgeType(str, Enum):
    """知识类型分类（对齐 Phase 1 双轨制）。

    Attributes:
        FACT: 事实描述（"端口是8080"）。
        DECISION: 显式选型/决策（"选了Redis而非Memcached"）。
        PREFERENCE: 用户/团队的偏好或习惯。
        EXPERIENCE: 引用过去项目经验。
    """

    FACT = "fact"
    DECISION = "decision"
    PREFERENCE = "preference"
    EXPERIENCE = "experience"


VALID_KNOWLEDGE_TYPES: frozenset[str] = frozenset(t.value for t in KnowledgeType)


class ResourceType(str, Enum):
    """资源类型枚举。

    Attributes:
        REQUIREMENTS: 需求文档（PRD、用户故事、业务目标）。
        SPECS: Spec 文档（API Doc、DB Schema、架构图）。
        DESIGN: 设计文档（系统设计、详细设计）。
        API: API 文档（接口定义、OpenAPI）。
        SCHEMA: 数据库 Schema（SQL、Prisma）。
    """

    REQUIREMENTS = "requirements"
    SPECS = "specs"
    DESIGN = "design"
    API = "api"
    SCHEMA = "schema"


VALID_RESOURCE_TYPES: frozenset[str] = frozenset(t.value for t in ResourceType)


class ResourceLinkType(str, Enum):
    """资源↔知识链接类型枚举。

    Attributes:
        DERIVED_FROM: 知识从资源提炼而来（spec 提炼成知识）。
        REFERENCES: 知识引用了资源内容（决策理由里提到 spec 章节）。
        CONTRADICTS: 知识与资源冲突（spec 说用 MySQL，代码用 PG）。
        UPDATES: 知识是对旧资源版本的更新。
    """

    DERIVED_FROM = "derived_from"
    REFERENCES = "references"
    CONTRADICTS = "contradicts"
    UPDATES = "updates"


VALID_RESOURCE_LINK_TYPES: frozenset[str] = frozenset(t.value for t in ResourceLinkType)


class KnowledgeRelation(str, Enum):
    """知识↔知识关系类型枚举。

    Attributes:
        MERGED_FROM: 两个原始条目互补，被合并为一条。
        SUPERSEDED_BY: 一条是另一条的精确化升级。
        CONTRADICTS: 两条知识互相矛盾。
    """

    MERGED_FROM = "merged_from"
    SUPERSEDED_BY = "superseded_by"
    CONTRADICTS = "contradicts"


VALID_KNOWLEDGE_RELATIONS: frozenset[str] = frozenset(r.value for r in KnowledgeRelation)


# =============================================================================
# V2.0 T1-T25 跃迁迁移矩阵
# =============================================================================


# 严格按 V2.0 晋升生命周期 T 表（用户确认）：
# - draft 无 →staged 直接跃迁（draft 仅可 →active(T9) / deprecated(T10/T19)）
# - cold 无 →active 捷径（冷知识复活必须经 cold→stale(T13)→active(T15) 完整路径）
# - 自迁移（same→same）全部合法（no-op 语义）
# - 任意状态 →deprecated 合法（手动废弃）
# - deprecated 仅可 →staged（T20 人工恢复）
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "staged": frozenset({"staged", "candidate", "pending_review", "draft", "active", "deprecated"}),
    "candidate": frozenset({"candidate", "active", "pending_review", "deprecated"}),
    "pending_review": frozenset({"pending_review", "active", "deprecated"}),
    "draft": frozenset({"draft", "active", "deprecated"}),
    "active": frozenset({"active", "cold", "stale", "deprecated"}),
    "cold": frozenset({"cold", "stale", "deprecated"}),
    "stale": frozenset({"stale", "active", "deprecated"}),
    "deprecated": frozenset({"deprecated", "staged"}),
}


# =============================================================================
# 校验函数
# =============================================================================


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """检查状态迁移是否合法（依据 V2.0 T1-T25 跃迁规则）。

    Args:
        from_status: 起始状态（小写字符串，如 "staged"）。
        to_status: 目标状态（小写字符串，如 "active"）。

    Returns:
        True 如果迁移合法（含自迁移），False 如果非法或状态值未知。

    Examples:
        >>> is_valid_transition("staged", "candidate")
        True
        >>> is_valid_transition("draft", "staged")
        False
        >>> is_valid_transition("cold", "active")
        False
        >>> is_valid_transition("deprecated", "staged")
        True
    """
    allowed = ALLOWED_TRANSITIONS.get(from_status)
    if allowed is None:
        return False
    return to_status in allowed


def is_valid_status(status: str) -> bool:
    """检查状态值是否为合法的 8 态之一。

    Args:
        status: 状态字符串。

    Returns:
        True 如果是合法状态值。
    """
    return status in VALID_STATUSES


def is_valid_lx(value: str) -> bool:
    """检查粒度值是否合法（L0-L5）。

    Args:
        value: 粒度字符串。

    Returns:
        True 如果是 L0/L1/L2/L3/L4/L5 之一。
    """
    return value in VALID_GRANULARITIES


def is_valid_sy(value: str) -> bool:
    """检查稳定性值是否合法（S1-S5）。

    Args:
        value: 稳定性字符串。

    Returns:
        True 如果是 S1/S2/S3/S4/S5 之一。
    """
    return value in VALID_STABILITIES


def is_valid_depth(value: str) -> bool:
    """检查深度值是否合法（KW/KH/KY）。

    Args:
        value: 深度字符串。

    Returns:
        True 如果是 KW/KH/KY 之一。
    """
    return value in VALID_DEPTHS


def is_valid_domain(domain: str, domain_tree: dict[str, Any]) -> bool:
    """检查 domain 是否在领域树中注册。

    当 domain_tree 为空时，允许所有 domain（自动模式）。

    Args:
        domain: 领域字符串（如 "order"）。
        domain_tree: 领域树字典，键为领域名。

    Returns:
        True 如果 domain 有效。

    Examples:
        >>> tree = {"order": {}, "payment": {}}
        >>> is_valid_domain("order", tree)
        True
        >>> is_valid_domain("shopping_cart", tree)
        False
        >>> is_valid_domain("general", {})
        True
    """
    if not domain_tree:  # 空树 = 自动模式，允许所有 domain
        return bool(domain)
    return domain in domain_tree


def is_valid_knowledge_type(value: str) -> bool:
    """检查知识类型是否合法。

    Args:
        value: 知识类型字符串。

    Returns:
        True 如果是 fact/decision/preference/experience 之一。
    """
    return value in VALID_KNOWLEDGE_TYPES
