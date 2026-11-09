-- Enable the single scheduled worker only after the current Preview was
-- verified with a protected HTTP 200 idle response. All secrets are read from
-- Supabase Vault at dispatch time; no credential values are stored in source.
-- This replaces both historical scheduler names with one canonical job.

do $schedule$
declare
    v_job record;
begin
    for v_job in
        select jobid
        from cron.job
        where jobname in ('fieldshift-analysis-worker','fieldshift-analysis-reconciliation')
    loop
        perform cron.unschedule(v_job.jobid);
    end loop;

    perform cron.schedule(
        'fieldshift-analysis-worker',
        '*/5 * * * *',
        $worker$
        select net.http_post(
            url := rtrim(
                (select decrypted_secret
                 from vault.decrypted_secrets
                 where name = 'fieldshift_worker_url'),
                '/'
            ) || '/api/internal/worker/tick',
            headers := jsonb_build_object(
                'Content-Type', 'application/json',
                'x-fieldshift-worker',
                    (select decrypted_secret
                     from vault.decrypted_secrets
                     where name = 'fieldshift_worker_secret'),
                'x-vercel-protection-bypass',
                    (select decrypted_secret
                     from vault.decrypted_secrets
                     where name = 'fieldshift_vercel_bypass_secret')
            ),
            body := jsonb_build_object(
                'source', 'supabase_pg_cron',
                'requested_at', now()
            ),
            timeout_milliseconds := 240000
        );
        $worker$
    );
end;
$schedule$;

comment on extension pg_cron is
    'Runs one verified FieldShift Preview worker every five minutes; all dispatch secrets are read from Supabase Vault.';
