# KrishiNexus / FieldShift0 — Final Owner Handoff

**Last verified:** 12 November 2026 (Asia/Dhaka)  
**Repository:** `moshiour0/FieldShift0`  
**Production branch:** `main`  
**Latest merged change:** PR #6 — [Fix FieldShift result loading and preserve field inputs](https://github.com/moshiour0/FieldShift0/pull/6)  
**Main release SHA:** `456ef50920b6c0518d536becea042aa19d32acbe`  
**Stable Production URL:** https://field-shift0.vercel.app  
**Current Production deployment:** `dpl_ABfXZhQpny7UkxfBvcpWGs4CsPJb` — READY, exact main SHA above  
**Supabase:** `FieldShift0` · `bipyrlegaxmhwzwrmcmi` · Free plan · ACTIVE_HEALTHY  
**Budget rule:** remain on existing Free/Hobby resources; no paid SMTP, plan upgrade, extra database, or new storage billing.

> **Authority:** This is the current operational handoff as of 12 November 2026. The older [11 November handoff](FINAL_HANDOFF_2026-11-11.md), roadmap checkpoints and earlier release notes are retained as historical records; do not follow their superseded pre-release or Preview-only instructions.

## 1. Release decision

The FieldShift0 application, PR #4's egress/storage changes, and PR #6's result-pointer/field-input repairs are merged and live in Production. The current Production deployment is READY on exact `main` SHA `456ef50920b6c0518d536becea042aa19d32acbe`.

The project is **not yet fully accepted as an end-to-end live-data service or field-validated agronomy product**. Two authenticated runs and their preliminary result revisions now exist, and their latest-result pointers are consistent. The runs are still waiting for provider data; a full Drive result restore after a fresh sign-in, national data archive completion, and agronomic field validation remain open. Do not describe those gates as complete.

## 2. Live Production verification

The stable Production alias was checked after PR #6 was merged on 12 November:

| Endpoint | Result | What it proves |
|---|---:|---|
| `GET /` | HTTP 200 | Public application page is served |
| `GET /health` | HTTP 200 | Engine reports `3.0.0`; product reports `3.3.0` |
| `GET /api/status` | HTTP 200 | Integration/configuration status is readable |
| `GET /api/auth/config` | HTTP 200 | Supabase email magic-link configuration is present |
| `GET /api/v3/config` | HTTP 200 | V3 model weights are readable |
| `GET /api/v3/demo` | HTTP 200 | Live engine endpoint responds; provider-specific data validation remains separate |
| `GET /api/regions` | HTTP 200 | Region catalogue is readable; zones remain provisional, without official polygons |
| `GET /school-game/` | HTTP 200 | School learning experience is served |
| `GET /static/history.html` | HTTP 200 | Regional evidence explorer is served |

The live `/api/status` response reports:

- Supabase account storage is configured; saved-run metadata and the transactional queue use the existing Supabase Postgres project.
- The result archive provider is private Google Drive; the four Drive variables are configured in Vercel Production.
- `archive_storage.connection_tested=false`. This must remain an explicit **not yet verified** status until a Vercel-hosted signed-in run writes and restores a result successfully.
- NASA POWER live requests are enabled, but `connectivity_tested=false`.
- AppEEARS credentials are configured, but `credentials_validated=false`.
- Earth Engine is not configured in Production. This is intentional under the strict $0 constraint; do not enable it without confirming eligible non-commercial/research use and zero-billing conditions.

A public HTTP 200 or configured credential flag is not proof of a successful upstream provider call.

## 3. PR #4 and PR #6 release contents

PR #4 was merged to `main` as `15b216b2d8379f4d18ccae0a5603739214e4ffac`; its post-merge CI run succeeded. PR #6 was merged as `456ef50920b6c0518d536becea042aa19d32acbe`; both Python 3.11 and 3.12 CI jobs succeeded (run `43111044356`).

The PR #4 storage release includes:

1. Full new signed-in analysis result JSON is written to private Google Drive objects. Supabase stores a compact object pointer, SHA-256 digest and byte count.
2. A restored Drive result is checked against its SHA-256 digest. Historical inline result payloads remain readable; they are not bulk-migrated.
3. Browser polling uses compact owner-scoped run/source status. It no longer downloads full result revisions every poll.
4. A full detail read fetches only the current result revision, then restores its Drive object.
5. The Drive adapter resolves only the requested private object/folder path. Drive is not used as a transactional queue, and files are not made public.
6. The private Drive preflight uses the real adapter's put → get → byte/SHA-256 verification → delete path.

