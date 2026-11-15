"""First-plug bind: read panel serial / id, prove device key, write local Artiphact bind file.

Runs after install so the buyer's PC shows the permanent serial and gets a
device-bound install key. Does not change the panel serial.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("ARTIPHACT_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "connector"))

from panel_ports import confirmed_panels, panel_absence_message, scan_panels  # noqa: E402
from serial_guard import SerialGuard  # noqa: E402

BIND_PATH = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "Artiphact" / "device_bind.json"


def _open(port: str):
    import serial

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = 0.2
    ser.write_timeout = 3
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def _line(ser, timeout=6.0) -> str:
    deadline = time.time() + timeout
    buf = b""
    while time.time() < deadline:
        n = getattr(ser, "in_waiting", 0) or 0
        chunk = ser.read(n or 1)
        if chunk:
            buf += chunk
            if b"\n" in buf:
                line, _, _ = buf.partition(b"\n")
                return line.decode("ascii", "replace").strip()
        else:
            time.sleep(0.02)
    return buf.decode("ascii", "replace").strip()


def _ask(ser, cmd: str) -> str:
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode("ascii"))
    ser.flush()
    return _line(ser)


def bind(port: str | None = None) -> dict:
    scan = scan_panels(timeout=2.0)
    msg = panel_absence_message(scan)
    if msg:
        raise RuntimeError(msg)
    ready = scan["ready"]
    if port is None:
        port = ready[0]["port"]

    with SerialGuard(timeout=15):
        ser = _open(port)
        try:
            _ask(ser, "HELLO")
            ident = _ask(ser, "ID?")
            device_id = ident[3:].strip().upper() if ident.startswith("ID ") else ""
            serial_line = _ask(ser, "SERIAL?")
            serial = serial_line[7:].strip() if serial_line.startswith("SERIAL ") else device_id
            status = _ask(ser, "STATUS")
            key = _ask(ser, "KEY?")
            nonce = secrets.token_hex(16)
            proof_line = _ask(ser, f"CHALLENGE {nonce}")
            proof = proof_line[6:].strip().lower() if proof_line.startswith("PROOF ") else ""
            if not proof:
                raise RuntimeError(
                    f"Panel has no factory key yet (got {proof_line!r}). "
                    "Provision it with Artiphact Factory before shipping."
                )
            install_key = hashlib.sha256(
                f"artiphact-install-v1|{device_id}|{serial}|{proof}".encode("utf-8")
            ).hexdigest()
            payload = {
                "device_id": device_id,
                "serial": serial,
                "key_locked": "locked" in key,
                "status": status,
                "challenge_nonce": nonce,
                "challenge_proof": proof,
                "install_key": install_key,
                "port": port,
            }
            BIND_PATH.parent.mkdir(parents=True, exist_ok=True)
            BIND_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return payload
        finally:
            ser.close()


def main() -> int:
    try:
        info = bind()
    except Exception as exc:
        print(f"Bind skipped: {exc}")
        return 1
    print()
    print(" Your Artiphact panel")
    print(f"   Serial:    {info['serial']}")
    print(f"   Device ID: {info['device_id']}")
    print(f"   Bound to:  {BIND_PATH}")
    print()
    print(" This serial stays the same on every PC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
