# Fennsill account web

Signup / login site so people can get an MCP bearer token for Claude or ChatGPT.

**Point Claude at this folder:** open [`PROMPT.md`](PROMPT.md).

## Quick start

```bash
cd account-web
pip install -r requirements.txt
python server.py
```

Open http://127.0.0.1:8090/

Talks to the live cloud API at `https://mcp.fennsill.com` by default.

## Env

| Variable | Default |
|----------|---------|
| `FENNSILL_API_BASE` | `https://mcp.fennsill.com` |
| `FENNSILL_PUBLIC_MCP_URL` | `https://mcp.fennsill.com/mcp` |
| `FENNSILL_ACCOUNT_HOST` | `0.0.0.0` |
| `FENNSILL_ACCOUNT_PORT` | `8090` |
