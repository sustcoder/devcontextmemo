# 自动采集 + 流水线串联 — 实现设计 V1.0

> **日期**：2026-06-19  
> **状态**：待实施  
> **关联文档**：需求文档 V1.0、决策总账 V1.0、数据写入流水线详细设计 V1.0、Stream 0/1 细化设计、MiMo-Code 调研报告 V1.0

---

## 一、背景与目标

### 1.1 当前状态

devContextMemo 的 Steps 0-6 流水线各 Step 独立实现已完成，但缺少关键基础设施：

| 缺失项 | 影响 |
|--------|------|
| Step 0 无自动触发机制 | 采集器需要手动调用 `receiver.receive()` |
| `services/pipeline.py` 为空壳 | Steps 0-6 未串联，各自独立 |
| `main.py:serve()` 为 pass | 无后台 daemon |
| 无回调/事件机制 | Step 间无法自动传递数据 |

### 1.2 目标

实现 **① 对话自动采集** 和 **② 全链路流水线串联**，使 devContextMemo 成为一个可独立运行的 daemon 进程。

### 1.3 设计依据

- 需求文档 V1.0 §1.3：自动沉淀结构化领域知识
- 体系架构设计 V1.0 §二：七层架构中的接收层 + 服务层
- 数据写入流水线详细设计 V1.0 §二-§三：Step 0 采集层 + Step 1 攒批层
- Stream 0/1 细化设计：`MessageCollector` / `BatchWriter` 接口签名
- MiMo-Code 调研报告：会话边界触发 + 文件化中间产物

---

## 二、整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                         main.py: serve()                             │
│  ┌──────────────────────┐  ┌───────────────────────────────────────┐ │
│  │  PipelineService     │  │  MCP Server (已有)                    │ │
│  │  (编排层，回调链)     │  │  127.0.0.1:9020                      │ │
│  └──────────┬───────────┘  └───────────────────────────────────────┘ │
│             │                                                         │
│  ┌──────────▼──────────────────────────────────────────────────────┐ │
│  │                   PipelineService 回调链                          │ │
│  │                                                                  │ │
│  │  ┌─────────────────────────────────────┐                         │ │
│  │  │         Step 0: 采集策略层            │                         │ │
│  │  │  ┌──────────────────┐               │                         │ │
│  │  │  │ PollingCollector │  (Phase 1)     │                         │ │
│  │  │  │ (轮询线程+水位线)  │               │                         │ │
│  │  │  └────────┬─────────┘               │                         │ │
│  │  │           │                          │                         │ │
│  │  │  ┌────────▼─────────┐  ┌───────────┐│                         │ │
│  │  │  │ HookCollector    │  │ (Phase 2+) ││  ← 架构预留              │ │
│  │  │  │ (事件订阅)        │  └───────────┘│                         │ │
│  │  │  └────────┬─────────┘               │                         │ │
│  │  └───────────┼─────────────────────────┘                         │ │
│  │              │ 调用 adapter.xxx()                                  │ │
│  │  ┌───────────▼─────────────────────────┐                         │ │
│  │  │    CollectorAdapter 接口 (数据源层)    │                         │ │
│  │  │  ┌──────────┐ ┌────────┐ ┌────────┐ │                         │ │
│  │  │  │ OpenCode │ │ File   │ │Generic │ │                         │ │
│  │  │  │ SQLite   │ │ System │ │SQLite  │ │  ← 多数据源适配器         │ │
│  │  │  └──────────┘ └────────┘ └────────┘ │                         │ │
│  │  └─────────────────────────────────────┘                         │ │
│  │              │                                                    │ │
│  │              │ on_buffer_ready 回调                                │ │
│  │              ▼                                                    │ │
│  │  BatchWriter ──► Step 2→6 顺序调用                                │ │
│  │  (Step 1)       extract → validate → dedup → write → consolidate │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘

        外部数据源（只读）：OpenCode SQLite / Cursor SQLite / 文件夹 / ...
