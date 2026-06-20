"""CLI 应用入口 — Typer 实例 + 7 组命令注册。

命令：
    dev init: 冷启动（创建 .devContextMemo/ + 初始化 DB）
    dev review: 审核交互（list/approve/reject/restore）
    dev dream: 主动扫描（巩固 + 校准）
    dev status: 知识库状态查看
    dev config: 配置管理（get/set）
    dev resource: 资源管理（add/list/show/search/remove/links）
    dev staging: Staging 批次管理（status/retry-failed）
"""

from __future__ import annotations

import typer

from devcontext.cli.config import config_get, config_set
from devcontext.cli.dream import dream_command
from devcontext.cli.init import init_command
from devcontext.cli.resource import resource_app
from devcontext.cli.review import review_approve, review_list, review_reject, review_restore
from devcontext.cli.staging_cli import staging_app
from devcontext.cli.status import status_command

app = typer.Typer(name="devcontext", help="码上记忆（devContextMemo）CLI 工具")


@app.callback()
def callback() -> None:
    """devContextMemo 知识管理 CLI。"""


# === dev init ===
app.command(name="init")(init_command)


# === dev status ===
app.command(name="status")(status_command)


# === dev config ===
config_app = typer.Typer(help="配置管理", no_args_is_help=True)
config_app.command(name="get")(config_get)
config_app.command(name="set")(config_set)
app.add_typer(config_app, name="config", no_args_is_help=True)


# === dev review ===
review_app = typer.Typer(help="审核交互", no_args_is_help=True)
review_app.command(name="list")(review_list)
review_app.command(name="approve")(review_approve)
review_app.command(name="reject")(review_reject)
review_app.command(name="restore")(review_restore)
app.add_typer(review_app, name="review", no_args_is_help=True)

# === dev resource ===
app.add_typer(resource_app, name="resource", no_args_is_help=True)

# === dev staging ===
app.add_typer(staging_app, name="staging", no_args_is_help=True)


# === dev dream ===
app.command(name="dream")(dream_command)


# === dev capture ===
@app.command("capture")
def capture_command(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview mode, no actual writes"
    ),
) -> None:
    """手动触发一次完整采集。

    无参数时执行实际采集并写入知识库。
    --dry-run 预览模式：仅显示会采集多少数据，不实际写入。
    """
    from pathlib import Path

    from devcontext.config import settings
    from devcontext.core.adapters.filesystem import FileSystemAdapter
    from devcontext.core.adapters.opencode_sqlite import OpenCodeSQLiteAdapter
    from devcontext.core.collectors.polling import PollingCollector
    from devcontext.core.pipeline.batcher import BatchWriter
    from devcontext.services.pipeline import PipelineService

    collectors = []

    if settings.opencode_db_path:
        db_path = Path(settings.opencode_db_path).expanduser()
        if db_path.exists():
            collectors.append(
                PollingCollector(
                    adapter=OpenCodeSQLiteAdapter(
                        db_path=str(db_path),
                    ),
                    poll_interval_ms=settings.poll_interval_ms,
                )
            )

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
        typer.echo("No data sources configured or available.")
        typer.echo(
            "  Configure opencode_db_path or filesystem_scan_paths in settings."
        )
        raise typer.Exit(code=1)

    batch_writer = BatchWriter(
        staging_dir=settings.staging_dir,
        token_threshold=settings.batch_token_threshold,
    )

    pipeline = PipelineService(
        collectors=collectors,
        batch_writer=batch_writer,
    )

    if dry_run:
        typer.echo("=== DRY RUN (preview mode) ===")

    result = pipeline.capture(dry_run=dry_run)

    for source, info in result["collectors"].items():
        if "error" in info:
            typer.echo(f"  [{source}] ERROR: {info['error']}")
        else:
            typer.echo(
                f"  [{source}] Found {info['messages_found']} new messages"
            )
            typer.echo(
                f"  [{source}] Watermarks: {info['watermarks']}"
            )

    if not dry_run:
        typer.echo("Capture complete.")


@app.command("serve")
def serve_command():
    """启动后台 daemon：自动轮询采集 + 全链路流水线处理。"""
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from devcontext.main import serve

    typer.echo("Starting devContextMemo daemon...")
    typer.echo(f"  OpenCode DB: ~/.local/share/opencode/opencode.db")
    typer.echo(f"  Staging dir: .devContextMemo/staging/")
    typer.echo("Press Ctrl+C to stop.")
    serve()


if __name__ == "__main__":
    app()
