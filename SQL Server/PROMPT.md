# Prompt: implement Fennsill SQL Server + registration + 60-day trial

Point Claude / Cursor at **this folder** (`SQL Server/`) and the related reference paths below. Implement only what this prompt specifies. Stay on branch **`feature/sqlserver-subscriptions`**. Do **not** merge subscription / SQL Server cutover to `main` or point live production at SQL Server until the owner explicitly approves cutover.

---

## Mission

Make Fennsill’s hosted cloud work with **Microsoft SQL Server** for:

1. Factory **presave** of real panel identity (device id + box serial) before ship  
2. Buyer **signup** (email/password) + **product id claim** (box serial)  
3. Minting and storing **user session** + **device keys**  
4. **60-day trial** started when FennSill Desk activates after the buyer pastes the device key  
5. **MCP + agent jobs only while the subscription is active/unexpired**

Buyers never host MCP. Cloud never opens USB. MCU device secrets never enter SQL Server.

```text
Factory --import API--> SQL Server (manufactured_devices)
Buyer   --HTTPS-------> Cloud API / account UI
AI      --user bearer-> /mcp  (gated on subscription)
Agent   --device key--> /api/agent/*  (jobs only if subscribed)
Desk    --device key--> POST /api/device/activate  (starts 60-day trial)
```

---

## Read first (in this folder)

| File | Use |
|------|-----|
| [`schema.sql`](schema.sql) | Authoritative T-SQL schema — apply this |
| [`flows.md`](flows.md) | Buy → flash → ship → signup → paste → trial → MCP |
| [`integration-requirements.md`](integration-requirements.md) | What every app needs to communicate |
| [`env.example`](env.example) | Env var names (no real secrets) |
| [`README.md`](README.md) | Branch / cutover rules |

## Reuse as behavior reference (repo)

| Path | Role |
|------|------|
| [`docs/Fennsill-Cloud-Server-Brief.md`](../docs/Fennsill-Cloud-Server-Brief.md) | Product rules (change period to **60 days**; trial starts on **activate**, not first MCP) |
| [`cloud/main.py`](../cloud/main.py) | Live Starlette + MCP mount |
| [`cloud/store.py`](../cloud/store.py) | Current SQLite store — port semantics, do not delete SQLite until cutover |
| [`cloud/tests/test_cloud.py`](../cloud/tests/test_cloud.py) | Extend with inventory claim + activate + gating tests |
| [`factory/provision.py`](../factory/provision.py) | Flash + permanent serial + ledger fields |
| [`fennsill-desk/MainForm.cs`](../fennsill-desk/MainForm.cs) | Paste device key UX — add activate call |
| [`connector/runtime/cloud_agent.py`](../connector/runtime/cloud_agent.py) | Agent heartbeat / job poll |

## Do not use as the cloud database target

- `server/app.py` / `server/fennsill.db` — local setup UI, wrong ownership rules  
- Storing `device_secret_hex` or factory `master.key` in SQL Server  
- Free-form claim of any `FSxxxxxxxxxxxx` that was never manufactured  

---

## Locked product decisions

1. **Product id** = box serial `FS-YYMM-NNNNNN` (factory write-once). Not the MCU `device_id`.  
2. **`device_id`** = `FS` + 12 uppercase hex from eFuse. Permanent.  
3. **Trial** = **60 days**. Starts on successful `POST /api/device/activate` with a valid device key (called from Desk after paste). Idempotent if already active.  
4. Signup creates `access_subscriptions` with `status=pending`, ends null. Login does not move the period.  
5. MCP tools (including `list_panels`) require active unexpired subscription. Pending → 403 `trial_not_started` (or equivalent). Expired/inactive → 403 `subscription_inactive`.  
6. `GET /api/agent/jobs/next` **never** starts the trial. While pending → **204**.  
7. Factory must upload inventory **before** ship so claim cannot succeed for fake serials.  
8. Work only on **`feature/sqlserver-subscriptions`**. Rebase/merge from `main` for live fixes. Do not cut over production until approved.

---

## Schema

Apply [`schema.sql`](schema.sql). Core tables:

- `users`, `sessions` (with `expires_at`)  
- `manufactured_devices` — factory inventory; unique `device_id` + `box_serial`; `claimed_user_id` nullable  
- `devices` — linked ownership including `box_serial`  
- `device_tokens` — prefer `token_hash` (return plaintext once at mint)  
- `access_subscriptions` — `pending|active|inactive`, 60-day period  
- `push_jobs`, `push_rate`, `update_manifests`  
- `factory_imports` — optional audit  

