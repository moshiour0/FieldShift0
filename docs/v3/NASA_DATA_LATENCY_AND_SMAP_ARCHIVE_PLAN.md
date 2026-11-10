# KrishiNexus — NASA Data Latency, SMAP Archive & Persistent Analysis Implementation Plan

> **Document status:** Active implementation specification / continuity handoff  
> **Created:** 2026-11-09 (Asia/Dhaka)  
> **Repository:** `moshiour0/FieldShift0`  
> **Branch:** `feat/krishinexus-real-data-school-lab`  
> **PR:** #1 — Draft / Open / Unmerged. Do not merge without explicit user approval.  
> **Production:** Keep `main` and the Production deployment unchanged until explicit release approval.  
> **Supabase:** `FieldShift0`, ref `bipyrlegaxmhwzwrmcmi`, region `ap-south-1`.

---

## 0. Latest POWER archive and Preview evidence — 2026-11-10

The exact-head Preview was checked for each configured reference point over 2025-01-01 through 2025-12-31. All nine returned daily representation, 365 available days out of 365 expected, full coverage, no missing years, and an embedded SHA-256 archive checksum. These data are NASA POWER gridded reference-point histories, not field measurements or spatially complete Bangladesh coverage. The archive-first pipeline change now uses a complete annual archive only on an exact coordinate/date match; all other requests retain the live POWER path.

The same Preview reports SMAP, HLS, MODIS MOD16 and GPM as `not_archived` at all nine reference points. The 2025 SMAP reference-point pilot has not yet been dispatched. No arbitrary-location national SMAP grid archive exists.

## 0. Read this first in a future chat

This file is the authoritative implementation handoff for the data-latency and saved-analysis scope. A future session must:

1. Read this file completely.
2. Inspect the current PR #1 head and this branch's newest commits.
3. Inspect the latest GitHub Actions run and the newest READY Vercel Preview; compare their exact commit SHAs.
4. Read `docs/v3/PERSISTENT_ANALYSIS_ROADMAP.md` for the detailed database, worker, auth, retry, and deployment history.
5. Continue only on `feat/krishinexus-real-data-school-lab`. Do not merge PR #1, promote Production, rotate secrets, or change unrelated projects.

Do not ask the user to repeat the requirements recorded below.

## 1. User problem and required outcome

A farmer selects a field/location on the map, enters an exact analysis date window and farm/soil/water/priority inputs, and submits an analysis request.

NASA AppEEARS products are asynchronous. The user's own 53-request AppEEARS history shows that the three satellite products do not have equal latency:

- SMAP is the dominant long-tail delay. Some requests complete in minutes, others in about 30–50 minutes, and six October 24–25 requests in the supplied history did not complete until November 5–6 (about 11 days 20 hours to 12 days 2 hours).
- HLS and MODIS ET usually finish much sooner, but they are not guaranteed to finish inside 15–20 minutes for every request.
- The website must not make users wait for the slowest optional satellite product before it can show a useful first analysis.
- Closing a browser or changing a Vercel function instance must not lose a submitted request, its selected location, date window, inputs, provider task IDs, source states, or result history.
- Returning after one or two days and signing in must show the same saved analysis and its newest result revision.
- Every new revision must use the same immutable original request unless the user explicitly submits a new request.

### User-facing target

**Target:** show a useful, evidence-labelled first analysis in approximately 15–20 minutes when the required core data are ready, without waiting for a slow SMAP task. Then continue the background source lifecycle and publish a new result revision when SMAP (or any other pending requested source) completes.

This is a target, not an unconditional SLA. NASA product availability, AppEEARS queue load, AOI/date coverage, quotas, and provider outages can still extend processing. Never claim a final result is ready while required evidence is missing or unverified.

## 2. Evidence from the user's 53 AppEEARS requests

### 2.1 What the supplied history says

The table shows 53 total requests. Thirteen recent three-product groups can be paired by their common request start time. Durations below are calculated from the supplied Bangladesh-local timestamps (GMT+6); values are rounded to the nearest second where useful.

| Request submitted (Bangladesh time) | HLS completion time | MODIS ET completion time | SMAP completion time |
|---|---:|---:|---:|
| 2026-11-09 16:13 | 4m 54s | 4m 16s | 3m 28s |
| 2026-11-09 06:46 | 20m 50s | 19m 08s | 49m 36s |
| 2026-11-09 00:24 | 10m 19s | 9m 21s | 49m 12s |
| 2026-10-25 05:38 | 15m 10s | 16m 16s | 11d 20h 39m |
| 2026-10-25 00:28 | 23m 00s | 22m 28s | 12d 1h 46m |
| 2026-10-24 22:49 | 1h 18m 47s | 42m 05s | 12d 2h 41m |
| 2026-10-24 22:36 | 1h 30m 56s | 40m 30s | 12d 2h 26m |
| 2026-10-24 22:05 | 1h 08m 46s | 31m 05s | 12d 2h 05m |
| 2026-10-24 22:04 | 29m 55s | 29m 01s | 12d 1h 09m |
| 2026-10-13 15:25 | 1m 52s | 1m 44s | 42m 21s |
| 2026-10-08 22:56 | 2m 34s | 1m 59s | 31m 51s |
| 2026-10-08 22:49 | 2m 08s | 2m 35s | 32m 05s |
| 2026-10-08 22:39 | 2m 14s | 1m 44s | 31m 35s |

The remaining older records include standalone SMAP requests completing in roughly 3m 32s and 9m 31s, plus older test requests. They do not invalidate the long-tail pattern above.

