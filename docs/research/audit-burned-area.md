# Audit: estimated burned area (`est_area_ha`)

Date: 17 Oct 2026. Data: a read-only copy of the production DuckDB (season 2026), plus the 2019 and
2023 FIRMS yearly Indonesia archives (VIIRS S-NPP, VIIRS NOAA-20, MODIS). These were loaded into a
scratch copy of the DB and clustered with the unchanged pipeline (`pipeline.ingest_archive` →
`tag_hotspots` → `events.build`). The rebuilt 2023 season has 144,565 events, the same as
[clustering-evaluation.md](../clustering-evaluation.md), so the rebuild matches production.

## 1. Verdict

**Our hectare figures are 4.3–4.6× the official KLHK figures in the two calibration years.
Publishing them as "luas terbakar" (burned area) would not survive scrutiny.**

| Season | Ours (Σ `fire_events.est_area_ha`) | Official (SiPongi, Kemenhut) | Ratio |
| --- | --- | --- | --- |
| 2019 | 7.14 M ha | 1.649 M ha | 4.3× |
| 2023 | 5.40 M ha | 1.161 M ha | 4.6× |
| 2026 (to 17 Oct) | 11.89 M ha | 0.202 M ha *(Jan–Jul only, "data input s.d. Juli 2026")* | — |
| Central Kalimantan 2019 / 2023 / 2026 | 0.99 / 0.57 / 1.88 M ha | 0.318 / 0.166 / 0.008 *(Jan–Jul)* M ha | 3.1× / 3.4× / — |

The recommended method (§5) reproduces the official national figure within ±4% when fitted on one
year and tested on the other. For 2026 to date it gives **2.28 M ha (90% range 1.86–2.65 M ha)**
nationally and **0.47 M ha (0.38–0.55)** for Central Kalimantan.

## 2. How the number is computed today

- `events.area_by`: for each event, **unique cells of a fixed 0.0034° (~375 m) grid** hit by any
  VIIRS detection from any satellite, × 14.06 ha (the nominal 375 m pixel). Events with **no**
  VIIRS detection instead count unique 0.009° MODIS cells × **100 ha**.
- `events.snapshots`: `growth_ha` and `cum_area_ha` use the same cells, counted on the first day
  each cell appears in the event.
- Footprints (`perimeter_geom`, `day_geom`): unions of 0.0017° (~190 m radius) octagons. These
  only draw the map; **no area figure comes from them**. Each isolated octagon is about 10 ha.
- `publish.dashboard` (`by_provinsi.area_ha`) and `publish.tables` (`regions.json` `area_ha`)
  **sum `est_area_ha` over events**. That gives the provincial totals in the task (Central
  Kalimantan 2026 = 1.88 M ha).

So the method already uses a fixed 375 m grid of unique cells, not unions of buffers. The
inflation comes from the factors below.

## 3. Diagnosis: where the factor of 4–5 comes from

Each step removes one cause. Numbers are national, in M ha.

| Step | 2019 | 2023 | 2026 | Factor |
| --- | --- | --- | --- | --- |
| Published Σ events | 7.14 | 5.40 | 11.89 | |
| − MODIS-only events (7.4k–10.9k events, about 80% single detections, 100 ha each) | 6.25 | 4.53 | 10.53 | ×1.13–1.19 |
| − double counting between events (re-burns > 48 h apart become new events; season-unique cells) | 5.47 | 3.99 | 9.07 | ×1.14–1.16 |
| − extra satellites (single-satellite average of unique cells) | 3.44 | 2.33 | 4.64 | ×1.59 (2 sats), ×1.95 (3 sats) |
| Official KLHK | 1.649 | 1.161 | *n/a (full year)* | ×2.0–2.1 left over |

What each factor means:

1. **Summing over overlapping events (×1.14).** One place that burns, goes quiet for more than
   48 h, then flares again is two events, and its cells are counted twice. Province and national
   totals must be counted once per season, not summed over events.
