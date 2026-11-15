"""Local agent stub: heartbeat, claim jobs, print them, complete.

Usage:
  set ARTIPHACT_CLOUD_URL=http://127.0.0.1:8080
  set ARTIPHACT_DEVICE_TOKEN=<token from POST /api/device/token>
  python scripts/agent_stub.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("ARTIPHACT_CLOUD_URL", "http://127.0.0.1:8080").rstrip("/")
TOKEN = os.environ.get("ARTIPHACT_DEVICE_TOKEN", "")


def call(method: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            payload = {"error": raw.decode("utf-8", errors="replace")}
        return exc.code, payload


def main():
    if not TOKEN:
        print("Set ARTIPHACT_DEVICE_TOKEN", file=sys.stderr)
        sys.exit(1)
    print(f"agent stub -> {BASE}", flush=True)
    while True:
        status, payload = call("GET", "/api/agent/heartbeat")
        print("heartbeat", status, payload, flush=True)
        status, job = call("GET", "/api/agent/jobs/next")
        if status == 204:
            time.sleep(2)
            continue
        if status != 200:
            print("jobs/next", status, job, flush=True)
            time.sleep(2)
            continue
        print("claimed", json.dumps(job, indent=2), flush=True)
        job_id = job["job_id"]
        # Real Artiphact.exe would call intake_page(..., push=True) here.
        st, done = call("POST", f"/api/agent/jobs/{job_id}/complete", {"ok": True})
        print("complete", st, done, flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
