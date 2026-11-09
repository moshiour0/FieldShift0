from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import google_drive
from .diagnostics import safe_error
from .models import Provenance, RemoteDay
from .provenance import now_iso

NEX_GDDP_ASSET = "NASA/GDDP-CMIP6"
HISTORICAL_START = "1995-01-01"
HISTORICAL_END = "2015-01-01"
MIDCENTURY_START = "2041-01-01"
MIDCENTURY_END = "2061-01-01"
BANDS = ("tasmax", "tasmin", "hurs", "pr", "rsds", "sfcWind")
_BAND_LIMITS = {
    "tasmax": (180.0, 360.0),
    "tasmin": (180.0, 360.0),
    "hurs": (0.0, 100.0),
    "pr": (0.0, 0.05),
    "rsds": (0.0, 1000.0),
    "sfcWind": (0.0, 80.0),
}
_INIT_LOCK = threading.Lock()
_EE_INITIALIZED = False
DEFAULT_NEX_MODELS = ("ACCESS-CM2", "MPI-ESM1-2-HR", "MRI-ESM2-0")


class NEXPending(RuntimeError):
    """A bounded request saved partial monthly normals for a later refresh."""


class NEXRetryable(NEXPending):
    """Some monthly requests timed out; completed months can still be resumed."""


def _transient_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    status = getattr(getattr(exc, "resp", None), "status", None)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    message = str(exc).lower()
    return any(marker in message for marker in ("timed out", "timeout", "deadline exceeded", "connection reset", "temporarily unavailable"))


def nex_models() -> tuple[str, ...]:
    models = tuple(dict.fromkeys(x.strip() for x in os.getenv("FIELD_SHIFT_NEX_MODELS", ",".join(DEFAULT_NEX_MODELS)).split(",") if x.strip()))
    if not models or len(models) > 10:
        raise ValueError("FIELD_SHIFT_NEX_MODELS must name between 1 and 10 CMIP6 models.")
    return models


@dataclass(frozen=True)
class NEXDeltaResult:
    monthly: dict[int, dict[str, float | None]] | None
    status: str
    retrieved_at: str | None = None
    age_seconds: int | None = None
    error: str | None = None
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class SMAPPointResult:
    rows: tuple[RemoteDay, ...]
    status: str
    coverage_fraction: float
    retrieval_mode: str
    retry_after_seconds: int | None = None
    archive_cache_status: str = "not_configured"
    archive_object_key: str | None = None
    archive_object_keys: tuple[str, ...] = ()
    archive_sha256: str | None = None
    chunk_count: int = 1


def gee_credentials_configured() -> bool:
    return bool(
        os.getenv("FIELD_SHIFT_GEE_PROJECT", "").strip()
        and os.getenv("FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON", "").strip()
    )


def _gpm_cache_path(cache_dir: Path, lat: float, lon: float, start: date, end: date) -> Path:
    key = f"v4-full-days|NASA/GPM_L3/IMERG_V07|{lat:.5f}|{lon:.5f}|{start.isoformat()}:{end.isoformat()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return cache_dir / f"gpm_imerg_{digest}.json"


def _smap_identity(lat: float, lon: float, start: date, end: date) -> dict[str, Any]:
    return {
        "asset": "NASA/SMAP/SPL4SMGP/008",
        "product": "SPL4SMGP.008",
        "coordinate": {
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "precision_decimal_degrees": 5,
        },
        "requested_dates": {"start": start.isoformat(), "end": end.isoformat()},
        "layers": ["sm_surface", "sm_rootzone"],
        "aggregation": "UTC daily mean of exactly eight 3-hourly intervals",
        "schema_version": 1,
        "qa_processing_version": "fieldshift-smap-l4-gee-v1",
    }


def _smap_key(identity: dict[str, Any]) -> str:
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _smap_cache_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"smap_l4_gee_{key[:24]}.json"


