"""NASA AppEEARS point-sampling connector for satellite time-series evidence.

The connector is opt-in because NASA Earthdata credentials are required. It
discovers current AppEEARS product/layer versions at runtime so a retired
collection does not silently become a source of fabricated data.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, TypedDict

from . import google_drive
from .diagnostics import safe_error
from .models import Provenance, RemoteDay
from .provenance import now_iso

APPEEARS_API = "https://appeears.earthdatacloud.nasa.gov/api/"
_TASK_LOCKS_GUARD = threading.Lock()
_TASK_LOCKS: dict[str, threading.Lock] = {}
_TOKEN_GUARD = threading.Lock()
_TOKEN_VALUE: str | None = None
_TOKEN_EXPIRATION_TS: float = 0.0
_TOKEN_SOURCE: str | None = None
_REQUEST_GUARD = threading.Lock()
_NEXT_REQUEST_AT = 0.0
_MIN_REQUEST_INTERVAL = 1.0


class AppEEARSDataError(RuntimeError):
    """Raised when AppEEARS cannot provide an authenticated point sample."""

    def __init__(self, message: str, *, stage: str | None = None, http_status: int | None = None):
        super().__init__(message)
        self.stage = stage
        self.http_status = http_status


class AppEEARSRetryableError(AppEEARSDataError):
    """A temporary provider failure; never retry a task POST blindly."""

    def __init__(self, message: str, *, retry_after_seconds: int = 60, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after_seconds = retry_after_seconds


def _request_stage(path: str, method: str) -> str:
    parts = path.split("?", 1)[0].strip("/").split("/")
    if parts[0] == "task":
        return "task-submission" if method == "POST" else "task-status" if len(parts) > 1 else "task-list"
    if parts[0] == "product":
        return "layer-metadata" if len(parts) > 1 else "product-catalog"
    if parts[0] == "bundle":
        return "file-download" if len(parts) > 2 else "bundle-list"
    return "login" if parts[0] == "login" else "provider-request"


def _retry_delay(header: str | None, default: int) -> int:
    """Retry-After is either delay-seconds or an HTTP date."""
    try:
        if header and header.strip().isdigit():
            return max(1, int(header))
        if header:
            retry_at = parsedate_to_datetime(header)
            return max(1, math.ceil(retry_at.timestamp() - time.time()))
    except (ValueError, TypeError, OverflowError):
        pass
    return default


def _cooldown_path() -> Path:
    account = os.getenv("FIELD_SHIFT_APPEEARS_USER", "").strip() or os.getenv("FIELD_SHIFT_APPEEARS_TOKEN", "")
    key = hashlib.sha256(account.encode()).hexdigest()[:24]
    root = Path(os.getenv("FIELD_SHIFT_CACHE_DIR") or str(Path(tempfile.gettempdir()) / "fieldshift-appeears"))
    return root / f"appeears_cooldown_{key}.json"


def _check_cooldown() -> None:
    try:
        saved = json.loads(_cooldown_path().read_text(encoding="utf-8"))
        remaining = math.ceil(float(saved["until"]) - time.time())
    except (OSError, ValueError, TypeError, KeyError):
        return
    if remaining > 0:
        raise AppEEARSRetryableError(
            str(saved["message"]), stage=saved.get("stage"), http_status=saved.get("http_status"),
            retry_after_seconds=remaining,
        )


def _remember_cooldown(exc: AppEEARSRetryableError) -> None:
    _write_json(_cooldown_path(), {
        "until": time.time() + exc.retry_after_seconds, "stage": exc.stage,
        "http_status": exc.http_status, "message": safe_error(exc),
    })


def _open_bytes(request: urllib.request.Request, stage: str, timeout: int) -> bytes:
    """Pace all calls, including downloads, and honor the provider cooldown.

    Cooldowns survive requests on the same server filesystem. Separate cold
    serverless instances cannot share this file; the UI also honors Retry-After.
    """
    global _NEXT_REQUEST_AT
    with _REQUEST_GUARD:
        _check_cooldown()
        delay = _NEXT_REQUEST_AT - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise  # Authentication is refreshed outside the request lock.
            detail = exc.read(512).decode("utf-8", "replace")
            message = f"AppEEARS {stage} returned HTTP {exc.code}: {detail[:300]}"
            if exc.code in {408, 429} or 500 <= exc.code < 600:
                retry = AppEEARSRetryableError(
                    message, stage=stage, http_status=exc.code,
                    retry_after_seconds=_retry_delay(exc.headers.get("Retry-After"), 60 if exc.code == 429 else 30),
                )
                _remember_cooldown(retry)
                raise retry from exc
            raise AppEEARSDataError(message, stage=stage, http_status=exc.code) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            retry = AppEEARSRetryableError(f"AppEEARS {stage} connection failed: {safe_error(exc)}", stage=stage, retry_after_seconds=30)
            _remember_cooldown(retry)
            raise retry from exc
        finally:
            _NEXT_REQUEST_AT = time.monotonic() + _MIN_REQUEST_INTERVAL


@dataclass(frozen=True)
class LayerSelection:
    source_key: str
    source_name: str
    product: str
    layer: str
    target: str
    resolution: str | None
    temporal_resolution: str | None
    available_start: date | None = None
    available_end: date | None = None


@dataclass(frozen=True)
class AppEEARSResult:
    remote: tuple[RemoteDay, ...]
    datasets: tuple[dict[str, Any], ...]


class SourceDefinition(TypedDict):
    key: str
    name: str
    product_ids: tuple[str, ...]
    layers: dict[str, tuple[str, ...]]
    source_type: str
    citation: str


SOURCE_DEFINITIONS: tuple[SourceDefinition, ...] = (
    {
        "key": "smap",
        "name": "NASA SMAP",
        "product_ids": ("SPL4SMGP.008", "SPL3SMP_E.006", "SPL3SMP.009"),
        "layers": {
            "smap_surface_m3_m3": ("sm_surface", "surface_soil_moisture", "soil_moisture", "soil_moisture_am"),
            "smap_rootzone_m3_m3": ("sm_rootzone", "rootzone_soil_moisture"),
            "smap_qa": ("retrieval_qual_flag", "retrieval_qual_flag_am"),
        },
        "source_type": "satellite",
        "citation": "https://nsidc.org/data/spl4smgp/versions/8",
    },
    {
        "key": "modis_et",
        "name": "NASA MODIS MOD16",
        "product_ids": ("MOD16A2GF.061", "MOD16A2.061"),
        "layers": {
            "modis_et_mm": ("ET_500m", "ET"),
            "modis_et_qc": ("ET_QC_500m",),
        },
        "source_type": "satellite",
        "citation": "https://doi.org/10.5067/MODIS/MOD16A2GF.061",
    },
    {
        "key": "hls_vi",
        "name": "NASA HLS",
        "product_ids": (),
        "layers": {
            "ndvi": ("NDVI",),
            "evi": ("EVI",),
            "ndmi": ("NDMI",),
            "hls_qa": ("QA", "Fmask"),
        },
        "source_type": "satellite",
        "citation": "https://doi.org/10.5067/HLS/HLSL30_VI.002",
    },
)


def credentials_configured() -> bool:
    return bool((os.getenv("FIELD_SHIFT_APPEEARS_TOKEN", "").strip()) or (os.getenv("FIELD_SHIFT_APPEEARS_USER", "").strip() and os.getenv("FIELD_SHIFT_APPEEARS_PASSWORD", "")))


def _clear_token() -> None:
    global _TOKEN_VALUE, _TOKEN_EXPIRATION_TS, _TOKEN_SOURCE
    with _TOKEN_GUARD:
        _TOKEN_VALUE = None
        _TOKEN_EXPIRATION_TS = 0.0
        _TOKEN_SOURCE = None


def _login_token(*, timeout: int = 25, force: bool = False) -> str:
    """Acquire/reuse the official AppEEARS Bearer token.

    The API token is valid for roughly 48 hours; this in-process cache avoids
    logging in on every analysis request and refreshes only when needed.
    """
    global _TOKEN_VALUE, _TOKEN_EXPIRATION_TS, _TOKEN_SOURCE
    supplied = os.getenv("FIELD_SHIFT_APPEEARS_TOKEN", "").strip()
    user = os.getenv("FIELD_SHIFT_APPEEARS_USER", "").strip()
    password = os.getenv("FIELD_SHIFT_APPEEARS_PASSWORD", "")
    if not supplied and not (user and password):
        raise AppEEARSDataError("AppEEARS credentials are not configured")
    source = "env-token" if supplied else f"basic:{hashlib.sha256(user.encode()).hexdigest()[:12]}"
    with _TOKEN_GUARD:
        now = time.time()
        if not force and _TOKEN_VALUE and _TOKEN_SOURCE == source and _TOKEN_EXPIRATION_TS > now + 120:
            return _TOKEN_VALUE
        if supplied and not force:
            _TOKEN_VALUE = supplied
            # User supplied tokens do not expose an expiration here; force a
            # refresh on the first 403 if username/password are available.
            _TOKEN_EXPIRATION_TS = now + 6 * 3600
            _TOKEN_SOURCE = source
            return supplied
        if supplied and not (user and password):
            raise AppEEARSDataError("Configured AppEEARS token is unavailable; provide Earthdata username/password for automatic refresh.")
        token_response = _safe_json_request(
            "login", method="POST", auth=(user, password), timeout=timeout, _allow_token_refresh=False,
        )
        token = token_response.get("token") if isinstance(token_response, dict) else None
        if not token:
            raise AppEEARSDataError("AppEEARS login did not return a bearer token")
        expiration = token_response.get("expiration") if isinstance(token_response, dict) else None
        try:
            expiry_ts = datetime.fromisoformat(str(expiration)).timestamp() if expiration else now + 44 * 3600
        except (TypeError, ValueError, OverflowError):
            expiry_ts = now + 44 * 3600
        _TOKEN_VALUE = str(token)
        _TOKEN_EXPIRATION_TS = expiry_ts
        _TOKEN_SOURCE = source
        return _TOKEN_VALUE


def _request_bytes(
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    auth: tuple[str, str] | None = None,
    timeout: int = 25,
    _allow_token_refresh: bool = True,
) -> bytes:
    headers = {"User-Agent": "FieldShift/3.2 NASA AppEEARS connector"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if auth:
        basic = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {basic}"
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
        body = b"grant_type=client_credentials"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{APPEEARS_API}{path.lstrip('/')}", data=body, headers=headers, method=method)
    stage = _request_stage(path, method)
    try:
        return _open_bytes(request, stage, timeout)
    except urllib.error.HTTPError as exc:
        # NASA AppEEARS documents 403 as the signal to reacquire an expired
        # Bearer token. Refresh at most once for a secure request.
        if exc.code in {401, 403} and token and _allow_token_refresh:
            _clear_token()
            fresh = _login_token(timeout=timeout, force=True)
            return _request_bytes(
                path, method=method, token=fresh, payload=payload, auth=None, timeout=timeout, _allow_token_refresh=False,
            )
        detail = exc.read(512).decode("utf-8", "replace")
        raise AppEEARSDataError(f"AppEEARS {stage} returned HTTP {exc.code}: {detail[:300]}", stage=stage, http_status=exc.code) from exc
    except AppEEARSDataError:
        raise
    except Exception as exc:
        raise AppEEARSDataError(f"AppEEARS {stage} request failed: {safe_error(exc)}", stage=stage) from exc


def _safe_json_request(path: str, **kwargs) -> Any:
    raw = _request_bytes(path, **kwargs)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        stage = _request_stage(path, kwargs.get("method", "GET"))
        raise AppEEARSDataError(f"AppEEARS {stage} returned an invalid JSON response", stage=stage) from exc


def _download(path: str, token: str, timeout: int = 40) -> bytes:
    return _request_bytes(path, token=token, timeout=timeout)


def _metadata_request(path: str, token: str, timeout: int, cache_dir: Path | None = None) -> Any:
    """Catalog/layers change slowly; don't re-fetch them on every status poll."""
    cache_path = cache_dir / f"appeears_metadata_{hashlib.sha256(path.encode()).hexdigest()[:24]}.json" if cache_dir else None
    if cache_path:
        try:
            if time.time() - cache_path.stat().st_mtime < 3600:
                return json.loads(cache_path.read_text(encoding="utf-8"))["value"]
        except (OSError, ValueError, TypeError, KeyError):
            pass
    value = _safe_json_request(path, token=token, timeout=timeout)
    if cache_path and isinstance(value, (list, dict)):
        _write_json(cache_path, {"value": value})
    return value


