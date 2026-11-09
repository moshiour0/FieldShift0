# KrishiNexus — Persistent Analysis, Delayed Data Recovery & User Accounts Roadmap

> **Status:** Active implementation handoff  
> **Last updated:** 2026-11-09 (Asia/Dhaka)  
> **Repository:** moshiour0/FieldShift0  
> **Working branch:** feat/krishinexus-real-data-school-lab  
> **Pull request:** #1 — Draft / Open / Unmerged (do not merge without explicit approval)  
> **Production rule:** Do not promote this feature branch to Production without explicit approval.

## 0. Read this first in a future chat

This file is the continuity document for the implementation. A new assistant/session should read this file first, then inspect the current branch head, PR #1, latest CI run, and current Vercel preview before editing anything. Do not ask the user to repeat the requirements below.

### Current verified repository state

- Pre-implementation baseline branch head: a5e27f48073c52891b994849aa03a13f33d2c025.
- First implementation commit: d2d3d0f8fef6c4ecb1ef1e5041c5e3fd4b4ca19a.
- Latest implementation branch head at last verified CI: 4b067fb0cef01eb034f9c2a91482c0d5cece7011.
- PR #1: https://github.com/moshiour0/FieldShift0/pull/1
- PR state at last check: open=true, draft=true, merged=false.
- Latest completed strict Drive verification run: #2, run ID 42576819439.
- Run URL: https://github.com/moshiour0/FieldShift0/actions/runs/42576819439
- Workflow: Backfill nine-region NASA POWER daily history.
- Branch and SHA: feat/krishinexus-real-data-school-lab @ a5e27f48073c52891b994849aa03a13f33d2c025.
- Overall: success; preflight + all nine region jobs succeeded.
- Each region reported year 2025, 365 daily records, retrieval_mode=google_drive, drive_readback_verified=true, and quality=NASA POWER (live).
- The Drive verification now does a direct remote read-back and byte-for-byte comparison. Do not regress to local-cache fallback verification.
- Earlier CI on this same SHA passed Python 3.11 and 3.12: 121 tests passed on each, Ruff passed, mypy passed, compileall passed. There was one non-blocking existing warning.
- Vercel Preview for the pre-implementation branch was READY at https://field-shift0-qld6tcfc1.vercel.app. Preview for the latest verified implementation commit 4b067fb0cef01eb034f9c2a91482c0d5cece7011 was READY at https://field-shift0-73l6w90yr.vercel.app. The production alias is https://field-shift0.vercel.app. Do not assume Preview is Production.

### User's requested outcome

A person must be able to start an analysis today, leave the website, return later (including after one or two days), sign in, open the same saved run, see which NASA datasets have arrived, and receive a refreshed/final analysis only when the required data and quality checks are satisfied. The user must not have to re-enter their field, date range, soil inputs, or priorities.

The system must tolerate provider latency without:
- marking incomplete datasets as complete;
- repeatedly downloading datasets that are already verified;
- starting duplicate AppEEARS tasks;
- losing run state when a browser tab closes or a Vercel instance changes;
- treating missing/not-yet-released data as zero;
- substituting a nearby region's sample for a field-specific point;
- showing a preliminary or synthetic-fallback simulation as a fully validated final prediction.

## 1. Existing architecture and verified gaps

### 1.1 Current analysis lifecycle

Relevant files:
- src/fieldshift/api/app.py
- src/fieldshift/api/product.py
- src/fieldshift/api/static/index.html
- src/fieldshift/v3/pipeline.py
- src/fieldshift/v3/appeears.py
- src/fieldshift/v3/gee.py
- src/fieldshift/v3/nasa.py
- src/fieldshift/v3/history.py
- src/fieldshift/v3/history_extended.py
- src/fieldshift/v3/refresh_jobs.py
- src/fieldshift/v3/refresh_worker.py

Verified findings from code inspection:

1. product.py stores runs in an in-process dictionary named _RUNS. The API status endpoint explicitly reports analysis_state.storage=process_memory and durable_across_instances=false. A Vercel function instance restart or a request routed to another instance can therefore lose the saved run.
2. create_analysis() runs _run_engine() synchronously, then stores the result in _RUNS. It is not a durable queued-run workflow.
3. The browser's pending-source refresh re-posts the whole /api/analysis/run payload. It is browser-timer driven, stops after at most 20 checks, and is lost when the page is closed. It can recompute the whole analysis instead of refreshing only the missing source.
4. The browser checks only pending and retrying evidence statuses. A partial source (for example, a dataset with incomplete date coverage) is not automatically rechecked. However, partial does not always mean delayed: it can mean the provider product does not cover the requested dates. It must not be retried forever without provider evidence.
5. product.py currently labels a run pending only when some evidence item is pending or retrying. Other incomplete states (partial, stale, unavailable, not_configured, error, fallback) can otherwise yield run.status=complete. This is scientifically misleading.
6. refresh_jobs.py has a durable job-table concept, but on Vercel it requires FIELD_SHIFT_JOBS_DSN and a durable database. It currently supports NASA POWER YTD refresh only, not a user's complete multi-source analysis lifecycle. The route currently hashes request.client.host as an owner/rate-limit identity; this is not a user-account identity and must be replaced by authenticated user UUID ownership.
7. refresh_worker.py is a supervised Python worker, but deployment and invocation have not been wired into the public FieldShift product.
8. AppEEARS already reuses pending/recent provider tasks using stable task names, pending cache files, and the account task list. That is useful, but Vercel ephemeral files are not a durable source of truth. Provider task IDs and source state must be persisted in the database.
9. NASA GPM IMERG can return partial date coverage. Its current cache path may store any non-empty subset and subsequently return that subset as a cache hit until TTL expiry. The missing dates must be tracked separately and re-queried/merged; a partial cache must not be treated as a full cache hit.
10. NASA POWER supports live retrieval, expiring cache, stale-cache fallback, validation, and bounded gap filling. Its values are gridded point estimates, not field sensor measurements. Existing verified historical archive entries are exact representative-coordinate samples.
11. history.py implements archived_weather() for exact representative coordinates, but pipeline.py's run_v3() weather path currently calls power_daily() directly. The prediction engine is not yet fully connected to the verified Google Drive completed-year archive.
12. The current 2025 backfill is verified. The intended 2016–2025 archive is not yet verified complete.

### 1.2 Current data-source behaviour

- NASA POWER Daily weather: primary daily meteorology input. Missing values may be filled only under the existing explicit bounded policy; provenance must show the number of imputed values. Synthetic fallback must never be relabelled as NASA data.
- NASA AppEEARS sources: SMAP, HLS vegetation indices, and MODIS MOD16 ET. Task submission, task status, bundle download, date coverage, and product-specific QA are separate stages. Persist task IDs and reuse them; never blindly POST duplicate tasks.
- NASA GPM IMERG V07: sampled through Google Earth Engine. A day is only usable when all 48 half-hour intervals pass the adapter's requirement. Missing days must stay missing; retry only the missing day/date windows where appropriate.
- NASA NEX-GDDP-CMIP6: projection inputs and monthly normals are a separate modeled evidence class. If pending, retain completed month/model work and resume missing requests; clearly distinguish actual NASA projection data from diagnostic stress-test fallback.
- SoilGrids / user soil inputs: source and confidence differ. Farmer-entered estimates, lab reports, and modeled soil products must not be conflated.

A provider's one-to-two-day publication delay is not a universal guarantee for every product. Retry schedules must respect each provider's task state, Retry-After, date availability window, quota, and product cadence.

## 2. Target user experience

### 2.1 Account and saved run

- Sign-in choices: Supabase Auth email OTP/magic link and optionally Google OAuth. Email/password may also be enabled if desired.
- Do not build a custom password store or store passwords in public tables. Supabase Auth owns credentials and sessions.
- A profile may have a display name/username, but the security identity is the immutable Supabase Auth user UUID.
- A signed-in user can see only their own runs, source states, results, and reports.
- Add a My Runs page showing run date, field label, observation window, current status, core-data readiness, source coverage, and latest result revision.
- Opening a run loads the immutable original request snapshot and its latest source/result records. It must not silently use current form defaults.

### 2.2 Run experience and status meanings

The product must distinguish the processing lifecycle from the data quality of the output.

| Status | Meaning | User experience |
|---|---|---|
| queued | Request accepted and waiting for a worker | Show queue state; no prediction yet |
| running | Core orchestration is executing | Show progress and source checks |
| preliminary_ready | A provisional output exists, but at least one required input or asynchronous source is pending/unverified | Clearly label PRELIMINARY; never call it final |
| waiting_for_data | A required source is not ready and no eligible output should be shown | Keep the run saved and show what is missing |
| final_ready | Required inputs and all configured/requested sources passed their required checks | Show final result and provenance |
| final_with_gaps | Required core input passed, but optional or requested data remain partial/unavailable/not configured | Show result with visible limitations and source gaps |
| failed | Retry budget exhausted or non-recoverable processing error | Keep original request and error history; allow a controlled manual retry where safe |
| cancelled | User explicitly cancelled the run | Preserve the audit trail |