**Important interpretation:** the log does not support a fixed “SMAP always takes 35–40 hours” rule. It demonstrates a much wider observed range, including a cluster of approximately 12-day delays. HLS and MODIS are faster in most paired examples, but the October 24–25 batch also shows HLS taking about 1h 9m–1h 31m and MODIS about 29–42 minutes. Therefore, no satellite source should be used as a synchronous hard wait in the HTTP request.

### 2.2 Latency-based priority decision

| Product | Priority | Initial strategy | Why |
|---|---|---|---|
| **NASA SMAP** | **P0 — archive first** | Build a verified historical spatial archive and a durable exact-location cache. Continue exact live fetch for spatial/time gaps. | It has the longest and most variable observed delay, including the 12-day cluster. |
| **NASA HLS vegetation indices** | P1 — live first | Submit live in parallel; persist completed results to the shared Drive cache so retries and repeat analyses can reuse them. | Most paired jobs finish faster than SMAP; some still exceed 20 minutes. |
| **NASA MODIS MOD16 ET** | P1 — live first | Submit live in parallel; persist completed results to the shared Drive cache. | Most paired jobs finish faster than SMAP; some October jobs took 29–42 minutes. |
| NASA POWER Daily weather | P1 core | Keep current live/cache logic and existing history archive policy; do not create a new bulk archive solely because of this AppEEARS latency report. | It is not one of the AppEEARS long-tail products in the supplied table. |
| NASA GPM IMERG | Existing source policy | Keep its independent coverage/48-interval QA and retry policy. Do not add a bulk archive in this change. | No GPM request rows are present in the supplied AppEEARS history. |
| NASA NEX-GDDP-CMIP6 | Existing source policy | Keep it separate as modelled climate evidence, not observed weather. Do not add a bulk archive in this change. | No NEX request rows are present in the supplied AppEEARS history. |

**Do not interpret this table as permission to silently drop HLS/MODIS.** They remain requested, independently tracked evidence. Their slow tail must not block the first useful result if the versioned analysis dependency policy marks them optional for that run.

## 3. SMAP product and spatial-resolution constraints

Current code discovers and prefers AppEEARS product `SPL4SMGP.008` (SMAP L4 Global 3-hourly 9-km Surface and Root Zone Soil Moisture). Its relevant documented properties:

- Global spatial coverage.
- Native 3-hour temporal cadence.
- Approximately 9 km native EASE-Grid 2.0 spatial resolution (catalogues may state pixel size around 11 km after reprojection).
- Surface soil moisture represents approximately 0–5 cm; root-zone soil moisture represents approximately 0–100 cm.
- SMAP L4 is an assimilated geophysical estimate. It is not a direct farm sensor measurement, and outages of the SMAP instrument can leave the product relying on land-model estimates without contemporaneous brightness-temperature assimilation.
- NSIDC documents Version 8 as `SPL4SMGP.008` and the product's current coverage/resolution.

Official references:
- NSIDC product page: https://nsidc.org/data/spl4smgp/versions/8
- NASA/AppEEARS changelog for SMAP cloud migration and Version 8 availability: https://appeears.earthdatacloud.nasa.gov/changelog
- AppEEARS overview (supports point and area samples): https://appeears.earthdatacloud.nasa.gov/
- NASA AppEEARS area API tutorial: https://github.com/nasa/AppEEARS-Data-Resources/blob/main/R/tutorials/AppEEARS_API_Area_R.Rmd
- NASA AppEEARS point API tutorial: https://github.com/nasa/AppEEARS-Data-Resources/blob/main/R/tutorials/AppEEARS_API_Point_R.Rmd
- NSIDC AppEEARS point/area help: https://nsidc.org/ru/node/32087

The AppEEARS task table supplied by the user displays a “Sample Request Retention” notice. AppEEARS task IDs and completed bundles must not be treated as permanent storage. Downloaded, validated output must be copied into the project's own private archive before relying on it.

### 3.1 Spatial integrity rule — non-negotiable

The current code's `appeears_point_timeseries()` is a **Point Sample** request. The nine coordinates in `history.py::REGIONS` are representative anchor points, not nine polygons, not official AEZ zones, not district averages, and not farm sensors.

Therefore:

- A nine-point reference archive may be used for its own exact anchor point or for clearly labelled regional context only.
- It must **never** be silently substituted for an arbitrary user-selected farm coordinate.
- “Nearest region” is not a valid substitute for a field-specific SMAP point sample.
- For arbitrary map coordinates, the scalable archive must preserve the SMAP native spatial cells covering the target geography (for example, AppEEARS Area output or an equivalent verifiable gridded archive). A field query can then be mapped to its actual native grid cell and its exact selected date window.
- The spatial lookup must store the grid system, CRS, cell geometry/identifier, native product/version, and extraction/aggregation method.
- When the AOI intersects multiple cells, apply a documented area-weighted or explicitly selected-cell policy. Do not average cells without recording the method.
- A 9-km product cannot resolve sub-grid variation inside a small farm. The UI and scientific output must state this limitation.
- If a valid spatial tile/cell is not archived, submit the exact selected-point AppEEARS task and mark it pending. Do not use another location's observation to force a quick result.

### 3.2 Historical archive scope

The first bulk archive scope is **SMAP only**, for 2016–2025 (completed calendar years) across the nine operational reference regions / spatial tiles covering the intended Bangladesh geography.

Implementation must separate two concepts:

1. **SMAP spatial archive:** grid/tile coverage that can serve a user-selected coordinate only when the coordinate maps to a verified archived cell.
2. **SMAP point sample archive:** exact coordinate + exact date-window result, stored for subsequent repeat requests and cache reuse.

The nine current reference point coordinates alone do not satisfy national spatial coverage. Before calling the archive “Bangladesh-wide,” the nine geometries must be verified to cover the intended geographic area; an actual boundary or documented tiling scheme must be committed. Do not fabricate official AEZ polygons. A grid partition can be called an operational tile grid, not an official agricultural zone system.

