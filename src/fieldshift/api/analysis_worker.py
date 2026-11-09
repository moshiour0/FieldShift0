"""Vercel-side runner for the token-gated Supabase analysis queue.

The browser never owns this lifecycle. Supabase pg_cron invokes the protected
HTTP route; this module claims one leased job, runs the scientific engine, and
persists a versioned result through the RLS-protected worker RPC.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any


class WorkerAPIError(RuntimeError):
    """A safe, non-secret worker/Data API failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _settings(worker_token_override: str | None = None) -> tuple[str, str, str, str]:
    base_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    anon_jwt = os.getenv("SUPABASE_ANON_KEY", "").strip()
    worker_token = (
        worker_token_override
        or os.getenv("FIELDSHIFT_WORKER_TOKEN", "").strip()
        or os.getenv("FIELD_SHIFT_WORKER_SECRET", "").strip()
    )
    if not base_url or not publishable_key or not anon_jwt or len(worker_token) < 48:
        raise WorkerAPIError("The scheduled analysis worker is not configured.")
    return base_url, publishable_key, anon_jwt, worker_token


def _rest_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    query: str | None = None,
    timeout: int = 20,
    worker_token: str | None = None,
) -> Any:
    base_url, publishable_key, anon_jwt, worker_token = _settings(worker_token)
    url = f"{base_url}/rest/v1/{path.lstrip('/')}"
    if query:
        url = f"{url}?{query}"
    body = None if payload is None else json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            # The publishable key identifies the project. With no user JWT,
            # PostgREST applies the anon role and the token-gated worker RLS.
            "apikey": publishable_key,
            "Authorization": f"Bearer {anon_jwt}",
            "x-fieldshift-worker": worker_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        # Never echo remote response bodies: they may contain provider internals.
        raise WorkerAPIError(f"Supabase worker API returned HTTP {exc.code}.", status_code=exc.code) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WorkerAPIError("Supabase worker API could not be reached.") from exc
    except json.JSONDecodeError as exc:
        raise WorkerAPIError("Supabase worker API returned invalid JSON.") from exc


def _retry_after_seconds(items: list[dict[str, Any]]) -> int | None:
    pending = [
        item for item in items
        if item.get("status") in {"pending", "retrying"}
        or (
            item.get("status") in {"partial", "unavailable"}
            and item.get("retry_after_seconds") is not None
        )
    ]
    if not pending:
        return None
    # Respect the slowest provider-specific Retry-After so retries do not
    # recreate a request while another provider is still in its cooldown.
    delays: list[int] = []
    for item in pending:
        try:
            delay = int(item.get("retry_after_seconds") or 900)
        except (TypeError, ValueError):
            delay = 900
        delays.append(max(900, min(172800, delay)))
    return max(delays, default=900)


