#!/usr/bin/env python3
"""Check the deployed website's actual Run Analysis endpoint (stdlib only)."""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Your deployed site origin, e.g. https://your-project.vercel.app")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-01-15")
    parser.add_argument("--lat", type=float, default=24.7471)
    parser.add_argument("--lon", type=float, default=90.4203)
    parser.add_argument("--attempts", type=int, default=10)
    parser.add_argument("--out", default="website_integration_result.json")
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be positive")
    payload = {"field": {"lat": args.lat, "lon": args.lon}, "start_date": args.start, "end_date": args.end,
               "n_weight_samples": 60, "n_uncertainty_samples": 20}
    for attempt in range(args.attempts):
        request = urllib.request.Request(args.url.rstrip("/") + "/api/analysis/run", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=310) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            print(f"Website returned HTTP {exc.code}; check deployment logs and the evidence panel.")
            return 2
        evidence = result["evidence"]["items"]
        print(f"Attempt {attempt + 1}: {result['run']['status']}")
        for item in evidence:
            print(f"  {item['name']}: {item['status']} | {item.get('error') or item.get('coverage') or ''}")
        if not any(item["status"] == "pending" for item in evidence):
            break
        if attempt + 1 < args.attempts:
            time.sleep(15)
    Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved {args.out}")
    nasa = [item for item in evidence if item["name"].startswith("NASA ")]
    return 0 if len(nasa) >= 6 and all(item["status"] in {"available", "partial", "stale"} for item in nasa) else 1


if __name__ == "__main__":
    raise SystemExit(main())
