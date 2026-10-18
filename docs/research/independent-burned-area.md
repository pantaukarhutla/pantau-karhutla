# Research: an independent burned-area estimate with confidence intervals

Compiled 2026-10-17. This note designs and prototypes a burned-area figure that the site can publish
**without relying on official numbers**. The figure is validated against independent remote sensing:

- a **stratified random sample** of points (Olofsson et al. 2014);
- **reference labels** from Sentinel-2, Landsat 8/9 and Sentinel-1 radar, read keyless;
- the **error-adjusted area estimator** with a 95% confidence interval (CI);
- the **user's and producer's accuracy** of our own detection map.

The prototype covers Central Kalimantan (Kalimantan Tengah) in 2019 and in 2026 up to 17 Oct.

A separate audit, [audit-burned-area.md](audit-burned-area.md), covers the current `est_area_ha`
pixel-count method and calibrates it to KLHK. This note does not repeat that work. Its estimate uses no
official number at any step; the KLHK figures appear only for context.

How each claim was checked:

- **[T]** tested from this container on 2026-10-17 (HTTP calls, reads, code runs).
- **[D]** computed by us from data, with the scripts listed in §9.
- **[V]** read in the source's own text (abstract, data record or documentation page).
- **[S]** search snippet or secondary summary only.
- **[M]** from memory; check before relying on it.

---

## 1. Headline numbers (prototype)

Central Kalimantan (15.45 M ha province polygon from our `regions` table), area burned during the
season:

| Season | Our independent estimate | 95% CI (sampling + label error) | 95% CI (sampling only) | Points |
| --- | --- | --- | --- | --- |
| **2019** (Aug–Dec, post-season imagery) | **≈ 650,000 ha** | **390,000 – 950,000 ha** | 564,000 – 863,000 ha (714,000 ha before label correction) | 700 |
| **2026 to 17 Oct** (season still burning) | **≈ 660,000 ha** | **370,000 – 1,060,000 ha** | 689,000 – 1,160,000 ha (924,000 ha before label correction) | 700 |

The same 2019 numbers set against independent products and the official figure **[D]**:

| Central Kalimantan 2019 | ha | Source |
| --- | --- | --- |
| **This estimate (rule H, label-corrected)** | **649,000 (389,000–952,000)** | §4 |
| Same 700 points labelled with the Gaveau et al. 2021 map instead | 548,000 (417,000–679,000) | §4.5, an estimator check |
| Gaveau et al. 2021 Sentinel-2 map, wall-to-wall | 473,000 | their Zenodo map, clipped by us |
| MODIS MCD64A1 C6.1 | 518,000 | Planetary Computer COGs, clipped by us |
| ESA FireCCI S311 v1.1 (Sentinel-3, 300 m) | 626,000 | CEDA 0.25° grid, apportioned by area overlap |
| *KLHK / SiPongi (official, context only)* | *317,749* | `audit/sipongi_prov.csv` |
| Our detection footprint (cells holding ≥1 VIIRS detection) | 793,000 | stratum 1 |

**For 2026**, the official SiPongi figure for Central Kalimantan is 7,634 ha (data entered to July
2026, see the audit). The 639 ha the president was reportedly told cannot be squared with any
satellite source:

- **MCD64A1 alone** maps 100,600 ha by the end of August **[D]**, before September and October,
  which hold most of the season's detections.
- **The lower bound of our CI** (370,000 ha) is about 50× the official figure and about 580× the
  639 ha.

Reading the numbers:

- **2019.** Our estimate lies inside the spread of the independent products (470,000–630,000 ha), a
  little above them. All the independent products agree the official figure is too low, by
  1.5–2× (Gaveau et al. 2021 report the same nationally: 3.11 M ha vs 1.64 M ha official).
- **2026.** The estimate is provisional. Its imagery stops on 14–16 Oct while fires are still
  burning, so it is closer to "burned so far and already visible to satellites" than to a season
  total. §5 has the caveats.
- **Feasibility.** Automating this is feasible: a province-season takes about 10–20 min of I/O on
  keyless services (§7). The CI is wide **because the labels are automated**. Label error, not
  sample size, now drives the width (§6).

---

## 2. Data access, tested keyless

| Source | Endpoint | Result | Use |
| --- | --- | --- | --- |
| Sentinel-2 L2A Collection 1 | Earth Search STAC `https://earth-search.aws.element84.com/v1`, collection `sentinel-2-c1-l2a`; COGs on `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com` | Works keyless **[T]**. Bands carry `scale 0.0001, offset −0.1` in `raster:bands` (baseline 05.00 reprocessing, also for 2019) **[T]** | NBR from B8A/B12 at 20 m, SCL mask |
| Sentinel-1 GRD | Earth Search `sentinel-1-grd` | Catalogue works, but the assets are `s3://sentinel-s1-l1c/…`, a **requester-pays** bucket **[T]**, so it is not keyless | Not used |
| **Sentinel-1 RTC** (gamma0, radiometric terrain-corrected, 10 m) | Planetary Computer (PC) STAC `https://planetarycomputer.microsoft.com/api/stac/v1`, `sentinel-1-rtc`; blobs on `sentinel1euwestrtc.blob.core.windows.net` | Works with **anonymous SAS tokens** from `…/api/sas/v1/token/{account}/{container}` **[T]**. 2019: S1A. 2026: S1A + S1D, last scene 16 Oct 2026 (one day before the test) **[T]** | VV/VH change |
| Landsat 8/9 C2 L2 | Earth Search `landsat-c2-l2` points at requester-pays `s3://usgs-landsat` **[T]**. **PC `landsat-c2-l2`** works with SAS **[T]** | PC used | NBR from SR_B5/SR_B7, QA_PIXEL mask |
| MODIS MCD64A1 C6.1 | PC `modis-64A1-061` | The **collection** token (`/token/modis-64A1-061`) returns **403** on the COG container; the **account/container** token (`/token/modiseuwest/modis-061-cogs`) works **[T]** | Comparison |
| FireCCI S311 v1.1 grid | `https://dap.ceda.ac.uk/neodc/esacci/fire/data/burned_area/Sentinel3_SYN/grid/v1.1/2019/` | 2 MB/month NetCDF, keyless **[T]** | Comparison |
| Gaveau et al. 2021 map + expert reference points | Zenodo record 4551243 (73 MB zip + 31 kB reference points, CC BY 4.0) | **[T]** | Comparison, and the label-error model |

