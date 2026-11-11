-- Identity sequences are separate database objects. The invoker RPC needs
-- sequence USAGE when it inserts append-only account events.
grant usage on sequence public.analysis_run_events_id_seq to authenticated;
