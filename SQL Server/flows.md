# Registration, trial, and MCP access flow

## End-to-end

```text
1. Customer buys product
2. Factory flashes firmware
   - Reads real device_id (FS + 12 hex from eFuse)
   - Locks permanent box serial FS-YYMM-NNNNNN (product id)
   - Locks MCU device secret (stays on panel; NOT uploaded)
   - Presaves to SQL Server manufactured_devices:
       device_id, box_serial, key_fingerprint, fw_version, provisioned_at
3. Ship unit (serial printed on box / insert)
4. Customer receives unit
5. Signup on account website
   - email + password
   - product id = box serial (FS-YYMM-NNNNNN)
   - Server claims manufactured_devices row (must exist, unclaimed)
   - Creates users + access_subscriptions(pending) + devices link
   - Mints user session bearer + cloud device key
6. Customer pastes device key into FennSill Desk
   - Desk writes %LOCALAPPDATA%\FennsillApp\cloud_device_token.txt
   - Desk calls POST /api/device/activate with the device key
   - Server starts 60-day trial: pending → active, current_period_end = now+60d
7. FennSill Agent heartbeats + polls jobs with device key
8. Claude / ChatGPT call MCP with user session bearer
   - MCP tools only succeed while subscribed (active + end in future)
```

## Identity fields

| Field | Example | Where it lives | Secret? |
|-------|---------|----------------|---------|
| `device_id` | `FSA1B2C3D4E5F6` | MCU + SQL inventory + devices | No |
| `box_serial` / product id | `FS-2511-000042` | MCU NVS + box + SQL | No |
| MCU `device_secret` | 64 hex | MCU only (factory ledger offline) | Yes — never SQL |
| User session bearer | random | sessions + buyer clipboard for MCP | Yes |
| Cloud device key | random | device_tokens (+ local cloud_device_token.txt) | Yes |

Do **not** use repeating placeholder serials like `FS-0000-000001` in production inventory. Factory assigns a real next serial (`FS-YYMM-NNNNNN`).

## Subscription states

| status | current_period_end | Meaning |
|--------|--------------------|---------|
| `pending` | null | Signed up / claimed. No MCP job delivery yet. |
| `active` | future | Trial or paid period open. MCP + jobs work. |
| `active` | past | Period ended. Treat as blocked; do not auto-open a second free period. |
| `inactive` | any | Operator revoked. MCP blocked. |

`subscribed` is computed: `status == active` AND `current_period_end > utcnow`.

## When the 60-day clock starts

**Preferred (this design):** FennSill Desk, after a successful paste/save of the device key, calls:

```http
POST /api/device/activate
Authorization: Bearer <device key>
```

Server (single transaction):

1. Authenticate device token (unrevoked, bound to device_id + user).
2. Load `access_subscriptions` for that user.
3. If `pending` → set `active`, `started_at = now`, `current_period_end = now + 60 days`.
4. If already `active` with future end → no-op success (idempotent).
5. If expired or `inactive` → 403 `subscription_inactive`.

Do **not** start the clock from:

- signup / login
- factory inventory insert
- agent `GET /api/agent/jobs/next`
- silent factory or QA heartbeats without activate

Heartbeat may refresh `devices.last_seen_at` while pending or while the period is open. Heartbeat alone must **not** start the 60-day period.

## Claim rules (signup / link)

1. Buyer submits email, password, and **product id** (`box_serial`).
2. Lookup `manufactured_devices` by `box_serial`.
3. Missing → 404 `unknown_product`.
4. `claimed_user_id` set to another user → 409 `already_claimed`.
5. Same user reclaim / already linked → idempotent OK.
6. Else atomically set `claimed_user_id` / `claimed_at`, insert `devices` row with both `device_id` and `box_serial`, insert `access_subscriptions` pending if new user.

Ownership of a `device_id` never transfers to a second account.

## MCP and agent gating

Before any MCP tool runs (including `list_panels`):

1. Valid user session → else 401.
2. Subscription open (`subscribed`) → else 403 `subscription_inactive` or `trial_not_started` if still pending.
3. Tool-specific ownership checks still apply.

Agent routes:

- `GET /api/agent/heartbeat` — auth device key; refresh `last_seen_at` if pending or subscribed; after expiry/revoke → 403.
- `GET /api/agent/jobs/next` — **never** starts the clock. While pending → 204. While subscribed → claim one job. Expired/inactive → 403.
- `POST /api/agent/jobs/{id}/complete` — same subscription rules as claim.

## Operator renew / revoke (later billing)

One write path (CLI or webhook later):

- Renew: `status = active`, set `current_period_end` to a future UTC time.
- Revoke: `status = inactive`.

No buyer route may extend their own period.

## Fixes vs current SQLite live behavior

When implementing on this branch, correct these live bugs:

1. `list_panels` must call the same access gate as other MCP tools.
2. `jobs/next` must not call “start period” logic; while pending return 204.
3. Period length is **60 days**, not 30.
4. Device link requires factory inventory + serial claim (not free-form unlisted `device_id`).
