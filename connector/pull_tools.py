"""Pull the frozen MCP tool catalog once for Claude.

Customization of the screen happens in Claude Artifacts after this pull.
The MCP never redesigns the tools or the buyer's content.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "tools.json"


def load_catalog():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("tools"), list):
        raise SystemExit("tools.json is damaged.")
    return data


def main():
    catalog = load_catalog()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    text = json.dumps(catalog, indent=2)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
        print(out)
        return
    print(text)


if __name__ == "__main__":
    main()