def _decode_smap_rows(rows: Any) -> tuple[RemoteDay, ...]:
    if not isinstance(rows, list):
        raise TypeError("SMAP cache observation list is invalid")
    decoded: list[RemoteDay] = []
    for item in rows:
        if not isinstance(item, dict):
            raise TypeError("SMAP cache observation is not an object")
        provenance_raw = item.get("provenance")
        provenance = Provenance(**provenance_raw) if isinstance(provenance_raw, dict) else None
        decoded.append(RemoteDay(
            d=date.fromisoformat(str(item["d"])),
            smap_surface_m3_m3=float(item["smap_surface_m3_m3"]),
            smap_rootzone_m3_m3=float(item["smap_rootzone_m3_m3"]),
            source=str(item.get("source") or "NASA SMAP SPL4SMGP.008"),
            provenance=provenance,
        ))
    return tuple(decoded)


def _smap_shared_cache_read(
    object_key: str, key: str, identity: dict[str, Any], start: date, end: date,
) -> tuple[tuple[RemoteDay, ...], dict[str, Any], str] | None:
    raw = google_drive.get_object(object_key)
    if raw is None:
        return None
    try:
        envelope = json.loads(raw.decode("utf-8"))
        if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
            return None
        if envelope.get("cache_key") != key or envelope.get("identity") != identity:
            return None
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            return None
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        if digest != envelope.get("payload_sha256"):
            return None
        rows = _decode_smap_rows(payload.get("rows"))
        if any(row.d < start or row.d > end for row in rows):
            return None
        meta = payload.get("meta")
        if not isinstance(meta, dict) or meta.get("retry_after_seconds") is not None:
            return None
        return rows, meta, digest
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _smap_shared_cache_write(
    object_key: str, key: str, identity: dict[str, Any], rows: tuple[RemoteDay, ...],
    meta: dict[str, Any],
) -> str:
    payload = {
        "rows": [
            {
                "d": row.d.isoformat(),
                "smap_surface_m3_m3": row.smap_surface_m3_m3,
                "smap_rootzone_m3_m3": row.smap_rootzone_m3_m3,
                "source": row.source,
                "provenance": asdict(row.provenance) if row.provenance else None,
            }
            for row in rows
        ],
        "meta": meta,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    envelope = {
        "schema_version": 1,
        "cache_key": key,
        "identity": identity,
        "payload_sha256": digest,
        "payload": payload,
    }
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    google_drive.put_object(object_key, raw, sha256=hashlib.sha256(raw).hexdigest())
    readback = google_drive.get_object(object_key)
    if readback is None or readback != raw:
        raise google_drive.GoogleDriveError("SMAP Drive cache read-back did not match the uploaded bytes")
    verified = _smap_shared_cache_read(object_key, key, identity, date.fromisoformat(identity["requested_dates"]["start"]),
                                       date.fromisoformat(identity["requested_dates"]["end"]))
    if verified is None or verified[2] != digest:
        raise google_drive.GoogleDriveError("SMAP Drive cache metadata or payload checksum validation failed")
    return digest


def _smap_result(
    rows: tuple[RemoteDay, ...], expected: int, *, retrieval_mode: str,
    retry_after_seconds: int | None = None, archive_cache_status: str = "not_configured",
    archive_object_key: str | None = None, archive_sha256: str | None = None,
    archive_object_keys: tuple[str, ...] = (), chunk_count: int = 1,
) -> SMAPPointResult:
    coverage = len(rows) / max(1, expected)
    status = "available" if len(rows) == expected else "partial" if rows else "pending" if retry_after_seconds else "unavailable"
    return SMAPPointResult(
        rows=rows, status=status, coverage_fraction=round(min(1.0, coverage), 5),
        retrieval_mode=retrieval_mode, retry_after_seconds=retry_after_seconds,
        archive_cache_status=archive_cache_status, archive_object_key=archive_object_key,
        archive_sha256=archive_sha256,
        archive_object_keys=archive_object_keys or ((archive_object_key,) if archive_object_key else ()),
        chunk_count=chunk_count,
    )


def _smap_daily_point_timeseries_window(
    lat: float, lon: float, start: date, end: date, cache_dir: str | Path,
) -> SMAPPointResult:
    """Fetch point SMAP L4 daily means from the 3-hourly GEE collection.

    A date is accepted only when all eight 3-hourly intervals have valid
    surface and root-zone values at the selected native grid cell. No gap is
    interpolated. A recent trailing gap is returned as pending/partial so the
    durable worker can check again after provider ingestion catches up.
    """
    if not gee_credentials_configured():
        raise ValueError("Google Earth Engine credentials are not configured")
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("invalid latitude/longitude for NASA SMAP")
    if start > end or start < date(2015, 3, 31) or end > date.today():
        raise ValueError("SMAP date window must be within 2015-03-31 and today")
    expected = (end - start).days + 1
    if expected > 366:
        raise ValueError("Internal SMAP point window must not exceed 366 days")

    identity = _smap_identity(lat, lon, start, end)
    cache_key = _smap_key(identity)
    object_key = f"satellite-point-cache/v1/smap-gee/{cache_key}.json"
    if google_drive.configured():
        try:
            shared = _smap_shared_cache_read(object_key, cache_key, identity, start, end)
        except google_drive.GoogleDriveError:
            shared = None
        if shared is not None:
            shared_rows, meta, digest = shared
            return _smap_result(
                shared_rows, expected, retrieval_mode="google_drive_cache",
                archive_cache_status="verified", archive_object_key=object_key, archive_sha256=digest,
            )

    cache_path = _smap_cache_path(Path(cache_dir), cache_key)
    cached, age = _read_cache(cache_path)
    if cached and cached.get("identity") == identity and age is not None:
        cached_meta = cached.get("meta") or {}
        retry_after = cached_meta.get("retry_after_seconds")
        ttl = max(60, int(os.getenv("FIELD_SHIFT_SMAP_GEE_CACHE_TTL_SECONDS", "604800" if retry_after is None else "600")))
        if age <= ttl:
            try:
                cached_rows = _decode_smap_rows(cached.get("rows"))
                return _smap_result(
                    cached_rows, expected, retrieval_mode="local_cache", retry_after_seconds=retry_after,
                    archive_cache_status=str(cached_meta.get("archive_cache_status") or "not_configured"),
                    archive_object_key=cached_meta.get("archive_object_key"),
                    archive_sha256=cached_meta.get("archive_sha256"),
                )
            except (KeyError, TypeError, ValueError):
                pass

    ee = _initialise_ee()
    point = ee.Geometry.Point([lon, lat])
    collection = (
        ee.ImageCollection("NASA/SMAP/SPL4SMGP/008")
        .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
        .select(["sm_surface", "sm_rootzone"])
    )

    def daily_sample(offset):
        day_start = ee.Date(start.isoformat()).advance(offset, "day")
        subset = collection.filterDate(day_start, day_start.advance(1, "day"))
        seed = ee.Image.constant([0, 0]).rename(["sm_surface", "sm_rootzone"]).selfMask()
        safe_subset = subset.merge(ee.ImageCollection.fromImages([seed]))
        daily = safe_subset.mean()
        interval_counts = subset.select(["sm_surface", "sm_rootzone"]).count().rename(["n_surface", "n_rootzone"])
        complete = interval_counts.select("n_surface").eq(8).And(interval_counts.select("n_rootzone").eq(8))
        daily = daily.updateMask(complete).addBands(interval_counts)
        stats = daily.reduceRegion(
            reducer=ee.Reducer.first(), geometry=point, scale=11000, maxPixels=10000,
        )
        return ee.Feature(None, stats).set({"date": day_start.format("YYYY-MM-dd")})

    features = ee.List.sequence(0, expected - 1).map(daily_sample)
    result = ee.FeatureCollection(features).getInfo()
    provenance = Provenance(
        source="NASA SMAP SPL4SMGP.008 via Google Earth Engine",
        source_type="satellite",
        retrieval_date=now_iso(),
        spatial_resolution="~11 km pixel; native ~9 km EASE-Grid 2.0",
        temporal_resolution="3-hourly input aggregated to UTC daily mean; exactly 8 intervals required",
        citation="https://doi.org/10.5067/T5RUATAQREF8",
        confidence=0.88,
    )
    smap_rows: list[RemoteDay] = []
    for feature in result.get("features", []):
        properties = feature.get("properties", {}) if isinstance(feature, dict) else {}
        try:
            observed_day = date.fromisoformat(str(properties["date"]))
            surface_intervals = int(properties.get("n_surface") or 0)
            rootzone_intervals = int(properties.get("n_rootzone") or 0)
            surface = _finite(properties.get("sm_surface"))
            rootzone = _finite(properties.get("sm_rootzone"))
        except (KeyError, TypeError, ValueError):
            continue
        if surface_intervals != 8 or rootzone_intervals != 8 or surface is None or rootzone is None:
            continue
        if not 0.0 <= surface <= 0.9 or not 0.0 <= rootzone <= 0.9:
            continue
        smap_rows.append(RemoteDay(
            d=observed_day,
            smap_surface_m3_m3=surface,
            smap_rootzone_m3_m3=rootzone,
            source=provenance.source,
            provenance=provenance,
        ))

    smap_rows.sort(key=lambda row: row.d)
    present = {row.d for row in smap_rows}
    trailing_missing = end not in present or any(
        date.fromordinal(day.toordinal()) not in present
        for day in (end - timedelta(days=offset) for offset in range(min(6, expected)))
    )
    recent_window = end >= date.today() - timedelta(days=6)
    retry_after = 3600 if trailing_missing and recent_window else None
    result_state = _smap_result(tuple(smap_rows), expected, retrieval_mode="google_earth_engine",
                                retry_after_seconds=retry_after)
    meta = {
        "status": result_state.status,
        "coverage_fraction": result_state.coverage_fraction,
        "retry_after_seconds": result_state.retry_after_seconds,
        "retrieved_at": now_iso(),
    }
    archive_status = "not_configured"
    archive_digest = None
    if result_state.status in {"available", "partial"} and retry_after is None and google_drive.configured():
        try:
            archive_digest = _smap_shared_cache_write(object_key, cache_key, identity, tuple(smap_rows), meta)
            archive_status = "verified"
        except Exception:
            archive_status = "write_failed"
    meta.update(archive_cache_status=archive_status, archive_object_key=object_key if archive_status == "verified" else None,
                archive_sha256=archive_digest)
    _write_cache(cache_path, {
        "identity": identity,
        "rows": [
            {
                "d": row.d.isoformat(),
                "smap_surface_m3_m3": row.smap_surface_m3_m3,
                "smap_rootzone_m3_m3": row.smap_rootzone_m3_m3,
                "source": row.source,
                "provenance": asdict(row.provenance) if row.provenance else None,
            }
            for row in smap_rows
        ],
        "meta": meta,
    })
    return _smap_result(
        tuple(smap_rows), expected, retrieval_mode=result_state.retrieval_mode,
        retry_after_seconds=retry_after, archive_cache_status=archive_status,
        archive_object_key=object_key if archive_status == "verified" else None,
        archive_sha256=archive_digest,
    )


def smap_daily_point_timeseries(
    lat: float, lon: float, start: date, end: date, cache_dir: str | Path,
) -> SMAPPointResult:
    """Read a long SMAP window in bounded, independently cached <=366-day chunks.

    The chunk boundaries depend only on the original request's start date. Each
    completed chunk is persisted and verified independently, so a later retry
    can reuse successful chunks without repeating their Earth Engine queries.
    """
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("invalid latitude/longitude for NASA SMAP")
    if start > end or start < date(2015, 3, 31) or end > date.today():
        raise ValueError("SMAP date window must be within 2015-03-31 and today")
    expected = (end - start).days + 1
    if expected > 30 * 366:
        raise ValueError("SMAP historical point window cannot exceed 30 years")

    chunks: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=365))
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)

    results = [
        _smap_daily_point_timeseries_window(lat, lon, chunk_start, chunk_end, cache_dir)
        for chunk_start, chunk_end in chunks
    ]
    by_date = {row.d: row for result in results for row in result.rows}
    rows = tuple(by_date[key] for key in sorted(by_date))
    retry_values = [result.retry_after_seconds for result in results if result.retry_after_seconds is not None]
    retry_after = max(retry_values, default=None)
    coverage = len(rows) / max(1, expected)
    status = (
        "available" if len(rows) == expected else
        "partial" if rows else
        "pending" if retry_after is not None else
        "unavailable"
    )
    modes = {result.retrieval_mode for result in results}
    retrieval_mode = next(iter(modes)) if len(modes) == 1 else "mixed_chunks"
    chunk_objects = tuple(
        key
        for result in results
        for key in (result.archive_object_keys or ((result.archive_object_key,) if result.archive_object_key else ()))
    )
    archive_states = {result.archive_cache_status for result in results}
    archive_status = (
        "verified" if archive_states == {"verified"} else
        "write_failed" if "write_failed" in archive_states else
        "partial" if "verified" in archive_states else
        "not_configured"
    )
    single_object = chunk_objects[0] if len(chunk_objects) == 1 else None
    single_sha = results[0].archive_sha256 if len(results) == 1 else None
    return SMAPPointResult(
        rows=rows,
        status=status,
        coverage_fraction=round(min(1.0, coverage), 5),
        retrieval_mode=retrieval_mode,
        retry_after_seconds=retry_after,
        archive_cache_status=archive_status,
        archive_object_key=single_object,
        archive_object_keys=chunk_objects,
        archive_sha256=single_sha,
        chunk_count=len(chunks),
    )


