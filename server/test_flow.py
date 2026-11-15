"""Account, connector, frame, and update-signature checks. No hardware required."""

import hashlib
import hmac
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "templates"))
sys.path.insert(0, str(ROOT / "firmware"))
sys.path.insert(0, str(ROOT / "connector"))
sys.path.insert(0, str(ROOT / "updates"))

from artifact_frame import artifact_to_frame, wrap_page  # noqa: E402
from panel_ports import CH340_VID, CP2102_VID, answered_ready, confirmed_panels, probe  # noqa: E402
from render import FRAME_BYTES, render_market_movers  # noqa: E402
from usb_protocol import PanelLink, push_frame, wifi_line  # noqa: E402
import mcp_server  # noqa: E402
import sign_update  # noqa: E402


def expect(condition, message):
    if not condition:
        raise SystemExit(message)


def request(base, path, payload=None, cookie=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method=None if payload is None else "POST")
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    last = None
    for _ in range(20):
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()
        except urllib.error.URLError as error:
            last = error
            time.sleep(0.1)
    raise SystemExit(f"server did not answer: {last}")


def cookie_from(headers):
    raw = headers.get("Set-Cookie") or headers.get("set-cookie") or ""
    return raw.split(";", 1)[0]


def test_frame_and_usb():
    frame = render_market_movers()
    expect(len(frame) == FRAME_BYTES, "frame length")
    link = PanelLink()
    replies = push_frame(link, frame)
    expect(replies[-1] == "OK" and link.frame == frame, replies[-1])
    secret = "panel-only-secret"
    reply = link.feed(wifi_line("House", secret)).decode("ascii")
    expect(reply.strip() == "OK" and link.wifi == ("House", secret), reply)


def test_signature():
    key = sign_update.load_key()
    manifest = json.loads((ROOT / "updates" / "manifest.json").read_text(encoding="utf-8"))
    body = (ROOT / "updates" / "fennsill-1.1.0.bin").read_bytes()
    expect(hashlib.sha256(body).hexdigest() == manifest["sha256"], "firmware hash")
    message = f"{manifest['version']}\n{manifest['sha256']}".encode("utf-8")
    expect(hmac.new(key, message, hashlib.sha256).hexdigest() == manifest["signature"], "signature")
    tampered = dict(manifest)
    tampered["signature"] = "00" * 32
    bad = hmac.new(key, message, hashlib.sha256).hexdigest()
    expect(bad != tampered["signature"], "unsigned file must not match")
    expect("1.1.0" > "1.0.0", "newer version")


def test_artifact_wrap():
    expect("Pass the Claude Artifact" in _error(lambda: wrap_page()), "empty artifact")
    html = wrap_page(html="<h1>Today</h1>")
    expect("800px" in html and "<h1>Today</h1>" in html, html[:80])
    svg = wrap_page(svg='<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>')
    expect("<svg" in svg and "800px" in svg, svg[:80])


def _error(fn):
    try:
        fn()
    except ValueError as exc:
        return str(exc)
    return ""


def test_connector(link_path):
    os.environ["FENNSILL_LINK"] = str(link_path)
    mcp_server.LINKED = link_path
    link_path.write_text("", encoding="utf-8")
    missing = mcp_server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "push_artifact", "arguments": {}}},
        PanelLink(),
    )
    expect(missing["result"]["isError"] is True, missing)
    link_path.write_text(json.dumps({"email": "owner@example.com", "provider": "claude"}), encoding="utf-8")
    panel = PanelLink()
    secret = "panel-only-secret"
    response = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "set_wifi", "arguments": {"ssid": "House", "password": secret}},
        },
        panel,
    )
    expect(response["result"]["isError"] is False, response)
    expect(panel.wifi == ("House", secret), panel.wifi)
    expect(secret not in link_path.read_text(encoding="utf-8"), "wifi saved beside the connector")
    listed = mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    names = [tool["name"] for tool in listed["result"]["tools"]]
    expect(names == ["list_panels", "push_artifact", "set_wifi"], names)
    empty = mcp_server.handle(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "push_artifact", "arguments": {}}},
        PanelLink(),
    )
    expect(empty["result"]["isError"] is True, empty)
    html = '<div style="font-family:sans-serif;padding:24px"><h1>Today</h1><p>Dentist at 3</p></div>'
    frame = artifact_to_frame(html=html)
    expect(len(frame) == FRAME_BYTES, len(frame))
    expect(frame != render_market_movers(), "artifact matched the sample board")
    panel = PanelLink()
    pushed = mcp_server.handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "push_artifact", "arguments": {"html": html}},
        },
        panel,
    )
    expect(pushed["result"]["isError"] is False and panel.frame == frame, pushed)
    other = artifact_to_frame(html='<div style="padding:24px"><h1>Else</h1></div>')
    expect(frame != other, "different artifacts must draw different frames")


