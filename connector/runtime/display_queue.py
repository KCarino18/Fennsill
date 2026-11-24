"""Local display queue shared by the Fennsill Agent and Desk.

Jobs claimed from the cloud are rendered here (frame + preview), then played
in order. Desk can reorder waiting items and remove them. The Agent holds the
panel for hold_sec after a successful show before advancing.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)

FRAME_BYTES = 48000
MAX_HOLD_SEC = 6 * 3600
STATUS_WAITING = "waiting"
STATUS_SHOWING = "showing"


def _local_app() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "FennsillApp"
    return ROOT


def queue_path() -> Path:
    env = os.environ.get("FENNSILL_DISPLAY_QUEUE")
    if env:
        return Path(env)
    preferred = ROOT / "connector" / "display_queue.json"
    if preferred.parent.is_dir() or ROOT.is_dir():
        return preferred
    return _local_app() / "display_queue.json"


def previews_dir() -> Path:
    env = os.environ.get("FENNSILL_QUEUE_PREVIEWS")
    if env:
        return Path(env)
    d = ROOT / "connector" / "queue_previews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def clamp_hold_sec(value) -> int:
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        n = 0
    return max(0, min(n, MAX_HOLD_SEC))


@contextmanager
def _file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        try:
            if os.fstat(fd).st_size < 1:
                os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
        except OSError:
            pass
        if sys.platform == "win32":
            import msvcrt

            deadline = time.time() + 8.0
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.time() >= deadline:
                        raise
                    time.sleep(0.05)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if sys.platform == "win32":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass


def _empty() -> dict:
    return {"version": 1, "items": [], "updated_at": _stamp(), "generation": 0}


def _stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, indent=2)
    tmp.write_text(data, encoding="utf-8")
    os.replace(str(tmp), str(path))


def _parse_queue_unlocked(path: Path) -> dict:
    if not path.is_file():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    items = data.get("items")
    if not isinstance(items, list):
        items = []
    cleaned = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        if not item_id:
            continue
        cleaned.append(
            {
                "id": item_id,
                "job_id": str(raw.get("job_id") or ""),
                "title": str(raw.get("title") or "")[:80],
                "hold_sec": clamp_hold_sec(raw.get("hold_sec")),
                "preview_path": str(raw.get("preview_path") or ""),
                "frame_path": str(raw.get("frame_path") or ""),
                "status": str(raw.get("status") or STATUS_WAITING),
                "created_at": str(raw.get("created_at") or _stamp()),
                "held_until": raw.get("held_until"),
            }
        )
    try:
        generation = int(data.get("generation") or 0)
    except (TypeError, ValueError):
        generation = 0
    return {
        "version": 1,
        "items": cleaned,
        "updated_at": data.get("updated_at") or _stamp(),
        "generation": generation,
    }


def load_queue() -> dict:
    path = queue_path()
    with _file_lock(path):
        return _parse_queue_unlocked(path)


def save_queue(data: dict) -> dict:
    path = queue_path()
    payload = {
        "version": 1,
        "items": list(data.get("items") or []),
        "updated_at": _stamp(),
        "generation": int(data.get("generation") or 0),
    }
    with _file_lock(path):
        _atomic_write(path, payload)
    return payload


def _mutate(mutator: Callable[[dict], object]) -> object:
    """Read-modify-write under one lock so Desk remove cannot be overwritten."""
    path = queue_path()
    with _file_lock(path):
        data = _parse_queue_unlocked(path)
        result = mutator(data)
        payload = {
            "version": 1,
            "items": list(data.get("items") or []),
            "updated_at": _stamp(),
            "generation": int(data.get("generation") or 0),
        }
        _atomic_write(path, payload)
        return result


def _delete_files(item: dict) -> None:
    for key in ("preview_path", "frame_path"):
        p = Path(str(item.get(key) or ""))
        if not p.is_file():
            continue
        try:
            p.unlink()
        except OSError:
            pass


def append_item(
    *,
    job_id: str,
    title: str,
    hold_sec: int,
    frame: bytes,
) -> dict:
    if len(frame) != FRAME_BYTES:
        raise ValueError("frame must be 48000 bytes")
    item_id = uuid.uuid4().hex
    folder = previews_dir()
    folder.mkdir(parents=True, exist_ok=True)
    frame_path = folder / f"{item_id}.bin"
    preview_path = folder / f"{item_id}.png"
    frame_path.write_bytes(frame)
    from render import write_png

    write_png(frame, preview_path)
    item = {
        "id": item_id,
        "job_id": str(job_id or ""),
        "title": (title or "")[:80] or item_id[:8],
        "hold_sec": clamp_hold_sec(hold_sec),
        "preview_path": str(preview_path),
        "frame_path": str(frame_path),
        "status": STATUS_WAITING,
        "created_at": _stamp(),
        "held_until": None,
    }

    def _add(data: dict):
        data.setdefault("items", []).append(item)
        return item

    return _mutate(_add)  # type: ignore[return-value]


def has_job(job_id: str) -> bool:
    jid = str(job_id or "").strip()
    if not jid:
        return False
    return any(str(i.get("job_id") or "") == jid for i in load_queue()["items"])


def list_items() -> list[dict]:
    return list(load_queue()["items"])


def move_item(item_id: str, direction: int) -> bool:
    """Move a waiting item up (-1) or down (+1). Showing item stays at head."""

    def _move(data: dict):
        items = data["items"]
        idx = next((i for i, it in enumerate(items) if it["id"] == item_id), None)
        if idx is None:
            return False
        if items[idx].get("status") == STATUS_SHOWING:
            return False
        new_idx = idx + int(direction)
        if new_idx < 0 or new_idx >= len(items):
            return False
        if items[new_idx].get("status") == STATUS_SHOWING:
            return False
        items[idx], items[new_idx] = items[new_idx], items[idx]
        return True

    return bool(_mutate(_move))


def remove_item(item_id: str) -> dict | None:
    removed_box: dict = {"item": None}

    def _remove(data: dict):
        items = data["items"]
        idx = next((i for i, it in enumerate(items) if it["id"] == item_id), None)
        if idx is None:
            return None
        removed = items.pop(idx)
        # Desk removed the live page — bump generation so Agent interrupts hold.
        if removed.get("status") == STATUS_SHOWING:
            data["generation"] = int(data.get("generation") or 0) + 1
        removed_box["item"] = removed
        return removed

    removed = _mutate(_remove)
    if isinstance(removed, dict):
        _delete_files(removed)
        return removed
    return None


def head_item() -> dict | None:
    items = load_queue()["items"]
    return items[0] if items else None


def queue_generation() -> int:
    try:
        return int(load_queue().get("generation") or 0)
    except (TypeError, ValueError):
        return 0


def mark_showing(item_id: str, held_until: float | None = None) -> dict | None:
    def _mark(data: dict):
        found = None
        for it in data["items"]:
            if it["id"] == item_id:
                it["status"] = STATUS_SHOWING
                it["held_until"] = held_until
                found = it
            elif it.get("status") == STATUS_SHOWING:
                it["status"] = STATUS_WAITING
                it["held_until"] = None
        return found

    result = _mutate(_mark)
    return result if isinstance(result, dict) else None


def finish_head(item_id: str) -> dict | None:
    """Remove the finished showing item from the queue."""
    return remove_item(item_id)


def load_frame_bytes(item: dict) -> bytes:
    path = Path(str(item.get("frame_path") or ""))
    data = path.read_bytes()
    if len(data) != FRAME_BYTES:
        raise ValueError("Stored queue frame is damaged.")
    return data