def _gpm_date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def gpm_daily_point_timeseries(
    lat: float, lon: float, start: date, end: date, cache_dir: str | Path,
) -> tuple[RemoteDay, ...]:
    """Fetch daily GPM IMERG V07 rainfall at a point through Earth Engine.

    AppEEARS does not currently expose an IMERG product in the observed
    catalog used by FieldShift, while Earth Engine publishes
    NASA/GPM_L3/IMERG_V07 at 30-minute cadence. Each half-hourly
    precipitation value is in mm/hour, so multiplying by 0.5 and summing
    within each UTC day yields a daily precipitation depth in mm.
    """
    if not gee_credentials_configured():
        raise ValueError("Google Earth Engine credentials are not configured")
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("invalid latitude/longitude for NASA GPM IMERG")
    if start > end:
        raise ValueError("NASA GPM start date must be on or before end date")

    cache_path = _gpm_cache_path(Path(cache_dir), lat, lon, start, end)
    cached, age = _read_cache(cache_path)
    ttl = max(60, int(os.getenv("FIELD_SHIFT_GPM_GEE_CACHE_TTL_SECONDS", "21600")))
    if cached and age is not None and age <= ttl:
        rows: list[RemoteDay] = []
        provenance = Provenance(**cached["provenance"]) if cached.get("provenance") else None
        for item in cached.get("rows", []):
            if not isinstance(item, dict):
                continue
            try:
                rows.append(RemoteDay(
                    d=date.fromisoformat(str(item["d"])),
                    gpm_rain_mm=float(item["gpm_rain_mm"]),
                    source=str(item.get("source", "NASA GPM IMERG")),
                    provenance=provenance,
                ))
            except (KeyError, TypeError, ValueError):
                continue
        if rows:
            return tuple(rows)

    ee = _initialise_ee()
    point = ee.Geometry.Point([lon, lat])
    collection = (ee.ImageCollection("NASA/GPM_L3/IMERG_V07")
                  .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat()).select("precipitation"))
    # Build a compact server-side map. An empty day has a masked seed band,
    # so .rename() cannot abort an otherwise valid request after data latency.
    def daily_sample(offset):
        day_start = ee.Date(start.isoformat()).advance(offset, "day")
        subset = collection.filterDate(day_start, day_start.advance(1, "day"))
        seed = ee.Image.constant(0).rename("precipitation").selfMask()
        safe_subset = subset.merge(ee.ImageCollection.fromImages([seed]))
        daily = safe_subset.sum().multiply(0.5).rename("gpm_rain_mm")
        daily = daily.updateMask(safe_subset.count().eq(48))
        stats = daily.reduceRegion(reducer=ee.Reducer.first(), geometry=point, scale=11132, maxPixels=10000)
        return ee.Feature(None, stats).set({"date": day_start.format("YYYY-MM-dd"), "count": subset.size()})

    features = ee.List.sequence(0, (end - start).days).map(daily_sample)
    result = ee.FeatureCollection(features).getInfo()
    provenance = Provenance(
        source="NASA GPM IMERG V07 via Google Earth Engine",
        source_type="satellite",
        retrieval_date=now_iso(),
        spatial_resolution="0.1 degree (~11 km)",
        temporal_resolution="30 min aggregated to daily UTC total",
        citation="https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07",
        confidence=0.85,
    )
    rows = []
    for feature in result.get("features", []):
        props = feature.get("properties", {}) if isinstance(feature, dict) else {}
        raw_day = props.get("date")
        value = props.get("gpm_rain_mm")
        count = props.get("count", 0)
        try:
            day = date.fromisoformat(str(raw_day))
            rain = float(value) if value is not None else float("nan")
            count_i = int(count)
        except (TypeError, ValueError):
            continue
        if count_i != 48 or not math.isfinite(rain) or rain < 0:
            continue
        rows.append(RemoteDay(
            d=day, gpm_rain_mm=max(0.0, rain),
            source=provenance.source, provenance=provenance,
        ))

    if rows:
        _write_cache(cache_path, {
            "rows": [
                {"d": row.d.isoformat(), "gpm_rain_mm": row.gpm_rain_mm, "source": row.source}
                for row in rows
            ],
            "provenance": {
                "source": provenance.source, "source_type": provenance.source_type,
                "retrieval_date": provenance.retrieval_date, "spatial_resolution": provenance.spatial_resolution,
                "temporal_resolution": provenance.temporal_resolution, "citation": provenance.citation,
                "confidence": provenance.confidence,
            },
        })
    return tuple(sorted(rows, key=lambda x: x.d))


