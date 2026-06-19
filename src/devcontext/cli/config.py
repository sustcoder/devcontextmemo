"""dev config 命令 — 配置管理。

用法：
    dev config get [KEY]
    dev config set KEY VALUE
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from devcontext.config import settings

console = Console()


def config_get(
    key: str = typer.Argument(None, help="配置项名称（空则列出全部）"),
) -> None:
    """查看配置。"""
    all_config = {
        "db_path": settings.db_path,
        "knowledge_dir": settings.knowledge_dir,
        "staging_dir": settings.staging_dir,
        "deprecated_dir": settings.deprecated_dir,
        "quarantined_dir": settings.quarantined_dir,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_base_url": settings.llm_base_url,
        "host": settings.host,
        "port": settings.port,
    }

    if key:
        if key in all_config:
            console.print(f"{key} = {all_config[key]}")
        else:
            console.print(f"[red]未知配置项: {key}[/red]")
            raise typer.Exit(1)
    else:
        table = Table(title="配置项")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        for k, v in all_config.items():
            table.add_row(k, str(v))
        console.print(table)


def config_set(
    key: str = typer.Argument(..., help="配置项名称"),
    value: str = typer.Argument(..., help="配置值"),
) -> None:
    """设置配置（写入 .env 文件）。"""
    env_path = Path(".env")
    lines: list[str] = []
    found = False

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"DEVCONTEXT_{key.upper()}="):
                lines.append(f"DEVCONTEXT_{key.upper()}={value}")
                found = True
            else:
                lines.append(line)

    if not found:
        lines.append(f"DEVCONTEXT_{key.upper()}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]✓[/green] {key} = {value} (写入 .env)")


from pathlib import Path  # noqa: E402
