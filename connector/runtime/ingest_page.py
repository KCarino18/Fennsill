"""CLI intake for Fennsill.exe paste/import and any AI that can write a file."""

from __future__ import annotations

import os

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent
ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)
sys.path.insert(0, str(ROOT / "connector"))
sys.path.insert(0, str(ROOT / "connector" / "runtime"))

from intake import intake_page  # noqa: E402
from security import SecurityError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Ingest HTML/SVG into Fennsill.")
    parser.add_argument("--html-file", help="Path to an HTML file")
    parser.add_argument("--svg-file", help="Path to an SVG file")
    parser.add_argument("--html", help="Raw HTML string")
    parser.add_argument("--svg", help="Raw SVG string")
    parser.add_argument("--title", default="")
    parser.add_argument("--source", default="import")
    parser.add_argument("--push", action="store_true", help="Also push to the USB panel")
    parser.add_argument("--no-push", action="store_true", help="Gallery only (default)")
    args = parser.parse_args()

    html = args.html
    svg = args.svg
    if args.html_file:
        html = Path(args.html_file).read_text(encoding="utf-8")
    if args.svg_file:
        svg = Path(args.svg_file).read_text(encoding="utf-8")
    if not html and not svg:
        raise SystemExit("Pass --html-file, --svg-file, --html, or --svg.")

    push = bool(args.push) and not args.no_push
    # Default: save only. Fennsill gallery → Send to panel.
    if not args.push:
        push = False

    try:
        result = intake_page(html=html, svg=svg, title=args.title, source=args.source, push=push)
    except SecurityError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result))


if __name__ == "__main__":
    main()
