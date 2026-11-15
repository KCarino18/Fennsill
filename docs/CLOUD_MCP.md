# Fennsill cloud MCP (product architecture)

Buyers **never host** the MCP server. Fennsill hosts it.  
`Fennsill.exe` is a **local agent** that drives USB and pulls jobs for **that buyer’s devices only**.

```text
Claude / ChatGPT / …
        |  HTTPS + auth  (your MCP URL)
        v
Fennsill cloud
  - MCP tools (scoped to caller’s devices)
  - job queue (html → device_id)
  - OTA manifests (read-only to clients)
        |  device token
        v
Fennsill.exe (agent on buyer PC)
        |  USB
        v
Their panel only
```

## Security rules (non-negotiable)

1. **Auth on every MCP and agent call** — session or device bearer. No anonymous push.
2. **Device ownership** — `push_artifact` / jobs only for `device_id` linked to that account.
3. **No cross-tenant access** — cannot list or push another user’s boards.
4. **Clients do not write the server freely** — they may only:
   - use **their** tools (which enqueue a job for **their** device)
   - **GET updates** (signed manifests / packages)
   - poll/ack **their** jobs  
   They cannot upload firmware, rewrite manifests, or mutate other tenants.
5. **Wi‑Fi secrets stay on device** — never accepted by the cloud API.

## Roles

| Piece | Writes | Reads |
|-------|--------|--------|
| Cloud MCP | Job row for caller’s device | Tool list, job status for caller |
| Agent | Local USB + local gallery | Jobs for its device token; update manifests |
| Buyer AI | Nothing on disk of Fennsill cloud except via tools | Tools |

## Local Host / Cloudflare

Test harness only. Production = this cloud model.
