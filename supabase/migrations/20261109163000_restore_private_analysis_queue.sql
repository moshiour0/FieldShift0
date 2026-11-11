-- Reconcile the new queue migration with the existing token-gated worker.
-- The deployed worker functions and RLS policies intentionally use
-- private.analysis_run_jobs; keep that table in the unexposed schema.

drop function if exists public.claim_fieldshift_analysis_job(uuid);
drop function if exists public.finish_fieldshift_analysis_job(uuid, uuid, integer, text, text);
drop function if exists public.get_fieldshift_worker_config();
drop function if exists public.save_fieldshift_worker_result(uuid, uuid, jsonb);

drop policy if exists "Users can enqueue their own analysis jobs" on public.analysis_run_jobs;
revoke all on table public.analysis_run_jobs from authenticated, anon;

drop policy if exists "Backend service role manages worker locks" on private.analysis_worker_locks;
drop table if exists private.analysis_worker_locks;

alter table public.analysis_run_jobs set schema private;
revoke all on private.analysis_run_jobs from authenticated;
comment on table private.analysis_run_jobs is
    'Durable run reconciliation queue. The worker accesses it only through token-gated RLS and a bounded lease.';

-- pg_net was originally installed with its extension marker in public. It has
-- no scheduled jobs or application dependencies yet, so reinstall it into
-- the dedicated extensions schema to satisfy Supabase Security Advisor.
drop extension if exists pg_net;
create extension pg_net with schema extensions;