2. **MODIS-only events at 100 ha each (×1.13–1.19).** These are mostly single MODIS detections that
   no VIIRS pass confirmed, so they are probably small or short fires. Each one adds a full 1 km²
   (100 ha), seven times a VIIRS pixel. Tansey et al. 2008 find about 15–16 ha of burned area per
   MODIS hotspot in Central Kalimantan peat. KLHK's own totals work out to 20–26 ha per eligible
   MODIS detection in 2019 and 2023.
3. **Number of satellites (×1.6 to ×2.0).** Unique-cell area is not stable when satellites are
   added. In 2019, S-NPP alone gives 3.42 M ha, S-NPP plus NOAA-20 gives 5.47 M ha, and in 2026
   NOAA-21 lifts 7.17 to 9.07 M ha. Two causes:
   - extra overpasses catch short-lived fires the others miss (real, but KLHK's Landsat scars do
     not capture them either);
   - detection centres scatter around the grid.

   Even a union of 375 m discs with no grid grows 1.6× (2 satellites) and 2.0× (3 satellites).
   **This also makes 2026 look bigger against 2019 and 2023 just because NOAA-21 started flying
   in 2024.**
4. **Repeated detections of the same place: grid-boundary jitter.** As a test, take the 126
   persistent point sources (flares and smelters) with ≥ 100 VIIRS detections. Their detection
   centres sit a median 99 m (p90 217 m) from the source, so one fixed point covers a **median of
   3 unique 375 m cells with S-NPP alone (42 ha) and 4 cells with two satellites (56 ha)**. Every
   long-burning fire is spread over its neighbouring cells in the same way.
5. **Counting a full pixel for every fire (the remaining ×2).** A VIIRS 375 m detection can come
   from a fire of a few hundred m² (Schroeder et al. 2014). Counting every detected pixel as 14 ha
   burned is an upper bound. This is the classic finding that the burned area per fire pixel
   depends on fire size and land cover (Giglio et al. 2006). KLHK's totals come to **4.2–5.5 ha per
   S-NPP detection**, about a third of a pixel.
6. **Off-nadir pixel size: not the cause.** In our 2023 data, VIIRS `scan` runs 0.32–0.80 km and
   `track` 0.36–0.78 km, so pixel area runs 0.14–0.62 km² (mean 0.22 km², 1.5× nadir). We
   *already* count every detection as one nadir-size pixel, so pixel growth does not inflate the
   cell count. Using the true `scan × track` area would add about 55%. Off-nadir pixels do place
   their centres slightly less precisely (p90 offset 254 m against 212 m near nadir), which adds a
   little to factor 4.
7. **Buffer radius: does not affect the numbers.** The 0.0017° octagons affect only the drawn
   footprints. Their unions are not burn scars and should be labelled as detection footprints.

**The reference is itself uncertain.** KLHK's method (as stated on SiPongi) is Landsat 8 OLI/TIRS
image analysis overlaid with hotspots, plus Manggala Agni ground-check and suppression reports.
Independent Sentinel-2 mapping found **3.11 M ha in 2019**, which is 1.9× the official 1.64 M ha and
1.5× MCD64A1's 2.03 M ha (Gaveau et al. 2021). Our single-satellite pixel area for 2019 (3.44 M ha)
is within 10% of that Sentinel-2 figure. So the honest framing is:

> "Our raw pixel area is a fire-affected-area upper bound. Calibrated to KLHK it gives the
> official-style figure, which research suggests is conservative."

## 4. Literature

