"""Quick panel presence check for Artiphact.exe (plug-and-play status).

Uses USB VID listing only — never opens COM — so ChatGPT/MCP can push while
the desk app stays open and polls status.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "connector"))

from panel_ports import list_candidate_ports  # noqa: E402


def main():
    candidates = list_candidate_ports()
    ports = [p["port"] for p in candidates]
    # Desk polls often — skip logging to keep MCP push logs readable.
    print(
        json.dumps(
            {
                "count": len(candidates),
                "ports": ports,
                "ready": len(candidates) == 1,
                "busy": False,
            }
        )
    )


if __name__ == "__main__":
    main()
