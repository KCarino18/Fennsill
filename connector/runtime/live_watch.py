"""Watch connector/inbox for new HTML/SVG and push live to the panel.

Any AI or automation can drop a finished 800x480 page here. Fennsill.exe
(or this script alone) picks it up, saves a gallery preview, and sends it
to the USB panel so live data stays current.
"""

from __future__ import annotations

import os

import argparse
import shutil
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
sys.path.insert(0, str(ROOT / "connector"))
sys.path.insert(0, str(ROOT / "connector" / "runtime"))

from intake import intake_page  # noqa: E402
from security import SecurityError  # noqa: E402

INBOX = Path(__import__("os").environ.get("FENNSILL_INBOX", ROOT / "connector" / "inbox"))
DONE = INBOX / "done"
FAILED = INBOX / "failed"
EXTS = {".html", ".htm", ".svg"}


def ensure_dirs():
    INBOX.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)


def settle(path: Path, waits: int = 10) -> bool:
    """Wait until file size stops changing (writer finished)."""
    last = -1
    for _ in range(waits):
        try:
            size = path.stat().st_size
        except OSError:
            return False
        if size > 0 and size == last:
            return True
        last = size
        time.sleep(0.15)
    return path.is_file() and path.stat().st_size > 0


def process_file(path: Path) -> bool:
    if not settle(path):
        return False
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"live: skip {path.name}: {exc}", flush=True)
        return False
    kwargs = {
        "title": path.stem,
        "source": "live-inbox",
        "push": True,
    }
    if suffix == ".svg":
        kwargs["svg"] = text
    else:
        kwargs["html"] = text
    try:
        result = intake_page(**kwargs)
        print(f"live: {path.name} -> {result}", flush=True)
        dest = DONE / f"{int(time.time())}-{path.name}"
        shutil.move(str(path), str(dest))
        return True
    except SecurityError as exc:
        print(f"live: failed {path.name}: {exc}", flush=True)
        dest = FAILED / f"{int(time.time())}-{path.name}"
        try:
            shutil.move(str(path), str(dest))
        except OSError:
            pass
        return False
    except Exception as exc:
        print(f"live: error {path.name}: {exc}", flush=True)
        return False


def scan_once() -> int:
    ensure_dirs()
    count = 0
    for path in sorted(INBOX.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in EXTS:
            continue
        if process_file(path):
            count += 1
    return count


def watch_loop(interval: float = 1.0):
    ensure_dirs()
    print(f"Fennsill live inbox: {INBOX}", flush=True)
    while True:
        try:
            scan_once()
        except Exception as exc:
            print(f"live: loop error: {exc}", flush=True)
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Live-push pages dropped into the Fennsill inbox.")
    parser.add_argument("--once", action="store_true", help="Process current inbox files and exit.")
    parser.add_argument("--interval", type=float, default=1.0, help="Poll seconds when watching.")
    args = parser.parse_args()
    if args.once:
        n = scan_once()
        print(f"processed {n}")
        return
    watch_loop(args.interval)


if __name__ == "__main__":
    main()
