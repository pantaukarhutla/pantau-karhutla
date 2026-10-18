# Claims audit: every number and label a user sees

Date: 17 Oct 2026. Reviewer stance: a hostile fact-checker, whether a data journalist or a
government analyst trying to discredit the site.

**Snapshot used for checking**

- Production DuckDB, read-only copy. The last run finished 2026-10-17 13:14Z.
- Published JSON. `dashboard.json` was generated at 2026-10-17 18:10Z, which is 01:10 WIB on 18 Oct.
  `smoke/*` was generated at 17:00–17:50Z, and `spread/*` at 13:00Z.
- The code at commit `45ddcc8`, which includes the new Data view.

**Independent sources**

- SiPongi (Kemenhut), from news citations and its own hotspot feed.
- Databoks/Katadata, from FIRMS VIIRS.
- ASMC, from news.
- Kemenhut/SiPongi burned area.
- The raw ISPU (KLH) station feed.
- 2019 and 2023 ministerial statements on transboundary haze.
- GFW and the NASA FIRMS country summaries were **not** pulled. The DB *is* FIRMS, so the useful
  check is against the official SiPongi numbers.

**Verdicts**

- **OK**: accurate and adequately caveated.
- **Fix**: defensible, but mislabelled, over-precise or missing a caveat.
- **Remove**: cannot be defended in its current form.

## 0. The headline finding: the same data gives three very different numbers

These are the same FIRMS detections, counted three ways:

| Window | SiPongi (official) | haze, same satellites as SiPongi | haze as published (adds NOAA-21) |
| --- | --- | --- | --- |
| 24 h to 13 Sep 2026 11:36 WIB, national, all confidence | **11,711** | 13,283 | **20,497** |
| …Kalimantan Tengah | 3,790 | 3,856 | 6,456 |
| …Kalimantan Barat | 1,376 | 1,373 | 2,622 |
| 5 Oct 2026, national, **high confidence only** (the headline figure Kemenhut uses) | **1,359** | 1,500 | 1,995 high / **34,145 all** |
| …Kalimantan Tengah | 569 | – | 807 high / 9,542 all |
| Kalimantan, 8–15 Oct, VIIRS (Databoks) | 34,226 | 35,024 (NOAA-20 alone) | 90,904 (3 VIIRS) |

- **When it matches.** Restricted to Terra/Aqua + S-NPP + NOAA-20 at all confidence levels, haze
  reproduces SiPongi's provincial numbers almost exactly (Kalbar 1,373 vs 1,376). That makes it
  credible.
- **When it doesn't.** As published, haze adds NOAA-21 and labels everything "titik api". Its
  numbers then run **1.6–1.7× SiPongi's all-confidence count** and **~25× the high-confidence
  headline count**.
- **Why it matters.** A government analyst only needs one screenshot next to SiPongi to call the
  site inflated. Every count on the site needs its method stated next to it, and the counts need
  to be offered in a SiPongi-comparable form.

## 1. Claims table

Verdicts: OK / Fix / Remove. In the Suggested fix column, **ID** is the new Bahasa string and
**EN** the new English one.

### Header, terminology and sourcing

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 1 | "Titik api dari satelit NASA, dikelompokkan per lokasi kebakaran" / "NASA FIRMS satellite hotspots, grouped into fire events" | `i18n.subtitle` | Fix | **Wrong term.** KLHK and BMKG use *titik panas* for a satellite hotspot and insist it is "bukan jumlah kejadian kebakaran". In 2023 Minister Siti Nurbaya accused Malaysia of "confusing hotspots with firespots", so this is exactly the line a government critic will use. **Wrong attribution.** NOAA-20/21 are NOAA satellites, not NASA ones; NASA FIRMS distributes the data. | **ID** "Titik panas dari satelit (data NASA FIRMS), dikelompokkan menjadi lokasi kebakaran" · **EN** "Satellite hotspots (NASA FIRMS data), grouped into fire locations" |
| 2 | "Titik api" for each detection, used everywhere: `hotspots`, `historyChart`, `data24h`, `data7d`, `dataSeason`, `dataRegionsNote` | i18n (many keys) | Fix | Same as #1. EN already says "hotspots"; ID doesn't. | Replace "titik api" with **"titik panas"** in every ID string. Keep "kebakaran" only for clustered events. EN: keep "hotspots". |
| 3 | No disclaimer that this is an unofficial site. "Pantau Karhutla" sounds like a government service. | header / footer | Fix | No string says who runs the site or that it is not official. A ministry can easily say the site "menyesatkan publik". | Add to the footer. **ID** "Bukan situs resmi pemerintah. Angka resmi: SiPongi (Kemenhut), BMKG, ISPU (KLH)." · **EN** "Not an official government site. Official figures: SiPongi (Ministry of Forestry), BMKG, ISPU (KLH)." Link all three. |
| 4 | "Sumber: NASA FIRMS (VIIRS, MODIS)…" | `i18n.source`, dashboard footer | Fix | **Satellites not named.** It doesn't list the five satellites, which is the main reason haze's counts differ from SiPongi's. **Credits incomplete.** CAMS, Open-Meteo, ISPU/DOE/NEA, KHG and geoBoundaries appear only in the collapsed map attribution. | **ID** "Sumber titik panas: NASA FIRMS — VIIRS (S-NPP, NOAA-20, NOAA-21) dan MODIS (Terra, Aqua), tingkat kepercayaan sedang & tinggi. SiPongi tidak memakai NOAA-21, jadi angka kami lebih tinggi. Asap: CAMS (Copernicus) via Open-Meteo. Udara: ISPU (KLH), DOE Malaysia, NEA Singapura." · **EN** "Hotspots: NASA FIRMS — VIIRS (S-NPP, NOAA-20, NOAA-21) and MODIS (Terra, Aqua), nominal and high confidence. SiPongi does not use NOAA-21, so our counts run higher. Haze: CAMS (Copernicus) via Open-Meteo. Air: ISPU (KLH), Malaysia DOE, Singapore NEA." |
| 5 | README: "A live map of every active fire in Indonesia" | README.md | Fix | **Coverage.** Clouds, thick smoke, small fires (< ~375 m pixel) and underground peat smouldering are missed; BMKG and KLHK both say "tidak munculnya hotspot bukan berarti bebas kebakaran". **Grouping accuracy.** The clustering itself is 76–98% "correct" by one non-expert reviewer (clustering-evaluation.md). | "A live map of satellite-detected fire activity in Indonesia. Clouds, smoke and small or underground fires are missed." |

