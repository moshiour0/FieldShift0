"""Evidence-aware lifecycle classification for product analysis runs.

The current analysis engine can produce a provisional simulation with synthetic
fallbacks. This module prevents those outputs from being labelled final until
required core evidence is present and source jobs have settled.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REQUIRED_SOURCE_KEYS = frozenset({"nasa_power_daily_weather"})
PENDING_STATUSES = frozenset({"queued", "pending", "retrying"})
GAP_STATUSES = frozenset({
    "partial",
    "stale",
    "unavailable",
    "not_configured",
    "error",
    "fallback",
    "failed",
})
KNOWN_SOURCE_NAMES = {
    "nasa power daily weather": "nasa_power_daily_weather",
    "nasa smap": "nasa_smap",
    "nasa hls": "nasa_hls",
    "nasa modis mod16": "nasa_modis_mod16",
    "nasa gpm imerg": "nasa_gpm_imerg",
    "nasa nex gddp cmip6 ssp245": "nasa_nex_gddp_cmip6_ssp245",
    "nasa nex gddp cmip6 ssp585": "nasa_nex_gddp_cmip6_ssp585",
}


def source_key_for(name: str) -> str:
    """Return a stable source key from the current evidence display name."""
    normalized = re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()
    if normalized in KNOWN_SOURCE_NAMES:
        return KNOWN_SOURCE_NAMES[normalized]
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "unknown_source"


def classify_run_readiness(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize current evidence state without confusing simulation and final readiness.

    NASA POWER daily weather is the initial required core source. Supplemental
    sources remain optional, but pending work keeps a result preliminary and
    settled source gaps are disclosed as final_with_gaps.
    """
    normalized: list[dict[str, Any]] = []
    for item in items:
        name = str(item.get("name") or item.get("source_name") or "Evidence source")
        key = str(item.get("source_key") or source_key_for(name))
        status = str(item.get("status") or "unknown").lower()
        is_required = bool(item.get("required", key in REQUIRED_SOURCE_KEYS))
        normalized.append({
            "name": name,
            "source_key": key,
            "status": status,
            "required": is_required,
        })

    required_items = [item for item in normalized if item["required"]]
    core_ready = bool(required_items) and all(item["status"] == "available" for item in required_items)
    pending = [item for item in normalized if item["status"] in PENDING_STATUSES]
    gaps = [
        item for item in normalized
        if item["status"] in GAP_STATUSES
        or item["status"] not in PENDING_STATUSES | GAP_STATUSES | {"available", "skipped"}
    ]
    missing_required = [item for item in required_items if item["status"] != "available"]

    if pending or not core_ready:
        status = "preliminary_ready"
        if pending:
            names = ", ".join(item["name"] for item in pending[:4])
            message = (
                "A preliminary result is available. Waiting for these data sources to finish: "
                f"{names}. Do not treat this as a final result."
            )
        else:
            message = (
                "A preliminary/diagnostic result is available, but the required NASA POWER "
                "weather input has not passed readiness checks. Synthetic fallback must not "
                "be interpreted as observed weather."
            )
    elif gaps:
        status = "final_with_gaps"
        names = ", ".join(item["name"] for item in gaps[:5])
        message = (
            "The required core weather input is ready. Some supplemental or requested sources "
            f"remain incomplete or unavailable: {names}. Review their provenance and limitations."
        )
    else:
        status = "final_ready"
        message = "Required core evidence and all configured/requested sources passed their readiness checks."

    return {
        "status": status,
        "status_message": message,
        "is_final": status in {"final_ready", "final_with_gaps"},
        "prediction_eligible": core_ready,
        "core_data_ready": core_ready,
        "pending_sources": [item["name"] for item in pending],
        "gap_sources": [item["name"] for item in gaps],
        "missing_required_sources": [item["name"] for item in missing_required],
        "required_source_keys": sorted(REQUIRED_SOURCE_KEYS),
    }
