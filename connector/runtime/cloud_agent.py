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
_SINGLETON_MUTEX: int | None = None


def _local_app() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FennsillApp"
    return ROOT


def acquire_singleton() -> bool:
    """Only one cloud agent may run — duplicates steal jobs and fight over USB.

    Windows: named mutex (works across python.exe / Store shim / py launcher).
    File lock alone failed when Desk left an orphan agent and started another.
    """
    global _SINGLETON_FD, _SINGLETON_MUTEX
    path = _local_app() / "cloud_agent.lock"
    path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        # Local\ = per-session; avoids needing SeCreateGlobalPrivilege.
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, "Local\\FennsillCloudAgent.v1")
        if not handle:
            print("cloud agent mutex failed — exiting", flush=True)
            return False
        # ERROR_ALREADY_EXISTS = 183: another live agent owns the mutex.
        if kernel32.GetLastError() == 183:
            kernel32.CloseHandle(handle)
            print("cloud agent already running — exiting duplicate", flush=True)
            return False
        _SINGLETON_MUTEX = handle

        def _release_mutex() -> None:
            global _SINGLETON_MUTEX
            h = _SINGLETON_MUTEX
            _SINGLETON_MUTEX = None
            if h:
                try:
                    kernel32.CloseHandle(h)
                except Exception:
                    pass

        atexit.register(_release_mutex)

    fd = os.open(str(path), os.O_CREAT | os.O_RDWR)
    try:
        # Ensure length >= 1 before msvcrt.locking (empty file → lock fails on Win).
        try:
            if os.fstat(fd).st_size < 1:
                os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
        except OSError:
            pass
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        # Mutex already held above on Windows; file-lock failure still means duplicate.
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


def _parse_http_result(status: int, text: str):
    text = text or ""
    low = text.lower()
    if "error code: 1010" in low or "error code 1010" in low or "error 1010" in low:
        return 1010, {
            "error": "cloudflare_1010",
            "message": "Cloudflare blocked this client signature.",
        }
    if status == 204 or not text.strip():
        return status, None
    try:
        return status, json.loads(text)
    except json.JSONDecodeError:
        return status, {"error": text[:500]}