```

**设计原则**：
- **采集策略与数据源解耦**：采集器不关心数据来自 SQLite 还是文件夹，只调用 `CollectorAdapter` 接口
- **回调链模式**：Step N 完成时通过 callback 触达 Step N+1，松耦合
- **文件作为契约**：Step 1 落盘 JSONL 后，通过文件路径传递给 Step 2-6
- **优雅降级**：某 Step 失败时保留中间产物，记录日志，不丢弃数据
- **架构预留**：Hook 模式新增 `HookCollector` 即可，无需修改 `BaseCollector`、现有适配器或流水线

---

## 三、Step 0 — 多源可扩展采集器

### 3.1 设计原则：采集策略与数据源解耦

采集器分为两层，互不绑定：

```
采集策略层（怎么采）                数据源适配层（从哪采）
──────────────────────              ──────────────────────────
                                     ┌─ OpenCodeSQLiteAdapter
PollingCollector ──────调用────────►├─ FileSystemAdapter
  (轮询线程 + Watermark)            ├─ GenericSQLiteAdapter
       │                             └─ ...（未来扩展）
       │  ┌─ HookCollector（预留）
       └──├─ (事件订阅)
          └─ 新增仅需 50 行
```

- **策略层**：决定采集时机（轮询/事件），管理缓冲区和回调
- **适配层**：封装具体数据源（SQLite/文件系统/...），返回标准化消息
- **换策略不改适配器，换数据源不改策略**

### 3.2 CollectorAdapter 接口（数据源抽象）

```python
class CollectorAdapter:
    """数据源适配器基类 — 轮询 + Hook 共用"""
    source_name: str

    # ---- 轮询模式方法 ----
    def incremental_query(self, watermarks: dict) -> list[dict]:
        """增量查询：按 watermark 拉取新消息。子类必须实现。"""
        raise NotImplementedError

    def fetch_full(self) -> list[dict]:
        """全量查询：冷启动或手动触发时使用。默认调用 incremental_query({})。"""
        return self.incremental_query({})

    # ---- 共享方法 ----
    def normalize(self, raw: dict) -> dict:
        """标准化原始消息 → {session_id, role, content, timestamp, ...}"""
        raise NotImplementedError

    def validate_connection(self) -> bool:
        """检查数据源是否可访问（DB 存在、路径有效等）"""
        return True
```

**轮询适配器**只需实现 `source_name` + `incremental_query` + `normalize` 三个方法，约 40 行。

### 3.3 采集策略基类：BaseCollector

```python
class BaseCollector:
    """采集策略基类 — 不绑定轮询或 Hook"""

    adapter: CollectorAdapter           # 数据源（可替换）
    buffer: list[CleanMessage]          # 内存缓冲
    on_buffer_ready: Callable | None    # 回调：通知 Step 1（BatchWriter）

    # 通用能力
    def _strip_noise(self, raw: dict) -> CleanMessage: ...
    def _check_buffer(self) -> bool:
        """检查缓冲区是否达到触发阈值"""
    def _flush_buffer(self) -> list[CleanMessage]: ...
    def _emit(self, messages: list[CleanMessage]):
        """触发 on_buffer_ready 回调"""

    # 生命周期（子类实现）
    def start(self): ...
    def stop(self): ...
```

`BaseCollector` 不包含任何轮询或事件订阅逻辑，仅提供缓冲管理 + 去噪 + 回调通知。

#### 3.3.1 CleanMessage：采集→流水线数据契约

```python
@dataclass
class CleanMessage:
    """采集器标准化输出，全流水线统一数据格式"""
    session_id: str          # 会话标识（来自 adapter 的 normalize）
    role: str                # "user" | "assistant" | "system" | "tool"
    content: str             # 消息正文（已去噪）
    timestamp: float         # Unix 时间戳
    source: str              # 数据源名称（对应 adapter.source_name）
    metadata: dict = field(default_factory=dict)  # 扩展字段
