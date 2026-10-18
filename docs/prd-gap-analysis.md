# PRD gap analysis: Indonesia Wildfire Tracker

Date: 2026-10-17. Compared: *Indonesia Wildfire Tracker — PRD* (Oct 17, 2026) against the repo at
`d0aa9da` (pipeline `pipeline/src/haze/*.py`, web `web/src/*`, `.github/workflows/*`, `README.md`, `docs/`).

Status key:

- **Done**: implemented as the PRD describes, or with a documented equivalent.
- **Partial**: some of it exists, or it exists in a different form. The gap is stated.
- **Missing**: nothing in the repo.

Phase tags: v1 = public launch scope, v2/v3 = later phases. Items the PRD does not mention are in
section 12 and marked "not in PRD".

## 1. Summary

| Scope | Done | Partial | Missing | Total |
| --- | --- | --- | --- | --- |
| Goals and success metrics (§2) | 2 | 6 | 2 | 10 |
| Users and use cases (§3) | 2 | 5 | 3 | 10 |
| v1 features (§4) | 4 | 5 | 1 | 10 |
| v2 / v3 features (§4) | 0 | 0 | 6 | 6 |
| Data sources (§5) | 6 | 5 | 7 | 18 |
| Architecture and stack (§6) | 7 | 5 | 0 | 12 |
| Data model (§7) | 4 | 3 | 1 | 8 |
| 3D visualization (§8) | 5 | 6 | 3 | 14 |
| Risks and mitigations (§9) | 6 | 3 | 1 | 10 |
| Open questions (§10) | 2 | 2 | 2 | 6 |
| Milestone exit criteria (§11) | 0 | 5 | 2 | 7 |
| Cross-cutting NFRs (§12) | 2 | 9 | 6 | 17 |
| **All** | **40** | **54** | **34** | **128** |

Without the 13 rows tagged v2/v3 (6 features, 4 sources, E7, U6, and alerts in §12): 40 Done, 54 Partial,
21 Missing.

The fire core is strong: ingest, masking, tagging, clustering, stable ids, event pages, the 3D map,
the per-event timeline, smoke and wind, the dashboard and Bahasa. What's missing is mostly launch
plumbing (hosting, 30-minute cadence, monitoring, OG previews, load and Lighthouse tests), the
national timeline, AQ stations, context layers, export, and a few things users explicitly asked for
(near me, sort and filter events, today vs yesterday).

## 2. Goals and success metrics

| # | Requirement | Status | Evidence / gap |
| --- | --- | --- | --- |
| G1 | Every active fire within ~3 h of overpass (v1) | Partial | `pipeline.yml` cron is `17 */2 * * *` (every 2 h, not 30 min). With FIRMS NRT at ~3 h, median overpass-to-map is likely 3–5 h. Dashboard `lag_hours` (`publish.py` `dashboard()`) is the age of the newest detection, not ingest latency. |
| G2 | Fires as events: start, growth curve, intensity, status | Done | `events.py` `summarise()`/`snapshots()`, `status_for()` (24 h / 72 h in `config.py` `StatusParams`). Event page JSON has daily `area_ha`, `growth_ha`, `frp_sum`, `peak_frp`. `EventPanel.tsx` charts. |
| G3 | Scrub a timeline and watch each fire grow, in 3D | Partial | Per-event: `EventPanel.tsx` range + play; `MapView.tsx` footprints by `dayIndex` on 3D terrain. National scrubber missing: `days/{date}.geojson` is published but never loaded by the web. |
| G4 | Smoke now and 48–72 h drift; which cities get haze | Done | `smoke.py` (CAMS PM2.5 via Open-Meteo, puff model, `city_outlook()`); `Controls.tsx` `ForecastBar` (0–72 h) and `Cities`. |
| G5 | Readable by non-experts on mid-range Android | Partial | 2D by default under 760 px, bottom sheets (`App.tsx` `isSmall`, `styles.css` `@media`). Not tested on a device. Initial payload is heavy: `live.json` 2.8 MB, `hotspots_recent.json` 0.86 MB, `plumes.json` 0.82 MB, JS 1.0 MB (283 KB gzip, one chunk). |
| M1 | Detection latency median < 3 h, measured from FIRMS acq vs ingest time | Partial | `hotspots.ingested_at` and `runs.latest_acq_time` exist (`db.py`), but nothing computes or publishes the median `ingested_at − acq_time`. The 2 h cron works against the target. |
| M2 | Clustering ≥ 90% of 100 events judged correct | Partial | `docs/clustering-evaluation.md`: 98% if ambiguous calls count as correct, 76% if not. Single non-expert reviewer. |
| M3 | Static false positives removed ≥ 95% | Partial | `mask.py`. 94–97% of FIRMS-flagged volcano/static detections are masked (eval doc §4). No independent ground-truth list. |
| M4 | First load on 4G < 4 s (Lighthouse, mid Android) | Missing | No Lighthouse run, budget or CI check. Payload sizes above make < 4 s unlikely without changes. |
| M5 | Pipeline uptime ≥ 99% via cron health checks | Missing | `runs` table records ok/fail (`pipeline.record_run`), but no health check, alert or uptime report. A failed workflow only shows in Actions. |

