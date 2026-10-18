# Research: extra GIS and Earth-observation layers

Compiled 2026-10-17. Every endpoint below was tested from the dev container (outbound HTTPS through a proxy) on 2026-10-17 between 16:30 and 17:00 UTC. HTTP codes are what the container got. `206` means a ranged request (first bytes of the file) succeeded.

Tags:

- **[T]** tested here, with the code shown.
- **[D]** read in the provider's own docs or listing.
- **[S]** search snippet only. Check before relying on it.

GitHub Actions runners sit on different IPs. Hosts that failed here (Indonesian `.go.id`, Geofabrik, Overpass) should be re-tested from a runner before they are written off.

Tile coordinates used in tests (`{z}/{y}/{x}`, Web Mercator): `6/32/51` covers South Kalimantan and the Java Sea. `5/16/25` covers South Sumatra and Java. `7/64/99` covers Riau.

## 1. Faster or more hotspots

| Dataset | Endpoint (tested) | Code | Licence | Res. | Latency | Size | Fit / priority / effort |
| --- | --- | --- | --- | --- | --- | --- | --- |
| VIIRS 375 m (SNPP, NOAA-20, NOAA-21) | `firms…/api/area/csv` (MAP_KEY), plus keyless `firms…/data/active_fire/noaa-21-viirs-c2/csv/J2_VIIRS_C2_SouthEast_Asia_24h.csv` | 206 [T] | NASA open | 375 m | ~3 h | ~1 MB/day SE Asia | **Already in use** (`firms.py`, all 3 VIIRS sats plus MODIS). The keyless regional 24 h/48 h/7 d CSVs could back up the API if the key is rate-limited. Low priority, small effort. |
| FIRMS LANDSAT_NRT (30 m, OLI) | API source `LANDSAT_NRT` | n/a | NASA open | 30 m | ~30 min | small | **Not usable.** The FIRMS API docs say "US/Canada only" [D]. `…/data/active_fire/landsat/csv/` returns 404 [T]. Skip. |
| FIRMS "Filtered Geostationary" (Himawari FRP-PIXEL from CAMS/IPMA, 2 km, 10 min) | FIRMS web map only | n/a | provisional | 2 km | ~30 min | – | Shown in the FIRMS viewer [S]. **It is not a valid API `SOURCE`** [D], so it can't be pulled by script. Skip unless FIRMS adds it to the API. |
| JAXA P-Tree Himawari-9 WLF L2 (10 min hotspots + FRP, CSV) | `ftp.ptree.jaxa.jp` over FTPS:990 / SFTP:2051. README at `eorc.jaxa.jp/ptree/documents/README_Himawari_L2WLF.txt` | README 200. SFTP:2051 **timed out from the container** [T] | Registration required. Non-profit research/education only. **No redistribution to third parties** [D/S] | 2 km (0.02°) | ~10–20 min | KB per file, 144 files/day | Best geostationary product, but it can't be republished in a public static app. Could drive internal "fire still burning" flags (counts, not points) from a runner that can reach SFTP. **No open mirror found.** Medium priority, medium effort, licence-blocked for display. |
| NOAA Himawari-9 open data (AWS) | `https://noaa-himawari9.s3.amazonaws.com/AHI-L1b-FLDK/YYYY/MM/DD/hhmm/` | 200 [T] | NOAA open data (no restriction) | B07 3.9 µm 2 km; B03 0.5 km | **~11 min** (0300 UTC scan objects at 03:11) [T] | B07 segments S05+S06 (equator band) ≈ 5.8 MB per 10 min | Only L1b, Clouds, Winds, RainfallRate and ISatSS. **No fire L2.** We would have to run our own contextual 3.9/11 µm detector (a JAXA-style 11×11 normalised deviation is documented in the WLF README). This gives sub-hourly "is it still burning" and diurnal FRP between VIIRS passes, open to redistribute. Medium priority, **high effort**. |
| GOES-style FireTemp RGB for Asia | GIBS has `GOES-East/West_ABI_FireTemp` only | [T] caps | – | – | – | – | **No Himawari FireTemp/GeoColor on GIBS.** See section 5 for Himawari imagery. |

## 2. Burned area

