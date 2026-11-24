# FennSill

USB e-ink panel software: Desk UI + always-on Agent service + factory flasher. Buyers' AIs talk to the **hosted cloud MCP** ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â nothing hosts MCP on the buyer PC.

Cloud MCP uses **SQLite** ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â **no SQL Server** required.

## One-click downloads (Windows)

**Latest release: [v0.1.28](https://github.com/KCarino18/Fennsill/releases/tag/v0.1.28)** — 2026-11-23

| What | Download |
|------|----------|
| **FennSill Setup** (Desk + Agent service — run as Admin once) | [FennsillSetup.exe](https://github.com/KCarino18/Fennsill/releases/download/v0.1.28/FennsillSetup.exe) |
| **FennSill Factory** (flasher — manufacturing PC) | [FennsillFactory.exe](https://github.com/KCarino18/Fennsill/releases/download/v0.1.28/FennsillFactory.exe) |
| **All releases** | [github.com/KCarino18/Fennsill/releases](https://github.com/KCarino18/Fennsill/releases) |


**Panels ship already flashed.** Buyers only need Setup + account + MCP.

**FennsillSetup.exe** (Admin once) installs:

- **Desk** ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â Device ID / serial / install key, Paste device key, panel status
- **FennSill Agent** ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â Windows service for USB cloud pushes (stays on when Desk is closed)
- **Python + Playwright** runtime (verified during Setup)
- **FennSill Quick Start.pdf** on the Desktop
- Registers under **Settings ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ Apps ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ Installed apps** (with Uninstall)

Page delivery is **MCP-only**. There is **no local Host**.

### Quick use (buyers)

1. Run **FennsillSetup.exe** as Administrator (allow UAC). Open the Desktop **Quick Start** PDF.
2. Plug in the panel over USB. Desk shows connected + Device ID.
3. On the FennSill account site: Link panel with Device ID ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ Mint device key ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â‚¬Å¾Ã‚Â¢ **Paste device key** in Desk.
4. Connect any AI that supports custom MCP: account MCP **URL** + header `Authorization: Bearer <token>` (Copy header). Device ID does not go in the MCP form.
5. Ask the AI to push a page; confirm the e-ink refreshes.

### Manufacturing

**Factory** (`FennsillFactory.exe`) is for flashing panels before they ship ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â not part of the buyer flow.

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
