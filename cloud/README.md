# Artiphact cloud MCP server

Hosted MCP + agent API for Artiphact. Buyers’ AIs call `/mcp`. Agents poll jobs with a device key. **SQLite** for now — SQL Server is commented out / unused.

This is **not** `connector/mcp_http_server.py` (local USB Host).

## Quick start (local)

```bash
cd cloud
pip install -r requirements.txt
set ARTIPHACT_CLOUD_DB=%CD%\cloud.db
set ARTIPHACT_CLOUD_HOST=127.0.0.1
set ARTIPHACT_CLOUD_PORT=8080
python main.py
```

Service: `http://127.0.0.1:8080/mcp` and `/api/...`

## Unraid / Docker

```bash
cd cloud
docker build -t artiphact-cloud .
docker run -d --name artiphact-cloud \
  -p 8080:8080 \
  -v artiphact_cloud_data:/data \
  -e ARTIPHACT_PUBLIC_URL=https://mcp.yourdomain.com \
  artiphact-cloud
```

Put TLS (Swag / NPM / reverse proxy) in front. Public URL should be `https://mcp.yourdomain.com/mcp`.

## Buyer flow

1. **Signup**
   ```bash
   curl -s -X POST http://127.0.0.1:8080/api/session \
     -H "Content-Type: application/json" \
     -d "{\"mode\":\"signup\",\"email\":\"you@example.com\",\"password\":\"password1\"}"
   ```
   Save `token`. Status is `pending`; the 30-day clock has not started.

2. **Link device** (id from panel `ID?` → `APA1B2C3D4E5F6`)
   ```bash
   curl -s -X POST http://127.0.0.1:8080/api/devices \
     -H "Authorization: Bearer USER_TOKEN" \
     -H "Content-Type: application/json" \
     -d "{\"device_id\":\"APA1B2C3D4E5F6\",\"label\":\"desk\"}"
   ```

3. **Mint device key**
   ```bash
   curl -s -X POST http://127.0.0.1:8080/api/device/token \
     -H "Authorization: Bearer USER_TOKEN" \
     -H "Content-Type: application/json" \
     -d "{\"device_id\":\"APA1B2C3D4E5F6\"}"
   ```

4. **Agent heartbeat** (starts activation, not the month)
   ```bash
   set ARTIPHACT_CLOUD_URL=http://127.0.0.1:8080
   set ARTIPHACT_DEVICE_TOKEN=DEVICE_TOKEN
   python scripts/agent_stub.py
   ```

5. **Point Claude / ChatGPT** at `https://mcp.yourdomain.com/mcp` with header:
   `Authorization: Bearer USER_TOKEN`

   First MCP call after heartbeat opens 30 days of access.

## Operator

```bash
cd cloud
python scripts/operator_cli.py publish-manifest stable 1.0.0 https://example.com/app.bin <sha256>
python scripts/operator_cli.py set-subscription you@example.com inactive
python scripts/operator_cli.py set-subscription you@example.com active 2027-01-01T00:00:00Z
```

## Env

| Variable | Meaning |
|----------|---------|
| `ARTIPHACT_CLOUD_DB` | SQLite path (default `./cloud.db` or `/data/cloud.db` in Docker) |
| `ARTIPHACT_CLOUD_HOST` | Bind host |
| `ARTIPHACT_CLOUD_PORT` | Bind port |
| `ARTIPHACT_PUBLIC_URL` | Public base URL for docs |
| `ARTIPHACT_SQL_CONNECTION` | **Unused** — SQL Server later |

## Tests

```bash
cd cloud
python -m unittest tests.test_cloud -v
```

## Threat model

The panel `device_id` identifies the board; it is not a secret. The device key is the secret and only works for that id. A stolen user session can enqueue jobs only for that user’s devices and only while the access period is open. The 30 days start only on the first MCP call after a real agent heartbeat; buyers cannot reset that clock. Manifests are public-read and operator-write. Wi-Fi secrets are never accepted by this service.