## 3. Users and use cases

| # | Requirement | Status | Evidence / gap |
| --- | --- | --- | --- |
| U1 | Residents: see nearest fires | Missing | No geolocation, "near me" or place search. |
| U2 | Residents: smoke forecast for their kabupaten | Partial | `cities.json` covers big towns (pop ≥ 250k or PPLA) plus 5 regional cities; `Cities` shows only the top 8. No kabupaten lookup. |
| U3 | Journalists: sort events by size and growth | Partial | Only `top_growth` (10 published, 8 shown in `Dashboard.tsx`). No sortable list by size or FRP, even though `events/{season}.json` has the data. |
| U4 | Journalists: share a link to one fire's timeline | Partial | `#/event/<id>?lang=en` (`App.tsx` `readHash`). The timeline day isn't in the URL. Links to single-detection events break (no page is published, `publish.py` `hotspot_count > 1`), and so do events from a previous season (`loadEvent(dash.season, …)`). |
| U5 | Responders: filter new events since last pass | Missing | Only the `new_today` count. No filter, highlight or "since last pass" view. |
| U6 | Responders: kabupaten alerts (v2) | Missing | v2. |
| U7 | Researchers: national dashboard, season comparison | Done | `Dashboard.tsx` + `publish.dashboard()`; 2015/2019/2023 baselines, S-NPP only. |
| U8 | Researchers: export events as CSV/GeoJSON | Partial | Raw files exist (`events/{season}.json` columnar, `events/live.geojson`, `days/*.geojson`). No CSV, no download UI. |
| UC1 | "What's burning right now": national 3D, events sized by intensity | Done | `MapView.tsx` national tilted view; flames/glow sized by `totalFrp`; columns available. |
| UC4 | "How bad is this season": by province, today vs yesterday, season vs past | Partial | By province and season comparison done. Today vs yesterday missing. |

(UC2 "show me this fire", UC3 "where is the smoke going" and UC5 "share it" are covered by G3/G4,
§4 and §12.)

## 4. Product scope

### v1 features

| # | Feature (priority) | Status | Evidence / gap |
| --- | --- | --- | --- |
| F1 | 3D national map, glowing columns extruded by FRP (P0) | Partial | `MapView.tsx` `columns` fill-extrusion, height √total FRP, colour by status. **Off by default** (`App.tsx` `columns: false`, layer `visibility: "none"`); particle flames (`fire3d.ts`) are the default. |
| F2 | Fire events: named, start, last seen, size, peak FRP, status (P0) | Done | `events.py`, `fire_events` (`db.py`), ids `<kabupaten>-<YYYYMMDD>-<n>` via `event_registry`; name `"<town>, <kabupaten>"`. |
| F3 | Event timeline: per-event and national scrubber, daily growth, play/pause (P0) | Partial | Per-event done (`EventPanel.tsx`, 1 day/s). National scrubber missing. |
| F4 | Event page: fly-to, growth and intensity curves, peat flag, region, nearest town, URL (P0) | Done | `EventPanel.tsx`, `MapView.tsx` `fitBounds` at pitch 62. Caveats under U4. |
| F5 | Smoke layer: CAMS PM2.5 overlay, animated wind particles, 72 h slider (P0) | Done | `smoke.py`, `smoke.ts`, `windParticles.ts`, `ForecastBar`. CAMS comes through Open-Meteo, not ADS (§5). |
| F6 | Air quality: ground PM2.5 stations by category (P1) | Missing | No OpenAQ/ISPU ingest, no `aq_readings`, no layer. Only ISPU bands applied to CAMS model values (`smoke.py` `ISPU_PM25`). |
| F7 | National dashboard: active, new today, top 10 growth, by province, season vs 2015/2019/2023 (P0) | Partial | All present except: 8 of 10 shown; the province table drops hotspots; "today vs yesterday" (UC4) missing. |
| F8 | Context layers: KHG peat, admin boundaries, days since rain (P1) | Partial | Provinsi lines from OpenFreeMap only (`MapView.tsx` layer `provinsi`). Peat is only an event flag, not a layer. No kabupaten boundaries. No days since rain. |
| F9 | Data export CSV/GeoJSON per day (P2) | Partial | See U8. |
| F10 | Bahasa Indonesia + English, Bahasa default (P1) | Done | `i18n.ts`, default `id`, `index.html lang="id"`, `document.documentElement.lang`. Polish items in §12. |

### v2 / v3

| # | Feature | Status | Evidence / gap |
| --- | --- | --- | --- |
| V2-1 | Himawari-9 10-minute detection | Missing | Needs JAXA P-Tree registration. |
| V2-2 | Telegram/WhatsApp alerts by kabupaten or radius | Missing | |
| V2-3 | Sentinel-2/Sentinel-1 burn scars | Missing | |
| V2-4 | BMKG fire danger rating layer | Missing | |
| V3-1 | Peat reignition risk model | Missing | |
| V3-2 | Next-48 h fire risk per kabupaten | Missing | `spread.py` forecasts spread of existing fires, not ignition risk. |

