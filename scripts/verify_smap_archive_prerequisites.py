"""Verify the private Drive and Earth Engine prerequisites for SMAP archival.

This performs only a temporary Drive round-trip and a one-day Earth Engine
collection metadata/count read. It does not retrieve or archive daily SMAP data.
"""
from __future__ import annotations

import json
import sys

from fieldshift.v3.gee import _initialise_ee, gee_credentials_configured
from fieldshift.v3.google_drive import configured as google_drive_configured, verify_storage

ASSET = "NASA/SMAP/SPL4SMGP/008"
PROBE_START = "2025-01-01"
PROBE_END = "2025-01-02"


def verify() -> dict[str, object]:
    """Verify credentials, private Drive read-back and GEE asset visibility."""
    if not google_drive_configured():
        raise RuntimeError("Google Drive archive credentials are not configured.")
    if not gee_credentials_configured():
        raise RuntimeError("Earth Engine is disabled until FIELD_SHIFT_GEE_NONCOMMERCIAL_CONFIRMED=true and eligible noncommercial registration is verified.")

    drive = verify_storage()
    ee = _initialise_ee()
    image_count = ee.ImageCollection(ASSET).filterDate(PROBE_START, PROBE_END).size().getInfo()
    if not isinstance(image_count, int) or image_count <= 0:
        raise RuntimeError("The SMAP SPL4SMGP.008 collection is not accessible for the probe date.")

    return {
        "status": "ok",
        "drive": drive,
        "earth_engine": "verified",
        "asset": ASSET,
        "probe_date": PROBE_START,
        "probe_image_count": image_count,
        "note": "No daily SMAP time series were fetched or archived by this preflight.",
    }


def main() -> int:
    try:
        result = verify()
    except Exception as exc:
        # Never print exception details from credential or provider libraries.
        print(json.dumps({
            "status": "failed",
            "error_type": type(exc).__name__,
            "message": "SMAP archive preflight failed; no SMAP backfill data were requested.",
        }), flush=True)
        return 1
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
