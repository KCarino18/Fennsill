"""Download arduino-cli into factory/tools and install the ESP32 core + libs.

Used by Fennsill Factory so Flash works without a manual PATH install.
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
    # Zip may nest or place exe at top level
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


def ensure_core_and_libs(arduino: str) -> None:
    env = cli_env()
    # Point board manager at Espressif packages (XIAO ESP32-S3 Plus lives here).
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
    # Seeed_GFX (TFT_eSPI.h + EE04 e-ink) — GitHub, not Library Manager name.
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
    marker = DATA_DIR / ".fennsill_core_ready_v2"
    if not marker.is_file():
        print("Installing ESP32 board support + Seeed_GFX (one-time)…", flush=True)
        ensure_core_and_libs(arduino)
        marker.write_text("ok\n", encoding="utf-8")
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
