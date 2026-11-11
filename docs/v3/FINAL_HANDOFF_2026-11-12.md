# KrishiNexus / FieldShift0 — Final Owner Handoff

**Last verified:** 12 November 2026 (Asia/Dhaka)  
**Repository:** `moshiour0/FieldShift0`  
**Production branch:** `main`  
**Latest merged change:** PR #4 — [Supabase egress reduction and Google Drive result archive](https://github.com/moshiour0/FieldShift0/pull/4)  
**Main release SHA:** `15b216b2d8379f4d18ccae0a5603739214e4ffac`  
**Stable Production URL:** https://field-shift0.vercel.app  
**Current Production deployment:** `dpl_2VS5Xh3iBHWx6LrG6ve9w6KquK8h` — READY, exact main SHA above  
**Supabase:** `FieldShift0` · `bipyrlegaxmhwzwrmcmi` · Free plan · ACTIVE_HEALTHY  
**Budget rule:** remain on existing Free/Hobby resources; no paid SMTP, plan upgrade, extra database, or new storage billing.

> **Authority:** This is the current operational handoff as of 12 November 2026. The older [11 November handoff](FINAL_HANDOFF_2026-11-11.md), roadmap checkpoints and earlier release notes are retained as historical records; do not follow their superseded pre-release or Preview-only instructions.

## 1. Release decision

The FieldShift0 application and PR #4's egress/storage changes are merged and live in Production. The current Production deployment is READY on the exact `main` SHA. The core code release is complete.

The project is **not yet fully accepted as an end-to-end live-data service**. A human-controlled Auth redirect check, a real sign-in, a real signed-in analysis, and data-archive completion remain unverified. Do not describe those operator gates as completed.

## 2. Live Production verification

The stable Production alias was checked on 12 November:

| Endpoint | Result | What it proves |
|---|---:|---|
| `GET /` | HTTP 200 | Public application page is served |
| `GET /health` | HTTP 200 | Engine reports `3.0.0`; product reports `3.3.0` |
| `GET /api/status` | HTTP 200 | Integration/configuration status is readable |
| `GET /api/auth/config` | HTTP 200 | Supabase email magic-link configuration is present |

The live `/api/status` response reports:

- Supabase account storage is configured; saved-run metadata and the transactional queue use the existing Supabase Postgres project.
- The result archive provider is private Google Drive; the four Drive variables are configured in Vercel Production.
- `archive_storage.connection_tested=false`. This must remain an explicit **not yet verified** status until a Vercel-hosted signed-in run writes and restores a result successfully.
- NASA POWER live requests are enabled, but `connectivity_tested=false`.
- AppEEARS credentials are configured, but `credentials_validated=false`.
- Earth Engine is not configured in Production. This is intentional under the strict $0 constraint; do not enable it without confirming eligible non-commercial/research use and zero-billing conditions.

A public HTTP 200 or configured credential flag is not proof of a successful upstream provider call.

## 3. PR #4 release contents

PR #4 was merged to `main` as `15b216b2d8379f4d18ccae0a5603739214e4ffac`. Its post-merge GitHub CI run `43022770075` succeeded.

The release includes:

1. Full new signed-in analysis result JSON is written to private Google Drive objects. Supabase stores a compact object pointer, SHA-256 digest and byte count.
2. A restored Drive result is checked against its SHA-256 digest. Historical inline result payloads remain readable; they are not bulk-migrated.
3. Browser polling uses compact owner-scoped run/source status. It no longer downloads full result revisions every poll.
4. A full detail read fetches only the current result revision, then restores its Drive object.
5. The Drive adapter resolves only the requested private object/folder path. Drive is not used as a transactional queue, and files are not made public.
6. The private Drive preflight uses the real adapter's put → get → byte/SHA-256 verification → delete path.

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

The existing Free Supabase project is ACTIVE_HEALTHY and has 26 recorded migrations. A read-only check on 12 November found zero rows in:

- `public.analysis_runs`
- `public.analysis_run_sources`
- `public.analysis_results`
- `public.analysis_run_events`
- `private.analysis_run_jobs`

This means there is no real signed-in analysis run to use as an end-to-end persistence test yet. It does not mean the tables or queue are missing. No synthetic user/run was inserted as part of this handoff.

Supabase Advisor currently reports:

