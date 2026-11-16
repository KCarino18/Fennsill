"""Flash + provision one Fennsill panel. Separate from Fennsill.exe."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _repo_root() -> Path:
    """Project root that contains firmware/ (or factory/firmware/ when shipped alone)."""
    env = (os.environ.get("FENNSILL_ROOT") or "").strip()
    if env:
        p = Path(env)
        if (p / "firmware" / "panel_ports.py").is_file():
            return p
    # Normal repo: …/Fennsill/factory/provision.py → …/Fennsill
    parent = ROOT.parent
    if (parent / "firmware" / "panel_ports.py").is_file():
        return parent
    # Standalone C:\factory (or zip factory\) with firmware nested beside scripts
    if (ROOT / "firmware" / "panel_ports.py").is_file():
        return ROOT
    return parent


REPO = _repo_root()
sys.path.insert(0, str(REPO / "firmware"))
if (ROOT / "firmware").is_dir():
    sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT))

from device_crypto import (  # noqa: E402
    LEDGER_PATH,
    append_ledger,
    device_secret,
    key_fingerprint,
    load_master,
    next_box_serial,
)
from panel_ports import (  # noqa: E402
    assert_factory_flash_port,
    list_factory_flash_targets,
)

FQBN = "esp32:esp32:XIAO_ESP32S3_Plus"


def _sketch_path() -> Path:
    for base in (REPO, ROOT):
        cand = base / "firmware" / "fennsill" / "fennsill.ino"
        if cand.is_file():
            return cand
    return REPO / "firmware" / "fennsill" / "fennsill.ino"


SKETCH = _sketch_path()


def _read_line(ser, timeout=8.0) -> str:
    deadline = time.time() + timeout
    buf = b""
    while time.time() < deadline:
        waiting = getattr(ser, "in_waiting", 0) or 0
        chunk = ser.read(waiting or 1)
        if chunk:
            buf += chunk
            if b"\n" in buf:
                line, _, rest = buf.partition(b"\n")
                # Keep leftover bytes for the next read (multi-line bursts).
                if rest:
                    try:
                        ser._fennsill_buf = getattr(ser, "_fennsill_buf", b"") + rest
                    except Exception:
                        pass
                return line.decode("ascii", "replace").strip()
        else:
            pending = getattr(ser, "_fennsill_buf", b"")
            if pending and b"\n" in pending:
                line, _, rest = pending.partition(b"\n")
                ser._fennsill_buf = rest
                return line.decode("ascii", "replace").strip()
            time.sleep(0.02)
    return buf.decode("ascii", "replace").strip()


def _exchange(ser, command: str, timeout=8.0, expect: str | None = None) -> str:
    """Send a USB line and return a reply. If expect is set, skip banner noise until it matches."""
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    ser._fennsill_buf = b""
    ser.write((command.rstrip() + "\n").encode("ascii"))
    ser.flush()
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        last = _read_line(ser, timeout=min(2.0, max(0.1, deadline - time.time())))
        if not last:
            continue
        if expect is None:
            return last
        if last.startswith(expect) or last.startswith("ERR ") or last.startswith("NAK"):
            return last
        # Ignore READY / splash chatter between commands.
    return last


def open_port(port: str):
    import serial

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = 0.2
    ser.write_timeout = 3
    ser.dtr = False
    ser.rts = False
    ser.open()
    time.sleep(0.3)
    return ser


def wait_ready(ser, timeout=45.0) -> dict:
    deadline = time.time() + timeout
    ser.write(b"HELLO\n")
    ser.flush()
    info = {}
    while time.time() < deadline:
        line = _read_line(ser, timeout=2.0)
        if not line:
            ser.write(b"HELLO\n")
            continue
        if line.startswith("READY"):
            parts = line.split()
            if len(parts) >= 2:
                info["fw_version"] = parts[1]
            for token in parts[2:]:
                if "=" in token:
                    k, v = token.split("=", 1)
                    info[k] = v
            return info
    raise TimeoutError("Panel did not answer READY after flash. Check cable / boot.")


def read_identity(ser) -> dict:
    ready = wait_ready(ser)
    device_id = _exchange(ser, "ID?", expect="ID ")
    if device_id.startswith("ID "):
        device_id = device_id[3:].strip()
    else:
        device_id = ready.get("id") or ""
    serial_line = _exchange(ser, "SERIAL?", expect="SERIAL ")
    serial = serial_line[7:].strip() if serial_line.startswith("SERIAL ") else ready.get("serial") or device_id
    status = _exchange(ser, "STATUS", expect="STATUS ")
    key_line = _exchange(ser, "KEY?", expect="KEY ")
    return {
        "device_id": device_id.upper(),
        "serial": serial,
        "fw_version": ready.get("fw_version", ""),
        "status": status,
        "key": key_line,
        "ready": ready,
    }


def key_is_locked(key_line: str) -> bool:
    return key_line.strip().lower() == "key locked"


def _esptool_cmd(*args: str) -> list[str]:
    return [sys.executable, "-m", "esptool", *args]


def _run_esptool(args: list[str], *, env: dict[str, str]) -> None:
    print("+", " ".join(args), flush=True)
    try:
        subprocess.run(args, check=True, cwd=str(ROOT), env=env)
    except PermissionError as exc:
        raise PermissionError(_format_exc(exc)) from exc
    except OSError as exc:
        if getattr(exc, "errno", None) == 13 or "virtual_file.log" in str(exc).lower():
            raise PermissionError(_format_exc(exc)) from exc
        raise


def find_prebuilt_firmware() -> Path | None:
    """Full firmware image (merged) shipped with Factory — same sketch, already built."""
    names = (
        "fennsill.ino.merged.bin",
        "fennsill.merged.bin",
        "firmware.merged.bin",
    )
    roots = (
        ROOT / "prebuilt",
        ROOT / "firmware" / "prebuilt",
        REPO / "factory" / "prebuilt",
        REPO / "firmware" / "prebuilt",
    )
    for root in roots:
        if not root.is_dir():
            continue
        for name in names:
            cand = root / name
            if cand.is_file() and cand.stat().st_size > 100_000:
                return cand
        # Nested export-binaries folder
        for cand in root.rglob("*.merged.bin"):
            if cand.is_file() and cand.stat().st_size > 100_000:
                return cand
    return None


def erase_chip(port: str) -> None:
    """Full flash wipe — removes stock TRMNL (or any) firmware + NVS before Fennsill."""
    from ensure_arduino import cli_env, harden_process_paths

    harden_process_paths()
    env = cli_env()
    cmd = _esptool_cmd(
        "--chip",
        "esp32s3",
        "--port",
        port,
        "erase-flash",
    )
    print("Wiping chip (TRMNL/stock firmware + NVS):", " ".join(cmd))
    _run_esptool(cmd, env=env)
    time.sleep(1.5)


def flash_prebuilt(port: str, image: Path, *, erase: bool = True) -> None:
    """Write the complete prebuilt Fennsill firmware image (splash + app + USB)."""
    from ensure_arduino import cli_env, harden_process_paths

    harden_process_paths()
    env = cli_env()
    if erase:
        erase_chip(port)
    cmd = _esptool_cmd(
        "--chip",
        "esp32s3",
        "--port",
        port,
        "--baud",
        "921600",
        "write_flash",
        "0x0",
        str(image),
    )
    print(f"Installing FULL Fennsill firmware from prebuilt image:\n  {image}", flush=True)
    _run_esptool(cmd, env=env)


def flash_firmware(port: str, sketch: Path = SKETCH, fqbn: str = FQBN, *, erase: bool = True) -> None:
    from ensure_arduino import cli_env, ensure_arduino, harden_process_paths

    harden_process_paths()
    target = assert_factory_flash_port(port)
    print(f"Target OK: {target.get('kind')} — {target.get('reason')}")

    prebuilt = find_prebuilt_firmware()
    if prebuilt is not None:
        flash_prebuilt(port, prebuilt, erase=erase)
        return

    print("No prebuilt image — compiling FULL firmware with arduino-cli…", flush=True)
    arduino = ensure_arduino()
    if not sketch.is_file():
        raise FileNotFoundError(sketch)
    if erase:
        erase_chip(port)
    env = cli_env()
    cmd = [
        arduino,
        "compile",
        "--fqbn",
        fqbn,
        "--upload",
        "-p",
        port,
        str(sketch.parent),
    ]
    print("Installing Fennsill firmware:", " ".join(cmd), flush=True)
    try:
        subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)
    except PermissionError as exc:
        raise PermissionError(_format_exc(exc)) from exc



def lock_serial(ser, box_serial: str) -> None:
    reply = _exchange(ser, f"SERIALSET {box_serial}", expect="OK")
    if reply == "OK":
        return
    if "serial locked" in reply.lower():
        print(f"Serial already locked on device ({reply})")
        return
    raise RuntimeError(f"SERIALSET failed: {reply}")


def lock_key(ser, secret_hex: str) -> None:
    reply = _exchange(ser, f"KEYSET {secret_hex}", expect="OK")
    if reply == "OK":
        return
    if "key locked" in reply.lower():
        print(f"Key already locked on device ({reply})")
        return
    raise RuntimeError(f"KEYSET failed: {reply}")


def verify_challenge(ser, secret_hex: str) -> str:
    import hashlib
    import hmac as hm
    import secrets

    nonce = secrets.token_hex(16)
    reply = _exchange(ser, f"CHALLENGE {nonce}", expect="PROOF ")
    if reply.startswith("ERR ") and "key missing" in reply.lower():
        raise RuntimeError("key_missing")
    if not reply.startswith("PROOF "):
        raise RuntimeError(f"CHALLENGE failed: {reply}")
    proof = reply[6:].strip().lower()
    expect = hm.new(bytes.fromhex(secret_hex), nonce.encode("ascii"), hashlib.sha256).hexdigest()
    if proof != expect:
        raise RuntimeError("Device proof mismatch — key not locked correctly")
    return proof


def provision(
    port: str,
    *,
    flash: bool = True,
    box_serial: str | None = None,
    master_path: Path | None = None,
) -> dict:
    # Refuse random COM devices before any flash or KEYSET.
    assert_factory_flash_port(port)
    if flash:
        flash_firmware(port)
        time.sleep(2.0)

    master = load_master(master_path)
    ser = open_port(port)
    try:
        ident = read_identity(ser)
        device_id = ident["device_id"]
        if not device_id.startswith("FS") or len(device_id) < 10:
            raise RuntimeError(f"Bad device id from panel: {device_id!r}")

        if box_serial is None:
            box_serial = next_box_serial()
        box_serial = box_serial.strip().upper()

        secret = device_secret(master, device_id)
        fp = key_fingerprint(secret)

        # After erase/flash, NVS is empty — always try to lock. Write-once if already set.
        serial_now = ident["serial"]
        if serial_now == device_id or not serial_now.startswith("FS-"):
            lock_serial(ser, box_serial)
        else:
            box_serial = serial_now
            print(f"Serial already locked: {box_serial}")

        if key_is_locked(ident["key"]):
            print("Device reports key locked — verifying challenge")
        else:
            print(f"Locking device key ({ident['key']!r})")
            lock_key(ser, secret)

        try:
            proof = verify_challenge(ser, secret)
        except RuntimeError as exc:
            if str(exc) != "key_missing":
                raise
            # KEY? lied or NVS empty after wipe — force KEYSET then re-prove.
            print("Challenge said key missing — locking key now")
            lock_key(ser, secret)
            proof = verify_challenge(ser, secret)
        final = read_identity(ser)

        append_ledger(
            serial=box_serial,
            device_id=device_id,
            key_fp=fp,
            fw_version=final.get("fw_version") or ident.get("fw_version") or "",
            port=port,
            secret_hex=secret,
        )
        return {
            "port": port,
            "device_id": device_id,
            "serial": box_serial,
            "key_fingerprint": fp,
            "fw_version": final.get("fw_version"),
            "proof_ok": True,
            "proof": proof,
            "ledger": str(LEDGER_PATH),
        }
    finally:
        ser.close()


def main(argv: list[str] | None = None) -> int:
    import json

    parser = argparse.ArgumentParser(description="Fennsill Factory — flash & serialize a panel")
    parser.add_argument("--port", help="COM port (e.g. COM7). Omit to list candidates.")
    parser.add_argument("--no-flash", action="store_true", help="Only lock serial/key (firmware already on panel)")
    parser.add_argument("--serial", help="Force box serial FS-YYMM-NNNNNN")
    parser.add_argument("--list", action="store_true", help="List USB panel candidates")
    parser.add_argument("--check", action="store_true", help="Verify --port is an e-ink XIAO target")
    parser.add_argument("--json", action="store_true", help="Machine-readable output for FennsillFactory.exe")
    args = parser.parse_args(argv)

    if args.check:
        if not args.port:
            raise SystemExit("--check needs --port")
        target = assert_factory_flash_port(args.port)
        if args.json:
            print(json.dumps({"ok": True, "target": target}, default=str))
        else:
            print(f"OK {target.get('port')} [{target.get('kind')}] {target.get('reason')}")
        return 0

    if args.list or not args.port:
        rows = list_factory_flash_targets()
        if args.json:
            print(json.dumps({"ok": True, "targets": rows}, default=str))
            return 0 if rows else 2
        print("Fennsill e-ink flash targets (XIAO ESP32-S3 only):")
        if not rows:
            print("  (none — plug in the panel, not a random USB-UART)")
        for row in rows:
            print(
                f"  {row.get('port')}  [{row.get('kind')}]  "
                f"{row.get('description', '')}  — {row.get('reason', '')}"
            )
        if not args.port:
            return 0 if rows else 2

    result = provision(
        args.port,
        flash=not args.no_flash,
        box_serial=args.serial,
    )
    if args.json:
        print(json.dumps({"ok": True, **result}, default=str))
        return 0
    print()
    print("Provisioned")
    print(f"  serial:     {result['serial']}")
    print(f"  device_id:  {result['device_id']}")
    print(f"  key_fp:     {result['key_fingerprint']}")
    print(f"  fw:         {result['fw_version']}")
    print(f"  ledger:     {result['ledger']}")
    print()
    print("Buyer next (required for Claude/ChatGPT push over USB):")
    print("  1. Install/open Fennsill.exe on the PC that will keep the panel plugged in.")
    print(f"  2. On mcp.fennsill.com, Link panel with device id {result['device_id']}.")
    print("  3. Mint a device key on that SAME account → Paste device key in Fennsill.")
    print("  4. Leave Fennsill open until the AI's list_panels shows online/last_seen_at.")
    print("Flash erase clears panel NVS (including any old Wi-Fi). USB cloud push does NOT")
    print("need Wi-Fi — the PC agent heartbeats. Set Wi-Fi in Fennsill only if you use it later.")
    print("This serial never changes across PCs.")
    return 0


def _format_exc(exc: BaseException) -> str:
    text = str(exc)
    low = text.lower()
    if "virtual_file.log" in low or "bitdefender virtual disk" in low:
        return (
            f"{text}\n\n"
            "Bitdefender (or similar AV) is blocking Factory file writes on its virtual disk.\n"
            "Allow/exclude: this Factory folder, python.exe, arduino-cli.exe, and "
            "%LOCALAPPDATA%\\FennsillApp — then Flash again."
        )
    return text


if __name__ == "__main__":
    try:
        from ensure_arduino import harden_process_paths

        harden_process_paths()
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {_format_exc(exc)}", file=sys.stderr)
        raise SystemExit(1)
