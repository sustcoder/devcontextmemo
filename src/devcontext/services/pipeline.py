"""流水线编排服务 — 多 collector 调度 + 回调链 + 生命周期管理。"""

import asyncio
import logging
from pathlib import Path

from devcontext.core.collectors.base import CleanMessage

logger = logging.getLogger(__name__)


class PipelineService:
    """流水线编排服务。

    持有所有 Step 实例，注册回调链，管理 start/stop 生命周期。

    Attributes:
        collectors: 采集器列表。
        batch_writer: 攒批器（BatchWriter）。
        extractor: Step 2a 知识提炼器（可选）。
        entity_extractor: Step 2b 实体提取器（可选）。
        validator: Step 3 验证器（可选）。
        deduplicator: Step 4 去重器（可选）。
        writer: Step 5 写入器（可选）。
        consolidator: Step 6 巩固器（可选）。
    """

    def __init__(
        self,
        collectors: list,
        batch_writer,
        extractor=None,
        entity_extractor=None,
        validator=None,
        deduplicator=None,
        writer=None,
        consolidator=None,
    ):
        """初始化编排服务。

        Args:
            collectors: 采集器列表（≥1 个）。
            batch_writer: BatchWriter 攒批器实例。
            extractor: Extractor 实例（可选）。
            entity_extractor: EntityExtractor 实例（可选）。
            validator: Validator 实例（可选）。
            deduplicator: Deduplicator 实例（可选）。
            writer: Writer 实例（可选）。
            consolidator: Consolidator 实例（可选）。
        """
        self.collectors = collectors
        self.batch_writer = batch_writer
        self.extractor = extractor
        self.entity_extractor = entity_extractor
        self.validator = validator
        self.deduplicator = deduplicator
        self.writer = writer
        self.consolidator = consolidator

        self._register_callbacks()
        self._running = False

    def _register_callbacks(self):
        """注册回调链：Step 0 → Step 1 → Step 2-6。"""
        for collector in self.collectors:
            collector.on_buffer_ready = self._on_messages

        self.batch_writer.on_batch_ready = self._on_batch_ready

    def _on_messages(self, messages: list[CleanMessage]) -> None:
        """Step 0 缓冲区满回调 → Step 1 攒批。

        Args:
            messages: CleanMessage 列表。
        """
        if not messages:
            return

        session_id = messages[0].session_id
        batch_path = self.batch_writer.on_messages(messages, session_id)
        if batch_path:
            logger.info(
                "batch flushed: %s (%d messages)", batch_path, len(messages)
            )

    def _on_batch_ready(self, batch_path: Path) -> None:
        """Step 1 批次就绪回调 → Step 2-6 顺序执行。

        任一步骤失败即终止，不传递空/损坏文件给后续步骤。

        Args:
            batch_path: 批次目录路径。
        """
        logger.info("processing batch: %s", batch_path)

        # 解析 messages.jsonl 文件路径
        try:
            current_path: Path = batch_path
            if current_path.is_dir():
                messages_file = current_path / "messages.jsonl"
                if not messages_file.exists():
                    candidates = sorted(current_path.glob("batch_*.jsonl"))
                    if not candidates:
                        raise FileNotFoundError(
                            f"No messages.jsonl or batch_*.jsonl in {batch_path}"
                        )
                    messages_file = candidates[0]
                current_path = messages_file
        except Exception:
            logger.error(
                "failed to resolve batch files: %s", batch_path, exc_info=True
            )
            self._update_batch_status(batch_path, "failed")
            return

        # Step 2a: 提炼
        if self.extractor:
            try:
                logger.info("  [Step 2a] extracting knowledge...")
                current_path = self.extractor.process(current_path)
                logger.info("  [Step 2a] done: %s", current_path)
            except Exception:
                logger.error(
                    "  [Step 2a] extraction failed", exc_info=True
                )
                self._update_batch_status(batch_path, "failed")
                return

        # Step 2b: 实体提取
        if self.entity_extractor:
            try:
                logger.info("  [Step 2b] extracting entities...")
                current_path = self.entity_extractor.process(current_path)
                logger.info("  [Step 2b] done: %s", current_path)
            except Exception:
                logger.error(
                    "  [Step 2b] entity extraction failed", exc_info=True
                )
                self._update_batch_status(batch_path, "failed")
                return

        # Step 3: 验证
        if self.validator:
            try:
                logger.info("  [Step 3] validating...")
                current_path = self.validator.process(current_path)
                logger.info("  [Step 3] done")
            except Exception:
                logger.error(
                    "  [Step 3] validation failed", exc_info=True
                )
                self._update_batch_status(batch_path, "failed")
                return

        # Step 4: 去重
        if self.deduplicator:
            try:
                logger.info("  [Step 4] deduplicating...")
                current_path = self.deduplicator.process(current_path)
                logger.info("  [Step 4] done")
            except Exception:
                logger.error(
                    "  [Step 4] dedup failed", exc_info=True
                )
                self._update_batch_status(batch_path, "failed")
                return

        # Step 5: 写入
        if self.writer:
            try:
                logger.info("  [Step 5] writing to knowledge...")
                results = self.writer.process(current_path)
                logger.info("  [Step 5] done: %d items written", len(results))
            except Exception:
                logger.error(
                    "  [Step 5] write failed", exc_info=True
                )
                self._update_batch_status(batch_path, "failed")
                return

        # Step 6: 巩固
        if self.consolidator:
            try:
                logger.info("  [Step 6] consolidating...")
                report = self.consolidator.process()
                logger.info(
                    "  [Step 6] done: promoted=%d pruned=%d",
                    report.promotions,
                    report.pruned_count,
                )
            except Exception:
                logger.error(
                    "  [Step 6] consolidation failed", exc_info=True
                )
                self._update_batch_status(batch_path, "failed")
                return

        # 全部完成 → 标记 done
        self._update_batch_status(batch_path, "done")
        logger.info("batch complete: %s", batch_path)

    def _update_batch_status(self, batch_path: Path, status: str):
        """更新 _meta.yaml 中的 status 字段。

        Args:
            batch_path: 批次目录或文件路径。
            status: 新状态（done/failed）。
        """
        import yaml

        batch_dir = batch_path if batch_path.is_dir() else batch_path.parent
        meta_file = batch_dir / "_meta.yaml"
        if not meta_file.exists():
            return

        try:
            meta = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
            meta["status"] = status
            meta_file.write_text(
                yaml.safe_dump(meta, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except Exception:
            logger.warning(
                "failed to update batch status: %s -> %s", meta_file, status
            )

    async def start(self):
        """启动编排服务（后台运行）。"""
        self._running = True

        # 启动时扫描 staging 中已有的 ready batch 并处理
        self._process_existing_batches()

        for collector in self.collectors:
            if hasattr(collector, "start"):
                asyncio.create_task(collector.start())
        logger.info(
            "PipelineService started with %d collector(s)",
            len(self.collectors),
        )

    def _process_existing_batches(self):
        """扫描 staging 目录中 status=ready 的 _meta.yaml，触发 Steps 2-6。"""
        import yaml

        staging = Path(self.batch_writer.staging_dir)
        if not staging.exists():
            return

        ready_batches: list[Path] = []
        for meta_file in sorted(staging.rglob("_meta.yaml")):
            try:
                meta = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if meta.get("status") == "ready":
                ready_batches.append(meta_file.parent)

        if not ready_batches:
            return

        total = len(ready_batches)
        for i, batch_dir in enumerate(ready_batches, 1):
            logger.info("[%d/%d] processing batch: %s", i, total, batch_dir.name)
            try:
                self._on_batch_ready(batch_dir)
                logger.info("[%d/%d] done: %s", i, total, batch_dir.name)
            except Exception:
                logger.error(
                    "[%d/%d] failed: %s", i, total, batch_dir.name, exc_info=True
                )

        logger.info("backlog complete: %d batches processed", total)

    async def stop(self):
        """停止编排服务。"""
        self._running = False
        for collector in self.collectors:
            if hasattr(collector, "stop"):
                await collector.stop()
        logger.info("PipelineService stopped")

    def capture(self, *, dry_run: bool = False) -> dict:
        """手动触发一次完整采集（调试/兜底用）。

        Args:
            dry_run: 预览模式，不实际写入。

        Returns:
            采集结果摘要 {"dry_run": bool, "collectors": {source_name: {...}}}.
        """
        results = {"dry_run": dry_run, "collectors": {}}

        for collector in self.collectors:
            source = collector.adapter.source_name
            try:
                if hasattr(collector, "_poll_once"):
                    messages = collector._poll_once()
                    results["collectors"][source] = {
                        "messages_found": len(messages),
                        "watermarks": dict(getattr(collector, "watermarks", {})),
                    }

                    # Flush buffer through pipeline (capture = full pipeline)
                    if not dry_run and collector.buffer:
                        flushed = collector._flush_buffer()
                        # Group by session_id and send to BatchWriter
                        by_session: dict[str, list] = {}
                        for msg in flushed:
                            by_session.setdefault(msg.session_id, []).append(msg)
                        for session_id, batch in by_session.items():
                            batch_path = self.batch_writer.on_messages(
                                batch, session_id, force=True
                            )
                            if batch_path:
                                results["collectors"][source][
                                    "batch_path"
                                ] = str(batch_path)

                        # Persist watermarks
                        if hasattr(collector, "_persist_watermarks"):
                            collector._persist_watermarks()
            except Exception as e:
                results["collectors"][source] = {"error": str(e)}

        return results
