"""Build a tiny FAT12 disk image the panel can serve over USB MSC.

Contains README + SETUP.BAT + a bootstrap Install-Fennsill.ps1 that pulls
from the PC if the full project is present, or tells the user to run the
desktop installer. The image stays small enough for flash/PROGMEM.
"""

from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = Path(__file__).resolve().parent / "msc_payload"
OUT_BIN = Path(__file__).resolve().parent / "fennsill_msc.img"
OUT_H = ROOT / "firmware" / "fennsill" / "msc_disk.h"

# 128 sectors * 512 = 64 KiB FAT12 image
SECTOR = 512
SECTOR_COUNT = 128
RESERVED = 1
FAT_SECTORS = 1
ROOT_ENT = 16  # 1 sector of root directory
ROOT_SECTORS = 1
FAT_ID = 0xF8


def fat12_encode(clusters: list[int]) -> bytes:
    """Pack 12-bit FAT entries into bytes."""
    # clusters[0] and [1] are reserved media values
    vals = list(clusters)
    out = bytearray()
    i = 0
    while i < len(vals):
        a = vals[i] & 0xFFF
        b = vals[i + 1] & 0xFFF if i + 1 < len(vals) else 0
        # little-endian fat12 packing: |aaaa aaaa| bbbb aaaa | bbbb bbbb|
        out.append(a & 0xFF)
        out.append(((b & 0xF) << 4) | ((a >> 8) & 0xF))
        out.append((b >> 4) & 0xFF)
        i += 2
    return bytes(out)


def dir_entry(name: str, ext: str, size: int, cluster: int, attr: int = 0x20) -> bytes:
    n = f"{name.upper():<8}"[:8].encode("ascii")
    e = f"{ext.upper():<3}"[:3].encode("ascii")
    return n + e + bytes([attr]) + bytes(14) + struct.pack("<HH", 0, cluster) + struct.pack("<I", size) + bytes(0)


def file_to_83(path: Path) -> tuple[str, str]:
    stem = path.stem.upper().replace("-", "")[:8]
    ext = path.suffix.upper().lstrip(".")[:3] or "TXT"
    return stem, ext


