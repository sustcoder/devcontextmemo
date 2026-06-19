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

    # 采集流水线状态
    _print_pipeline_status()

    store.close()


def _print_pipeline_status():
    """打印采集流水线 staging 状态。"""
    import yaml
    from pathlib import Path

    staging_dir = Path(settings.staging_dir)
    if not staging_dir.exists():
        return

    meta_files = list(staging_dir.rglob("_meta.yaml"))
    if not meta_files:
        return

    status_count: dict[str, int] = {}
    total_messages = 0
    for mf in meta_files:
        try:
            meta = yaml.safe_load(mf.read_text(encoding="utf-8"))
            s = meta.get("status", "unknown")
            status_count[s] = status_count.get(s, 0) + 1
            total_messages += meta.get("message_count", 0)
        except Exception:
            continue

    console.print(f"\n[bold]采集流水线[/bold]")
    table = Table(title=f"Staging 批次状态 ({staging_dir})")
    table.add_column("状态", style="cyan")
    table.add_column("批次数", justify="right", style="magenta")

    for s in ["ready", "done", "failed"]:
        cnt = status_count.get(s, 0)
        style = ""
        if s == "ready" and cnt > 0:
            style = " [yellow](等待 daemon 处理)[/yellow]"
        elif s == "failed" and cnt > 0:
            style = " [red](API key 错误?)[/red]"
        table.add_row(s, str(cnt) + style)

    console.print(table)
    console.print(f"  总消息数: {total_messages}")
