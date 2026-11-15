"""SQLite store for Fennsill cloud MCP (no SQL Server)."""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from security_artifact import DEVICE_ID_RE, MAX_ARTIFACT_CHARS

# FENNSILL_SQL_CONNECTION is intentionally unused — SQL Server later.
# _SQL_CONNECTION = os.environ.get("FENNSILL_SQL_CONNECTION")

DB_PATH = Path(os.environ.get("FENNSILL_CLOUD_DB", Path(__file__).resolve().parent / "cloud.db"))
PBKDF2_ROUNDS = 120_000
ONLINE_SEC = 60
RATE_WINDOW_SEC = 600
RATE_LIMIT = 30
PERIOD_DAYS = 30


class StoreError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


def stamp(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
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
                user_id INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                device_id TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                linked_at TEXT NOT NULL,
                last_seen_at TEXT
            );
            CREATE TABLE IF NOT EXISTS device_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                device_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS access_subscriptions (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                status TEXT NOT NULL,
                started_at TEXT,
                current_period_end TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS push_jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                device_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                html TEXT,
                svg TEXT,
                title TEXT NOT NULL DEFAULT '',
                feed_kind TEXT,
                interval_sec INTEGER,
                status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS update_manifests (
                channel TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                url TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                published_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS push_rate (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_claim
                ON push_jobs(user_id, device_id, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_devices_user ON devices(user_id);
            CREATE INDEX IF NOT EXISTS idx_rate ON push_rate(user_id, device_id, created_at);
            """
        )


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt_hex, _ = stored.split("$", 1)
    candidate = hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(candidate, f"{salt_hex}${stored.split('$', 1)[1]}")


def valid_email(email: str) -> bool:
    return isinstance(email, str) and 3 <= len(email) <= 200 and "@" in email and " " not in email


def subscription_view(row) -> dict:
    if not row:
        return {
            "subscribed": False,
            "status": "inactive",
            "started_at": None,
            "current_period_end": None,
        }
    status = row["status"]
    end = row["current_period_end"]
    end_dt = parse_stamp(end)
    subscribed = status == "active" and end_dt is not None and end_dt > datetime.now(timezone.utc)
    return {
        "subscribed": subscribed,
        "status": status,
        "started_at": row["started_at"],
        "current_period_end": end,
    }


def get_subscription(conn, user_id: int):
    return conn.execute(
        "SELECT * FROM access_subscriptions WHERE user_id = ?", (user_id,)
    ).fetchone()


def period_is_open(row) -> bool:
    view = subscription_view(row)
    return bool(view["subscribed"])


def user_has_activated_device(conn, user_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM devices WHERE user_id = ? AND last_seen_at IS NOT NULL LIMIT 1",
        (user_id,),
    ).fetchone()
    return row is not None


def begin_access_period(user_id: int) -> dict:
    """Start the 30-day clock once. Call only from MCP auth path."""
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = get_subscription(conn, user_id)
        if not row:
            raise StoreError("subscription_inactive", "No subscription.", 403)
        if row["status"] != "pending":
            if row["status"] == "inactive" or not period_is_open(row):
                raise StoreError("subscription_inactive", "Subscription inactive.", 403)
            return subscription_view(row)
        if not user_has_activated_device(conn, user_id):
            raise StoreError(
                "device_not_activated",
                "Plug in the panel and run the agent so it can heartbeat first.",
                403,
            )
        now = datetime.now(timezone.utc)
        started = stamp(now)
        end = stamp(now + timedelta(days=PERIOD_DAYS))
        cur = conn.execute(
            """
            UPDATE access_subscriptions
            SET status = 'active', started_at = ?, current_period_end = ?, updated_at = ?
            WHERE user_id = ? AND status = 'pending'
            """,
            (started, end, started, user_id),
        )
        if cur.rowcount == 0:
            row = get_subscription(conn, user_id)
            if row["status"] == "inactive" or not period_is_open(row):
                raise StoreError("subscription_inactive", "Subscription inactive.", 403)
            return subscription_view(row)
        return {
            "subscribed": True,
            "status": "active",
            "started_at": started,
            "current_period_end": end,
        }


def require_mcp_access(user_id: int) -> dict:
    """Ensure period is open, starting it if pending + activated."""
    with connect() as conn:
        row = get_subscription(conn, user_id)
    if not row:
        raise StoreError("subscription_inactive", "Subscription inactive.", 403)
    if row["status"] == "pending":
        return begin_access_period(user_id)
    if row["status"] == "inactive" or not period_is_open(row):
        raise StoreError("subscription_inactive", "Subscription inactive.", 403)
    return subscription_view(row)


def require_open_period(user_id: int) -> dict:
    with connect() as conn:
        row = get_subscription(conn, user_id)
    if not period_is_open(row):
        code = "subscription_inactive"
        if row and row["status"] == "pending":
            # jobs path: pending means nothing to claim / refuse mutate
            raise StoreError(code, "Subscription not active yet.", 403)
        raise StoreError(code, "Subscription inactive.", 403)
    return subscription_view(row)


def signup(email: str, password: str) -> dict:
    email = email.strip().lower()
    if not valid_email(email) or not isinstance(password, str) or len(password) < 8:
        raise StoreError("bad_request", "Use an email and a password of at least 8 characters.")
    now = stamp()
    with connect() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise StoreError("conflict", "That email already has an account. Log in instead.", 409)
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, hash_password(password), now),
        )
        user_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO access_subscriptions (user_id, status, started_at, current_period_end, updated_at)
            VALUES (?, 'pending', NULL, NULL, ?)
            """,
            (user_id, now),
        )
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, user_id, now),
        )
        sub = subscription_view(get_subscription(conn, user_id))
    return {"token": token, "email": email, **sub}


def login(email: str, password: str) -> dict:
    email = email.strip().lower()
    if not valid_email(email) or not isinstance(password, str):
        raise StoreError("unauthorized", "Email or password is wrong.", 401)
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise StoreError("unauthorized", "Email or password is wrong.", 401)
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
            (token, int(row["id"]), stamp()),
        )
        sub = subscription_view(get_subscription(conn, int(row["id"])))
    return {"token": token, "email": email, **sub}


