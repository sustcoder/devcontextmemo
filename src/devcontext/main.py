"""devContextMemo — 码上记忆 daemon 入口。

启动后自动采集对话知识并串联全链路流水线（Steps 0-6）。
"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def serve():
    """启动 devContextMemo daemon。

    创建采集器 + 攒批器 + Steps 2-6 + 流水线编排，并发运行采集和处理。
    """
    from devcontext.config import settings
    from devcontext.core.adapters.filesystem import FileSystemAdapter
    from devcontext.core.adapters.opencode_sqlite import OpenCodeSQLiteAdapter
    from devcontext.core.collectors.polling import PollingCollector
    from devcontext.core.pipeline.batcher import BatchWriter
    from devcontext.core.pipeline.consolidator import Consolidator
    from devcontext.core.pipeline.deduplicator import Deduplicator
    from devcontext.core.pipeline.entity_extractor import EntityExtractor
    from devcontext.core.pipeline.extractor import Extractor
    from devcontext.core.pipeline.validator import Validator
    from devcontext.core.pipeline.writer import Writer
    from devcontext.services.pipeline import PipelineService
    from devcontext.storage.markdown import MarkdownStore
    from devcontext.storage.sqlite import SQLiteStore
    from devcontext.utils.llm import create_llm_client

    collectors = []

    # OpenCode SQLite 适配器
    opencode_db = Path(settings.opencode_db_path).expanduser()
    if opencode_db.exists():
        collectors.append(
            PollingCollector(
                adapter=OpenCodeSQLiteAdapter(db_path=str(opencode_db)),
            )
        )

    # 文件系统适配器
    if settings.filesystem_scan_paths:
        collectors.append(
            PollingCollector(
                adapter=FileSystemAdapter(
                    scan_paths=settings.filesystem_scan_paths,
                    file_patterns=settings.filesystem_file_patterns,
                ),
            )
        )

    if not collectors:
        logger.warning("no data sources configured, daemon will idle")
        return

    batch_writer = BatchWriter(staging_dir=settings.staging_dir)

    # Steps 2-6: 仅在 LLM 配置就绪时启用
    extractor = None
    entity_extractor = None
    validator = None
    deduplicator = None
    writer = None
    consolidator = None

    if settings.llm_api_key and settings.llm_base_url:
        llm_client = create_llm_client()
        domain_tree = {}  # 可从配置或数据库中加载

        staging = Path(settings.staging_dir)
        knowledge = Path(settings.knowledge_dir)
        deprecated = Path(settings.deprecated_dir)

        markdown_store = MarkdownStore(
            str(staging), str(knowledge), str(deprecated)
        )
        db_store = SQLiteStore(settings.db_path)
        db_store.init_db()

        extractor = Extractor(llm_client, domain_tree, str(staging))
        entity_extractor = EntityExtractor(llm_client, str(staging))
        validator = Validator(str(staging))
        deduplicator = Deduplicator(str(staging), existing_records=[])
        writer = Writer(markdown_store, db_store)
        consolidator = Consolidator(db_store, markdown_store)

        logger.info("Steps 2-6 enabled (LLM configured)")
    else:
        missing = []
        if not settings.llm_api_key:
            missing.append("DEVCONTEXT_LLM_API_KEY")
        if not settings.llm_base_url:
            missing.append("DEVCONTEXT_LLM_BASE_URL")
        msg = (
            "LLM 未配置，知识提炼流水线（Steps 2-6）无法启动。\n"
            "请设置以下环境变量：\n"
            f"  export DEVCONTEXT_LLM_API_KEY=<your-api-key>\n"
            f"  export DEVCONTEXT_LLM_BASE_URL=<api-base-url>\n"
            f"  export DEVCONTEXT_LLM_MODEL=<model-name>    # 可选，默认: abab6.5s-chat\n"
            f"当前缺失: {', '.join(missing)}"
        )
        logger.error(msg)
        raise SystemExit(msg)

    pipeline = PipelineService(
        collectors=collectors,
        batch_writer=batch_writer,
        extractor=extractor,
        entity_extractor=entity_extractor,
        validator=validator,
        deduplicator=deduplicator,
        writer=writer,
        consolidator=consolidator,
    )

    async def _run():
        await pipeline.start()
        while True:
            await asyncio.sleep(1)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.info("shutting down...")
        asyncio.run(pipeline.stop())


if __name__ == "__main__":
    serve()
