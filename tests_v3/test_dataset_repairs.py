"""Regression tests for the website/provider boundary (no external credentials)."""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fieldshift.api.app import app
from fieldshift.v3 import appeears, gee, pipeline
from fieldshift.v3.dates import evidence_dates
from fieldshift.v3.diagnostics import safe_error
from fieldshift.v3.models import RemoteDay

START, END = date(2025, 1, 1), date(2025, 1, 15)
PRODUCTS = [
    {"ProductAndVersion": "SPL4SMGP.008", "TemporalExtentStart": "2015-03-31", "TemporalExtentEnd": "Present"},
    {"ProductAndVersion": "MOD16A2GF.061", "TemporalExtentStart": "2001-01-01", "TemporalExtentEnd": "2025-12-31"},
    {"ProductAndVersion": "MOD16A2.061", "TemporalExtentStart": "2001-01-01", "TemporalExtentEnd": "Present"},
    {"ProductAndVersion": "HLSS30_VI.020", "TemporalExtentStart": "2015-11-28", "TemporalExtentEnd": "Present"},
]
LAYERS = {
    "SPL4SMGP.008": {"Geophysical_Data_sm_surface": {}, "Geophysical_Data_sm_rootzone": {}},
    "MOD16A2GF.061": {"ET_500m": {}, "ET_QC_500m": {}},
    "MOD16A2.061": {"ET_500m": {}, "ET_QC_500m": {}},
    "HLSS30_VI.020": {"NDVI": {}, "EVI": {}},
}
CSVS = {
    "smap": b"Date,SPL4SMGP_008_Geophysical_Data_sm_surface,SPL4SMGP_008_Geophysical_Data_sm_rootzone\n2025-01-01T03:00:00Z,0.2,0.3\n",
    "modis_et": b"Date,MOD16A2GF_061_ET_500m,MOD16A2GF_061_ET_QC_500m\n2025-01-01,16,0\n",
    "hls_vi": b"Date,HLSS30_VI_020_NDVI,HLSS30_VI_020_EVI\n2025-01-01,0.6,0.4\n",
}


class NASAService:
    def __init__(self, failure=None, pending=False):
        self.failure, self.pending = failure, pending
        self.tasks, self.payloads, self.calls = {}, [], []

    def request(self, path, **kwargs):
        self.calls.append((path, kwargs.get("method", "GET")))
        if path == "login":
            return {"token": "mock-token"}
        if path == "product":
            return PRODUCTS
        if path.startswith("product/"):
            return LAYERS[path.split("/")[1]]
        if path == "task" and kwargs.get("method", "GET") == "GET":
            return list(self.tasks.values())
        if path == "task":
            body = kwargs["payload"]
            self.payloads.append(body)
            key = body["task_name"].split("-")[2]
            if key == self.failure:
                raise appeears.AppEEARSDataError("AppEEARS returned HTTP 400: product request rejected")
            self.tasks[key] = {**body, "task_id": key, "status": "pending" if self.pending else "done"}
            return self.tasks[key]
        if path.startswith("task/"):
            return self.tasks[path.split("/")[1]]
        if path.startswith("bundle/"):
            key = path.split("/")[1]
            return {"files": [{"file_name": f"{key}.csv", "file_type": "csv", "file_id": key}]}
        raise AssertionError(path)

    def download(self, path, *args):
        return CSVS[path.split("/")[-1]]


@pytest.fixture
def nasa(monkeypatch):
    service = NASAService()
    monkeypatch.setenv("FIELD_SHIFT_APPEEARS_USER", "mock-user")
    monkeypatch.setenv("FIELD_SHIFT_APPEEARS_PASSWORD", "mock-password")
    monkeypatch.delenv("FIELD_SHIFT_APPEEARS_TOKEN", raising=False)
    appeears._clear_token()
    monkeypatch.setattr(appeears, "_safe_json_request", service.request)
    monkeypatch.setattr(appeears, "_download", service.download)
    return service


