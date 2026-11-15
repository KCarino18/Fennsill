# Fennsill shipping checklist (MVP)

This is an engineering checklist, not legal advice. Have counsel review before
public sale / app-store distribution.

## Product split

| Binary | Role | Network |
|--------|------|---------|
| `Fennsill.exe` | Desk: USB panel + local workers that claim cloud jobs | Local USB only — **no** public MCP |
| `FennsillFactory.exe` | Manufacturing flash/provision | Local USB only |
| Cloud MCP (`cloud/`) | Hosted Streamable HTTP for Claude / ChatGPT | Fennsill-hosted |

**Do not ship** `FennsillHost.exe` or Cloudflare tunnels. Buyers use the account MCP URL + Bearer token.

## Security (already enforced or required before ship)

- **Tool allowlist** — only `list_panels`, `push_artifact`, live update, `set_wifi`.
- **Artifact size bounds** and rejection of external `http(s)/file/javascript` URIs in HTML/SVG.
- **Render sandbox** — Playwright viewport 800×480, no network for page fetch.
- **Serial lock** — single writer to the panel COM port.
- **Cloud MCP** — session bearer required; no unattended public tunnels on buyer PCs.

## Privacy

- Pages and Wi‑Fi credentials stay on the buyer’s PC / panel NVS unless they opt into OTA.
- Disclose: AI providers process prompts/HTML under **their** policies; Fennsill cloud stores account + device link + jobs.

## Firmware

- USB CDC frame protocol; OTA only via signed manifest path.
- Wi‑Fi secrets in Preferences (device flash) — disclose in privacy note; never log passwords.

## Before release build

1. Publish `Fennsill.exe` + `FennsillFactory.exe` + Setup; run Setup into LocalAppData.
2. Verify cloud MCP push reaches the desk agent / panel with the panel plugged in.
3. Verify ChatGPT / Claude custom MCP with account URL + `Authorization: Bearer …`.
4. Attach Privacy Policy + EULA URLs in Setup/README (counsel-provided).
