# devContextMemo SQLite Schema — 详细设计 V1.2

> **版本**：V1.2（🆕 增加 collector_watermark + batch_log 两张辅助表——V50/V56）  
> **日期**：2026-06-16（V1.2 修订）  
> **设计参考**：MiMo Code（FTS5 OR 语义 + CJK 支持 + BM25 排序）、Hermes Agent（WAL 模式 + FTS5 + LLM 混合检索）、OpenViking（fingerprint mtime 检测）

---

## 一、核心设计原则

| # | 原则 | 来源 | 理由 |
|---|------|------|------|
| **P1** | DB 不含 content 全文 | OpenViking | content 从 MD 文件读取，DB 只管索引 |
| **P2** | DB 可随时从 MD 重建 | OpenViking | `devContextMemo rebuild-db --from-md` |
| **P3** | WAL 模式必须开启 | Hermes | 读不阻塞写 |
| **P4** | FTS5 用 OR 语义 + BM25 | MiMo Code | AND 导致多词查询零结果 |
| **P5** | fingerprint 做 mtime 检测 | OpenViking | 高效增量同步 |
| **P6** | 🆕 FTS5 手动同步 | 本轮修补 | 触发器无法在 INSERT 时填充 keywords/summary |

---

## 二、表结构设计

### 2.1 `knowledge_index` — 知识索引主表

```sql
CREATE TABLE knowledge_index (
    id              TEXT PRIMARY KEY,             -- 如 "kw-20260614-001"
    title           TEXT NOT NULL,                -- 知识标题
    domain          TEXT NOT NULL DEFAULT '',     -- 领域，如 "auth"/"order"
    sub_domain      TEXT NOT NULL DEFAULT '',     -- 子领域，如 "oauth2"

    -- 三元组分类（必填）
    granularity     TEXT NOT NULL,                -- L0/L1/L2/L3/L4/L5（🆕 V1.1: L4-L5）
    stability       TEXT NOT NULL,                -- S1/S2/S3/S4/S5
    depth           TEXT NOT NULL,                -- KW/KH/KY

    -- 🆕 V1.1: V2.0 状态模型（对齐晋升生命周期 V2.0）
    status          TEXT NOT NULL DEFAULT 'staged',
      -- 状态流转: staged → candidate → pending_review → draft → active → cold → stale → deprecated
      -- RAW 不落 DB（仅存在于 Step 5 写入流程的 in-memory 阶段）
      -- ACTIVE   = 稳定可用（默认检索命中）
      -- COLD     = 低使用但未过期（仍可检索）
      -- STALE    = 待审核/预删除（90天缓冲）
      -- DEPRECATED = 废弃待清理

    confidence      REAL NOT NULL DEFAULT 0.0,    -- 0.0-1.0（LLM 初始 + 校准修正）

    -- 🆕 V1.1: V2.0 晋升与修剪所需字段
    code_verified   INTEGER NOT NULL DEFAULT 0,   -- 代码验证标志（0/1），V2.0 晋升公式 anchor_bonus
    prune_priority  REAL NOT NULL DEFAULT 0.0,    -- 修剪优先级（0.0-1.0），V2.0 修剪规则排序
    concept_tags    TEXT,                          -- JSON array，如 ["#幂等","#createOrder","#事务"]
    certainty       REAL NOT NULL DEFAULT 0.5,    -- LLM 确定度（0.0-1.0），T12/T18 分流
    freshness       REAL NOT NULL DEFAULT 0.5,    -- 新鲜度（0.0-1.0），V2.0 晋升公式

    -- 🆕 V1.1: embedding 向量（Step 4 去重 + Phase 2 语义检索）
    embedding       TEXT,                          -- JSON array of floats（1536 维或用户配置维度）

    -- 定位
    uri             TEXT NOT NULL,                 -- MD 文件路径，如 ".devContextMemo/knowledge/auth/oauth2.md"

    -- 使用统计
    used_count      INTEGER NOT NULL DEFAULT 0,    -- 被检索/注入次数
    last_used_at    TEXT,                          -- ISO 8601

    -- 校准追踪
    last_calibrated_at TEXT,                       -- 最后校准时间
    calibration_status TEXT DEFAULT 'uncalibrated',-- uncalibrated/verified/stale/conflict

    -- 来源
    source_session   TEXT,                         -- 来源 session ID

    -- 时间戳
    created_at      TEXT NOT NULL,                 -- ISO 8601
    updated_at      TEXT NOT NULL                  -- ISO 8601
);

-- 索引：领域过滤 + 三元组过滤 + 状态过滤
CREATE INDEX idx_ki_domain ON knowledge_index(domain);
CREATE INDEX idx_ki_granularity ON knowledge_index(granularity);
CREATE INDEX idx_ki_stability ON knowledge_index(stability);
CREATE INDEX idx_ki_depth ON knowledge_index(depth);
CREATE INDEX idx_ki_status ON knowledge_index(status);
CREATE INDEX idx_ki_confidence ON knowledge_index(confidence);
CREATE INDEX idx_ki_created ON knowledge_index(created_at);

-- 🆕 V1.1: V2.0 修剪规则所需索引
CREATE INDEX idx_ki_prune_priority ON knowledge_index(prune_priority);
CREATE INDEX idx_ki_code_verified ON knowledge_index(code_verified);
CREATE INDEX idx_ki_last_used ON knowledge_index(last_used_at);

-- 组合索引：query_knowledge 最常见的过滤组合
CREATE INDEX idx_ki_domain_depth ON knowledge_index(domain, depth);
CREATE INDEX idx_ki_depth_stability ON knowledge_index(depth, stability);

-- 🆕 V1.1: updated_at 自动触发器（V46 修复）
CREATE TRIGGER ki_updated_at AFTER UPDATE ON knowledge_index BEGIN
    UPDATE knowledge_index SET updated_at = datetime('now')
    WHERE id = new.id AND old.updated_at = new.updated_at;
END;
```

