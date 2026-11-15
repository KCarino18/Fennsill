# Plug in → get Artiphact (option 3)

## What the buyer sees
1. Plug the panel into the PC USB port.
2. Windows shows a drive (or a setup prompt) named **ARTIPHACT**.
3. They double-click **SETUP.BAT**.
4. Artiphact installs itself, starts on login, and wires Claude / ChatGPT.
5. They restart their AI app once and talk to it.

## What we built
| Piece | Role |
| --- | --- |
| `installer/Install-Artiphact.ps1` | Installs host app under `%LOCALAPPDATA%\Artiphact` |
| `installer/msc_payload/` | Files that appear on the USB drive |
| `installer/make_msc_image.py` | Builds `msc_disk.h` for firmware |
| `firmware/artiphact/usb_installer.h` | Serves that disk over USB MSC |

## Firmware note
The panel must use **TinyUSB** (not Hardware CDC) for the SETUP drive and the serial protocol at once. Enable:

```cpp
#define ARTIPHACT_USB_INSTALLER
```

in `artiphact.ino`, rebuild the MSC header, then flash with a TinyUSB USB mode on the XIAO board package.

Until that firmware is flashed, run `installer/Install-Artiphact.ps1` manually once; after that Artiphact owns plug-in behavior on the PC.
