"""Local page library for Artifacts pushed to the panel.

Each page is a folder under connector/pages/<id>/ with frame.bin, preview.png,
and meta.json. The desktop app shows these previews and can delete them.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = Path(__import__("os").environ.get("ARTIPHACT_PAGES", ROOT / "connector" / "pages"))
FRAME_BYTES = 48000


def pages_root() -> Path:
    PAGES.mkdir(parents=True, exist_ok=True)
    return PAGES


def _write_png(frame: bytes, path: Path):
    from render import write_png

    write_png(frame, path)


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
    # Signal the desktop app to refresh.
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
