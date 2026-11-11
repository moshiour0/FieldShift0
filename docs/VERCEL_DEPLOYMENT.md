> **Current deployment boundary — 11 November 2026.** This checklist predates the V3.3 account/worker release. The feature-branch Preview now includes Supabase Auth, owner-scoped `My Runs`, a durable queue and a protected background worker. The older Production deployment remains on product 3.1.3 with `process_memory` and no `/api/auth/config`; Production has not been promoted. Use [Final Owner Handoff — 11 November 2026](v3/FINAL_HANDOFF_2026-11-11.md) for the authoritative environment, migration and release state.

> Historical release notes. For the 7 October repair, use [FIXES_AND_DEPLOYMENT.md](../FIXES_AND_DEPLOYMENT.md). The earlier smoke results do not establish that the new production queries have been live-validated.

# Vercel deployment and API checks

## Deploy from the project root

Import the repository with its Root Directory set to the directory containing `vercel.json`, `pyproject.toml`, `requirements.txt`, `api/`, `src/`, `config/`, and `data/`. The Vercel Python runtime detects FastAPI from the project dependencies and loads the `app` exported by `api/index.py`.

Use the safe `.env.example` as a variable-name reference only. Do not upload a credential file or commit a real `.env` file. Add each required value in **Project Settings → Environment Variables**, selecting the deployment environment where it is needed. Save the values and redeploy so the new function receives them.

## Which variables are needed?

| Capability | Variables | What the app can verify |
|---|---|---|
| NASA POWER daily weather | None; live mode is enabled by default on Vercel | `/api/status` shows whether live requests are enabled. It does not make an upstream request. |
| NASA AppEEARS point samples | `FIELD_SHIFT_APPEEARS_USER`, `FIELD_SHIFT_APPEEARS_PASSWORD` | `/api/status` reports whether both are non-empty. It cannot confirm Earthdata login or product availability. |
| NASA NEX-GDDP-CMIP6 through Earth Engine | `FIELD_SHIFT_GEE_PROJECT`, `FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON` | `/api/status` reports whether both are non-empty. It cannot confirm IAM permissions, Earth Engine registration, or a successful query. |
| SoilGrids adapter | `FIELD_SHIFT_SOILGRIDS=1` | `/api/status` reports whether it is enabled. This is an optional modeled soil input, not a field test. |
| Signed-in accounts and durable My Runs | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_ANON_KEY` | `/api/auth/config` reports safe configuration state; `/api/auth/me` validates a supplied user token. Environment presence alone is not proof of a working magic-link callback or owner isolation. |
| Background analysis worker | `FIELDSHIFT_WORKER_TOKEN`, `VERCEL_AUTOMATION_BYPASS_SECRET` plus the Supabase values above | The protected `POST /api/internal/worker/tick` uses the high-entropy worker token and lease-gated Postgres queue. `/api/status` checks worker settings, but a real queued run is required to validate processing.

For `FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON`, paste the complete service-account JSON as the value of a server-side environment variable. Never expose it to browser code and never include the key file in the repository. For NASA AppEEARS, use your current Earthdata credentials. Store neither credential in source control.

## Check the deployment

Open these paths on the deployed domain:

1. `/health` — the FastAPI app loaded.
2. `/api/status` — the named environment variables reached this deployment. `credentials_validated: false` means the route only checked for non-empty values.
3. `/` — the PWA shell loaded.
4. `/api/demo` — the saved demo response loaded. This is a fixture and does not test NASA connectivity.
5. Submit a real field analysis in the UI — inspect the evidence panel for data source, retrieval dates, coverage, quality notes, missing sources, stale cache, or synthetic fallback.

The UI and API share one origin, so the app does not require permissive cross-origin access.

## Diagnose common failures

| Symptom | Check |
|---|---|
| `/health` returns 404 | Confirm the deployed project Root Directory is the repository root and the latest deployment finished. |
| Build fails before routes load | Read the deployment build log for Python dependency resolution or packaging errors. Confirm both `pyproject.toml` and `requirements.txt` are in the selected root. |
| `/health` works but AppEEARS says `not_configured` | Check the two exact variable names, that they are set for the active Production/Preview environment, and that you redeployed afterward. |
| `/api/status` says credentials are configured but AppEEARS/GEE fails | The status route checks only that values exist. Read function logs and the analysis evidence error/setup hint; validate Earthdata access, GEE project registration, IAM permissions, and requested product availability. |
| POWER is enabled but evidence shows unavailable | This is an upstream/network/data-window failure, not proof the Vercel secret is wrong. Review the evidence error and fallback. POWER is a daily source, not an instantaneous sensor feed. |
| A live run cannot be opened by its public run ID | This is intentional: public `/api/analysis/{run_id}` reads are limited to the static demo. Signed-in owners must use `/api/account/runs` and `/api/account/runs/{run_id}`. Do not make live run IDs public or restore process-global caching. |
| Analysis times out | Live data calls and Monte Carlo scoring run synchronously. Check function duration and provider latency in Vercel logs. Reduce analysis samples for a demo only after confirming the uncertainty display remains honest. |

`/health` and `/api/demo` are smoke checks for app boot and static demo packaging. Neither proves that NASA APIs or optional credentials are working.

## Release gate — 2026-10-06 hardening

Before the GitHub/Vercel release, the connector layer was smoke-tested externally for all six production NASA paths: POWER, SMAP, MODIS MOD16, HLS, GPM IMERG V07, and NEX-GDDP-CMIP6. The project test suite passes locally, but Vercel still needs a real post-deploy field run because its environment, IAM permissions, cache behavior, and function duration are deployment-specific.


## V3.3 account and worker path

The V3.3 signed-in dashboard does not depend on process-local state for saved runs. The browser submits a request to `POST /api/analysis/queue`; Supabase stores the immutable request and idempotency key, and the scheduled worker processes one leased job at a time. Owners list and restore analyses through `GET /api/account/runs` and `GET /api/account/runs/{run_id}`. Manual owner recheck uses `POST /api/account/runs/{run_id}/recheck`.

The feature-branch Preview variables are scoped to `feat/krishinexus-real-data-school-lab`. At the current handoff, they are not provisioned for Production. Do not copy the Preview Supabase URL/token into Production without an explicit environment/database plan; use a separately provisioned Production Supabase project and its own migrations, Auth redirect allowlist, worker token and five-minute schedule before promotion. The public Supabase email sender is restricted; configure custom SMTP before allowing public sign-ups. See the Final Owner Handoff for the current acceptance and release gate.
