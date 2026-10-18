# Smoke and spread models

Both models are built from the literature summarised in
[research/fire-spread-and-smoke.md](research/fire-spread-and-smoke.md). Both are labelled
experimental in the UI.

## Smoke: `haze smoke`

| Part | What it does |
| --- | --- |
| Inputs | CAMS global PM2.5 / AOD forecast on a 0.75° grid. Winds at 925 hPa, 850 hPa and 10 m, plus rain, on a 1.5° grid. All from Open-Meteo, keyless, refreshed every 6 h within the free quota. |
| Sources | Fires active in the last 24 h. Mean FRP = Σ FRP over detections / 6 overpasses. |
| Emissions | PM2.5 kg/h = FRP · 3600 · β · EF / 1000. Peat: β 5.87 kg/MJ (GFAS) and EF 20 g/kg (Wooster 2018). Other fires: savanna values, β 0.78 and EF 4.9. Fires are assumed to keep burning with an e-folding time of 48 h on peat and 18 h elsewhere. |
| Transport | One puff per fire per hour, moved hourly (RK2, bilinear in space, linear in time) on 10 m wind, which beat 925 and 850 hPa against CAMS (below). |
| Dispersion and loss | Gaussian puff width σ = 5 km + 0.7 m/s · t (HYSPLIT-style linear growth). 1 km mixing depth, 5-day lifetime, washout (1 h e-folding) where rain > 1 mm/h. |
| Output | A fire-smoke index (µg/m³-like) on a 0.25° grid every 3 h out to 72 h, plume-tip tracks, and per-city first-arrival times. CAMS gives the absolute PM2.5 for each city (all sources). |
| Running check | Every run logs CSI and log-correlation between the model footprint (index > 15) and CAMS excess PM2.5 (> 25 µg/m³ above the regional median) over Sumatra–Kalimantan. |

Transport-level test against CAMS on 17 Oct 2026 (CSI and log-correlation every 12 h out to 72 h):

| Transport wind | Mean CSI | CSI range | r(log) |
| --- | --- | --- | --- |
| **10 m** | **0.41** | 0.25–0.52 | 0.10–0.51 |
| 50/50 blend of 925 hPa and 10 m | 0.34 | 0.28–0.40 | 0.06–0.26 |
| 925 hPa | 0.30 | 0.21–0.38 | ≈ 0 |
| 850 hPa | 0.26 | 0.18–0.32 | ≈ 0 |

10 m wind is the default. Peat smoke stays in the surface layer (Sofiev 2012), and every level
higher up loses skill against CAMS. This is one day's comparison against another model, not
against stations. `smoke.skill_vs_cams` is logged on every run, so it can be revisited.