```

- 所有 adapter 的 `normalize()` 必须返回符合此格式的 dict
- `BaseCollector._strip_noise()` 输入/输出均为 `CleanMessage`
- `BaseCollector.buffer` 类型为 `list[CleanMessage]`
- `on_buffer_ready` 回调传递 `list[CleanMessage]`

### 3.4 轮询策略实现：PollingCollector (Phase 1)

```python
class PollingCollector(BaseCollector):
    """定时轮询采集器 — 当前唯一采集策略"""

    poll_interval_ms: int = 500
    watermarks: dict[str, str]               # {adapter.source_name: last_checkpoint}
    max_buffer_messages: int = 200
    max_buffer_tokens: int = 6000

    async def start(self) -> asyncio.Task:
        """创建后台轮询 task"""
        ...

    async def _poll_loop(self):
        while self._running:
            try:
                # sync 适配器方法通过 to_thread 避免阻塞事件循环
                messages = await asyncio.to_thread(
                    self.adapter.incremental_query, self.watermarks
                )
            except Exception:
                logger.warning("poll failed, retry next cycle")
                await asyncio.sleep(self.poll_interval_ms / 1000)
                continue

            for msg in messages:
                clean = self.adapter.normalize(msg)
                self.buffer.append(clean)

            self._update_watermarks(messages)    # watermark = 最后一条消息的标识

            if self._check_buffer():
                flushed = self._flush_buffer()
                self._emit(flushed)

            await asyncio.sleep(self.poll_interval_ms / 1000)

    async def stop(self):
        self._running = False
        self._flush_buffer()         # 退出前清空剩余缓冲
        self._persist_watermarks()   # 持久化水位线到 WatermarkStore

    def _update_watermarks(self, messages: list[dict]):
        """更新水位线：取最后一条消息的标识字段。子类 adapter 可覆盖。"""
        if not messages:
            return
        last = messages[-1]
        self.watermarks[self.adapter.source_name] = last.get("id") or str(
            time.time()
        )

    def _persist_watermarks(self):
        """持久化水位线到 WatermarkStore（JSON 文件，路径 ~/.devContextMemo/watermarks.json）。"""
        WatermarkStore.save(self.adapter.source_name, self.watermarks)
```

**关键**：`PollingCollector` 只持有 `CollectorAdapter` 引用，不关心是 SQLite 还是文件系统。换数据源只需换 adapter 实例。

### 3.5 轮询适配器实现（Phase 1 实现）

#### 3.5.1 OpenCodeSQLiteAdapter

```python
class OpenCodeSQLiteAdapter(CollectorAdapter):
    source_name = "opencode"
    db_path: str                         # ~/.opencode/opencode.db

    def incremental_query(self, watermarks: dict) -> list[dict]:
        last_id = watermarks.get("last_message_id", 0)
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT * FROM messages WHERE id > ? ORDER BY id", (last_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def normalize(self, raw: dict) -> dict:
        return {
            "session_id": raw["conversation_id"],
            "role": raw["role"],
            "content": raw["content"],
            "timestamp": raw["created_at"],
            "source": self.source_name,
        }
```

- 外部只读（`mode=ro`），零侵入
- Watermark 用 `last_message_id`，不丢消息

#### 3.5.2 FileSystemAdapter

```python
class FileSystemAdapter(CollectorAdapter):
    source_name = "filesystem"
    scan_paths: list[str]                # 可配置多个路径
    file_patterns: list[str] = ["*.jsonl", "*.md", "*.yaml"]
    seen_files: set[str] = set()         # fingerprint 去重

    def incremental_query(self, watermarks: dict) -> list[dict]:
        last_scan = watermarks.get("last_scan_time", 0)
        results = []
        for scan_path in self.scan_paths:
            for filepath in Path(scan_path).rglob("*"):
                if not self._match_pattern(filepath):
                    continue
                fp = self._fingerprint(filepath)   # size + mtime
                if fp in self.seen_files:
                    continue
                if filepath.stat().st_mtime <= last_scan:
                    continue
                self.seen_files.add(fp)
                results.append(self._read_as_message(filepath))
        return results

    def normalize(self, raw: dict) -> dict:
        return raw   # _read_as_message 已标准化
