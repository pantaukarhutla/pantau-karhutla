# Research: fire danger and "risk area" forecast from weather data

Compiled 2026-10-17. The goal is a layer showing where fires are likely in the coming days, for prevention. It should be based on weather, peat and recent fire activity. It is not a smoke or spread layer.

Tags, as in `data-gis-layers.md`:

- **[T]** tested from this container on 2026-10-17, 18:00–18:40 UTC. Outbound HTTPS went through the agent proxy.
- **[D]** read in the provider's documentation, in a directory listing, or in the paper's full text.
- **[S]** search snippet or secondary source only.

All pilot numbers below come from scripts in the session scratchpad, run against `data/haze.duckdb` and GFWED files. They are not part of the repo. Section 5 has enough detail to reproduce them.

---

## 0. Recommendation in one page

1. **Danger index.** Use the Canadian FWI System as calibrated for Indonesia by the ASEAN/CFS South-East Asia FDRS project (de Groot et al. 2007). BMKG runs the same system operationally (SPARTAN). The indices are:
   - **FFMC**, for ignition potential;
   - **DC**, for deep peat dryness and haze potential;
   - **ISI**, for difficulty of control in grass;
   - **DMC / BUI / FWI**, as context.

   The equatorial day-length constants are Le = 9.0 h for DMC and Lf = 1.39 for DC. BMKG's official class bounds are in §4.
2. **Data source.** Use NASA **GFWED** as the primary source. It is keyless NetCDF, and the files contain FFMC, DMC, DC, ISI, BUI, FWI and DSR already spun up since 1980.
   - **Live:** GEOS-5 runs, analysis plus 8-day forecasts at 0.25° × 0.3125°, about 1.5–3 days behind [T].
   - **Calibration:** the archive for 2019 and 2023 [T]. It includes GEOS-5 analyses, *archived GEOS-5 forecast runs*, and MERRA-2 runs with gauge-corrected rain.
   - **Reading:** `scipy.io.netcdf_file`, which is already a dependency, reads the files [T]. No new packages are needed.
   - **Open-Meteo** stays a cheap supplement: add `temperature_2m` to the existing `fetch_wind` request. It then has 9 variables, so the weight is unchanged. This lets us step DC and FFMC forward ourselves from the latest GFWED state when GFWED is late.
   - Open-Meteo alone is a poor source for this layer. Its free quota is already about 90 % used. `past_days` is capped at 93 [T], which is not enough to spin up DC in a dry year. Its archive host returned 429 from our IP [T].
3. **Risk model.** Use a small **logistic regression** of "≥ 1 VIIRS detection in a 0.25° cell on day t+1 (and t+1..t+3)". The features are:
   - FWI codes;
   - days since rain and 30-day rain;
   - peat fraction (KHG), with a DC × peat interaction;
   - recent fire activity (log fires in the last 1, 7 and 30 days);
   - a fire climatology from other years.

   The pilot trained on 2019 and tested on 2023:
   - **Single danger index:** AUC 0.75–0.77.
   - **Weather + peat:** AUC 0.78–0.80.
   - **Persistence alone:** AUC 0.88.
   - **Full model:** **AUC 0.89–0.90**, Brier skill 0.37–0.45, and well calibrated.
   - **Real GEOS-5 forecasts:** skill holds at forecast lead 3 (AUC 0.890).
4. **UI classes.** Show the model probability in four classes:

   | Class | Next-day P(fire in 0.25° cell) |
   | --- | --- |
   | **Rendah** | < 5 % |
   | **Sedang** | 5–15 % |
   | **Tinggi** | 15–40 % |
   | **Ekstrem** | ≥ 40 % |

   The tooltip shows the BMKG/FDRS component classes (FFMC, DC, ISI). In 2023 these classes covered 44 / 26 / 16 / 14 % of land cells and held 4 / 15 / 27 / 54 % of next-day fires. Observed frequencies were 1.5 / 9.7 / 29 / 65 %.

---

## 1. Fire danger indices for Indonesia

### 1.1 Canadian FWI System as adopted for Indonesia and Malaysia

The South-East Asia Fire Danger Rating System project (CIDA/CFS with BMG/LAPAN, MMD and ASEAN) adapted the Canadian FWI System in 1999–2004. de Groot et al. (2007) is the reference paper. Its key calibrations, all [D] from the full text, are:

- **Equatorial day length.** Le = 9.0 drying hours per day for DMC, and Lf = 1.39 for DC. These are constant through the year, "representing the annual average value for southern and northern hemispheres."
- **DC as smoke potential.**
  - Field et al. (2004) compared visibility (haze) with DC over Sumatra and Kalimantan for 1994–1998. They found that "the occurrence of severe haze events increased substantially when DC was above 400."
  - The paper also notes deep smouldering potential once DC exceeds about 300 (de Groot 1988).
  - DC classes are defined by *drying days until DC reaches the ~400 threshold* (Table 1 of the paper):

| Smoke potential | DC | Dry days before drought | Interpretation (abridged) |
| --- | --- | --- | --- |
| Low | < 140 | > 30 | Typical wet season. Severe haze unlikely. |
| Moderate | 140–260 | 16–30 | Mid-dry season. Burning regulated and monitored. |
| High | 260–350 | 6–15 | Dry-season peak. **All burning in peatlands restricted.** |
| Extreme | > 350 | < 6 | Approaching disaster drought. Severe haze highly likely. Complete burning ban. |

> Note: the brief mentioned "DC > 140 / > 250". The published and operational bounds are **140 / 260 / 350**, with 400 as the haze threshold.

- **FFMC as ignition potential.** The calibration has two parts:
  - **Hotspots, 1995–2000.** Hotspot frequency rose sharply at FFMC 81–83. Over 78 % of hotspots occurred when FFMC > 81, though that covered only 20 % of days. Over 85 % occurred when FFMC ≥ 78.
  - **Grass ignition in Riau** (de Groot, Wardati & Wang 2005). The match-test ignition threshold (P = 0.5) was about 35 % moisture in dead *Imperata* grass, which corresponds to FFMC 81–83.

  The resulting classes (Table 2 of the paper):

| Ignition potential | FFMC | Share of days | Share of hotspots |
| --- | --- | --- | --- |
| Low | 0–72 | 0.62 | 0.10 |
| Moderate | 73–77 | 0.08 | 0.04 |
| High | 78–82 | 0.16 | 0.13 |
| Extreme | 83+ | 0.13 | 0.73 |

  How the bounds were set:
  - **77/78** is the lower 95 % CI of dead-grass ignition.
  - **82/83** is the ignition threshold itself.
  - **72/73** was set "arbitrarily … to provide early warning".
