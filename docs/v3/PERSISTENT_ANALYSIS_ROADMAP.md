# KrishiNexus — Persistent Analysis, Delayed Data Recovery & User Accounts Roadmap

> **Status:** Active implementation handoff  
> **Last updated:** 2026-11-10 (Asia/Dhaka)  
> **Repository:** moshiour0/FieldShift0  
> **Working branch:** feat/krishinexus-real-data-school-lab  
> **Pull request:** #1 — Draft / Open / Unmerged (do not merge without explicit approval)  
> **Production rule:** Do not promote this feature branch to Production without explicit approval.

## 0. Latest operational checkpoint — 2026-11-10 15:40 UTC

- Current PR head: `f4417bf5107d001fac848d549e709b620eda66c5` (documentation-only after runtime commit `f2baa301dc30fbe6dc71d7076a41a30336b57b76)); PR #1 is still Open/Draft/Unmerged.
- Exact-head CI run #562 (`42846659223`) passed on Python 3.11 and 3.12: 178 tests per job, compileall, strict Ruff and mypy (34 source files).
- Exact-head Preview is READY at `https://field-shift0-hbmuwnxdu.vercel.app` (deployment `dpl_U5ppyfczeMtA7PKdDch7WNbuPvRo`). The runtime-code Preview at `https://field-shift0-nttj3iysm.vercel.app` is also READY and matches runtime SHA `f2baa301dc30fbe6dc71d7076a41a30336b57b76`.
- All nine reference-point 2025 POWER history endpoints returned daily, complete 365/365 coverage, no missing dates and SHA-256 provenance. All nine data-status endpoints report POWER ready and SMAP/HLS/MOD16/GPM not_archived. These are exact gridded reference samples, not farm observations or district averages.
- The POWER processing pipeline now checks a complete, checksum-validated annual archive only for an exact reference coordinate/date window; non-reference coordinates continue to their own live POWER request. CI tests enforce checksum rejection and no reference-point substitution.
- Supabase is ACTIVE_HEALTHY; one five-minute worker cron is active. Latest safe worker response was HTTP 200 with processed=false / no queued job. Durable analysis/run/source/result/event/job/cache/profile tables remain empty, so real authenticated user continuity is not yet proven.
- Preview auth configuration is present, but actual Magic Link login, My Runs persistence, delayed return, two-user isolation and real NASA provider-task resume remain untested. Drive/AppEEARS/GEE configuration metadata is not live credential validation.
- No merge, Production promotion or ownership transfer is authorized/performed. Do not promote Production without explicit user approval.

## 0. Read this first in a future chat

> **Additional scope handoff:** Read [`NASA_DATA_LATENCY_AND_SMAP_ARCHIVE_PLAN.md`](./NASA_DATA_LATENCY_AND_SMAP_ARCHIVE_PLAN.md) for the user's AppEEARS 53-request latency evidence, SMAP-first archive decision, exact-location cache, preliminary-result policy, and phased implementation/acceptance gates. This file governs the latency/archive scope; the sections below retain the durable queue/auth/worker history.

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

1. product.py still keeps `_RUNS` for the synchronous compatibility/anonymous `POST /api/analysis/run` path and legacy GET/what-if/report routes. The signed-in main dashboard instead submits to `POST /api/analysis/queue`; it persists an immutable request through the authenticated Supabase RPC and exposes the owner-scoped `/api/account/runs` list/detail/recheck routes. The durable path and the legacy process-memory path must not be conflated.
2. `create_analysis()` runs `_run_engine()` synchronously for the compatibility route. A signed-in main-dashboard request uses the queued background worker and does not hold the HTTP request open for the full analysis.
3. The signed-in dashboard polls the saved run and has a My Runs recovery path; the request, source states and result revisions stay in Supabase when the browser closes. The synchronous unauthenticated/legacy path can still use browser-timer refresh and is not a substitute for durable saved-run continuity. The educational Learning Lab currently calls the synchronous `/api/analysis/run` endpoint.
4. The synchronous product response and compatibility path still have narrower pending-source refresh semantics. The durable worker stores per-source status/retry state; partial must not be treated as automatically retryable because it can also represent genuine provider date/coverage limits.
5. The legacy synchronous `product.py` response can label a run complete based on its own reduced pending/retrying logic; its output must not be confused with the signed-in worker lifecycle statuses (`preliminary_ready`, `waiting_for_data`, `final_ready`, `final_with_gaps`).
6. refresh_jobs.py has a durable job-table concept, but on Vercel it requires FIELD_SHIFT_JOBS_DSN and a durable database. It currently supports NASA POWER YTD refresh only, not a user's complete multi-source analysis lifecycle. The route currently hashes request.client.host as an owner/rate-limit identity; this is not a user-account identity and must be replaced by authenticated user UUID ownership.
7. refresh_worker.py is a supervised Python worker, but deployment and invocation have not been wired into the public FieldShift product.
8. AppEEARS already reuses pending/recent provider tasks using stable task names, pending cache files, and the account task list. That is useful, but Vercel ephemeral files are not a durable source of truth. Provider task IDs and source state must be persisted in the database.
9. NASA GPM IMERG can return partial date coverage. Its current cache path may store any non-empty subset and subsequently return that subset as a cache hit until TTL expiry. The missing dates must be tracked separately and re-queried/merged; a partial cache must not be treated as a full cache hit.
10. NASA POWER supports live retrieval, expiring cache, stale-cache fallback, validation, and bounded gap filling. Its values are gridded point estimates, not field sensor measurements. Existing verified historical archive entries are exact representative-coordinate samples.
11. `history.py` exposes a strict archive reader for exact reference coordinates, and the current branch wires it into the POWER baseline as an archive-first lookup. Only a complete, checksummed annual object for the exact requested coordinate/date span can be reused; other locations or missing years continue through the live POWER path.
12. The 2025 archive is complete for the nine reference points (365/365 per point). The 2016–2025 archive is not complete.

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

Never use a nearby representative coordinate as the user's field value. The verified 2025 reference archive is reusable only for the exact nine coordinates and only for fully covered date windows. It must not be treated as arbitrary field coverage.

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
- [Completed in runtime commit 5c3040c] Connect `run_v3` weather retrieval to verified archive-first logic for exact reference coordinates and complete annual date coverage.
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


## 10. Continuation update — 2026-11-09

### Latest lifecycle implementation

- Latest branch head: `79421092c83cbb961b5e724da0e833eb463faa34`.
- `classify_run_readiness(..., result_available=False)` now distinguishes:
  - `waiting_for_data` when the analysis has no result and pending or required core evidence is still missing.
  - `running` when source readiness has passed but the result is still being computed.
- A preliminary result with required NASA POWER evidence not ready is explicitly labelled `DIAGNOSTIC PREVIEW · NOT FOR FIELD DECISIONS` in the UI.
- New lifecycle tests cover both no-result states.
- Push CI run `42582333784` and PR CI run `42582339898`: success.
- Python 3.11 and 3.12: 129 passed, 1 existing Starlette/httpx TestClient deprecation warning; compileall, Ruff and mypy passed (32 source files).
- Vercel Preview for exact SHA `79421092c83cbb961b5e724da0e833eb463faa34`: READY at https://field-shift0-6fu9kk0jp.vercel.app.
- PR #1 remains open, Draft, and unmerged. Production remains unchanged.

### Supabase provisioning attempt and current blocker

- The selected Supabase organization is `moshiour's Org`; the requested project name is `FieldShift0`, in `ap-south-1` (Mumbai).
- Supabase quoted project creation at $0/month on the current Free plan, but the create request was rejected because the account owner has already consumed the two-active-Free-project limit with `SARGuardian_Dynamic` and `SARGuardian-Monorepo`.
- No project was created. No existing project was paused/deleted. No organization plan was upgraded. No migration was applied and no Vercel Supabase environment variables were added.
- User approval is still required for one of two actions: pause one of those existing active projects, or authorize an organization plan upgrade after reviewing the exact billing impact. Do not select or execute either action without that decision.
- Supabase's current project-wide billing rules mean a Pro plan applies to every project in that organization; separate project compute is billed in addition to the plan. Check the current bill estimate before any upgrade.
- Supabase changelog states that, from 2026-10-30, newly created public tables require explicit grants before Data API access. This migration already includes explicit, least-privilege grants: browser roles can read only owner-scoped run records and edit their own profile; cache/jobs remain backend-only; `service_role` has backend privileges. Keep these grants in the migration.

### Next safe actions

1. Resolve the Free active-project limit with explicit user direction; do not modify SARGuardian projects or billing without it.
2. Create `FieldShift0` in `ap-south-1`, then verify project identity, health, tables and migration history.
3. Apply the reviewed migration only to that exact new project; verify RLS, explicit grants, indexes, constraints, and Supabase Security/Performance Advisors.
4. Add only Preview-scoped Supabase URL and publishable key, plus server-only secret credentials. Never expose the secret/service-role key to browser code.
5. Implement and test Auth/JWT validation, owner-scoped backend routes, durable run submission, My Runs and resume-on-return before provider workers.


## 11. Supabase bootstrap completed — 2026-11-09

### Project and account state

- Supabase project successfully created on the **Free** organization plan after the user explicitly authorized pausing `SARGuardian_Dynamic`.
- Project: `FieldShift0`
- Project ref: `bipyrlegaxmhwzwrmcmi`
- Organization: `moshiour's Org` (`qzrbewvkrtyphlxwuize`)
- Region: `ap-south-1` (Mumbai)
- Database: PostgreSQL 17.11; project status `ACTIVE_HEALTHY`.
- `SARGuardian_Dynamic` project ref `ufwjmhivvnoewjsbteey`: status `INACTIVE` (paused), as requested.
- `SARGuardian-Monorepo` project ref `qbmhpdprvxssqinnommz`: remains `ACTIVE_HEALTHY`; it was not modified.
- Organization plan remains Free. Project creation cost check returned $0/month; project creation succeeded with no paid upgrade or add-on.

### Applied migrations

The following migrations were applied successfully to `bipyrlegaxmhwzwrmcmi` and confirmed in migration history:

1. `20261109090000_persistent_analysis_runs.sql` — registered version `20261109080151` as `persistent_analysis_runs`.
2. `20261109102000_private_worker_tables_and_fk_indexes.sql` — registered version `20261109080257` as `private_worker_tables_and_fk_indexes`.
3. `20261109104500_private_backend_rls_policies.sql` — registered version `20261109080412` as `private_backend_rls_policies`.

Verified database objects:
- Public/user-owned: `user_profiles`, `analysis_runs`, `analysis_run_sources`, `analysis_results`, `analysis_run_events`.
- Private backend-only: `private.dataset_cache`, `private.analysis_run_jobs`.
- All seven tables have RLS enabled.
- Authenticated browser grants are limited to profile select/insert/update and select-only access to own run/source/result/event records, further constrained by ownership policies.
- No `anon` table grants were found for the application tables.
- `private` schema usage and private table privileges are granted only to `service_role`; explicit service-role RLS policies are present for the two private tables.
- Added foreign-key indexes for `analysis_run_sources.cache_id`, `analysis_run_jobs.source_id`, and `analysis_run_events.source_id`.

### Advisor verification

- Security Advisor: **no findings** after the private backend service-role policies were added.
- Performance Advisor: only INFO-level unused-index notices remain because the new database has no application workload yet. The prior unindexed-foreign-key findings were resolved by the added indexes.
- Health Advisor: no findings at initial bootstrap.
- Migration and schema verification completed without applying any schema to either SARGuardian project.

### Vercel Preview config

For Vercel project `field-shift0`, these variables were created for Preview only and scoped to Git branch `feat/krishinexus-real-data-school-lab`:
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`

They are not set for Production. The publishable key is browser-safe; no secret/service-role key has been placed in frontend code or Vercel browser-exposed variables. The Vercel Preview deployment must be regenerated from the latest branch commit to receive the variables.

### Remaining work — do not mark as complete yet

- Implement Supabase Auth UI and backend JWT verification.
- Configure the intended sign-in provider and production email delivery/redirect URLs.
- Implement authenticated create/list/detail/resume APIs using user UUID from verified Auth identity.
- Implement durable asynchronous execution and source-specific retry handling; the new schema is ready but no worker has been deployed or connected.
- Integrate the verified Drive archive into run retrieval/cache checks.
- Add two-user RLS isolation tests against this project and end-to-end sign-in/resume tests.
- Keep PR #1 Draft/Open/Unmerged and Production unchanged until the user explicitly authorizes release.


## 12. Authenticated accounts and saved-run persistence — 2026-11-09

### Implementation

- Current implementation commit before this roadmap update: `61bf3c580b528020540f1c393e668f0e97478a68`.
- Added `src/fieldshift/api/supabase_auth.py`:
  - Uses only `SUPABASE_URL` plus `SUPABASE_PUBLISHABLE_KEY` (legacy anon key fallback).
  - Validates every supplied access token by calling Supabase Auth `/auth/v1/user`; the API never trusts a user ID supplied by the browser.
  - Uses the caller's access token for PostgREST RPC/reads, so the caller remains subject to RLS. No service-role/secret key is used or exposed.
  - Persists exact request snapshot, source statuses/quality/provenance, result payload, evidence fingerprint and run event.
- Added API routes:
  - `GET /api/auth/config` — public-safe Supabase URL and publishable-key configuration only.
  - `GET /api/auth/me` — server-validated signed-in identity.
  - `GET /api/account/runs` — current user's saved run list.
  - `GET /api/account/runs/{run_id}` — owner-scoped run, source records and versioned results.
- `POST /api/analysis/run` persists completed analyses when a valid signed-in user token is present. Guests can still use the public demo/analysis flow, but guest analyses are not account-persistent.
- `POST /api/analysis/{run_id}/what-if` also saves the what-if result for signed-in users.
- Frontend adds passwordless email Magic Link sign-in, local session persistence/refresh, sign out, My Runs list/detail, saved result restore, and client-generated idempotency keys.
- The current app only exposes Email Magic Link sign-in; Google OAuth is not enabled/configured.

### Additional database migrations

1. `20261109133000_authenticated_analysis_persistence.sql` — owner-scoped INSERT policies and the `SECURITY INVOKER` RPC `public.save_completed_analysis(jsonb,jsonb,jsonb)`.
2. `20261109134500_authenticated_events_sequence.sql` — authenticated sequence usage for append-only event inserts.
3. `20261109143000_revision_aware_analysis_saves.sql` — owner-scoped lifecycle/source/result-current-marker updates and evidence revision handling.

Migration history confirmed on project `bipyrlegaxmhwzwrmcmi`:
- `persistent_analysis_runs`
- `private_worker_tables_and_fk_indexes`
- `private_backend_rls_policies`
- `authenticated_analysis_persistence`
- `authenticated_events_sequence`
- `revision_aware_analysis_saves`

### Security and database tests

- Security Advisor: no findings after the new Auth/persistence migrations.
- Health Advisor: no findings.
- Performance Advisor: only INFO-level unused-index notices on this still-empty application database.
- Executed a transaction-scoped RLS integration probe under the `authenticated` role:
  - Owner A saved one preliminary result.
  - Same idempotency key plus changed evidence produced revision 2, updated source status, and transitioned run status from `preliminary_ready` to `final_ready`.
  - Exactly one result row was marked current.
  - Two lifecycle events were recorded.
  - The transaction was rolled back; test user/run data were not retained.
- Executed a second transaction-scoped ownership test:
  - User A created a run with source/result/event rows.
  - User B then queried those records under their own JWT claims.
  - RLS returned 0 run, source, result and event rows to User B.
  - This transaction was also rolled back.
- GitHub Actions for commit `61bf3c580b528020540f1c393e668f0e97478a68`: push and PR runs succeeded.
- Python 3.11 and 3.12: 135 passed, 1 existing Starlette/httpx TestClient deprecation warning; Ruff, compileall and mypy passed (33 source files).

### Preview deployment and Auth activation requirements

- Vercel Preview for commit `61bf3c580b528020540f1c393e668f0e97478a68`: READY at https://field-shift0-qt6xckc1v.vercel.app.
- `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` exist only in Preview for `feat/krishinexus-real-data-school-lab`.
- Production environment and Production deployment were not modified.
- Live runtime HTTP smoke test could not be completed from the current execution environment because the preview hostname did not resolve through its available network path. Vercel confirmed the exact deployment state as READY; this is not a claim that end-user login email was tested.
- Before a Magic Link can return to this Vercel Preview, add the following redirect pattern in Supabase Auth → URL Configuration:
  - `https://field-shift0-*.vercel.app/**`
  - Current exact Preview URL: `https://field-shift0-qt6xckc1v.vercel.app/**`
- Supabase's default email sender is restricted to organization members. That is suitable for an initial owner test if the email belongs to the organization, but public sign-ups require a configured custom SMTP provider. No SMTP credentials were provided or configured. See Supabase's [email provider changelog](https://supabase.com/changelog?tags=auth) and [redirect URL guide](https://supabase.com/docs/guides/auth/redirect-urls).
- No user account was created during the database RLS probes. End-to-end Magic Link deliverability and browser session callback remain unverified until the redirect allowlist is set and an actual email is opened.

### Important boundary: what is and is not durable yet

- **Completed authenticated analyses** now persist in Supabase and can be reopened through My Runs after a fresh sign-in/session.
- Repeated checks with the same client request ID append a new immutable result revision when the evidence fingerprint or run status changes. Identical submissions are idempotent.
- The current `POST /api/analysis/run` still performs the scientific computation synchronously before the persistence RPC is called. It is not yet a queued background execution.
- The private `analysis_run_jobs` table is provisioned but no source-specific worker has been connected to it. Closing the browser during an upstream pending-data window does not yet guarantee autonomous provider polling; the existing frontend refresh path remains.
- The exact-coordinate completed-year POWER archive is now consulted before a live POWER request. The separate SMAP/HLS/MODIS/GPM archive resolver and real provider round-trip tests remain open.
- Until the durable worker and archive recovery phase is complete, do not claim that pending provider tasks continue independently for days or that all delayed datasets are automatically fetched after a user closes the page.

### Next implementation phases

1. Complete Preview Auth activation: add the redirect allowlist, then test a real owner Magic Link, refresh, sign-out, and sign-in again. Configure custom SMTP before opening sign-up to public users.
2. Run a real two-account end-to-end test through the deployed browser UI: create a completed analysis as User A, sign out, sign in as User B and confirm the run is absent, then sign back in as User A and restore it.
3. Add pre-execution durable run acceptance and enqueue source-specific jobs; do not wait until synchronous analysis completion to save the request snapshot.
4. Implement a durable worker with lease/claim, provider task reuse, bounded retries, Retry-After support, failed-product-only retry, and final reconciliation.
5. Wire verified Google Drive cache/archive lookup into source retrieval; verify checksums and exact spatial/time/product/QA compatibility before reusing cached data.
6. Complete delayed-data/revision tests with provider mocks and a true close-tab/reopen end-to-end test.
7. Keep PR #1 Draft/Open/Unmerged and Production unchanged until explicit user release approval.


---

## 12. Durable queue + worker implementation update — 2026-11-09

This section supersedes the earlier “Important boundary: what is and is not durable yet” and “Next implementation phases” statements above for the source-code/database state. It does **not** claim a production or live Preview worker smoke test.

### Implemented in the Draft PR branch

- Signed-in users submit an immutable request snapshot to `POST /api/analysis/queue`. The API validates the Supabase access token and calls `public.queue_analysis_request`; the browser no longer has to finish the analysis before the initial run record exists.
- `queue_analysis_request` validates the date range, binds the run to `auth.uid()`, computes a request hash, and uses the unique `(user_id, client_request_id)` key for idempotency. Concurrent replays with the same payload return the existing run; a different payload using the same key is rejected.
- The `analysis_runs` insert trigger creates the initial `build_result` job. The worker can claim both `build_result` and `reconcile_run` jobs through `public.claim_analysis_run_job`.
- The only intended HTTP worker entry point is `POST /api/internal/worker/tick`. The obsolete `/api/internal/worker` route was removed. The tick route compares the incoming worker token against server-only Preview settings and passes the matched token into the worker module.
- `src/fieldshift/api/analysis_worker.py` claims one job, loads the owner-scoped request snapshot, runs the existing FieldShift analysis engine, stores a versioned evidence snapshot, and either completes or reschedules the job.
- Worker writes use a publishable API key plus the legacy anon JWT role context. The additional high-entropy token is checked against Supabase Vault, and RLS requires an active lease tied to the exact run. No service-role key is placed in Vercel or the browser.
- Retry handling respects the slowest pending provider's Retry-After value (bounded to 15 minutes–48 hours), retries transient transport/provider failures, and treats authentication/validation failures as terminal.
- A run with any retryable provider still pending is saved as `waiting_for_data` with a **preliminary** result snapshot and `is_final=false`, even when the synchronous engine response itself reported `final_with_gaps`. The worker never upgrades a pending-data snapshot to a final result. At retry-budget exhaustion, the saved run remains `waiting_for_data` with stage `retry_exhausted`; it is not falsely marked final.
- The worker appends the lifecycle event while its lease is still active, then releases/reschedules the job. Source retry counters are maintained with column-scoped grants and UPDATE-then-INSERT logic; no table-wide anon UPDATE/INSERT privilege was added.
- The frontend can reopen the run from My Runs and restore the latest saved result revision. Browser polling is only a view refresh; the queue lifecycle itself is stored in Postgres.

### Live database migrations applied and verified

- Added the corrected worker state/idempotency migration and the worker source retry-counter/update-column grants.
- Replaced the source write path to avoid PostgreSQL's table-wide UPDATE requirement for `INSERT ... ON CONFLICT DO UPDATE`.
- Reordered worker completion so the token/lease-gated event policy remains true until the audit event is written.
- Live function privilege checks confirm `queue_analysis_request` is executable by `authenticated`, while `claim_analysis_run_job`, `worker_save_analysis`, and `worker_fail_analysis_job` are executable by `anon` only through the token/lease RLS surface.
- Security Advisor: no findings. Health Advisor: no findings.
- A transaction-scoped integration test ran as the low-privilege `anon` worker role with a temporary test-only token matcher. It successfully claimed an initial `build_result` lease, upserted a pending NASA SMAP source, wrote a preliminary result revision, appended one lifecycle event, and released the job to `retrying`. The returned database state was `waiting_for_data`, stage `waiting_for_datasets`, progress 75, `completed_at=NULL`, result kind `preliminary`, snapshot `is_final=false`. The transaction was rolled back.
- A separate transaction-scoped authenticated queue test exercised first submit, identical idempotent replay, and conflicting-payload rejection. Its transaction was rolled back.
- Post-test checks confirm zero retained synthetic users, runs, jobs, sources, results or events.

### Verification status and deployment boundary

- Current CI commit `5a0381374c914a52aba7c995c86b04a8aeb76dc3`: Python 3.11 and 3.12 both report 151 passed and one existing Starlette/httpx TestClient deprecation warning. Ruff, compileall, and mypy pass (34 source files).
- PR #1 remains Draft/Open/Unmerged.
- **The scheduled worker is intentionally paused.** Two cron job names had existed; both have been removed. A live `cron.job` check returns no active jobs. This prevents the old Preview build from repeatedly issuing failed requests while it lacks the newest worker API-key role context.
- The new branch requires a fresh Vercel Preview build to include the sensitive `SUPABASE_ANON_KEY` Preview variable and the final `/api/internal/worker/tick` implementation. Vercel's deployment API returned HTTP 402 `api-deployments-free-per-day` (more than 100 API deployment requests in 24 hours, retry-after 86400 seconds). The available Vercel CLI fallback is not installed in this execution environment. No billing/plan setting was changed and no Production deployment was attempted.
- Therefore, **the database worker logic and its low-privilege transaction test are verified, but an end-to-end Vercel Preview HTTP worker smoke test is still pending**. Do not claim the worker is live or autonomously processing user runs until a fresh Preview deployment returns an authenticated `idle` response and a real queued run successfully produces a new revision.
- Once a new Preview build is READY and the worker endpoint has passed the authenticated HTTP smoke test, re-register exactly one five-minute Supabase schedule named `fieldshift-analysis-worker`. Do not enable both schedule names. Keep Production unchanged until explicit release approval.

### Remaining work

1. Wait until Vercel's API deployment quota allows one fresh Preview build for the current PR head; verify that the Preview contains the new `SUPABASE_ANON_KEY` and matches the current Git SHA.
2. Trigger one manual worker tick using the Vault-stored token and Vercel protection-bypass value. First expect a safe `idle` response with no queued work; then run a real signed-in queue smoke test and verify claim → source/result/event write → retry/completion in Supabase.
3. Only after that smoke test succeeds, register the single five-minute `fieldshift-analysis-worker` cron job and verify its first HTTP response, not merely the pg_cron dispatch submission.
4. Test a real Magic Link account and a two-account owner-isolation flow in the newly deployed Preview. Configure a custom SMTP provider before enabling public sign-ups.
5. Verify reuse of provider task IDs across worker retries and wire the verified Google Drive archive/cache resolver into source retrieval. A queued request alone does not prove archive reuse or provider task resume.
6. Keep PR #1 Draft/Open/Unmerged and Production unchanged until explicit user release approval.


---

## 13. Preview worker smoke test and schedule activation — 2026-11-09 10:04 UTC

This update supersedes the paused-scheduler deployment boundary in Section 12 below, while preserving the distinction between an idle endpoint smoke test and processing a real user run.

- Git-linked Vercel Preview deployment `dpl_5KT2DaXfPCeqeb2QDCL9hYSYEDj4` is READY at `https://field-shift0-nzct8ir1y.vercel.app`, commit `2f97e4245354d36abd5c7c90fe187c62a2951de2`. Its branch alias is `field-shif-git-c9816e-moshiour-rahman-sarkers-projects-2cebe363.vercel.app`.
- The Preview environment metadata includes `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, sensitive `SUPABASE_ANON_KEY`, `FIELDSHIFT_WORKER_TOKEN`, and `VERCEL_AUTOMATION_BYPASS_SECRET`. All are scoped to Preview branch `feat/krishinexus-real-data-school-lab`; no Production values were added.
- Authenticated manual HTTP smoke tests through Supabase `pg_net` returned HTTP 200 with `{"ok":true,"processed":false,"message":"No queued analysis job is ready."}` for request IDs 8 and 11 against the branch alias and request ID 10 against the deployment-specific hostname. This verifies the current Preview's worker token check, Vercel protection bypass, Supabase publishable-key/anon-JWT context, PostgREST reachability, and empty-queue claim.
- Exactly one Supabase scheduled job is active: `fieldshift-analysis-worker`, `*/5 * * * *`. Both historical scheduler names are not simultaneously active. Migration `activate_verified_preview_analysis_worker` registers the single canonical schedule after the authenticated Preview smoke test.
- The 10:00 UTC `cron.job_run_details` entry reports `succeeded` for the pg_net dispatch statement. Its HTTP response row (request ID 9) separately recorded a transient `Error in the HTTP2 framing layer` with no HTTP status. That response is not treated as a worker success. Direct/manual retries through both Preview host forms returned HTTP 200. Verify the next scheduled HTTP response independently; pg_cron success only proves that the dispatch SQL ran.
- At this point there are still no real user analysis runs in the database. The successful HTTP 200 responses were idle-queue checks, not completed NASA analyses. The transaction-scoped worker RLS test described in Section 12 verified the full claim → pending source → preliminary result → lifecycle event → retrying-job transition and rolled back all synthetic rows.
- Latest CI for the schedule-activation migration commit `3f5b7ccc0e9342f7a922e3342a99b1b5718bf601`: Python 3.11 and 3.12 both report 151 passed and one existing Starlette/httpx deprecation warning; Ruff and mypy pass.
- PR #1 is still Draft/Open/Unmerged. No Production deployment or Production environment change has been made.
- The next end-to-end acceptance gate remains a real signed-in user's queued analysis: the worker must claim it, refresh provider evidence, persist a new result revision and event, and leave a retry scheduled while a provider remains pending. Until this is observed, do not claim a real NASA run has completed autonomously.


---

## 14. First scheduled HTTP tick verified — 2026-11-09 10:05 UTC

- The 10:05 UTC `fieldshift-analysis-worker` cron execution completed with pg_cron status `succeeded`.
- The corresponding pg_net response (request ID 12) completed with HTTP 200 and body `{"ok":true,"processed":false,"message":"No queued analysis job is ready."}`.
- This confirms the automatic five-minute schedule, Vault-sourced worker/protection headers, Vercel branch alias, worker token validation, Supabase API key/JWT role context, and queue claim path work together without a manual request.
- The earlier 10:00 UTC dispatch had one intermittent pg_net `HTTP2 framing layer` transport error; the 10:05 scheduled retry succeeded. The separate manual branch-alias and deployment-host checks also returned HTTP 200.
- No real user run was queued at this time, so the scheduled worker correctly returned `processed=false`. A real NASA source acquisition/retry/result revision has not yet been observed end-to-end.
- The single `fieldshift-analysis-worker` schedule remains active at `*/5 * * * *`; no duplicate schedule is present.


---

## 14. Real queued-run execution probe and explicit AppEEARS task resume — 2026-11-09

### Live Preview worker execution probe

A controlled temporary owner/run was submitted through the authenticated queue RPC and processed by the deployed Preview worker (deployment commit `2f97e4245354d36abd5c7c90fe187c62a2951de2`).

Request window: 2026-06-20 through 2026-06-30, inclusive; Mymensingh pilot coordinates; 0.4 ha; reduced Monte Carlo sample counts for the probe.

Observed worker response from pg_net HTTP response ID 14:

- HTTP 200, `ok=true`, `processed=true`.
- Worker claimed one `build_result` job (attempt 1) and ran the FieldShift V3 engine.
- Saved result revision 1, result kind `preliminary`.
- Run status `waiting_for_data`, stage `waiting_for_datasets`, progress 75, `completed_at=NULL`.
- Job status `retrying`, next retry `2026-11-09 10:28:46 UTC`.
- One `analysis_revision_created` event was recorded from `queued` to `waiting_for_data`.

Observed source provenance for the 11-day probe:

- NASA POWER Daily weather: 11 daily live records (2026-06-20 to 2026-06-30), required core source available.
- NASA GPM IMERG V07: 11 daily point observations, available.
- NASA NEX-GDDP-CMIP6 SSP245/SSP585: 12 monthly climate signals per scenario through Google Earth Engine, available as modeled climate signals.
- NASA SMAP, NASA HLS and NASA MODIS MOD16: AppEEARS tasks were pending; no values were substituted.
- SoilGrids remained not configured; the Mymensingh soil profile was a labelled pilot fallback.
- Weather outside the observation window was explicitly labelled synthetic extension; it was not represented as observed weather.

This is an actual queued Preview worker execution, not just an idle-route ping. It verifies request acceptance, durable claim, engine execution, result revision, status/event writes and retry scheduling. It does **not** establish a final decision-ready result, nor does it yet prove a later provider-completion retry produced a second revision.

### Temporary probe cleanup

- The probe used a synthetic `.invalid` email identity, not a real user account.
- Its run, job, source rows, result revision, event and auth user were deleted immediately after inspection.
- Follow-up SQL returned zero for the probe user, run, job, source, result and event counts. No test analysis data was retained.

### Explicit provider task-ID persistence added to the Draft PR

The real probe revealed that AppEEARS returned pending SMAP/HLS/MODIS tasks with `retry_after_seconds`, but those task IDs were not being propagated from the adapter into the saved evidence records. The adapter had an account-task-list fallback, but the durable worker did not persist and reload the exact provider task identifier.

The current Draft PR head now closes that gap:

- `appeears_point_timeseries` exposes a pending task's `provider_task_id`.
- `_evidence_state` preserves the identifier in the product evidence item.
- Worker source persistence writes the identifier to `analysis_run_sources.provider_task_id`.
- Before a retry, the worker queries source task IDs under its active run lease and injects them as internal execution metadata. The immutable farmer request snapshot is not modified.
- The V3 pipeline passes saved identifiers into AppEEARS. The adapter checks the exact persisted task first; a missing/expired ID falls back to the existing account task-list lookup before it can submit another task.
- Added cold-instance resume coverage verifies that a new AppEEARS invocation can complete using only the saved task IDs and does not submit duplicate tasks.
- Added worker tests verify that persisted IDs are loaded under the active worker context and passed to the engine without mutating the saved user request.

### Latest code verification and deployment gate

- Current code commit at this section's creation: `1cb42f9477f7a7600532ab2e2bc714210e0b4be2`.
- Python 3.11 and 3.12: **153 passed, 1 existing Starlette/httpx TestClient deprecation warning** each; Ruff, compileall and mypy pass (34 source files).
- The current READY Vercel Preview is still the older deployment `dpl_EW33d9RLejMcU2iJneCZJJaQQEvy`, commit `5886df8bee798aada53de9a450a24952a294b504`. It contains pending-task ID exposure but predates the explicit DB → worker → pipeline task-ID reload code.
- A deployment request for the current source commit was rejected by Vercel with HTTP 402 `api-deployments-free-per-day` and `retry-after: 86400`. The mapped Vercel CLI fallback is not installed in this execution environment. No alternate deployment mechanism was used to bypass the limit. No billing/plan setting was changed.
- The explicit task-ID reload code is deployed on the current READY Preview and CI-verified. Its actual reuse across a real AppEEARS worker retry remains unproven until a real provider task is submitted, persisted, and resumed on a later attempt.
- The one canonical five-minute Supabase schedule remains active and the old Preview worker responds to the idle endpoint. The temporary queue is gone, so it has no test job to process.
- PR #1 remains Draft/Open/Unmerged. Production, Production env vars, and the unrelated SARGuardian-Monorepo project remain unchanged.

### Remaining acceptance gates

1. Obtain one fresh Preview deployment after the Vercel deployment limit is resolved; verify its commit SHA equals the current PR head.
2. Re-run a controlled AppEEARS-backed queue probe and verify that the first worker revision stores non-empty `provider_task_id` values for pending NASA SMAP/HLS/MODIS sources.
3. Re-trigger the same run after its retry delay. Confirm the worker loads those exact IDs, queries those exact AppEEARS tasks, and does not submit duplicate tasks; then verify revision 2 and updated source/event state.
4. Test a real Magic Link owner sign-in, refresh, sign-out/sign-in, and two-account isolation after adding the branch Preview URL to the Supabase Auth redirect allowlist. A custom SMTP provider is still needed before public sign-ups.
5. Keep PR #1 Draft/Open/Unmerged and Production unchanged until explicit release approval.


---

## 15. Preview SQL regression audit — 11 November 2026

A full-function replacement for the worker lease/audit ordering fix unintentionally restored an older unconditional `retry_at → waiting_for_data` mapping. This contradicted Phase 1's required-vs-optional readiness contract: optional satellite evidence could remain pending while a useful preliminary result was available, but Postgres hid it as waiting for data.

### Corrected Preview database state

- Additive migration `20261111052954_worker_preserve_preliminary_status_with_active_lease` now preserves `preliminary_ready` when the Python worker sends that status with a retry time. Required pending evidence remains `waiting_for_data`.
- Both paths retain `completed_at=NULL`, `result_kind=preliminary`, `is_final=false` and the durable retry while data is pending.
- The corrective replacement retains the worker token/header comparison, active-lease check, source write grants, evidence fingerprint/revision logic and event-before-lease-release ordering.
- The failure handler `worker_fail_analysis_job()` was separately corrected by `20261111050822_worker_fail_event_before_lease_release` so transient/terminal failure events are inserted before clearing the job lease.
- Live SQL read-back verifies both functions' event-before-release ordering and token/lease checks. The canonical single five-minute cron is active.
- Matching versioned SQL files and a regression test are committed on `feat/krishinexus-real-data-school-lab`.

### Current code verification

- Review commit: `9adacb90cf06d2745226b39096bd46fe46de3ac4`.
- Exact Git SHA Preview: `https://field-shift0-e4qwww1wl.vercel.app`, deployment `dpl_37RcoXzaANYhit4CDtaDiV94qQMD`, READY.
- PR CI run #619 (`42966807479`) passed Python 3.11 and 3.12 with **187 passed, 1 existing Starlette/httpx TestClient deprecation warning** in each matrix; compileall, Ruff and mypy passed.
- The seven checked Supabase run/account/source/result/event/job/cache/profile tables remain empty. An owner-created run has not yet demonstrated the preliminary revision, later source completion or a real failure/retry transaction end-to-end.
- PR #1 remains Draft/Open/Unmerged. Production remains on the older process-memory deployment without Supabase Auth/worker configuration. No Production deployment or database was changed.

### Next gates (unchanged)

1. Complete real owner Magic Link / queue / My Runs / two-account isolation tests on the exact Preview.
2. Verify one real AppEEARS task creation, durable task-ID reuse and a later result revision without duplicate task submission.
3. Register and dispatch the 2025 nine-point SMAP pilot only after PR #2 is approved/merged; require full QA and remote private Drive checksum read-back.
4. Backfill and verify POWER daily history for 2016–2024; do not label monthly chart aggregates as daily coverage.
5. Provision a separate Production Supabase/Auth/worker environment and pass the same account/queue gates before Production release.


---

## 16. Supabase egress reduction and Google Drive result archive — 11 November 2026

The organization Usage screenshot is an All-projects view, not a per-project measurement. Five Supabase projects exist in the Free organization; FieldShift0 was created on 9 November, whereas the graph includes activity from 26 October. The 7.21 GB aggregate therefore cannot be attributed wholly to FieldShift0. Auth egress is separate from PostgREST/Database egress; the screenshot explicitly identifies PostgREST.

A code audit found two avoidable egress multipliers in the signed-in My Runs path: the detail endpoint selected every column and every result revision, and the client repeated that full-detail request during background polling. Branch fix/supabase-egress-drive-result-archive addresses this without changing the database schema:

1. Add an owner-scoped status endpoint that selects only compact run/source status and never queries analysis_results.
2. Poll with an adaptive interval, fetching the full detail only when latest_result_id changes or the run transitions to final.
3. Read a single current analysis_results row by latest_result_id with limit=1; do not return all historical revisions.
4. Put full new result JSON in the existing private Google Drive object store under a run/request UUID and SHA-256 path. Supabase stores only the Drive reference, SHA-256, byte count and small metadata/queue state.
5. Verify SHA-256 when restoring Drive objects. Continue to read legacy inline result payloads so existing saved analyses do not break.

Supabase still owns Auth, owner RLS, compact run metadata and the atomic transactional job queue. This preserves correct lease/idempotency semantics; Google Drive is not used as a queue database. No schema migration or destructive old-row migration is required.

At this checkpoint the branch is not yet merged or deployed; CI and a real Drive write/read round-trip are release gates. The Usage dashboard supports selecting an individual project/branch; measure each one before attributing historic organization egress or changing the status of another project. Do not pause/delete projects or upgrade from Free solely to clear the warning. The dashboard warning gives 9 December 2026 as the restriction date if the organization remains over quota.

