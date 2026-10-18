# Air-quality data for Kalimantan and Sumatra: observed and near-real-time PM2.5

Research note, 17 Oct 2026. Every endpoint below was probed from the build container (behind
an HTTPS proxy) on this date. "Verified" means we got a real response with data. Where a
claim comes only from documentation or the literature, it is marked *(doc)* or *(unverified)*.

Today the pipeline uses CAMS global PM2.5 from Open-Meteo, plus the puff model in
[../models.md](../models.md). The Open-Meteo docs list CAMS global at 0.4° (~45 km) with
12-hourly updates. `models.md` says 0.75°, so check what grid `smoke.py` actually samples.

## 1. Headline finding: CAMS badly under-reads tonight's haze

The KLH ISPU feed (see 2.1) gives about 50 live stations across Kalimantan, Riau, Jambi and
South Sumatra. We compared it with CAMS (Open-Meteo, mean of 15 and 16 UTC) and with GEOS-CF
v2 (`pm25_rh35`, 15:30 UTC) for the hour ending 23:00 WIB on 17 Oct 2026 (n = 48 stations,
PM2.5 > 1 µg/m³, not flagged for maintenance). Script:
`scratch/scripts/cmp.py`.

| Model | Median model/obs | r (log space) |
| --- | --- | --- |
| CAMS global (Open-Meteo) | **0.39** | 0.69 |
| GEOS-CF v2 forecast | 0.23 | 0.43 |

| Station | Obs ISPU (µg/m³) | CAMS | GEOS-CF |
| --- | --- | --- | --- |
| Palangkaraya (Jekan Raya) | 1470 | 405 | 59 |
| Kab. Katingan | 1184 | 260 | 76 |
| Kab. Kampar (Riau) | 441 | 80 | 61 |
| Jambi | 230 | 151 | 31 |
| Pontianak | 211 | 37 | 37 |
| Palembang | 206 | 56 | 52 |
| Banjarmasin | 132 | 14 | 14 |
| Balikpapan | 31 | 17 | 13 |

Caveats:
- This is a single night-time hour. Night-time boundary-layer collapse is exactly where
  global models fail.
- The ISPU monitors are unvalidated (`auto_validation=1`), and a beta-attenuation monitor at
  99% RH can read high.
- Grosvenor et al. (2024) found the Palangka Raya fixed station read consistently higher than
  co-located PurpleAir sensors.

Even so, this matches the literature (section 4). CAMS NRT under-reads peat haze by a factor
of about 2 to 3, and spatial correlation is only moderate. Station-based bias correction is
the highest-value addition.

## 2. Ground networks

### 2.1 Summary table

