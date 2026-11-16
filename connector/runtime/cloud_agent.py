"""Local cloud agent: heartbeat + claim push jobs + USB to the panel.

ChatGPT/Claude talk to https://mcp.fennsill.com/mcp. This process (started by
Fennsill.exe) is what makes the panel “checked in” and delivers queued pages.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "connector"))
sys.path.insert(0, str(ROOT / "connector" / "runtime"))
sys.path.insert(0, str(ROOT / "templates"))

DEFAULT_CLOUD = "https://mcp.fennsill.com"
TOKEN_NAMES = ("cloud_device_token.txt", "device_token.txt")


def _local_app() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FennsillApp"
    return ROOT


def cloud_base() -> str:
    return (
        os.environ.get("FENNSILL_CLOUD_URL")
        or os.environ.get("FENNSILL_API_BASE")
        or DEFAULT_CLOUD
    ).rstrip("/")


def token_paths() -> list[Path]:
    app = _local_app()
    paths = [app / name for name in TOKEN_NAMES] + [ROOT / name for name in TOKEN_NAMES]
    env_file = os.environ.get("FENNSILL_DEVICE_TOKEN_FILE")
    if env_file:
        paths.insert(0, Path(env_file))
    return paths


def load_device_token() -> str:
    env = (os.environ.get("FENNSILL_DEVICE_TOKEN") or "").strip()
    if env:
        return env
    for path in token_paths():
        if path is None:
            continue
        try:
            if path.is_file():
                tok = path.read_text(encoding="utf-8").strip()
                # Allow "Bearer xxx" paste
                if tok.lower().startswith("bearer "):
                    tok = tok[7:].strip()
                if tok:
                    return tok
        except OSError:
            continue
    return ""


def save_device_token(token: str) -> Path:
    tok = token.strip()
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    path = _local_app() / "cloud_device_token.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tok + "\n", encoding="utf-8")
    return path


def call(method: str, path: str, token: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(cloud_base() + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    # Cloudflare rejects bare Python-urllib (error 1010). Look like a normal client.
    req.add_header(
        "User-Agent",
        "FennsillDesk/1.0 (Windows; cloud-agent; +https://mcp.fennsill.com)",
    )
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read()
            if resp.status == 204 or not raw:
                return resp.status, None
            return resp.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {"error": str(exc)}
        except json.JSONDecodeError:
            payload = {"error": raw.decode("utf-8", errors="replace")}
        return exc.code, payload
    except Exception as exc:
        return 0, {"error": str(exc)}


def run_job(job: dict) -> tuple[bool, str]:
    from intake import intake_page

    job_type = (job.get("job_type") or job.get("type") or "push").strip().lower()
    if job_type not in ("push", "artifact", ""):
        return False, f"unsupported job_type={job_type}"
    html = job.get("html")
    svg = job.get("svg")
    title = job.get("title") or ""
    try:
        intake_page(html=html, svg=svg, title=title, source="cloud", push=True)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def write_status(payload: dict) -> None:
    path = _local_app() / "cloud_agent_status.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    token = load_device_token()
    if not token:
        msg = (
            "No cloud device key. On the account site: Link panel → Mint device key → "
            "paste that key into Fennsill (Paste device key), keep Fennsill open."
        )
        print(msg, flush=True)
        write_status({"ok": False, "error": "missing_device_token", "message": msg})
        # Stay alive so Desk can see the status file; retry when token appears.
        while not load_device_token():
            time.sleep(5)
        token = load_device_token()

    print(f"cloud agent → {cloud_base()} (device key loaded)", flush=True)
    fail_streak = 0
    while True:
        token = load_device_token() or token
        st, hb = call("GET", "/api/agent/heartbeat", token)
        write_status(
            {
                "ok": st == 200,
                "cloud": cloud_base(),
                "heartbeat_status": st,
                "heartbeat": hb,
                "ts": int(time.time()),
            }
        )
        if st != 200:
            fail_streak += 1
            print(f"heartbeat {st} {hb}", flush=True)
            time.sleep(min(30, 2 + fail_streak))
            continue
        fail_streak = 0

        # Heartbeat again right before claim so list_panels stays online during long renders.
        call("GET", "/api/agent/heartbeat", token)

        st, job = call("GET", "/api/agent/jobs/next", token)
        if st == 204 or job is None:
            time.sleep(1)
            continue
        if st != 200:
            print(f"jobs/next {st} {job}", flush=True)
            time.sleep(2)
            continue

        job_id = str(job.get("job_id") or "")
        print(f"claimed job {job_id}", flush=True)
        # Keep "online" true while Playwright/USB work runs (can take >60s).
        call("GET", "/api/agent/heartbeat", token)
        ok, err = run_job(job)
        call("GET", "/api/agent/heartbeat", token)
        done_st, done = call(
            "POST",
            f"/api/agent/jobs/{job_id}/complete",
            token,
            {"ok": ok, "error": err},
        )
        print(f"complete {done_st} ok={ok} {err or done}", flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    # Never exit on transient errors — offline drops when this process dies.
    while True:
        try:
            raise SystemExit(main())
        except KeyboardInterrupt:
            raise SystemExit(0)
        except SystemExit:
            raise
        except Exception as exc:
            write_status({"ok": False, "error": "agent_crash", "message": str(exc)})
            print(f"cloud agent crash (restarting): {exc}", flush=True)
            time.sleep(3)
