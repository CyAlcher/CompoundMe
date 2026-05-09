#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from config_loader import DEFAULT_CONFIG_PATH, load_config

RUNNER_LABEL = "ai-trace-runner"
MONITOR_LABEL = "ai-trace-monitor"


def plist_header() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
"""


def plist_footer() -> str:
    return """</dict>
</plist>
"""


def render_runner_plist(script_path: Path, log_dir: Path, schedule: dict) -> str:
    return (
        plist_header()
        + f"""    <key>Label</key>
    <string>{RUNNER_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>{script_path}</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{schedule["hour"]}</integer>
        <key>Minute</key>
        <integer>{schedule["minute"]}</integer>
    </dict>

    <key>RunAtLoad</key>
    <{"true" if schedule.get("run_at_load", True) else "false"}/>

    <key>StandardOutPath</key>
    <string>{log_dir / "launchd_runner.out.log"}</string>

    <key>StandardErrorPath</key>
    <string>{log_dir / "launchd_runner.err.log"}</string>
"""
        + plist_footer()
    )


def render_monitor_plist(script_path: Path, log_dir: Path, schedules: list[dict]) -> str:
    intervals = "\n".join(
        [
            f"""        <dict>
            <key>Hour</key>
            <integer>{item["hour"]}</integer>
            <key>Minute</key>
            <integer>{item["minute"]}</integer>
        </dict>"""
            for item in schedules
        ]
    )
    return (
        plist_header()
        + f"""    <key>Label</key>
    <string>{MONITOR_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>{script_path}</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
{intervals}
    </array>

    <key>StandardOutPath</key>
    <string>{log_dir / "launchd_monitor.out.log"}</string>

    <key>StandardErrorPath</key>
    <string>{log_dir / "launchd_monitor.err.log"}</string>
"""
        + plist_footer()
    )


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def maybe_bootout(uid: str, plist_path: Path) -> None:
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", str(plist_path)], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and install launchd jobs from app_config.json.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--load", action="store_true", help="Bootstrap launchd after generating plists.")
    args = parser.parse_args()

    config = load_config(args.config)
    script_dir = Path(__file__).resolve().parent
    log_dir = Path(config["paths"]["log_dir"]).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)

    runner_plist = render_runner_plist(script_dir / "run_review.sh", log_dir, config["schedule"]["runner"])
    monitor_plist = render_monitor_plist(script_dir / "monitor_review.sh", log_dir, config["schedule"]["monitor"])

    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)
    runner_path = launch_agents / f"{RUNNER_LABEL}.plist"
    monitor_path = launch_agents / f"{MONITOR_LABEL}.plist"
    runner_path.write_text(runner_plist, encoding="utf-8")
    monitor_path.write_text(monitor_plist, encoding="utf-8")

    if args.load:
        uid = subprocess.check_output(["id", "-u"], text=True).strip()
        maybe_bootout(uid, runner_path)
        maybe_bootout(uid, monitor_path)
        run(["launchctl", "bootstrap", f"gui/{uid}", str(runner_path)])
        run(["launchctl", "bootstrap", f"gui/{uid}", str(monitor_path)])

    print(f"runner plist: {runner_path}")
    print(f"monitor plist: {monitor_path}")
    if args.load:
        print("launchd loaded")


if __name__ == "__main__":
    main()
