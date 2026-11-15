# Prebuilt full Fennsill firmware

This folder holds the **complete** panel firmware image (splash, USB, app — same as compiling `firmware/fennsill`).

Factory Flash prefers `*.merged.bin` here so Bitdefender cannot block an on-PC `arduino-cli` compile. The image is built by `.github/workflows/build-firmware.yml`.