Dataset status is separate from run status:

- queued, pending, retrying
- available, stale, partial
- unavailable, not_configured, failed
- skipped (only when the source policy says it is not required for this run)

A partial result is not automatically final. A partial result may be terminal when the provider has no data for the requested part of the window; it may be retryable when the provider confirms an ingest delay. Store a retry reason and next_retry_at so these cases remain distinct.

### 2.3 Data policy

Define a versioned source dependency policy for each engine version and analysis type.

Initial policy recommendation:
- NASA POWER daily weather is the required core weather series for a live observed-weather result.
- If POWER is not ready and the engine falls back to synthetic weather, outputs can be shown only as a provisional/diagnostic preview, never as final observed-data prediction.
- SMAP, HLS, MODIS ET, and GPM are supplemental/optional unless a specific model feature explicitly requires them.
- NEX-GDDP-CMIP6 is a modeled climate scenario source, not a substitute for observed baseline weather.
- A source being not_configured must be disclosed as a gap, not counted as zero or silently treated as available.

Keep source policy versioned so later changes do not retroactively alter the interpretation of an old run.

## 3. Target architecture

### 3.1 Components and ownership

1. **Supabase Auth** — account identity and sessions.
2. **Supabase Postgres** — durable analysis runs, user ownership, source state, retry state, worker jobs, event history, result revisions, and cache metadata.
3. **Python FieldShift API** — validates the Supabase access token, enforces ownership, stores request snapshots, returns run state, and coordinates the existing scientific engine.
4. **Durable worker** — claims bounded jobs, checks/submits only required provider tasks, downloads and quality-checks source data, publishes verified data to the archive, and updates source status. It must not depend on a user's browser being open.
5. **Google Drive archive** — private shared verified evidence archive. The browser never receives Drive OAuth secrets or direct folder access.
6. **Supabase Storage** — optional private user-owned reports/large artifacts. It is not a replacement for the shared scientific dataset archive.
7. **Vercel frontend/API deployment** — serves the public experience and short API requests. Never hold an HTTP request open for a one-to-two-day provider task.

The production worker execution mechanism is still a deployment decision. Evaluate Vercel Cron + a bounded internal worker route against a separate long-running Python worker. Verify the actual Vercel plan/runtime duration and cron-frequency limits before choosing. Do not assume Render or another host has been selected.

### 3.2 Data flow

1. User signs in. Browser obtains a Supabase Auth access token.
2. User submits a request with a client-generated idempotency key.
3. API validates the token with Supabase Auth and obtains user UUID; never trust a user_id supplied by the browser.
4. API stores the exact input snapshot and creates source rows plus idempotent worker jobs; returns HTTP 202 and run ID.
5. Worker claims a job using a DB transaction/lease (FOR UPDATE SKIP LOCKED or an appropriately configured durable queue).
6. For each requested dataset, worker first checks a verified cache with an exact compatibility key. Reuse only when provider, product/layer, exact spatial support, date range, native cadence, processing/QA version, and data version match.
7. If no compatible verified cache exists, worker submits or resumes the provider task. Persist provider task IDs before returning.
8. Download only missing/failed products. Do not re-download verified data. Validate schema, date range, fill values, QA flags, units, physical bounds, and completeness.
9. Publish to Google Drive using a deterministic object key and verify remote bytes/checksum after upload. Then upsert cache metadata.
10. Update the source row with coverage, quality, provenance, next retry, and terminal/active status.
11. When source states change, recompute run readiness. Save a preliminary revision when eligible; save a final/final-with-gaps revision only when policy permits.
12. Browser watches Supabase Realtime or a low-frequency status endpoint. Closing the browser does not stop work.
13. On return, user signs in and opens My Runs. The API loads the run, per-source records, and latest result revision.

### 3.3 Idempotency and cache keys

A cache key must include enough information to prevent scientific mismatches:
- provider and product collection;
- selected layer/parameter and product version;
- exact point or officially supported grid-cell identity (do not use an arbitrary nearest region);
- requested start/end dates and native temporal support;
- scale/resolution/aggregation method;
- QA/processing policy version;
- code/schema version where serialization changes affect interpretation.

