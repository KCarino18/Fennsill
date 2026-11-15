"""Expose the local Fennsill bridge on a public https URL.

Cloud AIs and phones cannot reach 127.0.0.1. A Cloudflare quick tunnel
gives a temporary https://….trycloudflare.com address that points at this PC
while Fennsill.exe is open. The URL can change each launch unless a named
tunnel is configured later.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL_PATH = Path(os.environ.get("FENNSILL_PUBLIC_URL_FILE", ROOT / "connector" / "public_url.txt"))
PORT = int(os.environ.get("FENNSILL_BRIDGE_PORT", "8765"))
LOCAL = f"http://127.0.0.1:{PORT}"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)


def find_cloudflared() -> str | None:
    bundled = ROOT / "connector" / "bin" / "cloudflared.exe"
    if bundled.is_file():
        return str(bundled)
    which = shutil.which("cloudflared")
    if which:
        return which
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "cloudflared" / "cloudflared.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "cloudflared" / "cloudflared.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def write_url(url: str):
    URL_PATH.parent.mkdir(parents=True, exist_ok=True)
    URL_PATH.write_text(url.strip() + "\n", encoding="utf-8")
    print(f"PUBLIC_URL {url}", flush=True)


def clear_url():
    try:
        if URL_PATH.is_file():
            URL_PATH.unlink()
    except OSError:
        pass


def run():
    exe = find_cloudflared()
    if not exe:
        print("NO_CLOUDFLARED", flush=True)
        print(
            "Install Cloudflare Tunnel (cloudflared), then reopen Fennsill for a phone/cloud link.",
            flush=True,
        )
        return 2

    clear_url()
    cmd = [exe, "tunnel", "--url", LOCAL, "--no-autoupdate"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    found = None
    try:
        deadline = time.time() + 45
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                match = URL_RE.search(line)
                if match and not found:
                    found = match.group(0)
                    write_url(found)
        if not found:
            print("TUNNEL_URL_TIMEOUT", flush=True)
            proc.kill()
            return 1
        # Keep the tunnel alive; Fennsill.exe kills this process on exit.
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
    finally:
        clear_url()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(run())
