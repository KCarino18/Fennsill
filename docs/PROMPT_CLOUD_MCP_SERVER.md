# Prompt: build Fennsill cloud MCP server (SQLite)

**Implemented in-repo:** see [`cloud/`](../cloud/) (`main.py`, `store.py`, Dockerfile, README, tests).

Point Claude / Cursor at **this file** to extend or redeploy. Build only what is below.

SQL Server is **out**. Do not connect to MSSQL. Use SQLite. Comment out or omit any `FENNSILL_SQL_CONNECTION` / pyodbc path.

---

## Mission

Build the **Fennsill hosted MCP server** that buyers’ AIs call. Fennsill runs it (Linux / Unraid Docker). Buyers never host MCP and never open ports.

Claude / ChatGPT call `https://mcp.<domain>/mcp`. Push jobs go to that buyer’s device only. A Windows `Fennsill.exe` agent (stub OK) polls jobs with a device key. This process **never** opens USB/COM.

```text
AI apps  --HTTPS+user bearer-->  THIS SERVICE (/mcp + /api)
                                      |
                                   SQLite
                                      ^
Agent  --device key HTTPS---------/
```

## Do not use as the cloud server

- `connector/mcp_http_server.py` — **local USB Host only** (reference for Streamable HTTP + tool names)
- `connector/mcp_server.py` — local USB push
- `server/app.py` — local setup UI; do not merge
- `server/fennsill.db` — wrong database

## Reuse as reference

- `docs/Fennsill-Cloud-Server-Brief.md` — full product rules
- `docs/DEVICE.md` — `device_id = AP` + 12 hex from panel USB
- `connector/tools.json` — tool names
- `connector/security.py` — 512KB + reject `http/https/file/javascript` URIs (copy or import; no USB)
- `server/tenant_store.py` / `server/cloud_api.py` — early SQLite/job shapes to extend

## Stack

- One Python process
- Official `mcp` SDK Streamable HTTP (`MCPServer`), mount so `/mcp` and `/api/*` share one port (Starlette/ASGI)
- SQLite: `FENNSILL_CLOUD_DB` (default `/data/cloud.db` in Docker)
- Dockerfile for Unraid / Linux. TLS reverse proxy in front → public `https://mcp.<domain>/mcp`
- Mount a volume on `/data` so SQLite survives restarts

```text
FENNSILL_CLOUD_DB=/data/cloud.db
FENNSILL_PUBLIC_URL=https://mcp.<domain>
FENNSILL_CLOUD_HOST=0.0.0.0
FENNSILL_CLOUD_PORT=8080
# FENNSILL_SQL_CONNECTION=...   # unused — SQL Server later
```

## Auth

- Account + `/mcp`: `Authorization: Bearer <session token>` from signup/login (return token in JSON)
- Agent: `Authorization: Bearer <device key>` bound to `device_id`
- Device key does not authorize `/mcp`. User session does not claim jobs.
- No anonymous MCP → 401

## Subscription clock (one row per account)

Table `access_subscriptions`: `pending` | `active` | `inactive`, plus `started_at`, `current_period_end`.

1. **Signup** → `pending`, `current_period_end` null. Login does not move the period.
2. **Heartbeat** → sets `devices.last_seen_at` only. Does **not** start the month.
3. **First MCP call** after a linked device has heartbeated → start month: `active`, `started_at=now`, `current_period_end=now+30 days` (one `BEGIN IMMEDIATE` update so parallel calls share one end).
4. MCP before any heartbeat → 403 `device_not_activated`.
5. Expired (`current_period_end` past) or `inactive` → 403 `subscription_inactive`. Do **not** open a second free month.
6. `jobs/next` never starts the clock. While `pending` → 204 (no claim).

`subscribed` is computed: `active` and end still in the future.

Operator CLI only (not buyer MCP): renew/revoke; publish update manifests. Buyers cannot extend their own month.

## Device id

- Pattern: `^FS[0-9A-F]{12}$` (from panel `ID?` / `READY`)
- Globally unique. Link does not transfer ownership → 409 if another user owns it.
- Id is not a secret. The **device key** is the secret.

## MCP tools

Server instructions: build 800×480 self-contained B/W HTML; call `list_panels` then `push_artifact` with that `device_id`; do not substitute a web Artifact; do not send Wi-Fi.

| Tool | Behavior |
|------|----------|
| `list_panels` | Own devices only; `online` if heartbeated ~60s. May start the month. |
| `push_artifact` | Requires `device_id`. Validate artifact (512KB, no external URIs). Enqueue job. Return `{ job_id, device_id, status: "queued" }`. No USB. |
| `start_live_update` / `stop_live_update` | Enqueue `live_start` / `live_stop`. Same ownership + subscription rules. |
| `set_wifi` | **Do not register.** Reject JSON with ssid/password/psk/passphrase (400; never store/log). |

Rate-limit pushes (~30 / 10 min per account+device) → 429.

## HTTP API

**Agent (device key)**

- `GET /api/agent/heartbeat`
- `GET /api/agent/jobs/next` — claim one queued job for this device, or 204
- `POST /api/agent/jobs/{id}/complete` — `{ ok, error? }` only if job belongs to this device
- `GET /api/updates/{channel}` — read-only `{ version, url, sha256, published_at }`

**Account (user session)**

- `POST /api/session` — `{ mode: "signup"|"login", email, password }` → `{ token, email, subscribed, status, current_period_end }`
- `GET /api/me`
- `POST /api/devices` — `{ device_id, label? }`
- `POST /api/device/token` — mint device key (OK while pending or active-unexpired)
- `GET /api/me/devices`

**Health:** `GET /health` → `{ ok: true, service: "fennsill-cloud" }`

Job statuses: `queued` → `claimed` → `done` | `failed`. Claim must be atomic.

## Deliverables

1. Runnable service + Dockerfile + short Unraid notes
2. README: signup → link device → mint key → heartbeat → point Claude/ChatGPT at `/mcp` with user bearer → agent stub prints claimed jobs
3. Tests: cross-tenant denied; unauth rejected; clock only after heartbeat+first MCP; expired → 403; no `set_wifi`; Wi-Fi body rejected; updates GET read-only; buyer cannot publish manifests
4. Short threat-model paragraph in README

## Acceptance

1. Signup → `pending`, end null
2. Link `FSA1B2C3D4E5F6`, mint key; MCP before heartbeat → `device_not_activated`
3. Heartbeat; first `list_panels` starts 30-day access
4. `push_artifact` queues; that device key claims; other key cannot
5. Other user cannot push to that device
6. Past end or `inactive` → 403; MCP does not grant another free month
7. `GET /api/updates/stable` works after operator publish; buyer MCP cannot overwrite it

## Out of scope

- SQL Server / MSSQL
- USB, Playwright, local Host, trycloudflare
- OAuth, card checkout
- Buyer self-renewal
- Editing `dist/` or local USB connector as the cloud
