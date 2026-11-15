# Fennsill cloud server brief

Build spec for the hosted MCP, device key, and subscription service. November 14, 2026.

Fennsill hosts this service. Buyers never host MCP, never run Cloudflare tunnels, and never expose ports. Buyers run `Fennsill.exe` on the PC that has the USB e-ink panel. Claude, ChatGPT, Gemini, and the rest call the hosted MCP URL. Push jobs go only to that buyer’s paired device, and only while the account’s Fennsill access period is open.

## 1. Architecture

```text
Claude / ChatGPT / Gemini / Grok
        |  HTTPS Streamable HTTP MCP + user bearer
        v
Fennsill cloud (this build)
  - subscription clock (one row per account)
  - MCP tools at /mcp
  - device key check (key bound to the panel id)
  - push job queue (scoped to that device)
  - OTA manifests (read-only to clients)
        |  device key over HTTPS
        v
Fennsill.exe agent
  reads USB id=FSxxxxxxxxxxxx, heartbeats, polls jobs
        |  USB (not this build)
        v
Their panel only (800×480 e-ink)
```

The cloud process never opens USB or a COM port. “Plugged in” on the server means the agent has heartbeated for a linked panel id.

## 2. Device identity and the key

The panel id is defined in `docs/DEVICE.md`:

```text
device_id = "FS" + 12 uppercase hex digits of ESP.getEfuseMac()
example:   FSA1B2C3D4E5F6
USB:       READY … id=FSxxxxxxxxxxxx
           ID? → ID FSxxxxxxxxxxxx
```

That id is the lookup identity. It is printed on USB and is not a password. The Windows COM serial number is not the device id.

1. During link, the signed-in user submits the `device_id` the agent just read from the panel.
2. The server links that id to the account when this user already owns it, or when it is still unclaimed. An id owned by someone else returns 409. Ownership never moves to a second account.
3. The server mints a device key (bearer token) bound to that exact `device_id` and user. Return it once to `Fennsill.exe`. The panel does not store this key. Mint works while the access period has not started, so the agent can heartbeat.
4. The agent heartbeats with that key. The server sets `devices.last_seen_at`. That write is the activation signal. A heartbeat does not start the 30-day clock.
5. On every later agent call the server loads the key, checks it is unrevoked, and checks `token.device_id` is the linked device. A key for one panel cannot act as another panel. A device key does not authorize `/mcp`. A user session does not claim or complete jobs.

## 3. Subscription clock

This is Fennsill access to this server. It is separate from the local setup screen’s “which AI you already pay for” provider (Claude, ChatGPT, Gemini). Leave `server/app.py` and that provider table alone.

There is one clock per account. The first linked device that heartbeats, followed by the first MCP call, starts it. Later devices on that account share the same `current_period_end`.

Table `access_subscriptions`:

- `user_id` unique
- `status`: `pending`, `active`, or `inactive`
- `current_period_end` (ISO timestamp, null while pending)
- `started_at` (null until the clock starts)
- `updated_at`

### States

| Stored row | Meaning |
|---|---|
| `pending`, end is null | Signed up. Link, mint, and heartbeat leave this row pending. |
| `active`, end in the future | Access is on. |
| `active`, end in the past | The month is over. Leave status `active`. The past end is what blocks access, so a later MCP call cannot open a second free month. |
| `inactive` | An operator revoked access early. MCP must not turn this back into `active`. |

`subscribed` is computed on read: status is `active` and `current_period_end` is still ahead of now. It is not its own column.

### Signup

In the same transaction as the user, insert `status = pending`, `current_period_end = null`, `started_at = null`. Signup and login show `subscribed: false` and `status: "pending"`. Login does not move the period. Signup of an existing email returns 409 and does not grant another month.

### When the month starts

The clock starts once, on the first authenticated MCP request that finds the subscription still `pending` and at least one device this user owns with `last_seen_at` set. In that same transaction, before the tool runs, set:

- `status = active`
- `started_at = now (UTC)`
- `current_period_end = now + 30 days`

That first MCP call then proceeds. A later MCP call must not move `started_at` or `current_period_end`.

If the MCP call arrives before any linked device has heartbeated, leave the row `pending` and return 403 `device_not_activated`.

### Access rule

