"""Local + public HTTP bridge for Fennsill.

Local:  http://127.0.0.1:8765
Public: Cloudflare quick tunnel (https://….trycloudflare.com) while Fennsill
        is open — phones and cloud AIs can reach /drop and /v1/pages.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
sys.path.insert(0, str(ROOT / "connector"))
sys.path.insert(0, str(ROOT / "connector" / "runtime"))

from intake import intake_page  # noqa: E402
from mcp_server import handle as mcp_handle  # noqa: E402
from panel_ports import list_candidate_ports  # noqa: E402
from security import SecurityError, load_json_object  # noqa: E402

HOST = "127.0.0.1"
PORT = int(os.environ.get("FENNSILL_BRIDGE_PORT", "8765"))
TOKEN_PATH = Path(os.environ.get("FENNSILL_BRIDGE_TOKEN", ROOT / "connector" / "bridge_token.txt"))
PROMPT_PATH = ROOT / "connector" / "prompts" / "send_to_fennsill.md"
SETUP_PATH = ROOT / "connector" / "prompts" / "setup_for_any_ai.md"
DROP_PATH = ROOT / "connector" / "drop.html"
PUBLIC_URL_PATH = Path(os.environ.get("FENNSILL_PUBLIC_URL_FILE", ROOT / "connector" / "public_url.txt"))
BASE_URL = f"http://{HOST}:{PORT}"


def public_base() -> str:
    if PUBLIC_URL_PATH.is_file():
        url = PUBLIC_URL_PATH.read_text(encoding="utf-8").strip().rstrip("/")
        if url.startswith("https://"):
            return url
    return BASE_URL


def setup_text(token: str) -> str:
    base = public_base()
    if SETUP_PATH.is_file():
        body = SETUP_PATH.read_text(encoding="utf-8")
    else:
        body = (
            "Fennsill bridge\n"
            f"Base URL: {base}\n"
            f"Phone page: {base}/drop\n"
            f"OpenAPI: {base}/openapi.json\n"
            "Auth: Authorization: Bearer {{TOKEN}}\n"
        )
    body = body.replace("{{TOKEN}}", token)
    body = body.replace("http://127.0.0.1:8765", base)
    if "Phone page" not in body and "/drop" not in body:
        body += f"\n\n## Phone / any device\nOpen `{base}/drop` and paste HTML from any AI app.\n"
    return body


def ensure_token() -> str:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.is_file():
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if len(token) >= 16:
            return token
    token = secrets.token_urlsafe(24)
    TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
    return token


def openapi_doc():
    base = public_base()
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Fennsill bridge",
            "version": "1.1.0",
            "description": (
                "Deliver a finished 800x480 HTML/SVG page to Fennsill. "
                "Works from this PC, phones, and cloud AI actions via the public https URL."
            ),
        },
        "servers": [{"url": base}],
        "paths": {
            "/v1/panels": {
                "get": {
                    "operationId": "listPanels",
                    "summary": "List plugged-in Fennsill panels",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/v1/pages": {
                "post": {
                    "operationId": "createPage",
                    "summary": "Save and push an HTML/SVG page",
                    "security": [{"bearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "html": {"type": "string"},
                                        "svg": {"type": "string"},
                                        "title": {"type": "string"},
                                        "push": {"type": "boolean", "default": True},
                                        "source": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "FennsillBridge/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("bridge: " + (fmt % args) + "\n")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Fennsill-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, code: int, payload: dict):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def _text(self, code: int, text: str, content_type="text/plain; charset=utf-8"):
        raw = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def _bytes(self, code: int, raw: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def _auth_ok(self) -> bool:
        expected = getattr(self.server, "bridge_token", "")
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip() == expected
        if self.headers.get("X-Fennsill-Token", "").strip() == expected:
            return True
        # Allow token in query for simple phone bookmarks.
        query = parse_qs(urlparse(self.path).query)
        return (query.get("token") or [""])[0] == expected

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        token = getattr(self.server, "bridge_token", "")
        base = public_base()
        if path == "/":
            return self._json(
                200,
                {
                    "ok": True,
                    "service": "fennsill",
                    "message": "Talk to your AI (Claude Desktop / Cursor). It calls Fennsill tools directly.",
                    "mcp": f"{base}/mcp",
                    "base_url": base,
                },
            )
        if path == "/mcp":
            # Streamable HTTP discovery / idle GET
            return self._json(
                200,
                {
                    "ok": True,
                    "mcp": True,
                    "transport": "streamable-http",
                    "endpoint": f"{base}/mcp",
                    "auth": "none",
                    "note": "POST JSON-RPC here. Prefer Claude Desktop local MCP on the same PC.",
                },
            )
        if path == "/health":
            return self._json(
                200,
                {
                    "ok": True,
                    "service": "fennsill-bridge",
                    "base_url": base,
                    "local_url": BASE_URL,
                    "mcp": f"{base}/mcp",
                    "openapi": f"{base}/openapi.json",
                    "setup": f"{base}/setup",
                },
            )
        if path == "/drop":
            if DROP_PATH.is_file():
                return self._bytes(200, DROP_PATH.read_bytes(), "text/html; charset=utf-8")
            return self._text(404, "drop page missing")
        if path == "/openapi.json":
            return self._json(200, openapi_doc())
        if path == "/setup":
            return self._text(200, setup_text(token), "text/markdown; charset=utf-8")
        if path == "/link":
            return self._text(200, base + "\n")
        if path == "/prompt":
            if PROMPT_PATH.is_file():
                return self._text(200, PROMPT_PATH.read_text(encoding="utf-8"), "text/markdown; charset=utf-8")
            return self._text(404, "prompt missing")
        if path == "/v1/panels":
            # VID-only — do not open COM (MCP/desk may be pushing).
            panels = [
                {"port": p["port"], "description": p.get("description", "")}
                for p in list_candidate_ports()
            ]
            return self._json(200, {"panels": panels})
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > 1_048_576:
            return self._json(400, {"error": "Body too large or empty."})
        raw = self.rfile.read(length)

        if path == "/mcp":
            try:
                message = load_json_object(raw)
            except SecurityError as exc:
                return self._json(400, {"error": str(exc)})
            response = mcp_handle(message)
            if response is None:
                self.send_response(202)
                self._cors()
                self.end_headers()
                return
            return self._json(200, response)

        if path != "/v1/pages":
            return self._json(404, {"error": "not found"})
        if not self._auth_ok():
            return self._json(401, {"error": "Unauthorized."})
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        try:
            if ctype == "application/x-www-form-urlencoded":
                form = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
                data = {
                    "html": (form.get("html") or [""])[0],
                    "svg": (form.get("svg") or [""])[0] or None,
                    "title": (form.get("title") or [""])[0],
                    "push": (form.get("push") or ["true"])[0].lower() != "false",
                    "source": (form.get("source") or ["form"])[0],
                }
            else:
                data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._json(400, {"error": "JSON or form body required."})
        if not isinstance(data, dict):
            return self._json(400, {"error": "JSON object required."})
        try:
            result = intake_page(
                html=data.get("html") or None,
                svg=data.get("svg") or None,
                title=str(data.get("title") or ""),
                source=str(data.get("source") or "http-bridge"),
                push=bool(data.get("push", True)),
            )
            return self._json(200, result)
        except SecurityError as exc:
            return self._json(400, {"error": str(exc)})
        except Exception:
            return self._json(500, {"error": "Intake failed."})


def serve_forever(port: int = PORT):
    token = ensure_token()
    server = ThreadingHTTPServer((HOST, port), Handler)
    server.bridge_token = token
    print(f"Fennsill bridge {BASE_URL} (token in {TOKEN_PATH})", flush=True)
    server.serve_forever()


def start_background(port: int = PORT):
    token = ensure_token()
    server = ThreadingHTTPServer((HOST, port), Handler)
    server.bridge_token = token
    thread = threading.Thread(target=server.serve_forever, name="fennsill-bridge", daemon=True)
    thread.start()
    return {"host": HOST, "port": port, "token": token, "server": server, "thread": thread}


if __name__ == "__main__":
    serve_forever()