- **ISI as difficulty of control in grassland.** This uses the FBP grass model with a fuel load of 1.8 kg/m² and 65 % curing.

  | Class | ISI | Head-fire intensity | Rate of spread |
  | --- | --- | --- | --- |
  | Low | 0–1 | < 250 kW/m | – |
  | Moderate | 2–3 | 250–1250 kW/m | – |
  | High | 4–5 | 1250–2500 kW/m | – |
  | Extreme | 6+ | > 2500 kW/m | ≥ 4.7 m/min |

- **Operations.** BMG HQ computes FFMC, DC and ISI daily from 12:00 LST synoptic observations (163 stations) using sFMS.

### 1.2 What BMKG publishes today (SPARTAN) [T]

`https://spartan.bmkg.go.id/` ("Sistem Peringkat Bahaya Kebakaran") shows FFMC, DMC, DC, BUI, ISI and FWI for "Prediksi H+0 … H+7". The legend is stored in the site bundle (`/_nuxt/CZFWjVBd.js`) and was extracted on 2026-10-17. The four colours are biru `1,176,241`, hijau `0,255,1`, kuning `255,255,1` and merah `255,0,0`. Every product carries the disclaimer "BUKAN lokasi kebakaran hutan".

| Index | Biru | Hijau | Kuning | Merah |
| --- | --- | --- | --- | --- |
| FFMC | 0–72 "masih cukup basah" | 73–77 | 78–82 "mudah menyala" | > 82 "sangat mudah menyala" |
| DMC | 0–4 | 5–14 | 15–29 | > 29 |
| DC | 0–140 rendah | 141–260 sedang | 261–350 tinggi | > 350 sangat tinggi |
| BUI | 0–6 | 7–19 | 20–33 | > 33 |
| ISI | 0–1 | 2–3 | 4–5 | > 5 |
| FWI | 0–1 rendah | 2–6 sedang | 7–13 tinggi | > 13 sangat tinggi |

BMKG names the top class "sangat tinggi". The FDRS paper calls it "Extreme", and the brief asks for "Ekstrem". Section 6 discusses the choice. SPARTAN has a `/Download-Data` page, but no anonymous API was found. Its map is not a source for us. It is useful for consistency checks.

### 1.3 KBDI (Keetch–Byram Drought Index)

KBDI is a soil-moisture deficit from 0 to 203.2 mm (0–800 in 0.01 inch), driven by daily maximum temperature, daily rain and mean annual rain (Keetch & Byram 1968). The metric form (Crane 1982, as used by Janis et al. 2002) is:

```
dQ = (203.2 − Q) · (0.968·exp(0.0875·Tmax + 1.5552) − 8.30) / (1 + 10.88·exp(−0.001736·R)) · 10⁻³   [mm/day]
```

- Q is the previous KBDI in mm, Tmax is in °C, and R is the mean annual rain in mm.
- Net rain is subtracted from Q. Within a consecutive-rain spell, the first 5.1 mm (0.2 in) is not counted.
- Q is floored at 0.

KBDI is used in Malaysia and in several Indonesian studies (e.g. Agdialta 2021, Jurnal Penelitian Kehutanan Sumatrana). For us it carries the same information as DC: both are slow drought codes driven by temperature and rain. **The FDRS standard is DC, so we skip KBDI.**

### 1.4 Days without rain (BMKG "Hari Tanpa Hujan", HTH)

BMKG monitors HTH at about 4,500 rain posts. A day with ≥ 1 mm counts as a rain day and resets the count. The classes, [S] from news reports quoting BMKG bulletins, are:

| HTH (days) | Class |
| --- | --- |
| 1–5 | sangat pendek |
| 6–10 | pendek |
| 11–20 | menengah |
| 21–30 | panjang |
| 31–60 | sangat panjang |
| > 60 | kekeringan ekstrem |

It is trivial to compute from Open-Meteo or GFWED rain (`Prec.*` inputs, [T]). It is easy for the public to understand, so we include it as a feature and a tooltip item. On its own it was the weakest predictor in the pilot (AUC 0.69–0.71).

### 1.5 Precipitation thresholds from the Indonesian fire literature

- **Field et al. (2016, PNAS).** Fire and smoke increase sharply when rain averaged over the previous 12 weeks falls below **about 4 mm/day**. Change points across indicators were 3.9–5.2 mm/day, with little activity above about 6 mm/day. The authors recommend "early warning triggers tied to precipitation forecasts". [D]
- **Fanin & van der Werf (2017).** The best antecedent window for southern Sumatra and Kalimantan is **120 days**; for northern Sumatra it is 30 days. A high-fire year corresponds to about 200 mm (S Sumatra) and 305 mm (S Kalimantan) accumulated before fires. [D]
- **Field et al. (2009).** Severe burning since 1960 occurs only below a well-defined dry-season rain threshold. [D]
- **Fernandes et al. (2017).** In normal-to-wet July–October, fire probability rises sharply with temperature. Weather therefore still matters outside El Niño years. [D] This argues for keeping FFMC and ISI, which respond to temperature and RH, next to DC.
- **Shawki et al. (2017).** DC from NCEP CFSv2 seasonal forecasts predicted the high DC of 2015 up to 180 days ahead for southern Kalimantan and New Guinea, and up to 60 days for southern Sumatra. This is a seasonal-outlook option for later. [D]
- **Spessa et al. (2015).** ECMWF System 4 seasonal rain explains about 70 % of the variance in burnt area in Kalimantan. The relationship is non-linear and strongest in the south, where tree-cover loss is high. [D]

### 1.6 Peat-specific dryness

- **Water table.** Peat ignites and burns deep when the groundwater level (GWL) is below about **−40 cm**.
  - Wösten et al. (2008) give the hydrological basis.
  - PP 71/2014 as amended by PP 57/2016 sets "muka air tanah > 0,4 m below the peat surface" as the criterion for damaged peat. [S]
  - BRGM's SiPALAGA loggers measure GWL, but they have no public API (`data-gis-layers.md`).
