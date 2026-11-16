"""Build FennSill-Quick-Start.pdf (no third-party deps)."""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "FennSill-Quick-Start.pdf"

# Simple text lines for the buyer guide (pre-flashed panel).
LINES = [
    "FennSill Quick Start",
    "",
    "Your e-ink panel arrives already flashed. You only need to install FennSill,",
    "link your account, and connect the AI tools you already use.",
    "",
    "1. Install FennSill",
    "   - Download FennsillSetup.exe from the FennSill releases page.",
    "   - Run it and allow the Administrator (UAC) prompt.",
    "   - Wait until FennSill Desk opens. Setup also installs the FennSill Agent",
    "     service so the panel stays checked in when Desk is closed.",
    "",
    "2. Plug in the panel",
    "   - Connect the panel with USB.",
    "   - Desk should show: FennSill panel connected.",
    "   - Copy Device ID, Serial, and Install key from Desk when needed.",
    "",
    "3. Link your account",
    "   - Open the FennSill account site and sign up or sign in.",
    "   - Use Link your panel and paste the Device ID from Desk.",
    "   - Do not put Device ID in the AI MCP connector form.",
    "",
    "4. Paste the device key",
    "   - On the account site: Mint device key, then Copy.",
    "   - In Desk, click Paste device key.",
    "   - Status should become Cloud: checked in.",
    "   - You can close Desk; the Agent service keeps check-in while USB is plugged in.",
    "",
    "5. Connect any AI that supports custom MCP",
    "   Works the same for ChatGPT, Claude, Cursor, and similar tools:",
    "   - MCP URL = the MCP URL from your FennSill account site",
    "   - Add header Authorization = Bearer <token> (use Copy header on the site)",
    "   - Leave any Bearer token environment-variable field empty",
    "   - Device ID does not go in the MCP form",
    "",
    "6. Try a push",
    "   - Ask your AI to send a simple page to your panel (for example a short greeting).",
    "   - Confirm the e-ink screen refreshes.",
    "",
    "7. Troubleshooting",
    "   - Panel not seen: try another USB cable/port; click Refresh in Desk.",
    "   - Cloud offline / agent stale: open Services and confirm FennSill Agent is Running;",
    "     Paste device key again if needed.",
    "   - AI cannot push: re-check MCP URL and Authorization Bearer header on the same account.",
    "   - Uninstall: Settings > Apps > Installed apps > FennSill.",
    "",
    "Need help? https://github.com/KCarino18/Fennsill/releases",
]


def escape_pdf(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf(path: Path) -> None:
    # Helvetica, 11pt, starting near top of US Letter.
    y = 720
    leading = 14
    content_lines = ["BT", "/F1 11 Tf", "50 720 Td", "14 TL"]
    first = True
    for line in LINES:
        if line.startswith("FennSill Quick Start"):
            # Title slightly larger
            if not first:
                content_lines.append("ET")
                content_lines.append("BT")
                content_lines.append("/F1 18 Tf")
                content_lines.append(f"50 {y} Td")
                content_lines.append("18 TL")
            else:
                content_lines = ["BT", "/F1 18 Tf", f"50 {y} Td", "18 TL"]
            content_lines.append(f"({escape_pdf(line)}) Tj")
            content_lines.append("T*")
            y -= 22
            content_lines.append("ET")
            content_lines.append("BT")
            content_lines.append("/F1 11 Tf")
            content_lines.append(f"50 {y} Td")
            content_lines.append("14 TL")
            first = False
            continue
        if y < 72:
            # New page
            content_lines.append("ET")
            # We'll only use one page for this short guide; clamp.
            break
        if first:
            first = False
        content_lines.append(f"({escape_pdf(line)}) Tj")
        content_lines.append("T*")
        y -= leading
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode("ascii")
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    out = bytearray()
    out.extend(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    path.write_bytes(out)
    print(f"wrote {path} ({path.stat().st_size} bytes)", flush=True)


if __name__ == "__main__":
    build_pdf(OUT)
