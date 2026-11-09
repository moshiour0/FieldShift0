-- Permit a run owner to refresh only their own lifecycle/evidence fields.
-- No user_id, request snapshot, or result payload columns are updateable directly.

create policy "Users can update lifecycle fields on their own runs"
    on public.analysis_runs
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "Users can update source evidence on their own runs"
    on public.analysis_run_sources
    for update to authenticated
    using (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_run_sources.run_id
          and r.user_id = (select auth.uid())
    ))
    with check (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_run_sources.run_id
          and r.user_id = (select auth.uid())
    ));

create policy "Users can update current marker on their own results"
    on public.analysis_results
    for update to authenticated
    using (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_results.run_id
          and r.user_id = (select auth.uid())
    ))
    with check (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_results.run_id
          and r.user_id = (select auth.uid())
    ));

grant update (
    status, stage, progress_percent, status_message,
    completed_at, last_activity_at, updated_at
) on public.analysis_runs to authenticated;

grant update (
    status, provider_task_id, coverage_start, coverage_end, coverage_fraction,
    next_retry_at, last_checked_at, last_error_code, last_error_message,
    quality, provenance, updated_at
) on public.analysis_run_sources to authenticated;

grant update (is_current) on public.analysis_results to authenticated;

create or replace function public.save_completed_analysis(
    p_run jsonb,
    p_sources jsonb,
    p_result jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $function$
declare
    v_user_id uuid := auth.uid();
    v_client_request_id uuid;
    v_run_id uuid;
    v_result_id uuid;
    v_revision integer;
    v_source jsonb;
    v_existing_status text;
    v_existing_fingerprint text;
    v_result_payload jsonb;
    v_event_type text;
begin
    if v_user_id is null then
        raise exception 'Authentication required' using errcode = '42501';
    end if;
    if jsonb_typeof(p_run) <> 'object'
       or jsonb_typeof(p_sources) <> 'array'
       or jsonb_typeof(p_result) <> 'object' then
        raise exception 'Invalid analysis persistence payload' using errcode = '22023';
    end if;

    v_client_request_id := (p_run->>'client_request_id')::uuid;

    select id, status
      into v_run_id, v_existing_status
    from public.analysis_runs
    where user_id = v_user_id
      and client_request_id = v_client_request_id;

    if v_run_id is null then
        insert into public.analysis_runs (
            user_id, client_request_id, request_sha256, request_payload,
            engine_version, source_policy_version, requested_start, requested_end,
            status, stage, progress_percent, status_message, started_at, completed_at
        )
        values (
            v_user_id,
            v_client_request_id,
            p_run->>'request_sha256',
            coalesce(p_run->'request_payload', '{}'::jsonb),
            coalesce(nullif(p_run->>'engine_version', ''), 'unknown'),
            coalesce(nullif(p_run->>'source_policy_version', ''), 'v1'),
            (p_run->>'requested_start')::date,
            (p_run->>'requested_end')::date,
            p_run->>'status',
            'analysis_complete',
            coalesce((p_run->>'progress_percent')::smallint, 100),
            p_run->>'status_message',
            now(),
            now()
        )
        on conflict (user_id, client_request_id) do nothing
        returning id into v_run_id;

        if v_run_id is null then
            select id, status
              into v_run_id, v_existing_status
            from public.analysis_runs
            where user_id = v_user_id
              and client_request_id = v_client_request_id;
        end if;
    end if;

    select evidence_fingerprint
      into v_existing_fingerprint
    from public.analysis_results
    where run_id = v_run_id
      and is_current = true
    order by revision desc
    limit 1;

    if v_existing_fingerprint = p_result->>'evidence_fingerprint'
       and v_existing_status = p_run->>'status' then
        select coalesce(max(revision), 1)
          into v_revision
        from public.analysis_results
        where run_id = v_run_id;
        return jsonb_build_object(
            'run_id', v_run_id,
            'already_saved', true,
            'revision', v_revision,
            'result_id', null
        );
    end if;

    if v_existing_status is not null then
        update public.analysis_runs
        set status = p_run->>'status',
            stage = 'analysis_complete',
            progress_percent = coalesce((p_run->>'progress_percent')::smallint, 100),
            status_message = p_run->>'status_message',
            completed_at = now(),
            last_activity_at = now(),
            updated_at = now()
        where id = v_run_id;

        update public.analysis_results
        set is_current = false
        where run_id = v_run_id
          and is_current = true;

        v_event_type := 'analysis_refreshed';
    else
        v_event_type := 'analysis_saved';
    end if;

    for v_source in select value from jsonb_array_elements(p_sources)
    loop
        insert into public.analysis_run_sources (
            run_id, source_key, source_name, source_type, required,
            provider, product_key, status, requested_start, requested_end,
            coverage_start, coverage_end, coverage_fraction, quality, provenance
        )
        values (
            v_run_id,
            coalesce(nullif(v_source->>'source_key', ''), 'unknown_source'),
            coalesce(nullif(v_source->>'source_name', ''), 'Evidence source'),
            coalesce(nullif(v_source->>'source_type', ''), 'unknown'),
            coalesce((v_source->>'required')::boolean, false),
            v_source->>'provider',
            v_source->>'product_key',
            coalesce(nullif(v_source->>'status', ''), 'failed'),
            nullif(v_source->>'requested_start', '')::date,
            nullif(v_source->>'requested_end', '')::date,
            nullif(v_source->>'coverage_start', '')::date,
            nullif(v_source->>'coverage_end', '')::date,
            nullif(v_source->>'coverage_fraction', '')::numeric,
            coalesce(v_source->'quality', '{}'::jsonb),
            coalesce(v_source->'provenance', '{}'::jsonb)
        )
        on conflict (run_id, source_key) do update
        set status = excluded.status,
            provider_task_id = excluded.provider_task_id,
            coverage_start = excluded.coverage_start,
            coverage_end = excluded.coverage_end,
            coverage_fraction = excluded.coverage_fraction,
            quality = excluded.quality,
            provenance = excluded.provenance,
            updated_at = now();
    end loop;

    select coalesce(max(revision), 0) + 1
      into v_revision
    from public.analysis_results
    where run_id = v_run_id;

    v_result_payload := p_result->'result_payload';
    v_result_payload := jsonb_set(
        v_result_payload,
        '{run,id}',
        to_jsonb(v_run_id::text),
        true
    );
    v_result_payload := jsonb_set(
        v_result_payload,
        '{run,saved_run_id}',
        to_jsonb(v_run_id::text),
        true
    );

    insert into public.analysis_results (
        run_id, revision, result_kind, evidence_fingerprint, result_payload, is_current
    )
    values (
        v_run_id,
        v_revision,
        p_result->>'result_kind',
        p_result->>'evidence_fingerprint',
        v_result_payload,
        true
    )
    returning id into v_result_id;

    insert into public.analysis_run_events (
        run_id, event_type, from_status, to_status, safe_message, details
    )
    values (
        v_run_id,
        v_event_type,
        v_existing_status,
        p_run->>'status',
        p_run->>'status_message',
        jsonb_build_object('source_count', jsonb_array_length(p_sources), 'revision', v_revision)
    );

    return jsonb_build_object(
        'run_id', v_run_id,
        'already_saved', false,
        'revision', v_revision,
        'result_id', v_result_id
    );
end;
$function$;

comment on function public.save_completed_analysis(jsonb, jsonb, jsonb) is
    'Atomically saves or appends an evidence revision for one authenticated user. SECURITY INVOKER; RLS applies.';
