# Dataset integration repair — 8 October 2026

This archive contains the complete corrected project. Deploy the folder containing
`vercel.json`, `pyproject.toml`, `api/`, `src/`, `config/`, and `data/`.
The new API product version is **3.1.3**.

## Follow-up: Mymensingh and Iowa errors

The new screenshots show AppEEARS HTTP 500 for multiple products at both
locations, plus HTTP 429 in Mymensingh. Iowa also shows an Earth Engine
20-second read timeout for both NEX scenarios. These are request failures;
the screenshots do not establish that the locations have no satellite coverage.

This update makes the following changes:

- Use one unfiltered `GET /task` and match stable task names locally. The older
  connector sent `task_type=point` as a query filter once per product. Removing
  that unnecessary filter is a compatibility repair; the screenshots omit the
  failing endpoint, so the precise cause of their upstream 500 is not proven.
- Submit/process SMAP, MODIS and HLS separately but sequentially, with a
  one-second gap between HTTP requests, including downloads. Cache the product
  catalog and layer metadata for one hour. Preserve existing v4 task identities
  to resume already submitted requests.
- Honor `Retry-After` for HTTP 429 and transient errors. HTTP 5xx and connection
  timeouts also receive a cooldown. Persist the cooldown per account on the
  server filesystem; no requests are sent during that cooldown. A failed task
  POST is not blindly repeated. The next pass checks for an existing task first.
- Show temporary failures as `retrying`, retain the HTTP code and request stage,
  and have the website and both smoke scripts wait before retrying. The browser
  waits at least 30 seconds, up to 20 automatic checks. Manual checks respect
  the same wait. `available` still requires real, quality-filtered observations.
- Treat GEE timeouts as resumable: keep completed monthly normals and request
  only missing months on the next pass. Increase the default per-request GEE
  timeout to 45 seconds. Missing bands and other permanent failures still show
  `unavailable`; no diagnostic scenario is relabeled as NASA data.
- Let long provider errors wrap inside mobile evidence cards; move map controls
  away from the zoom buttons. Use location-neutral wording for missing soil data.

**No existing environment variable was renamed or removed.** No new variable
is required for this update. Keep your current credentials. If Vercel already
has `FIELD_SHIFT_GEE_REQUEST_TIMEOUT_SECONDS=20`, change its value to **45**;
an existing environment setting overrides the new code default. Keep
`FIELD_SHIFT_APPEEARS_WAIT_SECONDS=0`. Then redeploy and confirm `/health`
reports product **3.1.3**. Reopen/reload the site so its updated service worker
can activate.

For the Iowa location in the screenshot, use **41.4594, -93.0862**. The test
script supports `--lat 41.4594 --lon -93.0862` for either smoke-test command.
Start with 1–15 January 2025 to compare against the working SMAP script, then
test the full year. SoilGrids remains optional; no local soil test means an
explicit generic/pilot soil fallback, not a NASA connection failure.

## What the review established

The standalone scripts and the website were not exercising the same workflow.
The supplied scripts use 1–15 January 2025. The old website selected a 2026
window automatically, combined SMAP/MODIS/HLS into one NASA task, and ran a
much larger NEX climate calculation than a simple Earth Engine point sample.
The screenshot establishes that POWER and the GPM Earth Engine path worked
in that deployment; it does not establish why its shared AppEEARS task failed.
The old response discarded the useful provider error and retained only the
exception class. Without the original provider response or server logs, the
precise historical rejection cannot be proven.

Confirmed code defects and repairs:

| Area | Original behavior | Corrected behavior |
| --- | --- | --- |
| AppEEARS isolation | One task/failure affected three satellite sources | Separate SMAP, MODIS and HLS tasks with one shared login token; independent results and failures |
| Product dates | Selected the preferred product without considering its temporal extent | Choose the supported product with the best date overlap, then the configured preference; intersect requests with published availability and label partial coverage |
| SMAP | Namespace-aware matching already existed in the supplied ZIP, but lived inside the shared workflow | Preserve the working `Geophysical_Data_sm_surface` / `sm_rootzone` matching in an independent production task; accept timestamped CSV dates and require actual moisture values |
| GPM evidence | AppEEARS failure created an unavailable GPM entry even when Earth Engine succeeded | GPM uses its own route and has one evidence entry; partial date coverage is labeled |
| Pending jobs | No automatic website follow-up; unhelpful pending coverage | Browser checks pending/retrying sources after at least 30 seconds, respecting provider delays, up to 20 checks; supports stop/check-now; stable NASA task names support reuse after a cold start |
| Failed/expired tasks | Failed account tasks could be reused indefinitely | Adapter-versioned task names and cache keys; failed-task cooldown is ten minutes; expired or missing local task references are re-resolved |
| NEX calculation | One large graph repeatedly aggregated all models and six bands across two 20-year periods; relied on a band-name property filter | Monthly point requests, masked missing-band handling, a disclosed model subset, bounded work per request, cached partial normals, and shared historical normals between SSPs |
| GPM empty dates | Summing an empty collection could produce a bandless image and fail rename | Masked seed band keeps empty dates safe; only days with 48 valid half-hour values are accepted; mm/hour × 0.5 is retained |
| MOD16 | MODLAND_QC interpreted as two bits; all intervals divided by 8 | Read bit 0; bit 1 is the sensor. Short year-end composites use their actual interval length |
| Date selection | No UI controls or end-to-end API fields | Inclusive start/end dates, presets, validation, provider propagation, result/report metadata, and preservation in what-if requests |
| Error messages | Generic exception names | Bounded, credential-redacted provider errors appear in evidence details |
| PWA cache | Some API responses could be cached by the service worker | API requests bypass shell caching; shell cache version updated |

