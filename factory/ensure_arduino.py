"""Download arduino-cli into factory/tools and install the ESP32 core + libs.

Used by Fennsill Factory so Flash works without a manual PATH install.
If a previous install is half-broken, Flash wipes it and reinstalls cleanly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"
CLI_DIR = TOOLS / "arduino-cli"
CLI_EXE = CLI_DIR / "arduino-cli.exe"
DATA_DIR = TOOLS / "arduino-data"
ZIP_URL = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip"
FQBN = "esp32:esp32:XIAO_ESP32S3_Plus"
ESP32_INDEX = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"
MARKER = DATA_DIR / ".fennsill_core_ready_v3"


def writable_temp_dir() -> Path:
    """Prefer LocalAppData — Bitdefender's virtual disk rejects writes like virtual_file.log."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        path = Path(local) / "FennsillApp" / "tmp"
    else:
        path = ROOT / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def harden_process_paths() -> Path:
    """Keep flash tools off AV sandbox / read-only volumes."""
    tmp = writable_temp_dir()
    os.environ["TEMP"] = str(tmp)
    os.environ["TMP"] = str(tmp)
    os.environ["TMPDIR"] = str(tmp)
    try:
        os.chdir(ROOT)
    except OSError:
        pass
    return tmp


def _run(cmd: list[str], **kwargs) -> None:
    harden_process_paths()
    kwargs.setdefault("cwd", str(ROOT))
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kwargs)


def _run_out(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    harden_process_paths()
    kwargs.setdefault("cwd", str(ROOT))
    kwargs.setdefault("text", True)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("check", False)
    return subprocess.run(cmd, **kwargs)


def find_arduino_cli() -> str | None:
    if CLI_EXE.is_file():
        return str(CLI_EXE)
    which = shutil.which("arduino-cli")
    return which


def download_arduino_cli() -> str:
    TOOLS.mkdir(parents=True, exist_ok=True)
    if CLI_EXE.is_file():
        return str(CLI_EXE)
    zip_path = TOOLS / "arduino-cli.zip"
    print("Downloading arduino-cli…", flush=True)
    urlretrieve(ZIP_URL, zip_path)
    CLI_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(CLI_DIR)
    zip_path.unlink(missing_ok=True)
    if not CLI_EXE.is_file():
        for path in CLI_DIR.rglob("arduino-cli.exe"):
            if path != CLI_EXE:
                shutil.copy2(path, CLI_EXE)
                break
    if not CLI_EXE.is_file():
        raise RuntimeError(f"arduino-cli.exe missing after download in {CLI_DIR}")
    print(f"Installed {CLI_EXE}", flush=True)
    return str(CLI_EXE)


def cli_env() -> dict[str, str]:
    tmp = harden_process_paths()
    env = os.environ.copy()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)
    env["TMPDIR"] = str(tmp)
    env["ARDUINO_DIRECTORIES_DATA"] = str(DATA_DIR)
    env["ARDUINO_DIRECTORIES_DOWNLOADS"] = str(DATA_DIR / "staging")
    env["ARDUINO_DIRECTORIES_USER"] = str(DATA_DIR / "user")
    (DATA_DIR / "user" / "libraries").mkdir(parents=True, exist_ok=True)
    return env


def wipe_arduino_data(*, keep_cli: bool = True) -> None:
    """Delete a half-installed board pack so Flash can reinstall cleanly."""
    print("Wiping old Arduino board install…", flush=True)
    MARKER.unlink(missing_ok=True)
    # Old marker names from earlier Factory builds.
    for stale in DATA_DIR.glob(".fennsill_core_ready*"):
        stale.unlink(missing_ok=True)
    for name in ("packages", "staging", "tmp", "inventory.yaml"):
        path = DATA_DIR / name
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)
    # Legacy folder name from older builds.
    legacy = TOOLS / "arduino-cli-data"
    if legacy.exists():
        shutil.rmtree(legacy, ignore_errors=True)
    if not keep_cli and CLI_DIR.exists():
        shutil.rmtree(CLI_DIR, ignore_errors=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def fqbn_ready(arduino: str) -> bool:
    """True when the XIAO ESP32-S3 Plus board pack is actually installed."""
    env = cli_env()
    # Platform must show up in core list.
    cores = _run_out([arduino, "core", "list"], env=env)
    if cores.returncode != 0 or "esp32:esp32" not in (cores.stdout or ""):
        return False
    # Hardware tree must exist (partial downloads often leave tools/ but no hardware/).
    hardware = DATA_DIR / "packages" / "esp32" / "hardware" / "esp32"
    if not hardware.is_dir():
        return False
    s3_libs = DATA_DIR / "packages" / "esp32" / "tools" / "esp32s3-libs"
    if not s3_libs.is_dir():
        return False
    details = _run_out([arduino, "board", "details", "-b", FQBN], env=env)
    return details.returncode == 0


def seeed_gfx_ready() -> bool:
    lib = DATA_DIR / "user" / "libraries"
    if not lib.is_dir():
        return False
    for path in lib.iterdir():
        if path.is_dir() and path.name.lower().startswith("seeed"):
            if (path / "TFT_eSPI.h").is_file() or (path / "src" / "TFT_eSPI.h").is_file():
                return True
            # Seeed_GFX repo layout varies; accept any installed Seeed_* tree.
            return True
    return False


def ensure_core_and_libs(arduino: str) -> None:
    env = cli_env()
    _run(
        [
            arduino,
            "config",
            "init",
            "--overwrite",
            "--additional-urls",
            ESP32_INDEX,
        ],
        env=env,
    )
    _run([arduino, "config", "set", "library.enable_unsafe_install", "true"], env=env)
    _run([arduino, "core", "update-index"], env=env)
    _run([arduino, "core", "install", "esp32:esp32"], env=env)
    if not seeed_gfx_ready():
        try:
            _run(
                [
                    arduino,
                    "lib",
                    "install",
                    "--git-url",
                    "https://github.com/Seeed-Studio/Seeed_GFX.git",
                ],
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            print(f"Seeed_GFX install failed: {exc}", flush=True)
            raise


def ensure_arduino() -> str:
    arduino = find_arduino_cli()
    if not arduino:
        arduino = download_arduino_cli()

    if MARKER.is_file() and fqbn_ready(arduino):
        return arduino

    # Marker missing, or leftover half-install from a failed Flash — wipe and redo.
    if DATA_DIR.exists() and (
        (DATA_DIR / "packages").exists()
        or (DATA_DIR / "staging").exists()
        or any(DATA_DIR.glob(".fennsill_core_ready*"))
    ):
        if not fqbn_ready(arduino):
            wipe_arduino_data(keep_cli=True)
            arduino = find_arduino_cli() or download_arduino_cli()

    print("Installing ESP32 board support + Seeed_GFX (one-time)…", flush=True)
    try:
        ensure_core_and_libs(arduino)
    except Exception:
        print("Board install failed — wiping and retrying once…", flush=True)
        wipe_arduino_data(keep_cli=True)
        arduino = find_arduino_cli() or download_arduino_cli()
        ensure_core_and_libs(arduino)

    if not fqbn_ready(arduino):
        wipe_arduino_data(keep_cli=True)
        raise RuntimeError(
            "ESP32 board pack still incomplete after reinstall. "
            "Allow/exclude %LOCALAPPDATA%\\FennsillApp in antivirus, then Flash again."
        )

    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text("ok\n", encoding="utf-8")
    return arduino


def main() -> int:
    path = ensure_arduino()
    print("arduino-cli:", path)
    _run([path, "version"], env=cli_env())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
