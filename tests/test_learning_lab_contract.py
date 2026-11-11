from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from fieldshift.api.app import app

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "school-game"


def test_learning_lab_loads_the_active_assets() -> None:
    page = (LAB / "index.html").read_text(encoding="utf-8")
    assert '/school-game/app.js' in page
    assert '/school-game/style.css' in page


def test_learning_lab_script_only_uses_elements_present_in_the_page() -> None:
    page = (LAB / "index.html").read_text(encoding="utf-8")
    script = (LAB / "app.js").read_text(encoding="utf-8")
    page_ids = set(re.findall(r'id="([^"]+)"', page))
    script_ids = set(re.findall(r'\$\("([^"]+)"\)', script))
    assert script_ids <= page_ids, f"Learning Lab script references missing page IDs: {sorted(script_ids - page_ids)}"


def test_learning_lab_keeps_missing_metrics_distinct_from_zero() -> None:
    script = (LAB / "app.js").read_text(encoding="utf-8")
    assert "present(quality.coverage_fraction)" in script
    assert 'Number(quality.coverage_fraction||0)' not in script
    assert "pct(s.top1_probability)" in script


def test_learning_lab_styles_match_the_page_layout() -> None:
    page = (LAB / "index.html").read_text(encoding="utf-8")
    css = (LAB / "style.css").read_text(encoding="utf-8")
    page_classes = {
        token
        for value in re.findall(r'class="([^"]+)"', page)
        for token in value.split()
    }
    required_classes = {"shell", "hero", "panel", "heading", "grid", "field", "form-footer", "result-grid"}
    required_ids = {"quality"}
    assert required_classes <= page_classes
    assert required_ids <= set(re.findall(r'id="([^"]+)"', page))
    for name in required_classes:
        assert f".{name}" in css, f"Missing CSS selector for .{name}"
    for name in required_ids:
        assert f"#{name}" in css, f"Missing CSS selector for #{name}"


def test_learning_lab_analysis_submit_returns_live_v3_strategies(monkeypatch) -> None:
    monkeypatch.setenv("FIELD_SHIFT_LIVE_NASA", "0")
    client = TestClient(app)
    response = client.post(
        "/api/analysis/run",
        json={
            "field": {
                "lat": 24.75,
                "lon": 90.41,
                "area_ha": 0.4,
                "land_type": "medium highland",
                "previous_crop": "Rice",
                "soil": {},
                "soil_data_source": "regional-defaults",
                "farmer": {
                    "water_available_mm_season": 900,
                    "irrigation_reliability": 0.8,
                    "budget_bdt_ha": 100000,
                    "labour_available_person_days_ha": 120,
                },
            },
            "priority_choices": ["water"],
            "year": 2026,
            "n_weight_samples": 80,
            "n_uncertainty_samples": 24,
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["run"]["mode"] == "live"
    assert result["run"]["status"] == "preliminary_ready"
    assert result["run"]["is_final"] is False
    assert result["run"]["prediction_eligible"] is False
    assert result["field"]["location"]["lat"] == 24.75
    assert result["field"]["area_ha"] == 0.4
    assert result["strategies"]
    assert result["evidence"]["items"]
