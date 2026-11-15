# Fennsill device software (this chat’s scope)

Firmware on the XIAO ESP32-S3 + EE04 7.5" panel. **No cloud auth here** — that lives in another chat / `docs/PROMPT_CLOUD_MCP_BUILDER.md`.

## Responsibilities

| On device | Not on device |
|-----------|----------------|
| Splash, 800×480 1-bit paint | Claude/ChatGPT OAuth |
| USB CDC frame protocol (`AFC1` / `AFS1`) | Job queue / MCP tools |
| Wi-Fi SSID/PSK in NVS (USB `WIFI` only) | Cross-tenant isolation |
| Signed HTTPS OTA + button confirm | Publishing update manifests |
| Stable `device_id` for pairing (`APxxxxxxxxxxxx`) | Account login |

## USB lines (host ↔ panel)

- `HELLO` / `READY?` → `READY 1.1.0 id=FSxxxxxxxxxxxx`
- `ID?` / `WHOAMI` → `ID FSxxxxxxxxxxxx`
- `STATUS` → `STATUS version=… id=… wifi=0|1` (never SSID/PSK)
- `WIFI <b64ssid> <b64psk>` → `OK` (secrets stay in flash)
- `FORGET` → clear Wi-Fi
- `UPDATES https://…` → set manifest URL (`https` only)
- `YES` / `NO` while update prompt is showing
- Binary chunks + show as in `firmware/usb_protocol.py`

## OTA

1. If Wi-Fi saved, boot fetches HTTPS manifest.
2. HMAC (`update_key.h`) over `version\nsha256` must match `signature`.
3. Binary URL must be `https://`; SHA-256 of download must match.
4. Panel shows “Software update”; top = install, middle = skip.
5. Serial errors: `ERR bad signature`, `ERR ota url|http|begin|write|sha|end`.

## Flash

Board `esp32:esp32:XIAO_ESP32S3_Plus`, Hardware CDC, OPI PSRAM, Seeed_GFX + `driver.h` beside the sketch. Keep `FENNSILL_USB_INSTALLER` off for Hardware CDC builds.

## Host pairing stub

Desk/agent can read `id=` from READY or send `ID?` and store that string for later cloud link. Auth tokens stay off the MCU.

## How each device is serialized

Use **Fennsill Factory** (`factory/`) — a separate program from Fennsill.exe. See [`factory/README.md`](../factory/README.md).

| Field | Source | Changes across PCs? |
|-------|--------|---------------------|
| `device_id` | ESP32 eFuse MAC → `APxxxxxxxxxxxx` | **Never** |
| `serial` | Factory `SERIALSET` → `FS-YYMM-NNNNNN` (write-once NVS) | **Never** |
| `dkey` | `HMAC(master, device_id)` locked via `KEYSET` (write-once) | **Never** (secret stays on MCU; PC only sees `PROOF`) |
| `install_key` | Buyer PC: SHA256 of id+serial+challenge proof → `device_bind.json` | Per PC bind file; panel identity unchanged |

USB (firmware 1.2+):

- `READY … id=… serial=…`
- `SERIAL?` / write-once `SERIALSET …`
- `KEY?` → `locked|missing` (never dumps secret)
- write-once `KEYSET <64hex>`
- `CHALLENGE <nonce>` → `PROOF <hmac>`

**Not used as product serial:** Windows COM `serial_number`.

**Auth (other chat):** cloud bearer tokens stay off the MCU. Factory ledger `key_fingerprint` / offline `device_secrets.csv` are for your backend claim flow.
