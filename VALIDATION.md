# Verification record — 8 October 2026, product 3.1.3

The source in this archive passed:

- Full offline Python test suite: **93 passed**.
- Ruff checks of production code, provider regression tests and both smoke scripts: passed.
- Mypy: no issues in 24 source files.
- Python compilation: passed.
- Local API `/health`: `engine=3.0.0`, `product=3.1.3`.
- DOM interaction checks against the local offline API: custom date selection,
  request payload, displayed inclusive dates, invalid-range rejection,
  retry display, stopping checks, manual resume after cooldown, what-if date
  preservation, provider Retry-After display, early-check blocking, Iowa
  coordinates, and local-soil wording. **12 checks passed; no JavaScript errors.**
- The production AppEEARS smoke entry point works with Python site packages
  disabled (`python3 -S run_appeears_smoke.py --help`).

## Regression cases

The provider tests replace the HTTP transport or Earth Engine computation,
not the production task payloads, HTTP error parser, cooldown, or CSV parser.
They verify:

- Both screenshot locations: Mymensingh (24.7471, 90.4203) and Iowa
  (41.4594, -93.0862).
- One unfiltered task list shared across sources, separate valid point tasks,
  sequential HTTP pacing, and catalog/layer cache reuse.
- HTTP 500/429 retain the failing request stage and status code, block outgoing
  requests during the cooldown, and recover afterward. Retry-After supports
  both delay-seconds and HTTP dates. Downloads use the same retry policy.
- A failed POST is not immediately resubmitted; stable names still recover
  previously queued tasks after local cache loss.
- A NEX read timeout after 23 monthly normals preserves those results. The
  next request fetches the single missing month and completes. A missing-band
  error still produces `unavailable`.
- Retry delay, stage and HTTP code reach the website response.
- Earlier integration, date, QA, scenario and offline simulation tests still pass.

## Limits

No authenticated live NASA or Earth Engine requests were run here; no
credentials were supplied. The user's screenshots establish successful POWER
and GPM requests at both locations and successful NEX requests in Mymensingh,
but do not live-validate this update. Mocked tests cannot prove an upstream
500 has disappeared. The new errors identify the endpoint if it recurs.

DOM tests do not render CSS. The mobile grid/word-wrap and map-toolbar changes
were inspected in source; no rendered Chromium screenshot test is claimed.
A browser binary is unavailable in this environment.

An AppEEARS cooldown and NEX partial cache survive requests on the same server
filesystem. Separate cold serverless instances do not share those files. The
browser also honors provider retry delays, and NASA's account task list can
recover submitted AppEEARS jobs. Durable cross-instance NEX progress still
requires shared storage.

Use `FIXES_AND_DEPLOYMENT.md` and `scripts/check_integrations.py` for a
credentialed post-deploy test of the actual website endpoint.