### Freshness and status counts

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 6 | "Deteksi terbaru: 17 Okt 19.25 WIB · 6 jam lalu" | Dashboard freshness | Fix | **Frozen age.** `lag_hours` is computed at publish time and shown as-is. If the pipeline stops, the page keeps saying "6 jam lalu" indefinitely, and the "stale" banner never fires. **Misleading "latest".** The newest detection (12:25Z) is a single **Terra MODIS** pass. VIIRS supplies 95% of detections, and its newest pass is NOAA-20 at 07:03Z; S-NPP's is 16 Oct 19:42Z. | Compute the age from `Date.now()` in the browser, and show the newest VIIRS time. **ID** "Deteksi VIIRS terbaru: {waktu} WIB ({n} jam lalu) · MODIS: {waktu} WIB" · **EN** "Latest VIIRS pass: {time} WIB ({n} h ago) · MODIS: {time} WIB" |
| 7 | "Aktif 2.939" | Dashboard KPI | Fix | **Inflated by single detections.** 1,135 of 2,939 active events (39%) are a **single detection**, and 1,609 (55%) have ≤ 2. Only 625 (21%) have ≥ 10. One nominal-confidence pixel seen once is not "an active fire" to a reader. **No definition.** The UI never says that "active" means "seen < 24 h". | **Option 1**: show "Aktif 2.939 lokasi · 1.804 dengan ≥ 2 deteksi" (computed). **Option 2**: count only events with ≥ 2 detections in the KPI. Add the tooltip **ID** "Lokasi dengan titik panas dalam 24 jam terakhir. Satu titik panas belum tentu kebakaran." · **EN** "Locations with a hotspot in the last 24 h. A single hotspot is not necessarily a fire." |
| 8 | "Mereda 3.688" / "Cooling" | Dashboard KPI, badges | Fix | **Singletons.** 43% (1,586) are single detections. **Unknown cause.** "Mereda" claims the fire is dying down. All the data says is "no detection for 24–72 h", which can be cloud or smoke cover, or peat smouldering below the surface. | **ID** "Tidak terdeteksi 1–3 hari" (tooltip: "Bisa karena api mengecil, tertutup awan/asap, atau membara di bawah gambut.") · **EN** "Not seen for 1–3 days" (tooltip: "The fire may be dying down, hidden by cloud or smoke, or smouldering in peat.") |
| 9 | "Padam" / "Out" | Event panel badge for status `out` | **Remove** | **Unsupported.** "Padam" asserts the fire is extinguished. The pipeline only knows there has been no detection for > 72 h. On peat, which is 97–100% of the largest events, this is often false. **Already contradicted.** The site's own `peatNote` says peat burns unseen. | **ID** "Tidak terdeteksi > 3 hari" · **EN** "Not seen for 3+ days" |
| 10 | "Baru hari ini 0" | Dashboard KPI | Fix | **Shows 0 for hours after midnight.** At publish (01:10 WIB, 18 Oct) it shows **0**, while `daily` shows 1,614 new events on 17 Oct. "Hari ini" resets at WIB midnight, before any satellite pass. **Singletons.** Many of the new events are single detections. | Use a rolling window. **ID** "Baru (24 jam terakhir)" · **EN** "New (last 24 h)". Show the ≥ 2-detection count as in #7. |

### Season chart

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 11 | Season chart "Musim ini dibanding tahun-tahun terparah": 2026 vs 2015/2019/2023, S-NPP only | Dashboard | Fix | **The method is sound.** Same filters as the baselines; S-NPP only; continuous across the SP→NRT switch on 1 Jul (S-NPP/NOAA-20 ratio ≈ 1.0 on 30 Jun–2 Jul); all Collection 2. **What it shows.** Cumulative S-NPP hotspots to 17 Oct: 2026 **500,641**, 2015 628,406, 2019 313,499, 2023 169,100. Read naively, 2026 is "60% worse than 2019". **Contradicting signals.** Singapore's 2026 PSI peak so far is 181 (9 Oct), vs ~240 in 2019 and >300 in 2015. Official burned area for 2026 is only available to July (202,004 ha). **Data gap.** S-NPP had only 124 detections on 13 Oct (vs ~8,000 on nearby days), and nothing in the chart flags it. **Incomplete day.** Today's partial day is plotted like a complete one. **Missing labels.** No y-axis label; the y-axis is "k". | Keep the chart. **Title** ID "Jumlah titik panas kumulatif (satelit S-NPP) dibanding tahun El Niño sebelumnya" · EN "Cumulative hotspots (S-NPP satellite) vs past El Niño years". **Note** ID "Hanya satelit S-NPP agar adil antartahun. Ini jumlah titik panas, bukan luas terbakar: luas resmi 2026 baru tersedia s.d. Juli (SiPongi). Hari ini belum lengkap." · EN "S-NPP only, so years compare fairly. These are hotspot counts, not burned area: official 2026 burned area is only available to July (SiPongi). Today is incomplete." Mark days with < 20% of the 7-day median S-NPP count as "data satelit tidak lengkap / incomplete satellite data". |

