"""Build a professional Fennsill-MCP-Commands.pdf via Playwright print."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
HTML = HERE / "mcp_commands_print.html"
OUT = HERE / "Fennsill-MCP-Commands.pdf"


def _browser_exe() -> Path:
    browsers = ROOT / "connector" / "browsers"
    preferred = browsers / "chromium-1254" / "chrome-win64" / "chrome.exe"
    if preferred.is_file():
        return preferred
    for path in browsers.rglob("chrome.exe"):
        return path
    raise SystemExit(f"Bundled Chromium not found under {browsers}")


def build_pdf() -> Path:
    from playwright.sync_api import sync_playwright

    if not HTML.is_file():
        raise SystemExit(f"Missing HTML source: {HTML}")

    browsers = ROOT / "connector" / "browsers"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    exe = _browser_exe()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=str(exe))
        page = browser.new_page()
        page.goto(HTML.as_uri(), wait_until="load")
        # CSS @page owns margins; keep Playwright margins at zero.
        page.pdf(
            path=str(OUT),
            format="Letter",
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            prefer_css_page_size=True,
        )
        browser.close()

    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)", flush=True)
    return OUT


if __name__ == "__main__":
    build_pdf()