- `active` and `current_period_end` in the future: MCP tools and agent job routes work.
- `pending` and no heartbeat yet: MCP returns 403 `device_not_activated`. Do not enqueue.
- `pending` and a device has heartbeated: this MCP call starts the month, then runs the tool.
- `inactive`, or `active` with `current_period_end` already past: MCP tools, `jobs/next`, and job complete return 403 `subscription_inactive`. Do not enqueue, claim, or return job HTML. Do not start another free month.
- A missing subscription row is treated as inactive.

Renewal and early revoke are an operator write. One function, `set_access_subscription(email, active|inactive, current_period_end)`, is what a later payment webhook calls. The CLI can set a new future end (renew) or set `inactive` (stop access during the month). No card form in this build. No buyer route can change `status` or move `current_period_end` forward.

## 4. Server-side handling

The database row is the clock. Each request decides from that row. The service does not run a 30-day timer, a cron job, or a USB watcher.

### Heartbeat

`GET /api/agent/heartbeat` uses the device key. Confirm the key is unrevoked and bound to that `device_id`. While the row is `pending` or the month is still open, set `devices.last_seen_at` and stop. Do not read or write `current_period_end`. After expiry or revoke, return 403 and do not refresh `last_seen_at`.

### MCP, before the tool runs

1. Missing or bad user session → 401.
2. Load the subscription row.
3. If it is `pending`, look for any device this user owns with `last_seen_at` set. None → 403 `device_not_activated`. At least one → start the month, then run the tool.
4. If it is `inactive`, or `active` and the end is already past → 403 `subscription_inactive`.
5. Otherwise run the tool. `push_artifact` still checks that `device_id` belongs to this user.

### Job claim and complete

These routes never start the clock. While `pending`, `jobs/next` returns 204 and claims nothing. After the end date, or when status is `inactive`, claim and complete return 403 and do not hand out HTML.

### Start the month in one update

Two MCP calls at the same moment must not write two end dates. Call this only from the MCP auth step. Heartbeat, device link, and signup do not call it.

```sql
UPDATE access_subscriptions
SET status = 'active',
    started_at = ?,
    current_period_end = ?,
    updated_at = ?
WHERE user_id = ? AND status = 'pending'
```

`current_period_end` is that same timestamp plus 30 days. If the update changes a row, this call started the month. If it changes nothing, read the row again and use the end date the other call already stored. Wrap the check and the update in one `BEGIN IMMEDIATE` transaction. Put it in `begin_access_period(user_id)`.

### After the month

Every MCP and job request compares `current_period_end` to the current time. No scheduler is required for the cutoff. Renewal is a separate operator write: set `status = 'active'` and a new future `current_period_end`.

## 5. What already exists

Extend the Python cloud pieces. Do not rewrite from scratch. Do not import USB, serial, Playwright, or `intake_page` into the cloud process. Leave `connector/mcp_http_server.py` and `connector/mcp_server.py` alone. Those are the local USB Host.

- `docs/CLOUD_MCP.md`, `docs/SHIPPING.md`, `docs/DEVICE.md`
- `connector/tools.json` — stable tool names
- `connector/security.py` — `reject_external_uris`, 512KB artifact cap, control-character checks. Reuse it. It does not touch USB.
- `server/tenant_store.py` — SQLite users, sessions, devices, device tokens, push jobs, update manifests, enqueue / claim / complete. Add the subscription row and the checks here.
- `server/cloud_api.py` — health, update GET, claim, complete, list devices, mint token. It rejects JSON keys that look like Wi-Fi secrets. Fold this behavior into the service below.
- `server/app.py` — separate local setup server on port 8080. Do not merge it into the cloud process. It uses `server/fennsill.db` and a different `devices` schema, and its device link can move ownership. The cloud must not do that.

## 6. Process and config

One Python process. Official `mcp` SDK (`MCPServer`, the same import as `connector/mcp_http_server.py`) mounted on a Starlette/ASGI app so `/mcp` and the agent/account routes share one port. Stateless Streamable HTTP at `/mcp`. SQLite is the database. One replica is enough.

Default `FENNSILL_CLOUD_DB` to `server/cloud.db`, not `server/fennsill.db`.

Environment: `FENNSILL_CLOUD_DB`, `FENNSILL_CLOUD_HOST`, `FENNSILL_CLOUD_PORT`, `FENNSILL_PUBLIC_URL` (documented as `https://mcp.example/mcp`). No secrets in the repo.

Auth:

