# Detection quality audit: confidence, false alarms and double counting

Audit of how haze ("Pantau Karhutla") turns NASA FIRMS hotspots into the numbers it publishes,
measured against the literature and against the production database. Written 17 Oct 2026.

**Short answer to "are we showing inaccurate data?"**

- Our **confidence filter is already the one NASA recommends**: VIIRS nominal+high, MODIS ≥ 30.
  Making it stricter changes almost nothing (MODIS ≥ 80: −3% events), or the wrong thing ("VIIRS
  high only" keeps 6% of detections and is not a quality class; see §1.1).
- The real accuracy risks are elsewhere:
  1. **Raw detection counts are inflated by satellite count, not by fire.** In 2026, five satellites
     each see the same fire. Raw counts are 3.0× S-NPP (2.0× in 2019/2023). "Detections per day"
     in History and the dashboard cannot be compared across years.
  2. **Half of all "fires" are one daytime pixel seen once.** 102,694 of 203,890 events in 2026
     (50%) are single detections, 86,755 of them single *daytime* nominal pixels. Daytime is when
     all documented commission errors happen. These events carry only 6% of detections, but they
     make up 41% of the events on the live map and most of "new today".
  3. **Persistent industrial heat in 2026 is not masked.** 163 cells were hot on ≥ 30 days over
     ≥ 6 months of 2026, but the mask was built from 2019–2025 only. This affects 685 events. Two
     of the season's ~125 largest "fires" sit on one persistent source near Binuang, Tapin.
  4. **Some public tables still include filtered-out data.** History counts include detections
     outside Indonesia and low-confidence ones (+14% over what events use). Region tables
     include low-confidence detections (+5.4%).
  5. **Our numbers are ~20–30× the official figure journalists quote.** Kemenhut's headline counts
     only "kepercayaan tinggi" (saturated pixels), from four satellites. Nothing on the site explains
     the difference yet.
- The fix is a **two-tier event model** ("strong detection" vs "single detection, unverified"),
  **satellite-count-robust metrics**, a **rolling static mask**, and **clear hotspot ≠ fire
  wording**. Concrete code changes are in §4.

---

## 1. What the literature says

### 1.1 Confidence classes are not the same thing on VIIRS and MODIS

**VIIRS 375 m (VNP14IMG / VJ114IMG / VJ214IMG).** The fire mask has three fire classes. These
are where BRIN's **7/8/9** codes come from ([VIIRS C2 375 m User Guide v1.2, 2025, Table 1][viirs-ug]):

| Class | FIRMS | BRIN | Meaning (user guide / [Schroeder et al. 2014][s14]) |
| --- | --- | --- | --- |
| 7 low | `l` | 7 rendah | **Daytime only** in Indonesia. Pixels near sun glint, or a *stand-alone* pixel (no adjacent fire pixel) whose I4 is < 15 K above its 3×3 ring. |
| 8 nominal | `n` | 8 sedang | Free of sun glint, with a strong (> 15 K) anomaly, day or night. |
| 9 high | `h` | 9 tinggi | **Saturated I4 pixels** (including DN folding), day or night. |

So VIIRS "high" means *very hot* (intense flaming fire, flare, smelter), **not "more certain"**.
Schroeder 2014 measured commission errors **< 1.2 % for nominal pixels**. The worst region was
eastern China (1.2%), from bright factory rooftops. The global urban false-alarm rate was 0.03%.
Night commission outside the South Atlantic Anomaly was "considered negligible". Low-confidence
daytime pixels had ~6% urban false alarms on average (40% in eastern China). Elsewhere they
mostly sat "along the edge of fire pixel clusters of nominal confidence … lower intensity
sub-pixel fire activity".

**MODIS (MOD14/MYD14 C6/C6.1).** Confidence is a continuous 0–100%. The classes are
low < 30, nominal 30–79 and high ≥ 80 ([MODIS C6/C6.1 Fire User Guide][modis-ug], Table 11).
The guide's advice is: "Users requiring fewer false alarms may wish to retain only nominal- and
high-confidence fire pixels, and treat low-confidence fire pixels as clear, non-fire, land pixels."
The FIRMS FAQ adds that the confidence field "should be used with caution as it is likely that it
will vary in terms of meaning in different parts of the world", and that "there is no way to
establish an optimal cutoff a priori" ([FIRMS FAQ][firms-faq]).

The [FIRMS FAQ][firms-faq] also says FIRMS has removed night-time low-confidence VIIRS pixels
from NRT data. They occur only in the SAMA region, and a 2025 preprint documents their
absence globally ([arXiv 2510.26816][arxiv-low]). **In our DB, 0.0% of VIIRS night detections
are low** (2019, 2023, 2026), which matches.

### 1.2 Commission (false alarms) and omission

| Study | Region | Finding |
| --- | --- | --- |
| [Schroeder et al. 2014][s14], RSE 143 | Global, Aug 2013 | VIIRS 375 m nominal commission < 1.2%. Night commission negligible. 375 m detects 3× (day) and 25× (night) more fire pixels than 750 m VIIRS. 50% detection probability at night for very small fires: a 1.25 m bonfire was detected. |
| [Csiszar et al. 2014][c14], JGR 119 | Global | 750 m VIIRS product status. VIIRS gives 26% more detections than MODIS in the central scan zone and ~70% more outside it, because of scan geometry and sampling. **Different sensors give different counts for the same fires.** |
| [Giglio et al. 2016][g16], RSE 178 | Global, > 2,500 ASTER scenes | MODIS C6 daytime commission 1.2% (C5: 2.4%). **No night-time commission errors found.** False alarms are highest in dense tree cover, where forest clearings mimic fires. **Equatorial Asia** commission fell by ~5% absolute from C5 to C6. Omission is 86% for all ASTER-visible fires, which can be as small as 4 m², but < 10% for fires ≥ 140 ASTER pixels. Large-fire omission levels off at ~5%: smoke and burn scars. |
| [Schroeder et al. 2016][s16], RSE 185 | Landsat-8 30 m | The 30 m active-fire reference used to validate 375 m VIIRS. The basis for the Indonesian peat validations below. |
| [Schroeder et al. 2008][s08], RSE 112 | Amazon | Industrial heat sources "can be readily isolated … using simple detection persistence analysis". This is the basis for our recurrence mask. |
| [Tansey et al. 2008][t08], JGR 113 | Central Kalimantan peat | MODIS hotspots: **~60% omission, ~8% commission**. Using the *lower* confidence threshold improved agreement with burned area. ~15–16 ha burned per hotspot. |
| [Sofan et al. 2020][sofan], IJDE 13 (with W. Schroeder) | Indonesian peatlands, Landsat-8 reference | Night VIIRS 375 m agreed ~**80%** for small fires (< 14 ha). Buffered day+night clusters reached up to **90%** detection probability. The authors recommend cluster analysis and combining day and night passes. |
| [Indradjad et al. 2023][indr] (BRIN), Fire 7(1):9 | Indonesia, field-reported burns | VIIRS point and cluster hotspots matched reported fires within 1.5 km **52–53%** of the time, and **83%** for burns > 14 ha. Clusters do better on peat (62% vs 57%). BRIN's portal now serves "Cluster" hotspots. |
| [Vadrevu & Lasko 2018][vl18], Remote Sens. 10:978 | Punjab croplands | VIIRS 375 m found 4.8× more fires than MODIS Terra+Aqua (6.5× Aqua alone). Mixing sensors changes counts by integer factors. |
| [Liu et al. 2020][liu20], RSE 237 | Indonesia | The main uncertainties in Indonesian fire data are the "small, fragmented fire landscape" and "very poor satellite observing conditions due to clouds and thick haze". Inventories that correct for obscuration (GFAS) match Singapore PM2.5 best. |
| [Wooster et al. 2018][w18], Remote Sens. 10:495 | Central Kalimantan, 2015 field campaign | Field emission factors for sub-surface peat burning. Peat fires smoulder for long periods at low intensity. This supports treating low-FRP repeated detections on peat as real, not as noise. |
| [Lohberger et al. 2018][lo18], GCB 24 | Indonesia 2015 | Sentinel-1 radar burned area was ~4.6 Mha, well above hotspot-based estimates, so **hotspots under-represent peat burning**. |

I could not locate a specific "Fernandes" paper on Indonesian VIIRS peat-fire detection, nor an
Ichoku paper on that topic. The closest Indonesian validations are Tansey 2008, Sofan 2020 and
Indradjad 2023, listed above.

**What this means for us.** False alarms from nominal VIIRS pixels are rare (≤ 1.2%) and almost
all happen in **daytime** (glint, roofs, hot bare ground, forest clearings). In Indonesia the
bigger error is **omission**: cloud, haze, smouldering peat and small, short fires. Making the
confidence threshold stricter therefore buys little precision and costs a lot of recall. Both
Indonesian validations recommend **clustering and repeat (day+night) detection**.

### 1.3 Static and industrial heat; plume artefacts

- **Gas flares, smelters, refineries, cement and steel plants, coal stockpiles and mines, and
  volcanoes** look like fires at 375 m. NRT FIRMS data carries no type flag ([FIRMS FAQ][firms-faq]:
  "Different types of thermal anomalies are not currently attributed in the NRT"). The SP `type`
  field (0 vegetation, 1 volcano, 2 static land, 3 offshore) had a bug in VNP14IMGML v1/v2 that
  labelled obvious type-2 sources as type-0, fixed in May 2025 ([VIIRS UG §6.1][viirs-ug]).
  FIRMS now ships its own persistent-anomaly mask: 2023 S-NPP, 400 m grid, ≥ 5 detections a
  year, cross-checked against industrial datasets ([FIRMS FAQ][firms-faq]).
- **VIIRS Nightfire** ([Elvidge et al. 2013][nf13]; flare survey [Elvidge et al. 2016][nf16])
  catalogues gas flares from VIIRS M-band night data. It can be used to list flare sites (Riau,
  East Kalimantan, Natuna, offshore Java Sea) for `static_sources_manual.csv`.
- **Super-heated plume artefacts.** At night, at high scan angle, over very intense fires, VIIRS
  can flag plume pixels displaced outside the perimeter ([VIIRS UG FAQ][viirs-ug]). This matters
  little for us. It can inflate the footprints of a few extreme events.

### 1.4 Hotspot ≠ fire: how officials and analysts say to report it

- **FIRMS:** "Each hotspot/active fire detection represents the center of a pixel flagged as
  containing one or more fires or other thermal anomalies … The 'location' is the center point
  of the pixel (not necessarily the coordinates of the actual fire)." ([FIRMS FAQ][firms-faq])
- **GFW:** "Each dot on the map represents the center of a 375 meter pixel that has been flagged
  by the algorithm" ([GFW VIIRS Active Fires dataset][gfw-ds]). GFW's VIIRS launch post says a
  single alert does not indicate a fire's size or intensity, and that one fire can be recorded
  more than once on later orbits ([GFW blog][gfw-blog]). I saw this only in a search excerpt,
  because the page renders client-side. GFW recommends comparing seasons with
  *same-source cumulative* curves ([GFW wildfire trends][gfw-trends]).
- **Kemenhut (SiPongi+), 7 Sep 2026:** a hotspot is an "indikasi anomali suhu permukaan yang
  terdeteksi melalui satelit" and "tidak serta-merta menunjukkan satu kejadian kebakaran". Every
  indication needs a groundcheck. The classes are green/low 0–29% "indikasinya rendah",
  yellow/medium 30–79% "indikasinya sedang dan perlu verifikasi", and red/high 80–100% "indikasinya
  tinggi dan perlu lebih diperhatikan" ([kehutanan.go.id][kemenhut]).
- **Kemenhut headline practice, 16 Oct 2026:** "secara nasional terdeteksi **799 hotspot dengan
  tingkat kepercayaan tinggi**", from Terra/Aqua, S-NPP and NOAA-20. The spokesman added that the
  "jumlah hotspot tidak dapat langsung disamakan dengan jumlah kejadian kebakaran maupun luas area
  yang terbakar" ([detik.com][detik799]). Other outlets quoted the full SiPongi total for 14 Oct:
  20,334 = 1,784 tinggi + 17,916 sedang + 634 rendah ([fin.co.id][fin], seen as a search excerpt;
  fetch blocked).
- **KLHK analysis convention:** the KLHK 2016 hotspot report analysed only **≥ 80%** hotspots, so
  that Manggala Agni crews go to "tingkat kemungkinan tertinggi" first ([Endrawati 2016, KLHK][klhk16]).
  **Regulation:** Permen LHK P.32/2016, Pasal 1, defines titik panas as "istilah untuk sebuah
  pixel yang memiliki nilai temperatur di atas ambang batas (threshold) tertentu … yang dapat
  digunakan sebagai indikasi kejadian kebakaran hutan dan lahan" ([JDIH BPK][p32]). I saw this
  text in search excerpts; the PDF download was blocked, so check the article number before quoting it.
- **Terminology:** official usage is **"titik panas"** (hotspot). "Titik api" is colloquial and
  reads as "a fire". Our Bahasa UI currently says "Titik api" everywhere (`web/src/i18n.ts`).

**Our data reproduces the official split.** For the 24 h to 14 Oct 21:00 WIB, our four-satellite
counts (excluding NOAA-21) are 1,634 high, 20,069 nominal and 1,194 low. SiPongi's are 1,784,
17,916 and 634. So SiPongi's "tinggi" ≈ VIIRS `h` + MODIS ≥ 80, which is about 7% of detections.
On 15 Oct we published 25,802 raw detections (five satellites) and 24,386 in events. Kemenhut
quoted 799.

---

## 2. Audit of the pipeline

### 2.1 What confidence each output uses

| Output | Code | Confidence | Static mask | Outside Indonesia |
| --- | --- | --- | --- | --- |
| Events (clustering) | `events.eligible` | VIIRS n+h, MODIS ≥ 30 (`ClusterParams.min_confidence="nominal"`) | excluded | excluded |
| Map glow and flames, 48 h | `publish.recent_hotspots` | n+h | excluded | excluded |
| Spread seeds | `spread.py:214` | n+h | excluded | excluded |
| Dashboard counts, daily curve, baselines | `publish.dashboard`, `daily_counts` | via `event_id IS NOT NULL`, so n+h | excluded | excluded |
| **Region tables** (`tables/regions.json`: 24 h / 7 d / season / 30-day series) | `publish.tables` → `det`, `daily` | **all, including low** | excluded | excluded |
| **History** (`history/summary.json`, `fires-YYYY-MM.json`) | `history.daily_fires` | **all, including low** | excluded | **included** |

Both gaps, measured on 2026:

- **History, since 1 Jul:** 1,782,810 detections published. Of those, **132,931 (7.5%) are
  outside Indonesia** (Malaysia, Timor-Leste, PNG in the bbox) and 89,906 are low confidence.
  Events use 1,559,973 for the same period, so **History is 14.3% higher** than the event data.
- **Region tables, season:** 1,729,545, of which **93,079 (5.4%) are low confidence**.

### 2.2 Confidence classes per satellite and season (in Indonesia, before masking)

| Year | Satellite | n | low % | nominal % | high % |
| --- | --- | ---: | ---: | ---: | ---: |
| 2019 | S-NPP | 436,956 | 6.8 | 89.4 | 3.8 |
| 2019 | NOAA-20 | 436,963 | 6.8 | 89.9 | 3.3 |
| 2019 | Terra | 35,711 | 8.7 | 57.7 | 33.5 |
| 2019 | Aqua | 54,762 | 6.9 | 61.4 | 31.7 |
| 2023 | S-NPP | 253,258 | 7.5 | 89.1 | 3.3 |
| 2023 | NOAA-20 | 250,137 | 7.7 | 89.6 | 2.7 |
| 2023 | Terra | 16,481 | 8.9 | 67.2 | 24.0 |
| 2023 | Aqua | 35,675 | 6.1 | 70.3 | 23.6 |
| 2026 | S-NPP | 545,700 | 5.0 | 91.5 | 3.5 |
| 2026 | NOAA-20 | 562,532 | 5.3 | 91.7 | 3.0 |
| 2026 | NOAA-21 | 562,150 | 5.6 | 90.7 | 3.7 |
| 2026 | Terra | 50,644 | 6.5 | 54.2 | 39.3 |
| 2026 | Aqua | 72,696 | 5.4 | 67.5 | 27.0 |

By day/night: VIIRS night is 0.0% low and ~99% nominal. VIIRS day is ~10% low (11.3% in 2019,
10.3% in 2023, 9.7% in 2026). That matches Schroeder 2014's 11% global daytime low share.

By season (2026, VIIRS): Jul–Oct 5.4% low and 2.35% masked as static. Jan–Mar 4.2% low and
**16.9% static**. Apr–Jun 2.7% low and **31.2% static**. In 2019 and 2023, outside Jul–Oct,
12–24% of detections are static. **Off-season, the static mask matters more than confidence.**

Low-confidence detections are mostly real fire margins. **87.4%** of 2026 low detections fall
within 1.5 km / 48 h of a nominal or high detection, so they would join an existing event. Only
10,475 clusters are low-only. This is the "edge of nominal clusters" pattern in Schroeder 2014,
not the eastern-China false-alarm pattern. Excluding them is still right for counts, and costs
little: −4% events, −5% detections.

### 2.3 What stricter rules would change (re-clustered with `haze.cluster`, exact)

Season totals (Indonesia, static masked). "Active now" is as of the last detection in the DB
(2026: 17 Oct 12:25 UTC). Rule A is production and reproduces `fire_events` exactly
(203,890 events, 1,636,466 detections).

**2026**

| Rule | Detections | Events | Single-det. events | Active now | New today | Area (kha) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **A. current: VIIRS n+h, MODIS ≥ 30** | 1,636,466 | 203,890 | 102,694 | 2,939 | 1,614 | 11,895 |
| B. VIIRS n+h, MODIS ≥ 50 | 1,621,142 | 203,139 | 102,273 | 2,933 | 1,616 | 11,751 |
| C. VIIRS n+h, MODIS ≥ 80 | 1,562,468 | 197,025 | 98,751 | 2,916 | 1,623 | 10,790 |
| D. VIIRS n+h only, no MODIS | 1,523,800 | 195,627 | 97,829 | 2,900 | 1,621 | 10,563 |
| E. VIIRS high + MODIS ≥ 80 ("SiPongi tinggi") | 94,749 | 27,676 | 16,389 | 223 | 157 | 1,755 |
| Z. everything, including low | 1,729,545 | 211,714 | 106,362 | 3,118 | 1,736 | 12,465 |
| A + event needs ≥ 2 detections | 1,533,772 | 101,196 | 0 | 1,804 | 614 | 9,731 |
| A + event needs ≥ 2 overpasses | 1,487,000 | 80,693 | 0 | 1,483 | 323 | 8,697 |
| **A + "strong" tier (§3.1)** | 1,549,711 | 117,135 | — | — | — | — |

**2019 and 2023** (end of season)

| Rule | 2019 events | 2019 single | 2023 events | 2023 single |
| --- | ---: | ---: | ---: | ---: |
| A. current | 160,404 | 92,259 | 144,565 | 85,955 |
| C. MODIS ≥ 80 | 155,249 | 90,046 | 139,332 | 83,950 |
| D. VIIRS only | 154,860 | 90,101 | 138,894 | 84,000 |
| E. "SiPongi tinggi" | 16,895 | 10,256 | 12,776 | 8,446 |
| A + ≥ 2 detections | 68,145 | — | 58,610 | — |
| A + ≥ 2 overpasses | 46,030 | — | 37,669 | — |
| A + "strong" tier | 80,437 | — | 67,888 | — |

What the tables say:

- **The MODIS threshold barely matters.** MODIS ≥ 50 changes events by −0.4%, and ≥ 80 by −3%.
  93.4% of MODIS detections in 2026 (92.0% in 2019, 86.4% in 2023) are within 1 km and 60 min of a VIIRS detection.
  MODIS mostly duplicates VIIRS. The exception is 10,879 MODIS-only events in 2026.
- **"VIIRS high only" would be a mistake.** It keeps 5.8% of detections and 13.6% of events. It
  keeps only the hottest (saturated) fires and would drop most smouldering peat fires.
- **Single detections are the big lever.** They are 50% of events in 2026, 58% in 2019 and 59% in
  2023, but only 6.3%, 10.7% and 18.4% of detections. **86% are daytime**, and 98% are nominal.
  Their median FRP is 4.0 MW, against 4.7 MW for all detections, so they are small but not
  implausible. Many are real small agricultural or clearing fires seen on one overpass. Some
  fraction are the daytime commission errors in §1.2. We cannot tell which without ground truth.
- **Repeat detection** (≥ 2 overpasses) cuts events by 60% but keeps 91% of detections and 73%
  of area. It also drops real short fires. ≥ 2 detections in one overpass (adjacent pixels) is
  also good evidence: Schroeder's low class is defined on *stand-alone* pixels. Night detections
  carry negligible commission (Schroeder 2014; Giglio 2016).

### 2.4 Single-detection events

| | 2019 | 2023 | 2026 |
| --- | ---: | ---: | ---: |
| Events | 160,404 | 144,565 | 203,890 |
| Single-detection | 92,259 (58%) | 85,955 (59%) | 102,694 (50%) |
| … of which a single daytime non-saturated pixel | 79,967 | 76,677 | 86,755 |
| Events with ≥ 2 detections but one overpass | 22,115 | 20,941 | 20,503 |
| Size buckets (2026) | 1: 102,694 · 2: 38,331 · 3–4: 28,269 · 5–9: 18,592 · 10–49: 12,888 · 50+: 3,116 | | |

Of the 6,627 live events (active + cooling) in 2026, **2,721 (41%) are single detections**.
Single-detection events get no event page (`publish_season`), but they are counted in
"Aktif", "Baru hari ini", "Kebakaran musim ini" and the province table.

### 2.5 Double counting across satellites

**Within an event, counts are fine.** Single linkage merges S-NPP, NOAA-20, NOAA-21, Terra and
Aqua detections of the same fire into one event. `est_area_ha` already counts unique 375 m
cells. But `hotspot_count`, `season_hotspots`, `daily[].hotspots`, `by_provinsi.hotspots`,
History `n` and region `h24/d7` are **raw detection counts**. One burning 375 m cell gives up to
~6–10 detections a day: three VIIRS satellites × 2 passes, plus Terra and Aqua, plus overlap
between adjacent orbits, which VIIRS has at ~15% at the equator ([VIIRS UG][viirs-ug]).

Measured on events, Jul 1 – Oct 16 of each year:

| Metric | 2019 | 2023 | 2026 | 2026 / 2019 |
| --- | ---: | ---: | ---: | ---: |
| All detections (what History shows) | 638,816 | 332,755 | 1,545,604 | **2.42** |
| S-NPP detections (season chart) | 288,448 | 151,626 | 476,413 | **1.65** |
| NOAA-20 detections | 289,445 | 148,060 | 482,513 | **1.67** |
| Unique VIIRS 375 m cell-days, all satellites | 449,558 | 257,175 | 994,429 | 2.21 |
| Unique 1 km cell-days, all VIIRS | 268,855 | 182,828 | 573,965 | 2.13 |
| Unique S-NPP 375 m cell-days | 258,337 | 141,726 | 432,340 | 1.67 |
| Event-days | 142,967 | 120,718 | 267,197 | 1.87 |

- Two independent single sensors, S-NPP and NOAA-20, agree at 1.65–1.67×. **That is the real
  change in fire activity.** Raw counts overstate it by ~47% (2.42 / 1.65).
- **Unique-pixel metrics are not satellite-robust.** All-satellite cell-days still give 2.21×.
  Extra overpasses at other times catch extra fires and cells, and geolocation jitter spreads
  one fire over neighbouring cells. Raw VIIRS detections per S-NPP detection were 2.00 (2019),
  1.99 (2023) and 3.04 (2026). Detections per unique (event, day, 375 m cell) were 1.26 (2019), 1.16 (2023)
  and 1.43 (2026).
- **The only robust family is a per-satellite count.** That is S-NPP alone, or better, the
  *mean over available VIIRS satellites per day*. The mean matches S-NPP within 0.3% in 2019
  (311,879 vs 311,408 to 16 Oct) and 2023 (165,736 vs 166,252).
- **S-NPP has gaps in 2026.** There is no S-NPP data on **44 WIB days**, including 29 Apr – 2 Jun
  and **11–16 Jul**, in the fire season. On those days the season chart's 2026 curve is flat.
  The per-satellite mean fills them: +8,289 detections, 1.7% of the cumulative total, all
  concentrated in those weeks.
- The dashboard already uses S-NPP for the season chart (README). But the History chart
  ("Titik api harian", `history.summary.days[].hotspots`), the dashboard `daily[1]` column, the
  region tables and `season_hotspots` all use raw counts. The History note says "satu lokasi bisa
  terhitung beberapa kali", which is true, but the chart is still read as a trend.

### 2.6 Static mask

- In 2026, 64,177 of 1,793,722 Indonesian detections (**3.58%**) are masked: recurrent 44,591,
  industrial 14,584, volcano 3,314, offshore 1,688. VIIRS 3.62%, MODIS 3.06%. In 2019 the
  share was 4.2% (VIIRS) and in 2023 8.6%. A quieter fire season means a larger static share.
- **The mask does not see 2026.** It was derived from the 2019, 2023, 2024 and 2025 archives.
  Running `mask.recurrent_cells` on 2026 finds **562 persistent cells, 163 of them not in the
  mask**. Within 750 m of those cells are 6,837 detections. They touch **685 events**, and 672
  of those have ≥ 50% of their detections there. Main clusters: Tapin (2,444 detections) and
  Hulu Sungai Selatan and Tanah Bumbu, all coal mining areas in Kalimantan Selatan; Lahat and
  Muara Enim (coal); Kutai Timur; Balikpapan and Indramayu (refineries); Cilegon and Serang
  (heavy industry); Morowali (nickel); Surabaya. With 2026's shorter year relaxed to ≥ 20 days
  over ≥ 4 months, 287 new cells appear.
- **Example.** Near Binuang, Tapin (−3.085, 115.12) there were 2,284 detections on 181 days
  in 2026, of which only 570 are masked. The site was also persistent in 2015, 2019 and 2023.
  It produced `tapin-20260702-1` (1,218 detections, 368 overpasses, rank #111 of 203,890 by size)
  and `tapin-20260920-1`, which is **active** on the live map now. Both have `near_static=True`,
  but they still count as fires everywhere. Possibly coal-seam or stockpile fires, which are
  real combustion but not karhutla. This needs a manual look.
- Nickel smelter complexes are mostly masked: IMIP Morowali 3,281 of 3,736 nearby detections,
  IWIP Weda Bay 5,555 of 6,030, VDNI Konawe 4,855 of 5,042. Their unmasked edges (~10%) leak
  into events, and new lines will keep appearing.
- `near_static` uses only the event *centroid* within 2 km (927 events in 2026, 36 live). It is
  only a flag. These events still count in every headline.

### 2.7 Data caveat

The audit DB copy holds **2026 only** (Jan 1 – Oct 17). The 2019 and 2023 numbers come from the
local `data/haze.duckdb`, opened read-only. It has 2015 and 2019–2025, and no NOAA-21 in 2023.
Scripts are in the session scratchpad (`aq/rules.py`, `aq/tier.py`, `aq/newstatic.py`, `aq/*.sql`).

---

## 3. Recommended rules

### 3.1 Two event tiers

Compute these per event from its member hotspots in `events.summarise`. They are a pure
function of the members, so the incremental rebuild stays exact.

| Tier | Rule | 2026 events | Share of detections |
| --- | --- | ---: | ---: |
| **`strong`**: "Terdeteksi kuat" / "Strong detection" | Nominal or high detections (current eligibility) **and** any of: (a) seen on ≥ 2 distinct overpasses (satellite + acq_time); (b) ≥ 2 detections in one overpass (adjacent pixels); (c) any night detection; (d) any saturated VIIRS pixel (`h`) | 117,135 (57%) | 94.7% |
| **`single`**: "Deteksi tunggal — belum terverifikasi" / "Single detection, unverified" | Everything else: one daytime nominal pixel, seen once | 86,755 (43%) | 5.3% |
| **`industrial`**: "Kemungkinan sumber panas industri" / "Possible industrial heat" | `near_static` (centroid ≤ 2 km of a static source) **or** ≥ 50% of detections within 750 m of a rolling-mask candidate (§3.3) | ~1,600 | <1% |

Why each part of the rule:

- (a) Repeat detection: Sofan 2020 and Indradjad 2023 recommend it, and so does the GOES FAQ
  advice to look for coincident detections ([FIRMS FAQ][firms-faq]).
- (b) The VIIRS low class is defined for stand-alone pixels (Schroeder 2014), so contiguous
  pixels are already more credible.
- (c) No night commission was found by Schroeder 2014 or Giglio 2016.
- (d) Saturation needs a very hot source.

`single` events stay in the data and on the map as faint dots, and in exports with their tier.
They leave every headline number. A `single` event less than ~13 h old is "pending": the next
overpass can upgrade it. Label it "baru, menunggu lintasan berikutnya" (new, waiting for the next
pass) rather than hiding it.

Effect on live headlines (2026, at 17 Oct 12:25 UTC): live events go from 6,627 to 4,542 strong.
"Active" goes from 2,939 to roughly 1,500–2,200, depending on pending handling: 1,483 with a
strict ≥ 2-overpass rule. "New today" goes from 1,614 to roughly 323–600.

**Confidence thresholds: keep them as they are.** VIIRS n+h, MODIS ≥ 30. Do not adopt "high
only" (§2.3). Optionally drop MODIS-only *single* events. They are already `single` unless at
night or multi-pixel.

### 3.2 Satellite-robust metrics

| Use | Metric | Why |
| --- | --- | --- |
| Season-vs-baseline chart, History chart, cross-year text | **VIIRS per-satellite mean** per WIB day (mean over S-NPP / NOAA-20 / NOAA-21 present that day), strong-tier events only | Matches S-NPP within 0.3% when all are up. Fills S-NPP outages (44 days in 2026). Does not jump when a satellite is added. |
| "How much is burning today" | **Unique 375 m fire cells per day** (VIIRS, strong tier) | Close to "burning area today". Fine within a season, but **not** for comparing years (§2.5). |
| Fires | **Strong-tier events**: active, new today, season | What a reader means by "a fire". |
| Official reconciliation | **"Setara SiPongi"**: VIIRS `h` + MODIS ≥ 80, S-NPP + NOAA-20 + Terra + Aqua, last 24 h | Lets a journalist match Kemenhut's quoted number. Label it plainly and do not headline it. |
| Raw detections | Keep in exports and tables, labelled "deteksi satelit (mentah)" | Transparency. Never as a trend. |

### 3.3 Static mask

1. Re-run `haze static-mask` with 2026 included.
2. Add a **rolling live check**: `recurrent_cells` on the trailing 365 days, every daily run.
   Write candidates to a `static_candidates` table that feeds the `industrial` tier, not the hard
   mask. A human promotes candidates into `static_sources_manual.csv`, so that real recurring
   peat fires are not silently removed.
3. Seed the manual list from VIIRS Nightfire flare sites and known smelter, refinery and cement
   coordinates.

### 3.4 UI wording

**Rename "Titik api" → "Titik panas"** everywhere in `i18n.ts` (id). "Titik api" reads as a
confirmed fire. Kemenhut, BRIN and the regulation use "titik panas". English stays "hotspot".

Info text (dashboard "?" and History note), Bahasa:

> **Titik panas bukan berarti kebakaran.** Satu titik panas adalah satu piksel citra satelit
> (sekitar 375 × 375 m untuk VIIRS, 1 × 1 km untuk MODIS) yang jauh lebih panas daripada
> sekelilingnya. Satu kebakaran bisa muncul sebagai puluhan titik panas, dan lokasi yang sama bisa
> terdeteksi beberapa kali sehari oleh satelit yang berbeda. Panas dari pabrik, tambang, suar gas,
> dan gunung api juga bisa terdeteksi; sebagian sudah kami saring. Sebaliknya, api kecil, api di
> bawah awan atau asap tebal, dan gambut yang membara di bawah permukaan bisa tidak terlihat.
> Kebenaran di lapangan hanya bisa dipastikan lewat pengecekan langsung (groundcheck).

English:

> **A hotspot is not the same as a fire.** Each hotspot is one satellite pixel (about 375 × 375 m
> for VIIRS, 1 × 1 km for MODIS) that is much hotter than its surroundings. One fire can show up
> as dozens of hotspots, and the same spot can be seen several times a day by different
> satellites. Heat from factories, mines, gas flares and volcanoes can also be detected; we filter
> out the known ones. Small fires, fires under cloud or thick smoke, and peat smouldering below
> the surface can be missed. Only a check on the ground can confirm a fire.

Tier labels:

| Key | id | en |
| --- | --- | --- |
| strong | Terdeteksi kuat — terlihat di beberapa lintasan satelit, beberapa piksel, atau malam hari | Strong detection — seen on several satellite passes, several pixels, or at night |
| single | Deteksi tunggal — satu piksel siang hari, belum terverifikasi | Single detection — one daytime pixel, not yet verified |
| pending | Baru — menunggu lintasan satelit berikutnya | New — waiting for the next satellite pass |
| industrial | Kemungkinan sumber panas industri, bukan karhutla | Possibly industrial heat, not a land fire |

Note next to the official comparison:

> **Mengapa angka kami berbeda dengan SiPongi?** Angka resmi Kemenhut yang sering dikutip hanya
> menghitung titik panas "kepercayaan tinggi", yaitu piksel yang sangat panas sampai sensor
> satelit jenuh, dari empat satelit. Itu hanya sekitar 5–10% dari semua deteksi. Kami memakai semua
> deteksi kepercayaan sedang dan tinggi sesuai anjuran NASA, dari lima satelit, lalu
> mengelompokkannya menjadi lokasi kebakaran. Kedua angka sah, tetapi mengukur hal yang berbeda.

> **Why do our numbers differ from SiPongi?** The official figure most often quoted by the
> Ministry of Forestry counts only "high confidence" hotspots: pixels so hot that the sensor
> saturates, from four satellites. That is only about 5–10% of all detections. We use all
> nominal- and high-confidence detections, as NASA recommends, from five satellites, and group
> them into fire locations. Both numbers are valid; they measure different things.

Season chart note (replace `seasonNote`): "Rata-rata titik panas per satelit VIIRS, agar adil
dibandingkan antartahun meski jumlah satelit bertambah." / "Hotspots per VIIRS satellite
(average), so years compare fairly even as satellites are added."

---

## 4. Code changes

| File · function | Change |
| --- | --- |
| `config.py` | Add `TierParams(min_passes=2, min_pixels_per_pass=2, night_strong=True, saturated_strong=True, pending_hours=13)` and `TIER = TierParams()`. |
| `events.summarise` | Per event, add `n_passes` (unique `satellite`+`acq_time`), `n_satellites`, `max_pixels_per_pass`, `has_night`, `has_saturated` and `n_cells` (unique 375 m cells). Derive `tier` ∈ {strong, single, industrial}. `eligible` must also select `satellite, daynight`. |
| `db.SCHEMA` / `db.connect` | Add `ALTER TABLE fire_events ADD COLUMN IF NOT EXISTS tier VARCHAR`, plus `n_passes INTEGER`, `n_cells INTEGER`. Add a `static_candidates` table. |
| `publish.EVENT_PROPS`, `LIVE_COLUMNS` | Add `tier`, `n_passes`, `n_cells`. |
| `publish.dashboard` | Compute `counts.active / cooling / new_today / season_events` and `by_provinsi` from `tier == 'strong'`. Add a `counts.possible` block (single + pending + industrial). Replace `season_hotspots` with `season_fire_cells`. Add `sipongi_equiv_24h`. |
| `publish.daily_counts` / `write_baselines` | Add `viirs_mean` (mean of per-satellite VIIRS counts per WIB day, strong events) and `cells` (unique 375 m cell-days). Baselines use `viirs_mean`, replacing `snpp`. Regenerate `static/season_baselines.csv`. |
| `history.daily_fires` | Add `AND in_indonesia AND confidence IN ('nominal','high')`, or better `event_id IS NOT NULL`. Add a `tier` filter and emit a per-day `viirs_mean` for `summary.days[].hotspots`. |
| `publish.tables` | Add `AND confidence IN ('nominal','high')` to the `det` and `daily` queries, and count `active` / `season_fires` from strong events. |
| `publish.recent_hotspots` | Add the event's `tier` to each row, so the map can draw `single` dots faintly. |
| `mask.recurrent_cells` + `pipeline` / `cli run` | Run a daily trailing-365-day recurrence. Write `static_candidates`, and feed it to the `industrial` tier and to `near_static`, using a detection share as well as the centroid. Re-run `haze static-mask` with 2026. |
| `web/src/i18n.ts` | Rename "Titik api" → "Titik panas". Add the texts in §3.4. Change `seasonNote`. |
| `web` Dashboard / MapView / EventPanel | Show the tier badge. Make headline KPIs strong-only, with a muted "+N deteksi tunggal" line. Draw single and industrial events in a distinct muted style. Add the SiPongi comparison note. |
| `docs` / README | Document the tiers and the metric definitions. |

[viirs-ug]: https://www.earthdata.nasa.gov/s3fs-public/2025-06/VIIRS_C2_AF-375m_User_Guide_1.2.pdf
[s14]: https://doi.org/10.1016/j.rse.2013.12.008
[modis-ug]: https://earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf
[firms-faq]: https://www.earthdata.nasa.gov/data/tools/firms/faq
[arxiv-low]: https://arxiv.org/pdf/2510.26816
[c14]: https://doi.org/10.1002/2013JD020453
[g16]: https://doi.org/10.1016/j.rse.2016.02.054
[s16]: https://doi.org/10.1016/j.rse.2015.08.032
[s08]: https://doi.org/10.1016/j.rse.2008.01.005
[t08]: https://doi.org/10.1029/2008JD010717
[sofan]: https://doi.org/10.1080/17538947.2020.1791268
[indr]: https://doi.org/10.3390/fire7010009
[vl18]: https://doi.org/10.3390/rs10070978
[liu20]: https://doi.org/10.1016/j.rse.2019.111557
[w18]: https://doi.org/10.3390/rs10040495
[lo18]: https://doi.org/10.1111/gcb.13841
[nf13]: https://doi.org/10.3390/rs5094423
[nf16]: https://doi.org/10.3390/en9010014
[gfw-ds]: https://hub.arcgis.com/datasets/gfw::viirs-active-fires
[gfw-blog]: https://globalnaturewatch.org/blog/data/fighting-fires-with-satellites-viirs-fire-data-now-available-on-global-forest-watch/
[gfw-trends]: https://globalnaturewatch.org/blog/data-and-tools/wildfire-trends-gfw-fire-data/
[kemenhut]: https://www.kehutanan.go.id/news/cek-informasi-terbaru-karhutla-kemenhut-di-sini
[detik799]: https://news.detik.com/berita/d-8709594/kemenhut-deteksi-799-hotspot-karhutla-kalteng-terbanyak
[fin]: https://news.fin.co.id/2026/10/16/titik-hotspot-tembus-20334-titik-dalam-sehari-dpr-minta-pemerintah-cegah-karhutla-meluas
[klhk16]: https://rfmrc-sea.org/wp-content/uploads/2015/01/Analisis-Data-Titik-Panas-Hotspot-dan-Areal-Kebakran-Hutan-dan-Lahan-Tahun-2016.pdf
[p32]: https://peraturan.bpk.go.id/Download/357647/Permen%20LHK%20Nomor%20P%2032%20Tahun%202016.pdf
