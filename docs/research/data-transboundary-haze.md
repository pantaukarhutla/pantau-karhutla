# Transboundary haze: data sources, validation cases and attribution method

Research for a "Kabut asap lintas batas" feature: smoke from Indonesian fires reaching
Malaysia, Singapore and Brunei, plus the ASEAN context. Every endpoint below was probed
from this container (proxy egress) on **17 Oct 2026, ~16:30–17:00 UTC**, unless marked
otherwise. A severe episode was running at the time: Singapore 24-h PSI 212–229
(Very Unhealthy), Klang Valley API 160–172 and Johor API 161–193 (Unhealthy), and ASMC
Alert Level 3 for the southern ASEAN region since 26 Aug 2026.

## 1. Summary

| Need | Best source | Machine-readable? | Verdict |
| --- | --- | --- | --- |
| Singapore observed PSI / PM2.5 | data.gov.sg v2 real-time API | Yes, JSON, keyless (rate-limited) | **Use.** Open licence. |
| Singapore history 2014→ | data.gov.sg "Historical 24-hr PSI" dataset | Yes (datastore_search) | **Use** for validation. |
| Malaysia API per station | MyEQMS (DOE) `api3/publicportalapims/*` | Yes, undocumented JSON, keyless | **Use with care.** Last 24 h only, so archive it ourselves. No licence stated. |
| ASEAN haze context | ASMC (asmc.asean.org) KML + AJAX text | Partly (KML, HTML fragments) | **Link out, plus derived facts.** Terms say no republishing without MSS permission. |
| Brunei PSI | JASTRe env.gov.bn | No (hand-edited WordPress block, stale) | **Don't ingest.** Use CAMS at BSB plus a link. |
| Thailand (south) | Air4Thai PCD JSON | Not verified (TLS chain error, then 503) | Defer. |
| Indonesia ISPU | ispu.kemenlh.go.id | No public JSON found | Out of scope here. |
| Back-trajectory met data | NOAA ARL READY GFS 0.25° ARL files | Yes (HTTP directory) | Optional, for offline HYSPLIT checks. |

## 2. Endpoints

### 2.1 Singapore: NEA via data.gov.sg

| Item | Value |
| --- | --- |
| Real-time PSI | `GET https://api-open.data.gov.sg/v2/real-time/api/psi` (optional `?date=YYYY-MM-DD` or `?date=YYYY-MM-DDTHH:mm:ss`) → **200**, `application/json` |
| Real-time PM2.5 | `GET https://api-open.data.gov.sg/v2/real-time/api/pm25` → **200** |
| Legacy v1 | `https://api.data.gov.sg/v1/environment/psi`, `/pm25` → **200** (still live; `?date=` works for 2016–2019 days where v2 says "not found") |
| Auth | None needed. An optional `x-api-key` header raises the limits. |
| Rate limit (guide.data.gov.sg) | Requests per 10 s: v2 real-time 6 without a key, 12 with a dev key, 30 with a prod key. Datastore search 4/8/20. Over the limit returns HTTP 429. |
| Licence | Singapore Open Data Licence v1.0, so attribute "NEA / data.gov.sg". |
| Cadence | Hourly, published about 30 min after the hour (`updatedTimestamp` 00:30:34 for the 00:00 reading). |
| Spatial | 5 regions (north, south, east, west, central) with label points; `national` in older records. |
| Fields (psi) | `psi_twenty_four_hourly`, `pm25_twenty_four_hourly`, `pm25_sub_index`, `pm10_*`, `o3_*`, `co_*`, `so2_*`, `no2_one_hour_max` |
| Fields (pm25) | `pm25_one_hourly` per region (µg/m³). A `?date=` call returns all 24 hours. |
| Gotchas | Python `urllib`'s default User-Agent got **403** (CloudFront); curl and httpx UAs are fine. Archive gaps exist: v2 `date=2019-09-14` returns "not found", while v1 and the historical dataset have it. `2023-10-07` returns only 11 of 24 hours. |

