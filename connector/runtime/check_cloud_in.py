"""Buyer-side cloud check-in diagnostic.

Run on the PC with Fennsill.exe + the panel:
  python check_cloud_in.py

Or double-click / from PowerShell after installing Fennsill v0.1.11+.
Prints whether the device key can heartbeat against the cloud (no secrets dumped).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_CLOUD = "https://mcp.fennsill.com"


def app_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FennsillApp"
    return Path.home() / "AppData" / "Local" / "FennsillApp"


def load_cloud() -> str:
    env = (os.environ.get("FENNSILL_CLOUD_URL") or os.environ.get("FENNSILL_API_BASE") or "").strip()
    if env:
        return env.rstrip("/")
    for path in (app_dir() / "cloud_url.txt",):
        if path.is_file():
            line = path.read_text(encoding="utf-8").strip().splitlines()[0].strip().rstrip("/")
            if line.lower().endswith("/mcp"):
                line = line[:-4].rstrip("/")
            if line.startswith("http"):
                return line
    return DEFAULT_CLOUD


def load_token() -> str:
    env = (os.environ.get("FENNSILL_DEVICE_TOKEN") or "").strip()
    if env:
        return env[7:].strip() if env.lower().startswith("bearer ") else env
    for name in ("cloud_device_token.txt", "device_token.txt"):
        path = app_dir() / name
        if path.is_file():
            tok = path.read_text(encoding="utf-8").strip()
            if tok.lower().startswith("bearer "):
                tok = tok[7:].strip()
            if tok:
                return tok
    return ""


def call(base: str, path: str, token: str | None = None):
    headers = {
        "User-Agent": "FennsillDesk/1.0 (Windows; check-cloud-in)",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, raw
    except Exception as exc:
        return 0, str(exc)


def main() -> int:
    app = app_dir()
    cloud = load_cloud()
    token = load_token()

    print("Fennsill cloud check-in")
    print(f"  app folder: {app}")
    print(f"  exists:     {app.is_dir()}")
    print(f"  cloud:      {cloud}")
    print(f"  device key: {'YES (' + str(len(token)) + ' chars)' if token else 'MISSING'}")
    if (app / "cloud_url.txt").is_file():
        print("  note:       cloud_url.txt is set (overrides default mcp.fennsill.com)")
    print()

    st, body = call(cloud, "/api/config")
    print(f"GET /api/config -> {st}")
    if st == 200:
        try:
            cfg = json.loads(body)
            print(f"  site says mcp_url = {cfg.get('mcp_url')}")
        except json.JSONDecodeError:
            print(f"  body: {body[:200]}")
    else:
        print(f"  {body[:300]}")
        print("FAIL: cannot reach cloud. Check internet / VPN / firewall.")
        return 1

    if not token:
        print()
        print("FAIL: no device key on this PC.")
        print("  1. Open https://mcp.fennsill.com (same account as Claude)")
        print("  2. Link Device ID from Fennsill.exe")
        print("  3. Mint device key → Copy")
        print("  4. In Fennsill.exe click Paste device key")
        print("  Do NOT paste the account Bearer / MCP Authorization header.")
        return 2

    st, body = call(cloud, "/api/agent/heartbeat", token)
    print(f"GET /api/agent/heartbeat -> {st}")
    print(f"  {body[:400]}")
    print()

    if st == 200:
        print("OK: cloud check-in works. Claude should see the panel online after list_panels.")
        return 0
    if st == 401:
        print("FAIL: device key not accepted (wrong key, or you pasted the account Bearer).")
        print("  Remint device key on https://mcp.fennsill.com → Paste device key in Fennsill.")
        return 3
    if st == 403:
        print("FAIL: cloud refused check-in (403).")
        print("  Usually: access inactive/expired, or panel unlinked after mint.")
        print("  Remint on the same account; if mint also 403, renew access on that account.")
        return 4
    print("FAIL: unexpected response. Send this whole output to support.")
    return 5


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
