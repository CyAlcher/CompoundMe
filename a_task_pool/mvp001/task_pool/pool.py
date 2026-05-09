"""L2 任务池：SQLite + WAL.

方案 §2：单机 10w 任务/天用 SQLite 足够，不要上来就 Kafka。
关键约束：task_id 唯一（幂等），四态流转，insert-only 事件写入 runs 表。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from .schema import Task

Status = Literal["pending", "awaiting_approval", "running", "done", "failed"]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id        TEXT PRIMARY KEY,
    domain         TEXT NOT NULL,
    intent         TEXT NOT NULL,
    status         TEXT NOT NULL,
    channel        TEXT,
    payload_json   TEXT NOT NULL,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL,
    last_error     TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_channel ON tasks(channel);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT NOT NULL,
    started_at    REAL NOT NULL,
    finished_at   REAL,
    status        TEXT NOT NULL,
    executor      TEXT,
    stdout        TEXT,
    stderr        TEXT,
    duration_s    REAL
);
CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id);
"""


class TaskPool:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # -- 写 --

    def submit(self, task: Task, channel: str) -> Status:
        """入池。approve-before 模式落入 awaiting_approval，其他 pending."""
        initial: Status = (
            "awaiting_approval"
            if task.human_in_loop.mode.value == "approve-before"
            else "pending"
        )
        now = time.time()
        payload = task.model_dump_json()
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """INSERT INTO tasks
                    (task_id, domain, intent, status, channel, payload_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task.task_id,
                        task.domain.value,
                        task.intent,
                        initial,
                        channel,
                        payload,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as e:
                raise ValueError(f"task_id 已存在: {task.task_id}") from e
        return initial

    def approve(self, task_id: str) -> bool:
        """把 awaiting_approval 推进到 pending."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='pending', updated_at=? "
                "WHERE task_id=? AND status='awaiting_approval'",
                (time.time(), task_id),
            )
            return cur.rowcount > 0

    def claim_next(self, channel: str | None = None) -> Task | None:
        """原子地从 pending 里拿一个改成 running."""
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            if channel:
                row = conn.execute(
                    "SELECT task_id, payload_json FROM tasks "
                    "WHERE status='pending' AND channel=? "
                    "ORDER BY created_at LIMIT 1",
                    (channel,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT task_id, payload_json FROM tasks "
                    "WHERE status='pending' ORDER BY created_at LIMIT 1"
                ).fetchone()
            if row is None:
                conn.execute("COMMIT;")
                return None
            conn.execute(
                "UPDATE tasks SET status='running', updated_at=? WHERE task_id=?",
                (time.time(), row["task_id"]),
            )
            conn.execute("COMMIT;")
            return Task.model_validate_json(row["payload_json"])

    def finish(
        self,
        task_id: str,
        *,
        status: Literal["done", "failed"],
        executor: str,
        stdout: str = "",
        stderr: str = "",
        started_at: float,
        error: str | None = None,
    ) -> None:
        finished = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET status=?, last_error=?, updated_at=? WHERE task_id=?",
                (status, error, finished, task_id),
            )
            conn.execute(
                """INSERT INTO runs
                (task_id, started_at, finished_at, status, executor, stdout, stderr, duration_s)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    started_at,
                    finished,
                    status,
                    executor,
                    stdout[-4000:],
                    stderr[-4000:],
                    finished - started_at,
                ),
            )

    # -- 读 --

    def get(self, task_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_tasks(self, status: Status | None = None) -> list[dict]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status=? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]
