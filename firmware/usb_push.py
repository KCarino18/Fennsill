"""Repair host: find the panel on USB and push a 48,000-byte frame.

The buyer never runs this. Setup is the login page. This talks the chunked
USB protocol when a cable is plugged in for the bench or a repair.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "templates"))
sys.path.insert(0, str(ROOT / "firmware"))

from panel_ports import answered_ready, confirmed_panels  # noqa: E402
from usb_protocol import encode_show, split_frame  # noqa: E402


def matching_ports():
    return confirmed_panels()


def read_ready(ser, timeout):
    deadline = time.time() + timeout
    buffer = b""
    while time.time() < deadline:
        buffer += ser.read(ser.in_waiting or 1)
        if answered_ready(buffer):
            return buffer
    raise TimeoutError("The panel did not send READY. Use the micro-USB cable, then press EN.")


def push(ser, frame):
    ser.write(b"HELLO\n")
    ser.flush()
    read_ready(ser, 5)
    for packet in split_frame(frame):
        ser.write(packet)
        ser.flush()
        reply = ser.read_until(b"\n", 3).decode("ascii", "replace").strip()
        if not reply.startswith("ACK"):
            raise RuntimeError(f"Chunk was rejected: {reply or 'no reply'}")
    ser.write(encode_show(frame))
    ser.flush()
    reply = ser.read_until(b"\n", 15).decode("ascii", "replace").strip()
    if reply != "OK":
        raise RuntimeError(reply or "The panel did not confirm the frame.")
    return reply


def main():
    parser = argparse.ArgumentParser(description="Push a 1-bit frame to an Artiphact panel over USB.")
    parser.add_argument("--port", help="Serial port. Omit to use the only matching panel.")
    parser.add_argument("--list", action="store_true", help="Show matching USB serial ports.")
    parser.add_argument("--frame", required=True, help="Path to a 48000-byte frame of the buyer's own content.")
    parser.add_argument("--out", help="Write the frame to this path and do not open a port.")
    args = parser.parse_args()

    frame = Path(args.frame).read_bytes()
    if len(frame) != 48000:
        raise SystemExit("Frame must be 48000 bytes.")
    if args.out:
        Path(args.out).write_bytes(frame)
        print(args.out)
        return

    try:
        import serial
    except ImportError as exc:
        raise SystemExit("Install pyserial to open the panel's USB port.") from exc

    if args.list or not args.port:
        ports = matching_ports()
        if args.list:
            for port in ports:
                print(f"{port['port']}\t{port['description']}")
            return
        if len(ports) != 1:
            names = ", ".join(port["port"] for port in ports) or "none"
            raise SystemExit(f"Pass --port. Matching panels: {names}")
        args.port = ports[0]["port"]

    try:
        ser = serial.Serial(args.port, 115200, timeout=0.2, write_timeout=3)
    except serial.SerialException as exc:
        raise SystemExit(f"{args.port} is busy. Close the other serial monitor and try again.") from exc
    with ser:
        print(push(ser, frame))


if __name__ == "__main__":
    main()