## 5. Data sources

| Source | Phase | Status | Evidence / gap |
| --- | --- | --- | --- |
| FIRMS VIIRS SNPP / NOAA-20 / NOAA-21 | v1 | Done | `firms.py` `NRT_SOURCES`, `SP_SOURCES`, availability windows. |
| FIRMS MODIS | v1 | Done | `MODIS_NRT`, `MODIS_SP`; MODIS area used when there's no VIIRS (`events.py`). |
| FIRMS archive 2012–now | v1 | Partial | `haze archive <years>` works. Only 2015, 2019, 2023, 2024, 2025 used (baselines CSV, mask). No 2012–now load script or record of it. |
| CAMS global forecast | v1 | Partial | Through Open-Meteo's air-quality API (`smoke.py` `AQ_URL`), not the ADS account. Keyless and works; it depends on Open-Meteo's CAMS mirror and free quota. |
| Open-Meteo wind, rain, humidity, days since rain | v1 | Partial | Wind (10 m / 925 / 850 hPa) and rain: `smoke.fetch_wind`. Days since rain isn't computed. |
| OpenAQ + ISPU stations | v1 | Missing | |
| geoBoundaries / BIG admin | v1 | Partial | geoBoundaries ADM1 and ADM2 (`regions.py` `GB_BASE`). No kecamatan (ADM3). |
| KHG peat units | v1 | Done | `regions.py` `PEAT_SOURCES` (KHG 2017, GFW fallback). |
| DEMNAS | v1 (hilly) | Missing | Terrain is AWS Terrarium/SRTM (`dem.py` `TILE_URL`, `MapView.tsx` `DEM_TILES`). |
| Copernicus GLO-30 | v1 | Missing | Same; SRTM is used instead. |
| Sentinel-2 cloudless basemap | v1 | Done | EOX `s2cloudless-2023` (`MapView.tsx`). Licence is CC BY-NC-SA (§12). |
| Static source mask (VIIRS Nightfire + manual) | v1 | Partial | FIRMS type flags + 30-day persistence + `static_sources_manual.csv` (`mask.py`). No VIIRS Nightfire flare list. |
| Himawari-9 (JAXA) | v2 | Missing | |
| Sentinel-2 L2A | v2 | Missing | |
| Sentinel-1 SAR | v2 | Missing | |
| BMKG fire danger | v2 | Missing | |
| GeoNames towns (not in PRD table) | v1 | Done | `regions.load_towns()`, used for nearest town and city outlook. |
| Signups: FIRMS key, map token | v1 | Done | `FIRMS_MAP_KEY` secret in `pipeline.yml`. No map token needed: all basemaps are keyless. CAMS ADS and DEMNAS signups not done (not needed so far / missing). |

## 6. Architecture and stack

| # | Requirement | Status | Evidence / gap |
| --- | --- | --- | --- |
| A1 | Poll FIRMS VIIRS + MODIS, Indonesia bbox, last 24 h, upsert | Done | `cli.cmd_run` → `pipeline.ingest_recent(day_range=2)`; `config.BBOX`; `db.upsert_hotspots` (`ON CONFLICT DO NOTHING`). |
| A2 | Drop static heat sources (mask + 30-day recurrence) | Done | `mask.py` `recurrent_cells`, `classify`. |
| A3 | Tag peat, provinsi, kabupaten | Done | `pipeline.tag_hotspots`, `regions.Tagger`. |
| A4 | Space-time clustering ~1.5 km / ~48 h, incremental, tuned on 2019/2023 | Done | `cluster.py` (single linkage = DBSCAN with minPts 1), `pipeline.update_events`, frozen in `config.ClusterParams`. |
| A5 | Per event per day: concave-hull perimeter, FRP sum, estimated area | Partial | `events.snapshots()`: FRP and area done. Perimeter is a union of half-pixel buffers, not a concave hull. This is a deliberate, documented change (README "Footprint"). |
| A6 | Publish GeoJSON/vector tiles + dashboard JSON to object storage behind a CDN | Partial | `publish.py` writes JSON/GeoJSON (no vector tiles). The R2 sync step in `pipeline.yml` only runs if R2 secrets exist; today the output is a 2-day workflow artifact. |
| A7 | Every 6 h: CAMS + Open-Meteo, smoke and wind tiles per forecast hour | Partial | `smoke.needs_refresh` (6 h) inside each run. JSON grids every 3 h, not raster tiles. |
| A8 | 30-minute cron | Partial | Every 2 h while the repo is private (`pipeline.yml` comment). |
| A9 | Python + DuckDB spatial acceptable for v1 | Done | DuckDB with WKB + shapely (`db.py`). No geopandas/scikit-learn, which is fine. |
| A10 | Cron on VPS or GitHub Actions | Done | `pipeline.yml`; state in the Actions cache. |
| A11 | Cloudflare R2 + Pages hosting | Partial | R2 step stubbed; no Pages deploy workflow. `ci.yml` only builds. |
| A12 | MapLibre + deck.gl frontend | Done | MapLibre 4.7 (`package.json`). deck.gl was replaced by native layers plus a custom WebGL2 layer (`fire3d.ts`), which the README explains. |

