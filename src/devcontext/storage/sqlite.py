"""SQLite 存储层 — 连接管理 + DDL 建表 + FTS5 手动同步。

数据库索引层，从 MD 文件派生（P1/P2 原则）。DB 不含 content 全文，
可随时从 MD 重建（``devcontext rebuild-db --from-md``）。

采用「raw SQL 管 DDL + SQLModel 管数据操作」混合模式：
FTS5 虚拟表、触发器、PRAGMA 等 DDL 无法通过 SQLModel 声明，必须用原生 SQL；
knowledge_index 主表的 CRUD 用 SQLModel（Phase 4+ 添加）。

权威来源：``docs/devContextMemo-SQLite-Schema-详细设计-V1.1.md``
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# DDL 定义（严格按 Schema V1.1，幂等：IF NOT EXISTS）
# =============================================================================

_DDL_KNOWLEDGE_INDEX = """
CREATE TABLE IF NOT EXISTS knowledge_index (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    domain          TEXT NOT NULL DEFAULT '',
    sub_domain      TEXT NOT NULL DEFAULT '',

    granularity     TEXT NOT NULL,
    stability       TEXT NOT NULL,
    depth           TEXT NOT NULL,

    status          TEXT NOT NULL DEFAULT 'staged',
    confidence      REAL NOT NULL DEFAULT 0.0,

    code_verified   INTEGER NOT NULL DEFAULT 0,
    prune_priority  REAL NOT NULL DEFAULT 0.0,
    concept_tags    TEXT,
    certainty       REAL NOT NULL DEFAULT 0.5,
    freshness       REAL NOT NULL DEFAULT 0.5,

    embedding       TEXT,

    uri             TEXT NOT NULL,

    used_count      INTEGER NOT NULL DEFAULT 0,
    last_used_at    TEXT,

    last_calibrated_at TEXT,
    calibration_status TEXT DEFAULT 'uncalibrated',

    source_session   TEXT,

    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,

    -- V2.0 §8 晋升生命周期扩展字段（schema V1.3 迁移）
    stale_sub_phase       TEXT,                    -- STALE 子阶段: suspicious/confirmed/deep
    stale_check_count     INTEGER NOT NULL DEFAULT 0,  -- STALE 置信度折扣累积次数 (1/2/3)
    stale_entered_at      TEXT,                    -- 进入 STALE 的时间戳
    deprecation_reason    TEXT,                    -- 废弃原因: superseded/verification_failed/direct_contradiction/low_quality/human_rejected
    restored_count        INTEGER NOT NULL DEFAULT 0,  -- 人工恢复次数
    locked_promotion_score REAL,                   -- CANDIDATE 时锁定的首轮分数
    flag                  TEXT,                    -- 特殊标记: unverified_for_long 等

    -- V1.7 知识保真体系扩展字段（schema V1.4 迁移）
    evidence_level        INTEGER NOT NULL DEFAULT 3,  -- 证据可信度层级 0-5（V1.7 §3.3）
    conflict_with         TEXT,                    -- 冲突的知识 ID（V1.7 §3.4）
    superseded_by         TEXT,                    -- 被哪个知识取代（修订链，V1.7 §4.1）
    successor_id          TEXT,                    -- 后继知识 ID（新版本）
    code_active           INTEGER NOT NULL DEFAULT 1,  -- 代码活性（V1: 0=dead code, 1=活代码）
    auto_adopted_unreviewed INTEGER NOT NULL DEFAULT 0,  -- 自动采用未审核次数（V5）
    applicable_versions   TEXT,                    -- 时效冲突的适用版本（JSON array）
    exceptions            TEXT                     -- 范围冲突的例外说明（JSON array）
);
"""

_DDL_KNOWLEDGE_INDEX_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_ki_domain ON knowledge_index(domain);
CREATE INDEX IF NOT EXISTS idx_ki_granularity ON knowledge_index(granularity);
CREATE INDEX IF NOT EXISTS idx_ki_stability ON knowledge_index(stability);
CREATE INDEX IF NOT EXISTS idx_ki_depth ON knowledge_index(depth);
CREATE INDEX IF NOT EXISTS idx_ki_status ON knowledge_index(status);
CREATE INDEX IF NOT EXISTS idx_ki_confidence ON knowledge_index(confidence);
CREATE INDEX IF NOT EXISTS idx_ki_created ON knowledge_index(created_at);
CREATE INDEX IF NOT EXISTS idx_ki_prune_priority ON knowledge_index(prune_priority);
CREATE INDEX IF NOT EXISTS idx_ki_code_verified ON knowledge_index(code_verified);
CREATE INDEX IF NOT EXISTS idx_ki_last_used ON knowledge_index(last_used_at);
CREATE INDEX IF NOT EXISTS idx_ki_domain_depth ON knowledge_index(domain, depth);
CREATE INDEX IF NOT EXISTS idx_ki_depth_stability ON knowledge_index(depth, stability);
CREATE INDEX IF NOT EXISTS idx_ki_stale_sub_phase ON knowledge_index(stale_sub_phase);
CREATE INDEX IF NOT EXISTS idx_ki_deprecation_reason ON knowledge_index(deprecation_reason);
CREATE INDEX IF NOT EXISTS idx_ki_evidence_level ON knowledge_index(evidence_level);
CREATE INDEX IF NOT EXISTS idx_ki_conflict_with ON knowledge_index(conflict_with);
CREATE INDEX IF NOT EXISTS idx_ki_superseded_by ON knowledge_index(superseded_by);
"""

