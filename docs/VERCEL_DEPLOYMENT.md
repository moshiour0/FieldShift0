> **Production release — 11 November 2026.** V3.3 is merged to `main` and live at [https://field-shift0.vercel.app](https://field-shift0.vercel.app). Production uses the existing Supabase Free project, owner-scoped My Runs and the five-minute Vault-backed worker. Preview deployments remain protected; Production is public. The remaining Supabase dashboard action is Site URL/Redirect URL configuration for the Production domain. See [Final Owner Handoff — 11 November 2026](v3/FINAL_HANDOFF_2026-11-11.md) for verification, $0 guardrails and outstanding data actions.

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


## Fix the Supabase email redirect before testing Sign in

The browser code sends the current Vercel origin as the Supabase `redirect_to`. Do not hardcode localhost in Vercel. The Supabase Auth URL Configuration controls whether that redirect is allowed and where confirmation emails fall back when it is not.

For the current feature Preview only, set Supabase Dashboard → Authentication → URL Configuration:

- Site URL: `https://field-shif-git-c9816e-moshiour-rahman-sarkers-projects-2cebe363.vercel.app`
- Redirect URL: `https://field-shif-git-c9816e-moshiour-rahman-sarkers-projects-2cebe363.vercel.app/**`
- Optional exact deployment URL: `https://field-shift0-dprqqtf6d.vercel.app/**`

Save the settings, open the stable Preview alias above, then request one fresh email link. The existing verified Supabase user should sign in; do not create another account. Successful callback now displays a session-verified toast only after the backend's `/api/auth/me` validation. Before Production release, change Site URL to the verified Production domain.

The Supabase project organization is verified on Free. Default Auth SMTP is included, but is capped at 2 messages/hour and only sends to organization-team addresses. Do not add custom SMTP or upgrade while enforcing a strict $0 budget. Google Earth Engine may only be used for eligible registered noncommercial/research use without a paid billable setup; do not dispatch SMAP/GPM/NEX Earth Engine workflows until its noncommercial registration and Google Cloud billing state are confirmed.


## Strict $0 Earth Engine guard

Earth Engine is disabled in the V3.3 code by default. Setting `FIELD_SHIFT_GEE_PROJECT` and `FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON` is no longer sufficient. The app and SMAP archive scripts also require `FIELD_SHIFT_GEE_NONCOMMERCIAL_CONFIRMED=true` after the owner has verified eligibility for Google's noncommercial/research use and confirmed there are no paid Cloud services/billing that could create charges. The SMAP Actions workflow checks the corresponding Repository Actions Variable and stops before requests if it is absent.

For strict no-cost operation, leave that flag absent. Do not register the project as commercial, add a payment method or enable billable Cloud services. If later verified as eligible noncommercial, add the opt-in separately to Vercel Preview and GitHub Actions Variables; never copy it into Production automatically. The two GEE credential variables are currently Preview-only and removed from Vercel Production.