- **Taufik et al. (2015).** A modified KBDI (mKBDI) for tropical wetlands that includes water-table depth, developed in Central Kalimantan.
- **Taufik et al. (2017).** Hydrological drought (low groundwater recharge) amplifies burnt area in the humid tropics.
- **Taufik et al. (2019, Geoderma).** Critical groundwater thresholds depend on peat physical properties.

  Without GWL data, **DC is the accepted proxy** for deep peat dryness (de Groot 2007; Field 2004).
- **Pilot result: DC splits sharply by peat (2019 / 2023).** Next-day fire frequency per 0.25° cell, by DC class:

| DC class | ≤ 140 | 140–260 | 260–350 | 350–400 | 400–600 | > 600 |
| --- | --- | --- | --- | --- | --- | --- |
| Non-peat | 0.09 / 0.10 | 0.23 / 0.23 | 0.30 / 0.30 | 0.35 / 0.35 | 0.39 / 0.38 | 0.45 / 0.51 |
| Peat (> 20 % KHG) | 0.11 / 0.08 | 0.33 / 0.35 | **0.52 / 0.47** | **0.60 / 0.54** | **0.65 / 0.66** | 0.80 / – |

  This supports a **DC × peat interaction** and the FDRS rule "restrict all peat burning at DC > 260".
- **Option, not tested:** Hooijer & Vernimmen's (2026) rainfall-driven 10 km water-table maps (Mendeley, CC BY 4.0, cited in `data-gis-layers.md`) could later be added as a feature.

---

## 2. Equations to port

### 2.1 Where to take the code from

| Implementation | Licence | Notes |
| --- | --- | --- |
| **xclim** `xclim/indices/fire/_cffwis.py` (v0.62.0 wheel, read here) [T] | **Apache-2.0** [T, PyPI] | Clean numba code with equation numbers.<br>Includes `DAY_LENGTHS` / `DAY_LENGTH_FACTORS` "taken from GFWED code", with the equatorial band −15°…15° set to 9 h and 1.39. That is exactly the Indonesian FDRS calibration.<br>Also has GFWED-style "dry start" and overwintering.<br>**Port about 150 lines to plain numpy** (`np.where` instead of numba scalar ufuncs) and keep the Apache notice. Do not depend on xclim: it pulls in xarray, dask, numba, pint and scikit-learn. |
| **cffdrs** R package 1.9.2 (CFS) | **GPL-2** [T, CRAN] | The reference implementation. Do not copy it into a non-GPL repo. Use it for test values only. |
| Wang, Anderson & Suddaby (2015), CFS Information Report NOR-X-424 | Government report with listings in Fortran 95, C, C++, **Python**, Java and SAS | Official updated source, tested against the 1985 FORTRAN 77 code. Good for unit-test fixtures. |
| Van Wagner (1987), Forestry Technical Report 35 | Public | Defines the equations themselves. Equation numbers below follow it. |
| PyPI `pyfwi` | GPL-3 | **Not fire weather.** It is *PyFWI*, a seismic full-waveform-inversion package (AmirMardan/PyFWI) [T, PyPI]. Do not use. |

### 2.2 Inputs

The inputs are local-noon (12:00 LST) **temperature** T (°C), **relative humidity** H (%), **10 m wind** W (km/h) and **24 h rain ending at noon** P (mm).

- With Open-Meteo `timezone=GMT`, take hour `12 − round(lon/15)` UTC. That is 05 UTC for WIB longitudes, 04 for WITA and 03 for WIT.
- P is the sum of the 24 hourly values ending at that hour.
- Our `fetch_wind` returns m/s, so **multiply by 3.6**.

### 2.3 Fine Fuel Moisture Code (FFMC), timelag about 2/3 day

```
m0 = 147.2(101 − F0)/(59.5 + F0)                                   (1)
if P > 0.5:  rf = P − 0.5
   m0 ≤ 150: m = m0 + 42.5·rf·exp(−100/(251 − m0))·(1 − exp(−6.93/rf))           (3a)
   m0 > 150: m = (3a) + 0.0015(m0 − 150)²·√rf                       (3b);  m ≤ 250
Ed = 0.942H^0.679 + 11exp((H−100)/10) + 0.18(21.1−T)(1 − e^(−0.115H))    (4)
Ew = 0.618H^0.753 + 10exp((H−100)/10) + 0.18(21.1−T)(1 − e^(−0.115H))    (5)
m > Ed (drying):  k0 = 0.424[1 − (H/100)^1.7] + 0.0694√W[1 − (H/100)^8]       (6a)
                  kd = 0.581·k0·exp(0.0365T);  m = Ed + (m − Ed)·10^(−kd)     (6b, 8)
m < Ew (wetting): k1 = 0.424[1 − ((100−H)/100)^1.7] + 0.0694√W[1 − ((100−H)/100)^8] (7a)
                  kw = 0.581·k1·exp(0.0365T);  m = Ew − (Ew − m)·10^(−kw)     (7b, 9)
otherwise m unchanged
F = 59.5(250 − m)/(147.2 + m)                                      (10), clip 0..101
```

### 2.4 Duff Moisture Code (DMC), timelag about 12 days (Le = 9.0 at the equator)

```
if P > 1.5:  re = 0.92P − 1.27                                      (11)
   Mo = 20 + exp(5.6348 − D0/43.43)                                 (12)
   b  = 100/(0.5 + 0.3D0) if D0 ≤ 33;  14 − 1.3 ln D0 if D0 ≤ 65;  6.2 ln D0 − 17.2 otherwise (13a-c)
   Mr = Mo + 1000re/(48.77 + b·re)                                  (14)
   Pr = 244.72 − 43.43 ln(Mr − 20), ≥ 0                             (15)
else Pr = D0
K = 1.894(T + 1.1)(100 − H)·Le·10⁻⁶  (T ≥ −1.1)                     (16)
D = Pr + 100K                                                       (17)
```

### 2.5 Drought Code (DC), timelag about 52 days (Lf = 1.39 at the equator)

```
if P > 2.8:  rd = 0.83P − 1.27                                      (18)
   Qo = 800 exp(−DC0/400)                                           (19)
   Qr = Qo + 3.937rd                                                (20)
   DCr = 400 ln(800/Qr), ≥ 0                                        (21)
else DCr = DC0
V = 0.36(T + 2.8) + Lf, ≥ 0                                         (22)
DC = DCr + 0.5V                                                     (23)
```

At Indonesian noon temperatures of 30–34 °C, DC rises by about **6.6–7.3 per dry day**. That is why the FDRS table converts DC margins into "dry days until 400": (400 − 350)/7 ≈ 6 days.