| Topic | Finding | Source |
| --- | --- | --- |
| Per-pixel footprint vs scaling factor | Burned area from active-fire counts needs a scaling factor that varies with tree and herbaceous cover and with mean fire-cluster size. One constant per pixel does not hold globally. A deforestation and persistence correction was needed in the tropics. | Giglio et al. 2006, ACP 6, 957 — https://acp.copernicus.org/articles/6/957/2006/ |
| Active fire to burned area outside the MODIS era | The GFED3 merge used local and regional regressions of MODIS burned area on active-fire counts, fitted where both exist. The ratio is region-specific and calibrated, not geometric. | Giglio et al. 2010, BG 7, 1171 — https://bg.copernicus.org/articles/7/1171/2010/ |
| Indonesia: hotspots per hectare | Central Kalimantan degraded peat swamp: **15–16 ha burned per MODIS hotspot**. About 60% omission and about 8% commission. The ratio depends strongly on vegetation. | Tansey et al. 2008, JGR 113, D23112, doi:10.1029/2008JD010717 — abstract https://modarch.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=01368 |
| Peat fire distribution | 53% of MODIS detections fall on peat, which is 12% of the area. Fire density is driven by land cover: intact peat swamp forest about 30 detections per 1000 km², deforested peat 831–915. 71% of peat hotspots are in South Sumatra and Central Kalimantan. | Miettinen, Shi & Liew 2017, Environ. Manage. 60, 747 — https://dx.doi.org/10.1007/s00267-017-0911-7 |
| 2015 Indonesia (Sentinel-1 SAR) | **4.60 M ha** burned in 2015 (84% overall accuracy), about 1.8× KLHK's 2.61 M ha. Also compared with MCD64 and GFED4/4.1s. | Lohberger et al. 2018, GCB 24, 644, doi:10.1111/gcb.13841 — abstract https://modarch.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=27897 |
| 2019 Indonesia (Sentinel-2) | **> 3.11 M ha**, against official 1.64 M ha and MCD64A1 2.03 M ha. 31% on peat (0.96 M ha, official 0.64). Producer accuracy 75.6%, against 49.5% (official) and 53.1% (MCD64A1). The coarse products miss small burns (< 100 ha). | Gaveau et al. 2021, ESSD 13, 5353 — https://essd.copernicus.org/articles/13/5353/2021/ |
| MCD64A1 / FireCCI51 on peat | Against SPOT-5 reference burns, MODIS products captured 38–48% of the burned area (MCD45 < 1%). **MCD64A1 C6 was best. FireCCI51 (250 m) was less accurate despite its finer resolution.** R² 0.6–0.8 on peat, 0.2–0.5 off peat. Accuracy improves when burns < 100 ha are excluded. | Vetrita et al. 2021, ERL 16, 035015, doi:10.1088/1748-9326/abd3d1 — https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=43160 |
| El Niño and hotspots (Nurdiati) | EOF analysis of 2001–2019 hotspots, dry spells and rain. Kalimantan responds even to moderate El Niño; South Sumatra only to strong ones. It uses hotspot counts, not an area conversion. **We found no Nurdiati paper that gives a hotspot-to-area ratio.** | Nurdiati, Sopaheluwakan & Septiawan 2021, Agromet 35(1) — https://journal.ipb.ac.id/agromet/article/view/31804 |
| VIIRS 375 m pixel | I-band pixels are 375 m at nadir and grow off-nadir. FIRMS `scan`/`track` give the real pixel size (0.32–0.80 km in our data). Fires much smaller than a pixel are detected. | Schroeder et al. 2014, RSE 143, 85, doi:10.1016/j.rse.2013.12.008; https://www.earthdata.nasa.gov/data/instruments/viirs/viirs-i-band-375-m-active-fire-data; FIRMS FAQ https://www.earthdata.nasa.gov/faq/firms-faq |
| KLHK / SiPongi method | "Luas Kebakaran Hutan dan Lahan dihitung berdasarkan analisis citra satelit Landsat8 OLI/TIRS yang di-overlay dengan data sebaran hotspot, serta laporan hasil groundcheck hotspot dan laporan pemadaman yang dilaksanakan Manggala Agni." Published monthly with a lag. 2026 is "data input s.d. Juli 2026". | https://sipongi.gakkum.kehutanan.go.id/indikasi-luas-kebakaran, API https://opsroom.sipongidata.my.id/api/list/luas-kebakaran/provinsi?tahunAwal=2015&tahunAkhir=2026 |
| Revisions to official figures | 2023 went from 994,313 ha (Jan–Oct, preliminary) to 1.16 M ha (full year). | Mongabay, https://news.mongabay.com/2024/01/2023-fires-increase-fivefold-in-indonesia-amid-el-nino |
| GFW | Presents VIIRS 375 m as *fire alerts* for locating fires, warns they are coarse, and gives < 8% false positives for Equatorial Asia. It does not convert alerts to hectares; for area it uses separate burn-scar and tree-cover-loss data. | https://www.globalforestwatch.org/blog/data/fighting-fires-with-satellites-viirs-fire-data-now-available-on-global-forest-watch |

