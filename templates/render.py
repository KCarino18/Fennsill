"""Draw the default dashboard as an 800x480 1-bit frame.

Bit 1 is white and bit 0 is black. The leftmost pixel of each byte is the
high bit. A full frame is 48,000 bytes, which is what the panel stores.
"""

import json
import struct
import zlib
from pathlib import Path

WIDTH = 800
HEIGHT = 480
ROW_BYTES = WIDTH // 8
FRAME_BYTES = ROW_BYTES * HEIGHT

HERE = Path(__file__).resolve().parent

# 5x7 glyphs, '#' is ink. One extra blank column is added between letters.
GLYPHS = {
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "G": [".###.", "#...#", "#....", "#.###", "#...#", "#...#", ".###."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "J": ["..###", "...#.", "...#.", "...#.", "#..#.", "#..#.", ".##.."],
    "K": ["#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#", "#...#"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "Q": [".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "V": ["#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."],
    "W": ["#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."],
    "Z": ["#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "5": ["#####", "#....", "#....", "####.", "....#", "....#", "####."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    ".": [".....", ".....", ".....", ".....", ".....", ".##..", ".##.."],
    "+": [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    "-": [".....", ".....", ".....", "#####", ".....", ".....", "....."],
    "%": ["##..#", "##..#", "...#.", "..#..", ".#...", "#..##", "#..##"],
    ":": [".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."],
}


class Canvas:
    def __init__(self):
        self.buf = bytearray([0xFF]) * FRAME_BYTES

    def pixel(self, x, y, black):
        if x < 0 or y < 0 or x >= WIDTH or y >= HEIGHT:
            return
        index = y * ROW_BYTES + (x >> 3)
        mask = 0x80 >> (x & 7)
        if black:
            self.buf[index] &= ~mask
        else:
            self.buf[index] |= mask

    def rect(self, x, y, w, h, black=True):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.pixel(xx, yy, black)

    def text_width(self, text, scale):
        if not text:
            return 0
        return (len(text) * 6 - 1) * scale

    def text(self, text, x, y, scale, black=True, align="left"):
        width = self.text_width(text, scale)
        if align == "right":
            x -= width
        elif align == "center":
            x -= width // 2
        cursor = x
        for char in text:
            glyph = GLYPHS.get(char, GLYPHS[" "])
            for row, bits in enumerate(glyph):
                for col, mark in enumerate(bits):
                    if mark != "#":
                        continue
                    self.rect(cursor + col * scale, y + row * scale, scale, scale, black)
            cursor += 6 * scale
        return width


def load_dashboard(path=None):
    source = Path(path) if path else HERE / "market_movers.json"
    return json.loads(source.read_text(encoding="utf-8"))


def render_own(data):
    """Draw only the words the buyer sent. Nothing is filled in for them."""
    title = str(data.get("title") or "").upper()
    lines = [str(line).upper() for line in data.get("lines") or [] if str(line).strip()]
    if not title and not lines:
        raise ValueError("The panel needs the buyer's own content.")
    canvas = Canvas()
    canvas.rect(0, 0, WIDTH, 64, True)
    if title:
        canvas.text(title[:22], 28, 16, 4, black=False)
    y = 92
    for line in lines:
        if y > 440:
            break
        canvas.text(line[:36], 28, y, 4)
        y += 40
    frame = bytes(canvas.buf)
    if len(frame) != FRAME_BYTES:
        raise RuntimeError(f"frame is {len(frame)} bytes")
    return frame


def render_market_movers(data=None):
    data = data or load_dashboard()
    canvas = Canvas()
    canvas.rect(0, 0, WIDTH, 64, True)
    canvas.text(data["brand"], 28, 16, 4, black=False)
    canvas.text(data["as_of"], WIDTH - 28, 20, 3, black=False, align="right")

    canvas.text(data["title"], 28, 88, 5)
    canvas.rect(28, 140, WIDTH - 56, 6, True)

    columns = data["columns"]
    canvas.text(columns[0], 28, 164, 3)
    canvas.text(columns[1], 470, 164, 3, align="right")
    canvas.text(columns[2], WIDTH - 28, 164, 3, align="right")
    canvas.rect(28, 196, WIDTH - 56, 2, True)

    y = 214
    for ticker, last, change in data["rows"]:
        canvas.text(ticker, 28, y, 4)
        canvas.text(last, 470, y + 4, 3, align="right")
        canvas.text(change, WIDTH - 28, y + 4, 3, align="right")
        y += 36
        canvas.rect(28, y - 8, WIDTH - 56, 1, True)

    canvas.text(data["footer"], 28, 446, 2)
    frame = bytes(canvas.buf)
    if len(frame) != FRAME_BYTES:
        raise RuntimeError(f"frame is {len(frame)} bytes")
    return frame


def write_png(frame, path):
    """Write an 8-bit grayscale PNG so the frame can be looked at."""
    if len(frame) != FRAME_BYTES:
        raise ValueError("frame must be 48000 bytes")
    rows = []
    for y in range(HEIGHT):
        row = bytearray(1 + WIDTH)
        base = y * ROW_BYTES
        for x in range(WIDTH):
            white = frame[base + (x >> 3)] & (0x80 >> (x & 7))
            row[1 + x] = 255 if white else 0
        rows.append(bytes(row))

    def chunk(tag, payload):
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 0, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")
    Path(path).write_bytes(png)


if __name__ == "__main__":
    destination = HERE / "market_movers.png"
    write_png(render_market_movers(), destination)
    print(destination)