### 2.6 ISI, BUI and FWI

```
fW = exp(0.05039W);  fF = 91.9 exp(−0.1386m)[1 + m^5.31/4.93·10⁷]   (24, 25)
ISI = 0.208·fW·fF                                                   (26)
BUI = 0.8·D·DC/(D + 0.4DC)                       if D ≤ 0.4DC        (27a)
    = D − [1 − 0.8DC/(D + 0.4DC)]·[0.92 + (0.0114D)^1.7]  otherwise  (27b)
fD  = 0.626·BUI^0.809 + 2 (BUI ≤ 80);  1000/(25 + 108.64 e^(−0.023BUI)) otherwise (28a,b)
B   = 0.1·ISI·fD                                                    (29)
FWI = exp(2.72(0.434 ln B)^0.647) if B > 1, else B                  (30a,b)
DSR = 0.0272·FWI^1.77                                               (41)
```

### 2.7 Initialisation and spin-up

The codes are recursive, so they must be started from a known state.

| Code | Standard start value | Spin-up needed |
| --- | --- | --- |
| FFMC | 85 | About 3 days |
| DMC | 6 | About 6 weeks |
| DC | 15 | Through a **real wet period** |

These are the CFS start values. GFWED uses the same (`DCStart 15`, `DMCStart 6`, `FFMCStart 85` in its NetCDF global attributes [T]), plus a "dry start" that adds 5 (DC) or 2 (DMC) per day since the last rain.

DC needs a long spin-up because drying is **additive** (eq. 22–23 do not depend on DC0). An error in the initial DC therefore survives the whole dry season unchanged. Only rain shrinks it, through eq. 19–21: 50 mm of rain on DC 300 takes it to about 160.

The practical rules:

- **Cold start from our own weather:**
  - Begin in the wet season, e.g. 1 January, with DC = 15, and integrate daily.
  - Open-Meteo forecast `past_days` is capped at **93** [T]. Starting cold in mid-October would begin at 16 July, inside the dry season. A wrong start value would then bias DC by the full amount for the rest of the season. **Open-Meteo alone cannot spin up DC late in the season.**
  - The archive API (ERA5, 1940 onwards, 5-day lag [D]) would solve this, but returned 429 from our shared IP [T].
- **Recommended: warm start from GFWED.**
  - GFWED integrates continuously from 1980 (`nClimSkipYears 1`).
  - Each day, read the newest GFWED GEOS-5 analysis (DC, DMC, FFMC for day t−2 or t−3) as the state.
  - Optionally step it forward with Open-Meteo noon weather to today and through the forecast.
  - Persist the state in DuckDB so a missed GFWED day costs nothing.

---

## 3. Data sources

### 3.1 Open-Meteo (current provider)

| Check | Result |
| --- | --- |
| Forecast `past_days` | **Allowed range 0–93**: `past_days=100` returned "Past days is invalid. Allowed range 0 to 93" [T]. `past_days=93` with `daily=precipitation_sum` returned data from 2026-07-17 [T]. |
| Forecast `start_date` | Window "**from 2026-07-16 to 2026-11-01**" (about 93 days back to 16 days ahead) [T]. |
| Archive (ERA5) `archive-api.open-meteo.com` | **429 "Daily API request limit exceeded"** at 18:1x UTC [T], same as the earlier agent saw. `historical-forecast-api.open-meteo.com` gave the same 429 [T]. The docs say ERA5 runs from 1940 with a 5-day delay at 0.25°, so **2019 and 2023 should be available** [D], but this is not verified here. The IP is shared, so try again from an Actions runner. |
| `timezone=auto` | Works and returns local hours, e.g. `Asia/Pontianak` GMT+7 for Palangkaraya [T]. Our code uses GMT plus a longitude offset, which is equivalent. |
| Free quota | 600/min, 5,000/hour, **10,000/day**, 300,000/month [D, pricing page]. A request counts as more than one call above **10 variables** or **2 weeks** per location (15 vars × 2 weeks = 1.5 calls) [D]. Our code assumes location-calls (`smoke.py` `REFRESH_HOURS` comment). |
| Our current use | Estimated from the code, not measured:<br>• `fetch_smog`: 65 × 27 = 1,755 points × 4 refreshes/day ≈ 7,000.<br>• `fetch_wind`: 33 × 14 = 462 points × 4 ≈ 1,850.<br>• History backfill on top of that.<br>**About 8,900 of 10,000 per day are already used.** |

What this means:

- An independent FWI fetch at 0.25° over land (2,872 cells) would cost about 2,900 calls/day and breaks the budget.
- **The cheap path is to add `temperature_2m` to `fetch_wind`.** It goes from 8 to 9 variables and 7 days, so the weight is still 1 per location. This adds zero calls.
- That gives noon T, RH, wind and rain on the 1.5° `WIND_GRID` for t−3…t+3. It is enough to step DC and FFMC forward from GFWED and to compute HTH.
- The 1.5° grid is coarse for FFMC, which depends on local RH and wind. Accept it as a fallback only.

### 3.2 NASA GFWED (recommended primary)

Root: `https://portal.nccs.nasa.gov/datashare/GlobalFWI/v2.0/` [T]. All files are keyless HTTPS.

| Product | Path pattern | Coverage tested | Grid | Size |
| --- | --- | --- | --- | --- |
| **GEOS-5 forecast runs** (live) | `fwiCalcs.GEOS-5/Default/GEOS-5/YYYY/YYYYMMDD00/FWI.GEOS-5.Daily.Default.YYYYMMDD00.YYYYMMDD.nc` | Run `2026101400` holds 8 files, 15–22 Oct, posted 15 Oct 21:47 UTC [T]. Runs are irregular: 11 and 12 Oct were both posted on 12 Oct, and 13 and 14 Oct on 15 Oct [T]. | 0.25° × 0.3125° | 16.4 MB global per day |
| **GEOS-5 analysis** (live, about 1.5–3 days behind) | `…/GEOS-5/YYYY/FWI.GEOS-5.Daily.Default.YYYYMMDD.nc` | Latest is 20261014 on 17 Oct [T] | same | 16.4 MB |
| **GEOS-5 archive, including forecast runs** | same paths, 2014–2026 | 2019: 361 analysis days and 364 run folders. 2023: 364 run folders. Run `2023091500` holds 16–23 Sep [T]. | same | – |
| MERRA-2 (Default rain) | `fwiCalcs.MERRA2/Default/MERRA2/YYYY/FWI.MERRA2.Daily.Default.YYYYMMDD.nc` | 1980 to 2026-04-30 [T] | 0.5° × 0.625° | 4.3 MB |
| **MERRA-2, gauge-corrected rain** (calibration) | `fwiCalcs.MERRA2/Default/MERRA2.CORRECTED/…` | 1980–2026 [T]. Used in the pilot. | 0.5° × 0.625° | 4.1 MB |
| MERRA-2 met + IMERG Final v7 rain | `fwiCalcs.MERRA2/Default/IMERG.FINAL.v7/…` | 2000 to 2024-11-30 [T] | finer | 128 MB/day |
| Other rain variants | `CPC`, `GPCP`, `GPM.EARLY/LATE/FINAL.v5`, `TRMM`, `Sheff` | GPM-based and CPC live variants stop in Mar–May 2025 [T]. Do not rely on them. | | |
| Weather inputs | `wxInput/{MERRA2,MERRA2.CORRECTED,GEOS-5,…}/YYYY/Prec.*.Daily.Default.YYYYMMDD.nc` | 1980–2025 (MERRA2) [T] | | 610 KB |

