# Fennsill

USB e-ink panel software: desk app, local MCP host for AI apps, and factory firmware flasher.

## One-click downloads (Windows)

| What | Download |
|------|----------|
| **Fennsill** (desk / gallery / USB panel) | [Fennsill.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/Fennsill.exe) |
| **Fennsill Host** (local MCP server for Claude / ChatGPT) | [FennsillHost.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/FennsillHost.exe) |
| **Fennsill Factory** (firmware flasher — wipe TRMNL, install Fennsill) | [FennsillFactory.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/FennsillFactory.exe) |
| **Fennsill Setup** (install into LocalAppData) | [FennsillSetup.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/FennsillSetup.exe) |

Or open the full [latest release](https://github.com/KCarino18/Fennsill/releases/latest).

### Quick use

1. **Factory** — plug in the XIAO e-ink panel → Check → Flash (needs Python + `pip install esptool pyserial` on the factory PC; arduino-cli auto-downloads).
2. **Fennsill** — install/run on the buyer PC with the panel plugged in.
3. **Fennsill Host** — run for local MCP at `http://127.0.0.1:8766/mcp` and point Claude / ChatGPT at it.

## Repo layout

| Path | Role |
|------|------|
| `fennsill-desk/` | Fennsill.exe |
| `fennsill-host/` | FennsillHost.exe (MCP) |
| `fennsill-factory/` | FennsillFactory.exe UI |
| `factory/` | Flash/provision scripts used by the Factory exe |
| `firmware/` | Panel firmware (ESP32-S3 + EE04) |
| `connector/` | USB push, MCP tools, install helpers |
| `cloud/` | Hosted MCP server (SQLite) |
| `account-web/` | Signup site — point Claude at [`account-web/PROMPT.md`](account-web/PROMPT.md) |
| `docs/` | Shipping, device, cloud notes |

## Build from source

```bat
dotnet publish fennsill-desk\FennsillDesk.csproj -c Release -o releases\desk
dotnet publish fennsill-host\FennsillHost.csproj -c Release -o releases\host
dotnet publish fennsill-factory\FennsillFactory.csproj -c Release -o releases\factory
```
