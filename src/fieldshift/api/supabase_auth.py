"""Small, server-side Supabase Auth and Data API adapter.

Only publishable keys are read from configuration. User requests are forwarded with
the caller's access token, so Supabase Auth and RLS remain the authorization source.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class SupabaseAPIError(RuntimeError):
    """Safe error wrapper for Supabase HTTP failures."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def settings() -> dict[str, str | bool]:
    base_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    publishable_key = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
    )
    return {
        "configured": bool(base_url and publishable_key),
        "url": base_url,
        "publishable_key": publishable_key,
    }


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: float = 8.0,
) -> Any:
    body = None if payload is None else json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        message = "Supabase request was rejected."
        try:
            parsed = json.loads(raw.decode("utf-8"))
            message = str(parsed.get("msg") or parsed.get("message") or parsed.get("error_description") or message)
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        raise SupabaseAPIError(exc.code, message[:300]) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SupabaseAPIError(503, "Supabase could not be reached. Please try again.") from exc
    except json.JSONDecodeError as exc:
        raise SupabaseAPIError(502, "Supabase returned an invalid response.") from exc


def _headers(access_token: str) -> dict[str, str]:
    config = settings()
    if not config["configured"]:
        raise SupabaseAPIError(503, "Account storage is not configured for this deployment.")
    return {
        "apikey": str(config["publishable_key"]),
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return None
    return parts[1].strip()


def get_user(access_token: str) -> dict[str, Any]:
    """Validate the access token with Supabase Auth; never trust decoded claims alone."""
    config = settings()
    if not config["configured"]:
        raise SupabaseAPIError(503, "Account storage is not configured for this deployment.")
    user = _request_json(
        f"{config['url']}/auth/v1/user",
        headers=_headers(access_token),
    )
    if not isinstance(user, dict) or not user.get("id"):
        raise SupabaseAPIError(401, "The sign-in session is invalid or expired.")
    return {
        "id": str(user["id"]),
        "email": user.get("email"),
        "created_at": user.get("created_at"),
        "last_sign_in_at": user.get("last_sign_in_at"),
    }


def rest_select(
    resource: str,
    *,
    access_token: str,
    filters: dict[str, str],
) -> Any:
    config = settings()
    if not resource.replace("_", "").isalnum():
        raise ValueError("Invalid Supabase resource name")
    query = urllib.parse.urlencode(filters, safe="(),.*:")
    return _request_json(
        f"{config['url']}/rest/v1/{resource}?{query}",
        headers=_headers(access_token),
    )


def save_completed_analysis(
    *,
    access_token: str,
    run_record: dict[str, Any],
    sources: list[dict[str, Any]],
    result_record: dict[str, Any],
) -> dict[str, Any]:
    config = settings()
    result = _request_json(
        f"{config['url']}/rest/v1/rpc/save_completed_analysis",
        method="POST",
        headers={**_headers(access_token), "Content-Type": "application/json"},
        payload={
            "p_run": run_record,
            "p_sources": sources,
            "p_result": result_record,
        },
    )
    if not isinstance(result, dict) or not result.get("run_id"):
        raise SupabaseAPIError(502, "Supabase did not confirm that the analysis was saved.")
    return result



def queue_analysis_request(
    *,
    access_token: str,
    client_request_id: str,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    """Accept one authenticated request into the database-owned durable queue."""
    config = settings()
    result = _request_json(
        f"{config['url']}/rest/v1/rpc/queue_analysis_request",
        method="POST",
        headers={**_headers(access_token), "Content-Type": "application/json"},
        payload={
            "p_client_request_id": client_request_id,
            "p_request_payload": request_payload,
        },
    )
    if not isinstance(result, dict) or not result.get("run_id"):
        raise SupabaseAPIError(502, "Supabase did not confirm that the analysis was queued.")
    return result


def request_analysis_run_recheck(*, access_token: str, run_id: str) -> dict[str, Any]:
    """Ask Supabase to requeue one owner-verified saved analysis."""
    import uuid

    try:
        safe_run_id = str(uuid.UUID(run_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("A valid saved analysis ID is required.") from exc

    config = settings()
    result = _request_json(
        f"{config['url']}/rest/v1/rpc/request_analysis_run_recheck",
        method="POST",
        headers={**_headers(access_token), "Content-Type": "application/json"},
        payload={"p_run_id": safe_run_id},
    )
    if not isinstance(result, dict) or not result.get("run_id"):
        raise SupabaseAPIError(502, "Supabase did not confirm the saved analysis recheck.")
    return result


def archive_result_payload(result_payload: dict[str, Any], *, storage_key: str) -> dict[str, Any]:
    """Store a full analysis JSON document in private Google Drive, not Postgres."""
    from fieldshift.v3 import google_drive

    safe_key = str(storage_key).strip()
    if not safe_key or len(safe_key) > 128 or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in safe_key
    ):
        raise ValueError("A safe analysis archive key is required.")
    if not google_drive.configured():
        raise SupabaseAPIError(
            503,
            "Google Drive result storage is not configured; the result was not copied into Supabase.",
        )

    content = json.dumps(
        result_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    object_key = f"analysis-results/{safe_key}/{digest}.json"
    try:
        google_drive.put_object(object_key, content, sha256=digest, mime_type="application/json")
    except google_drive.GoogleDriveError as exc:
        raise SupabaseAPIError(503, "Google Drive could not store the analysis result.") from exc
    return {
        "storage_provider": "google_drive",
        "archive_object_key": object_key,
        "archive_sha256": digest,
        "archive_size_bytes": len(content),
    }


def restore_result_payload(stored_payload: Any) -> Any:
    """Hydrate a private Drive result reference; pass through legacy inline results."""
    if not isinstance(stored_payload, dict) or stored_payload.get("storage_provider") != "google_drive":
        return stored_payload

    from fieldshift.v3 import google_drive

    object_key = str(stored_payload.get("archive_object_key") or "")
    expected_sha = str(stored_payload.get("archive_sha256") or "")
    parts = object_key.split("/")
    if (
        len(parts) != 3
        or parts[0] != "analysis-results"
        or not parts[1]
        or len(expected_sha) != 64
        or any(char not in "0123456789abcdef" for char in expected_sha.lower())
        or parts[2] != f"{expected_sha}.json"
    ):
        raise SupabaseAPIError(502, "The saved Google Drive result reference is invalid.")

    try:
        content = google_drive.get_object(object_key)
    except google_drive.GoogleDriveError as exc:
        raise SupabaseAPIError(503, "Google Drive could not retrieve the saved analysis result.") from exc
    if content is None:
        raise SupabaseAPIError(503, "The saved analysis result is not available in Google Drive.")
    actual_sha = hashlib.sha256(content).hexdigest()
    if actual_sha != expected_sha:
        raise SupabaseAPIError(502, "The saved Google Drive result failed its integrity check.")
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SupabaseAPIError(502, "The saved Google Drive result is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise SupabaseAPIError(502, "The saved Google Drive result has an invalid structure.")
    return payload


def persist_product_analysis(
    *,
    access_token: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
) -> dict[str, Any]:
    """Persist a completed product response using the signed-in user's JWT/RLS."""
    import hashlib
    import uuid

    run = response_payload.get("run") or {}
    window = run.get("evidence_window") or {}
    start_date = window.get("start_date")
    end_date = window.get("end_date")
    if not start_date or not end_date:
        raise ValueError("The analysis response is missing its observation window.")

    raw_client_id = request_payload.get("client_request_id")
    try:
        client_request_id = str(uuid.UUID(str(raw_client_id)))
    except (ValueError, TypeError, AttributeError):
        client_request_id = str(uuid.uuid4())

    request_snapshot = {key: value for key, value in request_payload.items() if key != "client_request_id"}
    canonical_request = json.dumps(
        request_snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    request_sha256 = hashlib.sha256(canonical_request).hexdigest()

    evidence = response_payload.get("evidence") or {}
    evidence_items = evidence.get("items") or []
    canonical_evidence = json.dumps(
        evidence_items, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    evidence_fingerprint = hashlib.sha256(canonical_evidence).hexdigest()

    status = str(run.get("status") or "preliminary_ready")
    result_kind = {
        "final_ready": "final",
        "final_with_gaps": "final_with_gaps",
    }.get(status, "preliminary")

    status_map = {
        "available": "available",
        "ready": "available",
        "queued": "queued",
        "pending": "pending",
        "retrying": "retrying",
        "partial": "partial",
        "stale": "stale",
        "unavailable": "unavailable",
        "not_configured": "not_configured",
        "failed": "failed",
        "error": "failed",
        "fallback": "failed",
        "skipped": "skipped",
    }
    sources: list[dict[str, Any]] = []
    for item in evidence_items:
        name = str(item.get("name") or "Evidence source")
        source_status = str(item.get("status") or "failed").lower()
        sources.append({
            "source_key": str(item.get("source_key") or "unknown_source"),
            "source_name": name,
            "source_type": str(item.get("source_type") or "unknown"),
            "required": bool(item.get("required", False)),
            "provider": item.get("provider"),
            "product_key": item.get("product_key"),
            "status": status_map.get(source_status, "failed"),
            "requested_start": start_date,
            "requested_end": end_date,
            "quality": {
                "quality_status": item.get("quality_status"),
                "quality_note": item.get("quality_note"),
                "coverage": item.get("coverage"),
                "confidence": item.get("confidence"),
            },
            "provenance": {
                "retrieval_mode": item.get("retrieval_mode"),
                "citation": item.get("citation"),
                "data_start_date": item.get("data_start_date"),
                "data_end_date": item.get("data_end_date"),
                "temporal_resolution": item.get("temporal_resolution"),
                "spatial_resolution": item.get("spatial_resolution"),
            },
        })

    run_record = {
        "client_request_id": client_request_id,
        "request_sha256": request_sha256,
        "request_payload": request_snapshot,
        "engine_version": str(run.get("engine_version") or "unknown"),
        "source_policy_version": "v1",
        "requested_start": start_date,
        "requested_end": end_date,
        "status": status,
        "progress_percent": 100 if run.get("is_final") else 75,
        "status_message": str(run.get("status_message") or "Analysis completed."),
    }
    result_record = {
        "result_kind": result_kind,
        "evidence_fingerprint": evidence_fingerprint,
        "result_payload": archive_result_payload(response_payload, storage_key=client_request_id),
    }
    return save_completed_analysis(
        access_token=access_token,
        run_record=run_record,
        sources=sources,
        result_record=result_record,
    )


def worker_rpc(
    function_name: str,
    *,
    worker_secret: str,
    payload: dict[str, Any],
    timeout: float = 12.0,
) -> Any:
    """Call an RLS-gated worker RPC using the publishable key and server-only header token."""
    config = settings()
    if not config["configured"]:
        raise SupabaseAPIError(503, "Worker database access is not configured.")
    if not function_name.replace("_", "").isalnum():
        raise ValueError("Invalid worker RPC name")
    return _request_json(
        f"{config['url']}/rest/v1/rpc/{function_name}",
        method="POST",
        headers={
            "apikey": str(config["publishable_key"]),
            "Content-Type": "application/json",
            "x-fieldshift-worker": worker_secret,
        },
        payload={**payload, "p_worker_token": worker_secret},
        timeout=timeout,
    )


def claim_worker_job(worker_secret: str) -> dict[str, Any] | None:
    result = worker_rpc(
        "claim_analysis_run_job",
        worker_secret=worker_secret,
        payload={},
    )
    return result if isinstance(result, dict) and result.get("id") else None


def save_worker_analysis(
    *,
    worker_secret: str,
    job_id: str,
    run_id: str,
    response_payload: dict[str, Any],
    retry_at: str | None,
) -> dict[str, Any]:
    run = response_payload.get("run") or {}
    window = run.get("evidence_window") or {}
    start_date = window.get("start_date")
    end_date = window.get("end_date")
    if not start_date or not end_date:
        raise ValueError("The refreshed analysis response is missing its observation window.")

    evidence = response_payload.get("evidence") or {}
    evidence_items = evidence.get("items") or []
    canonical_evidence = json.dumps(
        evidence_items, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    evidence_fingerprint = hashlib.sha256(canonical_evidence).hexdigest()

    status = str(run.get("status") or "preliminary_ready")
    result_kind = {
        "final_ready": "final",
        "final_with_gaps": "final_with_gaps",
    }.get(status, "preliminary")
    status_map = {
        "available": "available",
        "ready": "available",
        "queued": "queued",
        "pending": "pending",
        "retrying": "retrying",
        "partial": "partial",
        "stale": "stale",
        "unavailable": "unavailable",
        "not_configured": "not_configured",
        "failed": "failed",
        "error": "failed",
        "fallback": "failed",
        "skipped": "skipped",
    }

    sources: list[dict[str, Any]] = []
    for item in evidence_items:
        source_status = str(item.get("status") or "failed").lower()
        retry_seconds = item.get("retry_after_seconds")
        next_retry = None
        if retry_seconds is not None:
            try:
                from datetime import UTC, datetime, timedelta
                next_retry = (datetime.now(UTC) + timedelta(seconds=max(1, int(retry_seconds)))).isoformat()
            except (TypeError, ValueError, OverflowError):
                next_retry = None
        sources.append({
            "source_key": str(item.get("source_key") or "unknown_source"),
            "source_name": str(item.get("name") or "Evidence source"),
            "source_type": str(item.get("source_type") or "unknown"),
            "required": bool(item.get("required", False)),
            "provider": item.get("provider"),
            "product_key": item.get("product_key"),
            "provider_task_id": item.get("provider_task_id") or item.get("task_id"),
            "status": status_map.get(source_status, "failed"),
            "requested_start": start_date,
            "requested_end": end_date,
            "coverage_start": item.get("coverage_start") or item.get("data_start_date"),
            "coverage_end": item.get("coverage_end") or item.get("data_end_date"),
            "coverage_fraction": item.get("coverage_fraction"),
            "next_retry_at": next_retry,
            "last_error_code": "provider_pending" if source_status in {"pending", "retrying"} else None,
            "last_error_message": None,
            "quality": {
                "quality_status": item.get("quality_status"),
                "quality_note": item.get("quality_note"),
                "coverage": item.get("coverage"),
                "confidence": item.get("confidence"),
            },
            "provenance": {
                "retrieval_mode": item.get("retrieval_mode"),
                "citation": item.get("citation"),
                "data_start_date": item.get("data_start_date"),
                "data_end_date": item.get("data_end_date"),
                "temporal_resolution": item.get("temporal_resolution"),
                "spatial_resolution": item.get("spatial_resolution"),
            },
        })

    run_record = {
        "status": status,
        "progress_percent": 100 if run.get("is_final") else 75,
        "status_message": str(run.get("status_message") or "Evidence refreshed."),
    }
    result_record = {
        "result_kind": result_kind,
        "evidence_fingerprint": evidence_fingerprint,
        "result_payload": archive_result_payload(response_payload, storage_key=run_id),
    }
    result = worker_rpc(
        "worker_save_analysis",
        worker_secret=worker_secret,
        payload={
            "p_job_id": job_id,
            "p_run": run_record,
            "p_sources": sources,
            "p_result": result_record,
            "p_retry_at": retry_at,
        },
        timeout=20,
    )
    if not isinstance(result, dict) or not result.get("run_id"):
        raise SupabaseAPIError(502, "Worker persistence did not confirm a saved revision.")
    return result


def fail_worker_job(
    *,
    worker_secret: str,
    job_id: str,
    error_code: str,
    retry_at: str | None,
) -> dict[str, Any]:
    result = worker_rpc(
        "worker_fail_analysis_job",
        worker_secret=worker_secret,
        payload={
            "p_job_id": job_id,
            "p_error_code": error_code[:80],
            "p_retry_at": retry_at,
        },
        timeout=12,
    )
    if not isinstance(result, dict) or not result.get("job_status"):
        raise SupabaseAPIError(502, "Worker failure state was not confirmed.")
    return result
