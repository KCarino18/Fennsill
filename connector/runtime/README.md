# Connector runtime fallbacks

Some Windows PCs (Controlled Folder Access / AV) block classic filenames such as
`panel_status.py`, `bind_device.py`, and `mcp_server.py` under `connector/`.

This folder holds the same scripts so Fennsill Desk can still resolve them via:

1. `connector/<name>.py` (preferred)
2. `connector/runtime/<name>.py` (fallback)

Also prefer the unblockable aliases at the connector root:

- `identity_status.py` → panel / bind status JSON
- `device_bind_tool.py` → first-plug bind → `%LOCALAPPDATA%\Fennsill\device_bind.json`
