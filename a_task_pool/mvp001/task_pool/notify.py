"""L6 通知：字符串前缀路由 + 可插拔后端.

方案 §6：Resend 不硬依赖，SMTP 环境变量未配置时降级到 console。
前缀契约：email: / console: / lark: / telegram:（后两个留 stub）。
"""
from __future__ import annotations

import os
import smtplib
import sys
from email.mime.text import MIMEText

from task_pool.schema import Task
from executors.base import ExecResult


def _fmt(task: Task, result: ExecResult, status: str) -> tuple[str, str]:
    subject = f"[{status.upper()}] {task.task_id}"
    body = (
        f"task_id : {task.task_id}\n"
        f"domain  : {task.domain.value} / {task.intent}\n"
        f"status  : {status}\n"
        f"criteria: {task.contract.success_criteria}\n"
        f"---- stdout ----\n{result.stdout[-1500:]}\n"
        f"---- stderr ----\n{result.stderr[-1500:]}\n"
        f"---- error  ----\n{result.error or ''}\n"
    )
    return subject, body


def _send_console(target: str, subject: str, body: str) -> None:
    print(f"\n=== NOTIFY[{target}] {subject} ===\n{body}", file=sys.stderr)


def _send_email(addr: str, subject: str, body: str) -> None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        _send_console(f"email:{addr}", subject, body)
        print("  (SMTP_HOST 未配置，降级到 console)", file=sys.stderr)
        return
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", user or "agent@localhost")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = addr

    with smtplib.SMTP(host, port, timeout=10) as s:
        s.starttls()
        if user:
            s.login(user, password)
        s.sendmail(sender, [addr], msg.as_string())


def notify(task: Task, result: ExecResult) -> None:
    status = "success" if result.ok else "failure"
    targets = (
        task.notify.on_success if result.ok else task.notify.on_failure
    )
    if not targets:
        return
    subject, body = _fmt(task, result, status)
    for t in targets:
        scheme, _, rest = t.partition(":")
        if scheme == "email":
            _send_email(rest, subject, body)
        elif scheme == "console":
            _send_console(t, subject, body)
        else:
            # lark / telegram 留 stub
            _send_console(t, subject, body)
            print(f"  ({scheme} adapter 未实现，降级到 console)", file=sys.stderr)
