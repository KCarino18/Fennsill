"""Build the monochrome Fennsill startup splash as a C header for the panel."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / ".cursor" / ".."  # placeholder; real path set below
LOGO = Path(r"C:\Users\Kyle\.cursor\projects\c-Users-Kyle-Desktop-This-Is-A-Test-For-The-Tablet\assets\ChatGPT_Image_Sep_19__2025__05_16_56_PM-47e1839c-5a51-4d33-9279-17b1962b7f10.png")
OUT_PNG = ROOT / "templates" / "splash.png"
OUT_H = ROOT / "firmware" / "fennsill" / "splash_frame.h"
WIDTH = 800
HEIGHT = 480
ROW_BYTES = WIDTH // 8
FRAME_BYTES = ROW_BYTES * HEIGHT


def to_frame(img: Image.Image) -> bytes:
    # Floyd-Steinberg keeps sphere shading on a 1-bit panel.
    bw = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    frame = bytearray([0x00]) * FRAME_BYTES
    px = bw.convert("L").load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if px[x, y] >= 128:
                frame[y * ROW_BYTES + (x >> 3)] |= 0x80 >> (x & 7)
    return bytes(frame)


def compose() -> Image.Image:
    canvas = Image.new("L", (WIDTH, HEIGHT), 0)
    logo = Image.open(LOGO).convert("RGBA")
    gray = Image.new("L", logo.size, 0)
    src = logo.load()
    dst = gray.load()
    for y in range(logo.height):
        for x in range(logo.width):
            r, g, b, a = src[x, y]
            if a < 8 or (r < 18 and g < 18 and b < 18):
                continue
            # Lift midtones so the spheres stay visible after dithering on black.
            value = int(0.3 * r + 0.59 * g + 0.11 * b)
            dst[x, y] = min(255, int(value * 1.35) + 20)

    mark = ImageOps.contain(gray, (560, 300))
    mx = (WIDTH - mark.width) // 2
    my = 40
    canvas.paste(mark, (mx, my))

    draw = ImageDraw.Draw(canvas)
    label = "FENNSILL"
    font = None
    for name in ("arialbd.ttf", "segoeuib.ttf", "calibrib.ttf", "arial.ttf"):
        path = Path(r"C:\Windows\Fonts") / name
        if path.is_file():
            font = ImageFont.truetype(str(path), 52)
            break
    if font is None:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (WIDTH - tw) // 2
    ty = my + mark.height + 28
    if ty + th > HEIGHT - 24:
        ty = HEIGHT - 24 - th
    draw.text((tx, ty), label, fill=255, font=font)
    return canvas


def write_header(frame: bytes):
    lines = [
        "#pragma once",
        "// Monochrome Fennsill startup splash. 800x480, bit 1 white, MSB left.",
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


def write_png(frame: bytes, path: Path):
    rows = []
    for y in range(HEIGHT):
        row = bytearray(1 + WIDTH)
        base = y * ROW_BYTES
        for x in range(WIDTH):
            white = frame[base + (x >> 3)] & (0x80 >> (x & 7))
            row[1 + x] = 255 if white else 0
        rows.append(bytes(row))

    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 0, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


def main():
    img = compose()
    frame = to_frame(img)
    if len(frame) != FRAME_BYTES:
        raise SystemExit(f"frame is {len(frame)} bytes")
    write_png(frame, OUT_PNG)
    write_header(frame)
    print(OUT_PNG)
    print(OUT_H)


if __name__ == "__main__":
    main()
