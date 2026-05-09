"""Runner + CLI.

方案 §4.1 三通道：Auto / Notify-After / Approve-Before。
MVP 简化：先不开三条独立 worker 进程池，改成一次 run 循环里
按通道优先级串行消费 —— 单机场景够用，上千并发再拆。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import click

from executors.base import ExecResult, get as get_executor
from task_pool.loader import TaskLoadError, load_from_yaml
from task_pool.notify import notify
from task_pool.pool import TaskPool
from task_pool.router import route


DEFAULT_DB = Path.cwd() / ".taskpool" / "pool.db"


def _pool(db: str | None) -> TaskPool:
    return TaskPool(db or DEFAULT_DB)


@click.group()
@click.option("--db", default=None, help=f"SQLite 路径，默认 {DEFAULT_DB}")
@click.pass_context
def cli(ctx: click.Context, db: str | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["db"] = db


@cli.command()
@click.argument("yaml_path", type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def submit(ctx: click.Context, yaml_path: str) -> None:
    """校验 YAML → 入池."""
    try:
        task = load_from_yaml(yaml_path)
    except TaskLoadError as e:
        click.echo(str(e), err=True)
        sys.exit(2)

    r = route(task)
    pool = _pool(ctx.obj["db"])
    try:
        status = pool.submit(task, channel=r.channel)
    except ValueError as e:
        click.echo(f"入池失败: {e}", err=True)
        sys.exit(3)

    click.echo(
        f"submitted: {task.task_id}  channel={r.channel}  "
        f"executor={r.executor}  mode={r.mode.value}  status={status}"
    )


@cli.command(name="list")
@click.option("--status", default=None, help="过滤状态")
@click.pass_context
def list_cmd(ctx: click.Context, status: str | None) -> None:
    """列出池中任务."""
    pool = _pool(ctx.obj["db"])
    rows = pool.list_tasks(status=status)  # type: ignore[arg-type]
    if not rows:
        click.echo("(空)")
        return
    for r in rows:
        click.echo(
            f"{r['task_id']:<40} {r['status']:<18} {r['channel']:<8} "
            f"{r['domain']}.{r['intent']}"
        )


@cli.command()
@click.argument("task_id")
@click.pass_context
def approve(ctx: click.Context, task_id: str) -> None:
    """把 awaiting_approval 推进到 pending."""
    pool = _pool(ctx.obj["db"])
    ok = pool.approve(task_id)
    if ok:
        click.echo(f"approved: {task_id}")
    else:
        click.echo(f"not found or not in awaiting_approval: {task_id}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("task_id")
@click.pass_context
def show(ctx: click.Context, task_id: str) -> None:
    pool = _pool(ctx.obj["db"])
    row = pool.get(task_id)
    if row is None:
        click.echo(f"not found: {task_id}", err=True)
        sys.exit(1)
    # payload_json 单独漂亮输出
    payload = row.pop("payload_json")
    click.echo(json.dumps(row, indent=2, ensure_ascii=False, default=str))
    click.echo("--- payload ---")
    click.echo(json.dumps(json.loads(payload), indent=2, ensure_ascii=False))


@cli.command()
@click.option(
    "--channel",
    default=None,
    type=click.Choice(["auto", "notify", "approve"]),
    help="只消费某个通道。默认按 auto → notify 优先级串行。",
)
@click.option(
    "--max-tasks",
    default=0,
    type=int,
    help="最多消费多少个任务后退出，0 表示跑到池空。",
)
@click.pass_context
def run(ctx: click.Context, channel: str | None, max_tasks: int) -> None:
    """消费任务池。approve 通道需要先 approve，不会被这里自动拉起。"""
    pool = _pool(ctx.obj["db"])
    order = [channel] if channel else ["auto", "notify"]
    consumed = 0
    while True:
        task = None
        for ch in order:
            task = pool.claim_next(channel=ch)
            if task:
                break
        if task is None:
            click.echo("(池空，退出)")
            return

        r = route(task)
        executor = get_executor(r.executor)
        click.echo(
            f"▶ {task.task_id}  via {executor.name}  channel={r.channel}"
        )
        started = time.time()
        try:
            result: ExecResult = executor.run(task)
        except Exception as e:  # noqa: BLE001 - executor 边界
            result = ExecResult(ok=False, error=f"executor 异常: {e}")

        pool.finish(
            task.task_id,
            status="done" if result.ok else "failed",
            executor=executor.name,
            stdout=result.stdout,
            stderr=result.stderr,
            started_at=started,
            error=result.error,
        )
        notify(task, result)
        click.echo(
            f"  → {'done' if result.ok else 'failed'} "
            f"({time.time() - started:.2f}s)"
        )

        consumed += 1
        if max_tasks and consumed >= max_tasks:
            click.echo(f"(达到 --max-tasks={max_tasks}，退出)")
            return


if __name__ == "__main__":
    cli(obj={})