```

- 适用场景：扫描 AI 工具的输出目录（如 OpenCode 的 sessions/ 文件夹）
- fingerprint 去重：`f"{size}:{mtime}"`，避免重复采集
- 支持 glob pattern 过滤文件类型

#### 3.5.3 GenericSQLiteAdapter

```python
class GenericSQLiteAdapter(CollectorAdapter):
    """通用 SQLite 适配器 — 通过配置接入任意 AI 工具数据库"""
    source_name: str                     # "cursor", "comate" 等
    db_path: str
    query_template: str                  # "SELECT ... FROM messages WHERE {id_col} > ?"
    id_column: str = "id"

    def incremental_query(self, watermarks: dict) -> list[dict]:
        last_id = watermarks.get(f"{self.source_name}_last_id", 0)
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        rows = conn.execute(
            self.query_template, (last_id,)
        ).fetchall()
        return [dict(row) for row in rows]
```

- 通过配置即可接入 Cursor、Comate 等工具的 SQLite DB，无需写新适配器
- 配置示例见 §八

### 3.6 触发策略（MiMo-Code 启发叠加）

| 优先级 | 触发条件 | 行为 |
|:--:|------|------|
| P0 | 会话边界检测 | 轮询检测到新 session_id → 立即 flush 上一 session 缓冲区 |
| P1 | 缓冲区累积触发 | token ≥ 6000 或 200 条消息 → 触发 on_buffer_ready 回调 |
| P2 | 定时兜底 | 每日扫描未 flush 的 session → 全量采集 |
| P3 | CLI 手动触发 | `devcontext capture` 命令 |

### 3.7 Hook 模式扩展路径（架构预留）

```
HookCollector(BaseCollector)                    # Phase 2+ 实现（约 50 行）
├── 输入：adapter 提供 subscribe(callback)       # 注册到 code agent 生命周期
├── 触发事件：on_session_start / on_message / on_session_end
├── 行为：消息实时入 buffer → 满足阈值触发 flush
└── 与 PollingCollector 可共存（多源同时运行）
```

**新增 Hook 模式仅需 3 步，无需修改任何现有代码**：

| 步骤 | 改动 | 行数 |
|:--:|------|:--:|
| 1 | 实现 `HookCollector(BaseCollector)`（事件订阅 loop 替代轮询 loop） | ~50 |
| 2 | 为需要的适配器实现 `subscribe(callback)` 方法 | ~20/适配器 |
| 3 | `PipelineService` 中 `collectors.append(HookCollector(...))` | 1 |

`BaseCollector`、`PollingCollector`、现有适配器、流水线无需任何改动。

---

## 四、Step 1 — 回调式攒批器

### 4.1 新增类：BatchWriter

```
BatchWriter
├── 输入：on_messages(messages, session_id) 回调
├── 内存缓冲 (按 session_id 分组)
│   ├─ 累计 token 计数
│   └─ 记录 batch_start_at（超时保护）
├── 触发条件（任一满足）
│   ├─ token ≥ 6000 → 立即落盘 JSONL
│   ├─ 消息数 ≥ 200 → 立即落盘
│   ├─ batch_age ≥ 30min → 强制落盘（兜底）
│   └─ session 结束信号 → 落盘剩余消息
├── 输出：staging/{date}/{session_id}/messages.jsonl + _meta.yaml
└── 落盘后 → on_batch_ready 回调 → 触发 Step 2-6
```

#### 4.1.1 _meta.yaml 格式

```yaml
# staging/2026-06-19/abc123/_meta.yaml
session_id: "abc123"
source: "opencode"           # 来自 adapter.source_name
batch_created: 1718809200.0  # Unix 时间戳
message_count: 187
token_count: 6200
message_file: "messages.jsonl"
trigger_reason: "token_threshold"  # token_threshold | message_count | age_timeout | session_end
status: "ready"              # ready → Step 2-6 处理完后 → done
```

- Step 2-6 通过 `_meta.yaml` 了解 batch 元信息（无需解析 JSONL 头部）
- `status` 字段防重入：Step 2 处理前检查 `status == "ready"`

### 4.2 与现有 Batcher 的关系

`BatchWriter`（回调模式）与现有 `Batcher`（文件扫描模式）互补共存：

| 模式 | 类 | 触发方式 | 使用场景 |
|------|-----|----------|---------|
| 回调模式 | `BatchWriter` | Step 0 `on_buffer_ready` 回调 | daemon 自动采集的主路径 |
| 扫描模式 | `Batcher`（已有） | 手动扫描 `raw_dir/` 目录 | CLI 手动触发 + 历史数据迁移 |

两者输出格式相同（JSONL + `_meta.yaml`），下游 Step 2-6 无需区分来源。`PipelineService` 默认使用 `BatchWriter`，CLI `devcontext capture` 可选用 `Batcher`。

---

## 五、PipelineService — 编排层

### 5.1 职责

- 持有所有 Step 实例（MessageCollector、BatchWriter、Extractor 等）
- 注册回调链：Step 0 → Step 1 → Step 2→6
- 管理生命周期：`start()` / `stop()`
- 提供手动触发入口：`capture()`

### 5.2 回调链约定

```
Step 0 (MessageCollector)
  └── on_buffer_ready(messages: list[CleanMessage]) → 同步回调
        │
        ▼
