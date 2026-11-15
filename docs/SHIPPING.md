# Fennsill shipping checklist (MVP)

This is an engineering checklist, not legal advice. Have counsel review before
public sale / app-store distribution.

## Product split

| Binary | Role | Network |
|--------|------|---------|
| `Fennsill.exe` | Desk: gallery, USB panel, local workers | Localhost bridge only — **no** public tunnel |
| `FennsillHost.exe` | Opt-in MCP for AI apps | Local `127.0.0.1:8766`; public Cloudflare **only** after explicit confirm |

## Security (already enforced or required before ship)

- **Tool allowlist** — only `list_panels`, `push_artifact`, live update, `set_wifi` ([`connector/security.py`](../connector/security.py)).
- **Artifact size bounds** and rejection of external `http(s)/file/javascript` URIs in HTML/SVG.
- **Render sandbox** — Playwright viewport 800×480, no network for page fetch.
- **Serial lock** — single writer to the panel COM port.
- **Hosted MCP** — prefer localhost for ChatGPT Desktop; public tunnel is opt-in and warned.
- **Do not ship** with unattended public tunnels or empty auth as the default buyer path for cloud AIs without a token / account gate.

## Privacy

- Pages and Wi‑Fi credentials stay on the buyer’s PC / panel NVS unless they opt into a public tunnel or OTA update URL.
- Gallery lives under `%LOCALAPPDATA%\Fennsill\connector\pages`.
- Disclose: AI providers (Claude/ChatGPT) process prompts/HTML under **their** policies; Fennsill does not host buyer chat content.

## Firmware

- USB CDC frame protocol; OTA only via signed manifest path ([`firmware/fennsill/fennsill.ino`](../firmware/fennsill/fennsill.ino)).
- Wi‑Fi secrets in Preferences (device flash) — disclose in privacy note; never log passwords.
- Regulatory: shipping a radio product requires the usual FCC/CE path for the module + host; keep manufacturer docs with the kit.

## Claims

- Do not claim “certified secure,” “hack-proof,” or that any AI is “connected” unless that connector is actually enabled in the AI app.
- Marketing: Fennsill displays pages the buyer’s AI generates; Fennsill is not the AI.

## Before release build

1. Publish `Fennsill.exe` + `FennsillHost.exe`; run Setup into LocalAppData.
2. Verify gallery updates on MCP push (same `FENNSILL_ROOT`).
3. Verify ChatGPT Desktop works with `http://127.0.0.1:8766/mcp` (no bearer).
4. Verify public tunnel shows the Host warning dialog.
5. Attach Privacy Policy + EULA URLs in Setup/README (counsel-provided).
