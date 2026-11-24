"""Shared artifact / chart validation for local and cloud MCP.

Treat every tool argument as untrusted LLM output. Keep checks server-side.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any

MAX_ARTIFACT_CHARS = 512_000
MAX_TITLE_CHARS = 80
MAX_CHART_POINTS = 24
MAX_LABEL_CHARS = 40
MAX_SUBTITLE_CHARS = 120
MAX_UNIT_CHARS = 16
DEVICE_ID_RE = re.compile(r"^FS[0-9A-F]{12}$")
CHART_TYPES = frozenset({"auto", "bar", "line", "hbar", "table"})
WIFI_KEYS = frozenset(
    {"ssid", "wifi", "wifi_ssid", "wifi_password", "psk", "passphrase", "password_wifi", "network"}
)
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Strip xmlns so SVG namespace URIs do not trip the network filter.
XMLNS_ATTR = re.compile(r"(?i)\sxmlns(?::[\w.-]+)?\s*=\s*(\"[^\"]*\"|'[^']*')")
# Named / numeric entities that can hide schemes (javascript&#58;, etc.).
HTML_ENTITY = re.compile(
    r"&(?:#x[0-9a-f]+|#\d+|lt|gt|amp|quot|apos|colon|sol|Tab|NewLine);",
    re.IGNORECASE,
)
# Explicit schemes, protocol-relative //host, and data:text/html.
FORBIDDEN_URI = re.compile(
    r"(?i)"
    r"(?:"
    r"\b(?:https?|file|ftp|ws|wss|chrome|chrome-extension|javascript)\s*:"
    r"|(?:^|[\s\"'=(])/\s*/\s*[a-z0-9]"
    r"|data\s*:\s*text\s*/\s*html"
    r")"
)


class SecurityError(RuntimeError):
    """Rejected input. Message is safe to return to the client."""


def require_string(value, label, *, allow_empty=False, max_chars=None):
    if value is None:
        if allow_empty:
            return ""
        raise SecurityError(f"{label} is required. Pass a non-empty string.")
    if not isinstance(value, str):
        raise SecurityError(f"{label} must be a string.")
    if CONTROL_CHARS.search(value):
        raise SecurityError(f"{label} contains control characters. Remove them and retry.")
    if max_chars is not None and len(value) > max_chars:
        raise SecurityError(f"{label} is too large (max {max_chars} characters).")
    if not allow_empty and not value.strip():
        raise SecurityError(f"{label} is required. Pass a non-empty string.")
    return value


def validate_device_id(device_id: str) -> str:
    device_id = require_string(device_id, "device_id", max_chars=14).upper()
    if not DEVICE_ID_RE.match(device_id):
        raise SecurityError(
            "device_id must be FS plus 12 hex digits (example: FSA1B2C3D4E5F6). "
            "Copy it from list_panels."
        )
    return device_id


def _decode_entities_for_scan(text: str) -> str:
    """Best-effort decode so obfuscated schemes are visible to the filter."""
    prev = None
    out = text
    for _ in range(3):
        if out == prev:
            break
        prev = out
        out = html_lib.unescape(out)
        out = HTML_ENTITY.sub(":", out)
    return out


def reject_external_uris(text, label):
    scrubbed = XMLNS_ATTR.sub("", text)
    scrubbed = _decode_entities_for_scan(scrubbed)
    if FORBIDDEN_URI.search(scrubbed):
        raise SecurityError(
            f"{label} must be self-contained. Remove network URLs, //hosts, "
            "javascript:, file:, and data:text/html from the page."
        )


def body_has_wifi_keys(data: dict) -> bool:
    return any(str(k).lower() in WIFI_KEYS for k in data)


def validate_artifact_args(arguments=None, *, html=None, svg=None, device_id=None, require_device_id=False):
    """Validate push_artifact inputs.

    Local connector passes a dict as the first positional arg.
    Cloud passes html=/svg=/device_id= kwargs with require_device_id implied.
    """
    if arguments is not None:
        if not isinstance(arguments, dict):
            raise SecurityError("arguments must be a JSON object.")
        unexpected = set(arguments) - {"html", "svg", "title", "device_id"}
        if unexpected:
            raise SecurityError(
                "push_artifact only accepts html or svg (optional title/device_id). "
                "For graphs from data points, call push_chart instead."
            )
        html = arguments.get("html", html)
        svg = arguments.get("svg", svg)
        if "device_id" in arguments and arguments.get("device_id") is not None:
            device_id = arguments.get("device_id")
            require_device_id = True

    if require_device_id or device_id is not None:
        if device_id is None or (isinstance(device_id, str) and not device_id.strip()):
            raise SecurityError("device_id is required. Call list_panels and pass panels[0].device_id.")
        device_id = validate_device_id(str(device_id))

    has_html = isinstance(html, str) and bool(html.strip())
    has_svg = isinstance(svg, str) and bool(svg.strip())
    if has_html and has_svg:
        raise SecurityError("Send either html or svg — not both.")
    if has_html:
        html = require_string(html, "html", max_chars=MAX_ARTIFACT_CHARS)
        reject_external_uris(html, "html")
        out = {"html": html, "svg": None}
    elif has_svg:
        svg = require_string(svg, "svg", max_chars=MAX_ARTIFACT_CHARS)
        reject_external_uris(svg, "svg")
        out = {"html": None, "svg": svg}
    else:
        raise SecurityError(
            "Pass the finished page as html or svg. "
            "For a chart from labels/values, call push_chart instead."
        )
    if device_id is not None:
        out["device_id"] = device_id
    return out


def validate_chart_args(
    *,
    device_id: str | None = None,
    title: str,
    labels: list[Any],
    values: list[Any],
    chart_type: str = "auto",
    unit: str = "",
    subtitle: str = "",
    require_device_id: bool = False,
) -> dict[str, Any]:
    """Validate push_chart structured inputs. Returns normalized fields."""
    if require_device_id or device_id is not None:
        if device_id is None or (isinstance(device_id, str) and not str(device_id).strip()):
            raise SecurityError("device_id is required. Call list_panels and pass panels[0].device_id.")
        device_id = validate_device_id(str(device_id))

    title = require_string(title, "title", max_chars=MAX_TITLE_CHARS)
    subtitle = require_string(subtitle or "", "subtitle", allow_empty=True, max_chars=MAX_SUBTITLE_CHARS)
    unit = require_string(unit or "", "unit", allow_empty=True, max_chars=MAX_UNIT_CHARS)

    chart_type = require_string(chart_type or "auto", "chart_type", max_chars=16).strip().lower()
    if chart_type not in CHART_TYPES:
        raise SecurityError(
            "chart_type must be one of: auto, bar, line, hbar, table. "
            "Use auto if unsure."
        )

    if not isinstance(labels, list) or not isinstance(values, list):
        raise SecurityError("labels and values must be arrays of the same length.")
    if len(labels) != len(values):
        raise SecurityError(
            f"labels and values must be the same length "
            f"(got {len(labels)} labels and {len(values)} values)."
        )
    if not labels:
        raise SecurityError("Pass at least one data point in labels and values.")
    if len(labels) > MAX_CHART_POINTS:
        raise SecurityError(
            f"Too many points (max {MAX_CHART_POINTS}). "
            "Summarize or split the data, then call push_chart again."
        )

    clean_labels: list[str] = []
    clean_values: list[float] = []
    for i, (lab, val) in enumerate(zip(labels, values)):
        lab_s = require_string(str(lab), f"labels[{i}]", max_chars=MAX_LABEL_CHARS)
        try:
            num = float(val)
        except (TypeError, ValueError) as exc:
            raise SecurityError(
                f"values[{i}] must be a number. Got {val!r}."
            ) from exc
        if num != num or num in (float("inf"), float("-inf")):  # NaN / inf
            raise SecurityError(f"values[{i}] must be a finite number.")
        clean_labels.append(lab_s)
        clean_values.append(num)

    out: dict[str, Any] = {
        "title": title,
        "subtitle": subtitle,
        "unit": unit,
        "chart_type": chart_type,
        "labels": clean_labels,
        "values": clean_values,
    }
    if device_id is not None:
        out["device_id"] = device_id
    return out
