"""Provider failures seen in the Mymensingh and Iowa deployment screenshots."""
from __future__ import annotations

import io
import json
import time
import urllib.error
from datetime import UTC, datetime
from email.message import Message
from email.utils import format_datetime
from unittest.mock import patch

import pytest
from test_dataset_repairs import END, START, NASAService

from fieldshift.api.product import _evidence_state
from fieldshift.v3 import appeears, gee


@pytest.fixture
def wire(monkeypatch, tmp_path):
    """Exercise real HTTP/error/JSON code, replacing only the remote server."""
    service = NASAService()
    monkeypatch.setenv("FIELD_SHIFT_APPEEARS_USER", "mock-user")
    monkeypatch.setenv("FIELD_SHIFT_APPEEARS_PASSWORD", "mock-password")
    monkeypatch.delenv("FIELD_SHIFT_APPEEARS_TOKEN", raising=False)
    monkeypatch.setenv("FIELD_SHIFT_CACHE_DIR", str(tmp_path / "cooldown"))
    monkeypatch.setattr(appeears, "_NEXT_REQUEST_AT", 0)
    monkeypatch.setattr(appeears, "_MIN_REQUEST_INTERVAL", 0)
    appeears._clear_token()
    clock = [time.time()]
    monkeypatch.setattr(appeears.time, "time", lambda: clock[0])
    failures, calls = {}, []

    def urlopen(request, **kwargs):
        path = request.full_url.removeprefix(appeears.APPEEARS_API)
        method = request.get_method()
        calls.append((path, method))
        if (path, method) in failures:
            code, retry_after = failures.pop((path, method))
            headers = Message()
            if retry_after is not None:
                headers["Retry-After"] = retry_after
            raise urllib.error.HTTPError(request.full_url, code, "test failure", headers,
                                         io.BytesIO(b'{"message":"can only concatenate list (not str) to list"}'))
        if path.startswith("bundle/") and path.count("/") == 2:
            return io.BytesIO(service.download(path))
        data = json.loads(request.data) if request.data and method == "POST" and path != "login" else None
        return io.BytesIO(json.dumps(service.request(path, method=method, payload=data)).encode())

    monkeypatch.setattr(appeears.urllib.request, "urlopen", urlopen)
    return service, failures, calls, clock


@pytest.mark.parametrize("lat,lon", [(24.7471, 90.4203), (41.4594, -93.0862)])
def test_real_adapter_uses_same_valid_task_shape_at_both_locations(wire, tmp_path, lat, lon):
    service, _, calls, _ = wire
    result = appeears.appeears_point_timeseries(lat, lon, START, END, cache_dir=tmp_path)
    assert {r["status"] for r in result.datasets} == {"available"}
    assert calls.count(("task", "GET")) == 1
    assert not any("?" in path for path, _ in calls)
    assert len(service.payloads) == 3
    for body in service.payloads:
        assert body["task_type"] == "point"
        assert body["params"]["coordinates"] == [{"id": "field", "category": "field", "latitude": lat, "longitude": lon}]
        assert body["params"]["dates"] == [{"startDate": "01-01-2025", "endDate": "01-15-2025"}]


@pytest.mark.parametrize("code,delay", [(429, 120), (500, 30)])
def test_temporary_failure_honors_cooldown_and_later_recovers(wire, tmp_path, code, delay):
    service, failures, calls, clock = wire
    failures[("task", "GET")] = code, "120" if code == 429 else None
    result = appeears.appeears_point_timeseries(24.7471, 90.4203, START, END, cache_dir=tmp_path)
    assert {r["status"] for r in result.datasets} == {"retrying"}
    assert all(r["request_stage"] == "task-list" and r["http_status"] == code for r in result.datasets)
    assert result.datasets[0]["retry_after_seconds"] == delay
    before = len(calls)
    appeears.appeears_point_timeseries(41.4594, -93.0862, START, END, cache_dir=tmp_path)
    assert len(calls) == before  # Even a different field shares the account cooldown.
    assert not service.payloads
    clock[0] += delay + 1
    recovered = appeears.appeears_point_timeseries(24.7471, 90.4203, START, END, cache_dir=tmp_path)
    assert {r["status"] for r in recovered.datasets} == {"available"}
    assert len(service.payloads) == 3