Sample (v2 psi, 2026-10-18T00:00+08:00):
`psi_twenty_four_hourly {central 185, east 182, north 129, south 168, west 215}`,
`pm25_twenty_four_hourly {central 136, east 133, north 83, south 119, west 165}`.
The 1-h PM2.5 peak was 243 µg/m³ (west) at 17 Oct 14:00 SGT.

**History:** dataset `d_b4cf557f8750260d229c49fd768e11ed` ("Historical 24-hr PSI"). It is hourly, 5 regions, 108,864 rows, from 2014-04-01 to 2026-08-31.
`GET https://data.gov.sg/api/action/datastore_search?resource_id=d_b4cf557f8750260d229c49fd768e11ed&offset=N&limit=100` → 200.
Timestamps are in `d/m/yyyy H:MM` SGT format and values are strings. Collection 2216 holds the "Historical PM2.5" per-year datasets
(for example 2022 = `d_7ed60bd5f903ab2d09bf4078e6210a10`). Its disclaimer: "may contain missing records, not QC'd".

PSI from PM2.5 (24-h µg/m³, NEA): 0–12 → 0–50 · 13–55 → 51–100 · 56–150 → 101–200 ·
151–250 → 201–300 · 251–350 → 301–400 · 351–500 → 401–500 (piecewise linear).
Check: 165 µg/m³ gives PSI 215 by this table, and the API reported exactly that.
Bands: ≤50 Good, 51–100 Moderate, 101–200 Unhealthy, 201–300 Very Unhealthy, >300 Hazardous.

### 2.2 Malaysia: DOE APIMS (MyEQMS portal)

The old `apims.doe.gov.my` returns **404**, and `aqms.doe.gov.my` gave no connection. The current public
portal is `https://eqms.doe.gov.my/` (Vue/ArcGIS SPA). I extracted its API from the JS bundle
(`js/483.a8a22cd3.js`). Base: `https://eqms.doe.gov.my/api3/publicportalapims`.

| Endpoint | Result | Content |
| --- | --- | --- |
| `/statelist` | 200 JSON | 16 states: 1 Johor, 10 Selangor, 12 Sabah, 13 Sarawak, 14 WP KL, 15 Labuan, 16 Putrajaya, … |
| `/apitablehourly?stateid=13` | 200 JSON | `api_table_hourly[]`: `STATION_ID, STATION_LOCATION, LATITUDE, LONGITUDE, DATETIME (local, MYT), API, PARAM_SYMBOL`. Last 24 h × every station in the state. |
| `/apitablehourly?stateid=N&datetime=YYYY-MM-DDTHH:00:00` | 200 | Works for the last 24 h only. A datetime 7 days or more back returns `[]`. |
| `/apiranking` | 200 JSON | 5 cleanest stations right now |
| `/datatrendchart?stationid=…` | 200 JSON | `highcharts_bar[]`, 1,560 rows = 24 h × all ~65 stations with `API_CATEGORY` (the stationid parameter seemed ignored) |
| `/getstationidbylonglat?latitude=&longitude=` | 200 | nearest station + distance |
| `/currentapicurrentlocation?stationid=` | 200 | current API, dominant pollutant, class, site address |

Auth: none (a browser UA was sent). Licence: **none published**, so treat it as all rights reserved
and attribute "Jabatan Alam Sekitar Malaysia (APIMS)". Ask DOE for permission before showing it publicly.
Cadence: hourly, about 10 min past the hour (the SPA retries at minute 10).
`PARAM_SYMBOL "**"` = PM2.5 is the dominant pollutant; `*` = PM10 (legend in the bundle).

Key stations (lat, lon; API at 18 Oct 00:00 MYT):

