"""Schema + 路由 + 池最小测试."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from executors.base import get as get_executor  # noqa: E402
from task_pool.loader import TaskLoadError, load_from_dict  # noqa: E402
from task_pool.pool import TaskPool  # noqa: E402
from task_pool.router import route  # noqa: E402
from task_pool.schema import HumanMode  # noqa: E402


def _minimal(**over) -> dict:
    base = {
        "task_id": "t-001",
        "domain": "data-ops",
        "intent": "fetch",
        "contract": {"success_criteria": ["ok"]},
        "exec": {"source_uri": "a", "target_uri": "b"},
    }
    base.update(over)
    return base


# --- schema ---

def test_accept_minimal():
    task = load_from_dict(_minimal())
    assert task.task_id == "t-001"


def test_reject_missing_criteria():
    bad = _minimal()
    bad["contract"] = {}
    with pytest.raises(TaskLoadError) as e:
        load_from_dict(bad)
    assert "success_criteria" in str(e.value)


def test_reject_unknown_domain():
    bad = _minimal(domain="unknown")
    with pytest.raises(TaskLoadError):
        load_from_dict(bad)


def test_approve_before_needs_reviewers():
    bad = _minimal(human_in_loop={"mode": "approve-before", "reviewers": []})
    with pytest.raises(TaskLoadError):
        load_from_dict(bad)


def test_notify_prefix_check():
    bad = _minimal(notify={"on_success": ["slack://x"]})
    with pytest.raises(TaskLoadError):
        load_from_dict(bad)


def test_domain_exec_required():
    # data-ops 必须有 source_uri / target_uri
    bad = _minimal()
    bad["exec"] = {}
    with pytest.raises(TaskLoadError):
        load_from_dict(bad)


# --- router ---

def test_route_default_none():
    task = load_from_dict(_minimal())  # intent=fetch → DEFAULT_MODE none
    r = route(task)
    assert r.channel == "auto"
    assert r.mode == HumanMode.NONE


def test_route_notify_after_intent():
    task = load_from_dict(
        _minimal(
            domain="social-media",
            intent="publish",
            **{"exec": {"platform": "xiaohongshu"}},
        )
    )
    assert route(task).channel == "notify"


def test_route_approve_before_explicit():
    task = load_from_dict(
        _minimal(
            human_in_loop={
                "mode": "approve-before",
                "reviewers": ["alice@example.com"],
            }
        )
    )
    assert route(task).channel == "approve"


# --- pool ---

def test_pool_idempotent_and_claim(tmp_path: Path):
    pool = TaskPool(tmp_path / "x.db")
    task = load_from_dict(_minimal())
    assert pool.submit(task, channel="auto") == "pending"
    with pytest.raises(ValueError):
        pool.submit(task, channel="auto")  # 幂等

    claimed = pool.claim_next(channel="auto")
    assert claimed is not None and claimed.task_id == task.task_id
    assert pool.claim_next(channel="auto") is None  # 没了


def test_pool_approve_flow(tmp_path: Path):
    pool = TaskPool(tmp_path / "x.db")
    task = load_from_dict(
        _minimal(
            task_id="t-approve",
            human_in_loop={
                "mode": "approve-before",
                "reviewers": ["alice@example.com"],
            },
        )
    )
    assert pool.submit(task, channel="approve") == "awaiting_approval"
    # 未 approve 前 claim_next 拿不到
    assert pool.claim_next(channel="approve") is None
    assert pool.approve("t-approve")
    claimed = pool.claim_next(channel="approve")
    assert claimed is not None


def test_pool_finish_records_run(tmp_path: Path):
    import time

    pool = TaskPool(tmp_path / "x.db")
    task = load_from_dict(_minimal())
    pool.submit(task, channel="auto")
    pool.claim_next(channel="auto")
    pool.finish(
        task.task_id,
        status="done",
        executor="echo",
        stdout="hi",
        stderr="",
        started_at=time.time() - 0.1,
    )
    row = pool.get(task.task_id)
    assert row and row["status"] == "done"


# --- executors ---

def test_echo_executor():
    task = load_from_dict(_minimal())
    r = get_executor("echo").run(task)
    assert r.ok and "t-001" in r.stdout


def test_shell_executor_ok():
    task = load_from_dict(_minimal(**{"exec": {
        "source_uri": "a", "target_uri": "b", "command": "echo hi"
    }}))
    r = get_executor("shell").run(task)
    assert r.ok and "hi" in r.stdout


def test_shell_executor_fail():
    task = load_from_dict(_minimal(**{"exec": {
        "source_uri": "a", "target_uri": "b", "command": "false"
    }}))
    r = get_executor("shell").run(task)
    assert not r.ok
