# KrishiNexus / FieldShift0 — Release Handoff

**Prepared:** 2026-11-10 (Asia/Dhaka)  
**Repository:** `moshiour0/FieldShift0`  
**Working branch:** `feat/krishinexus-real-data-school-lab`  
**PR:** [#1 — Draft / Open / Unmerged](https://github.com/moshiour0/FieldShift0/pull/1)  
**Latest exact-head Preview:** https://field-shift0-fce6othm3.vercel.app  
**Runtime-code Preview:** https://field-shift0-nttj3iysm.vercel.app  
**Supabase:** FieldShift0 project, ref `bipyrlegaxmhwzwrmcmi`  
**Production:** not promoted by this handoff.

## Latest verification snapshot — 2026-11-10 16:46 UTC

- Current validated code commit: `75a276cadc6d2f9fe1135afa6829162d2f76e9a5`; PR #1 remains Open / Draft / Unmerged.
- Exact-code GitHub Actions push run #582 (`42857786427`) passed on Python 3.11 and 3.12: **184 passed, 1 existing Starlette/httpx TestClient deprecation warning per job**. `compileall`, strict Ruff and mypy all passed on both versions.
- Exact-code Vercel Preview is READY: `https://field-shift0-hxweuo20n.vercel.app`, deployment `dpl_FVpgUfPKPgMC2M2Rtn59FQTZtkSY`, source SHA equals the code commit above.
- Exact-code smoke checks: `/health` HTTP 200 (`engine=3.0.0`, `product=3.3.0`); `/api/status` HTTP 200; `/api/auth/config` HTTP 200 (`configured=true`, `email_magic_link`). The status endpoint now correctly reports `active_execution_durable_across_instances=true` when either supported worker-token setting is configured with at least 48 characters.
- Worker-token resolution is now centralised in `analysis_worker.configured_worker_token()`. Worker execution (`_settings`), the internal tick route (which constant-time compares both supported token aliases) and `/api/status` use compatible fallback semantics. A regression test proves that a valid `FIELD_SHIFT_WORKER_SECRET` fallback activates the status flag even when `FIELDSHIFT_WORKER_TOKEN` is blank, and that a too-short fallback does not.
- Public `GET /api/analysis/demo_mymensingh_v3` remains HTTP 200 with eight demo strategies. Public run-ID GETs for live analysis, strategies, scenarios, evidence and report return HTTP 404. Live analysis results are no longer retained in the process-global `_RUNS` dictionary; non-demo what-if uses only the caller-supplied field snapshot.
- 2025 NASA POWER history remains readable as complete daily data (365/365, coverage 1.0, SHA-256 provenance) for all nine representative reference points. SMAP, HLS, MODIS MOD16 and GPM remain `not_archived`; full 2016–2025 daily coverage is not claimed.
- Supabase `FieldShift0` is `ACTIVE_HEALTHY`; exactly one `fieldshift-analysis-worker` cron is active at `*/5 * * * *`. Latest observed tick succeeded at 16:45 UTC while idle. The account/run/source/result/event/job/cache/profile tables remain empty, so no real user job/revision lifecycle is proven.
- Preview status still says Drive `connection_tested=false`, AppEEARS/GEE `credentials_validated=false`, and POWER `connectivity_tested=false`. No live provider ingestion or Google Drive write/read-back round-trip is claimed complete.
- PR #2 is the one-file Draft workflow registration for the 2025 SMAP pilot; PR #3 is the one-file Draft registration for weekly POWER YTD refresh. Both remain Open/Unmerged; merging either workflow-only PR may trigger a Vercel Production redeploy from unchanged app code. Review before merge.
- No PR merge, Production promotion, Production environment edit, alias/domain change, billing/plan change, Supabase mutation or provider account ownership transfer was performed.

## What is delivered in the codebase

- FieldShift V3.3 crop-rotation decision engine with water conservation accounting, soil nutrient unit conversion, a multi-year SOC proxy, fixed agronomic score scales, input-level Monte Carlo uncertainty and farmer operational constraints.
- NASA POWER daily weather; AppEEARS adapters for SMAP, HLS and MODIS MOD16; GPM IMERG and NEX-GDDP-CMIP6 Google Earth Engine adapters; optional SoilGrids and farmer-entered soil evidence.
- Evidence/provenance reporting, regional history explorer, responsive farmer workflow and Bengali Learning Lab.
- Supabase Auth, user-scoped saved runs, immutable request snapshots, source-state rows, versioned results, lifecycle events, token-scoped worker queue and manual owner recheck. Live run results are not exposed by public run-ID GET routes or retained in a process-global cache; authenticated owners use the My Runs endpoints.
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

1. **SMAP 2025 reference-point pilot:** The workflow file is currently absent from `main`; GitHub only exposes a `workflow_dispatch` workflow when the file exists on the default branch. Separate one-file Draft [PR #2](https://github.com/moshiour0/FieldShift0/pull/2) registers `.github/workflows/smap-reference-backfill.yml`. After explicit approval/merge of PR #2, open Actions → **Backfill nine-reference-point NASA SMAP archive**, select branch `feat/krishinexus-real-data-school-lab`, and keep `start_year=2025`, `end_year=2025`. The workflow then uses the scripts/adapters from PR #1's branch. Require the preflight, all nine point jobs, exactly 365 daily records per point, both `sm_surface` and `sm_rootzone`, exactly eight 3-hourly intervals per day, full coverage, private Drive read-back and SHA-256 verification. Do not start 2016–2025 until the 2025 pilot passes and runtime/volume are reviewed. Merging PR #2 may trigger a Vercel Production redeploy from unchanged application code; review that side effect first.
2. Run one real authenticated Preview analysis from a human-controlled test account. Verify queue creation, a worker result revision, source states, My Runs listing, sign-out/sign-in restoration, and reopening after at least one day.
3. Test two separate user accounts and prove cross-account reads/rechecks are rejected by RLS.
4. Validate real AppEEARS task resume and the second-attempt SMAP path. A configured credential flag is not a provider test.
5. The archive-first POWER baseline is now wired into the processing engine and covered by tests that require a verified exact-coordinate archive hit and prevent off-anchor reference-point substitution. Still perform a real authenticated Preview analysis to demonstrate this route end-to-end for a user request.
6. Complete Bangladesh agronomic calibration with local crop calendars, field-measured soils, yield/price evidence and independent agronomist review. The current crop/soil scoring pack remains a Mymensingh pilot.
7. Review the outstanding Supabase advisor warnings: the owner-scoped `SECURITY DEFINER` manual recheck RPC is intentional (it checks `auth.uid()`, locks the caller's run, and is not executable by anon); the private worker RLS performance warning should be rechecked after policy changes and not “fixed” by weakening token checks.
8. Before Production release, separately review the exact PR head, final CI, authenticated user acceptance evidence, Supabase Production migration state, Production-only environment configuration, auth redirect allowlist, worker schedule/secret, and Vercel Production build. Obtain explicit release approval before merging or promoting.

## Operator runbook

### Manual SMAP 2025 pilot

1. Confirm separate one-file PR #2 has been approved and merged so the workflow file exists on `main`. This is not approval to merge PR #1. Review first: a main commit may trigger Vercel Production redeployment even though application code is unchanged.
2. GitHub → Actions → **Backfill nine-reference-point NASA SMAP archive**.
3. Select branch `feat/krishinexus-real-data-school-lab` so the complete workflow/scripts/adapters from PR #1's feature branch are used.
4. Keep `start_year=2025` and `end_year=2025` for the first pilot.
5. Run once. Drive temporary write/read/delete and Earth Engine asset-visibility preflight must pass before SMAP daily ingestion begins.
6. Review all nine region jobs and the final workflow conclusion. A green workflow with an incomplete region is not accepted. Require 365 daily rows, 8/8 intervals for both SMAP bands, complete coverage, private Drive remote bytes/read-back and SHA-256 verification.

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