def _call_curl(method: str, path: str, token: str, body: dict | None = None):
    """Windows curl.exe uses Schannel — avoids Cloudflare 1010 on Python urllib TLS."""
    import subprocess
    import tempfile

    url = cloud_base() + path
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    args = [
        "curl.exe",
        "-sS",
        "-X",
        method.upper(),
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        f"User-Agent: {ua}",
        "-H",
        "Accept: application/json, text/plain, */*",
        "-H",
        "Accept-Language: en-US,en;q=0.9",
        "--connect-timeout",
        "20",
        "--max-time",
        "45",
        "-w",
        "\n__HTTP_STATUS__:%{http_code}",
        url,
    ]
    tmp_path = None
    if body is not None:
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="fenn_body_", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(body))
            args[1:1] = ["-H", "Content-Type: application/json", "--data-binary", f"@{tmp_path}"]
        except OSError as exc:
            return 0, {"error": f"curl_body_temp: {exc}"}
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except FileNotFoundError:
        return None  # caller falls back
    except Exception as exc:
        return 0, {"error": f"curl_failed: {exc}"}
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    out = proc.stdout or ""
    err = (proc.stderr or "").strip()
    if "__HTTP_STATUS__:" not in out:
        return 0, {"error": (err or out or "curl empty")[:500]}
    body_text, _, status_part = out.rpartition("__HTTP_STATUS__:")
    body_text = body_text.rstrip("\n")
    try:
        status = int(status_part.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0, {"error": (out or err)[:500]}
    if status == 0 and err:
        return 0, {"error": err[:500]}
    return _parse_http_result(status, body_text)


def _call_urllib(method: str, path: str, token: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(cloud_base() + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    req.add_header("Accept", "application/json, text/plain, */*")
    req.add_header("Accept-Language", "en-US,en;q=0.9")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return _parse_http_result(resp.status, raw)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        return _parse_http_result(exc.code, text)
    except Exception as exc:
        return 0, {"error": str(exc)}


def call(method: str, path: str, token: str, body: dict | None = None):
    # Windows: curl.exe (Schannel) first — Python urllib TLS often gets CF 1010.
    if sys.platform == "win32":
        try:
            result = _call_curl(method, path, token, body)
            if result is not None:
                return result
        except Exception as exc:
            # Never crash the agent loop on transport bugs.
            return 0, {"error": f"curl_exception: {exc}"}
    return _call_urllib(method, path, token, body)


def write_status(payload: dict) -> None:
    path = _local_app() / "cloud_agent_status.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def append_push_log(line: str) -> None:
    path = _local_app() / "cloud_push.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{int(time.time())} {line}\n")
    except OSError:
        pass


def set_usb_pause(active: bool) -> None:
    """Tell Desk/live workers to stop opening COM while a cloud push runs."""
    path = _local_app() / "pause_usb.poll"
    try:
        if active:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{os.getpid()}\n{int(time.time()) + 180}\n", encoding="utf-8")
        elif path.is_file():
            path.unlink()
    except OSError:
        pass


def run_job(job: dict) -> tuple[bool, str]:
    job_type = (job.get("job_type") or job.get("type") or "push").strip().lower()
    if job_type not in ("push", "artifact", ""):
        return False, f"unsupported job_type={job_type}"
    html = job.get("html")
    svg = job.get("svg")
    title = job.get("title") or ""
    last_err = "panel push failed"
    # Log before importing intake/Playwright — that import can hang and used to
    # leave claimed jobs with zero local evidence.
    append_push_log(f"run_job_start title={title!r} has_html={bool(html)} has_svg={bool(svg)}")
    # Win the COM lock even while Desk status polls / Factory was just closed.
    os.environ["FENNSILL_SERIAL_LOCK_TIMEOUT"] = "90"
    set_usb_pause(True)
    time.sleep(1.5)  # let in-flight Desk READY polls finish
    try:
        # Fail fast with a clear error if the Desk payload omitted USB helpers.
        try:
            import push_page  # noqa: F401
        except ImportError as exc:
            msg = (
                f"missing_usb_module: {exc}. "
                "Reinstall/update Fennsill.exe (payload must include connector/push_page.py)."
            )
            append_push_log(msg)
            return False, msg
        from intake import intake_page

        append_push_log("intake_imported")
        for attempt in range(10):
            try:
                append_push_log(f"attempt={attempt + 1} title={title!r}")
                result = intake_page(
                    html=html, svg=svg, title=title, source="cloud", push=True
                )
                if result.get("pushed"):
                    append_push_log(f"pushed_ok page_id={result.get('page_id')}")
                    return True, ""
                last_err = (
                    result.get("panel_error")
                    or result.get("note")
                    or "panel push failed"
                )
                append_push_log(f"push_fail {last_err}")
                busy = "busy" in last_err.lower() or "lock" in last_err.lower()
                if busy and attempt < 9:
                    time.sleep(3 + attempt)
                    continue
                return False, last_err
            except Exception as exc:
                last_err = str(exc)
                append_push_log(f"exception {last_err}")
                if attempt < 9:
                    time.sleep(3 + attempt)
                    continue
                return False, last_err
        return False, last_err
    finally:
        set_usb_pause(False)


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
        append_push_log(f"claimed job_id={job_id} title={job.get('title')!r}")
        write_status(
            {
                "ok": True,
                "cloud": cloud_base(),
                "heartbeat_status": 200,
                "job_in_progress": job_id,
                "job_title": job.get("title") or "",
                "ts": int(time.time()),
            }
        )
        # Keep "online" true while Playwright/USB work runs (can take >60s).
        call("GET", "/api/agent/heartbeat", token)
        try:
            ok, err = run_job(job)
        except Exception as exc:
            ok, err = False, f"run_job_crash: {exc}"
            append_push_log(err)
        call("GET", "/api/agent/heartbeat", token)
        done_st, done = call(
            "POST",
            f"/api/agent/jobs/{job_id}/complete",
            token,
            {"ok": ok, "error": err},
        )
        print(f"complete {done_st} ok={ok} {err or done}", flush=True)
        append_push_log(
            f"complete job_id={job_id} ok={ok} http={done_st} err={err or ''}"
        )
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
            import traceback

            msg = f"{exc}\n{traceback.format_exc()}"
            write_status({"ok": False, "error": "agent_crash", "message": msg[:1500]})
            print(f"cloud agent crash (restarting): {exc}", flush=True)
            time.sleep(3)