def _source_records(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_map = {
        "ready": "available",
        "error": "failed",
        "fallback": "failed",
    }
    records: list[dict[str, Any]] = []
    for item in items:
        status = str(item.get("status") or "failed").lower()
        status = status_map.get(status, status)
        if status not in {
            "queued", "pending", "retrying", "available", "partial", "stale",
            "unavailable", "not_configured", "failed", "skipped",
        }:
            status = "failed"
        error_value = item.get("error")
        safe_error = str(error_value)[:300] if error_value else None
        records.append({
            "source_key": item.get("source_key") or "unknown_source",
            "source_name": item.get("name") or "Evidence source",
            "source_type": item.get("source_type") or "unknown",
            "required": bool(item.get("required", False)),
            "provider": item.get("provider"),
            "product_key": item.get("product_key"),
            "provider_task_id": item.get("provider_task_id"),
            "status": status,
            "requested_start": item.get("requested_start"),
            "requested_end": item.get("requested_end"),
            "coverage_start": item.get("data_start_date"),
            "coverage_end": item.get("data_end_date"),
            "coverage_fraction": item.get("coverage_fraction"),
            "next_retry_at": item.get("next_retry_at"),
            "last_error_code": "PROVIDER_PENDING" if status in {"pending", "retrying", "partial"} else "SOURCE_ERROR" if safe_error else None,
            "last_error_message": "The provider has not returned a complete data set." if safe_error else None,
            "quality": {
                key: item[key] for key in ("quality_status", "quality_note", "confidence", "coverage")
                if item.get(key) is not None
            },
            "provenance": {
                key: item[key] for key in (
                    "retrieval_mode", "citation", "temporal_resolution",
                    "spatial_resolution", "data_start_date", "data_end_date",
                ) if item.get(key) is not None
            },
        })
    return records


def _claim_job(worker_token: str) -> dict[str, Any] | None:
    result = _rest_json(
        "rpc/claim_analysis_run_job",
        method="POST",
        payload={"p_worker_token": worker_token},
        timeout=25,
        worker_token=worker_token,
    )
    return result if isinstance(result, dict) and result.get("id") else None


def _load_run(run_id: str, worker_token: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({
        "select": "id,user_id,client_request_id,request_payload,requested_start,requested_end,status",
        "id": f"eq.{run_id}",
        "limit": "1",
    }, safe="(),.*:")
    result = _rest_json("analysis_runs", query=query, timeout=20, worker_token=worker_token)
    if not isinstance(result, list) or not result:
        raise WorkerAPIError("The leased analysis run could not be loaded.")
    row = result[0]
    if not isinstance(row.get("request_payload"), dict):
        raise WorkerAPIError("The saved analysis request is invalid.")
    return row


def _save_result(job_id: str, result: dict[str, Any], worker_token: str) -> dict[str, Any]:
    run = result.get("run") or {}
    items = (result.get("evidence") or {}).get("items") or []
    if not isinstance(items, list):
        raise WorkerAPIError("The engine returned invalid evidence metadata.")

    engine_status = str(run.get("status") or "preliminary_ready")
    retry_seconds = _retry_after_seconds(items)
    retry_at = (
        (datetime.now(UTC) + timedelta(seconds=retry_seconds)).isoformat()
        if retry_seconds is not None else None
    )
    # Never label a result FINAL while a provider has a scheduled retry.
    # Keep the current evidence snapshot, but expose it as waiting_for_data.
    status = (
        "waiting_for_data"
        if retry_at is not None and engine_status in {"final_ready", "final_with_gaps"}
        else engine_status
    )
    is_final = status in {"final_ready", "final_with_gaps"}
    status_message = str(run.get("status_message") or "Background analysis completed.")
    if status == "waiting_for_data" and engine_status in {"final_ready", "final_with_gaps"}:
        status_message = "A preliminary evidence snapshot is available. Some provider data is still pending and will be checked again automatically."

    result_payload = copy.deepcopy(result)
    stored_run = result_payload.setdefault("run", {})
    stored_run["status"] = status
    stored_run["is_final"] = is_final
    stored_run["status_message"] = status_message

    fingerprint = hashlib.sha256(
        json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    result_kind = "final" if status == "final_ready" else "final_with_gaps" if status == "final_with_gaps" else "preliminary"

    payload = {
        "p_worker_token": worker_token,
        "p_job_id": job_id,
        "p_run": {
            "status": status,
            "progress_percent": 100 if is_final else 75,
            "status_message": status_message,
        },
        "p_sources": _source_records(items),
        "p_result": {
            "result_kind": result_kind,
            "evidence_fingerprint": fingerprint,
            "result_payload": {key: value for key, value in result_payload.items() if key != "_request_payload"},
        },
        "p_retry_at": retry_at,
    }
    saved = _rest_json("rpc/worker_save_analysis", method="POST", payload=payload, timeout=30, worker_token=worker_token)
    if not isinstance(saved, dict) or not saved.get("run_id"):
        raise WorkerAPIError("Supabase did not confirm the worker result.")
    return saved


def _is_retryable_worker_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, urllib.error.URLError)):
        return True
    if isinstance(exc, WorkerAPIError):
        return exc.status_code in {408, 425, 429} or bool(exc.status_code and exc.status_code >= 500)
    name = type(exc).__name__.lower()
    return "retryable" in name or name in {"apiexception", "serviceunavailable"}


def _fail_job(job_id: str, attempts: int, exc: Exception, worker_token: str) -> None:
    # Retry transient transport/provider failures only. Invalid requests, auth
    # failures and scientific validation errors are recorded as terminal.
    retryable = _is_retryable_worker_error(exc)
    delay = min(21600, 900 * (2 ** max(0, attempts - 1)))
    retry_at = (
        (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
        if retryable else None
    )
    try:
        _rest_json(
            "rpc/worker_fail_analysis_job",
            method="POST",
            payload={
                "p_worker_token": worker_token,
                "p_job_id": job_id,
                "p_error_code": type(exc).__name__[:80],
                "p_retry_at": retry_at,
            },
            timeout=20,
            worker_token=worker_token,
        )
    except WorkerAPIError:
        # A lost lease is recovered by the database after lease_expires_at.
        return


def process_one(worker_token: str | None = None) -> dict[str, Any]:
    """Claim and process at most one job; safe to call from a scheduled HTTP route."""
    configured_token = _settings(worker_token)[3]
    job = _claim_job(configured_token)
    if job is None:
        return {"processed": False, "message": "No queued analysis job is ready."}

    job_id = str(job["id"])
    run_id = str(job["run_id"])
    try:
        run = _load_run(run_id, configured_token)
        from fieldshift.api.product import create_analysis

        result = create_analysis(run["request_payload"])
        saved = _save_result(job_id, result, configured_token)
        return {
            "processed": True,
            "run_id": run_id,
            "status": saved.get("status") or result.get("run", {}).get("status"),
            "revision": saved.get("revision"),
            "job_status": saved.get("job_status"),
            "next_retry_at": saved.get("next_retry_at"),
        }
    except Exception as exc:
        _fail_job(job_id, int(job.get("attempts") or 1), exc, configured_token)
        raise WorkerAPIError("The analysis worker could not complete this job; the lease will retry it safely.") from exc