| City | Station | Lat, lon | API |
| --- | --- | --- | --- |
| Kuala Lumpur | CA15W Batu Muda / CA16W Cheras | 3.212, 101.682 / 3.106, 101.718 | 160 / 162 |
| Klang Valley | CA19B Petaling Jaya, CA20B Shah Alam, CA21B Klang, CA17W Putrajaya | | 165 / 166 / 168 / 165 |
| Johor Bahru | CA33J Larkin, CA34J Pasir Gudang | 1.495, 103.736 / 1.470, 103.894 | 179 / 193 |
| Kuching | CA65Q Kuching, CA64Q Samarahan, MCAQM002 Serian | 1.562, 110.389 | 79 / 84 / 106 |
| Sri Aman (W Sarawak) | CA63Q | 1.220, 111.465 | 91 |
| Kota Kinabalu | CA50S, MCAQM003 Politeknik KK | 5.880, 116.056 | 52 / 66 |
| Miri / Limbang (near BSB) | CA56Q / CA54Q | 4.425, 114.012 / 4.759, 115.014 | 61 / 43 |

API from PM2.5 (DOE `Documents/APIMS/API_Calculation.pdf`, fetched, 200; a USEPA-modified table,
24-h mean): 0–12.0 → 0–50 · 12.1–50.4 → 51–100 · 50.5–55.4 → 101–150 · 55.5–150.4 → 151–200 ·
150.5–250.4 → 201–300 · 250.5–350.4 → 301–400 · 350.5–500.4 → 401–500. This differs from
Singapore PSI between 50 and 150 µg/m³, so convert per country and never compare raw index numbers.
Bands: 0–50 Baik, 51–100 Sederhana, 101–200 Tidak Sihat, 201–300 Sangat Tidak Sihat, >300 Berbahaya.

### 2.3 ASEAN Specialised Meteorological Centre (ASMC)

The site sits behind an **Azure WAF**: curl's default UA → 403, browser UA → 200. Some files
(`hotspotsday/*.kml`) still returned 403 after several quick requests, so the limit is rate- or rule-based. Fetch
at most once an hour with a descriptive UA and back off.

| Product | Endpoint | Status | Notes |
| --- | --- | --- | --- |
| Home / regional haze map | `https://asmc.asean.org/home/` | 200 | Embeds the current file URLs in JS (`ASMC_KML_URL`, `ASMC_HOTSPOT_NOAA19_URL`, …) and `startupDatePayload.rawIssueDate`. |
| Haze boundaries (polygons) | `files/warnadv/haze/boundaries/HazeBoundaries_YYYYMMDD_HHMMSS.kml` | 200 KML, 13 kB | Placemarks named "Moderate Haze" / "Dense Haze" (styles `modHaze`, `denHaze`). This is the satellite-analysed smoke extent, the best independent check of our plume footprint. |
| Hotspots (NOAA-20 VIIRS) | `files/warnadv/haze/hotspots/Haze_Hotspots_YYYYMMDD_HHMMSS.kml` | 200 KML, 262 kB | 670 points on 17 Oct. `ExtendedData`: satellite, time (UTC hhmm), region (Kalimantan 277, Sulawesi 148, Nusa Tenggara 131, Sumatra 25, SabahSarawak 2, …). |
| Day/night hotspots | `files/warnadv/haze/hotspotsday/NOAA20_DayHotspot_*.kml`, `hotspotsnight/…` | 403 (WAF) | |
| 2500 ft wind analysis | `files/warnadv/haze/wind/Haze_Wind_YYYYMMDD_000000.kml` → PNG ground overlay (81.25–150 E, −18.75–28.75 N) | 200 | Image only |
| IR haze satellite | `files/warnadv/haze/mtsat/MTSAT_IR_Haze_*.png` | 200, 8 MB PNG | |
| File URL for a past date | `POST wp-content/themes/asmctheme/page-functions/functions-ajax-haze-{hotspots,bounds}.php`, form `date=15 Oct, 2026`, with `Referer: https://asmc.asean.org/home/` and `X-Requested-With: XMLHttpRequest` | 200, returns a KML URL | Without these headers: WAF 403. Wrong date format: 400 `{"error":"Date format not allowed."}`. 90-day window. |
| Daily situation text | same with `functions-ajax-haze-content.php` | 200 HTML fragment | e.g. "Moderate to dense transboundary smoke haze was observed over parts of Peninsular Malaysia, Singapore, Kalimantan, Sumatra, and the western parts of Sarawak…" |
| Outlook text | `functions-ajax-haze-outlook.php` | 200 HTML fragment | Prevailing winds and risk statement |
| Alert levels | `https://asmc.asean.org/asmc-alerts/` | 200 HTML table (date, level, text, year filter 2022–2026) | Scrape the table. No feed. |
| RSS | `https://asmc.asean.org/feed/` | 200 | Outlooks and monthly reviews only, no alerts |
| WIS2 data catalogue | `https://wis2.asmc.asean.org` | connection reset | Not verified |

