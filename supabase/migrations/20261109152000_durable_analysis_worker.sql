-- Durable queue lifecycle for authenticated analysis requests.
-- Worker-only operations execute as service_role via RLS-preserving SECURITY INVOKER RPCs.

alter table private.analysis_run_jobs
    add column if not exists lease_expires_at timestamptz;

create index if not exists analysis_run_jobs_lease_idx
    on private.analysis_run_jobs (lease_expires_at)
    where status = 'running';

alter table public.analysis_run_sources
    alter column max_attempts set default 50;

create table if not exists private.worker_settings (
    setting_id smallint primary key check (setting_id = 1),
    token_sha256 bytea not null,
    updated_at timestamptz not null default now()
);
alter table private.worker_settings enable row level security;
revoke all on private.worker_settings from public, anon, authenticated;
grant all privileges on private.worker_settings to service_role;

create or replace function public.verify_fieldshift_worker_token(p_candidate text)
returns boolean
language sql
security invoker
set search_path = pg_catalog, public, private, extensions
as $
    select p_candidate is not null
       and length(p_candidate) >= 48
       and exists (
           select 1
           from private.worker_settings s
           where s.setting_id = 1
             and s.token_sha256 = extensions.digest(convert_to(p_candidate, 'UTF8'), 'sha256')
       );
$;
revoke all on function public.verify_fieldshift_worker_token(text) from public, anon, authenticated;
grant execute on function public.verify_fieldshift_worker_token(text) to service_role;

create or replace function private.enqueue_initial_analysis_job()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, private
as $
begin
    if auth.uid() is not null and auth.uid() <> new.user_id then
        raise exception 'Cannot enqueue another user analysis' using errcode = '42501';
    end if;
    insert into private.analysis_run_jobs (
        run_id, job_type, idempotency_key, payload, status, available_at
    )
    values (
        new.id, 'build_result', new.id::text || ':initial',
        jsonb_build_object('reason', 'initial_analysis'),
        'queued', now()
    )
    on conflict (idempotency_key) do nothing;
    return new;
end;
$;

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
as $
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
    end;
    if (v_end - v_start) > 3660 then
        raise exception 'Analysis date window exceeds the ten-year limit' using errcode = '22023';
    end;

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
$;

revoke all on function public.queue_analysis_request(uuid, jsonb) from public, anon;
grant execute on function public.queue_analysis_request(uuid, jsonb) to authenticated;