def test_three_independent_tasks_parse_namespaced_smap_and_cache(nasa, tmp_path):
    first = appeears.appeears_point_timeseries(24.75, 90.41, START, END, cache_dir=tmp_path)
    assert {d["status"] for d in first.datasets} == {"available"}
    assert len(nasa.payloads) == 3
    assert nasa.calls.count(("task", "GET")) == 1
    assert not any("?" in path for path, _ in nasa.calls)
    assert all(len({l["product"] for l in p["params"]["layers"]}) == 1 for p in nasa.payloads)
    assert any(r.smap_rootzone_m3_m3 == 0.3 for r in first.remote)
    cached = appeears.appeears_point_timeseries(24.75, 90.41, START, END, cache_dir=tmp_path)
    assert len(nasa.payloads) == 3
    assert {d["retrieval_mode"] for d in cached.datasets} == {"cache"}
    assert nasa.calls.count(("product", "GET")) == 1
    assert nasa.calls.count(("product/SPL4SMGP.008", "GET")) == 1


def test_failed_smap_does_not_remove_hls_or_modis(nasa, tmp_path):
    nasa.failure = "smap"
    result = appeears.appeears_point_timeseries(24.75, 90.41, START, END, cache_dir=tmp_path)
    statuses = {d["name"]: d["status"] for d in result.datasets}
    assert statuses == {"NASA SMAP": "unavailable", "NASA MODIS MOD16": "available", "NASA HLS": "available"}
    assert "HTTP 400" in result.datasets[0]["error"]


def test_pending_tasks_resume_from_persisted_ids_after_serverless_cache_loss(nasa, tmp_path):
    nasa.pending = True
    first = appeears.appeears_point_timeseries(24.75, 90.41, START, END, cache_dir=tmp_path / "cold1")
    assert {d["status"] for d in first.datasets} == {"pending"}
    assert all("resumes" in d["coverage"] for d in first.datasets)
    saved_task_ids = {
        {"NASA SMAP": "nasa_smap", "NASA MODIS MOD16": "nasa_modis_mod16", "NASA HLS": "nasa_hls"}[row["name"]]:
            row["provider_task_id"]
        for row in first.datasets
    }
    assert set(saved_task_ids) == {"nasa_smap", "nasa_modis_mod16", "nasa_hls"}
    assert all(saved_task_ids.values())

    # Simulate a new Vercel instance with no pending-task files or result cache.
    # The task IDs persisted by the previous worker attempt must be sufficient.
    for task in nasa.tasks.values():
        task["status"] = "done"
    second = appeears.appeears_point_timeseries(
        24.75,
        90.41,
        START,
        END,
        cache_dir=tmp_path / "cold2",
        existing_task_ids=saved_task_ids,
    )
    assert len(nasa.payloads) == 3
    assert {d["status"] for d in second.datasets} == {"available"}
    assert all(d["retrieval_mode"] == "live" for d in second.datasets)
    assert nasa.calls.count(("task", "GET")) == 1


def test_date_aware_modis_selection_avoids_expired_gap_filled_product(nasa):
    selected = appeears.discover_layers("mock", source_key="modis_et", start=date(2026, 1, 1), end=date(2026, 1, 15))
    assert {s.product for s in selected} == {"MOD16A2.061"}


def test_modis_sensor_bit_and_short_year_end_composite():
    selected = tuple(appeears.LayerSelection("modis_et", "NASA MODIS MOD16", "MOD16A2.061", layer, target, None, None)
                     for layer, target in [("ET_500m", "modis_et_mm"), ("ET_QC_500m", "modis_et_qc")])
    raw = b"Date,ET_500m,ET_QC_500m\n2025-12-27,10,2\n"
    rows = appeears._records_from_csv_files([("modis.csv", raw)], selected, "test", date(2025, 12, 1), date(2025, 12, 31))
    assert rows[0].modis_et_mm == 2 and rows[0].modis_et_period_days == 5




