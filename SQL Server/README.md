# SQL Server package (subscription offshoot)

Handoff package for wiring **Microsoft SQL Server** to the Fennsill cloud MCP, factory inventory, buyer registration, and 60-day trial.

**Branch:** `feature/sqlserver-subscriptions` only.  
**Do not merge to `main` / do not cut over live** until schema, factory upload, serial claim, trial activation, and MCP gating are tested end-to-end. Live production stays on SQLite in `cloud/` until that cutover.

## Point Claude / Cursor here

Open [`PROMPT.md`](PROMPT.md) and this folder. That prompt is the full implementer brief.

## Files

| File | Role |
|------|------|
| [`PROMPT.md`](PROMPT.md) | Claude prompt for the person implementing SQL Server + cloud wiring |
| [`schema.sql`](schema.sql) | T-SQL tables, indexes, constraints |
| [`flows.md`](flows.md) | Buy → flash → ship → signup → paste key → trial → MCP gate |
| [`integration-requirements.md`](integration-requirements.md) | What every app needs (URLs, tokens, env) |
| [`env.example`](env.example) | Connection string / secret placeholders (no real secrets) |

## Locked product decisions

- **Product id** = box serial `FS-YYMM-NNNNNN` (factory write-once), not MCU `device_id`.
- **Trial** = **60 days**, started when FennSill Desk calls activate after the buyer pastes the website-minted **device key**.
- MCP tools and agent job delivery work **only** while the subscription is `active` and `current_period_end` is in the future.
- Factory **presaves** real `device_id` + serial into inventory before ship. Never store MCU `device_secret` / master key in SQL Server.

## Related live code (reference only until cutover)

- [`cloud/store.py`](../cloud/store.py) — current SQLite store (`PERIOD_DAYS = 30`)
- [`docs/Fennsill-Cloud-Server-Brief.md`](../docs/Fennsill-Cloud-Server-Brief.md) — product rules (update period to 60 days on this branch)
- [`factory/provision.py`](../factory/provision.py) — flash + permanent serial
- [`fennsill-desk/MainForm.cs`](../fennsill-desk/MainForm.cs) — paste device key UX

## Branch hygiene

1. All SQL Server / subscription / claim / activate work lands on `feature/sqlserver-subscriptions`.
2. Regularly merge or rebase from `main` so live bugfixes stay in sync.
3. Keep production on SQLite until an explicit cutover decision.