| Dataset | Endpoint (tested) | Code | Licence | Res. | Latency | Size | Fit / priority / effort |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MODIS MCD64A1 C6.1 | Planetary Computer STAC `…/api/stac/v1/collections/modis-64A1-061`, plus keyless SAS token `…/api/sas/v1/token/modis-64A1-061` | 206 / 206 [T] | NASA open | 500 m, monthly with burn day | **~2.5 months** (latest is A2026213 = Aug 2026, processed Oct 13) [T] | ~2–5 MB per tile-month (h28–h30 v08–v09) | **Calibration truth** for the spread model: compare predicted cumulative area against the burn-date raster for 2019 and 2023 (GlobFire perimeters derive from this). High priority, low–medium effort (COG via PC, no login). |
| VIIRS VNP64A1 C2 | CMR `short_name=VNP64A1` (latest A2026213) [T]; data at LP DAAC/LAADS | 200 (CMR) [T] | NASA open; **Earthdata login** | 500 m | ~2.5 months | similar | Same role as MCD64A1, and outlives MODIS (Terra/Aqua are ending). Medium priority; needs a free Earthdata token as a secret. |
| ESA FireCCI S311 (Sentinel-3 SYN) v1.1 | `https://dap.ceda.ac.uk/neodc/esacci/fire/data/burned_area/Sentinel3_SYN/pixel/v1.1/compressed/{2019..2024}/` | 200 [T] | CC BY 4.0 (CCI) | **300 m** pixel with burn day | annual release (2024 added Oct 2025) | 35–140 MB per month per AREA tile | Best open small-fire burned area for **both 2019 and 2023**. Use as the area target in `spread-eval` alongside the active-fire mask. MODIS FireCCI51 stops at 2020. High priority, medium effort. |
| GWIS/EFFIS NRT burned area | WMS `https://maps.effis.emergency.copernicus.eu/gwis?…&LAYERS=nrt.ba.poly&STYLES=` | 200, but **blank PNG over Indonesia** [T] | Copernicus | MODIS/VIIRS | daily | – | Rendered map only, and empty over Indonesia today. Not useful. |
| KLHK/Kemenhut burned area (Luas Karhutla, SiPongi) | `sipongi.kehutanan.go.id`, `geoportal.kehutanan.go.id` (menlhk.go.id renamed) | **502 CONNECT** from container [T] | Gov. Decree SK 399/2024 limits SHP to government/universities [S] | Landsat-based, yearly | annual | – | The official figures. Scrape province totals for validation from a runner if reachable. Low priority. |
| Sentinel-2 dNBR on demand | Earth Search STAC `POST https://earth-search.aws.element84.com/v1/search` with `sentinel-2-c1-l2a`; COGs at `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/…/B12.tif` | 200 / 206 [T] | Copernicus open (free, attribution) | 20 m (B8A/B12) | **~3 h** (sensed 02:48, catalogued 06:05 UTC) [T] | ~60–120 MB per tile per band; range reads are much smaller | Post-fire scars per event: pre/post NBR = (B8A−B12)/(B8A+B12), masked with SCL. **Caveat:** over Central Kalimantan, 18 of 20 scenes from 15 Sep–17 Oct 2026 have 88–100% "cloud" (smoke is flagged as cloud) [T]. Works after the rains, not during the event. Medium priority, medium effort (rasterio range reads on a runner). Earth Search `landsat-c2-l2` points at requester-pays USGS buckets. |
| OPERA DIST-ALERT (HLS, 30 m vegetation loss, global) | GIBS `OPERA_L3_DIST-ALERT-HLS_Color_Index/default/2026-10-11/GoogleMapsCompatible_Level12/…` | 200 [T] (empty tile at test location) | NASA open | 30 m | days | tiles | Ready-made "recently disturbed land" overlay. Low priority, trivial effort. |
| GFW tree-cover loss from fire (`umd_tree_cover_loss_from_fires` v1.13) | tiles `https://tiles.globalforestwatch.org/umd_tree_cover_loss_from_fires/v1.13/default/{z}/{x}/{y}.png` | 307 [T]; data lake 403 | CC BY 4.0 | 30 m, annual | yearly | – | Context layer only. Low priority. |

## 3. Fuel, land cover, peat and drainage

The current spread model has only two fuels: peat and other.

