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
