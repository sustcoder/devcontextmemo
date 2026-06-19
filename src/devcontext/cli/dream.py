"""dev dream 命令 — 主动扫描（巩固 + 校准）。

用法：
    dev dream [--dry-run] [--scope SCOPE]
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from devcontext.config import settings
from devcontext.core.pipeline.consolidator import Consolidator
from devcontext.mcp.tools import calibrate_knowledge
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore

console = Console()


def dream_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="预览不实际修改"),
    scope: str = typer.Option("all", "--scope", "-s", help="校准范围"),
    skip_calibrate: bool = typer.Option(False, "--skip-calibrate", help="跳过校准"),
) -> None:
    """dev dream：巩固（晋升+修剪）+ 校准。"""
    db = SQLiteStore(settings.db_path)
    db.init_db()
    md = MarkdownStore(
        staging_dir=settings.staging_dir,
        knowledge_dir=settings.knowledge_dir,
        deprecated_dir=settings.deprecated_dir,
    )

    # === 巩固 ===
    console.print("\n[bold cyan]Phase 1: 巩固评估[/bold cyan]")
    if dry_run:
        console.print("  [dim](dry-run 模式，不实际修改)[/dim]")

    consolidator = Consolidator(db, md, dry_run=dry_run)
    report = consolidator.process()

    # 报告
    table = Table(title="巩固报告")
    table.add_column("指标", style="cyan")
    table.add_column("数量", justify="right", style="magenta")
    table.add_row("扫描总数", str(report.total_scanned))
    table.add_row("晋升", str(report.promotions))
    table.add_row("修剪", str(report.pruned))
    table.add_row("标记 STALE", str(report.stale_marked))
    table.add_row("标记 COLD", str(report.cold_marked))
    table.add_row("文件移动", str(report.moved_files))
    table.add_row("错误", str(report.errors))
    console.print(table)

    # === 校准 ===
    if not skip_calibrate:
        console.print("\n[bold cyan]Phase 2: 校准检查[/bold cyan]")
        cal_result = calibrate_knowledge(db, scope=scope, mode="quick")
        stale_count = cal_result.data["total_stale"]
        checked = cal_result.data["total_checked"]
        console.print(f"  检查 {checked} 条，发现 {stale_count} 条可能过时")

        if stale_count > 0:
            stale_table = Table(title="过时知识")
            stale_table.add_column("ID", style="cyan")
            stale_table.add_column("标题", style="white")
            stale_table.add_column("原因", style="yellow")
            for item in cal_result.data["stale_items"][:10]:
                stale_table.add_row(
                    item["id"],
                    item["title"][:30],
                    item["reason"],
                )
            console.print(stale_table)

    console.print("\n[bold green]dev dream 完成[/bold green]")
    db.close()
