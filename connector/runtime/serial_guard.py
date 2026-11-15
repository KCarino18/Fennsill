"""Exclusive access to the panel USB serial port.

Fennsill.exe polls READY, live/rotate workers push frames, and MCP clients
also open COM. Without a lock, a busy port looks like “no panel” and long
wait_ready loops can hang ChatGPT for minutes.

On Windows, the lock lives under %LOCALAPPDATA%\\Fennsill so ChatGPT’s MCP
process can write it (Desktop project folders are sometimes denied). Uses
msvcrt byte-range locking instead of O_EXCL create/delete, which races and
returns Access Denied on Windows.
"""

from __future__ import annotations

import atexit
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
def _default_lock_path() -> Path:
    env = os.environ.get("FENNSILL_SERIAL_LOCK")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Fennsill" / "serial.lock"
    return ROOT / "connector" / ".serial.lock"


def get_lock_path() -> Path:
    """Resolve every time so long-lived workers pick up path changes."""
    return _default_lock_path()


# Back-compat alias (may be stale in already-running processes).
LOCK_PATH = _default_lock_path()


class SerialBusy(TimeoutError):
    """Raised when another Fennsill process holds the panel serial lock."""


class SerialGuard:
    """Context manager: exclusive short-lived ownership of panel serial work."""

    def __init__(self, timeout: float = 3.0, *, stale_after: float = 120.0):
        self.timeout = max(0.05, float(timeout))
        self.stale_after = max(5.0, float(stale_after))
        self._fd: int | None = None
        self._path: Path = get_lock_path()

    def acquire(self) -> None:
        self._path = get_lock_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout
        last_err = ""
        while True:
            try:
                fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR)
            except OSError as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                # #region agent log
                try:
                    from debug_ndjson import dlog

                    dlog(
                        "H",
                        "serial_guard.py:acquire",
                        "lock_open_fail",
                        {"lock_path": str(self._path), "err": last_err},
                    )
                except Exception:
                    pass
                # #endregion
                if time.time() >= deadline:
                    raise SerialBusy(
                        f"Panel serial lock unavailable ({last_err}). "
                        "Retry in a few seconds."
                    ) from exc
                time.sleep(0.05)
                continue

            locked = False
            try:
                if sys.platform == "win32":
                    import msvcrt

                    # Non-blocking lock of 1 byte; retry until timeout.
                    try:
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                        locked = True
                    except OSError as exc:
                        last_err = f"{type(exc).__name__}: {exc}"
                        os.close(fd)
                        if time.time() >= deadline:
                            # #region agent log
                            try:
                                from debug_ndjson import dlog

                                dlog(
                                    "H",
                                    "serial_guard.py:acquire",
                                    "lock_timeout",
                                    {
                                        "lock_path": str(self._path),
                                        "err": last_err,
                                        "timeout": self.timeout,
                                    },
                                )
                            except Exception:
                                pass
                            # #endregion
                            raise SerialBusy(
                                f"Panel serial is busy ({last_err}). Retry in a few seconds."
                            ) from exc
                        time.sleep(0.05)
                        continue
                else:
                    import fcntl

                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        locked = True
                    except OSError as exc:
                        last_err = f"{type(exc).__name__}: {exc}"
                        os.close(fd)
                        if time.time() >= deadline:
                            raise SerialBusy(
                                f"Panel serial is busy ({last_err}). Retry in a few seconds."
                            ) from exc
                        time.sleep(0.05)
                        continue

                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    os.ftruncate(fd, 0)
                    os.write(fd, f"{os.getpid()}\n".encode("ascii"))
                except OSError:
                    pass
                self._fd = fd
                atexit.register(self.release)
                # #region agent log
                try:
                    from debug_ndjson import dlog

                    dlog(
                        "D",
                        "serial_guard.py:acquire",
                        "lock_acquired",
                        {
                            "lock_path": str(self._path),
                            "timeout": self.timeout,
                            "backend": "msvcrt" if sys.platform == "win32" else "fcntl",
                        },
                    )
                except Exception:
                    pass
                # #endregion
                return
            except Exception:
                if not locked:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                raise

    def release(self) -> None:
        fd = self._fd
        self._fd = None
        if fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            atexit.unregister(self.release)
        except Exception:
            pass
        # #region agent log
        try:
            from debug_ndjson import dlog

            dlog("D", "serial_guard.py:release", "lock_released", {"lock_path": str(self._path)})
        except Exception:
            pass
        # #endregion

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
