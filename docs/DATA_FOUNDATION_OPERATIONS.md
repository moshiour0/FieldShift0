# Data Foundation Operations

This runbook describes the reproducible NASA POWER daily point archive for the nine configured Bangladesh reference points. It does not claim official AEZ zonal coverage, farm-level measurements, or satellite-product coverage.

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

In GitHub, add a repository **Variable** named `GOOGLE_DRIVE_ARCHIVE_ENABLED` with value `true` only after the four secrets are set and the preflight succeeds. This enables the scheduled weekly refresh. A manual workflow dispatch always performs its own preflight.

## Backfill and resume

1. Open Actions → **Backfill nine-region NASA POWER daily history**.
2. Dispatch a small initial test window first (for example, 2025–2025) to confirm upload and read-back.
3. Confirm files appear under the private root folder in the expected region/year layout.
4. Then dispatch 2016–2025. The workflow processes at most three regions concurrently. Existing checksum-valid year files are reused; only missing or invalid years are fetched.
5. Each region reports JSON-lines progress and a final job result. A failed region does not stop other region jobs; the overall workflow still reports failure if one region fails.

The current-year refresh is scheduled weekly. It stores year-to-date files and only requests new data when the available date advances.

## API verification

After the branch is deployed and Vercel environment variables are set, verify:

- `GET /api/status`: `archive_storage.provider` should be `google_drive` and `credentials_configured` should be true. This is configuration evidence, not a live connection test.
- `GET /api/history/mymensingh?start_year=2025&end_year=2025`: response should report `archive_representation: daily`, `status: complete`, and 365 daily observations (assuming the backfill succeeded).
- `GET /api/data-status/mymensingh`: POWER should report `ready` and the archive kind should identify daily history.
- Repeat for all nine regions after the full backfill.

An HTTP 200 alone is not proof of complete daily coverage. Inspect status, missing years, day counts, and provenance.

## Free-cost controls and limitations

- Google Drive storage consumes the quota of the Google account that authorizes OAuth. It does not use a service-account storage quota.
- This adapter stores processed NASA POWER JSON, not raw satellite imagery.
- Standard Google Drive API usage currently has no additional API-use charge. Google has announced usage thresholds and potential charges for usage above standard daily limits later in 2026. The nine-point climate archive is expected to remain far below normal transfer limits; monitor usage before large bulk transfers.
- Keep the root folder private. The adapter requests `drive.file`, not broad access to all Drive files.
- Refresh tokens can be revoked or expire. If OAuth access is revoked, rerun the bootstrap and replace all four secret values consistently.
- Drive is file/object storage, not a transactional database. The analysis run store remains `process_memory`; durable refresh-job queueing still requires a separate PostgreSQL service. Do not connect this project to an unrelated Supabase database.

## Scientific boundaries

NASA POWER values are gridded representative-point samples, not field sensors, district averages, official AEZ means, or farm-specific observations. The existing Mymensingh 2016–2025 monthly aggregate remains a separate chart-only product. It is not converted into daily records. This workflow does not ingest or validate SMAP, MODIS MOD16, HLS, or GPM archives. Crop/soil recommendations remain a Mymensingh pilot pending Bangladesh field calibration.
