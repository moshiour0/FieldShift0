from __future__ import annotations

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20261111052954_worker_preserve_preliminary_status_with_active_lease.sql"
)


def _worker_save_function() -> str:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    start = sql.index("create or replace function public.worker_save_analysis")
    end = sql.index("$function$;", start)
    return sql[start:end]


def test_optional_pending_evidence_remains_preliminary_in_database() -> None:
    sql = _worker_save_function()
    assert "p_retry_at is not null and p_run->>'status' = 'preliminary_ready'" in sql
    assert "then 'preliminary_ready'" in sql
    assert "when p_retry_at is not null\n            then 'waiting_for_data'" in sql
    assert "case when p_retry_at is not null then 'preliminary' else p_result->>'result_kind' end" in sql
    assert "completed_at = case when p_retry_at is null then now() else null end" in sql


def test_worker_token_lease_and_audit_order_are_preserved() -> None:
    sql = _worker_save_function()
    assert "private.worker_token_matches(p_worker_token)" in sql
    assert "v_header_token is distinct from p_worker_token" in sql
    assert "private.worker_has_active_lease(v_job.run_id)" in sql
    event_insert = sql.index("insert into public.analysis_run_events")
    lease_release = sql.index("update private.analysis_run_jobs", event_insert)
    assert event_insert < lease_release
    assert "lease_expires_at = null" in sql[lease_release:]
    assert "lock_owner = null" in sql[lease_release:]