| Source | Endpoint | Probe result | Auth | Licence / terms | Latency, resolution | Kalimantan coverage | Effort |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **KLH ISPU** (Ministry of Environment, formerly KLHK/MenLHK) | `https://ispu.kemenlh.go.id/apimobile/v1/getStations` | **200**, 141 kB JSON, 119 stations, CORS `*`. The old host `ispu.menlhk.go.id` fails (proxy 502). | None | No licence stated. Public government portal. Attribute "KLH/BPLH" and ask for permission before redistributing raw data. | Hourly, about 1 h behind. Point stations. | **~29 stations**: Kalteng 8, Kaltim 10, Kalbar 5, Kalsel 4, Kaltara 1. Sumatra: Riau 7, Jambi 4, Sumsel 9, plus others. | Low. One GET returns the latest hour only. `getDetail/<id>` exists but returned 400 for every parameter form we tried, so no history API was found. We must poll and store it ourselves. |
| **Malaysia DOE APIMS** (Sarawak, Sabah: northern Borneo) | `https://eqms.doe.gov.my/api3/publicmapproxy/PUBLIC_DISPLAY/CAQM_MCAQM_Current_Reading/MapServer/0/query?where=1%3D1&outFields=*&f=json` | **200**, 68 stations: 12 in Sarawak, 6 in Sabah | None | No licence stated. Government data. | Hourly. Reports the **API index**, not µg/m³: invert the Malaysian PM2.5 breakpoints. | 0 in Indonesian Kalimantan, but 18 on Borneo downwind of Kalbar. Serian and Sri Aman read 91 to 106 tonight. | Low |
| **Singapore NEA** | `https://api-open.data.gov.sg/v2/real-time/api/pm25` | **200**, 5 regions; 83 to 199 µg/m³ tonight | None (higher rate limits with a key) | Singapore Open Data Licence | Hourly | Sumatra and Riau transboundary receptor only | Very low |
| **AirGradient public API** (carries **Nafas** sensors) | `https://api.airgradient.com/public/api/v1/world/locations/measures/current` | **200**, 1.5 MB, 2,913 locations | None | AirGradient open-data terms *(unverified)*. Attribute Nafas or AirGradient. | 1 to 5 min; low-cost Plantower. Raw `pm02`; `pm02_corrected` was null. | **2**, both in Balikpapan: Karang Joang (77242), Gunung Sari Ilir (77270). **0 in Sumatra.** Most Nafas sensors are in Jabodetabek and Malang. | Low. Needs a humidity correction. |
| **Nafas Indonesia** (own API) | `api.nafas.co.id` | DNS failed. The site 301-redirects to `nafas.co.id`. | Partnership only | Commercial | n/a | Pontianak was listed as a planned DBS-funded city in 2024 *(doc)*. It is not in the AirGradient feed. | Use the AirGradient feed instead. |
| **Sensor.Community** | `https://data.sensor.community/airrohr/v1/filter/country=ID` (5-min) and `static/v2/data.24h.json` | **200** | None | ODbL | 5 min | **0 in Kalimantan.** 1 in Sumatra: SDS011 #31476 in Palembang (-2.957, 104.708), reading PM2.5 511 at RH 99.9%, which is fog or humidity inflation. 2 in Banyuwangi. | Low, but almost no value |
| **OpenAQ v3** | `https://api.openaq.org/v3/locations?bbox=…` | **401** without a key | Free key in the `X-API-Key` header. About 60 requests/min and 2,000/h *(unverified)*. | Platform CC BY 4.0; each provider's licence also applies | Mirrors upstream sources | Indonesian coverage not verifiable without a key. It mostly re-hosts AirNow (stopped), AirGradient and Clarity, so it is probably a subset of the above. Keyless archive: `s3://openaq-data-archive/records/csv.gz/` (verified listable). | Medium. Useful for history and backfill, not for unique sensors. |
| **WAQI / aqicn** | `https://api.waqi.info/feed/@8342/?token=…` | **200**, but the `demo` token always returns Shanghai. `map/bounds` with `demo` returns "Invalid key". The unofficial `api/feed/@8342/obs.en.json` works (Palangka Raya PM2.5 AQI 650). | Free token | Attribution to WAQI and the originating EPA is required. Non-profits must notify WAQI by email; for-profit use needs an agreement. | Hourly | Indonesian stations re-broadcast ISPU | Skip. ISPU directly is the same data with fewer terms. |
| **IQAir / AirVisual** | `api.airvisual.com/v2/…` | **403** with a dummy key. Website returned 429 (Vercel bot checkpoint). | Key (free Community tier) | Community tier is non-commercial, attribution required, no bulk redistribution *(doc, unverified)* | Hourly | Mostly ISPU plus a few IQAir sensors | Skip |
| **PurpleAir** | `https://api.purpleair.com/v1/sensors?nwlat=…` | **403** `ApiKeyMissingError` | API key plus prepaid "points": about 1M free at signup, roughly $1 per 100k after *(doc)* | PurpleAir data licence (attribution) | 2 to 10 min | Leeds / Universitas Palangka Raya network in Central Kalimantan: 4 outdoor sensors in 2023, 42 in 2024, 6 in 2025 (Graham et al. 2026). Grosvenor et al. ran 10 sensors in Palangka Raya in 2019. Current public count needs a key. | Medium. A bbox query for Borneo and Sumatra is about 4 to 10 points per call. Apply the US-EPA or Grosvenor high-concentration correction. |
| **US Embassy Jakarta / Surabaya (AirNow DOS)** | `dosairnowdata.org` | DNS fails (proxy 502). AirNow embassy page is 404. | n/a | n/a | n/a | Never in Kalimantan. Feed has been halted since 5 Mar 2025 ("budget constraints"), with no sign of a restart. | Drop |
| **University / NGO networks** | none public in real time | n/a | n/a | n/a | n/a | Leeds / UPR PurpleAir network (Palangka Raya, Kereng) is visible only through PurpleAir. No public feeds found for Pekanbaru, Pontianak, Jambi or Palembang beyond ISPU. | Ask Leeds (A. Graham, D. Spracklen) for data access |

