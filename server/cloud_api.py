"""Artiphact cloud HTTP API for the local agent + read-only updates.

Agent (device bearer):
  GET  /api/agent/jobs/next   — claim next job for THIS device only
  POST /api/agent/jobs/{id}/complete — ack success/failure for THIS device only
  GET  /api/updates/{channel} — read firmware/app manifest (no upload)

Account session (cookie / Bearer user session) can mint device tokens and list devices.
Buyers never write manifests or other tenants' data.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import tenant_store as store  # noqa: E402

HOST = __import__("os").environ.get("ARTIPHACT_CLOUD_HOST", "127.0.0.1")
PORT = int(__import__("os").environ.get("ARTIPHACT_CLOUD_PORT", "8090"))


def bearer(headers) -> str | None:
    auth = headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "ArtiphactCloud/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self._json(200, {"ok": True, "service": "artiphact-cloud"})
        if path.startswith("/api/updates/"):
            channel = path.split("/api/updates/", 1)[1].strip("/") or "stable"
            if "/" in channel or ".." in channel:
                return self._json(400, {"error": "Bad channel."})
            manifest = store.get_update_manifest(channel)
            if not manifest:
                return self._json(404, {"error": "No update published for this channel."})
            return self._json(200, manifest)
        if path == "/api/agent/jobs/next":
            auth = store.auth_device_token(bearer(self.headers))
            if not auth:
                return self._json(401, {"error": "Device token required."})
            job = store.claim_next_job(auth)
            if not job:
                return self._json(204, None)
            return self._json(200, job)
        if path == "/api/me/devices":
            user = store.user_from_session(bearer(self.headers) or self._cookie())
            if not user:
                return self._json(401, {"error": "Sign in first."})
            return self._json(200, {"devices": store.list_devices_for_user(int(user["id"]))})
        return self._json(404, {"error": "Not found."})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()
        if body is None:
            return
        if path.startswith("/api/agent/jobs/") and path.endswith("/complete"):
            job_id = path[len("/api/agent/jobs/") : -len("/complete")]
            if not job_id or "/" in job_id or ".." in job_id:
                return self._json(400, {"error": "Bad job id."})
            auth = store.auth_device_token(bearer(self.headers))
            if not auth:
                return self._json(401, {"error": "Device token required."})
            try:
                ok = store.complete_job(
                    auth,
                    job_id,
                    ok=bool(body.get("ok", True)),
                    error=str(body.get("error") or ""),
                )
            except PermissionError as exc:
                return self._json(403, {"error": str(exc)})
            if not ok:
                return self._json(404, {"error": "Job not found."})
            return self._json(200, {"ok": True})
        if path == "/api/device/token":
            user = store.user_from_session(bearer(self.headers) or self._cookie())
            if not user:
                return self._json(401, {"error": "Sign in first."})
            device_id = str(body.get("device_id") or "").strip()
            if not device_id:
                return self._json(400, {"error": "device_id required."})
            try:
                token = store.issue_device_token(int(user["id"]), device_id)
            except PermissionError as exc:
                return self._json(403, {"error": str(exc)})
            return self._json(200, {"device_id": device_id, "token": token})
        return self._json(404, {"error": "Not found."})

    def _cookie(self) -> str | None:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            part = part.strip()
            if part.startswith("artiphact="):
                return part.split("=", 1)[1].strip() or None
        return None

    def _body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 1_048_576:
            self._json(413, {"error": "Body too large."})
            return None
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "Send JSON."})
            return None
        if not isinstance(data, dict):
            self._json(400, {"error": "Send a JSON object."})
            return None
        # Never accept Wi-Fi secrets on the cloud API.
        banned = {"ssid", "wifi", "wifi_ssid", "wifi_password", "psk", "passphrase"}
        if any(k.lower() in banned for k in data):
            self._json(400, {"error": "Wi-Fi credentials stay on the panel."})
            return None
        return data

    def _json(self, code: int, payload):
        if code == 204:
            self.send_response(204)
            self.end_headers()
            return
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    store.init_db()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ARTIPHACT_CLOUD http://{HOST}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
