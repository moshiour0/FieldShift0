"""Backfill annual SMAP point samples for the nine configured reference coordinates.

These are representative point samples, not regional means or a gridded
Bangladesh-wide archive. They must never be substituted for an arbitrary
user-selected farm coordinate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fieldshift.v3.gee import gee_credentials_configured, smap_daily_point_timeseries
from fieldshift.v3.google_drive import configured as google_drive_configured
from fieldshift.v3.history import REGIONS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True, choices=[item["id"] for item in REGIONS])
    parser.add_argument("--start-year", type=int, default=2016)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--pause", type=float, default=2.0)
    parser.add_argument("--cache-dir", type=Path, default=Path(
        os.getenv("FIELD_SHIFT_CACHE_DIR", ".cache/fieldshift-smap-reference")
    ))
    args = parser.parse_args()

    current_year = date.today().year
    if (
        args.start_year < 2016
        or args.end_year < args.start_year
        or args.end_year >= current_year
        or args.end_year - args.start_year > 29
    ):
        parser.error("Select 1–30 completed calendar years from 2016 onward.")

    if not google_drive_configured():
        print(json.dumps({
            "region": args.region,
            "status": "failed",
            "error": "GOOGLE_DRIVE_* archive settings are not configured",
            "requests_started": False,
        }), flush=True)
        return 2
    if not gee_credentials_configured():
        print(json.dumps({
            "region": args.region,
            "status": "failed",
            "error": "Earth Engine is disabled until FIELD_SHIFT_GEE_NONCOMMERCIAL_CONFIRMED=true and eligible noncommercial registration is verified",
            "requests_started": False,
        }), flush=True)
        return 2

    region = next(item for item in REGIONS if item["id"] == args.region)
    results = []
    failed = False
    for year in range(args.start_year, args.end_year + 1):
        start, end = date(year, 1, 1), date(year, 12, 31)
        try:
            result = smap_daily_point_timeseries(
                float(region["lat"]),
                float(region["lon"]),
                start,
                end,
                args.cache_dir,
                allow_live_query=True,
            )
            complete = (
                result.status == "available"
                and result.coverage_fraction == 1.0
                and result.archive_cache_status == "verified"
                and len(result.rows) == (end - start).days + 1
                and len(result.archive_object_keys) == 1
            )
            row = {
                "region": args.region,
                "year": year,
                "sample_type": "representative_point_only",
                "latitude": region["lat"],
                "longitude": region["lon"],
                "status": "available" if complete else result.status,
                "daily_records": len(result.rows),
                "coverage_fraction": result.coverage_fraction,
                "retrieval_mode": result.retrieval_mode,
                "archive_cache_status": result.archive_cache_status,
                "archive_object_keys": list(result.archive_object_keys),
                "sha256": result.archive_sha256,
                "source": "NASA SMAP SPL4SMGP.008 via Google Earth Engine",
                "spatial_resolution": "~11 km GEE pixel; native SMAP L4 grid ~9 km",
                "temporal_resolution": "3-hourly source aggregated to UTC daily mean; 8/8 intervals required",
                "note": "Point sample only; not a regional mean, AEZ polygon, or arbitrary-field measurement.",
            }
            if not complete:
                failed = True
                row["error"] = "Annual point archive did not pass full-coverage and Drive read-back gates."
        except Exception as exc:
            failed = True
            row = {
                "region": args.region,
                "year": year,
                "sample_type": "representative_point_only",
                "status": "failed",
                "error_type": type(exc).__name__,
            }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        time.sleep(max(1.0, args.pause))

    summary = {
        "region": args.region,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "status": "failed" if failed else "available",
        "successful_years": sum(item["status"] == "available" for item in results),
        "failed_years": [item["year"] for item in results if item["status"] != "available"],
        "sample_type": "representative_point_only",
    }
    print(json.dumps({"summary": summary}, ensure_ascii=False), flush=True)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
