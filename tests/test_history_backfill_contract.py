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

    preflight = workflow["jobs"]["preflight"]["steps"]
    credentials = next(
        step for step in preflight
        if step.get("name") == "Validate credentials, folder access and year window"
    )
    for name in (
        "GOOGLE_DRIVE_CLIENT_ID",
        "GOOGLE_DRIVE_CLIENT_SECRET",
        "GOOGLE_DRIVE_REFRESH_TOKEN",
        "GOOGLE_DRIVE_FOLDER_ID",
    ):
        assert name in credentials["env"][name]
    assert "No NASA data request was started." in credentials["run"]
    assert "scripts/google_drive_archive.py verify" in credentials["run"]

    ingest = workflow["jobs"]["ingest"]
    assert ingest["needs"] == "preflight"
    assert ingest["strategy"]["max-parallel"] == "3"
    assert set(ingest["strategy"]["matrix"]["region"]) == {
        "mymensingh", "dhaka", "rajshahi", "rangpur", "khulna",
        "barishal", "sylhet", "chattogram", "rangamati",
    }
    publish = next(
        step for step in ingest["steps"]
        if step.get("name") == "Fetch, quality-check and publish completed daily years"
    )
    assert "scripts/prefetch_history.py" in publish["run"]
    assert "--refresh" not in publish["run"]
    assert "FIELD_SHIFT_ARCHIVE_S3_BUCKET" not in str(workflow)


def test_history_refresh_is_google_drive_gated_and_never_uses_aws() -> None:
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "history-refresh.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert "GOOGLE_DRIVE_ARCHIVE_ENABLED" in str(workflow)
    assert "scripts/google_drive_archive.py verify" in str(workflow)
    assert "FIELD_SHIFT_ARCHIVE_S3_BUCKET" not in str(workflow)
    assert "AWS_ROLE_ARN" not in str(workflow)