**V1.0→V1.1 变更摘要**：

| 变更 | 旧值 | 新值 | 对应漏洞 |
|------|------|------|:---:|
| status 默认值 | `'valid'` | `'staged'` | V36 |
| status 枚举 | valid/stale/deprecated/archived | staged/candidate/pending_review/draft/active/cold/stale/deprecated | V36 |
| granularity | L0/L1/L2/L3 | L0/L1/L2/L3/L4/L5 | V41 |
| + embedding | — | TEXT (JSON array) | V37 |
| + code_verified | — | INTEGER DEFAULT 0 | V40 |
| + prune_priority | — | REAL DEFAULT 0.0 | V40 |
| + concept_tags | — | TEXT (JSON array) | V40 |
| + certainty | — | REAL DEFAULT 0.5 | V40 |
| + freshness | — | REAL DEFAULT 0.5 | V40 |
| + updated_at 触发器 | — | ki_updated_at | V46 |

---

### 2.2 `knowledge_fts` — FTS5 全文索引虚拟表

```sql
-- 🆕 V1.1: FTS5 虚拟表（外部内容表）
-- 改用「手动同步」替代触发器——因为 CREATE 时 keywords/summary 尚未提炼
CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    title,                                      -- 知识标题
    keywords,                                   -- 关键词（逗号分隔）
    summary,                                    -- L0 摘要（~100 tokens）
    content='knowledge_index',                  -- 外部内容表
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'    -- CJK 支持
);

-- 🆕 V1.1: 仅保留 DELETE 触发器（同步删除，简单安全）
-- INSERT 和 UPDATE 改为手动同步：由 Step 5 在写入后调用 _sync_fts()
CREATE TRIGGER ki_ad AFTER DELETE ON knowledge_index BEGIN
    INSERT INTO knowledge_fts(knowledge_fts, rowid, title, keywords, summary)
    VALUES ('delete', old.rowid, old.title, old.keywords, old.summary);
END;

-- 🆕 V1.1: FTS5 手动同步函数（在 Step 5 写入后调用）
-- 伪代码:
-- def _sync_fts(rowid: int, title: str, keywords: str, summary: str):
--     db.execute("""
--         INSERT INTO knowledge_fts(rowid, title, keywords, summary)
--         VALUES (?, ?, ?, ?)
--         ON CONFLICT(rowid) DO UPDATE SET
--             title=excluded.title,
--             keywords=excluded.keywords,
--             summary=excluded.summary
--     """, [rowid, title, keywords, summary])
--
-- rebuild 时的批量同步:
-- def _rebuild_fts():
--     db.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")
--     db.execute("""
--         INSERT INTO knowledge_fts(rowid, title, keywords, summary)
--         SELECT rowid, title, keywords, summary FROM knowledge_index
--     """)
```