def build() -> bytes:
    files = []
    for path in sorted(PAYLOAD.iterdir()):
        if path.is_file() and path.name.upper() != "FENNSILL.IMG":
            files.append(path)
    # Bootstrap PS1 copied into payload as INSTALL.PS1 (8.3)
    install_src = Path(__file__).resolve().parent / "Install-Fennsill.ps1"
    raw_files: list[tuple[str, str, bytes]] = []
    for path in files:
        name, ext = file_to_83(path)
        raw_files.append((name, ext, path.read_bytes()))
    if install_src.is_file():
        # Short offline bootstrap for the drive (download-free when project nearby)
        bootstrap = r"""$ErrorActionPreference='Stop'
$here=Split-Path -Parent $MyInvocation.MyCommand.Path
# If this PC already has the Fennsill project next to a cloned tree, use full installer.
$candidates=@(
  (Join-Path $env:USERPROFILE 'Desktop\This Is A Test For The Tablet\installer\Install-Fennsill.ps1'),
  (Join-Path $env:LOCALAPPDATA 'FennsillApp\Install-Fennsill.ps1'),
  (Join-Path $env:LOCALAPPDATA 'Fennsill\Install-Fennsill.ps1')
)
foreach($c in $candidates){ if(Test-Path $c){ & $c; exit $LASTEXITCODE } }
Write-Host 'Fennsill full installer not found on this PC yet.'
Write-Host 'Copy FennsillSetup from the product site, or keep the project folder on the Desktop.'
pause
"""
        raw_files.append(("INSTALL", "PS1", bootstrap.encode("utf-8")))

    data_start = RESERVED + FAT_SECTORS + ROOT_SECTORS
    image = bytearray(SECTOR_COUNT * SECTOR)

    # BPB / boot sector
    bpb = bytearray(SECTOR)
    bpb[0:3] = b"\xEB\x3C\x90"
    bpb[3:11] = b"FENNSILL"
    struct.pack_into("<H", bpb, 11, SECTOR)
    bpb[13] = 1  # sectors per cluster
    struct.pack_into("<H", bpb, 14, RESERVED)
    bpb[16] = 1  # FAT count
    struct.pack_into("<H", bpb, 17, ROOT_ENT)
    struct.pack_into("<H", bpb, 19, SECTOR_COUNT)
    bpb[21] = FAT_ID
    struct.pack_into("<H", bpb, 22, FAT_SECTORS)
    struct.pack_into("<H", bpb, 24, 32)
    struct.pack_into("<H", bpb, 26, 2)
    bpb[510:512] = b"\x55\xAA"
    image[0:SECTOR] = bpb

    # FAT
    fat_clusters = [0xFF8, 0xFFF]  # media + EOC marker style for first two
    next_cluster = 2
    root = bytearray(ROOT_SECTORS * SECTOR)
    root_i = 0
    for name, ext, data in raw_files:
        clusters_needed = max(1, (len(data) + SECTOR - 1) // SECTOR)
        first = next_cluster
        for c in range(clusters_needed):
            cl = next_cluster
            next_cluster += 1
            is_last = c == clusters_needed - 1
            fat_clusters.append(0xFFF if is_last else next_cluster)
            start = (data_start + (cl - 2)) * SECTOR
            chunk = data[c * SECTOR : (c + 1) * SECTOR]
            image[start : start + len(chunk)] = chunk
        entry = dir_entry(name, ext, len(data), first)
        root[root_i : root_i + 32] = entry
        root_i += 32
        if root_i >= len(root):
            raise SystemExit("Root directory full — shrink MSC payload.")

    fat_bytes = fat12_encode(fat_clusters)
    if len(fat_bytes) > FAT_SECTORS * SECTOR:
        raise SystemExit("FAT too large")
    image[RESERVED * SECTOR : RESERVED * SECTOR + len(fat_bytes)] = fat_bytes
    image[(RESERVED + FAT_SECTORS) * SECTOR : (RESERVED + FAT_SECTORS + ROOT_SECTORS) * SECTOR] = root
    return bytes(image)


def write_header(img: bytes):
    lines = [
        "#pragma once",
        "// Auto-generated USB MSC installer disk. Do not edit.",
        f"static const uint32_t FENNSILL_MSC_SECTORS = {SECTOR_COUNT};",
        f"static const uint32_t FENNSILL_MSC_SECTOR_SIZE = {SECTOR};",
        f"static const uint32_t FENNSILL_MSC_BYTES = {len(img)};",
        "static const uint8_t FENNSILL_MSC_DISK[] PROGMEM = {",
    ]
    row = []
    for i, b in enumerate(img):
        row.append(f"0x{b:02X}")
        if len(row) == 16:
            lines.append("  " + ", ".join(row) + ",")
            row = []
    if row:
        lines.append("  " + ", ".join(row) + ",")
    lines.append("};")
    lines.append("")
    OUT_H.write_text("\n".join(lines), encoding="utf-8")


def main():
    PAYLOAD.mkdir(parents=True, exist_ok=True)
    # Ensure SETUP.BAT calls INSTALL.PS1 on the drive
    setup = PAYLOAD / "SETUP.BAT"
    setup.write_text(
        "@echo off\r\n"
        "title Fennsill Setup\r\n"
        "cd /d \"%~dp0\"\r\n"
        "echo Installing Fennsill from the panel...\r\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -File \"%~dp0INSTALL.PS1\"\r\n"
        "if errorlevel 1 pause\r\n",
        encoding="ascii",
    )
    img = build()
    OUT_BIN.write_bytes(img)
    write_header(img)
    print(OUT_BIN, len(img), "bytes")
    print(OUT_H)


if __name__ == "__main__":
    main()