Step 1 (BatchWriter)
  ├── on_messages(messages, session_id) → 攒批
  └── on_batch_ready(batch_path: Path) → 同步回调
        │
        ▼
Step 2→6 (顺序执行)
  └── process_batch(batch_path: Path)
        ├── Step 2: Extractor.extract(batch_path)
        ├── Step 3: Validator.validate(extracted_items)
        ├── Step 4: Deduplicator.dedup(validated_items)
        ├── Step 5: Writer.write(deduped_items)
        └── Step 6: Consolidator.consolidate(written_items)
```

### 5.3 生命周期

```
PipelineService.start()
  ├── 创建 collectors（≥1 个）:
  │   ├── PollingCollector(adapter=OpenCodeSQLiteAdapter(...))
  │   ├── PollingCollector(adapter=FileSystemAdapter(...))
  │   └── ...（可扩展更多数据源）
  ├── 注册回调链：collector.on_buffer_ready → batcher.on_messages
  ├── 启动所有 collector（后台 asyncio task）
  └── 启动 MCP Server（FastMCP）
  
PipelineService.stop()
  ├── 停止所有 collector
  ├── flush 剩余缓冲区 + 持久化水位线
  └── 关闭 MCP Server

PipelineService.capture()
  └── 手动触发一次完整采集（调试/兜底用）
