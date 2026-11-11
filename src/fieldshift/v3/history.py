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


def _decode_year_payload(
    region_id: str,
    year: int,
    raw: bytes,
) -> tuple[tuple[WeatherDay, ...], dict]:
    """Decode and validate an exact archive object returned by a storage provider."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("History archive object is not valid JSON") from exc
    region = region_by_id(region_id)
    if (payload.get("region") != region or payload.get("year") != year
            or payload.get("schema_version") != 1 or _digest(payload["days"]) != payload.get("sha256")):
        raise ValueError("Archive identity or checksum mismatch")
    days = tuple(WeatherDay(**{**row, "d": date.fromisoformat(row["d"]),
                              "provenance": Provenance(**row["provenance"])}) for row in payload["days"])
    validate_days(days, date(year, 1, 1), date(year, 12, 31))
    return days, {k: v for k, v in payload.items() if k != "days"}


def read_year_with_mode(region_id: str, year: int) -> tuple[tuple[WeatherDay, ...], dict, str]:
    """Read one fully validated annual archive and identify the storage path."""
    path = _path(region_id, year)
    if google_drive.configured():
        try:
            archived = google_drive.get_object(f"power-history/{region_id}/{year}.json")
        except google_drive.GoogleDriveError as exc:
            raise RuntimeError("Google Drive history archive unavailable") from exc
        if archived is not None:
            days, metadata = _decode_year_payload(region_id, year, archived)
            return days, metadata, "google_drive_archive"
    if path.exists():
        days, metadata = _decode_year_payload(region_id, year, path.read_bytes())
        return days, metadata, "local_archive"
    raise FileNotFoundError(str(path))


def read_year(region_id: str, year: int) -> tuple[tuple[WeatherDay, ...], dict]:
    days, metadata, _ = read_year_with_mode(region_id, year)
    return days, metadata


def prefetch_year(region_id: str, year: int, *, refresh: bool = False) -> dict:
    """CLI-only mutation with local and remote byte-for-byte verification."""
    region = region_by_id(region_id)
    path = _path(region_id, year)
    if date(year, 12, 31) >= date.today():
        raise ValueError("Only completed calendar years can be archived")
    archive_key = f"power-history/{region_id}/{year}.json"
    if not refresh:
        try:
            if google_drive.configured():
                remote_payload = google_drive.get_object(archive_key)
                if remote_payload is not None:
                    remote_days, meta = _decode_year_payload(region_id, year, remote_payload)
                    return {
                        **meta,
                        "daily_records": len(remote_days),
                        "retrieval_mode": "google_drive",
                        "drive_readback_verified": True,
                    }
                if path.exists():
                    # Publish a validated local archive, then fetch the object
                    # directly from Drive. Do not let read_year's local fallback
                    # turn a missing remote object into a false success.
                    local_days, local_meta = read_year(region_id, year)
                    local_bytes = path.read_bytes()
                    google_drive.put_object(
                        archive_key,
                        local_bytes,
                        sha256=hashlib.sha256(local_bytes).hexdigest(),
                    )
                    remote_bytes = google_drive.get_object(archive_key)
                    if remote_bytes is None or remote_bytes != local_bytes:
                        raise NasaDataError("Migrated Google Drive archive remote read-back verification failed")
                    remote_days, remote_meta = _decode_year_payload(region_id, year, remote_bytes)
                    if remote_meta["sha256"] != local_meta["sha256"] or len(remote_days) != len(local_days):
                        raise NasaDataError("Migrated Google Drive archive checksum verification failed")
                    return {
                        **remote_meta,
                        "daily_records": len(remote_days),
                        "retrieval_mode": "local_archive_published",
                        "drive_readback_verified": True,
                    }
            else:
                local_days, meta = read_year(region_id, year)
                return {
                    **meta,
                    "daily_records": len(local_days),
                    "retrieval_mode": "local_archive",
                    "drive_readback_verified": False,
                }
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
        local_bytes = path.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise NasaDataError("Local archive write verification failed") from exc
    if local_payload.get("sha256") != payload["sha256"] or _digest(local_payload.get("days", [])) != payload["sha256"]:
        raise NasaDataError("Local archive checksum verification failed")
    if google_drive.configured():
        try:
            google_drive.put_object(
                archive_key,
                local_bytes,
                sha256=hashlib.sha256(local_bytes).hexdigest(),
            )
            remote_bytes = google_drive.get_object(archive_key)
            if remote_bytes is None or remote_bytes != local_bytes:
                raise NasaDataError("Google Drive archive remote read-back verification failed")
            remote_days, verified = _decode_year_payload(region_id, year, remote_bytes)
        except Exception as exc:
            if isinstance(exc, NasaDataError):
                raise
            raise RuntimeError("Completed-year Google Drive archive could not be published and verified") from exc
        if verified["sha256"] != payload["sha256"] or len(remote_days) != len(days):
            raise NasaDataError("Google Drive archive checksum verification failed")
        return {
            **verified,
            "daily_records": len(remote_days),
            "retrieval_mode": "google_drive_published",
            "drive_readback_verified": True,
        }
    _, verified = read_year(region_id, year)
    if verified["sha256"] != payload["sha256"]:
        raise NasaDataError("Archive write verification failed")
    return {
        **verified,
        "daily_records": len(days),
        "retrieval_mode": "local_archive",
        "drive_readback_verified": False,
    }


def archived_weather_details(
    lat: float, lon: float, start: date, end: date,
) -> tuple[tuple[WeatherDay, ...], tuple[dict[str, Any], ...], str] | None:
    """Return verified archive rows only for an exact reference coordinate and full date coverage.

    Each annual object must pass its identity, embedded SHA-256, physical-bound and
    daily-continuity checks. A missing/corrupt year makes this helper return None;
    callers must then use their normal live-source path rather than fill the gap.
    """
    if end < start:
        return None
    region = next((r for r in REGIONS if abs(r["lat"] - lat) < 0.000001 and abs(r["lon"] - lon) < 0.000001), None)
    if region is None:
        return None

    out: list[WeatherDay] = []
    metadata: list[dict[str, Any]] = []
    storage_modes: set[str] = set()
    try:
        for year in range(start.year, end.year + 1):
            days, year_meta, storage_mode = read_year_with_mode(region["id"], year)
            storage_modes.add(storage_mode)
            metadata.append({
                "year": year,
                "sha256": year_meta["sha256"],
                "archived_at": year_meta.get("archived_at"),
            })
            out.extend(
                WeatherDay(
                    **{
                        **asdict(day),
                        "d": day.d,
                        "provenance": day.provenance,
                        "source": f"NASA POWER (archive); original: {day.source}",
                    }
                )
                for day in days if start <= day.d <= end
            )
        result = tuple(out)
        validate_days(result, start, end)
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        return None

    retrieval_mode = (
        "google_drive_archive" if storage_modes == {"google_drive_archive"}
        else "local_archive" if storage_modes == {"local_archive"}
        else "mixed_archive"
    )
    return result, tuple(metadata), retrieval_mode


def archived_weather(lat: float, lon: float, start: date, end: date) -> tuple[WeatherDay, ...] | None:
    """Compatibility wrapper for exact-coordinate, fully covered annual archive rows."""
    details = archived_weather_details(lat, lon, start, end)
    return details[0] if details is not None else None


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
