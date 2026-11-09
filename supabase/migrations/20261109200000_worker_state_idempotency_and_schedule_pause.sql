-- Reconcile the durable worker's public status semantics, idempotency and schedule.
-- Pending provider products must never be presented as a final result, even when
-- the synchronous science engine produced a final_with_gaps snapshot.
-- Concurrent queue submits with the same idempotency key must reuse one run.

do $pause$
declare
    v_job record;
begin
    for v_job in
        select jobid
        from cron.job
        where jobname in ('fieldshift-analysis-worker','fieldshift-analysis-reconciliation')
    loop
        perform cron.unschedule(v_job.jobid);
    end loop;
end;
$pause$;

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
            coverage_fraction, attempt_count, max_attempts, next_retry_at, last_checked_at,
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
            1,
            50,
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
            attempt_count = public.analysis_run_sources.attempt_count + 1,
            max_attempts = 50,
            next_retry_at = excluded.next_retry_at,
            last_checked_at = now(),
            last_error_code = excluded.last_error_code,
            last_error_message = excluded.last_error_message,
            quality = excluded.quality,
            provenance = excluded.provenance,
            updated_at = now();
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
        v_run_status,
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
        'status', v_run_status,
        'status_message', v_run_status_message,
        'job_status', v_job_status,
        'next_retry_at', case when v_job_status = 'retrying' then p_retry_at else null end
    );
end;
$function$
;

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
    on conflict (user_id, client_request_id) do nothing
    returning id into v_run_id;

    if v_run_id is null then
        -- Close the concurrent-submit race: the winning request owns this
        -- idempotency key. Reuse it only when the payload hash also matches.
        select id, request_sha256
          into v_existing_id, v_existing_hash
        from public.analysis_runs
        where user_id = v_user_id
          and client_request_id = p_client_request_id;

        if v_existing_id is null then
            raise exception 'The analysis request could not be queued. Please retry.' using errcode = '40001';
        end if;
        if v_existing_hash <> v_request_hash then
            raise exception 'client_request_id was already used for a different request' using errcode = '23505';
        end if;
        return jsonb_build_object('run_id', v_existing_id, 'status', 'queued', 'already_queued', true);
    end if;

    return jsonb_build_object('run_id', v_run_id, 'status', 'queued', 'already_queued', false);
end;
$function$;

notify pgrst, 'reload schema';