## 7. Data model

| Table / item | Status | Evidence / gap |
| --- | --- | --- |
| `hotspots` (dedup on satellite, acq_time, lat, lon) | Done | `db.py`; id hash from `firms.hotspot_ids`. No `geom` column (lat/lon only), which is fine. |
| `fire_events` (all PRD fields) | Done | `db.py`, plus `peat_share`, `near_static`, `nearest_town_km`, `season`. Bbox is four columns. |
| Status rules active < 24 h, cooling 24–72 h, out > 72 h | Done | `config.StatusParams`, `pipeline.refresh_status`. |
| `event_snapshots` (daily perimeter, count, FRP, growth) | Done | `db.py` (`perimeter_geom` cumulative + `day_geom`). |
| `regions` (provinsi / kabupaten / kecamatan, `peat_share`) | Partial | Levels are provinsi, kabupaten, peat. No kecamatan, no `peat_share` per region. |
| `aq_readings` | Missing | |
| Raster smoke/wind as COG or PNG tiles per hour on CDN | Partial | Quantised JSON grids (`smoke/smog.json`, `wind.json`, `plumes.json`), painted to canvas client-side (`smoke.ts`). |
| Naming `<kabupaten>-<YYYYMMDD>-<n>`, friendly name from nearest town | Partial | Done for ids (WIB date) and names. Single-detection events have no page (U4). |

## 8. 3D visualization

| # | Requirement | Status | Evidence / gap |
| --- | --- | --- | --- |
| D1 | MapLibre GL with terrain | Done | `MapView.tsx` `setTerrain(terrainDem, 1.6)`. |
| D2 | Terrain from DEMNAS where hilly, GLO-30 elsewhere | Missing | SRTM via AWS Terrarium. |
| D3 | Active events: column per event, height = FRP, colour by age | Partial | Exists (`columns`, `STATUS_RGB`) but hidden by default (F1). Colour is by status (amber / red), close to the PRD. |
| D4 | Hotspots zoomed in: glowing points, size = FRP, fade over 72 h | Partial | `fire-glow` heatmap weighted by FRP. Fades over 0–48 h, and `publish.recent_hotspots(hours=48)` only ships 48 h. |
| D5 | Daily perimeters, older days darker, animated by timeline | Done | `burn-scar` + `ember` layers, `scarColor()`, driven by `dayIndex`. Per event only. |
| D6 | Smoke: semi-transparent PM2.5 field draped + animated wind particles | Done | `smog_*`/`plume_*` image sources, `windParticles.ts`, `fire3d.ts` smoke. |
| D7 | Peat: subtle brown hatch, toggle | Missing | No peat layer or toggle. |
| D8 | AQ stations: small dots by PM2.5 category | Missing | See F6. Counted again here because it is a separate map layer. |
| D9 | Default tilted national view over Sumatra + Kalimantan, auto-rotate off | Done | `INITIAL_VIEW` (111.5, −1.8, z 4.75), pitch 45; no rotation. |
| D10 | Click event: fly-to at ~60° pitch, panel with curves | Done | `fitBounds` pitch 62; `EventPanel`. Click targets are `columns` and `glow` only. |
| D11 | Timeline scrubber at bottom: hourly steps, 1 day/s, national or per event | Partial | Per event, in the side panel, daily steps, 1 day/s. Not hourly, not national. The bottom bar is the forecast slider. |
| D12 | Mobile: 2D default on low-end devices, 3D toggle | Partial | Chosen by viewport width (`max-width: 760px`), not by device capability. A tablet or low-end landscape phone gets 3D. Toggle exists. |
| D13 | 60 fps desktop, 30 fps mid Android | Partial | Throttling, `prefers-reduced-motion` and `document.hidden` checks (`fx.ts`, `fire3d.ts`). Never measured. |
| D14 | Precompute server-side; per-day files; no raw hotspot history to client | Partial | Precompute done. `days/*.geojson` is published but unused. The client gets 48 h of raw detections (OK for D4) and the full 7-day `live.json` (2.8 MB). |

## 9. Risks and mitigations

| Risk mitigation | Status | Evidence / gap |
| --- | --- | --- |
| Peat: "cooling" for 72 h, label peat events as possibly still burning | Done | `peatNote` callout in `EventPanel.tsx` when `on_peat`. Same 72 h cooling for all events. |
| Show last-seen time prominently | Done | `EventPanel` facts block. |
| Static mask + 30-day recurrence flag | Done | `mask.py`; `near_static` warning (`nearStatic` string). |
| Bad clustering: tune on archives, 100-event review | Partial | Done once (eval doc). Expert review still pending. |
| FIRMS outage: freshness banner | Done | `Dashboard.tsx` `freshness` + stale note at > 6 h. |
| FIRMS outage: MODIS fallback | Done | MODIS is always ingested. |
| FIRMS outage: alert on ingest lag > 6 h | Missing | No operator alert (§12 monitoring). |
| "Estimated area", method explained | Done | `estimateNote`, README "Area". |
| Political sensitivity: satellite facts only, cite sources, no attribution | Partial | No concessions or companies anywhere (good). The source line names FIRMS, EOX and OpenFreeMap only, not CAMS/Open-Meteo, geoBoundaries, KHG or GeoNames. No methodology page. |
| Traffic spikes: static frontend + CDN | Partial | Frontend is static; no CDN deployed yet (A6/A11). |