| Dataset | Endpoint (tested) | Code | Licence | Res. | Vintage | Size | Fit / priority / effort |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **MapBiomas Indonesia Collection 3** (annual LULC) | `https://storage.googleapis.com/mapbiomas-public/initiatives/indonesia/collection_3/coverage_indonesia_{2016..2024}.tif` | 200 (bucket listing) [T] | Open, free; MapBiomas network uses CC BY-SA 4.0 [S] | 30 m | **annual to 2024**, so it has 2019 and 2023 | ~260 MB/yr national | **Best fuel layer**: a year-matched class map (forest, plantation, oil palm, shrub, agriculture) for the 2019 fit and the 2023 test. Rasterise to the 375 m grid as class fractions and fit p0 per class. High priority, medium effort. |
| KLHK Penutupan Lahan (official 23-class) | `geoportal.kehutanan.go.id` 502 [T]. GFW mirror of 2017: tiles `https://tiles.globalforestwatch.org/idn_land_cover_2017/v201807/default/{z}/{x}/{y}.png` | 200 [T]; data lake 403 | gov; SHP restricted | 1:250k | 2017 (mirror) | – | Official, but the vector isn't openly downloadable. Use the mirror only as a map layer. Low priority. |
| ESA WorldCover v200 | `https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N00E102_Map.tif` | 206 [T] | CC BY 4.0 | 10 m | 2021 only | ~30–90 MB per 3° tile | Good static fallback, but only 2021, with no oil palm or plantation class. Medium priority. |
| Oil palm (Descals et al. 2021, industrial vs smallholder) | `https://zenodo.org/api/records/4473715` | 200 [T] | CC BY 4.0 | 10 m | 2019 | 101 MB zip | Adds a palm class (drained, often on peat) for 2019. Combine with MapBiomas. Medium priority, low effort. |
| Hansen GFC v1.13 (loss year to 2025) | `https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_lossyear_00N_100E.tif` | 200 [T] | CC BY 4.0 | 30 m | 2001–2025 | 86 MB per 10° tile | Fuel modifier: recently cleared or degraded peat burns more. Use "years since loss" as a covariate. Medium priority, low effort. |
| **Drainage canals (Dadap et al. 2021, CNN on Planet 2017)** | `https://stacks.stanford.edu/file/druid:yj761xk5815/geotiffs.zip` | 206 [T] | CC BY 3.0 | 5 m canal raster | 2017 | 227 MB | Canal density per 375 m cell, the main control on peat dryness (subsidence about 3.2× in drained areas [S]). Feed it to p_dry and persistence on peat. High priority, medium effort. |
| **OSM waterways (canals/ditches/drains)** via HOT export | `https://production-raw-data-api.s3.amazonaws.com/ISO3/IDN/_layers/osm/waterways.parquet` | 200 [T] (listing; updated 2026-10-11) | ODbL | vector | weekly | 271 MB GeoParquet | DuckDB-native (`ST_Read`/spatial). Filter `waterway in (canal, ditch, drain)` for a current, if incomplete, canal map that complements Dadap 2017. Medium priority, low effort. |
| Peat depth | No open national raster found. KHG 2017 (in use) has no depth. Gumbricht 2017 / GFW `gfw_peatlands` (CC BY 4.0, 30 m) give extent only | – | – | – | – | – | Gap. BBSDLP 2019 depth classes exist but no public download was found [S]. Skip for now. |
| Pantau Gambut | `https://pantaugambut.id/` | **522** (Cloudflare origin down) [T] | – | – | – | – | Unavailable. Skip. |

## 4. Peat moisture, groundwater and fire danger