def test_smap_long_date_windows_use_reusable_366_day_chunks(monkeypatch, tmp_path):
    calls = []

    def chunk(lat, lon, start, end, cache_dir, *, allow_live_query=True):
        calls.append((start, end))
        expected = (end - start).days + 1
        rows = tuple(
            RemoteDay(date.fromordinal(start.toordinal() + offset), smap_surface_m3_m3=0.2,
                      smap_rootzone_m3_m3=0.3, source="NASA SMAP test")
            for offset in range(expected)
        )
        return gee.SMAPPointResult(
            rows=rows, status="available", coverage_fraction=1.0,
            retrieval_mode="google_drive_cache", archive_cache_status="verified",
            archive_object_key=f"satellite-point-cache/chunk-{len(calls)}.json",
            archive_sha256=(str(len(calls)) * 64),
        )

    monkeypatch.setattr(gee, "_smap_daily_point_timeseries_window", chunk)
    start, end = date(2024, 1, 1), date(2025, 12, 31)
    result = gee.smap_daily_point_timeseries(24.75, 90.41, start, end, tmp_path)

    assert calls == [(date(2024, 1, 1), date(2024, 12, 31)),
                     (date(2025, 1, 1), date(2025, 12, 31))]
    assert len(result.rows) == 731
    assert result.status == "available"
    assert result.coverage_fraction == 1.0
    assert result.chunk_count == 2
    assert result.archive_cache_status == "verified"
    assert result.archive_object_keys == (
        "satellite-point-cache/chunk-1.json",
        "satellite-point-cache/chunk-2.json",
    )
    assert result.archive_object_key is None
    assert result.retrieval_mode == "google_drive_cache"



def test_smap_year_cache_chunks_are_sliced_to_exact_user_window(monkeypatch, tmp_path):
    calls = []

    def year_chunk(lat, lon, start, end, cache_dir, *, allow_live_query=True):
        calls.append((start, end))
        count = (end - start).days + 1
        rows = tuple(
            RemoteDay(
                date.fromordinal(start.toordinal() + offset),
                smap_surface_m3_m3=0.22,
                smap_rootzone_m3_m3=0.34,
                source="NASA SMAP cached year",
            )
            for offset in range(count)
        )
        number = len(calls)
        return gee.SMAPPointResult(
            rows=rows,
            status="available",
            coverage_fraction=1.0,
            retrieval_mode="google_drive_cache",
            archive_cache_status="verified",
            archive_object_key=f"satellite-point-cache/year-{start.year}.json",
            archive_sha256=(str(number) * 64),
        )

    monkeypatch.setattr(gee, "_smap_daily_point_timeseries_window", year_chunk)
    requested_start, requested_end = date(2024, 3, 1), date(2025, 6, 30)
    result = gee.smap_daily_point_timeseries(
        24.75, 90.41, requested_start, requested_end, tmp_path,
    )

    assert calls == [
        (date(2024, 1, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 12, 31)),
    ]
    assert len(result.rows) == (requested_end - requested_start).days + 1
    assert result.rows[0].d == requested_start
    assert result.rows[-1].d == requested_end
    assert all(requested_start <= row.d <= requested_end for row in result.rows)
    assert result.status == "available"
    assert result.archive_cache_status == "verified"
    assert result.archive_object_keys == (
        "satellite-point-cache/year-2024.json",
        "satellite-point-cache/year-2025.json",
    )


