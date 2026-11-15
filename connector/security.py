"""Security controls for the Fennsill MCP connector.

Aligned with OWASP ASVS input validation, secret handling, and least-privilege
rendering. This module is not a certification; it encodes the concrete checks
the connector enforces.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Transport and tool bounds (ASVS V5 input validation / V11 business limits)
MAX_MESSAGE_BYTES = 1_048_576
MAX_HEADER_LINE = 256
MAX_HEADERS = 32
MAX_ARTIFACT_CHARS = 512_000
MAX_SSID_CHARS = 32
MAX_PASSWORD_CHARS = 63
MAX_TOOL_NAME = 64
ALLOWED_PROVIDERS = frozenset(
    {
        "local",
        "claude",
        "chatgpt",
        "openai",
        "gemini",
        "google",
        "grok",
        "xai",
        "cursor",
    }
)
ALLOWED_TOOLS = frozenset(
    {"list_panels", "push_artifact", "start_live_update", "stop_live_update", "set_wifi"}
)

# Artifact body must not open a second channel off this computer
FORBIDDEN_URI = re.compile(
    r"(?i)\b(?:https?|file|ftp|ws|wss|chrome|chrome-extension|javascript)\s*:",
)

CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class SecurityError(RuntimeError):
    """Rejected input or unsafe state. Message is safe to return to the client."""


def require_dict(value, label="arguments"):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SecurityError(f"{label} must be a JSON object.")
    return value


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


def validate_tool_name(name):
    name = require_string(name, "tool name", max_chars=MAX_TOOL_NAME)
    if name not in ALLOWED_TOOLS:
        raise SecurityError("Unknown tool.")
    return name


def validate_artifact_args(arguments):
    arguments = require_dict(arguments)
    unexpected = set(arguments) - {"html", "svg"}
    if unexpected:
        raise SecurityError("push_artifact only accepts html or svg.")
    html = arguments.get("html")
    svg = arguments.get("svg")
    has_html = isinstance(html, str) and bool(html.strip())
    has_svg = isinstance(svg, str) and bool(svg.strip())
    if has_html and has_svg:
        raise SecurityError("Send either an HTML Artifact or an SVG Artifact.")
    if has_html:
        html = require_string(html, "html", max_chars=MAX_ARTIFACT_CHARS)
        reject_external_uris(html, "html")
        return {"html": html, "svg": None}
    if has_svg:
        svg = require_string(svg, "svg", max_chars=MAX_ARTIFACT_CHARS)
        reject_external_uris(svg, "svg")
        return {"html": None, "svg": svg}
    raise SecurityError("Pass the finished page as html or svg.")


def reject_external_uris(text, label):
    if FORBIDDEN_URI.search(text):
        raise SecurityError(
            f"{label} must stay on this computer. Remove network and file URLs from the Artifact."
        )


def validate_wifi_args(arguments):
    arguments = require_dict(arguments)
    unexpected = set(arguments) - {"ssid", "password"}
    if unexpected:
        raise SecurityError("set_wifi only accepts ssid and password.")
    ssid = require_string(arguments.get("ssid"), "ssid", max_chars=MAX_SSID_CHARS)
    password = require_string(arguments.get("password"), "password", allow_empty=True, max_chars=MAX_PASSWORD_CHARS)
    if "\n" in ssid or "\r" in ssid or "\n" in password or "\r" in password:
        raise SecurityError("Wi-Fi fields must be a single line.")
    try:
        ssid.encode("utf-8")
        password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SecurityError("Wi-Fi fields must be valid UTF-8.") from exc
    return {"ssid": ssid, "password": password}


def validate_linked_file(path: Path, root: Path):
    """Resolve the link file and keep it inside the project unless FENNSILL_LINK is absolute."""
    try:
        resolved = path.expanduser().resolve(strict=False)
    except OSError as exc:
        raise SecurityError("Linked subscription path is not usable.") from exc
    root_resolved = root.resolve()
    if not str(resolved).startswith(str(root_resolved)):
        # Absolute override from the environment is allowed for tests and installs.
        if not path.is_absolute() and "FENNSILL_LINK" not in __import__("os").environ:
            raise SecurityError("Linked subscription path escapes the project.")
    if resolved.exists() and not resolved.is_file():
        raise SecurityError("Linked subscription path must be a file.")
    if resolved.exists() and resolved.stat().st_size > 4096:
        raise SecurityError("Linked subscription file is too large.")
    return resolved


def read_linked_provider(path: Path, root: Path):
    linked = validate_linked_file(path, root)
    if not linked.is_file():
        return None
    try:
        data = json.loads(linked.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise SecurityError("Linked subscription file is damaged.")
    if not isinstance(data, dict):
        raise SecurityError("Linked subscription file is damaged.")
    # Only the provider claim is used. Email is ignored for tool authorization.
    provider = data.get("provider")
    if not isinstance(provider, str):
        return None
    provider = provider.strip().lower()
    if provider not in ALLOWED_PROVIDERS:
        raise SecurityError(
            "Connect a supported AI subscription first (Claude, ChatGPT, Gemini, Grok, or Cursor)."
        )
    return provider


def redact(text: str, secrets) -> str:
    out = text
    for secret in secrets:
        if not secret or not isinstance(secret, str):
            continue
        if secret in out:
            out = out.replace(secret, "[redacted]")
    return out


def parse_content_length(value: str) -> int:
    if not value or not value.isdigit():
        raise SecurityError("Content-Length must be a positive integer.")
    length = int(value)
    if length <= 0 or length > MAX_MESSAGE_BYTES:
        raise SecurityError("JSON-RPC message is too large.")
    return length


def load_json_object(raw: bytes):
    if len(raw) > MAX_MESSAGE_BYTES:
        raise SecurityError("JSON-RPC message is too large.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecurityError("JSON-RPC message must be UTF-8.") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SecurityError("JSON-RPC message is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise SecurityError("JSON-RPC message must be an object.")
    return data