| Dataset | Endpoint (tested) | Code | Licence | Res. | Latency | Size | Fit / priority / effort |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **GFWED (NASA Global Fire WEather Database), GEOS-5 FWI** with FFMC/DMC/**DC**/ISI/BUI/FWI | `https://portal.nccs.nasa.gov/datashare/GlobalFWI/v2.0/fwiCalcs.GEOS-5/Default/GEOS-5/2026/2026101400/FWI.GEOS-5.Daily.Default.2026101400.20261017.nc` | 206 [T] | NASA open, keyless | ~0.25°×0.3125° | analysis ~1–2 days behind; **forecast +8 days** (14 Oct run covers 15–22 Oct) [T] | 16.4 MB per global day | Replace `p_dry = exp(−rain/5)` with Drought Code (deep peat dryness, a 52-day memory) and DMC. The MERRA2-driven archive (`fwiCalcs.MERRA2/Default/MERRA2/{2000..2026}/FWI.MERRA2.Daily.Default.YYYYMMDD.nc`, 2019 files tested [T]) **gives the 2019/2023 hindcast a weather signal it currently lacks**. Highest priority, low–medium effort (xarray subset to the bbox, then a DuckDB table). |
| CEMS/GWIS fire danger (ECMWF FWI/DC/DMC forecast) | WMS `https://maps.effis.emergency.copernicus.eu/gwis?…&LAYERS=ecmwf.dc&STYLES=&TIME=2026-10-20` | 200 PNG (rendered for today and +3 d) [T]; GetFeatureInfo not offered | Copernicus | ~9 km | daily, ~10 d forecast | – | Good-looking map overlay (render the PNG per day). Raw grids: EWDS `cems-fire-historical-v1` (200 [T], **needs a CDS/EWDS key**); no forecast collection in the EWDS catalogue [T]. Medium priority. |
| SMAP L4 soil moisture (surface + root zone, 9 km, 3-hourly) | CMR latest `SMAP_L4_SM_gph_20261014T223000` [T]; data `data.nsidc.earthdatacloud.nasa.gov` (Earthdata login). GIBS `SMAP_L4_Analyzed_Root_Zone_Soil_Moisture/…/2026-10-14/…` | 200 / GIBS 200 [T] | NASA open, login | 9 km | ~2–3 days | ~140 MB per granule | Weakly informative over saturated peat, and GFWED DC covers the same need. GIBS tile is fine as a view-only layer. Low priority. |
| Open-Meteo soil moisture (forecast) | `api.open-meteo.com/v1/forecast?…&hourly=soil_moisture_27_to_81cm,vapour_pressure_deficit` | 200 [T] | CC BY 4.0 | ~0.1–0.25° | hourly, 16 d | tiny | Already our provider. Add VPD and soil moisture to the spread weather fetch at no cost. Medium priority, trivial. Note: `archive-api.open-meteo.com` returned **429 "daily limit exceeded"** from this shared IP [T], so prefer GFWED-MERRA2 for hindcasts. |
| BRGM SiPALAGA water-table (TMAT) sensors | `https://sipalaga.brg.go.id/` | **403 Cloudflare challenge** [T]; `tmat.brg.go.id`, `prims.brg.go.id` no connection [T] | gov | ~140+ stations | hourly upload of 10-min data [S] | – | **No public API found**; data is view-only in the app [S]. A Mendeley dataset by Hooijer & Vernimmen 2026 (10 km rainfall-driven water-table maps, CC BY 4.0, doi:10.17632/69mbg22fxf.1 [S]) is a possible substitute. Low priority until BRGM grants access. |
| GPM IMERG precipitation | GIBS `IMERG_Precipitation_Rate/…/2026-10-16/…` | 200 [T] | NASA open | 0.1° | ~4–12 h | – | Observed rain for the last 24–72 h (Open-Meteo rain is a model). View layer. Low priority. |

## 5. Exposure

| Dataset | Endpoint (tested) | Code | Licence | Res. | Vintage | Size | Fit / priority / effort |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **WorldPop R2025A constrained** | `https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2025/IDN/v1/100m/constrained/idn_pop_2025_CN_100m_R2025A_v1.tif` | 200 [T] | CC BY 4.0 | 100 m | 2025 | 59 MB | "People under smoke": aggregate to the 0.25° smoke grid once, then index > threshold × population per 3 h step. Show it per city and per province. High priority, low effort. |
| GHSL GHS-POP R2023A | `https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/…/GHS_POP_E2025_GLOBE_R2023A_4326_30ss_V1_0.zip` | 206 [T] | CC BY 4.0 | 1 km (30″) | 2025 epoch | 484 MB global zip | Alternative to WorldPop. Already 1 km, but a large download. Use only if WorldPop changes. |
| Health facilities (HOT/OSM) | `https://production-raw-data-api.s3.amazonaws.com/ISO3/IDN/_layers/osm/health_facilities.parquet` (also `.pmtiles`) | 200 [T] | ODbL | points | weekly (2026-10-11) | 2.8 MB | "Hospitals and clinics under smoke" list, plus a map layer (PMTiles plug straight into MapLibre). High priority, trivial. healthsites.io API returns **403 without an API key** [T]. |
| Schools (HOT/OSM) | `…/ISO3/IDN/_layers/osm/education_facilities.parquet` | 200 [T] | ODbL | points | weekly | 15 MB | Schools under smoke, linked to school-closure decisions. Medium priority, trivial. |
| Roads (HOT/OSM) | `…/ISO3/IDN/_layers/osm/roads.parquet` | 200 [T] | ODbL | lines | weekly | 1.1 GB | Access and distance-to-road for fire events (ignition proxy). The basemap (OpenFreeMap) already draws roads. Filter to `highway` primary–tertiary with DuckDB. Low priority. Geofabrik PBF and Overpass were **reset or unreachable** from the container [T]. |