def user_from_session(token: str | None):
    if not token:
        return None
    with connect() as conn:
        return conn.execute(
            """
            SELECT u.id, u.email FROM users u
            JOIN sessions s ON s.user_id = u.id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()


def auth_device_token(token: str | None) -> dict | None:
    if not token:
        return None
    with connect() as conn:
        row = conn.execute(
            """
            SELECT user_id, device_id FROM device_tokens
            WHERE token = ? AND revoked = 0
            """,
            (token,),
        ).fetchone()
        if not row:
            return None
        owned = conn.execute(
            "SELECT 1 FROM devices WHERE user_id = ? AND device_id = ?",
            (row["user_id"], row["device_id"]),
        ).fetchone()
        if not owned:
            return None
        return {"user_id": int(row["user_id"]), "device_id": str(row["device_id"])}


def link_device(user_id: int, device_id: str, label: str = "") -> dict:
    device_id = device_id.strip().upper()
    if not DEVICE_ID_RE.match(device_id):
        raise StoreError("bad_request", "device_id must be FS plus 12 hex digits.")
    label = (label or "")[:80]
    now = stamp()
    with connect() as conn:
        existing = conn.execute(
            "SELECT user_id FROM devices WHERE device_id = ?", (device_id,)
        ).fetchone()
        if existing and int(existing["user_id"]) != user_id:
            raise StoreError("conflict", "Device already linked to another account.", 409)
        if existing:
            conn.execute(
                "UPDATE devices SET label = ?, linked_at = ? WHERE device_id = ? AND user_id = ?",
                (label, now, device_id, user_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO devices (user_id, device_id, label, linked_at, last_seen_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (user_id, device_id, label, now),
            )
    return {"device_id": device_id, "label": label}


def issue_device_token(user_id: int, device_id: str) -> str:
    device_id = device_id.strip().upper()
    with connect() as conn:
        owned = conn.execute(
            "SELECT 1 FROM devices WHERE user_id = ? AND device_id = ?",
            (user_id, device_id),
        ).fetchone()
        if not owned:
            raise StoreError("forbidden", "Device not linked to this account.", 403)
        sub = get_subscription(conn, user_id)
        if sub and sub["status"] == "inactive":
            raise StoreError("subscription_inactive", "Subscription inactive.", 403)
        if sub and sub["status"] == "active" and not period_is_open(sub):
            raise StoreError("subscription_inactive", "Subscription inactive.", 403)
        # pending OK so agent can heartbeat
        token = secrets.token_urlsafe(32)
        conn.execute(
            """
            INSERT INTO device_tokens (token, user_id, device_id, created_at, revoked)
            VALUES (?, ?, ?, ?, 0)
            """,
            (token, user_id, device_id, stamp()),
        )
    return token


def list_devices(user_id: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT device_id, label, linked_at, last_seen_at
            FROM devices WHERE user_id = ? ORDER BY linked_at DESC
            """,
            (user_id,),
        ).fetchall()
    out = []
    for r in rows:
        seen = parse_stamp(r["last_seen_at"])
        online = seen is not None and (now - seen).total_seconds() <= ONLINE_SEC
        out.append(
            {
                "device_id": r["device_id"],
                "label": r["label"],
                "linked_at": r["linked_at"],
                "last_seen_at": r["last_seen_at"],
                "online": online,
            }
        )
    return out


