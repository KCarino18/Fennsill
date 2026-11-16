# Fennsill

USB e-ink panel software: Desk UI + always-on Agent service + factory flasher. Buyersâ€™ AIs talk to the **hosted cloud MCP** â€” nothing hosts MCP on the buyer PC.

Cloud MCP uses **SQLite** â€” **no SQL Server** required.

## One-click downloads (Windows)

**Latest release: [v0.1.19](https://github.com/KCarino18/Fennsill/releases/tag/v0.1.19)** — 2026-11-16

| What | Download |
|------|----------|
| **Fennsill Setup** (Desk + Agent service — run as Admin once) | [FennsillSetup.exe](https://github.com/KCarino18/Fennsill/releases/download/v0.1.19/FennsillSetup.exe) |
| **Fennsill Factory** (flasher — manufacturing PC) | [FennsillFactory.exe](https://github.com/KCarino18/Fennsill/releases/download/v0.1.19/FennsillFactory.exe) |
| **All releases** | [github.com/KCarino18/Fennsill/releases](https://github.com/KCarino18/Fennsill/releases) |


**FennsillSetup.exe** (Admin once) installs:

- **Desk** â€” Device ID / serial / install key, Paste device key, panel status
- **Fennsill Agent** â€” Windows service that heartbeats and pushes MCP pages over USB (stays on when Desk is closed)
- Files under `%LOCALAPPDATA%\FennsillApp\` plus a desktop shortcut

Page delivery is **MCP-only** (no local Import HTML / Paste page). There is **no Fennsill Host** â€” use the cloud account MCP URL.

### Run names on disk

- **Setup:** `FennsillSetup.exe` (buyer install)
- **Desk:** `Fennsill.exe` under `%LOCALAPPDATA%\FennsillApp\`
- **Agent service:** `FennsillAgent` (Automatic) â†’ `FennsillAgent.exe`
- **Factory:** `FennsillFactory.exe`
- **Install root:** `%LOCALAPPDATA%\FennsillApp\`

### Quick use

1. **Factory** (manufacturing PC) â€” download **FennsillFactory.exe**. Plug in the XIAO e-ink panel â†’ open Factory â†’ Check â†’ Flash.
2. **Buyer PC** â€” run **FennsillSetup.exe** as Administrator once. Open Desk â†’ copy **Device ID / Serial / Install key**.
3. **Account site** â€” Link your panel with the **Device ID** from Desk (not the MCP form). Mint a **device key** â†’ **Paste device key** in Desk.
4. **Cloud MCP** (ChatGPT / Claude â€œConnect to a custom MCPâ€):
   - **URL** = MCP URL from the account site
   - Leave any **Bearer token** env-var field **empty**
   - **Headers** â†’ `Authorization` = `Bearer <token>` from **Copy header**
   - Device ID does **not** go in the MCP connector form

You can close Desk after pasting the device key; the Agent service keeps the panel checked in while USB is connected.

## Repo layout

| Path | Role |
|------|------|
| `fennsill-setup/` | Elevated Setup (Desk + Agent + payload) |
| `fennsill-desk/` | Desk UI |
| `fennsill-agent/` | Windows service hosting `cloud_agent.py` |
| `fennsill-factory/` | `FennsillFactory.exe` UI source |
| `factory/` | Flash/provision scripts |
| `firmware/` | Panel firmware (ESP32-S3 + EE04) |
| `connector/` | USB push + install helpers (not a public MCP host) |
| `cloud/` | Hosted MCP server (**SQLite**) + account UI |
| `account-web/` | Standalone signup site â€” see [`account-web/PROMPT.md`](account-web/PROMPT.md) |
| `installer/build_dist.py` | Builds `dist/Fennsill` + `dist/factory` + `Fennsill-Setup.zip` |
| `installer/publish_release.ps1` | Ships GitHub release + README version links |

## Local publish helpers

```bat
dotnet publish fennsill-desk\FennsillDesk.csproj -c Release -o releases\desk
dotnet publish fennsill-agent\FennsillAgent.csproj -c Release -o releases\agent
dotnet publish fennsill-factory\FennsillFactory.csproj -c Release -o factory
dotnet publish fennsill-setup\FennsillSetup.csproj -c Release -o releases\setup
python installer\build_dist.py
```

### Ship a GitHub release (updates README version + download links)

```powershell
powershell -File installer\publish_release.ps1 -Version 0.1.19
```

Builds Setup (Desk + Agent + scripts) + Factory, rewrites the **Latest release** line and download table URLs in this README, commits, pushes, and runs `gh release create`.
