from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from fieldshift.api.product import (
    create_analysis,
    create_demo,
    get_analysis,
    get_evidence,
    get_strategy,
    report,
    report_from_response,
    what_if,
)
from fieldshift.v3.appeears import credentials_configured as appeears_credentials_configured
from fieldshift.v3.gee import gee_credentials_configured
from fieldshift.v3.history import REGIONS, history_summary, read_year
from fieldshift.v3.history_extended import history_date_range, read_ytd
from fieldshift.v3.pipeline import DEFAULT_WEIGHTS, run_v3
from fieldshift.v3.refresh_jobs import create_refresh, get_refresh
from fieldshift.v3.region_catalog import zone_catalog
from fieldshift.v3.satellite_archive import satellite_history, SOURCES as SATELLITE_SOURCES

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install FieldShift API dependencies with `pip install .[api]`.") from exc

APP_ROOT = Path(__file__).resolve().parent
app = FastAPI(
    title="FieldShift V3 Product API",
    version="3.3.0",
    description="Farmer-facing evidence-aware crop rotation decision support",
)

static_dir = APP_ROOT / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Bengali learning lab: ship the static client with the same FastAPI function.
school_game_dir = Path(__file__).resolve().parents[3] / "school-game"
if school_game_dir.is_dir():
    app.mount("/school-game", StaticFiles(directory=school_game_dir, html=True), name="school-game")


def _jsonable(run) -> dict[str, Any]:
    return json.loads(json.dumps(asdict(run), default=str))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine": "3.0.0", "product": "3.3.0"}


@app.get("/api/status")
def integration_status() -> dict[str, Any]:
    """Report safe configuration state without exposing environment values."""
    live_mode = os.getenv("FIELD_SHIFT_LIVE_NASA", "auto").strip().lower() not in {"0", "false", "off", "no"}
    soilgrids_enabled = os.getenv("FIELD_SHIFT_SOILGRIDS", "0").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "status": "ok",
        "deployment": "vercel" if os.getenv("VERCEL") else "local",
        "integrations": {
            "nasa_power": {
                "live_requests_enabled": live_mode,
                "credentials_required": False,
                "connectivity_tested": False,
            },
            "nasa_appeears": {
                "credentials_configured": appeears_credentials_configured(),
                "credentials_validated": False,
            },
            "earth_engine": {
                "credentials_configured": gee_credentials_configured(),
                "credentials_validated": False,
            },
            "soilgrids": {"enabled": soilgrids_enabled},
        },
        "analysis_state": {"storage": "process_memory", "durable_across_instances": False},
    }


@app.get("/api/v3/config")
def config() -> dict[str, dict[str, float]]:
    return {"default_weights": DEFAULT_WEIGHTS}


@app.get("/api/v3/demo")
def demo() -> dict[str, Any]:
    try:
        run_result = run_v3(n_weight_samples=80, n_uncertainty_samples=24)
        return _jsonable(run_result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v3/run")
def run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    priorities = payload.get("priorities")
    field_override = payload.get("field")
    year = int(payload.get("year", 2026))
    n_weight = min(1000, max(20, int(payload.get("n_weight_samples", 250))))
    n_uncertainty = min(300, max(8, int(payload.get("n_uncertainty_samples", 48))))
    try:
        run_result = run_v3(
            priorities=priorities,
            year=year,
            n_weight_samples=n_weight,
            n_uncertainty_samples=n_uncertainty,
            field_override=field_override,
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
        )
        return _jsonable(run_result)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/demo")
def product_demo() -> dict[str, Any]:
    try:
        return create_demo()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/field/preview")
def field_preview(payload: dict[str, Any]) -> dict[str, Any]:
    field = payload.get("field", payload)
    if not isinstance(field, dict):
        raise HTTPException(status_code=400, detail="field must be an object")
    soil = field.get("soil") or {}
    if not isinstance(soil, dict):
        raise HTTPException(status_code=400, detail="soil must be an object")
    try:
        lat = float(field.get("lat", 24.75))
        lon = float(field.get("lon", 90.41))
        area_ha = float(field.get("area_ha", 0.4))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="lat, lon, and area_ha must be numeric") from exc
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise HTTPException(status_code=400, detail="lat must be between -90 and 90")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise HTTPException(status_code=400, detail="lon must be between -180 and 180")
    if not math.isfinite(area_ha) or area_ha <= 0:
        raise HTTPException(status_code=400, detail="area_ha must be a positive finite number")
    pilot_box = abs(lat - 24.75) <= 0.15 and abs(lon - 90.41) <= 0.15
    return {
        "field": {
            "location": {"lat": lat, "lon": lon},
            "area_ha": area_ha,
            "soil_source": field.get("soil_data_source", "farmer-reported") if soil else "mymensingh-pilot-estimate" if pilot_box else "not-provided",
            "soil_inputs_provided": sorted(soil.keys()),
            "within_mymensingh_pilot_box": pilot_box,
            "locally_validated": False,
        },
        "warnings": ["The Mymensingh coordinate check is only a pilot-area hint; no field-specific local validation is established by this preview."],
        "status": "inputs_received",
    }


