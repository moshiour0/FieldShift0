"""One-time Google Drive OAuth bootstrap. Run locally; never commit credentials."""
from __future__ import annotations

import getpass
import json
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fieldshift.v3.google_drive import API, FOLDER_MIME  # noqa: E402

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/drive.file"


class OAuthCallback(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        self.server.state = query.get("state", [""])[0]  # type: ignore[attr-defined]
        self.server.code = query.get("code", [""])[0]  # type: ignore[attr-defined]
        self.server.error = query.get("error", [""])[0]  # type: ignore[attr-defined]
        message = "Authorization received. Return to the terminal." if self.server.code else "Authorization failed."
        body = f"<html><body><h2>{message}</h2></body></html>".encode("utf-8")
        self.send_response(200 if self.server.code else 400)  # type: ignore[attr-defined]
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def _exchange(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict[str, Any]:
    form = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Google token exchange failed with HTTP {exc.code}") from exc
    except (urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Google token exchange failed") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Google token exchange returned an invalid response")
    return payload


def _api_call(access_token: str, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{API}/{path}"
    if method == "GET":
        url += "?" + urllib.parse.urlencode(
            {"q": f"name = 'FieldShift0 Archive' and mimeType = '{FOLDER_MIME}' and trashed = false",
             "spaces": "drive", "pageSize": "100", "fields": "files(id,name)"}
        )
    body = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"Authorization": f"Bearer {access_token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Google Drive folder setup failed with HTTP {exc.code}") from exc
    data = json.loads(raw.decode("utf-8")) if raw else {}
    if not isinstance(data, dict):
        raise RuntimeError("Google Drive returned an invalid folder response")
    return data


def main() -> int:
    print("FieldShift0: Google Drive private archive setup")
    print("In Google Cloud, enable Google Drive API and create an OAuth Client ID of type Desktop app.")
    client_id = input("OAuth Client ID: ").strip()
    client_secret = getpass.getpass("OAuth Client Secret (hidden): ").strip()
    if not client_id or not client_secret:
        print("Both OAuth client values are required.", file=sys.stderr)
        return 2

    server = HTTPServer(("127.0.0.1", 0), OAuthCallback)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}"
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    print("\nOpening Google authorization page. Authorize the account with the 5 TB Drive storage.")
    print("If your browser does not open, copy this URL:\n" + auth_url)
    webbrowser.open(auth_url)
    server.timeout = 300
    server.handle_request()
    callback_state = getattr(server, "state", "")
    code = getattr(server, "code", "")
    error = getattr(server, "error", "")
    server.server_close()
    if error or not code or callback_state != state:
        print("OAuth authorization was cancelled, timed out, or failed state validation.", file=sys.stderr)
        return 2

    tokens = _exchange(client_id, client_secret, code, redirect_uri)
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    if not refresh_token or not access_token:
        print("Google did not issue an offline refresh token. Revoke the prior app grant and run again.", file=sys.stderr)
        return 2

    existing = _api_call(str(access_token), "GET", "files")
    folders = existing.get("files", [])
    if len(folders) > 1:
        print("Multiple app-visible FieldShift0 Archive folders exist. Resolve duplicates first.", file=sys.stderr)
        return 2
    if folders:
        folder_id = folders[0].get("id")
    else:
        created = _api_call(
            str(access_token),
            "POST",
            "files",
            {"name": "FieldShift0 Archive", "mimeType": FOLDER_MIME},
        )
        folder_id = created.get("id")
    if not folder_id:
        print("Google Drive did not return an archive folder ID.", file=sys.stderr)
        return 2

    print("\nGoogle Drive authorization and private archive folder setup completed.")
    print("Add these values to GitHub Actions Secrets and Vercel Environment Variables:")
    print("\nGOOGLE_DRIVE_CLIENT_ID=" + client_id)
    print("GOOGLE_DRIVE_CLIENT_SECRET=<the Client Secret you entered>")
    print("GOOGLE_DRIVE_REFRESH_TOKEN=" + str(refresh_token))
    print("GOOGLE_DRIVE_FOLDER_ID=" + str(folder_id))
    print("\nDo not send these credentials in chat or commit them to Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
