"""Private Google Drive object storage adapter using the Drive API v3.

OAuth uses the non-sensitive drive.file scope. Only files created by this
application are visible to the adapter. No Drive file is made public.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
TOKEN_API = "https://oauth2.googleapis.com/token"
FOLDER_MIME = "application/vnd.google-apps.folder"
_TOKEN: str | None = None
_TOKEN_EXPIRY = 0.0
_FOLDER_IDS: dict[tuple[str, str], str] = {}


class GoogleDriveError(RuntimeError):
    """Drive API, OAuth, quota, or archive error."""


class GoogleDriveNotFound(GoogleDriveError):
    """The requested archive object is absent."""


def configured() -> bool:
    names = (
        "GOOGLE_DRIVE_CLIENT_ID",
        "GOOGLE_DRIVE_CLIENT_SECRET",
        "GOOGLE_DRIVE_REFRESH_TOKEN",
        "GOOGLE_DRIVE_FOLDER_ID",
    )
    return all(os.getenv(name, "").strip() for name in names)


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise GoogleDriveError(f"Missing required Google Drive setting: {name}")
    return value


def _request(
    method: str,
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    last_error: Exception | None = None
    for attempt in range(5):
        req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read(), dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            detail = ""
            try:
                decoded = json.loads(payload.decode("utf-8"))
                error_value = decoded.get("error", {})
                detail = str(error_value.get("message", ""))[:240]
                reason = str(error_value.get("status", "")) + " " + detail
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                reason = ""
            rate_limited = exc.code == 403 and any(
                marker in reason.lower()
                for marker in ("ratelimitexceeded", "userratelimitexceeded", "rate limit exceeded", "too many requests")
            )
            if (exc.code in {429, 500, 502, 503, 504} or rate_limited) and attempt < 4:
                time.sleep(min(32.0, (2**attempt) + random.random()))
                continue
            if exc.code == 404:
                raise GoogleDriveNotFound("Google Drive archive object not found") from exc
            raise GoogleDriveError(f"Google Drive API HTTP {exc.code}: {detail}".rstrip()) from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(min(32.0, (2**attempt) + random.random()))
                continue
    raise GoogleDriveError("Google Drive request failed after five attempts") from last_error


def _token(*, force_refresh: bool = False) -> str:
    global _TOKEN, _TOKEN_EXPIRY
    if not force_refresh and _TOKEN and time.time() < _TOKEN_EXPIRY:
        return _TOKEN
    form = urllib.parse.urlencode(
        {
            "client_id": _env("GOOGLE_DRIVE_CLIENT_ID"),
            "client_secret": _env("GOOGLE_DRIVE_CLIENT_SECRET"),
            "refresh_token": _env("GOOGLE_DRIVE_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    raw, _ = _request(
        "POST",
        TOKEN_API,
        body=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        payload = json.loads(raw.decode("utf-8"))
        _TOKEN = str(payload["access_token"])
        _TOKEN_EXPIRY = time.time() + max(60, int(payload.get("expires_in", 3600)) - 60)
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise GoogleDriveError("Google OAuth did not return a valid access token") from exc
    return _TOKEN


def _auth_request(
    method: str,
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    global _TOKEN, _TOKEN_EXPIRY
    request_headers = dict(headers or {})
    request_headers["Authorization"] = f"Bearer {_token()}"
    try:
        return _request(method, url, body=body, headers=request_headers)
    except GoogleDriveError as exc:
        if "HTTP 401" not in str(exc):
            raise
        _TOKEN = None
        _TOKEN_EXPIRY = 0.0
        request_headers["Authorization"] = f"Bearer {_token(force_refresh=True)}"
        return _request(method, url, body=body, headers=request_headers)


def _url(path: str, params: dict[str, str] | None = None, *, upload: bool = False) -> str:
    base = UPLOAD_API if upload else API
    url = f"{base}/{path.lstrip('/')}"
    return f"{url}?{urllib.parse.urlencode(params)}" if params else url


def _json_api(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json; charset=UTF-8"} if body is not None else {}
    raw, _ = _auth_request(method, _url(path, params), body=body, headers=headers)
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoogleDriveError("Google Drive returned invalid metadata JSON") from exc
    if not isinstance(data, dict):
        raise GoogleDriveError("Google Drive returned an unexpected metadata response")
    return data


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _list_children(parent_id: str, name: str, mime_type: str | None = None) -> list[dict[str, Any]]:
    query = f"'{_escape_query(parent_id)}' in parents and name = '{_escape_query(name)}' and trashed = false"
    if mime_type:
        query += f" and mimeType = '{mime_type}'"
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params = {
            "q": query,
            "spaces": "drive",
            "pageSize": "100",
            "fields": "nextPageToken,files(id,name,mimeType,size,md5Checksum)",
        }
        if page_token:
            params["pageToken"] = page_token
        result = _json_api("GET", "files", params=params)
        batch = result.get("files", [])
        if isinstance(batch, list):
            items.extend(item for item in batch if isinstance(item, dict))
        page_token = result.get("nextPageToken")
        if not page_token:
            return items


def _child(parent_id: str, name: str, mime_type: str | None = None) -> dict[str, Any] | None:
    matches = _list_children(parent_id, name, mime_type)
    if len(matches) > 1:
        raise GoogleDriveError(f"Duplicate archive entries named {name!r}; refusing ambiguous access")
    return matches[0] if matches else None


def _parts(key: str) -> list[str]:
    parts = key.split("/")
    if not key or key.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Archive key must be a safe relative path")
    if any("\x00" in part for part in parts):
        raise ValueError("Archive key contains a null byte")
    return parts


def _folder(parent_id: str, name: str, *, create: bool) -> str | None:
    cache_key = (parent_id, name)
    if cache_key in _FOLDER_IDS:
        return _FOLDER_IDS[cache_key]
    found = _child(parent_id, name, FOLDER_MIME)
    if found:
        folder_id = str(found["id"])
        _FOLDER_IDS[cache_key] = folder_id
        return folder_id
    if not create:
        return None
    payload = _json_api(
        "POST",
        "files",
        payload={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
    )
    created_folder_id = payload.get("id")
    if not created_folder_id:
        raise GoogleDriveError(f"Google Drive did not return the {name!r} folder ID")
    _FOLDER_IDS[cache_key] = str(created_folder_id)
    return str(created_folder_id)


def _resolve_parent(parts: list[str], *, create: bool) -> str | None:
    parent_id = _env("GOOGLE_DRIVE_FOLDER_ID")
    for name in parts:
        folder_id = _folder(parent_id, name, create=create)
        if folder_id is None:
            return None
        parent_id = folder_id
    return parent_id


def get_object(key: str) -> bytes | None:
    parts = _parts(key)
    parent_id = _resolve_parent(parts[:-1], create=False)
    if parent_id is None:
        return None
    item = _child(parent_id, parts[-1])
    if item is None:
        return None
    file_id = item.get("id")
    if not file_id:
        raise GoogleDriveError("Google Drive archive metadata has no file ID")
    raw, _ = _auth_request(
        "GET",
        _url(f"files/{urllib.parse.quote(str(file_id), safe='')}", {"alt": "media"}),
    )
    return raw


def _upload(
    *,
    file_id: str | None,
    parent_id: str,
    name: str,
    content: bytes,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"name": name, "mimeType": "application/json"}
    if file_id is None:
        metadata["parents"] = [parent_id]
    path = "files" if file_id is None else f"files/{urllib.parse.quote(file_id, safe='')}"
    method = "POST" if file_id is None else "PATCH"
    fields = "id,name,size,md5Checksum"
    if len(content) > 5 * 1024 * 1024:
        # Google recommends resumable sessions for files over 5 MB. Use a
        # single complete media PUT for our archive objects; the session URI
        # lets Drive safely identify/retry the upload if the response is lost.
        _, response_headers = _auth_request(
            method,
            _url(path, {"uploadType": "resumable", "fields": fields}, upload=True),
            body=json.dumps(metadata, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "application/json",
                "X-Upload-Content-Length": str(len(content)),
            },
        )
        upload_url = response_headers.get("Location") or response_headers.get("location")
        if not upload_url:
            raise GoogleDriveError("Google Drive did not return a resumable upload URL")
        raw, _ = _auth_request(
            "PUT",
            upload_url,
            body=content,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(content)),
            },
        )
    else:
        boundary = f"fieldshift_{uuid.uuid4().hex}"
        metadata_bytes = json.dumps(metadata, separators=(",", ":")).encode("utf-8")
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode("ascii")
            + metadata_bytes
            + f"\r\n--{boundary}\r\nContent-Type: application/json\r\n\r\n".encode("ascii")
            + content
            + f"\r\n--{boundary}--\r\n".encode("ascii")
        )
        raw, _ = _auth_request(
            method,
            _url(path, {"uploadType": "multipart", "fields": fields}, upload=True),
            body=body,
            headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        )
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoogleDriveError("Google Drive upload returned invalid metadata") from exc
    if not isinstance(result, dict) or not result.get("id"):
        raise GoogleDriveError("Google Drive upload did not return a file ID")
    return result


def put_object(key: str, content: bytes, *, sha256: str | None = None) -> dict[str, Any]:
    parts = _parts(key)
    parent_id = _resolve_parent(parts[:-1], create=True)
    if parent_id is None:
        raise GoogleDriveError("Could not create the archive's parent folder")
    actual_sha = hashlib.sha256(content).hexdigest()
    if sha256 is not None and sha256 != actual_sha:
        raise ValueError("Archive SHA-256 does not match the content being uploaded")
    found = _child(parent_id, parts[-1])
    return _upload(
        file_id=str(found["id"]) if found else None,
        parent_id=parent_id,
        name=parts[-1],
        content=content,
    )


def verify_storage() -> dict[str, str]:
    """Perform a temporary Drive write/read/delete round-trip before ingestion."""
    key = f"_preflight/probe-{uuid.uuid4().hex}.txt"
    marker = f"FieldShift0 Drive preflight {uuid.uuid4().hex}".encode()
    parts = _parts(key)
    parent_id = _resolve_parent(parts[:-1], create=True)
    if parent_id is None:
        raise GoogleDriveError("Could not create Google Drive preflight folder")
    item_id: str | None = None
    try:
        created = _upload(file_id=None, parent_id=parent_id, name=parts[-1], content=marker)
        item_id = str(created["id"])
        raw, _ = _auth_request(
            "GET",
            _url(f"files/{urllib.parse.quote(item_id, safe='')}", {"alt": "media"}),
        )
        if raw != marker:
            raise GoogleDriveError("Google Drive preflight read-back did not match uploaded bytes")
    finally:
        if item_id:
            _auth_request("DELETE", _url(f"files/{urllib.parse.quote(item_id, safe='')}"))
    return {"provider": "google_drive", "status": "ok", "round_trip": "verified"}
