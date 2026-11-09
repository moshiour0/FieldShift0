-- Keep one token-gated policy per queue operation and evaluate the
-- worker-token predicate once per statement via an initplan.
-- This does not broaden access: the same private token check remains mandatory.

drop policy if exists "FieldShift worker can read queue with token"
    on private.analysis_run_jobs;
drop policy if exists "FieldShift worker can update queue with token"
    on private.analysis_run_jobs;

alter policy "Worker can read queue rows with a valid token"
    on private.analysis_run_jobs
    using (
        (select private.worker_token_matches(
            (nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        ))
    );

alter policy "Worker can update queue rows with a valid token"
    on private.analysis_run_jobs
    using (
        (select private.worker_token_matches(
            (nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        ))
    )
    with check (
        (select private.worker_token_matches(
            (nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        ))
    );

notify pgrst, 'reload schema';
