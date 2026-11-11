-- The token-gated worker upserts public.analysis_run_sources and owns only
-- these retry counters in addition to the metadata columns granted earlier.
-- Column-level grants preserve least privilege; do not grant table-wide writes.

grant insert (attempt_count, max_attempts),
      update (attempt_count, max_attempts)
on table public.analysis_run_sources
to anon;