### Fastest-growing fires

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 12 | "Meluas paling cepat (24 jam terakhir)" vs EN "Fastest growing (latest day)" | Dashboard heading | Fix | **The two languages disagree, and both are inaccurate.** The value is `growth_ha` of each event's **latest WIB calendar day with detections**. **Different days are mixed.** That day can be up to 72 h old for cooling events; Fakfak's entry is from 16 Oct, the others from 17 Oct. The 17 Oct values are partial days. **No date shown.** | **ID** "Penambahan area deteksi terbesar (hari terakhir terdeteksi)" · **EN** "Largest new detected area (latest day seen)". Show the date on each row ("17 Okt"). |
| 13 | "+4.655 ha" (Kumai, Seruyan), and the rest of the list | Dashboard list | Fix | **Over-precise.** 4,654.69 ha = **331 new 375 m grid cells** × 14.0625 ha. The "+4.655 ha" is reported to the hectare, from pixels of 14+ ha, with off-nadir VIIRS pixels up to ~0.6 km² (`scan × track` max 0.624 km²). **Driven by satellite count.** The 1,143 detections that day come from **3 VIIRS satellites + 1 MODIS**, with different geolocation. More overpasses or clearer skies give more unique cells, so "growth" tracks sampling as much as fire. The same event's daily growth went 8,016 → 6,975 → 3,094 → 5,850 → 1,491 → 2,503 → 4,655 ha (11–17 Oct). **Not burned area.** It is the detected footprint, and the heading says "meluas" (spreading). | Round to 2 significant figures and say what was counted. **ID** "+≈4.700 ha (331 piksel baru)" · **EN** "+≈4,700 ha (331 new pixels)". Tooltip: **ID** "Piksel satelit 375 m yang baru terdeteksi panas, dari semua satelit VIIRS. Bukan luas terbakar terukur." · **EN** "New 375 m satellite pixels with a hotspot, all VIIRS satellites. Not measured burned area." Better still, rank on S-NPP + NOAA-20 only, so the ranking doesn't depend on how many satellites passed. |
| 14 | Fire name "Kumai, Seruyan" | Every list, panel, transboundary | Fix | **Wrong place.** Nearest-town logic names the fire after **Kumai, 62.1 km away**, which is in Kotawaringin Barat, joined to the majority kabupaten Seruyan. The id says `kotawaringin-barat-…`. **Not one fire.** The event spans 0.51° × 0.53° (~56 × 59 km), and it is credited with 120,487 ha. **Blame risk.** Locals will read it as "the Kumai fire". Naming a village as the source of haze (#30) can be read as blaming its residents. | Name by kabupaten, and add the town only if it is ≤ 10 km away. **ID** "Kompleks kebakaran Seruyan (dekat Kumai, 62 km)" · **EN** "Seruyan fire complex (62 km from Kumai)". Use "Kompleks" / "complex" for events > 10 km across. |

### By-province table

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 15 | "Per provinsi (aktif & mereda)", sorted by event count; "Papua 1.141 kebakaran" ranks above "Kalimantan Tengah 862" | Dashboard table | Fix | **Misleading ranking.** Sorting by event count rewards fragmentation. Papua has 1,141 events with 42k hotspots; Kalteng has 862 events with **242k** hotspots. **Inflated counts.** The event counts include single detections (#7). | Sort by hotspots in the last 7 days, and show that column. **Header** ID "Provinsi · lokasi aktif & tidak terdeteksi 1–3 hari · titik panas 7 hari" · EN "Province · active & not-seen-1–3-days locations · hotspots, 7 days". |
| 16 | Province names: 34 provinces, including "Papua" and "Papua Barat" | Dashboard, Data view, history, transboundary | Fix | **Out-of-date map.** geoBoundaries ADM1/ADM2 is BPS 2020, from before the **2022 split into 38 provinces**. "Papua" here includes Papua Selatan (Merauke, Boven Digoel, Mappi), Papua Tengah and Papua Pegunungan; "Papua Barat" includes Papua Barat Daya. **Doesn't match the official figures.** SiPongi reports Papua Selatan separately (1,259 hotspots in its 17 Oct feed). An analyst will say "your Papua number is wrong". `stations.py` already uses the new names, so the site is internally inconsistent too. | Switch to 2022+ boundaries: BIG/Kemendagri, or the HDX COD-AB update. Until then, note it. **ID** "Batas wilayah: BPS 2020 (34 provinsi). Papua termasuk Papua Selatan, Tengah, Pegunungan; Papua Barat termasuk Papua Barat Daya." · **EN** "Boundaries: BPS 2020 (34 provinces). Papua includes Papua Selatan, Tengah and Pegunungan; Papua Barat includes Papua Barat Daya." |
| 17 | Unlabelled area column, e.g. "Kalimantan Tengah … 662k ha" | Dashboard table | **Remove** (or relabel) | **No header**, so it reads as burned area. **What it sums.** The whole-season detected footprint of every active or cooling event. A single event (#14) contributes 120k ha. **Contradicts the official figure.** SiPongi's official 2026 burned area for Kalteng is **7,634 ha** (Jan–Jul). The Data view CSV `wilayah-2026.csv` exports `area_ha` totalling **11.9 Mha for 2026**. That is 4.5× the official 2015 record (2.61 Mha) and 7× 2019 (1.65 Mha). It is the single most quotable "proof" that the site is wrong. **Cause.** Five satellites accumulate unique cells over months; this is not burned area (README says so, but the UI doesn't). | Remove it from the dashboard table and from the regions CSV. If kept, rename it everywhere and drop it from province sums. **ID** "Piksel terdeteksi panas (bukan luas terbakar)" · **EN** "Hotspot pixels (not burned area)". Add: **ID** "Luas terbakar resmi: SiPongi (Kemenhut), dihitung dari citra Landsat dan diperbarui berkala." · **EN** "Official burned area: SiPongi (Ministry of Forestry), mapped from Landsat imagery and updated periodically." |
| 18 | "Perkiraan luas 120k ha" + `estimateNote` | Event panel | Fix | `estimateNote` is good. **Wrong unit and word.** "k" is not Indonesian. "Luas" invites comparison with burned area. | **ID** "Area terdeteksi panas ≈ 120 ribu ha" · **EN** "Detected hotspot area ≈ 120k ha". `fmtHa`: use "rb" in ID, 2 significant figures, and a "≈" prefix. |
| 19 | "Luas terbakar, kumulatif (ha)" | Event panel chart title | Fix | It says "terbakar" (burned), which contradicts `estimateNote` right below it. | **ID** "Area terdeteksi panas, kumulatif (ha)" · **EN** already "Cumulative area (ha)", change to "Cumulative detected area (ha)". |

### Event panel

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 20 | "Intensitas harian (FRP, MW)" and "Tinggi kolom = total energi api (FRP)" | Event panel, legend | Fix | **Unit error.** FRP is *power* (MW). Summing instantaneous FRP over every overpass and satellite is not energy, and not "daily intensity". **Depends on overpasses.** The value scales with how many satellites passed. | **ID** "Jumlah FRP dari semua deteksi hari itu (MW)" / legend "Tinggi kolom = jumlah daya radiasi api (FRP) semua deteksi" · **EN** "Sum of FRP over the day's detections (MW)" / "Column height = summed fire radiative power of all detections" |
| 21 | "Di lahan gambut" (`on_peat`) | Event panel callout; also drives smoke emissions | Fix | **What the flag means.** It is based on lying inside a **KHG unit**, a *peat hydrological unit* that includes mineral soil between and around domes. It is not peat extent. **Large knock-on effect.** The flag switches the smoke model to peat factors (β 5.87 vs 0.78, EF 20 vs 4.9 g/kg), i.e. **~30× more PM2.5 per MW**. So it drives "gambut 89%" in the attribution. | **ID** "Di dalam Kesatuan Hidrologis Gambut (KHG)" · **EN** "Inside a peat hydrological unit (KHG)". Long term: intersect with a peat-depth/extent map (BBSDLP 2019). |
| 22 | "Dekat sumber panas industri — bisa jadi bukan kebakaran" | Event panel | OK / Fix | Good caveat. However, static sources include **volcanoes** and gas flares, not only industry. | **ID** "Dekat sumber panas tetap (industri, suar gas, atau gunung api) — bisa jadi bukan kebakaran" · **EN** "Near a permanent heat source (industry, gas flare or volcano) — may not be a fire" |
| 23 | Permit-holder (PBPH) section | Event panel | OK | Hidden in the UI (`SHOW_LAND = false`) and withheld by the pipeline. `landNote` already says detection inside a permit ≠ the holder caused it. Keep it hidden until legal review. | No change. |

### History mode

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 24 | History "Jumlah titik api per hari" / "Titik api harian sejak 1 Jul", with the per-day top-5 provinces | History panel and slider | Fix | **Built with different filters from the rest of the site.** `history.daily_fires` filters only `is_static`. It **includes low-confidence detections and detections outside Indonesia**. **5 Oct, for example.** It shows 37,646 detections: 3,501 (9.3%) are in Malaysia, PNG or Timor-Leste, and 2,692 are low confidence. The dashboard uses 31,869 that day, and SiPongi's high-confidence count is 1,359. **Satellites.** All 5 satellites, including NOAA-21 (see §0). **Data gap.** The 13 Oct dip (11,949) is the S-NPP gap, not a lull. `historyChartNote` is good but understates all of this. | Apply `in_indonesia AND confidence IN ('nominal','high')`, as in the dashboard. **Title** ID "Titik panas per hari (5 satelit, kepercayaan sedang–tinggi)" · EN "Hotspots per day (5 satellites, nominal–high confidence)". **Note** ID "Satu lokasi bisa terhitung beberapa kali dalam sehari. Angka ini sekitar 1,6× angka SiPongi karena kami juga memakai satelit NOAA-21. Hari dengan data satelit tidak lengkap ditandai." · EN "One place can be counted several times a day. Numbers run ~1.6× SiPongi's because we also use NOAA-21. Days with incomplete satellite data are marked." |
| 25 | `historyNote`: "PM2.5 harian berasal dari model CAMS tanpa koreksi data stasiun…" | History panel | OK | Accurate and honest. **Inconsistency between modes.** Live mode is corrected, history is not, so switching modes produces an artificial jump. | Add **ID** "Peta Terkini sudah dikoreksi stasiun, jadi tidak bisa dibandingkan langsung." · **EN** "The Live map is station-corrected, so the two are not directly comparable." |

### Stations and the CAMS comparison

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 26 | Station list "Kualitas udara saat ini (hasil ukur stasiun)": top 8 by PM2.5, e.g. "Palangkaraya Jekan Raya 1470 µg/m³ Berbahaya", "Kabupaten Katingan 1184", "Kabupaten Kampar 441 Berbahaya" | Sidebar, `StationsList` | Fix | **Bands match.** The ISPU bands match P.14/2020, and agree with KLH's own category at 100 of 105 stations. **Readings KLH itself excludes.** In the raw ISPU feed, **Katingan (a_pm25 1,036)** and **Kampar (494)** have `c_pm25 = null`: KLH did not use their PM2.5 in the official index. KLH's official categories for them are **BAIK** and **SEDANG**; haze shows **Berbahaya** for both. Aceh Selatan (193) is the same. A government analyst can show the ISPU site saying "Baik" next to haze saying "Berbahaya". **Precision and timing.** Values are single unvalidated hourly readings, shown to the µg, up to 6 h old, with no per-row time. **DOE estimates.** DOE values are inverted from Malaysia's API, which is based on a **24 h average** for PM2.5, so they are not "per jam". | Drop ISPU PM2.5 where `c_pm25` is null, both from the list and from the CAMS ratio. Show the reading time per row and round to 2 significant figures above 100 ("≈1.500"). **Note** ID "Data mentah per jam dari stasiun ISPU (KLH) dan NEA Singapura, belum divalidasi. Angka Malaysia (≈) diperkirakan dari indeks API DOE yang berbasis rata-rata 24 jam. Kategori mengikuti batas PM2.5 ISPU (P.14/2020) dan bisa berbeda dari kategori resmi di ispu.kemenlh.go.id." · EN "Raw, unvalidated hourly readings from ISPU (KLH) and Singapore NEA stations. Malaysian values (≈) are estimated from the DOE API index, which uses 24 h averages. Categories use the ISPU PM2.5 breakpoints (P.14/2020) and may differ from the official category at ispu.kemenlh.go.id." |
| 27 | "Di wilayah berasap, model CAMS hanya menunjukkan sekitar 26% dari angka stasiun. Karena itu, peta kabut asap sudah kami koreksi dengan data stasiun." | `StationsList` callout | Fix | **The number reproduces.** It is the median CAMS/obs ratio over the **33 stations reading > 100 µg/m³** at one hour. **Biased by selection.** Picking stations *because* they read high biases the ratio low (regression to the mean). Over all 111 stations the median ratio is **0.85**. **Not like for like.** It compares a point reading with a 0.75° (~80 km) grid cell, for one hour. **Flawed inputs.** It includes the Kampar reading that KLH excluded (#26). **Direction is right, number overstated.** CAMS does underestimate peat haze in the literature, but "only 26%" reads as a general fact about CAMS. | **ID** "Pada {jam} WIB, di {n} stasiun yang mencatat PM2,5 di atas 100 µg/m³, model CAMS rata-rata hanya sekitar seperempat angka stasiun (di semua {N} stasiun: {r}%). Karena itu, peta kabut asap dekat stasiun kami sesuaikan dengan data stasiun." · **EN** "At {time} WIB, at the {n} stations reading above 100 µg/m³, CAMS showed about a quarter of the station value (across all {N} stations: {r}%). Near stations, the haze map is adjusted towards the measurements." |

### Cities table and smoke arrival

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 28 | Cities table "PM2.5 dari prakiraan CAMS (semua sumber polusi)", with "Puncak 72 jam" + ISPU band | `Cities` | Fix | **The source label is wrong.** The values are **CAMS × station correction** (up to 8×, faded over 48 h), not CAMS. **Absurd peak.** Palangkaraya shows a forecast peak of **3,732 µg/m³**, which no instrument has recorded and which is an artefact of the ×8 clip. **Wrong band period.** The ISPU band is applied to a 1 h forecast peak; the ISPU category is meant for a sustained level. **Misleading title.** "Kota yang terpapar asap" also lists Jakarta, Bekasi etc. (~190 µg/m³ peaks, fire-smoke index ≈ 0.9), whose pollution is urban. | Cap the displayed values (e.g. "> 500"). **Title** ID "PM2,5 kota: sekarang, puncak 72 jam, dan perkiraan asap kebakaran" · EN "City PM2.5: now, 72 h peak, and modelled fire smoke". **Note** ID "PM2,5 dari prakiraan CAMS (semua sumber polusi), disesuaikan dengan stasiun terdekat untuk 48 jam pertama. Angka di atas 500 ditampilkan '> 500' karena di luar kemampuan model." · EN "PM2.5 from the CAMS forecast (all pollution sources), adjusted to nearby stations for the first 48 h. Values above 500 are shown as '> 500', beyond what the model can resolve." |
| 29 | "Asap tiba 18 Okt 03.00" | `Cities` column | Fix | **Wrong for cities already in smoke.** Five cities, **including Palangkaraya, which is already measuring 1,470**, get the *first model frame* (+3 h) as their "arrival". **Over-precise.** Times are given to the minute from 3-hourly frames on a 1.5° (~165 km) wind grid, using an uncalibrated index threshold of 15. **No time zone.** The column lacks "WIB", and Singapore and Malaysia readers are on UTC+8. | If the first frame is ≥ threshold, show **ID** "sudah berasap" / **EN** "already smoky". Otherwise round to a half-day: **ID** "Sab 18 Okt, pagi (WIB)" · **EN** "Sat 18 Oct, morning (WIB)". Rename the header: **ID** "Asap kebakaran tiba (model)" · **EN** "Fire smoke arrives (model)". |

### Cross-border attribution

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 30 | "Asap lintas batas: dari mana asapnya?" Singapore: "Dari Jambi 42% · Sumatera Selatan 38% · gambut 89%", "Penyumbang terbesar: Simpang, Muaro Jambi (17%)", next to "98 Tidak sehat · terukur" | `TransboundaryPanel` | **Fix (high priority)** | (a) **Only Indonesian fires can be sources, by construction.** Sources are `fire_events`, which are `in_indonesia` only. A Malaysian or Bruneian city can never be attributed to local fires; the "Luar Indonesia" fallback can never occur. This is *exactly* Indonesia's 2019 argument ("haze in KL came from Sarawak and Peninsular Malaysia"). It is true that in the last 48 h only 101 non-low hotspots were in MY/BN vs 30,874 in Indonesia, but the method cannot show that. (b) **The shares rest on almost no smoke.** Singapore's 24 h index sum is **10.0**. That clears the weak-signal flag (5), but the city never reaches the arrival threshold (15 in any frame; `arrival: null`). Put next to a measured 98 µg/m³, a reader concludes "42% of Singapore's PM2.5 is from Jambi". The model says close to *nothing* of that 98 is modelled fire smoke. (c) **Shares shown where there is no smoke at all.** KL (0.3), Kota Kinabalu (0.0) and Bandar Seri Begawan (0.0) still show shares ("Kalimantan Timur 70%"), only chipped "sinyal lemah". (d) **False precision.** Integer percentages from a single-member model with no ensemble and an uncalibrated emission factor (Kiely 2019: 1.4–3.5× low). (e) **Blame risk.** Naming a village ("Simpang") as the "largest contributor" to another country's haze. (f) **"terukur" is wrong for Malaysia.** DOE values are estimates. | Hide shares unless the modelled smoke reaches the arrival threshold. Round to 10% and use words for small shares. Put the model caveat *above* the numbers. **Intro** ID "Model kami memperkirakan dari provinsi mana asap kebakaran **di Indonesia** yang sampai ke kota ini dalam 24 jam ke depan. Kebakaran di Malaysia, Brunei, dan negara lain tidak dimodelkan, dan model ini tidak mengukur polusi kota itu sendiri." · EN "Our model estimates which provinces the smoke from fires **in Indonesia** reaching each city over the next 24 h comes from. Fires in Malaysia, Brunei and elsewhere are not modelled, and the model does not measure the city's own pollution." **Row** ID "Asap kebakaran model: sangat sedikit — tidak ada pembagian" when below threshold; else "Sebagian besar dari Jambi dan Sumatera Selatan (≈ 40% / 40%)". EN "Modelled fire smoke: very little — no breakdown" / "Mostly from Jambi and South Sumatra (≈ 40% / 40%)". **Biggest contributor** ID "Kompleks kebakaran terbesar: Muaro Jambi" · EN "Largest fire complex: Muaro Jambi" (no village names). **Label** "terukur" only for ISPU/NEA; ID "perkiraan dari indeks API" / EN "estimated from API index" for DOE. |
| 31 | docs/models.md: "Singapore: Jambi 42%, South Sumatra 38%, peat 89% … consistent with Reddington 2014 and Koplitz 2016" | docs | Fix | Same single run with a weak signal (index 10). Calling it "consistent" with multi-year studies from one 24 h run oversells it. Point (a) of #30 applies too. | Add: "On 17 Oct the modelled smoke reaching Singapore was weak (24 h index 10, below the arrival threshold), so this split is illustrative only. Non-Indonesian fires are not modelled." |

### Spread forecast

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 32 | "Prakiraan sebaran api (eksperimental)" + note "…Dikalibrasi dengan data 2019 dan diuji dengan data 2023. Hasilnya berupa peluang, bukan kepastian." | Event panel, map layer (on by default) | Fix | **"Tested" suggests the full model was validated.** The hindcast used **no wind or rain** (the archive has none), so the wind, rain and slope terms the note lists were *never tested*. **Skill is modest.** AP 0.083 vs 0.055 for persistence; CSI 0.115 vs 0.110, i.e. it only ties "assume today's fire stays". **Docs and output disagree.** Bands are 0.2/0.4/0.6 in the output but 0.25/0.5/0.75 in models.md, and the legend shows no values. **No timestamp.** The spread was generated at 13:00Z and the panel shows no time. **Default.** The layer is on by default. | Turn the layer **off by default**. **Note** ID "Simulasi eksperimental. Dalam uji data 2023 (tanpa data cuaca), hasilnya hanya sedikit lebih baik daripada menganggap api tetap di tempatnya. Pengaruh angin dan hujan belum diuji. Dibuat {waktu} WIB." · EN "Experimental simulation. In a 2023 test (without weather data) it did only slightly better than assuming the fire stays where it is. The effect of wind and rain has not been tested. Made {time} WIB." Legend: "20% / 40% / 60%". Fix the levels in models.md. |
| 33 | "Perkiraan area terbakar baru 4.365 ha" (+24 h) | Event panel | Fix | **Over-precise.** This is the sum of cell probabilities × 14.06, shown to the hectare. **Wrong word.** The model predicts cells with detected heat, not burned area. **No range.** There are 64 members, but no spread across them is shown. | **ID** "Area baru yang mungkin terdeteksi panas: ≈ 4.400 ha (kisaran {p10}–{p90})" · **EN** "New area likely to show hotspots: ≈ 4,400 ha (range {p10}–{p90})" |

### 3D fire and smoke visuals

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 34 | 3D flames ("Api (3D)") and legend "Api aktif" | Map | Fix | **Close up (zoom ≥ 9).** A flame is drawn at the **centre of every detection pixel < 12 h old**. Pixels are 375 m (VIIRS) to 1 km (MODIS), with geolocation error, and the flame keeps burning for 11 h after a single overpass. **From afar.** Flames sit at **event centroids**, the mean of detections. For a 56 km complex the centroid can fall on unburned land or a village. **History mode.** Flames are drawn at the centres of **0.05° (~5.5 km) bins**, including low-confidence and out-of-country detections, all at a fixed "age 6 h". **Smoke and scar.** Smoke billboards bend with the forecast wind regardless of the plume model. The "burn scar" is half-pixel buffers around detections, not mapped burned area. A screenshot can be read as "flames here, now". | Add a small persistent caption in 3D. **ID** "Ilustrasi. Api digambar di pusat piksel satelit (375 m–1 km) yang terdeteksi panas dalam 12 jam terakhir, bukan lokasi nyala api yang sebenarnya." · **EN** "Illustration. Flames are drawn at the centre of satellite pixels (375 m–1 km) with a hotspot in the last 12 h, not at actual flame locations." **Legend** ID "Titik panas (ilustrasi api)" · EN "Hotspot (flame illustration)". In history mode, draw dots instead of flames. Rename the scar to ID "Jejak titik panas hari sebelumnya" / EN "Earlier hotspot footprint". |
| 35 | "Kabut asap (PM2.5)" layer, and the sky/fog tint from PM2.5 | Map | OK / Fix | The layer is CAMS corrected by stations (see #28); its label doesn't say so. The ×8 cap can paint implausible values near stations. | Layer tooltip: **ID** "Prakiraan CAMS, disesuaikan dengan stasiun terdekat" · **EN** "CAMS forecast, adjusted to nearby stations". |
| 36 | "Sebaran asap kebakaran (model)" | Map layer | OK | Labelled as a model. `plumes.json` notes "relative index, not a calibrated concentration", but that note isn't in the UI. | Tooltip: **ID** "Indeks relatif, bukan konsentrasi terukur" · **EN** "Relative index, not a measured concentration". |

### Data view (added in 45ddcc8)

| # | Claim | Where | Verdict | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- |
| 37 | "Titik api 24 jam / 7 hari / musim ini", "Kebakaran aktif" | Data view | Fix | **Not the dashboard's filter.** `tables.regions` counts **include low-confidence** detections, unlike the dashboard and events. The note says only "bukan sumber panas industri". **Not comparable with SiPongi.** It uses NOAA-21 (§0). **Inflated.** "Kebakaran aktif" includes singletons. **Area exported.** The CSV exports `area_ha` (#17). | Use the same confidence filter as the dashboard, rename to "titik panas", and drop `area_ha` from the export. **Note** ID "Titik panas = deteksi satelit VIIRS (S-NPP, NOAA-20, NOAA-21) dan MODIS dengan kepercayaan sedang–tinggi, tanpa sumber panas tetap. Satu lokasi bisa terdeteksi beberapa kali sehari. Angka ini lebih tinggi daripada SiPongi karena SiPongi tidak memakai NOAA-21." · EN "Hotspots = VIIRS (S-NPP, NOAA-20, NOAA-21) and MODIS detections, nominal–high confidence, excluding permanent heat sources. One place can be detected several times a day. Counts are higher than SiPongi's because SiPongi does not use NOAA-21." |
| 38 | "Hanya kebakaran dengan minimal 5 titik api musim ini" | Data view note | OK | Accurate. A sensible threshold that partly fixes #7 for this view. Change "titik api" → "titik panas". | ID "…minimal 5 titik panas…" |
| 39 | `hoursAgo`, `updated … WIB` timestamps on the station, transboundary and cities panels | Sidebar | OK / Fix | The station and transboundary panels show "diperbarui {time} WIB". Cities and spread show no time (#29, #32), and the dashboard's age is frozen (#6). | Add "diperbarui" to cities and spread. |

## 2. What is solid (worth saying when challenged)

- **Raw counts reproduce the official ones.** Restricted to SiPongi's satellites, haze matches
  SiPongi's per-province counts to within ~2% (Kalteng 3,856 vs 3,790; Kalbar 1,373 vs 1,376).
  The FIRMS ingestion, static mask and province tagging work.
- **The season comparison is methodologically careful.** S-NPP only; the same filters for every
  year; Collection 2 throughout; no break at the SP→NRT switch.
- **ISPU bands match the regulation.** They follow P.14/2020, and agree with KLH's own category at
  100 of 105 stations.
- **The plain-language notes are accurate.** `estimateNote`, `historyChartNote`, `historyNote`,
  `peatNote`, `landNote` and `tbNote` all say what the numbers are.
- **Permit holders are withheld.** Holding back permit-holder names pending legal review is the
  right call.

## 3. Top 10 fixes, in priority order

1. **Remove or rename the area columns that read as burned area.**
   - Covers the province table "662k ha", the CSV `area_ha` (11.9 Mha for 2026) and
     "Luas terbakar, kumulatif".
   - Official 2026 burned area is 202k ha (Jan–Jul), and Kalteng's is 7,634 ha. Next to that,
     this is the most damaging number on the site (#17, #18, #19, #37).
2. **Cross-border attribution.**
   - State that only fires in Indonesia are modelled.
   - Hide the province percentages unless the modelled smoke reaches the arrival threshold.
     Singapore is at index 10 with no arrival, but still shows "Jambi 42%".
   - Round the shares, and drop village names as "largest contributor" (#30, #31).
3. **Say "titik panas", not "titik api", in every Bahasa string.** Fix "satelit NASA" too
   (#1, #2).
4. **Put the satellites and confidence level next to every count, and give a SiPongi-comparable
   figure.**
   - Haze's numbers are 1.6× SiPongi because of NOAA-21, and ~25× SiPongi's high-confidence
     headline.
   - Add a "Bukan situs resmi pemerintah" footer (#3, #4, §0).
5. **Stop counting single detections as fires in the headline KPIs.**
   - 39% of "Aktif" and 43% of "Mereda" are single detections.
   - Make "Baru hari ini" a rolling 24 h (it shows 0 after midnight WIB).
   - Rename "Padam" to "Tidak terdeteksi > 3 hari" (#7–#10).
6. **Station list and the "~26%" callout.**
   - Drop the ISPU PM2.5 readings that KLH itself excluded (`c_pm25` null). These are Katingan
     and Kampar, shown as "Berbahaya" where KLH shows Baik/Sedang.
   - Reword 26% as "at the 33 stations above 100 µg/m³", and give the all-station ratio (0.85)
     (#26, #27).
7. **Fastest-growing list.**
   - Make the two languages agree, and show each row's date.
   - Round to 2 significant figures ("≈4.700 ha, 331 piksel baru").
   - Rank on a fixed satellite set so the order doesn't depend on how many satellites passed
     (#12, #13).
8. **Cities and smoke arrival.**
   - Show "sudah berasap" instead of a fake arrival time, and round times to a half-day with WIB.
   - Cap the displayed PM2.5 (3,732 µg/m³ is an artefact of the correction).
   - Fix "dari prakiraan CAMS" to say "disesuaikan dengan stasiun" (#28, #29).
9. **Update the province boundaries to the 38 provinces (2022+), or label them as BPS 2020.**
   - Sort the province table by hotspots, not by event count (#15, #16).
   - Apply the dashboard's filters to the history counts (no low-confidence or out-of-country
     detections) (#24).
10. **Label the visuals and forecasts as what they are.**
    - 3D flames caption: "ilustrasi, di pusat piksel".
    - Spread layer off by default. Its note should say wind and rain were never tested and that
      skill only ties persistence on CSI. Show a timestamp and a range.
    - Fix the FRP "energi" wording.
    - Compute data freshness in the browser (#6, #20, #32–#34).

## Sources

**Official and media hotspot counts**

- Republika, 7 Oct 2026, quoting Kemenhut/SiPongi high-confidence counts:
  <https://news.republika.co.id/berita/tmiboa393/titik-panas-karhutla-nasional-melonjak-lagi>
- Databoks, 13 Sep 2026, SiPongi 24 h count by confidence and province:
  <https://databoks.katadata.co.id/datapublish/2026/09/13/kementerian-lhk-jumlah-titik-panas-di-indonesia-capai-11711-dalam-24-jam-terakhir-minggu-13-september-2026>
- Databoks, VIIRS hotspots in Kalimantan, 8–15 Oct 2026:
  <https://databoks.katadata.co.id/demografi/statistik/c41d1243366cd51/arah-angin-asap-karhutla-sepekan-titik-api-terpanas-843-mw-di-kalimantan>
- Metro TV, 18,065 hotspots on 28 Aug 2026:
  <https://www.metrotvnews.com/play/koGCaMPn-karhutla-meluas-18-065-titik-panas-terdeteksi-dalam-sehari>

**Official burned area**

- Kompas, SiPongi burned area Jan–Jul 2026 (202,004 ha):
  <https://lestari.kompas.com/read/2026/10/03/093745086/luas-karhutla-2026-melonjak-perbaikan-tata-kelola-lahan-dan-gambut-jadi>
- RCTI+/iNews, Kemenhut semester I 2026 (107,465 ha):
  <https://www.rctiplus.com/news/detail/terkini/5431931/karhutla-di-indonesia-capai-107-465-hektare--kalbar-paling-luas-terdampak>
- SiPongi per-province burned area 2015–2026, saved to the audit scratch folder as
  `sipongi_prov.csv`. Its 2026 total, 202,011 ha, matches the Kompas figure.

**Haze in Singapore and Malaysia, and ASMC hotspot counts**

- Outlook India, Singapore PSI 2026 high and Malaysian school closures:
  <https://www.outlookindia.com/international/indonesias-wildfire-haze-shuts-malaysian-schools-pushes-singapore-pollution-to-2026-high>
- The Vibes, ASMC hotspot counts for Kalimantan and Sumatra:
  <https://www.thevibes.com/articles/world/128329/indonesia-hotspots-spike-as-kalimantan-records-326-sumatra-303>
- Business Today, Singapore unhealthy air, 14 Sep 2026:
  <https://www.businesstoday.com.my/2026/09/14/singapores-central-region-returns-to-unhealthy-air-quality/>

**Indonesia's position on transboundary haze (2019, 2023)**

- Malay Mail, 11 Sep 2019, Jakarta says KL haze came from Sarawak and Peninsular Malaysia:
  <https://www.malaymail.com/news/malaysia/2019/09/11/jakarta-accuses-putrajaya-of-cover-up-insists-kl-haze-from-sarawak-peninsul/1789541>
- The Jakarta Post, 30 Sep 2023:
  <https://www.thejakartapost.com/world/2023/09/30/malaysia-blames-indonesian-fires-for-haze-poor-air-quality.html>

**"Titik panas" vs "titik api"**

- Tirto, BMKG on hotspots:
  <https://tirto.id/bmkg-pantau-titik-panas-yang-makin-bertambah-akibat-kemarau-cUok>
- Popbela, explainer on the difference between hotspots and fires:
  <https://www.popbela.com/career/working-life/sering-salah-paham-ini-beda-hotspot-dan-kebakaran-serta-cara-pantaunya-00-jclkf-swcfwt/amp>

**Malaysia's API method**

- SAYS: <https://says.com/my/news/aqi-api-explaining-malaysias-air-quality-confusion>
- Newswav: <https://newswav.com/article/why-myeqms-and-iqair-show-different-haze-readings-A2610_ToYVWG>

**ISPU raw feed**

- `ispu.kemenlh.go.id/apimobile/v1/getStations`, snapshot of 18 Oct 01:00 local, compared field by
  field (`a_pm25`, `c_pm25`, `cat`).
