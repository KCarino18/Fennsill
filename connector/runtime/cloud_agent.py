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

# Windows service consoles are often cp1252 — fancy arrows/dashes crash prints
# and leave Desk stuck on "Cloud: agent_crash".
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

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
            print("cloud agent mutex failed - exiting", flush=True)
            return False
        # ERROR_ALREADY_EXISTS = 183: another live agent owns the mutex.
        if kernel32.GetLastError() == 183:
            kernel32.CloseHandle(handle)
            print("cloud agent already running - exiting duplicate", flush=True)
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
        print("cloud agent already running - exiting duplicate", flush=True)
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


def ensure_playwright_browsers() -> None:
    """Make sure Chromium exists under connector/browsers (Setup can miss this)."""
    import subprocess

    browsers = ROOT / "connector" / "browsers"
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    has_exe = False
    if browsers.is_dir():
        for name in ("chrome-headless-shell.exe", "chrome.exe"):
            if any(browsers.rglob(name)):
                has_exe = True
                break
    if has_exe:
        return
    print(f"playwright browsers missing under {browsers} — installing…", flush=True)
    browsers.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    for browser in ("chromium", "chromium-headless-shell"):
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", browser],
                env=env,
                timeout=900,
                check=False,
            )
        except Exception as exc:
            print(f"playwright install {browser} failed: {exc}", flush=True)


def _queue_status_fields() -> dict:
    try:
        from display_queue import STATUS_SHOWING, list_items

        items = list_items()
        showing = next((i for i in items if i.get("status") == STATUS_SHOWING), None)
        return {
            "queue_len": len(items),
            "screen_held_until": showing.get("held_until") if showing else None,
            "holding_job_id": (showing or {}).get("job_id") or "",
            "holding_title": (showing or {}).get("title") or "",
        }
    except Exception:
        return {}


def complete_cloud_job(token: str, job_id: str, *, ok: bool, error: str = "") -> None:
    if not job_id:
        return
    done_st, done = call(
        "POST",
        f"/api/agent/jobs/{job_id}/complete",
        token,
        {"ok": ok, "error": error or ""},
    )
    print(f"complete {done_st} ok={ok} {error or done}", flush=True)
    append_push_log(
        f"complete job_id={job_id} ok={ok} http={done_st} err={error or ''}"
    )


def buffer_job_to_queue(job: dict) -> tuple[bool, str]:
    """Render a claimed cloud job into the local Desk/Agent queue (no USB yet)."""
    job_type = (job.get("job_type") or job.get("type") or "push").strip().lower()
    if job_type not in ("push", "artifact", ""):
        return False, f"unsupported job_type={job_type}"
    html = job.get("html")
    svg = job.get("svg")
    title = job.get("title") or ""
    job_id = str(job.get("job_id") or "")
    hold_sec = job.get("hold_sec", 0)
    append_push_log(
        f"buffer_start job_id={job_id} title={title!r} hold_sec={hold_sec!r}"
    )
    try:
        from display_queue import append_item, clamp_hold_sec, has_job
        from intake import render_frame

        if job_id and has_job(job_id):
            append_push_log(f"buffer_skip_duplicate job_id={job_id}")
            return True, ""
        args = {}
        if html:
            args["html"] = html
        if svg:
            args["svg"] = svg
        frame = render_frame(args)
        item = append_item(
            job_id=job_id,
            title=title,
            hold_sec=clamp_hold_sec(hold_sec),
            frame=frame,
        )
        append_push_log(f"buffered id={item['id']} job_id={job_id}")
        return True, ""
    except Exception as exc:
        append_push_log(f"buffer_fail {exc}")
        return False, str(exc)


def push_queue_item(item: dict) -> tuple[bool, str]:
    """USB-push a queued frame to the panel."""
    title = item.get("title") or ""
    last_err = "panel push failed"
    append_push_log(f"push_queue_start id={item.get('id')} title={title!r}")
    os.environ["FENNSILL_SERIAL_LOCK_TIMEOUT"] = "90"
    set_usb_pause(True)
    time.sleep(1.5)
    try:
        try:
            import push_page  # noqa: F401
        except ImportError as exc:
            msg = (
                f"missing_usb_module: {exc}. "
                "Reinstall/update Fennsill.exe (payload must include connector/push_page.py)."
            )
            append_push_log(msg)
            return False, msg
        from display_queue import load_frame_bytes
        from intake import push_frame_to_panel
        from security import SecurityError

        frame = load_frame_bytes(item)
        for attempt in range(10):
            try:
                append_push_log(f"attempt={attempt + 1} title={title!r}")
                push_frame_to_panel(frame)
                append_push_log(f"pushed_ok id={item.get('id')}")
                return True, ""
            except (SecurityError, TimeoutError, OSError, ValueError) as exc:
                last_err = str(exc)
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


def run_job(job: dict) -> tuple[bool, str]:
    """Legacy one-shot path: buffer then push that item immediately."""
    job_type = (job.get("job_type") or job.get("type") or "push").strip().lower()
    if job_type not in ("push", "artifact", ""):
        return False, f"unsupported job_type={job_type}"
    html = job.get("html")
    svg = job.get("svg")
    title = job.get("title") or ""
    job_id = str(job.get("job_id") or "")
    hold_sec = job.get("hold_sec", 0)
    try:
        from display_queue import append_item, clamp_hold_sec
        from intake import render_frame

        args = {}
        if html:
            args["html"] = html
        if svg:
            args["svg"] = svg
        frame = render_frame(args)
        item = append_item(
            job_id=job_id,
            title=title,
            hold_sec=clamp_hold_sec(hold_sec),
            frame=frame,
        )
    except Exception as exc:
        return False, str(exc)
    return push_queue_item(item)


