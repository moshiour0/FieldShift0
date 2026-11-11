-- Persistent Analysis lifecycle schema for FieldShift / KrishiNexus.
-- Do not apply to a project until the FieldShift Supabase project identity is confirmed.
-- Browser access is owner-scoped through RLS. Worker and API writes are service-role only.

create table public.user_profiles (
    user_id uuid primary key references auth.users (id) on delete cascade,
    display_name text check (display_name is null or char_length(display_name) <= 80),
    locale text not null default 'bn' check (locale in ('bn', 'en')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.dataset_cache (
    id uuid primary key default gen_random_uuid(),
    cache_key text not null unique,
    provider text not null,
    product_key text not null,
    layer_key text not null,
    location_key text not null,
    latitude double precision,
    longitude double precision,
    requested_start date not null,
    requested_end date not null,
    coverage_start date,
    coverage_end date,
    native_temporal_resolution text,
    spatial_resolution text,
    processing_version text not null,
    storage_provider text not null check (storage_provider in ('google_drive', 'supabase_storage')),
    object_key text not null,
    content_sha256 char(64) not null check (content_sha256 ~ '^[0-9a-f]{64}$'),
    state text not null default 'candidate' check (state in ('candidate', 'verified', 'quarantined')),
    coverage_fraction numeric(6,5) check (coverage_fraction is null or (coverage_fraction >= 0 and coverage_fraction <= 1)),
    quality jsonb not null default '{}'::jsonb,
    provenance jsonb not null default '{}'::jsonb,
    verified_at timestamptz,
    created_at timestamptz not null default now(),
    last_accessed_at timestamptz,
    check (requested_end >= requested_start),
    check (coverage_end is null or coverage_start is null or coverage_end >= coverage_start),
    check ((state = 'verified' and verified_at is not null) or state <> 'verified')
);

create index dataset_cache_lookup_idx
    on public.dataset_cache (provider, product_key, location_key, requested_start, requested_end, state);

create table public.analysis_runs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    client_request_id uuid not null,
    request_sha256 char(64) not null check (request_sha256 ~ '^[0-9a-f]{64}$'),
    request_payload jsonb not null,
    engine_version text not null,
    source_policy_version text not null default 'v1',
    requested_start date not null,
    requested_end date not null,
    status text not null default 'queued'
        check (status in ('queued', 'running', 'preliminary_ready', 'waiting_for_data',
                          'final_ready', 'final_with_gaps', 'failed', 'cancelled')),
    stage text not null default 'accepted',
    progress_percent smallint not null default 0 check (progress_percent between 0 and 100),
    status_message text,
    latest_result_id uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    started_at timestamptz,
    completed_at timestamptz,
    last_activity_at timestamptz not null default now(),
    unique (user_id, client_request_id),
    check (requested_end >= requested_start)
);

create index analysis_runs_owner_created_idx
    on public.analysis_runs (user_id, created_at desc);
create index analysis_runs_status_activity_idx
    on public.analysis_runs (status, last_activity_at);

create table public.analysis_run_sources (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.analysis_runs (id) on delete cascade,
    source_key text not null,
    source_name text not null,
    source_type text not null,
    required boolean not null default false,
    provider text,
    product_key text,
    provider_task_id text,
    status text not null default 'queued'
        check (status in ('queued', 'pending', 'retrying', 'available', 'partial',
                          'stale', 'unavailable', 'not_configured', 'failed', 'skipped')),
    requested_start date,
    requested_end date,
    coverage_start date,
    coverage_end date,
    coverage_fraction numeric(6,5) check (coverage_fraction is null or (coverage_fraction >= 0 and coverage_fraction <= 1)),
    cache_id uuid references public.dataset_cache (id) on delete set null,
    attempt_count integer not null default 0 check (attempt_count >= 0),
    max_attempts integer not null default 8 check (max_attempts between 1 and 50),
    next_retry_at timestamptz,
    last_checked_at timestamptz,
    last_error_code text,
    last_error_message text,
    quality jsonb not null default '{}'::jsonb,
    provenance jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (run_id, source_key),
    check (requested_end is null or requested_start is null or requested_end >= requested_start),
    check (coverage_end is null or coverage_start is null or coverage_end >= coverage_start)
);

create index analysis_run_sources_status_retry_idx
    on public.analysis_run_sources (status, next_retry_at);
create index analysis_run_sources_run_idx
    on public.analysis_run_sources (run_id);

create table public.analysis_run_jobs (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.analysis_runs (id) on delete cascade,
    source_id uuid references public.analysis_run_sources (id) on delete cascade,
    job_type text not null check (job_type in ('process_source', 'reconcile_run', 'build_result')),
    idempotency_key text not null unique,
    payload jsonb not null default '{}'::jsonb,
    status text not null default 'queued'
        check (status in ('queued', 'running', 'retrying', 'succeeded', 'failed', 'cancelled')),
    attempts integer not null default 0 check (attempts >= 0),
    max_attempts integer not null default 8 check (max_attempts between 1 and 50),
    available_at timestamptz not null default now(),
    locked_at timestamptz,
    lock_owner text,
    last_error_code text,
    last_error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index analysis_run_jobs_claim_idx
    on public.analysis_run_jobs (available_at, created_at)
    where status in ('queued', 'retrying');
create index analysis_run_jobs_run_idx
    on public.analysis_run_jobs (run_id, created_at);

create table public.analysis_results (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references public.analysis_runs (id) on delete cascade,
    revision integer not null check (revision >= 1),
    result_kind text not null check (result_kind in ('preliminary', 'final', 'final_with_gaps')),
    evidence_fingerprint char(64) not null check (evidence_fingerprint ~ '^[0-9a-f]{64}$'),
    result_payload jsonb not null,
    is_current boolean not null default true,
    created_at timestamptz not null default now(),
    unique (run_id, revision)
);

create unique index analysis_results_one_current_idx
    on public.analysis_results (run_id)
    where is_current;

create table public.analysis_run_events (
    id bigint generated always as identity primary key,
    run_id uuid not null references public.analysis_runs (id) on delete cascade,
    source_id uuid references public.analysis_run_sources (id) on delete cascade,
    event_type text not null,
    from_status text,
    to_status text,
    safe_message text,
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index analysis_run_events_run_created_idx
    on public.analysis_run_events (run_id, created_at);

alter table public.user_profiles enable row level security;
alter table public.dataset_cache enable row level security;
alter table public.analysis_runs enable row level security;
alter table public.analysis_run_sources enable row level security;
alter table public.analysis_run_jobs enable row level security;
alter table public.analysis_results enable row level security;
alter table public.analysis_run_events enable row level security;

create policy "Users can read their own profile"
    on public.user_profiles for select to authenticated
    using ((select auth.uid()) = user_id);
create policy "Users can create their own profile"
    on public.user_profiles for insert to authenticated
    with check ((select auth.uid()) = user_id);
create policy "Users can update their own profile"
    on public.user_profiles for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "Users can read their own analysis runs"
    on public.analysis_runs for select to authenticated
    using ((select auth.uid()) = user_id);

create policy "Users can read sources belonging to their own runs"
    on public.analysis_run_sources for select to authenticated
    using (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_run_sources.run_id
          and r.user_id = (select auth.uid())
    ));

create policy "Users can read results belonging to their own runs"
    on public.analysis_results for select to authenticated
    using (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_results.run_id
          and r.user_id = (select auth.uid())
    ));

create policy "Users can read events belonging to their own runs"
    on public.analysis_run_events for select to authenticated
    using (exists (
        select 1 from public.analysis_runs r
        where r.id = analysis_run_events.run_id
          and r.user_id = (select auth.uid())
    ));

-- No authenticated/anon policies or grants exist for shared cache and worker jobs.
-- These tables are private backend data. RLS remains enabled as defense in depth.
revoke all on public.user_profiles, public.dataset_cache, public.analysis_runs,
    public.analysis_run_sources, public.analysis_run_jobs, public.analysis_results,
    public.analysis_run_events from anon, authenticated;

grant select, insert, update on public.user_profiles to authenticated;
grant select on public.analysis_runs, public.analysis_run_sources,
    public.analysis_results, public.analysis_run_events to authenticated;

grant all privileges on public.user_profiles, public.dataset_cache, public.analysis_runs,
    public.analysis_run_sources, public.analysis_run_jobs, public.analysis_results,
    public.analysis_run_events to service_role;

grant usage, select on sequence public.analysis_run_events_id_seq to service_role;

comment on table public.analysis_runs is
    'Durable user-owned FieldShift analysis request and lifecycle state. Browser writes are prohibited.';
comment on table public.analysis_run_sources is
    'Per-source provider task, coverage, provenance, QA, and retry state for an analysis run.';
comment on table public.dataset_cache is
    'Private shared cache metadata. Only verified exact-match objects are eligible for reuse.';
comment on table public.analysis_run_jobs is
    'Private durable worker queue with idempotency, bounded attempts, and lease fields.';
comment on table public.analysis_results is
    'Versioned preliminary/final result snapshots tied to a source evidence fingerprint.';
