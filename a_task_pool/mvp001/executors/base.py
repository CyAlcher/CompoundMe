"""L4 执行层：adapter 约定.

每个 executor 约 50 行，包住对应工具的 SDK/CLI。
MVP 只实现 echo + shell。真实 claude_code / n8n / openclaw 留 stub，
未来只要换一个 run() 实现即可，不影响上层。
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol

from task_pool.schema import Task


@dataclass
class ExecResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class Executor(Protocol):
    name: str

    def run(self, task: Task) -> ExecResult: ...


class EchoExecutor:
    """最简实现：把 task 打印一遍，用来验证链路通不通."""

    name = "echo"

    def run(self, task: Task) -> ExecResult:
        out = (
            f"[echo] task_id={task.task_id} domain={task.domain.value} "
            f"intent={task.intent}\n"
            f"  criteria: {task.contract.success_criteria}\n"
            f"  exec: {task.exec}\n"
        )
        return ExecResult(ok=True, stdout=out)


class ShellExecutor:
    """跑一条 shell 命令，优先取 exec.command，其次 contract.test_command.

    覆盖 data-ops.fetch / github-dev 的 test_command 验证场景。
    超时 120s，stdout/stderr 截断 4k。
    """

    name = "shell"

    def run(self, task: Task) -> ExecResult:
        cmd = task.exec.get("command") or task.contract.test_command
        if not cmd:
            return ExecResult(
                ok=False,
                error="shell executor 需要 exec.command 或 contract.test_command",
            )
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as e:
            return ExecResult(ok=False, error=f"timeout after 120s: {e}")
        return ExecResult(
            ok=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            error=None if proc.returncode == 0 else f"exit={proc.returncode}",
        )


# --- 真实后端 stub（未来接入） ---

class ClaudeCodeExecutor:
    """TODO: 调用 `claude --print --spec ... ` headless 模式.

    现阶段退化成 ShellExecutor，保留 name 方便路由。
    """

    name = "claude_code"

    def run(self, task: Task) -> ExecResult:
        return ExecResult(
            ok=False,
            error="claude_code executor 未接入，请先用 shell + test_command 替代",
        )


class N8nWebhookExecutor:
    """TODO: POST 到 n8n webhook URL，payload = task.model_dump()."""

    name = "n8n_webhook"

    def run(self, task: Task) -> ExecResult:
        return ExecResult(ok=False, error="n8n_webhook executor 未接入")


REGISTRY: dict[str, Executor] = {
    "echo": EchoExecutor(),
    "shell": ShellExecutor(),
    "claude_code": ClaudeCodeExecutor(),
    "n8n_webhook": N8nWebhookExecutor(),
}


def get(name: str) -> Executor:
    if name not in REGISTRY:
        raise KeyError(f"未知 executor: {name}，已注册: {list(REGISTRY)}")
    return REGISTRY[name]
