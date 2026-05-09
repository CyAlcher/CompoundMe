"""YAML/JSON 载体 → 内部 Schema.

方案 §1.4：三种载体收敛到同一个内部 Schema。这里先实现 YAML + JSON，
Excel 走 pandas → JSON 单独一个脚本，保持入口层职责单一。
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema import Task


class TaskLoadError(Exception):
    """包装 Pydantic 错误，返回可定位的行号/字段提示."""

    def __init__(self, source: str, errors: list[dict]) -> None:
        self.source = source
        self.errors = errors
        lines = [f"Task 校验失败 ({source}):"]
        for e in errors:
            loc = ".".join(str(x) for x in e.get("loc", []))
            lines.append(f"  - {loc}: {e.get('msg')}")
        super().__init__("\n".join(lines))


def load_from_dict(data: dict, source: str = "<dict>") -> Task:
    try:
        return Task.model_validate(data)
    except ValidationError as e:
        raise TaskLoadError(source, e.errors()) from e


def load_from_yaml(path: str | Path) -> Task:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise TaskLoadError(str(p), [{"loc": [], "msg": "YAML 根节点必须是对象"}])
    return load_from_dict(data, source=str(p))


def load_from_json(path: str | Path) -> Task:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return load_from_dict(data, source=str(p))
