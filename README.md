# Fennsill

USB e-ink panel software: desk app + factory flasher. Buyers’ AIs talk to the **hosted cloud MCP** — nothing hosts MCP on the buyer PC.

Cloud MCP uses **SQLite** — **no SQL Server** required.

## One-click downloads (Windows)

**Latest release: [v0.1.14](https://github.com/KCarino18/Fennsill/releases/tag/v0.1.14)** � 2026-11-15

| What | Download |
|------|----------|
| **Fennsill** (desk — self-installs to LocalAppData) | [Fennsill.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/Fennsill.exe) |
| **Fennsill Factory** (flasher — self-installs to LocalAppData) | [FennsillFactory.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/FennsillFactory.exe) |
| **Full setup zip** (optional; same apps + extras) | [Fennsill-Setup.zip](https://github.com/KCarino18/Fennsill/releases/latest/download/Fennsill-Setup.zip) |

Each `.exe` is a **full install**: first launch copies scripts/firmware into `%LOCALAPPDATA%\FennsillApp\` and creates a desktop shortcut. No `C:\factory` folder required.

There is **no Fennsill Host** — use the cloud account MCP URL.

### Run names on disk

- **Desk:** `Fennsill.exe` (release name). Local builds may produce `FennsillDesk.exe` if Windows blocks `Fennsill.exe`.
- **Factory:** `FennsillFactory.exe` next to the `factory/` scripts folder
- **Install root:** `%LOCALAPPDATA%\FennsillApp\`

### Quick use

1. **Factory** (manufacturing PC) — download **FennsillFactory.exe** (self-installs). Plug in the XIAO e-ink panel → open Factory → Check → Flash.
2. **Fennsill** — install/run on the buyer PC with the panel plugged in. Copy **Device ID / Serial / Install key** from the desk window.
3. **Account site** — Link your panel with the **Device ID** from the desk app (not the MCP form).
4. **Cloud MCP** (ChatGPT / Claude “Connect to a custom MCP”):
   - **URL** = MCP URL from the account site
   - Leave any **Bearer token** env-var field **empty**
   - **Headers** → `Authorization` = `Bearer <token>` from **Copy header**
   - Device ID does **not** go in the MCP connector form

## Repo layout

| Path | Role |
|------|------|
| `fennsill-desk/` | Desk UI (publishes `Fennsill.exe` / `FennsillDesk.exe`) |
| `fennsill-factory/` | `FennsillFactory.exe` UI source |
| `factory/` | Flash/provision scripts |
| `firmware/` | Panel firmware (ESP32-S3 + EE04) |
| `connector/` | USB push + install helpers (not a public MCP host) |
| `cloud/` | Hosted MCP server (**SQLite**) + account UI |
| `account-web/` | Standalone signup site — see [`account-web/PROMPT.md`](account-web/PROMPT.md) |
| `installer/build_dist.py` | Builds `dist/Fennsill` + `dist/factory` + `Fennsill-Setup.zip` |
| `docs/` | Shipping, device, cloud notes |

`fennsill-host/` is retired (local MCP / tunnels). Do not ship it.

## Fennsill Factory

Manufacturing tool (not the buyer desk app).

- **In this repo:** `factory/` (scripts) + `fennsill-factory/` (WinForms UI)
- **In the download zip:** `factory\` beside the apps
- **Optional on factory PCs:** copy that folder to `C:\factory`
- **Details:** [`factory/README.md`](factory/README.md)

```bat
python installer\build_dist.py
```

## Build from source

```bat
dotnet publish fennsill-desk\FennsillDesk.csproj -c Release -o releases\desk
dotnet publish fennsill-factory\FennsillFactory.csproj -c Release -o factory
dotnet publish fennsill-setup\FennsillSetup.csproj -c Release -o releases\setup
python installer\build_dist.py
```

### Ship a GitHub release (updates README version automatically)

```powershell
powershell -File installer\publish_release.ps1 -Version 0.1.14
powershell -File installer\publish_release.ps1 -Version 0.1.14 -Factory
```

That script builds the exe(s), rewrites the **Latest release** line in this README, commits, pushes, and runs `gh release create`.
