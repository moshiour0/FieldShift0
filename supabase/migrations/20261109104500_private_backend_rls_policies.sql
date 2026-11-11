-- Make backend-only access to private tables explicit under RLS.
-- service_role is the only API role granted schema/table access.
create policy "Backend service role manages shared dataset cache"
    on private.dataset_cache
    for all
    to service_role
    using (true)
    with check (true);

create policy "Backend service role manages analysis worker jobs"
    on private.analysis_run_jobs
    for all
    to service_role
    using (true)
    with check (true);
