from __future__ import annotations

from pathlib import Path

import yaml


def test_power_history_backfill_is_manual_gated_and_resumable() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "history-backfill.yml"
    )
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert set(workflow["on"]) == {"workflow_dispatch"}
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["start_year"]["default"] == "2016"
    assert inputs["end_year"]["default"] == "2025"

    assert workflow["permissions"]["id-token"] == "write"
    jobs = workflow["jobs"]
    preflight = jobs["preflight"]["steps"][0]
    assert "FIELD_SHIFT_ARCHIVE_S3_BUCKET" in preflight["env"]["ARCHIVE_BUCKET"]
    assert "AWS_ROLE_ARN" in preflight["env"]["AWS_ROLE_ARN"]
    assert "No NASA data request was started." in preflight["run"]

    ingest = jobs["ingest"]
    assert ingest["needs"] == "preflight"
    assert ingest["strategy"]["max-parallel"] == "3"
    assert set(ingest["strategy"]["matrix"]["region"]) == {
        "mymensingh",
        "dhaka",
        "rajshahi",
        "rangpur",
        "khulna",
        "barishal",
        "sylhet",
        "chattogram",
        "rangamati",
    }
    steps = ingest["steps"]
    assert any(step.get("uses") == "aws-actions/configure-aws-credentials@v4" for step in steps)
    ingest_step = next(step for step in steps if step.get("name") == "Fetch, quality-check and publish completed daily years")
    assert "scripts/prefetch_history.py" in ingest_step["run"]
    assert "--refresh" not in ingest_step["run"]