Reading the files:

- **Format:** classic NetCDF, 64-bit offset (`file`: "NetCDF Data Format data (64-bit offset)"). `scipy.io.netcdf_file` reads it [T].
- **Variables:** `GEOS-5_DC`, `_DMC`, `_FFMC`, `_ISI`, `_BUI`, `_FWI`, `_DSR` as `(time=1, lat, lon)` float32 with NaN masking. MERRA-2 files use `MERRA2.CORRECTED_DC` and so on. Latitude runs −58 to 75 and longitude −180 to 179.69 [T].
- **Range requests:** the server sends `Accept-Ranges: bytes` [T]. Each variable is contiguous, so the about 73 Indonesian latitude rows (about 340 kB per variable) can be fetched with ranged GETs after parsing the header. That turns 16 MB per day into about 2 MB. This is optional: a full daily run of 8 forecast files is about 130 MB, which is fine on Actions.

Sample values for 17 Oct 2026, from the 14 Oct run (lead 3) [T]:

| Place | DC | DMC | FFMC | ISI | FWI |
| --- | --- | --- | --- | --- | --- |
| Palangkaraya | 625 | 60 | 88.4 | 4.1 | 16.7 |
| Palembang | 521 | 27 | 79.9 | 2.0 | 6.0 |
| Banjarmasin | 663 | 93 | 91.0 | 7.5 | 29.6 |
| Pekanbaru | 35 | 4 | 76.4 | 1.4 | 0.7 |

**Known biases.** Field (2020, NHESS) evaluated MERRA-2 FWI against 1,746 stations:

- The global median DC bias is −55.
- In Equatorial Asia, FFMC and ISI biases follow RH biases (r ≈ −0.62), and DC biases follow rain biases (r = −0.59).
- The paper recommends **re-deriving class thresholds for reanalysis or forecast FWI** instead of reusing station thresholds.
- GEOS-5 forecasts are near-perfect at day 1, and still have r > 0.8 at day 5 for most tropical regions.

In our pilot, on the same 2023 cell-days, **GEOS-5 FWI was much lower than MERRA-2-corrected FWI** (median DC 46 vs 75, FFMC 61.5 vs 73.2) [T]. **Train the model on the product you run live (GEOS-5)**, or quantile-map one onto the other.

### 3.3 Not chosen

- **CEMS/GWIS (ECMWF FWI)** is a nice WMS picture, but raw grids need an EWDS key (`data-gis-layers.md`).
- **BMKG SPARTAN** has no anonymous data API.
- **SMAP** soil moisture adds little over saturated peat, and DC covers the need.

---

## 4. Risk model

### 4.1 Why not a danger index alone

FDRS classes describe the *weather's* potential. In Indonesia almost all fires are lit by people (Cattau et al. 2016; Sloan et al. 2017). Where and when fires occur depends heavily on:

- **access** (roads, canals);
- **land conversion**;
- **previous burns.**

Cattau et al. (2016) show that ignitions on Kalimantan peat cluster near access routes and repeat on already-burned land. Sloan et al. (2017) show fire activity in Borneo during El Niño driven jointly by drought and industrial land conversion. Nikonovas et al. (2020) show fires do not penetrate more than about 2 km into intact primary forest, whatever the drought.

A model that adds **persistence** (recent fires nearby) and a **fire climatology** captures these human and land-cover controls cheaply, without new datasets. This matches the pilot: persistence alone beat every weather index.

### 4.2 Model specification

- **Unit:** 0.25° cell × local day. This matches `PLUME_GRID` resolution; the pilot used `lon0 = 94.5`, `lat0 = −11.25`.
- **Domain:** cells with ≥ 20 % land inside the geoBoundaries provinces. That gives 2,872 cells, 443 of them with > 20 % KHG peat.
- **Target:** `y1` = ≥ 1 VIIRS detection on day t+1, and `y3` = ≥ 1 detection on days t+1..t+3. Detections are filtered to `in_indonesia`, not `is_static`, confidence ≠ low. The local day uses lon/15 h.
- **Model:**

```
logit P(y=1) = β0 + β1·DC + β2·DC² + β3·FFMC + β4·ln(1+DMC) + β5·ln(1+ISI)
             + β6·ln(1+HTH) + β7·ln(1+P30) + β8·peat + β9·peat·DC
             + β10·ln(1+F1) + β11·ln(1+F7) + β12·ln(1+F30) + β13·ln(1+Fclim)
```

The variables are:

- **Weather codes:** DC, FFMC, DMC and ISI for the **target day**, taken from GEOS-5 at the matching lead.
- **HTH** is days since rain ≥ 1 mm, and **P30** is the 30-day rain total.
- **peat** is the KHG fraction of the cell (5 × 5 sub-sampling in the pilot).
- **F1, F7 and F30** are detections in the cell over the last 1, 7 and 30 days.
- **Fclim** is the July–October detection count in *other* years.

Fitting and serving:

- Fit with L2-penalised maximum likelihood on standardised features. The pilot used scipy L-BFGS and needs no scikit-learn.
- Store the means, SDs and β as JSON in the repo, and refit each year after the season.
- Fit one model per lead (+1, +2, +3, and +4..+7 combined) so each absorbs the forecast-error variance at that lead.

### 4.3 Pilot results (2019 train, 2023 test, July–October, 0.25° cells) [T]

