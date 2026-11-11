# KrishiNexus / FieldShift0 — Final Owner Handoff

**Prepared:** 11 November 2026 (Asia/Dhaka)  
**Repository:** `moshiour0/FieldShift0`  
**Production branch:** `main`  
**PR #1:** [Merged](https://github.com/moshiour0/FieldShift0/pull/1) · merge SHA `1e96de91ba991c6265a9db6956bffedb880115a2`  
**Latest main commit:** `0c84051abb7d13a0d55ab02ae75017a549c360df`  
**Stable Production URL:** https://field-shift0.vercel.app  
**Latest Production deployment:** `dpl_CWxAQCCRMABZMj4ASxFPzWw4eAtU` · READY  
**Supabase project:** `FieldShift0` · `bipyrlegaxmhwzwrmcmi` · Free · `ap-south-1`  
**Superseded workflow PRs:** #2 and #3 closed; their workflow files are included in PR #1.

> **Release status:** Production is live. Sections 1–14 below retain the earlier pre-release audit snapshots as historical context; whenever they conflict with the final release state, **Section 15 is authoritative**. Do not follow old Preview-only instructions in the historical sections.
>
## 1. Historical pre-release verification snapshot

### GitHub and CI

- PR #1 is Open, Draft, Unmerged, and GitHub currently reports `mergeable=true`. Its latest head is `aac5f19f6da71bc7a0d6cf862a56e74e49915cc7`; the feature branch includes the latest `main` commits through merge commit `d3ef6f428fb79d69bb06ba5efae525c279ab68ee`.
- Exact-head push run #600 (`42957064170`) and PR run #601 (`42957069874`) both passed on Python 3.11 and 3.12.
- Each Python job: **184 passed**, one existing Starlette/httpx TestClient deprecation warning; `compileall`, strict Ruff and mypy (34 source files) all passed.
- The CI workflow and the three feature-branch data workflows now pin GitHub actions by immutable commit SHA: `actions/checkout` v7.0.1 (`3d3c42e5aac5ba805825da76410c181273ba90b1`) and `actions/setup-python` v7.1.0 (`6d4fd22b20465ccc0f7354476588e8df7c9ca0e0`). The references are pinned, not floating tags.
- The branch is mergeable after reconciling the two newer `main` commits. No PR has been merged in this handoff.

### Exact-head Vercel Preview

- Deployment `dpl_FThVJpxo8tKp5GArfnEkDVAH7L3R` is READY and its Git metadata matches SHA `aac5f19f6da71bc7a0d6cf862a56e74e49915cc7`.
- Smoke GET checks: `/`, `/health`, `/api/status`, `/api/auth/config`, `/api/regions`, `/api/demo`, `/school-game/`, and `/static/history.html` returned HTTP 200.
- `/health` reports `engine=3.0.0`, `product=3.3.0`; auth config reports `configured=true`, provider `email_magic_link`; regions returns 12 provisional planning groups and nine representative points; public demo returns eight strategies.
- A static demo run ID is readable. A random live run ID returns HTTP 404 with the instruction to use signed-in My Runs. This is the expected public/live data boundary.
- Vercel runtime error aggregation returned no errors in the checked 24-hour window.
- Preview `/api/status` reports durable Supabase queue/versioned Postgres result storage for signed-in runs and active execution across instances. This is configuration/runtime evidence, not proof of a real person completed an analysis.

### NASA POWER archive — all nine reference points

The exact-head Preview was queried for 2025-01-01 through 2025-12-31 for all nine configured points:

| Reference point | Daily records | Coverage | Result |
|---|---:|---:|---|
| Mymensingh | 365/365 | 1.0 | Complete |
| Dhaka | 365/365 | 1.0 | Complete |
| Rajshahi | 365/365 | 1.0 | Complete |
| Rangpur | 365/365 | 1.0 | Complete |
| Khulna | 365/365 | 1.0 | Complete |
| Barishal | 365/365 | 1.0 | Complete |
| Sylhet | 365/365 | 1.0 | Complete |
| Chattogram | 365/365 | 1.0 | Complete |
| Rangamati | 365/365 | 1.0 | Complete |

Every response reports daily archive representation, `status=complete`, no missing dates/years and SHA-256 provenance. These are NASA POWER gridded representative-point samples, not farm sensors, district averages, official AEZ means or arbitrary farm coordinates. The bundled Mymensingh 2016–2025 monthly archive remains chart-only. Full 2016–2025 daily coverage is **not** claimed; 2016–2024 daily archives remain to be backfilled and verified.

