"""Build website zip + USB folder: dist/Fennsill + dist/Fennsill-Setup.zip

Also stages factory next to the buyer payload so manufacturing tools are not
missing from the download (dist/factory + factory/ inside the zip).
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "Fennsill"
FACTORY_OUT = ROOT / "dist" / "factory"
ZIP = ROOT / "dist" / "Fennsill-Setup.zip"
SKIP_DIRS = {"__pycache__", "pages", "inbox", "browsers", "bin", "tools"}
SKIP_NAMES = {
    "bridge_token.txt",
    "public_url.txt",
    "master.key",
    "device_secrets.csv",
    "_exe_check.txt",
    "fennsill-debug.log",
}


def copy_tree(src: Path, dst: Path):
    if not src.is_dir():
        return
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.name.lower() in SKIP_NAMES or path.name.lower().endswith(".log"):
            continue
        if path.suffix.lower() == ".csv" and "ledger" in rel.parts:
            continue
        if path.suffix.lower() in {".pdb", ".dll"} and "factory" in str(src).lower():
            # Skip publish sidecars; keep .exe / scripts / README
            if path.name.lower() != "fennsillfactory.exe":
                continue
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def find_desk_exe() -> Path:
    for cand in (
        ROOT / "Fennsill.exe",
        ROOT / "fennsill-desk" / "out" / "Fennsill.exe",
        ROOT / "fennsill-desk" / "out" / "FennsillDesk.exe",
        ROOT / "releases" / "desk" / "Fennsill.exe",
        ROOT / "releases" / "desk" / "FennsillDesk.exe",
    ):
        if cand.is_file():
            return cand
    raise SystemExit("Fennsill.exe / FennsillDesk.exe missing — publish the desk app first.")


def find_setup_exe() -> Path | None:
    for cand in (
        ROOT / "fennsill-setup" / "out" / "FennsillSetup.exe",
        ROOT / "releases" / "setup" / "FennsillSetup.exe",
        ROOT / "FennsillSetup.exe",
    ):
        if cand.is_file():
            return cand
    return None


def find_factory_exe() -> Path | None:
    for cand in (
        ROOT / "factory" / "FennsillFactory.exe",
        ROOT / "releases" / "factory" / "FennsillFactory.exe",
        ROOT / "FennsillFactory.exe",
    ):
        if cand.is_file():
            return cand
    return None


def find_install_ps1() -> Path:
    # Prefer Desk name — some PCs/AV block creating Install-Fennsill.ps1.
    for cand in (
        ROOT / "installer" / "Install-FennsillDesk.ps1",
        ROOT / "installer" / "Install-Fennsill.ps1",
    ):
        if cand.is_file():
            return cand
    raise SystemExit("Install-FennsillDesk.ps1 missing.")


def merge_connector(dst: Path) -> None:
    """Copy connector/, then fill gaps from connector/runtime/ (AV-blocked names)."""
    copy_tree(ROOT / "connector", dst)
    runtime = ROOT / "connector" / "runtime"
    if not runtime.is_dir():
        return
    for path in runtime.glob("*.py"):
        target = dst / path.name
        if not target.is_file():
            shutil.copy2(path, target)
    # Keep runtime/ as well for Desk ResolveConnectorScript fallbacks.
    copy_tree(runtime, dst / "runtime")


def stage_factory() -> None:
    """Buyer/operator download should include factory/ next to the project payload."""
    if FACTORY_OUT.exists():
        shutil.rmtree(FACTORY_OUT)
    FACTORY_OUT.mkdir(parents=True)
    copy_tree(ROOT / "factory", FACTORY_OUT)
    # Standalone C:\factory needs panel_ports + sketch without the full repo.
    copy_tree(ROOT / "firmware", FACTORY_OUT / "firmware")
    # Never ship master key / secret ledgers
    for banned in ("master.key",):
        p = FACTORY_OUT / banned
        if p.exists():
            p.unlink()
    secrets = FACTORY_OUT / "ledger" / "device_secrets.csv"
    if secrets.exists():
        secrets.unlink()
    exe = find_factory_exe()
    nested = OUT / "factory"
    nested.mkdir(parents=True, exist_ok=True)
    if exe:
        shutil.copy2(exe, FACTORY_OUT / "FennsillFactory.exe")
    else:
        print("WARN: FennsillFactory.exe not built — factory scripts copied without exe.")
    # Also nest under buyer zip so unzipping one archive has factory beside apps.
    copy_tree(FACTORY_OUT, nested)


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    desk = find_desk_exe()
    # Always ship as Fennsill.exe in the zip (AssemblyName may be FennsillDesk locally).
    shutil.copy2(desk, OUT / "Fennsill.exe")
    if desk.name.lower() == "fennsilldesk.exe":
        shutil.copy2(desk, OUT / "FennsillDesk.exe")

    setup_exe = find_setup_exe()
    if setup_exe:
        shutil.copy2(setup_exe, OUT / "FennsillSetup.exe")
    else:
        print("WARN: FennsillSetup.exe missing — bat/ps1 fallback only.")

    install_ps1 = find_install_ps1()
    # Ship both names when possible; Desk name is the reliable one under AV locks.
    shutil.copy2(install_ps1, OUT / "Install-FennsillDesk.ps1")
    try:
        shutil.copy2(install_ps1, OUT / "Install-Fennsill.ps1")
    except OSError as exc:
        print(f"WARN: could not write Install-Fennsill.ps1 ({exc}) — bat will use Desk name.")

    merge_connector(OUT / "connector")
    copy_tree(ROOT / "templates", OUT / "templates")
    copy_tree(ROOT / "firmware", OUT / "firmware")

    stage_factory()

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
                'set PS1=%~dp0Install-FennsillDesk.ps1',
                'if not exist "%PS1%" set PS1=%~dp0Install-Fennsill.ps1',
                'powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"',
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
                "BUYER PC",
                "1. Unzip this folder (website) or open it on the USB stick.",
                "2. Double-click FennsillSetup.exe (or FennsillSetup.bat).",
                "3. Open Fennsill.exe (panel desk) - copy Device ID into the website",
                "   Link your panel form (not into ChatGPT/Claude MCP).",
                "4. Cloud MCP (ChatGPT / Claude Connect to custom MCP):",
                "   - URL = MCP URL from the Fennsill account site",
                "   - Leave Bearer token env-var empty if the form asks for one",
                "   - Headers: Authorization = Bearer <token> (Copy header)",
                "   There is no local Host app - cloud MCP only.",
                "",
                "FACTORY / MANUFACTURING",
                "This download includes a factory\\ folder (scripts + FennsillFactory.exe when built).",
                "You can also copy that folder to C:\\factory on the factory PC.",
                "Or download FennsillFactory.exe from GitHub Releases and keep it next to factory\\.",
                "Open FennsillFactory.exe (or factory\\Run-Factory.bat) -> Check -> Flash.",
                "",
                "Cloud uses SQLite - no SQL Server required.",
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
    print("Factory folder:", FACTORY_OUT)
    print("Website zip:", ZIP, ZIP.stat().st_size, "bytes")
    print("Desktop:", desktop)


if __name__ == "__main__":
    main()
