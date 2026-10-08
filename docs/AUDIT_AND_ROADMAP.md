# KrishiNexus / FieldShift readiness audit

Audit date: 2026-10-06  
Scope: provided source archive and `KrishiNexus_Project_Summary_Fixed.pdf`. Ratings are this code review's estimates, not NASA or investor scores.

## Current rating

| Goal | Rating | Readout |
|---|---:|---|
| NASA Space Apps challenge prototype | 7/10 | Strong decision-support concept, thoughtful evidence lineage, multiple climate scenarios, uncertainty-aware ranking, and a working demo path. The submission still needs a verified live-data run, accurate claims, a short human-centered story, and local validation evidence. |
| Bangladesh startup pilot | 4/10 | A credible technical MVP for a supervised Mymensingh pilot. It is not yet a dependable farmer-facing service: live provider credentials are optional, analysis records are process-local, and the crop/soil pack is not calibrated across Bangladesh. |
| Nationwide production service | 2/10 | The code and import paths are extensible, but national agronomy, secure user accounts, durable data, consent, monitoring, support, and independent field validation are not delivered. |

## What is already implemented

- A deterministic rotation engine scores crop sequences against farmer priorities and operational limits.
- V3 includes explicit water accounting, soil nutrient unit conversions, a soil-carbon trajectory proxy, and input-level Monte Carlo uncertainty.
- The product has a mobile-friendly PWA, Mymensingh demo snapshot, soil input form, evidence/provenance panel, strategy comparison, scenario lab, what-if controls, and report export.
- NASA POWER daily weather is attempted in live mode on Vercel. NASA AppEEARS sampling for SMAP, MODIS, and HLS is optional and needs Earthdata credentials; GPM IMERG is routed through Earth Engine. NEX-GDDP-CMIP6 access through Earth Engine is optional and needs Google credentials. Each has a fallback or missing-evidence state.
- The Vercel entry point, FastAPI app, package metadata, `vercel.json`, Dockerfile, and CI workflow are present. Source inspection alone cannot establish that a specific Vercel deployment built or that its secrets were injected correctly.

## Important gaps and claims to correct

1. **SAR is described in the PDF but not implemented in this archive.** I found no Sentinel-1/NISAR SAR ingestion, radar backscatter processing, inundation detector, or SAR product tests. Do not claim a custom SAR monsoon layer until it is built and evidenced.
2. **The LLM reasoning layer and numeric grounding checker are described in the PDF but not implemented.** The delivered explanation path is deterministic. That is a useful and safer prototype; describe it accurately.
3. **“Real-time” and “field-level satellite moisture” overstate the evidence.** POWER is a daily source with latency and a recent-data buffer; multi-year runs extend weather synthetically. Satellite values are grid/point samples whose native scale and quality vary by product. Present them as contextual observations, not parcel-scale ground truth.
4. **The product pack is a Mymensingh pilot, not Bangladesh-wide agronomy.** Other locations can be analyzed, but the same crop library, prices, calendars, and scoring thresholds are not nationally validated.
5. **Future-climate outputs need careful labels.** The GEE path forms monthly climate signals from NEX-GDDP-CMIP6 and applies them to a dated daily analogue; without that connector, scenarios are diagnostic stress tests. Neither path is an operational forecast.
6. **Production state is not durable.** Analysis results are held in process memory. The browser's current what-if and report calls send a client-held snapshot, but API GET routes for a newly created analysis can fail when Vercel routes the next request to another function instance. Add a durable store before relying on run history or multi-device use.
7. **A preview coordinate match is not local field validation.** The API now labels the Mymensingh rectangle as a pilot-area hint and does not claim a field is validated.
8. **External review is still needed.** Crop parameter sources, Bangladeshi crop calendars, yield/price assumptions, soil proxies, and satellite residuals need review by local agronomists and comparison with measured field data.

## Vercel/API findings

