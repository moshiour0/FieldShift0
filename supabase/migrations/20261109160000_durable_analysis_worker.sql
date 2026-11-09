-- Durable server-side analysis queue. Browser users may enqueue only jobs for
-- their own run; only service_role can claim, mutate, and complete worker jobs.

alter table private.analysis_run_jobs set schema public;

revoke all on table public.analysis_run_jobs from anon, authenticated;
grant insert (
    run_id, job_type, idempotency_key, payload, status, max_attempts, available_at
) on public.analysis_run_jobs to authenticated;

create policy "Users can enqueue their own analysis jobs"
    on public.analysis_run_jobs
    for insert to authenticated
    with check (
        status = 'queued'
        and attempts = 0
        and max_attempts between 1 and 8
        and locked_at is null
        and lock_owner is null
        and job_type = 'build_result'
        and exists (
            select 1 from public.analysis_runs r
            where r.id = analysis_run_jobs.run_id
              and r.user_id = (select auth.uid())
        )
    );

create table private.analysis_worker_locks (
    lock_key text primary key,
    owner_id uuid,
    locked_until timestamptz,
    updated_at timestamptz not null default now()
);
alter table private.analysis_worker_locks enable row level security;
revoke all on private.analysis_worker_locks from public, anon, authenticated;
grant all privileges on private.analysis_worker_locks to service_role;
create policy "Backend service role manages worker locks"
    on private.analysis_worker_locks
    for all to service_role
    using (true)
    with check (true);
insert into private.analysis_worker_locks(lock_key)
values ('fieldshift-analysis-worker')
on conflict (lock_key) do nothing;