**MCD64A1 and FireCCI totals:** the only published Indonesia-wide MCD64A1 figure we could verify is
2.03 M ha for 2019 (Gaveau et al. 2021). We found no published MCD64A1 or FireCCI national total
for 2023.

**Official SiPongi totals** (ha, fetched 17 Oct 2026):

| Year | 2015 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (Jan–Jul) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Total | 2,611,411 | 529,267 | 1,649,258 | 296,942 | 358,867 | 204,894 | 1,161,193 | 376,805 | 359,619 | 202,011 |

The page narrative implies Jan–Jul totals of 137,007 ha (2019) and 92,924 ha (2023).

## 5. Recommended method

### 5.1 Season totals (national, province, kabupaten): KLHK-calibrated fire-pixel area

1. Take eligible detections: VIIRS, nominal or high confidence, not static, in Indonesia. This is
   the same filter as `events.eligible`. MODIS is not used for area.
2. **Separately for each VIIRS satellite**, count the season's unique cells on the fixed 0.0034°
   grid. Each cell is counted once per season, whatever the events.
3. **Average across the satellites flying that season** (single-satellite equivalent). This makes
   2019, 2023 and 2026 comparable and is robust to a single outage (S-NPP has no data in May 2026).
4. Fire-pixel area = mean cells × 14.06 ha. Burned-area estimate = **k × fire-pixel area, with
   k = 0.49 (90% range 0.40–0.57)**.
5. A cell belongs to the region of its first detection, so provinces add up to the national figure.

How k was fitted:
- official ÷ fire-pixel area = **0.480 in 2019 and 0.499 in 2023** (pooled 0.4875);
- a province bootstrap gives a 90% interval of 0.40–0.57;
- fitting on 2019 and predicting 2023 gives −3.7%; fitting on 2023 and predicting 2019 gives +3.9%;
- separate peat and non-peat factors (0.65 and 0.48) **do not reduce province scatter** (log-SD
  0.46 against 0.47), so a single k is used.
- Raw detection counts (4.2 against 5.5 ha per S-NPP detection) are a worse predictor than unique
  cells.

```python
CELL_DEG = 0.0034
PIXEL_HA = 0.375 * 0.375 * 100          # 14.06 ha
K_KLHK, K_LO, K_HI = 0.49, 0.40, 0.57   # official / single-satellite pixel area, 2019 + 2023
VIIRS_SATS = ("SNPP", "NOAA20", "NOAA21")

def cell_keys(lat, lon, cell=CELL_DEG):          # = haze.geo.cell_keys
    row = np.floor((np.asarray(lat) + 90.0) / cell).astype(np.int64)
    col = np.floor((np.asarray(lon) + 180.0) / cell).astype(np.int64)
    return row * 1_000_000 + col

def fire_pixel_area(hs: pd.DataFrame, by: str | None = None, min_det: int = 1000) -> pd.DataFrame:
    """Season-level unique 375 m cells per satellite, averaged over satellites flying."""
    v = hs[hs.sensor == "VIIRS"].assign(cell=lambda d: cell_keys(d.lat, d.lon))
    sats = [s for s in VIIRS_SATS if (v.satellite == s).sum() >= min_det]
    owner = v.sort_values("acq_time").drop_duplicates("cell").set_index("cell")   # first detection owns the cell
    per_sat = {}
    for s in sats:
        u = pd.Series(v.loc[v.satellite == s, "cell"].unique())
        key = u.map(owner[by]) if by else pd.Series("ID", index=u.index)
        per_sat[s] = key.value_counts()
    px = pd.DataFrame(per_sat).fillna(0).mean(axis=1)
    return pd.DataFrame({
        "fire_pixels_1sat": px,
        "pixel_area_ha": px * PIXEL_HA,
        "burned_ha": px * PIXEL_HA * K_KLHK,
        "burned_ha_lo": px * PIXEL_HA * K_LO,
        "burned_ha_hi": px * PIXEL_HA * K_HI,
    })
```

