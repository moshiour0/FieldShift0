-- Allow authenticated owners to persist completed analyses and retrieve them later.
-- All inserts run as the user's JWT role (SECURITY INVOKER), never as service_role.
-- Updates to run lifecycle/results remain unavailable to authenticated clients.

create policy "Users can create their own analysis runs"
    on public.analysis_runs
    for insert to authenticated
    with check ((select auth.uid()) is not null and (select auth.uid()) = user_id);

create policy "Users can create sources for their own runs"
    on public.analysis_run_sources
    for insert to authenticated
    with check (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_run_sources.run_id
          and r.user_id = (select auth.uid())
    ));

create policy "Users can create results for their own runs"
    on public.analysis_results
    for insert to authenticated
    with check (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_results.run_id
          and r.user_id = (select auth.uid())
    ));

create policy "Users can append events to their own runs"
    on public.analysis_run_events
    for insert to authenticated
    with check (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_run_events.run_id
          and r.user_id = (select auth.uid())
    ));

grant insert (
    user_id, client_request_id, request_sha256, request_payload,
    engine_version, source_policy_version, requested_start, requested_end,
    status, stage, progress_percent, status_message, started_at, completed_at
) on public.analysis_runs to authenticated;

grant insert (
    run_id, source_key, source_name, source_type, required, provider, product_key,
    provider_task_id, status, requested_start, requested_end, coverage_start,
    coverage_end, coverage_fraction, attempt_count, max_attempts, next_retry_at,
    last_checked_at, last_error_code, last_error_message, quality, provenance
) on public.analysis_run_sources to authenticated;

grant insert (
    run_id, revision, result_kind, evidence_fingerprint, result_payload, is_current
) on public.analysis_results to authenticated;

grant insert (
    run_id, source_id, event_type, from_status, to_status, safe_message, details
) on public.analysis_run_events to authenticated;

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
    v_source jsonb;
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
        select id into v_run_id
        from public.analysis_runs
        where user_id = v_user_id
          and client_request_id = v_client_request_id;
        return jsonb_build_object(
            'run_id', v_run_id,
            'already_saved', true,
            'result_id', null
        );
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
        );
    end loop;

    insert into public.analysis_results (
        run_id, revision, result_kind, evidence_fingerprint, result_payload, is_current
    )
    values (
        v_run_id,
        1,
        p_result->>'result_kind',
        p_result->>'evidence_fingerprint',
        p_result->'result_payload',
        true
    )
    returning id into v_result_id;

    insert into public.analysis_run_events (
        run_id, event_type, to_status, safe_message, details
    )
    values (
        v_run_id,
        'analysis_saved',
        p_run->>'status',
        p_run->>'status_message',
        jsonb_build_object('source_count', jsonb_array_length(p_sources))
    );

    return jsonb_build_object(
        'run_id', v_run_id,
        'already_saved', false,
        'result_id', v_result_id
    );
end;
$function$;

revoke all on function public.save_completed_analysis(jsonb, jsonb, jsonb) from public, anon;
grant execute on function public.save_completed_analysis(jsonb, jsonb, jsonb) to authenticated;

comment on function public.save_completed_analysis(jsonb, jsonb, jsonb) is
    'Atomically saves one authenticated user’s completed analysis. SECURITY INVOKER; RLS and ownership policies apply.';
