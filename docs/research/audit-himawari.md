# Himawari-9 Wild Fire (WLF) vs VIIRS over Indonesia: backtest, 1 Sep - 18 Oct 2026

Backtest run 19 Oct 2026. The live layer (pipeline/src/haze/himawari.py) applies the rule in "Suggested map-layer rule".

## Answer

**Show it, but only as a narrow layer: reliability 5 only, only where VIIRS has shown no fire within 5 km in the last 72 h, and only after Himawari sees the point in two scans within 1 hour.** Do not show reliability 1 or 3. Do not show Himawari points on top of fires that VIIRS already shows.

Measured over 47 days (2 Sep - 18 Oct 2026, Indonesia only, 31,076 new VIIRS fires):

- **Gain.** About **20 new fires per day** (3.0% of all new VIIRS fires, net of chance) appear **about 6 h earlier** (middle half 3-9 h). Himawari is first for 47% of new fires with more than 10 VIIRS pixels and for 17% of fires with 4-10 pixels (raw rates; the chance rate for this rule is 0.9%).
- **Cost.** About **16 new Himawari markers per day**; about **9.5 per day** never get a VIIRS detection within 5 km in the next 24 h. When VIIRS passes over these points at the same moment, it sees fire at **76%** of them (378 point-passes).
- **Baseline.** "Himawari would have shown 3% of new fires on average 6 h earlier, at a cost of about 10 unconfirmed markers per day across Indonesia."

A wider rule (reliability 3 and 5, novel points) doubles the gain to 46 early fires per day, but costs 170 unconfirmed markers per day, and VIIRS confirms only 15% of those points at the same moment: mostly noise.

Why "novel only": 92.5% of Himawari detections in Indonesia lie within 5 km of a VIIRS fire from the last 72 h; they add nothing the map does not already show.

Confidence: 7/10. Main doubt: VIIRS is the "truth" and also misses fires (clouds, short fires between passes), so some "unconfirmed" points are real fires.

## Data

| Item | Value |
|---|---|
| Himawari-9 L2 WLF v010, 10 min, full disk (FTPS ftp.ptree.jaxa.jp:990) | 6,804 of 6,912 slots (02:40 and 14:40 UTC never exist; 12 other files absent) |
| Himawari rows kept (bbox lon 94.5-141.5, lat -11.5-6.5) | 2,162,923; 1,993,922 in Indonesia; 9,209 at sea |
| VIIRS 375 m (DEA WFS, AFIMG, S-NPP/NOAA-20/NOAA-21), 29 Aug - 18 Oct | 1,190,698 rows; 1,037,817 in Indonesia during 1 Sep - 18 Oct |
| VIIRS passes over the bbox, 1 Sep - 18 Oct | 670 (about 14 per day) |
| Cache | 16 MB Himawari parquet, 28 MB VIIRS, 56 MB joined; 109 MB folder; no raw full-disk file written |

## Results

### 1. Matched-time precision
Share of Himawari pixels with a VIIRS detection within 2/3/5 km in the same pass (Himawari scans within ±30 min of the pass and inside its swath; one count per pass and pixel; Indonesia; static sources removed).

| Group | 2 km | 3 km | 5 km | n |
|---|---|---|---|---|
| Reliability 1 | 47% | 55% | 60% | 74,675 |
| Reliability 3 | 64% | 74% | 78% | 57,908 |
| Reliability 5 | 84% | **91%** | 92% | 23,576 |
| Level 1 (cold) | 57% | 65% | 68% | 16,753 |
| Level 2 (smouldering) | 68% | 78% | 81% | 113,570 |
| Level 3 (flaming) | 17% | **24%** | 31% | 25,836 |
| Day / Night | 49% / 74% | 58% / 82% | 64% / 84% | 94,343 / 61,816 |
| Kalimantan / Sumatra / other IDN | 64 / 47 / 56% | 73 / 55 / 65% | 76 / 58 / 71% | 74,159 / 20,526 / 61,474 |
| QF 2 | 6% | 16% | 26% | 304 |
| **Novel** (no VIIRS within 5 km in prior 72 h) | 11% | **14%** | 16% | 25,418 |
| Not novel | 68% | 78% | 82% | 130,741 |
| Volcano flag > 0 | 65% | 79% | 86% | 742 |
| Near pipeline static source (2 km) | 64% | 78% | 83% | 2,259 |
| At sea | 80% | 88% | 89% | 545 |

Precision at 3 km:

