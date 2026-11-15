"""Security checks for the Fennsill MCP connector."""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "connector"))
sys.path.insert(0, str(ROOT / "templates"))
sys.path.insert(0, str(ROOT / "firmware"))

import mcp_server  # noqa: E402
import security  # noqa: E402
from artifact_frame import wrap_page  # noqa: E402
from usb_protocol import PanelLink  # noqa: E402


def expect(condition, message):
    if not condition:
        raise SystemExit(message)


def test_artifact_validation():
    try:
        security.validate_artifact_args({})
        raise SystemExit("empty artifact accepted")
    except security.SecurityError:
        pass
    try:
        security.validate_artifact_args({"html": '<img src="https://evil.example/x.png">'})
        raise SystemExit("https artifact accepted")
    except security.SecurityError as exc:
        expect("network" in str(exc).lower() or "file" in str(exc).lower(), exc)
    try:
        security.validate_artifact_args({"html": '<a href="file:///etc/passwd">x</a>'})
        raise SystemExit("file uri accepted")
    except security.SecurityError:
        pass
    try:
        security.validate_artifact_args({"html": "x" * (security.MAX_ARTIFACT_CHARS + 1)})
        raise SystemExit("oversized artifact accepted")
    except security.SecurityError:
        pass
    clean = security.validate_artifact_args({"html": "<h1>Today</h1>"})
    expect(clean["html"] == "<h1>Today</h1>" and clean["svg"] is None, clean)
    page = wrap_page(html=clean["html"])
    expect("Content-Security-Policy" in page and "connect-src 'none'" in page, page[:200])


def test_wifi_validation_and_redaction():
    try:
        security.validate_wifi_args({"ssid": "House", "password": "secret", "extra": 1})
        raise SystemExit("extra wifi field accepted")
    except security.SecurityError:
        pass
    try:
        security.validate_wifi_args({"ssid": "A" * 40, "password": "x"})
        raise SystemExit("long ssid accepted")
    except security.SecurityError:
        pass
    clean = security.validate_wifi_args({"ssid": "House", "password": "panel-only-secret"})
    expect(clean["password"] == "panel-only-secret", clean)
    text = security.redact("failed panel-only-secret store", ["panel-only-secret"])
    expect("panel-only-secret" not in text and "[redacted]" in text, text)


def test_message_limits():
    try:
        security.parse_content_length("0")
        raise SystemExit("zero length accepted")
    except security.SecurityError:
        pass
    try:
        security.parse_content_length(str(security.MAX_MESSAGE_BYTES + 1))
        raise SystemExit("huge message accepted")
    except security.SecurityError:
        pass
    expect(security.parse_content_length("12") == 12, "content length")
    try:
        security.load_json_object(b"[1,2,3]")
        raise SystemExit("array rpc accepted")
    except security.SecurityError:
        pass


def test_linked_provider_allowlist():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "linked.json"
        os.environ["FENNSILL_LINK"] = str(path)
        mcp_server.LINKED = path
        path.write_text(json.dumps({"email": "a@b.c", "provider": "not-a-real-ai"}), encoding="utf-8")
        try:
            security.read_linked_provider(path, ROOT)
            raise SystemExit("unknown provider accepted")
        except security.SecurityError:
            pass
        path.write_text(json.dumps({"email": "a@b.c", "provider": "claude"}), encoding="utf-8")
        expect(security.read_linked_provider(path, ROOT) == "claude", "claude link")
        path.write_text(json.dumps({"email": "a@b.c", "provider": "chatgpt"}), encoding="utf-8")
        expect(security.read_linked_provider(path, ROOT) == "chatgpt", "chatgpt link")
        path.write_text(json.dumps({"email": "a@b.c", "provider": "gemini"}), encoding="utf-8")
        expect(security.read_linked_provider(path, ROOT) == "gemini", "gemini link")
        path.write_text(json.dumps({"email": "a@b.c", "provider": "grok"}), encoding="utf-8")
        expect(security.read_linked_provider(path, ROOT) == "grok", "grok link")
        path.write_text(json.dumps({"email": "a@b.c", "provider": "cursor"}), encoding="utf-8")
        expect(security.read_linked_provider(path, ROOT) == "cursor", "cursor link")
        path.write_text(json.dumps({"email": "local", "provider": "local"}), encoding="utf-8")
        expect(security.read_linked_provider(path, ROOT) == "local", "local link")


def test_mcp_refuses_hostile_calls():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "linked.json"
        path.write_text(json.dumps({"email": "owner@example.com", "provider": "claude"}), encoding="utf-8")
        os.environ["FENNSILL_LINK"] = str(path)
        mcp_server.LINKED = path

        listed = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [tool["name"] for tool in listed["result"]["tools"]]
        expect(
            names == ["list_panels", "push_artifact", "start_live_update", "stop_live_update", "set_wifi"],
            names,
        )
        again = mcp_server.handle({"jsonrpc": "2.0", "id": 11, "method": "tools/list"})
        expect(again["result"]["tools"] is listed["result"]["tools"], "tools must stay frozen after the pull")
        for tool in listed["result"]["tools"]:
            expect(tool["inputSchema"].get("additionalProperties") is False, tool)
            expect(isinstance(tool["description"], str) and len(tool["description"]) > 8, tool["name"])

        bad = mcp_server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "push_artifact", "arguments": {"html": '<script src="https://x"></script>'}},
            },
            PanelLink(),
        )
        expect(bad["result"]["isError"] is True, bad)
        expect("https://" not in bad["result"]["content"][0]["text"].lower() or "network" in bad["result"]["content"][0]["text"].lower(), bad)

        secret = "super-secret-wifi"
        leaked = mcp_server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "set_wifi",
                    "arguments": {"ssid": "House", "password": secret, "token": secret},
                },
            },
            PanelLink(),
        )
        expect(leaked["result"]["isError"] is True, leaked)
        expect(secret not in leaked["result"]["content"][0]["text"], leaked)

        panel = PanelLink()
        ok = mcp_server.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "set_wifi", "arguments": {"ssid": "House", "password": secret}},
            },
            panel,
        )
        expect(ok["result"]["isError"] is False, ok)
        expect(panel.wifi == ("House", secret), panel.wifi)
        expect(secret not in path.read_text(encoding="utf-8"), "password saved on disk")


def test_pages_library():
    import pages_lib
    from render import render_market_movers

    with tempfile.TemporaryDirectory() as tmp:
        pages_lib.PAGES = Path(tmp)
        frame = render_market_movers()
        meta = pages_lib.save_page(frame, source="test", title="Sample")
        listed = pages_lib.list_pages()
        expect(len(listed) == 1 and listed[0]["id"] == meta["id"], listed)
        expect(pages_lib.delete_page(meta["id"]) is True, "delete")
        expect(pages_lib.list_pages() == [], "empty after delete")


if __name__ == "__main__":
    test_artifact_validation()
    test_wifi_validation_and_redaction()
    test_message_limits()
    test_linked_provider_allowlist()
    test_mcp_refuses_hostile_calls()
    test_pages_library()
    print("security ok")