Re-fitting k each year once KLHK publishes the full-year table:

```python
def fit_k(pixel_area_by_prov_year: pd.DataFrame, official: pd.DataFrame, years=(2019, 2023), n_boot=2000):
    d = pixel_area_by_prov_year.merge(official, on=["provinsi", "season"]).query("season in @years")
    k = d.official.sum() / d.pixel_area_ha.sum()
    rng, provs = np.random.default_rng(0), d.provinsi.unique()
    boot = [(lambda s: s.official.sum() / s.pixel_area_ha.sum())(
                pd.concat([d[d.provinsi == p] for p in rng.choice(provs, len(provs))])) for _ in range(n_boot)]
    return k, np.percentile(boot, [5, 95])
```

The SiPongi names need mapping: Bangka Belitung → Kepulauan Bangka Belitung,
Yogyakarta → DI Yogyakarta. Papua Selatan, Tengah and Pegunungan → Papua, and Papua Barat Daya →
Papua Barat, because our boundaries are the 34-province set.

### 5.2 Results of the recommended method

National (M ha):

| Season | Published now | Fire-pixel area (1 satellite) | **Recommended (k = 0.49)** | Official | Rec. ÷ official |
| --- | --- | --- | --- | --- | --- |
| 2019 | 7.14 | 3.44 | **1.68 (1.37–1.96)** | 1.649 | 1.02 |
| 2023 | 5.40 | 2.33 | **1.14 (0.93–1.33)** | 1.161 | 0.98 |
| 2026 to 17 Oct | 11.89 | 4.64 | **2.28 (1.86–2.65)** | not yet published | — |
| 2026 Jan–Jul | 2.03 | 0.53 | **0.26 (0.21–0.30)** | 0.202 | 1.29 |
| 2019 / 2023 Jan–Jul | 1.04 / 0.93 | 0.39 / 0.33 | 0.19 / 0.16 | 0.137 / 0.093 | 1.41 / 1.74 |

- **Out-of-sample check:** on 2026 Jan–Jul the method reads +29% high. That is better than the
  early-season errors in the calibration years themselves.
- **Early-season bias:** off-season fires are small farm burns, and KLHK's Landsat scars miss more
  of them. KLHK also revises upward (2023: 994 k → 1,161 k ha). So treat season-to-date figures
  before August as likely high, and say so.
- **2026 against the bad years:** 2026 coming out above 2019 is consistent with SiPongi's own MODIS
  hotspot counts (Aug–Oct 2026 ≥ 2019) and with its statement that Jan–Jul 2026 is +47% on 2019.

Main provinces (thousand ha). Rec. = recommended, with its 90% range.

