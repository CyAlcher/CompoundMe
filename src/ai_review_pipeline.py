#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
import re

from config_loader import DEFAULT_CONFIG_PATH, load_config

# Runtime globals — overwritten by initialize_runtime()
BASE_DIR = Path("~/.ai-trace").expanduser()
DAILY_ROOT = Path("~/.ai-trace/daily").expanduser()
DB_PATH = BASE_DIR / "data" / "ai_review.db"
STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"
DEFAULT_SOURCES: dict[str, Path] = {}
NOISE_PATTERNS: list[str] = []
EXCLUDE_PATH_SUBSTRINGS: list[str] = []
CURSOR_INCLUDE_PATH_SUBSTRING = "/agent-transcripts/"
REPORT_DAILY_FOLDER_PATTERN = "{yyyymmdd}_ai_review"
REPORT_DAILY_NAME = "daily_report.md"
REPORT_WEEKLY_NAME = "weekly_report.md"

CATEGORY_KEYWORDS = {
    "code_reading": ["read", "logic", "param", "why", "reason", "call", "upstream", "downstream", "judge",
                     "阅读", "逻辑", "参数", "取值", "兜底", "为什么", "原因", "调用", "上下游", "判断"],
    "code_modification": ["modify", "refactor", "delete", "fix", "replace", "adapt",
                          "修改", "重构", "删除", "保留", "修复", "适配", "替换"],
    "env_tooling": ["conda", "brew", "ollama", "install", "permission", "error", "token", "cursor", "localhost",
                    "安装", "权限", "报错"],
    "prompt_experiment": ["prompt", "cot", "fewshot", "few-shot", "self-consistency", "experiment", "ablation",
                          "stability", "quantify", "notebook",
                          "提示词", "实验", "消融", "稳定性", "量化"],
    "digital_asset": ["digital asset", "skill", "automation", "personalization",
                      "数字资产", "数字分身", "历史对话", "偏好", "自动化", "个性化"],
    "structured_output": ["markdown", "table", "report", "organize", "output format",
                          "表格", "报告", "整理成", "输出格式"],
    "risk_assessment": ["plan", "assess", "risk", "workload", "impact", "discuss first",
                        "方案", "评估", "风险", "工作量", "影响范围", "先讨论", "先给我评估"],
}

PREFERENCE_RULES = {
    "high_constraint": ["must", "don't", "force", "constraint", "必须", "不要", "强制", "约束"],
    "structured_delivery": ["markdown", "table", "report", "organize", "表格", "报告", "整理"],
    "system_consistency": ["upstream", "downstream", "consistent", "上下游", "联动", "一致"],
    "asset_accumulation": ["skill", "template", "digital asset", "personalize", "模板", "数字资产", "个性化"],
    "quantifiable": ["quantify", "reproduce", "stability", "metric", "量化", "复现", "稳定性", "指标"],
    "assess_before_act": ["assess", "workload", "risk", "impact", "评估", "工作量", "风险", "影响范围"],
}


def initialize_runtime(config: dict) -> None:
    global BASE_DIR, DAILY_ROOT, DB_PATH, STATE_DIR, LOG_DIR
    global DEFAULT_SOURCES, NOISE_PATTERNS, EXCLUDE_PATH_SUBSTRINGS, CURSOR_INCLUDE_PATH_SUBSTRING
    global REPORT_DAILY_FOLDER_PATTERN, REPORT_DAILY_NAME, REPORT_WEEKLY_NAME

    paths = config["paths"]
    BASE_DIR = Path(paths["base_dir"]).expanduser()
    DAILY_ROOT = Path(paths["daily_root"]).expanduser()
    DB_PATH = Path(paths["db_path"]).expanduser()
    STATE_DIR = Path(paths["state_dir"]).expanduser()
    LOG_DIR = Path(paths["log_dir"]).expanduser()
    DEFAULT_SOURCES = {name: Path(path).expanduser() for name, path in config["sources"].items()}

    filters = config.get("filters", {})
    NOISE_PATTERNS = list(filters.get("noise_patterns", []))
    EXCLUDE_PATH_SUBSTRINGS = list(filters.get("exclude_path_substrings", []))
    CURSOR_INCLUDE_PATH_SUBSTRING = filters.get("cursor_include_path_substring", "/agent-transcripts/")

    reports = config.get("reports", {})
    REPORT_DAILY_FOLDER_PATTERN = reports.get("daily_folder_pattern", "{yyyymmdd}_ai_review")
    REPORT_DAILY_NAME = reports.get("daily_report_name", "daily_report.md")
    REPORT_WEEKLY_NAME = reports.get("weekly_report_name", "weekly_report.md")


