"""Verify the configured Google Drive archive before any NASA ingestion."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fieldshift.v3.google_drive import verify_storage


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "verify":
        print("Usage: python scripts/google_drive_archive.py verify", file=sys.stderr)
        return 2
    try:
        result = verify_storage()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), flush=True)
        raise
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
