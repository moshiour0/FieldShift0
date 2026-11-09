"""Auditable regional POWER archive. Missing observations are never synthesized."""
from __future__ import annotations

import calendar
import hashlib
import json
import math
import os
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from . import google_drive
from .models import Provenance, WeatherDay
from .nasa import NasaDataError, _cache_write, power_daily

ROOT = Path(__file__).resolve().parents[3]
REGIONS: list[dict[str, Any]] = [
    {"id": "mymensingh", "name": "ময়মনসিংহ", "zone": "মধ্য", "lat": 24.75, "lon": 90.41},
    {"id": "dhaka", "name": "ঢাকা", "zone": "মধ্য", "lat": 23.81, "lon": 90.41},
    {"id": "rajshahi", "name": "রাজশাহী", "zone": "উত্তর-পশ্চিম", "lat": 24.37, "lon": 88.60},
    {"id": "rangpur", "name": "রংপুর", "zone": "উত্তর-পশ্চিম", "lat": 25.75, "lon": 89.25},
    {"id": "khulna", "name": "খুলনা", "zone": "দক্ষিণ-পশ্চিম", "lat": 22.85, "lon": 89.54},
    {"id": "barishal", "name": "বরিশাল", "zone": "দক্ষিণ-পশ্চিম", "lat": 22.70, "lon": 90.35},
    {"id": "sylhet", "name": "সিলেট", "zone": "পূর্ব", "lat": 24.89, "lon": 91.87},
    {"id": "chattogram", "name": "চট্টগ্রাম", "zone": "পূর্ব", "lat": 22.36, "lon": 91.78},
    {"id": "rangamati", "name": "রাঙামাটি", "zone": "পার্বত্য", "lat": 22.65, "lon": 92.18},
]


def archive_dir() -> Path:
    return Path(os.getenv("FIELD_SHIFT_HISTORY_DIR", str(ROOT / "data" / "history")))


def region_by_id(region_id: str) -> dict[str, Any]:
    for region in REGIONS:
        if region["id"] == region_id:
            return region
    raise ValueError("Unknown region")


def _monthly_archive_year(region_id: str, year: int) -> tuple[list[dict[str, Any]], dict] | None:
    """Read compact 2016-2025 POWER monthly aggregates for charting only.

    Aggregate records are never accepted by `archived_weather`, which requires
    the original daily observations before using data in crop simulations.
    """
    path = archive_dir() / "monthly-archive.json"
    if not path.exists():
        path = archive_dir() / "monthly-archive" / f"{region_id}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("source") != "NASA POWER Daily API":
        raise ValueError("Monthly archive schema or source mismatch")
    entry = payload.get("regions", {}).get(region_id)
    if not isinstance(entry, dict) or entry.get("region") != region_by_id(region_id):
        return None
    selected = next((item for item in entry.get("years", []) if item[0] == year), None)
    if not selected or len(selected) != 3 or len(selected[2]) != 12:
        return None
    _, original_sha256, months = selected
    records = []
    for row in months:
        if len(row) != 4:
            raise ValueError("Monthly archive row has an invalid shape")
        month, rain, temperature, days = row
        expected = calendar.monthrange(year, int(month))[1]
        if int(days) != expected or not math.isfinite(float(rain)) or not math.isfinite(float(temperature)):
            raise ValueError("Monthly archive fails date coverage or numeric validation")
        records.append({"month": f"{year}-{int(month):02d}", "rain_mm": float(rain),
                        "temperature_c": float(temperature), "days": int(days),
                        "expected_days": expected})
    meta = {"schema_version": 1, "region": entry["region"], "year": year,
            "source": payload["source"], "citation": payload["citation"],
            "sha256": original_sha256, "archive_representation": "monthly_aggregate",
            "sample_type": payload["sample_type"], "coverage_note": payload["coverage_note"]}
    return records, meta