def drain_cloud_jobs(token: str) -> int:
    """Claim cloud jobs into the local queue until empty or error. Returns count."""
    from display_queue import has_job

    claimed = 0
    for _ in range(20):
        st, job = call("GET", "/api/agent/jobs/next", token)
        if st in (403, 429, 1010):
            return -st
        if st == 204 or job is None:
            break
        if st != 200:
            print(f"jobs/next {st} {job}", flush=True)
            break
        job_id = str(job.get("job_id") or "")
        job_type = (job.get("job_type") or "push").strip().lower()
        print(f"claimed job {job_id}", flush=True)
        append_push_log(f"claimed job_id={job_id} title={job.get('title')!r}")
        if job_type not in ("push", "artifact", ""):
            complete_cloud_job(
                token, job_id, ok=False, error=f"unsupported job_type={job_type}"
            )
            continue
        if job_id and has_job(job_id):
            # Already in the local queue — keep cloud status claimed until shown.
            append_push_log(f"claim_already_queued job_id={job_id}")
            continue
        call("GET", "/api/agent/heartbeat", token)
        ok, err = buffer_job_to_queue(job)
        if not ok:
            complete_cloud_job(token, job_id, ok=False, error=err)
            continue
        claimed += 1
    return claimed


def advance_local_queue(token: str) -> None:
    """Show the queue head, hold, then advance. Completes cloud job on panel show."""
    from display_queue import (
        STATUS_SHOWING,
        STATUS_WAITING,
        finish_head,
        head_item,
        mark_showing,
    )

    item = head_item()
    if not item:
        return
    now = time.time()
    held_until = item.get("held_until")
    if item.get("status") == STATUS_SHOWING and held_until is not None:
        try:
            until = float(held_until)
        except (TypeError, ValueError):
            until = 0.0
        if until > now:
            return
        # Hold finished — drop head and let the next item play next loop.
        finish_head(item["id"])
        append_push_log(f"hold_done id={item.get('id')}")
        return

    if item.get("status") != STATUS_WAITING and item.get("status") != STATUS_SHOWING:
        item["status"] = STATUS_WAITING

    if item.get("status") == STATUS_SHOWING:
        # held_until missing or past — advance
        finish_head(item["id"])
        return

    # Waiting head → push to panel.
    write_status(
        {
            "ok": True,
            "cloud": cloud_base(),
            "heartbeat_status": 200,
            "job_in_progress": item.get("job_id") or item.get("id"),
            "job_title": item.get("title") or "",
            "ts": int(time.time()),
            **_queue_status_fields(),
        }
    )
    call("GET", "/api/agent/heartbeat", token)
    ok, err = push_queue_item(item)
    call("GET", "/api/agent/heartbeat", token)
    job_id = str(item.get("job_id") or "")
    if not ok:
        complete_cloud_job(token, job_id, ok=False, error=err)
        finish_head(item["id"])
        write_status(
            {
                "ok": True,
                "cloud": cloud_base(),
                "heartbeat_status": 200,
                "last_job_id": job_id,
                "last_job_ok": False,
                "last_job_error": err or "",
                "ts": int(time.time()),
                **_queue_status_fields(),
            }
        )
        return

    complete_cloud_job(token, job_id, ok=True, error="")
    hold_sec = int(item.get("hold_sec") or 0)
    if hold_sec > 0:
        mark_showing(item["id"], held_until=now + hold_sec)
        append_push_log(f"holding id={item.get('id')} sec={hold_sec}")
    else:
        finish_head(item["id"])
    write_status(
        {
            "ok": True,
            "cloud": cloud_base(),
            "heartbeat_status": 200,
            "last_job_id": job_id,
            "last_job_ok": True,
            "last_job_error": "",
            "ts": int(time.time()),
            **_queue_status_fields(),
        }
    )


def main() -> int:
    token = load_device_token()
    if not token:
        msg = (
            "No cloud device key. On the account site: Link panel -> Mint device key -> "
            "paste that key into FennSill Desk (Paste device key). The Agent service delivers pushes."
        )
        print(msg, flush=True)
        write_status({"ok": False, "error": "missing_device_token", "message": msg})
        # Stay alive so Desk can see the status file; retry when token appears.
        while not load_device_token():
            time.sleep(5)
        token = load_device_token()

    print(f"cloud agent -> {cloud_base()} (device key loaded)", flush=True)
    ensure_playwright_browsers()
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
        status_payload = {
            "ok": st == 200,
            "cloud": cloud_base(),
            "heartbeat_status": st,
            "heartbeat": hb,
            "cloudflare_block": cf_block,
            "ts": int(time.time()),
            **_queue_status_fields(),
        }
        write_status(status_payload)
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

        drained = drain_cloud_jobs(token)
        if drained < 0:
            code = -drained
            fail_streak += 1
            print(f"jobs/next {code}", flush=True)
            time.sleep(min(180, 15 * fail_streak))
            continue

        advance_local_queue(token)

        from display_queue import STATUS_SHOWING, head_item

        head = head_item()
        if head and head.get("status") == STATUS_SHOWING:
            # Heartbeat during hold; wake often enough for Desk removes / hold end.
            call("GET", "/api/agent/heartbeat", token)
            write_status(
                {
                    "ok": True,
                    "cloud": cloud_base(),
                    "heartbeat_status": 200,
                    "heartbeat": hb,
                    "ts": int(time.time()),
                    **_queue_status_fields(),
                }
            )
            time.sleep(1.0)
            continue

        if drained == 0 and not head:
            time.sleep(idle_sleep)
        else:
            time.sleep(0.5)


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
