"""Run completed-year ingestion outside request handlers, one region/year at a time."""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fieldshift.v3.history import REGIONS, archive_dir, prefetch_year
from fieldshift.v3.nasa import _cache_write


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=[r["id"] for r in REGIONS],
                        default=[r["id"] for r in REGIONS])
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--pause", type=float, default=1.0)
    args = parser.parse_args()
    if args.start_year > args.end_year or args.end_year - args.start_year > 29:
        parser.error("Select 1–30 years")
    results = []
    for region in args.regions:
        for year in range(args.start_year, args.end_year + 1):
            try:
                meta = prefetch_year(region, year, refresh=args.refresh)
                item = {"region": region, "year": year, "status": "available", "sha256": meta["sha256"]}
            except Exception as exc:
                item = {"region": region, "year": year, "status": "failed", "error_type": type(exc).__name__}
            results.append(item)
            print(json.dumps(item), flush=True)
            _cache_write(archive_dir() / "prefetch-status.json", {"results": results})
            time.sleep(max(1.0, args.pause))
    return int(any(item["status"] == "failed" for item in results))


if __name__ == "__main__":
    raise SystemExit(main())
