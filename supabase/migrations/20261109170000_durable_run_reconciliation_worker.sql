-- Durable delayed-data reconciliation worker.
-- The scheduler lives in Supabase Postgres; Python science processing runs
-- in a bounded Vercel Function. The browser never owns the worker lifecycle.

create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net;

alter table private.analysis_run_jobs
    add column if not exists lease_expires_at timestamptz,
    add column if not exists heartbeat_at timestamptz;

create index if not exists analysis_run_jobs_lease_idx
    on private.analysis_run_jobs (status, lease_expires_at)
    where status = 'running';

create or replace function private.worker_token_matches(p_token text)
returns boolean
language sql
stable
security definer
set search_path = pg_catalog, vault, extensions
as $function$
    select coalesce(
        p_token is not null
        and length(p_token) >= 48
        and exists (
            select 1
            from vault.decrypted_secrets s
            where s.name = 'fieldshift_worker_secret'
              and extensions.digest(p_token, 'sha256')
                  = extensions.digest(s.decrypted_secret, 'sha256')
        ),
        false
    );
$function$;

revoke all on function private.worker_token_matches(text) from public;
grant usage on schema private to anon;
grant execute on function private.worker_token_matches(text) to anon;

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
          and j.job_type = 'reconcile_run'
          and j.status = 'running'
          and j.lock_owner = 'fieldshift-vercel-worker'
          and j.lease_expires_at > now()
    );
$function$;

revoke all on function private.worker_has_active_lease(uuid) from public;
grant execute on function private.worker_has_active_lease(uuid) to anon;

