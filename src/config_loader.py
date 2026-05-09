#!/usr/bin/env python3
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR.parent / "config" / "app_config.json"

DEFAULT_CONFIG = {
    "paths": {
        "base_dir": "~/.ai-trace",
        "daily_root": "~/.ai-trace/daily",
        "db_path": "~/.ai-trace/data/ai_review.db",
        "state_dir": "~/.ai-trace/state",
        "log_dir": "~/.ai-trace/logs",
    },
    "sources": {
        "codex": "~/.codex/sessions",
        "claude": "~/.claude/projects",
        "cursor": "~/.cursor/projects",
    },
    "filters": {
        "exclude_path_substrings": ["/subagents/", "/terminals/"],
        "cursor_include_path_substring": "/agent-transcripts/",
        "noise_patterns": [
            "Filesystem sandboxing defines which files can be read or written",
            "# Collaboration Mode:",
            "# AGENTS.md instructions",
            "The user interrupted the previous turn on purpose",
            "OS Version:",
            "open_and_recently_viewed_files",
            "system_reminder",
            "agent_skills",
            "rules section has a number of possible rules",
        ],
    },
    "schedule": {
        "runner": {"hour": 19, "minute": 0, "run_at_load": True},
        "monitor": [
            {"hour": 20, "minute": 30},
            {"hour": 21, "minute": 30},
            {"hour": 22, "minute": 30},
        ],
    },
    "mail": {"config_path": str(SCRIPT_DIR.parent / "config" / "mail_config.json")},
    "reports": {
        "daily_folder_pattern": "{yyyymmdd}_ai_review",
        "daily_report_name": "daily_report.md",
        "weekly_report_name": "weekly_report.md",
    },
}


def _deep_merge(base: dict, updates: dict) -> dict:
    merged = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: str | Path | None = None) -> dict:
    path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH
    config = deepcopy(DEFAULT_CONFIG)
    if path.exists():
        user_config = json.loads(path.read_text(encoding="utf-8"))
        config = _deep_merge(config, user_config)
    config["_config_path"] = str(path)
    return config