| Rel. | Day | Night | Kalim. | Sumatra | Other | Novel | Novel + seen twice in 1 h | Scan within 5 min of pass |
|---|---|---|---|---|---|---|---|---|
| 1 | 52% | 75% | 61% | 39% | 51% | 12% | 18% | 67% |
| 3 | 65% | 79% | 83% | 61% | 70% | 15% | 23% | 81% |
| 5 | 89% | 91% | 93% | 81% | 92% | 68% (n=552) | **76% (n=378)** | 93% |

- Reliability 5 is good everywhere; reliability 1 is close to a coin toss in daytime.
- Level 3 ("flaming") is the worst class: do not use Level to promote points.
- Sumatra is worst (about 45° from the sub-satellite point: larger, slanted pixels).
- Novel reliability 1-3 points are mostly not seen by VIIRS at the same moment, so they are likely false; novel reliability 5 points hold up (68-76%).

### 2. Matched-time recall
VIIRS detections (nominal/high, Indonesia, not static) grouped into 2 km cells per pass; a cell is "seen" if a Himawari pixel lies within 3 km within ±30 min.

| VIIRS FRP in cell (MW) | Cells | Seen (any rel.) | Seen (rel ≥3) |
|---|---|---|---|
| 0-5 | 208,403 | 15% | 13% |
| 5-10 | 101,852 | 25% | 18% |
| 10-25 | 86,260 | 38% | 27% |
| 25-50 | 34,062 | 52% | 36% |
| 50-100 | 16,763 | 60% | 40% |
| 100-250 | 8,033 | 60% | 39% |
| 250+ | 2,258 | 45% | 29% |
| **All** | 457,631 | **27%** | **20%** |
| Kalimantan / Sumatra / other | | 31 / 27 / 23% | 21 / 22 / 18% |
| Day / night | | 22 / 33% | 11 / 31% |

Himawari misses most small fires; even 50-250 MW cells only 60%. The drop above 250 MW is not explained.

### 3. Early warning
- **New VIIRS fire:** a nominal/high detection in Indonesia, not static, with no VIIRS detection of any confidence within 5 km in the previous 72 h; new detections from the same pass within 5 km form one event. 31,076 events; 73% single pixels.
- **Lead:** first VIIRS time minus first Himawari detection within 5 km in the 24 h before. "Himawari first": lead > 0.5 h.
- **Placebo:** the same events moved 25 km in a random direction (kept if on Indonesian land); its rate is the chance level.

| Himawari points used | First | Placebo | **Net** | Net fires/day | Net lead median (IQR) |
|---|---|---|---|---|---|
| All, any rel. | 16.3% | 12.5% | 3.8% | 25.0 | 4 h (2-7) |
| All, rel ≥3 | 13.2% | 10.5% | 2.7% | 17.7 | 4 h (2-7) |
| All, rel 5 | 6.0% | 4.9% | 1.2% | 7.8 | 5 h (3-7) |
| Novel, any rel. | 12.8% | 4.4% | 8.5% | 56.0 | 6 h (2-10) |
| Novel, rel ≥3 | 10.3% | 3.3% | 7.0% | 46.2 | 6 h (3-10) |
| Novel, rel 5 | 4.7% | 1.2% | 3.5% | 23.1 | 6 h (3-9) |
| Novel, rel ≥3, seen twice 1 h | 7.2% | 2.0% | 5.2% | 34.7 | 6 h (3-9) |
| **Novel, rel 5, seen twice 1 h** | **3.9%** | **0.9%** | **3.0%** | **19.5** | **6 h (3-9)** |

Raw "first" share by event size:

| Rule | 1 px (22,808) | 2-3 px (7,063) | 4-10 px (1,122) | >10 px (83) |
|---|---|---|---|---|
| Novel rel ≥3 | 7.9% | 14.0% | 31.7% | 60.2% |
| Novel rel 5 | 3.3% | 6.3% | 19.3% | 50.6% |
| Novel rel 5, twice | 2.6% | 5.3% | 17.0% | 47.0% |

By region and time of day (novel rel ≥3): Kalimantan 12.8%, Sumatra 15.0%, other 7.7%; day 7.7%, night 18.5%.
Lead-time plot: the real signal piles up at 0-10 h before VIIRS; the 17-22 h hump also appears in the placebo (mostly chance).

**Reverse view: new Himawari clusters** (one scan, Indonesia, not static, no Himawari detection within 5 km in the previous 72 h), checked for VIIRS within 5 km in the next 24 h (clusters up to 17 Oct):