Cadence (from the page): at Alert Level 0–1 the regional haze situation is updated daily at **09 UTC**; at
Level 2–3 it is updated at **03 and 09 UTC** (03 UTC uses NOAA-20 night passes).

Alert levels (AATHP early-warning tiers, as defined on the ASMC page):

| Level | Meaning |
| --- | --- |
| 0 | No transboundary smoke haze / stand down |
| 1 | Dry season |
| 2 | Increasing risk: escalating hotspots, moderate to dense haze for 2 or more consecutive days, dry weather persisting, winds blowing haze towards neighbours |
| 3 | High risk of severe transboundary haze: significant persistent hotspots, widespread moderate to dense haze for 2 or more days, dry, winds towards neighbours |

Recent issues from the table: 26 Aug 2026 L3 (southern ASEAN), 03 Aug 2026 L2, 10 Jul 2026 L1, and in
2025 L2 on 19 Jul and L1 on 12 Aug. Mekong sub-region entries are interleaved, so parse the "for the
Southern ASEAN Region / Mekong sub-region" phrase from each row.

**Licence: restrictive.** The terms of use (NEA/MSS) say content "shall not be reproduced, republished … without
the prior written permission of MSS", with no commercial use and no reuse of graphics. For the app,
show only derived facts (current alert level and date, a short summary in our own words) and link
to ASMC. Use the KML only internally for validation, and email MSS for permission to display haze polygons.

### 2.4 Brunei: JASTRe

`https://www.env.gov.bn/` returns 200 (WordPress). The PSI block is page content (`/wp-json/wp/v2/pages/1588`)
last modified 2026-09-02 and labelled "PSI reading as of 11AM 02/09/2026". The district values are not in the
text (they are images or shortcodes), so it is **not machine-readable** and is stale between hand edits.
`jastre.bn` gave no connection, and a redirect to `www.pm.gov.bn` was refused by the proxy. News (Borneo
Bulletin via The Star) reports updates 5×/day (07, 09, 11, 14, 16 local) during haze, 4 districts, PM2.5
folded into the PSI since 1 Sep 2026, and bands 0–50/51–100/101–200/201–300/>300. Fallback: CAMS PM2.5 at
BSB from Open-Meteo, plus the nearby APIMS stations Limbang (CA54Q) and Miri (CA56Q).

### 2.5 Others

| Source | Endpoint | Result | Note |
| --- | --- | --- | --- |
| Thailand Air4Thai (PCD) | `https://air4thai.pcd.go.th/services/getNewAQI_JSON.php` | curl: TLS "unable to get local issuer" (server sends an incomplete chain); WebFetch: 503 | Southern Thailand (Songkhla, Yala, Narathiwat) is relevant in Sumatra-source years. Not verified, so defer. |
| WAQI | `https://api.waqi.info/feed/{city}/?token=` | 200, but the `demo` token always returns Shanghai | A free token is needed. Aggregator with unclear redistribution terms; skip. |
| OpenAQ v3 | `https://api.openaq.org/v3/locations` | 401 without `X-API-Key` | Free key. Possible single path to Malaysian and Thai stations. Not explored. |
| Indonesia ISPU (KLHK) | `https://ispu.kemenlh.go.id/app/` | 200 HTML | No JSON endpoint found in the page JS |
| Open-Meteo CAMS | `air-quality-api.open-meteo.com/v1/air-quality` | 200 | Already used. Historical global PM2.5 is **null for 2019** and present for 2023, so it starts around 2022. |
| Open-Meteo ERA5 | `archive-api.open-meteo.com/v1/archive` | **429** "Daily API request limit exceeded" | Shared egress quota. Cache aggressively or use the CDS ERA5 API for hindcasts. |
| NOAA ARL READY | `https://www.ready.noaa.gov/data/archives/gfs0p25/YYYYMMDD_gfs0p25`, `/data/forecast/YYYYMMDD/` | 200 | ARL-format met for HYSPLIT (needs a registered HYSPLIT binary). Offline cross-checks only. |