Data: GFWED MERRA-2.CORRECTED with gauge-corrected rain. Features are from day t (`t wx`) or "perfect forecast" day t+1 (`t+1 wx`). There are 706,512 cell-days. Base rates are 0.20 / 0.17 for `y1` and 0.34 / 0.29 for `y3`.

**Single predictors, test year 2023 (`y1`):**

| Predictor | AUC |
| --- | --- |
| DC | 0.755 |
| FFMC | 0.772 |
| DMC | 0.772 |
| FWI | 0.772 |
| Days since rain (HTH) | 0.713 |
| 30-day rain (negative) | 0.735 |
| Fires, last 7 d | 0.851 |
| Fires, last 30 d | 0.866 |
| 2015 fire climatology | 0.754 |
| FDRS rule class (FFMC class; on peat, max of FFMC and DC class) | 0.734 |

**Logistic models, test 2023:**

| Model | y1 AUC | y1 Brier skill | y3 AUC | y3 BSS |
| --- | --- | --- | --- | --- |
| Weather only (DC, FFMC, DMC, ISI, HTH, P30), t | 0.777 | 0.145 | 0.770 | 0.195 |
| Weather + peat (+ DC×peat), t | 0.780 | 0.152 | 0.771 | 0.197 |
| Weather + peat, perfect t+1 | 0.795 | 0.166 | 0.785 | 0.214 |
| Weather + peat + climatology | 0.835 | 0.223 | – | – |
| Persistence only (F1, F7, F30) | 0.882 | 0.341 | 0.878 | 0.401 |
| **Full (weather + peat + persistence), t** | **0.891** | **0.365** | **0.888** | **0.427** |
| Full, perfect t+1 | 0.897 | 0.383 | 0.894 | 0.445 |
| Full + climatology | 0.895 | 0.369 | – | – |

Additional checks:

- **Reverse direction** (train 2023, test 2019): weather + peat AUC 0.770, full + climatology AUC 0.890. The model is stable across years.
- **"New fire" cells** (no detection in the previous 7 days; 60 % of test cells, base rate 3.4 %):
  - weather + peat: AUC 0.705;
  - weather + peat + F30 + climatology: **AUC 0.828**;
  - climatology alone: AUC 0.731.

  These are the cells that matter most for prevention.
- **Season tracking:** daily island-wide expected vs observed number of burning cells, weather-only model, r = **0.85**.
- **Real GEOS-5 forecasts** (August–October 2023, model trained on MERRA-2 2019):

  | Lead | Model | AUC (GEOS-5 forecast) | AUC (same rows, MERRA-2 perfect t+1) |
  | --- | --- | --- | --- |
  | 1 | Weather + peat | 0.804 | 0.784 |
  | 1 | Full | 0.894 | 0.893 |
  | 3 | Weather + peat | 0.795 | – |
  | 3 | Full | 0.890 | – |

  Discrimination holds at lead 3, helped by the finer GEOS-5 grid. Calibration does not: weather-only mean P was 0.128 vs 0.200 observed, because of the GEOS-5/MERRA-2 bias in §3.2. **Train on GEOS-5 analyses and archived runs.**

**Reliability, full model, `y1`, test 2023:**

| Predicted bin | n | Mean predicted | Observed |
| --- | --- | --- | --- |
| 0–0.02 | 52,699 | 0.014 | 0.004 |
| 0.02–0.05 | 89,287 | 0.033 | 0.022 |
| 0.05–0.10 | 59,477 | 0.069 | 0.071 |
| 0.10–0.20 | 39,344 | 0.143 | 0.181 |
| 0.20–0.30 | 20,830 | 0.246 | 0.285 |
| 0.30–0.50 | 24,432 | 0.391 | 0.411 |
| 0.50–0.70 | 15,619 | 0.596 | 0.585 |
| 0.70–1.00 | 19,029 | 0.844 | 0.811 |

Calibration is good. There is slight over-forecasting below 5 %, and 2023 being a slightly less active year than 2019 explains part of it.

Caveats:

- Both seasons are drought years: positive IOD in 2019, El Niño in 2023.
- Persistence rewards predicting "keeps burning". That is right for operations, but for prevention the "new fire" subset is the fairer measure.
- MERRA-2 cells were nearest-neighbour mapped to 0.25°.
- The 2015 climatology was used as Fclim for both years. That is legitimate here, because it is out of sample for both.

### 4.4 Validation plan (to run when implementing)

1. **Training data.**
   - Use GEOS-5 analyses for 2019, June–November, so features match the live product.
   - For each lead L = 1..7, use the archived run issued on t+1−L.
   - Labels come from FIRMS VIIRS in DuckDB.
2. **Test.** Run the same pipeline on 2023.
   - Report AUC, Brier score and Brier skill against the test-year base rate, a reliability diagram with 8 bins, and the share of fires captured by the top 10 % of area.
   - Report each metric per lead, separately for peat and non-peat cells, and for the "new fire" subset.
3. **Baselines.** Climatology, persistence, the FDRS rule class, and DC alone. The full model must beat persistence on the new-fire subset to justify the weather inputs.
4. **False-alarm check.** Use the archive's non-drought years, **2024 and 2025** (already in DuckDB: 220k and 190k VIIRS detections). Check how much area lands in Tinggi or Ekstrem, and whether the model is still calibrated in wetter years (Fernandes 2017).
5. **Spatial robustness.** Leave-one-island-out (Sumatra / Kalimantan / Papua) or 2° spatial blocks to avoid leakage between neighbouring cells. Compare class frequencies with BMKG SPARTAN maps on a few dates.
6. **Monitor every season.** Store each day's issued P per cell (lead 1..3) in DuckDB, verify it against FIRMS after the fact, and publish a small reliability chart.

---

## 5. Pipeline sketch and code pointers (no code changed)

- **New module `pipeline/src/haze/danger.py`:**
  - `fetch_gfwed(run_date)`: list the newest `YYYYMMDD00/` folder and download its 8 files, using httpx with a range-request option. Subset to `SMOG_GRID`/`PLUME_GRID` bounds with `scipy.io.netcdf_file`.
  - `fwi_step(state, T, H, W, P)`: a numpy port of §2 with the Apache-2.0 xclim notice. Use it for the Open-Meteo fallback and in unit tests against NOR-X-424 values.
  - `features(con, day)`: F1, F7 and F30 from the `hotspots` table, using the same filters as `firms`/`events`, plus peat fraction rasterised once from `regions` `level='peat'` (WKB, shapely `contains_xy`) and cached as `.npz` in `CACHE_DIR`.
  - `predict()`: logistic coefficients from `pipeline/static/danger_model.json` (or similar).