def me(user_id: int, email: str) -> dict:
    with connect() as conn:
        sub = subscription_view(get_subscription(conn, user_id))
    return {"email": email, **sub, "devices": list_devices(user_id)}


def heartbeat(device_auth: dict) -> dict:
    user_id = device_auth["user_id"]
    device_id = device_auth["device_id"]
    with connect() as conn:
        sub = get_subscription(conn, user_id)
        if sub and sub["status"] == "inactive":
            raise StoreError("subscription_inactive", "Subscription inactive.", 403)
        if sub and sub["status"] == "active" and not period_is_open(sub):
            raise StoreError("subscription_inactive", "Subscription inactive.", 403)
        # pending or open period: record activation
        now = stamp()
        cur = conn.execute(
            """
            UPDATE devices SET last_seen_at = ?
            WHERE user_id = ? AND device_id = ?
            """,
            (now, user_id, device_id),
        )
        if cur.rowcount == 0:
            raise StoreError("forbidden", "Device not linked.", 403)
    return {"ok": True, "device_id": device_id, "last_seen_at": now}


def _check_rate(conn, user_id: int, device_id: str) -> None:
    cutoff = stamp(datetime.now(timezone.utc) - timedelta(seconds=RATE_WINDOW_SEC))
    conn.execute(
        "DELETE FROM push_rate WHERE created_at < ?", (cutoff,)
    )
    count = conn.execute(
        """
        SELECT COUNT(*) AS c FROM push_rate
        WHERE user_id = ? AND device_id = ? AND created_at >= ?
        """,
        (user_id, device_id, cutoff),
    ).fetchone()["c"]
    if int(count) >= RATE_LIMIT:
        raise StoreError("rate_limited", "Too many pushes. Try again later.", 429)
    conn.execute(
        "INSERT INTO push_rate (user_id, device_id, created_at) VALUES (?, ?, ?)",
        (user_id, device_id, stamp()),
    )


def enqueue_job(
    *,
    user_id: int,
    device_id: str,
    job_type: str = "push",
    html: str | None = None,
    svg: str | None = None,
    title: str = "",
    feed_kind: str | None = None,
    interval_sec: int | None = None,
) -> dict:
    device_id = device_id.strip().upper()
    if job_type not in ("push", "live_start", "live_stop"):
        raise StoreError("bad_request", "Invalid job_type.")
    require_mcp_access(user_id)  # ensures period open / starts clock
    with connect() as conn:
        owned = conn.execute(
            "SELECT 1 FROM devices WHERE user_id = ? AND device_id = ?",
            (user_id, device_id),
        ).fetchone()
        if not owned:
            raise StoreError("forbidden", "Device not linked to this account.", 403)
        if job_type == "push":
            has_html = isinstance(html, str) and bool(html.strip())
            has_svg = isinstance(svg, str) and bool(svg.strip())
            if has_html == has_svg:
                raise StoreError("bad_request", "Send either html or svg.")
            if has_html and len(html) > MAX_ARTIFACT_CHARS:
                raise StoreError("bad_request", "html is too large.")
            if has_svg and len(svg) > MAX_ARTIFACT_CHARS:
                raise StoreError("bad_request", "svg is too large.")
        _check_rate(conn, user_id, device_id)
        job_id = secrets.token_hex(16)
        now = stamp()
        conn.execute(
            """
            INSERT INTO push_jobs
            (id, user_id, device_id, job_type, html, svg, title, feed_kind, interval_sec,
             status, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', '', ?, ?)
            """,
            (
                job_id,
                user_id,
                device_id,
                job_type,
                html if job_type == "push" and html else None,
                svg if job_type == "push" and svg else None,
                (title or "")[:80],
                feed_kind,
                interval_sec,
                now,
                now,
            ),
        )
    return {"job_id": job_id, "device_id": device_id, "status": "queued"}