## 10. Open questions

| Question | Status | Evidence |
| --- | --- | --- |
| Product name and domain | Partial | "Haze" in `index.html` and README. No domain. |
| Clustering parameters | Done | Frozen at 1.5 km / 48 h (eval doc). |
| Clean KHG source | Done | KHG 2017 via ArcGIS republish (`regions.py`); provenance is a third-party republish. |
| ISPU via API or scrape | Missing | Not investigated. |
| Hosting budget | Partial | Actions free-tier reasoning in `pipeline.yml`. No decision on VPS, Postgres or Cloudflare plan. |
| Validation partner | Missing | Recommended in the eval doc; not contacted. |

## 11. Milestone exit criteria

| # | Exit criterion | Status | Gap |
| --- | --- | --- | --- |
| E1 | Data access: FIRMS, CAMS, map token, DEMNAS keys; bbox fetch returns data | Partial | FIRMS works. CAMS and the map are keyless. DEMNAS not obtained. |
| E2 | Ingest + archive: 30-min cron, 2012–now archive, mask applied | Partial | 2 h cron; archive incomplete; mask done. |
| E3 | Clustering: 100-event review ≥ 90%, parameters frozen | Partial | 98% lenient / 76% strict, single reviewer; frozen. |
| E4 | 3D map + timeline on desktop and mid Android | Partial | Desktop national view, fly-to and per-event animation done. No national timeline; mid Android not tested. |
| E5 | Smoke, AQ, dashboard: CAMS smoke + wind, AQ stations, stats + season comparison | Partial | AQ stations missing. |
| E6 | Public v1: domain, Bahasa UI, share previews, freshness banner, load test | Missing | Bahasa and the banner exist, but no domain, share previews, deploy or load test. Nothing is public. |
| E7 | v2: Himawari + kabupaten alerts | Missing | v2. |

## 12. Cross-cutting non-functional requirements

Some of these are not stated in the PRD. They are rated against what a public v1 needs.

| Area | In PRD? | Status | Evidence / gap |
| --- | --- | --- | --- |
| Performance budget (< 4 s on 4G) | Yes | Missing | See M4. No code splitting (`vite.config.ts` just raises the warning limit). Data isn't trimmed for first paint. |
| Accessibility | Implied (non-experts) | Partial | Status never shown by colour alone; `role="status"` freshness; charts `role="img"` + `aria-label`; reduced motion respected. Gaps: map events not reachable by keyboard (no list of all fires); no visible focus styles in `styles.css`; language toggle has no `aria-label`; charts have no data-table fallback; no contrast audit. |
| i18n completeness | Yes | Partial | All UI strings in `i18n.ts`. Gaps: language lives only in the hash (not remembered); fetch errors shown raw; `index.html` meta in Bahasa only; units and "WIB" hard-coded (acceptable). |
| Hosting (R2 + Pages + CDN) | Yes | Partial | §6 A6/A11. |
| Update cadence 30 min fires / 6 h smoke | Yes | Partial | 2 h / 6 h. |
| Monitoring and uptime alerts | Yes (M5, risks) | Missing | No alert on failure or on lag > 6 h. |
| Data retention and backup | No | Partial | DuckDB lives only in the Actions cache (evicted after 7 days unused or when over 10 GB). A cold start re-backfills the current season from the API, but older seasons and `event_registry` ids would be lost. Artifact retention is 2 days. No backup to R2. |
| Sharing / permalinks for every event and view | Yes | Partial | Hash routes for events only. No view state (map position, day, forecast hour, layers). Singleton and previous-season links break. |
| Social preview (OG) images | Yes | Missing | `index.html` has `title` and `description` only. Hash routes can't carry per-event OG tags for crawlers. |
| SEO (robots, sitemap, canonical) | No | Missing | |
| Alerts / notifications | v2 | Missing | v2 (Telegram/WhatsApp). |
| Embed (iframe / widget) | No | Missing | |
| API / download | P2 | Partial | Static JSON is effectively a public API. Not documented for users, no CSV, no download buttons. |
| Mobile layout | Yes | Done | Bottom sheets, phone padding, 2D default (`App.tsx`, `MapView.tsx`, `styles.css`). Screenshots 06/07. |
| Analytics (privacy-friendly usage counts) | No | Partial | None, which is fine for privacy. But the PRD's metrics (latency, Lighthouse, uptime) have no measurement either. |
| Privacy | No | Done | No cookies, trackers or accounts. Third-party tile hosts (EOX, OpenFreeMap, AWS) see viewer IPs. A short notice is still worth adding. |
| Legal, attribution, disclaimers | Yes (cite sources) | Partial | Map attribution control lists EOX, OpenFreeMap/OSM and SRTM. Missing in the UI: Copernicus CAMS / Open-Meteo (CC BY 4.0), geoBoundaries (CC BY 3.0 IGO), KHG/KLHK, GeoNames (CC BY 4.0). The EOX basemap is CC BY-NC-SA (non-commercial only). No LICENSE file. No general disclaimer ("satellite-derived; misses fires under cloud and underground; not official — see SiPongi/BMKG"). |

