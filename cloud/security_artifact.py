"""Artifact validation for cloud push (no USB)."""

from __future__ import annotations

import re

MAX_ARTIFACT_CHARS = 512_000
FORBIDDEN_URI = re.compile(
    r"(?i)\b(?:https?|file|ftp|ws|wss|chrome|chrome-extension|javascript)\s*:",
)
# SVG/XML namespace decls look like http URLs but are not network fetches.
XMLNS_ATTR = re.compile(r"(?i)\sxmlns(?::[\w.-]+)?\s*=\s*(\"[^\"]*\"|'[^']*')")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
DEVICE_ID_RE = re.compile(r"^FS[0-9A-F]{12}$")
WIFI_KEYS = frozenset(
    {"ssid", "wifi", "wifi_ssid", "wifi_password", "psk", "passphrase", "password_wifi", "network"}
)


class SecurityError(RuntimeError):
    """Safe to return to the client."""


def require_string(value, label, *, allow_empty=False, max_chars=None):
    if value is None:
        if allow_empty:
            return ""
        raise SecurityError(f"{label} is required.")
    if not isinstance(value, str):
        raise SecurityError(f"{label} must be a string.")
    if CONTROL_CHARS.search(value):
        raise SecurityError(f"{label} contains control characters.")
    if max_chars is not None and len(value) > max_chars:
        raise SecurityError(f"{label} is too large.")
    if not allow_empty and not value.strip():
        raise SecurityError(f"{label} is required.")
    return value


def reject_external_uris(text, label):
    scrubbed = XMLNS_ATTR.sub("", text)
    if FORBIDDEN_URI.search(scrubbed):
        raise SecurityError(
            f"{label} must be self-contained. Remove network and file URLs from the page."
        )


def validate_artifact_args(*, html=None, svg=None, device_id=None):
    """Validate push_artifact inputs. device_id is required on cloud."""
    device_id = require_string(device_id, "device_id", max_chars=14).upper()
    if not DEVICE_ID_RE.match(device_id):
        raise SecurityError("device_id must be FS plus 12 hex digits.")
    has_html = isinstance(html, str) and bool(html.strip())
    has_svg = isinstance(svg, str) and bool(svg.strip())
    if has_html and has_svg:
        raise SecurityError("Send either html or svg.")
    if has_html:
        html = require_string(html, "html", max_chars=MAX_ARTIFACT_CHARS)
        reject_external_uris(html, "html")
        return {"device_id": device_id, "html": html, "svg": None}
    if has_svg:
        svg = require_string(svg, "svg", max_chars=MAX_ARTIFACT_CHARS)
        reject_external_uris(svg, "svg")
        return {"device_id": device_id, "html": None, "svg": svg}
    raise SecurityError("Pass the finished page as html or svg.")


def validate_device_id(device_id: str) -> str:
    device_id = require_string(device_id, "device_id", max_chars=14).upper()
    if not DEVICE_ID_RE.match(device_id):
        raise SecurityError("device_id must be FS plus 12 hex digits.")
    return device_id


def body_has_wifi_keys(data: dict) -> bool:
    return any(str(k).lower() in WIFI_KEYS for k in data)
