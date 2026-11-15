"""Everything Fennsill runs when the panel shows up.

Wires Cursor local MCP (if present), clears stale Claude/ChatGPT stdio, and
registers Windows startup. Claude/ChatGPT use FennsillHost.exe (remote MCP URL).
"""

from __future__ import annotations

import os

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
LINKED = ROOT / "connector" / "linked.json"
DONE = ROOT / "connector" / "panel_setup_done.json"


def ensure_local_link():
    LINKED.parent.mkdir(parents=True, exist_ok=True)
    if not LINKED.is_file():
        LINKED.write_text(
            json.dumps({"email": "local", "provider": "local"}, indent=2) + "\n",
            encoding="utf-8",
        )


def main():
    ensure_local_link()
    from install_clients import main as install_clients

    install_clients()
    try:
        from register_autostart import main as register_autostart

        register_autostart()
    except Exception as exc:
        print(f"autostart skipped: {exc}")
    DONE.write_text(
        json.dumps(
            {
                "ok": True,
                "message": "Panel setup complete. For Claude/ChatGPT open FennsillHost.exe, copy the public MCP URL into Connectors, then talk.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("ready")


if __name__ == "__main__":
    main()
