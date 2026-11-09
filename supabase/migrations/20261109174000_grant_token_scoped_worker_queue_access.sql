-- A worker request is a low-privilege anon Data API call carrying a
-- second, high-entropy token. Table grants plus token-gated RLS are required:
-- GRANT alone is not enough to make an untrusted client a worker.

grant usage on schema private to anon;
grant select, update on table private.analysis_run_jobs to anon;

-- The worker increments per-source retry counters during the token-gated upsert.
-- Keep these as narrow column grants; do not grant table-wide INSERT/UPDATE.
grant insert (attempt_count, max_attempts)
    on table public.analysis_run_sources to anon;
grant update (
    provider, product_key, requested_start, requested_end,
    attempt_count, max_attempts
) on table public.analysis_run_sources to anon;
alter table private.analysis_run_jobs alter column max_attempts set default 50;

drop policy if exists "FieldShift worker can read queue with token" on private.analysis_run_jobs;
drop policy if exists "FieldShift worker can update queue with token" on private.analysis_run_jobs;

create policy "FieldShift worker can read queue with token"
    on private.analysis_run_jobs
    for select to anon
    using (
        private.worker_token_matches(
            (nullif(current_setting('request.headers', true), '')::jsonb ->> 'x-fieldshift-worker')
        )
    );

create policy "FieldShift worker can update queue with token"
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