### 2.2 KLH ISPU stations in Kalimantan (live 17 Oct 2026, PM2.5 µg/m³)

| id_stasiun | Province | lat | lon | PM2.5 |
| --- | --- | --- | --- | --- |
| PALANGKARAYA | Kalteng | -2.222 | 113.860 | 1469.7 |
| KABUPATEN_KATINGAN | Kalteng | -1.890 | 113.415 | 1184.3 |
| KABUPATEN_BARITOSELATAN | Kalteng | -1.679 | 114.908 | 497.1 |
| KABUPATEN_GUNUNG_MAS | Kalteng | -1.131 | 113.857 | 495.1 |
| KABUPATEN_MURUNG_RAYA | Kalteng | -0.639 | 114.537 | 382.5 |
| KABUPATEN_KOTAWARINGIN(TIMUR) | Kalteng | -2.536 | 112.878 | 223.7 |
| KABUPATEN_KAPUAS | Kalteng | -2.966 | 114.415 | 184.8 |
| KABUPATEN_KOBAR | Kalteng | -2.706 | 111.614 | 39.3 |
| PONTIANAK | Kalbar | -0.031 | 109.322 | 211.0 |
| KABUPATEN_KUBU_RAYA | Kalbar | -0.127 | 109.404 | 84.8 |
| KABUPATEN_SEKADAU | Kalbar | 0.005 | 110.891 | 67.5 |
| KABUPATEN_BENGKAYANG | Kalbar | 0.864 | 109.499 | 47.5 |
| KABUPATEN_SAMBAS | Kalbar | 1.361 | 109.329 | 16.7 |
| KABUPATEN_TABALONG | Kalsel | -2.176 | 115.416 | 245.6 |
| KABUPATEN_BARITO_KUALA | Kalsel | -2.984 | 114.733 | 202.5 |
| BANJARMASIN | Kalsel | -3.296 | 114.589 | 131.8 |
| KABUPATEN_HSS | Kalsel | -2.784 | 115.263 | 60.7 |
| KABUPATEN_KUTAIBARAT | Kaltim | -0.234 | 115.693 | 167.4 |
| WT_KPIKN_IKN, SNP_KPIKN_IKN, MJT_KPIKN_IKN, PB_KIPP_IKN, PS_KIPP_IKN | Kaltim (IKN) | ≈ -1.0 | ≈ 116.7 to 117.2 | 26 to 71 |
| KABUPATEN_PENAJAM_PASER_UTARA | Kaltim | -1.311 | 116.725 | 43.1 |
| BALIKPAPAN, BALIKPAPAN_BB | Kaltim | -1.243 | 116.86 to 116.89 | 31 to 32 |
| KOTA_BONTANG | Kaltim | 0.122 | 117.486 | 37.6 |
| KOTA_TARAKAN | Kaltara | 3.311 | 117.601 | 54.2 |

Field notes:
- `a_*` is the concentration in µg/m³; CO is also µg/m³. `t_*` is the ISPU sub-index (it
  extrapolates above 500), `c_*` is the category, and `val` with `cat` gives the overall
  index and category.
- `waktu` is local time. `time_z` (WIB or WITA) is not always consistent for Kaltim stations.
  Convert to UTC using the province's time zone.
- QC rules to apply:
  - drop rows with `is_maintenance=1`, and treat `a_pm25` of 0 or ≤ 1 as missing (DLH_MEDAN_02 reads 0, DLH_MEDAN_01 reads 0.25);
  - flag PM2.5 well above PM10 (Tanjung Jabung Timur: PM2.5 209 against PM10 21) and
    flat-lined values;
  - cap values at about 2,000.

## 3. Satellite and model products