def _product_matches(definition: SourceDefinition, product: dict[str, Any]) -> bool:
    product_id = str(product.get("ProductAndVersion", ""))
    if not product.get("Available", True) or product.get("Deleted", False):
        return False
    if product_id in definition["product_ids"]:
        return True
    lower_id = product_id.lower()
    description = str(product.get("Description", "")).lower()
    product_name = str(product.get("Product", "")).lower()
    if definition["key"] == "hls_vi":
        return "hls" in lower_id and ("_vi" in lower_id or "vegetation indices" in description)
    if definition["key"] == "gpm":
        return ("gpm" in lower_id or "imerg" in lower_id or "imerg" in product_name) and (
            "df" in lower_id or "daily" in description.lower()
        )
    return False


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _first_layer(layers: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    by_norm = {_norm(name): name for name in layers}
    # AppEEARS may namespace a layer, e.g.
    # Geophysical_Data_sm_surface, while the semantic alias is sm_surface.
    # Match exact normalized names first, then namespace-safe suffix matches.
    for alias in aliases:
        alias_norm = _norm(alias)
        exact = by_norm.get(alias_norm)
        if exact:
            return exact
        for layer_norm, original in by_norm.items():
            if layer_norm.endswith(alias_norm):
                return original
    return None


def discover_layers(
    token: str, timeout: int = 25, *, source_key: str | None = None,
    start: date | None = None, end: date | None = None, products=None,
    cache_dir: Path | None = None,
) -> tuple[LayerSelection, ...]:
    if products is None:
        products = _metadata_request("product", token, timeout, cache_dir)
    if not isinstance(products, list):
        raise AppEEARSDataError("AppEEARS product catalog has an unexpected format")
    selected: list[LayerSelection] = []
    for definition in SOURCE_DEFINITIONS:
        if source_key and definition["key"] != source_key:
            continue
        candidates = [p for p in products if isinstance(p, dict) and _product_matches(definition, p)]
        priorities = {pid: i for i, pid in enumerate(definition["product_ids"])}

        def overlap(product):
            first = _date_value(str(product.get("TemporalExtentStart", "")))
            last = _date_value(str(product.get("TemporalExtentEnd", "")))
            lo, hi = max(start or date.min, first or date.min), min(end or date.max, last or date.max)
            return max(0, (hi - lo).days + 1)

        # Prefer coverage of the requested period, then the supported product order.
        candidates.sort(key=lambda p: (-overlap(p), priorities.get(str(p.get("ProductAndVersion", "")), 99)))
        errors = []
        for product in candidates:
            if not overlap(product):
                continue
            product_id = str(product.get("ProductAndVersion", ""))
            try:
                layer_map = _metadata_request(f"product/{urllib.parse.quote(product_id, safe='.')}", token, timeout, cache_dir)
            except AppEEARSRetryableError:
                raise  # Trying more products during a provider cooldown causes more 429s.
            except AppEEARSDataError as exc:
                errors.append(safe_error(exc))
                continue
            if not isinstance(layer_map, dict):
                continue
            layer_map = {k: v for k, v in layer_map.items() if not isinstance(v, dict) or v.get("Available", True)}
            found = []
            for target, aliases in definition["layers"].items():
                layer_name = _first_layer(layer_map, aliases)
                if layer_name:
                    found.append(LayerSelection(
                        definition["key"], definition["name"], product_id, layer_name, target,
                        product.get("Resolution"), product.get("TemporalGranularity"),
                        _date_value(str(product.get("TemporalExtentStart", ""))),
                        _date_value(str(product.get("TemporalExtentEnd", ""))),
                    ))
            targets = {x.target for x in found}
            if definition["key"] == "smap":
                moisture = bool(targets & {"smap_surface_m3_m3", "smap_rootzone_m3_m3"})
                valid = moisture and (product_id.startswith("SPL4") or "smap_qa" in targets)
            elif definition["key"] == "modis_et":
                valid = {"modis_et_mm", "modis_et_qc"}.issubset(targets)
            else:
                valid = {"ndvi", "evi"}.issubset(targets)
            if valid:
                selected.extend(found)
                break
        else:
            if errors:
                raise AppEEARSDataError("Product discovery failed: " + " | ".join(errors))
    return tuple(selected)


def _cache_key(lat: float, lon: float, start: date, end: date) -> str:
    raw = f"{lat:.5f}|{lon:.5f}|{start.isoformat()}|{end.isoformat()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _task_name(cache_key: str) -> str:
    """Keep the legacy stable name so already queued AppEEARS jobs are reused."""
    return f"fieldshift-{cache_key}"


def _task_is_reusable(task: dict[str, Any]) -> bool:
    """Reuse active tasks and unexpired bundles; avoid resubmitting failed jobs forever."""
    status = str(task.get("status", "")).lower()
    if status in {"pending", "processing"}:
        return True
    if status in {"error", "failed", "cancelled"}:
        if os.getenv("FIELD_SHIFT_APPEEARS_RETRY_FAILED", "").lower() in {"1", "true", "yes"}:
            return False
        # Reuse a recent failure briefly to prevent retry storms, not forever.
        try:
            failed_at = datetime.fromisoformat(str(task.get("updated") or task.get("created")))
            if failed_at.tzinfo is None:
                failed_at = failed_at.replace(tzinfo=UTC)
            return (datetime.now(UTC) - failed_at).total_seconds() < 600
        except (TypeError, ValueError):
            return False
    expires_on = task.get("expires_on")
    if expires_on:
        try:
            expiry = datetime.fromisoformat(str(expires_on))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            return expiry > datetime.now(UTC)
        except ValueError:
            return False
    created = task.get("created")
    if created:
        try:
            created_at = datetime.fromisoformat(str(created))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            return (datetime.now(UTC) - created_at).total_seconds() <= 30 * 86400
        except ValueError:
            return False
    return status == "done"


def _find_recent_task(
    token: str, task_name: str, selections: tuple[LayerSelection, ...], *, timeout: int,
    task_index: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Find this AppEEARS request in the account task list after serverless cache loss.

    Vercel function files are not durable across instances. The AppEEARS task
    list is the authoritative fallback that prevents each analysis from creating
    another queued job and notification for the same field request.
    """
    # Use the documented unfiltered GET /task, then match locally. The older
    # filtered query is unnecessary; omit it for endpoint compatibility.
    # Share the response across sources instead of listing this account 3 times.
    index = task_index if task_index is not None else {}
    if "tasks" not in index:
        tasks = _safe_json_request("task", token=token, timeout=timeout)
        if not isinstance(tasks, list):
            raise AppEEARSDataError("AppEEARS task list returned an unexpected format", stage="task-list")
        index["tasks"] = sorted((t for t in tasks if isinstance(t, dict)), key=lambda t: str(t.get("created", "")), reverse=True)
    limit = max(1, min(200, int(os.getenv("FIELD_SHIFT_APPEEARS_TASK_SCAN_LIMIT", "100"))))
    pages = max(1, min(10, int(os.getenv("FIELD_SHIFT_APPEEARS_TASK_SCAN_PAGES", "3"))))
    for task in index["tasks"][:limit * pages]:
        if task.get("task_name") != task_name or task.get("task_type", "point") != "point" or not _task_is_reusable(task):
            continue
        params = task.get("params")
        existing_layers = params.get("layers") if isinstance(params, dict) else None
        if isinstance(existing_layers, list):
            requested = sorted((item.product, item.layer) for item in selections)
            available = sorted(
                (str(item.get("product", "")), str(item.get("layer", "")))
                for item in existing_layers if isinstance(item, dict)
            )
            if available and available != requested:
                continue
        return task
    return None


def _task_lock(task_name: str) -> threading.Lock:
    """Serialize same-process submissions for one field request."""
    with _TASK_LOCKS_GUARD:
        return _TASK_LOCKS.setdefault(task_name, threading.Lock())


def _cache_paths(cache_dir: Path, key: str) -> tuple[Path, Path]:
    return cache_dir / f"appeears_{key}.json", cache_dir / f"appeears_{key}.pending.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            json.dump(payload, handle)
            tmp = Path(handle.name)
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass


def _read_cache(path: Path, ttl: int) -> tuple[tuple[RemoteDay, ...] | None, float | None, dict[str, Any]]:
    try:
        age = max(0.0, time.time() - path.stat().st_mtime)
        if age > ttl:
            return None, age, {}
        envelope = json.loads(path.read_text(encoding="utf-8"))
        rows = envelope.get("remote", []) if isinstance(envelope, dict) else envelope
        out = []
        for row in rows:
            row["d"] = date.fromisoformat(row["d"])
            if row.get("provenance"):
                row["provenance"] = Provenance(**row["provenance"])
            out.append(RemoteDay(**row))
        statuses = envelope.get("dataset_statuses", {}) if isinstance(envelope, dict) else {}
        return tuple(out), age, statuses if isinstance(statuses, dict) else {}
    except (OSError, ValueError, TypeError, KeyError):
        return None, None, {}

def _cache_identity(
    source_key: str,
    lat: float,
    lon: float,
    requested_start: date,
    requested_end: date,
    effective_start: date,
    effective_end: date,
    selections: tuple[LayerSelection, ...],
) -> dict[str, Any]:
    """Describe every dimension that makes a completed point result reusable."""
    return {
        "source_key": source_key,
        "coordinate": {"latitude": round(lat, 5), "longitude": round(lon, 5), "precision_decimal_degrees": 5},
        "requested_dates": {"start": requested_start.isoformat(), "end": requested_end.isoformat()},
        "effective_dates": {"start": effective_start.isoformat(), "end": effective_end.isoformat()},
        "products": [
            {
                "product": item.product,
                "layer": item.layer,
                "target": item.target,
                "resolution": item.resolution,
                "temporal_resolution": item.temporal_resolution,
            }
            for item in sorted(selections, key=lambda value: (value.product, value.layer, value.target))
        ],
        "schema_version": 1,
        "qa_processing_version": "fieldshift-appeears-qa-v1",
    }


def _shared_cache_key(identity: dict[str, Any]) -> str:
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _remote_rows(rows: Any) -> tuple[RemoteDay, ...]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Shared satellite cache contains no observations")
    output: list[RemoteDay] = []
    for raw in rows:
        if not isinstance(raw, dict) or not isinstance(raw.get("d"), str):
            raise TypeError("Shared satellite cache contains an invalid observation")
        row = dict(raw)
        row["d"] = date.fromisoformat(row["d"])
        if row.get("provenance"):
            row["provenance"] = Provenance(**row["provenance"])
        output.append(RemoteDay(**row))
    return tuple(output)


def _read_shared_cache(
    object_key: str,
    expected_key: str,
    identity: dict[str, Any],
    requested_start: date,
    requested_end: date,
) -> tuple[tuple[RemoteDay, ...], dict[str, Any], str] | None:
    """Read a private Drive object only after identity and SHA-256 validation."""
    raw = google_drive.get_object(object_key)
    if raw is None:
        return None
    try:
        envelope = json.loads(raw.decode("utf-8"))
        if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
            return None
        if envelope.get("cache_key") != expected_key or envelope.get("identity") != identity:
            return None
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            return None
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        if digest != envelope.get("payload_sha256"):
            return None
        remote = _remote_rows(payload.get("remote"))
        if any(day.d < requested_start or day.d > requested_end for day in remote):
            return None
        statuses = payload.get("dataset_statuses")
        if not isinstance(statuses, dict):
            return None
        return remote, statuses, digest
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        return None


def _publish_shared_cache(
    object_key: str,
    cache_key: str,
    identity: dict[str, Any],
    remote: tuple[RemoteDay, ...],
    dataset_status: dict[str, Any],
) -> str:
    """Publish a completed, QA-checked result and require byte-for-byte read-back."""
    payload = {
        "remote": [{**asdict(row), "d": row.d.isoformat()} for row in remote],
        "dataset_statuses": {str(dataset_status.get("name") or identity["source_key"]): dataset_status},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    envelope = {
        "schema_version": 1,
        "cache_key": cache_key,
        "identity": identity,
        "payload_sha256": digest,
        "payload": payload,
    }
    raw = json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    google_drive.put_object(object_key, raw, sha256=hashlib.sha256(raw).hexdigest())
    readback = google_drive.get_object(object_key)
    if readback is None or readback != raw:
        raise google_drive.GoogleDriveError("Satellite cache remote read-back verification failed")
    verified = _read_shared_cache(object_key, cache_key, identity, date.fromisoformat(identity["effective_dates"]["start"]),
                                  date.fromisoformat(identity["effective_dates"]["end"]))
    if verified is None or verified[2] != digest:
        raise google_drive.GoogleDriveError("Satellite cache checksum or metadata verification failed")
    return digest




def _date_value(value: str) -> date | None:
    clean = value.strip()
    try:
        return date.fromisoformat(clean[:10])
    except (ValueError, TypeError):
        pass
    try:
        if len(clean) == 8 and clean.isdigit():
            return date(int(clean[:4]), int(clean[4:6]), int(clean[6:8]))
        month, day, year = clean.split("/")
        return date(int(year), int(month), int(day))
    except (ValueError, TypeError):
        pass
    return None


def _number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if (
        not math.isfinite(number)
        or number in {-9999.0, -999.0, -32768.0, 32767.0, 32768.0, 65535.0}
        or 32761.0 <= number <= 32766.0
    ):
        return None
    return number


def _field_value(row: dict[str, str], layer: str) -> float | None:
    layer_key = _norm(layer)
    for name, value in row.items():
        name_key = _norm(name)
        if name_key == layer_key or name_key.endswith(layer_key):
            return _number(value)
    return None


def _quality_details(source_key: str, selections: tuple[LayerSelection, ...]) -> tuple[str, str]:
    selected = [x for x in selections if x.source_key == source_key]
    targets = {x.target for x in selected}
    if source_key == "modis_et":
        if "modis_et_qc" in targets:
            return "applied", "MOD16 ET_QC_500m was decoded; only observations with MODLAND_QC=0 were retained."
        return "unavailable", "The AppEEARS catalog did not expose ET_QC_500m; MOD16 ET observations are excluded."
    if source_key == "hls_vi":
        if "hls_qa" in targets:
            return "applied", "HLS QA was decoded; cloud, cloud-adjacent, shadow, snow/ice, water, and highest-aerosol pixels were excluded."
        return "provider_masked", "HLS VI processing masks cloud and cloud-shadow pixels; no separate HLS QA layer was returned to filter water, snow, or aerosol flags."
    if source_key == "smap":
        if "smap_qa" in targets and any(x.product.startswith("SPL3") for x in selected):
            return "applied", "SMAP retrieval_qual_flag was applied to L3 retrievals; only documented recommended-quality flags 0 or 8 were retained."
        if any(x.product.startswith("SPL4SMGP") for x in selected):
            return "product_level", "SPL4SMGP is an assimilated L4 geophysical estimate and does not provide the L2/L3 retrieval_qual_flag in the sampled fields. Values are not described as retrieval-flag filtered."
        return "unavailable", "A supported SMAP quality flag was not exposed; SMAP L3 moisture observations are excluded."
    if source_key == "gpm":
        return "product_level", "IMERG Final calibrated precipitation was selected; no separate AppEEARS pixel QA flag was applied."
    return "not_reported", "No product-specific quality handling is configured."


def _hls_clear(qa: float) -> bool:
    value = int(qa)
    # HLS QA bits 1-5 flag cloud, adjacency, shadow, snow/ice, and water;
    # bits 6-7 encode aerosol optical thickness, with 3 representing high AOT.
    return value >= 0 and (value & 0b00111110) == 0 and ((value >> 6) & 0b11) != 3


def _records_from_csv_files(
    files: list[tuple[str, bytes]], selections: tuple[LayerSelection, ...], retrieval_date: str,
    start: date, end: date,
) -> tuple[RemoteDay, ...]:
    grouped: dict[date, dict[str, list[float]]] = {}
    modis_period_days: dict[date, int] = {}
    for file_name, raw in files:
        if not file_name.lower().endswith(".csv"):
            continue
        try:
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            for row in reader:
                raw_date = row.get("Date") or row.get("date") or row.get("Day")
                day = _date_value(raw_date or "")
                if day is None or day < start or day > end:
                    continue
                row_values: dict[str, float] = {}
                for selection in selections:
                    product_key = _norm(selection.product)
                    file_key = _norm(file_name)
                    # AppEEARS creates a per-product file; when filenames omit the
                    # collection, a unique layer name remains a sufficient match.
                    layer_columns = [c for c in row if _norm(c) == _norm(selection.layer) or _norm(c).endswith(_norm(selection.layer))]
                    if not layer_columns:
                        continue
                    if product_key not in file_key and len(layer_columns) > 1:
                        continue
                    value = _field_value(row, selection.layer)
                    if value is None:
                        continue
                    row_values[selection.target] = value
                smap_is_l3 = any(x.source_key == "smap" and x.product.startswith("SPL3") for x in selections)
                if smap_is_l3:
                    smap_qa = row_values.get("smap_qa")
                    if smap_qa is None or int(smap_qa) not in {0, 8}:
                        row_values.pop("smap_surface_m3_m3", None)
                        row_values.pop("smap_rootzone_m3_m3", None)
                modis_selected = any(x.source_key == "modis_et" and x.target == "modis_et_mm" for x in selections)
                if modis_selected:
                    qc = row_values.get("modis_et_qc")
                    et = row_values.get("modis_et_mm")
                    # MODLAND_QC is bit 0 (bit 1 identifies the sensor) of ET_QC_500m. Missing QA must not
                    # silently turn a low-quality ET estimate into trusted evidence.
                    if et is not None and qc is not None and (int(qc) & 0b1) == 0:
                        period = min(8, (date(day.year, 12, 31) - day).days + 1)
                        row_values["modis_et_mm"] = et / period
                        modis_period_days[day] = period
                    else:
                        row_values.pop("modis_et_mm", None)
                if any(x.source_key == "hls_vi" for x in selections):
                    hls_values = {k: v for k, v in row_values.items() if k in {"ndvi", "evi", "ndmi"}}
                    if "hls_qa" in row_values and not _hls_clear(row_values["hls_qa"]):
                        for key in hls_values:
                            row_values.pop(key, None)
                    # Without the separate QA field, HLS VI cloud/shadow masking is
                    # still provider-applied; ancillary water/snow/aerosol checks are disclosed.
                values = grouped.setdefault(day, {})
                for target, value in row_values.items():
                    if target.endswith(("_qa", "_qc")):
                        continue
                    values.setdefault(target, []).append(value)
        except (UnicodeDecodeError, csv.Error):
            continue
    output: list[RemoteDay] = []
    for day, fields in sorted(grouped.items()):
        averages = {key: sum(vals) / len(vals) for key, vals in fields.items() if vals}
        if not averages:
            continue
        source_names = sorted({x.source_name for x in selections if x.target in fields})
        resolutions = sorted({x.resolution for x in selections if x.target in fields and x.resolution})
        provenance = Provenance(
            source="NASA AppEEARS point sample: " + ", ".join(source_names),
            source_type="satellite",
            retrieval_date=retrieval_date,
            spatial_resolution="mixed native pixels: " + ", ".join(resolutions) if resolutions else "native product pixels",
            temporal_resolution="product native interval",
            citation="https://appeears.earthdatacloud.nasa.gov/api/",
            confidence=0.80,
        )
        output.append(RemoteDay(
            d=day, source=provenance.source, provenance=provenance,
            modis_et_period_days=modis_period_days.get(day, 1), **averages,
        ))
    return tuple(output)


def _source_statuses(selections: tuple[LayerSelection, ...], status: str, coverage: str | None = None) -> list[dict[str, Any]]:
    records = []
    missing_status = "not_configured" if status == "not_configured" else "unavailable"
    missing_hint = (
        "Set FIELD_SHIFT_APPEEARS_USER/FIELD_SHIFT_APPEEARS_PASSWORD (or a managed AppEEARS token) for authenticated point sampling."
        if missing_status == "not_configured"
        else "The credentials worked, but the current AppEEARS catalog did not expose a supported product/layer for this source; no values were imputed."
    )
    for definition in SOURCE_DEFINITIONS:
        found = [x for x in selections if x.source_key == definition["key"]]
        if not found:
            records.append({
                "name": definition["name"], "source_type": "satellite", "status": missing_status,
                "coverage": coverage or "No matching supported product/layer is currently available from the AppEEARS catalog.",
                "setup_hint": missing_hint,
                "citation": definition["citation"],
            })
            continue
        records.append({
            "name": definition["name"], "source_type": "satellite", "status": status,
            "coverage": coverage or "; ".join(f"{x.product}/{x.layer} ({x.resolution or 'native'}, {x.temporal_resolution or 'native cadence'})" for x in found),
            "citation": definition["citation"],
        })
    return records


def _sample_source(
    definition: SourceDefinition, token: str, products: list, lat: float, lon: float,
    start: date, end: date, cache_dir: Path, timeout: int, max_wait_seconds: int,
    task_index: dict[str, Any] | None = None,
    existing_task_id: str | None = None,
) -> AppEEARSResult:
    key, name = definition["key"], definition["name"]
    selections = discover_layers(token, timeout, source_key=key, start=start, end=end, products=products, cache_dir=cache_dir)
    selections = tuple(x for x in selections if x.source_key == key)

    def result(status, coverage, remote=(), **extra):
        records = _source_statuses(selections, status, coverage)
        record = next(x for x in records if x["name"] == name)
        record.update(status=status, data_start_date=start.isoformat(), data_end_date=end.isoformat(), **extra)
        return AppEEARSResult(tuple(remote), (record,))

    if not selections:
        return result("unavailable", "No supported product with usable layers overlaps the requested dates. Try an earlier date range.")
    requested_start, requested_end = start, end
    start = max([start] + [x.available_start for x in selections if x.available_start])
    end = min([end] + [x.available_end for x in selections if x.available_end])
    signature = "v4|" + key + "|" + _cache_key(lat, lon, start, end) + "|" + "|".join(sorted(x.product + "/" + x.layer for x in selections))
    cache_key = hashlib.sha256(signature.encode()).hexdigest()[:24]
    cache_path, pending_path = _cache_paths(cache_dir, cache_key)
    task_name = "fieldshift-v4-" + key + "-" + cache_key
    ttl = max(60, int(os.getenv("FIELD_SHIFT_APPEEARS_CACHE_TTL_SECONDS", "604800")))
    identity = _cache_identity(key, lat, lon, requested_start, requested_end, start, end, selections)
    shared_key = _shared_cache_key(identity)
    shared_object_key = f"satellite-point-cache/v1/{key}/{shared_key}.json"

    if google_drive.configured():
        try:
            shared = _read_shared_cache(shared_object_key, shared_key, identity, start, end)
        except google_drive.GoogleDriveError:
            shared = None
        if shared is not None:
            cached_rows, cached_statuses, digest = shared
            stored = cached_statuses.get(name, {})
            return result(
                stored.get("status", "available"),
                stored.get("coverage", "Verified shared NASA observations."),
                cached_rows,
                retrieval_mode="google_drive_cache",
                quality_status=stored.get("quality_status"),
                quality_note=stored.get("quality_note"),
                retrieval_date=stored.get("retrieval_date"),
                archive_cache_status="verified",
                archive_object_key=shared_object_key,
                archive_sha256=digest,
            )

    cached, age, metadata = _read_cache(cache_path, ttl)
    if cached is not None:
        stored = metadata.get(name, {})
        archive_status = "not_configured"
        archive_digest = None
        if google_drive.configured():
            try:
                archive_digest = _publish_shared_cache(shared_object_key, shared_key, identity, cached, stored or {
                    "name": name, "status": "available", "coverage": "Validated local AppEEARS result promoted to shared archive.",
                })
                archive_status = "verified"
            except Exception:
                archive_status = "write_failed"
        return result(
            stored.get("status", "available"), stored.get("coverage", "Cached NASA observations."), cached,
            retrieval_mode="google_drive_cache_published" if archive_status == "verified" else "cache",
            quality_status=stored.get("quality_status"), quality_note=stored.get("quality_note"),
            retrieval_date=stored.get("retrieval_date"), cache_age_seconds=int(age or 0),
            archive_cache_status=archive_status, archive_object_key=shared_object_key if archive_status == "verified" else None,
            archive_sha256=archive_digest,
        )
    task_id = ""
    task = None
    with _task_lock(task_name):
        try:
            pending = json.loads(pending_path.read_text())
            if pending.get("task_name") == task_name and time.time() - float(pending.get("created", 0)) < 7 * 86400:
                task_id = str(pending["task_id"])
                try:
                    task = _safe_json_request(f"task/{urllib.parse.quote(task_id, safe='-')}", token=token, timeout=timeout)
                    if not _task_is_reusable(task):
                        task_id = ""
                        task = None
                except AppEEARSDataError as exc:
                    if "HTTP 404" not in str(exc):
                        raise
                    task_id = ""
        except (OSError, ValueError, TypeError, KeyError):
            pass
        if not task_id and existing_task_id:
            # Prefer the exact task ID persisted with this run. A stale or
            # expired ID falls through to the account task-list discovery path.
            try:
                candidate = _safe_json_request(
                    f"task/{urllib.parse.quote(existing_task_id, safe='-')}",
                    token=token,
                    timeout=timeout,
                )
                if _task_is_reusable(candidate):
                    task_id = existing_task_id
                    task = candidate
            except AppEEARSDataError as exc:
                if "HTTP 404" not in str(exc):
                    raise
        if not task_id:
            existing = _find_recent_task(token, task_name, selections, timeout=timeout, task_index=task_index)
            task_id = str(existing.get("task_id", "")) if existing else ""
            task = existing
        if not task_id:
            payload = {"task_type": "point", "task_name": task_name, "params": {
                "dates": [{"startDate": start.strftime("%m-%d-%Y"), "endDate": end.strftime("%m-%d-%Y")}],
                "layers": [{"product": x.product, "layer": x.layer} for x in selections],
                "coordinates": [{"id": "field", "latitude": lat, "longitude": lon, "category": "field"}],
            }}
            submitted = _safe_json_request("task", method="POST", token=token, payload=payload, timeout=timeout)
            task_id = str(submitted.get("task_id", ""))
            if not task_id:
                raise AppEEARSDataError("AppEEARS did not return a task identifier.")
            task = None
            if task_index is not None:
                task_index.setdefault("tasks", []).insert(0, {**payload, **submitted})
        _write_json(pending_path, {"task_id": task_id, "task_name": task_name, "created": time.time()})
    deadline = time.monotonic() + max_wait_seconds
    while True:
        task = task or _safe_json_request(f"task/{urllib.parse.quote(task_id, safe='-')}", token=token, timeout=timeout)
        status = str(task.get("status", "unknown")).lower()
        if status == "done":
            break
        if status in {"error", "failed", "cancelled"}:
            pending_path.unlink(missing_ok=True)
            detail = safe_error(AppEEARSDataError(str(task.get("error") or task.get("message") or status)))
            return result("unavailable", f"This {key} task ended with status {status}; the other products run independently.", error=detail)
        if time.monotonic() >= deadline:
            return result(
                "pending",
                f"NASA is {status} this point sample. Refreshing resumes the same task.",
                retry_after_seconds=30,
                provider_task_id=task_id,
            )
        time.sleep(min(10, max(0, deadline - time.monotonic())))
        task = None
    bundle = _safe_json_request(f"bundle/{task_id}", token=token, timeout=timeout)
    csv_files = []
    for item in bundle.get("files", []):
        filename = str(item.get("file_name", ""))
        if item.get("file_id") and (str(item.get("file_type", "")).lower() == "csv" or filename.lower().endswith(".csv")):
            csv_files.append((filename, _download(f"bundle/{task_id}/{urllib.parse.quote(str(item['file_id']), safe='-')}", token, timeout)))
    retrieved = now_iso()
    remote = _records_from_csv_files(csv_files, selections, retrieved, start, end)
    pending_path.unlink(missing_ok=True)
    if not remote:
        return result("unavailable", "NASA completed the task but returned no usable values after date, fill-value and quality checks. Try another date range.")
    quality, note = _quality_details(key, selections)
    coverage = f"{len(remote)} usable observation dates, {remote[0].d} to {remote[-1].d}; product {selections[0].product}."
    partial = start != requested_start or end != requested_end
    if partial:
        coverage += f" Product availability limited the request to {start} through {end}."
    output = result("partial" if partial else "available", coverage, remote,
                    retrieval_mode="live", retrieval_date=retrieved, quality_status=quality, quality_note=note)
    _write_json(cache_path, {"remote": [{**asdict(row), "d": row.d.isoformat()} for row in remote],
                             "dataset_statuses": {name: output.datasets[0]}})
    archive_status = "not_configured"
    archive_digest = None
    if google_drive.configured():
        try:
            archive_digest = _publish_shared_cache(
                shared_object_key, shared_key, identity, remote, output.datasets[0],
            )
            archive_status = "verified"
        except Exception as exc:
            # The validated live data remains usable for this revision. A failed
            # archive write is disclosed and can be retried; it is never a cache hit.
            archive_status = "write_failed"
            output.datasets[0]["archive_cache_error"] = safe_error(exc)
    output.datasets[0]["archive_cache_status"] = archive_status
    output.datasets[0]["archive_object_key"] = shared_object_key if archive_status == "verified" else None
    output.datasets[0]["archive_sha256"] = archive_digest
    _write_json(cache_path, {"remote": [{**asdict(row), "d": row.d.isoformat()} for row in remote],
                             "dataset_statuses": {name: output.datasets[0]}})
    return output


def appeears_point_timeseries(
    lat: float,
    lon: float,
    start: date,
    end: date,
    *,
    cache_dir: str | Path,
    timeout: int = 20,
    max_wait_seconds: int | None = None,
    existing_task_ids: dict[str, str] | None = None,
    source_keys: set[str] | None = None,
) -> AppEEARSResult:
    """Run only the selected independent product tasks, resumable across requests."""
    selected_definitions = tuple(
        definition for definition in SOURCE_DEFINITIONS
        if source_keys is None or definition["key"] in source_keys
    )
    if not selected_definitions:
        return AppEEARSResult((), ())
    if not credentials_configured():
        selected_names = {definition["name"] for definition in selected_definitions}
        statuses = _source_statuses((), "not_configured", "Earthdata credentials are not configured on the server.")
        return AppEEARSResult((), tuple(item for item in statuses if item.get("name") in selected_names))
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180 or start > end:
        raise ValueError("Invalid coordinate or date range for AppEEARS")
    max_days = max(1, min(366, int(os.getenv("FIELD_SHIFT_APPEEARS_MAX_DAYS", "366"))))
    if (end - start).days + 1 > max_days:
        raise ValueError(f"AppEEARS date range exceeds configured limit of {max_days} days; shorten the range.")
    def failure(definition, exc):
        retry = isinstance(exc, AppEEARSRetryableError)
        return {"name": definition["name"], "source_type": "satellite", "status": "retrying" if retry else "unavailable",
                "error": safe_error(exc), "request_stage": getattr(exc, "stage", None),
                "http_status": getattr(exc, "http_status", None), "retry_after_seconds": getattr(exc, "retry_after_seconds", None),
                "coverage": "Waiting before retrying a temporary NASA request failure; no observations have been substituted." if retry
                else "This product request failed; other datasets continue independently."}

    try:
        token = _login_token(timeout=timeout)
        products = _metadata_request("product", token, timeout, Path(cache_dir))
    except Exception as exc:
        return AppEEARSResult((), tuple(failure(d, exc) for d in selected_definitions))
    wait = max_wait_seconds if max_wait_seconds is not None else int(os.getenv("FIELD_SHIFT_APPEEARS_WAIT_SECONDS", "0"))
    task_index: dict[str, Any] = {}

    def sample(definition):
        try:
            task_aliases = {
                "smap": "nasa_smap",
                "modis_et": "nasa_modis_mod16",
                "hls_vi": "nasa_hls",
            }
            saved_task_id = (existing_task_ids or {}).get(definition["key"])
            if not saved_task_id:
                saved_task_id = (existing_task_ids or {}).get(task_aliases.get(definition["key"], ""))
            return _sample_source(
                definition,
                token,
                products,
                lat,
                lon,
                start,
                end,
                Path(cache_dir),
                timeout,
                max(0, min(30, wait)),
                task_index,
                existing_task_id=saved_task_id,
            )
        except Exception as exc:
            return AppEEARSResult((), (failure(definition, exc),))

    # NASA tasks remain independent, but HTTP requests are paced sequentially.
    results = [sample(definition) for definition in selected_definitions]
    return AppEEARSResult(tuple(row for r in results for row in r.remote), tuple(item for r in results for item in r.datasets))