| Clusters | /day | VIIRS ≤24 h | VIIRS earlier only | Never | **Unconfirmed/day** | Median VIIRS lag |
|---|---|---|---|---|---|---|
| Any rel. | 572 | 39% | 13% | 49% | 278 | 5.2 h |
| Rel ≥3 | 360 | 39% | 14% | 47% | 170 | 6.5 h |
| Rel 5 | 47 | 51% | 19% | 31% | 15 | 7.8 h |
| Novel, any | 341 | 19% | 0% | 81% | 277 | 4.1 h |
| Novel, rel ≥3 | 209 | 19% | 0% | 81% | 170 | 5.7 h |
| Novel, rel 5 | 23 | 35% | 0% | 65% | 15 | 7.4 h |
| Novel, rel ≥3, seen again ≤1 h | 68 | 34% | 0% | 66% | 45 | 5.7 h |
| **Novel, rel 5, seen again ≤1 h** | **16** | **39%** | 0% | 61% | **9.5** | 7.4 h |

Distinct pixels lit per day in Indonesia (share with no VIIRS within 3 km within ±1 day):

| Rel. | All | Novel | Novel + twice |
|---|---|---|---|
| ≥1 | 4,372 (31%) | 1,190 (83%) | 540 (74%) |
| ≥3 | 3,398 (25%) | 739 (80%) | 380 (72%) |
| 5 | 1,397 (13%) | 170 (65%) | **128 (61%)** |

### 4. Persistent false alarms
- 17,356 of 74,153 Himawari pixels (Indonesia or sea) have no VIIRS detection of any kind within 3 km over 29 Aug - 18 Oct.
- 428 were flagged on 7 or more days (copied to pipeline/static/himawari_false_alarms.csv): 5 near a pipeline static source, 5 with the volcano flag, 2 at sea; 367 reached reliability ≥3 at least once, 50 reached 5. Sumatra 222, other Indonesia 117, Kalimantan 87.
- The pipeline's static list comes from VIIRS, so it misses them. Many are towns (Himawari's 3.9 µm test seems to trigger on warm urban surfaces).

| # | Lat | Lon | Days | Scans | Max rel | Desa | Likely cause |
|---|---|---|---|---|---|---|---|
| 1 | -3.98 | 122.50 | 40 | 196 | 1 | Kadia | Kendari city |
| 2 | -8.84 | 121.66 | 37 | 330 | 1 | Kel. Mautapaga | Ende town |
| 3 | -3.40 | 126.56 | 36 | 200 | 5 | Waereman | unknown (Buru) |
| 4 | -3.96 | 135.60 | 35 | 431 | 5 | Ideduwa | unknown (Papua) |
| 5 | 1.46 | 124.84 | 34 | 216 | 1 | Ranotana Weru | Manado city |
| 6 | -3.46 | 102.54 | 32 | 333 | 5 | Duku Ulu | Curup town |
| 7 | -3.46 | 102.52 | 32 | 313 | 5 | Dusun Curup | Curup town |
| 8 | -0.86 | 134.06 | 31 | 179 | 1 | Manokwari Barat | Manokwari |
| 9 | -2.92 | 116.12 | 31 | 85 | 3 | (none) | unknown |
| 10 | 3.70 | 117.00 | 29 | 255 | 3 | Lubok Buat | unknown |
| 11 | 3.30 | 117.60 | 28 | 168 | 1 | Gunung Lingkas | Tarakan city |
| 12 | -6.26 | 140.06 | 27 | 251 | 5 | Sadar | unknown (Papua) |
| 13 | -3.82 | 102.30 | 27 | 198 | 1 | Jalan Gedang | Bengkulu city |
| 14 | -3.84 | 102.32 | 27 | 180 | 1 | Pagar Dewa | Bengkulu city |
| 15 | -3.96 | 135.58 | 26 | 231 | 3 | Ideduwa | unknown (Papua) |
| 16 | -1.42 | 133.80 | 25 | 343 | 5 | Menesrij | unknown (Papua Barat) |
| 17 | 1.10 | 117.92 | 25 | 67 | 3 | (none) | unknown |
| 18 | -3.30 | 102.86 | 24 | 280 | 1 | Jawa Kanan Ss | Lubuklinggau city |
| 19 | 1.08 | 117.92 | 24 | 110 | 1 | (none) | unknown |
| 20 | 3.82 | 117.52 | 24 | 107 | 5 | Tepian | unknown |

"Likely cause" names come from the desa name and the agent's knowledge of town locations; not checked against imagery.