**设计要点**：
- `tokenize='unicode61 remove_diacritics 2'` —— unicode61 支持 CJK 字符
- 使用外部内容表模式（`content='knowledge_index'`），不重复存储
- 🆕 **手动同步代替触发器**：`keywords` 和 `summary` 在 Step 5 写入时才就位（Step 2 提炼产出），INSERT 时无法填充
- 仅保留 DELETE 触发器（删除同步是安全的）

---

### 2.3 FTS5 检索 SQL（🆕 V1.1：对齐 V2.0 状态）

```sql
-- 🆕 V1.1: OR 语义 + BM25 排序 + V2.0 状态过滤
-- 输入 "鉴权 HMAC-SHA256" → 分词后: "鉴权" OR "HMAC" OR "SHA256"

SELECT k.id, k.title, k.uri, k.domain, k.depth, k.confidence,
       k.granularity, k.stability, k.code_verified, k.prune_priority,
       k.concept_tags, k.certainty, k.freshness, k.last_calibrated_at,
       snippet(knowledge_fts, 1, '<b>', '</b>', '...', 32) as snippet,
       bm25(knowledge_fts, 0.0, 1.0, 0.5, 0.5, 0.0) as score
FROM knowledge_fts
JOIN knowledge_index k ON k.rowid = knowledge_fts.rowid
WHERE knowledge_fts MATCH :query
  -- 🆕 V1.1: V2.0 可用状态——排除 staged（未审核）、stale（即将删除）、deprecated（已废弃）
  AND k.status IN ('active', 'cold', 'pending_review', 'draft', 'candidate')
  AND k.confidence >= 0.4
  AND (:domain IS NULL OR k.domain = :domain)
  AND (:depth IS NULL OR k.depth = :depth)
  AND (:stability_min IS NULL OR
       CASE :stability_min
         WHEN 'S1' THEN k.stability IN ('S1')
         WHEN 'S2' THEN k.stability IN ('S1','S2')
         WHEN 'S3' THEN k.stability IN ('S1','S2','S3')
         WHEN 'S4' THEN k.stability IN ('S1','S2','S3','S4')
         ELSE 1
       END)
ORDER BY score DESC
LIMIT :limit * 3;                            -- 过采样 3 倍（借鉴 MiMo Code）

-- 应用层再做相对阈值过滤：
-- topScore × 0.15 以下丢弃，第 1 名永远保留
```

---

### 2.4 `calibration_log` — 校准日志表

```sql
CREATE TABLE calibration_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    knowledge_id    TEXT NOT NULL,              -- → knowledge_index.id
    mode            TEXT NOT NULL,              -- "quick" / "full"
    result          TEXT NOT NULL,              -- "verified" / "stale" / "conflict"
    reason          TEXT,                       -- 校准原因描述
    evidence        TEXT,                       -- JSON: {mtime_changed: true, tool_success: false}
    performed_at    TEXT NOT NULL               -- ISO 8601
);

CREATE INDEX idx_cl_knowledge ON calibration_log(knowledge_id);
CREATE INDEX idx_cl_performed ON calibration_log(performed_at);
```