```

### 5.4 优雅降级

| Step | 失败策略 |
|------|---------|
| Step 0 | 跳过本次轮询，记录 WARNING 日志（丢一次不影响完整性） |
| Step 1 | 保留 buffer，记录 CRITICAL 日志 |
| Step 2-3 | batch JSONL 保留在 staging/，等待下轮重试 |
| Step 4-6 | 记录 ERROR 日志，不丢数据（staging/ 文件保留） |

---

## 六、main.py: serve() — Daemon 入口

```python
def serve():
    """启动 devContextMemo daemon。"""
    from devcontext.services.pipeline import PipelineService
    from devcontext.core.collectors.polling import PollingCollector
    from devcontext.core.adapters.opencode_sqlite import OpenCodeSQLiteAdapter
    from devcontext.core.adapters.filesystem import FileSystemAdapter
    from devcontext.core.pipeline.batcher import BatchWriter
    from devcontext.mcp.server import MCPServer

    # 创建采集器（多个数据源可同时运行）
    collectors = [
        PollingCollector(
            adapter=OpenCodeSQLiteAdapter(db_path=settings.opencode_db_path),
        ),
        PollingCollector(
            adapter=FileSystemAdapter(
                scan_paths=settings.filesystem_scan_paths,
            ),
        ),
    ]

    batcher = BatchWriter(
        staging_dir=settings.staging_dir,
        token_threshold=settings.batch_token_threshold,
    )

    # 创建编排服务（支持多 collector）
    pipeline = PipelineService(
        collectors=collectors,
        batcher=batcher,
        # ... 其他 Step 实例
    )

    # 启动 MCP Server（复用现有 MCPServer 类）
    mcp = MCPServer(...)

    # 并发运行
    asyncio.run(asyncio.gather(
        pipeline.start(),
        mcp.serve(),  # FastMCP 的 serve()
    ))