-- Queue rows are in an unexposed schema. The anon role receives only the
-- minimum table privileges needed by the token-gated SQL RPC.
create policy "Worker can read queue rows with a valid token"
    on private.analysis_run_jobs
    for select to anon
    using (
        private.worker_token_matches(
            (nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        )
    );

create policy "Worker can update queue rows with a valid token"
    on private.analysis_run_jobs
    for update to anon
    using (
        private.worker_token_matches(
            (nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        )
    )
    with check (
        private.worker_token_matches(
            (nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        )
    );

grant select, update on private.analysis_run_jobs to anon;

-- RLS policies for worker writes are tied to a live lease for the exact run.
create policy "Worker can read a run with an active lease"
    on public.analysis_runs
    for select to anon
    using (private.worker_has_active_lease(id));

create policy "Worker can update lifecycle for a leased run"
    on public.analysis_runs
    for update to anon
    using (private.worker_has_active_lease(id))
    with check (private.worker_has_active_lease(id));

create policy "Worker can read sources for a leased run"
    on public.analysis_run_sources
    for select to anon
    using (private.worker_has_active_lease(run_id));

create policy "Worker can insert sources for a leased run"
    on public.analysis_run_sources
    for insert to anon
    with check (private.worker_has_active_lease(run_id));

create policy "Worker can update sources for a leased run"
    on public.analysis_run_sources
    for update to anon
    using (private.worker_has_active_lease(run_id))
    with check (private.worker_has_active_lease(run_id));

create policy "Worker can read results for a leased run"
    on public.analysis_results
    for select to anon
    using (private.worker_has_active_lease(run_id));

create policy "Worker can insert results for a leased run"
    on public.analysis_results
    for insert to anon
    with check (private.worker_has_active_lease(run_id));

create policy "Worker can update current markers for a leased run"
    on public.analysis_results
    for update to anon
    using (private.worker_has_active_lease(run_id))
    with check (private.worker_has_active_lease(run_id));

create policy "Worker can append events for a leased run"
    on public.analysis_run_events
    for insert to anon
    with check (private.worker_has_active_lease(run_id));

grant select on public.analysis_runs, public.analysis_run_sources, public.analysis_results to anon;
grant update (
    status, stage, progress_percent, status_message,
    completed_at, last_activity_at, updated_at
) on public.analysis_runs to anon;
grant insert (
    run_id, source_key, source_name, source_type, required, provider, product_key,
    provider_task_id, status, requested_start, requested_end, coverage_start,
    coverage_end, coverage_fraction, next_retry_at, last_checked_at,
    last_error_code, last_error_message, quality, provenance
) on public.analysis_run_sources to anon;
grant update (
    provider_task_id, status, coverage_start, coverage_end, coverage_fraction,
    next_retry_at, last_checked_at, last_error_code, last_error_message,
    quality, provenance, updated_at
) on public.analysis_run_sources to anon;
grant insert (
    run_id, revision, result_kind, evidence_fingerprint, result_payload, is_current
) on public.analysis_results to anon;
grant update (is_current) on public.analysis_results to anon;
grant insert (
    run_id, source_id, event_type, from_status, to_status, safe_message, details
) on public.analysis_run_events to anon;
grant usage, select on sequence public.analysis_run_events_id_seq to anon;

-- Atomic single-job claim. A global one-worker lease prevents concurrent heavy
-- Python runs on the Free Vercel tier.
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
          and j.job_type = 'reconcile_run'
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

-- Save a refreshed evidence/result revision and finish or reschedule the job.
-- This remains SECURITY INVOKER: the lease-specific RLS policies above apply.
create or replace function public.worker_save_analysis(
    p_worker_token text,
    p_job_id uuid,
    p_run jsonb,
    p_sources jsonb,
    p_result jsonb,
    p_retry_at timestamptz default null
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, private
as $function$
declare
    v_header_token text;
    v_job private.analysis_run_jobs%rowtype;
    v_run public.analysis_runs%rowtype;
    v_source jsonb;
    v_revision integer;
    v_result_id uuid;
    v_existing_fingerprint text;
    v_fingerprint text;
    v_result_payload jsonb;
    v_job_status text;
    v_status_message text;
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
      and lease_expires_at > now();
    if not found then
        raise exception 'Worker job lease is no longer valid' using errcode = '42501';
    end if;

    if not private.worker_has_active_lease(v_job.run_id) then
        raise exception 'Worker run lease is no longer valid' using errcode = '42501';
    end if;

    select * into v_run
    from public.analysis_runs
    where id = v_job.run_id;
    if not found then
        raise exception 'Saved analysis run was not found' using errcode = 'P0002';
    end if;

    if jsonb_typeof(p_run) <> 'object'
       or jsonb_typeof(p_sources) <> 'array'
       or jsonb_typeof(p_result) <> 'object' then
        raise exception 'Invalid worker persistence payload' using errcode = '22023';
    end if;

    for v_source in select value from jsonb_array_elements(p_sources)
    loop
        insert into public.analysis_run_sources (
            run_id, source_key, source_name, source_type, required,
            provider, product_key, provider_task_id, status,
            requested_start, requested_end, coverage_start, coverage_end,
            coverage_fraction, next_retry_at, last_checked_at,
            last_error_code, last_error_message, quality, provenance
        )
        values (
            v_job.run_id,
            coalesce(nullif(v_source->>'source_key', ''), 'unknown_source'),
            coalesce(nullif(v_source->>'source_name', ''), 'Evidence source'),
            coalesce(nullif(v_source->>'source_type', ''), 'unknown'),
            coalesce((v_source->>'required')::boolean, false),
            v_source->>'provider',
            v_source->>'product_key',
            v_source->>'provider_task_id',
            coalesce(nullif(v_source->>'status', ''), 'failed'),
            nullif(v_source->>'requested_start', '')::date,
            nullif(v_source->>'requested_end', '')::date,
            nullif(v_source->>'coverage_start', '')::date,
            nullif(v_source->>'coverage_end', '')::date,
            nullif(v_source->>'coverage_fraction', '')::numeric,
            nullif(v_source->>'next_retry_at', '')::timestamptz,
            now(),
            v_source->>'last_error_code',
            v_source->>'last_error_message',
            coalesce(v_source->'quality', '{}'::jsonb),
            coalesce(v_source->'provenance', '{}'::jsonb)
        )
        on conflict (run_id, source_key) do update
        set provider = excluded.provider,
            product_key = excluded.product_key,
            provider_task_id = coalesce(excluded.provider_task_id, public.analysis_run_sources.provider_task_id),
            status = excluded.status,
            requested_start = excluded.requested_start,
            requested_end = excluded.requested_end,
            coverage_start = excluded.coverage_start,
            coverage_end = excluded.coverage_end,
            coverage_fraction = excluded.coverage_fraction,
            next_retry_at = excluded.next_retry_at,
            last_checked_at = now(),
            last_error_code = excluded.last_error_code,
            last_error_message = excluded.last_error_message,
            quality = excluded.quality,
            provenance = excluded.provenance,
            updated_at = now();
    end loop;

    update public.analysis_runs
       set status = coalesce(nullif(p_run->>'status', ''), status),
           stage = 'analysis_reconciled',
           progress_percent = coalesce((p_run->>'progress_percent')::smallint, 100),
           status_message = p_run->>'status_message',
           completed_at = now(),
           last_activity_at = now(),
           updated_at = now()
     where id = v_job.run_id;

    v_fingerprint := p_result->>'evidence_fingerprint';
    select evidence_fingerprint into v_existing_fingerprint
    from public.analysis_results
    where run_id = v_job.run_id and is_current = true
    order by revision desc
    limit 1;

    if v_existing_fingerprint is distinct from v_fingerprint then
        update public.analysis_results
           set is_current = false
         where run_id = v_job.run_id and is_current = true;

        select coalesce(max(revision), 0) + 1 into v_revision
        from public.analysis_results where run_id = v_job.run_id;

        v_result_payload := coalesce(p_result->'result_payload', '{}'::jsonb);
        v_result_payload := jsonb_set(v_result_payload, '{run,id}', to_jsonb(v_job.run_id::text), true);
        v_result_payload := jsonb_set(v_result_payload, '{run,saved_run_id}', to_jsonb(v_job.run_id::text), true);

        insert into public.analysis_results (
            run_id, revision, result_kind, evidence_fingerprint, result_payload, is_current
        )
        values (
            v_job.run_id,
            v_revision,
            p_result->>'result_kind',
            v_fingerprint,
            v_result_payload,
            true
        )
        returning id into v_result_id;
    else
        select coalesce(max(revision), 1) into v_revision
        from public.analysis_results where run_id = v_job.run_id;
    end if;

    v_job_status := case
        when p_retry_at is null then 'succeeded'
        when v_job.attempts >= v_job.max_attempts then 'failed'
        else 'retrying'
    end;

    update private.analysis_run_jobs
       set status = v_job_status,
           available_at = case when v_job_status = 'retrying' then p_retry_at else available_at end,
           locked_at = null,
           heartbeat_at = now(),
           lease_expires_at = null,
           lock_owner = null,
           last_error_code = case when v_job_status = 'failed' then 'retry_budget_exhausted' else null end,
           last_error_message = case when v_job_status = 'failed' then 'Provider data remained pending after the retry budget.' else null end,
           updated_at = now()
     where id = p_job_id;

    v_status_message := case
        when v_job_status = 'retrying' then 'Evidence is still arriving. The saved analysis will be checked again automatically.'
        when v_job_status = 'failed' then 'Automatic evidence refresh reached its retry limit. The saved result remains available.'
        else 'Evidence reconciliation completed.'
    end;

    insert into public.analysis_run_events (
        run_id, event_type, from_status, to_status, safe_message, details
    )
    values (
        v_job.run_id,
        case when v_existing_fingerprint is distinct from v_fingerprint then 'analysis_revision_created' else 'analysis_rechecked' end,
        v_run.status,
        p_run->>'status',
        v_status_message,
        jsonb_build_object(
            'revision', v_revision,
            'worker_attempt', v_job.attempts,
            'job_status', v_job_status
        )
    );

    return jsonb_build_object(
        'run_id', v_job.run_id,
        'result_id', v_result_id,
        'revision', v_revision,
        'job_status', v_job_status,
        'next_retry_at', case when v_job_status = 'retrying' then p_retry_at else null end
    );
end;
$function$;

revoke all on function public.worker_save_analysis(text, uuid, jsonb, jsonb, jsonb, timestamptz) from public, authenticated;
grant execute on function public.worker_save_analysis(text, uuid, jsonb, jsonb, jsonb, timestamptz) to anon;

create or replace function public.worker_fail_analysis_job(
    p_worker_token text,
    p_job_id uuid,
    p_error_code text,
    p_retry_at timestamptz default null
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, private
as $function$
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
      and lease_expires_at > now();
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

    return jsonb_build_object('job_status', v_status, 'next_retry_at', case when v_status = 'retrying' then p_retry_at else null end);
end;
$function$;

revoke all on function public.worker_fail_analysis_job(text, uuid, text, timestamptz) from public, authenticated;
grant execute on function public.worker_fail_analysis_job(text, uuid, text, timestamptz) to anon;

-- Enqueue one durable reconciliation job when a signed-in run first completes
-- with pending data. A single idempotent job is rescheduled across attempts.
create or replace function private.enqueue_analysis_run_reconciliation()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, private
as $function$
begin
    if new.status not in ('preliminary_ready', 'waiting_for_data') then
        return new;
    end if;

    insert into private.analysis_run_jobs (
        run_id, source_id, job_type, idempotency_key, payload,
        status, attempts, max_attempts, available_at
    )
    values (
        new.id,
        null,
        'reconcile_run',
        'reconcile_run:' || new.id::text,
        jsonb_build_object(
            'run_id', new.id,
            'user_id', new.user_id,
            'client_request_id', new.client_request_id,
            'request_payload', new.request_payload
        ),
        'queued',
        0,
        30,
        now() + interval '1 minute'
    )
    on conflict (idempotency_key) do nothing;

    return new;
end;
$function$;

revoke all on function private.enqueue_analysis_run_reconciliation() from public, anon, authenticated;

drop trigger if exists enqueue_analysis_reconciliation_after_run_insert on public.analysis_runs;
create trigger enqueue_analysis_reconciliation_after_run_insert
after insert on public.analysis_runs
for each row execute function private.enqueue_analysis_run_reconciliation();

create or replace function private.schedule_analysis_reconciliation_from_source()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public, private
as $function$
begin
    if new.status not in ('queued', 'pending', 'retrying') then
        return new;
    end if;

    update private.analysis_run_jobs
       set available_at = case
            when new.next_retry_at is not null then greatest(now() + interval '30 seconds', new.next_retry_at)
            else least(available_at, now() + interval '1 minute')
       end,
           updated_at = now()
     where run_id = new.run_id
       and job_type = 'reconcile_run'
       and status in ('queued', 'retrying');

    return new;
end;
$function$;

revoke all on function private.schedule_analysis_reconciliation_from_source() from public, anon, authenticated;

drop trigger if exists reschedule_analysis_reconciliation_after_source_insert on public.analysis_run_sources;
create trigger reschedule_analysis_reconciliation_after_source_insert
after insert on public.analysis_run_sources
for each row execute function private.schedule_analysis_reconciliation_from_source();

drop trigger if exists reschedule_analysis_reconciliation_after_source_update on public.analysis_run_sources;
create trigger reschedule_analysis_reconciliation_after_source_update
after update of status, next_retry_at on public.analysis_run_sources
for each row execute function private.schedule_analysis_reconciliation_from_source();

comment on table private.analysis_run_jobs is
    'Durable run reconciliation queue. Jobs are claimed with a six-minute lease and retried by Supabase pg_cron.';
comment on function public.claim_analysis_run_job(text) is
    'Claims one reconciliation job using the private worker token in the x-fieldshift-worker request header.';
comment on function public.worker_save_analysis(text, uuid, jsonb, jsonb, jsonb, timestamptz) is
    'Stores a refreshed evidence snapshot for the run tied to the active worker lease. SECURITY INVOKER and RLS protected.';