PR #6 adds:

1. A private `analysis_results` insert trigger keeps `analysis_runs.latest_result_id` synchronized with the current immutable revision. The migration also repairs existing rows with a missing pointer.
2. Farmer-drawn field boundary geometry is persisted and validated as latitude/longitude vertices.
3. The field-centre query location is aligned to the drawn polygon centroid; the UI labels the current satellite extraction as centre-point sampling, not a polygon-wide field average.
4. Initial demo loading no longer resets the user's live field form inputs; queued-run summaries echo the submitted coordinate, area, date window, irrigation reliability and boundary state.
5. The SMAP routing keeps Google Drive cache reads distinct from Earth Engine credentials and allows AppEEARS fallback when GEE is not configured.

The PR's GitHub Actions private Drive preflight passed with the four repository secrets. That proves the GitHub Actions credential set and private folder supported the test at that time. It does **not** prove that the separately configured Vercel Production credentials have completed a round-trip.

## 4. New operator-safe Drive preflight

This change adds a dedicated workflow named **Verify Google Drive private archive**:

- It is manually dispatched from the `main` branch in GitHub Actions.
- It checks that all four existing repository secrets are present without printing their values.
- It writes a uniquely named temporary probe object to the private Drive folder, reads it back, verifies the exact bytes and SHA-256 digest, and deletes the probe.
- It makes no NASA POWER, AppEEARS, SMAP, HLS, MODIS or GPM data request.
- It does not create a Supabase row or start an analysis.

Use this workflow to verify the GitHub Actions Drive credential set. Do **not** manually dispatch **Publish quality-gated NASA POWER archive** merely to test Drive connectivity: that workflow continues into data ingestion after its preflight.

## 5. Supabase state and security

The existing Free Supabase project is ACTIVE_HEALTHY and has **27 recorded migrations**. Two real authenticated runs now exist. A read-only check after PR #6 found:

| Table | Rows |
|---|---:|
| `public.analysis_runs` | 2 |
| `public.analysis_run_sources` | 24 |
| `public.analysis_results` | 9 |
| `public.analysis_run_events` | 9 |
| `private.analysis_run_jobs` | 2 |

Both runs have a non-null `latest_result_id` that points to the current result revision; the mismatch count is **0**. This verifies the result-pointer repair against real run rows. No synthetic user/run was inserted.

Both runs remain `preliminary_ready` at `waiting_for_datasets` with jobs `retrying` because provider evidence is incomplete. The cron worker has been running successfully, but those runs are not final results.

Supabase Advisor currently reports:

- One warning for `public.request_analysis_run_recheck(uuid)`, an authenticated SECURITY DEFINER RPC. Its owner identity check is intentional. Do not silence the warning by removing the `auth.uid()`/owner check or granting it to `anon`.
- Leaked-password protection is disabled. Enable it in Supabase Auth security settings when practical; this is a security-hardening item, not evidence that magic-link configuration is absent.
- Two worker-queue RLS initialization-plan performance warnings on `private.analysis_run_jobs`. Optimize only through a reviewed migration that preserves worker-token and active-lease checks.

PR #6's pointer synchronization migration is present in the migration history as `sync_latest_analysis_result_pointer`. Existing inline result payloads remain supported. The Drive result archive still needs a real signed-in write/read/SHA-256 restore test.

## 6. Authentication: remaining owner action

The live app reports Auth configuration present, and the two persisted analysis runs prove that authenticated requests have reached the owner-scoped queue. A fresh browser session, sign-out/sign-in continuity and My Runs restore have not yet been independently verified. Supabase Auth URL Configuration is not writable through the connected project tools.

In Supabase Dashboard → **Authentication → URL Configuration**, set:

- **Site URL:** `https://field-shift0.vercel.app`
- **Redirect URL:** `https://field-shift0.vercel.app/**`

Only change these settings if they are not already saved. Then open the stable Production URL, use the existing confirmed email account, request a new sign-in link and click the newest link. Verify `/api/auth/me` returns the authenticated user and the UI switches from **Sign in** to **My Runs**. Finally, reopen one of the existing runs after a fresh session. Do not create another account just to repeat confirmation.

The sign-in UI tells the user to allow the current site URL rather than referring incorrectly to a Preview URL. The current redirect value sent by the form is the Production page origin/path.

