"""USB channel shared by the connector and the firmware.

The panel sends ``READY <version> id=<deviceId>`` when the cable connects.
The host then sends 1024-byte chunks. Each chunk carries a CRC-32 and the
panel answers ACK or NAK. A show packet carries the CRC of the full
48,000-byte frame. Wi-Fi credentials travel on this cable as one WIFI line;
the firmware must never echo decoded SSID/PSK on Serial.

Cloud account auth is out of scope here — device_id is only for local pairing.
"""

import base64
import struct
import zlib

VERSION = "1.2.0"
FRAME_BYTES = 48000
CHUNK_SIZE = 1024
CHUNK_MAGIC = b"AFC1"
SHOW_MAGIC = b"AFS1"
DEFAULT_DEVICE_ID = "AP000000000000"
DEFAULT_SERIAL = DEFAULT_DEVICE_ID


def crc32(data):
    return zlib.crc32(data) & 0xFFFFFFFF


def chunk_count(size=FRAME_BYTES):
    return (size + CHUNK_SIZE - 1) // CHUNK_SIZE


def encode_chunk(index, total, payload):
    if len(payload) > CHUNK_SIZE:
        raise ValueError("chunk is larger than 1024 bytes")
    return CHUNK_MAGIC + struct.pack("<HHHI", index, total, len(payload), crc32(payload)) + payload


def encode_show(frame):
    if len(frame) != FRAME_BYTES:
        raise ValueError("frame must be 48000 bytes")
    return SHOW_MAGIC + struct.pack("<I", crc32(frame))


def split_frame(frame):
    if len(frame) != FRAME_BYTES:
        raise ValueError("frame must be 48000 bytes")
    total = chunk_count()
    packets = []
    for index in range(total):
        start = index * CHUNK_SIZE
        packets.append(encode_chunk(index, total, frame[start : start + CHUNK_SIZE]))
    return packets


