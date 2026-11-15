# Fennsill remote MCP setup

Use this **public MCP URL** (Streamable HTTP, no sign-in):

`{{MCP_URL}}`

## Claude Desktop

1. Open **Customize → Connectors**.
2. **+ Add** → **Add custom connector**.
3. Name: `Fennsill`
4. URL: `{{MCP_URL}}`
5. Authentication: **No sign-in**
6. Save, then start a **new chat** and enable the **Fennsill** connector for that chat.

## ChatGPT

1. Open **Plugins → Add custom MCP server** (or Settings → MCP / Connectors).
2. Name: `Fennsill`
3. URL: `{{MCP_URL}}`
4. Authentication: **No authentication**
5. Create / install the plugin, then start a **new chat** and select Fennsill (`@`).

Local LAN URL (same PC only, not for Claude/ChatGPT cloud): `{{LOCAL_MCP_URL}}`

Keep **Fennsill Host** running while you use the connector (server + public tunnel).
