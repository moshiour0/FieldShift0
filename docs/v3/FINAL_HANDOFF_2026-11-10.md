# KrishiNexus / FieldShift0 — Release Handoff

**Prepared:** 2026-11-10 (Asia/Dhaka)  
**Repository:** `moshiour0/FieldShift0`  
**Working branch:** `feat/krishinexus-real-data-school-lab`  
**PR:** [#1 — Draft / Open / Unmerged](https://github.com/moshiour0/FieldShift0/pull/1)  
**Latest exact-head Preview:** https://field-shift0-hbmuwnxdu.vercel.app  
**Runtime-code Preview:** https://field-shift0-nttj3iysm.vercel.app  
**Supabase:** FieldShift0 project, ref `bipyrlegaxmhwzwrmcmi`  
**Production:** not promoted by this handoff.

## Latest verification snapshot — 2026-11-10 15:40 UTC

- Current PR head: `f4417bf5107d001fac848d549e709b620eda66c5`. Its latest commit updates handoff documentation; runtime code is at `f2baa301dc30fbe6dc71d7076a41a30336b57b76`.
- Exact-head GitHub Actions PR run #562 (`42846659223`) succeeded on Python 3.11 and 3.12: **178 passed, 1 non-blocking warning** in each job. `compileall`, strict Ruff and mypy (34 source files) passed in both jobs.
- Exact-head Vercel Preview is READY: `https://field-shift0-hbmuwnxdu.vercel.app`, deployment `dpl_U5ppyfczeMtA7PKdDch7WNbuPvRo`, source SHA equals the current PR head. The latest runtime-code Preview is READY at `https://field-shift0-nttj3iysm.vercel.app`, deployment `dpl_5La2bQJp5nusHheaJTAUgW99ns27`, source SHA `f2baa301dc30fbe6dc71d7076a41a30336b57b76`.
- Exact-head GET checks: `/` HTTP 200, `/health` HTTP 200 (`engine=3.0.0`, `product=3.3.0`), `/api/status` HTTP 200, `/api/auth/config` HTTP 200 with `configured=true` and `email_magic_link`, `/api/regions` returned 12 planning groups and 9 reference points, and `/school-game/` served the Bengali Learning Lab.
- Full-year `/api/history/{region}` checks on the exact-head Preview for 2025 succeeded for all nine reference coordinates: daily representation, 365/365 records, `coverage_fraction=1.0`, no missing years and SHA-256 provenance. These are gridded reference-point samples—not farm sensors, district averages, official AEZ means or arbitrary-coordinate data.
- All nine `/api/data-status/{region}` results report NASA POWER `ready` through 2025-12-31. The same nine points report SMAP, HLS, MODIS MOD16 and GPM as `not_archived`. The Mymensingh 2016–2025 monthly history remains chart-only; a complete 2016–2025 daily archive is not claimed.
- The exact-coordinate POWER archive-first integration is in runtime commit `5c3040c` and has tests for checksum validation, exact-coordinate-only reuse, live fallback and no off-anchor reference-point substitution. Latest CI verifies these tests. An authenticated user-request exercise of that pipeline has not yet been performed.
- Supabase `FieldShift0` is `ACTIVE_HEALTHY`, with 23 migrations. Exactly one `fieldshift-analysis-worker` cron is active at `*/5 * * * *`. Latest `net._http_response` records show HTTP 200, `processed=false`, and “No queued analysis job is ready.” This proves a healthy idle worker tick—not a completed user job.
- The account/run/source/result/event/job/cache/profile tables contain zero records. No real signed-in user run, saved result revision or one-/two-day account restoration has been proven.
- Supabase security advisor still reports one intentional owner-scoped `SECURITY DEFINER` recheck RPC warning, plus two private queue RLS performance warnings. Do not remove owner checks or weaken worker-token policies just to silence the advisor. Four unused-index informational findings are not a reason to drop indexes on an empty database.
- Preview runtime error aggregation returned no errors in the checked one-hour window.
- Preview environment metadata confirms the worker token is stored as a non-readable Sensitive variable; Google Drive, AppEEARS, GEE and Supabase settings are present. Their presence is not a provider connection/credential validation: `/api/status` reports Drive `connection_tested=false`, AppEEARS/GEE `credentials_validated=false`, and POWER `connectivity_tested=false`.
- No PR merge, Production promotion, Production environment edit, domain/alias change, billing/plan change, or account ownership transfer was performed.

## What is delivered in the codebase

- FieldShift V3.3 crop-rotation decision engine with water conservation accounting, soil nutrient unit conversion, a multi-year SOC proxy, fixed agronomic score scales, input-level Monte Carlo uncertainty and farmer operational constraints.
- NASA POWER daily weather; AppEEARS adapters for SMAP, HLS and MODIS MOD16; GPM IMERG and NEX-GDDP-CMIP6 Google Earth Engine adapters; optional SoilGrids and farmer-entered soil evidence.
- Evidence/provenance reporting, regional history explorer, responsive farmer workflow and Bengali Learning Lab.
- Supabase Auth, user-scoped saved runs, immutable request snapshots, source-state rows, versioned results, lifecycle events, token-scoped worker queue and manual owner recheck.
- Supabase scheduled worker tick every five minutes; Google Drive private archive support; GitHub Actions workflows for POWER history and the SMAP reference-point pilot.

## Verified data and deployment evidence

### NASA POWER — nine reference points

The exact-head Preview was queried on 2026-11-10 for the full calendar year 2025 at all nine configured representative coordinates. Every region returned:

- `status=complete`
- `archive_representation=daily`
- `coverage_fraction=1.0`
- `available_days=365`, `expected_days=365`
- empty `missing_years`
- NASA POWER provenance and an embedded SHA-256 value.

The nine 2025 files report archive timestamps on 2026-11-09. This verifies the API's read path and full-year archive integrity for those nine exact reference points. They are gridded reference-point samples, not field measurements, area averages, official AEZ averages or arbitrary farm coordinates.

### Satellite archive boundary

The same Preview reports SMAP, HLS, MODIS MOD16 and GPM as `not_archived` for all nine regional points. The SMAP point-cache writer and manual nine-point prefetch workflow are implemented, but the actual 2025 SMAP pilot has not been dispatched and verified. No nationwide gridded SMAP archive exists.

### Supabase persistence and worker

- The FieldShift Supabase project is `ACTIVE_HEALTHY`; 23 migrations are recorded.
- The scheduled job `fieldshift-analysis-worker` is active at `*/5 * * * *` and the latest observed run succeeded at 15:30 UTC.
- Its safe command metadata confirms that it targets the protected worker route and supplies the worker header.
- Analysis/run/source/result/event/job/cache/profile tables currently contain zero records. Therefore the scheduler is proven to tick while idle; no real user run or result-revision lifecycle is yet proven.
- RLS is enabled for the account, result, event, source and private worker/cache tables. The worker role relies on the high-entropy header token and active-lease checks, not a service-role key.

### GitHub, CI and Vercel Preview

- Current exact-head PR CI run #555 (`42844515648`) succeeded on Python 3.11 and 3.12: 177 tests passed in each job, plus compileall, Ruff and mypy.
- Exact-head READY Preview: `https://field-shift0-4xuq3ds53.vercel.app` (`dpl_AjG39xBNaj4LpuojpZjG87rucf3F`, SHA `0d3546d091e9c7e4e4d3da003577655709f52e84`). Checked GET routes: `/`, `/health`, `/api/status`, `/api/auth/config`, `/api/regions`, and the 2025 full-year history endpoint for all nine reference coordinates.
- Preview runtime error aggregation returned no errors in the checked one-hour window.
- The data-history GET checks prove that the nine 2025 annual objects are readable through the configured archive path. They do not prove a Drive write/read-back roundtrip, which remains a separate gate for the SMAP preflight.
- Preview metadata shows Drive, AppEEARS, GEE and Supabase settings are configured. AppEEARS/GEE credentials are not provider-validated merely because they are configured. No actual 2025 SMAP backfill is claimed.
- No Production deployment, alias change, billing/plan change or PR merge was performed.

## Remaining acceptance gates

1. Dispatch the **SMAP Reference-Point Backfill** GitHub Actions workflow on this branch for the default 2025–2025 pilot. Confirm preflight, all nine point jobs, exactly 365 daily records per point, both `sm_surface` and `sm_rootzone`, exactly eight 3-hourly intervals per day, full coverage, private Drive read-back and SHA-256 verification. Do not start 2016–2025 until the 2025 pilot passes and runtime/volume are reviewed.
2. Run one real authenticated Preview analysis from a human-controlled test account. Verify queue creation, a worker result revision, source states, My Runs listing, sign-out/sign-in restoration, and reopening after at least one day.
3. Test two separate user accounts and prove cross-account reads/rechecks are rejected by RLS.
4. Validate real AppEEARS task resume and the second-attempt SMAP path. A configured credential flag is not a provider test.
5. The archive-first POWER baseline is now wired into the processing engine and covered by tests that require a verified exact-coordinate archive hit and prevent off-anchor reference-point substitution. Still perform a real authenticated Preview analysis to demonstrate this route end-to-end for a user request.
6. Complete Bangladesh agronomic calibration with local crop calendars, field-measured soils, yield/price evidence and independent agronomist review. The current crop/soil scoring pack remains a Mymensingh pilot.
7. Review the outstanding Supabase advisor warnings: the owner-scoped `SECURITY DEFINER` manual recheck RPC is intentional (it checks `auth.uid()`, locks the caller's run, and is not executable by anon); the private worker RLS performance warning should be rechecked after policy changes and not “fixed” by weakening token checks.
8. Before Production release, separately review the exact PR head, final CI, authenticated user acceptance evidence, Supabase Production migration state, Production-only environment configuration, auth redirect allowlist, worker schedule/secret, and Vercel Production build. Obtain explicit release approval before merging or promoting.

## Operator runbook

### Manual SMAP 2025 pilot

1. GitHub → Actions → **SMAP Reference-Point Backfill**.
2. Select branch `feat/krishinexus-real-data-school-lab`.
3. Keep `start_year=2025` and `end_year=2025`.
4. Run once. Preflight must pass before GEE or Drive ingestion.
5. Review all nine region jobs and the final workflow conclusion. A green workflow with an incomplete region is not accepted.
6. Confirm the archive object count, QA gates, and remote bytes/checksum verification before proceeding.

### User acceptance test in Preview

1. Open the Preview URL and choose **Sign in**.
2. Complete the email magic-link callback using a test account owned by the project operator.
3. Submit a small historical analysis request for an exact 2025 date window.
4. Confirm the run appears in **My Runs**; inspect its original request, source statuses and revision.
5. Close the page, reopen the Preview and sign in again. Confirm the same run and latest revision return.
6. Repeat with a second account and confirm it cannot read or recheck the first account's run.

## Important scientific boundaries

- `final_ready` means configured/requested inputs passed the product's readiness policy, not independent field validation.
- POWER is a gridded point estimate, not a field sensor.
- SMAP/HLS/MODIS/GPM coverage is source- and product-specific; not_archived is not zero.
- NEX-GDDP-CMIP6 is a modeled climate-signal path, not an operational daily forecast.
- SoilGrids is modeled soil evidence; farmer/lab soil results must retain their own provenance.
- The crop/soil pack is a Mymensingh pilot, not nationwide calibrated agronomy.
- NASA does not endorse KrishiNexus.

## Project ownership and handover

The GitHub repository and Vercel/Supabase projects remain in the owner's accounts. The branch and PR provide the full code review trail. No account ownership, billing, domain, OAuth owner, GitHub organization, or cloud project ownership was changed by this work. For a true access transfer to another operator, add that person to GitHub, Vercel, Supabase and the Google account/Drive folder using each provider's own access controls; never share secret values in chat or commit them to Git.
