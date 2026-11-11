# FieldShift — NASA Space Apps 2026 Challenge Readiness Audit

**Audit date:** 12 November 2026  
**Repository:** `moshiour0/FieldShift0`  
**Production:** https://field-shift0.vercel.app  
**Scope:** NASA Space Apps 2026 — “Field Shift: Adapting Farms with NASA Data”

> This is an implementation and evidence audit, not an official NASA score. A feature is counted as complete only when its behaviour is implemented and the supporting data or verification exists. A configured credential, modelled fallback, demo snapshot, or code-path alone is not proof of live data coverage or field validity.

## Executive assessment

FieldShift already has a production decision-support application, an interactive field workspace, a crop-rotation engine, farmer constraints and priorities, comparative strategy scoring, input-level Monte Carlo uncertainty, scientific provenance, and a durable signed-in analysis queue.

It is **not scientifically or operationally defensible to declare 100% completion yet**. The remaining gaps are not mostly cosmetic: local crop/economic calibration, local soil evidence, field-boundary satellite aggregation, complete provider retrieval, climate-projection provenance, and real field-outcome validation require evidence that cannot be fabricated in software.

The core software release is live. The current readiness blockers are itemized below so a future release can close them with evidence instead of optimistic labels.

## Challenge-objective mapping

| Challenge objective | Implementation evidence | Acceptance state |
|---|---|---|
| Farmer-centred decision-support tool | Responsive web UI; field coordinates and area; previous crop; observation window; irrigation, reliability, budget and labour constraints; soil inputs; six farmer priorities | **Implemented; usability validation remains** |
| Compare at least three rotation strategies including current practice | Baseline rotation `Boro rice → Aman rice`; generated calendar-feasible alternatives; ranking and comparison of water, yield, return and labour | **Implemented; crop library remains a regional pilot/proxy** |
| Explain why a strategy is suggested | Multi-dimension scoring, strategy explanations, constraints, evidence lineage and uncertainty statements | **Implemented; input-source quality limits conclusions** |
| Use NASA Earth observations | NASA POWER daily weather; AppEEARS support for SMAP, HLS and MODIS MOD16; GPM through Earth Engine; NEX-GDDP-CMIP6 file/GEE pathway | **Partially live; each provider must be verified separately** |
| Combine local soil information | Farmer/lab soil fields; Mymensingh pilot soil estimates only close to pilot coordinates; nearest licensed soil-point CSV adapter; optional SoilGrids adapter | **Partial; no validated district/national soil layer or farm test for arbitrary fields** |
| Explore water, heat, vegetation, ET and climate pressure | FAO-56 ET0, root-zone water balance, runoff, soil-carbon proxy, heat/water stress, MODIS ET, HLS vegetation features and climate scenarios | **Implemented as mixed observed/modelled indicators; source gaps remain visible** |
| Quantify uncertainty and explain model limitations | Input-parameter Monte Carlo for crop, soil and economic inputs; structural water-balance checks; absolute feature scales; provenance labels | **Implemented; external agronomic calibration remains** |
| Geospatial visualization | Interactive map, field-centre marker, drawn boundary, coordinates and area | **Partial; current NASA point adapters sample the centre, not a polygon-wide field average** |
| Scientific validation | Unit/integration tests, water mass-conservation checks, source-specific QA handling and reproducible engine tests | **Software validation exists; field/outcome validation is not complete** |
| Reopen and inspect a saved run | Supabase owner-scoped runs, worker queue, versioned results and private Drive result archive | **Pointer defect repaired in the live database; end-to-end browser restore still needs a post-release test** |

## Evidence status observed in a real signed-in run

The run below was created through the deployed application. These values describe one field point and one requested 2025 observation window; they are not national or district-wide coverage claims.

**Run:** `3e492282-4503-4842-b0ad-5c3f6199c4e6`  
**Field centre:** 22.5093, 89.8297  
**Requested observations:** 2025-01-01 to 2025-12-31  
**Field area entered:** 0.4 ha

