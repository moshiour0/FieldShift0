"""Run one queued NASA POWER refresh outside the HTTP request.

Use a supervised worker process: python -m fieldshift.v3.refresh_worker --poll-seconds 20
"""
from __future__ import annotations

import argparse
import time
from datetime import date

from .history_extended import prefetch_ytd
from .refresh_jobs import claim_refresh, retry_refresh, update_refresh


def execute_one() -> bool:
    job = claim_refresh()
    if not job:
        return False
    try:
        if job["product"] != "power":
            raise ValueError("Unsupported product for the POWER worker")
        result = prefetch_ytd(
            job["region_id"],
            date.fromisoformat(job["data_through"]),
            refresh=True,
            progress=lambda stage: update_refresh(job["id"], stage),
        )
        update_refresh(job["id"], "ready", published_through=result["data_through"])
    except Exception as exc:
        # Record the failure class, not provider payloads, credentials or URLs.
        retry_refresh(job["id"], int(job["attempts"]), type(exc).__name__ + ": provider or archive publish failed")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=20)
    args = parser.parse_args()
    while True:
        did_work = execute_one()
        if args.once:
            break
        if not did_work:
            time.sleep(max(5, args.poll_seconds))


if __name__ == "__main__":
    main()
