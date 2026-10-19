# Audit: air-quality and smoke numbers (CAMS bias correction, uncertainty, attribution)

Audit note, 17 Oct 2026 (data 13:00–19:00 UTC). It checks the numbers behind the PM2.5 map, the
city outlook and the cross-border panel: `stations.correction_field`, the 48 h fade in
`smoke.build`, `smoke.city_outlook` and `smoke.transboundary`. No source code was changed.

Scripts and raw outputs are in
`scratch/audit/`
(`scripts/`, `out_*.txt`, polled JSON under `raw/`). Section 6 says how to rerun them.

## 0. Summary

| Question | Answer (numbers from §2) |
| --- | --- |
| Does the station correction help? | **Yes, clearly.** Leave-one-station-out (LOO), 111 stations: median absolute log error (MdAE) falls from **1.05 to 0.61** (a typical miss of ×2.9 becomes ×1.8). The share within a factor of 2 (FAC2) rises from **29% to 56%**. Bootstrap 95% CI of the MdAE gain is −0.61 to −0.24. In Kalimantan, FAC2 goes from 29% to 71%. |
| Are 150 / 300 km sensible? | **Yes.** The log-ratio semivariogram rises to about half the total variance by 50–150 km and stays below it out to ~300 km; beyond 500 km stations carry no information. With every station within 100 km removed, the correction still beats raw CAMS (0.70 vs 1.05). Tuning to 200/500 km gains only 0.01–0.03 MdAE, which is not significant. Keep 150/300 (or 200/400). |
| Is the 0.5–8× clip sensible? | **The 0.5× floor is too high.** CAMS reads **3.6–5.3× above** the Java stations (r(log) ≈ 0.05), and 31–37 of 111 stations need a factor below 0.5. With the floor at 0.1, Java bias drops from +0.97 to +0.18 (log, hourly basis; +0.62 to +0.14 on the 24 h basis) and Java FAC2 rises from 36% to 47%. Use **0.1–10**. The 8× ceiling is touched by 2–5 stations, three of which fail QC. |
| Better method? | Ordinary/simple **kriging of the log ratio** (exponential covariance, L = 300 km, 30% nugget) is the best on every test: LOO MdAE 0.46–0.55 vs 0.56–0.61, and Malaysia out-of-network FAC2 94% vs 72%. The gain over IDW is not significant on one night of data (CI −0.20 to +0.05), so it is an optional upgrade. A regional (island) median ratio alone is worse than IDW (0.61–0.70). |
| Is ISPU `a_pm25` hourly? | **No. It behaves as a 24 h running mean, updated hourly.** The median hour-to-hour change is 1.0–1.2% (NEA's true hourly PM2.5: 6.7%). `t_pm25` equals the 24 h-breakpoint ISPU of `a_pm25` for 93% of stations. Comparing against a CAMS **trailing 24 h mean** raises r(log) from 0.23 to 0.46 and lowers raw MdAE from 1.05 to 0.85. Malaysia's API is also a rolling 24 h mean. |
| `waktu` time base | Local time of the province (WIB/WITA/WIT), stamped at the **end** of the hour: the 01:00 WIB value was online by 01:25 WIB. The `time_z` field is wrong for 4 Kaltim/Kaltara stations; using it would put 2 readings in the future. The province rule in `stations.py` is correct. |
| The 48 h fade | **It creates false trends.** At Singapore, the station/CAMS ratio measured at T still corrects CAMS at T+24–36 h (MdAE 0.19–0.21 vs 0.82 raw). Fading to raw CAMS by 48 h makes the published day-3 mean **2.0× day 1 in Java** and **0.48× day 1 in haze cities** (Pekanbaru 229 → 31 µg/m³). In 33 of 73 cities the "72 h peak" falls after +48 h, i.e. in uncorrected CAMS. |
| Transboundary attribution | The modelled smoke reaching Singapore, Johor Bahru and KL over 24 h averages **0.0–0.9 µg/m³**, against **76–110 µg/m³** measured: about 1% of the observed excess. Near the fires it is 14–45%. Percentages on a 1% signal should not be shown. The current "weak signal" cut (24 h sum < 5, i.e. mean < 0.6) lets Singapore through. |

**Measured skill to state publicly** (corrected field, at a station location, LOO, 24 h basis):
- typical error ×1.7, and 6 in 10 within a factor of 2;
- within 50 km of a station: ×1.6 typical, 80% within ×2.7;
- more than 150 km from a station: ×3 typical, i.e. no better than raw CAMS.

## 1. Data and time base

### 1.1 Sample

| Source | Used for | n |
| --- | --- | --- |
| `obs_aq` (read-only DB copy): ISPU 13–17 UTC, NEA 16–17 UTC, DOE 24 h | CV targets / Malaysia check | 106 ISPU + 5 NEA stations with PM2.5; 36 DOE |
| ISPU apimobile, polled 18:25–20:10 UTC (one GET per 25 min) | Adds the 18 UTC hour and the extra fields (`t_pm25`, `c_pm25`, `time_z`, `a_pm10`, `val`) | 118 stations |
| NEA `pm25?date=` for 15–17 Oct | 72 h of hourly Singapore PM2.5 (persistence test) | 5 regions × 72 h |
| CAMS cache `smoke_raw.npz` (fetched 17:50 UTC) | Raw model, 0.75° grid, 16 Oct 00 UTC – 20 Oct 23 UTC | 120 h |

Snapshot time `now` = 18:00 UTC (01:00 WIB). As in `correction_field`, each station gets the
median over its readings in [now − 6 h, now + 1 h]. By island: Java 36, Kalimantan 28,
Sumatra 31, other 16 (Sulawesi, NT, Bali, Maluku, Papua, Singapore).

This is **one night of one severe episode**. Every result below should be re-run on a
multi-week archive once `obs_aq` has one (§2.10).

### 1.2 ISPU `a_pm25` is a 24 h running mean

Evidence:
1. **Smoothness.** The median |Δln| between consecutive hours is 0.010 (16→17 UTC, n = 66) and
   0.012 (17→18 UTC, n = 67); the 90th percentile is 0.05. Singapore's hourly `pm25_one_hourly`
   over the same 72 h has a median |Δln| of **0.067**, six times larger. DOE's API (a documented
   rolling 24 h mean) changes 0.006 per hour.