create or replace function public.claim_analysis_job(
    p_worker_id text,
    p_lease_seconds integer default 240
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, private
as $
declare
    v_job private.analysis_run_jobs%rowtype;
    v_run public.analysis_runs%rowtype;
begin
    if coalesce(length(trim(p_worker_id)), 0) < 8 then
        raise exception 'Invalid worker identity' using errcode = '22023';
    end if;

    update private.analysis_run_jobs
       set status = 'failed',
           last_error_code = 'MAX_ATTEMPTS',
           last_error_message = 'Worker retry limit reached.',
           updated_at = now(),
           locked_at = null,
           lock_owner = null,
           lease_expires_at = null
     where attempts >= max_attempts
       and (
           (status in ('queued', 'retrying') and available_at <= now())
           or (status = 'running' and lease_expires_at <= now())
       );

    select *
      into v_job
    from private.analysis_run_jobs
    where attempts < max_attempts
      and (
          (status in ('queued', 'retrying') and available_at <= now())
          or (status = 'running' and lease_expires_at <= now())
      )
    order by available_at asc, created_at asc
    for update skip locked
    limit 1;

    if v_job.id is null then
        return null;
    end if;

    update private.analysis_run_jobs
       set status = 'running',
           attempts = attempts + 1,
           locked_at = now(),
           lock_owner = p_worker_id,
           lease_expires_at = now() + make_interval(secs => greatest(60, least(p_lease_seconds, 300))),
           updated_at = now()
     where id = v_job.id
     returning * into v_job;

    select * into v_run
    from public.analysis_runs
    where id = v_job.run_id
    for update;

    update public.analysis_runs
       set status = 'running',
           stage = 'processing',
           progress_percent = greatest(progress_percent, 5),
           status_message = 'A background worker is processing the requested evidence.',
           started_at = coalesce(started_at, now()),
           last_activity_at = now(),
           updated_at = now()
     where id = v_run.id
       and status not in ('final_ready', 'final_with_gaps', 'cancelled', 'failed');

    return jsonb_build_object(
        'job_id', v_job.id,
        'run_id', v_run.id,
        'job_type', v_job.job_type,
        'attempt', v_job.attempts,
        'max_attempts', v_job.max_attempts,
        'worker_id', p_worker_id,
        'request_payload', v_run.request_payload,
        'requested_start', v_run.requested_start,
        'requested_end', v_run.requested_end
    );
end;
$;

revoke all on function public.claim_analysis_job(text, integer) from public, anon, authenticated;
grant execute on function public.claim_analysis_job(text, integer) to service_role;

create or replace function public.complete_analysis_job(
    p_job_id uuid,
    p_worker_id text,
    p_result_payload jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, private, extensions
as $
declare
    v_job private.analysis_run_jobs%rowtype;
    v_run public.analysis_runs%rowtype;
    v_run_status text;
    v_result_kind text;
    v_fingerprint char(64);
    v_revision integer;
    v_result_id uuid;
    v_source jsonb;
    v_source_key text;
    v_source_status text;
    v_source_count integer := 0;
    v_pending_count integer := 0;
    v_retry_at timestamptz;
    v_saved_payload jsonb;
    v_previous_fingerprint char(64);
    v_previous_status text;
begin
    if jsonb_typeof(p_result_payload) <> 'object'
       or jsonb_typeof(p_result_payload->'run') <> 'object'
       or jsonb_typeof(p_result_payload->'evidence'->'items') <> 'array' then
        raise exception 'Worker returned an invalid analysis result' using errcode = '22023';
    end if;

    select * into v_job
    from private.analysis_run_jobs
    where id = p_job_id
    for update;

    if v_job.id is null
       or v_job.status <> 'running'
       or v_job.lock_owner <> p_worker_id
       or v_job.lease_expires_at < now() then
        raise exception 'Worker lease is no longer valid' using errcode = '42501';
    end if;

    select * into v_run
    from public.analysis_runs
    where id = v_job.run_id
    for update;

    v_run_status := p_result_payload->'run'->>'status';
    if v_run_status not in ('preliminary_ready', 'waiting_for_data', 'final_ready', 'final_with_gaps', 'failed') then
        v_run_status := 'preliminary_ready';
    end if;

    v_result_kind := case v_run_status
        when 'final_ready' then 'final'
        when 'final_with_gaps' then 'final_with_gaps'
        else 'preliminary'
    end;

    v_fingerprint := encode(
        extensions.digest(convert_to((p_result_payload->'evidence'->'items')::text, 'UTF8'), 'sha256'),
        'hex'
    );

    select evidence_fingerprint
      into v_previous_fingerprint
    from public.analysis_results
    where run_id = v_run.id and is_current = true
    order by revision desc limit 1;

    select status into v_previous_status
    from public.analysis_runs where id = v_run.id;

    for v_source in
        select value from jsonb_array_elements(p_result_payload->'evidence'->'items')
    loop
        v_source_count := v_source_count + 1;
        v_source_key := coalesce(nullif(v_source->>'source_key', ''), 'unknown_source_' || v_source_count::text);
        v_source_status := lower(coalesce(v_source->>'status', 'failed'));
        if v_source_status not in ('queued','pending','retrying','available','partial','stale','unavailable','not_configured','failed','skipped') then
            v_source_status := 'failed';
        end if;

        insert into public.analysis_run_sources (
            run_id, source_key, source_name, source_type, required,
            provider, product_key, status, requested_start, requested_end,
            coverage_start, coverage_end, coverage_fraction, attempt_count, max_attempts,
            next_retry_at, last_checked_at, last_error_code, last_error_message,
            quality, provenance, provider_task_id
        )
        values (
            v_run.id,
            v_source_key,
            coalesce(nullif(v_source->>'name',''), v_source_key),
            coalesce(nullif(v_source->>'source_type',''), 'unknown'),
            coalesce((v_source->>'required')::boolean, false),
            v_source->>'provider',
            v_source->>'product_key',
            case
                when v_source_status in ('pending','retrying','partial')
                    and coalesce((select attempt_count from public.analysis_run_sources s where s.run_id=v_run.id and s.source_key=v_source_key),0) >= 49
                    then 'unavailable'
                else v_source_status
            end,
            v_run.requested_start,
            v_run.requested_end,
            nullif(v_source->>'data_start_date','')::date,
            nullif(v_source->>'data_end_date','')::date,
            nullif(v_source->>'coverage','')::numeric,
            1,
            50,
            case
                when v_source_status in ('pending','retrying','partial')
                    then now() + make_interval(secs => greatest(900, least(172800, coalesce(nullif(v_source->>'retry_after_seconds','')::integer, 900))))
                else null
            end,
            now(),
            case when v_source ? 'error' then 'PROVIDER_INCOMPLETE' else null end,
            left(v_source->>'error', 350),
            jsonb_strip_nulls(jsonb_build_object(
                'quality_status', v_source->'quality_status',
                'quality_note', v_source->'quality_note',
                'confidence', v_source->'confidence',
                'coverage', v_source->'coverage'
            )),
            jsonb_strip_nulls(jsonb_build_object(
                'retrieval_mode', v_source->'retrieval_mode',
                'citation', v_source->'citation',
                'temporal_resolution', v_source->'temporal_resolution',
                'spatial_resolution', v_source->'spatial_resolution',
                'data_start_date', v_source->'data_start_date',
                'data_end_date', v_source->'data_end_date'
            )),
            nullif(v_source->>'provider_task_id','')
        )
        on conflict (run_id, source_key) do update
        set source_name = excluded.source_name,
            source_type = excluded.source_type,
            required = excluded.required,
            provider = excluded.provider,
            product_key = excluded.product_key,
            status = case
                when excluded.status in ('pending','retrying','partial')
                     and public.analysis_run_sources.attempt_count >= public.analysis_run_sources.max_attempts - 1
                    then 'unavailable'
                else excluded.status
            end,
            coverage_start = excluded.coverage_start,
            coverage_end = excluded.coverage_end,
            coverage_fraction = excluded.coverage_fraction,
            provider_task_id = coalesce(excluded.provider_task_id, public.analysis_run_sources.provider_task_id),
            attempt_count = public.analysis_run_sources.attempt_count + 1,
            next_retry_at = excluded.next_retry_at,
            last_checked_at = now(),
            last_error_code = excluded.last_error_code,
            last_error_message = excluded.last_error_message,
            quality = excluded.quality,
            provenance = excluded.provenance,
            updated_at = now();
    end loop;

    select count(*) into v_pending_count
    from public.analysis_run_sources
    where run_id = v_run.id and status in ('pending','retrying','partial');

    if v_previous_fingerprint = v_fingerprint and v_previous_status = v_run_status then
        select coalesce(max(revision),1) into v_revision
        from public.analysis_results where run_id = v_run.id;
    else
        update public.analysis_results
           set is_current = false
         where run_id = v_run.id and is_current = true;

        select coalesce(max(revision),0)+1 into v_revision
        from public.analysis_results where run_id = v_run.id;

        v_saved_payload := p_result_payload;
        v_saved_payload := jsonb_set(v_saved_payload, '{run,id}', to_jsonb(v_run.id::text), true);
        v_saved_payload := jsonb_set(v_saved_payload, '{run,saved_run_id}', to_jsonb(v_run.id::text), true);

        insert into public.analysis_results (
            run_id, revision, result_kind, evidence_fingerprint, result_payload, is_current
        )
        values (
            v_run.id, v_revision, v_result_kind, v_fingerprint, v_saved_payload, true
        )
        returning id into v_result_id;
    end if;

    update public.analysis_runs
       set status = v_run_status,
           stage = case when v_pending_count > 0 then 'waiting_for_datasets' else 'analysis_complete' end,
           progress_percent = case when v_run_status in ('final_ready','final_with_gaps') then 100 else 75 end,
           status_message = left(coalesce(p_result_payload->'run'->>'status_message','Analysis updated.'), 500),
           completed_at = case when v_pending_count = 0 then now() else null end,
           last_activity_at = now(),
           updated_at = now()
     where id = v_run.id;

    insert into public.analysis_run_events (
        run_id, event_type, from_status, to_status, safe_message, details
    )
    values (
        v_run.id,
        case when v_previous_fingerprint is null then 'analysis_completed' else 'analysis_evidence_refreshed' end,
        v_previous_status,
        v_run_status,
        left(coalesce(p_result_payload->'run'->>'status_message','Analysis updated.'), 500),
        jsonb_build_object('source_count',v_source_count,'pending_source_count',v_pending_count,'revision',v_revision)
    );

    update private.analysis_run_jobs
       set status = 'succeeded',
           locked_at = null,
           lock_owner = null,
           lease_expires_at = null,
           updated_at = now()
     where id = v_job.id;

    if v_pending_count > 0 then
        select min(next_retry_at) into v_retry_at
        from public.analysis_run_sources
        where run_id = v_run.id and status in ('pending','retrying','partial');
        insert into private.analysis_run_jobs (
            run_id, job_type, idempotency_key, payload, status, available_at, max_attempts
        )
        values (
            v_run.id,
            'build_result',
            v_run.id::text || ':refresh:' || v_job.id::text,
            jsonb_build_object('reason','delayed_dataset_recheck'),
            'queued',
            coalesce(v_retry_at, now() + interval '15 minutes'),
            50
        )
        on conflict (idempotency_key) do nothing;
    end if;

    return jsonb_build_object(
        'run_id', v_run.id,
        'status', v_run_status,
        'revision', v_revision,
        'pending_source_count', v_pending_count,
        'result_id', v_result_id
    );
end;
$;

revoke all on function public.complete_analysis_job(uuid, text, jsonb) from public, anon, authenticated;
grant execute on function public.complete_analysis_job(uuid, text, jsonb) to service_role;

create or replace function public.retry_analysis_job(
    p_job_id uuid,
    p_worker_id text,
    p_error_code text,
    p_safe_message text
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, private
as $
declare
    v_job private.analysis_run_jobs%rowtype;
    v_run public.analysis_runs%rowtype;
    v_delay integer;
    v_new_status text;
begin
    select * into v_job
    from private.analysis_run_jobs
    where id = p_job_id
    for update;

    if v_job.id is null or v_job.status <> 'running' or v_job.lock_owner <> p_worker_id then
        raise exception 'Worker lease is no longer valid' using errcode = '42501';
    end if;

    if v_job.attempts >= v_job.max_attempts then
        v_new_status := 'failed';
    else
        v_new_status := 'retrying';
    end if;
    v_delay := least(21600, 900 * (2 ^ greatest(0, v_job.attempts - 1))::integer);

    update private.analysis_run_jobs
       set status = v_new_status,
           available_at = now() + make_interval(secs => v_delay),
           locked_at = null,
           lock_owner = null,
           lease_expires_at = null,
           last_error_code = left(coalesce(p_error_code,'WORKER_ERROR'),80),
           last_error_message = left(coalesce(p_safe_message,'Background worker failed.'),350),
           updated_at = now()
     where id = v_job.id;

    select * into v_run from public.analysis_runs where id = v_job.run_id for update;

    if v_new_status = 'failed' then
        update public.analysis_runs
           set status = 'failed',
               stage = 'failed',
               status_message = 'Background processing reached its retry limit. Previous snapshots remain available.',
               completed_at = now(),
               last_activity_at = now(),
               updated_at = now()
         where id = v_run.id;
    else
        update public.analysis_runs
           set status = 'queued',
               stage = 'retry_scheduled',
               status_message = 'A temporary processing failure occurred. The run is safely queued for retry.',
               last_activity_at = now(),
               updated_at = now()
         where id = v_run.id;
    end if;

    insert into public.analysis_run_events (
        run_id, event_type, from_status, to_status, safe_message, details
    )
    values (
        v_run.id, 'worker_retry', v_run.status, case when v_new_status='failed' then 'failed' else 'queued' end,
        'Background processing will retry according to the job policy.',
        jsonb_build_object('error_code',left(coalesce(p_error_code,'WORKER_ERROR'),80),'attempt',v_job.attempts,'job_status',v_new_status)
    );

    return jsonb_build_object('job_id',v_job.id,'status',v_new_status,'retry_after_seconds',v_delay);
end;
$;

revoke all on function public.retry_analysis_job(uuid, text, text, text) from public, anon, authenticated;
grant execute on function public.retry_analysis_job(uuid, text, text, text) to service_role;

comment on function public.queue_analysis_request(uuid,jsonb) is
    'Creates a user-owned durable analysis request. Trigger enqueues the first background job.';
comment on function public.claim_analysis_job(text,integer) is
    'Service-role-only atomic SKIP LOCKED claim with a bounded lease.';
comment on function public.complete_analysis_job(uuid,text,jsonb) is
    'Service-role-only result/source commit with versioned evidence and delayed-data requeue.';
comment on function public.retry_analysis_job(uuid,text,text,text) is
    'Service-role-only lease release with bounded exponential retry.';