## 3. Validation episodes (Singapore 24-h PSI, max over 5 regions)

From the data.gov.sg historical dataset and API, verified here:

| Episode | Peak 24-h PSI | When (SGT) | Other peaks | Context |
| --- | --- | --- | --- | --- |
| 2015 (El Niño) | **322** (south) | 25 Sep 2015 08:00 | 231 on 24 Sep 16:00; 229 on 24 Oct 10:00; 214 on 29 Sep | 3-h PSI 341 on 25 Sep (news). Schools closed 25 Sep. South Sumatra was the dominant source (Koplitz 2016). |
| 2019 | **154** (south) | 19 Sep 2019 02:00 | 124 on 15 Sep; 129 on 23 Sep | Indonesia's KLHK said there was no transboundary haze (Al Jazeera, 10 Sep 2019). Kalimantan and Sumatra fires. |
| 2023 | **123** (east) | 7 Oct 2023 20:00 | 116 central | First Unhealthy PSI since 2019. KLHK (2 Oct 2023) said there was "no transboundary haze reaching Malaysia"; Sarawak cited ASMC data in reply. |
| 2026 (ongoing) | **229** | 16 Oct 2026 16:00 | 183 on 10 Oct; 162 on 8 Oct; 134 on 5 Oct; 123 on 20 Sep | Live test. ASMC L3. APIMS archive must start now (24-h retention). |

Indonesian statements are a sensitive input, so the UI should present model results and observations
side by side, neutrally, and attribute every number to its agency.

## 4. Literature on attribution

| Study | Method | Finding relevant to us |
| --- | --- | --- |
| Reddington et al. 2014, ERL 9 094006 | Chemical transport model plus a Lagrangian model, 2004–2009 | Fire share of Singapore's PM2.5 enhancement: southern Sumatra 42–62%, central Sumatra 21–35%, Kalimantan 14–15% |
| Kim et al. 2015, Atmos. Environ. | GEOS-Chem adjoint (source-receptor sensitivity) | 2006: Sumatra had 37% of emissions but 63% of population-weighted exposure. Location matters more than emission mass. |
| Koplitz et al. 2016, ERL 11 094023 | Adjoint sensitivities (2006 met) × GFAS 2015 emissions | South Sumatra >50% of regional exposure in 2006 and 2015. Central Kalimantan emitted as much as South Sumatra but caused about 1/3 of its exposure. Riau was not significant. About 100k excess deaths. |
| Crippa et al. 2016, Sci. Rep. | WRF-Chem 10 km | 69 M people exposed to unhealthy air in 2015. About 11,880 short-term excess deaths. |
| Engling et al. 2014, ACP 14 8043 | Molecular tracers (levoglucosan) + CMB + back-trajectories, Singapore 2006 | Sumatra and Kalimantan peat and forest fires identified as the source |
| Chen et al. 2018, ACP 18 7781 | Aerosol mass spectrometer, Singapore 2015 | Smoke aged about 1–4 days on arrival, which sets our minimum spin-up |
| Kiely et al. 2019 (already in models.md) | | Inventories underestimate peat PM2.5 by about 1.4–3.5× |

Takeaways: (1) attribution is linear and receptor-specific, and adjoint/footprint approaches are standard.
(2) Shares depend more on wind regime than on emission totals, so show the regime. (3) Absolute PM is
biased low by inventories, so attribute **shares**, not µg/m³. (4) CAMS also runs low in this
episode: Singapore CAMS max was 113 µg/m³ (14–17 Oct) against an observed 1-h peak of 243, and on
7 Oct 2023 CAMS gave 16–43 against an observed 24-h mean of about 63.

## 5. Feature design

### 5.1 Model changes (`pipeline/src/haze/smoke.py`)

