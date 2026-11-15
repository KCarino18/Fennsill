"""Find the Fennsill panel on USB.

Matches the XIAO ESP32-S3 (Espressif/Seeed native USB) and classic DevKit
UART bridges (CP2102/CH340). A port counts as ready only after it answers
READY (any firmware version / optional id=). Busy ports (held by
desk/live/rotate/MCP) are reported separately so callers do not confuse
“in use” with “unplugged”.
"""

import re
import time

CP2102_VID = 0x10C4
CH340_VID = 0x1A86
ESPRESSIF_VID = 0x303A
SEEED_VID = 0x2886
# Factory flash: only native USB on the XIAO ESP32-S3 panel — never CH340/CP2102 dongles.
FACTORY_VIDS = (ESPRESSIF_VID, SEEED_VID)
READY_RE = re.compile(rb"READY\s+\S+")
FENNSILL_READY_RE = re.compile(
    rb"READY\s+\d+\.\d+(?:\.\d+)?(?:\s+id=FS[0-9A-Fa-f]+)?(?:\s+serial=\S+)?"
)
XIAO_HINT_RE = re.compile(
    r"(xiao|seeed|esp32|esp32s3|usb.?jtag|serial debug unit|trmnl|fennsill)",
    re.I,
)
REJECT_HINT_RE = re.compile(
    r"(ch340|cp210|arduino uno|arduino mega|ft232|prolific|bluetooth|gps|modem)",
    re.I,
)


def adapter_vid(vid):
    return vid in (CP2102_VID, CH340_VID, ESPRESSIF_VID, SEEED_VID)


def factory_vid(vid):
    """True only for XIAO ESP32-S3 native USB (Fennsill e-ink panel board)."""
    return vid in FACTORY_VIDS


def answered_ready(buffer):
    return READY_RE.search(buffer) is not None


def parse_device_id(buffer):
    """Pull id=… from a READY or STATUS line if present."""
    match = re.search(rb"(?:READY|STATUS|ID)\b[^\n]*?\bid=([A-Za-z0-9]+)", buffer)
    if match:
        return match.group(1).decode("ascii", "replace")
    match = re.search(rb"^ID\s+(\S+)", buffer, re.M)
    if match:
        return match.group(1).decode("ascii", "replace")
    return None


def probe(ser, timeout=2.0):
    """Send HELLO. True when the panel answers any READY line."""
    waiting = getattr(ser, "in_waiting", 0) or 0
    buffer = ser.read(waiting) if waiting else b""
    if answered_ready(buffer):
        return True
    ser.write(b"HELLO\n")
    ser.flush()
    deadline = time.time() + timeout
    while time.time() < deadline:
        waiting = getattr(ser, "in_waiting", 0) or 0
        chunk = ser.read(waiting or 1)
        if chunk:
            buffer += chunk
            if answered_ready(buffer):
                return True
        else:
            time.sleep(0.02)
    return False


def _default_open_port(device):
    import serial

    # Keep DTR/RTS low so probing the port does not reset the ESP32.
    ser = serial.Serial()
    ser.port = device
    ser.baudrate = 115200
    ser.timeout = 0.05
    ser.write_timeout = 2
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def _port_info(port):
    ident = getattr(port, "serial_number", None) or getattr(port, "hwid", None) or port.device
    return {
        "port": port.device,
        "description": getattr(port, "description", None) or "",
        "ident": ident,
        "vid": getattr(port, "vid", None),
        "pid": getattr(port, "pid", None),
        "hwid": getattr(port, "hwid", None) or "",
    }


def _looks_like_xiao_panel(info) -> bool:
    blob = f"{info.get('description', '')} {info.get('hwid', '')} {info.get('ident', '')}"
    if REJECT_HINT_RE.search(blob):
        return False
    if not factory_vid(info.get("vid")):
        return False
    # Espressif/Seeed native USB on this kit is enough; hints are extra confidence.
    return True if XIAO_HINT_RE.search(blob) else factory_vid(info.get("vid"))


def fennsill_ready_line(buffer: bytes) -> bool:
    return FENNSILL_READY_RE.search(buffer) is not None


def probe_fennsill(ser, timeout=2.0) -> dict | None:
    """Return READY fields if this COM speaks Fennsill e-ink firmware; else None."""
    waiting = getattr(ser, "in_waiting", 0) or 0
    buffer = ser.read(waiting) if waiting else b""
    ser.write(b"HELLO\n")
    ser.flush()
    deadline = time.time() + timeout
    while time.time() < deadline:
        waiting = getattr(ser, "in_waiting", 0) or 0
        chunk = ser.read(waiting or 1)
        if chunk:
            buffer += chunk
            if b"\n" in buffer and fennsill_ready_line(buffer):
                text = buffer.decode("ascii", "replace")
                for line in text.splitlines():
                    if line.startswith("READY"):
                        info = {"ready_line": line.strip()}
                        parts = line.split()
                        if len(parts) >= 2:
                            info["fw_version"] = parts[1]
                        for token in parts[2:]:
                            if "=" in token:
                                k, v = token.split("=", 1)
                                info[k] = v
                        return info
        else:
            time.sleep(0.02)
    # Non-Fennsill chatter on the wire → not our panel.
    if buffer and not fennsill_ready_line(buffer):
        return None
    return None


