"""Artifact validation for cloud push — shared with local connector."""

from __future__ import annotations

import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1] / "connector" / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from artifact_security import (  # noqa: E402
    DEVICE_ID_RE,
    FORBIDDEN_URI,
    MAX_ARTIFACT_CHARS,
    SecurityError,
    WIFI_KEYS,
    XMLNS_ATTR,
    body_has_wifi_keys,
    reject_external_uris,
    require_string,
    validate_artifact_args as _validate_artifact_args,
    validate_chart_args,
    validate_device_id,
)

__all__ = [
    "DEVICE_ID_RE",
    "FORBIDDEN_URI",
    "MAX_ARTIFACT_CHARS",
    "SecurityError",
    "WIFI_KEYS",
    "XMLNS_ATTR",
    "body_has_wifi_keys",
    "reject_external_uris",
    "require_string",
    "validate_artifact_args",
    "validate_chart_args",
    "validate_device_id",
]


def validate_artifact_args(*, html=None, svg=None, device_id=None):
    """Cloud push_artifact always requires device_id."""
    return _validate_artifact_args(
        html=html,
        svg=svg,
        device_id=device_id,
        require_device_id=True,
    )