Store SHA-256, archive object key, quality/provenance metadata, coverage start/end, and verification timestamp. Cache states should include candidate, verified, and quarantined. Only verified entries may be reused as trusted cached evidence.

Never use a nearby representative coordinate as the user's field value. The existing nine-point 2016–2025 archive is directly reusable only for those exact representative coordinates, unless a scientifically validated grid-cell matching rule is introduced.

### 3.4 Retry design

- Honor provider Retry-After exactly when supplied.
- Otherwise use bounded exponential backoff with jitter and a provider-specific cap.
- Persist attempt_count, max_attempts, next_retry_at, last_error_code, and a safe user-visible explanation.
- Reuse existing provider task IDs. Never duplicate AppEEARS POST submissions for the same request.
- Retry only pending/transient/missing subranges. Do not re-download successful green sources.
- Separate source processing jobs from final analysis reconciliation jobs.
- Move exhausted or non-recoverable work to failed/dead-letter state; keep the run and its history.
- Avoid high-frequency browser polling. Prefer Realtime updates with a conservative status refresh fallback.
- Add user-facing manual Check now only as a controlled rate-limited action, not as a way to bypass provider cooldowns.

## 4. Database design target

A first migration is drafted in:
supabase/migrations/20261109090000_persistent_analysis_runs.sql

It defines:

- user_profiles — display profile only; authentication/passwords remain in auth.users.
- analysis_runs — user-owned immutable request snapshot, idempotency key, engine version, observation window, lifecycle state.
- analysis_run_sources — source-specific provider task, coverage, status, QA, provenance, retry and cache references.
- dataset_cache — shared exact-match verified archive metadata; never exposed to browser roles.
- analysis_run_jobs — durable worker queue/lease records, idempotent job keys, attempts and schedule.
- analysis_results — versioned preliminary/final/final-with-gaps outputs.
- analysis_run_events — append-only lifecycle/audit events.

Security requirements:
- RLS enabled for every public table.
- Users can read only their own runs and associated source/result/event rows.
- Users can edit only their own harmless display profile fields.
- Browser users cannot directly write run lifecycle, queue, cache, or result state.
- Cache and job tables are service-role/backend only.
- Never expose SUPABASE_SERVICE_ROLE_KEY, database passwords, Google Drive OAuth credentials, provider credentials, or internal job tokens to browser code.
- API must also enforce owner checks on every run ID route because service-role access bypasses RLS.
- Never use user-editable user_metadata as an authorization source.

**Important deployment blocker:** At the last inspection, the available Supabase connection listed no FieldShift0/KrishiNexus project. It listed SARGuardian_Dynamic and SARGuardian-Monorepo plus unrelated projects. The Vercel field-shift0 project's environment variable list contained the four Google Drive secrets and NASA/GEE settings but no SUPABASE_URL, SUPABASE_ANON_KEY/SUPABASE_PUBLISHABLE_KEY, SUPABASE_SERVICE_ROLE_KEY, or FieldShift database DSN. Do not apply this migration to any SARGuardian project. First identify/create the correct FieldShift Supabase project and add the intended variables to Vercel Preview before Production.


### First implementation slice (2026-11-09)

Commit d2d3d0f8fef6c4ecb1ef1e5041c5e3fd4b4ca19a added:
- docs/v3/PERSISTENT_ANALYSIS_ROADMAP.md — this continuity roadmap.
- supabase/migrations/20261109090000_persistent_analysis_runs.sql — proposed tables and owner-scoped RLS policies; not applied to a hosted database.
- src/fieldshift/v3/run_lifecycle.py — core-weather readiness and final/preliminary status classifier.
- tests_v3/test_run_lifecycle.py — six lifecycle policy tests.
- product.py now returns status_message, is_final, prediction_eligible, core_data_ready, pending_sources, gap_sources, and missing_required_sources.
- index.html now renders a run-readiness banner in the evidence section.