| Province | 2019 published | 2019 rec. | 2019 official | 2023 published | 2023 rec. | 2023 official | 2026 published | **2026 rec.** | 2026 official (Jan–Jul) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Kalimantan Tengah | 988 | 272 | 318 | 571 | 136 | 166 | 1,880 | **469 (383–546)** | 7.6 |
| Sumatera Selatan | 743 | 187 | 337 | 461 | 111 | 132 | 808 | **159 (130–185)** | 1.9 |
| Kalimantan Barat | 773 | 184 | 152 | 729 | 146 | 112 | 1,751 | **323 (264–376)** | 38.3 |
| Kalimantan Selatan | 330 | 76 | 138 | 310 | 68 | 190 | 533 | **100 (82–117)** | 8.0 |
| Riau | 453 | 105 | 91 | 120 | 13 | 7 | 114 | **24 (19–27)** | 15.7 |
| Jambi | 274 | 85 | 57 | 78 | 15 | 7 | 155 | **30 (25–35)** | 0.4 |
| Kalimantan Timur | 386 | 84 | 69 | 270 | 53 | 39 | 754 | **128 (105–149)** | 2.7 |
| Papua (incl. new provinces) | 405 | 92 | 108 | 583 | 134 | 155 | 1,988 | **384 (314–447)** | 30.6 |
| Nusa Tenggara Timur | 561 | 123 | 137 | 567 | 126 | 103 | 422 | **68 (56–79)** | 19.6 |

**Province scatter is large.** Recommended ÷ official across provinces with > 10 k ha has a
log-SD of about 0.47 (p10–p90 0.64–2.1×):
- peat-heavy South Kalimantan and South Sumatra read low;
- Sulawesi, Java and Maluku read high (official ÷ pixel area 0.16–0.32).

Show province figures with their range and the note "±50%". Where both calibration years agree,
a province's own k is defensible: Kalteng 0.57/0.60, Kalbar 0.40/0.38, Papua 0.57/0.57,
Kaltim 0.40/0.36. Kalteng 2026 with its own k would be 0.56 M ha. Do not show kabupaten hectares
as more than indicative.

### 5.3 Event level: show fire pixels, not hectares

One factor fitted to provincial annual totals does not hold for a single fire, where the
burned-area-to-pixel ratio ranges from about 0 (a farm burn under one pixel) to more than 1 (a
peat front between overpasses). Recommendation:

- Event headline: **"N piksel api (375 m)"** = unique 0.0034° cells, all satellites (what
  `area_by` already counts before multiplying). Add "≈ X ha indikatif" only as secondary text,
  with X = k · r · pixels · 14.06, where r = (single-satellite pixels ÷ all-satellite pixels)
  nationally for that season. r is 0.63 for 2019, 0.58 for 2023 and 0.51 for 2026, which gives
  k·r ≈ 0.25–0.31 ha per ha of pixel area. Round to 2 significant figures.
- MODIS-only events: show "–" (no area). Do not show 100 ha.
- Growth (`growth_ha`, `top_growth`): rank by new pixels per day, and show pixels.
- Footprints: label as "jejak deteksi satelit" (detection footprint), not a perimeter or burn scar.

```python
def event_area(hs, season_r, k=K_KLHK):
    """hs: eligible detections of one season with event_id; season_r from fire_pixel_area()."""
    v = hs[hs.sensor == "VIIRS"]
    px = v.groupby("event_id").apply(lambda g: np.unique(cell_keys(g.lat, g.lon)).size)
    return pd.DataFrame({"fire_pixels": px, "est_area_ha": (px * PIXEL_HA * k * season_r).round(-1)})

# season_r = nat.fire_pixels_1sat / unique_cells_all_sats   (both national, same season)
```

### 5.4 Wording (ID / EN)

- National card: **"Perkiraan luas terbakar: ±2,3 juta ha (1,9–2,7 juta ha)"**, footnote: *"Dari
  piksel api VIIRS 375 m, dikalibrasi ke data resmi KLHK 2019 dan 2023 (selisih ±4% di tingkat
  nasional). Angka resmi SiPongi: 202.011 ha s.d. Juli 2026. Penelitian Sentinel-2 menunjukkan
  angka resmi cenderung konservatif (2019: 3,1 vs 1,6 juta ha)."*
  - EN: *"Estimated burned area ≈ 2.3 M ha (1.9–2.7 M). From VIIRS 375 m fire pixels, calibrated
    to official KLHK totals for 2019 and 2023 (±4% nationally). Official SiPongi figure: 202,011 ha
    through July 2026."*
