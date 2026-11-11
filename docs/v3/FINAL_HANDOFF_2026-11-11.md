# KrishiNexus / FieldShift0 — Final Owner Handoff

**Prepared:** 11 November 2026 (Asia/Dhaka)  
**Repository:** `moshiour0/FieldShift0`  
**Working branch:** `feat/krishinexus-real-data-school-lab`  
**PR #1:** [Open · Draft · Unmerged · Mergeable](https://github.com/moshiour0/FieldShift0/pull/1)  
**Validated feature SHA:** `aac5f19f6da71bc7a0d6cf862a56e74e49915cc7`  
**Exact-head Preview:** https://field-shift0-2eee1evuc.vercel.app  
**Preview deployment:** `dpl_FThVJpxo8tKp5GArfnEkDVAH7L3R`  
**Supabase Preview project:** `FieldShift0` · `bipyrlegaxmhwzwrmcmi` · `ap-south-1`  
**Production:** deliberately not promoted; see the separate Production status below.

## 1. Current verification snapshot

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