**SAS signing.** PC hands out tokens per storage account and container. Signing with the collection
token failed for MCD64A1 COGs. The prototype's `pcsign.py` asks `/token/{account}/{container}` for
each blob host and caches the token for 45 min. That mirrors `planetary_computer.sign`, without the
dependency.

**Cloud and smoke (2019 vs 2026).** SCL classes 2, 4, 5 and 6 count as clear; class 2 ("dark
area") is often a burn scar. A point needs ≥ 6 of 9 clear pixels in a 3×3 window. With that rule:

- **2019** (post-window 1 Oct 2019 – 29 Feb 2020): ≥ 95% of points had at least one clear optical
  pre- and post-season observation in every stratum **[D]**.
- **2026** (post-window 1 Sep – 17 Oct, mid-season): 85–96% did **[D]**. That is better than the
  scene-level cloud cover in [data-gis-layers.md](data-gis-layers.md) suggests. A point needs only
  one clear 60 m window, not a clear scene.

The remaining 4–15% had radar only.

---

## 3. Method

### 3.1 The map and the strata

The **map** being assessed is our detection footprint, as `events.area_by` counts it. A 0.0034° grid
cell (~14.3 ha) is "map burned" when it holds at least one eligible VIIRS detection in the season:

- nominal or high confidence;
- not static;
- WIB calendar year.

Strata, rasterised on the same grid inside the province polygon (`strata.py`):

| # | Stratum | 2019 area (ha) | 2026 area (ha) |
| --- | --- | --- | --- |
| 1 | Map burned: cell with ≥ 1 detection | 792,896 | 1,545,109 |
| 2 | Near ring: cell centre ≤ 0.8 km from a stratum-1 cell (1–2 cells out) | 1,845,301 | 2,345,665 |
| 3 | Far ring: 0.8–2 km | 3,649,391 | 3,692,882 |
| 4 | Rest of KHG 2017 peat units | 2,274,164 | 1,779,533 |
| 5 | Rest of the province | 6,892,361 | 6,090,924 |

Why the strata differ from the suggested "(a) within 375 m, (b) 375 m–2 km":

- **Stratum 1 is our published map**, so its user's accuracy (UA) is the UA of what we publish. A
  375 m buffer around each detection would be 44 ha per isolated detection, three times the cell
  area.
- **A single 375 m–2 km ring is too big.** Season detections are scattered, so that ring covers 36%
  of the province (5.5 M ha) at a low burned share. Splitting it at 0.8 km isolates the band where
  most omission sits:
  - the Gaveau map puts 6.9% of the near ring burned, but only 0.35% of the far ring **[D]**;
  - all 92 expert-labelled burned sites in the province lie in strata 1–2 **[D]**.

### 3.2 Sampling design

The sample is a stratified random sample of cells, with one uniformly random point inside each
cell. The cells are near-equal-area (the area varies < 0.2% across the province). Two draws were
taken per season (`sample.py`):

| Draw | Allocation (strata 1–5) | Points | Seed |
| --- | --- | --- | --- |
| Pilot | 60 / 60 / 60 / 60 / 60 | 300 | = year |
| Main add-on | 140 / 140 / 90 / 15 / 15 | 400 | year + 1000 |
| **Union** | **200 / 200 / 150 / 75 / 75** | **700** | |

The union is still a stratified simple random sample within each stratum.

The add-on moves points toward the Neyman allocation `n_h ∝ A_h·√(p_h(1−p_h))`. The prior `p_h`
was the Gaveau-map burned share in each 2019 stratum, which gives roughly 32/39/18/5/6%. The add-on
still keeps ≥ 75 points in each background stratum, for the reason below.

**Design check.** We ran the estimator with the Gaveau map as "truth" at the 700 points. It gives
548,000 ha (417,000–679,000) **[D]**. The map's own wall-to-wall area is 473,000 ha, which lies
inside that CI. One run cannot prove the design unbiased, but the result is consistent with it and
shows the code works.

**Small strata cost the most.** The standard variance formula gives zero variance in a stratum with
no burned sample points. For stratum 5 in 2019 (0 of 75), the exact one-sided 95% upper bound is
270,000 ha (`A_h·(1 − 0.05^(1/n))`) **[D]**. Automated labels make points cheap, so production
should put several hundred points into strata 3–5 (§7).

### 3.3 Response design: automated reference labels

This step is a **proxy for visual interpretation** (§6). Each point gets three kinds of evidence
(`fetch.py`, `features.py`):

| Evidence | Pre-season window | Post-season window | Per-point feature |
| --- | --- | --- | --- |
| **Optical NBR** = (NIR − SWIR2)/(NIR + SWIR2), S2 (B8A, B12) and L8/9 (SR_B5, SR_B7) pooled, 3×3 window mean | 2019: 1 Apr–31 Jul. 2026: 1 Apr–20 Jul | 2019: 1 Oct 2019–29 Feb 2020. 2026: 1 Sep–17 Oct | `pre` = median of clear pre-season NBR. `post` = **second-lowest** clear post-season NBR among observations whose SWIR2 did not fall (burns raise SWIR2; shadow and water lower it). Use the lowest if only one exists. `dNBR = pre − post` |
| **SAR** Sentinel-1 RTC gamma0 VV and VH, 5×5 window (50 m) mean in linear units | 2019: 1 May–31 Jul. 2026: 1 May–20 Jul | 2019: 1 Oct–31 Dec. 2026: 1 Sep–17 Oct | Per relative orbit: mean dB post − mean dB pre. Then subtract that orbit's median change over background points (strata 4–5) to remove season-wide drying or wetting. Average over orbits → `ΔVH`, `ΔVV` |

Choices made after looking at the data:

- **Second-lowest post-season NBR**, not the median. Burned degraded peat regrows ferns fast. Expert-burned sites
  went from NBR 0.3 in early November to 0.73 in February, so a median of the post-season scenes
  misses many burns.
  The lowest single value was too noisy (specificity 0.52 at dNBR ≥ 0.1). The second-lowest needs
  two observations that agree **[D]**.
- **Season offset.** The 2026 background points have a median dNBR of 0.093, against 0.068 in
  2019. This is drought and smoke. The 2026 dNBR is shifted down by the difference (0.03) before
  the Key & Benson thresholds are applied.
- **SAR threshold by "Gaussian thresholding"** (supervised minimum-error form, Kittler & Illingworth
  1986):
  - fit one Gaussian to ΔVH at points that optical confidently calls burned (adjusted dNBR ≥ 0.44)
    and one to points it confidently calls unburned (< 0.10);
  - set the threshold where the two densities cross, with equal priors;
  - this is re-fitted every season.

  | Season | Burned ΔVH (dB) | Unburned ΔVH (dB) | Threshold |
  | --- | --- | --- | --- |
  | 2019 | −1.33 ± 1.20 (n = 104) | −0.07 ± 0.53 (n = 374) | −0.79 dB |
  | 2026 | −2.50 ± 1.92 (n = 52) | −0.21 ± 0.80 (n = 373) | −1.37 dB |

  These follow the burned-forest decrease reported for C-band (Lohberger et al. 2018; Belenguer-Plomer
  et al. 2019; Tanase et al. 2020). In 2019, VV separated worse than VH (§4.4).

**Label rules.** Key & Benson (2006) dNBR classes are: low severity 0.10–0.27, moderate-low
0.27–0.44, moderate-high ≥ 0.44. "S" means ΔVH ≤ the season's SAR threshold.

| Rule | Burned if |
| --- | --- |
| O27 | dNBR ≥ 0.27 |
| O44 | dNBR ≥ 0.44 |
| O44\|O27&S | dNBR ≥ 0.44, or (dNBR ≥ 0.27 and S) |
| **H (primary)** | strata 1–2: as O44\|O27&S. Strata 3–5 (no detection within 2 km): **dNBR ≥ 0.27 and S**, so a burn away from any detection needs two independent sensors to agree |
| SAR fallback (no clear optical) | S |

Why rule H. In 2019, five stratum-4 peat points had dNBR ≥ 0.44 but no detection within 2 km, no
MCD64A1 burn and no Gaveau burn.

- **Four of them** (near −3.3°, 112.0°E, coastal Katingan/Seruyan) showed **rising** VH. That points
  to seasonal senescence or flooding, not fire.
- **One** (−3.05°, 114.20°E) had ΔVH −2.5 dB and stays burned under H **[D]**.

One positive in stratum 4 is worth 30,000 ha, so requiring agreement there matters. The rule was
chosen after seeing these points. §6 covers what that does to the CI.

### 3.4 Label-error model and correction

The label-error model comes from Gaveau et al. (2021). They visually interpreted 1,298 reference
sites in 2019, each labelled by three analysts with disagreements dropped. 268 of those sites fall in
Central Kalimantan: 92 burned, 176 unburned. We ran our labeller on them (`gaveau_ref_ck.parquet`).
They spread across our 2019 strata as follows:

- strata 1–2: 92 burned, 44 unburned;
- strata 3–5: 0 burned, 132 unburned.

The error rates are computed per stratum group, because specificity differs near and far from
detections:

| Rule | Sensitivity (near) | Specificity (near, strata 1–2) | Specificity (far, strata 3–5) |
| --- | --- | --- | --- |
| O27 | 0.87 (80/92) | 0.89 (39/44) | 0.96 (127/132) |
| O44 | 0.66 (61/92) | 0.98 (43/44) | 1.00 (132/132) |
| **H** | **0.74 (68/92)** | **0.93 (41/44)** | **0.98 (130/132)** |
| SAR only (ΔVH ≤ −0.79 dB) | 0.60 | 0.87 (all points) | |

The overall accuracy of rule H against the expert labels is 0.89.

The label-corrected estimate is a Monte Carlo of 4,000 draws (`estimate.label_error_mc`). Each
draw:

1. bootstraps the points within each stratum (sampling error);
2. draws sensitivity Se and specificity Sp from Jeffreys Beta posteriors of the counts above. One
   draw is shared by every stratum in a group, so errors are correlated;
3. corrects each stratum's burned share with Rogan–Gladen, `p = (p_obs + Sp − 1)/(Se + Sp − 1)`,
   clipped to [0, 1];
4. sums `A_h·p`.

The reported value is the median, with the 2.5–97.5 percentiles as the CI. Sensitivity in strata
3–5 is borrowed from strata 1–2, because no expert-burned site lies there.

### 3.5 Estimators

The strata are not the map classes: strata 2–5 are all "map unburned". So the estimators are those
of Stehman (2014). They reduce to Olofsson et al. (2014) when strata and map classes coincide.
With `A_h` the stratum area, `n_h` the points in it and `y_u` the reference label (1 = burned):

- **Area.** `Â = Σ_h A_h·ȳ_h`, with `V̂(Â) = Σ_h A_h²·s²_h/n_h` and 95% CI `Â ± 1.96·√V̂`.
- **UA of the map.** `ȳ_1`, because map-burned equals stratum 1.
- **PA of the map.** The ratio `R̂ = Σ_h A_h·mean(y·m)_h / Â`, where `m` = 1 for map-burned. Its
  variance is Stehman's (2014) eq. 28.
- **Overall accuracy (OA).** The stratified mean of agreement, divided by the total area.

The code is in `estimate.py`.

---

## 4. Prototype: Central Kalimantan 2019

### 4.1 Area by rule

All 700 points were labelled: 695 from optical, 5 from SAR only **[D]**.

| Rule | Area, sampling CI (k ha) | Label-corrected (k ha) | Map UA | Map PA | Map OA |
| --- | --- | --- | --- | --- | --- |
| O27 | 1,255 (958–1,551) | 822 (478–1,252) | 0.54 | 0.34 | 0.922 |
| O44 | 669 (499–839) | 864 (563–1,231) | 0.41 | 0.48 | 0.947 |
| O44\|O27&S | 835 (646–1,024) | 785 (464–1,164) | 0.46 | 0.44 | 0.942 |
| **H** | **714 (564–863)** | **649 (389–952)** | **0.46 (0.39–0.53)** | **0.51 (0.40–0.62)** | **0.950** |

The uncorrected areas range from 669 to 1,255 k ha depending on the threshold. After correction
they converge to 650–860 k ha, which is the expected behaviour of the error model. They do not fully
agree because specificity is not the same everywhere (§6).

### 4.2 Rule H by stratum

| Stratum | Area (k ha) | n | Burned | p̂ | Estimate (k ha) |
| --- | --- | --- | --- | --- | --- |
| 1 Map burned | 793 | 200 | 92 | 0.46 | 365 |
| 2 Ring ≤ 0.8 km | 1,845 | 200 | 24 | 0.12 | 221 |
| 3 Ring 0.8–2 km | 3,649 | 150 | 4 | 0.027 | 97 |
| 4 Other peat | 2,274 | 75 | 1 | 0.013 | 30 |
| 5 Rest | 6,892 | 75 | 0 | 0 | 0 (one-sided upper 95%: 270) |

### 4.3 What this says about our detection map (2019)

- **UA ≈ 0.46.** Fewer than half the hectares in cells holding a detection were actually burned. A
  375 m pixel is often only partly burned, and VIIRS detects sub-pixel fires.
- **PA ≈ 0.51.** About half the burned area lies **outside** detection cells, mostly in the 0.8 km
  ring. These are burns between overpasses, burns under smoke or cloud, and smouldering peat.
- **The total looks right by accident.** The footprint (793,000 ha) is within about 20% of the
  estimate, but only because commission and omission errors cancel. Map pixels should not be read
  as "burned here", and a province total from the footprint is not an estimate. This agrees with
  the audit's conclusion by an independent route.

### 4.4 Label quality

- **Optical vs radar.** Over the 695 optically labelled sample points, the SAR rule agrees with rule
  H on 87%: sensitivity 0.74, specificity 0.90 **[D]**.
- **Optical vs the Gaveau map** at the same 700 points: rule H agrees on 92% **[D]**:
  - H flags 40 points burned that the map calls unburned, mostly in strata 1–2. The map's own
    producer's accuracy is 75.6% (Gaveau et al. 2021), so some of these are probably real.
  - The map flags 18 points burned that H calls unburned.
- **VV vs VH.** VV separated worse than VH in 2019: at a comparable specificity (0.98) VV
  sensitivity was 0.36 **[D]**. Rainfall in Oct–Dec brightens VV over bare and burned soil, the
  wet-soil effect reported since the ERS era.

### 4.5 Comparison with independent products

These comparisons are §1's table. Indonesia-wide, for context:

- **Gaveau et al. 2021:** 3.11 M ha from Sentinel-2, against 2.03 M ha from MCD64A1 and 1.64 M ha
  official **[V]**.
- **Our sum of FireCCI S311 v1.1 cells over Indonesia:** 3.66 M ha **[D]**.
- **Vetrita et al. 2021**, using SPOT-5 references over Indonesian peat, found MODIS products detect
  only 38–48% of burned area **[S]**. MCD64A1 therefore sits low because of omission.

---

## 5. Prototype: Central Kalimantan 2026, as of 17 Oct

| | Value |
| --- | --- |
| Our detection footprint (stratum 1) | 1,545,109 ha, from 516,509 eligible VIIRS detections (2019: 217,010) |
| Points | 700: 635 labelled from optical, 65 from SAR only |
| SAR threshold (re-fitted on 2026 points) | ΔVH ≤ −1.37 dB |
| **Rule H, sampling CI** | **924,000 ha (689,000–1,160,000)**. UA 0.33, PA 0.55 |
| **Rule H, label-corrected** | **664,000 ha (374,000–1,055,000)** |
| O44 / O27, label-corrected | 522,000 (194,000–967,000) / 713,000 (470,000–1,033,000) |
| MCD64A1, Jan–Aug only | 100,589 ha (Aug: 95,588) |
| SiPongi (official, to July) | 7,634 ha |
| Audit's KLHK-calibrated pixel model (2026 to date) | 470,000 ha (380,000–550,000), see [audit-burned-area.md](audit-burned-area.md) §1 |

Caveats specific to 2026:

1. **The season is not over.** Post-season scenes end on 14–16 Oct. Any cell that burned after its
   last clear scene is labelled unburned, so 2026 sensitivity is probably below the 2019 value of
   0.74 used in the correction. The estimate leans low. It means "burned to date and already seen".
   It should be re-run with Nov–Jan imagery for a final figure.
2. **The labels were taken mid-smoke.** SCL lets some thin smoke through as clear, and drought lowers
   NBR. The 0.03 dNBR season offset handles the average effect, not local smoke.
3. **The 2019 error model was transferred.** No 2026 expert set exists. On the 2026 points, the SAR
   and optical labels agree on 87%, as in 2019. That shows the two sensors are consistent with each
   other, not that either is right.
4. **One stratum-5 point carries 81,000 ha** (−2.44°, 111.77°E: dNBR 0.67, ΔVH −6.3 dB). It could be
   an unseen burn or land clearing. Both look the same to these indices, and only visual review can
   decide.
5. **Points labelled by SAR alone are weak evidence.** All four stratum-3 positives come from SAR
   alone, and SAR's specificity is only 0.87. The label correction takes some of that into account,
   but this is the weakest part of the 2026 number.

Even with all five caveats, every rule's lower CI bound is ≥ 194,000 ha. That is more than 25× the
official 7,634 ha.

---

## 6. What automated labels do to the CI

Olofsson et al. (2014) assume the reference labels are **correct**: the CI measures sampling error
only. Our labels are index rules, so three things change.

1. **Label error becomes a source of variance, and it dominates.**
   - 2019, rule H: the sampling-only half-width is ±150,000 ha, against roughly ±280,000 ha once
     label error is propagated.
   - With 700 points, sampling is no longer the limit. More points barely narrow the CI; better
     labels do.
2. **Bias that the correction only partly removes.** Rogan–Gladen assumes one Se/Sp pair per stratum
   group. In fact, specificity depends on the land type: the coastal false positives in §3.3 were
   absent from the expert set, whose far-strata specificity is 130/132. Strata 3–5 cover 12.8 M ha, so
   a 1-percentage-point change in far-strata specificity moves the total by about 130,000 ha.

   That is why rule H requires SAR agreement there. **The rule was chosen after looking at these
   data**, so the 2019 accuracy figures are somewhat optimistic. A 50/50 split of the expert points
   would make this rigorous. It was not done, because 92 burned points is too few to split.
3. **The reference is a proxy, not visual interpretation.** The expert set is itself a reference
   built from Sentinel-2 composites. Our estimate should be called *"sample-based, with automated
   labels validated against an expert-interpreted set"*. It should not be called an
   Olofsson-compliant reference estimate until we add our own visual interpretation (§7, step 6).

The direction of the remaining error is known:

- **Too low:** fast fern regrowth, and burns after the last clear scene.
- **Too high:** clearing, flooding, drought senescence.

The UI should present the CI as the result and not lead with the point value (§7.4).

---

## 7. Production design

### 7.1 Recipe (proposed `haze burned-area --province P --season Y [--asof D]`)

1. **Strata.** Take the season's eligible VIIRS detections from DuckDB and rasterise them on the
   0.0034° grid. This is `strata.py` logic, reusing `geo.cell_keys`, `regions` and the KHG peat
   units. Write the 5 stratum areas.
2. **Sample.**
   - Use Neyman allocation with prior `p_h` from the province's previous final estimate (or 2019
     for a new province).
   - Floors: ≥ 150 points in strata 1–2 and ≥ 200 in each of strata 3–5.
   - Total about 1,000 per province-season.
   - Seed = hash(province, season, asof), stored with the output so a run can be reproduced.
