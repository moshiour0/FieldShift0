-- Keep internal coordination and shared cache data outside the exposed Data API schema.
-- These tables remain backend-only; public user-facing records stay in public with RLS.
create schema if not exists private;

revoke all on schema private from public, anon, authenticated;
grant usage on schema private to service_role;

alter table public.dataset_cache set schema private;
alter table public.analysis_run_jobs set schema private;

grant all privileges on table private.dataset_cache, private.analysis_run_jobs to service_role;

-- Cover foreign keys used for cache references and source/job event traversal.
create index analysis_run_sources_cache_idx
    on public.analysis_run_sources (cache_id);

create index analysis_run_jobs_source_idx
    on private.analysis_run_jobs (source_id);

create index analysis_run_events_source_idx
    on public.analysis_run_events (source_id);

comment on schema private is
    'Unexposed backend-only schema for FieldShift internal cache and worker coordination.';
