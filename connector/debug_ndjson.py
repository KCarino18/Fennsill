"""Session debug logger (debug mode).

Writes:
  - NDJSON for the agent: .cursor/debug-7b0912.log
  - Human-readable lines: connector/artiphact-debug.log
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_NDJSON = Path(r"c:\Users\Kyle\Desktop\This Is A Test For The Tablet\.cursor\debug-7b0912.log")
_HUMAN = _ROOT / "connector" / "artiphact-debug.log"


def dlog(hypothesis_id: str, location: str, message: str, data: dict | None = None, run_id: str = "pre-fix"):
    # #region agent log
    try:
        now = time.time()
        payload = {
            "sessionId": "7b0912",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(now * 1000),
            "pid": os.getpid(),
        }
        _NDJSON.parent.mkdir(parents=True, exist_ok=True)
        with _NDJSON.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        stamp = datetime.now().strftime("%H:%M:%S")
        bits = []
        for key, val in (data or {}).items():
            if val is None or val == "" or val == []:
                continue
            text = str(val)
            if len(text) > 80:
                text = text[:77] + "..."
            bits.append(f"{key}={text}")
        detail = (" | " + " ".join(bits)) if bits else ""
        line = f"[{stamp}] pid={os.getpid()} [{hypothesis_id}] {message} @ {location}{detail}\n"
        with _HUMAN.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    # #endregion