A production backfill must be staged:
- First test one completed year (2025) and a small number of verified tiles/cells.
- Validate file sizes, date coverage, grid alignment, data values, quality metadata, and remote read-back.
- Then expand to 2016–2025 in bounded batches.
- Preserve per-tile/year failure isolation, resume completed valid tiles, and retry only missing/failed objects.
- Do not run a massive 10-year AppEEARS area job until output format, size, per-request limit, and runtime have been verified with the 2025 pilot.

If area extraction proves too large or unsupported for a viable free-tier workflow, retain the exact-point fallback and document that national arbitrary-location SMAP archive coverage is not yet complete. Do not silently degrade to the nine anchor points.

## 4. Shared Google Drive cache for completed satellite results

In addition to the bulk SMAP spatial archive, persist a successfully downloaded and QA-validated AppEEARS point result so that a repeat analysis for the same product, exact coordinate, date window, and product version can reuse it without another AppEEARS request.

### 4.1 Archive contents

For each completed product result, store:
- product key (`smap`, `hls_vi`, `modis_et`);
- ProductAndVersion and layer names returned by the current AppEEARS catalog;
- exact submitted latitude/longitude and a documented coordinate precision policy;
- requested and actual available start/end dates;
- AppEEARS task ID and task name (metadata only; never the only copy of the data);
- parsed usable observations, including dates and units/scale handling;
- QA method, QA outcome, product-specific limitations, and count of excluded/invalid observations;
- retrieval timestamp, provider citation, retrieval source (`appeears_live`, `google_drive_cache`, or spatial archive);
- schema/processing version, payload SHA-256, and archive verification timestamp.

### 4.2 Cache key and compatibility

A cache hit is permitted only when the key/metadata confirms:
- same product collection/version and layer selection;
- exact compatible coordinate or exact compatible native SMAP grid cell;
- requested dates are fully covered by the archived date span;
- same native cadence/aggregation convention;
- same processing and QA version, or an explicit compatibility migration;
- SHA-256 validation succeeds.

A superset date window may be sliced to the requested window only after checking every requested date and preserving native cadence/coverage. A narrower/partial cache must not be reported as a full hit.

Suggested Drive layout (versioned; final path may be refined during code review):

```text
FieldShift0 Archive/
  smap-grid/v1/{tile_id}/{year}/{object}.nc-or-cog
  satellite-point-cache/v1/smap/{cache_key}.json
  satellite-point-cache/v1/hls_vi/{cache_key}.json
  satellite-point-cache/v1/modis_et/{cache_key}.json
  archive-manifests/smap/{tile_id}/{year}.json
```

Use Drive resumable upload for large files. Upload must be private. Always perform remote read-back and SHA-256 verification before marking an archive object available. A local filesystem write alone is not a durable archive success.

### 4.3 Cache miss and error handling

- If Drive is not configured or unavailable, keep the source state honest and use the existing exact-location live request when possible.
- Never interpret a Drive 404/missing object as a valid empty dataset.
- Never swallow a remote archive permission or network error and label a cache hit.
- Cache validation errors must invalidate only the affected object and fall back to an exact live fetch; other source results continue independently.
- Failed/partial AppEEARS tasks must not be written to the verified cache.
- Cache only after product-specific QA, date-window coverage, fill-value filtering, unit/scale normalization, and checksum verification pass.

## 5. First-result and final-result lifecycle

A 15–20 minute first result requires a lifecycle change, not a dishonest relaxation of scientific validation.

### 5.1 Source policy

Use a versioned source dependency policy. Initial policy:
- NASA POWER daily weather remains the required core weather source for a live observed-weather analysis.
- SMAP, HLS and MODIS remain individually visible satellite evidence sources. Their role (required/optional) is determined by the model feature and versioned policy, not by whether they are currently available.
- If SMAP is optional for the current engine run and remains pending, the engine may publish a **preliminary** result based on the evidence actually available.
- If a particular prediction feature requires SMAP, that feature must remain unavailable/pending until SMAP passes QA; do not compute it as zero.
- Missing/unreleased data are not zero, not “dry soil,” not “no vegetation,” and not proof of no risk.
- A provider's missing date coverage is not necessarily a transient delay. Store the reason and only schedule retries when provider/task metadata makes retry appropriate.

### 5.2 Result status semantics

Keep run lifecycle separate from per-source state.

| Run status | Meaning |
|---|---|
| `queued` | Request snapshot is durably saved; waiting for worker |
| `running` | Worker is processing |
| `preliminary_ready` | Useful output exists, but one or more requested/optional sources remain pending or unverified; show visible caveats |
| `waiting_for_data` | A required source or required QA gate is not ready; no final decision output may be claimed |
| `final_ready` | All policy-required data and QA gates passed |
| `final_with_gaps` | Required core gates passed; optional/requested sources have terminal documented gaps |
| `failed` | Non-recoverable error or exhausted retry budget; preserve request and audit history |
| `cancelled` | User cancelled; preserve the audit trail |

### 5.3 Do not block the user's first useful output on SMAP

- Submit SMAP, HLS and MODIS tasks independently and early.
- Do not hold the user's HTTP request open waiting for AppEEARS.
- Persist all task IDs as soon as known.
- The worker may save a preliminary revision using the validated evidence already present.
- If SMAP is pending but optional for this model revision, the run can remain `preliminary_ready`; it must not be misrepresented as final.
- Reuse completed HLS/MODIS cached records and do not download them again on each worker retry.
- When SMAP completes, QA it, archive it, rebuild the result, and create a new immutable result revision/event.
- If a required source is missing, keep the run `waiting_for_data` and explain exactly which source/date/QA gate is blocking it.
- The user can close the website. The scheduled worker continues independently.