# updated_at 自动触发器（V46 修复）：
# 条件 old.updated_at = new.updated_at 在首次触发后变为 false，天然终止递归。
_DDL_KI_UPDATED_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS ki_updated_at AFTER UPDATE ON knowledge_index
WHEN old.updated_at = new.updated_at
BEGIN
    UPDATE knowledge_index SET updated_at = datetime('now')
    WHERE id = new.id;
END;
"""

_DDL_KNOWLEDGE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    title,
    keywords,
    summary,
    tokenize='unicode61 remove_diacritics 2'
);
"""

# FTS5 DELETE 触发器：knowledge_index 删除时同步删除 FTS5 索引。
# 改用自包含 FTS5 表（非外部内容表），因为 keywords/summary 不在 knowledge_index 中，
# 外部内容表模式无法正确同步删除。自包含表支持普通 DELETE。
_DDL_KI_FTS_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS ki_ad AFTER DELETE ON knowledge_index BEGIN
    DELETE FROM knowledge_fts WHERE rowid = old.rowid;
END;
"""

_DDL_CALIBRATION_LOG = """
CREATE TABLE IF NOT EXISTS calibration_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id    TEXT NOT NULL,
    mode            TEXT NOT NULL,
    result          TEXT NOT NULL,
    reason          TEXT,
    evidence        TEXT,
    performed_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cl_knowledge ON calibration_log(knowledge_id);