def _cache_path(cache_dir: Path, lat: float, lon: float, scenario: str) -> Path:
    key = f"v4|{NEX_GDDP_ASSET}|{lat:.5f}|{lon:.5f}|{scenario}|{HISTORICAL_START}:{HISTORICAL_END}|{MIDCENTURY_START}:{MIDCENTURY_END}|{','.join(nex_models())}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return cache_dir / f"nex_gddp_{digest}.json"


def _read_cache(path: Path) -> tuple[dict[str, Any] | None, int | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        age = max(0, int(time.time() - path.stat().st_mtime))
        return payload, age
    except (OSError, ValueError, TypeError):
        return None, None


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(payload, handle, allow_nan=False)
            temp_path = Path(handle.name)
        os.replace(temp_path, path)
    except OSError:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def monthly_climate_deltas(
    historical: dict[int, dict[str, float]], future: dict[int, dict[str, float]],
) -> dict[int, dict[str, float | None]]:
    """Convert NEX model normals into bounded, unit-aware climate-change signals."""
    output: dict[int, dict[str, float | None]] = {}
    for month in range(1, 13):
        old, new = historical.get(month), future.get(month)
        if old is None or new is None:
            raise ValueError(f"NEX-GDDP-CMIP6 is missing a monthly normal for month {month}")
        missing = [band for band in BANDS if _finite(old.get(band)) is None or _finite(new.get(band)) is None]
        if missing:
            raise ValueError(f"NEX-GDDP-CMIP6 is missing {', '.join(missing)} for month {month}")
        old_rain = float(old["pr"]) * 86400.0
        new_rain = float(new["pr"]) * 86400.0
        old_solar = float(old["rsds"])
        new_solar = float(new["rsds"])
        old_wind = float(old["sfcWind"])
        new_wind = float(new["sfcWind"])
        output[month] = {
            # Temperature differences are unchanged by conversion from Kelvin to Celsius.
            "tasmax_delta_c": float(new["tasmax"]) - float(old["tasmax"]),
            "tasmin_delta_c": float(new["tasmin"]) - float(old["tasmin"]),
            "hurs_delta_pct": float(new["hurs"]) - float(old["hurs"]),
            # Keep dry days dry; do not invent a ratio when the modeled historical normal is zero.
            "precip_ratio": new_rain / old_rain if old_rain > 0.05 else None,
            "historical_precip_mm_day": old_rain,
            "future_precip_mm_day": new_rain,
            "solar_ratio": new_solar / old_solar if old_solar > 0.0 else None,
            "wind_ratio": new_wind / old_wind if old_wind > 0.0 else None,
        }
    return output


def apply_monthly_deltas(weather: tuple, monthly: dict[int, dict[str, float | None]]) -> tuple:
    """Apply NEX monthly signals to a dated daily analogue without changing its dates."""
    adjusted = []
    for day in weather:
        delta = monthly.get(day.d.month)
        if not delta:
            raise ValueError(f"NEX-GDDP-CMIP6 has no climate signal for month {day.d.month}")
        rain_ratio = delta.get("precip_ratio")
        solar_ratio = delta.get("solar_ratio")
        wind_ratio = delta.get("wind_ratio")
        adjusted.append(type(day)(
            d=day.d,
            tmax_c=day.tmax_c + float(delta["tasmax_delta_c"] or 0.0),
            tmin_c=day.tmin_c + float(delta["tasmin_delta_c"] or 0.0),
            rh_mean_pct=max(0.0, min(100.0, day.rh_mean_pct + float(delta["hurs_delta_pct"] or 0.0))),
            wind_2m_ms=max(0.0, day.wind_2m_ms * float(wind_ratio if wind_ratio is not None else 1.0)),
            solar_rad_mj_m2_day=max(0.0, day.solar_rad_mj_m2_day * float(solar_ratio if solar_ratio is not None else 1.0)),
            rain_mm=max(0.0, day.rain_mm * float(rain_ratio if rain_ratio is not None else 1.0)),
            source=f"NASA POWER daily analogue + NASA NEX-GDDP-CMIP6 {day.d.month:02d} climate signal",
            provenance=day.provenance,
        ))
    return tuple(adjusted)


def _initialise_ee():
    global _EE_INITIALIZED
    import ee
    if _EE_INITIALIZED:
        return ee
    with _INIT_LOCK:
        if not _EE_INITIALIZED:
            from google.oauth2.service_account import Credentials

            raw = os.environ["FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON"]
            info = json.loads(raw)
            if not isinstance(info, dict) or info.get("type") != "service_account":
                raise ValueError("FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON must be a service-account JSON object")
            credentials = Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/earthengine", "https://www.googleapis.com/auth/cloud-platform"],
            )
            ee.Initialize(credentials, project=os.environ["FIELD_SHIFT_GEE_PROJECT"].strip())
            ee.data.setDeadline(max(5000, min(60000, int(os.getenv("FIELD_SHIFT_GEE_REQUEST_TIMEOUT_SECONDS", "45")) * 1000)))
            ee.data.setMaxRetries(0)
            _EE_INITIALIZED = True
    return ee


