"""溯源与队列模型 — SQLModel 类。

对应 SQLite Schema V1.1 的 4 张辅助表：
- §2.5 staging_queue（写入队列）
- §2.6 dead_letter（死信队列）
- §2.7 collector_watermark（采集水位线，V1.2 新增）
- §2.8 batch_log（批处理日志，V1.2 新增）

权威来源：``docs/devContextMemo-SQLite-Schema-详细设计-V1.1.md``
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。

    Returns:
        ISO 8601 格式时间戳。
    """
    return datetime.now(UTC).isoformat()


class StagingQueue(SQLModel, table=True):
    """写入队列表 — staging_queue。

    write_knowledge Tool 写入此表，返回 task_id；
    后台 Worker 轮询 status='pending' 任务执行流水线。

    Attributes:
        task_id: 任务 ID，如 "write-20260614-003"。
        status: pending/processing/completed/failed。
        content: 知识正文。
        session_id: 来源 session。
        priority: normal/high。
        attempts: 重试次数。
        last_error: 最后错误信息。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    __tablename__ = "staging_queue"

    task_id: str = Field(primary_key=True)
    status: str = Field(default="pending", nullable=False)
    content: str = Field(nullable=False)
    session_id: str = Field(nullable=False)
    priority: str = Field(default="normal", nullable=False)
    attempts: int = Field(default=0, nullable=False)
    last_error: str | None = Field(default=None)
    created_at: str = Field(default_factory=_now_iso, nullable=False)
    updated_at: str = Field(default_factory=_now_iso, nullable=False)


class DeadLetter(SQLModel, table=True):
    """死信队列表 — dead_letter。

    记录 3 次重试失败的任务，等待人工处理。

    Attributes:
        id: 自增主键。
        task_id: 关联 staging_queue.task_id。
        content: 知识正文。
        session_id: 来源 session。
        attempts: 累计重试次数。
        last_error: 最后错误信息。
        failed_at: 失败时间。
        handled: 是否已人工处理 0/1。
    """

    __tablename__ = "dead_letter"

    id: int | None = Field(default=None, primary_key=True)
    task_id: str = Field(nullable=False)
    content: str = Field(nullable=False)
    session_id: str = Field(nullable=False)
    attempts: int = Field(nullable=False)
    last_error: str = Field(nullable=False)
    failed_at: str = Field(default_factory=_now_iso, nullable=False)
    handled: int = Field(default=0, nullable=False)


class CollectorWatermark(SQLModel, table=True):
    """采集水位线表 — collector_watermark（V1.2 新增）。

    Step 0 增量采集使用：记录每个 session 的采集进度。

    Attributes:
        session_id: 会话 ID（主键）。
        last_message_id: 最后采集的消息 ID。
        last_part_id: 最后采集的分片 ID。
        last_poll_at: 最后轮询时间 ISO 8601。
        total_messages: 累计采集消息数。
    """

    __tablename__ = "collector_watermark"

    session_id: str = Field(primary_key=True)
    last_message_id: str = Field(nullable=False)
    last_part_id: str | None = Field(default=None)
    last_poll_at: str = Field(default_factory=_now_iso, nullable=False)
    total_messages: int = Field(default=0, nullable=False)


class BatchLog(SQLModel, table=True):
    """批处理日志表 — batch_log（V1.2 新增）。

    Step 1 攒批层使用：记录每个批次的落盘状态。

    Attributes:
        id: 自增主键。
        batch_id: 批次 ID，如 "batch-{session_id}-{timestamp}"。
        session_id: 来源 session。
        directory: 批次目录。
        jsonl_path: messages.jsonl 绝对路径。
        meta_path: _meta.yaml 绝对路径。
        msg_count: 消息数。
        token_count: token 数。
        status: staged/processing/done/failed。
        created_at: 创建时间。
        updated_at: 更新时间。
    """

    __tablename__ = "batch_log"

    id: int | None = Field(default=None, primary_key=True)
    batch_id: str = Field(nullable=False, unique=True)
    session_id: str = Field(nullable=False)
    directory: str = Field(nullable=False)
    jsonl_path: str = Field(nullable=False)
    meta_path: str = Field(nullable=False)
    msg_count: int = Field(nullable=False)
    token_count: int = Field(nullable=False)
    status: str = Field(default="staged", nullable=False)
    created_at: str = Field(default_factory=_now_iso, nullable=False)
    updated_at: str = Field(default_factory=_now_iso, nullable=False)
