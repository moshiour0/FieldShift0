#!/usr/bin/env python3
"""Termux smoke test of the SAME AppEEARS adapter used by Run Analysis.

Run from the extracted project. Only the Python standard library is needed.
Read credentials from FIELD_SHIFT_APPEEARS_USER / PASSWORD or TOKEN.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from fieldshift.v3.appeears import appeears_point_timeseries, credentials_configured
from fieldshift.v3.dates import evidence_dates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=24.7471)
    parser.add_argument("--lon", type=float, default=90.4203)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-01-15")
    parser.add_argument("--wait", type=int, default=300)
    parser.add_argument("--out", default="appeears_production_result.json")
    args = parser.parse_args()
    if not credentials_configured():
        print("Set FIELD_SHIFT_APPEEARS_USER and FIELD_SHIFT_APPEEARS_PASSWORD (or TOKEN) first.")
        return 2
    start, end = evidence_dates(args.start, args.end)
    deadline = time.monotonic() + args.wait
    cache = Path(__file__).resolve().parent / ".smoke-cache"
    while True:
        result = appeears_point_timeseries(args.lat, args.lon, start, end, cache_dir=cache, max_wait_seconds=0)
        for item in result.datasets:
            print(f"{item['name']}: {item['status']} | {item.get('error') or item.get('coverage')}")
        waiting = [item for item in result.datasets if item["status"] in {"pending", "retrying"}]
        if not waiting or time.monotonic() >= deadline:
            break
        delay = max(30, *(int(item.get("retry_after_seconds") or 30) for item in waiting))
        if delay >= deadline - time.monotonic():
            print(f"NASA requires another {delay}s before checking; run this command again later to resume.")
            break
        print(f"Next check in {delay}s.")
        time.sleep(delay)
    output = {"start_date": start.isoformat(), "end_date": end.isoformat(), "results": result.datasets,
              "usable_rows": len(result.remote), "note": "Uses the production adapter, including pixel QA and real numeric-value parsing."}
    Path(args.out).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Saved {args.out}")
    return 0 if all(x["status"] in {"available", "partial"} for x in result.datasets) else 1


if __name__ == "__main__":
    raise SystemExit(main())
