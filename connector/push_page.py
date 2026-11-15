"""Push a saved page frame to the panel over USB."""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "connector"))

from pages_lib import load_frame  # noqa: E402
from panel_ports import confirmed_panels, panel_absence_message, scan_panels  # noqa: E402
from serial_guard import SerialBusy, SerialGuard  # noqa: E402
from usb_protocol import encode_show, split_frame  # noqa: E402

# MCP / intake should fail in seconds, not minutes (ChatGPT tool timeouts).
DEFAULT_READY_TIMEOUT = 8.0
DEFAULT_SHOW_TIMEOUT = 12.0


def wait_ready(ser, timeout=DEFAULT_READY_TIMEOUT):
    """Wait for a READY that answers HELLO — not the boot banner.

    Opening the port can catch the board mid-splash. Splash drawing blocks
    USB command handling, so keep HELLO-ing until the loop is alive.

    Raises TimeoutError (never SystemExit) so MCP can return an error instead
    of dying mid-call and leaving ChatGPT waiting for tool_timeout.
    """
    deadline = time.time() + timeout
    buffer = b""
    last_hello = 0.0
    hello_sent_at = None

    # Drop anything already queued (ROM banner, early noise, stale READY).
    time.sleep(0.15)
    try:
        ser.reset_input_buffer()
    except Exception:
        pass

    while time.time() < deadline:
        now = time.time()
        if now - last_hello >= 1.0:
            ser.write(b"HELLO\n")
            ser.flush()
            last_hello = now
            hello_sent_at = now
            # Fresh window for this HELLO's reply.
            buffer = b""

        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buffer += chunk
            # Ignore lines that arrived before we asked.
            if hello_sent_at is None:
                continue
            if b"READY" in buffer and b"\n" in buffer[buffer.find(b"READY") :]:
                return buffer.decode("ascii", "replace")
            if len(buffer) > 4096:
                buffer = buffer[-2048:]
        else:
            time.sleep(0.05)

    text = buffer.decode("ascii", "replace").strip()
    if "Build:" in text or "ESP-ROM" in text or "SPLASH" in text:
        raise TimeoutError(
            "Panel is still booting or drawing the splash. Wait for the screen to finish, then try again."
        )
    raise TimeoutError(text or "Panel did not answer READY. Close other serial monitors and try again.")


def read_line(ser, timeout=8.0):
    deadline = time.time() + timeout
    buffer = b""
    while time.time() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buffer += chunk
            if b"\n" in buffer:
                return buffer.decode("ascii", "replace").strip()
        else:
            time.sleep(0.01)
    return buffer.decode("ascii", "replace").strip()


def open_panel(port):
    import serial

    # Avoid an automatic chip reset when the COM port opens.
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = 0.2
    ser.write_timeout = 5
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: push_page.py <page_id>")
    page_id = sys.argv[1]
    frame = load_frame(page_id)

    try:
        with SerialGuard(timeout=20.0):
            from panel_ports import list_candidate_ports

            candidates = list_candidate_ports()
            if len(candidates) != 1:
                scan = {"ready": candidates if len(candidates) > 1 else [], "busy": [], "silent": [], "candidates": len(candidates)}
                raise SystemExit(panel_absence_message(scan))
            ser = open_panel(candidates[0]["port"])
            try:
                wait_ready(ser, timeout=DEFAULT_READY_TIMEOUT)
                for packet in split_frame(frame):
                    ser.write(packet)
                    ser.flush()
                    line = read_line(ser, 8.0)
                    # Splash can still print after a late boot; re-sync once.
                    if line == "SPLASH":
                        wait_ready(ser, timeout=DEFAULT_READY_TIMEOUT)
                        ser.write(packet)
                        ser.flush()
                        line = read_line(ser, 8.0)
                    if not line.startswith("ACK"):
                        raise SystemExit(line or "Chunk failed.")
                ser.write(encode_show(frame))
                ser.flush()
                show = read_line(ser, DEFAULT_SHOW_TIMEOUT)
                if "OK" not in show:
                    raise SystemExit(show or "Show failed.")
                print("OK")
            finally:
                ser.close()
    except SerialBusy as exc:
        raise SystemExit(str(exc)) from exc
    except TimeoutError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
