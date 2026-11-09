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
    assert captured["mime_type"] == "application/json"


def test_large_drive_upload_uses_resumable_session(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, str]]] = []

    def fake_request(method: str, url: str, *, body=None, headers=None):
        calls.append((method, url, dict(headers or {})))
        if method == "POST":
            return b"", {"Location": "https://upload.example/session"}
        return b'{"id":"large-file","name":"large.json"}', {}

    monkeypatch.setattr(google_drive, "_auth_request", fake_request)
    result = google_drive._upload(
        file_id=None,
        parent_id="root",
        name="large.json",
        content=b"x" * (5 * 1024 * 1024 + 1),
        mime_type="text/csv",
    )
    assert result["id"] == "large-file"
    assert len(calls) == 2
    assert calls[0][0] == "POST"
    assert "uploadType=resumable" in calls[0][1]
    assert calls[1][0] == "PUT"
    assert calls[1][1] == "https://upload.example/session"
    assert calls[0][2]["X-Upload-Content-Type"] == "text/csv"
    assert calls[1][2]["Content-Type"] == "text/csv"
    assert calls[1][2]["Content-Length"] == str(5 * 1024 * 1024 + 1)