def test_pipeline_uses_gee_smap_and_only_requests_hls_modis_from_appeears(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "credentials_configured", lambda: True)
    monkeypatch.setattr(pipeline, "gee_credentials_configured", lambda: True)
    smap_provenance = gee.Provenance(
        source="NASA SMAP SPL4SMGP.008 via Google Earth Engine",
        source_type="satellite",
        temporal_resolution="3-hourly input aggregated to UTC daily mean; exactly 8 intervals required",
        spatial_resolution="~11 km pixel",
        citation="https://doi.org/10.5067/T5RUATAQREF8",
        confidence=0.88,
    )
    smap_result = gee.SMAPPointResult(
        rows=tuple(
            RemoteDay(date.fromordinal(START.toordinal() + offset), smap_surface_m3_m3=0.25,
                      smap_rootzone_m3_m3=0.32, source=smap_provenance.source, provenance=smap_provenance)
            for offset in range((END - START).days + 1)
        ),
        status="available", coverage_fraction=1.0, retrieval_mode="google_earth_engine",
        archive_cache_status="verified",
        archive_object_key="satellite-point-cache/v1/smap-gee/test.json",
        archive_sha256="a" * 64,
    )
    appeears_result = appeears.AppEEARSResult(
        remote=(
            RemoteDay(START, ndvi=0.6, source="NASA HLS"),
            RemoteDay(START, modis_et_mm=2.0, source="NASA MODIS MOD16"),
        ),
        datasets=(
            {"name": "NASA HLS", "source_type": "satellite", "status": "available"},
            {"name": "NASA MODIS MOD16", "source_type": "satellite", "status": "available"},
        ),
    )
    monkeypatch.setattr(pipeline, "smap_daily_point_timeseries", lambda *a, **k: smap_result)
    monkeypatch.setattr(pipeline, "gpm_daily_point_timeseries", lambda *a, **k: ())
    field = pipeline.build_field(pipeline.load_config(), pipeline.DEFAULT_WEIGHTS)
    records = []
    appeears_calls = []
    def sampled_products(*args, **kwargs):
        appeears_calls.append(kwargs)
        return appeears_result
    monkeypatch.setattr(pipeline, "appeears_point_timeseries", sampled_products)
    remote = pipeline._load_optional_remote(tmp_path, records, field, START, END, tmp_path)
    assert appeears_calls and appeears_calls[0]["source_keys"] == {"hls_vi", "modis_et"}
    satellite = {row["name"]: row for row in records}
    assert satellite["NASA SMAP"]["status"] == "available"
    assert satellite["NASA SMAP"]["retrieval_mode"] == "google_earth_engine"
    assert satellite["NASA SMAP"]["archive_cache_status"] == "verified"
    assert "eight complete 3-hourly" in satellite["NASA SMAP"]["coverage"]
    assert satellite["NASA HLS"]["status"] == "available"
    assert satellite["NASA MODIS MOD16"]["status"] == "available"
    assert any(row.smap_surface_m3_m3 == pytest.approx(0.25) for row in remote)
    assert any(row.ndvi == pytest.approx(0.6) for row in remote)
    assert any(row.modis_et_mm == pytest.approx(2.0) for row in remote)


def test_initial_worker_defers_smap_even_when_only_appeears_is_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "credentials_configured", lambda: True)
    monkeypatch.setattr(pipeline, "gee_credentials_configured", lambda: False)
    app_result = appeears.AppEEARSResult(
        remote=(
            RemoteDay(START, ndvi=0.61, source="NASA HLS"),
            RemoteDay(START, modis_et_mm=2.1, source="NASA MODIS MOD16"),
        ),
        datasets=(
            {"name": "NASA HLS", "source_type": "satellite", "status": "available"},
            {"name": "NASA MODIS MOD16", "source_type": "satellite", "status": "available"},
        ),
    )
    calls = []

    def sampled_products(*args, **kwargs):
        calls.append(kwargs)
        return app_result

    monkeypatch.setattr(pipeline, "appeears_point_timeseries", sampled_products)
    field = pipeline.build_field(pipeline.load_config(), pipeline.DEFAULT_WEIGHTS)
    records = []
    remote = pipeline._load_optional_remote(
        tmp_path, records, field, START, END, tmp_path, allow_live_smap=False,
    )

    assert calls and calls[0]["source_keys"] == {"hls_vi", "modis_et"}
    smap = next(row for row in records if row["name"] == "NASA SMAP")
    assert smap["status"] == "pending"
    assert smap["retry_after_seconds"] == 900
    assert "deferred" in smap["coverage"]
    assert any(row.ndvi == pytest.approx(0.61) for row in remote)
    assert any(row.modis_et_mm == pytest.approx(2.1) for row in remote)


