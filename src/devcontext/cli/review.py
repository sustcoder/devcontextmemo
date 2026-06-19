"""dev review 命令 — 审核交互（list/approve/reject/restore）。

用法：
    dev review list [--status STATUS]
    dev review approve KNOWLEDGE_ID
    dev review reject KNOWLEDGE_ID [--reason REASON]
    dev review restore KNOWLEDGE_ID
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from devcontext.config import settings
from devcontext.services.review import ReviewService
from devcontext.storage.markdown import MarkdownStore
from devcontext.storage.sqlite import SQLiteStore

console = Console()


def review_list(
    status: str = typer.Option(None, "--status", "-s", help="按状态过滤"),
) -> None:
    """列出待审核知识。"""
    db = SQLiteStore(settings.db_path)
    db.init_db()
    md = MarkdownStore(
        staging_dir=settings.staging_dir,
        knowledge_dir=settings.knowledge_dir,
        deprecated_dir=settings.deprecated_dir,
    )
    service = ReviewService(db, md)
    pending = service.list_pending(status=status)

    if not pending:
        console.print("[green]没有待审核的知识[/green]")
        db.close()
        return

    table = Table(title=f"待审核知识 ({len(pending)} 条)")
    table.add_column("ID", style="cyan")
    table.add_column("标题", style="white")
    table.add_column("状态", style="yellow")
    table.add_column("置信度", justify="right", style="magenta")
    table.add_column("领域", style="green")

    for item in pending:
        table.add_row(
            item["id"],
            item["title"][:40],
            item["status"],
            f"{item.get('confidence', 0):.2f}",
            item.get("domain", ""),
        )
    console.print(table)
    console.print("\n[dim]使用 dev review approve <ID> 采纳，dev review reject <ID> 拒绝[/dim]")
    db.close()


def review_approve(
    knowledge_id: str = typer.Argument(..., help="知识 ID"),
) -> None:
    """采纳知识（→ active）。"""
    db = SQLiteStore(settings.db_path)
    db.init_db()
    md = MarkdownStore(
        staging_dir=settings.staging_dir,
        knowledge_dir=settings.knowledge_dir,
        deprecated_dir=settings.deprecated_dir,
    )
    service = ReviewService(db, md)
    result = service.approve(knowledge_id)

    if result.success:
        console.print(f"[green]✓[/green] 已采纳 {knowledge_id} → active")
        if result.moved_to:
            console.print(f"  文件移动至: {result.moved_to}")
    else:
        console.print(f"[red]✗ 失败: {result.error}[/red]")
        raise typer.Exit(1)
    db.close()


def review_reject(
    knowledge_id: str = typer.Argument(..., help="知识 ID"),
    reason: str = typer.Option("human_rejected", "--reason", "-r", help="拒绝原因"),
) -> None:
    """拒绝知识（→ deprecated）。"""
    db = SQLiteStore(settings.db_path)
    db.init_db()
    md = MarkdownStore(
        staging_dir=settings.staging_dir,
        knowledge_dir=settings.knowledge_dir,
        deprecated_dir=settings.deprecated_dir,
    )
    service = ReviewService(db, md)
    result = service.reject(knowledge_id, reason=reason)

    if result.success:
        console.print(f"[green]✓[/green] 已拒绝 {knowledge_id} → deprecated ({reason})")
    else:
        console.print(f"[red]✗ 失败: {result.error}[/red]")
        raise typer.Exit(1)
    db.close()


def review_restore(
    knowledge_id: str = typer.Argument(..., help="知识 ID"),
) -> None:
    """恢复知识（deprecated → staged）。"""
    db = SQLiteStore(settings.db_path)
    db.init_db()
    md = MarkdownStore(
        staging_dir=settings.staging_dir,
        knowledge_dir=settings.knowledge_dir,
        deprecated_dir=settings.deprecated_dir,
    )
    service = ReviewService(db, md)
    result = service.restore(knowledge_id)

    if result.success:
        console.print(f"[green]✓[/green] 已恢复 {knowledge_id} → staged")
    else:
        console.print(f"[red]✗ 失败: {result.error}[/red]")
        raise typer.Exit(1)
    db.close()