---

### 2.5 `staging_queue` — 写入队列表

```sql
CREATE TABLE staging_queue (
    task_id         TEXT PRIMARY KEY,           -- "write-20260614-003"
    status          TEXT NOT NULL DEFAULT 'pending', -- pending/processing/completed/failed
    content         TEXT NOT NULL,               -- 知识正文
    session_id      TEXT NOT NULL,               -- 来源 session
    priority        TEXT NOT NULL DEFAULT 'normal', -- normal/high
    attempts        INTEGER NOT NULL DEFAULT 0,  -- 重试次数
    last_error      TEXT,                        -- 最后错误信息
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX idx_sq_status ON staging_queue(status);
CREATE INDEX idx_sq_created ON staging_queue(created_at);
```

**设计要点**：
- `write_knowledge` Tool 写入此表，返回 task_id
- 后台 Worker 轮询 `status='pending'` 任务，执行 Step 2-5 流水线
- `attempts` 追踪重试次数，3 次失败进死信队列

---

### 2.6 `dead_letter` — 死信队列表

```sql
CREATE TABLE dead_letter (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL,
    content         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    attempts        INTEGER NOT NULL,
    last_error      TEXT NOT NULL,
    failed_at       TEXT NOT NULL,
    handled         INTEGER NOT NULL DEFAULT 0  -- 是否已人工处理
);
```

---

### 2.7 `collector_watermark` — 🆕 V1.2 采集水位线表（V50 修补）

```sql
-- Step 0 增量采集使用：记录每个 session 的采集进度
CREATE TABLE collector_watermark (
    session_id      TEXT PRIMARY KEY,
    last_message_id TEXT NOT NULL,
    last_part_id    TEXT,
    last_poll_at    TEXT NOT NULL,       -- ISO 8601
    total_messages  INTEGER NOT NULL DEFAULT 0
);
```

**设计要点**：
- Step 0 每次轮询后更新 `last_message_id`，下次轮询只拉取之后的新消息
- 即使水位线写入失败，Step 4 去重可兜底（允许少量重复采集）
- `last_poll_at` 用于 crash-recovery：如果上次轮询距现在 > 5 分钟，回退水位线

---

### 2.8 `batch_log` — 🆕 V1.2 批处理日志表（V56 修补）

```sql
-- Step 1 攒批层使用：记录每个批次的落盘状态
CREATE TABLE batch_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    TEXT NOT NULL UNIQUE,           -- "batch-{session_id}-{timestamp}"
    session_id  TEXT NOT NULL,
    directory   TEXT NOT NULL,
    jsonl_path  TEXT NOT NULL,                  -- messages.jsonl 绝对路径
    meta_path   TEXT NOT NULL,                  -- _meta.yaml 绝对路径
    msg_count   INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'staged', -- staged | processing | done | failed
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bl_session ON batch_log(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bl_status ON batch_log(status);

-- 🆕 V1.2: updated_at 自动触发器（V46 修补）
CREATE TRIGGER batch_log_updated AFTER UPDATE ON batch_log
BEGIN
    UPDATE batch_log SET updated_at = datetime('now') WHERE id = NEW.id;
END;
```

**设计要点**：
- Step 1 `_do_flush` 成功后 INSERT 一条记录
- Step 2 处理完成后 UPDATE status='done'
- 如果 DB 写入失败不影响主流程（文件已落盘，DB 记录丢失可重建）
- 定时扫描 status='staged' 的批次兜底处理

---

```sql
-- WAL 模式（借鉴 Hermes Agent）
PRAGMA journal_mode = WAL;

-- 同步模式：NORMAL（WAL 模式下安全且性能好）
PRAGMA synchronous = NORMAL;

-- 外键约束
PRAGMA foreign_keys = ON;

-- 缓存大小：64MB（足够 Phase 1 的知识库规模）
PRAGMA cache_size = -64000;

-- 自动 vacuum：incremental（防止文件膨胀）
PRAGMA auto_vacuum = INCREMENTAL;
```

