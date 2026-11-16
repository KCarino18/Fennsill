"""Fennsill cloud MCP + agent API (SQLite). No USB. No SQL Server."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure cloud/ is on the path when run as a script or module.
CLOUD_ROOT = Path(__file__).resolve().parent
if str(CLOUD_ROOT) not in sys.path:
    sys.path.insert(0, str(CLOUD_ROOT))

from mcp.server.mcpserver import Context, MCPServer  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from starlette.requests import Request  # noqa: E402
from starlette.responses import FileResponse, JSONResponse, Response  # noqa: E402

import store  # noqa: E402
from security_artifact import (  # noqa: E402
    SecurityError,
    body_has_wifi_keys,
    validate_artifact_args,
    validate_device_id,
)

HOST = os.environ.get("FENNSILL_CLOUD_HOST", "0.0.0.0")
PORT = int(os.environ.get("FENNSILL_CLOUD_PORT", "8080"))
PUBLIC_URL = os.environ.get("FENNSILL_PUBLIC_URL", f"http://{HOST}:{PORT}").rstrip("/")
MCP_URL = os.environ.get("FENNSILL_PUBLIC_MCP_URL", f"{PUBLIC_URL}/mcp")
WEB_DIR = CLOUD_ROOT / "web"

# SQL Server later — do not enable:
# FENNSILL_SQL_CONNECTION = os.environ.get("FENNSILL_SQL_CONNECTION")

server = MCPServer(
    "fennsill-cloud",
    instructions=(
        "Fennsill cloud pushes finished 800x480 black/white self-contained HTML/SVG "
        "to the buyer's e-ink panel via a queued job. Call list_panels, then push_artifact "
        "with that device_id. After push_artifact, call get_push_status with the job_id "
        "(retry a few times) until status is done or failed — only then say the screen "
        "refreshed or report the error. Do not say 'unconfirmed' without checking. "
        "Offline at enqueue time is OK; the desk agent still delivers. "
        "Do not create a web Artifact preview as a substitute. "
        "Do not send Wi-Fi credentials — Wi-Fi stays on the panel via the local USB agent."
    ),
)


def _bearer(headers) -> str | None:
    if not headers:
        return None
    auth = headers.get("authorization") or headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _user_from_request(request: Request):
    return store.user_from_session(_bearer(request.headers))


def _device_from_request(request: Request):
    return store.auth_device_token(_bearer(request.headers))


def _json(status: int, payload):
    if status == 204:
        return Response(status_code=204)
    return JSONResponse(payload, status_code=status)


def _store_error(exc: store.StoreError):
    body = {"error": exc.message, "code": exc.code}
    return _json(exc.http_status, body)


async def _read_json(request: Request) -> dict | Response:
    try:
        raw = await request.body()
    except Exception:
        return _json(400, {"error": "Bad body."})
    if len(raw) > 1_048_576:
        return _json(413, {"error": "Body too large."})
    if not raw:
        data = {}
    else:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json(400, {"error": "Send JSON."})
    if not isinstance(data, dict):
        return _json(400, {"error": "Send a JSON object."})
    if body_has_wifi_keys(data):
        return _json(400, {"error": "Wi-Fi credentials stay on the panel."})
    return data


# --- HTTP API + account website (same container) ---


@server.custom_route("/", methods=["GET"])
async def homepage(_request: Request) -> Response:
    return FileResponse(WEB_DIR / "index.html")


@server.custom_route("/app.css", methods=["GET"])
async def app_css(_request: Request) -> Response:
    return FileResponse(WEB_DIR / "app.css", media_type="text/css")


@server.custom_route("/app.js", methods=["GET"])
async def app_js(_request: Request) -> Response:
    return FileResponse(WEB_DIR / "app.js", media_type="application/javascript")


@server.custom_route("/api/config", methods=["GET"])
async def api_config(_request: Request) -> Response:
    return _json(200, {"mcp_url": MCP_URL, "api_base": PUBLIC_URL})


@server.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> Response:
    return _json(200, {"ok": True, "service": "fennsill-cloud"})


@server.custom_route("/api/session", methods=["POST"])
async def api_session(request: Request) -> Response:
    body = await _read_json(request)
    if isinstance(body, Response):
        return body
    mode = str(body.get("mode") or "login")
    email = str(body.get("email") or "")
    password = body.get("password") or ""
    try:
        if mode == "signup":
            return _json(200, store.signup(email, password))
        if mode == "login":
            return _json(200, store.login(email, password))
        return _json(400, {"error": "Choose login or signup."})
    except store.StoreError as exc:
        return _store_error(exc)


@server.custom_route("/api/me", methods=["GET"])
async def api_me(request: Request) -> Response:
    user = _user_from_request(request)
    if not user:
        return _json(401, {"error": "Sign in first."})
    return _json(200, store.me(int(user["id"]), user["email"]))


@server.custom_route("/api/me/devices", methods=["GET"])
async def api_me_devices(request: Request) -> Response:
    user = _user_from_request(request)
    if not user:
        return _json(401, {"error": "Sign in first."})
    return _json(200, {"devices": store.list_devices(int(user["id"]))})


@server.custom_route("/api/devices", methods=["POST"])
async def api_devices(request: Request) -> Response:
    user = _user_from_request(request)
    if not user:
        return _json(401, {"error": "Sign in first."})
    body = await _read_json(request)
    if isinstance(body, Response):
        return body
    try:
        device_id = validate_device_id(str(body.get("device_id") or ""))
        label = str(body.get("label") or "")
        return _json(200, store.link_device(int(user["id"]), device_id, label))
    except SecurityError as exc:
        return _json(400, {"error": str(exc)})
    except store.StoreError as exc:
        return _store_error(exc)


@server.custom_route("/api/device/token", methods=["POST"])
async def api_device_token(request: Request) -> Response:
    user = _user_from_request(request)
    if not user:
        return _json(401, {"error": "Sign in first."})
    body = await _read_json(request)
    if isinstance(body, Response):
        return body
    try:
        device_id = validate_device_id(str(body.get("device_id") or ""))
        token = store.issue_device_token(int(user["id"]), device_id)
        return _json(200, {"device_id": device_id, "token": token})
    except SecurityError as exc:
        return _json(400, {"error": str(exc)})
    except store.StoreError as exc:
        return _store_error(exc)


@server.custom_route("/api/agent/heartbeat", methods=["GET"])
async def api_heartbeat(request: Request) -> Response:
    auth = _device_from_request(request)
    if not auth:
        return _json(401, {"error": "Device token required."})
    try:
        return _json(200, store.heartbeat(auth))
    except store.StoreError as exc:
        return _store_error(exc)


@server.custom_route("/api/agent/jobs/next", methods=["GET"])
async def api_jobs_next(request: Request) -> Response:
    auth = _device_from_request(request)
    if not auth:
        return _json(401, {"error": "Device token required."})
    try:
        job = store.claim_next_job(auth)
    except store.StoreError as exc:
        return _store_error(exc)
    if not job:
        return _json(204, None)
    return _json(200, job)


@server.custom_route("/api/agent/jobs/{job_id}/complete", methods=["POST"])
async def api_jobs_complete(request: Request) -> Response:
    auth = _device_from_request(request)
    if not auth:
        return _json(401, {"error": "Device token required."})
    job_id = request.path_params.get("job_id") or ""
    if not job_id or "/" in job_id or ".." in job_id:
        return _json(400, {"error": "Bad job id."})
    body = await _read_json(request)
    if isinstance(body, Response):
        return body
    try:
        store.complete_job(
            auth,
            job_id,
            ok=bool(body.get("ok", True)),
            error=str(body.get("error") or ""),
        )
        return _json(200, {"ok": True})
    except store.StoreError as exc:
        return _store_error(exc)


@server.custom_route("/api/updates/{channel}", methods=["GET"])
async def api_updates(request: Request) -> Response:
    channel = request.path_params.get("channel") or "stable"
    if "/" in channel or ".." in channel:
        return _json(400, {"error": "Bad channel."})
    manifest = store.get_update_manifest(channel)
    if not manifest:
        return _json(404, {"error": "No update published for this channel."})
    return _json(200, manifest)


# --- MCP tools (user session bearer via Context.headers) ---


def _mcp_user(ctx: Context):
    token = _bearer(ctx.headers)
    user = store.user_from_session(token)
    if not user:
        raise store.StoreError("unauthorized", "Authentication required.", 401)
    return user


def _tool_result(payload: Any) -> str:
    return json.dumps(payload, indent=2)


@server.tool(description="List Fennsill e-ink panels linked to this account.")
def list_panels(ctx: Context) -> str:
    try:
        user = _mcp_user(ctx)
        store.require_mcp_access(int(user["id"]))
        return _tool_result({"ok": True, "panels": store.list_devices(int(user["id"]))})
    except store.StoreError as exc:
        return _tool_result({"ok": False, "error": exc.message, "code": exc.code})


@server.tool(
    description=(
        "Push a finished 800x480 black/white HTML or SVG page to a linked Fennsill panel. "
        "Requires device_id from list_panels. Self-contained only — no external URLs. "
        "Returns job_id with status=queued. Then call get_push_status(job_id) until "
        "delivered=true (done) or status=failed. "
        "If list_panels shows offline, still enqueue — the desk agent will pick it up when online. "
        "Do not tell the user the push failed solely because online was false at enqueue time."
    )
)
def push_artifact(
    ctx: Context,
    device_id: str,
    html: str | None = None,
    svg: str | None = None,
    title: str = "",
) -> str:
    try:
        user = _mcp_user(ctx)
        args = validate_artifact_args(html=html, svg=svg, device_id=device_id)
        result = store.enqueue_job(
            user_id=int(user["id"]),
            device_id=args["device_id"],
            job_type="push",
            html=args["html"],
            svg=args["svg"],
            title=title or "",
        )
        return _tool_result(
            {
                "ok": True,
                **result,
                "delivered": False,
                "next": "Call get_push_status with this job_id until status is done or failed.",
            }
        )
    except SecurityError as exc:
        return _tool_result({"ok": False, "error": str(exc)})
    except store.StoreError as exc:
        return _tool_result({"ok": False, "error": exc.message, "code": exc.code})


@server.tool(
    description=(
        "Check whether a push_artifact job reached the panel. "
        "Pass job_id from push_artifact. Poll until status is done (delivered) or failed. "
        "Optionally pass device_id with no job_id to see recent pushes for that panel."
    )
)
def get_push_status(
    ctx: Context,
    job_id: str | None = None,
    device_id: str | None = None,
) -> str:
    try:
        user = _mcp_user(ctx)
        store.require_mcp_access(int(user["id"]))
        if job_id:
            return _tool_result({"ok": True, **store.get_job_for_user(int(user["id"]), job_id)})
        did = validate_device_id(device_id) if device_id else None
        jobs = store.recent_jobs_for_user(int(user["id"]), did, limit=5)
        return _tool_result({"ok": True, "jobs": jobs})
    except SecurityError as exc:
        return _tool_result({"ok": False, "error": str(exc)})
    except store.StoreError as exc:
        return _tool_result({"ok": False, "error": exc.message, "code": exc.code})


@server.tool(description="Start a recurring live feed job for a linked panel (agent runs the feed).")
def start_live_update(
    ctx: Context,
    device_id: str,
    kind: str,
    interval_sec: int = 300,
    title: str = "",
) -> str:
    try:
        user = _mcp_user(ctx)
        device_id = validate_device_id(device_id)
        if kind != "nfl_scores":
            raise SecurityError("Unsupported live feed kind.")
        interval_sec = int(interval_sec)
        if interval_sec < 60 or interval_sec > 3600:
            raise SecurityError("interval_sec must be between 60 and 3600.")
        result = store.enqueue_job(
            user_id=int(user["id"]),
            device_id=device_id,
            job_type="live_start",
            title=title or "",
            feed_kind=kind,
            interval_sec=interval_sec,
        )
        return _tool_result({"ok": True, **result})
    except SecurityError as exc:
        return _tool_result({"ok": False, "error": str(exc)})
    except store.StoreError as exc:
        return _tool_result({"ok": False, "error": exc.message, "code": exc.code})


@server.tool(description="Stop a live feed previously started with start_live_update.")
def stop_live_update(ctx: Context, device_id: str, kind: str | None = None) -> str:
    try:
        user = _mcp_user(ctx)
        device_id = validate_device_id(device_id)
        result = store.enqueue_job(
            user_id=int(user["id"]),
            device_id=device_id,
            job_type="live_stop",
            feed_kind=kind,
        )
        return _tool_result({"ok": True, **result})
    except SecurityError as exc:
        return _tool_result({"ok": False, "error": str(exc)})
    except store.StoreError as exc:
        return _tool_result({"ok": False, "error": exc.message, "code": exc.code})


# set_wifi is intentionally NOT registered.


def main() -> None:
    store.init_db()
    print(f"FENNSILL_CLOUD http://{HOST}:{PORT}/mcp", flush=True)
    print(f"FENNSILL_PUBLIC_URL {PUBLIC_URL}", flush=True)
    server.run(
        transport="streamable-http",
        host=HOST,
        port=PORT,
        streamable_http_path="/mcp",
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


if __name__ == "__main__":
    main()
