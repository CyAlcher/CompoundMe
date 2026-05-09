"""极简 HTTP 后端：复用 loader + pool + router，不引新依赖。

路由：
  GET  /                → index.html
  GET  /api/tasks       → 池内任务列表
  POST /api/submit      → JSON body → Task → 入池
  POST /api/approve     → {task_id} → pool.approve
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from executors.base import ExecResult, get as get_executor
from task_pool.loader import TaskLoadError, load_from_dict
from task_pool.notify import notify
from task_pool.pool import TaskPool
from task_pool.router import route


BASE = Path(__file__).parent
INDEX = BASE / "index.html"
DB = BASE / ".taskpool" / "pool.db"

pool = TaskPool(DB)


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict | list) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length") or 0)
    if not length:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw.decode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print(f"[http] {self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = INDEX.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/tasks":
            rows = pool.list_tasks()
            for r in rows:
                r.pop("payload_json", None)
            _json(self, 200, rows)
            return
        _json(self, 404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/submit":
            try:
                data = _read_body(self)
            except json.JSONDecodeError as e:
                _json(self, 400, {"error": f"bad json: {e}"})
                return
            try:
                task = load_from_dict(data, source="<http>")
            except TaskLoadError as e:
                _json(self, 422, {"error": str(e), "details": e.errors})
                return
            r = route(task)
            try:
                status = pool.submit(task, channel=r.channel)
            except ValueError as e:
                _json(self, 409, {"error": str(e)})
                return
            _json(
                self,
                200,
                {
                    "task_id": task.task_id,
                    "status": status,
                    "channel": r.channel,
                    "executor": r.executor,
                    "mode": r.mode.value,
                },
            )
            return

        if self.path == "/api/approve":
            data = _read_body(self)
            task_id = data.get("task_id")
            if not task_id:
                _json(self, 400, {"error": "task_id required"})
                return
            ok = pool.approve(task_id)
            _json(self, 200 if ok else 404, {"ok": ok})
            return

        if self.path == "/api/run":
            data = _read_body(self)
            task_id = data.get("task_id")
            task = None
            if task_id:
                row = pool.get(task_id)
                if row and row["status"] == "pending":
                    from task_pool.schema import Task
                    import time as _time
                    task = Task.model_validate_json(row["payload_json"])
                    with pool._lock, pool._connect() as conn:  # noqa: SLF001
                        conn.execute(
                            "UPDATE tasks SET status='running', updated_at=? WHERE task_id=?",
                            (_time.time(), task_id),
                        )
            else:
                task = pool.claim_next()

            if task is None:
                _json(self, 200, {"ran": 0})
                return

            rt = route(task)
            executor = get_executor(rt.executor)
            import time
            started = time.time()
            try:
                result: ExecResult = executor.run(task)
            except Exception as e:  # noqa: BLE001
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
            _json(
                self,
                200,
                {
                    "ran": 1,
                    "task_id": task.task_id,
                    "ok": result.ok,
                    "stdout": result.stdout[-2000:],
                    "stderr": result.stderr[-2000:],
                    "error": result.error,
                },
            )
            return

        _json(self, 404, {"error": "not found"})


def main(host: str = "127.0.0.1", port: int = 8765) -> None:
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"task-pool UI: http://{host}:{port}/")
    print(f"db: {DB}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n(bye)")
        srv.shutdown()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    main(port=port)
