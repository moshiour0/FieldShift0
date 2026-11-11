-- Owner-verified requeue for a terminal durable analysis run.
-- This RPC is SECURITY DEFINER only so it can update the private queue; all
-- access is bound to auth.uid() and a locked owner-scoped analysis_runs row.

create or replace function public.request_analysis_run_recheck(p_run_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public, private, auth
as $function$
declare
    v_user_id uuid := auth.uid();
    v_run public.analysis_runs%rowtype;
    v_job private.analysis_run_jobs%rowtype;
    v_previous_status text;
    v_available_at timestamptz := now();
begin
    if v_user_id is null then
        raise exception 'Authentication required' using errcode = '42501';
    end if;
    if p_run_id is null then
        raise exception 'A saved analysis ID is required' using errcode = '22023';
    end if;

    select *
      into v_run
    from public.analysis_runs
    where id = p_run_id
      and user_id = v_user_id
    for update;

    if not found then
        -- Do not reveal whether another user's run ID exists.
        raise exception 'Saved analysis not found' using errcode = 'P0002';
    end if;

    if v_run.status not in ('waiting_for_data', 'failed', 'final_with_gaps') then
        raise exception 'Only a waiting, failed, or final-with-gaps run can be checked again'
            using errcode = '22023';
    end if;

    v_previous_status := v_run.status;

    -- Idempotently reuse an existing active job; never create parallel jobs
    -- when a user presses Check now repeatedly or two tabs race.
    select *
      into v_job
    from private.analysis_run_jobs
    where run_id = p_run_id
      and job_type in ('build_result', 'reconcile_run')
      and status in ('queued', 'running', 'retrying')
    order by created_at desc
    limit 1
    for update;

    if found then
        return jsonb_build_object(
            'run_id', p_run_id,
            'status', v_run.status,
            'stage', v_run.stage,
            'job_status', v_job.status,
            'already_queued', true,
            'available_at', v_job.available_at
        );
    end if;

    -- Reuse the existing logical job and its source/task history where
    -- possible. If no job exists (e.g. a legacy completed snapshot), create
    -- one new build_result job with a unique idempotency key.
    select *
      into v_job
    from private.analysis_run_jobs
    where run_id = p_run_id
      and job_type in ('build_result', 'reconcile_run')
    order by created_at desc
    limit 1
    for update;

    if found then
        update private.analysis_run_jobs
           set status = 'queued',
               attempts = 0,
               max_attempts = 50,
               available_at = v_available_at,
               locked_at = null,
               lock_owner = null,
               heartbeat_at = null,
               lease_expires_at = null,
               last_error_code = null,
               last_error_message = null,
               updated_at = v_available_at
         where id = v_job.id;
    else
        insert into private.analysis_run_jobs (
            run_id, job_type, idempotency_key, payload,
            status, attempts, max_attempts, available_at
        )
        values (
            p_run_id,
            'build_result',
            p_run_id::text || ':manual-recheck:' || gen_random_uuid()::text,
            jsonb_build_object('reason', 'manual_recheck'),
            'queued',
            0,
            50,
            v_available_at
        )
        returning * into v_job;
    end if;

    update public.analysis_runs
       set status = 'waiting_for_data',
           stage = 'queued',
           progress_percent = least(coalesce(progress_percent, 75), 75),
           status_message = 'A new evidence check has been queued. Your previously saved result remains available while the worker checks the data again.',
           started_at = coalesce(started_at, v_available_at),
           completed_at = null,
           last_activity_at = v_available_at,
           updated_at = v_available_at
     where id = p_run_id;

    insert into public.analysis_run_events (
        run_id, event_type, from_status, to_status, safe_message, details
    )
    values (
        p_run_id,
        'analysis_recheck_requested',
        v_previous_status,
        'waiting_for_data',
        'A new evidence check was requested for this saved analysis.',
        jsonb_build_object(
            'job_id', v_job.id,
            'job_type', v_job.job_type,
            'trigger', 'owner_manual_recheck'
        )
    );

    return jsonb_build_object(
        'run_id', p_run_id,
        'status', 'waiting_for_data',
        'stage', 'queued',
        'job_status', 'queued',
        'already_queued', false,
        'available_at', v_available_at
    );
end;
$function$;

revoke all on function public.request_analysis_run_recheck(uuid) from public, anon;
grant execute on function public.request_analysis_run_recheck(uuid) to authenticated;

comment on function public.request_analysis_run_recheck(uuid) is
    'Owner-only, idempotent requeue of an existing terminal saved analysis; preserves its source rows and provider task identifiers.';
notify pgrst, 'reload schema';
