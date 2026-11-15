"""Shared page intake for MCP, HTTP bridge, and Artiphact.exe paste/import.

Any AI can produce HTML/SVG. This module turns it into a gallery page and
optionally pushes it to the USB panel.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "templates"))
sys.path.insert(0, str(ROOT / "connector"))

from artifact_frame import FRAME_BYTES, artifact_to_frame  # noqa: E402
from pages_lib import save_page  # noqa: E402
from panel_ports import panel_absence_message  # noqa: E402
from push_page import DEFAULT_READY_TIMEOUT, DEFAULT_SHOW_TIMEOUT, open_panel, read_line, wait_ready  # noqa: E402
from security import SecurityError, validate_artifact_args  # noqa: E402
from serial_guard import SerialBusy, SerialGuard  # noqa: E402
from usb_protocol import encode_show, split_frame  # noqa: E402

# Probe is short; lock wait is longer so ChatGPT can push while Artiphact.exe
# is open (desk status / rotate may briefly hold the lock).
PROBE_TIMEOUT = 1.2
# Scheduled ChatGPT/Cursor tasks need time to win the COM lock (tool timeout ~120s).
LOCK_TIMEOUT = 45.0


def render_frame(arguments: dict) -> bytes:
    clean = validate_artifact_args(arguments)
    try:
        frame = artifact_to_frame(html=clean["html"], svg=clean["svg"])
    except (ValueError, RuntimeError) as exc:
        raise SecurityError(str(exc)) from exc
    if len(frame) != FRAME_BYTES:
        raise SecurityError("The page did not become an 800x480 panel frame.")
    return frame


def push_frame_to_panel(frame: bytes) -> list[str]:
    """Push using the same HELLO/ACK path as push_page.py.

    Acquires the serial lock *before* opening COM so desk polling cannot
    steal the port mid-push (which ChatGPT reports as COM busy).
    """
    import os

    import serial

    # #region agent log
    try:
        from debug_ndjson import dlog
        from serial_guard import LOCK_PATH as _LOCK

        dlog(
            "C",
            "intake.py:push_frame_to_panel",
            "push_enter",
            {
                "root": str(ROOT),
                "cwd": os.getcwd(),
                "artiphact_root": os.environ.get("ARTIPHACT_ROOT"),
                "lock_path": str(_LOCK),
                "frame_bytes": len(frame),
                "runId_tag": "post-fix",
            },
            run_id="post-fix",
        )
    except Exception:
        pass
    # #endregion

    try:
        with SerialGuard(timeout=LOCK_TIMEOUT):
            # One open only: VID list + HELLO on the same handle (no close/reopen).
            from panel_ports import list_candidate_ports

            candidates = list_candidate_ports()
            # #region agent log
            try:
                from debug_ndjson import dlog

                dlog(
                    "E",
                    "intake.py:push_frame_to_panel",
                    "candidates_after_lock",
                    {"ports": [p["port"] for p in candidates]},
                    run_id="post-fix",
                )
            except Exception:
                pass
            # #endregion
            if len(candidates) != 1:
                scan = {
                    "ready": [],
                    "busy": [],
                    "silent": [],
                    "candidates": len(candidates),
                }
                if len(candidates) > 1:
                    scan["ready"] = candidates
                raise SecurityError(panel_absence_message(scan, timeout=PROBE_TIMEOUT))
            port = candidates[0]["port"]
            ser = None
            last_open_err: Exception | None = None
            for attempt in range(1, 4):
                try:
                    ser = open_panel(port)
                    # #region agent log
                    try:
                        from debug_ndjson import dlog

                        dlog(
                            "F",
                            "intake.py:push_frame_to_panel",
                            "open_panel_ok",
                            {"port": port, "attempt": attempt},
                            run_id="post-fix",
                        )
                    except Exception:
                        pass
                    # #endregion
                    break
                except serial.SerialException as exc:
                    last_open_err = exc
                    # #region agent log
                    try:
                        from debug_ndjson import dlog

                        dlog(
                            "F",
                            "intake.py:push_frame_to_panel",
                            "open_panel_fail",
                            {
                                "port": port,
                                "attempt": attempt,
                                "err": str(exc),
                                "err_type": type(exc).__name__,
                            },
                            run_id="post-fix",
                        )
                    except Exception:
                        pass
                    # #endregion
                    import time as _time

                    _time.sleep(0.35 * attempt)
            if ser is None:
                raise SecurityError(
                    f"{port} is busy. Retry in a few seconds."
                ) from last_open_err
            replies: list[str] = []
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
                    replies.append(line)
                    if not line.startswith("ACK"):
                        raise SecurityError(line or "Chunk failed.")
                ser.write(encode_show(frame))
                ser.flush()
                show = read_line(ser, DEFAULT_SHOW_TIMEOUT)
                replies.append(show)
                if "OK" not in show:
                    raise SecurityError(show or "Show failed.")
                # #region agent log
                try:
                    from debug_ndjson import dlog

                    dlog(
                        "E",
                        "intake.py:push_frame_to_panel",
                        "push_ok",
                        {"show": show, "acks": len(replies)},
                    )
                except Exception:
                    pass
                # #endregion
                return replies
            finally:
                ser.close()
    except SerialBusy as exc:
        # #region agent log
        try:
            from debug_ndjson import dlog

            dlog("A", "intake.py:push_frame_to_panel", "serial_busy", {"err": str(exc)})
        except Exception:
            pass
        # #endregion
        raise SecurityError(str(exc)) from exc
    except TimeoutError as exc:
        raise SecurityError(str(exc)) from exc


def intake_page(
    *,
    html: str | None = None,
    svg: str | None = None,
    title: str = "",
    source: str = "artifact",
    push: bool = True,
) -> dict:
    """Render, save to the gallery, and optionally push to the panel."""
    args = {}
    if html:
        args["html"] = html
    if svg:
        args["svg"] = svg
    # #region agent log
    try:
        from debug_ndjson import dlog

        dlog(
            "C",
            "intake.py:intake_page",
            "render_start",
            {
                "has_html": bool(html),
                "has_svg": bool(svg),
                "playwright": __import__("os").environ.get("PLAYWRIGHT_BROWSERS_PATH"),
            },
            run_id="post-fix",
        )
    except Exception:
        pass
    # #endregion
    frame = render_frame(args)
    # #region agent log
    try:
        from debug_ndjson import dlog

        dlog("C", "intake.py:intake_page", "render_ok", {"bytes": len(frame)}, run_id="post-fix")
    except Exception:
        pass
    # #endregion
    meta = save_page(frame, source=source, title=title or "")
    result = {
        "ok": True,
        "saved": True,
        "page_id": meta["id"],
        "bytes": len(frame),
        "pushed": False,
    }
    if not push:
        result["note"] = "Saved to Artiphact. Use Send to panel when you want it on the screen."
        return result

    try:
        push_frame_to_panel(frame)
        result["pushed"] = True
        result["note"] = "Saved and sent to the panel."
    except SecurityError as exc:
        result["note"] = f"Saved to Artiphact, but panel push failed: {exc}"
        result["panel_error"] = str(exc)
    except TimeoutError as exc:
        result["note"] = f"Saved to Artiphact, but panel push failed: {exc}"
        result["panel_error"] = str(exc)
    return result
