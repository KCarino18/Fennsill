"""Wire local MCP where it still helps (Cursor); Claude/ChatGPT use Host URL.

Claude Desktop and ChatGPT custom connectors need the hosted Streamable HTTP
MCP from Fennsill Host (Start-Fennsill-Host.bat) — not local stdio.
This installer keeps Cursor stdio and clears stale Claude/ChatGPT stdio entries.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP_SCRIPT = ROOT / "connector" / "mcp_server.py"
BROWSERS = ROOT / "connector" / "browsers"
STATUS_PATH = ROOT / "connector" / "setup_status.json"


def resolve_python() -> str:
    """Absolute interpreter for desktop MCP hosts.

    Claude Desktop / Electron apps often lack the user PATH, so bare
    ``python`` fails silently and tools never appear. Prefer the interpreter
    running this installer; skip the WindowsApps store stub.
    """
    candidates = [
        Path(sys.executable),
        Path(shutil.which("python") or ""),
        Path(shutil.which("py") or ""),
    ]
    for path in candidates:
        if not path or not str(path):
            continue
        resolved = path.resolve()
        text = str(resolved).lower()
        if "windowsapps" in text:
            continue
        if resolved.is_file():
            return str(resolved)
    # Last resort: keep bare name (better than nothing on PATH-rich shells).
    return sys.executable or "python"


def mcp_entry():
    return {
        "command": resolve_python(),
        "args": [str(MCP_SCRIPT)],
        "cwd": str(ROOT / "connector"),
        "env": {
            "PLAYWRIGHT_BROWSERS_PATH": str(BROWSERS),
            "FENNSILL_ROOT": str(ROOT),
        },
    }


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def merge_json_mcp(path: Path, key: str = "mcpServers") -> Path:
    data = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    servers = data.get(key)
    if not isinstance(servers, dict):
        servers = {}
    servers["fennsill"] = mcp_entry()
    data[key] = servers
    return write_json(path, data)


def _claude_config_paths() -> list[Path]:
    appdata = Path(os.environ.get("APPDATA", ""))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    paths: list[Path] = [appdata / "Claude" / "claude_desktop_config.json"]
    claude_data = local / "Claude-Data"
    if claude_data.is_dir():
        paths.extend(claude_data.glob("claude_*/claude_desktop_config.json"))
    packages = local / "Packages"
    if packages.is_dir():
        for pkg in packages.glob("Claude_*"):
            paths.append(pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json")
    return paths


def remove_json_mcp(path: Path, key: str = "mcpServers", name: str = "fennsill") -> Path | None:
    """Remove a named local stdio MCP entry; leave the rest of the config intact."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    servers = data.get(key)
    if not isinstance(servers, dict) or name not in servers:
        return None
    servers.pop(name, None)
    data[key] = servers
    write_json(path, data)
    return path


def clear_claude_chatgpt_stdio() -> list[Path]:
    """Drop stale local Fennsill stdio from Claude/ChatGPT — Host URL replaces it."""
    cleared: list[Path] = []
    for path in _claude_config_paths():
        done = remove_json_mcp(path)
        if done:
            cleared.append(done)
    appdata = Path(os.environ.get("APPDATA", ""))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    for path in (
        appdata / "OpenAI" / "ChatGPT" / "chatgpt_mcp_config.json",
        appdata / "ChatGPT" / "chatgpt_mcp_config.json",
    ):
        done = remove_json_mcp(path)
        if done:
            cleared.append(done)
    packages = local / "Packages"
    if packages.is_dir():
        for pkg in packages.glob("OpenAI.ChatGPT*"):
            path = pkg / "LocalCache" / "Roaming" / "ChatGPT" / "chatgpt_mcp_config.json"
            done = remove_json_mcp(path)
            if done:
                cleared.append(done)
    # Codex config.toml: strip [mcp_servers.fennsill] blocks if present.
    codex = Path(os.environ.get("USERPROFILE", "")) / ".codex" / "config.toml"
    if codex.is_file():
        text = codex.read_text(encoding="utf-8")
        cleaned = re.sub(
            r"\n?\[mcp_servers\.fennsill(?:\.env)?\][\s\S]*?(?=\n\[|\Z)",
            "\n",
            text,
        )
        cleaned = re.sub(
            r"\n?\[marketplaces\.fennsill_local\][\s\S]*?(?=\n\[|\Z)",
            "\n",
            cleaned,
        )
        cleaned = re.sub(
            r'\n?\[plugins\."fennsill@fennsill_local"\][\s\S]*?(?=\n\[|\Z)',
            "\n",
            cleaned,
        )
        if cleaned != text:
            codex.write_text(cleaned, encoding="utf-8")
            cleared.append(codex)
    return cleared