2. **Index identity.** `t_pm25 − ISPU₂₄(a_pm25)` has a median of 0.8, and |diff| ≤ 2 for 93% of
   105 stations. ISPU₂₄ uses the P.14/2020 breakpoints 15.5 / 55.4 / 150.4 / 250.4 / 500 µg/m³,
   which are 24 h breakpoints. The regulation says ISPU is "computed every hour from 24-hour
   monitoring data" (Permen LHK P.14/2020, Pasal 6, via the copy on peraturan.go.id; the PDF
   could not be fetched from here, so this wording is second-hand).
3. **Model fit.** Station/CAMS agreement improves when CAMS is averaged over the trailing 24 h:

| CAMS sampled as | r(log) all | sd of ln(obs/CAMS) | Kalimantan r | Sumatra r | Java r | Haze stations (> 100): CAMS/obs |
| --- | --- | --- | --- | --- | --- | --- |
| hour of reading (current code) | 0.23 | 1.43 | 0.82 | 0.44 | 0.09 | **0.27** (IQR 0.16–0.42) |
| trailing 24 h mean | **0.46** | **1.23** | 0.84 | 0.59 | 0.03 | **0.35** (IQR 0.28–0.54) |

Consequences:
- Dividing a 24 h mean by an hourly night-time CAMS value builds CAMS's diurnal phase into
  the factor. At Palangka Raya the factor is 3.96 on the hourly basis but **2.34** on the 24 h
  basis.
- Multiplying an hourly CAMS night peak by the hourly-basis factor gives the published
  **3,677 µg/m³ "72 h peak"** for Palangka Raya at +15 h (3,430 in the 3-hourly frames).
- `docs/models.md` ("CAMS reads a median 0.26×") and the UI callout use the hourly basis.
  Against a matching 24 h mean the haze ratio is **0.35×**.
- The UI says ISPU data are hourly ("Data per jam dari stasiun ISPU…"). They are 24 h means
  refreshed hourly, as is DOE's API. Only NEA's `pm25_one_hourly` is a true 1 h value.

### 1.3 `waktu` time base

- `waktu` is local time, and `time_offset` is the offset from WIB (0/1/2).
- The ISPU reading stamped 01:00 WIB (18:00 UTC) was already online at 18:25 UTC. It was still
  the latest at 18:53, so the hourly update lands later than :53. The stamp is therefore the
  **end** of the averaging period.
- For four stations the `time_z` field disagrees with the province: BALIKPAPAN, KUTAIBARAT,
  BONTANG (Kaltim) and TARAKAN (Kaltara) are labelled WIB. Reading `waktu` with `time_z` puts
  2 of them 7 minutes in the future, so the province rule in `_utc_offset` is right. BONTANG
  and TARAKAN then lag by 1.9 h, i.e. one hour late, which is plausible.
- Add a guard that drops any reading whose `ts_utc` is later than the fetch time.

### 1.4 QC findings (ISPU)

| Issue | Stations (17 Oct, 01:00 WIB) | Recommendation |
| --- | --- | --- |
| `c_pm25` null: PM2.5 has no category and is not used in the official index (`val`/`param` come from another pollutant), although it would dominate it | KATINGAN 1,037 µg/m³ (val 30, CO), KAMPAR 494 (val 59, NO₂), ACEH_SELATAN 193 (val 21, CO) | Drop. These drive factor-8 cells. |
| PM2.5 far above PM10 | TANJUNGJABUNGTIMUR 203 vs PM10 21 | Drop when `a_pm25 > 1.5·a_pm10 + 5` |
| `a_pm25` = 0 but `t_pm25` 111–126 (≈ 66–80 µg/m³) | DKI1/2/4/5 (Jakarta provincial network, `auto_validation=0`, one hour older) | Already dropped (≤ 1). They contradict KLH's own JAKARTA station (21 µg/m³). |
| Implausibly low night values in Java | JEPARA 2.4, SRAGEN 3.1, JOMBANG 5.2, SOLO 5.4 against CAMS 43–149 | Watch. Java station data are themselves inconsistent, so the Java correction is uncertain in both directions. |
| `auto_validation=1` (unvalidated) | 111 of 118 stations | State it in the UI (§3.3). |

Strict QC (dropping the first two rows) changes the CV only slightly (MdAE 0.563 → 0.559 on
the 24 h basis), because there are only 4 such stations. It does remove the most extreme
factors.

### 1.5 Malaysia DOE