## 13. Contradictions and inconsistencies

| # | Where | PRD says | Repo does |
| --- | --- | --- | --- |
| C1 | `pipeline.yml` | 30-minute cron | Every 2 h (documented as temporary while the repo is private). |
| C2 | `spread.py`, `EventPanel.tsx`, README "Spread" | Non-goal: physics-based fire spread simulation. Risk forecasting is v3. | A stochastic cellular-automaton spread forecast (wind/slope/rain/peat, Alexandridis 2008) runs for the top 40 fires and shows on the map by default (`layers.spread: true`). It is labelled experimental, but it is outside v1 scope and needs a product decision. |
| C3 | `App.tsx`, `MapView.tsx` | P0: glowing columns extruded by FRP | Columns are off by default; particle flames are the default encoding. |
| C4 | `smoke.py`, `web/src` | One consistent smoke drift story | Puffs move on **10 m** wind (`PuffParams.transport_levels = ("10",)`, docs/models.md), but `wind.json` publishes **850 hPa** wind (`level: "850 hPa"`, `u850/v850`). The web's wind particles and the 3D smoke bending (`MapView.tsx` `windAt`) use that 850 hPa field, so the drawn wind and smoke direction don't match the model's plumes. The `smoke.py` module docstring and `plumes.json` `model` string still say "850 hPa trajectories". The README says 3D smoke bends "with the forecast 10 m wind", which is wrong. |
| C5 | `events.py` | Concave-hull daily perimeter | Union of half-pixel buffers (a deliberate, documented change). |
| C6 | `dem.py`, `MapView.tsx` | DEMNAS / GLO-30 terrain | SRTM (AWS Terrarium). |
| C7 | `smoke.py` | CAMS via ADS account, raster tiles | CAMS via Open-Meteo, JSON grids. |
| C8 | `mask.py` | VIIRS Nightfire mask | FIRMS type flags + persistence + manual list. |
| C9 | `package.json`, `fire3d.ts` | deck.gl layers | Native MapLibre layers + custom WebGL2 layer. |
| C10 | `App.tsx` | Every event has a stable URL with a social preview | Hash URLs (no per-event OG possible). No page for single-detection events. Event pages are looked up under `dash.season`, so links break at the season change. |
| C11 | `publish.py`, `MapView.tsx` | Hotspots fade over 72 h | 48 h shipped and faded. |
| C12 | `EventPanel.tsx` | Hourly timeline steps, bottom of screen, national or per event | Daily steps, in the side panel, per event only. |
| C13 | `README.md` | n/a (docs accuracy) | Says the repo "currently holds the data pipeline (M0–M2)", but the web app and smoke work are in. The layout block lists `src/haze/` and `static/` under `web/` instead of `pipeline/`. |
| C14 | `MapView.tsx` | Free public basemap | EOX S2 cloudless 2023 is CC BY-NC-SA. Fine for a non-commercial public app, but it rules out commercial reuse or embedding by media partners without checking. |

## 14. Implementation plan

Ordered by launch value and risk. Each chunk can ship on its own. Effort: S ≤ 1 day, M 2–3 days,
L ≥ 4 days. **Ext** marks a dependency on external data, accounts or people we don't have yet.

### Phase A: correctness and quick wins (before any public link)

| # | Chunk | Files | Effort | Ext |
| --- | --- | --- | --- | --- |
| 1 | Fix the wind-level mismatch (C4): publish the transport-level wind (10 m) in `wind.json`, or publish both and pick 10 m in the web. Fix the docstring, the `plumes.json` model string and the README. | `pipeline/src/haze/smoke.py`, `web/src/smoke.ts`, `web/src/App.tsx`, `README.md`, `pipeline/tests/test_smoke.py` | S | — |
| 2 | Make every event linkable: publish a small page for single-detection events (or have the web fall back to the `live.json` row); take the season from the id's date instead of `dash.season`. | `pipeline/src/haze/publish.py`, `web/src/data.ts`, `web/src/App.tsx` | S | — |
| 3 | PRD-conformant defaults: columns on by default (or amend the PRD); spread layer off by default and behind an "experimental" toggle until the C2 decision. | `web/src/App.tsx`, `web/src/MapView.tsx` | S | — |
| 4 | Ship and fade hotspots over 72 h (C11). | `pipeline/src/haze/publish.py` (`recent_hotspots(hours=72)`), `web/src/MapView.tsx` (`fire-glow` weight) | S | — |
| 5 | Fix the stale README (C13). | `README.md` | S | — |

### Phase B: launch plumbing (E6)