## 6. Imagery: true colour, smoke plumes, night glow

All GIBS URLs are keyless WMTS. The MapLibre template is:

`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{LAYER}/default/{DATE}/{TMS}/{z}/{y}/{x}.{ext}`

| Layer | TMS / ext | Today 2026-10-17 | Yesterday 2026-10-16 | Notes |
| --- | --- | --- | --- | --- |
| `VIIRS_NOAA20_CorrectedReflectance_TrueColor` | `GoogleMapsCompatible_Level9` / jpg | 200 (10 KB) [T] | 200 [T] | Afternoon pass (~13:30 LT). Smoke over Sumatra and Java is clearly visible in the 5/16/25 test tile. **Best default "today" layer.** |
| `VIIRS_NOAA21_CorrectedReflectance_TrueColor` | Level9 / jpg | 200 [T] | 200 [T] | Same orbit, ~50 min apart. Use to fill swath gaps. |
| `VIIRS_SNPP_CorrectedReflectance_TrueColor` | Level9 / jpg | 200 [T] | 200 [T] | |
| `MODIS_Terra_CorrectedReflectance_TrueColor` | Level9 / jpg | 200 [T] | 200 [T] | Morning (~10:30 LT), before the afternoon convection. |
| `MODIS_Aqua_CorrectedReflectance_TrueColor` | Level9 / jpg | 200 but 1.6 KB (not yet filled) [T] | 200 [T] | Aqua is drifting and near end of mission. |
| `VIIRS_SNPP_DayNightBand_At_Sensor_Radiance` | `GoogleMapsCompatible_Level8` / png | 200, 0.7 KB (empty; night pass not yet processed) [T] | 200 (23 KB) [T] | **Night fire glow** (and city lights). Use the previous night's date. `VIIRS_NOAA20_DayNightBand` (Level7) also works [T]. `…_ENCC` stopped in 2023. |
| `VIIRS_Black_Marble` | Level8 / png, date `2016-01-01` | 200 [T] | – | Static night-lights base, good for "is that glow a fire or a town?". |
| `Himawari_AHI_Band3_Red_Visible_1km` | `GoogleMapsCompatible_Level7` / png, time `2026-10-17T03:00:00Z` | 200 [T] | 200 [T] | **10-min** imagery, but **grey single band, not true colour**. Rolling ~6 weeks. Gap 02:30–02:50 UTC (housekeeping). |
| `Himawari_AHI_Band13_Clean_Infrared` | `GoogleMapsCompatible_Level6` / png | 200 [T] | 200 [T] | 10.4 µm cloud tops. Also `Himawari_AHI_Air_Mass` [T]. |
| `VIIRS_*_Thermal_Anomalies_375m_All` | `GoogleMapsCompatible_Level8` / **mvt** | 404 = no features in tile [T] | 404 [T] | Vector fire points. Redundant with our FIRMS layer. |
| `SMAP_L4_Analyzed_Root_Zone_Soil_Moisture`, `IMERG_Precipitation_Rate`, `OPERA_L3_DIST-ALERT-HLS_Color_Index` | Level6 / Level6 / Level12 png | 200 [T] | | See sections 2 and 4. |

**Himawari true colour (not on GIBS):**

