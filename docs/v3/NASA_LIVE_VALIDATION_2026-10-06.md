> Historical release notes. For the 7 October repair, use [FIXES_AND_DEPLOYMENT.md](../../FIXES_AND_DEPLOYMENT.md). The earlier smoke results do not establish that the new production queries have been live-validated.

# NASA Live Validation — 2026-10-06

This record documents operator-run external validation of the release candidate. No credentials, tokens, service-account keys, or exact field coordinates are stored here.

## Results

| Source | Path | Result | Evidence observed |
|---|---|---|---|
| NASA POWER Daily | NASA POWER API | PASS | 15 daily records returned with six requested parameters |
| NASA SMAP | AppEEARS `SPL4SMGP.008` | PASS | Bearer-token login, point task completed, 120 CSV rows returned; namespaced surface/rootzone layers resolved |
| NASA MODIS MOD16 | AppEEARS `MOD16A2GF.061` | PASS | Point task completed and usable dates were returned |
| NASA HLS | AppEEARS `HLSS30_VI.020` | PASS | Point task completed and usable dates were returned |
| NASA GPM IMERG | Earth Engine `NASA/GPM_L3/IMERG_V07` | PASS | 144 half-hourly images found for a 3-day check; 3 daily aggregates produced |
| NASA NEX-GDDP-CMIP6 | Earth Engine `NASA/GDDP-CMIP6` | PASS | `ssp245` and `ssp585` image collections returned data and point samples for all nine inspected weather bands |

## Interpretation

All six NASA data acquisition paths used by FieldShift have been externally smoke-tested. The AppEEARS path uses a server-side Bearer token lifecycle; GPM uses Earth Engine because the observed AppEEARS catalog did not expose an IMERG product.

These checks validate connectivity and data retrieval, not local agronomic calibration. Bangladesh-specific yield validation, field soil calibration, and any causal or predictive performance claims remain separate evidence requirements.
