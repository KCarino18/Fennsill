# Fennsill Factory (manufacturing tool)

Separate from the buyer **Fennsill** desk app. Flashes panel firmware, locks a **permanent serial**, locks a **device key**, and writes a ledger row.

`Fennsill.exe` only talks USB to an already-provisioned panel.

**Download:** [FennsillFactory.exe](https://github.com/KCarino18/Fennsill/releases/latest/download/FennsillFactory.exe) from the [latest release](https://github.com/KCarino18/Fennsill/releases/latest), or use the `factory\` folder inside `Fennsill-Setup.zip` (also staged as `dist\factory` by `installer\build_dist.py`). On a factory PC you can copy that folder to `C:\factory`.

## One-time setup (factory PC)

1. Install [arduino-cli](https://arduino.github.io/arduino-cli/), then:
   ```bat
   arduino-cli core install esp32:esp32
   ```
2. Install Python deps: `pip install pyserial`
3. Create the master key (keep offline, never ship to buyers):
   ```bat
   cd factory
   python -c "import secrets; open('master.key','wb').write(secrets.token_bytes(32))"
   ```
4. **Real Windows app**
   - Build once: double-click `Build-Factory-Exe.bat` (needs .NET SDK)
   - Open: double-click **`FennsillFactory.exe`** (or `Run-Factory.bat`)
   - Window: **Select device → Check → Flash**
   - Flash erases TRMNL, installs Fennsill, locks serial + key
   - Needs **Python** + `pip install esptool pyserial`. **arduino-cli** is downloaded automatically into `factory/tools/` on first Flash.

## Safety: e-ink panel only

Factory **refuses** random COM devices. It only lists/flashes:

- Espressif (`0x303A`) or Seeed (`0x2886`) native USB — the XIAO ESP32-S3 on the panel
- Fennsill `READY`, **or** stock TRMNL / blank XIAO (will be wiped)
- **Never** CH340 / CP2102 / Arduino dongles

## TRMNL → Fennsill

Yes. FLASH on a kit that still has TRMNL:

1. Confirms it’s the XIAO panel USB  
2. **`esptool erase-flash`** — wipes TRMNL + NVS completely  
3. Uploads Fennsill firmware  
4. Locks serial + device key  

Needs `pip install esptool` and `arduino-cli` on PATH.

## What provision does

1. Verify port is the e-ink XIAO, erase chip, then `arduino-cli compile --upload` of `firmware/fennsill`
2. Reads chip `device_id` (`FSxxxxxxxxxxxx` from eFuse MAC — never changes)
3. Assigns box serial `FS-YYMM-NNNNNN` (or `--serial`) and **write-once** `SERIALSET`
4. Derives `device_secret = HMAC-SHA256(master, "fennsill-device-v1|" + device_id)` and **write-once** `KEYSET`
5. Verifies with `CHALLENGE` / `PROOF`
6. Appends `ledger/devices.csv` (+ offline `ledger/device_secrets.csv`)

Same physical panel on another PC → same `device_id` + same `serial` + same key.

## Buyer first plug

1. Panel USB → (optional FENNSILL drive) `SETUP.BAT` → installs Fennsill to `%LOCALAPPDATA%\Fennsill`
2. `bind_device.py` reads `SERIAL?` / `ID?`, runs `CHALLENGE`, writes `device_bind.json` with `install_key`
3. User sees their permanent serial; Fennsill is bound to that panel

Cloud account auth is a different chat — factory only mints identity + key material.