```

---

## 七、CLI 新增命令

```bash
devcontext capture          # 手动触发一次完整采集
devcontext capture --dry-run  # 预览模式，不实际写入
```

---

## 八、配置扩展

在 `config.py` 的 `Settings` 中新增：

### 全局采集配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `poll_interval_ms` | `500` | 轮询间隔 |
| `buffer_max_messages` | `200` | 缓冲区最大消息数 |
| `buffer_max_bytes` | `2 * 1024 * 1024` | 缓冲区最大字节数 |
| `batch_token_threshold` | `6000` | 攒批 token 阈值 |
| `batch_max_age_minutes` | `30` | 批次最大存活时间 |

### 数据源配置（按适配器分组）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `opencode_db_path` | `~/.opencode/opencode.db` | OpenCode SQLite 路径 |
| `filesystem_scan_paths` | `[]` | 文件夹扫描路径列表 |
| `filesystem_file_patterns` | `["*.jsonl", "*.md", "*.yaml"]` | 文件类型过滤 |
| `generic_sqlite_sources` | `[]` | 通用 SQLite 数据源配置列表 |

### GenericSQLiteAdapter 配置示例

```python
# config.py 中配置接入 Cursor 的 SQLite 数据库
generic_sqlite_sources = [
    {
        "source_name": "cursor",
        "db_path": "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb",
        "query_template": "SELECT key, value FROM ItemTable WHERE key LIKE 'composer:%'",
        "id_column": "key",
    }
]
```

新增数据源只需在配置中增加一项，无需修改采集器或流水线代码。

---

## 九、文件改动总览

| 文件 | 动作 | 说明 |
|------|:--:|------|
| `core/collectors/base.py` | **新建** | `BaseCollector`：采集策略基类（缓冲区 + 去噪 + 回调） |
| `core/collectors/polling.py` | **新建** | `PollingCollector`：轮询策略实现（~80 行） |
| `core/adapters/base.py` | 扩展 | 重构 `CollectorAdapter` 接口（统一轮询/Hook） |
| `core/adapters/opencode_sqlite.py` | **新建** | `OpenCodeSQLiteAdapter`（~40 行） |
| `core/adapters/filesystem.py` | **新建** | `FileSystemAdapter`：文件夹扫描（~50 行） |
| `core/adapters/generic_sqlite.py` | **新建** | `GenericSQLiteAdapter`：通用 SQLite（~30 行） |
| `core/adapters/opencode.py` | 保留 | 现有 `OpenCodeAdapter.collect()` 保持不变，新增 `incremental_query()` |
| `core/pipeline/batcher.py` | 重构 | 新增 `BatchWriter`（回调模式），保留 `Batcher` |
| `services/pipeline.py` | 重写 | `PipelineService`：多 collector 编排 + 回调链 + 生命周期 |
| `main.py` | 重写 | `serve()` 启动 daemon（多数据源配置） |
| `cli/app.py` | 扩展 | 新增 `devcontext capture` 命令 |
| `models/source.py` | 扩展 | 新增 `CollectorWatermark` 表 |
| `config.py` | 扩展 | 新增采集配置项（含多数据源配置） |

**不修改**：`extractor.py`、`validator.py`、`deduplicator.py`、`writer.py`、`consolidator.py`

---

## 十、采集可靠性分析

### 10.1 轮询不会丢消息的原因

| 风险场景 | 影响 | 防护机制 |
|---------|------|---------|
| DB 被锁/文件不可读（跳过本轮） | 延迟一个周期 | Watermark 持久化，下轮补上 |
| 进程崩溃（内存缓冲丢失） | 消息未落盘 | Watermark 持久化在 SQLite/磁盘，重启后从上次水位线继续 |
| 高并发写入（轮询间隔积压） | 缓冲区满 | 背压机制：200条/2MB 阈值触发 flush |
| 外部进程退出 | 采集中断 | 定时兜底扫描 + 文件系统 watermark 按 mtime 而非进程状态 |
| 文件系统数据源（文件被移动/删除） | fingerprint 失效 | `seen_files` 集合自动过期（按会话生命周期重置），不影响新文件采集 |

### 10.2 OpenViking 保护机制借鉴

| OpenViking 机制 | devContextMemo 映射 |
|---|---|
| `capturedTurnCount` 增量追踪 | `CollectorWatermark.last_message_id` |
| 全量原始消息归档 `messages.jsonl` | Step 1 JSONL 落盘 |
| 批量提交阈值 `commit_token_threshold=6000` | `batch_token_threshold=6000` |
| 会话边界 flush | 新 session 检测 → 立即 flush 缓冲区 |

---

## 十一、测试要点

### 11.1 单元测试

| 测试对象 | 覆盖点 |
|----------|--------|
| `CollectorAdapter` 接口 | `incremental_query` 返回格式、`normalize` 标准化正确性 |
| `OpenCodeSQLiteAdapter` | 增量查询 SQL 正确性、watermark 边界、空 DB 处理 |
| `FileSystemAdapter` | fingerprint 去重、mtime 过滤、glob 匹配、symlink 处理 |
| `GenericSQLiteAdapter` | 自定义 query_template 注入、多 source_name 隔离 |
| `BaseCollector` | 缓冲区满触发、`_strip_noise` 正确性、`_emit` 回调调用 |
| `PollingCollector` | 轮询间隔准时、异常重试、watermark 更新、stop() flush |
| `BatchWriter` | token 阈值触发、消息数阈值触发、超时强制落盘、按 session 分组 |
| `PipelineService` | 回调链注册正确性、多 collector 并发、优雅降级各场景 |
| `CollectorWatermark` | 读写正确性、多 source 隔离 |

### 11.2 集成测试

| 场景 | 验证点 |
|------|--------|
| Step 0→1 回调链 | `on_buffer_ready` 触发 → BatchWriter 正确落盘 JSONL |
| Step 1→6 全链路 | batch JSONL → `_meta.yaml` → extract → validate → dedup → write → consolidate |
| 多 collector 并发 | OpenCodeSQLite + FileSystem 同时运行，互不干扰 |
| 重启恢复 | 关闭 daemon → 重启 → 从 watermark 正确继续 |
| DB/文件不可读 | 跳过本轮 → 下轮补上 → 日志记录 |

### 11.3 E2E 测试

| 场景 | 验证点 |
|------|--------|
| `devcontext capture` CLI | 手动触发完整采集 → 知识库新增条目 |
| `devcontext capture --dry-run` | 预览模式不写入任何文件 |
| daemon 长期运行 | 24h 内存稳定、watermark 无漂移、无重复知识 |
| 空数据源冷启动 | `fetch_full()` 全量采集 → 正常完成
