"""Kill leftover Fennsill worker processes before desk starts fresh ones."""

from __future__ import annotations

import os
import sys

MARKERS = (
    "http_bridge.py",
    "live_watch.py",
    "live_jobs.py",
    "tunnel.py",
    "rotate_pages.py",
    # cloud_agent.py is owned by the Fennsill Agent Windows service — never kill it here.
)


def main() -> int:
    from pathlib import Path

    here = Path(__file__).resolve().parent
    default_root = here.parents[1] if here.name == "runtime" else here.parent
    root = os.environ.get("FENNSILL_ROOT") or str(default_root)
    root_l = root.lower()
    me = os.getpid()
    killed = 0
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        print(f"kill_orphans: list failed: {exc}", flush=True)
        return 0

    import json

    try:
        data = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        data = []
    if isinstance(data, dict):
        data = [data]

    for row in data:
        try:
            pid = int(row.get("ProcessId") or 0)
        except (TypeError, ValueError):
            continue
        if pid <= 0 or pid == me:
            continue
        cmd = str(row.get("CommandLine") or "")
        if root_l not in cmd.lower() and "this is a test for the tablet" not in cmd.lower():
            continue
        if not any(m in cmd for m in MARKERS):
            continue
        try:
            os.kill(pid, 9)
            killed += 1
            print(f"kill_orphans: killed {pid}", flush=True)
        except OSError as exc:
            print(f"kill_orphans: skip {pid}: {exc}", flush=True)
    print(f"kill_orphans: done killed={killed}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
