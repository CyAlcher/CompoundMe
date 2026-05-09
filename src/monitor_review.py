#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import smtplib
import sqlite3
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path

from config_loader import DEFAULT_CONFIG_PATH, load_config

# Runtime globals — overwritten by initialize_runtime()
DB_PATH = Path("~/.ai-trace/data/ai_review.db").expanduser()
LOG_DIR = Path("~/.ai-trace/logs").expanduser()
MAIL_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "mail_config.json"


def initialize_runtime(config: dict) -> None:
    global DB_PATH, LOG_DIR, MAIL_CONFIG_PATH
    paths = config["paths"]
    DB_PATH = Path(paths["db_path"]).expanduser()
    LOG_DIR = Path(paths["log_dir"]).expanduser()
    MAIL_CONFIG_PATH = Path(
        config.get("mail", {}).get("config_path", str(MAIL_CONFIG_PATH))
    ).expanduser()


def log_line(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
    with (LOG_DIR / "monitor.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def load_mail_config(path: Path) -> dict:
    if not path.exists():
        return {"enabled": False}
    return json.loads(path.read_text(encoding="utf-8"))


def already_alerted(conn: sqlite3.Connection, alert_key: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM monitor_alerts WHERE alert_key = ?", (alert_key,)
    ).fetchone()
    return row is not None


def save_alert(
    conn: sqlite3.Connection, alert_key: str, alert_date: str, status: str, message: str
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO monitor_alerts (alert_key, alert_date, status, message, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (alert_key, alert_date, status, message, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def send_mail(config: dict, subject: str, body: str) -> str:
    if not config.get("enabled"):
        return "Mail disabled, skipped."
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config["from_email"]
    msg["To"] = config["to_email"]
    msg.set_content(body)
    with smtplib.SMTP_SSL(config["smtp_host"], int(config["smtp_port"])) as server:
        server.login(config["smtp_user"], config["smtp_password"])
        server.send_message(msg)
    return "Mail sent."


def main() -> None:
    parser = argparse.ArgumentParser(description="Check if the daily pipeline ran and alert if missing.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--mail-config", default=None)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--force-alert", action="store_true", help="Force alert even if run succeeded (for testing).")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.db_path:
        config["paths"]["db_path"] = args.db_path
    if args.mail_config:
        config.setdefault("mail", {})["config_path"] = args.mail_config
    initialize_runtime(config)

    target_date = args.date
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """
            SELECT run_at, status, unique_prompt_count
            FROM pipeline_runs
            WHERE run_date = ? AND run_type = 'daily'
            ORDER BY run_at DESC
            LIMIT 1
            """,
            (target_date,),
        ).fetchone()

        if row and row[1] == "success" and not args.force_alert:
            message = f"{target_date}: pipeline succeeded at {row[0]}, unique_prompts={row[2]}"
            log_line(message)
            print(message)
            return

        alert_key = f"{target_date}:daily_missing"
        body = (
            f"AI review pipeline did not succeed on {target_date}.\n"
            f"Check logs, launchd config, SQLite DB, and script environment.\n"
            f"DB path: {DB_PATH}\n"
        )

        if already_alerted(conn, alert_key) and not args.force_alert:
            message = f"{target_date}: alert already recorded, skipping duplicate."
            log_line(message)
            print(message)
            return

        mail_config = load_mail_config(MAIL_CONFIG_PATH)
        mail_result = send_mail(mail_config, f"AI review missing — {target_date}", body)
        save_alert(conn, alert_key, target_date, "sent" if mail_config.get("enabled") else "logged", body)
        final_message = f"{target_date}: alert triggered. {mail_result}"
        log_line(final_message)
        print(final_message)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