create or replace function public.claim_fieldshift_analysis_job(p_worker_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, private
as $function$
declare
    v_lock private.analysis_worker_locks%rowtype;
    v_job public.analysis_run_jobs%rowtype;
    v_run public.analysis_runs%rowtype;
begin
    if p_worker_id is null then
        raise exception 'Worker identity is required' using errcode = '22023';
    end if;

    select * into v_lock
    from private.analysis_worker_locks
    where lock_key = 'fieldshift-analysis-worker'
    for update;

    if not found then
        raise exception 'Worker lock row is missing';
    end if;
    if v_lock.locked_until is not null and v_lock.locked_until > now() then
        return null;
    end if;

    update private.analysis_worker_locks
    set owner_id = p_worker_id,
        locked_until = now() + interval '4 minutes',
        updated_at = now()
    where lock_key = 'fieldshift-analysis-worker';

    select * into v_job
    from public.analysis_run_jobs
    where (
        status in ('queued', 'retrying')
        and available_at <= now()
    ) or (
        status = 'running'
        and locked_at < now() - interval '4 minutes'
    )
    order by available_at, created_at
    for update skip locked
    limit 1;

    if not found then
        update private.analysis_worker_locks
        set owner_id = null, locked_until = null, updated_at = now()
        where lock_key = 'fieldshift-analysis-worker'
          and owner_id = p_worker_id;
        return null;
    end if;

    update public.analysis_run_jobs
    set status = 'running',
        attempts = attempts + 1,
        locked_at = now(),
        lock_owner = p_worker_id::text,
        updated_at = now(),
        last_error_code = null,
        last_error_message = null
    where id = v_job.id
    returning * into v_job;

    select * into v_run
    from public.analysis_runs
    where id = v_job.run_id
    for update;

    if not found or v_run.status in ('cancelled', 'failed') then
        update public.analysis_run_jobs
        set status = 'cancelled', locked_at = null, lock_owner = null, updated_at = now()
        where id = v_job.id;
        update private.analysis_worker_locks
        set owner_id = null, locked_until = null, updated_at = now()
        where lock_key = 'fieldshift-analysis-worker'
          and owner_id = p_worker_id;
        return null;
    end if;

    update public.analysis_runs
    set status = 'running',
        stage = 'processing_evidence',
        progress_percent = greatest(progress_percent, 10),
        status_message = 'Queued analysis is being processed. Dataset checks continue independently of this browser session.',
        started_at = coalesce(started_at, now()),
        last_activity_at = now(),
        updated_at = now()
    where id = v_run.id
    returning * into v_run;

    return jsonb_build_object(
        'job', to_jsonb(v_job),
        'run', jsonb_build_object(
            'id', v_run.id,
            'user_id', v_run.user_id,
            'client_request_id', v_run.client_request_id,
            'request_sha256', v_run.request_sha256,
            'request_payload', v_run.request_payload,
            'engine_version', v_run.engine_version,
            'source_policy_version', v_run.source_policy_version,
            'requested_start', v_run.requested_start,
            'requested_end', v_run.requested_end,
            'status', v_run.status
        )
    );
end;
$function$;
revoke all on function public.claim_fieldshift_analysis_job(uuid) from public, anon, authenticated;
grant execute on function public.claim_fieldshift_analysis_job(uuid) to service_role;

create or replace function public.save_fieldshift_worker_result(
    p_run_id uuid,
    p_user_id uuid,
    p_result jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, private
as $function$
declare
    v_run public.analysis_runs%rowtype;
    v_item jsonb;
    v_evidence jsonb;
    v_status text;
    v_result_kind text;
    v_fingerprint text;
    v_revision integer;
    v_result_id uuid;
    v_payload jsonb;
    v_source_status text;
    v_start date;
    v_end date;
    v_existing_fingerprint text;
begin
    if p_run_id is null or p_user_id is null or jsonb_typeof(p_result) <> 'object' then
        raise exception 'Invalid worker result payload' using errcode = '22023';
    end if;

    select * into v_run
    from public.analysis_runs
    where id = p_run_id
      and user_id = p_user_id
    for update;

    if not found then
        raise exception 'Analysis run does not exist for this owner' using errcode = '42501';
    end if;

    v_status := coalesce(p_result #>> '{run,status}', 'preliminary_ready');
    if v_status not in ('queued','running','preliminary_ready','waiting_for_data',
                        'final_ready','final_with_gaps','failed','cancelled') then
        raise exception 'Worker returned an unsupported run status' using errcode = '22023';
    end if;
    v_start := coalesce(nullif(p_result #>> '{run,evidence_window,start_date}', '')::date, v_run.requested_start);
    v_end := coalesce(nullif(p_result #>> '{run,evidence_window,end_date}', '')::date, v_run.requested_end);

    v_evidence := coalesce(p_result #> '{evidence,items}', '[]'::jsonb);
    if jsonb_typeof(v_evidence) <> 'array' then
        raise exception 'Worker evidence items must be an array' using errcode = '22023';
    end if;

    v_fingerprint := encode(
        extensions.digest(convert_to(v_evidence::text, 'UTF8'), 'sha256'),
        'hex'
    );
    v_result_kind := case
        when v_status = 'final_ready' then 'final'
        when v_status = 'final_with_gaps' then 'final_with_gaps'
        else 'preliminary'
    end;

    for v_item in select value from jsonb_array_elements(v_evidence)
    loop
        v_source_status := lower(coalesce(v_item->>'status', 'failed'));
        v_source_status := case v_source_status
            when 'ready' then 'available'
            when 'error' then 'failed'
            when 'fallback' then 'failed'
            else v_source_status
        end;
        if v_source_status not in ('queued','pending','retrying','available','partial',
                                   'stale','unavailable','not_configured','failed','skipped') then
            v_source_status := 'failed';
        end if;

        insert into public.analysis_run_sources (
            run_id, source_key, source_name, source_type, required,
            provider, product_key, status, requested_start, requested_end,
            quality, provenance
        )
        values (
            p_run_id,
            coalesce(nullif(v_item->>'source_key',''), 'unknown_source'),
            coalesce(nullif(v_item->>'name',''), 'Evidence source'),
            coalesce(nullif(v_item->>'source_type',''), 'unknown'),
            coalesce((v_item->>'required')::boolean, false),
            v_item->>'provider',
            v_item->>'product_key',
            v_source_status,
            v_start,
            v_end,
            jsonb_strip_nulls(jsonb_build_object(
                'quality_status', v_item->'quality_status',
                'quality_note', v_item->'quality_note',
                'coverage', v_item->'coverage',
                'confidence', v_item->'confidence'
            )),
            jsonb_strip_nulls(jsonb_build_object(
                'retrieval_mode', v_item->'retrieval_mode',
                'citation', v_item->'citation',
                'data_start_date', v_item->'data_start_date',
                'data_end_date', v_item->'data_end_date',
                'temporal_resolution', v_item->'temporal_resolution',
                'spatial_resolution', v_item->'spatial_resolution'
            ))
        )
        on conflict (run_id, source_key) do update
        set source_name = excluded.source_name,
            source_type = excluded.source_type,
            required = excluded.required,
            provider = excluded.provider,
            product_key = excluded.product_key,
            status = excluded.status,
            requested_start = excluded.requested_start,
            requested_end = excluded.requested_end,
            quality = excluded.quality,
            provenance = excluded.provenance,
            last_checked_at = now(),
            updated_at = now();
    end loop;

    select evidence_fingerprint into v_existing_fingerprint
    from public.analysis_results
    where run_id = p_run_id and is_current = true
    order by revision desc
    limit 1;

    if v_existing_fingerprint = v_fingerprint
       and v_run.status = v_status then
        select coalesce(max(revision), 1) into v_revision
        from public.analysis_results where run_id = p_run_id;
        return jsonb_build_object(
            'run_id', p_run_id,
            'revision', v_revision,
            'already_saved', true,
            'status', v_status
        );
    end if;

    update public.analysis_results
    set is_current = false
    where run_id = p_run_id and is_current = true;

    select coalesce(max(revision), 0) + 1 into v_revision
    from public.analysis_results where run_id = p_run_id;

    v_payload := jsonb_set(p_result, '{run,id}', to_jsonb(p_run_id::text), true);
    v_payload := jsonb_set(v_payload, '{run,saved_run_id}', to_jsonb(p_run_id::text), true);

    insert into public.analysis_results (
        run_id, revision, result_kind, evidence_fingerprint, result_payload, is_current
    )
    values (
        p_run_id, v_revision, v_result_kind, v_fingerprint, v_payload, true
    )
    returning id into v_result_id;

    update public.analysis_runs
    set status = v_status,
        stage = 'analysis_complete',
        progress_percent = case when v_status in ('final_ready','final_with_gaps') then 100 else 75 end,
        status_message = coalesce(p_result #>> '{run,status_message}', 'Analysis result saved.'),
        latest_result_id = v_result_id,
        completed_at = case when v_status in ('final_ready','final_with_gaps','failed','cancelled') then now() else null end,
        last_activity_at = now(),
        updated_at = now()
    where id = p_run_id;

    insert into public.analysis_run_events (
        run_id, event_type, from_status, to_status, safe_message, details
    )
    values (
        p_run_id,
        case when v_revision = 1 then 'analysis_worker_completed' else 'analysis_worker_refreshed' end,
        v_run.status,
        v_status,
        coalesce(p_result #>> '{run,status_message}', 'Analysis result saved.'),
        jsonb_build_object('revision',v_revision,'source_count',jsonb_array_length(v_evidence))
    );

    return jsonb_build_object(
        'run_id', p_run_id,
        'revision', v_revision,
        'result_id', v_result_id,
        'already_saved', false,
        'status', v_status
    );
end;
$function$;
revoke all on function public.save_fieldshift_worker_result(uuid, uuid, jsonb) from public, anon, authenticated;
grant execute on function public.save_fieldshift_worker_result(uuid, uuid, jsonb) to service_role;

create or replace function public.finish_fieldshift_analysis_job(
    p_worker_id uuid,
    p_job_id uuid,
    p_retry_seconds integer default 0,
    p_error_code text default null,
    p_error_message text default null
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public, private
as $function$
declare
    v_job public.analysis_run_jobs%rowtype;
    v_status text;
    v_delay integer := greatest(30, least(86400, coalesce(p_retry_seconds, 0)));
begin
    select * into v_job
    from public.analysis_run_jobs
    where id = p_job_id
      and status = 'running'
      and lock_owner = p_worker_id::text
    for update;

    if not found then
        return jsonb_build_object('updated',false,'reason','job lease is not owned by this worker');
    end if;

    if p_error_code is not null or coalesce(p_retry_seconds,0) > 0 then
        if v_job.attempts >= v_job.max_attempts then
            v_status := 'failed';
            update public.analysis_run_jobs
            set status = 'failed',
                locked_at = null,
                lock_owner = null,
                last_error_code = left(coalesce(p_error_code,'provider_data_pending'),80),
                last_error_message = left(coalesce(p_error_message,'Automatic retry limit reached.'),350),
                updated_at = now()
            where id = p_job_id;
            update public.analysis_runs
            set status = case when p_error_code is null then 'waiting_for_data' else 'failed' end,
                status_message = case when p_error_code is null
                    then 'Automatic data checks reached their retry limit. Open this run and request another check when the provider publishes new data.'
                    else 'The background worker could not complete this analysis after bounded retries.' end,
                progress_percent = case when p_error_code is null then greatest(progress_percent,75) else progress_percent end,
                completed_at = null,
                last_activity_at = now(),
                updated_at = now()
            where id = v_job.run_id;
        else
            v_status := 'retrying';
            update public.analysis_run_jobs
            set status = 'retrying',
                available_at = now() + make_interval(secs => v_delay),
                locked_at = null,
                lock_owner = null,
                last_error_code = left(coalesce(p_error_code,'provider_data_pending'),80),
                last_error_message = left(coalesce(p_error_message,'Waiting for provider data.'),350),
                updated_at = now()
            where id = p_job_id;
        end if;
    else
        v_status := 'succeeded';
        update public.analysis_run_jobs
        set status = 'succeeded',
            locked_at = null,
            lock_owner = null,
            last_error_code = null,
            last_error_message = null,
            updated_at = now()
        where id = p_job_id;
    end if;

    update private.analysis_worker_locks
    set owner_id = null, locked_until = null, updated_at = now()
    where lock_key = 'fieldshift-analysis-worker'
      and owner_id = p_worker_id;

    return jsonb_build_object('updated',true,'job_status',v_status,'attempts',v_job.attempts);
end;
$function$;
revoke all on function public.finish_fieldshift_analysis_job(uuid, uuid, integer, text, text) from public, anon, authenticated;
grant execute on function public.finish_fieldshift_analysis_job(uuid, uuid, integer, text, text) to service_role;

create or replace function public.get_fieldshift_worker_config()
returns jsonb
language sql
security invoker
set search_path = pg_catalog, public
as $function$
    select jsonb_object_agg(name, decrypted_secret)
    from vault.decrypted_secrets
    where name in (
        'fieldshift_worker_token',
        'fieldshift_worker_url',
        'fieldshift_vercel_bypass_secret'
    );
$function$;
revoke all on function public.get_fieldshift_worker_config() from public, anon, authenticated;
grant execute on function public.get_fieldshift_worker_config() to service_role;

comment on table public.analysis_run_jobs is
    'Durable FieldShift worker queue; owners may enqueue only their own build job, while service_role controls claims and retries.';
comment on table private.analysis_worker_locks is
    'Singleton lease preventing overlapping scheduled analysis workers.';
