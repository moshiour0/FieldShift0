from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from fieldshift.v3 import history, history_extended


def test_completed_local_archive_is_published_to_drive_without_provider_fetch(
    monkeypatch, tmp_path: Path,
) -> None:
    local_file = tmp_path / "2025.json"
    local_file.write_bytes(b'{"validated":"local archive"}')
    remote: dict[str, bytes | None] = {"content": None}
    metadata = {"sha256": "validated-digest", "year": 2025}
    uploads: list[tuple[str, bytes]] = []

    monkeypatch.setattr(history, "_path", lambda region_id, year: local_file)
    monkeypatch.setattr(history.google_drive, "configured", lambda: True)
    monkeypatch.setattr(history.google_drive, "get_object", lambda key: remote["content"])
    monkeypatch.setattr(history, "read_year", lambda region_id, year: ((), metadata))
    monkeypatch.setattr(
        history, "_decode_year_payload", lambda region_id, year, raw: ((), metadata)
    )

    def upload(key: str, content: bytes, *, sha256: str | None = None) -> dict:
        uploads.append((key, content))
        remote["content"] = content
        return {"id": "drive-object"}

    monkeypatch.setattr(history.google_drive, "put_object", upload)

    result = history.prefetch_year("mymensingh", 2025)

    assert result["retrieval_mode"] == "local_archive_published"
    assert result["drive_readback_verified"] is True
    assert uploads == [("power-history/mymensingh/2025.json", local_file.read_bytes())]


def test_current_year_local_ytd_archive_is_published_to_drive_without_provider_fetch(
    monkeypatch, tmp_path: Path,
) -> None:
    through = date.today() - timedelta(days=5)
    local_file = tmp_path / f"{through.year}-ytd.json"
    local_file.write_bytes(b'{"validated":"local ytd archive"}')
    remote: dict[str, bytes | None] = {"content": None}
    metadata = {"sha256": "validated-ytd-digest", "data_through": through.isoformat()}
    uploads: list[tuple[str, bytes]] = []

    monkeypatch.setattr(history_extended, "_ytd_path", lambda region_id, year: local_file)
    monkeypatch.setattr(history_extended.google_drive, "configured", lambda: True)
    monkeypatch.setattr(history_extended.google_drive, "get_object", lambda key: remote["content"])
    monkeypatch.setattr(history_extended, "read_ytd", lambda region_id, year: ((), metadata))

    def upload(key: str, content: bytes) -> dict:
        uploads.append((key, content))
        remote["content"] = content
        return {"id": "drive-object"}

    monkeypatch.setattr(history_extended.google_drive, "put_object", upload)

    result = history_extended.prefetch_ytd("mymensingh", through)

    assert result["retrieval_mode"] == "local_archive_published"
    assert uploads == [
        (f"power-history/mymensingh/{through.year}-ytd.json", local_file.read_bytes())
    ]



def test_completed_local_archive_fails_when_drive_readback_is_missing(
    monkeypatch, tmp_path: Path,
) -> None:
    local_file = tmp_path / "2025.json"
    local_file.write_bytes(b'{"validated":"local archive"}')
    uploads: list[tuple[str, bytes]] = []
    metadata = {"sha256": "validated-digest", "year": 2025}

    monkeypatch.setattr(history, "_path", lambda region_id, year: local_file)
    monkeypatch.setattr(history.google_drive, "configured", lambda: True)
    monkeypatch.setattr(history.google_drive, "get_object", lambda key: None)
    monkeypatch.setattr(history, "read_year", lambda region_id, year: ((), metadata))

    def upload(key: str, content: bytes, *, sha256: str | None = None) -> dict:
        uploads.append((key, content))
        # Simulate an API write response without a readable persisted object.
        return {"id": "drive-object"}

    monkeypatch.setattr(history.google_drive, "put_object", upload)

    with pytest.raises(history.NasaDataError, match="remote read-back"):
        history.prefetch_year("mymensingh", 2025)

    assert uploads == [("power-history/mymensingh/2025.json", local_file.read_bytes())]
