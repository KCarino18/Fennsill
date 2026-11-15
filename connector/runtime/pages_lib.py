"""Local page store for Artifacts pushed to the panel.

Keeps only the newest page on disk (plus one previous) so scheduled AI pushes
do not pile up endless gallery folders. The desk app no longer shows a gallery.
"""

from __future__ import annotations

import os

import json
import shutil
import time
import uuid
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
PAGES = Path(__import__("os").environ.get("FENNSILL_PAGES", ROOT / "connector" / "pages"))
FRAME_BYTES = 48000
# Keep current + one previous for rotate/debug — prune the rest.
KEEP_PAGES = 2


def pages_root() -> Path:
    PAGES.mkdir(parents=True, exist_ok=True)
    return PAGES


def _write_png(frame: bytes, path: Path):
    from render import write_png

    write_png(frame, path)


def prune_old_pages(keep: int = KEEP_PAGES) -> None:
    root = pages_root()
    folders = sorted(
        [p for p in root.iterdir() if p.is_dir()],
        key=lambda p: p.name,
        reverse=True,
    )
    for folder in folders[max(0, keep) :]:
        try:
            shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            pass


def save_page(frame: bytes, *, source: str = "artifact", title: str = "") -> dict:
    if len(frame) != FRAME_BYTES:
        raise ValueError("frame must be 48000 bytes")
    page_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    folder = pages_root() / page_id
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "frame.bin").write_bytes(frame)
    preview = folder / "preview.png"
    _write_png(frame, preview)
    meta = {
        "id": page_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "title": title or page_id,
        "bytes": len(frame),
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    prune_old_pages()
    (pages_root() / ".changed").write_text(str(time.time()), encoding="utf-8")
    return meta


def list_pages() -> list[dict]:
    items = []
    root = pages_root()
    for folder in sorted(root.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        meta_path = folder / "meta.json"
        preview = folder / "preview.png"
        frame = folder / "frame.bin"
        if not meta_path.is_file() or not preview.is_file() or not frame.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        meta["folder"] = str(folder)
        meta["preview"] = str(preview)
        meta["frame"] = str(frame)
        items.append(meta)
    return items


def delete_page(page_id: str) -> bool:
    if not page_id or "/" in page_id or "\\" in page_id or ".." in page_id:
        raise ValueError("Bad page id.")
    folder = pages_root() / page_id
    if not folder.is_dir():
        return False
    for path in folder.iterdir():
        path.unlink()
    folder.rmdir()
    (pages_root() / ".changed").write_text(str(time.time()), encoding="utf-8")
    return True


def load_frame(page_id: str) -> bytes:
    if not page_id or "/" in page_id or "\\" in page_id or ".." in page_id:
        raise ValueError("Bad page id.")
    path = pages_root() / page_id / "frame.bin"
    data = path.read_bytes()
    if len(data) != FRAME_BYTES:
        raise ValueError("Stored frame is damaged.")
    return data