def test_pipeline_falls_back_to_appeears_when_gee_smap_is_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "credentials_configured", lambda: True)
    monkeypatch.setattr(pipeline, "gee_credentials_configured", lambda: True)
    monkeypatch.setattr(
        pipeline, "smap_daily_point_timeseries",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("GEE temporarily unavailable")),
    )
    app_result = appeears.AppEEARSResult(
        remote=(RemoteDay(START, smap_surface_m3_m3=0.2, smap_rootzone_m3_m3=0.3, source="AppEEARS SMAP"),),
        datasets=(
            {"name": "NASA SMAP", "source_type": "satellite", "status": "available"},
            {"name": "NASA HLS", "source_type": "satellite", "status": "available"},
            {"name": "NASA MODIS MOD16", "source_type": "satellite", "status": "available"},
        ),
    )
    appeears_calls = []
    def fallback_products(*args, **kwargs):
        appeears_calls.append(kwargs)
        return app_result
    monkeypatch.setattr(pipeline, "appeears_point_timeseries", fallback_products)
    monkeypatch.setattr(pipeline, "gpm_daily_point_timeseries", lambda *a, **k: ())
    field = pipeline.build_field(pipeline.load_config(), pipeline.DEFAULT_WEIGHTS)
    records = []
    remote = pipeline._load_optional_remote(tmp_path, records, field, START, END, tmp_path)
    assert appeears_calls and appeears_calls[0]["source_keys"] is None
    assert next(row for row in records if row["name"] == "NASA SMAP")["status"] == "available"
    assert any(row.smap_surface_m3_m3 == pytest.approx(0.2) for row in remote)