def test_account():
    tmp = tempfile.TemporaryDirectory()
    os.environ["FENNSILL_DB"] = str(Path(tmp.name) / "fennsill.db")
    os.environ["FENNSILL_HOST"] = "127.0.0.1"
    os.environ["FENNSILL_PORT"] = "8766"
    link_path = Path(tmp.name) / "linked.json"
    import app

    app.DB_PATH = Path(os.environ["FENNSILL_DB"])
    app.LINKED = link_path
    app.init_db()
    server = app.ThreadingHTTPServer(("127.0.0.1", 8766), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:8766"
    try:
        page = request(base, "/setup")[2].decode("utf-8")
        expect("Connect the subscription you already pay for." in page, "login copy")
        expect('id="ssid"' not in page and 'id="wifi-password"' not in page, "wifi field on the page")
        script = request(base, "/setup.js")[2].decode("utf-8")
        expect("wifi" not in script.lower() and "ssid" not in script.lower(), "wifi in the page script")

        status, _, body = request(
            base,
            "/api/session",
            {"email": "owner@example.com", "password": "correct-horse", "mode": "signup", "ssid": "House"},
        )
        expect(status == 400 and b"Wi-Fi" in body, body)

        status, headers, body = request(
            base, "/api/session", {"email": "owner@example.com", "password": "correct-horse", "mode": "signup"}
        )
        expect(status == 200, body)
        cookie = cookie_from(headers)
        status, _, body = request(
            base, "/api/session", {"email": "owner@example.com", "password": "nope-nope", "mode": "login"}
        )
        expect(status == 401, body)

        status, _, body = request(base, "/api/subscription", {"provider": "claude"}, cookie)
        expect(status == 200, body)
        expect(json.loads(link_path.read_text(encoding="utf-8"))["provider"] == "claude", "link file")

        status, _, body = request(base, "/api/device", {"device_id": "USB-TEST"}, cookie)
        expect(status == 200, body)
        me = json.loads(request(base, "/api/me", cookie=cookie)[2].decode("utf-8"))
        expect(me["subscription"] == "claude" and me["devices"] == ["USB-TEST"], me)

        conn = sqlite3.connect(app.DB_PATH)
        columns = []
        for table in ("users", "sessions", "subscriptions", "devices"):
            columns += [row[1].lower() for row in conn.execute(f"PRAGMA table_info({table})")]
        conn.close()
        raw = Path(app.DB_PATH).read_bytes()
        expect("frame" not in columns and "ssid" not in columns and "psk" not in columns, columns)
        expect(b"panel-only-secret" not in raw and b"House" not in raw, "wifi leaked into the account")
        test_connector(link_path)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        tmp.cleanup()


class FakePort:
    def __init__(self, device, vid, serial_number=""):
        self.device = device
        self.vid = vid
        self.description = "USB Serial"
        self.serial_number = serial_number
        self.hwid = f"USB VID:PID={vid:04X}:0000"


class FakeSerial:
    def __init__(self, reply):
        self.reply = reply
        self.written = b""
        self.in_waiting = 0
        self.closed = False

    def write(self, data):
        self.written += data
        self.in_waiting = len(self.reply)

    def flush(self):
        return None

    def read(self, count):
        take = self.reply[:count]
        self.reply = self.reply[count:]
        self.in_waiting = len(self.reply)
        return take

    def close(self):
        self.closed = True


def test_devkit_ports():
    expect(answered_ready(b"READY 1.0\n") and answered_ready(b"noise READY 1.0.0\n"), "ready line")
    expect(not answered_ready(b"READY 2.0\n") and not answered_ready(b""), "other board")
    panel = FakeSerial(b"READY 1.0.0\n")
    expect(probe(panel, 0.05) and panel.written == b"HELLO\n", panel.written)
    stranger = FakeSerial(b"OK\n")
    expect(probe(stranger, 0.05) is False, "adapter without the panel")
    opened = []

    def open_port(device):
        reply = b"READY 1.0\n" if device == "COM4" else b"no\n"
        ser = FakeSerial(reply)
        opened.append(ser)
        return ser

    ports = confirmed_panels(
        comports=lambda: [
            FakePort("COM4", CH340_VID, "PANEL-1"),
            FakePort("COM5", CP2102_VID, "OTHER"),
            FakePort("COM6", 0x2886, "XIAO"),
            FakePort("COM7", 0x303A, "S3"),
        ],
        open_port=open_port,
        timeout=0.05,
    )
    expect(len(ports) == 1 and ports[0]["ident"] == "PANEL-1" and ports[0]["port"] == "COM4", ports)
    expect(all(ser.closed for ser in opened) and len(opened) == 2, opened)


if __name__ == "__main__":
    test_frame_and_usb()
    test_signature()
    test_artifact_wrap()
    test_devkit_ports()
    test_account()
    print("ok")
