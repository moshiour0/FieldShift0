from __future__ import annotations

import hashlib

import pytest

from fieldshift.v3 import google_drive


def test_drive_configuration_requires_all_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    names = (
        "GOOGLE_DRIVE_CLIENT_ID",
        "GOOGLE_DRIVE_CLIENT_SECRET",
        "GOOGLE_DRIVE_REFRESH_TOKEN",
        "GOOGLE_DRIVE_FOLDER_ID",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    assert not google_drive.configured()
    for name in names:
        monkeypatch.setenv(name, "test")
    assert google_drive.configured()


@pytest.mark.parametrize(
    "key",
    ["", "/a.json", "../escape.json", "a//b.json", "a/./b.json", "a/../b.json"],
)
def test_drive_archive_rejects_unsafe_keys(key: str) -> None:
    with pytest.raises(ValueError):
        google_drive._parts(key)


def test_drive_archive_key_is_relative_and_nested() -> None:
    assert google_drive._parts("power-history/dhaka/2025.json") == [
        "power-history", "dhaka", "2025.json",
    ]


def test_drive_sha256_check_happens_before_api_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "root")
    monkeypatch.setattr(google_drive, "_resolve_parent", lambda parts, create: "region")
    monkeypatch.setattr(google_drive, "_child", lambda *args, **kwargs: None)
    body = b'{"days":[]}'
    with pytest.raises(ValueError, match="SHA-256"):
        google_drive.put_object("power-history/dhaka/2025.json", body, sha256="0" * 64)


def test_drive_query_escape() -> None:
    assert google_drive._escape_query("folder'name") == "folder\\'name"


def test_drive_upload_updates_existing_file_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "root")
    monkeypatch.setattr(google_drive, "_resolve_parent", lambda parts, create: "region")
    monkeypatch.setattr(google_drive, "_child", lambda *args, **kwargs: {"id": "existing"})
    captured: dict[str, object] = {}

    def fake_upload(**kwargs):
        captured.update(kwargs)
        return {"id": kwargs["file_id"], "name": kwargs["name"]}

    monkeypatch.setattr(google_drive, "_upload", fake_upload)
    data = b'{"ok":true}'
    google_drive.put_object(
        "power-history/dhaka/2025.json",
        data,
        sha256=hashlib.sha256(data).hexdigest(),
    )
    assert captured["file_id"] == "existing"