The new `run_appeears_smoke.py` imports the production adapter. It replaces the
missing `appeears_test_common` dependency of the supplied smoke script. Run it
from this extracted project; it does not require third-party Python packages.
The original separate SMAP and GEE scripts were references, not drop-in website
backend modules.

## Deploy and check

1. Replace your project source with this complete folder and redeploy it from
   the same Vercel project. Keep the existing server-side credentials in Vercel.
2. Check the exact environment names below in the active Production/Preview
   environment. Redeploy after changing them. A Termux environment variable or
   a Code Editor login does not configure the deployed Python function.
3. Open `/health`; `product` should be `3.1.3`. Open `/api/status` to check whether
   credentials are present. That endpoint does not validate them remotely.
4. For a like-for-like check, enter latitude **24.7471**, longitude **90.4203**,
   choose **Custom dates**, then **2025-01-01** through **2025-01-15**. Click
   **Run analysis**. Do not use “Load demo field” as proof of live connectivity.
5. Let pending NASA tasks finish; the browser checks them automatically.
   “Available” requires real parsed values. Missing/cloud-masked observations,
   unavailable product dates, invalid credentials, or upstream outages remain
   visible rather than being relabeled as success.

| Variable | Value/action |
| --- | --- |
| `FIELD_SHIFT_LIVE_NASA` | `1` |
| `FIELD_SHIFT_APPEEARS_USER` | Your Earthdata username |
| `FIELD_SHIFT_APPEEARS_PASSWORD` | Your Earthdata password |
| `FIELD_SHIFT_APPEEARS_TOKEN` | Optional; omit if using username/password. A token alone needs manual replacement after expiry |
| `FIELD_SHIFT_APPEEARS_WAIT_SECONDS` | **`0`**; the browser resumes pending jobs |
| `FIELD_SHIFT_GEE_PROJECT` | Your Earth Engine-enabled Google Cloud project ID |
| `FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON` | The complete service-account JSON, as a server-side environment value |
| `FIELD_SHIFT_GEE_REQUEST_TIMEOUT_SECONDS` | `45`; update an existing `20` setting |
| `FIELD_SHIFT_NEX_BUDGET_SECONDS` | `40` per scenario, plus in-flight request time |
| `FIELD_SHIFT_NEX_MODELS` | `ACCESS-CM2,MPI-ESM1-2-HR,MRI-ESM2-0` |
| `FIELD_SHIFT_SOILGRIDS` | Keep `0` unless you have separately verified that provider; NASA fixes do not make this optional service available |

The Earth Engine project must be registered and the service account must have
access. See the official [service-account guide](https://developers.google.com/earth-engine/guides/service_account).
The existing `vercel.json` requests a 300-second function duration. Actual host
limits and slow upstream services can still affect cold requests.

### Verify from Termux

With your existing Earthdata environment variables set, from the extracted root:

```sh
python run_appeears_smoke.py --start 2025-01-01 --end 2025-01-15 --wait 300
```

This resumes separate NASA tasks, checks parsed/quality-filtered data, and saves
`appeears_production_result.json`. Exit 0 means all three sources have usable
observations. A pending task can take longer than five minutes; run the same
command again to resume it.

Check all website integrations using the deployed endpoint:

```sh
python scripts/check_integrations.py --url https://YOUR-PROJECT.vercel.app --start 2025-01-01 --end 2025-01-15
```

The second script needs no local NASA/GEE credentials: the deployed server uses
its environment. It saves `website_integration_result.json` with the same
analysis response used by the browser. Share that report, with any private
field information removed, if a source still fails. Do not share credentials.

## Date and climate semantics

- The maximum observation window is 366 days, inclusive of both endpoints.
  Future observations, invalid calendar dates and reversed ranges are rejected.
- The browser defaults to the last complete calendar year. “Recent 90 days”
  ends 14 days before today; provider latency may be longer.
- POWER, GPM and AppEEARS use the selected observation window. POWER also keeps
  its existing seven-day freshness buffer; evidence reports actual returned
  coverage. AppEEARS checks each product's published date extent.
- The crop simulation still needs a complete three-year calendar. For custom
  ranges it starts in the selected start year. Dates outside retrieved weather
  are explicitly synthetic, including dates before a midyear start date.
- NEX compares historical **1995–2014** with **2041–2060**. The observation
  selector does not redefine those fixed climate-normal periods.
- The default three-model subset is an interactive approximation, **not the full
  CMIP6 ensemble**. The selected models appear in provenance. Each model has
  equal weight, and all configured models must supply usable monthly values.
  Changing `FIELD_SHIFT_NEX_MODELS` changes the cache identity; use a separate
  offline/batch workflow if you need a full-ensemble scientific assessment.
- AppEEARS tasks can be recovered from NASA's account task list across Vercel
  instances. AppEEARS cooldowns, partial NEX caches and analysis history are local to an instance;
  cold starts may recompute them. A shared cache/database is still needed for
  durable history and consistent progress at larger scale.

## Verification of this repair

See `VALIDATION.md` for executed checks. Authenticated live NASA/GEE calls were
**not** validated in this workspace: no credentials were supplied, and a public
AppEEARS catalog request timed out. Existing historical validation documents
are not proof that this repaired production path has been live-tested.

Primary API references used during the repair:

- [AppEEARS API: catalog extents, authentication, task and bundle schema](https://appeears.earthdatacloud.nasa.gov/api/)
- [GPM IMERG V07: units and half-hour cadence](https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_V07)
- [NEX-GDDP-CMIP6: model names and missing-band caveats](https://developers.google.com/earth-engine/datasets/catalog/NASA_GDDP-CMIP6)
- [MOD16 collection 6.1 user guide: composite periods and quality flags](https://modis-land.gsfc.nasa.gov/pdf/MOD16C61UsersGuideV11Mar112021.pdf)