def test_post_500_is_not_immediately_resubmitted(wire):
    _, failures, calls, _ = wire
    failures[("task", "POST")] = 500, None
    with pytest.raises(appeears.AppEEARSRetryableError) as failed:
        appeears._safe_json_request("task", method="POST", token="mock", payload={"task_type": "point"})
    assert failed.value.stage == "task-submission"
    assert calls == [("task", "POST")]


def test_bundle_download_429_uses_the_same_retry_policy(wire):
    _, failures, calls, _ = wire
    failures[("bundle/smap/smap", "GET")] = 429, "90"
    with pytest.raises(appeears.AppEEARSRetryableError) as failed:
        appeears._download("bundle/smap/smap", "mock")
    assert failed.value.stage == "file-download"
    assert failed.value.retry_after_seconds == 90
    assert len(calls) == 1


def test_retry_after_http_date_and_bad_header(wire):
    _, _, _, clock = wire
    header = format_datetime(datetime.fromtimestamp(int(clock[0]) + 90, UTC), usegmt=True)
    assert 89 <= appeears._retry_delay(header, 60) <= 90
    assert appeears._retry_delay("invalid", 60) == 60


def test_requests_are_paced_across_products(wire, monkeypatch):
    monkeypatch.setattr(appeears, "_MIN_REQUEST_INTERVAL", 1)
    with patch.object(appeears.time, "monotonic", return_value=100), patch.object(appeears.time, "sleep") as sleep:
        appeears._safe_json_request("product", token="mock")
        appeears._safe_json_request("product/SPL4SMGP.008", token="mock")
    sleep.assert_called_once_with(1)


def test_retry_details_survive_the_website_response():
    item = _evidence_state([{
        "name": "NASA SMAP",
        "status": "retrying",
        "http_status": 429,
        "request_stage": "task-list",
        "retry_after_seconds": 120,
        "provider_task_id": "appeears-task-123",
    }], 0)["items"][0]
    assert item["retry_after_seconds"] == 120
    assert item["http_status"] == 429
    assert item["request_stage"] == "task-list"
    assert item["provider_task_id"] == "appeears-task-123"


def test_nex_timeout_resumes_only_missing_month_at_iowa_coordinate(monkeypatch, tmp_path):
    monkeypatch.setattr(gee, "gee_credentials_configured", lambda: True)
    monkeypatch.setattr(gee, "_initialise_ee", lambda: object())
    normal = {"tasmax": 301, "tasmin": 291, "hurs": 70, "pr": 0.0001, "rsds": 150, "sfcWind": 2}

    def fetch(ee, lat, lon, period, scenario, month):
        if period == "future" and month == 5:
            raise TimeoutError("Read timed out. (read timeout=20.0)")
        return normal

    with patch.object(gee, "_fetch_normal_month", side_effect=fetch):
        first = gee.nex_gddp_monthly_deltas(41.4594, -93.0862, "ssp245", tmp_path)
    assert first.status == "retrying" and first.monthly is None
    assert "23/24" in first.error and first.retry_after_seconds == 60
    with patch.object(gee, "_fetch_normal_month", return_value=normal) as resumed:
        second = gee.nex_gddp_monthly_deltas(41.4594, -93.0862, "ssp245", tmp_path)
    assert second.status == "live"
    assert resumed.call_count == 1 and resumed.call_args.args[-1] == 5


def test_nex_missing_bands_remain_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(gee, "gee_credentials_configured", lambda: True)
    with patch.object(gee, "_fetch_monthly_normals", side_effect=ValueError("missing usable bands")):
        result = gee.nex_gddp_monthly_deltas(41.4594, -93.0862, "ssp245", tmp_path)
    assert result.status == "unavailable" and result.retry_after_seconds is None