class PanelLink:
    """Byte-level stand-in for the firmware receiver. Tests push frames through it."""

    def __init__(self, display_ok=True, device_id=DEFAULT_DEVICE_ID, serial=None, device_key_hex=None):
        self.display_ok = display_ok
        self.device_id = device_id
        self.serial = serial or device_id
        self.device_key_hex = device_key_hex
        self.parts = {}
        self.total = 0
        self.frame = None
        self.wifi_cleared = False
        self.wifi = None
        self.updates_url = None
        self._buffer = b""
        self._need = 0
        self._header = b""
        self.out = b""

    def greeting(self):
        line = f"READY {VERSION} id={self.device_id} serial={self.serial}\n".encode("ascii")
        self.out += line
        return line

    def feed(self, data):
        self._buffer += data
        replies = []
        while True:
            if self._need:
                if len(self._buffer) < self._need:
                    break
                payload = self._buffer[: self._need]
                self._buffer = self._buffer[self._need :]
                self._need = 0
                replies.append(self._on_payload(self._header, payload))
                self._header = b""
                continue
            if self._buffer.startswith(SHOW_MAGIC):
                if len(self._buffer) < 8:
                    break
                header = self._buffer[:8]
                self._buffer = self._buffer[8:]
                replies.append(self._on_show(header))
                continue
            if self._buffer.startswith(CHUNK_MAGIC):
                if len(self._buffer) < 14:
                    break
                self._header = self._buffer[:14]
                self._buffer = self._buffer[14:]
                _index, _total, length, _crc = struct.unpack("<HHHI", self._header[4:])
                if length > CHUNK_SIZE:
                    replies.append(b"NAK 0\n")
                    continue
                self._need = length
                continue
            newline = self._buffer.find(b"\n")
            if newline < 0:
                break
            line = self._buffer[:newline]
            self._buffer = self._buffer[newline + 1 :]
            replies.append(self._on_line(line.decode("ascii", "replace").strip()))
        self.out += b"".join(replies)
        return b"".join(replies)

    def _on_line(self, line):
        if line in ("HELLO", "READY?"):
            return f"READY {VERSION} id={self.device_id} serial={self.serial}\n".encode("ascii")
        if line in ("ID?", "WHOAMI"):
            return f"ID {self.device_id}\n".encode("ascii")
        if line == "SERIAL?":
            return f"SERIAL {self.serial}\n".encode("ascii")
        if line.startswith("SERIALSET "):
            if self.serial != self.device_id and self.serial.startswith("AP-"):
                return b"ERR serial locked\n"
            value = line[10:].strip()
            if len(value) < 4 or len(value) > 32:
                return b"NAK 0\n"
            self.serial = value
            return b"OK\n"
        if line == "KEY?":
            state = "locked" if self.device_key_hex else "missing"
            return f"KEY {state}\n".encode("ascii")
        if line.startswith("KEYSET "):
            if self.device_key_hex:
                return b"ERR key locked\n"
            value = line[7:].strip().lower()
            if len(value) != 64:
                return b"NAK 0\n"
            self.device_key_hex = value
            return b"OK\n"
        if line.startswith("CHALLENGE "):
            import hashlib
            import hmac as hm

            if not self.device_key_hex:
                return b"ERR key missing\n"
            nonce = line[10:].strip().encode("ascii")
            proof = hm.new(bytes.fromhex(self.device_key_hex), nonce, hashlib.sha256).hexdigest()
            return f"PROOF {proof}\n".encode("ascii")
        if line == "FORGET":
            self.wifi_cleared = True
            self.wifi = None
            return b"OK\n"
        if line == "STATUS":
            flag = "1" if self.wifi else "0"
            key_flag = "1" if self.device_key_hex else "0"
            return (
                f"STATUS version={VERSION} id={self.device_id} serial={self.serial} "
                f"key={key_flag} wifi={flag}\n".encode("ascii")
            )
        if line.startswith("WIFI "):
            parts = line.split(" ")
            if len(parts) != 3:
                return b"NAK 0\n"
            try:
                ssid = base64.b64decode(parts[1], validate=True).decode("utf-8")
                password = base64.b64decode(parts[2], validate=True).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return b"NAK 0\n"
            self.wifi = (ssid, password)
            return b"OK\n"
        if line.startswith("UPDATES "):
            url = line[8:].strip()
            if not url.startswith("https://"):
                return b"NAK 0\n"
            self.updates_url = url
            return b"OK\n"
        return b"NAK 0\n"

    def _on_payload(self, header, payload):
        index, total, length, expected = struct.unpack("<HHHI", header[4:])
        if length != len(payload) or crc32(payload) != expected or index >= total:
            return f"NAK {index}\n".encode("ascii")
        self.parts[index] = payload
        self.total = total
        return f"ACK {index}\n".encode("ascii")

    def _on_show(self, header):
        expected = struct.unpack("<I", header[4:8])[0]
        if len(self.parts) != self.total or self.total == 0:
            return b"NAK 0\n"
        frame = b"".join(self.parts[index] for index in range(self.total))
        if len(frame) != FRAME_BYTES or crc32(frame) != expected:
            return b"NAK 0\n"
        if not self.display_ok:
            return b"ERR display not detected\n"
        self.frame = frame
        return b"OK\n"


def wifi_line(ssid, password):
    user = base64.b64encode(ssid.encode("utf-8")).decode("ascii")
    secret = base64.b64encode(password.encode("utf-8")).decode("ascii")
    return f"WIFI {user} {secret}\n".encode("ascii")


def push_frame(link, frame):
    """Send a frame the way the repair host does. Returns the reply lines."""
    link.greeting()
    replies = []
    for packet in split_frame(frame):
        reply = link.feed(packet).decode("ascii")
        replies.append(reply.strip())
        if not reply.startswith("ACK"):
            return replies
    replies.append(link.feed(encode_show(frame)).decode("ascii").strip())
    return replies
