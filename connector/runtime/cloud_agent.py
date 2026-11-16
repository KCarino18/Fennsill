"""Local cloud agent: heartbeat + claim push jobs + USB to the panel.

ChatGPT/Claude talk to https://mcp.fennsill.com/mcp. This process (started by
Fennsill.exe) is what makes the panel “checked in” and delivers queued pages.
"""

from __future__ import annotations

import atexit
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
_SINGLETON_FD: int | None = None


def _local_app() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FennsillApp"
    return ROOT


def acquire_singleton() -> bool:
    """Only one cloud agent may run — duplicates steal jobs and fight over USB."""
    global _SINGLETON_FD
    path = _local_app() / "cloud_agent.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        print("cloud agent already running — exiting duplicate", flush=True)
        return False
    try:
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
    except OSError:
        pass
    _SINGLETON_FD = fd

    def _release() -> None:
        global _SINGLETON_FD
        if _SINGLETON_FD is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(_SINGLETON_FD, 0, os.SEEK_SET)
                msvcrt.locking(_SINGLETON_FD, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(_SINGLETON_FD, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(_SINGLETON_FD)
        except OSError:
            pass
        _SINGLETON_FD = None

    atexit.register(_release)
    return True


def cloud_base() -> str:
    env = (
        os.environ.get("FENNSILL_CLOUD_URL")
        or os.environ.get("FENNSILL_API_BASE")
        or ""
    ).strip()
    if env:
        return env.rstrip("/")
    # Desk / buyer override: one-line URL file (no /mcp suffix needed).
    for path in (_local_app() / "cloud_url.txt", ROOT / "cloud_url.txt"):
        try:
            if path.is_file():
                line = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
                if line.lower().startswith("bearer "):
                    continue
                line = line.rstrip("/")
                if line.lower().endswith("/mcp"):
                    line = line[:-4].rstrip("/")
                if line.startswith("http://") or line.startswith("https://"):
                    return line
        except OSError:
            continue
    return DEFAULT_CLOUD


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
    last_err = "panel push failed"
    # USB lock contention with Desk READY polls — retry before failing the job.
    for attempt in range(6):
        try:
            result = intake_page(html=html, svg=svg, title=title, source="cloud", push=True)
            if result.get("pushed"):
                return True, ""
            last_err = (
                result.get("panel_error")
                or result.get("note")
                or "panel push failed"
            )
            busy = "busy" in last_err.lower() or "lock" in last_err.lower()
            if busy and attempt < 5:
                time.sleep(2 + attempt)
                continue
            return False, last_err
        except Exception as exc:
            last_err = str(exc)
            if attempt < 5:
                time.sleep(2 + attempt)
                continue
            return False, last_err
    return False, last_err


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
    # Idle poll was ~2–3 req/s and Cloudflare starts returning 403 after a burst,
    # which leaves MCP jobs queued while list_panels still looks "online".
    idle_sleep = 5.0
    while True:
        token = load_device_token() or token
        st, hb = call("GET", "/api/agent/heartbeat", token)
        err_text = ""
        if isinstance(hb, dict):
            err_text = str(hb.get("error") or hb.get("message") or "")
        elif isinstance(hb, str):
            err_text = hb
        cf_block = st in (403, 429, 1010) and (
            "cloudflare" in err_text.lower()
            or "<html" in err_text.lower()
            or "attention required" in err_text.lower()
            or "error code" in err_text.lower()
        )
        write_status(
            {
                "ok": st == 200,
                "cloud": cloud_base(),
                "heartbeat_status": st,
                "heartbeat": hb,
                "cloudflare_block": cf_block,
                "ts": int(time.time()),
            }
        )
        if st != 200:
            fail_streak += 1
            print(f"heartbeat {st} {hb}", flush=True)
            # Back off hard on 403/429 — hammering makes CF keep blocking.
            if st in (403, 429, 1010) or cf_block:
                time.sleep(min(180, 15 * fail_streak))
            else:
                time.sleep(min(45, 3 + fail_streak))
            continue
        fail_streak = 0

        st, job = call("GET", "/api/agent/jobs/next", token)
        if st in (403, 429, 1010):
            fail_streak += 1
            print(f"jobs/next {st} {job}", flush=True)
            time.sleep(min(180, 15 * fail_streak))
            continue
        if st == 204 or job is None:
            time.sleep(idle_sleep)
            continue
        if st != 200:
            print(f"jobs/next {st} {job}", flush=True)
            time.sleep(5)
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
        write_status(
            {
                "ok": True,
                "cloud": cloud_base(),
                "heartbeat_status": 200,
                "last_job_id": job_id,
                "last_job_ok": ok,
                "last_job_error": err or "",
                "last_job_complete_status": done_st,
                "ts": int(time.time()),
            }
        )
        time.sleep(1.0)


if __name__ == "__main__":
    if not acquire_singleton():
        raise SystemExit(0)
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
