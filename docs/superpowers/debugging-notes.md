# 调试经验记录

> 记录开发过程中发现的非显而易见的 bug 及处理方案，供后续参考。

---

## #1: E2E 比单元测试多发现数据流断点

**日期:** 2026-06-19
**关联:** auto-capture + pipeline orchestration

**问题：** `devcontext capture` 命令能采集到 7 条消息，但 staging 目录未生成任何文件。单元测试全部通过。

**根因：** 3 个串联的数据流断点，mock 单元测试全部漏过：

| 断点 | 位置 | 单元测试为什么漏过 |
|------|------|-------------------|
| `capture()` 只调用 `_poll_once()` 但未触发 `_flush_buffer()` → `_emit()` | `services/pipeline.py` | mock 不关心消息是否落盘 |
| 水位线键 `source_name` 与 WatermarkStore 的 `source_name` 外层键冲突，导致双层嵌套 `{"opencode": {"opencode": "ts"}}` | `core/collectors/polling.py` | mock 适配器不调用真实 WatermarkStore |
| `normalize()` 丢弃了增量查询必需的 `id` 字段，导致 watermark 回退为 `str(time.time())` | `core/adapters/opencode_sqlite.py` | mock 适配器手动塞 `id` 字段 |

**修复：**
1. `capture()` 中按 session 分组后调用 `batch_writer.on_messages(force=True)` 强制落盘
2. 统一水位线键名为 `checkpoint`，避免与 WatermarkStore 分区键冲突
3. `normalize()` 保留 `id` 字段，确保 `_update_watermarks` 能取到真实消息 ID

**经验：** mock 单元测试覆盖的是「接口契约」，E2E 覆盖的是「数据流契约」。当数据流跨越多层（adapter → collector → pipeline → batch_writer → staging），必须用真实数据源跑端到端。不应仅靠 mock 单元测试就认为功能完整。

---

## #2: 采集策略与 CLI 的触发语义不同

**日期:** 2026-06-19
**关联:** BatchWriter token threshold

**问题：** `capture` 命令手动触发后，消息进入 BatchWriter 缓冲区但未落盘，因为 token 阈值（6000）远超测试消息总量。

**根因：** daemon 模式和 CLI 模式对「攒批」的语义不同：

| 模式 | 触发方 | 预期行为 | 阈值应 |
|------|--------|---------|--------|
| daemon `_poll_loop` | 自动轮询 | 等 token 累积到阈值再落盘 | 生效 |
| CLI `capture` | 用户手动 | 立即落盘所有采集到的消息 | 忽略 |

**修复：** 给 `BatchWriter.on_messages()` 增加 `force` 参数。daemon 回调传 `force=False`（等阈值），CLI `capture` 传 `force=True`（立即落盘）。

**经验：** 同一接口服务于不同触发模式时，行为差异应通过显式参数区分，而非依赖阈值「恰好满足」。默认行为是单场景最优，特殊场景用 flag 覆盖。

---

## #3: 水位线是跨层契约，键名变更需全局一致

**日期:** 2026-06-19
**关联:** PollingCollector ↔ Adapter watermark 键名

**问题：** 3 个适配器使用了 3 种不同的水位线键名：
- `OpenCodeSQLiteAdapter`: `last_message_id`
- `FileSystemAdapter`: `last_scan_time`
- `GenericSQLiteAdapter`: `{source_name}_last_id`

而 `PollingCollector._persist_watermarks()` 用 `self.adapter.source_name` 作为键存到 `WatermarkStore`，导致双层嵌套 `{"opencode": {"opencode": timestamp}}`。

**根因：** 水位线 dict 是 PollingCollector ↔ Adapter 之间的契约，但没有统一的键名规范。每个适配器各写一套键名，造成读写不一致。

**修复：** 统一所有适配器使用 `checkpoint` 作为水位线键名。`WatermarkStore` 以 `source_name` 分区存储：
```json
{"opencode": {"checkpoint": "msg-008"}, "filesystem": {"checkpoint": 1234567890.0}}
```

