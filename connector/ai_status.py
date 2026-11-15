"""Report which AI desktop apps Fennsill has wired up."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_MARKER = "fennsill"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _json_has_fennsill(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        data = json.loads(_read_text(path))
    except json.JSONDecodeError:
        return MCP_MARKER in _read_text(path).lower()
    if not isinstance(data, dict):
        return False
    for key in ("mcpServers", "servers"):
        servers = data.get(key)
        if isinstance(servers, dict) and MCP_MARKER in servers:
            return True
    return False


def _toml_has_fennsill(path: Path) -> bool:
    if not path.is_file():
        return False
    text = _read_text(path)
    return bool(re.search(r"\[mcp_servers\.fennsill\]", text))


def _exists_any(paths: list[Path]) -> bool:
    return any(p.is_file() for p in paths)


def _appdata(*parts: str) -> Path:
    return Path(os.environ.get("APPDATA", "")) / Path(*parts)


def _local(*parts: str) -> Path:
    return Path(os.environ.get("LOCALAPPDATA", "")) / Path(*parts)


def _home(*parts: str) -> Path:
    return Path(os.environ.get("USERPROFILE", "")) / Path(*parts)


def detect() -> list[dict]:
    apps = []

    claude_cfgs = [_appdata("Claude", "claude_desktop_config.json")]
    packages = _local("Packages")
    if packages.is_dir():
        claude_cfgs += list(packages.glob("Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json"))
    claude_data = _local("Claude-Data")
    if claude_data.is_dir():
        claude_cfgs += list(claude_data.glob("claude_*/claude_desktop_config.json"))
    claude_bins = [
        _local("AnthropicClaude", "claude.exe"),
        _local("Programs", "Claude", "Claude.exe"),
    ]
    claude_installed = (
        _exists_any(claude_bins)
        or claude_data.is_dir()
        or (packages.is_dir() and any(packages.glob("Claude_*")))
        or any(p.is_file() for p in claude_cfgs)
    )
    apps.append(
        {
            "id": "claude",
            "name": "Claude Desktop",
            "installed": claude_installed,
            "connected": any(_json_has_fennsill(p) for p in claude_cfgs),
        }
    )

    chatgpt_bins = [
        _local("Programs", "ChatGPT", "ChatGPT.exe"),
    ]
    chatgpt_json = [
        _appdata("OpenAI", "ChatGPT", "chatgpt_mcp_config.json"),
        _appdata("ChatGPT", "chatgpt_mcp_config.json"),
    ]
    if packages.is_dir():
        chatgpt_json += list(
            packages.glob("OpenAI.ChatGPT*/LocalCache/Roaming/ChatGPT/chatgpt_mcp_config.json")
        )
        chatgpt_bins += list(packages.glob("OpenAI.ChatGPT*/**/ChatGPT.exe"))
    codex = _home(".codex", "config.toml")
    apps.append(
        {
            "id": "chatgpt",
            "name": "ChatGPT Desktop",
            "installed": _exists_any(chatgpt_bins) or _toml_has_fennsill(codex) or any(p.is_file() for p in chatgpt_json),
            "connected": _toml_has_fennsill(codex) or any(_json_has_fennsill(p) for p in chatgpt_json),
        }
    )

    cursor_cfgs = [_home(".cursor", "mcp.json"), ROOT / ".cursor" / "mcp.json"]
    cursor_bins = [_local("Programs", "cursor", "Cursor.exe"), _local("Programs", "Cursor", "Cursor.exe")]
    apps.append(
        {
            "id": "cursor",
            "name": "Cursor",
            "installed": _exists_any(cursor_bins) or any(p.is_file() for p in cursor_cfgs),
            "connected": any(_json_has_fennsill(p) for p in cursor_cfgs),
        }
    )

    gemini_cfg = _home(".gemini", "config", "mcp_config.json")
    apps.append(
        {
            "id": "gemini",
            "name": "Gemini",
            "installed": gemini_cfg.is_file() or _local("Programs", "Google", "Gemini").exists(),
            "connected": _json_has_fennsill(gemini_cfg),
        }
    )

    grok_note = {
        "id": "grok",
        "name": "Grok",
        "installed": False,
        "connected": False,
        "note": "Use ChatGPT/Claude/Cursor desktop, or paste via AI that has Fennsill tools.",
    }
    apps.append(grok_note)

    copilot_cfg = _home(".copilot", "mcp-config.json")
    apps.append(
        {
            "id": "copilot",
            "name": "Copilot",
            "installed": copilot_cfg.is_file(),
            "connected": _json_has_fennsill(copilot_cfg),
        }
    )

    for app in apps:
        if app["connected"]:
            app["status"] = "Connected"
        elif app["installed"]:
            app["status"] = "Installed — reopen Fennsill with panel plugged in to connect"
        else:
            app["status"] = "Not installed"
    return apps


def main():
    print(json.dumps({"ok": True, "apps": detect()}, indent=2))


if __name__ == "__main__":
    main()
