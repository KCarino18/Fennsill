"""Artiphact hosted MCP — Streamable HTTP for Claude / ChatGPT connectors.

Local (preferred for ChatGPT Desktop):  http://127.0.0.1:8766/mcp
Public (opt-in via Artiphact Host confirm): Cloudflare URL + /mcp

Ship note: bind 127.0.0.1 by default. Public tunnels are explicit Host UX only.
Tools delegate to mcp_server.call_tool (allowlisted in security.py).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "templates"))
sys.path.insert(0, str(ROOT / "connector"))

os.environ.setdefault("ARTIPHACT_ROOT", str(ROOT))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "connector" / "browsers"))
os.environ.setdefault("ARTIPHACT_PAGES", str(ROOT / "connector" / "pages"))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

from mcp_server import call_tool  # noqa: E402
from security import SecurityError  # noqa: E402

HOST = os.environ.get("ARTIPHACT_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ARTIPHACT_MCP_PORT", "8766"))

server = MCPServer(
    "artiphact",
    instructions=(
        "Artiphact pushes finished 800x480 HTML/SVG pages to a USB e-ink panel. "
        "Call list_panels, then push_artifact. Do not create a Claude Artifact web preview "
        "as a substitute for pushing to the panel."
    ),
)


def _run(name: str, arguments: dict[str, Any] | None = None) -> str:
    try:
        result = call_tool(name, arguments or {})
        return json.dumps(result, indent=2)
    except (SecurityError, RuntimeError, ValueError, TypeError, TimeoutError) as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


@server.tool(description="List Artiphact e-ink panels plugged in over USB.")
def list_panels() -> str:
    return _run("list_panels")


@server.tool(
    description=(
        "Push a finished 800x480 black/white HTML or SVG page to the Artiphact panel now. "
        "Self-contained HTML only — no external URLs. Prefer html for dashboards."
    )
)
def push_artifact(html: str | None = None, svg: str | None = None) -> str:
    args: dict[str, Any] = {}
    if html:
        args["html"] = html
    if svg:
        args["svg"] = svg
    return _run("push_artifact", args)


@server.tool(
    description=(
        "Start a recurring live feed on the Artiphact panel. "
        "kind=nfl_scores refreshes an NFL scoreboard on an interval."
    )
)
def start_live_update(kind: str, interval_sec: int = 300, title: str = "") -> str:
    return _run(
        "start_live_update",
        {"kind": kind, "interval_sec": interval_sec, "title": title},
    )


@server.tool(description="Stop a live feed previously started with start_live_update.")
def stop_live_update(kind: str | None = None) -> str:
    args: dict[str, Any] = {}
    if kind:
        args["kind"] = kind
    return _run("stop_live_update", args)


@server.tool(description="Send home Wi-Fi name and password to the panel over USB.")
def set_wifi(ssid: str, password: str) -> str:
    return _run("set_wifi", {"ssid": ssid, "password": password})


def main() -> None:
    # Line-buffered so Artiphact Host can drain logs without stalling the process.
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    print(f"ARTIPHACT_MCP http://{HOST}:{PORT}/mcp", flush=True)
    # Cloudflare quick tunnels send Host: *.trycloudflare.com — the SDK's
    # default DNS-rebinding guard rejects that with HTTP 421.
    # Clients MUST Accept: application/json, text/event-stream or the SDK returns 406.
    server.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        streamable_http_path="/mcp",
        # Stateless avoids session sticky issues with ChatGPT Desktop / tunnels.
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


if __name__ == "__main__":
    main()