| Product | Endpoint (verified) | Probe result | Auth | Licence | Latency | Resolution | Kalimantan notes | Effort |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Himawari-9 AHI ARP AOT** (JAXA P-Tree) | `ftp.ptree.jaxa.jp/pub/himawari/L2/ARP/…`, `…/L3/ARP/…` (FTP, FTPS port 990, SFTP port 2051) | Web portal 200. FTP not reachable through the HTTPS-only proxy (timeout or reset). | Free registration | JAXA terms: attribution required. Commercial use is allowed for geophysical parameters from 1 Feb 2026 but not for the aerosol *model* product. | L2 2 to 5 h, L3 2.5 to 6 h *(FAQ)* | L2 10-min, L3 hourly, 5 km, AOT at 500 nm | Geostationary, so several daytime looks a day between clouds. Best temporal coverage. | Medium-high: FTP credentials as a secret, then NetCDF. Should work from GitHub Actions; we could not test it here. |
| Himawari on AWS (NOAA open data) | `s3://noaa-himawari9/` | 200 | None | Open | ~10 min | L1b only | Prefixes: `AHI-L1b-FLDK`, `-Japan`, `-Target`, `AHI-L2-FLDK-Clouds`, `-ISatSS`, `-Winds`. **No aerosol product.** | High (we would have to retrieve AOD ourselves). Use only for true-colour smoke imagery. |
| NASA AHI Dark Target (`XAERDT_L2_AHI_H09`) | LAADS / Earthdata cloud | CMR 200 | Earthdata | NASA open | **Research archive only**: latest granule 2022-12-31 | 10 km, 10 min | Not NRT | n/a |
| **VIIRS Deep Blue NRT** (`AERDB_L2_VIIRS_NOAA20_NRT`, also SNPP and NOAA-21) | Discovery via CMR `granules.json` (200); files on `sips-data.ssec.wisc.edu/nrt/…` | Latest Borneo granule 07:00Z, published 08:19Z | Download needs an **Earthdata Login** bearer token (302 to URS) | NASA open, no restrictions | **~1.3 h** | 6 km L2, about 3 overpasses a day | Retrieves AOD over dark land and bright surfaces; more robust than Dark Target in smoke | Medium: CMR search, then netCDF4 with `EARTHDATA_TOKEN` |
| **MODIS MAIAC NRT** (`MCD19A2N`) | CMR (200); `nrt3.modaps.eosdis.nasa.gov/api/v2/content/archives/allData/61/MCD19A2N/…` | Borneo tile for 16 Oct published 17 Oct 08:11Z | Earthdata token (303 to licence page) | NASA open | ~1 day | **1 km**, daily, sinusoidal tiles h28 to 30 / v08 to 09 | Highest resolution. Terra and Aqua are drifting and near end of life, so do not build on them for long. | Medium (HDF4 tiles) |
| **NASA GIBS WMTS / WMS** | `https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?…&LAYERS=VIIRS_NOAA20_AOD_Deep_Blue_Land_Ocean&TIME=2026-10-15` | **200**, PNG, keyless | None | NASA open | Same day | 2 km tiles (colour-mapped) | Layers: `VIIRS_{SNPP,NOAA20,NOAA21}_AOD_Deep_Blue_Land_Ocean` (to 2026-10-17), `…_Dark_Target_Land_Ocean`, `MODIS_Combined_MAIAC_L2G_AerosolOpticalDepth` (to 2026-10-16), `OMPS_NOAA21_NadirMapper_AerosolIndex_380`, `AIRS_L2_Carbon_Monoxide_500hPa…` | **Very low**: drop it straight into MapLibre as a raster layer. Not quantitative. |
| **Sentinel-5P TROPOMI** AER_AI and CO (NRTI) | Catalogue: `https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$filter=contains(Name,'L2__AER_AI')…` (200); download `zipper.dataspace…/$value` (401 without a token) | Latest AER_AI and CO granules sensed 15:28Z, published 16:02Z | Free CDSE account with OAuth token, or GEE (`COPERNICUS/S5P/NRTI/L3_AER_AI`, `…/L3_CO`) | Copernicus free and open | ~3 h | 5.5 × 3.5 km (CO 5.5 × 7) | Absorbing aerosol index detects smoke above cloud. CO is a good fire tracer and is not affected by the AOD cloud mask. One overpass at 13:30 LT. | Medium |
| **GEOS-CF v2 forecast** (NASA GMAO) | `https://opendap.nccs.nasa.gov/dods/gmao/geos-cf/v2/fcst/aqc_tavg_1hr_glo_L1440x721_slv.latest` | **200**. Point time series in ~11 s with `.ascii?pm25_rh35[t][0][i][j]`. The v1 path `…/fcast/aqc_tavg_1hr_g1440x721_v1` gives proxy 502 at the dataset level. | None | NASA open | Daily 12Z run, 5 days, hourly | 0.25° | Under-reads more than CAMS tonight (×0.23). Uses QFED emissions, so it is a different fire inventory from CAMS/GFAS: useful as a second opinion and spread estimate. | Low (xarray or pydap, subset a bbox) |
| GEOS-FP aerosol | `…/dods/GEOS-5/fp/0.25_deg/fcast/tavg3_2d_aer_Nx` | 200 (listing) | None | NASA open | 4 runs a day | 0.25°/0.3125°, 3-hourly | PM2.5 must be built from species (DUSMASS25, OCSMASS, BCSMASS, SO4SMASS, SSSMASS25) | Medium. GEOS-CF is simpler. |
| Satellite-derived surface PM2.5 (WashU ACAG V6.GL, van Donkelaar) | WashU site / Zenodo | not probed | None | CC BY | **Months to a year** | 0.01°, monthly | Climatology and validation only, not NRT | n/a for live maps |