3. **Fetch.**
   - S2 C1 L2A from Earth Search; Landsat 8/9 and S1 RTC from PC, signed per account and container.
     These are point window reads only (`fetch.py`: thread pool, GDAL vsicurl, `GDAL_HTTP_MAX_RETRY=6`).
   - Cache pre-season features per point in a DuckDB table `ba_obs`, so monthly runs only fetch new
     post-season scenes.
4. **Label.**
   - Features as in §3.3, the season's dNBR offset from strata 4–5, and the SAR Gaussian threshold
     re-fitted per season and province.
   - Rule H.
5. **Estimate.** Run the Stehman estimators and the label-error Monte Carlo (Se/Sp from the expert
   set, §3.4). A stratum with no burned points also reports its one-sided upper bound.
6. **Human check, small and targeted.** Export every positive point in strata 3–5, and a random 30
   from strata 1–2, to a review page: pre/post S2 SWIR-NIR-red chips plus the S1 change. Two
   reviewers label each point. Store the labels as `ba_review`. They feed back into Se/Sp and,
   once there are enough, replace the automated labels for those points.

   Strata 3–5 are where errors cost most and where positives are fewest, a handful per season. This
   is the cheapest way to turn the proxy into a proper response design.
7. **Publish.**
   - **Monthly provisional runs** during the season (Aug–Nov) with `status: "provisional"`.
   - **One final run per season** in February with the Nov–Jan post-season window and
     `status: "final"`.