---

## Implementation plan

### 1. SQL Server store behind a flag

- If `FENNSILL_SQL_CONNECTION` is set → use SQL Server (pyodbc or equivalent).  
- If unset → keep existing SQLite path so live/rollback still works.  
- Share one behavioral store interface so tests cover both where practical.  
- Use transactions for claim, activate, and job claim (SQL Server: appropriate isolation; atomic single-row updates).

### 2. Factory import API

```http
POST /api/factory/devices
Authorization: Bearer <FENNSILL_FACTORY_IMPORT_TOKEN>
```

Body: `device_id`, `box_serial`, `key_fingerprint`, `fw_version`.  
Idempotent upsert. Reject any `device_secret` / `secret` / `master` fields.  
Wire factory provision (or a small post-step) to call this after a successful flash so SQL has the **real** serial, not placeholders.

### 3. Signup + claim

- `POST /api/session` signup: create user + pending subscription.  
- `POST /api/devices/claim` with `{ "box_serial": "FS-YYMM-NNNNNN" }` (product id):  
  - unknown → 404  
  - claimed by other → 409  
  - else link `devices` and mark inventory claimed  
- Mint user session token and device key (`POST /api/device/token`) for account UI copy/paste.

### 4. Activate trial (Desk)

- Add `POST /api/device/activate` (device key auth).  
- First success: `pending` → `active`, `started_at=now`, `current_period_end=now+60 days`.  
- Update FennSill Desk paste-key path to call activate after saving `cloud_device_token.txt`.  
- Do **not** start trial from `jobs/next` or from factory QA heartbeats without activate.

### 5. MCP / agent gating fixes

- Every MCP tool (including `list_panels`) must require active subscription.  
- Remove any “start period” side effect from `claim_next_job` / `jobs/next`.  
- Heartbeat updates `last_seen_at` only; does not start the 60-day clock.  
- Expired or `inactive`: block MCP enqueue and job claim/complete.

### 6. Account UI

- Collect email, password, and **product id (box serial)** for registration/claim.  
- Show MCP URL + user Bearer + device key mint/copy (existing UX).  
- Surface subscription status / period end.

### 7. Tests (required before claiming done)

Add coverage for:

- Factory import then claim by serial succeeds; unknown serial fails.  
- Second user cannot claim same serial / device_id.  
- Activate starts exactly one 60-day window; second activate is idempotent.  
- Pending: MCP tools blocked; `jobs/next` returns 204.  
- After activate: MCP + jobs work until end; after end: 403 and no second free period.  
- `list_panels` gated.  
- `jobs/next` does not start trial even after heartbeat.

---

## Env

Copy names from [`env.example`](env.example):

- `FENNSILL_SQL_CONNECTION`  
- `FENNSILL_FACTORY_IMPORT_TOKEN`  
- `FENNSILL_PUBLIC_URL` / `FENNSILL_PUBLIC_MCP_URL`  
- `FENNSILL_TRIAL_DAYS=60`  
- Keep `FENNSILL_CLOUD_DB` for SQLite fallback until cutover  

Never commit real passwords or tokens.

---

## What each app needs (summary)

Full matrix: [`integration-requirements.md`](integration-requirements.md).

| App | Must have |
|-----|-----------|
| Factory | Import URL + factory token; uploads real `device_id` + `box_serial` after flash |
| Cloud | SQL connection; factory token; trial=60; schema applied |
| Account site | Cloud API; signup + claim serial + mint keys |
| FennSill Desk | Cloud URL; paste device key; call activate; status UI |
| FennSill Agent | Device key file; heartbeat + jobs |
| Claude/ChatGPT | `https://mcp.fennsill.com/mcp` + user Bearer |

---

## Non-goals (this pass)

- Payment / Stripe checkout UI  
- Storing MCU secrets in SQL  
- Wi-Fi SSID/PSK in cloud  
- Merging to `main` or flipping live production to SQL Server without explicit cutover  
- Changing firmware serial format (already `FS-YYMM-NNNNNN` via factory)

---

## Done when

1. `schema.sql` applied on a SQL Server instance and cloud can read/write via `FENNSILL_SQL_CONNECTION`.  
2. Factory can presave inventory; buyer can claim only manufactured serials.  
3. Desk paste → activate starts a **60-day** trial once.  
4. MCP works only while subscribed; `jobs/next` never starts the clock.  
5. All new tests pass.  
6. Changes exist only on `feature/sqlserver-subscriptions` (or PRs into that branch), not silently on live `main`.