## 4. Literature on haze PM2.5 over Indonesia

| Paper | What it found | Relevance |
| --- | --- | --- |
| Grosvenor et al. 2024, *Commun. Earth Environ.* 5:649, doi:10.1038/s43247-024-01813-w | 10 PurpleAir PA-II sensors in Palangka Raya, Aug to Oct 2019. 3-h means above 700 µg/m³ city-wide; season mean 137. **CAMS NRT r² 0.70, but 66% low on days above 100 µg/m³.** CAMS EAC4 reanalysis r² 0.80, 35% high. The Jekan Raya AQMS (our ISPU `PALANGKARAYA`) read higher than the sensors. | Direct evidence for multiplicative bias-correction of CAMS NRT in Kalimantan. Also warns about uncertainty in station calibration. |
| Graham et al. 2026, EGUsphere preprint, doi:10.5194/egusphere-2026-2746 | Dense PurpleAir network in Central Kalimantan peatland, 2023 to 2025. WHO 24-h exceedance on 99% of days in the 2023 El Niño, 41% in 2024. | Confirms a sensor network exists; ask the authors for data. |
| Shi et al. 2019, *ACP* 19:259 | During the 2015 haze, MODIS Dark Target masked thick smoke (AOD > 3) as cloud or inland water and used a too-absorbing aerosol model. It missed 0.22 of the regional mean AOD and up to 3.0 per 0.5° box. | Satellite AOD is biased **low or missing exactly in the worst plumes**. Prefer Deep Blue or MAIAC, and never treat missing AOD as clean air. |
| Hutauruk et al. 2022, *Adv. Meteorol.* doi:10.1155/2022/7544310 | Evaluated MODIS Deep Blue C6.1 over Indonesia against AERONET. AOD of 3 to 4 at Jambi, Pontianak and Palangka Raya in Sep to Oct 2015. | Deep Blue is usable over Indonesia. |
| Kiely et al. 2019, *ACP* 19:11105 | WRF-Chem constrained by PM measurements: 2015 Sumatra and Borneo fire PM2.5 emissions were 7.33 Tg, 3.5× FINN and 1.8× GFED4s. | Global models with standard inventories under-predict peat haze. This matches our ×0.39. |
| Field et al. 2016, *PNAS* doi:10.1073/pnas.1524888113 | Haze (MODIS AOD and OMI AI) responds nonlinearly to El Niño drought. | Context for seasonal bias that changes with drought. |
| Wooster et al. 2018, *ACP* | Peat PM2.5 emission factors (already used in `smoke.py`) | n/a |

