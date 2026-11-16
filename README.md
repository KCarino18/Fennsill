# FennSill

USB e-ink panel software: Desk UI + always-on Agent service + factory flasher. Buyers' AIs talk to the **hosted cloud MCP** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â nothing hosts MCP on the buyer PC.

Cloud MCP uses **SQLite** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â **no SQL Server** required.

## One-click downloads (Windows)

**Latest release: [v0.1.26](https://github.com/KCarino18/Fennsill/releases/tag/v0.1.26)** — 2026-11-16

| What | Download |
|------|----------|
| **FennSill Setup** (Desk + Agent service — run as Admin once) | [FennsillSetup.exe](https://github.com/KCarino18/Fennsill/releases/download/v0.1.26/FennsillSetup.exe) |
| **FennSill Factory** (flasher — manufacturing PC) | [FennsillFactory.exe](https://github.com/KCarino18/Fennsill/releases/download/v0.1.26/FennsillFactory.exe) |
| **All releases** | [github.com/KCarino18/Fennsill/releases](https://github.com/KCarino18/Fennsill/releases) |


**Panels ship already flashed.** Buyers only need Setup + account + MCP.

**FennsillSetup.exe** (Admin once) installs:

- **Desk** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Device ID / serial / install key, Paste device key, panel status
- **FennSill Agent** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Windows service for USB cloud pushes (stays on when Desk is closed)
- **Python + Playwright** runtime (verified during Setup)
- **FennSill Quick Start.pdf** on the Desktop
- Registers under **Settings ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ Apps ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ Installed apps** (with Uninstall)

Page delivery is **MCP-only**. There is **no local Host**.

### Quick use (buyers)

1. Run **FennsillSetup.exe** as Administrator (allow UAC). Open the Desktop **Quick Start** PDF.
2. Plug in the panel over USB. Desk shows connected + Device ID.
3. On the FennSill account site: Link panel with Device ID ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ Mint device key ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ **Paste device key** in Desk.
4. Connect any AI that supports custom MCP: account MCP **URL** + header `Authorization: Bearer <token>` (Copy header). Device ID does not go in the MCP form.
5. Ask the AI to push a page; confirm the e-ink refreshes.

### Manufacturing

**Factory** (`FennsillFactory.exe`) is for flashing panels before they ship ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â not part of the buyer flow.

### Run names on disk

- **Setup:** `FennsillSetup.exe`
- **Desk:** `Fennsill.exe` under `%LOCALAPPDATA%\FennsillApp\`
- **Agent service:** `FennsillAgent` (display name **FennSill Agent**, Automatic)
- **Install root:** `%LOCALAPPDATA%\FennsillApp\`

## Repo layout

| Path | Role |
|------|------|
| `fennsill-setup/` | Elevated Setup (Desk + Agent + runtime bootstrap + Quick Start PDF) |
| `fennsill-desk/` | Desk UI |
| `fennsill-agent/` | Windows service hosting `cloud_agent.py` |
| `fennsill-factory/` | Manufacturing flasher UI |
| `factory/` | Flash/provision scripts |
| `firmware/` | Panel firmware (ESP32-S3 + EE04) |
| `connector/` | USB push + runtime helpers |
| `cloud/` | Hosted MCP server (**SQLite**) + account UI |
| `installer/publish_release.ps1` | Ships GitHub release + README version links |

### Ship a GitHub release

```powershell
powershell -File installer\publish_release.ps1 -Version 0.1.24
```