| Source | Observed state | Correct interpretation |
|---|---|---|
| NASA POWER Daily weather | 365 daily records | Gridded point weather for the submitted coordinate; not an in-situ field sensor |
| NASA HLS | 71 usable observation dates | Cloud/shadow-masked vegetation-index observations; not daily coverage |
| NASA MODIS MOD16 | 45 usable observation dates | 8-day ET composites with MODLAND QC=0 retained |
| NASA SMAP | 0/365 at first processing attempt; pending | No valid daily root-zone values were available in that attempt; retry may reuse an archive or attempt AppEEARS |
| NASA GPM IMERG | Not configured | POWER precipitation fallback is not GPM data |
| ISRIC SoilGrids | Not configured | No SoilGrids values were used |
| NASA NEX-GDDP-CMIP6 | Real SSP files/usable response unavailable | SSP scenario views use labelled diagnostic stress-test deltas, not NASA projections |
| Local field soil profile | Not supplied | Missing soil inputs remain unknown/defaulted with low confidence; not local soil measurements |
| Three-year simulation outside the observation period | Synthetic extension | Explicitly labelled synthetic weather, not NASA observations |

The analysis initially produced preliminary revisions. A production persistence defect left `analysis_runs.latest_result_id` empty even though current result rows existed. A narrowly scoped database trigger was applied to keep this pointer synchronized and backfill the affected real runs. Verification confirmed the two existing runs now reference their current result revisions. This repairs the pointer; a signed-in browser restore and private Google Drive read-back must still be checked after the code release.

## Scientific and spatial limitations that must stay explicit

1. **Point versus field area.** The submitted polygon is retained as farmer-provided geometry, but current POWER/AppEEARS adapters still sample the field-centre point. Do not describe these data as a zonal mean over the full polygon.
2. **Soil is not observed everywhere.** The bundled soil profile is a Mymensingh pilot estimate. Outside that pilot, no such values are silently copied. A farmer estimate is not a laboratory report; generic physical defaults are not a soil survey.
3. **Crop values are not yet calibrated locally.** The six current crop entries (Boro rice, Aman rice, Jute, Wheat, Mustard and Lentil) contain proxy yield, price, cost, coefficient and response values marked as placeholders. BRRI variety values must be attached to a named variety and season, not silently substituted for a generic crop parameter.
4. **Diagnostic climate stress tests are not climate projections.** The fallback SSP2-4.5/SSP5-8.5 deltas must not be described as NASA NEX-GDDP-CMIP6 data when no matching projection dataset was retrieved.
5. **Provider configuration is not provider success.** AppEEARS, Earth Engine and Drive credentials have distinct purposes. A Drive archive secret is not an Earth Engine credential. An HTTP 200 or configured flag does not prove an upstream dataset was returned.
6. **Satellite products have different spatial and temporal support.** SMAP L4 is a 3-hourly, approximately 9 km assimilated geophysical product; MOD16 ET is an 8-day, 500 m composite; POWER meteorology uses source-specific gridded resolution. These should not be presented as equivalent field-scale measurements.

## What “100% challenge-ready” should mean

The project can close every software requirement, but scientific completion needs a field-validation evidence pack. The following gates define a defensible 100% acceptance target.

### A. Product and operational gates

- [ ] Production PR containing the result-pointer, field-input, geometry and provider-routing fixes is merged.
- [ ] GitHub CI passes Python 3.11 and 3.12, including tests, compileall, Ruff and mypy.
- [ ] Production deploy is READY on the merged `main` SHA.
- [ ] A signed-in user can submit an analysis, close the browser, reopen My Runs, restore the same result and inspect each source.
- [ ] The restored result is read from the private archive and its byte count/SHA-256 are verified.
- [ ] The run summary echoes the submitted coordinate, area, date range, irrigation reliability and whether a boundary was supplied.
- [ ] A user-drawn boundary is clearly distinguished from the point support of the current satellite extraction.

### B. NASA evidence gates

