"""CLI 资源管理命令 — resource add/list/show/search/remove/links。

Spec 依据：``docs/superpowers/specs/2026-06-19-Phase1-数据源偏离度调研与修复方案-V1.0.md`` §6.1
"""

from __future__ import annotations

import typer

resource_app = typer.Typer(help="资源管理（Resource Track）", no_args_is_help=True)


@resource_app.command("add")
def resource_add(
    path: str = typer.Argument(..., help="源文件路径"),
    type: str | None = typer.Option(
        None, "--type", help="资源类型: requirements|specs|design|api|schema"
    ),
    reason: str | None = typer.Option(
        None, "--reason", help="添加原因（触发知识提炼）"
    ),
) -> None:
    """添加资源文件到 Resource Track。"""
    from devcontext.config import settings
    from devcontext.services.resource import ResourceService
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(str(settings.db_path))
    store.init_db()
    service = ResourceService(store, settings.resources_dir)

    try:
        result = service.add(path, resource_type=type, reason=reason)
        typer.echo(f"Resource: {result['resource_id']}")
        typer.echo(f"  Type: {result['type']}")
        typer.echo(f"  Hash: {result['content_hash']}")
        typer.echo(f"  Blocks: {result['blocks']}")
        if result.get("title"):
            typer.echo(f"  Title: {result['title']}")
        if result.get("status") == "unchanged":
            typer.echo(f"  {result.get('message', 'Unchanged')}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
    finally:
        store.close()


@resource_app.command("list")
def resource_list(
    type: str | None = typer.Option(None, "--type", help="按类型过滤"),
) -> None:
    """列出所有资源。"""
    from devcontext.config import settings
    from devcontext.services.resource import ResourceService
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(str(settings.db_path))
    store.init_db()
    service = ResourceService(store, settings.resources_dir)

    try:
        resources = service.list(resource_type=type)
        if not resources:
            typer.echo("No resources found.")
            return
        for r in resources:
            typer.echo(f"  [{r['resource_id']}] {r.get('title', 'N/A')} ({r['type']})")
    finally:
        store.close()


@resource_app.command("show")
def resource_show(
    resource_id: str = typer.Argument(..., help="资源 ID"),
) -> None:
    """查看资源详情。"""
    from devcontext.config import settings
    from devcontext.services.resource import ResourceService
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(str(settings.db_path))
    store.init_db()
    service = ResourceService(store, settings.resources_dir)

    try:
        resource = service.get(resource_id)
        if not resource:
            typer.echo(f"Resource not found: {resource_id}", err=True)
            raise typer.Exit(code=1)
        typer.echo(f"Resource: {resource['resource_id']}")
        typer.echo(f"  Type: {resource['type']}")
        typer.echo(f"  Title: {resource.get('title', 'N/A')}")
        typer.echo(f"  Source: {resource.get('source_path', 'N/A')}")
        typer.echo(f"  Blocks: {resource.get('block_count', 0)}")
        typer.echo(f"  Added: {resource.get('added_at', 'N/A')}")
    finally:
        store.close()


@resource_app.command("search")
def resource_search(
    query: str = typer.Argument(..., help="搜索关键词"),
    type: str | None = typer.Option(None, "--type", help="按类型过滤"),
    top_k: int = typer.Option(5, "--top-k", help="返回条数"),
) -> None:
    """全文搜索资源。"""
    from devcontext.config import settings
    from devcontext.services.resource import ResourceService
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(str(settings.db_path))
    store.init_db()
    service = ResourceService(store, settings.resources_dir)

    try:
        results = service.search(query, resource_type=type, top_k=top_k)
        if not results:
            typer.echo("No results found.")
            return
        for r in results:
            typer.echo(f"  [{r['block_type']}] {r.get('title', 'N/A')}")
            typer.echo(f"    {r['content'][:100]}...")
    finally:
        store.close()


@resource_app.command("remove")
def resource_remove(
    resource_id: str = typer.Argument(..., help="资源 ID"),
) -> None:
    """软删除资源。"""
    from devcontext.config import settings
    from devcontext.services.resource import ResourceService
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(str(settings.db_path))
    store.init_db()
    service = ResourceService(store, settings.resources_dir)

    try:
        if service.remove(resource_id):
            typer.echo(f"Resource {resource_id} soft-deleted.")
        else:
            typer.echo(f"Resource not found: {resource_id}", err=True)
            raise typer.Exit(code=1)
    finally:
        store.close()


@resource_app.command("links")
def resource_links(
    resource_id: str = typer.Argument(..., help="资源 ID"),
) -> None:
    """查看资源→知识链接。"""
    from devcontext.config import settings
    from devcontext.services.resource import ResourceService
    from devcontext.storage.sqlite import SQLiteStore

    store = SQLiteStore(str(settings.db_path))
    store.init_db()
    service = ResourceService(store, settings.resources_dir)

    try:
        links = service.get_links(resource_id)
        if not links:
            typer.echo(f"No links found for {resource_id}.")
            return
        for link in links:
            typer.echo(
                f"  [{link['link_type']}] {link['knowledge_id']} "
                f"(confidence: {link.get('confidence', 1.0):.2f})"
            )
    finally:
        store.close()
