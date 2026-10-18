# Indonesian official and local data sources

Survey of Indonesian government data we could add to haze, checked from this container on
**17 Oct 2026, 16:30–17:15 UTC**. The container's traffic leaves through a proxy in the US
(Cloudflare `cf-ray` … `-IAD`), the same kind of place GitHub Actions runs. So "reachable here"
is a fair guess for "reachable from the cron job". Every sample below was fetched live.

Key: ✅ works without login · 🔑 needs a key or token · 🖼 image only (no numbers) · ⛔ blocked or
broken from here · 🤖 robots.txt disallows it.

## 1. Changes since earlier writing

| Old host | Status today | Replacement |
| --- | --- | --- |
| `sipongi.menlhk.go.id` | ⛔ NXDOMAIN (proxy returns 502). KLHK was split into the Ministry of Forestry (Kemenhut) and the Ministry of Environment (KLH). | `sipongi.gakkum.kehutanan.go.id` (front end) + `opsroom.sipongidata.my.id/api` (the JSON backend it calls) |
| `ispu.menlhk.go.id` | ⛔ NXDOMAIN | `ispu.kemenlh.go.id` (KLH/BPLH) |
| `modis-catalog.lapan.go.id` | ⛔ NXDOMAIN | `hotspot.brin.go.id` |
| `www.menlhk.go.id` | TLS certificate expired | `kehutanan.go.id`, `kemenlh.go.id` |

## 2. Summary

| # | Source | Endpoint | Here? | Format | Cadence | Auth | Feature it enables |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | KLH ISPU stations | `ispu.kemenlh.go.id/apiweb/stasiun` | ✅ 200 (with the public web token) | JSON | hourly | 🔑 Bearer token that ships inside the public web app | **Ground-truth PM2.5/PM10 at 119 stations** (52 in Sumatra and Kalimantan). Lets us calibrate the smoke index and show real city air quality. |
| 2 | SiPongi+ hotspots | `opsroom.sipongidata.my.id/api/opsroom/indoHotspot` | ✅ 200 | GeoJSON (gzip) | ~per overpass | none | The official national hotspot count (what government and media quote). Each point carries a BRIN or NASA source, a confidence level, and desa/kecamatan/kabupaten tags. |
| 3 | SiPongi+ burned area | `…/api/list/luas-kebakaran/provinsi`, `…/kabupaten` | ✅ 200 | JSON | monthly (official figure) | none | Official burned area (ha) per province and per kabupaten per year, to set beside our modelled area. |
| 4 | SiPongi+ Daops ops | `…/api/daops/pemadaman` | ✅ 200 | GeoJSON | daily | none | **Where Manggala Agni crews are fighting fires** (point, date, hectares put out, note). Can mark fire events as "being handled". |
| 5 | BNPB karhutla ops | `gis.bnpb.go.id/server/rest/services/2026_karhutla/mv_prov_karhutla_2026/FeatureServer/3` | ✅ 200 | ArcGIS JSON/GeoJSON | irregular (last 26 Sep) | none | Per-province response: personnel, water-bombing sorties, OMC (cloud seeding), visibility, area put out, deaths, situation text. |
| 6 | BRIN hotspots | `hotspot.brin.go.id/getHS`, `/getCSV` | ✅ 200 | GeoJSON, CSV | per overpass | none | BRIN's own VIIRS hotspots with Indonesia's official 7/8/9 (low/medium/high) confidence scale and kecamatan names. |
| 7 | BMKG forecast | `api.bmkg.go.id/publik/prakiraan-cuaca?adm4=` | ✅ 200 | JSON | 2×/day, 3-hourly steps, 3 days | none (60 req/min/IP) | City forecast that includes the **"Kabut/Asap" (smoke haze) weather code 45**, visibility, and wind. |
| 8 | BMKG SPARTAN FDRS maps | `dataweb.bmkg.go.id/cuaca/spartan/{region}_{index}_{step}.png` | ✅ 200 🖼 | PNG | daily (obs + H+0…H+7) | none | Official fire-danger maps (FFMC, DMC, DC, ISI, BUI, FWI) per province, as an overlay or a panel. |
| 9 | BMKG satellite/haze images | `inderaja.bmkg.go.id/IMAGE/…`, `…/Trajektori/Asap.png` | ✅ 200 🖼 | PNG | 10 min to daily | none | Himawari geo-hotspot, smoke trajectory and GSMaP dry-days images, for a "BMKG says" panel. |
| 10 | BMKG HTH and ENSO | `dataweb.bmkg.go.id/iklim/hari-tanpa-hujan.png`, `…/el-nino-la-nina/*_SSTA_latest.gif` | ✅ 200 🖼 | PNG/GIF | dasarian (10-day) / weekly | none | Season context: dry-spell map and SST anomaly. |
| 11 | InaRISK fire hazard | `gis.bnpb.go.id/server/rest/services/inarisk/layer_bahaya_kebakaran_hutan_dan_lahan/ImageServer` | ✅ 200 | ArcGIS ImageServer (F32, 100 m) | static | none | Official karhutla hazard index (0–1), for a "fire-prone area" layer or for weighting risk. |
| 12 | BMKG PM2.5 (BAM monitors) | `www.bmkg.go.id/api/kualitas-udara/pm25` | 🤖 not fetched | JSON | hourly | unknown | Second PM2.5 network (Palangka Raya, Pekanbaru, …). Ask BMKG for access. |
| 13 | Kalbar Satu Data (CKAN) | `data.kalbarprov.go.id/api/3/action/package_search` | ✅ 200 | CKAN JSON → XLSX/PDF | ad hoc, yearly | none | Historic hotspot and burned-area tables, plus Satgas daily PDFs. Good for back-fill, not live. |
| 14 | DIBI (BNPB disaster DB) | `dibi.bnpb.go.id` | ⛔ timeout (Cloudflare reached, origin silent) | — | — | — | Incidents, evacuees, affected people. Not usable from here. |