def install_claude_desktop() -> Path:
    """Deprecated for Claude: local stdio is no longer the path.

    Prefer Fennsill Host + Customize → Connectors (remote Streamable HTTP).
    Kept for manual/debug calls only.
    """
    paths = _claude_config_paths()
    written = [merge_json_mcp(p) for p in paths if p]
    for path in written:
        if "Claude-Data" in str(path):
            return path
    return written[0] if written else paths[0]


def install_cursor() -> list[Path]:
    return [
        merge_json_mcp(ROOT / ".cursor" / "mcp.json"),
        merge_json_mcp(Path(os.environ.get("USERPROFILE", "")) / ".cursor" / "mcp.json"),
    ]


def install_chatgpt_json() -> list[Path]:
    """Older / alternate ChatGPT desktop JSON configs."""
    appdata = Path(os.environ.get("APPDATA", ""))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    targets = [
        appdata / "OpenAI" / "ChatGPT" / "chatgpt_mcp_config.json",
        appdata / "ChatGPT" / "chatgpt_mcp_config.json",
    ]
    packages = local / "Packages"
    if packages.is_dir():
        for pkg in packages.glob("OpenAI.ChatGPT*"):
            targets.append(
                pkg / "LocalCache" / "Roaming" / "ChatGPT" / "chatgpt_mcp_config.json"
            )
    return [merge_json_mcp(path) for path in targets]


def _toml_quote(value: str) -> str:
    return json.dumps(value)


def _toml_win_path(value: str) -> str:
    """Match OpenAI bundled marketplace path style: single-quoted literal backslashes."""
    raw = value
    if os.name == "nt" and not raw.startswith("\\\\?\\"):
        raw = "\\\\?\\" + raw
    return "'" + raw.replace("'", "''") + "'"


def install_fennsill_codex_plugin() -> Path:
    """Local Codex marketplace with one Fennsill plugin (ChatGPT Desktop).

    Layout matches OpenAI bundled marketplaces:
      marketplace/plugins/fennsill/.codex-plugin/plugin.json
      marketplace/plugins/fennsill/.mcp.json
    """
    marketplace = ROOT / "connector" / "codex-marketplace"
    plugin_root = marketplace / "plugins" / "fennsill"
    plugin_meta = plugin_root / ".codex-plugin"
    plugin_meta.mkdir(parents=True, exist_ok=True)

    # Remove mistaken top-level plugin folder from earlier installs.
    stale = marketplace / "fennsill"
    if stale.is_dir() and stale.resolve() != plugin_root.resolve():
        shutil.rmtree(stale, ignore_errors=True)

    # Match OpenAI bundled layout: .agents/plugins/marketplace.json
    agents_plugins = marketplace / ".agents" / "plugins"
    agents_plugins.mkdir(parents=True, exist_ok=True)
    write_json(
        agents_plugins / "marketplace.json",
        {
            "name": "fennsill_local",
            "interface": {"displayName": "Fennsill"},
            "plugins": [
                {
                    "name": "fennsill",
                    "source": {"source": "local", "path": "./plugins/fennsill"},
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": "Productivity",
                }
            ],
        },
    )

    py = resolve_python()
    plugin_json = {
        "version": "1.0.0",
        "name": "fennsill",
        "mcpServers": "./.mcp.json",
        "description": "Push pages and live updates to your Fennsill e-ink panel.",
        "author": {"name": "Fennsill"},
    }
    mcp_json = {
        "mcpServers": {
            "fennsill": {
                "command": py,
                "args": [str(MCP_SCRIPT)],
                "cwd": str(ROOT / "connector"),
                "enabled": True,
                "startup_timeout_sec": 45,
                "tool_timeout_sec": 120,
                "default_tools_approval_mode": "auto",
                "env": {
                    "PLAYWRIGHT_BROWSERS_PATH": str(BROWSERS),
                    "FENNSILL_ROOT": str(ROOT),
                },
            }
        }
    }
    write_json(plugin_meta / "plugin.json", plugin_json)
    write_json(plugin_root / ".mcp.json", mcp_json)

    # Keep old path updated too (older installs / docs).
    legacy = ROOT / "connector" / "codex-plugin"
    legacy_meta = legacy / ".codex-plugin"
    legacy_meta.mkdir(parents=True, exist_ok=True)
    write_json(legacy_meta / "plugin.json", plugin_json)
    write_json(legacy / ".mcp.json", mcp_json)

    # Seed Codex plugin cache so Desktop can discover without rematerializing.
    cache = (
        Path(os.environ.get("USERPROFILE", ""))
        / ".codex"
        / "plugins"
        / "cache"
        / "fennsill_local"
        / "fennsill"
        / "1.0.0"
    )
    cache_meta = cache / ".codex-plugin"
    cache_meta.mkdir(parents=True, exist_ok=True)
    write_json(cache_meta / "plugin.json", plugin_json)
    write_json(cache / ".mcp.json", mcp_json)
    return marketplace