### Satellite data status

The exact Preview reports `not_archived` for SMAP, HLS, MODIS MOD16 and GPM at the nine representative points. `not_archived` is not zero and is not a failed observation. No nationwide gridded satellite archive is claimed.

The SMAP reference-point writer is implemented with strict gates: both `sm_surface` and `sm_rootzone` require eight valid 3-hourly observations per UTC day; each year requires full daily coverage, exact point identity, private Drive write/read-back and SHA-256 verification. The actual 2025 pilot has **not** been dispatched or validated.

## 2. Supabase Preview state and worker correction

- FieldShift0 Supabase is `ACTIVE_HEALTHY`; 24 migrations are recorded.
- Exactly one `fieldshift-analysis-worker` cron is active at `*/5 * * * *`. The latest observed tick succeeded at 2026-11-11 04:10 UTC; `pg_net` reported HTTP 200, not timed out, and `processed=false` because no job was queued. This proves the protected idle tick, not a real analysis run.
- All seven checked user/run/source/result/event/job/cache/profile tables currently contain zero rows. No real authenticated user run, result revision, cross-account isolation or one-/two-day browser restoration has yet been demonstrated.
- A worker persistence defect was found: the Preview database function released its active job lease before inserting the run audit event, while the event RLS policy requires that lease. The fix was applied to the **Preview Supabase project only** as migration `20261111040447_worker_event_before_lease_release_v2`.
- Post-apply read-back confirms `worker_save_analysis()` now inserts `analysis_run_events` before clearing `lease_expires_at` / `lock_owner`. The matching SQL file exists at `supabase/migrations/20261111040447_worker_event_before_lease_release_v2.sql` on this branch. Migration history and repository filename are aligned.
- Supabase advisors still report the intentional owner-scoped SECURITY DEFINER recheck RPC warning and two private worker-queue RLS initialization-plan performance warnings. Do not silence these by weakening owner or worker-token checks; the recheck RPC verifies `auth.uid()` and is not executable by `anon`.
- The migration correction was applied only to the FieldShift0 Preview Supabase project. No Production database migration was applied.

## 3. Production is not release-ready

Current Production remains on the older `main` deployment:

- URL: https://field-shift0-6ivtl33z2.vercel.app
- Deployment: `dpl_B2hHCWQqkkuPW9HzWtFECpgGWfMX`
- Source: `main` SHA `c84c9aa7a52eb74b64e7caaba09989ce80e4e273`
- `/health` returns `product=3.1.3` (Preview is `3.3.0`).
- Production `/api/status` reports `storage=process_memory`, `durable_across_instances=false`; `/api/auth/config` returns HTTP 404.
- The Supabase URL, publishable key, anon key and worker token are configured only for the Preview target/feature branch in Vercel metadata; the Production target is not provisioned for the durable signed-in queue.

Therefore a READY Preview does **not** mean the live Production site is updated or durable. Do not switch Production alias or promote until Production environment, auth redirect allowlist, Supabase production project/migrations, worker schedule/secret, and the real user acceptance test are reviewed. No Production deployment, alias, domain, env or database change was made.

## 4. Workflow registration and operator actions

GitHub requires a `workflow_dispatch` or scheduled workflow file to exist on the default branch before its Run workflow/schedule can activate. The feature branch contains the current workflow code, but two registration PRs remain separate so they can be reviewed without merging all application code.

- **PR #2 — [Register manual SMAP archive workflow](https://github.com/moshiour0/FieldShift0/pull/2):** Open/Draft/Unmerged. Adds only `.github/workflows/smap-reference-backfill.yml` to `main`. Its branch SHA is `154e06833a5c20dbe84f769e5eb11c0cbe7b0094`; push and PR CI runs #594/#595 passed. The workflow file is action-pinned. After owner approval/merge of PR #2, choose branch `feat/krishinexus-real-data-school-lab`, keep `start_year=2025`, `end_year=2025`, and dispatch the first SMAP pilot.
- **PR #3 — [Register weekly NASA POWER refresh](https://github.com/moshiour0/FieldShift0/pull/3):** Open/Draft/Unmerged. Adds only `.github/workflows/history-refresh.yml` to `main`. Its branch SHA is `46cb4b837f3a7ea053cd4d515cb18b6597792ae8`; push and PR CI runs #596/#597 passed. The schedule is Tuesday 03:20 UTC and is gated by `GOOGLE_DRIVE_ARCHIVE_ENABLED=true`. Do not set that variable until PR #1's scripts/code are merged and the four Drive Actions Secrets have passed preflight.
- The existing manual **Backfill nine-region NASA POWER daily history** workflow is already on `main`. To fill older daily gaps, select branch `feat/krishinexus-real-data-school-lab` and dispatch `start_year=2016`, `end_year=2025`; the workflow reuses checksum-valid 2025 files and fetches only missing/invalid years. It processes at most three regions concurrently.
- PR #2 and PR #3 are workflow-only merges, but this Vercel project is connected to `main`; either merge may trigger a Production deployment from unchanged app source. Review that side effect first.
- The current connected GitHub tool can inspect CI, Actions runs and logs but does not expose `workflow_dispatch`. GitHub Actions secret values cannot be inspected through this connection. No workflow dispatch or secret read was performed.