- Account routes and `/mcp`: `Authorization: Bearer <session token>` from signup/login. Return the token in the JSON body.
- Agent routes: `Authorization: Bearer <device key>` minted for the panel id the agent read.
- Missing or bad token on MCP → 401.
- Tool calls require an open period, or this call is the one that starts it because the device has already heartbeated. Agent job routes require the period to already be open.

## 7. MCP tools

Server instructions string: build 800×480 self-contained black-and-white HTML, call `list_panels` then `push_artifact` with that `device_id`, send the page to the panel through the tools, and do not send Wi-Fi credentials.

Do not register `set_wifi`. Wi-Fi stays on the panel through the local USB agent. If a request body contains `ssid`, `password`, `psk`, `passphrase`, or similar, reject it with 400 and do not store or log those fields.

| Tool | Server behavior |
|---|---|
| `list_panels` | Devices linked to this account only. `online: true` when `last_seen_at` is within about 60 seconds. This call can start the 30-day clock. Inactive or expired → 403 `subscription_inactive`. |
| `push_artifact` | Requires `device_id` (added on the cloud schema; the tool name stays `push_artifact`). The id must belong to this account. Missing, unknown, or someone else’s device → 403. One of html or svg, max 512KB, no `http`, `https`, `file`, or `javascript` URIs, using `connector/security.py`. Enqueue only. Return `{ job_id, device_id, status: "queued" }`. |
| `start_live_update` / `stop_live_update` | Enqueue `live_start` / `live_stop` for the caller’s device, with kind, interval, and title. Same ownership and subscription rules as push. Do not fetch live data in the cloud. |
| `set_wifi` | Not a cloud tool. |

Rate-limit pushes, including live start and stop, per account and per device (for example 30 per 10 minutes). Over limit → 429.

Claim must be atomic. Use one `BEGIN IMMEDIATE` transaction and update only a row still `queued` for this `user_id` and `device_id`. Statuses: `queued` → `claimed` → `done` or `failed`.

## 8. HTTP surface

Agent routes use the device key. The key’s `device_id` is the panel id the agent read over USB.

| Route | Behavior |
|---|---|
| `GET /api/agent/heartbeat` | Set `last_seen_at`. Allowed while `pending`. Inactive or expired → 403, and do not refresh `last_seen_at`. |
| `GET /api/agent/jobs/next` | Claim the next queued job for this device, or 204. While `pending`, return 204 and claim nothing. Inactive or expired → 403 and do not claim. This route never starts the clock. |
| `POST /api/agent/jobs/{id}/complete` | `{ ok, error? }` only when the job belongs to this device and the period is open. Otherwise 403. |
| `GET /api/updates/{channel}` | Read-only manifest `{ version, url, sha256, published_at }`. Unauthenticated. Writes stay closed. |

Account routes use the user session bearer.

| Route | Behavior |
|---|---|
| `POST /api/session` | `{ mode: "signup" or "login", email, password }` → `{ token, email, subscribed, status, current_period_end }`. Password at least 8 characters. Existing email on signup → 409. Bad login → 401. Signup leaves `pending` and a null end. |
| `GET /api/me` | `{ email, subscribed, status, started_at, current_period_end, devices }`. |
| `POST /api/devices` | Link `{ device_id, label? }`. `device_id` matches `^FS[0-9A-F]{12}$`. Linking does not start the clock. |
| `POST /api/device/token` | Mint the device key for a device this user owns. Succeeds while `pending` or while the period is open. After expiry or revoke → 403 `subscription_inactive`. |
| `GET /api/me/devices` | This user’s devices only, including `last_seen_at` and online. |

Operator CLI only (not MCP, not a buyer route):

- `set_access_subscription(email, active|inactive, current_period_end)` — renew or revoke. Signup and heartbeat do not call this. The first qualifying MCP call is the only automatic start.
- `publish_update_manifest(...)`

Schema additions on `tenant_store`: `devices.last_seen_at`, `access_subscriptions` as above, and a job kind (`push`, `live_start`, `live_stop`) plus the live-update fields. Keep html/svg on the job row. Jobs can be ephemeral. This is not a dashboard store.

## 9. Out of scope