- Province: the same, with the range and "±50% per provinsi".
- Event: **"128 piksel api (375 m) · ≈ 450 ha indikatif"**, tooltip: *"Piksel tempat satelit
  mendeteksi api. Bukan luas terbakar hasil pemetaan."*
- Always show SiPongi's official figure next to ours, with its "data s.d." month.

## 6. Code changes (not made, for review)

| File / function | Change |
| --- | --- |
| `pipeline/src/haze/config.py` | Add `BURNED_AREA_K = 0.49`, `BURNED_AREA_K_RANGE = (0.40, 0.57)` and a comment citing this audit. Keep `VIIRS_PIXEL_HA`. |
| `pipeline/src/haze/events.py` `area_by` | Return the unique-cell **count** (`fire_pixels`) per event. Drop the MODIS-only `MODIS_PIXEL_HA` branch (NaN area). |
| `events.summarise` | Store `fire_pixels`. Set `est_area_ha = fire_pixels · VIIRS_PIXEL_HA · K · season_r` (indicative). |
| `events.build` | Compute `season_r` once from the season's detections (`fire_pixel_area`). Pass it to `summarise` and `snapshots`. |
| `events.snapshots` | Add `new_pixels` / `cum_pixels`. Scale `growth_ha` / `cum_area_ha` with the same factor, MODIS cells excluded. |
| New `events.fire_pixel_area` (§5.1) | Season totals by `provinsi` / `kabupaten`, written to a new `area_summary` table (season, region, fire_pixels_1sat, burned_ha, lo, hi, sats, k). |
| `pipeline/src/haze/db.py` | Schema: `fire_events.fire_pixels`, `event_snapshots.cum_pixels`, table `area_summary`. |
| `pipeline/src/haze/publish.py` `dashboard` | Take `by_provinsi.area_ha` and a national total from `area_summary`, **not** `live.groupby(...).est_area_ha.sum()`. Add `area_lo/hi`, the official SiPongi figure and its `last` month. Rank `top_growth` by new pixels. |
| `publish.tables` | Take `regions.json` `area_ha` from `area_summary` (not Σ events). Add `fire_pixels` to `fires-{season}.json`. |
| New `haze official-area` step | Fetch `/api/list/luas-kebakaran/provinsi` (and `/kabupaten`) and parse the id-ID numbers. Store in an `official_area` table, used for display and to re-fit k each year. |
| `web/src/i18n.ts` (`area`, `growth`, the line at 41/196) | Event: "Piksel api" plus "≈ ha indikatif". National and province: "Perkiraan luas terbakar (dikalibrasi KLHK)" with range. |
| `web/src/EventPanel.tsx`, `Dashboard.tsx`, `data.ts` | Show `fire_pixels` as the event KPI and ranges on the dashboard. Hide area for MODIS-only events. |
| `docs/models.md` | Add a "Burned area" section that summarises §5 and links here. |

## 7. Reproduction

Scripts are in the session scratchpad (`scripts/build_hist.py`, `decompose.py`, `metrics.py`,
`calib.py`, `peatfit.py`, `jitter.py`, `discunion.py`, `recommended.py`). To reproduce:

1. Copy the DB.
2. Run `HAZE_DATA_DIR=<scratch> HAZE_DB=<copy> python build_hist.py <copy>`. This loads the FIRMS
   2019 and 2023 archives from
   `https://firms.modaps.eosdis.nasa.gov/data/country/{modis,viirs-snpp,viirs-jpss1}/{year}/…_Indonesia.csv`
   and rebuilds the events.
3. Run the analysis scripts read-only against the copy.

The production DB copy was never written to.
