"""CLI Staging 管理命令 — staging status/retry-failed。

Spec 依据：``docs/superpowers/specs/2026-06-19-Phase1-数据源偏离度调研与修复方案-V1.0.md`` §6.1.1.1
"""

from __future__ import annotations

import typer

staging_app = typer.Typer(help="Staging 批次管理", no_args_is_help=True)


@staging_app.command("status")
def staging_status() -> None:
    """查看 staging 批次状态（ready/done/failed）。"""
    from devcontext.config import settings
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(str(settings.db_path))
    store.init_db()
    conn = store.get_connection()

    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM batch_log GROUP BY status"
        ).fetchall()
        if not rows:
            typer.echo("No batch logs found.")
            return
        for row in rows:
            typer.echo(f"  {row['status']}: {row['cnt']}")
    finally:
        store.close()


@staging_app.command("retry-failed")
def staging_retry_failed(
    session_id: str = typer.Option(
        None, "--session-id", help="仅重置指定 session 的批次"
    ),
) -> None:
    """批量重置 status=failed → ready（重跑 daemon 即可再处理）。"""
    from datetime import UTC, datetime

    from devcontext.config import settings
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(str(settings.db_path))
    store.init_db()
    conn = store.get_connection()
    now = datetime.now(UTC).isoformat()

    try:
        if session_id:
            result = conn.execute(
                "UPDATE batch_log SET status = 'ready', updated_at = ? "
                "WHERE session_id = ? AND status = 'failed'",
                [now, session_id],
            )
        else:
            result = conn.execute(
                "UPDATE batch_log SET status = 'ready', updated_at = ? "
                "WHERE status = 'failed'",
                [now],
            )
        conn.commit()
        count = result.rowcount
        if count == 0:
            typer.echo("No failed batches to retry.")
        else:
            typer.echo(
                f"Reset {count} failed batch(es) to ready. Restart daemon to reprocess."
            )
    finally:
        store.close()