The puff model already carries `src` (source index) per puff, and `fire_events` has
`provinsi`/`kabupaten`/`on_peat`. That makes **forward tagging** almost free:

1. **Per-source receptor contributions.** In `city_outlook`, for each receptor and frame,
   evaluate the Gaussian kernel of each puff at the receptor and `np.bincount` by `src`. This gives
   `contrib[city, frame, source]`. The model is linear (no chemistry), so the parts sum exactly to the
   index. Then aggregate to kabupaten, provinsi, and peat vs non-peat via `sources.id → fire_events`.
2. **Spin-up / hindcast window (required).** Today puffs start at t0 from fires seen in the last 24 h,
   so smoke already in transit (1–4 days from Kalimantan) is missing, and "who is causing today's haze
   in Singapore" cannot be answered. Run from t0 − 96 h using analysis winds (`past_days=4` on the
   Open-Meteo wind call; verified to work) and hotspots by actual detection hour (per-day FRP, not
   24-h mean persistence). Emit the frames from t0 − 72 h onwards: the hindcast part feeds the observed comparison
   and the forecast part feeds arrival times.
3. **Non-Indonesian sources.** FIRMS BBOX (94.5–141.5 E, −11.5–6.5 N) already includes Malaysian,
   Bruneian and Timorese detections, but `events.py` keeps only `in_indonesia`. Add those as a
   separate source class ("Malaysia/Brunei, local") so that Kuching and KL shares are not forced onto
   Indonesia. Fires outside the box (Mekong) are untracked; note that.
4. **Receptor footprints (cross-check).** Release back-particles from each receptor every 3 h and
   integrate them backwards over 96 h on the same 10 m winds (negate velocity, same RK2). Grid the
   residence time to a footprint F(x). Footprint × emission grid gives the source shares, which
   should agree with (1). Large disagreement flags low confidence. This is our "HYSPLIT-like"
   back-trajectory, computed in-house and consistent with the forward model.
5. **Uncertainty ensemble.** Use about 8 members: wind perturbations (speed ×0.8/1.2, direction ±15°),
   one member on 925 hPa winds, and peat EF/β low/high (Kiely factor). Report each province share as
   median and min–max across members. Give a share only when the total index at the receptor is
   ≥ 15 and the provincial share is ≥ 10%. Otherwise label it "lainnya".
6. **Receptors.** Add Bandar Seri Begawan (4.890, 114.942) and Kota Kinabalu (5.980, 116.073) to
   `REGIONAL_CITIES`, and optionally Hat Yai (7.008, 100.475). All lie inside PLUME_GRID (to 8° N).
   Map each receptor to its observation stations: SG regions, KL (CA15W, CA16W), JB (CA33J, CA34J),
   Kuching (CA65Q), KK (CA50S), BSB (none, so CAMS plus Limbang CA54Q).

### 5.2 New ingest jobs

| Job | Source | Schedule | Table |
| --- | --- | --- | --- |
| `haze obs-sg` | data.gov.sg v2 psi + pm25 (one call each) | hourly at :40 | `obs_aq(country, station_id, region, lat, lon, ts_utc, pm25_1h, pm25_24h, index_24h, index_kind='PSI')` |
| `haze obs-my` | APIMS `apitablehourly` for states 1, 10, 12, 13, 14, 16 (6 calls, ≥2 s apart) | hourly at :20, upsert last 24 h | same, `index_kind='API'` (no raw PM2.5, so invert the DOE table to approximate PM2.5) |
| `haze asmc` | home page → current KML URLs; boundaries + hotspots KML; alerts table | every 3 h, UA set, back off on 403 | `asmc_alerts(issued, region, level, url)`, `asmc_haze_polygons(date, density, geom)` (internal only) |
| `haze backfill-sg` | historical dataset, paged by offset | once | `obs_aq`, for 2015/2019/2023 validation |

All raw responses are cached under `CACHE_DIR` as fetched. APIMS has 24-h retention, so a missed
day cannot be recovered.

### 5.3 Skill checks

