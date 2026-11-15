"""Operator CLI: renew/revoke access, publish update manifests.

Usage (from cloud/ with PYTHONPATH=.):
  python scripts/operator_cli.py publish-manifest stable 1.0.0 https://example/app.bin <sha256>
  python scripts/operator_cli.py set-subscription user@example.com active 2026-12-31T00:00:00Z
  python scripts/operator_cli.py set-subscription user@example.com inactive
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import store  # noqa: E402


def main(argv: list[str]) -> None:
    store.init_db()
    if not argv:
        print(__doc__)
        sys.exit(1)
    cmd = argv[0]
    if cmd == "publish-manifest" and len(argv) == 5:
        store.publish_update_manifest(argv[1], argv[2], argv[3], argv[4])
        print("published", argv[1], argv[2])
        return
    if cmd == "set-subscription" and len(argv) >= 3:
        email, status = argv[1], argv[2]
        end = argv[3] if len(argv) > 3 else None
        store.set_access_subscription(email, status, end)
        print("subscription", email, status, end)
        return
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