def _fetch_normal_month(ee, lat: float, lon: float, period: str, scenario: str, month: int) -> dict[str, float]:
    start, end = (HISTORICAL_START, HISTORICAL_END) if period == "historical" else (MIDCENTURY_START, MIDCENTURY_END)
    collection = (ee.ImageCollection(NEX_GDDP_ASSET).filterDate(start, end)
                  .filter(ee.Filter.eq("scenario", "historical" if period == "historical" else scenario))
                  .filter(ee.Filter.calendarRange(month, month, "month")))
    # Only reduce selected bands. A masked placeholder handles models with a
    # missing band without relying on a non-guaranteed system:band_names property.
    seed = ee.Image.constant([0] * len(BANDS)).rename(list(BANDS)).selfMask()
    lower = ee.Image.constant([_BAND_LIMITS[b][0] for b in BANDS]).rename(list(BANDS))
    upper = ee.Image.constant([_BAND_LIMITS[b][1] for b in BANDS]).rename(list(BANDS))

    def mask(image):
        values = seed.addBands(image, overwrite=True).select(list(BANDS))
        return values.updateMask(values.gte(lower).And(values.lte(upper)))

    # Equal weighting by model, not by number of images; the ensemble is
    # intentionally small for interactive requests and disclosed in provenance.
    models = []
    for model in nex_models():
        subset = collection.filter(ee.Filter.eq("model", model)).map(mask)
        models.append(subset.merge(ee.ImageCollection.fromImages([seed])).mean())
    ensemble = ee.ImageCollection.fromImages(models)
    image = ensemble.mean().updateMask(ensemble.count().eq(len(models)))
    stats = image.reduceRegion(reducer=ee.Reducer.first(), geometry=ee.Geometry.Point([lon, lat]), scale=27830, maxPixels=10000).getInfo()
    values = {band: _finite(stats.get(band)) for band in BANDS}
    if any(value is None for value in values.values()):
        raise ValueError(f"NEX {period} month {month} has missing usable bands in the configured models; check FIELD_SHIFT_NEX_MODELS.")
    return {band: float(value) for band, value in values.items() if value is not None}


