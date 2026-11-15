"""Build the monochrome FennSill startup splash as a C header for the panel."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
# Prefer the brand wordmark checked into templates/; fall back to Cursor asset.
LOGO_CANDIDATES = (
    ROOT / "templates" / "fennsill_splash_source.jpg",
    ROOT / "templates" / "fennsill_splash_source.png",
    Path(
        r"C:\Users\Kyle\.cursor\projects\c-Users-Kyle-Desktop-This-Is-A-Test-For-The-Tablet"
        r"\assets\image-308e34cc-f538-43d7-86e1-de303efc7097.jpg"
    ),
)
OUT_PNG = ROOT / "templates" / "splash.png"
OUT_H = ROOT / "firmware" / "fennsill" / "splash_frame.h"
WIDTH = 800
HEIGHT = 480
ROW_BYTES = WIDTH // 8
FRAME_BYTES = ROW_BYTES * HEIGHT


def find_logo() -> Path:
    for path in LOGO_CANDIDATES:
        if path.is_file():
            return path
    raise SystemExit("Splash source image not found.")


def to_frame(img: Image.Image) -> bytes:
    # Clean wordmark: hard threshold (no dither) — bit 1 = white, MSB left.
    bw = img.convert("L").point(lambda v: 255 if v >= 160 else 0, mode="1")
    frame = bytearray(FRAME_BYTES)
    px = bw.convert("L").load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if px[x, y] >= 128:
                frame[y * ROW_BYTES + (x >> 3)] |= 0x80 >> (x & 7)
    return bytes(frame)


def compose(logo_path: Path) -> Image.Image:
    """Center the FennSill wordmark on a full white 800x480 panel frame."""
    canvas = Image.new("L", (WIDTH, HEIGHT), 255)
    logo = Image.open(logo_path).convert("RGB")
    # Fit with margins so the mark reads clearly on e-ink.
    mark = ImageOps.contain(logo, (720, 280))
    gray = mark.convert("L")
    mx = (WIDTH - gray.width) // 2
    my = (HEIGHT - gray.height) // 2
    canvas.paste(gray, (mx, my))
    return canvas


def write_header(frame: bytes) -> None:
    lines = [
        "#pragma once",
        "// Monochrome FennSill startup splash. 800x480, bit 1 white, MSB left.",
        f"static const uint16_t SPLASH_FRAME_LEN = {FRAME_BYTES};",
        "static const uint8_t SPLASH_FRAME[48000] PROGMEM = {",
    ]
    for i in range(0, FRAME_BYTES, 16):
        chunk = ", ".join(f"0x{b:02x}" for b in frame[i : i + 16])
        comma = "," if i + 16 < FRAME_BYTES else ""
        lines.append(f"  {chunk}{comma}")
    lines.append("};")
    lines.append("")
    OUT_H.write_text("\n".join(lines), encoding="utf-8")


def write_png(frame: bytes, path: Path) -> None:
    rows = []
    for y in range(HEIGHT):
        row = bytearray(1 + WIDTH)
        base = y * ROW_BYTES
        for x in range(WIDTH):
            white = frame[base + (x >> 3)] & (0x80 >> (x & 7))
            row[1 + x] = 255 if white else 0
        rows.append(bytes(row))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 0, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def main() -> None:
    logo = find_logo()
    img = compose(logo)
    frame = to_frame(img)
    if len(frame) != FRAME_BYTES:
        raise SystemExit(f"frame is {len(frame)} bytes")
    write_png(frame, OUT_PNG)
    write_header(frame)
    # Keep a stable source next to the generator for rebuilds.
    dest = ROOT / "templates" / "fennsill_splash_source.jpg"
    if logo.resolve() != dest.resolve() and logo.suffix.lower() in {".jpg", ".jpeg"}:
        dest.write_bytes(logo.read_bytes())
    print(logo)
    print(OUT_PNG)
    print(OUT_H)
    print(f"frame bytes={len(frame)} white_ratio={frame.count(0xFF) / len(frame):.3f}")


if __name__ == "__main__":
    main()
