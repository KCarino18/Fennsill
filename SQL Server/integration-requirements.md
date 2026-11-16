# What each app needs to talk to SQL Server / cloud

SQL Server is owned by the **Fennsill cloud** process (or a tightly controlled factory import path). Buyer apps do **not** open a direct SQL connection. They talk HTTPS to the cloud API / MCP.

## Communications matrix

| Client | Talks to | Auth | Needs configured | Writes / reads |
|--------|----------|------|------------------|----------------|
| **Factory PC / FennsillFactory** | Cloud factory import API (preferred) or secured SQL insert tool | `FENNSILL_FACTORY_IMPORT_TOKEN` | Cloud base URL, factory token, local `master.key` (offline only) | Insert `manufactured_devices`: `device_id`, `box_serial`, `key_fingerprint`, `fw_version`, `provisioned_at`. Never upload MCU secret. |
| **Account website** (`cloud/web` or `account-web/`) | Same host as MCP (`https://mcp.fennsill.com`) | User email/password → session bearer | `FENNSILL_PUBLIC_URL`, `FENNSILL_PUBLIC_MCP_URL` | Signup/login, claim by product id (serial), mint device key, show MCP URL + Bearer header |
| **Cloud MCP + API** | SQL Server via `FENNSILL_SQL_CONNECTION` | N/A (server-side) | SQL connection string, public URL, trial days=60, factory token | All tables in `schema.sql`; enforces claim + trial + MCP gate |
| **Fennsill Desk** (`fennsill-desk`) | Cloud HTTPS | Device key (after paste); optional user token later | Cloud base URL (default `https://mcp.fennsill.com`) | Paste key → `cloud_device_token.txt`; `POST /api/device/activate`; show online / subscription status |
| **Fennsill Agent** (`fennsill-agent` / `cloud_agent.py`) | Cloud HTTPS | `Authorization: Bearer <device key>` | Same token file path; cloud base URL | `GET /api/agent/heartbeat`, `GET /api/agent/jobs/next`, `POST .../complete` |
| **Claude / ChatGPT / other AI** | `https://mcp.fennsill.com/mcp` | `Authorization: Bearer <user session token>` | MCP URL + headers from account site | MCP tools only while subscribed |
| **Operator / future billing** | Cloud operator CLI or webhook | Operator secret / provider signature | Renew/revoke credentials | Update `access_subscriptions` only |

## Endpoints each client must know

### Factory

```http
POST /api/factory/devices
Authorization: Bearer <FENNSILL_FACTORY_IMPORT_TOKEN>
Content-Type: application/json

{
  "device_id": "FSA1B2C3D4E5F6",
  "box_serial": "FS-2511-000042",
  "key_fingerprint": "<non-secret fingerprint>",
  "fw_version": "1.2.0"
}
```

Idempotent on `device_id` / `box_serial`. Reject secret fields if present.

### Account (user session)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/session` | signup/login → `{ token, email, subscribed, status, current_period_end }` |
| `GET` | `/api/me` | account + subscription view |
| `POST` | `/api/devices/claim` | `{ box_serial }` or product_id → link inventory device |
| `POST` | `/api/device/token` | mint cloud device key (OK while pending) |
| `GET` | `/api/me/devices` | list owned panels |

### Desk / Agent (device key)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/device/activate` | **start 60-day trial** (idempotent) |
| `GET` | `/api/agent/heartbeat` | refresh `last_seen_at` |
| `GET` | `/api/agent/jobs/next` | claim job or 204; never starts trial |
| `POST` | `/api/agent/jobs/{id}/complete` | ack job |
| `GET` | `/api/updates/{channel}` | OTA manifest |

### AI (user session)

| Surface | Purpose |
|---------|---------|
| `https://mcp.fennsill.com/mcp` | Streamable HTTP MCP |
| Tools: `list_panels`, `push_artifact`, live start/stop | All gated on active subscription |

## Local files on the buyer PC

| Path | Contents |
|------|----------|
| `%LOCALAPPDATA%\FennsillApp\cloud_device_token.txt` | Cloud device key (one line) |
| `%LOCALAPPDATA%\FennsillApp\device_bind.json` | Local USB bind metadata (`device_id`, `serial`, install_key). Not sufficient for MCP alone. |

## Secrets checklist (who holds what)

| Secret | Held by | Must NOT be in |
|--------|---------|----------------|
| SQL Server password / connection string | Cloud host / Unraid env | Buyer apps, firmware, git |
| Factory import token | Factory PC + cloud env | Buyer apps, public docs with real value |
| Factory `master.key` | Factory PC offline | SQL Server, cloud, buyer PC |
| MCU device secret | Panel NVS only | SQL Server, cloud |
| User session bearer | Buyer + AI MCP config | Device token table as the same value |
| Cloud device key | Account mint once → Desk/Agent file | MCP AI config (wrong credential type) |

## Env vars summary

See [`env.example`](env.example).

Minimum for cloud cutover:

1. `FENNSILL_SQL_CONNECTION`
2. `FENNSILL_PUBLIC_URL` / `FENNSILL_PUBLIC_MCP_URL`
3. `FENNSILL_FACTORY_IMPORT_TOKEN`
4. `FENNSILL_TRIAL_DAYS=60`

Minimum for factory upload:

1. Cloud base URL
2. Factory import token
3. Working provision tool that emits real `device_id` + `box_serial`

Minimum for FennSill Desk/Agent (buyer):

1. Reachable `https://mcp.fennsill.com`
2. Pasted device key file
3. Activate call on paste (new on this branch)

Minimum for AI:

1. MCP URL
2. `Authorization: Bearer <user session token>` from signup/login

## Branch rule for implementers

Wire these clients on `feature/sqlserver-subscriptions`. Do not point production buyers at SQL Server–backed behavior until cutover is approved. Keep SQLite env working as rollback.
