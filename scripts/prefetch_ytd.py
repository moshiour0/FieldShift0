"""Manual, opt-in current-year NASA POWER ingestion; no synthetic records are generated."""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fieldshift.v3.history import REGIONS
from fieldshift.v3.history_extended import prefetch_ytd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=[r["id"] for r in REGIONS],
                        default=[r["id"] for r in REGIONS])
    parser.add_argument("--through", type=date.fromisoformat, default=date.today() - timedelta(days=5),
                        help="Explicit last quality-available date; not necessarily today")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    errors = 0
    for region in args.regions:
        try:
            meta = prefetch_ytd(region, args.through, refresh=args.refresh)
            print(json.dumps({"region": region, "status": "ready", "data_through": meta["data_through"],
                              "sha256": meta["sha256"]}), flush=True)
        except Exception as exc:
            errors += 1
            print(json.dumps({"region": region, "status": "failed", "error_type": type(exc).__name__}), flush=True)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
