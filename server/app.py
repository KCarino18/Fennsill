"""Thin Artiphact login.

The account stores an email, the subscription the buyer already pays for,
and the panel id. It does not store dashboards or Wi-Fi passwords.
"""

import hashlib
import json
import secrets
import sqlite3
import sys
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "firmware"))
from panel_ports import confirmed_panels  # noqa: E402

WEB = ROOT / "web"
LINKED = ROOT / "connector" / "linked.json"
DB_PATH = Path(__import__("os").environ.get("ARTIPHACT_DB", ROOT / "server" / "artiphact.db"))
HOST = __import__("os").environ.get("ARTIPHACT_HOST", "0.0.0.0")
PORT = int(__import__("os").environ.get("ARTIPHACT_PORT", "8080"))
PBKDF2_ROUNDS = 120_000

WIFI_FIELDS = {
    "ssid",
    "wifi",
    "wifi_ssid",
    "wifi_password",
    "psk",
    "network",
    "passphrase",
    "password_wifi",
}


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    if DB_PATH.exists():
        probe = sqlite3.connect(DB_PATH)
        tables = {row[0] for row in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        columns = set()
        if "devices" in tables:
            columns = {row[1] for row in probe.execute("PRAGMA table_info(devices)")}
        probe.close()
        if "frame" in columns or "code" in columns:
            DB_PATH.unlink()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL,
                connected_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                device_id TEXT UNIQUE NOT NULL,
                linked_at TEXT NOT NULL
            );
            """
        )


def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    salt_hex, digest_hex = stored.split("$", 1)
    candidate = hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(candidate, f"{salt_hex}${digest_hex}")


def valid_email(email):
    return isinstance(email, str) and 3 <= len(email) <= 200 and "@" in email and " " not in email


def contains_wifi(value):
    if isinstance(value, dict):
        return any(key.lower() in WIFI_FIELDS or contains_wifi(item) for key, item in value.items())
    if isinstance(value, list):
        return any(contains_wifi(item) for item in value)
    return False


def write_link(email, provider):
    LINKED.parent.mkdir(parents=True, exist_ok=True)
    LINKED.write_text(json.dumps({"email": email, "provider": provider}), encoding="utf-8")


def matching_ports():
    return [panel["ident"] for panel in confirmed_panels()]


class Handler(BaseHTTPRequestHandler):
    server_version = "Artiphact/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/setup"):
            self._file(WEB / "setup.html", "text/html; charset=utf-8")
            return
        if path == "/setup.css":
            self._file(WEB / "setup.css", "text/css; charset=utf-8")
            return
        if path == "/setup.js":
            self._file(WEB / "setup.js", "text/javascript; charset=utf-8")
            return
        if path == "/api/me":
            self._me()
            return
        self._json(404, {"error": "Not found."})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()
        if body is None:
            return
        if path == "/api/session":
            self._session(body)
            return
        if path == "/api/subscription":
            self._subscription(body)
            return
        if path == "/api/device":
            self._device(body)
            return
        if path == "/api/device/link":
            self._link_plugged_in()
            return
        self._json(404, {"error": "Not found."})

    def _body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "Send JSON."})
            return None
        if contains_wifi(body):
            self._json(400, {"error": "Wi-Fi credentials stay on the panel."})
            return None
        if not isinstance(body, dict):
            self._json(400, {"error": "Send a JSON object."})
            return None
        return body

    def _session(self, body):
        email = str(body.get("email", "")).strip().lower()
        password = body.get("password", "")
        mode = body.get("mode", "login")
        if not valid_email(email) or not isinstance(password, str) or len(password) < 8:
            self._json(400, {"error": "Use an email and a password of at least 8 characters."})
            return
        with connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if mode == "signup":
                if row:
                    self._json(409, {"error": "That email already has an account. Log in instead."})
                    return
                conn.execute(
                    "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                    (email, hash_password(password), stamp()),
                )
                user_id = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()["id"]
            elif mode == "login":
                if not row or not verify_password(password, row["password_hash"]):
                    self._json(401, {"error": "Email or password is wrong."})
                    return
                user_id = row["id"]
            else:
                self._json(400, {"error": "Choose login or signup."})
                return
            token = secrets.token_hex(32)
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, user_id, stamp()),
            )
        self._json(200, {"email": email}, cookie=token)

    def _subscription(self, body):
        user = self._user()
        if not user:
            self._json(401, {"error": "Sign in first."})
            return
        provider = str(body.get("provider", "")).strip().lower()
        allowed = {"claude", "chatgpt", "openai", "gemini", "google", "grok", "xai", "cursor"}
        if provider not in allowed:
            self._json(400, {"error": "Pick Claude, ChatGPT, Gemini, Grok, or Cursor."})
            return
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO subscriptions (user_id, provider, connected_at) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET provider = excluded.provider, connected_at = excluded.connected_at
                """,
                (user["id"], provider, stamp()),
            )
        write_link(user["email"], provider)
        self._json(200, {"provider": provider})

    def _device(self, body):
        user = self._user()
        if not user:
            self._json(401, {"error": "Sign in first."})
            return
        device_id = str(body.get("device_id", "")).strip()
        if not device_id or len(device_id) > 200:
            self._json(400, {"error": "Plug in the panel."})
            return
        self._save_device(user["id"], device_id)
        self._json(200, {"device_id": device_id})

    def _link_plugged_in(self):
        user = self._user()
        if not user:
            self._json(401, {"error": "Sign in first."})
            return
        found = matching_ports()
        if len(found) != 1:
            self._json(404, {"error": "Plug in one panel and try again."})
            return
        self._save_device(user["id"], found[0])
        self._json(200, {"device_id": found[0]})

    def _save_device(self, user_id, device_id):
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO devices (user_id, device_id, linked_at) VALUES (?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET user_id = excluded.user_id, linked_at = excluded.linked_at
                """,
                (user_id, device_id, stamp()),
            )

    def _me(self):
        user = self._user()
        if not user:
            self._json(401, {"error": "Sign in first."})
            return
        with connect() as conn:
            sub = conn.execute(
                "SELECT provider FROM subscriptions WHERE user_id = ?", (user["id"],)
            ).fetchone()
            devices = conn.execute(
                "SELECT device_id FROM devices WHERE user_id = ?", (user["id"],)
            ).fetchall()
        self._json(
            200,
            {
                "email": user["email"],
                "subscription": sub["provider"] if sub else None,
                "devices": [row["device_id"] for row in devices],
            },
        )

    def _user(self):
        token = ""
        for part in self.headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "session":
                token = value
        if not token:
            return None
        with connect() as conn:
            return conn.execute(
                """
                SELECT users.id, users.email FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ?
                """,
                (token,),
            ).fetchone()

    def _json(self, status, payload, cookie=None):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", f"session={cookie}; HttpOnly; SameSite=Lax; Path=/")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path, content_type):
        if not path.is_file():
            self._json(404, {"error": "Not found."})
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Artiphact account at http://{HOST}:{PORT}/setup")
    server.serve_forever()


if __name__ == "__main__":
    main()