| Source | Endpoint (tested) | Code | Terms | Notes |
| --- | --- | --- | --- | --- |
| JMA "bosai" tiles (true colour `REP/ETC`, IR `B13/TBB`) | `https://www.jma.go.jp/bosai/himawari/data/satimg/{basetime}/fd/{validtime}/REP/ETC/{z}/{x}/{y}.jpg`. Times from `…/satimg/targetTimes_fd.json` | 200 at z5, **404 at z6** [T] | JMA content terms (Public Data License, CC BY 4.0-compatible) [M]; undocumented web API | **Web Mercator, aligns with GIBS** (checked visually). 10 min, max zoom 5 (~5 km). Easiest Himawari colour loop for the map. Medium priority, low effort, but unofficial and could change. |
| CIRA RAMMB SLIDER Himawari GeoColor / natural colour | `https://slider.cira.colostate.edu/data/json/himawari/full_disk/geocolor/latest_times.json`; tiles `…/data/imagery/YYYY/MM/DD/himawari---full_disk/geocolor/{ts}/{zz}/{row}_{col}.png` | 200 [T] | free with credit [M] | Full-disk projection (not Mercator), so it needs reprojection. Use it for a "loop" link-out rather than a map layer. |
| NICT Himawari true colour | `https://himawari8.nict.go.jp/img/D531106/latest.json` → `…/4d/550/YYYY/MM/DD/hhmmss_{x}_{y}.png` | 200 [T] | NICT terms [M] | Full-disk projection. Link-out only. |
| Build our own from NOAA AWS L1b (B01/B02/B03 + B04 green fix) | section 1 bucket | 200 [T] | open | Full freedom, but a heavy runner job (~60 MB per frame for the Indonesia segments). Not worth it before the JMA option is tried. |

## How these plug in

- **Spread model (`haze spread`, `spread-eval`):**
  - Add GFWED DC/DMC as p_dry (MERRA2 archive for the 2019 fit and the 2023 test; GEOS-5 forecast for live runs).
  - Add a year-matched MapBiomas class, Descals palm, Hansen years-since-loss and canal density as fuel covariates on the 375 m grid.
  - Fit p0 and persistence per class.
  - Score next-day masks as now, plus cumulative area against FireCCI S311 / MCD64A1.
- **Smoke model (`haze smoke`):**
  - Exposure = Σ (index > T) × WorldPop at 0.25°.
  - Facilities and schools inside the plume footprint go out as a static JSON list per run.
  - DC can scale the peat e-folding time (deeper dry peat burns longer).
- **Map (MapView.tsx):**
  - Add a date-aware raster source switcher for VIIRS true colour (today or yesterday), DNB night glow (last night), and the JMA Himawari 10-min loop (z ≤ 5).
  - Add an optional HOT health-facility PMTiles layer.
  - Credits: NASA GIBS, JMA, HOT/OSM (ODbL), WorldPop (CC BY 4.0).

## Ranked top 8

| # | Item | Why | Effort |
| --- | --- | --- | --- |
| 1 | **GFWED Drought Code / DMC** (GEOS-5 forecast + MERRA2 archive, keyless NetCDF) | Gives the spread model a real peat-dryness signal and fixes the weatherless 2019/2023 hindcast | Low–med |
| 2 | **GIBS VIIRS/MODIS true colour + DNB night glow** | Real smoke plumes and fire glow on the map today, no key, a few lines in MapView | Low |
| 3 | **MapBiomas Indonesia C3 annual 30 m** (+ Descals oil palm) | Year-matched fuel classes for both the calibration and test seasons | Med |
| 4 | **WorldPop 2025 + HOT OSM health/schools** | "People / hospitals / schools under smoke" headline numbers | Low |
| 5 | **FireCCI S311 300 m + MCD64A1** burned area | Independent area truth for spread-eval and season summaries | Med |
| 6 | **Drainage canals** (Dadap 5 m + OSM waterways parquet) | Strongest known control on peat fire persistence | Med |
| 7 | **Himawari 10-min imagery** (JMA true-colour tiles z ≤ 5; GIBS B3/B13) | Sub-hourly plume and pyro-convection view between VIIRS passes | Low |
| 8 | **Himawari fire detections**: own detector on NOAA AWS L1b (~11 min latency), or P-Tree WLF for internal use only | Diurnal FRP and "still burning" between polar passes; P-Tree licence bars redistribution | High |

Not recommended or blocked:

- FIRMS Landsat (US/Canada only).
- FIRMS geostationary (not in the API).
- SiPALAGA (Cloudflare, no API).
- KLHK/Kemenhut portals (502 from the container).
- Pantau Gambut (down).
- healthsites.io (needs a key).
- Open peat depth (none found).
- Sentinel-2 dNBR during smoke episodes (smoke and cloud ≈ 100%).
