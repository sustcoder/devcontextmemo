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
┌──────────────────────────────────────────────────────────────┐
│                    main.py: serve()                          │
│  ┌─────────────────────┐  ┌────────────────────────────────┐ │
│  │  PipelineService    │  │  MCP Server (已有)             │ │
│  │  (编排层，回调链)    │  │  127.0.0.1:9020               │ │
│  └──────┬──────────────┘  └────────────────────────────────┘ │
│         │                                                     │
│  ┌──────▼──────────────────────────────────────────────────┐ │
│  │              PipelineService 回调链                       │ │
│  │                                                          │ │
│  │  MessageCollector ──callback──► BatchWriter               │ │
│  │  (Step 0: 轮询采集)           (Step 1: 攒批落盘)          │ │
│  │                                         │                 │ │
│  │                              ┌──────────▼──────────┐     │ │
│  │                              │  Step 2→6 顺序调用   │     │ │
│  │                              │  extract → validate  │     │ │
│  │                              │  → dedup → write     │     │ │
│  │                              │  → consolidate       │     │ │
│  │                              └─────────────────────┘     │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘

          OpenCode SQLite (外部，只读)
```

**设计原则**：
- **回调链模式**：Step N 完成时通过 callback 触达 Step N+1，松耦合
- **文件作为契约**：Step 1 落盘 JSONL 后，通过文件路径传递给 Step 2-6
- **优雅降级**：某 Step 失败时保留中间产物，记录日志，不丢弃数据

---

## 三、Step 0 — 多源可扩展采集器

### 3.1 基类：BaseCollector

```
BaseCollector (抽象基类)
├── 通用能力（与数据源无关）
│   ├─ 轮询线程 (poll_interval=500ms)
│   ├─ 内存缓冲 (max 200条 / 2MB)
│   ├─ on_buffer_ready 回调注册
│   ├─ _strip_noise() 三层剥壳
│   └─ 水位线管理 (CollectorWatermark 表)
│
└── 抽象方法 → 子类实现
    ├─ incremental_query(watermarks) → list[Message]
    └─ source_name → str
```

### 3.2 数据源适配器：CollectorAdapter 接口

```python
class CollectorAdapter:
    source_name: str
    incremental_query(watermarks: dict) -> list[dict]
    normalize(raw: dict) -> dict
