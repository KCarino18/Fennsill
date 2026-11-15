# Fennsill

USB e-ink panel software: desk app, local MCP host for AI apps, and factory firmware flasher.

Cloud MCP uses **SQLite** — **no SQL Server** required.

## One-click downloads (Windows)

| What | Download |
|------|----------|
| **Fennsill** (desk / USB panel) | [Fennsill.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/Fennsill.exe) |
| **Fennsill Host** (local MCP for Claude / ChatGPT) | [FennsillHost.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/FennsillHost.exe) |
| **Fennsill Factory** (firmware flasher — wipe TRMNL, install Fennsill) | [FennsillFactory.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/FennsillFactory.exe) |
| **Fennsill Setup** (install into LocalAppData) | [FennsillSetup.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/FennsillSetup.exe) |
| **Full setup zip** (apps + `connector/` + **`factory/`**) | [latest release](https://github.com/KCarino18/Fennsill/releases/latest) (`Fennsill-Setup.zip`) |

Or open the full [latest release](https://github.com/KCarino18/Fennsill/releases/latest).

### Run names on disk

- **Desk:** `Fennsill.exe` (release name). Local builds may produce `FennsillDesk.exe` if Windows blocks `Fennsill.exe` — same app; Setup/zip still ship `Fennsill.exe` when possible.
- **Host:** `FennsillHost.exe`
- **Factory:** `FennsillFactory.exe` next to the `factory/` scripts folder
- **Install root:** `%LOCALAPPDATA%\Fennsill\`

### Quick use

1. **Factory** (manufacturing PC) — keep the `factory/` folder from the zip (or copy it to `C:\factory`). Plug in the XIAO e-ink panel → open **FennsillFactory.exe** → Check → Flash (needs Python + `pip install esptool pyserial`; arduino-cli auto-downloads).
2. **Fennsill** — install/run on the buyer PC with the panel plugged in. Copy **Device ID / Serial / Install key** from the desk window.
3. **Account site** — Link your panel with the **Device ID** from the desk app (not the MCP form).
4. **Cloud MCP** (ChatGPT / Claude “Connect to a custom MCP”):
   - **URL** = MCP URL from the account site
   - Leave any **Bearer token** env-var field **empty**
   - **Headers** → `Authorization` = `Bearer <token>` from **Copy header**
   - Device ID does **not** go in the MCP connector form
5. **Fennsill Host** (optional local MCP) — `http://127.0.0.1:8766/mcp`

## Repo layout

| Path | Role |
|------|------|
| `fennsill-desk/` | Desk UI (publishes `Fennsill.exe` / `FennsillDesk.exe`) |
| `fennsill-host/` | `FennsillHost.exe` (local MCP) |
| `fennsill-factory/` | `FennsillFactory.exe` UI source |
| `factory/` | Flash/provision scripts + built `FennsillFactory.exe` (gitignored exe; ships in zip/releases) |
| `firmware/` | Panel firmware (ESP32-S3 + EE04) |
| `connector/` | USB push, MCP tools, install helpers |
| `connector/identity_status.py` / `device_bind_tool.py` | Desk identity helpers (aliases when classic names are blocked) |
| `connector/runtime/` | Fallback copies of connector scripts |
| `cloud/` | Hosted MCP server (**SQLite**) + account UI |
| `account-web/` | Standalone signup site — see [`account-web/PROMPT.md`](account-web/PROMPT.md) |
| `installer/build_dist.py` | Builds `dist/Fennsill` + `dist/factory` + `Fennsill-Setup.zip` |
| `docs/` | Shipping, device, cloud notes |

## Fennsill Factory

Manufacturing tool (not the buyer desk app). Branding is **Fennsill Factory** (formerly Artiphact Factory).

- **In this repo:** `factory/` (scripts) + `fennsill-factory/` (WinForms UI)
- **In the download zip:** `factory\` beside the apps (so it is not missing next to the project)
- **Optional on factory PCs:** copy that folder to `C:\factory`
- **Build exe:** `factory\Build-Factory-Exe.bat` → `factory\FennsillFactory.exe`
- **Details:** [`factory/README.md`](factory/README.md)

```bat
python installer\build_dist.py
```

Produces `dist\Fennsill\` (buyer payload including nested `factory\`) and `dist\factory\` (standalone factory tree).

## Build from source

```bat
dotnet publish fennsill-desk\FennsillDesk.csproj -c Release -o releases\desk
dotnet publish fennsill-host\FennsillHost.csproj -c Release -o releases\host
dotnet publish fennsill-factory\FennsillFactory.csproj -c Release -o factory
dotnet publish fennsill-setup\FennsillSetup.csproj -c Release -o releases\setup
python installer\build_dist.py
```