| # | Chunk | Files | Effort | Ext |
| --- | --- | --- | --- | --- |
| 6 | Hosting: R2 bucket + public CDN domain with CORS and cache headers; Cloudflare Pages deploy on push to `main` with `VITE_DATA_URL`. | new `.github/workflows/web-deploy.yml`, `.github/workflows/pipeline.yml`, `README.md` | M | Cloudflare account and credentials |
| 7 | 30-minute cadence: make the repo public or move the cron to a small VPS; keep `concurrency`. | `.github/workflows/pipeline.yml` (or a VPS systemd timer + docs) | S | Hosting-budget decision |
| 8 | Monitoring: after each run, compute median `ingested_at − acq_time` and lag, write `status.json`, and open an issue or ping a webhook on failure or lag > 6 h. Add an uptime check against `status.json`. | `pipeline/src/haze/cli.py`, `pipeline/src/haze/publish.py`, `.github/workflows/pipeline.yml` | M | Alert channel (webhook) |
| 9 | State durability: back up DuckDB (or Parquet exports of `hotspots` + `event_registry`) to R2 after each run, and restore from there when the cache misses. | `.github/workflows/pipeline.yml`, `pipeline/src/haze/cli.py` | S | R2 (chunk 6) |
| 10 | Payload and performance: ship active/cooling events first and the rest lazily, or split `live.json` by status; trim columns; lazy-load smoke/plumes/spread; split the bundle (`fire3d`, smoke) with dynamic import; add a Lighthouse CI budget. | `pipeline/src/haze/publish.py`, `web/src/data.ts`, `web/src/App.tsx`, `web/vite.config.ts`, `.github/workflows/ci.yml` | M | — |
| 11 | Share previews: path routes (`/event/<id>`) with a Pages SPA fallback; the pipeline writes per-event `share/<id>.html` stubs with OG/Twitter tags plus an OG PNG (Pillow: footprint over a static basemap, stats, name). Add a national OG image, `robots.txt` and a sitemap. | new `pipeline/src/haze/og.py`, `pipeline/src/haze/publish.py`, `web/index.html`, `web/src/App.tsx`, Pages `_redirects` | L | Domain (chunk 12) |
| 12 | Name and domain. | `web/index.html`, `README.md` | S | Product decision |
| 13 | About / methodology / disclaimer page: what satellites can't see, estimated area, clustering, models labelled experimental, "not official data", full source attribution (CAMS/Open-Meteo, geoBoundaries, KHG, GeoNames, FIRMS, EOX), a privacy note, and a LICENSE for code and data. | new `web/src/About.tsx`, `web/src/i18n.ts`, `web/src/App.tsx`, `LICENSE` | S | — |
| 14 | Load test against the CDN (k6 or similar), plus a mid-Android Lighthouse and FPS check; record results. | new `web/scripts/loadtest.js`, `docs/` results | S | Deployed CDN; a test device |

### Phase C: missing v1 product features

| # | Chunk | Files | Effort | Ext |
| --- | --- | --- | --- | --- |
| 15 | National timeline scrubber at the bottom: load `days/{date}.geojson` for the last N days, play 1 day/s, share the bar with the forecast slider (past ↔ future). Hourly steps: add `hour` or `acq_time` buckets to day files, or derive them from `hotspots_recent`. | `web/src/Controls.tsx`, `web/src/App.tsx`, `web/src/MapView.tsx`, `web/src/data.ts`, `pipeline/src/haze/publish.py` | M | — |
| 16 | Event list: sortable by area, growth, peak FRP and last seen; filter "new today / since last pass", province and peat; search by name or kabupaten. Doubles as keyboard access to every fire. | new `web/src/EventList.tsx`, `web/src/data.ts` (load `events/{season}.json`), `web/src/i18n.ts`, `web/src/App.tsx` | M | — |
| 17 | Dashboard completions: today vs yesterday (events, hotspots, area), show all 10 top-growth rows, hotspots column in the province table. | `pipeline/src/haze/publish.py` (`dashboard()`), `web/src/Dashboard.tsx`, `web/src/data.ts`, `web/src/i18n.ts` | S | — |
| 18 | View state in the URL: map center/zoom/pitch, timeline day, forecast hour, layers, language. | `web/src/App.tsx`, `web/src/MapView.tsx` | S | — |
| 19 | Near me: geolocation and place/kabupaten search → nearest active fires with distance, plus that kabupaten's smoke outlook. The pipeline publishes a per-kabupaten outlook (centroid or max over the polygon). | `pipeline/src/haze/smoke.py`, `pipeline/src/haze/regions.py`, new `web/src/NearMe.tsx`, `web/src/App.tsx`, `web/src/i18n.ts` | M | — |
| 20 | Context layers: KHG peat (simplified GeoJSON or PMTiles, brown hatch, toggle); kabupaten boundaries from geoBoundaries ADM2; days since rain from the Open-Meteo past-days precipitation grid. Add kecamatan (ADM3) to `regions`. | `pipeline/src/haze/regions.py`, `pipeline/src/haze/publish.py`, `pipeline/src/haze/smoke.py`, `web/src/MapView.tsx`, `web/src/Controls.tsx`, `web/src/i18n.ts` | M | — (all free) |
| 21 | Data export: CSV + GeoJSON per day and per season; download buttons on the dashboard and event panel; a short data-format page. | `pipeline/src/haze/publish.py`, `web/src/Dashboard.tsx`, `web/src/EventPanel.tsx`, `web/src/i18n.ts`, `docs/` | S | — |
| 22 | Accessibility and i18n pass: focus styles, `aria-label` on toggles, chart data tables, contrast check, remembered language, translated error messages, English meta. | `web/src/styles.css`, `web/src/App.tsx`, `web/src/charts.tsx`, `web/src/i18n.ts`, `web/index.html` | S | — |
| 23 | Low-end detection: 2D by default from `navigator.deviceMemory`, `hardwareConcurrency`, missing WebGL2 or a slow first frame, not only width; cap particles. | `web/src/App.tsx`, `web/src/fire3d.ts` | S | — |