def claim_next_job(device_auth: dict) -> dict | None:
    user_id = device_auth["user_id"]
    device_id = device_auth["device_id"]
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        sub = get_subscription(conn, user_id)
        if not sub or sub["status"] == "pending":
            return None  # 204
        if sub["status"] == "inactive" or not period_is_open(sub):
            raise StoreError("subscription_inactive", "Subscription inactive.", 403)
        row = conn.execute(
            """
            SELECT id FROM push_jobs
            WHERE user_id = ? AND device_id = ? AND status = 'queued'
            ORDER BY created_at ASC, id ASC LIMIT 1
            """,
            (user_id, device_id),
        ).fetchone()
        if not row:
            return None
        now = stamp()
        cur = conn.execute(
            """
            UPDATE push_jobs SET status = 'claimed', updated_at = ?
            WHERE id = ? AND status = 'queued'
            """,
            (now, row["id"]),
        )
        if cur.rowcount == 0:
            return None
        claimed = conn.execute("SELECT * FROM push_jobs WHERE id = ?", (row["id"],)).fetchone()
        return {
            "job_id": claimed["id"],
            "device_id": claimed["device_id"],
            "job_type": claimed["job_type"],
            "html": claimed["html"],
            "svg": claimed["svg"],
            "title": claimed["title"],
            "feed_kind": claimed["feed_kind"],
            "interval_sec": claimed["interval_sec"],
            "status": claimed["status"],
        }


def complete_job(device_auth: dict, job_id: str, *, ok: bool, error: str = "") -> None:
    require_open_period(device_auth["user_id"])
    with connect() as conn:
        row = conn.execute("SELECT * FROM push_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise StoreError("not_found", "Job not found.", 404)
        if int(row["user_id"]) != int(device_auth["user_id"]) or row["device_id"] != device_auth["device_id"]:
            raise StoreError("forbidden", "Job not owned by this device.", 403)
        status = "done" if ok else "failed"
        conn.execute(
            "UPDATE push_jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, (error or "")[:500], stamp(), job_id),
        )


def get_update_manifest(channel: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT channel, version, url, sha256, published_at FROM update_manifests WHERE channel = ?",
            (channel,),
        ).fetchone()
    return dict(row) if row else None


def publish_update_manifest(channel: str, version: str, url: str, sha256: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO update_manifests (channel, version, url, sha256, published_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(channel) DO UPDATE SET
              version=excluded.version,
              url=excluded.url,
              sha256=excluded.sha256,
              published_at=excluded.published_at
            """,
            (channel, version, url, sha256, stamp()),
        )


def set_access_subscription(email: str, status: str, current_period_end: str | None) -> None:
    if status not in ("active", "inactive"):
        raise StoreError("bad_request", "status must be active or inactive.")
    if status == "active" and not current_period_end:
        raise StoreError("bad_request", "active requires current_period_end.")
    email = email.strip().lower()
    with connect() as conn:
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            raise StoreError("not_found", "User not found.", 404)
        now = stamp()
        if status == "inactive":
            conn.execute(
                """
                UPDATE access_subscriptions
                SET status = 'inactive', updated_at = ?
                WHERE user_id = ?
                """,
                (now, int(user["id"])),
            )
        else:
            conn.execute(
                """
                UPDATE access_subscriptions
                SET status = 'active',
                    current_period_end = ?,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE user_id = ?
                """,
                (current_period_end, now, now, int(user["id"])),
            )
