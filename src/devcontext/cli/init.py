"""dev init 命令 — 冷启动（创建 .devContextMemo/ 目录 + 初始化 DB）。

用法：
    dev init [--force]
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from devcontext.storage.sqlite import SQLiteStore

console = Console()


def init_command(force: bool = typer.Option(False, "--force", help="覆盖已有配置")) -> None:
    """冷启动：创建 .devContextMemo/ 目录结构 + 初始化 SQLite 数据库。"""
    devContextMemo_dir = Path(".devContextMemo")

    # 检查是否已初始化
    if devContextMemo_dir.exists() and not force:
        db_path = devContextMemo_dir / "devcontextmemo.db"
        if db_path.exists():
            console.print("[yellow].devContextMemo/ 已存在，使用 --force 覆盖[/yellow]")
            raise typer.Exit(1)

    # 创建目录结构
    dirs = [
        devContextMemo_dir / "knowledge",
        devContextMemo_dir / "staging",
        devContextMemo_dir / "deprecated",
        devContextMemo_dir / "quarantined",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]✓[/green] 创建 {d}")

    # 初始化 DB
    db_path = devContextMemo_dir / "devcontextmemo.db"
    store = SQLiteStore(str(db_path))
    store.init_db()
    tables = store.list_tables()
    store.close()

    console.print(f"  [green]✓[/green] 初始化数据库 ({len(tables)} 张表)")

    # 创建 AGENTS.md 骨架
    agents_md = devContextMemo_dir / "AGENTS.knowledge.md"
    if not agents_md.exists():
        agents_md.write_text(
            "# 项目知识（自动生成）\n\n" "<!-- 此文件由 devContextMemo 维护，请勿手动编辑 -->\n",
            encoding="utf-8",
        )
        console.print(f"  [green]✓[/green] 创建 {agents_md}")

    console.print("\n[bold green]devContextMemo 初始化完成！[/bold green]")
    console.print("下一步：开始编码对话，系统会自动采集知识。")
