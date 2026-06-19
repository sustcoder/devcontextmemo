"""CLI 应用入口 — Typer 实例 + 5 个命令注册。

命令：
    dev init: 冷启动（创建 .devContextMemo/ + 初始化 DB）
    dev review: 审核交互（list/approve/reject/restore）
    dev dream: 主动扫描（巩固 + 校准）
    dev status: 知识库状态查看
    dev config: 配置管理（get/set）
"""

from __future__ import annotations

import typer

from devcontext.cli.config import config_get, config_set
from devcontext.cli.dream import dream_command
from devcontext.cli.init import init_command
from devcontext.cli.review import review_approve, review_list, review_reject, review_restore
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
config_app = typer.Typer(help="配置管理")
config_app.command(name="get")(config_get)
config_app.command(name="set")(config_set)
app.add_typer(config_app, name="config")


# === dev review ===
review_app = typer.Typer(help="审核交互")
review_app.command(name="list")(review_list)
review_app.command(name="approve")(review_approve)
review_app.command(name="reject")(review_reject)
review_app.command(name="restore")(review_restore)
app.add_typer(review_app, name="review")


# === dev dream ===
app.command(name="dream")(dream_command)


if __name__ == "__main__":
    app()
