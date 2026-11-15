# Fennsill — talk to your AI only

Fennsill.exe is open and the panel is plugged in. **You talk to the AI. The AI pushes to the device.** Do not ask the buyer to paste HTML or use Claude’s website “Connect” OAuth screen.

## What the buyer says (examples)
- “Keep up-to-date NFL scores on my Fennsill panel.”
- “Here’s SQL query output — make a graph and push it to our device.”
- “Show today’s checklist on the e-ink panel.”

## What you do
1. Build an **800×480** black/white self-contained HTML page (no external URLs in the page).
2. Call the Fennsill MCP tool **`push_artifact`** with that HTML.
3. For ongoing NFL scores, call **`start_live_update`** with `kind: "nfl_scores"` (and optional `interval_sec`).

## Tools
- `list_panels`
- `push_artifact` — one-shot push (graphs, SQL dashboards, etc.)
- `start_live_update` / `stop_live_update` — recurring feeds
- `set_wifi`

## Where this runs
- **Claude Desktop** or **Cursor** on the same PC (local MCP) — preferred.
- MCP HTTP endpoint if configured: `http://127.0.0.1:8765/mcp` (or the public https URL Fennsill shows + `/mcp`).

Never tell the user to open a “phone page” or click Claude Connect / OAuth for Fennsill.
