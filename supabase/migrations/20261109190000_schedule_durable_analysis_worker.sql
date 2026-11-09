-- Schedule one durable analysis reconciliation tick every five minutes.
-- The Vercel Preview endpoint is authenticated with two secrets stored in Vault:
-- the worker token and Vercel's protection-bypass secret. Neither is in source.
-- The worker processes at most one job per invocation; DB lease + SKIP LOCKED
-- prevent concurrent work, while retry timestamps are persisted in Postgres.

select cron.schedule(
    'fieldshift-analysis-reconciliation',
    '*/5 * * * *',
    $job$
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
    $job$
);

comment on extension pg_cron is
    'Schedules FieldShift durable analysis reconciliation every five minutes.';