Supabase's default Free SMTP is testing-only and rate-limited; do not treat it as a public-launch email service. No paid SMTP provider has been configured.

## 7. Data archive status and scientific boundaries

- The nine 2025 NASA POWER reference-point daily archives were previously verified at 365/365 records each with complete coverage and SHA-256 provenance. These are gridded representative-point samples, not field sensors, farm coordinates, district averages or official AEZ means.
- Full daily 2016–2025 coverage across all nine points is **not yet verified**. The 2016–2024 daily backfill must be dispatched and its per-region/per-year output audited before claiming a complete ten-year daily archive.
- A real point analysis returned NASA POWER and SMAP daily observations plus HLS-VI observation dates, with some satellite cache objects stored in private Drive and SHA-256 verified. This is one point/time-window result, not a nationwide archive.
- MODIS MOD16 returned no usable values after QA for that run; GPM was not configured; NEX-GDDP-CMIP6 projections were not available and its displayed scenarios remain labelled diagnostic stress tests; SoilGrids remained disabled.
- A production audit found HLS-VI values outside the documented physical NDVI/EVI/NDMI range. The HLS parser/cache-version correction is being validated in the open follow-up PR; do not use previously cached HLS means as trusted measurements until that correction is deployed and a new sample is verified.
- SMAP L4 values are assimilated geophysical estimates, not in-situ field moisture measurements. NASA POWER, SMAP and HLS outputs are centre-point samples at their native spatial/temporal support; they are not polygon-wide field averages.
- Earth Engine access remains disabled by default until the owner has explicitly verified eligible non-commercial/research use and no paid Cloud billing/service path. Do not set the GEE opt-in flag just to make a status indicator green.
- Current crop/soil guidance remains a Mymensingh-oriented pilot pending Bangladesh-local crop-calendar, soil, yield/price and field validation with qualified agronomist review. It is not a nationally calibrated agronomy prescription.

## 8. Exact remaining acceptance gates

1. **HLS correction:** merge the HLS scale/range/cache-invalidation fix only after CI passes; deploy it and verify a new sample has NDVI/EVI/NDMI within `[-1, 1]` or is reported missing.
2. **Authenticated continuity and result restore:** complete a fresh Production sign-in, reopen an existing run, and verify that the full result is restored from private Google Drive with byte-count/SHA-256 checks.
3. **Historical POWER:** run **Backfill nine-region NASA POWER daily history** from GitHub Actions with branch `main`, `start_year=2016`, `end_year=2025`. Confirm all 9×10 annual objects, expected daily counts, checksums and no silently substituted coordinates. A workflow starting is not completion.
4. **Auth settings:** verify Supabase Site URL and exact Production Redirect URL are saved; do not create a new account or change working settings unnecessarily.
5. **Ownership isolation:** use a second owner-controlled account and confirm it cannot list, read or recheck the first account's run.
6. **Provider acceptance:** validate AppEEARS task creation/resume and each requested satellite provider using actual returned task IDs, product version, QA, date coverage and private cache integrity. Do not infer live validation from `credentials_configured=true`.
7. **Agronomic validation:** attach locally sourced crop-calendar/yield/price and field soil observations, then validate against an independent holdout season/field before presenting the rankings as locally calibrated recommendations.

## 9. $0 operating rules

- Keep the current Vercel Hobby and Supabase Free tiers. Do not upgrade plans, buy a domain, or add paid SMTP.
- Do not create another Supabase project or a paid bucket. Keep large result blobs and curated data in the private Google Drive archive.
- Do not pause, delete or disconnect any other project as a way to address an organization-level usage graph.
- Do not enable Earth Engine or paid Cloud products without explicit zero-cost eligibility verification.
- Never put OAuth tokens, Google Drive folder IDs, worker secrets, Supabase service-role keys or email credentials in source control, public logs or chat.
- Do not label an untested provider, data source or login path as complete.

**Final status:** Production code release PR #6 is merged and READY. Two authenticated runs and their current-result pointers are persisted correctly, but provider retries remain pending and HLS-VI scaling has a follow-up correction in validation. Full operational and scientific acceptance is still open for HLS redeployment/re-sampling, fresh-session result restoration, historical backfill, provider coverage, ownership isolation and Bangladesh field/a​​gronomic validation. See [NASA Space Apps Challenge Readiness Audit](CHALLENGE_READINESS_AUDIT_2026-11-12.md) for the evidence gates.