def install_chatgpt_codex() -> Path:
    """ChatGPT Desktop / Codex shared config: %USERPROFILE%\\.codex\\config.toml"""
    path = Path(os.environ.get("USERPROFILE", "")) / ".codex" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    marketplace = install_fennsill_codex_plugin()

    # Remove any previous fennsill tables / marketplace / plugin lines we own.
    cleaned = re.sub(
        r"\n?\[mcp_servers\.fennsill(?:\.env)?\][\s\S]*?(?=\n\[|\Z)",
        "\n",
        existing,
    )
    cleaned = re.sub(
        r"\n?\[marketplaces\.fennsill_local\][\s\S]*?(?=\n\[|\Z)",
        "\n",
        cleaned,
    )
    cleaned = re.sub(
        r'\n?\[plugins\."fennsill@fennsill_local"\][\s\S]*?(?=\n\[|\Z)',
        "\n",
        cleaned,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"

    py = resolve_python()
    block = "\n".join(
        [
            "",
            "[mcp_servers.fennsill]",
            f"command = {_toml_quote(py)}",
            f"args = [{_toml_quote(str(MCP_SCRIPT))}]",
            f"cwd = {_toml_quote(str(ROOT / 'connector'))}",
            "startup_timeout_sec = 45",
            "tool_timeout_sec = 120",
            "enabled = true",
            "",
            "[mcp_servers.fennsill.env]",
            f"PLAYWRIGHT_BROWSERS_PATH = {_toml_quote(str(BROWSERS))}",
            f"FENNSILL_ROOT = {_toml_quote(str(ROOT))}",
            "",
            "[marketplaces.fennsill_local]",
            'source_type = "local"',
            f"source = {_toml_win_path(str(marketplace))}",
            "",
            '[plugins."fennsill@fennsill_local"]',
            "enabled = true",
            "",
        ]
    )
    path.write_text(cleaned + block, encoding="utf-8")
    return path


def install_gemini_antigravity() -> Path | None:
    path = Path(os.environ.get("USERPROFILE", "")) / ".gemini" / "config" / "mcp_config.json"
    if path.parent.is_dir() or True:
        path.parent.mkdir(parents=True, exist_ok=True)
        return merge_json_mcp(path)
    return None


def install_copilot() -> Path | None:
    path = Path(os.environ.get("USERPROFILE", "")) / ".copilot" / "mcp-config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return merge_json_mcp(path)


def main():
    written = []
    cleared = clear_claude_chatgpt_stdio()
    for path in install_cursor():
        written.append(("cursor", str(path)))
    # Gemini / Copilot stay local-stdio optional (same machine). Claude/ChatGPT → Host.
    gem = install_gemini_antigravity()
    if gem:
        written.append(("gemini", str(gem)))
    cop = install_copilot()
    if cop:
        written.append(("copilot", str(cop)))

    status = {
        "ok": True,
        "message": (
            "Claude and ChatGPT use Fennsill Host (remote MCP URL), not local stdio. "
            "Run FennsillHost.exe → Start server → Start public link → Copy MCP URL "
            "into Customize → Connectors (Claude) or Plugins → custom MCP (ChatGPT). "
            "Cursor still uses local stdio."
        ),
        "apps": [
            "Cursor (local stdio)",
            "Claude Desktop (Fennsill Host URL + Connectors)",
            "ChatGPT (Fennsill Host URL + custom MCP)",
        ],
        "written": written,
        "cleared_stdio": [str(p) for p in cleared],
        "host": {
            "launcher": str(ROOT / "FennsillHost.exe"),
            "local_mcp": "http://127.0.0.1:8766/mcp",
            "setup_prompt": str(ROOT / "connector" / "prompts" / "remote_mcp_setup.md"),
            "push_prompt": str(ROOT / "connector" / "prompts" / "remote_mcp_push.md"),
        },
        "examples": [
            "Keep NFL scores up to date on my Fennsill panel",
            "Here is SQL output — make a graph and push it to the device",
        ],
    }
    write_json(STATUS_PATH, status)
    print(json.dumps(status, indent=2))
    for label, path in written:
        print(f"{label}\t{path}")
    for path in cleared:
        print(f"cleared\t{path}")


if __name__ == "__main__":
    main()
