"""Turn a Claude HTML or SVG Artifact into the panel's 800x480 1-bit frame.

The Chromium render is local-only: no network, no file URLs, fixed viewport,
and a hard timeout. External schemes are refused before the browser starts.
"""

from __future__ import annotations

import os
import re
import struct
import zlib
from pathlib import Path

WIDTH = 800
HEIGHT = 480
ROW_BYTES = WIDTH // 8
FRAME_BYTES = ROW_BYTES * HEIGHT
THRESHOLD = 128
MAX_ARTIFACT_CHARS = 512_000
RENDER_TIMEOUT_MS = 8_000
NAV_TIMEOUT_MS = 5_000
MAX_PNG_BYTES = 8_000_000

CSP = (
    "default-src 'none'; "
    "img-src data:; "
    "style-src 'unsafe-inline'; "
    "font-src data:; "
    "script-src 'unsafe-inline'; "
    "connect-src 'none'; "
    "frame-src 'none'; "
    "object-src 'none'; "
    "media-src 'none'; "
    "worker-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

SHELL = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<style>
  html, body {{
    margin: 0;
    padding: 0;
    width: {width}px;
    height: {height}px;
    overflow: hidden;
    background: #ffffff;
  }}
  body {{
    box-sizing: border-box;
  }}
  #root {{
    width: {width}px;
    height: {height}px;
    overflow: hidden;
    background: #ffffff;
  }}
  #root > svg {{
    display: block;
    width: {width}px;
    height: {height}px;
  }}