CI follow-up and final verification:
- Run #186 / 42579715675 initially failed because tests/test_learning_lab_contract.py still expected only the legacy values complete/pending. It reported 126 passed, 1 failed.
- The test was updated to the new contract: when live NASA is explicitly disabled and required POWER weather is not ready, the run must be preliminary_ready, is_final=false, and prediction_eligible=false.
- The next run exposed a mypy variable-reuse issue in run_lifecycle.py. It was fixed in commit 4b067fb0cef01eb034f9c2a91482c0d5cece7011 by separating is_required from required_items.
- Final verified CI on commit 4b067fb0cef01eb034f9c2a91482c0d5cece7011: push run 42580071172 and PR run 42580077962 both succeeded.
- Python 3.11: 127 passed, 1 warning; compileall passed; Ruff passed; mypy reported no issues in 32 source files.
- Python 3.12: 127 passed, 1 warning; compileall passed; Ruff passed; mypy reported no issues in 32 source files.
- The remaining warning is the existing Starlette TestClient/httpx deprecation warning. Do not describe the suite as warning-free.

Infrastructure verification:
- Vercel Preview for commit d2d3d0f8fef6c4ecb1ef1e5041c5e3fd4b4ca19a reached READY at https://field-shift0-qugdka886.vercel.app.
- The available Supabase account connection has no FieldShift project. Vercel project field-shift0 currently has Google Drive/NASA/GEE variables but no SUPABASE_* variables. Do not apply the SQL migration or wire auth until the correct FieldShift Supabase project is selected.

## 5. Implementation phases and acceptance criteria

### Phase 0 — Safe baseline and documentation
- Preserve PR #1 as Draft and unmerged.
- Keep Production unchanged.
- Record successful 2025 Drive verification and current branch SHA.
- Commit this roadmap and update it after every meaningful phase.
- Confirm correct Supabase project before any hosted schema mutation.

Acceptance: roadmap is committed on the feature branch; no production or unrelated Supabase project is modified.

### Phase 1 — Honest readiness semantics (started)
- Add canonical source keys and a versioned required/optional source policy.
- Compute run status from per-source evidence rather than only pending/retrying.
- Mark incomplete required core weather as preliminary.
- Mark settled but incomplete supplemental evidence as final_with_gaps.
- Mark final_ready only when the required core input and configured/requested sources meet policy.
- Expose status_message, is_final, core_data_ready, pending_sources, and gap_sources.
- Add tests for each status transition.
- Frontend must render status prominently, not merely as a toast.

Acceptance: unavailable/partial/not_configured/fallback cannot accidentally produce a green final-complete label.

### Phase 2 — Supabase project and schema bootstrap
- Identify the correct FieldShift Supabase project; confirm plan/region and existing tables/migrations.
- Add Supabase URL and publishable key to Preview; keep secret key server-only.
- Apply the migration only to the verified FieldShift project.
- Run list_tables, test queries, and Supabase security/performance advisors.
- Add authentication methods and callback URLs.
- Implement JWT validation and ownership checks on backend routes.

Acceptance: a signed-in test user can create/read their profile; a second user cannot access the first user's run or child records; anon cannot read private records.

### Phase 3 — Durable run submission and My Runs
- Replace synchronous user-run creation with an idempotent queued request API.
- Persist exact request payload and engine version before execution.
- Add GET list/detail/status endpoints with authenticated ownership.
- Add My Runs page, run detail route, and resume-on-return.
- Keep demo snapshot separate from account-owned runs.
- Ensure idempotent double-click/retry does not create duplicate runs.

Acceptance: run survives browser close, Vercel instance changes, and a new sign-in session; user can reopen it by ID from My Runs.

### Phase 4 — Provider source jobs and durable worker
- Add source-specific job handlers for POWER, AppEEARS sources, GPM, NEX-GDDP-CMIP6, and other configured sources.
- Persist AppEEARS task ID and source request signature before polling.
- Reuse provider tasks; add provider-aware retry and terminal failure handling.
- Claim jobs with leases and concurrency limits; protect against two workers downloading the same source simultaneously.
- Process only pending/missing datasets; collect failures without blocking successful siblings.
- Implement final reconciliation as a separate job.
- Decide worker deployment only after verifying Vercel plan/runtime and service operational limits.

Acceptance: one failed source does not restart successful sources; browser can close; worker can resume after termination; no duplicate provider tasks for the same source request.

### Phase 5 — Verified shared archive and scientific integration
- Connect run_v3 weather retrieval to verified archive-first logic where location/time exactly match.
- Add archive support for approved satellite products with deterministic paths and byte-for-byte remote readback.
- Fix GPM partial cache behaviour so partial cache entries are merged with newly available missing dates rather than returned as complete.
- Persist exact QA policy version, native temporal cadence, source coverage and limitations.
- Use only verified archive entries; quarantine checksum or QA failures.
- Keep region representative points separate from arbitrary farm coordinates.

