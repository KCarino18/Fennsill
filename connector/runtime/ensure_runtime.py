"""Bootstrap Python + pyserial/playwright + Chromium for FennSill Agent.

Run elevated from FennsillSetup after payload copy. Exits non-zero on failure.
Writes %ProgramData%\\Fennsill\\python_path.txt for the Windows service.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
BROWSERS = ROOT / "connector" / "browsers"
PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData") / "Fennsill"
PYTHON_PATH_FILE = PROGRAM_DATA / "python_path.txt"


def log(msg: str) -> None:
    print(msg, flush=True)


def fail(msg: str, code: int = 1) -> None:
    log(f"ERROR: {msg}")
    raise SystemExit(code)


def is_windowsapps(path: Path) -> bool:
    return "windowsapps" in str(path).lower()


def looks_like_python(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".exe" and not is_windowsapps(path)


def run(cmd: list[str], *, env: dict | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    log("+ " + " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def find_existing_python() -> Path | None:
    candidates: list[Path] = []
    if sys.executable:
        candidates.append(Path(sys.executable))
    for name in ("python", "py"):
        which = shutil.which(name)
        if which:
            candidates.append(Path(which))
    local = Path(os.environ.get("LOCALAPPDATA") or "")
    if local:
        candidates.extend(
            [
                local / "Python" / "pythoncore-3.14-64" / "python.exe",
                local / "Python" / "pythoncore-3.13-64" / "python.exe",
                local / "Python" / "pythoncore-3.12-64" / "python.exe",
                local / "Python" / "bin" / "python.exe",
                local / "Programs" / "Python" / "Python312" / "python.exe",
                local / "Programs" / "Python" / "Python313" / "python.exe",
            ]
        )
    for base in (
        Path(r"C:\Python312\python.exe"),
        Path(r"C:\Python313\python.exe"),
    ):
        candidates.append(base)

    seen: set[str] = set()
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen or not looks_like_python(resolved):
            continue
        seen.add(key)
        # `py` launcher is ok if it runs - but prefer real python.exe
        if resolved.name.lower() == "py.exe":
            probe = run([str(resolved), "-3", "-c", "import sys; print(sys.executable)"])
            if probe.returncode == 0:
                exe = Path((probe.stdout or "").strip().splitlines()[0].strip())
                if looks_like_python(exe):
                    return exe
            continue
        probe = run([str(resolved), "-c", "import sys; print(sys.version)"])
        if probe.returncode == 0:
            return resolved
    return None


def install_python_winget() -> bool:
    winget = shutil.which("winget")
    if not winget:
        log("winget not found")
        return False
    proc = run(
        [
            winget,
            "install",
            "-e",
            "--id",
            "Python.Python.3.12",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
        ],
        timeout=900,
    )
    log((proc.stdout or "")[-2000:])
    log((proc.stderr or "")[-1000:])
    # winget returns 0 on success; -1978335189 sometimes means already installed
    return proc.returncode in (0, -1978335189, 0x8A150005)


def install_python_msi() -> bool:
    """Silent official embeddable-less installer fallback."""
    url = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    dest = Path(os.environ.get("TEMP") or ".") / "fennsill-python-installer.exe"
    log(f"Downloading {url}")
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as exc:
        log(f"download failed: {exc}")
        return False
    # Install for all users into Program Files; Include PATH.
    proc = run(
        [
            str(dest),
            "/quiet",
            "InstallAllUsers=1",
            "PrependPath=1",
            "Include_test=0",
            "Include_launcher=1",
        ],
        timeout=900,
    )
    log((proc.stdout or "")[-1000:])
    log((proc.stderr or "")[-1000:])
    return proc.returncode == 0


def ensure_python() -> Path:
    existing = find_existing_python()
    if existing:
        log(f"Found Python: {existing}")
        return existing
    log("Python not found — installing…")
    if not install_python_winget():
        log("winget install failed or unavailable — trying python.org installer")
        if not install_python_msi():
            fail("Could not install Python. Install Python 3.12+ manually, then re-run FennSill Setup.")
    # PATH may not refresh in this process; search again with common locations.
    for _ in range(10):
        found = find_existing_python()
        if found:
            log(f"Installed Python: {found}")
            return found
        time.sleep(2)
    # Common post-winget path
    for cand in Path(os.environ.get("LOCALAPPDATA") or "").glob(
        "Programs/Python/Python3*/python.exe"
    ):
        if looks_like_python(cand):
            return cand
    fail("Python installed but could not locate python.exe. Reboot and re-run Setup.")


def pip_install(py: Path) -> None:
    env = os.environ.copy()
    for args in (
        [str(py), "-m", "pip", "install", "--upgrade", "pip"],
        [str(py), "-m", "pip", "install", "pyserial>=3.5", "playwright>=1.40"],
    ):
        proc = run(args, env=env, timeout=600)
        if proc.returncode != 0:
            log(proc.stdout or "")
            log(proc.stderr or "")
            fail(f"pip failed: {' '.join(args[3:])}")


def install_chromium(py: Path) -> None:
    """Install full Chromium + headless shell (Playwright 1.49+ needs both)."""
    BROWSERS.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS)
    # Default `chromium` includes headless shell unless --no-shell is passed.
    # Force when the shell is missing so a partial tree gets repaired.
    force = headless_shell_exe() is None or chrome_exe() is None
    for browser in ("chromium", "chromium-headless-shell"):
        cmd = [str(py), "-m", "playwright", "install", browser]
        if force:
            cmd.append("--force")
        proc = run(cmd, env=env, timeout=900)
        if proc.returncode != 0:
            log(proc.stdout or "")
            log(proc.stderr or "")
            fail(f"playwright install {browser} failed")


def _first_exe(name: str) -> Path | None:
    if not BROWSERS.is_dir():
        return None
    matches = list(BROWSERS.rglob(name))
    return matches[0] if matches else None


def chrome_exe() -> Path | None:
    return _first_exe("chrome.exe")


def headless_shell_exe() -> Path | None:
    return _first_exe("chrome-headless-shell.exe")


def verify(py: Path) -> None:
    proc = run(
        [str(py), "-c", "import serial, playwright; print('ok')"],
        timeout=60,
    )
    if proc.returncode != 0:
        log(proc.stdout or "")
        log(proc.stderr or "")
        fail("verify import serial, playwright failed")
    chrome = chrome_exe()
    if chrome is None:
        fail(f"Chromium chrome.exe not found under {BROWSERS}")
    log(f"Chromium OK: {chrome}")
    shell = headless_shell_exe()
    if shell is None:
        fail(
            f"Playwright chrome-headless-shell.exe not found under {BROWSERS}. "
            "Page render will fail until Setup finishes installing browsers."
        )
    log(f"Headless shell OK: {shell}")
    push = ROOT / "connector" / "push_page.py"
    agent = ROOT / "connector" / "runtime" / "cloud_agent.py"
    if not push.is_file():
        fail(f"missing {push}")
    if not agent.is_file():
        fail(f"missing {agent}")


def write_python_path(py: Path) -> None:
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
    PYTHON_PATH_FILE.write_text(str(py.resolve()) + "\n", encoding="utf-8")
    log(f"Wrote {PYTHON_PATH_FILE}")


def main() -> int:
    log(f"FENNSILL_ROOT={ROOT}")
    py = ensure_python()
    pip_install(py)
    install_chromium(py)
    verify(py)
    write_python_path(py)
    log("ensure_runtime: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        fail(str(exc))