**经验：** 跨层共享的 dict 结构，键名必须在所有读写方之间保持一致。发现键名不统一时，选择一个通用名并全局替换，比保留多键名的「灵活性」更安全。

---

## #4: 适配器 SQL 假设与真实 schema 不一致

**日期:** 2026-06-19
**关联:** OpenCodeSQLiteAdapter schema 适配

**问题：** adapter 按假设的 `conversation`/`role`/`content` 列写 SQL，真实 opencode DB 使用 `session`/`data(JSON)` 列。

**根因：** 开发时用 mock SQLite 创建了假想的表结构（conversation + message.role + part.type/text），而真实 opencode 的 schema 是：
- 表名 `session` 非 `conversation`
- `message.data` 是 JSON 文本，内含 `role` 等字段
- `part.data` 是 JSON 文本，内含 `type`/`text` 字段
- `time_created` 是整数毫秒时间戳，非 ISO 字符串

**修复：** SQL 改为 `json_extract(m.data, '$.role')`、`json_extract(p.data, '$.type')` 等。

**经验：** 写数据源适配器时，必须先读真实数据源的表结构和样例数据，再写 SQL。不能靠猜测或简化 mock。

---

## #5: IsADirectoryError — Step 2 收到目录而非文件

**日期:** 2026-06-19
**关联:** PipelineService._on_batch_ready

**问题：** daemon 启动后 `_on_batch_ready` 报 `IsADirectoryError`，因为 `Extractor.process()` 期望 JSONL 文件路径，实际传入的是 batch 目录路径。

**根因：** `BatchWriter._flush_batch()` 返回 batch 目录路径，回调传给 `_on_batch_ready`，但 Steps 2-6 的 `process()` 方法期望的是文件路径。目录 vs 文件的契约在回调链中断。

**修复：** `_on_batch_ready` 中判断传入的是目录时，解析内部的 `messages.jsonl`（兼容旧 `batch_*.jsonl`）再传递给 Step 2。

**经验：** 回调之间传递的路径对象，必须在上下游文档中明确是「目录」还是「文件」。同一个 Path 对象在不同环节可能有不同语义。

---

## #6: async start/stop 被同步调用

**日期:** 2026-06-19
**关联:** PipelineService.start/stop + PollingCollector

**问题：** `PipelineService.start()` 中 `collector.start()` 触发 `RuntimeWarning: coroutine was never awaited`。`collector.start()` 是 `async def`，但被同步调用。

**根因：** PipelineService 的 `_start_collectors()` 是同步方法，但它调用的是 async 的 `collector.start()`。重构时只改了 PipelineService.start 为 async，但内部调用方式未同步修改。

**修复：** 改为 `asyncio.create_task(collector.start())`，同理 `stop()` 改为 `await collector.stop()`。

**经验：** async/sync 边界是 Python 常见的 bug 来源。async 方法不能用同步方式调用。`import asyncio` 不能漏。

---

## #7: LLM 未配置时静默跳过 Steps 2-6

**日期:** 2026-06-19
**关联:** serve() 启动体验

**问题：** 最初 LLM 未配置时，`serve()` 只打 warning 日志，静默跳过 Steps 2-6。用户启动后看不到任何错误，也不知道为什么 staging 有数据但 knowledge 为空。

**根因：** 过度防御性设计。把「LLM 可选」理解为「静默跳过」，但用户期望的是明确知道缺少什么配置。

**修复：** 改为 `SystemExit` 并打印清晰的错误信息，列出缺失的环境变量（`DEVCONTEXT_LLM_API_KEY` / `DEVCONTEXT_LLM_BASE_URL`），以及完整的 export 命令。

**经验：** 用户面对的不是代码是终端。静默跳过 → 用户迷惑。明确报错 + 给出修复命令 → 用户秒懂。宁可报错吓一跳，不要静默走不通。

---

## #8: daemon 启动时不回扫已有 staging batch

**日期:** 2026-06-19
**关联:** PipelineService.start() + staging backlog

**问题：** 之前 `devcontext capture` 手动采集的 batch 留在 staging 里（status=ready），但 `devcontext serve` 启动后只等新回调，不回扫已有数据。

