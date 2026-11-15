"""Multi-tenant store: users, devices, device tokens, push jobs, updates.

Clients cannot write arbitrary server state. Allowed mutations:
- enqueue a push job for a device the caller owns
- ack/complete a job for a device the caller owns
- create device tokens for the caller's devices

Updates (firmware/app) are published by operators only; clients GET.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__import__("os").environ.get("ARTIPHACT_DB", Path(__file__).resolve().parent / "artiphact.db"))
PBKDF2_ROUNDS = 120_000
MAX_HTML_CHARS = 512_000


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                device_id TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                linked_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS device_tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS push_jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                device_id TEXT NOT NULL,
                html TEXT,
                svg TEXT,
                title TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS update_manifests (
                channel TEXT PRIMARY KEY,
                version TEXT NOT NULL,
                url TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                published_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_device_status
                ON push_jobs(device_id, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_devices_user ON devices(user_id);
            """
        )


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex_val = stored.split("$", 1)
    candidate = hash_password(password, bytes.fromhex(salt_hex))
    return secrets.compare_digest(candidate, f"{salt_hex}${digest_hex_val}")



def user_from_session(token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    with connect() as conn:
        return conn.execute(
            """
            SELECT u.* FROM users u
            JOIN sessions s ON s.user_id = u.id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()


def auth_device_token(token: str | None) -> dict | None:
    """Return {user_id, device_id} if token is valid and not revoked."""
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


def user_owns_device(user_id: int, device_id: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM devices WHERE user_id = ? AND device_id = ?",
            (user_id, device_id),
        ).fetchone()
        return row is not None


def list_devices_for_user(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT device_id, label, linked_at FROM devices WHERE user_id = ? ORDER BY linked_at DESC",
            (user_id,),
        ).fetchall()
    return [{"device_id": r["device_id"], "label": r["label"], "linked_at": r["linked_at"]} for r in rows]


def enqueue_push(
    *,
    user_id: int,
    device_id: str,
    html: str | None = None,
    svg: str | None = None,
    title: str = "",
) -> dict:
    if not user_owns_device(user_id, device_id):
        raise PermissionError("Device not linked to this account.")
    has_html = isinstance(html, str) and bool(html.strip())
    has_svg = isinstance(svg, str) and bool(svg.strip())
    if has_html and has_svg:
        raise ValueError("Send either html or svg.")
    if not has_html and not has_svg:
        raise ValueError("html or svg is required.")
    if has_html and len(html) > MAX_HTML_CHARS:
        raise ValueError("html is too large.")
    if has_svg and len(svg) > MAX_HTML_CHARS:
        raise ValueError("svg is too large.")

    job_id = secrets.token_hex(16)
    now = stamp()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO push_jobs
            (id, user_id, device_id, html, svg, title, status, created_at, updated_at, error)
            VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, '')
            """,
            (job_id, user_id, device_id, html if has_html else None, svg if has_svg else None, title or "", now, now),
        )
    return {"job_id": job_id, "device_id": device_id, "status": "queued"}


def claim_next_job(device_auth: dict) -> dict | None:
    """Agent pulls one queued job for its own device only."""
    device_id = device_auth["device_id"]
    user_id = device_auth["user_id"]
    with connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM push_jobs
            WHERE user_id = ? AND device_id = ? AND status = 'queued'
            ORDER BY created_at ASC LIMIT 1
            """,
            (user_id, device_id),
        ).fetchone()
        if not row:
            return None
        now = stamp()
        conn.execute(
            "UPDATE push_jobs SET status = 'claimed', updated_at = ? WHERE id = ? AND status = 'queued'",
            (now, row["id"]),
        )
        # Re-read to ensure we won the claim
        claimed = conn.execute("SELECT * FROM push_jobs WHERE id = ?", (row["id"],)).fetchone()
        if not claimed or claimed["status"] != "claimed":
            return None
        return {
            "job_id": claimed["id"],
            "device_id": claimed["device_id"],
            "html": claimed["html"],
            "svg": claimed["svg"],
            "title": claimed["title"],
            "status": claimed["status"],
        }


def complete_job(device_auth: dict, job_id: str, *, ok: bool, error: str = "") -> bool:
    with connect() as conn:
        row = conn.execute("SELECT * FROM push_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return False
        if int(row["user_id"]) != int(device_auth["user_id"]) or row["device_id"] != device_auth["device_id"]:
            raise PermissionError("Job not owned by this device.")
        status = "done" if ok else "failed"
        conn.execute(
            "UPDATE push_jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, (error or "")[:500], stamp(), job_id),
        )
    return True


def get_update_manifest(channel: str = "stable") -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT channel, version, url, sha256, published_at FROM update_manifests WHERE channel = ?",
            (channel,),
        ).fetchone()
    if not row:
        return None
    return dict(row)


def publish_update_manifest(channel: str, version: str, url: str, sha256: str) -> None:
    """Operator-only helper (CLI / admin). Not exposed on buyer MCP."""
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


def issue_device_token(user_id: int, device_id: str) -> str:
    if not user_owns_device(user_id, device_id):
        raise PermissionError("Device not linked to this account.")
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute(
            "INSERT INTO device_tokens (token, user_id, device_id, created_at, revoked) VALUES (?, ?, ?, ?, 0)",
            (token, user_id, device_id, stamp()),
        )
    return token