def list_candidate_ports(comports=None):
    """USB adapter ports by VID only — does not open COM (safe while MCP pushes)."""
    if comports is None:
        try:
            from serial.tools import list_ports
        except ImportError:
            return []
        comports = list_ports.comports
    out = []
    for port in comports():
        if not adapter_vid(getattr(port, "vid", None)):
            continue
        out.append(_port_info(port))
    return out


def list_factory_flash_targets(comports=None, open_port=None, timeout=2.0):
    """Ports safe to FLASH from Fennsill Factory.

    Accepts only:
      - XIAO ESP32-S3 native USB (Espressif/Seeed VID), and
      - either Fennsill READY (id=FS…) already on the panel, or a silent
        blank/bootloader board that still looks like that XIAO (first flash).

    Rejects CH340/CP2102 bridges and anything that talks non-Fennsill serial.
    """
    if comports is None:
        try:
            from serial.tools import list_ports
        except ImportError:
            return []
        comports = list_ports.comports
    if open_port is None:
        open_port = _default_open_port

    targets = []
    for port in comports():
        info = _port_info(port)
        if not _looks_like_xiao_panel(info):
            continue
        try:
            ser = open_port(port.device)
        except Exception:
            info["kind"] = "busy"
            info["reason"] = "port open failed (in use?)"
            continue
        try:
            ready = probe_fennsill(ser, timeout=timeout)
        finally:
            close = getattr(ser, "close", None)
            if close:
                close()
        if ready:
            info["kind"] = "fennsill"
            info["reason"] = "Fennsill e-ink panel (READY)"
            info.update(ready)
            targets.append(info)
            continue
        # No Fennsill READY — still OK if this is the XIAO on the TRMNL/Fennsill kit
        # (stock TRMNL firmware, blank flash, or bootloader). FLASH will erase + replace.
        info["kind"] = "xiao_replace"
        info["reason"] = "XIAO ESP32-S3 panel (TRMNL/other firmware or blank — will wipe + install Fennsill)"
        targets.append(info)
    return targets


def assert_factory_flash_port(port_name: str, targets=None) -> dict:
    """Raise if port is not a Fennsill e-ink / XIAO panel flash target."""
    if targets is None:
        targets = list_factory_flash_targets()
    for row in targets:
        if row.get("port") == port_name and row.get("kind") in (
            "fennsill",
            "xiao_replace",
            "xiao_blank",  # legacy name
        ):
            return row
    raise RuntimeError(
        f"{port_name} is not a Fennsill e-ink panel. "
        "Factory only flashes the XIAO ESP32-S3 panel (Espressif/Seeed USB), "
        "never random COM adapters. Plug in the panel alone and retry."
    )


def scan_panels(comports=None, open_port=None, timeout=1.5):
    """Classify USB adapter ports: ready, busy (open failed), or silent (no READY).

    Callers that push should hold SerialGuard first so desk polling and MCP
    do not open COM at the same time.
    """
    if comports is None:
        try:
            from serial.tools import list_ports
        except ImportError:
            return {"ready": [], "busy": [], "silent": [], "candidates": 0}
        comports = list_ports.comports
    if open_port is None:
        try:
            import serial  # noqa: F401
        except ImportError:
            return {"ready": [], "busy": [], "silent": [], "candidates": 0}
        open_port = _default_open_port

    ready = []
    busy = []
    silent = []
    candidates = 0
    for port in comports():
        if not adapter_vid(getattr(port, "vid", None)):
            continue
        candidates += 1
        info = _port_info(port)
        try:
            ser = open_port(port.device)
        except Exception as exc:
            # #region agent log
            try:
                import sys
                from pathlib import Path

                _conn = Path(__file__).resolve().parents[1] / "connector"
                if str(_conn) not in sys.path:
                    sys.path.insert(0, str(_conn))
                from debug_ndjson import dlog

                dlog(
                    "F",
                    "panel_ports.py:scan_panels",
                    "scan_open_fail",
                    {"port": port.device, "err": str(exc), "err_type": type(exc).__name__},
                )
            except Exception:
                pass
            # #endregion
            busy.append(info)
            continue
        try:
            ok = probe(ser, timeout)
        finally:
            close = getattr(ser, "close", None)
            if close:
                close()
        if ok:
            ready.append(info)
        else:
            silent.append(info)
    return {"ready": ready, "busy": busy, "silent": silent, "candidates": candidates}


def confirmed_panels(comports=None, open_port=None, timeout=1.5):
    return scan_panels(comports=comports, open_port=open_port, timeout=timeout)["ready"]


def panel_absence_message(scan=None, timeout=1.2) -> str:
    """Clear, fail-fast explanation when a push cannot use USB."""
    if scan is None:
        scan = scan_panels(timeout=timeout)
    ready = scan["ready"]
    if len(ready) == 1:
        return ""
    if len(ready) > 1:
        names = ", ".join(p["port"] for p in ready)
        return f"Plug in exactly one panel. Matching ports: {names}"
    if scan["busy"]:
        names = ", ".join(p["port"] for p in scan["busy"])
        return (
            f"Panel port {names} is briefly in use. "
            "Retry in a few seconds — you can leave Fennsill open."
        )
    if scan["silent"]:
        names = ", ".join(p["port"] for p in scan["silent"])
        return (
            f"USB device on {names} did not answer READY. "
            "Wait for the splash to finish, then retry."
        )
    return "No USB-connected Fennsill panel detected. Plug the panel in over USB and retry."
