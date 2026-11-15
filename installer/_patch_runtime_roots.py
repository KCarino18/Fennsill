"""One-shot: sync identity scripts into runtime/ and fix ROOT detection."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONN = ROOT / "connector"
RUNTIME = CONN / "runtime"

ROOT_BLOCK = (
    "_HERE = Path(__file__).resolve().parent\n"
    '_DEFAULT_ROOT = _HERE.parents[1] if _HERE.name == "runtime" else _HERE.parent\n'
    'ROOT = Path(os.environ.get("FENNSILL_ROOT") or _DEFAULT_ROOT)'
)

PAT = re.compile(r"^ROOT = Path\(__file__\)\.resolve\(\)\.parents\[1\]\s*$", re.M)
PAT2 = re.compile(
    r'^ROOT = Path\(os\.environ\.get\("FENNSILL_ROOT"\) or Path\(__file__\)\.resolve\(\)\.parents\[1\]\)\s*$',
    re.M,
)
PAT3 = re.compile(
    r'^ROOT = Path\(os\.environ\.get\("FENNSILL_ROOT"\) or Path\(__file__\)\.resolve\(\)\.parents\[1\]\)\s*$'
    r'|^ROOT = Path\(os\.environ\.get\("ARTIPHACT_ROOT".*$',
    re.M,
)


def ensure_os_import(text: str) -> str:
    head = text.split("sys.path", 1)[0]
    if "import os" in head:
        return text
    if "from __future__ import annotations\n" in text:
        return text.replace(
            "from __future__ import annotations\n",
            "from __future__ import annotations\n\nimport os\n",
            1,
        )
    return "import os\n" + text


def ensure_runtime_path(text: str) -> str:
    needle = 'sys.path.insert(0, str(ROOT / "connector"))'
    add = 'sys.path.insert(0, str(ROOT / "connector" / "runtime"))'
    if add in text or needle not in text:
        return text
    return text.replace(needle, needle + "\n" + add, 1)


def main() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "panel_status.py").write_text(
        (CONN / "identity_status.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (RUNTIME / "bind_device.py").write_text(
        (CONN / "device_bind_tool.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    print("synced panel_status.py + bind_device.py")

    for path in sorted(RUNTIME.glob("*.py")):
        if path.name in {"panel_status.py", "bind_device.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        orig = text
        text = ensure_os_import(text)
        text = PAT.sub(ROOT_BLOCK, text)
        text = PAT2.sub(ROOT_BLOCK, text)
        text = ensure_runtime_path(text)
        if text != orig:
            path.write_text(text, encoding="utf-8")
            print("patched", path.name)
        else:
            print("unchanged", path.name)


if __name__ == "__main__":
    main()