### 7.2 Compute, runtime and quotas

Measured in this container for 300–568 points, with up to six fetches running at once at 32 threads
each **[T]**:

| Fetch | Wall-clock |
| --- | --- |
| S2 | 270–500 s |
| S1 RTC | 230–530 s |
| Landsat | 130–200 s |
| Labelling and estimation | < 3 s |

A ~1,000-point province-season is therefore about **15–25 min**, almost all network I/O, with little
CPU or memory.

Fit with GitHub Actions:

- **Job limit.** Each job may run for 6 hours ([GitHub docs](https://docs.github.com/en/actions/reference/limits))
  **[V]**, so one province fits in one job.
- **Workflow.** Use a separate monthly `burned-area.yml` with a province **matrix**, for example the
  8 priority provinces as parallel jobs. Do not add it to the 2-hourly pipeline job.
- **Minutes on a private repo.** `pipeline.yml` already budgets about 1,440 of the 2,000 free
  minutes a month. A monthly 8-province run adds about 160–200 minutes, which fits but is tight.
  Once the repo is public, minutes are unlimited.
- **Earth Search.** AWS Open Data, keyless. No quota was hit during the test.
- **Planetary Computer.** Anonymous SAS tokens worked for every request here. PC documents tokens as
  short-lived and rate-limited for anonymous use **[M]**
  ([SAS docs](https://planetarycomputer.microsoft.com/docs/concepts/sas/)). Cache one token per
  container (`pcsign.py`). If runners get throttled, add an optional `PC_SDK_SUBSCRIPTION_KEY`
  secret.
- **Retries and failures.**
  - Of all S1 RTC scenes read, one 2019 scene failed after retries **[T]**. Its points were
    covered by other scenes.
  - The job should log the failed scenes. It should mark a stratum `insufficient` when more than
    10% of its points have no usable observation.
- **Re-test from a runner.** PC egress is from Azure West Europe. Runner IPs differ from this
  container, so re-test once from a runner, as the GIS-layers note advises for every host.

### 7.3 What to publish

Write `public/burned_area/{season}.json`, one entry per province:

```json
{
  "province": "Kalimantan Tengah",
  "season": 2019,
  "asof": "2026-10-17",
  "status": "final",
  "area_ha": 649000,
  "ci95": [389000, 952000],
  "ci95_sampling_only": [564000, 863000],
  "area_ha_uncorrected": 714000,
  "n_samples": 700,
  "strata": [
    {"id": 1, "name": "detected", "area_ha": 792896, "n": 200, "n_burned": 92},
    {"id": 2, "name": "ring_0_0.8km", "area_ha": 1845301, "n": 200, "n_burned": 24},
    {"id": 3, "name": "ring_0.8_2km", "area_ha": 3649391, "n": 150, "n_burned": 4},
    {"id": 4, "name": "peat_rest", "area_ha": 2274164, "n": 75, "n_burned": 1},
    {"id": 5, "name": "rest", "area_ha": 6892361, "n": 75, "n_burned": 0, "upper95_ha": 269876}
  ],
  "map": {"area_ha": 792896, "users_accuracy": 0.46, "users_ci95": [0.39, 0.53],
          "producers_accuracy": 0.51, "producers_ci95": [0.40, 0.62], "overall_accuracy": 0.95},
  "method": "stratified-random-sample/stehman2014-olofsson2014; automated labels rule H v1; Rogan-Gladen label correction",
  "label_error": {"source": "Gaveau et al. 2021 expert points (n=268 in province)", "sensitivity": 0.74,
                  "specificity_near": 0.93, "specificity_far": 0.98},
  "reference_imagery": ["Sentinel-2 L2A C1 (Earth Search)", "Landsat 8/9 C2 L2 (Planetary Computer)",
                        "Sentinel-1 RTC (Planetary Computer)"],
  "windows": {"pre": "2019-04-01/2019-07-31", "post": "2019-10-01/2020-02-29"},
  "label_sources": {"optical": 695, "sar": 5},
  "comparisons": {"mcd64a1_ha": 517735, "firecci_s311_ha": 625640, "gaveau2021_ha": 473153,
                  "klhk_official_ha": 317749},
  "code_version": "<git sha>"
}
```

Also publish the sample points with their labels (`burned_area/{season}/{province}.geojson`). Anyone
can then re-check any point, and that is what makes the number defensible.

### 7.4 How to explain it in the UI

The CI is the headline, not the point value. Suggested text:

**Bahasa Indonesia**

> **Perkiraan luas terbakar (independen): 390.000 – 950.000 ha**
> *(nilai tengah ± 650.000 ha · Kalimantan Tengah 2019)*
>
> Angka ini bukan dari pemerintah. Kami memilih 700 titik acak di seluruh provinsi, lalu memeriksa
> setiap titik dengan citra satelit Sentinel-2, Landsat dan radar Sentinel-1 (radar bisa menembus
> asap dan awan): apakah lahannya berubah menjadi bekas terbakar? Dari bagian titik yang terbakar,
> kami hitung luasnya untuk seluruh provinsi. Rentang di atas berarti: dengan keyakinan 95%, luas
> sebenarnya ada di antara dua angka itu. Rentangnya lebar karena titik diperiksa otomatis oleh
> komputer, bukan oleh manusia satu per satu; kami sudah mengukur seberapa sering pemeriksaan
> otomatis itu keliru dan memasukkannya ke dalam rentang.
>
> Sebagai pembanding: produk satelit lain (MODIS, ESA FireCCI, peta Sentinel-2 Gaveau dkk.)
> memperkirakan 470.000 – 630.000 ha; angka resmi KLHK 317.749 ha. Titik-titik sampel dan
> kodenya terbuka untuk diperiksa siapa saja.

**English**

> **Independent burned-area estimate: 390,000 – 950,000 ha**
> *(central value ≈ 650,000 ha · Central Kalimantan 2019)*
>
> This figure does not come from the government. We picked 700 random points across the province and
> checked each one in Sentinel-2, Landsat and Sentinel-1 radar imagery (radar sees through smoke and
> cloud): did the land turn into a burn scar? The share of points that burned, scaled up to the
> province, gives the area. The range means we are 95% confident the true area lies between the two
> numbers. It is wide because a computer checked the points, not a person looking at each one; we
> measured how often the automatic check is wrong and included that in the range.
>
> For comparison, other satellite products (MODIS, ESA FireCCI, the Gaveau et al. Sentinel-2 map)
> give 470,000 – 630,000 ha, and the official KLHK figure is 317,749 ha. The sample points and the
> code are open for anyone to check.

For a **provisional** (in-season) value, add:

- **Bahasa:** *"Sementara — musim kebakaran masih berlangsung; lahan yang terbakar setelah citra
  terakhir belum terhitung, jadi angka ini cenderung terlalu rendah."*
- **English:** *"Provisional — the fire season is still under way. Land that burned after the latest
  clear image is not yet counted, so this number is more likely too low than too high."*

Do not show the detection-footprint hectares next to this as "luas terbakar". If they are shown at
all, label them as *"luas piksel dengan titik panas"* (area of pixels with hotspots), together with
UA 0.46 and PA 0.51.

---

## 8. Limitations

- **Labels are a proxy** (§6). The CI includes measured label error, but the error model comes from
  one expert set: one province, one year, 92 burned sites.
- **The reference is "burned during the season".** It also picks up land clearing that drops NBR and
  backscatter, and it misses burns that recovered before the first clear post-season scene.
- **Early-year burns.** A burn before the pre-season window ends (Jan–Jul) is invisible. In 2019,
  MCD64A1 puts about 9,000 ha in Jan–Jul.
- **SAR.**
  - Only VH change is used. VV and the VH/VV ratio were weaker here, and texture or coherence is not
    available keyless.
  - The orbit-median normalisation assumes most background points did not burn.
  - Heavy rain after a fire raises backscatter (wet soil) and hides burns. That is why the SAR
    post-season window stops at Dec 31 in 2019.
- **Strata come from all-year VIIRS detections.** Detections from early-year agricultural fires
  enlarge strata 1–3 slightly. This affects efficiency, not bias.
- **FireCCI comparison.** Cells are apportioned by area overlap with the province polygon. Coastal
  cells may put a little non-provincial area in.
- **2023 was not prototyped.** Its detections are in `data/haze.duckdb` and `strata.py` runs on
  them unchanged. Gaveau's expert set is 2019-only, so 2023 would use the transferred error model,
  as 2026 does.

---

## 9. Code pointers (prototype, local working folder, not in the repo)

The scripts are in
`scratch/burned/code/`. They
were run with `pipeline/.venv/bin/python`, with `pystac-client`, `rasterio` and `pyproj` added via
`uv pip install`. The lockfile was not changed.

| Script | Does |
| --- | --- |
| `extract.py` | Pulls Central Kalimantan bbox detections (2019, 2023 from `data/haze.duckdb`; 2026 from the audit copy) plus province and peat polygons into parquet |
| `strata.py B YEAR` | Builds the 5-stratum raster on the 0.0034° grid and the stratum areas |
| `sample.py B YEAR n1,..,n5 [seed] [tag]` | Draws the stratified random points |
| `pcsign.py` | Anonymous Planetary Computer SAS signing per account and container |
| `fetch.py B POINTS PREFIX {S2,L8,S1} period=start/end …` | Point window reads, one row per (point, scene) clear observation |
| `features.py` | Per-point dNBR (second-lowest post-season NBR, SWIR2 guard) and orbit-normalised ΔVV/ΔVH |
| `rules.py` | Key & Benson thresholds, Gaussian minimum-error threshold, confusion counts |
| `estimate.py` | Stehman/Olofsson area, UA, PA, OA and CIs; label-error Monte Carlo (Rogan–Gladen) |
| `run_estimate.py B YEAR` | End-to-end. Writes `out/result_{YEAR}.json`, `out/labels_{YEAR}_{rule}.parquet` and `out/features_{YEAR}.parquet` |
| `mcd64.py`, `mcd64_points.py`, `firecci.py`, `gaveau_area.py`, `gaveau_points.py` | Comparison totals and point labels |

The raw observation tables are in `burned/obs/*.parquet`. In production, these modules would become
`pipeline/src/haze/burned.py`, plus a `burned-area` CLI subcommand and a `ba_obs` table, following
§7.1.

---

## 10. References

- **Olofsson, P., Foody, G. M., Herold, M., Stehman, S. V., Woodcock, C. E., Wulder, M. A. (2014).**
  Good practices for estimating area and assessing accuracy of land change. *Remote Sensing of
  Environment* 148, 42–57. [doi:10.1016/j.rse.2014.02.015](https://doi.org/10.1016/j.rse.2014.02.015)
  (DOI checked on Crossref) **[V]**
- **Stehman, S. V. (2014).** Estimating area and map accuracy for stratified random sampling when the
  strata are different from the map classes. *International Journal of Remote Sensing* 35,
  4923–4939. [doi:10.1080/01431161.2014.930207](https://doi.org/10.1080/01431161.2014.930207)
  (Crossref) **[S]** for the equations; the R package `mapaccuracy::stehman2014` implements them.
- **Lohberger, S., Stängel, M., Atwood, E. C., Siegert, F. (2018).** Spatial evaluation of Indonesia's
  2015 fire-affected area and estimated carbon emissions using Sentinel-1. *Global Change Biology*
  24(2), 644–654. [doi:10.1111/gcb.13841](https://doi.org/10.1111/gcb.13841) **[V]** (abstract): 4.6 M ha
  burned in 2015 at 84% overall accuracy, about double the official 2.6 M ha.
- **Gaveau, D. L. A., Descals, A., Salim, M. A., Sheil, D., Sloan, S. (2021).** Refined burned-area
  mapping protocol using Sentinel-2 data increases estimate of 2019 Indonesian burning. *Earth System
  Science Data* 13, 5353–5368. [doi:10.5194/essd-13-5353-2021](https://doi.org/10.5194/essd-13-5353-2021)
  **[V]**. Map and reference points: [doi:10.5281/zenodo.4551243](https://doi.org/10.5281/zenodo.4551243)
  **[T]** (CC BY 4.0).
- **Belenguer-Plomer, M. A., Tanase, M. A., Fernandez-Carrillo, A., Chuvieco, E. (2019).** Burned
  area detection and mapping using Sentinel-1 backscatter coefficient and thermal anomalies.
  *Remote Sensing of Environment* 233, 111345.
  [doi:10.1016/j.rse.2019.111345](https://doi.org/10.1016/j.rse.2019.111345) **[S]**
- **Tanase, M. A., Belenguer-Plomer, M. A., Roteta, E., Bastarrika, A., et al. (2020).** Burned area
  detection and mapping: intercomparison of Sentinel-1 and Sentinel-2 based algorithms over tropical
  Africa. *Remote Sensing* 12(2), 334. [doi:10.3390/rs12020334](https://doi.org/10.3390/rs12020334)
  (Crossref) **[M]** for content.
- **Kittler, J., Illingworth, J. (1986).** Minimum error thresholding. *Pattern Recognition* 19(1),
  41–47. [doi:10.1016/0031-3203(86)90030-0](https://doi.org/10.1016/0031-3203(86)90030-0) (Crossref)
- **Key, C. H., Benson, N. C. (2006).** Landscape Assessment: ground measure of severity, the
  Composite Burn Index; and remote sensing of severity, the Normalized Burn Ratio. In: Lutes et al.,
  *FIREMON: Fire effects monitoring and inventory system*, USDA Forest Service RMRS-GTR-164-CD,
  LA 1–51. [Treesearch record](https://www.fs.usda.gov/research/treesearch/24042) **[T]** (200). The
  dNBR class breaks used here (0.10 / 0.27 / 0.44 / 0.66) are the widely used FIREMON table **[M]**;
  check them against the PDF.
- **Vetrita, Y., Cochrane, M. A., Suwarsono, Priyatna, M., et al. (2021).** Evaluating accuracy of
  four MODIS-derived burned area products for tropical peatland and non-peatland fires.
  *Environmental Research Letters* 16, 035015.
  [doi:10.1088/1748-9326/abd3d1](https://doi.org/10.1088/1748-9326/abd3d1) **[S]**
- **Giglio, L., Boschetti, L., Roy, D. P., Humber, M. L., Justice, C. O. (2018).** The Collection 6
  MODIS burned area mapping algorithm and product. *Remote Sensing of Environment* 217, 72–85.
  [doi:10.1016/j.rse.2018.08.005](https://doi.org/10.1016/j.rse.2018.08.005) (Crossref).
  Data: [PC `modis-64A1-061`](https://planetarycomputer.microsoft.com/dataset/modis-64A1-061) **[T]**
- **ESA Fire_cci Sentinel-3 SYN burned area v1.1 (FireCCIS311).**
  [CEDA catalogue](https://catalogue.ceda.ac.uk/uuid/d441079fc77f49fabeb41330612b252f) **[T]**
- **Schroeder, W., Oliva, P., Giglio, L., Csiszar, I. A. (2014).** The New VIIRS 375 m active fire
  detection data product. *Remote Sensing of Environment* 143, 85–96.
  [doi:10.1016/j.rse.2013.12.008](https://doi.org/10.1016/j.rse.2013.12.008) (Crossref). This is the
  basis of our map.
- **Data services:** [Earth Search](https://element84.com/earth-search/) **[T]**,
  [Planetary Computer `sentinel-1-rtc`](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc)
  **[T]**, [PC SAS tokens](https://planetarycomputer.microsoft.com/docs/concepts/sas/) **[T]**.
- **Context, official 2026 figures:** Kemenhut, 107,465 ha nationally Jan–Jun 2026; SiPongi,
  202,011 ha Jan–Aug 2026, as reported by
  [RCTI+ / iNews](https://www.rctiplus.com/news/detail/terkini/5431931/karhutla-di-indonesia-capai-107-465-hektare--kalbar-paling-luas-terdampak)
  **[S]**. A search did not locate the "639 ha" report, so it is quoted here as relayed to us.
