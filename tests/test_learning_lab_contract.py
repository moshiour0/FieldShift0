from __future__ import annotations

import re
from pathlib import Path

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
    required_classes = {"shell", "hero", "panel", "heading", "grid", "field", "form-footer", "result-grid", "quality"}
    assert required_classes <= page_classes
    for name in required_classes:
        assert f".{name}" in css, f"Missing CSS selector for .{name}"