def _fetch_monthly_normals(lat: float, lon: float, scenario: str, cache_dir: str | Path) -> dict[str, dict[int, dict[str, float]]]:
    ee = _initialise_ee()
    normals: dict[str, dict[int, dict[str, float]]] = {"historical": {}, "future": {}}
    todo = []
    ttl = max(60, int(os.getenv("FIELD_SHIFT_GEE_CACHE_TTL_SECONDS", "604800")))
    for period, period_values in normals.items():
        # Historical normals are reusable between both SSP scenarios.
        key = _cache_path(Path(cache_dir), lat, lon, "historical" if period == "historical" else scenario).stem
        for month in range(1, 13):
            path = Path(cache_dir) / f"{key}_{period}_{month:02d}.json"
            cached, age = _read_cache(path)
            values = cached.get("normal", {}) if cached else {}
            if age is not None and age <= ttl and all(_finite(values.get(b)) is not None for b in BANDS):
                period_values[month] = values
            else:
                todo.append((period, month, path))
    deadline = time.monotonic() + max(5, min(80, int(os.getenv("FIELD_SHIFT_NEX_BUDGET_SECONDS", "40"))))

    def fetch(item):
        period, month, path = item
        if time.monotonic() >= deadline:
            return item, None
        values = _fetch_normal_month(ee, lat, lon, period, scenario, month)
        _write_cache(path, {"normal": values, "retrieved_at": now_iso()})
        return item, values

    errors = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fetch, item) for item in todo]
        for future in as_completed(futures):
            try:
                (period, month, _), values = future.result()
                if values is not None:
                    normals[period][month] = values
            except Exception as exc:
                errors.append(exc)
    count = sum(len(v) for v in normals.values())
    if count != 24:
        permanent_errors = [error for error in errors if not _transient_error(error)]
        if permanent_errors:
            raise permanent_errors[0]
        if errors:
            raise NEXRetryable(f"Computed {count}/24 monthly normals; a temporary Earth Engine request failed ({safe_error(errors[0])}). Refresh resumes missing months; completed months are cached on this server instance.")
        raise NEXPending(f"Computed {count}/24 monthly normals; refresh to resume. Partial results are cached on this server instance.")
    return normals