- **Reuse:**
  - `smoke.Grid` and `PLUME_GRID`, which is 0.25° and already covers Indonesia.
  - `_fetch_points` and `fetch_wind`: add `temperature_2m` to the `hourly` list.
  - `needs_refresh`-style throttling: run once a day, after the GFWED run appears.
- **DuckDB tables** (new, following `db.py` style):
  - `fire_weather (day DATE, i INT, j INT, source VARCHAR, run DATE, dc, dmc, ffmc, isi, bui, fwi, hth)`;
  - `danger_forecast (issued DATE, day DATE, lead INT, i, j, p DOUBLE, class VARCHAR)`, for verification.
- **Output:** `danger/latest.json` in the same grid encoding as the smoke grids, with `{grid, days[], p[day][cell] as uint8 percent, class}`, plus per-cell tooltips (FFMC, DC and ISI with BMKG classes, HTH, peat %). MapLibre draws it as a raster or fill layer with a day slider, H+0..H+3 (to H+5 when GFWED is fresh).
- **Pilot scripts** (session scratchpad, for reference): `build.py` (cell-day table), `evalp.py`, `eval2.py`, `eval3.py`, `eval4.py`, and `sub.py` (GFWED subsetter). They need only numpy, pandas, scipy, duckdb and shapely.

---

## 6. Classes for the UI

**Primary layer: "Risiko kebakaran" for H+1…H+3.** It shows the calibrated model probability P that at least one hotspot appears in the 0.25° cell (about 28 km) on that day.

| Class | P (next day) | Colour (BMKG scheme) | Meaning for the public | Pilot 2023, `y1`: share of area / share of fires / observed P |
| --- | --- | --- | --- | --- |
| **Rendah** | < 5 % | biru | Fires unlikely | 0.44 / 0.04 / 0.015 |
| **Sedang** | 5–15 % | hijau | Some fires possible in dry spots; control burning | 0.26 / 0.15 / 0.097 |
| **Tinggi** | 15–40 % | kuning | Fires likely; **ban burning on peat**; patrol | 0.16 / 0.27 / 0.29 |
| **Ekstrem** | ≥ 40 % | merah | Fires very likely or ongoing; full ban; deploy | 0.14 / 0.54 / 0.65 |

How the cut-points were chosen:

- **5 %** is about 1/4 of the dry-season base rate (about 20 %).
- **15 %** is close to the base rate.
- **40 %** is about 2× the base rate. It is also the level that DC > 350 on peat reaches by itself (0.54–0.60 in the pilot).

The classes keep the FDRS logic of four classes. The top class sits at the empirical threshold where fires become the norm, and the High class implies "restrict peat burning", as in the de Groot (2007) DC table. For 3-day risk (`y3`), use the same cut-points. That gives 17 / 35 / 20 / 28 % of area and 1 / 9 / 21 / 68 % of fires.

Display rules:

- **Tooltip, scientific basis.** Show the BMKG/FDRS component classes using the official bounds in §1.2:
  - FFMC 72 / 77 / 82 for ignition;
  - DC 140 / 260 / 350 for peat and haze, with a note at **DC > 400**: "ambang kabut asap berat" (Field 2004);
  - ISI 1 / 3 / 5 for spread;
  - HTH in BMKG's day classes;
  - peat %.

  This shows why the cell is red: dry fuel, dry peat, or fire already nearby.
- **Naming.** BMKG labels its top class "sangat tinggi", and the FDRS paper uses "Extreme". Using **Ekstrem** is fine, but note in the legend that our classes are *probabilities from a statistical model*, not BMKG's official FDRS. That avoids confusion with the official warnings.
- **Disclaimer,** in BMKG's wording: "Peta ini menunjukkan potensi, BUKAN lokasi kebakaran." Also show the GFWED run date, and dim days beyond lead 3.
- **Fallback when the model is unavailable.** Show the FDRS rule class: the FFMC class, and on peat cells the maximum of the FFMC and DC classes. It is weaker (AUC 0.73), but it is the official scientific basis.

---

## 7. References (links checked 2026-10-17; DOIs resolved through Crossref)

**FDRS and indices**

- de Groot W.J., Field R.D., Brady M.A., Roswintiarti O., Mohamad M. (2007). Development of the Indonesian and Malaysian fire danger rating systems. *Mitig. Adapt. Strateg. Glob. Change* 12:165–180. https://doi.org/10.1007/s11027-006-9043-8. Full text: https://rfmrc-sea.org/wp-content/uploads/2015/01/Development-of-the-Indonesian-and-Malaysian-Fire-Danger-Rating-Systems.pdf (read; curl gets 406, but browser and WebFetch work).
- de Groot W.J., Wardati, Wang Y. (2005). Calibrating the Fine Fuel Moisture Code for grass ignition potential in Sumatra, Indonesia. *Int. J. Wildland Fire* 14:161–168. https://doi.org/10.1071/WF04054
- Field R.D., Wang Y., Roswintiarti O., Guswanto (2004). A drought-based predictor of recent haze events in western Indonesia. *Atmos. Environ.* 38:1869–1878. https://doi.org/10.1016/j.atmosenv.2004.01.011
- Dymond C.C., Field R.D., Roswintiarti O., Guswanto (2005). Using satellite fire detection to calibrate components of the Fire Weather Index System in Malaysia and Indonesia. *Environ. Manage.* 35:426–440. https://doi.org/10.1007/s00267-003-0241-9
- Field R., Dymond C., de Groot W., Lee B. Spatial distribution of fire season and ENSO effects on the island of Sumatra (AMS conference paper; DC ignition threshold of about 350, Medan, Palembang). https://ams.confex.com/ams/pdfpapers/25739.pdf
- BMKG SPARTAN fire danger rating: https://spartan.bmkg.go.id/ (legend in `/StaticData`). BMKG karhutla page: https://www.bmkg.go.id/cuaca/karhutla
- Van Wagner C.E. (1987). Development and structure of the Canadian Forest Fire Weather Index System. For. Tech. Rep. 35. https://cfs.nrcan.gc.ca/pubwarehouse/pdfs/19927.pdf (redirects to the NRCan repository).
- Wang Y., Anderson K.R., Suddaby R.M. (2015). Updated source code for calculating fire danger indices in the Canadian Forest Fire Weather Index System. Inf. Rep. NOR-X-424. https://publications.gc.ca/site/eng/9.805607/publication.html
- Wang X. et al. (2017). cffdrs: an R package for the Canadian Forest Fire Danger Rating System. *Ecol. Process.* 6. https://doi.org/10.1186/s13717-017-0070-z. CRAN (GPL-2): https://cran.r-project.org/package=cffdrs
- xclim (Apache-2.0), `xclim/indices/fire/_cffwis.py`: https://github.com/Ouranosinc/xclim and https://pypi.org/project/xclim/
- Keetch J.J., Byram G.M. (1968). A drought index for forest fire control. USDA Forest Service Res. Pap. SE-38. Not checked online here. It is the standard citation.

