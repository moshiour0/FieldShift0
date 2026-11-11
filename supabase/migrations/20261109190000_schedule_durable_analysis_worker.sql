-- Retire the duplicate reconciliation schedule. The canonical scheduler is
-- fieldshift-analysis-worker from 20261109173000 and targets /api/internal/worker/tick.
-- A final migration below pauses it until the matching Preview build is verified.

do $cleanup$
declare
    v_job_id bigint;
begin
    select jobid into v_job_id
    from cron.job
    where jobname = 'fieldshift-analysis-reconciliation';

    if v_job_id is not null then
        perform cron.unschedule(v_job_id);
    end if;
end;
$cleanup$;

comment on extension pg_cron is
    'FieldShift uses one token-gated scheduled worker; duplicate schedule retired.';