- The API is a rolling 24 h mean ([SAYS, 28 Aug 2026](https://says.com/my/news/aqi-api-explaining-malaysias-air-quality-confusion)). It changes 0.6% per hour.
- The inversion table `DOE_PM25` has (50.4 µg/m³ → API 100). That does not match the US-EPA-style
  table it otherwise follows (35.4 → 100). Values above API 150, the haze range, are unaffected.
  The official DOE breakpoints were not found online; verify them before relying on API 50–100.
- DOE stations are excluded from the correction (`pm25_estimated`), which is right. That makes
  them a useful independent check (§2.8).

## 2. Cross-validation of the correction

### 2.1 Method

For each station *i*:
1. Build the factor field from all other stations, exactly as `correction_field` does: IDW with
   power 2 and a 10 km floor, full weight to 150 km and none beyond 300 km, then clipped.
2. Evaluate it on the four 0.75° cells around *i*, interpolate bilinearly, and multiply by CAMS
   at *i*.
3. Compare with the observation.

Metrics: MdAE = median |ln(pred/obs)| (0.69 = factor 2); bias = median ln(pred/obs);
FAC2 = share with |ln| ≤ ln 2. "Leave-X-km-out" also removes every station within X km of *i*,
to imitate a city with no station of its own. Scripts: `cv.py`, `cv2.py`, `boot.py`.

### 2.2 Overall

| Method | MdAE (hourly basis) | FAC2 | MdAE (24 h basis) | FAC2 | bias (24 h) |
| --- | --- | --- | --- | --- | --- |
| Raw CAMS | 1.048 | 0.29 | 0.848 | 0.39 | −0.19 |
| **Current IDW 150/300, clip 0.5–8** | **0.610** | **0.56** | **0.563** | **0.59** | +0.03 |
| IDW 150/300, clip 0.1–10 | 0.601 | 0.59 | 0.530 | 0.61 | −0.02 |
| Global median ratio | 0.953 | 0.32 | 0.849 | 0.44 | 0.00 |
| Island median ratio | 0.703 | 0.49 | 0.613 | 0.56 | −0.05 |
| Kriging L = 200 km, nugget 0.3, mean = median | 0.499 | 0.63 | 0.487 | 0.62 | 0.00 |
| Kriging L = 300 km, nugget 0.3, mean = 0 | 0.548 | 0.61 | **0.459** | **0.63** | — |

Bootstrap (2,000 resamples of stations, paired), MdAE difference with 95% CI:
- current − raw: hourly −0.44 [−0.61, −0.24]; 24 h basis −0.30 [−0.49, −0.17];
- clip 0.1–10 − current: −0.01 [−0.11, +0.09];
- kriging L300 − current: −0.08 [−0.20, +0.05].

### 2.3 By region (LOO, 24 h basis; the hourly basis is in `out_base_code_h0.txt`)

| Method | Java MdAE / bias / FAC2 | Kalimantan | Sumatra | Other |
| --- | --- | --- | --- | --- |
| Raw CAMS | 1.29 / **+1.29** / 0.36 | 0.87 / **−0.82** / 0.36 | 0.78 / −0.72 / 0.39 | 0.76 / −0.32 / 0.50 |
| Current IDW (clip 0.5–8) | 0.75 / +0.62 / 0.44 | **0.36** / −0.05 / **0.71** | 0.46 / −0.06 / 0.64 | 0.61 / 0.00 / 0.56 |
| IDW clip 0.1–10 | **0.67 / +0.14** / 0.53 | 0.36 / −0.05 / 0.71 | 0.46 / −0.06 / 0.64 | 0.61 / 0.00 / 0.56 |
| Island median | 0.82 / 0.00 / 0.39 | 0.41 / 0.00 / 0.79 | 0.61 / −0.11 / 0.55 | 0.60 / 0.00 / 0.56 |
| Kriging L200 (→ median) | 0.74 / +0.20 / 0.44 | **0.34** / −0.04 / **0.82** | **0.44** / −0.08 / **0.68** | 0.63 / 0.00 / 0.56 |

Hourly basis, current IDW: Kalimantan MdAE 0.48, FAC2 0.71 (raw 0.98 / 0.29); Sumatra 0.60 /
0.64 (raw 1.03 / 0.32); Java 1.02 / 0.36 (raw 1.66 / 0.25).

**CAMS has opposite biases by island.** It reads 2.1–2.7× too low in the Kalimantan and Sumatra
haze and 3.6–5.3× too high over Java at night. In Kalimantan+Sumatra, ln(obs) = 0.88 +
**0.94** ln(CAMS₂₄) (n = 59), so the bias there is close to a pure multiplier. In Java the slope
is **0.05**: CAMS has no spatial skill there.

### 2.4 By concentration (LOO, hourly basis, current code; observed ISPU bands)

| Observed band (µg/m³) | n | Raw MdAE / bias | Current MdAE / bias / FAC2 | Kriging L200 MdAE / FAC2 |
| --- | --- | --- | --- | --- |
| ≤ 15.5 (baik) | 24 | 1.86 / +1.86 | 1.47 / +1.47 / 0.21 | 1.09 / 0.33 |
| 15.5–55.4 (sedang) | 38 | 0.75 / +0.47 | 0.44 / +0.09 / 0.63 | 0.46 / 0.74 |
| 55.4–150.4 (tidak sehat) | 23 | 0.76 / −0.76 | 0.50 / +0.02 / 0.78 | 0.36 / 0.78 |
| 150.4–250.4 (sangat tidak sehat) | 14 | 1.28 / −1.28 | 0.72 / −0.72 / 0.50 | 0.63 / 0.57 |
| > 250.4 (berbahaya) | 12 | 1.75 / −1.75 | 0.57 / −0.57 / 0.67 | 0.40 / 0.67 |

- Binning by the observed value builds in regression to the mean, so the low band looks
  over-predicted and the high bands under-predicted.
- Binned by CAMS value (no such artefact): above 100 µg/m³ CAMS, current MdAE is 0.57 and
  clip-0.1 IDW is **0.41**. Below 25, it is 0.56.
- Even after correction, the "sangat tidak sehat / berbahaya" stations are under-predicted by
  ×1.8–2. **The corrected map still understates the worst haze.**

### 2.5 Radii: distance tests and semivariogram

Leave-X-km-out, MdAE (24 h basis; hourly basis in parentheses):

| Removed within | Median distance to nearest station | Raw | Current IDW | Kriging L200 → median | Island median |
| --- | --- | --- | --- | --- | --- |
| 0 km (LOO) | 38 km | 0.85 (1.05) | 0.56 (0.61) | 0.49 (0.50) | 0.61 (0.70) |
| 25 km | 52 km | 0.85 (1.05) | 0.57 (0.61) | 0.49 (0.57) | 0.63 (0.72) |
| 50 km | 70 km | 0.85 (1.05) | 0.59 (0.61) | 0.55 (0.57) | 0.66 (0.76) |
| 100 km | 121 km | 0.85 (1.05) | 0.61 (0.70) | 0.59 (0.67) | 0.65 (0.73) |
| 200 km | 216 km | 0.85 (1.05) | 0.81 (0.90) | 0.65 (0.88) | 0.71 (0.83) |

Semivariogram of ln(obs/CAMS₂₄), total variance 1.50:

| Separation (km) | 0–25 | 25–50 | 50–100 | 100–150 | 150–200 | 200–300 | 300–500 | 500–1000 | > 1000 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| γ | 0.22 | 0.33 | 0.80 | 0.83 | 0.47 | 0.69 | 0.90 | 1.70 | 1.72 |

Reading:
- There is a nugget of about 0.2. That is station-scale noise (siting, calibration), roughly a
  factor ±1.6 per station.
- A local component decorrelates by about 50–100 km.
- A regional component (island-wide haze) keeps γ below the variance out to ~300–500 km.
  Beyond 500 km, γ exceeds the variance, so the stations carry no information (the
  Java-vs-Kalimantan contrast).
- Error against distance to the nearest training station, current IDW, 24 h basis: 0–25 km
  0.43, 25–50 km 0.64, 50–100 km 0.66, 100–150 km 0.54, 150–300 km 1.29. Raw CAMS is
  0.72–1.19 at the same distances.
- **Conclusion: 150 km full and 300 km zero match the data.** Going further (200/500) wins
  0.01–0.03 MdAE (not significant) and helps Malaysia (§2.8). 300–400 km is a defensible zero
  radius; do not go past 500.

### 2.6 Clip range

- On the hourly basis, 37 of 111 stations have obs/CAMS < 0.5 (8 below 0.1). Five have > 8, of
  which KATINGAN, KAMPAR and ACEH_SELATAN fail QC (§1.4).
- On the 24 h basis: 31 below 0.5, 4 below 0.1, and 2 above 8.
- Lowering the floor from 0.5 to 0.1 matters only where CAMS is too high (Java, and Sulawesi and
  NT at low concentrations). There it removes most of the bias (+0.62 → +0.14) and cuts the CAMS
  > 100 µg/m³ error (0.57 → 0.41).
- The ceiling makes no measurable difference between 8 and 20 once QC is applied.
- **Recommend `CORR_CLIP = (0.1, 10.0)`.**

### 2.7 Tuning grid (`out_tune_code_h*.txt`)

160 IDW configurations: full ∈ {0, 50, 100, 150, 200} km, zero ∈ {100, 200, 300, 500} km,
four clip ranges, power ∈ {1, 2}. 36 kriging configurations: L ∈ {50 … 500} km,
nugget ∈ {0.1, 0.3, 0.5}, mean ∈ {median, 0}. Each was scored by LOO and by leave-50-km-out.

- **IDW:**
  - Power 2 always beats power 1.
  - The best settings have clip 0.1 and zero radius 300–500 km. On the 24 h basis the best is
    200/500, clip 0.1–10: LOO 0.530, leave-50 km 0.540. The current setting scores 0.563 / 0.591.
  - The spread across the top 20 configurations is ±0.03, well inside the bootstrap CI.
- **Kriging:**
  - L = 300–500 km with a 30% nugget is best: LOO 0.454–0.470, leave-50 km 0.475–0.498.
  - L ≤ 100 km is worse than IDW, and L = 50 km is the worst of all.
  - Mean = 0 (decay to raw CAMS) or mean = network median makes little difference inside the
    network. Outside it, the median mean helps Malaysia (§2.8) and hurts Java (CAMS too high).
- **Rejected:** a single global median ratio (no better than raw); island medians on their own
  (worse than IDW for Sumatra, where the ratio varies from 0.08 in Aceh to 0.9 in South Sumatra).

### 2.8 Out-of-network check: Singapore and Malaysia (`crossborder.py`)

The field was built from the 106 ISPU stations only and scored at NEA (5) and DOE (36; PM2.5
inverted from the 24 h API, so ±20% at least). The nearest ISPU station is 100–475 km away.

| Field | NEA MdAE / FAC2 (hourly basis) | DOE MdAE / FAC2 (hourly) | NEA (24 h basis) | DOE (24 h basis) |
| --- | --- | --- | --- | --- |
| Raw CAMS | 0.84 / 0.20 (CAMS = 0.43× obs) | 1.04 / 0.19 (0.35×) | 0.68 / 0.80 | 0.84 / 0.33 |
| Current IDW | **0.12** / 1.00 | 0.48 / 0.64 | 0.23 / 1.00 | 0.40 / 0.72 |
| IDW 200/500, clip 0.1–10 | 0.20 / 1.00 | 0.43 / 0.64 | 0.11 / 1.00 | 0.35 / 0.78 |
| Kriging L300, mean 0 | 0.25 / 0.80 | 0.44 / 0.78 | 0.06 / 1.00 | 0.39 / **0.94** |
| Kriging L300, mean = median | 0.28 / 0.80 | **0.40 / 0.83** | **0.04** / 1.00 | 0.39 / **0.97** |

Every variant still leaves the Malaysian stations about 1.5× too low (bias −0.33 to −0.48).
Sarawak and Sabah stations more than 300 km from any ISPU site stay at raw CAMS, about 2× low.
In haze, "no correction" far from stations is a biased default. That argues for decaying to a
regional ratio rather than to 1 (§5, item 2).

### 2.9 Time persistence and the 48 h fade (`temporal.py`, `fade.py`)

**Persistence.** The ratio from the last 6 h at time T was applied at T+k, for every hour
of the 42 h overlap between NEA's history and CAMS. The station corrects itself, so this
measures time decay only:

| Lead k (h) | 0 | 1 | 3 | 6 | 12 | 18 | 24 | 36 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Singapore raw MdAE | 0.71 | 0.72 | 0.71 | 0.72 | 0.70 | 0.75 | 0.84 | 0.82 |
| Singapore corrected MdAE | 0.11 | 0.14 | 0.20 | 0.24 | 0.22 | 0.20 | **0.19** | **0.21** |
| Singapore corrected FAC2 | 0.99 | 0.98 | 0.96 | 0.95 | 0.96 | 0.97 | 0.98 | 1.00 (n = 25) |
| Malaysia DOE corrected MdAE (raw 0.74–0.99) | 0.10 | 0.15 | 0.26 | 0.35 | 0.33 | 0.23 | — | — |

In this episode the CAMS bias persists for at least 1.5 days. A linear fade to 1 by 48 h
throws away a correction that is still worth a factor of ~2 at +24 h.

The Singapore diurnal cycle: obs/CAMS is 1.6 at night and 2.5–3.1 in late afternoon. There is a
CAMS jump at 12 UTC (49.8 → 72.0 µg/m³), which is a forecast-run splice in Open-Meteo's
`past_days` series.

**Fade artefacts in the published outlook** (`smoke/cities.json` and `smog.json`, run of
17 Oct 18:57 UTC, 73 cities):
- In **33 of 73** cities the 72 h maximum is after +48 h, where the field is raw CAMS. In 8
  cities the ISPU category of the "72 h peak" differs from the 0–48 h peak.
- In the 35 cities where the correction lowers CAMS (Java; factor at the 0.5 floor), the
  **day-3 mean is 2.0× the day-1 mean**. Jakarta goes 52 → 77 → 103 µg/m³ and shows "Sangat
  tidak sehat" for the 72 h peak at +52 h, though no station or fire signal supports that.
- In the 23 cities where it raises CAMS (haze), **day 3 is 0.48× day 1**: Pekanbaru 229 → 83 →
  31, Padang 110 → 42 → 18, Singapore 76 → 53 → 40. The table reads as "the haze clears by
  Monday", but that comes from the fade, not from the weather.

### 2.10 Limits of this validation

- One night (18 UTC, 01:00 WIB), one episode, 111 stations. A second snapshot at **19 UTC**
  (new ISPU hour; median hour-to-hour change again 1.2%) reproduces the first within ±0.03:
  - hourly basis: raw 1.04, current 0.58, kriging L200 0.48 (FAC2 0.28 / 0.56 / 0.63);
  - 24 h basis: raw 0.85, current 0.56, IDW clip 0.1 0.53, kriging 0.51.

  The two snapshots share most of their data, so this shows stability, not independence.
  Spatial CV at one time says nothing about forecast skill beyond what §2.9 shows, and
  Singapore is a single receptor.
- ISPU values are 24 h means, so the hourly corrected field cannot be validated against ISPU,
  only against NEA.
- CAMS hours before the fetch are earlier forecasts, not analyses.
- Stations cluster (IKN ×5, Jakarta, Riau, Palembang). LOO is optimistic for those, which is why
  the leave-X-km-out results are given.
- **Next step:** run `cv2.py` daily on the growing `obs_aq` archive, and log
  `cv_mdae`/`cv_fac2` in the run record next to `skill_vs_cams`.

## 3. Literature

### 3.1 Models against measured haze PM2.5 in Indonesia

| Study | Finding | Bearing on haze |
| --- | --- | --- |
| [Grosvenor et al. 2024, *Commun. Earth Environ.* 5:649](https://doi.org/10.1038/s43247-024-01813-w) ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11531407/)) | 10 PurpleAir PA-II sensors in Palangka Raya, 2019. Gravimetric adjustment factor 0.49, plus 0.67x − 225 above 1,000 µg/m³. Readings at RH > 75% (16% of data) flagged as more uncertain. Against daily means, **CAMS NRT** r² = 0.70, **66% low on days > 100 µg/m³** and 45% low on other days. **EAC4 reanalysis** r² = 0.80, 35% high above 100 µg/m³. The city AQMS (Trusur, Jekan Raya, i.e. our ISPU `PALANGKARAYA`) read consistently higher than the co-located sensor and was calibrated only after the season. | Matches our 0.35× (24 h basis) at haze stations. Supports a multiplicative correction. The station we trust most in Kalimantan may itself read high. |
| [Kiely et al. 2019, *ACP* 19:11105](https://doi.org/10.5194/acp-19-11105-2019) | WRF-Chem constrained by PM measurements: Sumatra+Borneo fire PM2.5 in Sep–Oct 2015 was 7.33 Tg, **3.5× FINNv1.5** and 1.8× GFED4s-type estimates (peat emission factors). With FINN, PM fractional bias was about −0.72. | Inventory-driven models (GFAS in CAMS, our puff model) run low by about 2–3.5× in peat haze. |
| [Kiely et al. 2020, *ERL* 15:094054](https://doi.org/10.1088/1748-9326/ab9a6c) | 2004–2015 fire PM emissions; 9.4 Tg in 2015. Peat is 45% of emissions (68% in 2015). The model reproduces a Malaysia–Indonesia PM network with these emissions. | Absolute magnitudes are achievable only with peat-aware emissions. |
| [Crippa et al. 2016, *Sci. Rep.* 6:37074](https://doi.org/10.1038/srep37074) | WRF-Chem with FINN, 2015. Singapore PM2.5 observed 52 vs modelled 45 µg/m³ (NMBF −0.15, r = 0.45 hourly, 0.55 daily). Pekanbaru PM10 NMBF −0.24 (r = 0.57 / 0.72). Larger AOD bias (−0.54 to −0.78). 69 M people exposed to unhealthy air. | Even a tuned regional model gets r ≈ 0.5 hourly at a receptor. Hourly city numbers 2–3 days out cannot be precise. |
| [Koplitz et al. 2016, *ERL* 11:094023](https://doi.org/10.1088/1748-9326/11/9/094023) | GEOS-Chem adjoint sensitivities × GFAS. South Sumatra dominated 2015 regional exposure. Central Kalimantan emitted as much but caused about 1/3 of the exposure. About 100,300 excess deaths. | Basis for the attribution sanity check. It is a seasonal, multi-day result, not a 24 h one. |
| [Reddington et al. 2014, *ERL* 9:094006](https://doi.org/10.1088/1748-9326/9/9/094006) | Fire share of Singapore's PM2.5 enhancement: southern Sumatra 42–62%, central Sumatra 21–35%, Kalimantan 14–15% (2004–2009). | Same. |
| [Tan, Latif & Ashfold 2023, *AAQR* 23:220444](https://doi.org/10.4209/aaqr.220444) (abstract only) | CAMS PM2.5 against Malaysian hourly stations 2018–2020: CSI 31%, R² 0.36, lower than in other countries. It captured the 2019 regional haze increase better than local variability. The authors recommend bias correction. | Matches the Malaysia result in §2.8. |

### 3.2 Bias-correcting model PM2.5 with sparse stations

- **Log-space multiplicative correction, decaying away from stations.** This is the
  standard first step: the bias is multiplicative and the errors are log-normal. Our slope of
  0.94 in the haze islands confirms it. See also [data-air-quality.md](data-air-quality.md) §4.
- **Residual kriging / Gaussian-process fusion of model and monitors.** This is the usual next
  step (model-plus-monitor fusion with kriged residuals; e.g. the CMAQ+AOD+monitor fusion cited
  in data-air-quality.md, CV R² ≈ 0.7). Here it is the best of the methods tried (§2.2), with a
  fitted range of 200–500 km and a nugget of about 0.3.
- **Machine-learning correction of CAMS forecasts.** [Wu, Li & Bai 2020, *Remote Sens.*
  12:3813](https://doi.org/10.3390/rs12223813) found large, non-stationary CAMS biases in China
  and the US, removed by random forests in CV (abstract only; we could not fetch the full
  text). This needs long training archives we do not have. Revisit after one season of
  `obs_aq`.
- **In SE Asia,** we found no published operational station-correction of CAMS for Indonesia.
  The Malaysian study recommends one. Southeast Asia is sparse, so every method relies on
  falling back to the model away from stations. Our Malaysia result shows that falling back to
  raw CAMS is biased low during haze.

### 3.3 ISPU reliability, and what uncertainty to state

- **Instrument class.** ISPU stations are continuous AQMS, many supplied by Trusur. The method
  per station is not published.
  - Reference monitors are held to **±10% bias and a 10% CV** (US EPA, 40 CFR 58 App. A
    §2.3.1.1, [text](https://www.law.cornell.edu/cfr/text/40/appendix-A_to_part_58)).
  - Even certified continuous FEMs read **~20% high, and more at smoke-affected sites**
    ([EPA 2024 T640 update](https://www.epa.gov/system/files/documents/2024-05/2_supplemental-info_t640-data-update_final-05-13-2024.pdf)).
- **Validation.** 111 of 118 stations report `auto_validation=1`, i.e. automatic, unreviewed data.
- **Peat-smoke specifics.** Grosvenor 2024 found the Palangka Raya AQMS reading higher than the
  gravimetrically adjusted sensors, and it had been calibrated only after the 2019 season.
  Peat-smoke particles are humid and hygroscopic; RH > 75% was 16% of measurements.
- **Network consistency.** At 01:00 WIB, the Jakarta provincial monitors and KLH's JAKARTA
  station disagree by 3–4×. Several Java stations read 2–5 µg/m³ at night.
- **What to state:**
  - ISPU readings are 24 h averages refreshed hourly, unvalidated.
  - Under normal conditions they are probably within about **±20%**. In very dense peat haze
    and high humidity the error can be **±30–50%, more often too high than too low**.
  - Treat values above ~1,000 µg/m³ as "> 1,000" rather than precise numbers.

## 4. Communicating uncertainty

### 4.1 How others present forecasts

| Provider | What a forecast looks like |
| --- | --- |
| **AirNow (US EPA)** | Forecasts are made by state and local agency forecasters and are "predictions of the observed daily AQI". For PM2.5 the daily AQI "is simply the 24-hour average"; the real-time value uses NowCast ([AirNow API, AQ 101](https://docs.airnowapi.org/aq101)). The forecast is shown as the **category** for today and tomorrow. HMS satellite smoke plumes are shown separately from monitor AQI ([Fire and Smoke Map](https://www.airnow.gov/fasm-v4/about/); its [disclaimer](https://www.airnow.gov/fasm-v4/disclaimer) calls the plume data general guidance). |
| **Singapore NEA** | The forecast is a **range of categories** for the next 24 h, e.g. "The 24-hr PSI … is forecast to be in the **higher end of the Moderate to the middle of the Unhealthy range**". The guidance reads: "Refer to the 1-hr PM2.5 for immediate activities, and the 24-hr PSI forecast to plan ahead" ([NEA haze update, 4 Sep 2026](https://www.nea.gov.sg/media/news/advisories/index/haze-situation-update-(04-september-2026))). The outlook beyond 24 h is wind and hotspot prose, with no numbers. |
| **IQAir** | Shows hourly "AQI⁺" built from hourly averages, not 24 h ([IQAir KB](https://www.iqair.com/ca/support/knowledge-base/what-does-iqairs-aqi-indicate)). Its multi-day forecast gives numbers per day from a proprietary model driven by GFS. No accuracy is published. Hourly numbers several days out imply more precision than any model has. |
| **KLH (ISPU)** | Publishes current ISPU, i.e. 24 h based (P.14/2020). We found no public ISPU forecast from KLH or BMKG. |

The common pattern is: current conditions as a number, the next 24 h as a category or range,
and beyond that prose and categories only. The 24 h mean, not the hourly maximum, is the
quantity that gets forecast.

### 4.2 Forecast PM2.5 beyond 24–48 h: proposal

1. **Day 1 (0–24 h):**
   - Show the 24 h mean as a number rounded to 2 significant figures, with a "likely range" of
     ÷1.7 to ×1.7. That is the CV 50% interval; inside the network it is ÷2 to ×2 for about 70%.
   - Show the ISPU category of the 24 h mean, plus the second category when the range crosses
     a breakpoint, as NEA does.
2. **Days 2–3:**
   - Show the **category only** (or a two-category range), computed from the daily mean of the
     re-faded field (§5 item 2), labelled "perkiraan kasar".
   - Do not show µg/m³ numbers. Do not show "Puncak 72 jam".
3. **Remove the 72 h hourly peak** (`pm25_peak`, `peak_time`, `ispu_peak`) from the city table.
   It is a maximum over 24 noisy 3-hourly values, lands in the uncorrected tail for 45% of
   cities, and produced 3,677 µg/m³ for Palangka Raya.
4. **Cap and round.** Show "> 500" above 500, as the in-progress UI change does. Also show 2
   significant figures, and "> 1,000" for stations.
5. **Mark precision on the map.** Shade or hatch cells more than 150 km from any measuring
   station ("di luar jangkauan stasiun"). There the error is ×3 typical and the number is
   effectively raw CAMS.

### 4.3 Transboundary attribution: proposal

Modelled fire-smoke index at receptors against what was measured (`transboundary.json`, same
run). "Explained" = 24 h mean index / (observed − 15 µg/m³ background):

| Receptor | 24 h mean model index | Observed / corrected PM2.5 | Explained | Shares shown today |
| --- | --- | --- | --- | --- |
| Singapore | 0.9 | 95 (NEA) | **1%** | Jambi 42%, Sumsel 28%, Kalbar 17%; not flagged weak |
| Johor Bahru | 0.7 | 110 (DOE ≈) | 1% | Jambi 44% …; flagged weak |
| Kuala Lumpur | 0.01 | 76 (DOE ≈) | 0% | Jambi 58% …; flagged weak |
| Kuching | 3.0 | 38 (DOE ≈) | 13% | Kalteng 99% |
| Pekanbaru | 3.4 | 233 (corrected CAMS) | 2% | Sumsel 53%, Jambi 41% |
| Banjarmasin | 3.4 | 112 | 3% | Kalteng 60%, Kalsel 38% |
| Jambi | 66 | 204 | 35% | Sumsel 87% |
| Palembang | 97 | 229 | 46% | Sumsel 98% |
| Pontianak | 76 | 205 | 40% | Kalteng 89% |
| Palangka Raya | 204 | 1,465 | 14% | Kalteng 96% |

Why the distant signal is tiny:
- Emissions are low by 2–3.5× (Kiely 2019).
- Spin-up is only 48 h, against 1–4 days of transport to Singapore and Malaysia. The
  transboundary note (§5.1.2 there) asks for 96 h.
- Puff dilution with σ growing at 0.7 m/s.
- Smoke older than the spin-up is missing.

So the shares at Singapore, Johor Bahru and KL describe how a trace of modelled smoke splits,
not what people are breathing. Proposal:

- **Show province shares only when the model explains a meaningful part of the haze:** a 24 h
  mean index ≥ 10 µg/m³ **and** ≥ 20% of the observed excess. Today that is Jambi, Palembang
  and Pontianak only.
  - Below that, show "Asal asap belum bisa ditentukan model" and, at most, a qualitative
    direction ("angin dari arah Sumatra bagian selatan").
  - Replace `WEAK_SIGNAL = 5` (a 24 h sum) in `web/src/Controls.tsx` with this test computed in
    `smoke.transboundary` (`entry["confidence"]`).
- **Round shares to the nearest 10%,** and never show a "biggest single fire" at a receptor
  where the explained fraction is below 20%.
- **Do not imply that the fraction is the share of PM2.5.** Label it as "dari asap kebakaran yang
  dimodelkan", next to the measured number.
- **Peat share:** show it only under the same rule.
- **Remove the "consistent with Reddington/Koplitz" claim** from docs/models.md for single runs.

### 4.4 Proposed UI wording

| Place | Bahasa Indonesia | English |
| --- | --- | --- |
| Station panel note (replaces "Data per jam…") | "Angka stasiun ISPU dan DOE Malaysia adalah rata-rata 24 jam yang diperbarui tiap jam; NEA Singapura rata-rata 1 jam. Data ISPU tervalidasi otomatis dan bisa meleset ±20%, lebih besar saat asap sangat pekat." | "ISPU and Malaysia DOE values are 24-hour averages updated hourly; Singapore NEA values are 1-hour averages. ISPU data are auto-validated only and may be off by ±20%, more in very dense smoke." |
| CAMS callout | "Di stasiun berasap (> 100 µg/m³), model CAMS hanya membaca sekitar 35% dari angka stasiun (rata-rata 24 jam). Peta sudah dikoreksi dengan data stasiun; di Jawa koreksinya justru menurunkan angka model." | "At smoky stations (> 100 µg/m³) CAMS reads only about 35% of the station value (24-hour means). The map is corrected with station data; over Java the correction lowers the model instead." |
| Map legend, accuracy | "Akurasi: dekat stasiun (< 50 km) biasanya dalam ×1,6; jauh dari stasiun (> 150 km) bisa meleset 3× atau lebih. Area arsiran = di luar jangkauan stasiun." | "Accuracy: near a station (< 50 km) typically within ×1.6; far from stations (> 150 km) can be off 3× or more. Hatched = beyond station reach." |
| City table header | "24 jam ke depan (rata-rata)" · "Besok" · "Lusa" | "Next 24 h (average)" · "Tomorrow" · "Day after" |
| City cell, day 1 | "≈ 150 µg/m³ (kisaran 90–250) · Tidak sehat–Sangat tidak sehat" | "≈ 150 µg/m³ (likely 90–250) · Unhealthy to Very unhealthy" |
| City cell, days 2–3 | "Kemungkinan Tidak sehat" (no number) | "Likely Unhealthy" (no number) |
| City table note | "Prakiraan PM2.5 dari model CAMS yang dikoreksi dengan stasiun. Koreksi paling andal untuk 24 jam pertama; hari ke-2 dan ke-3 hanya berupa kategori perkiraan kasar. Rujuk ISPU resmi untuk keputusan saat ini." | "PM2.5 forecast from CAMS corrected with station data. The correction is most reliable for the first 24 hours; days 2–3 are rough categories only. Check the official ISPU for decisions now." |
| Transboundary, low confidence | "Asap kebakaran yang dimodelkan hanya menjelaskan sebagian kecil kabut di kota ini, jadi asal asapnya belum bisa ditentukan." | "Modelled fire smoke explains only a small part of the haze in this city, so its source cannot be determined yet." |
| Transboundary, shown | "Dari asap kebakaran yang dimodelkan (≈ 40% dari kabut terukur): Sumatera Selatan ~90%." | "Of the modelled fire smoke (≈ 40% of the measured haze): South Sumatra ~90%." |
| Transboundary footer | "Pembagian asal asap adalah estimasi model eksperimental, bukan penetapan resmi. Model belum menghitung asap yang lebih tua dari 2 hari dan cenderung meremehkan emisi gambut 2–3 kali." | "Source shares are an experimental model estimate, not an official finding. The model omits smoke older than 2 days and tends to underestimate peat emissions 2–3×." |

### 4.5 Numbers to remove or change

- **Remove:** "Puncak 72 jam" µg/m³ and its ISPU chip. Remove province percentages and
  "Penyumbang terbesar" where the explained fraction is below 20% (today Singapore, Johor Bahru,
  KL, Kuching, Pekanbaru, Banjarmasin).
- **Change:** the "CAMS reads X%" callout should use the 24 h basis (0.35, not 0.27). City
  "Sekarang" should be labelled as a model estimate. Station numbers should be rounded to 2
  significant figures (in progress in the working tree).
- **Keep:** first arrival time of fire smoke, at half-day resolution as in the working tree.
  It is a qualitative product and the fade does not affect it.

## 5. Recommended code changes

| # | File / function | Change | Evidence |
| --- | --- | --- | --- |
| 1 | `stations.py` `correction_field` | Compare like with like. For ISPU (and DOE, if ever used), compute CAMS as the mean of the 24 hourly frames ending at `ts_utc` (`smog["pm25"]` already has `past_days=1`). For NEA, keep the hourly value. Select `network` in the query and set `avg_h = 24 if network in ("ISPU", "DOE") else 1`. | r(log) 0.23 → 0.46; raw MdAE 1.05 → 0.85; Palangka Raya factor 3.96 → 2.34 (§1.2) |
| 2 | `smoke.py` `build` (the fade) | Do not fade to 1 by 48 h. Blend in **log space** from the local factor to a regional factor: the same stations with a long range (IDW full 300 / zero 800 km, or the island median). Hold the local factor for the first 24 h, then use `w = exp(−(lead−24)/72)` and `lf = lf_reg + (lf_loc − lf_reg)·w`. At minimum, switch the current blend `1 + (f−1)·fade` to `exp(ln f · fade)`. | Singapore: ratio still worth ×2 at +24–36 h; current fade gives day-3/day-1 of 2.0 (Java) and 0.48 (haze) (§2.9) |
| 3 | `stations.py` `CORR_CLIP` | `(0.1, 10.0)` | Java bias +0.62 → +0.14; 37 stations need < 0.5 (§2.6) |
| 4 | `stations.py` `CORR_FULL_KM`/`CORR_ZERO_KM` | Keep 150/300, or 200/400. Do not exceed 500. | Semivariogram; tuning differences ±0.03 (§2.5, §2.7) |
| 5 | `stations.py` `parse_ispu` | Drop `a_pm25` when `c_pm25` is null, or when `a_pm25 > 1.5·a_pm10 + 5` with `a_pm10 > 1`. Drop rows whose `ts_utc` is later than the fetch time. Store `t_pm25` and `c_pm25`. Document that `pm25` is a 24 h running mean (SCHEMA comment says "1 h"). | §1.3, §1.4 |
| 6 | `stations.py` `correction_field` (optional) | Replace IDW with simple kriging of ln(obs/CAMS₂₄): exponential covariance, L = 300 km, nugget 30% of the variance, mean 0 inside 300 km. Return the kriging standard deviation as an uncertainty field for the hatched "beyond station reach" mask. | LOO 0.46 vs 0.56; Malaysia FAC2 0.94 vs 0.72; not yet significant (§2.2, §2.8) |
| 7 | `smoke.py` `city_outlook` | Replace `pm25_peak`/`peak_time`/`ispu_peak` with `days: [{mean, lo, hi, ispu, ispu_hi}]` for three 24 h windows from `start`. Set `lo`/`hi` to ÷1.7/×1.7 on day 1, or from the kriging SD. Mark days 2–3 `"coarse": true`. | §4.2 |
| 8 | `smoke.py` `transboundary` | Add `explained = mean24(index) / max(observed − 15, 1)` and `confidence = "ok" if mean24 ≥ 10 and explained ≥ 0.2 else "low"`. The UI hides shares on "low". Raise `SPINUP_H` to 96 (see data-transboundary-haze.md §5.1). | §4.3 |
| 9 | `stations.py` `publish` | Compute `cams_vs_obs` against CAMS₂₄ for ISPU, and report both bases during the transition. | §1.2 |
| 10 | `stations.py` `DOE_PM25` | Verify the (50.4, 100) breakpoint against DOE's published table. | §1.5 |
| 11 | `docs/models.md` | Replace "median 0.26×" with "0.35× against the matching 24 h CAMS mean (0.27× against the hourly value)". Add the CV skill (MdAE 1.05 → 0.61, FAC2 29% → 56%) and the per-distance accuracy. Drop "consistent with Reddington 2014 and Koplitz 2016" for single runs. | §2, §4.3 |
| 12 | pipeline run log | Run the LOO CV (`cv2.py` logic) on each run and log `cv_mdae_raw`, `cv_mdae_corr` and `cv_fac2` beside `skill_vs_cams`, so the radii and clip can be re-tuned on a season of data. | §2.10 |

## 6. Reproduce

All scripts run with `pipeline/.venv/bin/python -I` and `OMP_NUM_THREADS=1`.
Without that setting, BLAS oversubscription on the shared box makes the kriging folds about
200× slower. They read the DB copy read-only and never write to it or to the CAMS cache.

```
S=scratch/audit/scripts
python -I $S/cv2.py 2026-10-17T18:00 code 24 base     # LOO tables (0 = hourly basis, 24 = 24 h basis; strict = extra QC)
python -I $S/cv2.py 2026-10-17T18:00 code 24 cluster  # leave-X-km-out
python -I $S/cv2.py 2026-10-17T18:00 code 24 dist     # error vs distance and semivariogram
python -I $S/cv2.py 2026-10-17T18:00 code 24 tune     # IDW / kriging grids
python -I $S/boot.py 2026-10-17T18:00 code 24         # bootstrap CIs
python -I $S/crossborder.py 24                        # Singapore and Malaysia out of network
python -I $S/temporal.py                              # persistence of the ratio (NEA, DOE)
python -I $S/fade.py                                  # fade artefacts in the published outlook
python -I $S/checks.py                                # ISPU field semantics, time base, QC flags
```

`poll.sh` fetched ISPU and NEA (one request each) every 25 minutes, and DOE (6 states, 3 s
apart) every 75 minutes, for about 2 h.

## Addendum, 19 Oct 2026: BMKG stations and the ISPU conflict rule

BMKG's 26 hourly PM2.5 stations joined `obs_aq` on 19 Oct 2026. Leave-one-station-out on a live
snapshot (06:48 UTC; 105 ISPU, 26 BMKG, 5 NEA stations), same IDW, 150/300 km and 0.1–10 clip as
`correction_field`, evaluated at the left-out station. MdAE = median |log error|, FAC2 = share
within a factor of 2.

| Correction from | ISPU targets (105) | ISPU Kalimantan (29) | BMKG targets (26) | BMKG Kalimantan (9) |
| --- | --- | --- | --- | --- |
| raw CAMS | 0.86 / 38% | 0.70 / 48% | 0.71 / 46% | 0.84 / 33% |
| ISPU + NEA (before) | 0.52 / 62% | 0.44 / 86% | 0.52 / 54% | 0.36 / 67% |
| + BMKG | 0.51 / 57% | 0.34 / 79% | 0.52 / 54% | 0.35 / 67% |
| + BMKG, ISPU left out when > 5× off a BMKG station within 50 km | **0.46** / 59% | 0.35 / 79% | **0.43** / 62% | 0.33 / 78% |

- Each station's ratio uses its own time basis (ISPU trailing 24 h, BMKG and NEA 1 h), so the
  conflict test never compares a 24 h mean with an hourly value.
- The rule left out 6 ISPU stations: Kotawaringin Barat Madurejo (14× off BMKG Pangkalanbun; ISPU
  ~55 µg/m³ for days while BMKG read 500–1,050 every hour) and five Java stations reading
  6–11 µg/m³. They stay on the map; they only stop steering the model.
- Adding BMKG alone is mixed (lower MdAE in Kalimantan, lower FAC2). The rule improves MdAE at both
  networks. One snapshot only: differences of ~0.05 are within the noise of §2's bootstrap.
  The published skill (17 Oct) is not changed by this snapshot. Re-run on several days of `obs_aq`.