@dataclass
class PromptRecord:
    tool: str
    source_file: str
    source_mtime: str
    text: str
    assistant: str
    category: str
    prompt_hash: str


def ensure_dirs() -> None:
    for path in [DB_PATH.parent, STATE_DIR, LOG_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def normalize_text(text: str) -> str:
    # Strip XML-like tags injected by AI tools
    text = re.sub(
        r"</?(attached_files|user_query|code_selection|open_and_recently_viewed_files"
        r"|system_reminder|user_info|rules|agent_skills|environment_context)[^>]*>",
        " ",
        text,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\bL\d+:", " ", text)
    # Redact absolute home paths to avoid leaking usernames
    text = re.sub(r"/Users/[^/\s]+", "~", text)
    text = re.sub(r"/home/[^/\s]+", "~", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def short(text: str, limit: int = 120) -> str:
    return normalize_text(text)[:limit]


def should_skip(text: str) -> bool:
    if any(pattern in text for pattern in NOISE_PATTERNS):
        return True
    return len(normalize_text(text)) < 8


def parse_codex(path: Path):
    for line in path.read_text(errors="ignore").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "response_item":
            continue
        payload = obj.get("payload", {})
        if payload.get("type") != "message":
            continue
        role = payload.get("role")
        texts = []
        for item in payload.get("content", []):
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if value:
                    texts.append(value)
        text = "\n".join(texts).strip()
        if text:
            yield role, text


def parse_claude(path: Path):
    for line in path.read_text(errors="ignore").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") not in ("user", "assistant"):
            continue
        content = obj.get("message", {}).get("content", "")
        if isinstance(content, str) and content.strip():
            yield obj["type"], content.strip()


def parse_cursor(path: Path):
    for line in path.read_text(errors="ignore").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        role = obj.get("role")
        if role not in ("user", "assistant"):
            continue
        texts = []
        for item in obj.get("message", {}).get("content", []):
            if isinstance(item, dict) and item.get("text"):
                texts.append(item["text"])
        text = "\n".join(texts).strip()
        if text:
            yield role, text


def infer_category(text: str) -> str:
    low = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in low for keyword in keywords):
            return category
    return "other"


def collect_records(sources: dict[str, Path]) -> tuple[list[PromptRecord], int]:
    raw_session_count = 0
    temp_records: list[PromptRecord] = []

    def collect(tool: str, path: Path, message_iter):
        nonlocal raw_session_count
        raw_session_count += 1
        pending_user: str | None = None
        mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        for role, raw_text in message_iter:
            if should_skip(raw_text):
                continue
            clean = normalize_text(raw_text)
            if role == "user":
                pending_user = clean
            elif role == "assistant" and pending_user:
                prompt_hash = sha256(f"{tool}|{path}|{pending_user}".encode("utf-8")).hexdigest()
                temp_records.append(
                    PromptRecord(
                        tool=tool,
                        source_file=str(path),
                        source_mtime=mtime,
                        text=pending_user,
                        assistant=clean[:240],
                        category=infer_category(pending_user),
                        prompt_hash=prompt_hash,
                    )
                )
                pending_user = None
        if pending_user:
            prompt_hash = sha256(f"{tool}|{path}|{pending_user}".encode("utf-8")).hexdigest()
            temp_records.append(
                PromptRecord(
                    tool=tool,
                    source_file=str(path),
                    source_mtime=mtime,
                    text=pending_user,
                    assistant="",
                    category=infer_category(pending_user),
                    prompt_hash=prompt_hash,
                )
            )

    codex_root = sources.get("codex")
    if codex_root and codex_root.exists():
        for path in sorted(codex_root.rglob("*.jsonl")):
            collect("codex", path, parse_codex(path))

    claude_root = sources.get("claude")
    if claude_root and claude_root.exists():
        for path in sorted(claude_root.rglob("*.jsonl")):
            if not any(part in str(path) for part in EXCLUDE_PATH_SUBSTRINGS):
                collect("claude", path, parse_claude(path))

    cursor_root = sources.get("cursor")
    if cursor_root and cursor_root.exists():
        for path in sorted(cursor_root.rglob("*.jsonl")):
            if CURSOR_INCLUDE_PATH_SUBSTRING in str(path) and not any(
                part in str(path) for part in EXCLUDE_PATH_SUBSTRINGS
            ):
                collect("cursor", path, parse_cursor(path))

    deduped: list[PromptRecord] = []
    seen_text = set()
    for record in temp_records:
        if record.text in seen_text:
            continue
        seen_text.add(record.text)
        deduped.append(record)
    return deduped, raw_session_count


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS prompt_records (
            prompt_hash TEXT PRIMARY KEY,
            tool TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_mtime TEXT NOT NULL,
            text TEXT NOT NULL,
            assistant TEXT NOT NULL,
            category TEXT NOT NULL,
            first_seen_date TEXT NOT NULL,
            last_seen_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pipeline_runs (
            run_id TEXT PRIMARY KEY,
            run_date TEXT NOT NULL,
            run_at TEXT NOT NULL,
            run_type TEXT NOT NULL,
            status TEXT NOT NULL,
            raw_session_count INTEGER NOT NULL,
            unique_prompt_count INTEGER NOT NULL,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS monitor_alerts (
            alert_key TEXT PRIMARY KEY,
            alert_date TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_snapshot (
            snap_date TEXT PRIMARY KEY,
            new_prompts INTEGER NOT NULL,
            cumulative_prompts INTEGER NOT NULL,
            new_by_tool TEXT NOT NULL,
            new_by_category TEXT NOT NULL,
            new_by_preference TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def upsert_records(conn: sqlite3.Connection, records: list[PromptRecord], run_date: str) -> None:
    for record in records:
        conn.execute(
            """
            INSERT INTO prompt_records (
                prompt_hash, tool, source_file, source_mtime, text, assistant, category,
                first_seen_date, last_seen_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(prompt_hash) DO UPDATE SET
                source_mtime = excluded.source_mtime,
                assistant = excluded.assistant,
                category = excluded.category,
                last_seen_date = excluded.last_seen_date
            """,
            (
                record.prompt_hash,
                record.tool,
                record.source_file,
                record.source_mtime,
                record.text,
                record.assistant,
                record.category,
                run_date,
                run_date,
            ),
        )
    conn.commit()


def record_pipeline_run(
    conn: sqlite3.Connection,
    run_date: str,
    run_type: str,
    status: str,
    raw_session_count: int,
    unique_prompt_count: int,
    notes: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO pipeline_runs (run_id, run_date, run_at, run_type, status,
            raw_session_count, unique_prompt_count, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            run_date,
            datetime.now().isoformat(timespec="seconds"),
            run_type,
            status,
            raw_session_count,
            unique_prompt_count,
            notes,
        ),
    )
    conn.commit()


def compute_daily_snapshot(conn: sqlite3.Connection, run_date: str) -> dict:
    """Compute T-day incremental stats and upsert into daily_snapshot."""
    # New prompts first seen today
    new_rows = conn.execute(
        "SELECT tool, category, text FROM prompt_records WHERE first_seen_date = ?",
        (run_date,),
    ).fetchall()

    cumulative = conn.execute(
        "SELECT COUNT(*) FROM prompt_records WHERE first_seen_date <= ?",
        (run_date,),
    ).fetchone()[0]

    new_by_tool: Counter = Counter()
    new_by_category: Counter = Counter()
    new_by_preference: Counter = Counter()

    for tool, category, text in new_rows:
        new_by_tool[tool] += 1
        new_by_category[category] += 1
        for pref, keywords in PREFERENCE_RULES.items():
            if any(k in text for k in keywords):
                new_by_preference[pref] += 1

    conn.execute(
        """
        INSERT INTO daily_snapshot
            (snap_date, new_prompts, cumulative_prompts,
             new_by_tool, new_by_category, new_by_preference, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(snap_date) DO UPDATE SET
            new_prompts = excluded.new_prompts,
            cumulative_prompts = excluded.cumulative_prompts,
            new_by_tool = excluded.new_by_tool,
            new_by_category = excluded.new_by_category,
            new_by_preference = excluded.new_by_preference,
            created_at = excluded.created_at
        """,
        (
            run_date,
            len(new_rows),
            cumulative,
            json.dumps(dict(new_by_tool)),
            json.dumps(dict(new_by_category)),
            json.dumps(dict(new_by_preference)),
            datetime.now().isoformat(timespec="seconds"),
        ),
    )
    conn.commit()

    return {
        "new_prompts": len(new_rows),
        "cumulative_prompts": cumulative,
        "new_by_tool": new_by_tool,
        "new_by_category": new_by_category,
        "new_by_preference": new_by_preference,
    }


def load_snapshot(conn: sqlite3.Connection, snap_date: str) -> dict | None:
    """Load a previously stored daily_snapshot row as parsed dicts."""
    row = conn.execute(
        "SELECT new_prompts, cumulative_prompts, new_by_tool, new_by_category, new_by_preference "
        "FROM daily_snapshot WHERE snap_date = ?",
        (snap_date,),
    ).fetchone()
    if not row:
        return None
    return {
        "new_prompts": row[0],
        "cumulative_prompts": row[1],
        "new_by_tool": Counter(json.loads(row[2])),
        "new_by_category": Counter(json.loads(row[3])),
        "new_by_preference": Counter(json.loads(row[4])),
    }


def _delta(today: int, yesterday: int) -> str:
    """Format a day-over-day delta as a signed string."""
    diff = today - yesterday
    if diff > 0:
        return f"+{diff}"
    if diff < 0:
        return str(diff)
    return "—"


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def tool_counts(records: list[PromptRecord]) -> Counter:
    return Counter(record.tool for record in records)


def category_counts(records: list[PromptRecord]) -> Counter:
    return Counter(record.category for record in records)


def preference_counts(records: list[PromptRecord]) -> Counter:
    counts: Counter = Counter()
    for record in records:
        for name, keywords in PREFERENCE_RULES.items():
            if any(keyword in record.text for keyword in keywords):
                counts[name] += 1
    return counts


def top_examples(records: list[PromptRecord], limit_per_category: int = 3) -> dict[str, list[str]]:
    examples: dict[str, list[str]] = defaultdict(list)
    for record in records:
        bucket = examples[record.category]
        if len(bucket) < limit_per_category:
            bucket.append(short(record.text))
    return examples


ALL_CATEGORIES = [
    "code_reading", "code_modification", "env_tooling", "prompt_experiment",
    "structured_output", "risk_assessment", "digital_asset", "other",
]
ALL_PREFERENCES = [
    "high_constraint", "structured_delivery", "system_consistency",
    "asset_accumulation", "quantifiable", "assess_before_act",
]


def _render_examples(examples: dict[str, list[str]]) -> str:
    lines = []
    for cat, items in examples.items():
        if items:
            lines.append(f"### {cat}")
            lines.extend(f"- {item}" for item in items)
    return "\n".join(lines)


def generate_daily_report(
    run_day: date,
    today_snap: dict,
    yesterday_snap: dict | None,
    new_records: list[PromptRecord],
    output_dir: Path,
) -> Path:
    folder = output_dir / REPORT_DAILY_FOLDER_PATTERN.format(yyyymmdd=run_day.strftime("%Y%m%d"))
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / REPORT_DAILY_NAME

    yesterday_str = (run_day - timedelta(days=1)).isoformat()
    y = yesterday_snap or {}

    # Tool table: today new | DoD delta
    tool_rows = []
    for name in ["codex", "cursor", "claude"]:
        t = today_snap["new_by_tool"].get(name, 0)
        d = _delta(t, y.get("new_by_tool", Counter()).get(name, 0))
        tool_rows.append([name.capitalize(), str(t), d])

    # Category table: today new | DoD delta
    cat_rows = []
    for name in ALL_CATEGORIES:
        t = today_snap["new_by_category"].get(name, 0)
        d = _delta(t, y.get("new_by_category", Counter()).get(name, 0))
        cat_rows.append([name, str(t), d])

    # Preference table: today new | DoD delta
    pref_rows = []
    for name in ALL_PREFERENCES:
        t = today_snap["new_by_preference"].get(name, 0)
        d = _delta(t, y.get("new_by_preference", Counter()).get(name, 0))
        pref_rows.append([name, str(t), d])

    # DoD summary line
    new_today = today_snap["new_prompts"]
    new_yesterday = y.get("new_prompts", 0)
    dod_total = _delta(new_today, new_yesterday)
    cumulative = today_snap["cumulative_prompts"]

    examples = top_examples(new_records)

    content = f"""# MirrorCop Daily Report — {run_day.strftime('%Y-%m-%d')}

## Summary
| Metric | Value |
| --- | --- |
| Generated at | `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}` |
| New prompts today | `{new_today}` ({dod_total} vs {yesterday_str}) |
| Cumulative prompts | `{cumulative}` |

## New Prompts by Tool (T-day)
{render_table(["Tool", "New Today", "DoD"], tool_rows)}

## New Prompts by Category (T-day)
{render_table(["Category", "New Today", "DoD"], cat_rows)}

## Preference Signals (T-day)
{render_table(["Preference", "New Today", "DoD"], pref_rows)}

## Sample New Prompts by Category
{_render_examples(examples)}
"""
    report_path.write_text(content + "\n", encoding="utf-8")
    return report_path


def generate_weekly_report(run_day: date, conn: sqlite3.Connection, output_dir: Path) -> Path:
    folder = output_dir / REPORT_DAILY_FOLDER_PATTERN.format(yyyymmdd=run_day.strftime("%Y%m%d"))
    folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / REPORT_WEEKLY_NAME
    start_day = run_day - timedelta(days=6)

    runs = conn.execute(
        """
        SELECT run_date, status, raw_session_count, unique_prompt_count
        FROM pipeline_runs
        WHERE run_type = 'daily' AND run_date BETWEEN ? AND ?
        ORDER BY run_date
        """,
        (start_day.isoformat(), run_day.isoformat()),
    ).fetchall()

    rows = [[row[0], row[1], str(row[2]), str(row[3])] for row in runs]
    content = f"""# AI Weekly Report — {start_day.strftime('%Y-%m-%d')} to {run_day.strftime('%Y-%m-%d')}

## Pipeline Runs This Week
{render_table(["Date", "Status", "Raw Sessions", "Unique Prompts"], rows or [["—", "—", "0", "0"]])}
"""
    report_path.write_text(content + "\n", encoding="utf-8")
    return report_path


def write_last_run_state(run_day: date, success: bool, notes: str = "") -> None:
    payload = {
        "run_date": run_day.isoformat(),
        "success": success,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "notes": notes,
    }
    (STATE_DIR / "last_run.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AI session review pipeline")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to app_config.json")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--daily-root", default=None)
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--date", default=date.today().isoformat(), help="Run date YYYY-MM-DD")
    parser.add_argument("--force-weekly", action="store_true", help="Generate weekly report regardless of weekday")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.output_dir:
        config["paths"]["base_dir"] = args.output_dir
    if args.daily_root:
        config["paths"]["daily_root"] = args.daily_root
    if args.db_path:
        config["paths"]["db_path"] = args.db_path

    initialize_runtime(config)
    ensure_dirs()
    run_day = date.fromisoformat(args.date)

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    try:
        records, raw_session_count = collect_records(DEFAULT_SOURCES)
        upsert_records(conn, records, run_day.isoformat())

        # T-day snapshot
        today_snap = compute_daily_snapshot(conn, run_day.isoformat())
        yesterday_snap = load_snapshot(conn, (run_day - timedelta(days=1)).isoformat())

        # Only pass records first seen today to the report examples
        new_hashes = set(
            row[0] for row in conn.execute(
                "SELECT prompt_hash FROM prompt_records WHERE first_seen_date = ?",
                (run_day.isoformat(),),
            ).fetchall()
        )
        new_records = [r for r in records if r.prompt_hash in new_hashes]

        daily_report = generate_daily_report(run_day, today_snap, yesterday_snap, new_records, DAILY_ROOT)
        weekly_report = None
        if run_day.weekday() == 5 or args.force_weekly:
            weekly_report = generate_weekly_report(run_day, conn, DAILY_ROOT)
        record_pipeline_run(conn, run_day.isoformat(), "daily", "success", raw_session_count, len(records))
        write_last_run_state(run_day, True, "pipeline success")

        print("Pipeline complete")
        print(f"DB: {DB_PATH}")
        print(f"Daily report: {daily_report}")
        if weekly_report:
            print(f"Weekly report: {weekly_report}")
        print(f"Raw sessions: {raw_session_count}")
        print(f"Total unique prompts: {len(records)}")
        print(f"New today: {today_snap['new_prompts']}")
    except Exception as exc:
        record_pipeline_run(conn, run_day.isoformat(), "daily", "failed", 0, 0, notes=str(exc))
        write_last_run_state(run_day, False, str(exc))
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