---

## 四、索引重建 SQL

```sql
-- devContextMemo rebuild-db --from-md 的核心逻辑

-- === 应用层伪代码 ===
-- Step 0: 获取排他锁
--   LOCK_FILE = ".devContextMemo/.rebuild_lock"
--   acquire_exclusive_lock(LOCK_FILE, timeout=30s)
--
-- Step 1: 扫描 .devContextMemo/knowledge/*.md
-- Step 2: 解析每个 MD 文件的 YAML frontmatter
-- Step 3: 事务内重建

BEGIN TRANSACTION;
DELETE FROM knowledge_index;
INSERT INTO knowledge_index (id, title, domain, sub_domain,
    granularity, stability, depth, status, confidence,
    code_verified, prune_priority, concept_tags, certainty, freshness,
    embedding, uri,
    last_calibrated_at, calibration_status, source_session,
    created_at, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
COMMIT;

-- 🆕 V1.1: 重建 FTS5（手动同步）
INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild');
INSERT INTO knowledge_fts(rowid, title, keywords, summary)
SELECT rowid, title, keywords, summary FROM knowledge_index;

-- Step 4: 处理 rebuild 期间暂存的写入
--   PENDING_FILE = ".devContextMemo/.rebuild_pending.jsonl"
-- Step 5: 释放锁
--   release_lock(LOCK_FILE)
```

---

## 五、完整 ER 图

```
┌──────────────────────────┐      ┌──────────────────────┐
│    knowledge_index       │      │     knowledge_fts     │
│──────────────────────────│      │──────────────────────│
│ PK id                    │◄─────│ content='ki' (外部表) │
│    title                 │      │ title                 │
│    domain                │      │ keywords              │
│    granularity (L0-L5)   │      │ summary               │
│    stability   (S1-S5)   │      └──────────────────────┘
│    depth       (KW/KH/KY)│
│    status     (V2.0 7阶) │      ┌──────────────────────┐
│    confidence            │      │   calibration_log    │
│    code_verified         │      │──────────────────────│
│    prune_priority        │      │ PK id                │
│    concept_tags          │      │ FK knowledge_id ─────┼──→ knowledge_index.id
│    certainty             │      │    mode              │
│    freshness             │      │    result            │
│    embedding             │      │    evidence          │
│    uri ──────────────────┼──┐   └──────────────────────┘
│    used_count            │  │
│    last_used_at          │  │   MD 文件系统
│    last_calibrated_at    │  │   ┌──────────────────┐
│    source_session        │  │   │ .devContextMemo/knowledge/ │◄─ uri 指向
└──────────────────────────┘  │   │   auth/oauth2.md │
                               │   └──────────────────┘
┌─────────────────────┐       │
│   staging_queue     │       │
│─────────────────────│       │
│ PK task_id          │       │
│    content          │       │
│    session_id       │       │
└─────────────────────┘       │
                               │
┌─────────────────────┐       │
│   dead_letter       │       │
│─────────────────────│       │
│ PK id               │       │
│    task_id          │       │
└─────────────────────┘       │
                               │
🆕 V1.2:                      │
┌──────────────────────┐      │
│ collector_watermark  │      │
│──────────────────────│      │
│ PK session_id        │      │
│    last_message_id   │      │
│    last_poll_at      │      │
└──────────────────────┘      │
                               │
┌──────────────────────┐      │
│ batch_log            │      │
│──────────────────────│      │
│ PK id                │      │
│    batch_id          │      │
│    status            │      │
│    session_id        │──┐   │
└──────────────────────┘  │   │
                           │   │
  (batch_log.session_id ───┘   │
   关联 collector_watermark     │
   .session_id)                │
```

---

*设计完成时间：2026-06-14（V1.0）→ 2026-06-16（V1.1 修补）→ 2026-06-16（V1.2：加 collector_watermark + batch_log）*
