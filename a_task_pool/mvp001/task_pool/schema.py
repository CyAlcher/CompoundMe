"""L1 入口层：AI-Ready 六字段契约 Schema.

对应方案文档 §1.2：所有任务进池前必须满足六字段骨架，
缺任何一个直接拒绝。领域字段按 YAGNI 扩展，仅保留"AI 执行必需"的字段。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Domain(str, Enum):
    SOCIAL_MEDIA = "social-media"
    GITHUB_DEV = "github-dev"
    DATA_OPS = "data-ops"
    RESEARCH = "research"


class HumanMode(str, Enum):
    NONE = "none"
    NOTIFY_AFTER = "notify-after"
    APPROVE_BEFORE = "approve-before"


class InputRef(BaseModel):
    type: str
    path: str


class Contract(BaseModel):
    success_criteria: list[str] = Field(min_length=1)
    failure_modes: list[str] = Field(default_factory=list)
    test_command: str | None = None


class HumanInLoop(BaseModel):
    mode: HumanMode = HumanMode.NONE
    reviewers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _approve_needs_reviewers(self) -> "HumanInLoop":
        if self.mode == HumanMode.APPROVE_BEFORE and not self.reviewers:
            raise ValueError("approve-before 模式必须指定 reviewers")
        return self


class Notify(BaseModel):
    on_success: list[str] = Field(default_factory=list)
    on_failure: list[str] = Field(default_factory=list)

    @field_validator("on_success", "on_failure")
    @classmethod
    def _check_prefix(cls, v: list[str]) -> list[str]:
        allowed = ("email:", "console:", "lark:", "telegram:")
        for item in v:
            if not item.startswith(allowed):
                raise ValueError(
                    f"通知目标必须以 {allowed} 开头，收到: {item!r}"
                )
        return v


# --- 领域字段扩展（最小集） ---

class SocialMediaExec(BaseModel):
    platform: Literal["xiaohongshu", "wechat", "x", "weibo"]
    tone: str | None = None
    tag_list: list[str] = Field(default_factory=list)


class GithubDevExec(BaseModel):
    repo: str
    spec_file: str | None = None


class DataOpsExec(BaseModel):
    source_uri: str
    target_uri: str
    transform_type: str | None = None


class ResearchExec(BaseModel):
    query: str
    sources: list[str] = Field(default_factory=list)
    output_format: Literal["markdown", "json", "csv"] = "markdown"


class Task(BaseModel):
    """AI-Ready 任务骨架（六字段契约）."""

    task_id: str = Field(min_length=1, description="幂等键")
    domain: Domain
    intent: str = Field(min_length=1, description="动词+宾语，枚举值")
    input_refs: list[InputRef] = Field(default_factory=list)
    contract: Contract
    human_in_loop: HumanInLoop = Field(default_factory=HumanInLoop)
    notify: Notify = Field(default_factory=Notify)

    exec: dict[str, Any] = Field(default_factory=dict, description="领域扩展字段")

    @model_validator(mode="after")
    def _validate_domain_exec(self) -> "Task":
        mapping = {
            Domain.SOCIAL_MEDIA: SocialMediaExec,
            Domain.GITHUB_DEV: GithubDevExec,
            Domain.DATA_OPS: DataOpsExec,
            Domain.RESEARCH: ResearchExec,
        }
        schema = mapping.get(self.domain)
        if schema is not None:
            schema.model_validate(self.exec)
        return self