## 5. What the project contains

- FieldShift V3.3 crop-rotation decision-support engine: root-zone water accounting, SCS-CN runoff, irrigation losses, nutrient stock conversion, SOC proxy, operational constraints and input-level Monte Carlo uncertainty.
- NASA POWER weather; AppEEARS adapters for SMAP, HLS and MODIS MOD16; GPM IMERG and NEX-GDDP-CMIP6 Earth Engine paths; optional SoilGrids and farmer-entered soil evidence.
- Evidence and provenance reporting, 12 provisional Bangladesh planning groups, nine representative reference points, regional history explorer, farmer workflow and Bengali Learning Lab.
- Passwordless Supabase Auth, owner-scoped My Runs, immutable request snapshots, source states, versioned results, lifecycle events, durable queue, leased worker and manual owner recheck.
- Private Google Drive archive adapters and QA/backfill workflows. The 2025 NASA POWER daily archive is verified; satellite archive ingestion is not yet complete.

## 6. Remaining acceptance gates

1. Owner-controlled Preview login: use a real test mailbox, submit a small analysis, verify the queued job, worker persistence, source states, result revision and My Runs. Sign out/in, reopen after at least one day, and verify the same owner-run is restored.
2. Repeat with a second owner-controlled account and prove it cannot list, read or recheck the first account's run.
3. Dispatch the 2025 SMAP pilot through PR #2 after approval/merge. Require Drive write/read/delete preflight, Earth Engine collection visibility, all nine points, 365 daily rows, 8/8 intervals/day for both bands, full coverage and remote Drive SHA-256 read-back.
4. Backfill POWER 2016–2024 (workflow input 2016–2025 is safe; verified 2025 objects are reused), then confirm all 9×10 region/year objects and exact daily coverage. Do not confuse chart-only monthly Mymensingh data with daily observations.
5. Validate live AppEEARS task creation/resume, provider task-ID reuse, GEE/SMAP retry, HLS/MODIS/GPM actual responses and Google Drive write/read-back. Configuration flags alone are not provider validation.
6. Complete Bangladesh-local crop-calendar, soil, yield/price and field validation with qualified agronomist review. The current crop/soil pack remains a Mymensingh pilot, not nationwide calibrated agronomy.
7. Production release: provision a dedicated Production Supabase/Auth/worker configuration, apply migrations through reviewed version-controlled process, configure auth redirects and verify the real-user acceptance gates. Obtain explicit owner approval before merging PR #1 or promoting Production.

## 7. Ownership and transfer

The GitHub repository is under `moshiour0`, the Vercel project is under the owner's Vercel team, and the FieldShift0 Supabase project is in the owner's Supabase organization. The code, PR trail, operator docs and deployment Preview are available in those existing accounts; a separate account-ownership transfer is not required for the same owner.

Google Drive OAuth belongs to the Google account that created the private archive folder. Keep the folder private and retain its access under the owner's Google account. For another operator, grant that person least-privilege GitHub, Vercel, Supabase and Drive access through each provider; never share secret values in chat or commit them to Git.

**Release decision:** Engineering Preview is verified and the PR is mergeable, but the whole project is **not yet operationally complete or Production-ready** until the owner-controlled live data and authenticated user gates above pass.


---

## 8. Worker failure-path audit update — 11 November 2026, 05:16 UTC

A second worker lease/RLS ordering defect was identified during a source-level review of the failure path. The successful-save function already wrote its audit event before releasing the active lease, but `worker_fail_analysis_job()` previously released/rescheduled the job before inserting its failure/retry event. The event INSERT policy requires `private.worker_has_active_lease(run_id)`, so a provider/network failure could make that event write fail and roll back failure bookkeeping.