### 5.4 Retry schedule

- Respect provider `Retry-After` and task state.
- The worker's current minimum retry delay is 15 minutes and maximum provider wait is bounded at 48 hours. Preserve bounded backoff and lease semantics.
- Never POST a duplicate AppEEARS task while the original task is pending/processing or its exact persisted task ID remains reusable.
- Recheck only pending/retryable sources, not sources already validated and cached.
- Do not use a fixed 35/40-hour delay; the supplied log disproves a fixed latency and AppEEARS/provider status is authoritative.
- Do not retry terminal no-coverage or invalid-product results forever.
- Keep task IDs, retry reason, attempts, next_retry_at, and source status in durable storage.

## 6. Account identity and saved analyses

The user must be able to return after one or two days and recover all submitted requests.

The authoritative identity is the immutable Supabase Auth user UUID; never trust a browser-supplied `user_id`.

Each saved run must retain:
- owner user UUID;
- immutable request snapshot: selected map location/AOI, exact date window, field size, soil/water/farmer inputs, crop context and priorities;
- request idempotency key;
- source/product status and coverage;
- provider task IDs;
- retries, failure reasons and timestamps;
- evidence/provenance snapshot and fingerprint;
- versioned result revisions (preliminary/final/final-with-gaps);
- append-only lifecycle events.

User A must never read, recheck, update or delete User B's run. Test this with two actual authenticated accounts, not just unit tests. Sign-in may use Supabase Magic Link/OTP initially; custom SMTP and redirect allowlists remain operational prerequisites for a real sign-in test.

The original request must be immutable. A recheck/retry operates on the saved snapshot. A new location/date range/input set creates a new run.

## 7. Existing repository and production state inspected for this handoff

### 7.1 GitHub branch and PR

- Repository: `moshiour0/FieldShift0`.
- PR #1: https://github.com/moshiour0/FieldShift0/pull/1
- Working branch: `feat/krishinexus-real-data-school-lab`.
- Initial inspected branch head for this roadmap snapshot: `eb2b2ea804bc1c16b567fe1b75d62dff752774ce`. Later implementation and current branch head are recorded in Section 7.6.
- PR #1 is still open, Draft, and unmerged.
- Production/main baseline recorded by PR: `a0f6cb14cdc0cc65f1bbbe84cb2c8d9e405c728f`.
- Keep the PR Draft/Open/Unmerged until explicit user approval.

### 7.2 Historical baseline at initial inspection (superseded by Section 7.6)

- GitHub Actions workflow run inspected for current head: run ID `42602954531`, run #395, completed successfully.
- Python 3.11 and 3.12 jobs both passed pytest, compileall, Ruff, and mypy.
- At that historical inspection point, the branch's Vercel check failed due the free-plan daily deployment-rate limit. Later a runtime-bearing Preview was successfully deployed; see Section 7.6 for the READY deployment SHA and smoke-test results.
- Do not use this initial Vercel failure as the current deployment status.

### 7.3 Supabase project / existing durable queue

- Project `FieldShift0`, ref `bipyrlegaxmhwzwrmcmi`, is `ACTIVE_HEALTHY`, region `ap-south-1`.
- Applied migrations include authenticated run persistence, result revisions, durable worker queue, worker lease/retry state, worker schedule, and owner recheck RPC.
- The single active scheduled job verified in `cron.job` is `fieldshift-analysis-worker` with schedule `*/5 * * * *`.
- The current `private.dataset_cache` table exists but had **zero rows** when inspected. Cache metadata schema exists; verified dataset objects have not yet been populated there.
- `public.analysis_run_sources` includes `provider_task_id`, coverage, quality, provenance, attempts, and next retry fields.
- `private.analysis_run_jobs` exists with a lease, attempts, idempotency key, and run/source references.
- The current database contained no queued worker jobs when inspected.
- No real signed-in end-to-end user analysis has yet been demonstrated in the continuity record. The temporary worker probe previously ran and its synthetic user/run/job/source/result/event were deleted after verification.
- Supabase Security Advisor showed one warning for the intentionally owner-checked `public.request_analysis_run_recheck(uuid)` SECURITY DEFINER RPC. The function must remain owner-scoped and non-publicly executable; review whether it should be moved behind a private helper/wrapper.
- The initial Supabase Performance Advisor inspection found duplicate permissive worker RLS policies. They were removed in applied migrations; remaining initplan warnings and current policy state are recorded in Section 7.6. Do not weaken the worker-token restriction.
- Supabase Health Advisor returned no findings during inspection.

### 7.4 Initial code findings (historical; later changes are recorded in Section 7.6)

- `src/fieldshift/v3/appeears.py`:
  - `SOURCE_DEFINITIONS` currently includes SMAP, MODIS MOD16 and HLS.
  - SMAP product preference includes `SPL4SMGP.008`.
  - Requests are currently `task_type: point`, one coordinate `field`.
  - The AppEEARS request range is capped at 366 days by `FIELD_SHIFT_APPEEARS_MAX_DAYS`.
  - The product connector writes a local seven-day cache (default `FIELD_SHIFT_APPEEARS_CACHE_TTL_SECONDS=604800`) and a pending task file. Vercel local files are not shared durable storage.
  - AppEEARS task-list discovery and persisted task IDs reduce duplicate submissions, but they do not replace a durable copy of completed data.
  - The three products are sampled independently; the connector currently processes the product definitions sequentially and returns pending task IDs when tasks are not complete.