def test_gpm_has_one_evidence_entry_when_appeears_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "credentials_configured", lambda: True)
    monkeypatch.setattr(pipeline, "gee_credentials_configured", lambda: True)
    monkeypatch.setattr(pipeline, "appeears_point_timeseries", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(pipeline, "gpm_daily_point_timeseries", lambda *a, **k: (RemoteDay(START, gpm_rain_mm=4),))
    field = pipeline.build_field(pipeline.load_config(), pipeline.DEFAULT_WEIGHTS)
    records = []
    pipeline._load_optional_remote(tmp_path, records, field, START, END, tmp_path)
    gpm = [r for r in records if r["name"] == "NASA GPM IMERG"]
    assert len(gpm) == 1 and gpm[0]["status"] == "partial"


@pytest.mark.parametrize("start,end", [("2025-02-30", "2025-03-01"), ("2025-02-01", "2025-01-01"),
                                       ("2024-01-01", "2025-01-01"), ("2025-01-01", None),
                                       ("2099-01-01", "2099-01-02")])
def test_bad_date_ranges_are_client_errors(start, end):
    response = TestClient(app).post("/api/analysis/run", json={"start_date": start, "end_date": end})
    assert response.status_code == 400


def test_custom_dates_reach_both_providers_and_fill_plan_calendar(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_SHIFT_LIVE_NASA", "1")
    weather = tuple(w for w in pipeline.generate_weather(2025, 24.75, 90.41, 10, 42) if START <= w.d <= END)
    field = pipeline.build_field(pipeline.load_config(), pipeline.DEFAULT_WEIGHTS)
    with patch.object(pipeline, "power_daily", return_value=weather) as power, \
         patch.object(pipeline, "_load_optional_remote", return_value=()) as satellites, \
         patch.object(pipeline, "nex_gddp_monthly_deltas", return_value=gee.NEXDeltaResult(None, "not_configured")):
        data = pipeline.load_scenarios(field, 2025, tmp_path, [], start_date=START, end_date=END)
    assert power.call_args.args[2:4] == (START, END)
    assert satellites.call_args.args[3:5] == (START, END)
    assert data[0].weather[0].d == START and data[0].weather[-1].d == date(2027, 12, 31)
    assert len(data[0].weather) == 1095


def test_dates_survive_api_what_if_and_report(monkeypatch):
    monkeypatch.setenv("FIELD_SHIFT_LIVE_NASA", "0")
    client = TestClient(app)
    payload = {"start_date": "2025-01-01", "end_date": "2025-01-15", "n_uncertainty_samples": 20, "n_weight_samples": 60}
    response = client.post("/api/analysis/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    run_id = data["run"]["id"]
    window = data["run"]["evidence_window"]
    assert window["start_date"] == "2025-01-01" and window["end_date"] == "2025-01-15"
    assert window["plan_start_year"] == 2025
    from fieldshift.api import product
    product._RUNS.clear()  # Simulate the next request reaching another Vercel instance.
    changed = client.post(f"/api/analysis/{run_id}/what-if", json={"scenario": "dry", "field": data["field"], "evidence_window": window})
    assert changed.status_code == 200
    assert changed.json()["run"]["evidence_window"] == window
    report = client.post(f"/api/analysis/{run_id}/report", json={"data": data}).json()
    assert report["evidence_window"] == window


def test_nex_uses_cached_historical_normals_for_second_scenario(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_SHIFT_GEE_PROJECT", "test-project")
    monkeypatch.setenv("FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON", "mock")
    monkeypatch.setattr(gee, "_initialise_ee", lambda: object())
    old = {"tasmax": 301, "tasmin": 291, "hurs": 70, "pr": 0.0001, "rsds": 150, "sfcWind": 2}
    def month(ee, lat, lon, period, scenario, month):
        return {**old, "tasmax": 303 if period == "future" else 301}
    with patch.object(gee, "_fetch_normal_month", side_effect=month) as fetch:
        first = gee.nex_gddp_monthly_deltas(24.75, 90.41, "ssp245", tmp_path)
        second = gee.nex_gddp_monthly_deltas(24.75, 90.41, "ssp585", tmp_path)
    assert fetch.call_count == 36  # 12 historical + 12 each future scenario.
    assert first.status == second.status == "live"
    assert first.monthly[1]["tasmax_delta_c"] == 2


def test_provider_error_redacts_secrets(monkeypatch):
    monkeypatch.setenv("FIELD_SHIFT_APPEEARS_PASSWORD", "secret-pass")
    value = safe_error(RuntimeError("HTTP 403 secret-pass Bearer abc user@example.com projects/private-project"))
    assert "HTTP 403" in value
    assert not any(x in value for x in ("secret-pass", "abc", "user@example.com", "private-project"))


def test_single_day_is_inclusive():
    assert evidence_dates("2025-01-01", "2025-01-01") == (START, START)


def test_earth_engine_graphs_build_with_official_python_client(monkeypatch, tmp_path):
    import ee
    import ee.apitestcase
    case = ee.apitestcase.ApiTestCase()
    case.setUp()
    try:
        monkeypatch.setenv("FIELD_SHIFT_GEE_PROJECT", "test-project")
        monkeypatch.setenv("FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON", "mock")
        monkeypatch.setattr(gee, "_initialise_ee", lambda: ee)
        graphs = []
        def compute(expression):
            graphs.append(json.dumps(ee.serializer.encode(expression)))
            if isinstance(expression, ee.FeatureCollection):
                return {"features": [{"properties": {"date": "2025-01-01", "gpm_rain_mm": 8, "count": 48}},
                                      {"properties": {"date": "2025-01-02", "gpm_rain_mm": 2, "count": 47}},
                                      {"properties": {"date": "2025-01-03", "gpm_rain_mm": None, "count": 0}}]}
            return {"tasmax": 301, "tasmin": 290, "hurs": 75, "pr": 0.0001, "rsds": 150, "sfcWind": 2}
        monkeypatch.setattr(ee.data, "computeValue", compute)
        rain = gee.gpm_daily_point_timeseries(24.75, 90.41, START, END, tmp_path)
        assert len(rain) == 1 and rain[0].gpm_rain_mm == 8
        normal = gee._fetch_normal_month(ee, 24.75, 90.41, "historical", "ssp245", 1)
        assert normal["tasmax"] == 301
        assert len(graphs) == 2
    finally:
        case.tearDown()



def test_initial_smap_cache_miss_returns_pending_without_live_gee(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_SHIFT_GEE_PROJECT", "test-project")
    monkeypatch.setenv("FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON", "mock")
    monkeypatch.setattr(gee.google_drive, "configured", lambda: False)

    def unexpected_live_query():
        raise AssertionError("The initial cache-only worker attempt must not query Earth Engine")

    monkeypatch.setattr(gee, "_initialise_ee", unexpected_live_query)
    result = gee.smap_daily_point_timeseries(
        24.75, 90.41, date(2025, 1, 1), date(2025, 1, 10), tmp_path,
        allow_live_query=False,
    )
    assert result.status == "pending"
    assert result.rows == ()
    assert result.retry_after_seconds == 900
    assert result.retrieval_mode == "cache_miss"
    assert result.chunk_count == 1


def test_smap_gee_daily_values_require_all_eight_intervals(monkeypatch, tmp_path):
    import ee
    import ee.apitestcase

    case = ee.apitestcase.ApiTestCase()
    case.setUp()
    try:
        monkeypatch.setenv("FIELD_SHIFT_GEE_PROJECT", "test-project")
        monkeypatch.setenv("FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON", "mock")
        monkeypatch.setattr(gee, "_initialise_ee", lambda: ee)
        monkeypatch.setattr(gee.google_drive, "configured", lambda: False)
        graphs = []

        def compute(expression):
            graphs.append(json.dumps(ee.serializer.encode(expression)))
            return {
                "features": [
                    {"properties": {
                        "date": "2025-01-01", "sm_surface": 0.24,
                        "sm_rootzone": 0.31, "n_surface": 8, "n_rootzone": 8,
                    }},
                    {"properties": {
                        "date": "2025-01-02", "sm_surface": 0.28,
                        "sm_rootzone": 0.35, "n_surface": 8, "n_rootzone": 7,
                    }},
                ]
            }

        monkeypatch.setattr(ee.data, "computeValue", compute)
        result = gee.smap_daily_point_timeseries(24.75, 90.41, date(2025, 1, 1), date(2025, 1, 2), tmp_path)

        assert result.status == "partial"
        assert result.coverage_fraction == 0.5
        assert len(result.rows) == 1
        assert result.rows[0].smap_surface_m3_m3 == pytest.approx(0.24)
        assert result.rows[0].smap_rootzone_m3_m3 == pytest.approx(0.31)
        assert "8 intervals" in result.rows[0].provenance.temporal_resolution
        assert len(graphs) == 1
    finally:
        case.tearDown()


def test_partial_smap_year_is_not_archived_or_reused_as_a_complete_cache(monkeypatch, tmp_path):
    import hashlib

    import ee
    import ee.apitestcase

    case = ee.apitestcase.ApiTestCase()
    case.setUp()
    objects: dict[str, bytes] = {}
    calls = []
    writes = []
    try:
        monkeypatch.setenv("FIELD_SHIFT_GEE_PROJECT", "test-project")
        monkeypatch.setenv("FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON", "mock")
        monkeypatch.setattr(gee, "_initialise_ee", lambda: ee)
        monkeypatch.setattr(gee.google_drive, "configured", lambda: True)
        monkeypatch.setattr(gee.google_drive, "get_object", lambda key: objects.get(key))

        def put_object(key: str, content: bytes, *, sha256: str | None = None, mime_type: str = "application/json"):
            writes.append(key)
            assert sha256 == hashlib.sha256(content).hexdigest()
            objects[key] = content
            return {"id": key}

        monkeypatch.setattr(gee.google_drive, "put_object", put_object)

        def compute(expression):
            calls.append(ee.serializer.encode(expression))
            if len(calls) == 1:
                features = [
                    {"properties": {
                        "date": "2025-01-01", "sm_surface": 0.24,
                        "sm_rootzone": 0.31, "n_surface": 8, "n_rootzone": 8,
                    }},
                    {"properties": {
                        "date": "2025-01-02", "sm_surface": 0.28,
                        "sm_rootzone": 0.35, "n_surface": 8, "n_rootzone": 7,
                    }},
                ]
            else:
                features = [
                    {"properties": {
                        "date": "2025-01-01", "sm_surface": 0.24,
                        "sm_rootzone": 0.31, "n_surface": 8, "n_rootzone": 8,
                    }},
                    {"properties": {
                        "date": "2025-01-02", "sm_surface": 0.28,
                        "sm_rootzone": 0.35, "n_surface": 8, "n_rootzone": 8,
                    }},
                ]
            return {"features": features}

        monkeypatch.setattr(ee.data, "computeValue", compute)
        first = gee.smap_daily_point_timeseries(
            24.75, 90.41, date(2025, 1, 1), date(2025, 1, 2), tmp_path,
        )
        assert first.status == "partial"
        assert first.archive_cache_status == "not_configured"
        assert not writes

        # The stale local partial cache must not suppress another live query.
        second = gee.smap_daily_point_timeseries(
            24.75, 90.41, date(2025, 1, 1), date(2025, 1, 2), tmp_path,
        )
        assert second.status == "available"
        assert len(second.rows) == 2
        assert len(calls) == 2
        assert not writes
    finally:
        case.tearDown()


def test_smap_gee_completed_result_is_verified_in_drive_and_reused(monkeypatch, tmp_path):
    import hashlib

    import ee
    import ee.apitestcase

    case = ee.apitestcase.ApiTestCase()
    case.setUp()
    objects: dict[str, bytes] = {}
    try:
        monkeypatch.setenv("FIELD_SHIFT_GEE_PROJECT", "test-project")
        monkeypatch.setenv("FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON", "mock")
        monkeypatch.setattr(gee, "_initialise_ee", lambda: ee)
        monkeypatch.setattr(gee.google_drive, "configured", lambda: True)
        monkeypatch.setattr(gee.google_drive, "get_object", lambda key: objects.get(key))

        def put_object(key: str, content: bytes, *, sha256: str | None = None, mime_type: str = "application/json"):
            assert sha256 == hashlib.sha256(content).hexdigest()
            objects[key] = content
            return {"id": key}

        monkeypatch.setattr(gee.google_drive, "put_object", put_object)
        calls = []

        def compute(expression):
            calls.append(ee.serializer.encode(expression))
            year_start = date(2025, 1, 1)
            return {"features": [
                {"properties": {
                    "date": date.fromordinal(year_start.toordinal() + offset).isoformat(),
                    "sm_surface": 0.27,
                    "sm_rootzone": 0.36,
                    "n_surface": 8,
                    "n_rootzone": 8,
                }}
                for offset in range(365)
            ]}

        monkeypatch.setattr(ee.data, "computeValue", compute)
        first = gee.smap_daily_point_timeseries(24.75, 90.41, date(2025, 1, 1), date(2025, 1, 1), tmp_path / "first")
        assert first.status == "available"
        assert first.archive_cache_status == "verified"
        assert first.archive_sha256
        assert len(objects) == 1

        def no_earth_engine():
            raise AssertionError("A verified shared SMAP cache hit must not query Earth Engine")

        monkeypatch.setattr(gee, "_initialise_ee", no_earth_engine)
        second = gee.smap_daily_point_timeseries(24.75, 90.41, date(2025, 1, 1), date(2025, 1, 1), tmp_path / "cold")
        assert second.status == "available"
        assert second.retrieval_mode == "google_drive_cache"
        assert second.archive_cache_status == "verified"
        assert second.rows[0].smap_surface_m3_m3 == pytest.approx(0.27)
        assert len(calls) == 1
    finally:
        case.tearDown()


def test_nex_pending_can_resume_cached_months(monkeypatch, tmp_path):
    monkeypatch.setenv("FIELD_SHIFT_GEE_PROJECT", "test-project")
    monkeypatch.setenv("FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON", "mock")
    monkeypatch.setattr(gee, "_initialise_ee", lambda: object())
    old = {"tasmax": 301, "tasmin": 291, "hurs": 70, "pr": 0.0001, "rsds": 150, "sfcWind": 2}
    key = gee._cache_path(tmp_path, 24.75, 90.41, "historical").stem
    gee._write_cache(tmp_path / f"{key}_historical_01.json", {"normal": old})
    times = iter([0] + [100] * 30)
    with patch.object(gee.time, "monotonic", side_effect=lambda: next(times)):
        pending = gee.nex_gddp_monthly_deltas(24.75, 90.41, "ssp245", tmp_path)
    assert pending.status == "pending" and "1/24" in pending.error
    with patch.object(gee, "_fetch_normal_month", return_value=old) as fetch:
        completed = gee.nex_gddp_monthly_deltas(24.75, 90.41, "ssp245", tmp_path)
    assert completed.status == "live" and fetch.call_count == 23
