"""Sign a firmware file for the daily update check.

The signature is HMAC-SHA256 over the version and the file hash. The same
key is compiled into the panel. A file with no valid signature is refused.
"""

import hashlib
import hmac
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATES = Path(__file__).resolve().parent
KEY_PATH = UPDATES / "update_key.hex"
HEADER_PATH = ROOT / "firmware" / "fennsill" / "update_key.h"
MANIFEST_PATH = UPDATES / "manifest.json"
DEFAULT_BIN = UPDATES / "fennsill-1.1.0.bin"
VERSION = "1.1.0"
FILE_URL = "https://updates.fennsill.com/fennsill-1.1.0.bin"


def load_key():
    if not KEY_PATH.exists():
        KEY_PATH.write_text(
            "9f3c1a7e5b20d84c6a11e0f7b3924d58c6e1aa70d3b84f1290ab66c4de781503",
            encoding="utf-8",
        )
    key = bytes.fromhex(KEY_PATH.read_text(encoding="utf-8").strip())
    if len(key) != 32:
        raise SystemExit("Update key must be 32 bytes.")
    return key


def sign(version, digest, key):
    message = f"{version}\n{digest}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def write_header(key):
    cells = ", ".join(f"0x{byte:02x}" for byte in key)
    HEADER_PATH.write_text(
        "#pragma once\nstatic const uint8_t UPDATE_KEY[32] = { " + cells + " };\n",
        encoding="utf-8",
    )


def main():
    key = load_key()
    if not DEFAULT_BIN.exists():
        DEFAULT_BIN.write_bytes(b"FENNSILL-FIRMWARE-1.1.0\n" * 16)
    digest = hashlib.sha256(DEFAULT_BIN.read_bytes()).hexdigest()
    manifest = {
        "version": VERSION,
        "url": FILE_URL,
        "sha256": digest,
        "signature": sign(VERSION, digest, key),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_header(key)
    print(MANIFEST_PATH)


if __name__ == "__main__":
    main()
