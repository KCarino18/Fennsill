"""Quick panel presence check for Fennsill.exe (plug-and-play status).

Uses USB VID listing only — never opens COM — so ChatGPT/MCP can push while
the desk app stays open and polls status. Identity fields come from the local
bind file (written by bind_device.py), not from a live COM probe.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "connector"))

from panel_ports import list_candidate_ports  # noqa: E402

LOCAL = Path(os.environ.get("LOCALAPPDATA", str(ROOT)))
BIND_CANDIDATES = (
    LOCAL / "Fennsill" / "device_bind.json",
    Path(os.environ.get("FENNSILL_ROOT", ROOT)) / "device_bind.json",
    LOCAL / "Artiphact" / "device_bind.json",
)


def _load_bind() -> dict:
    for path in BIND_CANDIDATES:
        try:
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and (data.get("device_id") or data.get("serial")):
                return data
        except Exception:
            continue
    return {}


def main():
    candidates = list_candidate_ports()
    ports = [p["port"] for p in candidates]
    bind = _load_bind()
    print(
        json.dumps(
            {
                "count": len(candidates),
                "ports": ports,
                "ready": len(candidates) == 1,
                "busy": False,
                "device_id": (bind.get("device_id") or "").strip().upper(),
                "serial": (bind.get("serial") or "").strip(),
                "install_key": (bind.get("install_key") or "").strip(),
            }
        )
    )


if __name__ == "__main__":
    main()