## 3. Details

### 3.1 KLH ISPU — `ispu.kemenlh.go.id` (Ministry of Environment / BPLH)

| Item | Value |
| --- | --- |
| Front end | `https://ispu.kemenlh.go.id/app/` (Angular). Its config sets `api.url = ["https://ispu.kemenlh.go.id/apiweb", "https://ispu.kemenlh.go.id/brin/api/"]` and a static JWT `api.token`. |
| Station list + latest values | `GET /apiweb/stasiun` with `Authorization: Bearer <token>` → 200, 119 rows. Without the token → `{"status":{"code":401,"desc":"Unauthorized"}}`. |
| Station detail | `GET /apiweb/stasiun/detail/id/{id_stasiun}` → latest values plus `waktu_24` and 24-hour hourly series. |
| Other (BRIN side, `x-api-key`) | `/brin/api/globalWind.php` (GFS GRIB JSON, refTime is from **July 2026**, so stale), `rain.php`, `temp.php` and `ispuPediction.php` (all return a PHP warning and empty data). Not usable. |
| Fields | `id_stasiun, waktu (local), lat, lon, a_pm25, a_pm10, a_so2, a_o3, a_no2` (concentrations, µg/m³), `c_*` (category 1–5), `val` (ISPU index), `cat` (BAIK … BERBAHAYA), `provinsi, kota, time_z, is_maintenance, tipe_text (KLH/BPLH or INTEGRASI)` |
| Coverage | 119 stations. Sumatra/Kalimantan fire belt: Kalteng 8, Kalbar 5, Kalsel 4, Kaltim 10, Kaltara 1, Riau 7, Jambi 4, Sumsel 9, Babel 1, Lampung 1, Aceh 4, Sumut 4, Sumbar 2. |
| Update | Hourly. The `waktu` value of every station was within the last hour. |
| CORS | `Access-Control-Allow-Origin: *`, so a browser could call it directly. Proxy through the pipeline anyway, so the token stays out of our bundle. |
| Licence | None published. The token is in a public bundle, but it was not issued to us. **Ask KLH (Deputi Pengendalian Pencemaran) for an API key** before production use; until then, treat this as research only. |
| Robots | `/robots.txt` returns 404, so there are no restrictions. |

Sample (17 Oct 2026 23:00 WIB):

