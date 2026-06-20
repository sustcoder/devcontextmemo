"""知识索引模型 — SQLModel 类（knowledge_index + calibration_log 表）。

对应 SQLite Schema V1.1 的 §2.1 knowledge_index 主表 和 §2.4 calibration_log 表。
SQLModel 类用于运行时数据操作（Phase 4+），DDL 建表由 storage/sqlite.py 用原生 SQL 执行，
两者通过 ``__tablename__`` 保持一致。

权威来源：``docs/devContextMemo-SQLite-Schema-详细设计-V1.1.md``
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from devcontext.models.enums import KnowledgeStatus


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。

    Returns:
        ISO 8601 格式时间戳，如 "2026-06-18T16:00:00+00:00"。
    """
    return datetime.now(UTC).isoformat()


class KnowledgeIndex(SQLModel, table=True):
    """知识索引主表 — knowledge_index。

    DB 不含 content 全文（P1 原则），content 从 MD 文件读取。
    status 默认 'staged'（V2.0 状态模型，RAW 不落 DB）。

    Attributes:
        id: 知识 ID，如 "kw-20260614-001"。
        title: 知识标题。
        domain: 领域，如 "auth"/"order"。
        sub_domain: 子领域，如 "oauth2"。
        granularity: 粒度 L0-L5。
        stability: 稳定性 S1-S5。
        depth: 深度 KW/KH/KY。
        status: V2.0 状态（默认 staged）。
        confidence: 置信度 0.0-1.0。
        code_verified: 代码验证标志 0/1。
        prune_priority: 修剪优先级 0.0-1.0。
        concept_tags: JSON array 字符串，如 '["#幂等","#事务"]'。
        certainty: LLM 确定度 0.0-1.0。
        freshness: 新鲜度 0.0-1.0。
        embedding: JSON array of floats 字符串。
        uri: MD 文件路径。
        used_count: 被检索/注入次数。
        last_used_at: 最后使用时间 ISO 8601。
        last_calibrated_at: 最后校准时间。
        calibration_status: 校准状态。
        source_session: 来源 session ID。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    __tablename__ = "knowledge_index"

    id: str = Field(primary_key=True)
    title: str = Field(nullable=False)
    domain: str = Field(default="", nullable=False)
    sub_domain: str = Field(default="", nullable=False)

    # 三元组分类（必填）
    granularity: str = Field(nullable=False)
    stability: str = Field(nullable=False)
    depth: str = Field(nullable=False)

    # V2.0 状态模型
    status: str = Field(default=KnowledgeStatus.STAGED.value, nullable=False)
    confidence: float = Field(default=0.0, nullable=False)

    # V2.0 晋升与修剪所需字段
    code_verified: int = Field(default=0, nullable=False)

    # Phase 1 双轨制：知识类型 + 决策详情
    knowledge_type: str | None = Field(default=None)
    decision_detail: str | None = Field(default=None)  # JSON: {context, options, rationale, consequence}

    prune_priority: float = Field(default=0.0, nullable=False)
    concept_tags: str | None = Field(default=None)
    certainty: float = Field(default=0.5, nullable=False)
    freshness: float = Field(default=0.5, nullable=False)

    # embedding 向量
    embedding: str | None = Field(default=None)

    # 定位
    uri: str = Field(nullable=False)

    # 使用统计
    used_count: int = Field(default=0, nullable=False)
    last_used_at: str | None = Field(default=None)

    # 校准追踪
    last_calibrated_at: str | None = Field(default=None)
    calibration_status: str = Field(default="uncalibrated")

    # 来源
    source_session: str | None = Field(default=None)

    # 时间戳
    created_at: str = Field(default_factory=_now_iso, nullable=False)
    updated_at: str = Field(default_factory=_now_iso, nullable=False)

    # V2.0 §8 晋升生命周期扩展字段（schema V1.3 迁移）
    stale_sub_phase: str | None = Field(default=None)
    stale_check_count: int = Field(default=0, nullable=False)
    stale_entered_at: str | None = Field(default=None)
    deprecation_reason: str | None = Field(default=None)
    restored_count: int = Field(default=0, nullable=False)
    locked_promotion_score: float | None = Field(default=None)
    flag: str | None = Field(default=None)

    # V1.7 知识保真体系扩展字段（schema V1.4 迁移）
    evidence_level: int = Field(default=3, nullable=False)
    conflict_with: str | None = Field(default=None)
    superseded_by: str | None = Field(default=None)
    successor_id: str | None = Field(default=None)
    code_active: int = Field(default=1, nullable=False)
    auto_adopted_unreviewed: int = Field(default=0, nullable=False)
    applicable_versions: str | None = Field(default=None)
    exceptions: str | None = Field(default=None)


class CalibrationLog(SQLModel, table=True):
    """校准日志表 — calibration_log。

    记录每次校准操作的结果，用于追踪知识质量变化历史。

    Attributes:
        id: 自增主键。
        knowledge_id: 关联 knowledge_index.id。
        mode: 校准模式 "quick"/"full"。
        result: 校准结果 "verified"/"stale"/"conflict"。
        reason: 校准原因描述。
        evidence: JSON 字符串，如 '{"mtime_changed": true}'。
        performed_at: 校准执行时间 ISO 8601。
    """

    __tablename__ = "calibration_log"

    id: int | None = Field(default=None, primary_key=True)
    knowledge_id: str = Field(nullable=False)
    mode: str = Field(nullable=False)
    result: str = Field(nullable=False)
    reason: str | None = Field(default=None)
    evidence: str | None = Field(default=None)
    performed_at: str = Field(default_factory=_now_iso, nullable=False)