**GFWED and forecasts**

- Field R.D. et al. (2015). Development of a Global Fire Weather Database. *Nat. Hazards Earth Syst. Sci.* 15:1407–1423. https://doi.org/10.5194/nhess-15-1407-2015
- Field R.D. (2020). Evaluation of Global Fire Weather Database reanalysis and short-term forecast products. *NHESS* 20:1123–1147. https://doi.org/10.5194/nhess-20-1123-2020
- GFWED data: https://portal.nccs.nasa.gov/datashare/GlobalFWI/v2.0/ and info page https://data.giss.nasa.gov/impacts/gfwed/
- Di Giuseppe F. et al. (2016). The potential predictability of fire danger provided by numerical weather prediction. *J. Appl. Meteorol. Climatol.* 55:2469–2491. https://doi.org/10.1175/JAMC-D-15-0297.1
- Vitolo C. et al. (2020). ERA5-based global meteorological wildfire danger maps. *Sci. Data* 7. https://doi.org/10.1038/s41597-020-0554-z
- Shawki D. et al. (2017). Long-lead prediction of the 2015 fire and haze episode in Indonesia. *Geophys. Res. Lett.* 44:9996. https://doi.org/10.1002/2017GL073660
- Open-Meteo docs: https://open-meteo.com/en/docs, archive https://open-meteo.com/en/docs/historical-weather-api, pricing and quota https://open-meteo.com/en/pricing

**Fire occurrence and drought in Indonesia**

- Spessa A.C. et al. (2015). Seasonal forecasting of fire over Kalimantan, Indonesia. *NHESS* 15:429–442. https://doi.org/10.5194/nhess-15-429-2015
- Field R.D. et al. (2016). Indonesian fire activity and smoke pollution in 2015 show persistent nonlinear sensitivity to El Niño-induced drought. *PNAS* 113:9204–9209. https://doi.org/10.1073/pnas.1524888113 (open: https://pmc.ncbi.nlm.nih.gov/articles/PMC4995960)
- Field R.D., van der Werf G.R., Shen S.S.P. (2009). Human amplification of drought-induced biomass burning in Indonesia since 1960. *Nat. Geosci.* 2:185–188. https://doi.org/10.1038/ngeo443
- Fanin T., van der Werf G.R. (2017). Precipitation–fire linkages in Indonesia (1997–2015). *Biogeosciences* 14:3995–4008. https://doi.org/10.5194/bg-14-3995-2017
- Fernandes K. et al. (2017). Heightened fire probability in Indonesia in non-drought conditions: the effect of increasing temperatures. *Environ. Res. Lett.* 12:054002. https://doi.org/10.1088/1748-9326/aa6884
- Sloan S. et al. (2017). Fire activity in Borneo driven by industrial land conversion and drought during El Niño periods, 1982–2010. *Glob. Environ. Change* 47:95–109. https://doi.org/10.1016/j.gloenvcha.2017.10.001
- Cattau M.E. et al. (2016). Sources of anthropogenic fire ignitions on the peat-swamp landscape in Kalimantan, Indonesia. *Glob. Environ. Change* 39:205–219. https://doi.org/10.1016/j.gloenvcha.2016.05.005
- Nikonovas T., Spessa A., Doerr S.H., Clay G.D., Mezbahuddin S. (2020). Near-complete loss of fire-resistant primary tropical forest cover in Sumatra and Kalimantan. *Commun. Earth Environ.* 1. https://doi.org/10.1038/s43247-020-00069-4
- Nurdiati S. et al. (2021). Spatial and temporal analysis of El Niño impact on land and forest fire in Kalimantan and Sumatra. *Agromet* 35:1–10. https://doi.org/10.29244/j.agromet.35.1.1-10
- Nurdiati S. et al. (2021, published in vol. 8, 2022). Modelling and analysis impact of El Niño and IOD to land and forest fire using polynomial and generalized logistic function: cases study in South Sumatra and Kalimantan, Indonesia. *Model. Earth Syst. Environ.* 8:3341–3356. https://doi.org/10.1007/s40808-021-01303-4
- Wooster M.J., Perry G.L.W., Zoumas A. (2012). Fire, drought and El Niño relationships on Borneo (Southeast Asia) in the pre-MODIS era (1980–2000). *Biogeosciences* 9:317–340. https://doi.org/10.5194/bg-9-317-2012

**Peat hydrology**

- Taufik M., Setiawan B.I., van Lanen H.A.J. (2015). Modification of a fire drought index for tropical wetland ecosystems by including water table depth. *Agric. For. Meteorol.* 203:1–10. https://doi.org/10.1016/j.agrformet.2014.12.006
- Taufik M. et al. (2017). Amplification of wildfire area burnt by hydrological drought in the humid tropics. *Nat. Clim. Change* 7:428–431. https://doi.org/10.1038/nclimate3280
- Taufik M. et al. (2019). Exploration of the importance of physical properties of Indonesian peatlands to assess critical groundwater table depths. *Geoderma* 347:160–169. https://doi.org/10.1016/j.geoderma.2019.04.001
- Wösten J.H.M., Clymans E., Page S.E., Rieley J.O., Limin S.H. (2008). Peat–water interrelationships in a tropical peatland ecosystem in Southeast Asia. *Catena* 73:212–224. https://doi.org/10.1016/j.catena.2007.07.010
- Agdialta et al. (2021). Pemantauan tingkat bahaya kebakaran hutan dan lahan dengan indeks kekeringan Keetch-Byram Drought Index. *J. Penelit. Kehutan. Sumatrana* 2:11–24. https://doi.org/10.20886/jpks.2021.2.1.11-24
