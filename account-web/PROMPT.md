# Prompt: build / deploy Fennsill account web

Point Claude / Cursor at **this folder** (`account-web/`).

## Prefer the main cloud container

The account UI is now also built into [`cloud/`](../cloud/) (same process as MCP). Prefer rebuilding **fennell-cloud** / `cloud/` so one container serves `https://mcp.fennsill.com/` (website) and `https://mcp.fennsill.com/mcp`.

Use **this** `account-web/` folder only if you want a separate site.

## Mission

Ship a small **account website** so buyers can:

1. Create an account or log in  
2. Copy the **MCP URL** + **bearer token** for Claude / ChatGPT  
3. Link their panel (`FS` + 12 hex)  
4. Mint a **device key** for `Fennsill.exe`

This is **not** the MCP server. The MCP API already lives at `https://mcp.fennsill.com`. This site is the human-facing signup UI that talks to that API.

## What is already here

| File | Role |
|------|------|
| `server.py` | Starlette app: static UI + JSON proxy to the cloud API |
| `web/index.html` | Signup / login / token / device UI |
| `web/app.css` | Styles |
| `web/app.js` | Front-end logic |
| `requirements.txt` | Dependencies |
| `Dockerfile` | Optional container |
| `README.md` | Run notes |

## Do

- Keep API calls going through this server’s `/api/*` proxy (avoids browser CORS issues).
- Default upstream: `https://mcp.fennsill.com` via `FENNSILL_API_BASE`.
- Do not open USB. Do not accept Wi-Fi passwords.
- Do not implement MCP tools here.

## Run locally

```bash
cd account-web
pip install -r requirements.txt
set FENNSILL_API_BASE=https://mcp.fennsill.com
set FENNSILL_PUBLIC_MCP_URL=https://mcp.fennsill.com/mcp
python server.py
```

Open `http://127.0.0.1:8090/`.

## Deploy

Put TLS in front. Example public URL: `https://account.fennsill.com`.  
Env:

```text
FENNSILL_API_BASE=https://mcp.fennsill.com
FENNSILL_PUBLIC_MCP_URL=https://mcp.fennsill.com/mcp
FENNSILL_ACCOUNT_HOST=0.0.0.0
FENNSILL_ACCOUNT_PORT=8090
```

## Done when

1. Signup returns a token shown on the page.  
2. “Copy header” yields `Bearer <token>`.  
3. MCP URL shows `https://mcp.fennsill.com/mcp`.  
4. Link device + mint device key work against the live cloud API.  
5. Login works for a second browser / person (4 people = 4 accounts).
