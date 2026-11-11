# Data Foundation Operations

This runbook describes the reproducible NASA POWER daily point archive for the nine configured Bangladesh reference points. It does not claim official AEZ zonal coverage, farm-level measurements, or satellite-product coverage.

## Owner handoff checkpoint — 11 November 2026

- Authoritative release record: [Final Owner Handoff](v3/FINAL_HANDOFF_2026-11-11.md).
- Current reviewed feature head `9adacb90cf06d2745226b39096bd46fe46de3ac4`; exact Preview `https://field-shift0-e4qwww1wl.vercel.app` (READY, matching Git SHA).
- Latest runtime-correction CI #619 passed Python 3.11/3.12: 187 tests each, one existing Starlette/httpx deprecation warning, Ruff, compileall and mypy. Subsequent documentation/operations CI #636 also passed both Python versions. Workflow actions are pinned to immutable current Node 24 release commits.
- 2025 NASA POWER is already complete and readable for all nine reference points (365/365, coverage 1.0, SHA-256). Years 2016–2024 are not yet proven daily.
- SMAP/HLS/MODIS MOD16/GPM remain `not_archived`; the 2025 SMAP pilot is not yet run.
- [PR #2](https://github.com/moshiour0/FieldShift0/pull/2) registers only the manual SMAP workflow; [PR #3](https://github.com/moshiour0/FieldShift0/pull/3) registers only weekly POWER refresh. Both remain Draft/Open/Unmerged. Workflow-only merges may trigger a Production redeploy because Vercel is connected to `main`.
- Preview Supabase has 24 migrations. Worker lease/audit ordering and failure-path fixes are applied as `20261111040447_worker_event_before_lease_release_v2` and `20261111050822_worker_fail_event_before_lease_release`. A later full-function replacement had regressed optional-pending status; `20261111052954_worker_preserve_preliminary_status_with_active_lease` now restores `preliminary_ready` while retaining event-before-lease-release. The active worker cron returns successful idle ticks; no real user job is present. All seven checked account/run/source/result/event/job/cache/profile tables remain empty, so live owner-account acceptance remains outstanding.
- Production is still on product 3.1.3 and reports `process_memory`; the durable Supabase/Auth/worker configuration is Preview-only. Do not promote until the separate Production migration/environment and human account acceptance gates pass.


## Current verified state — 10 November 2026

- The exact-head Preview returned complete NASA POWER daily history for **all nine reference points** over 2025-01-01 through 2025-12-31: 365/365 days, coverage 1.0, no missing dates and SHA-256 provenance.
- The daily annual files are read through the configured private Google Drive path. The repository only bundles the older Mymensingh monthly summaries, so these API daily reads demonstrate that the remote object read path is working. This does not prove a new upload/write-back; the separate SMAP preflight performs its own temporary Drive write/read/delete test.
- Years 2016–2024 are not yet verified as daily archives. The bundled Mymensingh 2016–2025 monthly aggregates remain chart-only.
- The manual POWER workflow file `.github/workflows/history-backfill.yml` already exists on `main`, so it can be dispatched and run against the feature branch.
- The weekly refresh workflow and SMAP workflow currently exist only on the feature branch, not `main`. Scheduled events and `workflow_dispatch` only run after the corresponding workflow file is present on the default branch. PR #2 registers the SMAP workflow as a separate one-file Draft PR; do not merge it without reviewing the possible Vercel Production redeploy.
- PR #1 remains Draft/Open/Unmerged. No Production deployment or promotion is authorized by this runbook.


## Storage design

The durable archive provider is a private Google Drive folder. GitHub Actions fetches and quality-checks NASA POWER daily data, then stores versioned JSON objects through the Google Drive API. The Vercel API reads the same files and validates their embedded SHA-256 digest before using them.

Canonical Drive layout:

`FieldShift0 Archive/power-history/{region_id}/{year}.json`

Current-year partial archives use:

`FieldShift0 Archive/power-history/{region_id}/{year}-ytd.json`

The root folder is created by the one-time OAuth bootstrap script. The archive is private; do not enable link sharing or public access.

## One-time Google Cloud setup

1. Open Google Cloud Console and create or select a dedicated project for FieldShift0.
2. Enable **Google Drive API**.
3. Configure Google Auth Platform / OAuth consent:
   - User type: External (unless this belongs to a Google Workspace organization and is Internal).
   - App name: FieldShift0 Private Archive.
   - Add the Google account holding the Drive storage as a test user while setting up.
   - Request only the non-sensitive scope `https://www.googleapis.com/auth/drive.file`.
4. Create an OAuth 2.0 Client ID of type **Desktop app**. Do not use a service account. Drive ownership and storage quota are attached to the authorized Google account.
5. For unattended weekly refresh, set the OAuth app publishing status to **In production** before generating the final refresh token. If you leave an External app in **Testing**, Google expires the authorization (including its refresh token) after seven days, so you would have to re-authorize weekly. This is a single-owner personal integration (well under 100 users) and uses the non-sensitive `drive.file` scope; Google says personal-use apps under 100 users can operate without OAuth verification, although an unverified-app warning may appear and must be acknowledged during your own consent flow. Do not request the broad `drive` or `drive.readonly` scopes.
6. Copy the Client ID and Client Secret.
7. **Android / Termux setup (no PC required):** install the current Termux build from one official source (F-Droid or the Termux GitHub releases; do not mix APK sources). Android 7+ is supported. In Termux run:
   ```bash
   pkg update && pkg upgrade -y
   pkg install python git termux-tools -y
   git clone --single-branch --branch feat/krishinexus-real-data-school-lab https://github.com/moshiour0/FieldShift0.git
   cd FieldShift0
   python scripts/google_drive_oauth.py
   ```
   If the repository is already cloned, enter its folder, fetch the branch and check it out instead of cloning again.
8. Enter the Desktop OAuth Client ID and Client Secret when prompted. The script uses `termux-open-url` to open Android Chrome; if automatic launch is unavailable, copy the printed authorization URL into Chrome on the same phone. Approve access using the Google account holding the Drive storage. **Keep Termux running in the foreground/session** while Chrome opens: Google redirects to the `127.0.0.1` listener running inside Termux. Return to Termux after the browser confirms authorization. The script creates a private folder named **FieldShift0 Archive** and prints the four values to add as secrets. It does not write credentials to the repository.

   Important OAuth distinction: create a Google **Desktop app** client, not an Android client. Google continues to support loopback redirects for Desktop OAuth clients but has deprecated that redirect method for Android OAuth client types. Termux is a command-line runtime on Android, not a native Android OAuth app; the browser-to-Termux loopback callback should be tested on the phone before treating setup as complete. Do not use Google's deprecated manual copy/paste authorization-code (OOB) flow.

## Required secrets

Add the same four **GitHub repository Actions Secrets** and **Vercel Production + Preview Environment Variables**:

| Name | Value |
|---|---|
| `GOOGLE_DRIVE_CLIENT_ID` | Desktop OAuth Client ID |
| `GOOGLE_DRIVE_CLIENT_SECRET` | Desktop OAuth Client Secret |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | Refresh token printed once by the OAuth bootstrap |
| `GOOGLE_DRIVE_FOLDER_ID` | Private FieldShift0 Archive folder ID printed by bootstrap |

No AWS account, bucket, IAM role, OIDC trust, or S3 variables are required. Do not put credentials in GitHub Variables, source files, browser code, or chat. Vercel values must be server-side environment variables only.

In GitHub, add a repository **Variable** named `GOOGLE_DRIVE_ARCHIVE_ENABLED` with value `true` only after the four secrets are set and the preflight succeeds. This enables the scheduled weekly refresh **only after** `.github/workflows/history-refresh.yml` has been merged into the default branch. At present that workflow file is feature-branch-only, so weekly scheduled refresh is not active on `main`. A manual workflow dispatch always performs its own preflight.

## Backfill and resume

1. The 2025–2025 POWER daily archive is already complete and readable for all nine reference points (365/365 each). Do not rerun 2025 merely as a connectivity test.
2. To fill the older daily gaps, open Actions → **Backfill nine-region NASA POWER daily history**. This workflow file exists on `main`; choose the branch `feat/krishinexus-real-data-school-lab` in the workflow branch selector so the current feature-branch script is used.
3. Dispatch `start_year=2016`, `end_year=2025`. Existing checksum-valid 2025 objects are reused; only missing or invalid years should be fetched.
4. Confirm files appear under the private root folder in the expected region/year layout and that remote read-back matches the uploaded bytes and SHA-256.
5. The workflow processes at most three regions concurrently. Each region reports JSON-lines progress and a final job result. A failed region does not stop other region jobs; the overall workflow still reports failure if one region fails.

The weekly YTD refresh workflow is currently branch-only. Scheduled workflows use the default branch, so it will not execute until `.github/workflows/history-refresh.yml` is merged into `main` and `GOOGLE_DRIVE_ARCHIVE_ENABLED=true` is set. Merging that workflow file may trigger a Vercel Production redeploy from unchanged app code; review this side effect before approval.

## API verification

After the branch is deployed and Vercel environment variables are set, verify:

- `GET /api/status`: `archive_storage.provider` should be `google_drive` and `credentials_configured` should be true. This is configuration evidence, not a live connection test.
- `GET /api/history/{region}?start=2025-01-01&end=2025-12-31`: all nine current reference points have already been verified as `archive_representation: daily`, `status: complete`, 365/365 observations and full coverage.
- `GET /api/data-status/{region}`: NASA POWER should report `ready` through `2025-12-31`; satellite products remain independent and may report `not_archived`.
- For older POWER history, repeat the checks for 2016–2024 after the historical backfill completes. Do not call the archive a complete 2016–2025 daily dataset until every region/year passes.

An HTTP 200 alone is not proof of complete daily coverage. Inspect status, missing years, day counts, and provenance.

## Free-cost controls and limitations

- Google Drive storage consumes the quota of the Google account that authorizes OAuth. It does not use a service-account storage quota.
- This adapter stores processed NASA POWER JSON, not raw satellite imagery.
- Standard Google Drive API usage currently has no additional API-use charge. Google has announced usage thresholds and potential charges for usage above standard daily limits later in 2026. The nine-point climate archive is expected to remain far below normal transfer limits; monitor usage before large bulk transfers.
- Keep the root folder private. The adapter requests `drive.file`, not broad access to all Drive files.
- Refresh tokens can be revoked or expire. If OAuth access is revoked, rerun the bootstrap and replace all four secret values consistently.
- Drive is private object storage, not a transactional database. Signed-in analysis runs, source states, result revisions and the analysis worker queue live in the FieldShift0 Supabase project (`bipyrlegaxmhwzwrmcmi`). The separate `POST /api/refresh-jobs` regional POWER refresh queue still requires `FIELD_SHIFT_JOBS_DSN`; do not confuse it with the authenticated analysis queue or connect an unrelated Supabase project.

## Scientific boundaries

NASA POWER values are gridded representative-point samples, not field sensors, district averages, official AEZ means, or farm-specific observations. The existing Mymensingh 2016–2025 monthly aggregate remains a separate chart-only product. It is not converted into daily records. This POWER workflow does not ingest or validate SMAP, MODIS MOD16, HLS, or GPM archives. The SMAP workflow is currently present on PR #1's feature branch but absent from `main`. GitHub only exposes a manual `workflow_dispatch` workflow when its file exists on the default branch. A separate one-file Draft [PR #2](https://github.com/moshiour0/FieldShift0/pull/2) registers it; after explicit approval/merge, select `feat/krishinexus-real-data-school-lab` as the run ref and use `2025–2025` for the first pilot. The merge may trigger a Vercel Production redeploy. The pilot must pass Google Drive write/read/delete preflight, Earth Engine collection visibility, all nine region jobs, 365 days, eight valid 3-hourly intervals per day in both SMAP bands, remote Drive read-back and SHA-256 verification before any longer SMAP archive is started. Crop/soil recommendations remain a Mymensingh pilot pending Bangladesh field calibration.


## Worker status / lease regression correction — 11 November 2026

The latest Preview SQL read-back confirms the required/optional evidence contract: optional-only pending evidence with worker status `preliminary_ready` remains preliminary, while required pending evidence stays `waiting_for_data`. Both `worker_save_analysis()` and `worker_fail_analysis_job()` append their audit event before clearing the active lease. The matching branch migrations are in `supabase/migrations/`; the exact review checkpoint and open Production/account/data gates are in the [Final Owner Handoff](v3/FINAL_HANDOFF_2026-11-11.md).