The repository wiring is structurally plausible: Vercel can detect FastAPI from Python project dependencies, `api/index.py` exports a top-level `app`, and the function includes the config, V3 data, and static assets it needs. The current official Python runtime documentation describes FastAPI support and dependency discovery from `pyproject.toml` or `requirements.txt` ([Vercel Python runtime](https://vercel.com/docs/functions/runtimes/python), [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)).

No deployed URL, Vercel build output, function logs, or Vercel environment settings were provided, so this review cannot confirm the live deployment or identify a specific production failure. A new `GET /api/status` endpoint reports whether variables were injected, without returning their values. It explicitly does not claim to validate credentials or test provider connectivity.

- NASA POWER is public and needs no API secret. Vercel enables its live requests by default; failures should be visible in the analysis evidence and may fall back to synthetic weather.
- AppEEARS requires `FIELD_SHIFT_APPEEARS_USER` and `FIELD_SHIFT_APPEEARS_PASSWORD` as server-side Vercel variables.
- The optional Earth Engine connector requires `FIELD_SHIFT_GEE_PROJECT` and `FIELD_SHIFT_GEE_SERVICE_ACCOUNT_JSON` as server-side variables.
- Add variables to the Vercel environment that serves the deployment, save them, then redeploy. Never prefix credentials with `NEXT_PUBLIC_`.
- `/health` confirms the app booted. `/api/demo` returns a saved demo and does not prove a live NASA connection. Use `/api/status` to check configuration, then run an analysis and inspect its evidence panel for source status, dates, fallback, and errors.
- The product UI uses same-origin API calls; CORS is not required for this deployment shape. The wildcard CORS middleware was removed.

See [VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md) for a deployment checklist and diagnosis guide.

## Credential handling

The supplied ZIP contained real NASA Earthdata and Google service-account credentials in files named like templates, plus a separate service-account JSON file. Those files have been removed from this cleaned project, and `.env.example` now contains blank credential fields. The original ZIP and its Git history are unchanged.

Treat those credentials as exposed: change the NASA Earthdata password and revoke/delete the exposed Google service-account key, then create a replacement only if still needed. Review and clean any Git repository/history or deployment logs where the old values may have been committed. Removing files from this cleaned ZIP does not revoke credentials or erase copies elsewhere.

## Checks run for this cleaned archive

- Python source compilation: passed.
- Inline JavaScript syntax check: passed.
- JSON data-file parsing: passed for all nine JSON files in the clean source tree.
- Packaging review: passed; the output excludes `.git`, credential files, and local caches, and its environment template has blank credential values.
- The Python test suite and HTTP smoke tests were not rerun because this audit workspace does not have the project's FastAPI, PyYAML, pytest, or Uvicorn dependencies installed. The deployed Vercel API and external NASA/GEE connectivity remain unverified without a deployment URL and logs.

## Recommended completion order

### Before a NASA Space Apps submission

1. Rotate the exposed credentials; verify the clean archive contains no credential material.
2. Deploy from the repository root and capture `/health`, `/api/status`, plus one analysis evidence panel with retrieval dates and source/fallback labels.
3. Reword the summary to match implemented code, or implement SAR and the LLM layer with tests, product-specific quality handling, and a clear demonstration.
4. Record a short end-to-end demo: a Bangladesh field, farmer priorities, a real source with provenance, strategy trade-offs, uncertainty, and one limitation.
5. Have a Bangladesh agronomist review crop assumptions and a farmer or extension worker review whether the advice is understandable and actionable.

NASA Space Apps lists awards including Best Use of Science, Best Use of Data, Best Use of Technology, and Local Impact; the strongest evidence for this project is a transparent, reproducible decision trace and a clearly scoped local impact story ([2026 event page](https://www.spaceappschallenge.org/2026/), [awards overview](https://www.spaceappschallenge.org/2025/awards/)).

### Before a real Bangladesh startup pilot

1. Add a durable database/cache with tenant isolation, retention rules, backups, and access control; replace process-local analysis state.
2. Add authentication and roles for farmers, extension staff, researchers, and administrators; document consent and data deletion.
3. Validate input ranges and field boundaries, then pilot in one Mymensingh upazila with consented ground measurements and local agronomists.
4. Calibrate crop yields, calendars, costs, prices, and soil/water parameters using held-out seasons and farms. Report bias and error by crop, season, and location.
5. Add monitoring for API latency, upstream failure rates, fallback frequency, stale data, cost, and user-reported outcomes.
6. Expand to other agroecological zones only after region-specific crop packs and validation are reviewed. Add Bangla-first onboarding, low-bandwidth behavior, and assisted/voice workflows with local users.
7. Add a radar/SAR module only with a defined product, units, native resolution, quality flags, date handling, licensing, validation labels, and a demonstrated decision benefit.

Until those steps are complete, position KrishiNexus as an evidence-aware decision-support prototype for supervised trials, not an autonomous planting instruction or nationwide agronomy service.
