"""Fennsill account website — UI + proxy to cloud MCP API."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

API_BASE = os.environ.get("FENNSILL_API_BASE", "https://mcp.fennsill.com").rstrip("/")
MCP_URL = os.environ.get("FENNSILL_PUBLIC_MCP_URL", f"{API_BASE}/mcp")
HOST = os.environ.get("FENNSILL_ACCOUNT_HOST", "0.0.0.0")
PORT = int(os.environ.get("FENNSILL_ACCOUNT_PORT", "8090"))

ALLOWED_API = {
    "/api/session",
    "/api/me",
    "/api/me/devices",
    "/api/devices",
    "/api/device/token",
}


async def homepage(_: Request) -> FileResponse:
    return FileResponse(WEB / "index.html")


async def config(_: Request) -> JSONResponse:
    return JSONResponse({"mcp_url": MCP_URL, "api_base": API_BASE})


async def proxy(request: Request) -> Response:
    path = request.url.path
    if path not in ALLOWED_API:
        return JSONResponse({"error": "Not found."}, status_code=404)

    url = f"{API_BASE}{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    headers = {}
    auth = request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth
    content_type = request.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type

    body = await request.body()
    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream = await client.request(request.method, url, headers=headers, content=body)

    out_headers = {}
    if "content-type" in upstream.headers:
        out_headers["content-type"] = upstream.headers["content-type"]
    return Response(content=upstream.content, status_code=upstream.status_code, headers=out_headers)


routes = [
    Route("/", homepage),
    Route("/api/config", config, methods=["GET"]),
    Route("/api/session", proxy, methods=["POST"]),
    Route("/api/me", proxy, methods=["GET"]),
    Route("/api/me/devices", proxy, methods=["GET"]),
    Route("/api/devices", proxy, methods=["POST"]),
    Route("/api/device/token", proxy, methods=["POST"]),
    Mount("/", app=StaticFiles(directory=str(WEB)), name="static"),
]

app = Starlette(routes=routes)


def main() -> None:
    import uvicorn

    print(f"FENNSILL_ACCOUNT http://{HOST}:{PORT}/", flush=True)
    print(f"FENNSILL_API_BASE {API_BASE}", flush=True)
    print(f"FENNSILL_PUBLIC_MCP_URL {MCP_URL}", flush=True)
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