def nex_gddp_monthly_deltas(
    lat: float, lon: float, scenario: str, cache_dir: str | Path,
) -> NEXDeltaResult:
    if scenario not in {"ssp245", "ssp585"}:
        raise ValueError("NEX-GDDP-CMIP6 scenario must be 'ssp245' or 'ssp585'")
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("invalid latitude/longitude for NASA NEX-GDDP-CMIP6")
    cache_path = _cache_path(Path(cache_dir), lat, lon, scenario)
    cached, age = _read_cache(cache_path)
    ttl = max(60, int(os.getenv("FIELD_SHIFT_GEE_CACHE_TTL_SECONDS", "604800")))
    if cached and age is not None and age <= ttl:
        try:
            monthly = {int(month): values for month, values in cached["monthly"].items()}
            if len(monthly) == 12:
                return NEXDeltaResult(monthly, "cache", cached.get("retrieved_at"), age)
        except (KeyError, TypeError, ValueError):
            pass
    if not gee_credentials_configured():
        if cached and age is not None:
            try:
                monthly = {int(month): values for month, values in cached["monthly"].items()}
                if len(monthly) == 12:
                    return NEXDeltaResult(monthly, "stale-cache", cached.get("retrieved_at"), age)
            except (KeyError, TypeError, ValueError):
                pass
        return NEXDeltaResult(None, "not_configured", error="Google Earth Engine service credentials are not configured.")
    try:
        normals = _fetch_monthly_normals(lat, lon, scenario, cache_dir)
        monthly = monthly_climate_deltas(normals["historical"], normals["future"])
        retrieved_at = datetime.now(UTC).isoformat()
        _write_cache(cache_path, {"monthly": monthly, "retrieved_at": retrieved_at})
        return NEXDeltaResult(monthly, "live", retrieved_at)
    except NEXRetryable as exc:
        return NEXDeltaResult(None, "retrying", error=str(exc), retry_after_seconds=60)
    except NEXPending as exc:
        return NEXDeltaResult(None, "pending", error=str(exc), retry_after_seconds=30)
    except Exception as exc:
        if cached and age is not None:
            try:
                monthly = {int(month): values for month, values in cached["monthly"].items()}
                if len(monthly) == 12:
                    return NEXDeltaResult(monthly, "stale-cache", cached.get("retrieved_at"), age, type(exc).__name__)
            except (KeyError, TypeError, ValueError):
                pass
        if _transient_error(exc):
            return NEXDeltaResult(None, "retrying", error=safe_error(exc), retry_after_seconds=60)
        # Redact credentials/account details from the provider response.
        return NEXDeltaResult(None, "unavailable", error=safe_error(exc))