- `src/fieldshift/api/analysis_worker.py`:
  - Worker claims one durable job, loads the immutable request, reloads stored provider task IDs, runs the engine, persists the new revision/source state, and schedules retries.
  - Retry delay is derived from pending source metadata and is bounded.
  - This concern was addressed in the later worker and database changes recorded in Section 7.6: optional pending data can remain `preliminary_ready`, while required-source gaps remain `waiting_for_data`.
- `src/fieldshift/v3/region_catalog.py`:
  - It defines 12 provisional UI groupings, not official AEZ polygons.
  - No official polygon/crosswalk should be inferred.
- `src/fieldshift/v3/history.py`:
  - `REGIONS` defines nine representative coordinates.
  - Those anchors cannot be used as exact data for arbitrary user coordinates.
- `src/fieldshift/v3/google_drive.py`:
  - The private Drive adapter supports OAuth refresh, object get/put, and resumable uploads.
  - The SMAP and AppEEARS cache writers now use SHA-256 and remote read-back verification; a real NASA-derived object round-trip remains unverified in Preview.
- `private.dataset_cache` remains empty and is not the storage layer for the Drive object cache; cache provenance is persisted in `analysis_run_sources`.

## 7.5 Implementation progress — 2026-11-09 (branch head `6ddf3aeead2d81a8b22973d50fefab160249b308`)

### Completed code on the Draft PR branch

- `src/fieldshift/v3/appeears.py` now checks a private Google Drive shared cache for completed Point Sample outputs before submitting or resuming AppEEARS tasks.
- The shared-cache identity includes product/source key, layer/product version, spatial resolution/cadence, exact request/effective date window, and the five-decimal coordinate precision policy used by the current adapter.
- Cached objects have a canonical payload SHA-256, private Drive object key, schema version, and identity. The writer uploads and then fetches the exact object bytes back; a mismatch prevents the object from being marked verified.
- This works for completed SMAP, HLS and MODIS point samples. It is intentionally **on-demand durable caching**, not yet a Bangladesh-wide SMAP raster/tile archive.
- Local seven-day cache remains only an optimization; Google Drive is the shared durable cache when configured.
- A corrupt or incompatible shared object is treated as a cache miss. The engine must use the exact live provider path rather than accept the corrupted object.
- `src/fieldshift/api/analysis_worker.py` now distinguishes pending required from pending optional datasets. When the required core source is ready and only optional satellite work remains, the saved result is `preliminary_ready`, `is_final=false`, and `result_kind=preliminary`; the worker still schedules the pending source retry. If the required core source is pending, it remains `waiting_for_data`.
- Saved source provenance now records whether shared archive cache verification succeeded, plus archive object key and payload digest.
- Frontend `src/fieldshift/api/static/index.html` already has a `PRELIMINARY RESULT` readiness state and restores a saved result while the worker continues. Keep its copy distinct from a final result.

### Verification

- Current branch head: `6ddf3aeead2d81a8b22973d50fefab160249b308`.
- GitHub Actions push run #409 (`42614121990`) and pull-request run #408 (`42614112366`) both completed successfully.
- Python 3.11 and 3.12: **161 passed, one existing Starlette/httpx TestClient deprecation warning** on each version.
- `compileall`, strict Ruff and mypy all passed on both Python versions.
- PR #1 remains Draft/Open/Unmerged. No Production deployment was promoted.

### Not yet verified / next gates

- No live Google Drive read/write round-trip for these new satellite point-cache objects has yet been performed from a deployed current-head Preview.
- No production or Preview result has yet demonstrated a repeat cold-instance request reusing the shared object against real NASA/AppEEARS data.
- The current READY Vercel Preview still points at an older commit, not the current branch head; current-head Vercel commit status remains a failure caused by the team's free-plan daily deployment rate limit. Do not treat an older Preview as the current code.
- The nine geographic storage-tile geometries, 2025 SMAP Area request, NetCDF schema, 3-hour native cadence, cell mapping, object size, QA and Drive read-back remain to be implemented/verified before the 2016–2025 bulk archive.
- The durable account/queue implementation remains code/database-verified but still needs a real signed-in user acceptance test, two-account isolation test, and a complete live NASA result revision lifecycle.

### AppEEARS Area request research

NASA's AppEEARS Area tutorial documents:
- `task_type: "area"`;
- a polygon/feature collection in `params.geo`;
- an explicit output projection and `params.output.format.type`;
- `geotiff` or `netcdf4` output formats;
- task submission through the same AppEEARS task endpoint (HTTP 202 for accepted tasks).

Official API example: https://github.com/nasa/AppEEARS-Data-Resources/blob/main/R/tutorials/AppEEARS_API_Area_R.Rmd

This confirms the technical request shape for an area-archive pilot. It does **not** prove that a 10-year Bangladesh-sized request will pass AppEEARS size/runtime limits or that its output has already been processed. The next step must be one small 2025 area/tile pilot and inspection of the actual bundle.

---

## 7.6 Implementation update — 2026-11-09 (after SMAP cache/retry and DB lifecycle work)

### Code now present on this Draft PR branch