```json
{"id_stasiun":"PALANGKARAYA","waktu":"2026-10-17 23:00:00","lat":"-2.22154","lon":"113.86",
 "a_pm25":"1469.71","a_pm10":"1955.89","val":"4140","cat":"BERBAHAYA","provinsi":"Kalimantan Tengah"}
```

Stations in the fire belt at that hour included Barito Selatan 497, Gunung Mas 495, Tebo 375,
Muaro Jambi 350, Pontianak 211 and Palembang 206 µg/m³ PM2.5.

**Data quality.** `a_pm25` and `val` do not always agree: Katingan has `a_pm25` 1184 but ISPU 30
(BAIK), and Kampar has 441 but ISPU 59. `a_*` looks like the raw latest hour, while `val` is the
validated or averaged ISPU. Use `val`/`c_*` for categories. Clip or flag `a_pm25` values above
~1500, and those that disagree strongly with `val`. Skip stations with `is_maintenance=1`.

**Value.** This is the single biggest gap in the app: the smoke model is "not calibrated against
stations" (docs/models.md). These stations give real PM2.5 in exactly the cities the model
forecasts (Palangka Raya, Pontianak, Pekanbaru, Jambi, Palembang, Banjarmasin). Possible uses:
city cards with measured AQI, a nightly skill score of the model against stations (CSI or
correlation), and a station layer on the map.

### 3.2 SiPongi+ — Ministry of Forestry (Ditjen Gakkum / Direktorat PKHL)

The front end is `https://sipongi.gakkum.kehutanan.go.id/` (SvelteKit; `robots.txt`: `Disallow:`
is empty, so everything is allowed). All data comes from **`https://opsroom.sipongidata.my.id`**,
a `.my.id` domain that is not `.go.id` but is hard-coded in the official site. The responses carry
`X-RateLimit-Limit: 300` (per minute) and reflect the request's Origin back in CORS. No auth.
Responses come back gzip-encoded even without `Accept-Encoding`, so use `curl --compressed` /
`httpx` (which handles it automatically).

| Endpoint (GET, base `https://opsroom.sipongidata.my.id`) | Params | Result here | Content |
| --- | --- | --- | --- |
| `/api/opsroom/indoHotspot` | `wilayah=IN&filterperiode=false&late=24&satelit[]=…&confidence[]=low&confidence[]=medium&confidence[]=high` (`late` = hours: 12/24/48) | 200, 297 KB gzip. 10 729 NASA points or 11 134 BRIN points in 24 h. | GeoJSON points. `sumber` (LPN-NPP, LPN-NOAA20, LPN-MODIS, NASA-SNPP, NASA-NOAA20, NASA-MODIS), `ori_sumber`, `confidence` (number), `confidence_level` (low/medium/high), `date_hotspot_ori` (UTC), `desa, kecamatan, kabkota, nama_provinsi, provinsi_id`, `counter`, `kawasan` (empty in every point we saw). |
| `/api/konfigurasi` | — | 200 | `sumber_satelit: "nasa"`, the source the site shows by default (it switches between `lapan` and `nasa`) |
| `/api/getProvinsi/all` | — | 200 | Provinces with `id_mendagri`, centroid and `total_hs` |
| `/api/grafik/hotspot` | `text=…&satelit=NASA-SNPP&tahun=2026` | 200 | Monthly counts: `{"data":[69,68,148,75,68,126,450,5769,7108,4958,0,0]}` |
| `/api/list/luas-kebakaran/provinsi` | `tahunAwal=2024&tahunAkhir=2026` | 200 | `{"nama_provinsi":"Aceh","data_luas":[{"tahun":"2024","luas":"7.257,35"},…]}`. Hectares, in Indonesian number format (`.` = thousands separator, `,` = decimal). |
| `/api/list/luas-kebakaran/kabupaten` | `provinsi=…&tahunAwal&tahunAkhir` | 200 | Per kabupaten. The `provinsi` filter seemed to be ignored (we got every kabupaten back). |
| `/api/list/emisi-co2` | — | 200 | CO₂e emissions (t) per province per year, 2021–2026 |
| `/api/getSummaryKebakaran` | — | 200 | `{"kejadian_kebakaran":3212,"luas_kebakaran":"202K+","total_provinsi":36,"total_kabupaten":340}` |
| `/api/daops/pemadaman` | — | 200, 75 features (25 Aug – 16 Oct 2026) | GeoJSON: `nama_daops` (DAOPS PASER, PONTIANAK, KETAPANG, SINTANG…), `tanggal`, `lokasi`, `luas_bakar`, `luas_padam` (ha), `catatan` |
| `/api/data/laporan-harian` | paginated | 200 | Links to monthly/daily reports. The newest are from 2021, so this is stale. |
| `/api/sebaran` | `startdate, enddate, satelit, confidence, provinsi` | 500 with the parameters we guessed | The table view. Use `indoHotspot` instead. |
| `/api/{…}/download` | `late/startdate/enddate, provinsi, confidence, satelit, tipe` | not tried | Excel/CSV export from the site |

