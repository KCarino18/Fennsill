# Artiphact

USB e-ink panel software: desk app, local MCP host for AI apps, and factory firmware flasher.

## One-click downloads (Windows)

| What | Download |
|------|----------|
| **Artiphact** (desk / gallery / USB panel) | [Artiphact.exe](https://github.com/KCarino18/artiphact/releases/latest/download/Artiphact.exe) |
| **Artiphact Host** (local MCP server for Claude / ChatGPT) | [ArtiphactHost.exe](https://github.com/KCarino18/artiphact/releases/latest/download/ArtiphactHost.exe) |
| **Artiphact Factory** (firmware flasher — wipe TRMNL, install Artiphact) | [ArtiphactFactory.exe](https://github.com/KCarino18/artiphact/releases/latest/download/ArtiphactFactory.exe) |

Or open the full [latest release](https://github.com/KCarino18/artiphact/releases/latest).

### Quick use

1. **Factory** — plug in the XIAO e-ink panel → Check → Flash (needs Python + `pip install esptool pyserial` on the factory PC; arduino-cli auto-downloads).
2. **Artiphact** — install/run on the buyer PC with the panel plugged in.
3. **Artiphact Host** — run for local MCP at `http://127.0.0.1:8766/mcp` and point Claude / ChatGPT at it.

## Repo layout

| Path | Role |
|------|------|
| `artiphact-desk/` | Artiphact.exe |
| `artiphact-host/` | ArtiphactHost.exe (MCP) |
| `artiphact-factory/` | ArtiphactFactory.exe UI |
| `factory/` | Flash/provision scripts used by the Factory exe |
| `firmware/` | Panel firmware (ESP32-S3 + EE04) |
| `connector/` | USB push, MCP tools, install helpers |
| `docs/` | Shipping, device, cloud notes |

## Build from source

```bat
dotnet publish artiphact-desk\ArtiphactDesk.csproj -c Release -o releases\desk
dotnet publish artiphact-host\ArtiphactHost.csproj -c Release -o releases\host
dotnet publish artiphact-factory\ArtiphactFactory.csproj -c Release -o releases\factory
```
