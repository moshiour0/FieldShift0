-- Initial authenticated requests must enter the durable queue, and the
-- worker must be able to claim both the first build and later reconciliation.
create or replace function private.worker_has_active_lease(p_run_id uuid)
returns boolean
language sql
stable
security invoker
set search_path = pg_catalog, private
as $function$
    select private.worker_token_matches(
        (nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
    )
    and exists (
        select 1
        from private.analysis_run_jobs j
        where j.run_id = p_run_id
          and j.job_type in ('reconcile_run','build_result')
          and j.status = 'running'
          and j.lock_owner = 'fieldshift-vercel-worker'
          and j.lease_expires_at > now()
    );
$function$;
revoke all on function private.worker_has_active_lease(uuid) from public;
grant execute on function private.worker_has_active_lease(uuid) to anon;

create or replace function public.claim_analysis_run_job(p_worker_token text)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, private
as $function$
declare
    v_header_token text;
    v_job jsonb;
begin
    v_header_token := nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker';
    if not private.worker_token_matches(p_worker_token)
       or v_header_token is distinct from p_worker_token then
        raise exception 'Worker authentication failed' using errcode = '42501';
    end if;

    -- One heavy Python worker at a time on the Free Vercel plan.
    if exists (
        select 1
        from private.analysis_run_jobs j
        where j.status = 'running'
          and j.lease_expires_at > now()
    ) then
        return null;
    end if;

    with next_job as (
        select j.id
        from private.analysis_run_jobs j
        where (
            (j.status in ('queued', 'retrying') and j.available_at <= now())
            or (j.status = 'running' and j.lease_expires_at <= now())
        )
          and j.job_type in ('reconcile_run','build_result')
          and j.attempts < j.max_attempts
        order by j.available_at asc, j.created_at asc
        for update skip locked
        limit 1
    )
    update private.analysis_run_jobs j
       set status = 'running',
           attempts = j.attempts + 1,
           locked_at = now(),
           heartbeat_at = now(),
           lease_expires_at = now() + interval '6 minutes',
           lock_owner = 'fieldshift-vercel-worker',
           updated_at = now()
      from next_job
     where j.id = next_job.id
    returning to_jsonb(j) into v_job;

    return v_job;
end;
$function$;
revoke all on function public.claim_analysis_run_job(text) from public, authenticated;
grant execute on function public.claim_analysis_run_job(text) to anon;

create or replace function private.enqueue_initial_analysis_job()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, private
as $function$
begin
    if auth.uid() is not null and auth.uid() <> new.user_id then
        raise exception 'Cannot enqueue another user analysis' using errcode = '42501';
    end if;
    insert into private.analysis_run_jobs (
        run_id, job_type, idempotency_key, payload, status, available_at
    )
    values (
        new.id,
        'build_result',
        new.id::text || ':initial',
        jsonb_build_object('reason','initial_analysis'),
        'queued',
        now()
    )
    on conflict (idempotency_key) do nothing;
    return new;
end;
$function$;
revoke all on function private.enqueue_initial_analysis_job() from public, anon, authenticated;

drop trigger if exists enqueue_initial_analysis_job on public.analysis_runs;
create trigger enqueue_initial_analysis_job
after insert on public.analysis_runs
for each row execute function private.enqueue_initial_analysis_job();

create or replace function public.queue_analysis_request(
    p_client_request_id uuid,
    p_request_payload jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, extensions
as $function$
declare
    v_user_id uuid := auth.uid();
    v_request_hash char(64);
    v_existing_id uuid;
    v_existing_hash char(64);
    v_start date;
    v_end date;
    v_run_id uuid;
begin
    if v_user_id is null then
        raise exception 'Authentication required' using errcode = '42501';
    end if;
    if p_client_request_id is null or jsonb_typeof(p_request_payload) <> 'object' then
        raise exception 'Invalid run request' using errcode = '22023';
    end if;

    v_start := nullif(p_request_payload->>'start_date', '')::date;
    v_end := nullif(p_request_payload->>'end_date', '')::date;
    if v_start is null or v_end is null or v_end < v_start then
        raise exception 'Analysis date window is invalid' using errcode = '22023';
    end if;
    if (v_end - v_start) > 3660 then
        raise exception 'Analysis date window exceeds the ten-year limit' using errcode = '22023';
    end if;

    v_request_hash := encode(
        extensions.digest(convert_to(p_request_payload::text, 'UTF8'), 'sha256'),
        'hex'
    );

    select id, request_sha256
      into v_existing_id, v_existing_hash
    from public.analysis_runs
    where user_id = v_user_id
      and client_request_id = p_client_request_id;

    if v_existing_id is not null then
        if v_existing_hash <> v_request_hash then
            raise exception 'client_request_id was already used for a different request' using errcode = '23505';
        end if;
        return jsonb_build_object('run_id', v_existing_id, 'status', 'queued', 'already_queued', true);
    end if;

    insert into public.analysis_runs (
        user_id, client_request_id, request_sha256, request_payload,
        engine_version, source_policy_version, requested_start, requested_end,
        status, stage, progress_percent, status_message
    )
    values (
        v_user_id, p_client_request_id, v_request_hash, p_request_payload,
        '3.3.0', 'v1', v_start, v_end,
        'queued', 'queued', 0, 'Your analysis is safely queued for background processing.'
    )
    returning id into v_run_id;

    return jsonb_build_object('run_id', v_run_id, 'status', 'queued', 'already_queued', false);
end;
$function$;
revoke all on function public.queue_analysis_request(uuid, jsonb) from public, anon;
grant execute on function public.queue_analysis_request(uuid, jsonb) to authenticated;
