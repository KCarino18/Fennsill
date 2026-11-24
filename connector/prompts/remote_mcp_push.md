# Push to my Fennsill e-ink panel

The Fennsill connector is already enabled on this chat (remote MCP).

Do **not** create a Claude Artifact / web preview as a substitute.

1. Call **`list_panels`** and copy a `device_id`.
2. Prefer **`push_chart`** for a graph. Example: title `Fennsill connected`, labels `["Status"]`, values `[1]`, or a small demo series for today’s date.
   - For a custom page instead, call **`push_artifact`** with finished **800×480** self-contained HTML (black/white, high contrast, no external URLs) that says **Fennsill connected** and includes today’s date.
3. Confirm the tool reported **`delivered: true`**. If `delivered` is false, call **`get_push_status`** with the `job_id`.

If tools are missing, the connector is not enabled — tell me to turn on Fennsill for this chat.