- SMAP uses `NASA/SMAP/SPL4SMGP/008` through Google Earth Engine at the selected map coordinate when GEE is configured. AppEEARS remains the exact-location fallback when GEE cannot be used.
- Daily SMAP records are accepted only when both `sm_surface` and `sm_rootzone` independently have all eight 3-hourly observations. No missing interval or day is interpolated.
- The GEE path has an exact coordinate + product + QA version + date-chunk key. Completed records are written to private Google Drive with canonical payload SHA-256 and byte-for-byte remote read-back verification.
- SMAP cache chunks are now stable **calendar-year chunks**, not request-relative 365-day ranges. A request for (for example) 2024-03-01 through 2025-06-30 reads the 2024 and 2025 year objects, then returns only the requested inclusive dates. This enables reuse when a user changes the date window but retains the same exact field coordinate.
- Multi-year SMAP windows are bounded into one calendar-year query per year, with each year object cached independently. A failed year must not invalidate already-verified year objects.
- AppEEARS point results for HLS and MODIS remain live-first and are stored in the shared Drive exact-result cache after QA. If GEE SMAP is unavailable, AppEEARS can fetch SMAP as fallback.
- The first durable worker attempt performs **SMAP cache lookup only**; on a cache miss the source remains pending and the run can show a preliminary result if required core weather is ready. Cache-miss retry is 900 seconds (15 minutes), allowing HLS/MODIS status and task IDs to be rechecked. From the second worker attempt onward, live SMAP acquisition is allowed. This is designed to keep a first useful result from being blocked by a long SMAP acquisition, while still enriching the same run in later revisions.
- The cache-only first-pass rule also applies when **GEE is not configured but AppEEARS is configured**: the first attempt request only HLS and MODIS from AppEEARS, add an explicit pending SMAP evidence row, and let the second attempt submit the exact-location AppEEARS SMAP fallback. This closes a configuration-dependent path that otherwise could have submitted the slow SMAP task on the first attempt.
- Added `scripts/prefetch_smap_points.py`, `scripts/verify_smap_archive_prerequisites.py` and `.github/workflows/smap-reference-backfill.yml`. The manual workflow can prefetch SMAP yearly objects for the nine configured representative coordinates, with per-year full coverage, 8/8 interval QA, private Drive write, remote read-back and checksum gates; up to three reference points are processed in parallel. The workflow defaults to a **2025 one-year pilot**, not the full 2016–2025 backfill. Its preflight now verifies Google Drive temporary write/read/delete plus Earth Engine credential initialization and read access to `NASA/SMAP/SPL4SMGP.008` before any yearly data retrieval. This is a reference-point archive only and does not claim national raster coverage or permit nearest-point substitution.
- The first worker attempt still starts HLS/MODIS AppEEARS tasks independently; their task IDs and result states are persisted. A pending task must reuse the saved provider task ID on the next worker attempt rather than submit a duplicate.
- The crop-water model's SMAP initialization limitation is explicitly disclosed: it uses a root-zone observation only when one is within ±7 days of sowing; otherwise it uses the labelled 35% TAW initial depletion default.

### Durable result-status correction applied to the FieldShift0 Supabase project

A live database inspection found that the deployed `public.worker_save_analysis` RPC previously forced every run with `p_retry_at` to `waiting_for_data`, even when Python correctly sent `preliminary_ready` for optional pending SMAP. This caused a mismatch between the useful preliminary result and the saved run status.

An additive migration now preserves the status contract:
- optional pending source + required core available → `preliminary_ready`, `completed_at=NULL`, result kind `preliminary`, retry continues;
- required pending source → `waiting_for_data`, `completed_at=NULL`, result kind `preliminary`, retry continues;
- no retry required → the engine's configured final/final-with-gaps state is saved.

The migration has been applied successfully to the non-production Supabase project `FieldShift0` (`bipyrlegaxmhwzwrmcmi`). The actual remote migration versions are recorded in the GitHub filenames to avoid CLI history drift:
- `20261109124135_preserve_preliminary_run_status.sql`
- `20261109124329_deduplicate_worker_queue_policies.sql`
- `20261109124402_cache_worker_rls_header.sql`

### Protected Preview smoke test — 2026-11-09

- Runtime Preview: `https://field-shift0-igfpm2kn9.vercel.app`, deployment `dpl_ASLoBnTYWcTGCAPbwbZfZ2StDL51`, source commit `62d76f38ced0a67ca479150bc36d447f5103a83c`.
- Protected Preview `GET /api/auth/config` returned HTTP 200: `configured=true`, provider `email_magic_link`, and the FieldShift0 Supabase project URL/key were configured. Key values are not reproduced here.
- A safe idle worker tick was invoked from the FieldShift0 Supabase project only after confirming zero queue jobs in `queued`, `retrying`, or `running` states. It used the existing Vault-backed worker token and Vercel protection-bypass secret. The Preview returned HTTP 200 with `processed=false` and “No queued analysis job is ready.”
- This validates protected Preview routing, Vercel bypass, worker token validation, Supabase connectivity and the empty-queue claim path. It does **not** prove a real authenticated user submission, NASA task execution, or a live Drive cache write/read.
- The Vercel Hobby runtime-log API returned a 400 retention-limit response for the requested one-hour window. Treat this as an observability-plan limitation, not an application runtime error.

### Supabase queue-policy cleanup and live DB state

- Duplicate anonymous worker SELECT/UPDATE RLS policies on `private.analysis_run_jobs` have been removed. Exactly one token-gated SELECT policy and one token-gated UPDATE policy remain, plus the independent `service_role` policy.
- The remaining anon policies still require `private.worker_token_matches` for the `x-fieldshift-worker` header. Access semantics have not been broadened.
- The current performance advisor still reports two `auth_rls_initplan` warnings for these policies even after scalar-subquery wrapping of the helper/header expressions. Do not claim the warning is cleared; retain it for further plan-level analysis.
- Security advisor still reports one warning for the owner-scoped `public.request_analysis_run_recheck(uuid)` SECURITY DEFINER RPC. It has not been disabled or altered in this update because the product needs a user-initiated recheck and owner isolation must be preserved.
- Performance advisor lists four unused indexes (informational; new/empty tables have not exercised them). Health advisor reports no findings.
- Supabase currently has exactly one active `fieldshift-analysis-worker` schedule at `*/5 * * * *`.
- `public.analysis_runs`, `private.analysis_run_jobs`, and `private.dataset_cache` had zero rows at the most recent inspection. No test user/run/job was inserted or left behind.

