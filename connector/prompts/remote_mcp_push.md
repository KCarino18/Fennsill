# Push to my Fennsill e-ink panel

The Fennsill connector is already enabled on this chat (remote MCP).

Do **not** create a Claude Artifact / web preview as a substitute.

1. Call **`list_panels`**.
2. Call **`push_artifact`** with a finished **800×480** self-contained HTML page (black/white, high contrast, no external URLs) that says **Fennsill connected** and includes today's date.
3. Confirm the tool reported `pushed: true`.

If tools are missing, the connector is not enabled — tell me to turn on Fennsill for this chat.
