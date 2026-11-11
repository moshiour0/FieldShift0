-- Keep the active worker lease through the failure audit event.
-- The event INSERT policy checks private.worker_has_active_lease(run_id),
-- which requires this job to remain running until the event has been appended.

CREATE OR REPLACE FUNCTION public.worker_fail_analysis_job(
    p_worker_token text,
    p_job_id uuid,
    p_error_code text,
    p_retry_at timestamp with time zone DEFAULT NULL::timestamp with time zone
)
RETURNS jsonb
LANGUAGE plpgsql
SET search_path TO 'pg_catalog', 'public', 'private'
AS $function$
declare
    v_header_token text;
    v_job private.analysis_run_jobs%rowtype;
    v_status text;
begin
    v_header_token := nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker';
    if not private.worker_token_matches(p_worker_token)
       or v_header_token is distinct from p_worker_token then
        raise exception 'Worker authentication failed' using errcode = '42501';
    end if;

    select * into v_job
    from private.analysis_run_jobs
    where id = p_job_id
      and status = 'running'
      and lock_owner = 'fieldshift-vercel-worker'
      and lease_expires_at > now()
    for update;
    if not found or not private.worker_has_active_lease(v_job.run_id) then
        raise exception 'Worker job lease is no longer valid' using errcode = '42501';
    end if;

    v_status := case
        when p_retry_at is not null and v_job.attempts < v_job.max_attempts then 'retrying'
        else 'failed'
    end;

    if v_status = 'failed' then
        update public.analysis_runs
           set status = 'failed',
               status_message = 'Automatic evidence refresh stopped after a non-recoverable error or retry limit.',
               updated_at = now(),
               last_activity_at = now()
         where id = v_job.run_id;
    end if;

    -- This insert must happen while the queue row is still running and leased.
    -- Do not move it below the job update: the RLS policy will reject it.
    insert into public.analysis_run_events (
        run_id, event_type, from_status, to_status, safe_message, details
    )
    values (
        v_job.run_id,
        'analysis_worker_' || v_status,
        null,
        v_status,
        case when v_status = 'retrying' then 'The worker will retry this saved analysis automatically.'
             else 'Automatic evidence refresh stopped. The saved result remains available.' end,
        jsonb_build_object('worker_attempt', v_job.attempts, 'error_code', p_error_code)
    );

    -- Release/reschedule only after the RLS-gated audit event is persisted.
    update private.analysis_run_jobs
       set status = v_status,
           available_at = case when v_status = 'retrying' then p_retry_at else available_at end,
           locked_at = null,
           heartbeat_at = now(),
           lease_expires_at = null,
           lock_owner = null,
           last_error_code = left(coalesce(p_error_code, 'worker_error'), 80),
           last_error_message = case when v_status = 'failed' then 'Worker could not complete the reconciliation.' else null end,
           updated_at = now()
     where id = p_job_id;

    return jsonb_build_object(
        'job_status', v_status,
        'next_retry_at', case when v_status = 'retrying' then p_retry_at else null end
    );
end;
$function$;

notify pgrst, 'reload schema';