### CI and deployment status

- Runtime code currently deployed on Preview: `eb635f5a94fcd3236e8e1c1062c7e507feb0585a`. Later branch commits through the PR head tested below are documentation-only; the deployed runtime and tested source behavior are therefore aligned.
- PR head validated in the latest CI run: `f9f67925a7f82c12f632271a237773c58aeea45a`. Run #549 (`42627275074`) completed successfully. Python 3.11 and 3.12 each report **173 passed, 1 existing Starlette/httpx TestClient deprecation warning**; `compileall`, strict Ruff and mypy (34 source files) all passed in both jobs.
- PR #1 remains **Draft / Open / Unmerged**.
- Latest READY runtime Preview: `https://field-shift0-76gice8g5.vercel.app`, deployment `dpl_JBuwpxmGuyD8a27yL24e96nirTXx`, source SHA `eb635f5a94fcd3236e8e1c1062c7e507feb0585a`.
- Latest Preview `GET /api/auth/config`, sent with the Vault-backed Vercel protection bypass header, returned HTTP 200 with `configured=true` and provider `email_magic_link`. No secret value was included in the response or copied.
- A safe idle-worker probe was sent to this same deployment only after the database query showed **0 non-terminal jobs** (`queued`, `retrying`, `running`). The Vault-backed `POST /api/internal/worker/tick` returned HTTP 200, `processed=false`, and `No queued analysis job is ready.` No user job was processed. These two smoke checks verify protected routing, bypass/worker-token validation, auth configuration and Supabase connectivity; they do **not** prove a real authenticated submission, NASA task execution, AppEEARS task-ID reuse, second-attempt SMAP retrieval or Drive object write/read.
- Project-level Vercel environment metadata confirms Preview configuration entries for the four Google Drive settings, AppEEARS user/password and both GEE settings. Secret values were not read or copied.
- A fresh exact-head Preview creation attempt (for the then-current docs-only SHA `dda8555...`) returned HTTP 402 `api-deployments-free-per-day` with `retryAfter=86400`; the PR's Vercel check still reports `build-rate-limit`. The current tested PR head adds only another documentation correction, not runtime changes. The documented CLI fallback is unavailable here because there is no linked repository checkout and no `vercel` executable. Do not loop deployment calls, change billing/plan, or promote Production.
- A single quota-aware retry is scheduled for **10 November 2026, 20:00 Asia/Dhaka**. It will deploy only if PR #1 remains open/draft, no READY Preview already matches its then-current head, and Vercel permits a new deployment. A further quota error will stop the retry; no repeated attempts.
- The Vercel Hobby runtime-log API returned a 400 retention-limit response for the requested one-hour window. Treat this as an observability-plan limitation, not an application runtime error.
- Supabase non-production migrations through `20261109124402` are present. Exactly one `fieldshift-analysis-worker` cron job is active at `*/5 * * * *`.
- No Production deployment, Production environment/configuration change, billing/plan change, or PR merge was performed.

### Still not proven — do not mark these as complete

1. **Real Drive round-trip:** the current automated cache tests mock the Drive adapter. A deployed Preview must upload a real NASA-derived QA-checked SMAP/HLS/MODIS object, read it back, compare bytes/SHA-256, and then prove a cold-instance cache hit.
2. **Nationwide gridded archive:** the current GEE cache is exact-point data for one selected coordinate per cache key. It is not a raster/area archive for arbitrary Bangladesh fields. Nine reference points alone are not enough. A verified Bangladesh boundary/operational tile geometry and a 2025 SMAP area/tile pilot are still required before describing the archive as Bangladesh-wide.
3. **Actual 2016–2025 prefetch:** no ten-year national SMAP data backfill has been dispatched. The one-year-per-point cache mechanism is a reusable foundation, not a finished nationwide backfill.
4. **Live AppEEARS provider-resume and SMAP enrichment:** the READY `55a7a9c...` Preview now contains the runtime policy, but a genuine queue run has not yet proved the initial cache-only attempt, exact persisted HLS/MODIS task-ID reuse, second-attempt AppEEARS SMAP submission/resume, and later result revision without duplicate task submission.
5. **Account continuity:** real Magic Link login, submit a genuine authenticated analysis, close/reopen after one or two days, and two-account access isolation remain to be demonstrated against a Preview whose SHA equals the current branch head.
6. **15–20 minute experience:** this remains a product target, not a guaranteed SLA. NASA publication lag and provider queues can exceed it; only show a useful preliminary result when required core data and their QA gates are ready.
7. **GitHub Actions backfill credentials:** the manual nine-reference-point workflow requires all four `GOOGLE_DRIVE_*` repository secrets plus `FIELD_SHIFT_GEE_PROJECT` and `FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON` as GitHub Actions Secrets. GitHub Actions secret presence has not been independently verified. The workflow preflight fails before yearly SMAP retrieval if they are missing or the Earth Engine asset/Drive round-trip check fails. Start with the default 2025 pilot; do not select 2016–2025 until the pilot's runtime, coverage and cost/volume are reviewed.

---

## 8. Implementation sequence

### Phase A — create durable exact-result caching (implemented in current branch; live Drive validation remains)

1. Add a Google Drive-backed completed AppEEARS result cache keyed by product/version, selected layers, exact coordinate or native cell ID, requested/actual date coverage, temporal cadence and QA/processing version.
2. Keep current local cache as a speed optimization, not source of truth.
3. On cache lookup: validate key/schema/product/date coverage/SHA-256; then use it. If not valid, do exact AppEEARS task discovery/reuse.
4. After successful task completion: parse data, run existing QA, serialize a versioned object, upload to Drive, fetch it back, verify exact bytes/hash, and only then mark cache `available`.
5. Never archive a pending/failed task or a product with no usable values.
6. Add tests for cache hit, cache miss, invalid checksum, Drive outage, exact date-window slicing, product/version mismatch, and no duplicate task POST.