- Buyers running FennsillHost or trycloudflare
- The cloud process opening USB or COM
- OAuth (bearer is this version)
- Card checkout (the first MCP call after a heartbeat grants 30 days; the operator CLI renews or revokes; a webhook can call the same function later)
- Postgres
- Long-term storage of dashboards
- Accepting or storing Wi-Fi passwords
- Treating `device_id` itself as the bearer secret
- A buyer route that extends or restarts the month
- Starting the month at signup, at device link, or at heartbeat
- Editing `dist/` or the local connector’s USB push path

## 10. Deliverables

1. One deployable service. Dockerfile or a short PaaS note. HTTPS is TLS in front of this process. The app serves `/mcp` and `/api/...`.
2. Env-based config.
3. README with a Subscription section and a Device key section. State that signup leaves the account `pending`, that plugging in the panel is an agent heartbeat, and that the first MCP call after that heartbeat sets `current_period_end` to 30 days later. Access stops when that time passes or an operator sets `inactive`. Document the path: create a user, link the panel id, mint the device key, heartbeat, call `/mcp` once as that user, confirm `subscribed: true`, point Claude or ChatGPT at `https://<host>/mcp` with the user bearer, and run a local agent stub that prints claimed jobs and completes them.
4. Tests on a temp database, listed below.
5. A short threat-model paragraph in the README: the panel id identifies the device and is not a secret; the device key is the secret and is useless for any other id; a stolen user token can enqueue only for that user’s devices and only while the period is open; the 30 days start only on the first MCP call after a real agent heartbeat, and buyers cannot reset that clock; a stolen device key can pull only that device’s jobs and only while the owner’s period is open; manifests are public-read and operator-write; Wi-Fi secrets never enter this service.

## 11. Tests

- Signup leaves `pending`, `subscribed: false`, and `current_period_end` null.
- Linking a device does not set `current_period_end`.
- Heartbeat while `pending` sets `last_seen_at` and still leaves `current_period_end` null.
- An MCP call before any heartbeat returns 403 `device_not_activated` and leaves the row `pending`.
- The first MCP call after a heartbeat sets `active`, `started_at` to now, and `current_period_end` about 30 days out, and the tool succeeds.
- A second MCP call does not move `started_at` or `current_period_end`.
- Two parallel first MCP calls result in one end date.
- Signup of the same email again returns 409 and does not start or move the period.
- A buyer request cannot change `status` or `current_period_end`.
- With `current_period_end` in the past, MCP push and `jobs/next` return 403 `subscription_inactive`, no job is claimed, and another MCP call does not open a new free month.
- Operator `inactive` during the month returns 403, and a later MCP call does not return the account to `active`.
- Operator renew to a future `current_period_end` restores push and claim.
- User A cannot claim or complete user B’s job.
- A key minted for A1 cannot claim a job for a different device.
- Unauthenticated MCP and push are rejected.
- User B cannot push to A’s device.
- `GET /api/updates/stable` returns a manifest written by the operator CLI.
- No MCP tool and no buyer route can overwrite the manifest.
- `set_wifi` is not a cloud tool.
- A Wi-Fi-looking JSON body is rejected and not stored.
- A `device_id` that is not `AP` plus 12 hex digits is rejected.

## 12. Acceptance

1. User A signs up. The response shows `subscribed: false`, `status: "pending"`, and `current_period_end: null`. A links device `FSA1B2C3D4E5F6` and mints a key. An MCP call before the agent heartbeats returns 403 `device_not_activated` and the clock is still unset.
2. The agent heartbeats with A’s key. `last_seen_at` is set. `current_period_end` is still null.
3. An MCP client authenticated as A calls `list_panels`. That call sees `FSA1B2C3D4E5F6` only, and it starts the month: `subscribed: true`, `current_period_end` 30 days out.
4. `push_artifact` with that `device_id` queues a job. A second call does not move `current_period_end`.
5. The agent with A’s key for that id claims the job. The agent with B’s key cannot. A key for a different id cannot.
6. User B cannot push to A’s device (403).
7. Set A’s `current_period_end` in the past, or set A `inactive`. The same MCP token and the same device key get 403 `subscription_inactive`. The agent does not receive further jobs, and another MCP call does not start a second free month.
8. `GET /api/updates/stable` returns the manifest. Nothing on the buyer MCP can change it, and nothing a buyer can call can extend their own month.

Keep the agent HTTP shapes stable so a later `Fennsill.exe` can read `ID?`, store the device key, heartbeat, poll `jobs/next`, and pass `html` into the existing local `intake_page(..., push=True)`.
