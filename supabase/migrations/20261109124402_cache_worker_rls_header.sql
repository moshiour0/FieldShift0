-- Cache the request-header setting once per statement in the worker RLS
-- predicates. The worker-token validator and allowed role remain unchanged.

alter policy "Worker can read queue rows with a valid token"
    on private.analysis_run_jobs
    using (
        (select private.worker_token_matches(
            (select nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        ))
    );

alter policy "Worker can update queue rows with a valid token"
    on private.analysis_run_jobs
    using (
        (select private.worker_token_matches(
            (select nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        ))
    )
    with check (
        (select private.worker_token_matches(
            (select nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        ))
    );

notify pgrst, 'reload schema';
