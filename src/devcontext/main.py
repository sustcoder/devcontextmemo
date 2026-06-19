"""devContextMemo — 码上记忆 daemon 入口。

启动后自动采集对话知识并串联全链路流水线（Steps 0-6）。
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


def serve():
    """启动 devContextMemo daemon。

    创建采集器 + 攒批器 + 流水线编排，并发运行采集和后续处理。
    """
    from pathlib import Path

    from devcontext.config import settings
    from devcontext.core.adapters.filesystem import FileSystemAdapter
    from devcontext.core.adapters.opencode_sqlite import OpenCodeSQLiteAdapter
    from devcontext.core.collectors.polling import PollingCollector
    from devcontext.core.pipeline.batcher import BatchWriter
    from devcontext.services.pipeline import PipelineService

    collectors = []

    # OpenCode SQLite 适配器
    opencode_db = Path("~/.config/opencode/opencode.db").expanduser()
    if opencode_db.exists():
        collectors.append(
            PollingCollector(
                adapter=OpenCodeSQLiteAdapter(
                    db_path=str(opencode_db),
                ),
            )
        )

    # 文件系统适配器 — 扫描 raw 目录
    raw_dir = Path(settings.raw_dir).expanduser()
    if raw_dir.exists():
        collectors.append(
            PollingCollector(
                adapter=FileSystemAdapter(
                    scan_paths=[str(raw_dir)],
                ),
            )
        )

    if not collectors:
        logger.warning("no data sources configured, daemon will idle")
        return

    batch_writer = BatchWriter(
        staging_dir=settings.staging_dir,
    )

    pipeline = PipelineService(
        collectors=collectors,
        batch_writer=batch_writer,
    )

    async def _run():
        await pipeline.start()
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("shutting down...")
        asyncio.run(pipeline.stop())


if __name__ == "__main__":
    serve()
