"""Explicitly imported, QA-filtered satellite point observations.

Remote connector availability is not evidence of an archived time series.
Raw files are retained by checksum; curated data records product, QA policy,
source cadence, units and its representative-point scope.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from . import google_drive
from .history import region_by_id
from .nasa import _cache_write, remote_csv

SOURCES = {
    "smap": {"source": "NASA SMAP", "field": "smap_surface_m3_m3", "unit": "m³/m³",
             "aggregate": "mean", "qa": "Product ID and product-specific SMAP QA required for SPL3; SPL4 product ID required"},
    "mod16": {"source": "NASA MODIS MOD16", "field": "modis_et_mm", "unit": "mm/composite",
              "aggregate": "sum", "qa": "MOD16 ET_QC is mandatory; compositing period retained"},
    "hls": {"source": "NASA HLS", "field": "ndvi", "unit": "unitless NDVI",
            "aggregate": "mean", "qa": "HLS QA mask is mandatory; cloud/shadow masked"},
    "gpm": {"source": "NASA GPM IMERG", "field": "gpm_rain_mm", "unit": "mm per supplied period",
            "aggregate": "sum", "qa": "Finite, nonnegative values; input must already be aggregated over a documented UTC interval"},
}


def _base() -> Path:
    return Path(os.getenv("FIELD_SHIFT_SATELLITE_DIR", str(Path(__file__).resolve().parents[3] / "data" / "satellite")))


def _key(region_id: str, product: str) -> str:
    return f"satellite-curated/{region_id}/{product}.json"


def _read_remote(region_id: str, product: str) -> dict | None:
    if not google_drive.configured():
        return None
    try:
        raw = google_drive.get_object(_key(region_id, product))
        return json.loads(raw.decode("utf-8")) if raw is not None else None
    except (google_drive.GoogleDriveError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Google Drive satellite curated archive is inaccessible") from exc


def satellite_history(region_id: str, product: str) -> dict:
    region_by_id(region_id)
    if product not in SOURCES:
        raise ValueError("Unknown satellite product")
    payload = _read_remote(region_id, product)
    if payload is None:
        try:
            payload = json.loads((_base() / "curated" / region_id / f"{product}.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"status": "not_archived", "product": product, "region_id": region_id,
                    "monthly": [], "note": "Connector presence is NOT evidence of archived satellite observations."}
    rows = payload.get("monthly")
    if not isinstance(rows, list) or payload.get("schema_version") != 1 or payload.get("product") != product or payload.get("region_id") != region_id:
        raise ValueError("Satellite archive identity mismatch")
    canonical = json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest() != payload.get("sha256"):
        raise ValueError("Satellite archive checksum mismatch")
    return payload


def import_satellite_csv(*, region_id: str, product: str, filepath: Path, product_id: str,
                         version: str, native_resolution: str, temporal_resolution: str,
                         citation: str, smap_reprocessing_verified: bool = False,
                         reprocessing_evidence: str = "") -> dict:
    region_by_id(region_id)
    if product not in SOURCES:
        raise ValueError("Unknown satellite product")
    if not all(value.strip() for value in (product_id, version, native_resolution, temporal_resolution, citation)):
        raise ValueError("Product ID, version, spatial/temporal resolution and citation are mandatory")
    import csv
    file_bytes = filepath.read_bytes()
    raw_hash = hashlib.sha256(file_bytes).hexdigest()
    records = list(csv.DictReader(file_bytes.decode("utf-8-sig").splitlines()))
    if not records:
        raise ValueError("Source file is empty")
    if product == "smap" and not all(row.get("smap_product") and
                                      (row.get("smap_qa") or row["smap_product"].upper().startswith("SPL4SMGP"))
                                      for row in records):
        raise ValueError("SMAP product ID and product-specific QA are mandatory")
    if product == "smap":
        affected = any(row.get("smap_product", "").upper().startswith("SPL4SMGP")
                       and "2026-05-14" <= str(row.get("date", "")) <= "2026-07-28"
                       for row in records)
        if affected and not (smap_reprocessing_verified and reprocessing_evidence.strip()):
            raise ValueError("SMAP L4 2026-05-14 to 2026-07-28 geolocation issue: documented reprocessing verification is required")
    if product == "mod16" and not all(row.get("modis_et_qc") for row in records):
        raise ValueError("MOD16 ET_QC is mandatory")
    if product == "hls" and not all(row.get("hls_qa") for row in records):
        raise ValueError("HLS QA mask is mandatory")

    accepted = remote_csv(filepath, SOURCES[product]["source"], "satellite")
    field = SOURCES[product]["field"]
    monthly: dict[str, list] = defaultdict(list)
    for item in accepted:
        value = getattr(item, field, None)
        if value is None:
            continue
        valid_range = (value >= 0 if product in {"gpm", "mod16", "smap"} else -1 <= value <= 1)
        if math.isfinite(value) and valid_range:
            monthly[item.d.strftime("%Y-%m")].append((item.d, value, item.modis_et_period_days))
    aggregates = []
    for month, values in sorted(monthly.items()):
        value = sum(v for _, v, _ in values) if SOURCES[product]["aggregate"] == "sum" else mean(v for _, v, _ in values)
        aggregates.append({
            "month": month, "value": round(value, 5), "n_observations": len(values),
            "data_through": max(day for day, _, _ in values).isoformat(),
            "native_period_days": sorted({days for _, _, days in values}),
        })
    if not aggregates:
        raise ValueError("No QA-passed observations; refusing to publish")
    row_digest = hashlib.sha256(json.dumps(aggregates, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    output = {
        "schema_version": 1, "product": product, "region_id": region_id, "product_id": product_id,
        "collection_version": version, "native_resolution": native_resolution, "temporal_resolution": temporal_resolution,
        "unit": SOURCES[product]["unit"], "aggregation": SOURCES[product]["aggregate"], "citation": citation,
        "retrieved_at": datetime.now(UTC).isoformat(), "data_through": aggregates[-1]["data_through"],
        "raw_sha256": raw_hash, "sha256": row_digest, "quality_status": "qa_filtered", "status": "ready",
        "coverage_fraction": None, "fallback_used": False, "source_geometry": "representative_point_not_zone_average",
        "accepted_observations": sum(len(items) for items in monthly.values()), "input_observations": len(records),
        "qa_policy": SOURCES[product]["qa"],
        "smap_reprocessing_verified": smap_reprocessing_verified if product == "smap" else None,
        "smap_reprocessing_evidence": reprocessing_evidence if product == "smap" else None,
        "monthly": aggregates,
        "note": "Imported user-provided CSV; provenance is not independent confirmation of NASA retrieval.",
    }
    raw_dir = _base() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{raw_hash}.csv"
    if not raw_path.exists():
        raw_path.write_bytes(file_bytes)
    if os.getenv("VERCEL") and not google_drive.configured():
        raise RuntimeError("Serverless satellite ingestion requires Google Drive archive configuration")
    if google_drive.configured():
        try:
            google_drive.put_object(
                f"satellite-raw/{raw_hash}.csv",
                file_bytes,
                mime_type="text/csv",
            )
            curated_bytes = json.dumps(output, ensure_ascii=False, sort_keys=True).encode("utf-8")
            google_drive.put_object(_key(region_id, product), curated_bytes)
            archived = google_drive.get_object(_key(region_id, product))
            if archived != curated_bytes:
                raise RuntimeError("Google Drive satellite archive read-back mismatch")
        except Exception as exc:
            raise RuntimeError("Satellite archive could not be published to Google Drive") from exc
    else:
        _cache_write(_base() / "curated" / region_id / f"{product}.json", output)
    return output
