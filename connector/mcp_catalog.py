"""Shared MCP tool copy + schemas for local and cloud servers.

One source of truth for descriptions so Claude / GPT / Grok / Cursor / Gemini
see the same call patterns.
"""

from __future__ import annotations

CLOUD_INSTRUCTIONS = (
    "Fennsill cloud pushes finished 800x480 black/white pages to the buyer's e-ink panel. "
    "Workflow: (1) Call list_panels and copy device_id. "
    "(2) For graphs/charts from data points, call push_chart with title, labels, and values — "
    "do not hand-write HTML for simple charts. "
    "(3) For custom dashboards/layouts, call push_artifact with self-contained html (or svg). "
    "(4) Only tell the user the screen updated when delivered=true. "
    "If delivered=false, report the error or call get_push_status with job_id. "
    "Offline at enqueue time is OK — the local Agent still delivers over USB. "
    "Never create a web Artifact preview as a substitute. Never send Wi-Fi credentials."
)

LOCAL_INSTRUCTIONS = (
    "Fennsill pushes finished 800x480 black/white pages to a USB e-ink panel. "
    "Workflow: (1) Call list_panels. "
    "(2) For graphs/charts from data points, call push_chart with title, labels, and values — "
    "do not hand-write HTML for simple charts. "
    "(3) For custom dashboards/layouts, call push_artifact with self-contained html (or svg). "
    "(4) Confirm delivery from the tool result (delivered or pushed). "
    "Never create a web Artifact preview as a substitute for pushing to the panel."
)

LIST_PANELS_CLOUD = (
    "Call this first. Lists e-ink panels linked to this MCP account and returns device_id "
    "values you must pass to push tools. If panels is empty, the buyer must link the panel "
    "on mcp.fennsill.com with the same account. If linked but never heartbeated, they must "
    "paste a device key into Fennsill Desk and keep the Agent service running."
)

LIST_PANELS_LOCAL = (
    "Call this first. Lists Fennsill e-ink panels plugged in over USB on this computer."
)

PUSH_CHART = (
    "Push a clean 800x480 black/white chart to the panel from structured data. "
    "Use this whenever the user asks for a graph/chart/plot of data points — "
    "do not hand-write HTML. Required: title, labels[], values[] (same length). "
    "Optional chart_type: auto|bar|line|hbar|table (default auto). "
    "Optional hold_sec: seconds to keep this page on the panel before the next "
    "queued push starts (max 21600). Later pushes wait their turn in order."
)

PUSH_ARTIFACT = (
    "Push a custom 800x480 black/white self-contained HTML or SVG page to the panel. "
    "Use only for custom dashboards/layouts — for simple graphs from data points, "
    "prefer push_chart. No external URLs; inline CSS only; pure black/white high contrast. "
    "Prefer html over svg for dashboards. Optional hold_sec: seconds to keep this page "
    "on the panel before the next queued push starts (max 21600); later pushes wait "
    "their turn. Only report success when delivered=true (cloud) or the tool confirms "
    "the panel refresh. If status is queued/claimed, it is waiting in the panel queue."
)

GET_PUSH_STATUS = (
    "Check whether a push reached the panel. Call after delivered=false or when you need "
    "to re-check. Pass job_id from the last push, or pass device_id alone to see recent jobs."
)

START_LIVE = (
    "Start a recurring live feed on the panel (keeps updating without the user pasting). "
    "Use for ongoing feeds like NFL scores — not for one-shot charts (use push_chart). "
    "kind must be nfl_scores. Default interval_sec is 300."
)

STOP_LIVE = (
    "Stop a live feed previously started with start_live_update. "
    "Omit kind to stop all live feeds on that panel."
)

SET_WIFI = "Send home Wi-Fi name and password to the panel over USB (local only)."

DEVICE_ID_PROP = {
    "type": "string",
    "pattern": "^FS[0-9A-F]{12}$",
    "description": "Panel id from list_panels (example: FSA1B2C3D4E5F6).",
}

CHART_INPUT_PROPERTIES = {
    "title": {
        "type": "string",
        "maxLength": 80,
        "description": "Chart headline shown on the panel.",
    },
    "labels": {
        "type": "array",
        "minItems": 1,
        "maxItems": 24,
        "items": {"type": "string", "maxLength": 40},
        "description": "Category labels, same order/length as values.",
    },
    "values": {
        "type": "array",
        "minItems": 1,
        "maxItems": 24,
        "items": {"type": "number"},
        "description": "Numeric series, same order/length as labels.",
    },
    "chart_type": {
        "type": "string",
        "enum": ["auto", "bar", "line", "hbar", "table"],
        "default": "auto",
        "description": "Layout. Use auto if unsure.",
    },
    "unit": {
        "type": "string",
        "maxLength": 16,
        "description": "Optional unit suffix (e.g. %, $, pts).",
    },
    "subtitle": {
        "type": "string",
        "maxLength": 120,
        "description": "Optional secondary line under the title.",
    },
    "hold_sec": {
        "type": "integer",
        "minimum": 0,
        "maximum": 21600,
        "description": "Seconds to keep this page on the panel before the next queued push (default 0).",
    },
}


def local_tools_catalog() -> dict:
    """Frozen local stdio catalog (includes set_wifi; no cloud-only tools)."""
    return {
        "version": "1.4.0",
        "note": "Frozen tools. The buyer talks to their AI. The AI calls these tools.",
        "tools": [
            {
                "name": "list_panels",
                "description": LIST_PANELS_LOCAL,
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "name": "push_chart",
                "description": PUSH_CHART + " On local USB, device_id is optional.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        **CHART_INPUT_PROPERTIES,
                    },
                    "required": ["title", "labels", "values"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "push_artifact",
                "description": PUSH_ARTIFACT,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "html": {
                            "type": "string",
                            "maxLength": 512000,
                            "description": (
                                "Finished 800x480 self-contained HTML. Pure B/W, inline CSS, "
                                "no external URLs."
                            ),
                        },
                        "svg": {
                            "type": "string",
                            "maxLength": 512000,
                            "description": "Finished 800x480 self-contained SVG (same rules as html).",
                        },
                        "hold_sec": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 21600,
                            "description": (
                                "Seconds to keep this page on the panel before the next "
                                "queued push (default 0)."
                            ),
                        },
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "start_live_update",
                "description": START_LIVE,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["nfl_scores"],
                            "description": "Which live feed to run.",
                        },
                        "interval_sec": {
                            "type": "integer",
                            "minimum": 60,
                            "maximum": 3600,
                            "description": "Seconds between refreshes (default 300).",
                        },
                        "title": {"type": "string", "maxLength": 80},
                    },
                    "required": ["kind"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "stop_live_update",
                "description": STOP_LIVE,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["nfl_scores"],
                            "description": "Feed to stop. Omit to stop all.",
                        }
                    },
                    "additionalProperties": False,
                },
            },
            {
                "name": "set_wifi",
                "description": SET_WIFI,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "ssid": {
                            "type": "string",
                            "maxLength": 32,
                            "description": "Wi-Fi network name.",
                        },
                        "password": {
                            "type": "string",
                            "maxLength": 63,
                            "description": "Wi-Fi password.",
                        },
                    },
                    "required": ["ssid", "password"],
                    "additionalProperties": False,
                },
            },
        ],
    }
