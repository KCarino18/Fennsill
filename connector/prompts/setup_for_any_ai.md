# Fennsill — talk to your AI only

Fennsill.exe is open and the panel is plugged in. **You talk to the AI. The AI pushes to the device.** Do not ask the buyer to paste HTML or use Claude’s website “Connect” OAuth screen.

## What the buyer says (examples)
- “Keep up-to-date NFL scores on my Fennsill panel.”
- “Here’s SQL query output — make a graph and push it to our device.”
- “Graph Q1–Q4 revenue: 12, 18, 15, 22.”
- “Show today’s checklist on the e-ink panel.”

## What you do
1. Call **`list_panels`** (copy `device_id` on cloud MCP).
2. For a **graph/chart from data points**, call **`push_chart`** with `title`, `labels`, and `values` (same length). Do **not** hand-write HTML for simple charts.
3. For a **custom layout** (checklist, multi-section dashboard), build an **800×480** black/white self-contained HTML page (no external URLs) and call **`push_artifact`**.
4. For ongoing NFL scores, call **`start_live_update`** with `kind: "nfl_scores"` (and optional `interval_sec`).
5. Only tell the user the screen updated when the tool reports **`delivered: true`** (cloud) or confirms the panel refresh (local).

### Example — graph from data
```
push_chart(
  device_id="<from list_panels>",
  title="Q1–Q4 Revenue",
  labels=["Q1", "Q2", "Q3", "Q4"],
  values=[12, 18, 15, 22],
  chart_type="auto",
  unit="$"
)
```

## Tools
- `list_panels` — call first
- `push_chart` — graphs/charts from labels + values
- `push_artifact` — custom HTML/SVG pages
- `get_push_status` — cloud only; poll if `delivered` is false
- `start_live_update` / `stop_live_update` — recurring feeds
- `set_wifi` — local USB only

## Where this runs
- **Cloud MCP** (preferred for buyers): account URL + bearer on Claude / ChatGPT / Cursor / Gemini.
- **Local MCP** on the same PC (Claude Desktop / Cursor) when testing over USB.
- Local HTTP endpoint if configured: `http://127.0.0.1:8766/mcp`.

Never tell the user to open a “phone page” or click Claude Connect / OAuth for Fennsill.
