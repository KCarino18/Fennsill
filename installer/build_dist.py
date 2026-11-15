"""Build website zip + USB folder: dist/Fennsill + dist/Fennsill-Setup.zip"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "Fennsill"
ZIP = ROOT / "dist" / "Fennsill-Setup.zip"
SKIP_DIRS = {"__pycache__", "pages", "inbox", "browsers", "bin"}


def copy_tree(src: Path, dst: Path):
    if not src.is_dir():
        return
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    exe = ROOT / "Fennsill.exe"
    if not exe.is_file():
        exe = ROOT / "fennsill-desk" / "out" / "Fennsill.exe"
    if not exe.is_file():
        raise SystemExit("Fennsill.exe missing — publish the desk app first.")
    shutil.copy2(exe, OUT / "Fennsill.exe")

    host = ROOT / "FennsillHost.exe"
    if not host.is_file():
        host = ROOT / "fennsill-host" / "out" / "FennsillHost.exe"
    if not host.is_file():
        raise SystemExit("FennsillHost.exe missing — publish fennsill-host first.")
    shutil.copy2(host, OUT / "FennsillHost.exe")

    setup_exe = ROOT / "fennsill-setup" / "out" / "FennsillSetup.exe"
    if not setup_exe.is_file():
        raise SystemExit("FennsillSetup.exe missing — publish fennsill-setup first.")
    shutil.copy2(setup_exe, OUT / "FennsillSetup.exe")

    shutil.copy2(ROOT / "installer" / "Install-Fennsill.ps1", OUT / "Install-Fennsill.ps1")
    copy_tree(ROOT / "connector", OUT / "connector")
    copy_tree(ROOT / "templates", OUT / "templates")
    copy_tree(ROOT / "firmware", OUT / "firmware")

    (OUT / "FennsillSetup.bat").write_text(
        "\r\n".join(
            [
                "@echo off",
                "title Fennsill Setup",
                'cd /d "%~dp0"',
                "echo.",
                "echo  FENNSILL SETUP",
                "echo  Prefer FennsillSetup.exe - this .bat is a fallback.",
                "echo.",
                'if exist "%~dp0FennsillSetup.exe" (',
                '  start "" "%~dp0FennsillSetup.exe"',
                "  exit /b 0",
                ")",
                'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Fennsill.ps1"',
                "if errorlevel 1 (",
                "  echo Setup failed.",
                "  pause",
                "  exit /b 1",
                ")",
                "echo.",
                "echo Installed. You can close this window.",
                "timeout /t 4 >nul",
                "",
            ]
        ),
        encoding="ascii",
    )
    (OUT / "README.txt").write_text(
        "\r\n".join(
            [
                "FENNSILL",
                "",
                "1. Unzip this folder (website) or open it on the USB stick.",
                "2. Double-click FennsillSetup.exe",
                "3. Open Fennsill.exe (panel desk).",
                "4. Open FennsillHost.exe: Start server, Start public link, Copy MCP URL",
                "   into Claude Connectors or ChatGPT custom MCP (No sign-in).",
                "5. Copy panel prompt from Host and paste in a new chat with Fennsill enabled.",
                "",
                "FennsillSetup.bat is only a fallback if the .exe is blocked.",
                "",
            ]
        ),
        encoding="ascii",
    )

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in OUT.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(OUT).as_posix())

    desktop = Path.home() / "Desktop" / "FennsillSetup.bat"
    shutil.copy2(OUT / "FennsillSetup.bat", desktop)
    # Desktop bat won't find payload — also copy a desktop helper that points at dist
    desktop.write_text(
        "\r\n".join(
            [
                "@echo off",
                f'cd /d "{OUT}"',
                "call FennsillSetup.bat",
            ]
        ),
        encoding="ascii",
    )

    print("USB/folder:", OUT)
    print("Website zip:", ZIP, ZIP.stat().st_size, "bytes")
    print("Desktop:", desktop)


if __name__ == "__main__":
    main()
