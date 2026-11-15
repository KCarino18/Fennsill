"""Build website zip + USB folder: dist/Artiphact + dist/Artiphact-Setup.zip"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "Artiphact"
ZIP = ROOT / "dist" / "Artiphact-Setup.zip"
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

    exe = ROOT / "Artiphact.exe"
    if not exe.is_file():
        exe = ROOT / "artiphact-desk" / "out" / "Artiphact.exe"
    if not exe.is_file():
        raise SystemExit("Artiphact.exe missing — publish the desk app first.")
    shutil.copy2(exe, OUT / "Artiphact.exe")

    host = ROOT / "ArtiphactHost.exe"
    if not host.is_file():
        host = ROOT / "artiphact-host" / "out" / "ArtiphactHost.exe"
    if not host.is_file():
        raise SystemExit("ArtiphactHost.exe missing — publish artiphact-host first.")
    shutil.copy2(host, OUT / "ArtiphactHost.exe")

    setup_exe = ROOT / "artiphact-setup" / "out" / "ArtiphactSetup.exe"
    if not setup_exe.is_file():
        raise SystemExit("ArtiphactSetup.exe missing — publish artiphact-setup first.")
    shutil.copy2(setup_exe, OUT / "ArtiphactSetup.exe")

    shutil.copy2(ROOT / "installer" / "Install-Artiphact.ps1", OUT / "Install-Artiphact.ps1")
    copy_tree(ROOT / "connector", OUT / "connector")
    copy_tree(ROOT / "templates", OUT / "templates")
    copy_tree(ROOT / "firmware", OUT / "firmware")

    (OUT / "ArtiphactSetup.bat").write_text(
        "\r\n".join(
            [
                "@echo off",
                "title Artiphact Setup",
                'cd /d "%~dp0"',
                "echo.",
                "echo  ARTIPHACT SETUP",
                "echo  Prefer ArtiphactSetup.exe - this .bat is a fallback.",
                "echo.",
                'if exist "%~dp0ArtiphactSetup.exe" (',
                '  start "" "%~dp0ArtiphactSetup.exe"',
                "  exit /b 0",
                ")",
                'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Artiphact.ps1"',
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
                "ARTIPHACT",
                "",
                "1. Unzip this folder (website) or open it on the USB stick.",
                "2. Double-click ArtiphactSetup.exe",
                "3. Open Artiphact.exe (panel desk).",
                "4. Open ArtiphactHost.exe: Start server, Start public link, Copy MCP URL",
                "   into Claude Connectors or ChatGPT custom MCP (No sign-in).",
                "5. Copy panel prompt from Host and paste in a new chat with Artiphact enabled.",
                "",
                "ArtiphactSetup.bat is only a fallback if the .exe is blocked.",
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

    desktop = Path.home() / "Desktop" / "ArtiphactSetup.bat"
    shutil.copy2(OUT / "ArtiphactSetup.bat", desktop)
    # Desktop bat won't find payload — also copy a desktop helper that points at dist
    desktop.write_text(
        "\r\n".join(
            [
                "@echo off",
                f'cd /d "{OUT}"',
                "call ArtiphactSetup.bat",
            ]
        ),
        encoding="ascii",
    )

    print("USB/folder:", OUT)
    print("Website zip:", ZIP, ZIP.stat().st_size, "bytes")
    print("Desktop:", desktop)


if __name__ == "__main__":
    main()
