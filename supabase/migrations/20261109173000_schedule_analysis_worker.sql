-- Invoke the protected Vercel Preview worker every five minutes.
-- All credentials are read at execution time from encrypted Supabase Vault.
-- No secret values are stored in this migration.

do $schedule$
declare
    v_job_id bigint;
begin
    select jobid into v_job_id
    from cron.job
    where jobname = 'fieldshift-analysis-worker';

    if v_job_id is not null then
        perform cron.unschedule(v_job_id);
    end if;

    perform cron.schedule(
        'fieldshift-analysis-worker',
        '*/5 * * * *',
        $worker$
        select net.http_post(
            url := (
                select decrypted_secret
                from vault.decrypted_secrets
                where name = 'fieldshift_worker_url'
            ) || '/api/internal/worker/tick',
            headers := jsonb_build_object(
                'Content-Type', 'application/json',
                'x-fieldshift-worker', (
                    select decrypted_secret
                    from vault.decrypted_secrets
                    where name = 'fieldshift_worker_secret'
                ),
                'x-vercel-protection-bypass', (
                    select decrypted_secret
                    from vault.decrypted_secrets
                    where name = 'fieldshift_vercel_bypass_secret'
                )
            ),
            body := jsonb_build_object('trigger', 'supabase_pg_cron'),
            timeout_milliseconds := 280000
        );
        $worker$
    );
end;
$schedule$;

comment on extension pg_cron is
    'Runs FieldShift delayed-data queue through a protected Vercel Preview worker every five minutes.';
notify pgrst, 'reload schema';
