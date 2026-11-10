# KrishiNexus / FieldShift0 — Release Handoff

**Prepared:** 2026-11-10 (Asia/Dhaka)  
**Repository:** `moshiour0/FieldShift0`  
**Working branch:** `feat/krishinexus-real-data-school-lab`  
**PR:** [#1 — Draft / Open / Unmerged](https://github.com/moshiour0/FieldShift0/pull/1)  
**Preview:** https://field-shift0-fi04bj7bw.vercel.app  
**Supabase:** FieldShift0 project, ref `bipyrlegaxmhwzwrmcmi`  
**Production:** not promoted by this handoff.

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
- The scheduled job `fieldshift-analysis-worker` is active at `*/5 * * * *`.
- The latest observed cron tick succeeded. Its safe command metadata confirms that it targets the protected worker route and supplies the worker header.
- Analysis/run/source/result/event/job/cache tables currently contain zero records. Therefore the scheduler is proven to tick while idle; no real user run or result-revision lifecycle is yet proven.
- RLS is enabled for the account, result, event, source and private worker/cache tables. The worker role relies on the high-entropy header token and active-lease checks, not a service-role key.

### GitHub, CI and Vercel Preview

- Previous exact-head PR CI run #551 (commit `e1b58614b6a371b27c395b36e1ef8c130eba2132`) succeeded on Python 3.11 and 3.12, including pytest, compileall, Ruff and mypy.
- Exact-head Vercel Preview was READY. `/`, `/health`, `/api/status`, `/api/auth/config`, `/api/regions`, `/api/history/{region}` and `/api/data-status/{region}` passed the checked GET requests.
- Preview runtime error aggregation returned no errors in the checked 24-hour window.
- Configuration metadata says AppEEARS, GEE, Drive and Supabase credentials are present for Preview; this is not credential validation or a successful NASA/GEE/Drive connection test by itself.
- No Production deployment, alias change, billing/plan change or PR merge was performed.

## Remaining acceptance gates

1. Dispatch the **SMAP Reference-Point Backfill** GitHub Actions workflow on this branch for the default 2025–2025 pilot. Confirm preflight, all nine point jobs, exactly 365 daily records per point, both `sm_surface` and `sm_rootzone`, exactly eight 3-hourly intervals per day, full coverage, private Drive read-back and SHA-256 verification. Do not start 2016–2025 until the 2025 pilot passes and runtime/volume are reviewed.
2. Run one real authenticated Preview analysis from a human-controlled test account. Verify queue creation, a worker result revision, source states, My Runs listing, sign-out/sign-in restoration, and reopening after at least one day.
3. Test two separate user accounts and prove cross-account reads/rechecks are rejected by RLS.
4. Validate real AppEEARS task resume and the second-attempt SMAP path. A configured credential flag is not a provider test.
5. Verify the exact NASA POWER archive is actually reused by the processing engine for a reference coordinate/date window; verify an off-anchor coordinate continues to use its own exact point request and never substitutes a reference location.
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
