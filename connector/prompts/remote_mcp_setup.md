# Fennsill remote MCP setup

Use this **public MCP URL** (Streamable HTTP):

`{{MCP_URL}}`

## What goes where

| Field | Value |
|------|--------|
| **URL** | `{{MCP_URL}}` (the MCP URL) |
| **Bearer token env-var** | Leave **empty** |
| **Headers → Authorization** | `Bearer <token>` from the account site **Copy header** |
| **Device ID** | **Not** in this MCP form — paste into the website **Link your panel** from the desk app |

## Claude Desktop

1. Open **Customize → Connectors**.
2. **+ Add** → **Add custom connector**.
3. Name: `Fennsill`
4. URL: `{{MCP_URL}}`
5. Auth: leave bearer env empty; set header `Authorization` = `Bearer <token>` (or “No sign-in” only for local Host).
6. Save, then start a **new chat** and enable the **Fennsill** connector.

## ChatGPT

1. Open **Connect to a custom MCP** (Plugins / Settings → MCP / Connectors).
2. Name: `Fennsill`
3. URL: `{{MCP_URL}}`
4. Leave Bearer token env-var empty; Headers Authorization = `Bearer <token>`.
5. Create / install, then start a **new chat** and select Fennsill.

Local LAN URL (same PC only): `{{LOCAL_MCP_URL}}`

Keep **Fennsill Host** running for local MCP, or use the cloud account token for hosted MCP.
