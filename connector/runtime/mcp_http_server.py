"""Fennsill hosted MCP — Streamable HTTP for Claude / ChatGPT connectors.

Local (preferred for ChatGPT Desktop):  http://127.0.0.1:8766/mcp
Public (opt-in via Fennsill Host confirm): Cloudflare URL + /mcp

Ship note: bind 127.0.0.1 by default. Public tunnels are explicit Host UX only.
Tools delegate to mcp_server.call_tool (allowlisted in security.py).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "templates"))
sys.path.insert(0, str(ROOT / "connector"))
sys.path.insert(0, str(ROOT / "connector" / "runtime"))

os.environ.setdefault("FENNSILL_ROOT", str(ROOT))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "connector" / "browsers"))
os.environ.setdefault("FENNSILL_PAGES", str(ROOT / "connector" / "pages"))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

from mcp_catalog import (  # noqa: E402
    LOCAL_INSTRUCTIONS,
    LIST_PANELS_LOCAL,
    PUSH_ARTIFACT,
    PUSH_CHART,
    SET_WIFI,
    START_LIVE,
    STOP_LIVE,
)
from mcp_server import call_tool  # noqa: E402
from security import SecurityError  # noqa: E402

HOST = os.environ.get("FENNSILL_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("FENNSILL_MCP_PORT", "8766"))

server = MCPServer(
    "fennsill",
    instructions=LOCAL_INSTRUCTIONS,
)


def _run(name: str, arguments: dict[str, Any] | None = None) -> str:
    try:
        result = call_tool(name, arguments or {})
        return json.dumps(result, indent=2)
    except (SecurityError, RuntimeError, ValueError, TypeError, TimeoutError) as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


@server.tool(description=LIST_PANELS_LOCAL)
def list_panels() -> str:
    return _run("list_panels")


@server.tool(description=PUSH_CHART + " On local USB, device_id is optional.")
def push_chart(
    title: str,
    labels: list[str],
    values: list[float],
    chart_type: str = "auto",
    unit: str = "",
    subtitle: str = "",
) -> str:
    return _run(
        "push_chart",
        {
            "title": title,
            "labels": labels,
            "values": values,
            "chart_type": chart_type,
            "unit": unit,
            "subtitle": subtitle,
        },
    )


@server.tool(description=PUSH_ARTIFACT)
def push_artifact(html: str | None = None, svg: str | None = None) -> str:
    args: dict[str, Any] = {}
    if html:
        args["html"] = html
    if svg:
        args["svg"] = svg
    return _run("push_artifact", args)


@server.tool(description=START_LIVE)
def start_live_update(kind: str, interval_sec: int = 300, title: str = "") -> str:
    return _run(
        "start_live_update",
        {"kind": kind, "interval_sec": interval_sec, "title": title},
    )


@server.tool(description=STOP_LIVE)
def stop_live_update(kind: str | None = None) -> str:
    args: dict[str, Any] = {}
    if kind:
        args["kind"] = kind
    return _run("stop_live_update", args)


@server.tool(description=SET_WIFI)
def set_wifi(ssid: str, password: str) -> str:
    return _run("set_wifi", {"ssid": ssid, "password": password})


def main() -> None:
    # Line-buffered so Fennsill Host can drain logs without stalling the process.
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    print(f"FENNSILL_MCP http://{HOST}:{PORT}/mcp", flush=True)
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
