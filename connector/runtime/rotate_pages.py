"""Rotate selected gallery pages onto the panel on a fixed timer.

The desktop app writes connector/rotate_playlist.json. This worker keeps
pushing while enabled — including after Fennsill.exe is closed — so the
playlist stays in memory and on the e-ink.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
sys.path.insert(0, str(ROOT / "connector"))
sys.path.insert(0, str(ROOT / "connector" / "runtime"))
sys.path.insert(0, str(ROOT / "firmware"))

from pages_lib import load_frame  # noqa: E402
from panel_ports import confirmed_panels  # noqa: E402
from push_page import DEFAULT_READY_TIMEOUT, DEFAULT_SHOW_TIMEOUT, open_panel, read_line, wait_ready  # noqa: E402
from serial_guard import SerialBusy, SerialGuard  # noqa: E402
from usb_protocol import encode_show, split_frame  # noqa: E402

PLAYLIST_PATH = Path(
    os.environ.get("FENNSILL_ROTATE", ROOT / "connector" / "rotate_playlist.json")
)
DEFAULT_INTERVAL = 8


def load_playlist() -> dict:
    if not PLAYLIST_PATH.is_file():
        return {"enabled": False, "interval_sec": DEFAULT_INTERVAL, "page_ids": []}
    try:
        data = json.loads(PLAYLIST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": False, "interval_sec": DEFAULT_INTERVAL, "page_ids": []}
    if not isinstance(data, dict):
        return {"enabled": False, "interval_sec": DEFAULT_INTERVAL, "page_ids": []}
    ids = data.get("page_ids") or []
    if not isinstance(ids, list):
        ids = []
    interval = data.get("interval_sec", DEFAULT_INTERVAL)
    try:
        interval = int(interval)
    except (TypeError, ValueError):
        interval = DEFAULT_INTERVAL
    return {
        "enabled": bool(data.get("enabled")),
        "interval_sec": max(3, min(interval, 600)),
        "page_ids": [str(x) for x in ids if str(x).strip()],
    }


def push_frame(frame: bytes) -> bool:
    """Open COM only for the push, then release so MCP can use the panel."""
    try:
        with SerialGuard(timeout=8.0):
            panels = confirmed_panels(timeout=1.2)
            if len(panels) != 1:
                return False
            ser = open_panel(panels[0]["port"])
            try:
                wait_ready(ser, timeout=DEFAULT_READY_TIMEOUT)
                for packet in split_frame(frame):
                    ser.write(packet)
                    ser.flush()
                    line = read_line(ser, 8.0)
                    if line == "SPLASH":
                        wait_ready(ser, timeout=DEFAULT_READY_TIMEOUT)
                        ser.write(packet)
                        ser.flush()
                        line = read_line(ser, 8.0)
                    if not line.startswith("ACK"):
                        print(f"rotate: chunk failed: {line or 'empty'}", flush=True)
                        return False
                ser.write(encode_show(frame))
                ser.flush()
                show = read_line(ser, DEFAULT_SHOW_TIMEOUT)
                if "OK" not in show:
                    print(f"rotate: show failed: {show or 'empty'}", flush=True)
                    return False
                return True
            finally:
                ser.close()
    except SerialBusy as exc:
        print(f"rotate: serial busy: {exc}", flush=True)
        return False
    except TimeoutError as exc:
        print(f"rotate: timeout: {exc}", flush=True)
        return False
    except Exception as exc:
        print(f"rotate: open/push failed: {exc}", flush=True)
        return False


def main():
    print("rotate: watching playlist", flush=True)
    index = 0
    last_ids: list[str] = []

    while True:
        playlist = load_playlist()
        ids = playlist["page_ids"]
        interval = playlist["interval_sec"]

        if not playlist["enabled"] or len(ids) == 0:
            time.sleep(1.0)
            continue

        if ids != last_ids:
            index = 0
            last_ids = list(ids)

        page_id = ids[index % len(ids)]
        index = (index + 1) % len(ids)

        try:
            frame = load_frame(page_id)
        except Exception as exc:
            print(f"rotate: skip {page_id}: {exc}", flush=True)
            time.sleep(1.0)
            continue

        try:
            ok = push_frame(frame)
            if ok:
                print(f"rotate: showed {page_id}", flush=True)
        except Exception as exc:
            print(f"rotate: push error: {exc}", flush=True)

        # Sleep in small chunks so enable/disable and playlist edits apply quickly.
        # Port is closed between frames so ChatGPT/MCP can push without hanging.
        deadline = time.time() + interval
        while time.time() < deadline:
            time.sleep(0.25)
            fresh = load_playlist()
            if not fresh["enabled"] or fresh["page_ids"] != ids:
                break


if __name__ == "__main__":
    main()