- Per receptor: hindcast index (t0 − 72 h…t0) against observed PM2.5 excess over a clean baseline
  (rolling 30-day 10th percentile). Compute Spearman r, hit rate for arrival within ±6 h of the first hour
  over 55 µg/m³ (the SG "Unhealthy" PM2.5 edge), and log it like `skill_vs_cams`.
- Footprint against ASMC "Moderate/Dense Haze" polygons: CSI on the 0.25° grid daily at 09 UTC.
- Episode replays (2015-09-20→30, 2019-09-10→25, 2023-10-01→10, 2026-10-01→now) with FIRMS
  SP archive plus ERA5 winds (CDS, since the Open-Meteo archive hit the shared quota). This tests whether
  the provincial ranking matches the literature (South Sumatra dominant for Singapore in 2015; Kalimantan for Kuching).

### 5.4 UI (Bahasa default, English toggle)

Panel **"Asap Lintas Batas"** (new tab next to the smoke layer):

| Element | Content (ID copy) |
| --- | --- |
| Header chip | "Status ASEAN: Siaga 3 (sejak 26 Agu 2026) · sumber ASMC" with a link |
| City cards (SG, KL, JB, Kuching, BSB, KK) | "Perkiraan asap tiba: Sab 18 Okt 14:00 WIB" · "Puncak indeks asap model: 120" · "Teramati: PSI 24 jam 215 (Sangat tidak sehat) · NEA, 00:00 SGT". Native index and bands per country, plus PM2.5 µg/m³ for a common scale. |
| Chart per city | Line for observed PM2.5 (or API) over the last 72 h, model smoke index over hindcast + 72 h forecast (shaded ensemble range), and a vertical "sekarang" line. |
| Attribution bar | "Perkiraan asal asap (model)": stacked bar by provinsi with ranges, e.g. "Kalimantan Barat 45% (30–60%)". Includes "Sumber di Malaysia/Brunei" and "Tidak terlacak" (CAMS excess the model does not explain). Clicking opens the fire events behind it. |
| Map | Receptor footprint (where today's air at the city came from, 96 h) and plume tracks, optionally with ASMC haze polygons (only if MSS permits). |
| Caveat (always visible) | "Atribusi ini adalah estimasi model eksperimental berbasis angin 10 m dan titik panas satelit; bukan penetapan resmi asal asap. Kebakaran yang tertutup awan, asap lebih tua dari 4 hari, dan sumber di luar wilayah model tidak terhitung. Angka resmi: NEA, DOE Malaysia, JASTRe, ASMC." |

Wording rules: neutral ("asap terdeteksi berasal dari…", never "Indonesia menyebabkan…"),
always show the uncertainty range, hide shares when confidence is low ("Keyakinan rendah: angin lemah
dan berubah-ubah"), and attribute every observation to its agency with a timestamp.

### 5.5 Attribution caveats (for docs/models.md and the UI)

- 10 m wind on a 1.5° grid. Weak or variable winds over Borneo (ASMC's own outlook says "light and
  variable") make the Kuching/BSB shares unstable, so the spread between ensemble members is the honest signal.
- No plume rise. Deep flaming fires that loft smoke above the boundary layer are misplaced.
- Hotspots go missing under cloud and thick smoke (ASMC: "full extent … could not be determined
  due to obscuration"). This biases shares toward clear-sky provinces.
- Emissions are low by about 1.4–3.5× (Kiely 2019). Shares are more robust than magnitudes; magnitudes
  are not calibrated.
- Urban background PM2.5 (traffic, shipping) at receptors is not smoke. Compare excess over a baseline only.
- Index conversions differ (SG PSI vs MY API vs BN PSI vs ID ISPU), so compare in µg/m³ 24-h means.
- Licences: NEA open; DOE unstated, so ask; ASMC permission required to republish.

## 6. Open items

1. Email MSS/ASMC (permission for haze polygons and alert text) and DOE Malaysia (APIMS reuse).
2. Get a data.gov.sg dev key (12 req/10 s) to make backfills faster.
3. Re-test Air4Thai (TLS chain) and the WIS2 catalogue from another network.
4. Decide on ERA5 access (CDS key) for the 2015/2019 replays.
