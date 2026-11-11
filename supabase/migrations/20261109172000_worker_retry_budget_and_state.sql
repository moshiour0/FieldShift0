alter table public.analysis_run_sources alter column max_attempts set default 50;

update private.analysis_run_jobs set max_attempts = 50 where job_type = 'build_result' and status in ('queued','retrying');

CREATE OR REPLACE FUNCTION private.enqueue_initial_analysis_job()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public', 'private'
AS $function$
begin
    if auth.uid() is not null and auth.uid() <> new.user_id then
        raise exception 'Cannot enqueue another user analysis' using errcode = '42501';
    end if;
    insert into private.analysis_run_jobs (
        run_id, job_type, idempotency_key, payload, status, max_attempts, available_at
    )
    values (
        new.id,
        'build_result',
        new.id::text || ':initial',
        jsonb_build_object('reason','initial_analysis'),
        'queued',
        50,
        now()
    )
    on conflict (idempotency_key) do nothing;
    return new;
end;
$function$
;

CREATE OR REPLACE FUNCTION private.worker_has_active_lease(p_run_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE
 SET search_path TO 'pg_catalog', 'private'
AS $function$
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
$function$
;

CREATE OR REPLACE FUNCTION public.claim_analysis_run_job(p_worker_token text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'public', 'private'
AS $function$
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
$function$
;

CREATE OR REPLACE FUNCTION public.worker_save_analysis(p_worker_token text, p_job_id uuid, p_run jsonb, p_sources jsonb, p_result jsonb, p_retry_at timestamp with time zone DEFAULT NULL::timestamp with time zone)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog', 'public', 'private'
AS $function$
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
    v_run_status text;
    v_run_status_message text;
    v_source_key text;
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
        v_source_key := coalesce(nullif(v_source->>'source_key', ''), 'unknown_source');

        -- Update first so the worker needs only narrowly scoped column UPDATE
        -- privileges. INSERT ... ON CONFLICT DO UPDATE requires table-wide
        -- UPDATE permission in PostgreSQL, which would widen the RLS surface.
        update public.analysis_run_sources
           set provider = v_source->>'provider',
               product_key = v_source->>'product_key',
               provider_task_id = coalesce(
                   nullif(v_source->>'provider_task_id', ''),
                   public.analysis_run_sources.provider_task_id
               ),
               status = coalesce(nullif(v_source->>'status', ''), 'failed'),
               requested_start = nullif(v_source->>'requested_start', '')::date,
               requested_end = nullif(v_source->>'requested_end', '')::date,
               coverage_start = nullif(v_source->>'coverage_start', '')::date,
               coverage_end = nullif(v_source->>'coverage_end', '')::date,
               coverage_fraction = nullif(v_source->>'coverage_fraction', '')::numeric,
               attempt_count = public.analysis_run_sources.attempt_count + 1,
               max_attempts = 50,
               next_retry_at = nullif(v_source->>'next_retry_at', '')::timestamptz,
               last_checked_at = now(),
               last_error_code = v_source->>'last_error_code',
               last_error_message = v_source->>'last_error_message',
               quality = coalesce(v_source->'quality', '{}'::jsonb),
               provenance = coalesce(v_source->'provenance', '{}'::jsonb),
               updated_at = now()
         where run_id = v_job.run_id
           and source_key = v_source_key;

        if not found then
            insert into public.analysis_run_sources (
                run_id, source_key, source_name, source_type, required,
                provider, product_key, provider_task_id, status,
                requested_start, requested_end, coverage_start, coverage_end,
                coverage_fraction, attempt_count, max_attempts, next_retry_at, last_checked_at,
                last_error_code, last_error_message, quality, provenance
            )
            values (
                v_job.run_id,
                v_source_key,
                coalesce(nullif(v_source->>'source_name', ''), 'Evidence source'),
                coalesce(nullif(v_source->>'source_type', ''), 'unknown'),
                coalesce((v_source->>'required')::boolean, false),
                v_source->>'provider',
                v_source->>'product_key',
                nullif(v_source->>'provider_task_id', ''),
                coalesce(nullif(v_source->>'status', ''), 'failed'),
                nullif(v_source->>'requested_start', '')::date,
                nullif(v_source->>'requested_end', '')::date,
                nullif(v_source->>'coverage_start', '')::date,
                nullif(v_source->>'coverage_end', '')::date,
                nullif(v_source->>'coverage_fraction', '')::numeric,
                1,
                50,
                nullif(v_source->>'next_retry_at', '')::timestamptz,
                now(),
                v_source->>'last_error_code',
                v_source->>'last_error_message',
                coalesce(v_source->'quality', '{}'::jsonb),
                coalesce(v_source->'provenance', '{}'::jsonb)
            )
            on conflict (run_id, source_key) do nothing;
        end if;
    end loop;

    v_run_status := case
        when p_retry_at is not null then 'waiting_for_data'
        else coalesce(nullif(p_run->>'status', ''), v_run.status)
    end;

    v_run_status_message := case
        when p_retry_at is not null and v_job.attempts >= v_job.max_attempts
            then 'The provider data is still incomplete after the automatic retry window. This run is saved as waiting for data; open it later and request another check.'
        when p_retry_at is not null
            then 'A preliminary evidence snapshot is available. Some provider data is still pending and will be checked again automatically.'
        else coalesce(nullif(p_run->>'status_message', ''), 'Evidence reconciliation completed.')
    end;

    update public.analysis_runs
       set status = v_run_status,
           stage = case
               when p_retry_at is not null and v_job.attempts >= v_job.max_attempts then 'retry_exhausted'
               when p_retry_at is not null then 'waiting_for_datasets'
               else 'analysis_reconciled'
           end,
           progress_percent = case
               when p_retry_at is not null
                   then least(coalesce((p_run->>'progress_percent')::smallint, 75), 75)
               else coalesce((p_run->>'progress_percent')::smallint, 100)
           end,
           status_message = v_run_status_message,
           completed_at = case when p_retry_at is null then now() else null end,
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
        v_result_payload := jsonb_set(v_result_payload, '{run,status}', to_jsonb(v_run_status), true);
        v_result_payload := jsonb_set(v_result_payload, '{run,status_message}', to_jsonb(v_run_status_message), true);
        v_result_payload := jsonb_set(v_result_payload, '{run,is_final}', to_jsonb(v_run_status in ('final_ready','final_with_gaps')), true);

        insert into public.analysis_results (
            run_id, revision, result_kind, evidence_fingerprint, result_payload, is_current
        )
        values (
            v_job.run_id,
            v_revision,
            case when p_retry_at is not null then 'preliminary' else p_result->>'result_kind' end,
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

    v_status_message := case
        when v_job_status = 'retrying' then 'Evidence is still arriving. The saved analysis will be checked again automatically.'
        when v_job_status = 'failed' then 'Automatic evidence refresh reached its retry limit. The saved result remains available.'
        else 'Evidence reconciliation completed.'
    end;

    -- Append the event while the current lease is still active so the
    -- token/lease-gated event RLS policy can authorize this one insert.
    insert into public.analysis_run_events (
        run_id, event_type, from_status, to_status, safe_message, details
    )
    values (
        v_job.run_id,
        case when v_existing_fingerprint is distinct from v_fingerprint then 'analysis_revision_created' else 'analysis_rechecked' end,
        v_run.status,
        v_run_status,
        v_status_message,
        jsonb_build_object(
            'revision', v_revision,
            'worker_attempt', v_job.attempts,
            'job_status', v_job_status
        )
    );

    -- Release the job lease only after every run-scoped write is complete.
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

    return jsonb_build_object(
        'run_id', v_job.run_id,
        'result_id', v_result_id,
        'revision', v_revision,
        'status', v_run_status,
        'status_message', v_run_status_message,
        'job_status', v_job_status,
        'next_retry_at', case when v_job_status = 'retrying' then p_retry_at else null end
    );
end;
$function$
;

comment on function public.claim_analysis_run_job(text) is 'Claims one bounded Vercel worker job, including initial builds and delayed-data reconciliations.';

comment on function public.worker_save_analysis(text, uuid, jsonb, jsonb, jsonb, timestamptz) is 'Saves immutable evidence revisions, reschedules pending providers, and marks retry exhaustion as waiting_for_data rather than final.';