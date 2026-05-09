"""L3 路由层：纯函数，无副作用.

方案 §4.2 的 DEFAULT_MODE 在这里实现。规则：
1. 用户在 YAML 显式写了 human_in_loop.mode → 尊重用户。
2. 没写 → 按 intent 查默认表。
3. 都没有 → 默认 none（Auto 通道）。
"""
from __future__ import annotations

from dataclasses import dataclass

from .schema import Domain, HumanMode, Task


# intent 约定：{domain}.{verb-noun}（扁平化，避免嵌套）
DEFAULT_MODE: dict[str, HumanMode] = {
    # Auto：低风险、可撤回、重跑成本低
    "social-media.draft": HumanMode.NONE,
    "github-dev.create-branch": HumanMode.NONE,
    "data-ops.fetch": HumanMode.NONE,
    "research.summarize": HumanMode.NONE,
    # Notify-After：自动执行 + 事后抽查
    "social-media.publish": HumanMode.NOTIFY_AFTER,
    "github-dev.open-pr": HumanMode.NOTIFY_AFTER,
    "github-dev.add-feature": HumanMode.NOTIFY_AFTER,
    "data-ops.transform": HumanMode.NOTIFY_AFTER,
    # Approve-Before：不可逆、对外、高风险
    "github-dev.merge-main": HumanMode.APPROVE_BEFORE,
    "social-media.reply-comment": HumanMode.APPROVE_BEFORE,
    "data-ops.delete": HumanMode.APPROVE_BEFORE,
}


# 执行器选择：domain → executor 名。
# MVP 只接 echo/shell，真实 Claude Code / n8n / OpenClaw 留 adapter 点。
DEFAULT_EXECUTOR: dict[Domain, str] = {
    Domain.GITHUB_DEV: "shell",       # 后续替换为 claude_code
    Domain.SOCIAL_MEDIA: "echo",      # 后续替换为 n8n_webhook
    Domain.DATA_OPS: "shell",
    Domain.RESEARCH: "echo",
}


CHANNEL_OF: dict[HumanMode, str] = {
    HumanMode.NONE: "auto",
    HumanMode.NOTIFY_AFTER: "notify",
    HumanMode.APPROVE_BEFORE: "approve",
}


@dataclass(frozen=True)
class Route:
    channel: str      # auto / notify / approve
    executor: str     # echo / shell / ...
    mode: HumanMode


def route(task: Task) -> Route:
    """根据 task 决定通道 + 执行器。

    用户在 yaml 显式写了 mode（非默认 none）就尊重；否则查 intent 默认表。
    """
    intent_key = f"{task.domain.value}.{task.intent}"

    # 显式非默认值优先
    if task.human_in_loop.mode != HumanMode.NONE:
        mode = task.human_in_loop.mode
    else:
        mode = DEFAULT_MODE.get(intent_key, HumanMode.NONE)

    executor = DEFAULT_EXECUTOR.get(task.domain, "echo")
    return Route(channel=CHANNEL_OF[mode], executor=executor, mode=mode)
