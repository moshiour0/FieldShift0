from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from fieldshift.api.app import app
from fieldshift.v3.history import history_summary
from fieldshift.v3.history_extended import history_date_range
from fieldshift.v3.region_catalog import zone_catalog
from fieldshift.v3.satellite_archive import satellite_history


def test_zone_catalog_is_explicitly_provisional() -> None:
    result = zone_catalog()
    assert result["status"] == "provisional_no_polygons"
    assert len(result["zones"]) == 12
    assert all(not zone["polygon_available"] for zone in result["zones"])
    assert all(not zone["official_aez_crosswalk_verified"] for zone in result["zones"])


def test_mymensingh_compact_power_history_is_chart_only() -> None:
    result = history_summary("mymensingh", 2016, 2025)
    assert result["status"] == "summary_only"
    assert result["archive_representation"] == "monthly_aggregate"
    assert len(result["annual"]) == 10
    assert result["annual"][0]["year"] == 2016
    assert "chart-only" in result["note"].lower()


def test_date_range_never_turns_monthly_aggregate_into_daily_records() -> None:
    result = history_date_range("mymensingh", "2016-01-01", "2025-12-31")
    assert result["status"] == "summary_only"
    assert result["sample_type"] == "monthly_aggregate"
    assert result["archive_representation"] == "monthly_aggregate"
    assert result["monthly"]
    assert all(row["archive_representation"] == "monthly_aggregate" for row in result["monthly"])
    assert "daily crop-model inputs" in result["note"]


def test_history_explorer_labels_monthly_summary_days_as_equivalents() -> None:
    page = (Path(__file__).resolve().parents[1] / "src" / "fieldshift" / "api" / "static" / "history.html").read_text(
        encoding="utf-8"
    )
    assert "Days represented by monthly summaries" in page
    assert "not daily observations" in page


def test_satellite_connector_presence_does_not_claim_an_archive(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FIELD_SHIFT_SATELLITE_DIR", str(tmp_path))
    result = satellite_history("mymensingh", "hls")
    assert result["status"] == "not_archived"
    assert result["monthly"] == []


def test_regional_api_reports_archive_and_missing_satellites() -> None:
    client = TestClient(app)
    regions = client.get("/api/regions")
    assert regions.status_code == 200
    assert len(regions.json()["reference_points"]) == 9

    history = client.get("/api/history/mymensingh?start_year=2016&end_year=2025")
    assert history.status_code == 200
    assert history.json()["archive_representation"] == "monthly_aggregate"

    status = client.get("/api/data-status/mymensingh")
    assert status.status_code == 200
    products = status.json()["products"]
    assert products["power"]["state"] == "summary_only"
    assert products["hls"]["state"] == "not_archived"
    assert products["smap"]["state"] == "not_archived"