### Phase D: work that needs external data

| # | Chunk | Files | Effort | Ext |
| --- | --- | --- | --- | --- |
| 24 | AQ stations: OpenAQ v3 ingest (PM2.5, hourly) into `aq_readings`; publish `aq/stations.json`; map dots by ISPU category; nearest station in the cities table and event panel. | new `pipeline/src/haze/aq.py`, `pipeline/src/haze/db.py`, `pipeline/src/haze/cli.py`, `web/src/MapView.tsx`, `web/src/Controls.tsx`, `web/src/i18n.ts` | M | **Yes**: OpenAQ API key |
| 25 | ISPU (KLHK) station feed: API or scrape, merged into `aq_readings`. | `pipeline/src/haze/aq.py` | M | **Yes**: ISPU access (open question) |
| 26 | Full FIRMS archive 2012–now: `haze archive 2012 … 2025` in a one-off workflow, `haze baselines`, regenerate the mask. | `.github/workflows/backfill.yml`, `README.md` | S | FIRMS archive (free; storage/time only) |
| 27 | Terrain: DEMNAS in hilly regions, GLO-30 elsewhere, merged and published as Terrarium/RGB tiles on R2; point `dem.py` and `DEM_TILES` at them. | `pipeline/src/haze/dem.py`, new tiling script, `web/src/MapView.tsx` | L | **Yes**: DEMNAS account; GLO-30 download |
| 28 | VIIRS Nightfire flare list added to the static mask; re-evaluate M3. | `pipeline/src/haze/mask.py`, `pipeline/static/`, `docs/clustering-evaluation.md` | S | **Yes**: EOG Nightfire access |
| 29 | Expert clustering review (22 ambiguous + 2 wrong + a fresh sample) to close E3. | `docs/clustering-evaluation.md` | S | **Yes**: Pantau Gambut / BPBD / university partner |
| 30 | Transboundary context: hotspots in Malaysia/Brunei/Timor-Leste (currently dropped at tagging) as a dim "outside Indonesia" layer; ASMC regional haze reference. The smoke city list already covers Singapore and Peninsular Malaysia. | `pipeline/src/haze/pipeline.py`, `pipeline/src/haze/publish.py`, `web/src/MapView.tsx` | S–M | **Partly**: ASMC data terms |
| — | Concessions / company attribution | — | — | Explicit **non-goal** for v1. Do not build. Would need KLHK/GFW concession data and legal review. |

### Phase E: v2 and v3

| # | Chunk | Files | Effort | Ext |
| --- | --- | --- | --- | --- |
| 31 | Himawari-9 10-minute detections as a "new fire" fast path (provisional until VIIRS confirms). | new `pipeline/src/haze/himawari.py`, `pipeline/src/haze/events.py`, `web/src/*` | L | **Yes**: JAXA P-Tree registration |
| 32 | Kabupaten / radius alerts on Telegram, then WhatsApp; subscriptions store (needs a small backend, so it goes beyond the static-only architecture). | new service, `pipeline/src/haze/alerts.py` | L | **Yes**: Telegram bot token; WhatsApp Business API |
| 33 | Burn scars from Sentinel-2 dNBR, then Sentinel-1 SAR. | new `pipeline/src/haze/burnscar.py` | L | **Yes**: Copernicus Data Space account |
| 34 | BMKG fire danger rating layer. | new `pipeline/src/haze/bmkg.py`, `web/src/MapView.tsx` | M | **Yes**: BMKG data (scrape, terms unclear) |
| 35 | v3: peat reignition risk and 48 h fire risk per kabupaten. | new modules | L | Groundwater data (e.g. BRGM SiPPEG) |

### Decisions needed (no code)

| Decision | Why |
| --- | --- |
| Keep, hide or descope the spread forecast (C2) | It contradicts a v1 non-goal, and a public probabilistic "where fire will go" map is politically and operationally sensitive. |
| Columns vs flames as the default encoding (C3) | The P0 feature description and the current UI disagree. |
| Hosting budget: Actions (public repo) vs VPS | Blocks the 30-minute cadence (C1) and durable state. |
| Basemap licence (C14) | NC licence; check before media embedding. |
