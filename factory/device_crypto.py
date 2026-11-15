"""Device serial + secret derivation for Fennsill Factory (not Fennsill.exe)."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_MASTER_PATH = ROOT / "master.key"
LEDGER_PATH = ROOT / "ledger" / "devices.csv"

SERIAL_RE = re.compile(r"^FS-\d{4}-\d{6}$")


def ensure_master(path: Path | None = None) -> Path:
    """Create factory/master.key on first use (offline secret — never ship to buyers)."""
    import secrets

    path = path or Path(os.environ.get("FENNSILL_FACTORY_MASTER", DEFAULT_MASTER_PATH))
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(secrets.token_bytes(32))
        print(f"Created factory master key: {path}", flush=True)
    return path


def load_master(path: Path | None = None) -> bytes:
    path = ensure_master(path)
    raw = path.read_bytes().strip()
    if len(raw) == 64 and all(c in b"0123456789abcdefABCDEF" for c in raw):
        return bytes.fromhex(raw.decode("ascii"))
    if len(raw) < 16:
        raise ValueError("master.key must be at least 16 bytes (or 64 hex chars)")
    return raw


def device_secret(master: bytes, device_id: str) -> str:
    """64-hex HMAC locked into the panel at factory. Same device_id → same secret forever."""
    msg = f"fennsill-device-v1|{device_id.strip().upper()}".encode("ascii")
    return hmac.new(master, msg, hashlib.sha256).hexdigest()


def key_fingerprint(secret_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(secret_hex)).hexdigest()[:32]


def install_bind_key(device_id: str, serial: str, proof_hex: str) -> str:
    """PC-side key for this panel's Fennsill bind file (not the raw device secret)."""
    msg = f"fennsill-install-v1|{device_id}|{serial}|{proof_hex}".encode("utf-8")
    return hashlib.sha256(msg).hexdigest()


def next_box_serial(ledger: Path | None = None, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    yymm = when.strftime("%y%m")
    prefix = f"FS-{yymm}-"
    seq = 1
    path = ledger or LEDGER_PATH
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split(",")
            if not parts:
                continue
            serial = parts[0].strip()
            if serial.startswith(prefix):
                try:
                    seq = max(seq, int(serial.rsplit("-", 1)[-1]) + 1)
                except ValueError:
                    pass
    return f"{prefix}{seq:06d}"


def append_ledger(
    *,
    serial: str,
    device_id: str,
    key_fp: str,
    fw_version: str,
    port: str,
    secret_hex: str | None = None,
    ledger: Path | None = None,
    secrets_ledger: Path | None = None,
) -> None:
    path = ledger or LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(
            "box_serial,device_id,key_fingerprint,fw_version,port,provisioned_at_utc\n",
            encoding="utf-8",
        )
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{serial},{device_id},{key_fp},{fw_version},{port},{stamp}\n")
    if secret_hex:
        sec = secrets_ledger or (path.parent / "device_secrets.csv")
        if not sec.is_file():
            sec.write_text(
                "box_serial,device_id,device_secret_hex,provisioned_at_utc\n",
                encoding="utf-8",
            )
            # Keep offline; never ship this file to buyers.
        with sec.open("a", encoding="utf-8") as fh:
            fh.write(f"{serial},{device_id},{secret_hex},{stamp}\n")