- One warning for `public.request_analysis_run_recheck(uuid)`, an authenticated SECURITY DEFINER RPC. Its owner identity check is intentional. Do not silence the warning by removing the `auth.uid()`/owner check or granting it to `anon`.
- Leaked-password protection is disabled. Enable it in Supabase Auth security settings when practical; this is a security-hardening item, not evidence that magic-link configuration is absent.
- Two worker-queue RLS initialization-plan performance warnings on `private.analysis_run_jobs`. Optimize only through a reviewed migration that preserves worker-token and active-lease checks.

No database migration is required for PR #4's Drive pointer format. Existing inline result payloads remain supported.

## 6. Authentication: remaining owner action

The live app reports Auth configuration present, but a complete browser sign-in has not been confirmed. The Supabase Management/Auth URL Configuration is not writable through the connected project tools.

In Supabase Dashboard → **Authentication → URL Configuration**, set:

- **Site URL:** `https://field-shift0.vercel.app`
- **Redirect URL:** `https://field-shift0.vercel.app/**`

Save the settings. Then open the stable Production URL, use the already-confirmed email account, request a new sign-in link, and click that newest email link. Success is confirmed only when the browser returns to the Production site, `/api/auth/me` validates the bearer session, and the UI switches from **Sign in** to **My Runs**. Do not create another account just to repeat confirmation.

The sign-in UI now tells the user to allow the current site URL rather than referring incorrectly to a Preview URL. The UI text change is included in the final-operations change set.

Supabase's default Free SMTP is testing-only and rate-limited; do not treat it as a public-launch email service. No paid SMTP provider has been configured.

## 7. Data archive status and scientific boundaries

- The nine 2025 NASA POWER reference-point daily archives were previously verified at 365/365 records each with complete coverage and SHA-256 provenance. These are gridded representative-point samples, not field sensors, farm coordinates, district averages or official AEZ means.
- Full daily 2016–2025 coverage across all nine points is **not yet verified**. The 2016–2024 daily backfill must be dispatched and its per-region/per-year output audited before claiming a complete ten-year daily archive.
- SMAP, HLS, MODIS MOD16 and GPM are not yet represented as validated nationwide archives. `not_archived` means no curated archive is available, not zero.
- The 2025 nine-point SMAP pilot has not been proven complete. It must pass its daily interval, band, coverage and private Drive checksum checks before being called complete.
- Earth Engine access remains disabled by default until the owner has explicitly verified eligible non-commercial/research use and no paid Cloud billing/service path. Do not set the GEE opt-in flag just to make a status indicator green.
- Current crop/soil guidance remains a Mymensingh-oriented pilot pending Bangladesh-local crop-calendar, soil, yield/price and field validation with qualified agronomist review. It is not a nationally calibrated agronomy prescription.

## 8. Exact remaining acceptance gates

1. **Auth redirect:** save the two Supabase URL settings above and complete one real Production Magic Link login.
2. **Drive Actions preflight:** after this change is merged, run **Verify Google Drive private archive** on `main`; require `provider=google_drive`, `status=ok`, `round_trip=verified`.
3. **Historical POWER:** run **Backfill nine-region NASA POWER daily history** from GitHub Actions with branch `main`, `start_year=2016`, `end_year=2025`. Confirm all 9×10 annual objects, expected daily counts, checksums and no silently substituted coordinates. A workflow starting is not completion.
4. **First signed-in analysis:** submit one small, controlled analysis from the stable Production URL. Confirm the queue/worker, source states, result revision, private Drive object write/read/SHA-256 verification and My Runs restoration after sign-out/sign-in.
5. **Ownership isolation:** use a second owner-controlled account and confirm it cannot list, read or recheck the first account's run.
6. **Provider acceptance:** validate AppEEARS task creation/resume and any requested satellite provider using actual returned task IDs and evidence. Do not infer live validation from `credentials_configured=true`.

## 9. $0 operating rules

- Keep the current Vercel Hobby and Supabase Free tiers. Do not upgrade plans, buy a domain, or add paid SMTP.
- Do not create another Supabase project or a paid bucket. Keep large result blobs and curated data in the private Google Drive archive.
- Do not pause, delete or disconnect any other project as a way to address an organization-level usage graph.
- Do not enable Earth Engine or paid Cloud products without explicit zero-cost eligibility verification.
- Never put OAuth tokens, Google Drive folder IDs, worker secrets, Supabase service-role keys or email credentials in source control, public logs or chat.
- Do not label an untested provider, data source or login path as complete.

**Final status:** Production code release is complete and healthy. Operational acceptance is intentionally left open only for the human Auth setting/login, independent Drive checks, real signed-in run, provider verification and historical-data backfill listed above.
