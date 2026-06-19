"""dev status 命令 — 知识库状态查看。

用法：
    dev status [--domain DOMAIN]
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from devcontext.config import settings
from devcontext.storage.sqlite import SQLiteStore

console = Console()


def status_command(
    domain: str = typer.Option(None, "--domain", "-d", help="按领域过滤"),
) -> None:
    """查看知识库状态：按状态/领域统计。"""
    db_path = settings.db_path
    store = SQLiteStore(db_path)
    store.init_db()
    conn = store.get_connection()

    # 总览
    total = conn.execute("SELECT COUNT(*) FROM knowledge_index").fetchone()[0]
    console.print(f"\n[bold]知识库总览[/bold] ({db_path})")
    console.print(f"  总知识数: {total}")

    # 按状态统计
    table = Table(title="按状态分布")
    table.add_column("状态", style="cyan")
    table.add_column("数量", justify="right", style="magenta")

    status_rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM knowledge_index "
        + ("WHERE domain = ? " if domain else "")
        + "GROUP BY status ORDER BY cnt DESC",
        [domain] if domain else [],
    ).fetchall()

    for row in status_rows:
        table.add_row(row[0], str(row[1]))
    console.print(table)

    # 按领域统计
    domain_table = Table(title="按领域分布")
    domain_table.add_column("领域", style="cyan")
    domain_table.add_column("数量", justify="right", style="magenta")
    domain_table.add_column("平均置信度", justify="right", style="green")

    domain_rows = conn.execute(
        "SELECT domain, COUNT(*) as cnt, AVG(confidence) as avg_conf "
        "FROM knowledge_index GROUP BY domain ORDER BY cnt DESC LIMIT 10"
    ).fetchall()

    for row in domain_rows:
        avg_conf = f"{row[2]:.2f}" if row[2] else "N/A"
        domain_table.add_row(row[0] or "(空)", str(row[1]), avg_conf)
    console.print(domain_table)

    # 待审核
    pending = conn.execute(
        "SELECT COUNT(*) FROM knowledge_index WHERE status IN ('pending_review', 'draft')"
    ).fetchone()[0]
    if pending > 0:
        console.print(f"\n[yellow]⚠ {pending} 条知识待审核（dev review）[/yellow]")

    store.close()