Acceptance: repeat requests reuse checksum-verified cached products; missing data remains missing; only compatible spatial/time/product data are reused.

### Phase 6 — User notifications and operational polish
- Add opt-in email notification when final_ready/final_with_gaps becomes available.
- Optional in-app notifications and Realtime status.
- Add retry budget, manual refresh cooldown, cancellation, and retention policy.
- Add user export/delete controls and account deletion cascade policy.
- Add admin-only queue health, stuck-job recovery, retry and audit views.

Acceptance: user receives a clear completion signal; no secret or internal stack details leak; rate limits protect providers.

### Phase 7 — Production validation and release gate
- Run full Python 3.11/3.12 test suite, Ruff, mypy, compileall.
- Run migration tests and RLS owner-isolation tests against a disposable/dev FieldShift Supabase project.
- Run provider mock tests for delayed, partial, duplicate, timeout, Retry-After, missing-data and checksum mismatch cases.
- Run end-to-end browser tests: sign up, submit, close tab, wait, sign in again, open saved run, source completion, final revision.
- Check Vercel Preview, API status, logs, and production readiness.
- User explicitly approves PR conversion/merge and Production promotion only after the evidence is green.

Acceptance: production is not promoted solely because CI is green; real database/RLS/provider worker and resume-after-return behaviour must pass.

## 6. Immediate next actions

1. Review the implementation commit generated with this roadmap and inspect its CI.
2. Inspect the latest PR branch SHA before further writes; do not overwrite concurrent changes.
3. Backfill 2016–2025 after the 2025 verification gate is satisfied; keep 2025 files reusable.
4. Confirm the intended FieldShift Supabase project. Do not use any SARGuardian project.
5. Continue Phase 1 frontend status presentation and write migration/RLS tests before applying the database migration.
6. Then implement Phase 2 and Phase 3 before background source orchestration.

## 7. Environment variables expected later

Names only; do not ask the user to paste secret values in chat.

Browser-safe (public):
- SUPABASE_URL
- SUPABASE_PUBLISHABLE_KEY (or existing legacy anon key, if the project still uses it)

Server-only:
- SUPABASE_SERVICE_ROLE_KEY (or the current Supabase secret key equivalent)
- FIELD_SHIFT_JOBS_DSN only if using a direct Postgres Python worker connection; use a pooled connection mode suitable for the worker.
- Existing GOOGLE_DRIVE_CLIENT_ID
- Existing GOOGLE_DRIVE_CLIENT_SECRET
- Existing GOOGLE_DRIVE_REFRESH_TOKEN
- Existing GOOGLE_DRIVE_FOLDER_ID
- Existing NASA Earthdata / Google Earth Engine credentials as currently configured.

Never put server-only values in NEXT_PUBLIC_ variables or browser code. Never read or display decrypted secrets in logs or chat.

## 8. Future-chat handoff instructions

When continuing this project:
1. Read this file fully.
2. Check the current PR #1 metadata and latest feature branch head SHA.
3. Fetch recent GitHub Actions runs; inspect failed logs rather than trusting the top-level badge.
4. Inspect Vercel Preview deployment for the exact branch SHA.
5. Confirm the current Supabase project identity and schema before any migration.
6. Continue from the first unchecked implementation phase and update this document in the same PR branch.
7. Preserve the user's constraints: Bengali explanations; exact technical identifiers; no guessing; no Production promotion; no PR merge without explicit approval; do not request secrets in chat.

## 9. Reference documentation

- Supabase Auth: https://supabase.com/docs/guides/auth
- Supabase Row Level Security: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase Queues: https://supabase.com/docs/guides/queues
- Supabase Queues Quickstart: https://supabase.com/docs/guides/queues/quickstart
- Supabase database migrations: https://supabase.com/docs/guides/deployment/database-migrations
- Vercel Functions: https://vercel.com/docs/functions
- Vercel Cron Jobs: https://vercel.com/docs/cron-jobs
- NASA POWER Daily API: https://power.larc.nasa.gov/docs/services/api/temporal/daily/
- NASA AppEEARS API: https://appeears.earthdatacloud.nasa.gov/api/
- NASA GPM IMERG V07 dataset (Earth Engine): https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07
