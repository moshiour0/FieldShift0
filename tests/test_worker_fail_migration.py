from __future__ import annotations

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "supabase"
    / "migrations"
    / "20261111050822_worker_fail_event_before_lease_release.sql"
)


def test_worker_failure_audit_event_is_written_before_lease_release() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    function_start = sql.index(
        "create or replace function public.worker_fail_analysis_job"
    )
    function_end = sql.index("$function$;", function_start)
    function_sql = sql[function_start:function_end]

    assert "private.worker_token_matches(p_worker_token)" in function_sql
    assert "v_header_token is distinct from p_worker_token" in function_sql
    assert "private.worker_has_active_lease(v_job.run_id)" in function_sql
    assert "for update" in function_sql

    event_insert = function_sql.index(
        "insert into public.analysis_run_events"
    )
    lease_release = function_sql.index(
        "update private.analysis_run_jobs",
        event_insert,
    )
    assert event_insert < lease_release
    assert "lease_expires_at = null" in function_sql[lease_release:]
    assert "lock_owner = null" in function_sql[lease_release:]