### 5. Latency
FTP modification time (MLSD, UTC) minus the scan timeline start: normal days median **36 min**, p90 38, p99 46; 93.8% within 40 min, 95.6% within 60 min. Outages: 9 Sep (139 files, up to 31 h late), 10, 16, 17 Sep (29 each), 30 Sep (32), 7 Oct (25), 8 Oct (16); late files arrive as a batch, nothing lost. Header processing time is always ~30 min after the timeline start.
A live point would appear ~40-50 min after the scan, +10 min for the "twice" rule, + the site's poll interval. VIIRS on DEA arrives 40-60 min after a pass: the gain is the 10-minute revisit, not faster delivery.

## Suggested map-layer rule
1. **Source:** JAXA P-Tree L2 WLF v010 over FTPS; poll every 10 min; keep the Indonesia bbox.
2. **Keep a point only if:** reliability 5; not within 2 km of a pipeline static source; not on the persistent false-alarm list (rebuild each season); no VIIRS detection of any confidence within 5 km in the last 72 h; a second Himawari detection within 3 km in an earlier scan within 60 min.
3. **Label:** "Unconfirmed heat signal (Himawari-9, 2 km, every 10 min). Not yet seen by VIIRS. Most confirmed fires show up in VIIRS within about 7 h; about 6 in 10 points are never confirmed." Distinct hollow marker; never in statistics, events or alerts.
4. **Lifetime:** remove when VIIRS detects fire within 5 km, or 12 h after the last Himawari detection. (Removing on a VIIRS pass that sees nothing was not tested.)
5. **Expect:** ~16 new markers/day in peak season, ~10 never confirmed.

## Method
- Distances: planar km, equirectangular at 2.5°S (<2% error), scipy KD-trees.
- Labels: country via `haze.compare.assign_country` (Natural Earth, 3 km coast snap); Kalimantan lon 108-119.5, lat -4.5-4.5; Sumatra west of 106.9°E, north of 6.5°S; day = `solar_zenith` < 85°; static within 0.75 km (VIIRS) / 2 km (Himawari) of `pipeline/static/static_sources_*.csv`.
- Himawari time = per-row pixel time; FRP MW = FRP (W m⁻²) × Area (km²).
- Passes: one satellite's detections < 20 min apart. Swath: from median local solar time per satellite (13.53-13.72 h day, 1.28-1.51 h night); nadir lon = (centre − UTC hour) × 15; ±12° counts as in swath (96.5% of VIIRS detections within ±12° of nadir, 99.9% within ±15°).
- Precision: ±30 min, one count per (pass, pixel), closest distance. Recall: 2 km cells, summed FRP.
- Early warning: novel flag per UTC hour; "twice" = another Himawari detection within 3 km 5-60 min earlier; net lead = per-hour excess of real over placebo share (floored at 0).
- Persistent false alarms: 0.02° pixels with no VIIRS within 3 km over the whole period.
- Changes after the 3- and 7-day test runs (before the full run): added the placebo (13% of moved events also "had" a Himawari point within 5 km; without it raw rates overstate the value 3-4×); added the novel / twice / rel-5-twice rules.

## Caveats
- VIIRS is not perfect truth (4-6 looks a day, misses cloud-covered and short fires); same-time precision (76%) is the better false-alarm estimate.
- No cloud mask. Swath approximated from solar time (edge pixels 12-14° from nadir left out).
- DEA, not FIRMS (DEA flags ~2% extra edge pixels, which helps Himawari's precision slightly).
- One peak season; the placebo is one choice; regions are boxes; place names unchecked; recall drop above 250 MW unexplained; latency assumes MLSD times are UTC (consistent with header +6 min).

## Files and run order
`fetch_himawari.py` (implicit-TLS FTPS, 8 connections, bbox filter in memory, credentials from env only), `fetch_viirs.py` (DEA WFS per UTC day via `haze.dea.fetch`), `prep.py` (join, labels, passes), `analyze.py` (steps 1-5 + placebo; optional start/end), `plots.py` (figures). `data/` = cache (gitignored), `results/` = outputs (`run_7day.txt` = 7-day method run).

Run from pipeline/ (the backtest scripts are not in the repo):
```
set -a; . ~/.config/pantaukarhutla/jaxa.env; set +a
uv run python <backtest dir>/fetch_himawari.py 2026-09-01 2026-10-18 8
uv run python <backtest dir>/fetch_viirs.py 2026-08-29 2026-10-18
uv run python <backtest dir>/prep.py
uv run python <backtest dir>/analyze.py
uv run python <backtest dir>/plots.py 2026-10-13
```
