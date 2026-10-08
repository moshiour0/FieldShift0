## 3.1.1 — NASA connector hardening

- Reuses and refreshes AppEEARS Bearer tokens server-side; bundle downloads now retry once after an expired-token 403.
- Resolves namespaced AppEEARS SMAP layers such as `Geophysical_Data_sm_surface` and `Geophysical_Data_sm_rootzone`.
- Reports catalog-missing authenticated sources as `unavailable` instead of `not_configured`.
- Routes NASA GPM IMERG V07 through Earth Engine and keeps the 30-minute-to-daily conversion explicit.
- Aligns Python dependency declarations and fixes the TestClient `httpx` development dependency.
- Adds the 2026-10-06 external NASA smoke-validation record.

# V3 change log

## 3.0.0

### Confirmed V2 defects fixed

- `rank_p90` now comes from simulated rank samples rather than score percentiles.
- Rotation generator dead branch and duplicate traversal removed.
- NASA POWER missing values are imputed locally when gaps are recoverable; retries and disk caching were added.
- Irrigation is now split into gross withdrawal, effective root-zone input and reliability loss; water is conserved with runoff/drainage/storage terms.
- Nutrient balances convert mg/kg concentrations to kg/ha using bulk density and soil depth, with explicit availability fractions.
- Remote indicators never inject a synthetic 0.5 neutral value into the evidence bundle when observations are absent.

### Scientific upgrades

- Absolute feature scales replace candidate-relative min/max normalization.
- Input-parameter Monte Carlo reruns crop/soil/economic inputs through the pipeline.
- Risk tolerance contributes to the risk-adjusted ranking statistic.
- Budget, labour, water and avoided-crop constraints are active.
- Soil carbon is simulated over a multi-year horizon.
- Water runoff uses SCS-CN; deep drainage and paddy percolation/seepage are explicit.
- SMAP initializes crop-cycle soil moisture when a nearby observation exists.
- MODIS/HLS/SMAP data feed an observation-consistency dimension when available.
- Yield stability uses scenario downside + scenario CV rather than reusing yield potential features.

### Productization

- `pyproject.toml`, CLI, optional API dependencies, Dockerfile and GitHub Actions workflow added.
- FastAPI application + responsive web UI added.
- V3 package and configuration are isolated from V2 for compatibility.

## V3.1 Product Experience

- Added world-class farmer-facing product architecture and responsive web experience.
- Added product/BFF API contracts under `/api/analysis/*` while preserving `/api/v3/*` compatibility.
- Added map-based field context, movable field marker, simple field-boundary drawing and field constraints.
- Added evidence-first source states and provenance drawer.
- Added guided farmer priorities and explicit priority-blend preview.
- Added rotation explorer, trade-off comparison, climate lab and scenario comparison.
- Added counterfactual what-if analysis for lower water, lower irrigation reliability and lower labour availability.
- Added decision report, JSON export, print path and PWA shell caching.
- Added product API regression coverage.

## NASA connector hardening — 2026-10-06

- AppEEARS now caches its Bearer token in-process, supports an optional server-side `FIELD_SHIFT_APPEEARS_TOKEN`, and refreshes the token once after an authenticated HTTP 403. This follows the AppEEARS API authentication guidance.
- AppEEARS layer discovery now accepts provider namespace prefixes such as `Geophysical_Data_sm_surface` while preserving the exact provider layer name in task requests.
- NASA GPM IMERG was removed from AppEEARS discovery and routed through Google Earth Engine `NASA/GPM_L3/IMERG_V07`; half-hour precipitation is aggregated to daily UTC totals.
- Evidence statuses now distinguish AppEEARS product discovery/authentication from GPM Earth Engine configuration.
- Added GPM Earth Engine cache support via `FIELD_SHIFT_GPM_GEE_CACHE_TTL_SECONDS`.