</style>
{extra_styles}
</head>
<body>
<div id="root">{body}</div>
</body>
</html>
"""

_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)


def _size_ok(text, label):
    if not isinstance(text, str):
        raise ValueError(f"{label} must be a string.")
    if len(text) > MAX_ARTIFACT_CHARS:
        raise ValueError(f"{label} is too large.")
    return text


def _extract_styles(doc: str) -> str:
    """Keep author CSS when a full HTML document is reduced to a body fragment."""
    return "\n".join(m.group(0) for m in _STYLE_RE.finditer(doc))


def wrap_page(html=None, svg=None):
    has_html = isinstance(html, str) and html.strip()
    has_svg = isinstance(svg, str) and svg.strip()
    if has_html and has_svg:
        raise ValueError("Send either an HTML Artifact or an SVG Artifact.")
    if has_html:
        body = _size_ok(html.strip(), "html")
        extra_styles = ""
        # Always wrap so the CSP shell owns the page. Full documents are treated as a body fragment.
        if body.lower().startswith("<!doctype") or body.lower().startswith("<html"):
            # Head <style> must travel with the body — otherwise Playwright paints
            # an unstyled left-stacked text dump inside the 800x480 clip.
            extra_styles = _extract_styles(body)
            lower = body.lower()
            start = lower.find("<body")
            if start >= 0:
                start = lower.find(">", start) + 1
                end = lower.rfind("</body>")
                if start > 0 and end > start:
                    body = body[start:end]
            # Author CSS often layouts on `body`; #root would otherwise trap children.
            if extra_styles:
                extra_styles += "\n<style>#root{display:contents}</style>"
        return SHELL.format(
            csp=CSP, width=WIDTH, height=HEIGHT, body=body, extra_styles=extra_styles
        )
    if has_svg:
        body = _size_ok(svg.strip(), "svg")
        if not body.lower().startswith("<svg"):
            body = f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}">{body}</svg>'
        return SHELL.format(
            csp=CSP, width=WIDTH, height=HEIGHT, body=body, extra_styles=""
        )
    raise ValueError("Pass the Claude Artifact as html or svg.")


def _paeth(a, b, c):
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter(raw, width, height, channels):
    stride = width * channels
    expected = (stride + 1) * height
    if len(raw) < expected:
        raise ValueError("Artifact PNG pixels do not match the page size.")
    out = bytearray(stride * height)
    prev = bytearray(stride)
    offset = 0
    for y in range(height):
        filter_type = raw[offset]
        offset += 1
        row = bytearray(raw[offset : offset + stride])
        offset += stride
        if filter_type == 0:
            pass
        elif filter_type == 1:
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + left) & 255
        elif filter_type == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 255
        elif filter_type == 3:
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + ((left + prev[i]) // 2)) & 255
        elif filter_type == 4:
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                up = prev[i]
                up_left = prev[i - channels] if i >= channels else 0
                row[i] = (row[i] + _paeth(left, up, up_left)) & 255
        else:
            raise ValueError(f"Unsupported PNG filter {filter_type}.")
        out[y * stride : (y + 1) * stride] = row
        prev = row
    return out


def png_to_frame(png_bytes):
    if not isinstance(png_bytes, (bytes, bytearray)):
        raise ValueError("Artifact render was not a PNG.")
    if len(png_bytes) > MAX_PNG_BYTES:
        raise ValueError("Artifact render is too large.")
    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Artifact render was not a PNG.")
    offset = 8
    width = height = None
    bit_depth = color_type = None
    idat = bytearray()
    while offset + 8 <= len(png_bytes):
        length = struct.unpack(">I", png_bytes[offset : offset + 4])[0]
        if length > MAX_PNG_BYTES or offset + 12 + length > len(png_bytes):
            raise ValueError("Artifact PNG is damaged.")
        tag = png_bytes[offset + 4 : offset + 8]
        data = png_bytes[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if tag == b"IHDR":
            width, height, bit_depth, color_type, *_ = struct.unpack(">IIBBBBB", data)
        elif tag == b"IDAT":
            idat.extend(data)
            if len(idat) > MAX_PNG_BYTES:
                raise ValueError("Artifact render is too large.")
        elif tag == b"IEND":
            break
    if width != WIDTH or height != HEIGHT:
        raise ValueError(f"Artifact must render at {WIDTH}x{HEIGHT}, got {width}x{height}.")
    if bit_depth != 8 or color_type not in (0, 2, 6):
        raise ValueError("Artifact render must be 8-bit grayscale or RGB.")
    channels = {0: 1, 2: 3, 6: 4}[color_type]
    try:
        decoder = zlib.decompressobj()
        inflated = decoder.decompress(bytes(idat), WIDTH * HEIGHT * 4 + HEIGHT)
        if decoder.unconsumed_tail:
            raise ValueError("Artifact PNG is damaged.")
        pixels = _unfilter(inflated, width, height, channels)
    except zlib.error as exc:
        raise ValueError("Artifact PNG is damaged.") from exc
    frame = bytearray([0xFF]) * FRAME_BYTES
    for y in range(HEIGHT):
        base = y * WIDTH * channels
        for x in range(WIDTH):
            at = base + x * channels
            if channels == 1:
                gray = pixels[at]
            else:
                gray = (pixels[at] * 30 + pixels[at + 1] * 59 + pixels[at + 2] * 11) // 100
            if gray < THRESHOLD:
                frame[y * ROW_BYTES + (x >> 3)] &= ~(0x80 >> (x & 7))
    return bytes(frame)


def _browser_root():
    here = Path(__file__).resolve().parents[1] / "connector" / "browsers"
    if here.is_dir():
        return str(here)
    return None


def _allow_request(route):
    url = route.request.url
    if url.startswith("data:") or url.startswith("about:"):
        route.continue_()
        return
    route.abort()


def _shot_png(page_html):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Install Playwright on this computer: pip install playwright && python -m playwright install chromium"
        ) from exc

    browsers = _browser_root()
    if browsers:
        # Always prefer the Fennsill-bundled Chromium (ChatGPT MCP often
        # starts without PLAYWRIGHT_BROWSERS_PATH and then hangs/times out).
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers
        shell = (
            Path(browsers)
            / "chromium_headless_shell-1254"
            / "chrome-headless-shell-win64"
            / "chrome-headless-shell.exe"
        )
        if not shell.is_file():
            raise RuntimeError(
                f"Fennsill Chromium missing at {shell}. Reinstall Fennsill browsers."
            )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            chromium_sandbox=True,
            timeout=15_000,
            args=[
                "--disable-extensions",
                "--disable-translations",
                "--disable-sync",
                "--no-first-run",
                "--disable-background-networking",
                "--disable-client-side-phishing-detection",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-domain-reliability",
                "--disable-features=Translate,BackForwardCache",
                "--disable-hang-monitor",
                "--disable-popup-blocking",
                "--disable-prompt-on-repost",
                "--metrics-recording-only",
                "--safebrowsing-disable-auto-update",
            ],
        )
        try:
            context = browser.new_context(
                viewport={"width": WIDTH, "height": HEIGHT},
                device_scale_factor=1,
                java_script_enabled=True,
                bypass_csp=False,
                accept_downloads=False,
                offline=True,
                service_workers="block",
                permissions=[],
            )
            page = context.new_page()
            page.set_default_timeout(RENDER_TIMEOUT_MS)
            page.set_default_navigation_timeout(NAV_TIMEOUT_MS)
            page.route("**/*", _allow_request)
            page.on("dialog", lambda dialog: dialog.dismiss())
            page.set_content(page_html, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            png = page.screenshot(type="png", full_page=False, timeout=RENDER_TIMEOUT_MS)
            context.close()
            return png
        finally:
            browser.close()


def artifact_to_frame(html=None, svg=None, screenshot=_shot_png):
    page_html = wrap_page(html=html, svg=svg)
    return png_to_frame(screenshot(page_html))


def write_preview(frame, path):
    from render import write_png

    write_png(frame, path)


if __name__ == "__main__":
    sample = """
    <div style="font-family:sans-serif;padding:24px">
      <h1 style="margin:0 0 16px">Today</h1>
      <p style="font-size:28px;margin:8px 0">Dentist at 3</p>
      <p style="font-size:28px;margin:8px 0">Buy milk</p>
    </div>
    """
    frame = artifact_to_frame(html=sample)
    out = Path(__file__).with_name("artifact_preview.png")
    write_preview(frame, out)
    print(out)