### Phase B — make the first result independent of slow optional SMAP (implemented; live NASA run acceptance remains)

1. Inspect the model's actual use of SMAP fields and define a versioned source dependency contract.
2. Keep NASA POWER as required core weather under the current policy.
3. If SMAP is optional for the current model run, preserve a preliminary result while SMAP remains pending. Clearly mark the missing evidence and which model dimensions are affected.
4. Ensure HLS/MODIS results can be reused from the durable cache on each worker retry.
5. When SMAP is ready, create a new result revision and event without re-submitting the farmer's original request.
6. Add tests proving:
   - a slow optional SMAP source does not block a preliminary revision;
   - required POWER missing still blocks final readiness;
   - the first revision never calls itself final;
   - final revision only follows the configured QA/coverage gates;
   - completed HLS/MODIS data are not downloaded again on later worker retries.

### Phase C — SMAP historical spatial archive (nine-point pilot workflow implemented; national grid archive pending)

1. Commit a verified operational tile geometry covering the intended Bangladesh geography; do not call it official AEZ.
2. Confirm AppEEARS Area request schema and `SPL4SMGP.008` output format with one small 2025 tile/date test.
3. Determine whether area output includes native 3-hour observations and how AppEEARS names/retains each NetCDF/GeoTIFF object.
4. Convert/store data in a versioned gridded format that preserves native cell identity, native time, units, quality/provenance and product version.
5. Use a 2025 pilot to measure size, processing duration and Google Drive object count before enabling 2016–2025.
6. Add a manual GitHub Actions workflow with explicit tile/year inputs, preflight, bounded concurrency, resume semantics and final per-tile summaries.
7. Do not dispatch the full 10-year backfill until the pilot has passed and Drive write/read-back is verified.
8. On each map query, map the selected coordinate/AOI to the actual archived native grid cells. Only then can the tile archive satisfy that field's SMAP requirement.

### Phase D — persistence / ownership acceptance

1. Validate real Magic Link sign-in on the latest matching branch Preview.
2. Submit one real analysis from an authenticated account.
3. Close the browser and return after a worker retry; verify the same run appears in My Runs.
4. Verify request snapshot, source rows, provider task IDs, retry time, lifecycle events, and result revisions survive.
5. Test two accounts and prove each cannot access or recheck the other's run.
6. Verify a result revision advances when SMAP changes from pending to available.

### Phase E — deployment and release gate

1. Obtain a fresh Vercel Preview whose Git SHA equals the current branch head.
2. Confirm required Preview env vars exist without revealing their values.
3. Test `/api/auth/config`, authenticated queue submit, `/api/internal/worker/tick`, My Runs and result retrieval against that exact Preview.
4. Verify Supabase's five-minute worker schedule is single and active; inspect the pg_net HTTP response, not only pg_cron's SQL status.
5. Keep PR #1 Draft/Open/Unmerged and Production unchanged until the user explicitly approves release.

## 9. Acceptance checklist

- [ ] 2025 SMAP archive pilot passes product, spatial, temporal, unit, QA and checksum checks.
- [ ] A map coordinate inside a verified archive cell uses that cell without an AppEEARS point task.
- [ ] A coordinate outside archive coverage does not receive a nearest-reference-point substitution.
- [ ] Completed exact-point SMAP/HLS/MODIS results are persisted to private Google Drive.
- [ ] A repeat exact-coordinate/date-window request reads the shared archive without resubmitting AppEEARS.
- [ ] SMAP optional-pending run can show a clearly labelled preliminary result while background retry continues.
- [ ] No pending source or preliminary revision is marked final.
- [ ] Required core dataset gaps still block final readiness.
- [ ] HLS/MODIS task results are reused across worker retries.
- [ ] AppEEARS task IDs are persisted and exact IDs are resumed; no duplicate task POST.
- [ ] User can return after 1–2 days and retrieve the same run and revision history.
- [ ] Two-account ownership isolation is demonstrated with real Supabase sessions.
- [ ] Every archive write is private and remote read-back/SHA-256 verified.
- [ ] CI passes; Preview SHA equals branch head; Preview smoke passes.
- [ ] PR #1 remains Draft/Open/Unmerged and Production remains untouched until approval.

## 10. Explicit non-goals for this implementation

- Do not bulk-archive all NASA products. The user's latency history justifies **SMAP first**; HLS and MODIS remain live-first with durable on-demand caching.
- Do not silently replace a selected farm coordinate with one of nine regional anchor samples.
- Do not invent or claim official AEZ boundaries.
- Do not call SMAP L4 an in-situ observation or farm sensor.
- Do not turn missing/late values into zero.
- Do not treat modelled climate, synthetic extension, or a preliminary output as observed final evidence.
- Do not let AppEEARS request IDs act as the sole record of completed data.
- Do not make a production deployment, merge PR #1, or alter Production settings as part of this work.

---

## 11. Key conclusion

**Pre-store SMAP first. Keep HLS and MODIS live-first, but persist every completed product result in the shared Drive cache for exact compatible reuse.**

To meet the user's 15–20 minute experience, the website must show a useful, explicitly preliminary analysis as soon as required core evidence is ready, without waiting for SMAP's long-tail AppEEARS task. The worker then enriches the same saved run and writes a new result revision when SMAP completes. This improves responsiveness without pretending that missing SMAP values are available or scientifically validated.