def _digest(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _path(region_id: str, year: int) -> Path:
    region_by_id(region_id)
    if not 1981 <= year <= date.today().year:
        raise ValueError("Year outside POWER archive range")
    return archive_dir() / region_id / f"{year}.json"


def validate_days(days: tuple[WeatherDay, ...], start: date, end: date) -> None:
    expected = (end - start).days + 1
    if len(days) != expected or [d.d.toordinal() for d in days] != list(range(start.toordinal(), end.toordinal() + 1)):
        raise ValueError("Weather archive has missing, duplicate, or unordered dates")
    for day in days:
        values = [day.tmax_c, day.tmin_c, day.rh_mean_pct, day.wind_2m_ms, day.solar_rad_mj_m2_day, day.rain_mm]
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Weather archive has non-finite values")
        if not (-100 <= day.tmin_c <= day.tmax_c <= 70 and 0 <= day.rh_mean_pct <= 100
                and day.wind_2m_ms >= 0 and day.solar_rad_mj_m2_day >= 0 and day.rain_mm >= 0):
            raise ValueError("Weather archive fails physical bounds")
        if not day.provenance or day.provenance.source_type != "observed/model-derived":
            raise ValueError("Only actual POWER-derived records belong in the archive")


def read_year(region_id: str, year: int) -> tuple[tuple[WeatherDay, ...], dict]:
    path = _path(region_id, year)
    payload = None
    if google_drive.configured():
        try:
            archived = google_drive.get_object(f"power-history/{region_id}/{year}.json")
        except google_drive.GoogleDriveError as exc:
            raise RuntimeError("Google Drive history archive unavailable") from exc
        if archived is not None:
            try:
                payload = json.loads(archived.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Google Drive history object is not valid JSON") from exc
    if payload is None and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    if payload is None:
        raise FileNotFoundError(str(path))
    region = region_by_id(region_id)
    if (payload.get("region") != region or payload.get("year") != year
            or payload.get("schema_version") != 1 or _digest(payload["days"]) != payload.get("sha256")):
        raise ValueError("Archive identity or checksum mismatch")
    days = tuple(WeatherDay(**{**row, "d": date.fromisoformat(row["d"]),
                              "provenance": Provenance(**row["provenance"])}) for row in payload["days"])
    validate_days(days, date(year, 1, 1), date(year, 12, 31))
    return days, {k: v for k, v in payload.items() if k != "days"}


def prefetch_year(region_id: str, year: int, *, refresh: bool = False) -> dict:
    """CLI-only mutation: resumable one-year download with a strict quality gate."""
    region = region_by_id(region_id)
    path = _path(region_id, year)
    if date(year, 12, 31) >= date.today():
        raise ValueError("Only completed calendar years can be archived")
    if not refresh:
        try:
            if google_drive.configured():
                archive_key = f"power-history/{region_id}/{year}.json"
                remote_payload = google_drive.get_object(archive_key)
                if remote_payload is not None:
                    _, meta = read_year(region_id, year)
                    return {**meta, "retrieval_mode": "google_drive"}
                if path.exists():
                    # Migrate a validated local archive instead of downloading
                    # the same historical year from NASA again.
                    _, local_meta = read_year(region_id, year)
                    google_drive.put_object(archive_key, path.read_bytes())
                    _, remote_meta = read_year(region_id, year)
                    if remote_meta["sha256"] != local_meta["sha256"]:
                        raise NasaDataError("Migrated Google Drive archive checksum verification failed")
                    return {**remote_meta, "retrieval_mode": "local_archive_published"}
            else:
                _, meta = read_year(region_id, year)
                return {**meta, "retrieval_mode": "local_archive"}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    start, end = date(year, 1, 1), date(year, 12, 31)
    days = power_daily(region["lat"], region["lon"], start, end, timeout=20, retries=2,
                       cache_dir=archive_dir() / "raw")
    validate_days(days, start, end)
    rows = json.loads(json.dumps([asdict(d) for d in days], default=str))
    payload = {"schema_version": 1, "region": region, "year": year,
               "archived_at": datetime.now(UTC).isoformat(), "days": rows, "sha256": _digest(rows),
               "source": "NASA POWER", "citation": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
               "quality": days[0].source,
               "limitations": "Gridded point sample, not a field measurement or regional spatial average. Small gaps may be imputed by the POWER adapter."}
    _cache_write(path, payload)
    if not path.exists():
        raise NasaDataError("Archive directory is not writable")
    try:
        local_payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NasaDataError("Local archive write verification failed") from exc
    if local_payload.get("sha256") != payload["sha256"] or _digest(local_payload.get("days", [])) != payload["sha256"]:
        raise NasaDataError("Local archive checksum verification failed")
    if google_drive.configured():
        try:
            google_drive.put_object(
                f"power-history/{region_id}/{year}.json",
                path.read_bytes(),
            )
        except Exception as exc:
            raise RuntimeError("Completed-year Google Drive archive could not be published") from exc
    _, verified = read_year(region_id, year)
    if verified["sha256"] != payload["sha256"]:
        raise NasaDataError("Archive write verification failed")
    return verified


def archived_weather(lat: float, lon: float, start: date, end: date) -> tuple[WeatherDay, ...] | None:
    """Reuse only exact representative coordinates and a fully covered date span."""
    region = next((r for r in REGIONS if abs(r["lat"] - lat) < 0.000001 and abs(r["lon"] - lon) < 0.000001), None)
    if region is None:
        return None
    out: list[WeatherDay] = []
    try:
        for year in range(start.year, end.year + 1):
            days, _ = read_year(region["id"], year)
            out.extend(WeatherDay(**{**asdict(d), "d": d.d, "provenance": d.provenance,
                                     "source": f"NASA POWER (archive); original: {d.source}"})
                       for d in days if start <= d.d <= end)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    result = tuple(out)
    validate_days(result, start, end)
    return result


def history_summary(region_id: str, start_year: int = 2016, end_year: int = 2025) -> dict:
    region = region_by_id(region_id)
    if not 1981 <= start_year <= end_year < date.today().year or end_year - start_year > 29:
        raise ValueError("Select 1-30 completed calendar years from 1981 onward")
    monthly: list[dict[str, Any]] = []
    annual: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    missing: list[int] = []
    aggregate_only = False
    for year in range(start_year, end_year + 1):
        try:
            days, meta = read_year(region_id, year)
        except (OSError, ValueError, KeyError, TypeError):
            compact = _monthly_archive_year(region_id, year)
            if compact is None:
                missing.append(year)
                continue
            aggregate_only = True
            records, meta = compact
            evidence.append(meta)
            total_days = sum(item["days"] for item in records)
            annual.append({"year": year, "rain_mm": round(sum(item["rain_mm"] for item in records), 2),
                           "temperature_c": round(sum(item["temperature_c"] * item["days"] for item in records) / total_days, 2),
                           "days": total_days, "expected_days": 366 if calendar.isleap(year) else 365,
                           "is_partial": False, "archive_representation": "monthly_aggregate"})
            monthly.extend({**item, "is_partial": False, "archive_representation": "monthly_aggregate"}
                           for item in records)
            continue
        evidence.append(meta)
        annual.append({"year": year, "rain_mm": round(sum(d.rain_mm for d in days), 2),
                       "temperature_c": round(sum((d.tmax_c + d.tmin_c) / 2 for d in days) / len(days), 2),
                       "days": len(days), "expected_days": len(days), "is_partial": False})
        for month in range(1, 13):
            subset = [d for d in days if d.d.month == month]
            monthly.append({"month": f"{year}-{month:02d}", "rain_mm": round(sum(d.rain_mm for d in subset), 2),
                           "temperature_c": round(sum((d.tmax_c + d.tmin_c) / 2 for d in subset) / len(subset), 2),
                           "days": len(subset), "expected_days": calendar.monthrange(year, month)[1],
                            "is_partial": False})
    return {"region": region, "start_year": start_year, "end_year": end_year,
            "status": "summary_only" if aggregate_only and not missing else "partial" if missing and annual else "not_downloaded",
            "coverage_fraction": len(annual) / (end_year - start_year + 1), "missing_years": missing,
            "monthly": monthly, "annual": annual, "provenance": evidence,
            "archive_representation": "monthly_aggregate" if aggregate_only else "daily",
            "units": {"rain_mm": "mm total", "temperature_c": "°C; mean of daily (Tmax + Tmin)/2"},
            "note": "NASA POWER point history; not GPM, measured farm yield, or a 30-year climate normal. Missing years are gaps, not zero rainfall. Monthly-aggregate records are chart-only and are not daily crop-model inputs." if aggregate_only else "NASA POWER point history; not GPM, measured farm yield, or a 30-year climate normal. Missing years are gaps, not zero rainfall.",
            "supplemental_history": {"smap": "not_archived", "modis_et": "not_archived", "gpm": "not_archived"}}
