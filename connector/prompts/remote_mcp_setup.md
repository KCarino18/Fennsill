# Fennsill cloud MCP setup

Use this **public MCP URL** (Streamable HTTP) from your Fennsill account site:

`{{MCP_URL}}`

There is **no local Host app**. Buyers do not run MCP on the PC.

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
5. Auth: leave bearer env empty; set header `Authorization` = `Bearer <token>`.
6. Save, then start a **new chat** and enable the **Fennsill** connector.

## ChatGPT

1. Open **Connect to a custom MCP** (Plugins / Settings → MCP / Connectors).
2. Name: `Fennsill`
3. URL: `{{MCP_URL}}`
4. Leave Bearer token env-var empty; Headers Authorization = `Bearer <token>`.
5. Create / install, then start a **new chat** and select Fennsill.

Keep **Fennsill.exe** (desk) open with the panel plugged in so the PC can claim cloud push jobs over USB.
