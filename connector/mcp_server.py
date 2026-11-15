"""Artiphact MCP — the AI talks, the panel updates.

Buyer flow: plug in panel, open Artiphact.exe, talk to Claude Desktop / Cursor
(or any MCP client). Natural language like "push NFL scores" or "graph this
SQL and send it to the device" becomes tool calls: push_artifact /
start_live_update. No paste page required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "templates"))
sys.path.insert(0, str(ROOT / "connector"))

# ChatGPT sometimes starts MCP without env from config.toml. Force the
# paths so Playwright/serial never hang looking in the wrong place.
import os as _os

_os.environ.setdefault("ARTIPHACT_ROOT", str(ROOT))
_os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH",
    str(ROOT / "connector" / "browsers"),
)
_os.environ.setdefault("ARTIPHACT_PAGES", str(ROOT / "connector" / "pages"))

from intake import intake_page  # noqa: E402
from panel_ports import (  # noqa: E402
    confirmed_panels,
    list_candidate_ports,
    panel_absence_message,
    scan_panels,
)
from pull_tools import load_catalog  # noqa: E402
from security import (  # noqa: E402
    ALLOWED_TOOLS,
    MAX_HEADER_LINE,
    MAX_HEADERS,
    SecurityError,
    load_json_object,
    parse_content_length,
    read_linked_provider,
    redact,
    require_dict,
    validate_tool_name,
    validate_wifi_args,
)
from usb_protocol import wifi_line  # noqa: E402

LINKED = Path(__import__("os").environ.get("ARTIPHACT_LINK", ROOT / "connector" / "linked.json"))
CHUNK_RETRIES = 2
# Keep panel discovery short so ChatGPT fails in seconds when USB is missing/busy.
PANEL_PROBE_TIMEOUT = 1.2
_TOOLS = None


_TOOLS_MTIME = None


def tool_list():
    """Return the frozen catalog. Reloads only when tools.json changes on disk."""
    global _TOOLS, _TOOLS_MTIME
    catalog_path = ROOT / "connector" / "tools.json"
    try:
        mtime = catalog_path.stat().st_mtime
    except OSError:
        mtime = None
    if _TOOLS is None or mtime != _TOOLS_MTIME:
        catalog = load_catalog()
        tools = catalog["tools"]
        names = [tool.get("name") for tool in tools]
        if set(names) != ALLOWED_TOOLS or len(names) != len(ALLOWED_TOOLS):
            raise SecurityError("Frozen tool catalog does not match the allowlist.")
        _TOOLS = tools
        _TOOLS_MTIME = mtime
    return _TOOLS


def linked_provider():
    return read_linked_provider(LINKED, ROOT)


def matching_ports():
    panels = confirmed_panels(timeout=PANEL_PROBE_TIMEOUT)
    # Return only what Claude needs to choose a panel.
    return [{"port": panel["port"], "description": panel.get("description", "")} for panel in panels]


def active_provider():
    """Tag the page source. Plug-and-play: no account gate — the local exe is enough."""
    try:
        return linked_provider() or "local"
    except SecurityError:
        return "local"


class SerialLink:
    def __init__(self, ser):
        self.ser = ser

    def feed(self, data):
        self.ser.write(data)
        self.ser.flush()
        return self.ser.read_until(b"\n", 15)

    def greeting(self):
        self.ser.write(b"HELLO\n")
        self.ser.flush()
        return self.ser.read_until(b"\n", 5)

    def close(self):
        close = getattr(self.ser, "close", None)
        if close:
            close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def open_link():
    from serial_guard import SerialBusy, SerialGuard

    import serial

    try:
        with SerialGuard(timeout=20.0):
            scan = scan_panels(timeout=PANEL_PROBE_TIMEOUT)
            ports = scan["ready"]
            if len(ports) != 1:
                raise SecurityError(panel_absence_message(scan, timeout=PANEL_PROBE_TIMEOUT))
            try:
                # Avoid DTR/RTS reset; match push_page.open_panel.
                ser = serial.Serial()
                ser.port = ports[0]["port"]
                ser.baudrate = 115200
                ser.timeout = 0.5
                ser.write_timeout = 3
                ser.dtr = False
                ser.rts = False
                ser.open()
            except serial.SerialException as exc:
                raise SecurityError(f"{ports[0]['port']} is busy. Retry in a few seconds.") from exc
            # Caller owns the open port; release the file lock after open so
            # only this SerialLink holds COM (same process).
            link = SerialLink(ser)
    except SerialBusy as exc:
        raise SecurityError(str(exc)) from exc
    return link


def push_frame_reliable(link, frame):
    """Push with per-chunk retries. Stops on a permanent failure."""
    from usb_protocol import encode_show, split_frame

    link.greeting()
    replies = []
    for packet in split_frame(frame):
        accepted = False
        last = ""
        for _ in range(CHUNK_RETRIES + 1):
            last = link.feed(packet).decode("ascii", "replace").strip()
            replies.append(last)
            if last.startswith("ACK"):
                accepted = True
                break
        if not accepted:
            return replies
    last = link.feed(encode_show(frame)).decode("ascii", "replace").strip()
    replies.append(last)
    return replies


def call_tool(name, arguments, link=None):
    name = validate_tool_name(name)
    arguments = require_dict(arguments)
    owned = link is None

    if name == "list_panels":
        # Do NOT open COM here — desk status / another tool may hold the port
        # briefly and ChatGPT would abort with "COM3 busy" without ever pushing.
        candidates = list_candidate_ports()
        # #region agent log
        try:
            from debug_ndjson import dlog

            dlog(
                "G",
                "mcp_server.py:call_tool",
                "list_panels_vid_only",
                {"ports": [p["port"] for p in candidates]},
            )
        except Exception:
            pass
        # #endregion
        if len(candidates) == 1:
            return {
                "panels": [
                    {"port": candidates[0]["port"], "description": candidates[0].get("description", "")}
                ],
                "busy": [],
                "silent": [],
                "note": "",
            }
        if len(candidates) > 1:
            names = ", ".join(p["port"] for p in candidates)
            return {
                "panels": [
                    {"port": p["port"], "description": p.get("description", "")} for p in candidates
                ],
                "busy": [],
                "silent": [],
                "note": f"Plug in exactly one panel. Matching ports: {names}",
            }
        return {
            "panels": [],
            "busy": [],
            "silent": [],
            "note": "No USB-connected Artiphact panel detected. Plug the panel in over USB and retry.",
        }

    if name == "push_artifact":
        # #region agent log
        try:
            import os as _os

            from debug_ndjson import dlog

            dlog(
                "C",
                "mcp_server.py:call_tool",
                "push_artifact_enter",
                {
                    "cwd": _os.getcwd(),
                    "artiphact_root": _os.environ.get("ARTIPHACT_ROOT"),
                    "has_html": bool(arguments.get("html")),
                    "has_svg": bool(arguments.get("svg")),
                    "injected_link": link is not None,
                },
            )
        except Exception:
            pass
        # #endregion
        provider = active_provider()
        # Prefer the shared intake path (gallery + optional USB). Tests may
        # inject a fake serial link; honor that for push-only verification.
        if link is not None:
            from intake import render_frame
            from pages_lib import save_page

            frame = render_frame(arguments)
            replies = push_frame_reliable(link, frame)
            if not replies or replies[-1] != "OK":
                raise SecurityError(replies[-1] if replies else "The panel did not accept the frame.")
            meta = save_page(frame, source=f"{provider}-artifact")
            return {"ok": True, "bytes": len(frame), "page_id": meta["id"], "pushed": True}
        result = intake_page(
            html=arguments.get("html"),
            svg=arguments.get("svg"),
            source=f"{provider}-artifact",
            push=True,
        )
        # Fail fast to the AI when USB delivery did not happen (no multi-minute hang).
        if not result.get("pushed"):
            detail = result.get("panel_error") or result.get("note") or "Panel push did not complete."
            page_id = result.get("page_id") or "?"
            raise SecurityError(f"{detail} (saved page_id={page_id})")
        return result

    if name == "start_live_update":
        from live_jobs import run_job, upsert_job

        kind = str(arguments.get("kind") or "").strip().lower()
        interval = int(arguments.get("interval_sec") or 300)
        title = str(arguments.get("title") or "")
        try:
            job = upsert_job(kind=kind, interval_sec=interval, title=title)
            # Push an immediate first frame so the user sees results in-chat.
            first = run_job(job)
        except ValueError as exc:
            raise SecurityError(str(exc)) from exc
        except Exception as exc:
            raise SecurityError(f"Live update started but first refresh failed: {exc}") from exc
        return {"ok": True, "job": job, "first_push": first}

    if name == "stop_live_update":
        from live_jobs import stop_job

        kind = arguments.get("kind")
        removed = stop_job(str(kind) if kind else None)
        return {"ok": True, "stopped": removed}

    if name == "set_wifi":
        clean = validate_wifi_args(arguments)
        target = link or open_link()
        try:
            target.greeting()
            reply = target.feed(wifi_line(clean["ssid"], clean["password"])).decode("ascii", "replace").strip()
            if reply != "OK":
                raise SecurityError(reply or "The panel did not store the network.")
            return {"ok": True}
        finally:
            if owned and hasattr(target, "close"):
                target.close()

    raise SecurityError("Unknown tool.")


def _tool_error(exc, arguments):
    secrets = []
    if isinstance(arguments, dict):
        secrets.append(arguments.get("password"))
    message = redact(str(exc), secrets)
    if not message:
        message = "The request was refused."
    return {"content": [{"type": "text", "text": message}], "isError": True}


def handle(message, link=None):
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    method = message.get("method")
    msg_id = message.get("id")
    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "artiphact", "version": "1.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        arguments = {}
        tool_name = "?"
        try:
            params = require_dict(message.get("params"), "params") if message.get("params") is not None else {}
            tool_name = str(params.get("name") or "?")
            arguments = params.get("arguments") or {}
            # #region agent log
            try:
                from debug_ndjson import dlog

                dlog(
                    "C",
                    "mcp_server.py:handle",
                    f"TOOL_START {tool_name}",
                    {"tool": tool_name, "has_html": bool(isinstance(arguments, dict) and arguments.get("html"))},
                    run_id="post-fix",
                )
            except Exception:
                pass
            # #endregion
            result = call_tool(params.get("name"), arguments, link)
            # #region agent log
            try:
                from debug_ndjson import dlog

                summary = result if isinstance(result, dict) else {"raw": str(result)[:120]}
                dlog(
                    "C",
                    "mcp_server.py:handle",
                    f"TOOL_OK {tool_name}",
                    {
                        "tool": tool_name,
                        "pushed": summary.get("pushed") if isinstance(summary, dict) else None,
                        "page_id": summary.get("page_id") if isinstance(summary, dict) else None,
                        "note": (summary.get("note") or summary.get("panel_error") or "")[:120]
                        if isinstance(summary, dict)
                        else "",
                    },
                    run_id="post-fix",
                )
            except Exception:
                pass
            # #endregion
            result = {"content": [{"type": "text", "text": json.dumps(result)}], "isError": False}
        except (SecurityError, RuntimeError, ValueError, TypeError, TimeoutError) as exc:
            # #region agent log
            try:
                from debug_ndjson import dlog

                dlog(
                    "C",
                    "mcp_server.py:handle",
                    f"TOOL_FAIL {tool_name}",
                    {"tool": tool_name, "err": str(exc)[:200]},
                    run_id="post-fix",
                )
            except Exception:
                pass
            # #endregion
            return {"jsonrpc": "2.0", "id": msg_id, "result": _tool_error(exc, arguments)}
        except Exception as exc:
            # #region agent log
            try:
                from debug_ndjson import dlog

                dlog(
                    "C",
                    "mcp_server.py:handle",
                    f"TOOL_CRASH {tool_name}",
                    {"tool": tool_name, "err": f"{type(exc).__name__}: {exc}"[:200]},
                    run_id="post-fix",
                )
            except Exception:
                pass
            # #endregion
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": "The connector refused the request."}], "isError": True},
            }
    elif method == "notifications/initialized":
        return None
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def read_message():
    headers = {}
    for _ in range(MAX_HEADERS):
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if len(line) > MAX_HEADER_LINE:
            raise SecurityError("JSON-RPC header line is too long.")
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode("ascii", "replace").partition(":")
        headers[key.strip().lower()] = value.strip()
    else:
        raise SecurityError("JSON-RPC headers are too long.")
    length = parse_content_length(headers.get("content-length", "0"))
    raw = sys.stdin.buffer.read(length)
    if len(raw) != length:
        raise SecurityError("JSON-RPC message was truncated.")
    return load_json_object(raw)


def write_message(payload):
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(data) > 1_048_576:
        data = json.dumps(
            {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32603, "message": "Response too large"}}
        ).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def main():
    # #region agent log
    try:
        import os as _os

        from debug_ndjson import dlog
        from serial_guard import LOCK_PATH as _LOCK

        dlog(
            "C",
            "mcp_server.py:main",
            "MCP_SERVER_START build=2026-11-13c",
            {
                "lock_path": str(_LOCK),
                "artiphact_root": _os.environ.get("ARTIPHACT_ROOT"),
                "cwd": _os.getcwd(),
                "pid": _os.getpid(),
            },
            run_id="post-fix",
        )
    except Exception:
        pass
    # #endregion
    while True:
        try:
            message = read_message()
        except SecurityError as exc:
            write_message({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": str(exc)}})
            continue
        if message is None:
            break
        response = handle(message)
        if response is not None:
            write_message(response)


if __name__ == "__main__":
    main()
