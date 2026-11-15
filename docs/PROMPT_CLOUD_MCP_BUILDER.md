# Prompt: build Artiphact cloud MCP + agent API

Copy everything below the line into another chat / contractor brief.

---

## Mission

Build the **Artiphact cloud backend** that buyers connect to. Artiphact (the company) hosts everything. Buyers **never** host MCP, never run Cloudflare tunnels, never expose ports.

Buyers only run **Artiphact.exe** as a thin **local agent** on the PC with the USB e-ink panel. Claude / ChatGPT / Gemini / etc. call **our** hosted MCP URL to get tools. Push jobs are delivered only to **that buyer’s paired device**. Clients can also **GET firmware/app updates**. They must **not** get general write access to the server or other people’s boards.

Reference product notes already in-repo (if available): `docs/CLOUD_MCP.md`, `docs/SHIPPING.md`, local tool shapes in `connector/tools.json`, local USB push behavior in `connector/mcp_server.py` + `connector/intake.py`.

## Architecture

```text
Claude / ChatGPT / Gemini / Grok / …
        |  HTTPS Streamable HTTP MCP + OAuth or bearer
        v
Artiphact cloud (YOU build this)
  - MCP server (tools)
  - Auth + device ownership
  - Push job queue (scoped to device)
  - OTA / app update manifests (read-only to clients)
        |  device bearer token over HTTPS
        v
Artiphact.exe agent on buyer PC (separate; stub OK)
        |  USB
        v
Their panel only (800×480 e-ink)
```

## Hard security requirements

1. **No anonymous MCP** in production.
2. Every `push_artifact` (and any job) is bound to **devices owned by the authenticated account**. Wrong/missing device → 403.
3. **No cross-tenant access** — never list, read, or push another user’s devices/jobs.
4. Client capabilities toward the server are essentially:
   - use **their** tools (which may enqueue a job for **their** device)
   - **GET updates** (signed manifests)
   - agent: poll/ack **their** jobs  
   Not allowed: upload firmware, rewrite manifests, arbitrary DB/file writes, admin APIs, Wi‑Fi secrets to cloud.
5. **Wi‑Fi SSID/password must never be accepted or stored by the cloud API** (panel-local only).
6. Size-limit HTML/SVG (e.g. 512KB). Rate-limit pushes per account/device.
7. Prefer **localhost-style mental model for ChatGPT Desktop later**, but production MCP URL is **your** `https://mcp.…/mcp`.

## MCP tools to expose (Streamable HTTP)

Match local product tools (names stable):

| Tool | Cloud behavior |
|------|----------------|
| `list_panels` | Return **only devices linked to this account** (online if agent recently heartbeated). |
| `push_artifact` | Validate html/svg (no external `http/file/javascript` URIs if possible). Enqueue job for caller’s device. Do **not** talk USB from the cloud. Return `{ job_id, device_id, status: "queued" }`. |
| `start_live_update` / `stop_live_update` | Optional v1: enqueue recurring job types or stub with clear “agent required”. |
| `set_wifi` | **Do not implement on cloud** (or reject: Wi‑Fi stays on device via USB agent only). |

MCP transport: **Streamable HTTP** at `/mcp` (MCP Python SDK `MCPServer` / FastMCP successor). Claude Connectors + ChatGPT custom MCP must work with **auth** (OAuth preferred; bearer device/user token acceptable for MVP).

Server instructions string should tell models: build 800×480 self-contained B/W HTML; call tools; do not substitute a web Artifact for a panel push.

## Agent HTTP API (for Artiphact.exe)

Device bearer token auth on all routes:

- `GET /api/agent/heartbeat` — agent says device online  
- `GET /api/agent/jobs/next` — claim next `queued` job **for this device only** (or 204)  
- `POST /api/agent/jobs/{id}/complete` — `{ ok, error? }` only if job belongs to this device  
- `GET /api/updates/{channel}` — read-only manifest `{ version, url, sha256, published_at }`  

Account routes (session/OAuth):

- signup/login  
- link device (`device_id` unique, owned by user)  
- mint **device token** for Artiphact.exe  
- list **own** devices only  

Operator-only (not buyer MCP): publish update manifests.

## Data model (suggested)

- `users`, `sessions` / OAuth identities  
- `devices(user_id, device_id, label, last_seen_at)`  
- `device_tokens(token, user_id, device_id, revoked)`  
- `push_jobs(id, user_id, device_id, html/svg, title, status, error, timestamps)`  
- `update_manifests(channel, version, url, sha256, published_at)`  

Statuses: `queued` → `claimed` → `done` | `failed`.

## Non-goals for this cloud build

- Buyers running `ArtiphactHost` / trycloudflare tunnels  
- Cloud process opening USB/COM  
- Storing dashboards long-term as a CMS (jobs can be ephemeral)  
- Accepting Wi‑Fi passwords in cloud  

## Deliverables

1. Deployable service (Docker or clear PaaS instructions) with HTTPS `/mcp` + agent API.  
2. Env-based config (DB, secrets, public URL).  
3. README: how to create a user, link a device, mint device token, point Claude/ChatGPT at `/mcp`, run a local agent stub that prints claimed jobs.  
4. Tests: user A cannot complete or claim user B’s job; unauthenticated push rejected; updates GET works; manifest publish not exposed on MCP.  
5. Short threat model paragraph in README.

## Acceptance test

1. User A links device `A1`, mints token, agent heartbeats.  
2. Claude/ChatGPT (or MCP client) authenticated as A calls `list_panels` → sees `A1` only.  
3. `push_artifact` → job queued for `A1`.  
4. Agent with A1 token claims job; agent with B’s token cannot.  
5. User B cannot push to `A1`.  
6. `GET /api/updates/stable` returns manifest; no buyer MCP tool can overwrite it.

## Stack preference

Use whatever is fastest to ship correctly (Node or Python OK). If Python: official `mcp` SDK Streamable HTTP. Postgres preferred for prod; SQLite OK for MVP. Keep interfaces stable so the existing Windows `Artiphact.exe` can later poll jobs and call existing local `intake_page(..., push=True)`.