**Backtest against observed haze** (`scripts/backtest_smoke_model.py`). The model as
the scheduled job runs it (96 h spin-up, that day's fire sources), issued at 07 WIB on
each of 96 days, 1 Jul - 11 Oct 2026, scored at 13 WIB that day and the next against
MODIS Terra+Aqua AOD from NASA GIBS (thick haze = AOD >= 1, 0.25 deg cells over
Sumatra-Kalimantan, cloud-free cells only):

| ROC AUC for thick-haze cells | 6 h | 30 h |
| --- | --- | --- |
| Model, forecast wind (as live) | **0.864** | **0.870** |
| Model, ERA5 wind | 0.863 | 0.867 |
| Same model, wind off | 0.736 | 0.744 |
| Yesterday's observed AOD | 0.928 | 0.928 |

Transport adds real skill over smoke that stays at the fires, and forecast wind does as
well as reanalysis. Observed haze persists, so yesterday's satellite map beats the model
at "where is it hazy"; the haze map is CAMS (which assimilates satellite AOD), and the
model is for where new smoke goes.

**The smoke path of a fire** (`scripts/backtest_smoke_path.py`): the panel's dashed
line (hourly midpoint trajectory on the 10 m forecast wind, web/src/trajectory.ts) from
the biggest fire clusters of each day (2,038 starts, 1 Jul - 11 Oct 2026, 07 WIB),
against the same path through ERA5. The truth path travelled a median 193 km in 24 h.

| After 24 h | Median error | p75 | Named direction exact | Within one point |
| --- | --- | --- | --- | --- |
| Newest forecast (lead < 24 h) | 33 km | 50 km | 80% | 99% |
| A day older (lead 24-48 h) | 43 km | 63 km | 73% | 97% |
| Wind held as at the start | 121 km | 190 km | 46% | 96% |

The live path uses a forecast at most ~6 h old, between the first two rows. Winds for
both backtests: `scripts/backtest_smoke_winds.py` (Open-Meteo archive and previous-runs
APIs, run on a GitHub runner by the backtest workflow).

**Tuning against observed haze** (`scripts/calibrate_smoke.py`). Same score as above,
with NASA POWER hourly wind (MERRA-2) throughout. Each parameter was moved to half and
double its literature value on 1 Jul - 31 Aug, and the moves that helped were combined;
the combination was scored on 1 Sep - 11 Oct, which the search never saw. Mean AUC over
6 h and 30 h:

| Setting | Fit (Jul-Aug) | Held out (Sep-Oct) |
| --- | --- | --- |
| Literature defaults (live) | 0.936 | **0.811** |
| Peat fires burn 24 h, others 36 h, smoke lasts 240 h, peat emissions halved | 0.939 | 0.810 |
| Puff spread rate (sigma_u) x0.5 | 0.930 | 0.827 |
| Puff spread rate x2 | 0.936 | 0.731 |

The combined tuning did not beat the defaults on the held-out months, so the live model
keeps them. Persistence, lifetime and the peat emission weight move the score by under
0.002 either way: the haze pattern is set by where fires are and where the wind takes
the smoke. Only the spread rate matters, and the two periods disagree on which way, so
it stays at the HYSPLIT-style 0.7 m/s.

**Limits:**

- The index is not calibrated against stations.
- Kiely et al. 2019 suggest inventories like this underestimate peat PM2.5 by about 1.4–3.5×.
- There is no plume rise; Sofiev 2012 says peat smoke mostly stays in the boundary layer.
- The wind grid is coarse (1.5°).

### Spin-up, station correction and cross-border attribution

- **Spin-up.** Puffs are released from 96 h before now, so smoke already in transit is present at the start.
  - Releases from −96 h to −24 h use the rate from 24–48 h ago, and the last 24 h use the current rate.
- **Station correction of CAMS** (`stations.correction_field` / `apply_correction`).
  - **Comparison.** Each station gets a log ratio, observed over CAMS. ISPU `a_pm25` behaves like a trailing 24 h mean (it changes ~1%/h), so ISPU is compared with the trailing 24 h CAMS mean. NEA is compared hourly.
  - **Spatial spread.** Inverse-distance weighting, full within 150 km of a station and none beyond 300 km, clipped to 0.1–10×. CAMS reads 3–5× high over Java at night, so the factor has to be able to go down as well as up.
  - **Over the forecast.** The local factor is held for 24 h. It then relaxes in log space towards the regional median factor (e-folding 72 h), instead of fading back to raw CAMS, which created false trends.
- **Measured skill** (leave-one-station-out, 111 stations, 17 Oct 2026, `docs/research/audit-air-quality.md`):

  | | Median abs. log error | Within ×2 |
  | --- | --- | --- |
  | Raw CAMS | 1.05 | 29% |
  | Corrected | 0.61 | 56% |
  | Kalimantan, corrected | 0.48 | 71% |

  - Typical error is about ×1.6 within 50 km of a station and about ×3 beyond 150 km, which is no better than raw.
  - In haze (stations above 100 µg/m³), CAMS reads about 0.35× the station 24 h means. Over all stations it reads about 0.85×.
- **City outlook.** Daily means for the next three 24 h windows, not hourly peaks. Day 1 is shown as a ÷1.7–×1.7 range; days 2–3 as ISPU categories only.
- **Cross-border attribution** (`smoke/transboundary.json`).
  - Fires outside Indonesia are sources too.
  - Shares are shown only when the modelled smoke over the next 24 h averages ≥ 10 and explains ≥ 20% of the measured excess over a 15 µg/m³ background.
  - On 17 Oct 2026 the modelled smoke at Singapore, Johor Bahru and KL was about 1% of the measured excess, so no split is shown there. It is an attribution of modelled smoke, not of measured PM2.5, and there is no ensemble yet.

## Spread: `haze spread`

A stochastic cellular automaton on the 375 m VIIRS grid:

- **Steps.** 6 h steps out to 72 h, 64 Monte Carlo members.
- **Ignition.** A burning cell ignites a neighbour with probability p = p0[fuel] · p_wind · p_slope · p_dry:
  - p_wind and p_slope use the Alexandridis et al. 2008 forms (c1 0.045, c2 0.131, a 0.078/°). p_wind is normalised to mean 1, so wind redistributes spread rather than inflating it.
  - p_dry = exp(−rain_6h / 5 mm).
  - Slope comes from the same SRTM terrain tiles as the 3D map.
  - Peat comes from the KHG 2017 units.
- **Persistence.** Cells keep burning with probability `persist` per step: 0.75 on peat, 0.5 elsewhere.
- **Spotting.** 1% per step, 2–4 cells downwind.
- **Calibration.** p0 and persistence were fitted by grid search on a past season.
- **Output.** Probability of a cell being active on each forecast day (bands ≥ 0.25 / 0.5 / 0.75), plus the expected new area.

**Hindcast** (`haze spread-eval`): next-day active-fire mask, the same task as Huot 2022 and
WildfireSpreadTS. 143 event-days fitted on 2019, 143 held out on 2023. The hindcast uses no
weather, since the archive has none, so wind and rain only act in live forecasts.

| Held-out 2023 | Model | Persistence | Dilated persistence |
| --- | --- | --- | --- |
| Average precision (AUC-PR) | **0.083** | 0.055 | 0.057 |
| CSI (best threshold) | 0.115 | 0.110 | 0.080 |

**With weather** (`scripts/backtest_spread_weather.py`): the hindcast above has no
weather. Feeding each case the 6-hourly 10 m wind and rain of its day from NASA
POWER (MERRA-2), on 142 held-out 2023 fire-days:

| Held-out 2023 | AP | CSI (best) |
| --- | --- | --- |
| Persistence | 0.053 | 0.126 |
| Model, no weather | 0.100 | 0.128 |
| Model with wind and rain (as live) | **0.108** | 0.131 |
| Refitted on 2019 with weather | 0.109 | 0.132 |

Wind and rain add a little; the refit changes almost nothing, so the saved
parameters stay.

**Reading the results:**

- **Average precision.** The model ranks next-day fire cells about 50% better than persistence. That is similar to the gain WildfireSpreadTS reports for deep models over persistence (AP 0.19 → ≈ 0.3).
- **CSI.** At a single threshold the model only ties persistence. Most new detections are new ignitions inside or near existing fire, which no model sees coming.
- **Skill across seasons.** The 2019 fit scores higher (AP 0.20 vs 0.13) because 2019 was a far bigger season.
- **Re-fitting.** `haze spread-eval --save` writes `pipeline/static/spread_params.json` and the full trial grid.

## Hotspot counts, evidence tiers and burned area

- **Public hotspot filter.** Inside Indonesia, not a permanent heat source, nominal/high confidence. The same filter is used everywhere (dashboard, history, tables). The 24 h block also gives a SiPongi-comparable count: Terra, Aqua, S-NPP and NOAA-20, all confidence levels. Ours runs about 1.6–1.8× higher because NOAA-21 adds a third VIIRS pass.
- **Evidence tier per event.**
  - `strong`: ≥ 2 overpasses, ≥ 2 pixels in one pass, a night detection, or a saturated VIIRS pixel.
  - `single`: one daytime pixel seen once. That is about half of all 2026 events, and the bulk of false alarms.
  - Headline counts use strong events only.
- **Static mask.** Built from 2019–2025 archives plus cells persistently hot through 2026 (`haze static-mask --years 2026 --merge`).
- **Burned area** (`area.py`).
  - Unique 375 m VIIRS fire pixels per satellite (once per season), averaged over the satellites flying, × 14.06 ha × k.
  - k = 0.49 is fitted to KLHK's 2019/2023 totals and reproduces each year within ~4%. k = 0.90 is fitted to the Sentinel-2 map of Gaveau et al. 2021 for 2019.
  - The site shows the range between the two. 2026 to 17 Oct: 2.3–4.2 M ha nationally, against 202 k ha official (Jan–Jul data).
- **Independent check** (`research/burned_area/`). A stratified sample of 700 points labelled from Sentinel-1/2 and Landsat, using the Olofsson/Stehman estimator with label-error correction from expert points:

  | Central Kalimantan | This check | Official | Others |
  | --- | --- | --- | --- |
  | 2019 | ~649 k ha (95% 389 k–952 k) | 318 k ha | MCD64A1 518 k, FireCCI 626 k, Gaveau 473 k |
  | 2026 to 17 Oct | ~664 k ha (95% 374 k–1.06 M) | 7.6 k ha (to July) | — |

## Fire status: active, not seen 1-3 days, not seen > 3 days

A fire is "active" while detected in the last 24 h, then "not seen 1-3 days",
then "not seen > 3 days" (`config.StatusParams`). Smoke paths and spread
forecasts are shown only for active fires: the smoke model's sources are fires
detected in the last 24 h, and old spread forecasts are not shown.

Unseen is not the same as out. `scripts/backtest_fire_status.py` takes every fire
of Jul-Sep 2026 (71,172 with 2+ detections) and checks whether its own ~1.6 km
cells (0.015 deg) were detected again after it went quiet:

| Quiet for | Fires | Seen again within 7 days | within 14 days |
| --- | --- | --- | --- |
| 1 day, non-peat | 61,405 | 33% | 48% |
| 1 day, peat | 8,865 | 43% | 59% |
| 3 days, non-peat | 54,956 | 31% | 46% |
| 3 days, peat | 7,416 | 39% | 55% |

Clouds, smouldering peat and land burned again all play a part. The status
therefore says "not seen", never "out", and the fire panel of a quiet fire
shows its type's rate.

## Fire danger: `haze` run step `danger`

- **Weather.** NASA GFWED GEOS-5 forecasts of FFMC, DMC, DC, ISI and FWI: the Canadian FWI system with the equatorial calibration BMKG uses in SPARTAN. 0.25°, up to 8 days. Brought forward to today with ECMWF weather (below).
- **Model.** Logistic regression of "≥ 1 VIIRS hotspot in the 0.25° cell next day" on:
  - DC, DC², FFMC, ln DMC, ln ISI;
  - KHG peat fraction and peat × DC;
  - log hotspots in the cell over the last 1, 7 and 30 days.
- **Fitting.** Trained on 2019 with MERRA-2 (gauge-corrected rain). GEOS-5 codes are quantile-mapped to MERRA-2 using 2023 days. `scripts/fit_danger.py` refits it.
- **Test on 2023 with the real GEOS-5 forecasts:**

  | Lead | AUC | Brier skill | AUC where nothing burned in 7 days | DC alone |
  | --- | --- | --- | --- | --- |
  | 1 day | 0.895 | 0.39 | 0.82 | 0.78 |
  | 3 days (hotspot within 3 days) | 0.893 | 0.32 | 0.80 | 0.79 |

- **Test by forecast lead on 2026** (`scripts/backtest_danger_lead.py`). NASA publishes
  GFWED runs days late (on 18 Oct the newest was from 14 Oct), so the live card often
  uses weather forecast 4+ days ahead. Jul-Sep 2026, every 4th day, ~61,000 cell-days
  per lead, fires up to the day's start as live:

  | Weather lead | AUC | 'Ekstrem' burned | 'Rendah' burned |
  | --- | --- | --- | --- |
  | 1 day | 0.894 | 73% | 2.3% |
  | 3 days | 0.892 | 73% | 2.4% |
  | 5 days | 0.889 | 73% | 2.6% |
  | 7 days | 0.885 | 73% | 3.1% |

  Recent fires alone (7-day count) reach AUC 0.866 and DC alone 0.75: weather adds
  skill, but most of the signal is where it burned recently. danger.json carries the
  issue date and the card shows it.
- **Brought forward to today** (`haze.fwi`, `danger.freshen`). Since 18 Oct 2026 the
  codes no longer wait for NASA: the newest run's first day is the starting state, and
  each day after it is computed with the Canadian FWI equations (Van Wagner 1987;
  equatorial day lengths Le 9.0, Lf 1.4, Lawson & Armitage 2008) from ECMWF IFS
  weather via Open-Meteo: local-noon temperature, humidity and 10 m wind, rain in the
  24 h before noon, on a 0.75° grid fetched once a day. The forecast is then issued
  today and reaches today + 7. The equations reproduce the CFFDRS reference day exactly
  (FFMC 87.7, DMC 8.5, DC 19.0, ISI 10.9, FWI 10.1; `tests/test_fwi.py`). Against
  GFWED's own forecast for 16-22 Oct (same start, GEOS-5 weather), over the model's
  land cells: DC r = 0.99-1.00, DMC 0.93-0.98, FFMC 0.67-0.81, ISI 0.56-0.77; ours
  runs a little wetter (median DC 5-7% lower) because IFS rained more. If the weather
  fetch fails, the card falls back to GFWED's forecast as issued.
- **Classes.** Rendah < 5%, Sedang 5–15%, Tinggi 15–40%, Ekstrem ≥ 40%. In 2023, cells in those classes had a hotspot the next day 1.5%, 9%, 27% and 65% of the time.
- **Status.** A statistical model, not BMKG's official rating.

## Fire progression: `progression.py`

- **Arrival time per 375 m cell.** The first VIIRS detection minus half the gap to the previous overpass.
- **Inside the footprint.** Each cell takes the median of its 5 nearest detected cells, chosen by cross-validation on 2019/2023 fires: 54% of held-out cells within ±12 h and 68% within ±24 h.
- **Outputs:**
  - daily 14:00 WIB fronts;
  - spread arrows and rate of spread, with jumps of > 2 km listed separately;
  - an FRP-weighted ignition estimate with its uncertainty;
  - rapid-growth, jump and stall events;
  - an elevation profile from SRTM.

## Fire history and repeat burning: `fire_history.py`

Question: is this season burning land that burned before? Fire concentrates in
the same places (Vetrita & Cochrane 2019: in 2001–2018 cumulative burned area
equalled about half of Kalimantan and Sumatra but sat in ~25% of the land), and
drained peat that burned once burns again (Hoscilo et al. 2011). Recurring fire
is where rewetting, canal blocking and patrols pay off.

- **History:** the VIIRS S-NPP yearly archives for 2012–2025. A single satellite is used for every year so that NOAA-20/21 do not inflate the recent years. Only vegetation fires are kept (FIRMS `type` 0, which also drops volcanoes, static sources and offshore detections), at nominal/high confidence. They are snapped to the 375 m area grid (`config.CELL_DEG`). `static/fire_history.parquet` stores a year bit mask per cell: 1.51 M cells, 3.5 MB. Rebuild it with `haze fire-history --build`.
- **Season overlap:** this season's S-NPP fire cells under the public filter, matched against the history. The output is the share that burned before, the share that burned in ≥ 2 past years, and the share that burned in a big year (2015/2019/2023). It is reported nationally, for peat and non-peat, and per province with ≥ 300 cells.
- **Events:** the share of each event's VIIRS cells (all satellites) that burned before, plus the past years that cover ≥ 5% of the event.
- **Map:** a 0.01° grid with the number of fire years per cell (`fire_history.png`, grayscale, north-up).

Results (2026 to 17 Oct, 324k S-NPP fire cells):

| | burned before | in ≥ 2 years | in 2015/2019/2023 |
|---|---|---|---|
| All | 47% | 21% | 33% |
| Peat | 63% | 33% | 52% |
| Non-peat | 40% | 16% | 25% |

- **Land that ever burned:** 11% of Indonesia's land holds 47% of the 2026 fire cells, a 4.2× lift over chance.
- **Hindcast:** 52% of the 2023 fire cells fell on the 10% of land that burned in 2012–2022 (5.1× lift).
- **Provinces:** Central Kalimantan 59%, South Sumatra 61%, South Kalimantan 60%, West Kalimantan 50%. Papua is lower at 36%, and West Papua is 8%: much of its 2026 fire is on land with no fire detected since 2012.

Caveats:
- These are fire pixels, not burned area.
- "Same 375 m cell" is a strict match. Geolocation shifts by up to a pixel between overpasses, so the shares lean low; a 1 km neighbourhood would raise them.
- The land share uses BPS land area (1.90 M km²) and an equatorial cell size.

## Health advice and forecast check: `verify.py`

- **Advice:** the health card maps each city's forecast for the next 24 h to an ISPU category. The input is the 24 h mean PM2.5, station-corrected (ISPU is defined on 24 h means, not hourly peaks). Each category shows two pieces of guidance:
  - the school mode from SE Mendikdasmen No. 20/2026 (28 Aug 2026);
  - public advice from Kemenkes (26 Aug 2026).

  Only Indonesian cities are shown. News reports of the circular disagree on whether fully remote learning starts above ISPU 200 or 300, so for "Sangat tidak sehat" the card says to follow the dinas pendidikan rather than pick one.
- **Logging:** every smoke run stores each city's 24 h mean forecast for the next three windows in `aq_forecast`, one row per 6-hour CAMS cycle.
- **Scoring:**
  - A window counts once it has ended and an ISPU station within 25 km reports at its end. The ISPU value is a trailing 24 h mean, so it covers the same window.
  - The scores are the exact-category hit rate, the within-one-category rate and the median forecast/observed ratio.
  - They are compared with persistence: the station's 24 h mean at issue time, carried forward.
  - Scoring uses the last 30 days and needs at least 20 pairs per lead day. Until then the card shows no score.

## Desa waspada: `desa.py`

Desa (village) boundaries come from OCHA/BPS COD-AB (81,912 desa, CC BY-IGO). `scripts/build_desa.py` rasterises them once onto the 0.01° map grid, and the result is committed as `static/desa_grid.npz` plus `static/desa.parquet` (3.5 MB in total). Checked against exact point-in-polygon on 26k 2026 fire detections, the grid puts a fire in the right desa 93% of the time and in the right kecamatan 98%.

There are two lists, each published with the rate it earned in a hindcast (`scripts/desa_hindcast.py`: 2023 Jul–Oct, VIIRS S-NPP, weekly; the fire history there uses only 2012–2022):

| Desa this week | Burned the next week |
|---|---|
| Hotspots in the last 7 days ("fire now", 7.5k desa on 17 Oct 2026) | 39% |
| No hotspot, burned in ≥ 3 of 2012–2025 ("watch", 7.9k desa) | 11.6% |
| Any desa without a hotspot | 2.2% |
| No hotspot and no fire 2012–2022 | 0.1% |

Each row also shows tomorrow's highest fire-danger probability over the desa's area and its KHG peat share. The lists are filters with measured rates, not a fitted score. Fitting a score would need a hold-out season, and a filter is easier for a desa head or a Manggala Agni Daops to check.

## Seasonal outlook: `outlook.py`

The outlook shows ENSO (NOAA CPC ONI and weekly Niño 3.4) and the IOD (Bureau of Meteorology weekly index). It also shows each fire-belt province's chance that the next 30 / 60 days stay dry, meaning average rain under 4 mm/day (Field et al. 2016). That chance is the share of the 51 ECMWF seasonal ensemble members, served by Open-Meteo, that stay dry.

The live check from a GitHub runner (`outlook-check` workflow, 17 Oct 2026) returned 51 members per point. It gave very strong El Niño with a positive IOD, and a 30-day dry chance of 96% for Merauke, 63% for Kalimantan Selatan, 61% for Sumatera Selatan, 10% for Kalimantan Tengah and 0% for Riau.

**Backtest of the dry rule** (`scripts/backtest_outlook_rule.py`). The ensemble
forecast is ECMWF's; what the app adds is reading it with the < 4 mm/day rule.
Over 2012-2025, 896 thirty-day windows (starting 1 and 16 Jul-Oct) at the 8
points, rain from NASA POWER (MERRA-2) and VIIRS S-NPP detections within +-1 deg:

| | Dry windows | Wet windows |
| --- | --- | --- |
| Windows | 359 | 537 |
| Median detections | 1,388 | 178 |
| Mean detections | 4,899 | 809 |

78% of the biggest fire windows (top 10% per point) were dry. The rule is weaker
in West Kalimantan (42%) and Riau (50%), and says little at Merauke, which is dry
in 98 of 112 windows.

## Southeast Asia comparison: `compare.py`

`compare.json` sets Indonesia's hotspots against the other ten Southeast Asian
countries (Papua New Guinea shown as a neighbour, never ranked).

- **One satellite.** VIIRS S-NPP only, for every year and country, so the
  newer NOAA-20/21 do not inflate recent years.
- **2012-2025** (`static/compare_history.json`, built once by
  `scripts/build_compare.py`): FIRMS yearly country archives, type 0 (presumed
  vegetation fire) and nominal/high confidence, exactly as `fire_history.py`
  filters Indonesia; FIRMS assigns the country. Indonesia's distinct 375 m
  cells per year match `fire_history.json` in all 14 years.
- **Last 7 days**: the keyless S-NPP Southeast Asia 7-day NRT file. NRT has no
  type flag, so static heat sources are masked with the `haze.mask` rule
  instead (0.94-1.0x the type-0 count on 2025 data) and points are assigned
  with Natural Earth 10m borders (3 km coast snap; agrees with FIRMS'
  assignment 99.8-100% on 2025 points).
- **Year to date**: Indonesia only, from the `hotspots` table (S-NPP, same
  filters). No keyless year-to-date source exists for the other countries.
- **Per 1,000 km2**: land area from the World Bank (AG.LND.TOTL.K2, 2024).

Caveats the card states: counts are detections, not burned area; mainland
countries burn mostly short crop-residue fires in Feb-Apr and usually exceed
Indonesia per km2 in a normal year (2012-2025 mean: Cambodia 847, Laos 584,
Myanmar 451, Thailand 280, Indonesia 119 per 1,000 km2 a year); Indonesia
peaks Aug-Oct, often in peat. Indonesia ranked first in the region in 2014,
2015 and 2019, third in 2023 and fifth in 2025; by 16 Oct 2026 it had 496,645
detections, more than any other country recorded in any full year since 2012.