### Fix committed and applied to Preview

- Added `supabase/migrations/20261111050822_worker_fail_event_before_lease_release.sql`.
- The replacement `public.worker_fail_analysis_job()` retains the incoming worker-token comparison, active-lease check and row lock (`FOR UPDATE`).
- The run failure state is updated first when terminal; the audit event is then inserted while the queue row is still `running` and the lease is valid. Only after that event succeeds is the job marked `retrying` or `failed` and the lease cleared.
- Added `tests/test_worker_fail_migration.py`, which protects the required event-before-lease-release ordering and token/lease checks.
- Applied the migration to the non-production FieldShift0 Supabase Preview project. Database migration history now records `20261111050822_worker_fail_event_before_lease_release`; function-definition read-back confirms the new event ordering. No Production database was changed.
- New commit: `f0103f57590377051b74bb054e690db884125a82`.
- PR CI run #611 (`42964413377`) passed on Python 3.11 and 3.12: **185 passed, 1 existing Starlette/httpx TestClient deprecation warning per job**. `compileall`, Ruff and mypy (34 source files) passed in both jobs.
- Vercel Preview deployment `dpl_2zf4cBooH5YUBYLP29ayngycfbp5` is READY and its Git SHA matches `f0103f57590377051b74bb054e690db884125a82`.

### Current verification boundary

- PR #1 remains Open / Draft / Unmerged; PR #2 and #3 remain Open / Draft / Unmerged. Production remains on the unchanged `main` application baseline and has not been promoted.
- The Preview database has the canonical five-minute worker schedule. The queue and seven checked run/source/result/event/job/cache/profile tables remain empty; there is no real owner-created run on which to exercise a live provider-failure retry. The failure-path fix is migration-read-back and CI-regression-test verified, but a real failed-job end-to-end scenario is not claimed.
- Supabase Advisor still reports one warning for the owner-checked authenticated `request_analysis_run_recheck(uuid)` SECURITY DEFINER function and two worker-queue RLS initialization-plan performance warnings. The owner identity check and worker-token/lease policy remain intact; do not remove these checks to silence warnings.
- The new Preview deployment is confirmed READY by Vercel metadata. This audit did not claim a fresh public HTTP smoke test because direct requests to the protected Vercel hostname were not accessible through the available inspection path.

### Remaining external/operator acceptance gates

1. Use two owner-controlled email accounts to test Magic Link sign-in, run submission, My Runs restoration and cross-account denial on the exact-head Preview. Configure custom SMTP before public sign-ups.
2. Run the real AppEEARS task creation / saved-task-ID resume / later result-revision flow; confirm no duplicate task POSTs and no unverified source is called final.
3. Dispatch the 2025 nine-point SMAP pilot after PR #2's workflow registration is approved and merged to the default branch; validate every daily interval, both soil-moisture bands, private Drive read-back and SHA-256. The manual POWER history workflow already on `main` can backfill 2016–2024 against the feature branch; confirm exact per-year coverage before claiming ten-year daily history.
4. Complete Bangladesh crop-calendar, soil, yield/price and field-trial calibration with qualified agronomist review. The crop/soil recommendations remain a Mymensingh pilot.
5. Provision and validate a separate Production Supabase/Auth/worker environment, migration history, redirect allowlist, secrets and scheduled worker. Keep Production unchanged until those gates pass and the owner explicitly approves release.


---

## 9. Required-vs-optional pending regression correction — 11 November 2026, 05:37 UTC

A further database/source comparison found that the full-function replacement in migration `20261111040447_worker_event_before_lease_release_v2` had restored the older unconditional retry mapping in `worker_save_analysis()`. Python correctly sent `preliminary_ready` when only optional satellite evidence was pending, but the database overwrote it with `waiting_for_data`. This contradicted the documented product contract and hid a useful preliminary result even though the worker had computed one.

### Corrective migration and regression protection