CREATE INDEX IF NOT EXISTS idx_cl_performed ON calibration_log(performed_at);
"""

_DDL_STAGING_QUEUE = """
CREATE TABLE IF NOT EXISTS staging_queue (
    task_id         TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'pending',
    content         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    priority        TEXT NOT NULL DEFAULT 'normal',
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sq_status ON staging_queue(status);
CREATE INDEX IF NOT EXISTS idx_sq_created ON staging_queue(created_at);
"""

_DDL_DEAD_LETTER = """
CREATE TABLE IF NOT EXISTS dead_letter (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL,
    content         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    attempts        INTEGER NOT NULL,
    last_error      TEXT NOT NULL,
    failed_at       TEXT NOT NULL,
    handled         INTEGER NOT NULL DEFAULT 0
);
"""

_DDL_COLLECTOR_WATERMARK = """
CREATE TABLE IF NOT EXISTS collector_watermark (
    session_id      TEXT PRIMARY KEY,
    last_message_id TEXT NOT NULL,
    last_part_id    TEXT,
    last_poll_at    TEXT NOT NULL,
    total_messages  INTEGER NOT NULL DEFAULT 0
);
"""

_DDL_BATCH_LOG = """
CREATE TABLE IF NOT EXISTS batch_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    TEXT NOT NULL UNIQUE,
    session_id  TEXT NOT NULL,
    directory   TEXT NOT NULL,
    jsonl_path  TEXT NOT NULL,
    meta_path   TEXT NOT NULL,
    msg_count   INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'staged',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bl_session ON batch_log(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bl_status ON batch_log(status);
"""

_DDL_BATCH_LOG_UPDATED_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS batch_log_updated AFTER UPDATE ON batch_log
WHEN old.updated_at = new.updated_at
BEGIN
    UPDATE batch_log SET updated_at = datetime('now') WHERE id = new.id;
END;
"""

# 全部 DDL 按依赖顺序排列
_ALL_DDL: list[str] = [
    _DDL_KNOWLEDGE_INDEX,
    _DDL_KNOWLEDGE_INDEX_INDEXES,
    _DDL_KI_UPDATED_TRIGGER,
    _DDL_CALIBRATION_LOG,
    _DDL_STAGING_QUEUE,
    _DDL_DEAD_LETTER,
    _DDL_COLLECTOR_WATERMARK,
    _DDL_BATCH_LOG,
    _DDL_BATCH_LOG_UPDATED_TRIGGER,
]

# FTS5 相关 DDL（单独处理，支持降级）
_FTS_DDL: list[str] = [
    _DDL_KNOWLEDGE_FTS,
    _DDL_KI_FTS_DELETE_TRIGGER,
]


# =============================================================================
# SQLiteStore
# =============================================================================


class SQLiteStore:
    """SQLite 数据库存储层 — 唯一的 sqlite_index owner。

    负责建库（DDL）、连接管理（PRAGMA 配置）、FTS5 手动同步。
    CRUD 方法留给 Phase 4 Writer 实现时按需添加。

    Attributes:
        db_path: 数据库文件路径，或 ':memory:' 用于测试。
        _conn: 内部连接（懒加载）。
        _fts_available: FTS5 是否可用（init_db 后设置）。
    """

    def __init__(self, db_path: str) -> None:
        """初始化存储层。

        Args:
            db_path: 数据库路径。':memory:' 用于内存数据库测试（跳过 WAL PRAGMA）。
        """
        self.db_path: str = db_path
        self._conn: sqlite3.Connection | None = None
        self._fts_available: bool = False

    def get_connection(self) -> sqlite3.Connection:
        """获取已配置 PRAGMA 的数据库连接（懒加载，单例）。

        WAL 模式不支持 ':memory:'，内存数据库时跳过 WAL PRAGMA。
        foreign_keys 始终开启。

        Returns:
            配置好的 sqlite3.Connection。
        """
        if self._conn is not None:
            return self._conn

        is_memory = self.db_path == ":memory:"
        if not is_memory:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # PRAGMA 配置（Schema V1.1 §三）
        # foreign_keys 始终开启（含内存数据库）
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA synchronous = NORMAL;")
        self._conn.execute("PRAGMA cache_size = -64000;")
        self._conn.execute("PRAGMA auto_vacuum = INCREMENTAL;")

        # WAL 模式不支持 :memory:
        if not is_memory:
            self._conn.execute("PRAGMA journal_mode = WAL;")

        return self._conn

    def init_db(self) -> None:
        """幂等建库：创建全部 7 张表 + 索引 + 触发器 + FTS5 + PRAGMA。

        FTS5 不可用时跳过 FTS5 相关 DDL 并 log warning（不阻断建库，
        检索功能降级——可后续 rebuild）。
        """
        conn = self.get_connection()

        # 执行全部基础 DDL
        for ddl in _ALL_DDL:
            conn.executescript(ddl)

        # FTS5 可用性检测 + 创建
        self._fts_available = self._check_fts5_available()
        if self._fts_available:
            for ddl in _FTS_DDL:
                try:
                    conn.executescript(ddl)
                except sqlite3.OperationalError as e:
                    logger.warning("FTS5 DDL 失败，跳过: %s", e)
                    self._fts_available = False
                    break
        else:
            logger.warning(
                "FTS5 不可用，已跳过 knowledge_fts 创建。" "检索功能降级，可通过 rebuild-db 重建。"
            )

        conn.commit()

    def _check_fts5_available(self) -> bool:
        """检测当前 SQLite 是否支持 FTS5。

        Returns:
            True 如果 FTS5 可用。
        """
        conn = self.get_connection()
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x);")
            conn.execute("DROP TABLE IF EXISTS _fts5_probe;")
            conn.commit()
            return True
        except sqlite3.OperationalError:
            return False

    @property
    def fts_available(self) -> bool:
        """FTS5 是否可用（init_db 后才有意义）。"""
        return self._fts_available

    def list_tables(self) -> list[str]:
        """返回所有用户定义的表名（含 FTS5 虚拟表，不含影子表），按字母排序。

        FTS5 虚拟表会自动创建影子表（<name>_data / <name>_idx /
        <name>_content / <name>_config / <name>_docsize），
        此处过滤掉这些内部表，仅返回业务表。

        Returns:
            表名列表，如 ['batch_log', 'calibration_log', ...]。
        """
        conn = self.get_connection()
        # 先查出所有 FTS5 虚拟表名，用于过滤其影子表
        fts_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND sql LIKE 'CREATE VIRTUAL TABLE%' "
                "AND sql LIKE '%fts5%'"
            ).fetchall()
        }
        # FTS5 影子表后缀
        shadow_suffixes = ("_data", "_idx", "_content", "_config", "_docsize")

        def _is_shadow(name: str) -> bool:
            return any(
                name.startswith(fts + "_") and name.endswith(suffix)
                for fts in fts_tables
                for suffix in shadow_suffixes
            )

        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name;"
        ).fetchall()
        return [row[0] for row in rows if not _is_shadow(row[0])]

    def _sync_fts(
        self,
        rowid: int,
        title: str,
        keywords: str,
        summary: str,
    ) -> None:
        """FTS5 手动同步（INSERT/UPDATE）。

         替代触发器——因为 keywords 和 summary 在 Step 5 写入时才就位
        （Step 2 提炼产出），INSERT 时无法填充。
         FTS5 虚拟表不支持 UPSERT，故用 DELETE + INSERT 实现同步。

         Args:
             rowid: knowledge_index 的 rowid。
             title: 知识标题。
             keywords: 关键词（逗号分隔）。
             summary: L0 摘要（~100 tokens）。

         Raises:
             sqlite3.OperationalError: 如果 FTS5 不可用。
        """
        if not self._fts_available:
            raise sqlite3.OperationalError("FTS5 不可用，无法同步")
        conn = self.get_connection()
        # 自包含 FTS5 表支持普通 DELETE + INSERT（upsert 仍不支持）
        conn.execute("DELETE FROM knowledge_fts WHERE rowid = ?", [rowid])
        conn.execute(
            """
            INSERT INTO knowledge_fts(rowid, title, keywords, summary)
            VALUES (?, ?, ?, ?)
            """,
            [rowid, title, keywords, summary],
        )
        conn.commit()

    def _rebuild_fts(self) -> None:
        """FTS5 全量重建（rebuild-db 命令使用）。

        清空 FTS5 索引后从 knowledge_index 重新填充。
        注意：knowledge_index 表本身无 keywords/summary 列，
        实际 rebuild 需从 MD 文件读取这两个字段（Phase 3 实现）。
        此处提供 FTS5 rebuild 命令的框架。

        Raises:
            sqlite3.OperationalError: 如果 FTS5 不可用。
        """
        if not self._fts_available:
            raise sqlite3.OperationalError("FTS5 不可用，无法重建")
        conn = self.get_connection()
        conn.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild');")
        conn.commit()

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