Methods literature for blending sparse stations with model fields: model-output plus
residual-kriging fusion (e.g. CMAQ + AOD + monitors with spatiotemporal kriging, *Remote
Sensing* 2017, CV R² 0.72); random-forest bias correction of CAMS PM2.5 forecasts (*Remote
Sensing* 2020); and geographically weighted regression of AOD-derived PM2.5 residuals (van
Donkelaar et al., ACAG). The recurring lessons:
1. Do the correction in **log space**, because the bias is multiplicative.
2. Let the correction **decay to the model** far from stations, with a length scale of about
   100 to 200 km for haze.
3. Use AOD as a **spatial shape covariate**, not as an absolute PM2.5 source, because the
   AOD-to-surface ratio is highly variable and the smoke is low and humid.

## 5. Recommended plan (top 3 additions)

### 1. Ingest ground stations hourly (KLH ISPU, Malaysia DOE, Singapore NEA, AirGradient)

Size: S, about 1 day of work.

- Add a new `haze/stations.py` with four keyless GETs and the QC rules in 2.2 (Malaysia API
  index converted back to µg/m³).
- Append to a DuckDB table `obs_pm25(station_id, source, lat, lon, time_utc, pm25, pm10, qc)`.
- ISPU only serves the latest hour, so history only exists if we store it.
- The 2-hourly workflow will miss every other hour. Either add a cheap `*/60` job that runs
  only `haze stations`, which costs about 20 s, or accept the gaps.
- Publish `stations.json` and show the points on the map coloured by PM2.5. This is the
  verification layer the user asked for.
- Log CAMS and puff-index skill against the stations every run: log bias, r, and hit rate for
  > 55 µg/m³.

### 2. Bias-correct CAMS with stations for the PM2.5 map and the city outlook

Size: M, about 2 to 3 days.

At each station:

```
r_s = ln(obs + 1) − ln(CAMS + 1)
```

Use a rolling 24 h median of `r_s` (at least 6 of 24 h present), shrunk toward 0 when few
hours are present.

For the analysis map, interpolate `r_s` to the 0.25° grid. Start with Gaussian-weighted
inverse-distance weighting, L ≈ 150 km, with weights relaxing to 0 beyond about 300 km. Then
upgrade to ordinary kriging of the residual using a variogram fitted per run (pykrige).

```
PM_corr = exp(ln(CAMS + 1) + r̂) − 1
```

Optionally multiply r̂ by the puff smoke-index footprint, so the correction acts where smoke
is.

For the city outlook:
- apply each city's nearest-station or interpolated r̂ to the CAMS forecast, decaying with
  lead time (`r̂ · e^(−t/24h)`);
- show "observed now" next to the forecast;
- verify by lead time against stored station observations.

Add GEOS-CF as a second member later, only if its verified skill earns a place.

### 3. Satellite AOD and CO for the gaps between stations

Size: M.

- **Day 0 (very low effort):** add GIBS keyless layers to the web map:
  - `VIIRS_NOAA20_AOD_Deep_Blue_Land_Ocean` and `VIIRS_NOAA21_AOD_Deep_Blue_Land_Ocean`
  - `MODIS_Combined_MAIAC_L2G_AerosolOpticalDepth`
  - `OMPS_NOAA21_NadirMapper_AerosolIndex_380`
- **Pipeline:**
  - Pull VIIRS Deep Blue NRT L2 through CMR with an `EARTHDATA_TOKEN` secret, about 1.3 h
    latency, and grid it to 0.25°.
  - Use `AOD_sat / AOD_CAMS` as a covariate in the residual regression (regression-kriging),
    capped at ×0.3 to ×5, applied only where VIIRS has a valid retrieval.
  - Never treat a cloud-masked thick-smoke pixel as clean (Shi et al. 2019).
- **Stretch:**
  - Himawari-9 ARP L3 hourly AOT through P-Tree SFTP: free registration, 5 km, hourly, 2.5 to
    6 h latency. It gives diurnal coverage that polar orbiters miss.
  - TROPOMI CO as a cloud-robust smoke tracer.

Not recommended:
- **WAQI and IQAir**: they re-host ISPU and have stricter terms.
- **PurpleAir**: worth a key only if the Leeds sensors in Central Kalimantan are public.
- **OpenAQ**: a free key is useful for history, but adds little live coverage.
- **AirNow DOS**: halted since March 2025.
- **Sensor.Community**: one humid-biased sensor in Palembang.