- Applied additive Preview migration `20261111052954_worker_preserve_preliminary_status_with_active_lease`.
- The live function now preserves `preliminary_ready` when `p_retry_at` is set and Python sends `p_run.status=preliminary_ready`. Required-source pending runs remain `waiting_for_data`. Pending runs remain non-final, keep `completed_at=NULL`, store a `preliminary` result revision and retain the retry.
- The replacement is based on the active Preview function and retains its worker-token comparison, active lease validation, RLS-authorized audit event before queue lease release, source persistence, evidence fingerprinting and result revision behavior.
- Added branch migration `supabase/migrations/20261111052954_worker_preserve_preliminary_status_with_active_lease.sql` and regression tests in `tests/test_worker_status_migration.py`.
- Live SQL read-back confirms: `preliminary_ready` branch exists; the audit event insert precedes the job update that clears the lease; the separate failure handler also writes its event before releasing the lease.
- The five-minute `fieldshift-analysis-worker` schedule remains exactly one active job. No test run, synthetic user or analysis row was inserted; all seven inspected persistence/cache tables remain empty.
- Final regression commit for this correction: `9adacb90cf06d2745226b39096bd46fe46de3ac4`.
- PR CI run #619 (`42966807479`) passed Python 3.11 and 3.12: **187 passed, 1 existing Starlette/httpx TestClient deprecation warning per job**. `compileall`, Ruff and mypy (34 source files) passed in both jobs.
- Exact-head Vercel Preview `dpl_37RcoXzaANYhit4CDtaDiV94qQMD` is READY with Git SHA `9adacb90cf06d2745226b39096bd46fe46de3ac4`. Vercel runtime error aggregation found no errors in the selected 24-hour window. Direct public HTTP endpoint validation could not be performed because the Preview hostname is protected/inaccessible to the available web request path; READY metadata is not represented as an HTTP smoke test.

### Current end-to-end boundary