```

**现有适配器**：`OpenCodeAdapter`（已有 `collect()` + `normalize()`），需新增 `incremental_query()` 方法支持按 watermark 增量拉取。

### 3.3 子类：OpenCodeCollector

```
OpenCodeCollector(BaseCollector)
├── 适配器: OpenCodeAdapter
├── incremental_query() → 增量 SQL (watermark > last_message_id)
└── 复用 _strip_noise() + 缓冲区逻辑
```

### 3.4 触发策略（MiMo-Code 启发叠加）

| 优先级 | 触发条件 | 行为 |
|:--:|------|------|
| P0 | 会话边界检测 | 轮询检测到新 session_id → 立即 flush 上一 session 缓冲区 |
| P1 | 缓冲区累积触发 | token ≥ 6000 或 200 条消息 → 触发 on_buffer_ready 回调 |
| P2 | 定时兜底 | 每日扫描未 flush 的 session → 全量采集 |
| P3 | CLI 手动触发 | `devcontext capture` 命令 |

### 3.5 适配器双模架构（决策）

**Phase 1：轮询模式**（当前实施）
- 适合有 SQLite 存储的 AI 工具（OpenCode/Cursor 等）
- 外部只读，零侵入
- Watermark 机制保证不丢消息

**Phase 2+：Hook 模式**（未来扩展）
- 适合暴露生命周期 hook/MCP 的工具
- 同一 `BaseCollector` 接口，新增 `XxxHookCollector` 即可
- 流水线无需任何改动

### 3.6 扩展点：FileScanner

```
FileScanner(CollectorAdapter)   # Phase 2 预留
├── 递归遍历指定文件路径
├── fingerprint 去重 (size + mtime)
├── 识别文件类型 (code/md/yaml)
└── 输出 CleanMessage → 进入同一流水线
```

新增采集源只需实现 `CollectorAdapter` 接口，BaseCollector 完全复用。

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

### 4.2 与现有 Batcher 的关系

- 现有 `Batcher`：文件扫描模式（从 raw_dir 读取 session JSONL）
- 新增 `BatchWriter`：回调模式（从内存 Buffer 直接接收消息）
- **两者共存**，`BatchWriter` 收到消息后直接写 JSONL（跳过 raw_dir 中转）

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
  ├── 创建 OpenCodeCollector（绑定 OpenCodeAdapter）
  ├── 注册回调链
  ├── 启动轮询线程（后台 asyncio task）
  └── 启动 MCP Server（FastMCP）
  
PipelineService.stop()
  ├── 停止轮询线程
  ├── flush 剩余缓冲区
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
    from devcontext.core.adapters.opencode import OpenCodeAdapter
    from devcontext.core.pipeline.receiver import OpenCodeCollector
    from devcontext.core.pipeline.batcher import BatchWriter
    from devcontext.mcp.server import MCPServer
    
    # 创建 Step 实例
    collector = OpenCodeCollector(
        adapter=OpenCodeAdapter(db_path=settings.opencode_db_path),
        raw_dir=settings.raw_dir,
    )
    batcher = BatchWriter(
        staging_dir=settings.staging_dir,
        token_threshold=6000,
    )
    
    # 创建编排服务
    pipeline = PipelineService(
        collector=collector,
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

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `opencode_db_path` | `~/.opencode/opencode.db` | OpenCode SQLite 路径 |
| `poll_interval_ms` | `500` | 轮询间隔 |
| `buffer_max_messages` | `200` | 缓冲区最大消息数 |
| `buffer_max_bytes` | `2 * 1024 * 1024` | 缓冲区最大字节数 |
| `batch_token_threshold` | `6000` | 攒批 token 阈值 |
| `batch_max_age_minutes` | `30` | 批次最大存活时间 |

---

## 九、文件改动总览

| 文件 | 动作 | 说明 |
|------|:--:|------|
| `core/pipeline/receiver.py` | 重构 | 新增 `BaseCollector` + `OpenCodeCollector`，保留 `Receiver` |
| `core/adapters/base.py` | 扩展 | 新增 `CollectorAdapter` 协议接口 |
| `core/adapters/opencode.py` | 微调 | 新增 `incremental_query()` 方法 |
| `core/pipeline/batcher.py` | 重构 | 新增 `BatchWriter`，保留 `Batcher` |
| `services/pipeline.py` | 重写 | `PipelineService`：编排 + 回调链 + 生命周期 |
| `main.py` | 重写 | `serve()` 启动 daemon |
| `cli/app.py` | 扩展 | 新增 `devcontext capture` 命令 |
| `models/source.py` | 扩展 | 新增 `CollectorWatermark` 表 |
| `config.py` | 扩展 | 新增采集相关配置项 |

**不修改**：`extractor.py`、`validator.py`、`deduplicator.py`、`writer.py`、`consolidator.py`

**轻微修改**：`adapter/opencode.py`（新增 `incremental_query()` 方法，约 30 行）

---

## 十、采集可靠性分析

### 10.1 轮询不会丢消息的原因

| 风险场景 | 影响 | 防护机制 |
|---------|------|---------|
| DB 被锁（跳过本轮） | 延迟一个周期 | Watermark 记录 last_message_id，下轮补上 |
| 进程崩溃（内存缓冲丢失） | 消息未落盘 | Watermark 持久化在 SQLite，重启后从上次水位线继续 |
| 高并发写入（轮询间隔积压） | 缓冲区满 | 背压机制：200条/2MB 阈值触发 flush |
| OpenCode 进程退出 | 采集中断 | 定时兜底扫描：每日全量采集未 flush session |

### 10.2 OpenViking 保护机制借鉴

| OpenViking 机制 | devContextMemo 映射 |
|---|---|
| `capturedTurnCount` 增量追踪 | `CollectorWatermark.last_message_id` |
| 全量原始消息归档 `messages.jsonl` | Step 1 JSONL 落盘 |
| 批量提交阈值 `commit_token_threshold=6000` | `batch_token_threshold=6000` |
| 会话边界 flush | 新 session 检测 → 立即 flush 缓冲区 |

---

## 十一、测试要点