- [ ] A real AppEEARS task is completed for each supported requested product; task IDs, product version, layer, QA rule, date coverage, spatial support and retrieval mode are persisted.
- [ ] SMAP values pass the product-specific checks. For SPL4SMGP, describe values as assimilated L4 geophysical estimates; do not claim they are in-situ measurements.
- [ ] GPM is enabled only with a genuine Earth Engine retrieval or a validated, provenance-rich source file; POWER rainfall must remain labelled as POWER.
- [ ] HLS cloud/shadow and any returned QA layers are applied and their coverage is reported.
- [ ] MOD16 8-day ET sums, interval lengths and ET_QC are decoded correctly; do not treat an 8-day composite as a daily instantaneous reading.
- [ ] Actual coordinate-matched NEX-GDDP-CMIP6 historical/future monthly normals or daily inputs are present before calling the SSP views NASA projections.
- [ ] Any unavailable or incomplete date is retained as missing/pending; no satellite variable is filled by synthetic weather.

### C. Bangladesh agronomic and soil evidence gates

- [ ] Every crop has a documented regional source for sowing/harvest windows, duration, water response, heat/flood response, crop coefficients and management requirements.
- [ ] Rice recommendations use the appropriate BRRI variety, season and regional suitability; variety-specific yield figures are not treated as guaranteed farm yields.
- [ ] Jute, wheat, mustard and lentil parameter sources are linked to the relevant Bangladesh research/extension source, with year and variety/cultivar context.
- [ ] Soil values come from a dated field/lab test or a documented local sample whose distance, spatial support, institution, licence and uncertainty are shown.
- [ ] SoilGrids is used only with an operational official service and a scale caveat; the global model is not treated as a farm test.
- [ ] Missing pH, SOC, texture, bulk density, water capacity or nutrients remain explicitly unknown/estimated.

### D. Field-outcome validation gates

- [ ] At least one target region has paired field observations: field boundary, soil report, crop variety, planting/harvest dates, management, irrigation, yield and price.
- [ ] The model is calibrated on one group/season and evaluated on a separate holdout group/season. Do not score on the same records used for calibration.
- [ ] Yield, seasonal irrigation demand, soil indicator proxies and crop-calendar feasibility have documented error metrics and confidence intervals.
- [ ] At least three strategies are reviewed by a local agronomist or extension professional; the baseline remains visible.
- [ ] The farmer report includes assumptions, data gaps, scenario provenance, sensitivity, economic price basis and a non-guarantee statement.

## Recommended authoritative references

- [NASA Space Apps 2026 — Field Shift challenge](https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/)
- [Bangladesh Agro-Meteorological Information Service (BAMIS) crop-weather calendar](https://www.bamis.gov.bd/en/calendar)
- [BRRI Rice Profile — variety, season, life duration and yield information](https://riceprofile.brri.gov.bd/varieties)
- [BRRI official rice variety catalogue](https://brri.gov.bd/pages/static-pages/6922dc75933eb65569e107be)
- [NASA NSIDC SMAP L4 SPL4SMGP Version 8](https://nsidc.org/data/spl4smgp/versions/8)
- [NASA MOD16A2GF.061](https://doi.org/10.5067/MODIS/MOD16A2GF.061)
- [NASA POWER data resolution FAQ](https://power.larc.nasa.gov/docs/faqs/data/)
- [ISRIC SoilGrids documentation](https://docs.isric.org/globaldata/soilgrids/)
- [ISRIC SoilGrids WCS documentation](https://docs.isric.org/globaldata/soilgrids/WCS.html)

## Release decision

**Software foundation:** substantial and production deployed.  
**Live multi-source coverage:** incomplete and provider-dependent.  
**Local agronomic validity:** not yet established outside the Mymensingh pilot.  
**Field-scale spatial evidence:** polygon persistence is supported, but current satellite values remain centre-point samples.  
**Challenge completion:** do not label the project 100% until the relevant product and field-validation gates above are backed by real evidence.