- PR #1 remains Open / Draft / Unmerged and GitHub reports it mergeable. PR #2 and #3 also remain Draft/Open/Unmerged.
- Production remains on `main` deployment `dpl_B2hHCWQqkkuPW9HzWtFECpgGWfMX`, commit `c84c9aa7a52eb74b64e7caaba09989ce80e4e273`, product 3.1.3, `process_memory`, and no `/api/auth/config`. Supabase/worker variables are Preview-only. No Production alias, environment or database was changed.
- GitHub default branch `main` currently contains only `.github/workflows/ci.yml` and `.github/workflows/history-backfill.yml`. The SMAP registration (PR #2) and weekly refresh registration (PR #3) remain outside `main`, so neither action is dispatchable/scheduled from the default branch yet. The connected GitHub tool can inspect Actions but does not expose `workflow_dispatch`; no workflow was dispatched and no Action secret value was read.
- 2025 NASA POWER daily coverage remains complete at the nine representative points. 2016–2024 daily coverage remains unverified; SMAP/HLS/MODIS MOD16/GPM archive status remains `not_archived`. The 2025 SMAP pilot and live AppEEARS/GEE task-resume flow are still unverified.
- Owner-controlled Magic Link account creation, queue submission, My Runs restoration and two-account isolation remain untested. No human account credentials/session were supplied. Public email sign-up still needs a custom SMTP provider.
- Bangladesh crop calendar, soil, yield/price and field-trial calibration remain open; this is still a Mymensingh pilot, not a nationwide-calibrated agronomy service.

**Release decision:** the exact feature Preview, CI and Preview database function contracts are now verified at commit `9adacb9`. The whole project is still **not Production-ready** until real account/provider/archive acceptance and separate Production Supabase/Auth/worker provisioning are completed.


## 10. Documentation handoff checkpoint — 11 November 2026, 05:42 UTC

The handoff, README, Data Foundation Operations and Persistent Analysis Roadmap now reflect the worker failure-path and optional-pending status corrections. The latest documentation/operations checkpoint before this handoff refresh is commit `6b0b1d27cb665652ec0f5228b0846369eebcff4c`; its Vercel Preview `dpl_Awn39qMv7nu9FG4vWy3Bz4BXo5pt` is READY with the matching Git SHA. PR CI run #634 (`42968099190`) passed on Python 3.11 and 3.12: 187 tests in each matrix, the existing Starlette/httpx deprecation warning, Ruff, compileall and mypy. The application-code correction remains `9adacb90cf06d2745226b39096bd46fe46de3ac4`; docs/runbook commits do not change application code.

The documentation refresh changes no runtime code, secrets, cloud ownership, database schema or Production setting. PR #1 remains Draft/Open/Unmerged. The exact end-to-end and Production release gates remain those listed in Sections 6 and 9.


## 11. Repository governance note — 11 November 2026

The default `main` branch is currently **not protected** and has no required status-check rules. CI runs are passing on PR #1, but GitHub does not currently enforce those checks as a merge requirement. Before a future Production release, configure a repository ruleset/branch protection that requires the FieldShift CI checks and review approval. The available GitHub connection can read this state but does not expose branch-protection mutation, so no repository protection setting was changed.


## 12. Final owner handoff validation — 11 November 2026, 05:52 UTC

- The runtime fix that must be used by the feature branch is `9adacb90cf06d2745226b39096bd46fe46de3ac4`; its matching Preview `dpl_37RcoXzaANYhit4CDtaDiV94qQMD` is READY.
- The current documentation/operations checkpoint before this final handoff consolidation was `749bbd04b2837ca51ad212984f818c6f721635e8`; its matching Preview `dpl_HUHD1xZaCWR7vhQMGsLG4bRKfSoT` was READY.
- PR CI run #636 (`42968480158`) passed Python 3.11 and 3.12: **187 passed per job**, one existing Starlette/httpx TestClient deprecation warning per job; Ruff, compileall and mypy passed in both matrices.
- The final documentation consolidation changes no application runtime, database function, provider credentials, workflow dispatch, or Production setting.
- PR #1 remains Draft/Open/Unmerged; PR #2/#3 remain Draft/Open/Unmerged; no Production deployment or main merge is authorized by this handoff.


## 13. Email sign-in redirect incident and zero-cost guardrails — 11 November 2026

### What the live evidence says

- The only Supabase organization `moshiour's Org` is on the **Free** plan (`tier_free`). No plan upgrade, paid add-on, SMTP purchase, domain purchase or billing action was performed.
- A privacy-preserving aggregate query of `auth.users` returned: **1 user total, 1 email-confirmed, 1 with a recorded sign-in timestamp**. No email address or user identifier was retrieved. The user account was created and confirmed, and Supabase has recorded a sign-in event; this does not prove the browser retained a FieldShift session because the email callback opened `localhost:3000`.
- The FieldShift browser code already constructs the OTP `redirect_to` from the current page's `window.location.origin` and `pathname`. The likely remaining fault is Supabase Auth URL Configuration: `Site URL` is still the default `http://localhost:3000`, or the current Vercel redirect URL is not in the allowlist. When a redirect is absent/invalid, Supabase falls back to Site URL.
- The latest Preview stable branch alias is `https://field-shif-git-c9816e-moshiour-rahman-sarkers-projects-2cebe363.vercel.app`; latest exact deployment URL is `https://field-shift0-dprqqtf6d.vercel.app`.
- The available Supabase connection can inspect project metadata and query the database but does not expose the hosted Auth URL Configuration mutation. The operator must set the Site URL and Redirect URLs in the Supabase Dashboard; no SQL workaround or Vercel environment edit can replace that setting.
- The latest application callback UX now displays an explicit success toast only after `/api/auth/me` validates the returned session, and displays a clear error when an email callback returns without a valid session. It does not treat email delivery or a redirect alone as proof of sign-in.
- Callback UX correction commit: `141d1366a341b757efa23280458758895c73adab`. Exact Preview deployment `dpl_3FZNqo9LFNEMHu4ecNdQk3f3GBkR` is READY. PR CI run #640 (`42978142579`) passed Python 3.11 and 3.12: **187 passed per job**, one existing Starlette/httpx TestClient deprecation warning; Ruff, compileall and mypy passed.

### Operator action to fix redirects

Open Supabase Dashboard → Authentication → URL Configuration for project `bipyrlegaxmhwzwrmcmi`:

- Temporary **Site URL** for the current feature Preview:
  `https://field-shif-git-c9816e-moshiour-rahman-sarkers-projects-2cebe363.vercel.app`
- Add this **Redirect URL**:
  `https://field-shif-git-c9816e-moshiour-rahman-sarkers-projects-2cebe363.vercel.app/**`
- Also allow the current immutable deployment if testing from it:
  `https://field-shift0-dprqqtf6d.vercel.app/**`
- Save settings. Open the stable branch alias above (not `localhost` and not the older Production domain), choose Sign in, and request one fresh magic link. Do not re-register; the existing email-confirmed account is already present. Use the newest link once.
- On success the header changes to `My Runs` and the new callback toast says the session was verified. If the callback still fails, capture the visible error and current URL without sharing the email token or hash.

This is a temporary Preview Site URL. Before a future Production release, change the Site URL to the verified Production domain and keep the Preview alias as an additional allowlisted Redirect URL.

### No-cost policy

- Supabase organization is verified Free. Built-in Supabase Auth SMTP is included without a separate email bill, but the current built-in service sends at most **2 messages per hour per project** and only to addresses that belong to the Supabase organization team. It is best-effort/testing infrastructure, not a public production mail service. A custom SMTP service may have its own free limits or charges; none was configured by this work.
- Free Supabase plan quota includes 50,000 Monthly Active Users; stay within the Free plan quotas for database, storage and egress. Projects may pause after seven days of inactivity; a pause does not create a paid charge.
- Google Earth Engine is free only for eligible noncommercial/research/education use registered as noncommercial. A billing account is not required for noncommercial use. Commercial/operational/fee-for-service use requires a paid Earth Engine configuration; other enabled Google Cloud services can still incur charges. Do not run the SMAP/GPM/NEX Earth Engine jobs until the owner verifies that the Cloud project is registered as noncommercial and no paid Google Cloud billing/services are enabled. If the intended use is commercial, keep Earth Engine paths disabled under the strict $0 requirement.
- NASA POWER and NASA AppEEARS are used as public NASA data services; keep within their fair-use/provider limits. Google Drive storage must remain within the account's no-cost quota.
- The Vercel team plan was not exposed by the connected read interface, and the billing-charges endpoint returned `costs_not_found`; therefore no claim is made about the user's Vercel subscription or historical charges. No Vercel purchase, promotion, billing setting or paid service was changed by this task.
- User reports that the six GitHub Actions secrets have been added. Secret values are intentionally not readable through the connected GitHub interface. Workflow preflight is the authoritative operational validation; no workflow was dispatched by this task.


## 14. Earth Engine zero-cost opt-in and production credential isolation — 11 November 2026

### Code guard

- Added an explicit `FIELD_SHIFT_GEE_NONCOMMERCIAL_CONFIRMED=true` gate to `gee_credentials_configured()`. Project ID and service-account JSON alone no longer activate GEE. The opt-in must be set only after the owner has verified the Cloud project is registered for eligible noncommercial/research use and no paid Google Cloud services/billing will be used for this workload.
- The same guard controls Preview App API GEE paths (including SMAP/GPM/NEX connectors) and the SMAP archive scripts.
- The SMAP Actions workflow now also requires repository Actions Variable `FIELD_SHIFT_GEE_NONCOMMERCIAL_CONFIRMED=true` in its preflight and ingest jobs. Without it, the workflow exits before any Earth Engine or NASA data request.
- Vercel metadata showed `FIELD_SHIFT_GEE_PROJECT` and `FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON` were previously targeted to both Production and Preview. Both are now restricted to Preview and branch `feat/krishinexus-real-data-school-lab`; Production no longer receives these two GEE credentials. The secret values were not read or changed. This intentionally disables GEE in the old Production deployment to prevent an unverified billing path.
- No GEE preflight, AppEEARS backfill, SMAP backfill or NASA workflow dispatch was executed after adding this gate. The variable is currently absent, so GEE remains disabled by default.

### Verification

- Added a regression test covering missing/false/true noncommercial opt-in and missing credentials.
- Initial CI exposed six offline tests that mocked Earth Engine but did not declare their test-only eligibility; those fixtures now explicitly set the opt-in in their isolated test environment only.
- Final CI run #646 (`42979897914`) passed Python 3.11 and 3.12: **188 passed per job**, one existing Starlette/httpx TestClient deprecation warning; Ruff, compileall and mypy passed.
- Code/guard commit: `906b9950a64fd2fe3f6b6e0e1e82ab81b3898673`; test-fixture correction head: `2592f13b6dd20f64e6dff868f9227295d2337c62`.
- Latest Preview deployment `dpl_H893y1UtTuvjNiycL5U378Gf83zY` is READY for the test-fixture correction SHA; stable branch alias remains `https://field-shif-git-c9816e-moshiour-rahman-sarkers-projects-2cebe363.vercel.app`.

### Owner action only if eligible

Do not set `FIELD_SHIFT_GEE_NONCOMMERCIAL_CONFIRMED=true` until Google confirms the project is registered for noncommercial use and no paid Cloud products/billing will generate charges. If the project is used commercially/operationally/fee-for-service, leave the flag absent and keep GEE disabled under the strict $0 budget. No payment method or billing plan should be added for this purpose.


---

## 15. Final Production release — 11 November 2026

### GitHub release

- PR #1 merged successfully to `main`: merge commit `1e96de91ba991c6265a9db6956bffedb880115a2`.
- The feature branch was 356 commits ahead and 0 behind the then-current `main`; GitHub reported it mergeable. Latest CI run #648 (`42980311471`) passed Python 3.11 and 3.12: **188 passed per job**, Ruff, compileall and mypy passed (one existing Starlette/httpx deprecation warning).
- PR #2 (SMAP workflow) and PR #3 (weekly POWER refresh workflow) were closed as superseded; both workflow files were already included in PR #1 and are now on `main`.
- The manual POWER historical backfill workflow now accepts `main` as the recommended run branch as well as the retained feature branch. The SMAP workflow has the same branch allowance but remains blocked until the GEE noncommercial opt-in is intentionally confirmed.

### Stable Vercel Production

- Stable public URL: **`https://field-shift0.vercel.app`**.
- Production deployment: `dpl_3VC3cvM2L9YaCSVyYmxwj65b6yez`, source SHA `1e96de91ba991c6265a9db6956bffedb880115a2`, state **READY**.
- SSO protection is now scoped to Preview only; Production is public, while Preview deployments stay protected. No password, custom domain or paid add-on was configured.
- Production Vercel contains `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_ANON_KEY`, `FIELDSHIFT_WORKER_TOKEN`, `FIELD_SHIFT_WORKER_SECRET` and `VERCEL_AUTOMATION_BYPASS_SECRET`. The encrypted worker/auth secrets were moved to Production without reading or printing their values.
- Production reuses the existing single Supabase Free project (`bipyrlegaxmhwzwrmcmi`); no second project was created and no plan/billing change was made. This means Preview and Production use the same Supabase database, with owner isolation enforced by RLS.
- Supabase Vault `fieldshift_worker_url` now points to `https://field-shift0.vercel.app`. The canonical five-minute `fieldshift-analysis-worker` cron remains active. A release smoke tick using the Vault worker token and Vercel bypass secret returned HTTP 200 with `processed=false` because the job queue was empty.
- Production smoke checks returned HTTP 200 for `/`, `/health`, `/api/status`, `/api/auth/config`, `/api/demo` and `/school-game/`. `/api/status` reports email magic-link auth configured, saved runs in Supabase Postgres, durable queue/result storage, Google Drive archive credentials present and Earth Engine not configured. No runtime error clusters were found in the final checked window.

### Remaining owner action: Supabase Auth redirect

The Supabase Management/Auth URL Configuration cannot be edited through the connected Supabase tool. In Supabase Dashboard → Authentication → URL Configuration set:

- **Site URL:** `https://field-shift0.vercel.app`
- **Redirect URL:** `https://field-shift0.vercel.app/**`

Save it, then open the stable Production URL, use the existing email account and request a new sign-in link. Successful callback is confirmed only after `/api/auth/me` validates the session and the page displays the signed-in confirmation / `My Runs`. The existing email is already confirmed; do not create another account. Default Supabase SMTP on Free is testing-only, rate-limited to two messages per hour and restricted to organization-team addresses; no custom SMTP or paid service is configured.

### Remaining data/operator action

- The 2016–2025 POWER daily backfill workflow is now registered on `main`; the Actions connection cannot dispatch workflows, so the owner must run **Backfill nine-region NASA POWER daily history** from Actions with branch `main`, years 2016–2025. The four Google Drive Actions secrets were reported added by the owner; preflight performs the actual credential and Drive verification before data requests.
- Weekly POWER refresh remains disabled until repository variable `GOOGLE_DRIVE_ARCHIVE_ENABLED=true` is set after successful archive preflight. No such variable was set by this release.
- SMAP/GPM/NEX Earth Engine remains disabled in Vercel Production. Do not enable `FIELD_SHIFT_GEE_NONCOMMERCIAL_CONFIRMED=true` until eligible noncommercial/research registration and no paid Google Cloud billing/services are verified. This is intentional under the strict $0 requirement.
- Authenticated sign-in and owner-scoped My Runs still need the human browser acceptance test after the redirect setting is fixed; no user credentials or synthetic analysis rows were created.
- The one shared Free Supabase database means Preview and Production share run storage. The Preview deployment remains behind Vercel SSO; user data remains owner-scoped by RLS.

**Release status:** Production app is live at the stable URL and the durable worker integration is verified. The email redirect dashboard setting and historical data backfill dispatch are the remaining owner actions; do not describe those as completed until their results are observed.
