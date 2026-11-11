from __future__ import annotations

from pathlib import Path

import yaml


def test_power_history_backfill_is_one_time_main_trigger_plus_manual_and_resumable() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "history-backfill.yml"
    )
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert set(workflow["on"]) == {"push", "workflow_dispatch"}
    push = workflow["on"]["push"]
    assert push["branches"] == ["main"]
    assert push["paths"] == [".github/history-backfill-once.trigger"]

    # Manual dispatch remains a small completed-year pilot by default.
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert inputs["start_year"]["default"] == "2025"
    assert inputs["end_year"]["default"] == "2025"

    preflight = workflow["jobs"]["preflight"]["steps"]
    credentials = next(
        step for step in preflight
        if step.get("name") == "Validate branch, credentials, folder access and year window"
    )
    assert "feat/krishinexus-real-data-school-lab" in credentials["run"]
    assert "Wrong branch" in credentials["run"]
    for name in (
        "GOOGLE_DRIVE_CLIENT_ID",
        "GOOGLE_DRIVE_CLIENT_SECRET",
        "GOOGLE_DRIVE_REFRESH_TOKEN",
        "GOOGLE_DRIVE_FOLDER_ID",
    ):
        assert name in credentials["env"][name]
    assert "No NASA data request was started." in credentials["run"]
    assert "scripts/google_drive_archive.py verify" in credentials["run"]
    assert "github.event_name == 'workflow_dispatch' && github.event.inputs.start_year || 2016" in credentials["env"]["START_YEAR"]
    assert "github.event_name == 'workflow_dispatch' && github.event.inputs.end_year || 2025" in credentials["env"]["END_YEAR"]

    marker = Path(__file__).resolve().parents[1] / ".github" / "history-backfill-once.trigger"
    assert marker.exists()
    assert "2016–2025" in marker.read_text(encoding="utf-8")

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


def test_smap_reference_backfill_is_manual_pilot_first_and_gee_verified() -> None:
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "smap-reference-backfill.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert set(workflow["on"]) == {"workflow_dispatch"}
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    # Default to a one-year pilot; ten-year backfill must be an explicit choice.
    assert inputs["start_year"]["default"] == "2025"
    assert inputs["end_year"]["default"] == "2025"

    preflight = workflow["jobs"]["preflight"]
    assert preflight["timeout-minutes"] == "8"
    step = next(
        item for item in preflight["steps"]
        if item.get("name") == "Validate branch, year window, credentials and Drive access"
    )
    for name in (
        "GOOGLE_DRIVE_CLIENT_ID", "GOOGLE_DRIVE_CLIENT_SECRET",
        "GOOGLE_DRIVE_REFRESH_TOKEN", "GOOGLE_DRIVE_FOLDER_ID",
        "FIELD_SHIFT_GEE_PROJECT", "FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON",
    ):
        assert name in step["env"]
    assert "feat/krishinexus-real-data-school-lab" in step["run"]
    assert "scripts/verify_smap_archive_prerequisites.py" in step["run"]
    assert "No NASA request was started." in step["run"]

    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_smap_archive_prerequisites.py"
    source = script.read_text(encoding="utf-8")
    compile(source, str(script), "exec")
    assert "verify_storage()" in source
    assert "_initialise_ee()" in source
    assert "NASA/SMAP/SPL4SMGP/008" in source
    assert "No daily SMAP time series were fetched" in source

    ingest = workflow["jobs"]["ingest"]
    assert ingest["needs"] == "preflight"
    assert ingest["strategy"]["max-parallel"] == "3"
    assert len(ingest["strategy"]["matrix"]["region"]) == 9
    publish = next(
        item for item in ingest["steps"]
        if item.get("name") == "Fetch, QA and publish each completed SMAP year"
    )
    assert "scripts/prefetch_smap_points.py" in publish["run"]
    assert "--refresh" not in publish["run"]


def test_history_refresh_is_google_drive_gated_and_never_uses_aws() -> None:
    path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "history-refresh.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert "GOOGLE_DRIVE_ARCHIVE_ENABLED" in str(workflow)
    assert "scripts/google_drive_archive.py verify" in str(workflow)
    assert "FIELD_SHIFT_ARCHIVE_S3_BUCKET" not in str(workflow)
    assert "AWS_ROLE_ARN" not in str(workflow)