Confidence mapping seen in the BRIN-sourced (LPN-*) points: `low` = 29, `medium` = 79, `high` = 100
(from BRIN's 7/8/9 classes). NASA points pass FIRMS confidence through (VIIRS 25/70/90, MODIS 0–100).

**Licence.** Not stated. It is official government information (UU KIP, public information), so
credit "SiPongi+ Kementerian Kehutanan". Being on a non-government domain is a stability risk.

**Value.**
- *Official numbers:* show "SiPongi: N titik panas (24 jam)" beside our FIRMS count. Reporters
  and officials quote this number, and ours will differ because of the static mask and clustering.
- *Burned area:* official luas karhutla per province and per kabupaten per year, beside our
  event-area sum. Good for the dashboard "season comparison".
- *Operations:* Daops points let us mark an event as "dalam penanganan Manggala Agni". This is
  the only machine-readable ground-response feed we found.

### 3.3 BRIN hotspot — `hotspot.brin.go.id`

AngularJS app (`services/layerService.js`). Same-origin endpoints, no auth, behind Cloudflare.
`robots.txt` returns 404.

| Endpoint | Params (from the app) | Result |
| --- | --- | --- |
| `/getHS` | `class=hotspot&name=Hotspot&time=last24h&conf_lvl=low&mode=cluster&loc={"stt":"Indonesia","disp":"Indonesia"}`; plus `startdate/enddate` for a custom range | 200 (served as `text/html`, but the body is GeoJSON). Properties are only `c` (confidence 7/8/9), `r` (radius m), `s` (satellite). |
| `/getCSV` | same | 200 `text/csv`: `id,tanggal (WIB),waktu (WIB),lintang,bujur,tingkat kepercayaan,satelit,radius kemungkinan,kecamatan,kabupaten,provinsi,tipe` |
| `/getHSdetail?hsid=` | — | 200, empty body |
| `/getTSRaster`, `/getTSVector`, `/getLogin` | — | Raster layers need a login |

Sample: `4828393,2026-10-17,12:15:11,-8.11010361,117.92880249,8,noaa20,1125,Tambora,Bima,"Nusa Tenggara Barat",Cluster`

Last 24 h: 4 015 rows (conf ≥ low), 3 885 (≥ medium), 47 (high). Satellites: snpp and noaa20
(no MODIS in that window). **Confidence levels:** 7 = rendah (low), 8 = sedang (medium),
9 = tinggi (high). This is the scale used in Indonesian law enforcement; KLHK guidance acts on
"sedang" and above. `radius kemungkinan` (1125–1588 m) is the location uncertainty.

**Value.** Low cost (CSV, about 90 KB per day). Lets us show the official BRIN confidence class
on each detection, and cross-check FIRMS (BRIN processes the direct-broadcast data from its own
ground stations, so detections can arrive sooner). Licence is not stated; credit "BRIN".

### 3.4 BNPB — geoportal, InaRISK, DIBI

ArcGIS Enterprise 11.4 at `https://gis.bnpb.go.id/server/rest/services` (the old
`/arcgis/rest` path returns 500). 44 folders, no auth for most of them. `Bencana_Harian` asks for
a token (499).

| Service | Result | Content |
| --- | --- | --- |
| `2026_karhutla/mv_prov_karhutla_2026/FeatureServer/3` | ✅ 200, 6 polygons: Kalbar, Kalteng, Kalsel, Sumsel, Jambi, Riau | 58 fields per province: `tgl_update`, `total_hotspot`, `hotspot_rendah/sedang/tinggi`, `fire_spot`, `luas_lahan_terbakar_sipongi_2026`, `today_luas_terbakar`, `luas_ditangani_ops_darat/udara`, `sortie_water_bombing`, `volume_wb_harian` (L), `sortie_omc`, `total_bahan_semai` (kg NaCl), `manggala_agni`, `tni`, `polri`, `relawan`, `total_personil_gabungan`, `meninggal`, `jarak_pandang_km`, `kualitas_udara_pm25` (text), `rekomendasi`, `kesimpulan` (free-text situation report) |
| `2026_karhutla/mv_tabeldata_karhutla_prov_2026_v2` | ⛔ query returns 400 | Same schema, broken |
| `inarisk/layer_bahaya_kebakaran_hutan_dan_lahan/ImageServer` | ✅ `exportImage` 200 PNG | Fire hazard index, F32 0.01–1.0, 100 m, EPSG:3395. Also `layer_kerentanan_…`, `layer_risiko_…`, `layer_bahaya_…_30`. |
| `Hosted/Data_Bencana_Dashboard`, `Bencana_2019_2023`, `Karhutla_2022` | ⛔ query returns 500 | The DIBI schema (meninggal, mengungsi, menderita, hutan, lahan, lat/lon…), but the data store is down |
| `dibi.bnpb.go.id` | ⛔ curl and WebFetch time out after 45–60 s (Cloudflare answers, the origin never does). Possibly geo-restricted or overloaded. | — |
| `bnpb.go.id`, `data.bnpb.go.id` | ⛔ 403 Cloudflare challenge | — |
| `inarisk.bnpb.go.id` (v4, Svelte) | ✅ 200 | Front end only. Backend `/apiv4`; layers come from the gis.bnpb ImageServers above. |

BNPB sample (Kalteng, `tgl_update` 2026-09-26): `total_hotspot 3608, fire_spot 99, today_luas_terbakar 335.1 ha, sortie_omc 4, total_personil_gabungan 4686, kualitas_udara_pm25 "Baik-Berbahaya"`.
All six rows were last updated on 26 Sep. That is three weeks old during an active season, so
this feed is published sporadically.

**Value.** Per-province "response" panel (personnel, aircraft, cloud seeding, deaths) with
BNPB's situation text. Fetch it, but show its age clearly. The InaRISK hazard raster could add a
"kawasan rawan karhutla" layer. Licence is not stated; credit "BNPB".

### 3.5 BMKG

`data.bmkg.go.id` terms (page `tentang`): free open data. **Users must credit BMKG as the source
and show it in the app.** Forecast API limit: 60 requests per minute per IP.
`www.bmkg.go.id/robots.txt`: `Disallow: /api` and `Disallow: /alerts`.

| Product | URL | Result | Notes |
| --- | --- | --- | --- |
| Weather forecast (desa level) | `https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={kode Kemendagri}` | ✅ 200 JSON, CORS `*`, `max-age=3600` | 3-hourly for 3 days: `t, hu, tcc, tp, ws, wd, vs, weather, weather_desc`. Palangka Raya 18 Oct 00:00 WITA: `weather 45 "Kabut/Asap"`, ws 5.4, hu 72. One adm4 code per call, so use town-centre codes for about 30 haze cities. |
| Earthquakes | `data.bmkg.go.id/DataMKG/TEWS/autogempa.json`, `gempaterkini.json` | ✅ 200 | Not relevant for haze |
| Nowcast warnings (CAP) | `www.bmkg.go.id/alerts/nowcast/id/rss.xml`, `…/{code}_alert.xml` | 200 (HEAD only) 🤖 | Documented as open data on data.bmkg.go.id, but robots.txt disallows `/alerts`. Ask BMKG before using it. |
| PM2.5 (BAM monitors) | Page `www.bmkg.go.id/kualitas-udara/pm25` loads `/api/kualitas-udara/pm25` (fields include `LAT`, `LON`) | 🤖 not fetched | Hourly PM2.5 from BMKG monitors (Palangka Raya, Pekanbaru…). Categories: 0–15.5 Baik, 15.6–55.4 Sedang, 55.5–150.4 Tidak Sehat, 150.5–250.4 Sangat Tidak Sehat, > 250.5 Berbahaya. **Request access** (PTSP BMKG / `dataonline.bmkg.go.id`). |
| SPARTAN FDRS static maps | `https://dataweb.bmkg.go.id/cuaca/spartan/{region}_{index}_{step}.png`; region `01_aceh … 36_indonesia`, `35_asean`; index `ffmc, dmc, dc, isi, bui, fwi`; step `obs, 00…07` (H+0…H+7) | ✅ 200 PNG (~215 KB), `last-modified` 16–17 Oct, `max-age=3600` | 🖼 Rendered maps with legend. No numeric grid is exposed. |
| SPARTAN tiles | `spartan.bmkg.go.id/map/rgb_req/spartan/{index}/0/{run}/{valid}/{z}/{x}/{y}.png`, `…/HTH/hth/…`, `…/spartanobs/…`; run list at `/map/modelrun` | ⛔ `/map/modelrun` returns a 403 Cloudflare challenge | Can't get the run timestamps without a browser. Not usable from the pipeline. |
| Himawari / GK2A / GSMaP | `inderaja.bmkg.go.id/IMAGE/GEOHOTSPOT/H08_GH_Asean.png`, `IMAGE/HOTSPOT/Hotspot_Indonesia.png`, `IMAGE/GSMAP/GSMaP_HTH.png`, `IMAGE/HIMA/H08_*_Indonesia.png` | ✅ 200 PNG, updated within the hour | 🖼 The geo-hotspot (Himawari) and the "Sebaran Asap" RGB are the haze-relevant ones |
| Smoke trajectory | `inderaja.bmkg.go.id/Trajektori/Asap.png` | ✅ 200, updated daily (10:43 UTC) | 🖼 BMKG HYSPLIT smoke trajectories. A useful "official" check against our plume model. |
| Satellite tile API | `satellite.bmkg.go.id/api22/tile/{z}/{x}/{y}.png?tiletype=himawari9…` | ⛔ 403 Cloudflare challenge | — |
| Hari Tanpa Hujan | `dataweb.bmkg.go.id/iklim/hari-tanpa-hujan.png` | ✅ 200, updated 12 Oct (dasarian) | 🖼 Consecutive dry days map. No numeric data found. |
| ENSO / IOD | `dataweb.bmkg.go.id/iklim/el-nino-la-nina/Indo_SSTA_latest.gif`, `Global_SSTA_latest.gif` | ✅ 200, weekly | 🖼 For numbers, use NOAA CPC ONI / BoM IOD instead, and keep BMKG's text outlook as a link. |
| `dataonline.bmkg.go.id` | — | needs login | Station climate data (daily rain, so a true HTH per station). Registration required. |
| `signature.bmkg.go.id`, `inasiam.bmkg.go.id`, `dataweb.bmkg.go.id/` (root) | ⛔ 403 Cloudflare | — |

BMKG's hotspot layer on SPARTAN says "hotspot data source is FIRMS-NASA", so it adds nothing over
our current input.

**Value.** Forecast "Kabut/Asap" flags plus visibility for each haze city, as independent
confirmation of our smoke arrival times (BMKG credit required). SPARTAN FWI and the smoke
trajectory PNGs as an "Official BMKG products" panel with deep links. These are cheap to add
because we only show them, not process them.

### 3.6 Provincial portals

| Province | Portal | Here? | Fire-related content | Verdict |
| --- | --- | --- | --- | --- |
| Kalbar | `data.kalbarprov.go.id` (CKAN, `/api/3/action/package_search`) | ✅ 200 | 75 karhutla datasets: daily Satgas reports (PDF, 2022–23), yearly hotspot XLSX 2015–2021, LAPAN hotspot CSV/JSON (2021–22), burned area 2024 (XLSX, BPBD and DLHK), desa rawan karhutla 2025 | Back-fill and context only. Mixed licences (`cc-by` or `notspecified`). |
| Kalteng | `satudata.kalteng.go.id` → API `api.satudata.kalteng.go.id/dataset/public?page=` | ✅ 200 (`/dataset` needs a token; `/dataset/public` is open, 1 367 datasets, 10 per page, slow: 6 of 137 pages timed out after 30 s) | Of the 1 207 datasets crawled, only 2 match: "Data Karhutla/Hotspot, 2023-2024" (Dinas Kehutanan, yearly) and "Data Indeks Kualitas Udara, 2023-2024" (DLH, yearly) | Little live value |
| Sumsel | `satudata.sumselprov.go.id` (portal of portals), CKAN at `opendata.sumselprov.go.id` | ✅ 200 | 1 "karhutla" hit and 5 "kebakaran" hits (peat cover index IKL, Redkar volunteers). No hotspot data. `geoportal.sumselprov.go.id` (Palapa) not explored. | Low |
| Riau | `data.riau.go.id`, `satudata.riau.go.id` | ⛔ NXDOMAIN; `riau.go.id` has a broken TLS chain | Polda Riau "Dashboard Lancang Kuning" (`app.lancangkuning.net`) needs a login | None usable |
| Jambi | `data.jambiprov.go.id`, `satudata.jambiprov.go.id` | ⛔ connection reset / timeout (DNS resolves, so probably a foreign-IP firewall) | — | Probably geo-blocked; retry from an Indonesian IP |
| National | `data.go.id` (Next.js, no CKAN API at `/api/3`) | ✅ 200 (HTML) | — | Not explored further |

## 4. Blocked or unusable from a foreign IP (summary)

| Host | Symptom | Likely cause |
| --- | --- | --- |
| `sipongi.menlhk.go.id`, `ispu.menlhk.go.id`, `modis-catalog.lapan.go.id`, `rami.bmkg.go.id`, `geoportal.bnpb.go.id`, `satudata.bnpb.go.id`, `katalog.data.go.id`, `data.kalteng.go.id`, `bpbd.kalteng.go.id`, `data.riau.go.id`, `satudata.riau.go.id`, `satudata.kalbarprov.go.id` | proxy 502 / NXDOMAIN | The host no longer exists (ministry restructuring or renames) |
| `dibi.bnpb.go.id` | Cloudflare connects, then 45–60 s with no bytes | Origin is slow or filtering. Possibly geo. |
| `data.jambiprov.go.id`, `satudata.jambiprov.go.id`, `opendata.palangkaraya.go.id` | TCP reset / timeout | Probably a foreign-IP firewall |
| `spartan.bmkg.go.id/map/*`, `satellite.bmkg.go.id`, `signature.bmkg.go.id`, `inasiam.bmkg.go.id`, `bnpb.go.id`, `data.bnpb.go.id` | 403 "Just a moment…" | Cloudflare bot challenge. **We did not try to get around it.** |
| `www.bmkg.go.id/api/*`, `/alerts/*` | not fetched | robots.txt Disallow |
| `gis.bnpb.go.id …/Hosted/*` (DIBI tables) | ArcGIS 500 | Data store is down |

## 5. Integration notes

- **Pipeline cadence fits.** Every usable feed updates hourly or less often, so the 2-hour cron can
  pick it up. Send a `User-Agent` that names the project and a contact, and add jittered retries:
  these hosts are slow (Kalteng took up to 30 s per page) and drop connections.
- **Names.** SiPongi and BNPB key provinces by `id_mendagri` (BPS/Kemendagri 2-digit codes),
  which match geoBoundaries ADM1 through our `static/` provinsi table. BRIN gives names only.
- **Number format.** Parse SiPongi's `luas` strings as id-ID (`"38.310,89"` → 38310.89).
- **Time zones.** ISPU `waktu` is local (`time_z` WIB/WITA/WIT). BRIN CSV is WIB. SiPongi
  `date_hotspot_ori` is UTC. BMKG forecast gives both `utc_datetime` and `local_datetime`.
- **Credits (UI footer).** "BMKG" (required by its terms), "KLH/BPLH – ISPU", "SiPongi+
  Kementerian Kehutanan", "BRIN", "BNPB".
- **Ask for access (emails worth sending):** KLH for an ISPU API key; BMKG (PTSP) for PM2.5 JSON
  and permission for CAP; BNPB Pusdatin for DIBI/karhutla feature-service stability.