@app.post("/api/analysis/run")
def analysis_run(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return create_analysis(payload or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/analysis/{run_id}")
def analysis_get(run_id: str) -> dict[str, Any]:
    try:
        return get_analysis(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown analysis: {run_id}") from exc


@app.get("/api/analysis/{run_id}/strategies")
def analysis_strategies(run_id: str) -> dict[str, Any]:
    data = analysis_get(run_id)
    return {"strategies": data["strategies"]}


@app.get("/api/analysis/{run_id}/strategies/{strategy_id}")
def analysis_strategy(run_id: str, strategy_id: str) -> dict[str, Any]:
    try:
        return get_strategy(run_id, strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown strategy") from exc


@app.get("/api/analysis/{run_id}/scenarios")
def analysis_scenarios(run_id: str) -> dict[str, Any]:
    data = analysis_get(run_id)
    return {"scenarios": data["scenarios"], "strategies": data["strategies"]}


@app.get("/api/analysis/{run_id}/evidence/{evidence_id}")
def analysis_evidence(run_id: str, evidence_id: str) -> dict[str, Any]:
    try:
        return get_evidence(run_id, evidence_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown evidence item") from exc


@app.post("/api/analysis/{run_id}/what-if")
def analysis_what_if(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return what_if(run_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown analysis") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/analysis/{run_id}/report")
def analysis_report(run_id: str) -> dict[str, Any]:
    try:
        return report(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown analysis") from exc


@app.post("/api/analysis/{run_id}/report")
def analysis_report_from_client(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict) or data.get("run", {}).get("id") != run_id:
        raise HTTPException(status_code=400, detail="Report data does not match the requested analysis")
    try:
        return report_from_response(data)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc




@app.get("/api/regions")
def regions() -> dict[str, Any]:
    return {**zone_catalog(), "reference_points": REGIONS,
            "notice": "Planning zones are provisional groupings, not official AEZ polygons. NASA POWER values are gridded point samples, not zone averages."}


@app.get("/api/history/{region_id}")
def regional_history(region_id: str, start_year: int = 2016, end_year: int = 2025,
                     start: str | None = None, end: str | None = None,
                     product: str = "power") -> dict[str, Any]:
    try:
        if product != "power":
            raise ValueError("History source must be power; use /api/satellite-history for other products")
        if start is not None or end is not None:
            if not start or not end:
                raise ValueError("Both start and end dates are required")
            return history_date_range(region_id, start, end)
        return history_summary(region_id, start_year, end_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/data-status/{region_id}")
def source_data_status(region_id: str) -> dict[str, Any]:
    try:
        from fieldshift.v3.history import region_by_id
        region = region_by_id(region_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown region") from exc
    through = None
    archive_kind = "not_archived"
    archive_error = None
    try:
        _, meta = read_ytd(region_id, date.today().year)
        through = meta.get("data_through")
        archive_kind = "ytd_partial"
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        archive_error = type(exc).__name__
        for year in range(date.today().year - 1, max(2015, date.today().year - 11), -1):
            try:
                _, meta = read_year(region_id, year)
                through = f"{year}-12-31"
                archive_kind = "completed_year"
                archive_error = None
                break
            except (OSError, ValueError, KeyError, TypeError):
                continue
    power_state = "ready" if archive_kind in {"ytd_partial", "completed_year"} else "not_archived"
    if through is None:
        try:
            compact = history_summary(region_id, 2016, 2025)
            if compact.get("annual"):
                through = f"{max(row['year'] for row in compact['annual'])}-12-31"
                if compact.get("archive_representation") == "monthly_aggregate":
                    archive_kind = "monthly_summary_chart_only"
                    power_state = "summary_only"
        except (OSError, ValueError, RuntimeError):
            pass
    products = {"power": {"state": power_state,
                          "data_through": through, "archive_kind": archive_kind,
                          "sample_type": "NASA POWER gridded point",
                          "field_measurement": False,
                          "error_type": archive_error,
                          "citation": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/"}}
    for product in SATELLITE_SOURCES:
        try:
            sat = satellite_history(region_id, product)
            products[product] = {"state": sat.get("status", "available"),
                                 "data_through": sat.get("data_through"),
                                 "coverage_fraction": sat.get("coverage_fraction"),
                                 "product_id": sat.get("product_id"),
                                 "unit": sat.get("unit", SATELLITE_SOURCES[product]["unit"]),
                                 "field_measurement": False}
        except (OSError, ValueError, RuntimeError) as exc:
            products[product] = {"state": "unavailable", "error_type": type(exc).__name__,
                                 "field_measurement": False}
    return {"region": region, "products": products,
            "notice": "Source readiness is separate from whether a source was used in a particular analysis run."}


@app.get("/api/satellite-history/{region_id}")
def satellite_history_api(region_id: str, product: str) -> dict[str, Any]:
    try:
        return satellite_history(region_id, product)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc




@app.post("/api/refresh-jobs", status_code=202)
def create_refresh_api(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    # A trusted proxy and distributed edge limit are required for public scale.
    caller = request.client.host if request.client else "anonymous"
    try:
        job, created = create_refresh(
            payload.get("region_id", ""),
            payload.get("product", "power"),
            payload.get("data_through", ""),
            caller,
        )
        return {**job, "created": created,
                "notice": "A separate supervised worker is required. Cached history remains available."}
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/refresh-jobs/{job_id}")
def get_refresh_api(job_id: str) -> dict[str, Any]:
    try:
        result = get_refresh(job_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not result:
        raise HTTPException(status_code=404, detail="Refresh job not found")
    return result


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (APP_ROOT / "static" / "index.html").read_text(encoding="utf-8")