**根因：** `_on_batch_ready` 是事件驱动的回调，只在 `BatchWriter._flush_batch()` 时触发。启动时没有「扫描已有 ready batch」的逻辑。

**修复：** `PipelineService.start()` 中新增 `_process_existing_batches()`，扫描 staging 目录中所有 `_meta.yaml`，对 status=ready 的逐个触发 `_on_batch_ready`。

**经验：** 事件驱动系统的冷启动需要显式的「追赶」逻辑。不能假设启动前没有遗留状态。

---

## #9: 集成测试 watermark 跨测试污染

**日期:** 2026-06-19
**关联:** integration test isolation

**问题：** 集成测试首次跑 4/4 通过，第二次跑全失败（采集到 0 条消息）。因为 `WatermarkStore` 使用固定路径 `~/.devContextMemo/watermarks.json`，第一次测试的 watermark 被持久化后，第二次测试读到旧水位线跳过了所有消息。

**根因：** `WatermarkStore.load()` 的路径是全局常量 `DEFAULT_WATERMARK_FILE`，所有测试共享同一个文件。PollingCollector 初始化时自动加载。

**修复：** 测试中用 `unittest.mock.patch` 替换 `DEFAULT_WATERMARK_FILE` 为 `tmp_path` 下的临时文件，保证每个测试有独立的水位线。

**经验：** 任何带持久化状态的组件，测试必须隔离持久化路径。常量定义的默认路径是集成测试污染的常见来源。

---

## #10: LLM 失败导致下游步骤连锁崩溃

**日期:** 2026-06-19
**关联:** PipelineService._on_batch_ready error handling

**问题：** LLM API key 401 导致 `Extractor.process()` 失败后，pipeline 继续把空/损坏的输出传给 `EntityExtractor` → `Validator`，最终 Validator 报 `ValueError: Knowledge file is empty`。而且每次重启 daemon 都会重试同一个失败的 batch。

**根因：** 原 `_on_batch_ready` 用一个外层 `try/except` 包住所有步骤，单个步骤失败后仍继续执行后续步骤。同时 `_process_existing_batches()` 只检查 `status=ready`，失败后的 batch 状态仍是 ready，导致无限重试。

**修复：**
1. 每个 Step 拆分为独立的 `try/except`，失败后立即 `return`，不再传递给后续步骤
2. 新增 `_update_batch_status(batch_path, status)` 方法更新 `_meta.yaml`
3. 失败时标记 `status: failed`，成功时标记 `status: done`
4. `_process_existing_batches()` 已有 status 检查逻辑，无需修改（自动跳过 failed/done）

**经验：** 流水线的错误处理不能是一层大 `try/except`，必须每步独立。否则前一步的失败会被后一步的报错掩盖，定位问题困难。失败状态必须持久化，否则重启后无限重试。

---

## #11: 状态机 `staged → active` 缺失导致绿色通道被阻断

**日期:** 2026-06-19
**关联:** ALLOWED_TRANSITIONS + Consolidator

**问题：** LLM 提炼正常，知识已写入 `knowledge/` 目录，但 Consolidator 报错：
```
Invalid transition staged→active for kw-20260619-014, skipping
```

**根因：** `promotion.py` 的 T2 绿色通道规则允许 `staged + confidence ≥ 0.95 → active`，但 `ALLOWED_TRANSITIONS` 矩阵中 `staged` 没有 `active`。Consolidator 调用 `is_valid_transition` 校验时拒绝了这条转换。

**同时发现：** Writer 写入的知识初始状态是 `staged`，但管道知识已经过 validate + dedup，不应退回 `staged`。`staged` 是给 MCP 手动写入的起点。

**修复：**
1. `ALLOWED_TRANSITIONS["staged"]` 加 `"active"`
2. `Writer` 默认状态 `staged` → `candidate`
3. 新增 68 个状态机测试覆盖全部转换

**经验：** promotion 逻辑和 ALLOWED_TRANSITIONS 是双向独立维护的，没有编译期检查。修改其中一处必须检查另一处是否匹配。
