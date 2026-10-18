# Research: features for fire prevention

Compiled 2026-10-17. This note asks what would help the people who **prevent** fires, as opposed to
those who watch them: BPBD, Manggala Agni (Daops), Masyarakat Peduli Api (MPA) village brigades, the
peat-restoration agency (BRGM, and the planned BPGMN), dinas kesehatan and pendidikan, local
government and journalists. It covers what the literature says predicts fire, which early-warning
systems already exist, what open data we can reach, and a ranked list of features with the data,
algorithm and UI for each.

Every endpoint below was tested from the dev container (outbound HTTPS through a proxy) on
2026-10-17 between 18:00 and 19:30 UTC.

Tags:

- **[T]** tested here. The HTTP code is shown; `206` means a ranged read of the first bytes worked.
- **[D]** read in the provider's own page, file or document.
- **[S]** search snippet or press report only. Check it before relying on it.

GitHub Actions runners use different IPs. Hosts that failed here should be re-tested from a runner
before they are written off.

Related notes: [data-gis-layers.md](data-gis-layers.md) (fuel, canals, GFWED, WorldPop),
[data-indonesia-official.md](data-indonesia-official.md) (BMKG, SiPongi, BNPB, InaRISK),
[data-air-quality.md](data-air-quality.md) (ISPU and CAMS correction),
[data-land-ownership.md](data-land-ownership.md) (permits, and the legal cautions about naming them).

---

## 1. Summary

**Build these first.** They are listed in build order. Section 8 has the full ranking.

| # | Feature | Who uses it | Core data | Effort |
| --- | --- | --- | --- | --- |
| 1 | **Seasonal outlook card** (ENSO, IOD, rainy-season onset, 60-day rain probability) | Pemda, BPBD, journalists | NOAA CPC ONI and weekly Niño3.4, BoM weekly IOD, Open-Meteo seasonal ensemble | S |
| 2 | **Fire danger and dry days per kabupaten** (Drought Code class, days without rain, +8-day outlook) | BPBD, Manggala Agni, MPA | GFWED GEOS-5 DC/FFMC/FWI (+8 d), MERRA2 archive for percentiles, Open-Meteo / CHIRPS rain | M |
| 3 | **Repeat-burn layer** ("burned in 2015/2019/2023 and burning again now") | BRGM/BPGMN, Manggala Agni, journalists | FIRMS VIIRS S-NPP yearly archives 2012–2025 (already ingested by `haze archive`), live events | S–M |
| 4 | **Health advice from the ISPU forecast** (school mode per SE Mendikdasmen 20/2026, masks, vulnerable groups) | Dinas pendidikan and kesehatan, parents, journalists | Station-corrected CAMS (already built), KLH ISPU, Kemendikdasmen/OSM schools | S |
| 5 | **Desa waspada: villages to prioritise for patrols and support** | MPA, Manggala Agni Daops, BPBD, Pemda | BIG 1:10k desa boundaries (83,486, Kemendagri codes), KHG peat, OSM canals/roads, repeat-burn, WorldPop, live danger | L |
| 6 | **New-fire alerts by kabupaten or desa** (Telegram/RSS/email), flagged when near a settlement, school or clinic, or on peat | MPA, BPBD, village heads, journalists | Our events, BIG desa, OSM populated places, schools, health facilities | M |

Quick win alongside these: show **SiPongi Daops suppression reports** ("ditangani Manggala Agni")
on the map, so people can see where crews already are (`opsroom.sipongidata.my.id/api/daops/pemadaman`, 200 [T]).

**Context this week** (section 2): a very strong El Niño (ONI JAS +2.16; weekly Niño3.4 +3.3 °C),
a positive IOD developing (+0.88 °C), and BMKG expects a late rainy season in 61% of its season
zones. This is the 2015 and 2019 setup. BRGM's mandate ended on 31 Dec 2024, and a new peat and
mangrove agency (BPGMN) was announced on 24 Sep 2026 with MPA strengthening as a stated priority.
Prevention tools are timely now and, more importantly, for the run-up to the 2027 dry season.

**Cautions** (section 9): label risk as *priority for support*, never as blame. Never present our
output as an official warning: BMKG (fire danger), KLH (ISPU) and BNPB/BPBD (emergency status) are
the authorities, so link to them on every card. Show skill and uncertainty, and keep the people we
rank (villages) out of any "culprit" framing.

---

## 2. The situation on 17 Oct 2026

| Indicator | Value | Source |
| --- | --- | --- |
| ONI (3-month Niño3.4, ERSSTv5) | MJJ +1.39, JJA +1.80, **JAS +2.16** | `https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt` 206 [T] |
| Weekly Niño3.4 (OISST, 1991–2020 base) | **+3.3 °C**, week of 07 Oct 2026 | `https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for` 206 [T] |
| CPC ENSO alert | "El Niño Advisory … strong-to-very strong El Niño likely through January–March 2027 (> 83% chance)" | `https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml` 206 [T] |
| IRI plume (21 Sep 2026) | El Niño probability about 100% through Feb 2027 | `https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/` 200 [T] |
| BoM weekly IOD | **+0.88 °C**, week ending 11 Oct, fifth week above +0.4. A positive IOD is "likely to develop". | `https://reg.bom.gov.au/clim_data/IDCK000072/iod_1.txt` 200 [T]; text at `https://reg.bom.gov.au/climate/enso/` 200 [T] |
| BoM relative Niño3.4 | +2.81 °C, the highest weekly value in their record since 2008 | same page [D] |
| BMKG rainy-season onset 2026/27 | Later than normal in 529 ZOM (61.08% of zones); most of Sumatra and Kalimantan from November | [infopublik.id](https://infopublik.id/kategori/nasional-sosial-budaya/990337/musim-hujan-20262027-di-6108-persen-wilayah-indonesia-datang-lebih-lambat) [S] |
| BMKG consecutive dry days (HTH) | Map updated 10 Oct from 4,732 rain stations; most of southern Kalimantan and southern Sumatra in the "> 60 days, Ekstrem Panjang" class | `https://dataweb.bmkg.go.id/iklim/hari-tanpa-hujan.png` 206 [T][D] |
| BMKG SPARTAN Drought Code | Valid 17 Oct: "Sangat Mudah" over almost all of Kalimantan south of the equator and Sumatra south of Jambi | `https://dataweb.bmkg.go.id/cuaca/spartan/36_indonesia_dc_00.png` 200 [T][D] |
| Peat agency | BRGM's term (Perpres 120/2020) ended on 31 Dec 2024. On 24 Sep 2026 the President announced a new Badan Pengelola Gambut dan Mangrove Nasional. It will focus on prevention in six peat provinces, with stronger MPA and village quick-response pumps. | [Fortune IDN, 25 Sep 2026](https://www.fortuneidn.com/news/usai-brgm-bubar-prabowo-buat-badan-gambut-baru-00-my5jv-13m9wm) [S] |
| Schools and haze | SE Mendikdasmen No. 20/2026 ties school mode to ISPU (section 7.4) | [RCTI+ / iNews, 2 Sep 2026](https://www.rctiplus.com/news/detail/terkini/5464704/kemendikdasmen-terbitkan-aturan-sekolah-di-wilayah-terdampak-karhutla--ispu-jadi-penentu-) [S] |

Note: `www.bom.gov.au` returns 403 from here, but the `reg.bom.gov.au` mirror serves the same pages
and files [T]. NOAA PSL's HadISST DMI series (`psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data`)
is reachable but stops at May 2026 [T], so use BoM's weekly IOD.

---

## 3. What the literature says predicts fire

| Predictor | Finding | Source | How we use it |
| --- | --- | --- | --- |
| **Dry-season rain, ENSO** | Fire is nonlinearly sensitive to drought. The fire environment stays highly sensitive during long spells under **~4 mm/day**, and that sensitivity has grown over Kalimantan. The authors call for "early warning triggers tied to precipitation forecasts". | Field et al. 2016, PNAS, [doi:10.1073/pnas.1524888113](https://doi.org/10.1073/pnas.1524888113); Field et al. 2009, [doi:10.1038/ngeo443](https://doi.org/10.1038/ngeo443) | Seasonal card: probability that the 30/60-day mean rain stays under 4 mm/day. |
| **Seasonal forecasts** | ECMWF System 4 rainfall forecasts predict burned area months ahead, explaining ≥ 70% of the rain–fire variance, with a positive bias in El Niño years. CFSv2 Drought Code forecasts gave 180-day lead for southern Kalimantan in 2015, but only 60 days for southern Sumatra, because the IOD was missed. | Spessa et al. 2015, [doi:10.5194/nhess-15-429-2015](https://doi.org/10.5194/nhess-15-429-2015); Shawki et al. 2017, [doi:10.1002/2017GL073660](https://doi.org/10.1002/2017GL073660) | Show ENSO **and** IOD. Expect more skill for Kalimantan than for Sumatra. |
| **Warmth in non-drought years** | Burned area follows rain anomalies (R = −0.91). In wet seasons, though, fire probability rises sharply with temperature (from ~15% to > 40% at +0.5 °C), so "wet" no longer means "safe". | Fernandes et al. 2017, ERL, [doi:10.1088/1748-9326/aa6884](https://doi.org/10.1088/1748-9326/aa6884) | Do not show a reassuring card in neutral years. Add a temperature-anomaly line. |
| **Fire danger indices** | Indonesia's FDRS is the Canadian FWI system calibrated locally. **DC** (deep fuel and peat dryness) signals smoke potential; **FFMC** signals ease of ignition. ASMC classes DC by the dry days left before the haze threshold: Extreme is < 5 days, and "complete burning restriction should be enforced". | de Groot et al. 2006, [doi:10.1007/s11027-006-9043-8](https://doi.org/10.1007/s11027-006-9043-8); Field et al. 2015 (GFWED), [doi:10.5194/nhess-15-1407-2015](https://doi.org/10.5194/nhess-15-1407-2015); [ASMC Drought Code](https://asmc.asean.org/asmc-fire-dc/) [D] | Kabupaten danger card. Use the same four classes as BMKG (Aman / Tidak mudah / Mudah / Sangat mudah). |
| **Hydrological drought, peat water table** | Keep the water table within 40 cm below the peat surface. The modelled deep water table in July 1997 matched the areas that burned. Field work recommends a 40 cm threshold. PP 57/2016 (Art. 23) calls cultivated peat "damaged" when the water table is **> 0.4 m** below the surface at the compliance point. Drought amplifies burned area in the humid tropics. | Wösten et al. 2008, [doi:10.1016/j.catena.2007.07.010](https://doi.org/10.1016/j.catena.2007.07.010); Putra et al. 2018, [doi:10.1088/1755-1315/149/1/012027](https://doi.org/10.1088/1755-1315/149/1/012027); Taufik et al. 2017, [doi:10.1038/nclimate3280](https://doi.org/10.1038/nclimate3280); [Mongabay on PP 57/2016](https://mongabay.co.id/2016/12/15/catatan-hukum-peraturan-gambut-lama-vs-baru/amp/) [S] | No open water-table data (section 6.5). Use DC as the proxy and say so. |
| **Drainage canals** | Drainage is found in at least 65% of SE Asian peatland. Subsidence is 3.2× higher where drainage is intensive. Burn depth depends on fire frequency **and distance to canals**. Drainage raises smoke emitted per unit of fire energy. | Dadap et al. 2021, [doi:10.1029/2020AV000321](https://doi.org/10.1029/2020AV000321); Konecny et al. 2016, [doi:10.1111/gcb.13186](https://doi.org/10.1111/gcb.13186); Lu et al. 2021, [doi:10.1088/1748-9326/ac2011](https://doi.org/10.1088/1748-9326/ac2011) | Canal density per desa and per KHG is a static risk factor. |
| **Settlements, concessions, land cover** | In the Sabangau/ex-Mega Rice area, **68–71%** of fires start in non-forest, 17–19% in oil palm concessions and **6–9% within 5 km of settlements**. Most fires that start in concessions (90%) or near settlements (88%) stay there. Ignition density is highest within 5 km of settlements (0.125 per km²). Ignitions rise with distance from settlements up to about 7.2 km, then fall. | Cattau et al. 2016, GEC, [doi:10.1016/j.gloenvcha.2016.05.005](https://doi.org/10.1016/j.gloenvcha.2016.05.005) [D, read abstract] | Distance to settlement is **non-monotonic**, so let a fitted model weight it. Degraded non-forest is the main source class, which argues against blaming villages. |
| **Industrial conversion** | Across Borneo, 1982–2010, a random forest explains 56% of monthly fire variation. Oil palm extent raised fire frequency up to about 20% cover per cell; logging, settlements and drought also contribute. | Sloan et al. 2017, GEC, [doi:10.1016/j.gloenvcha.2017.10.001](https://doi.org/10.1016/j.gloenvcha.2017.10.001) [S] | Land-conversion signal (Hansen loss, MapBiomas change) as a feature. |
| **Land-cover trajectory, Jambi** | 2001–2015 hotspots recur on peat in both El Niño and La Niña years. Pre-fire cover is mostly shrub and disturbed secondary forest. | Prasetyo et al. 2016, Procedia Env. Sci., [doi:10.1016/j.proenv.2016.03.096](https://doi.org/10.1016/j.proenv.2016.03.096) [S] | Shrub/fern and degraded cover classes from MapBiomas. |
| **Repeat burning** | 2001–2018: peat burns at 2.8%/yr vs 0.6% on non-peat. Fire return intervals on peat are **28 years (Kalimantan) and 45 (Sumatra)**; on Kalimantan non-forest, 13 years. Cumulative burned area equals nearly half the area of both islands but is concentrated in about 25% of the land. In the ex-Mega Rice Project, 72% of peat swamp forest was lost to fire after drainage (1997–2005). | Vetrita & Cochrane 2019, [doi:10.3390/rs12010005](https://doi.org/10.3390/rs12010005); Hoscilo et al. 2011, [doi:10.1071/WF10029](https://doi.org/10.1071/WF10029) | Strong case for a repeat-burn layer: past burning concentrates where future burning happens. |
| **Forest edge** | Fires did not get deeper than 2 km into undisturbed primary forest, even in drought. Only 3% of peatland is still fire-resistant forest. | Nikonovas et al. 2020, [doi:10.1038/s43247-020-00069-4](https://doi.org/10.1038/s43247-020-00069-4) | Distance to intact forest edge as a feature; "forest within 2 km of a fire" flag. |
| **Governance and blame** | Fires come from many actors (smallholders, companies, brokers). Perceptions of cause and blame differ across levels of government. Prevention needs incentives and land-use reform, not just suppression. | Tacconi 2016, [doi:10.1038/nclimate3008](https://doi.org/10.1038/nclimate3008); Carmenta et al. 2017, [doi:10.1016/j.gloenvcha.2017.08.001](https://doi.org/10.1016/j.gloenvcha.2017.08.001); Purnomo et al. 2017, [doi:10.1016/j.forpol.2017.01.001](https://doi.org/10.1016/j.forpol.2017.01.001); Edwards et al. 2020, [doi:10.1016/j.worlddev.2019.104717](https://doi.org/10.1016/j.worlddev.2019.104717) | Framing rules in section 9. |
| **Health** | Early-life exposure to the 1997 fire haze had lasting effects (lower adult height). | Tan-Soo & Pattanayak 2019, PNAS, [doi:10.1073/pnas.1802876116](https://doi.org/10.1073/pnas.1802876116) | Supports school and pregnancy advice (section 7.4). |
| **Village programmes** | APRIL's Fire Free Village Programme reports about 90% less burned area in its first 9 villages (2014 to 2015). A commissioned third-party review found 391 → 159 ha (2016 → 2017). There is no peer-reviewed impact evaluation. | [APRIL 2015 review](https://www.aprilasia.com/id/our-media/artikel/fire-free-village-program-2015-s-review-and-outlook-for-2016) [S]; [FFVP report 2018](https://www.rgei.com/attachments/article/1115/ffvp-report-05-04-2018.pdf) [S] | Village-level prevention is plausible but unproven. Our ranking should help target support, not claim effects. |

Takeaways for design:

1. **Drought decides how bad a year will be; land condition decides where.** Seasonal and danger
   products answer *when* and *how bad*. Peat, canals, degradation and repeat-burn history answer *where*.
2. Past burning is the single cheapest spatial predictor we already hold.
3. Most ignitions are on degraded non-forest. Village proximity matters, but not monotonically, so a
   fitted model beats hand-set distance buffers.

---

## 4. Early-warning systems that already exist

| System | Operator | What it gives | Reachable from here | Our relation to it |
| --- | --- | --- | --- | --- |
| **SPARTAN** (Sistem Peringatan Kebakaran Hutan dan Lahan) | BMKG | FFMC, DMC, DC, ISI, BUI and FWI from the Canadian FWI system calibrated with local weather; observed plus H+0…H+7 maps per province. BMKG stresses that it "does not show hotspots", only weather conditions that support fire if there is fuel and an ignition. | Static PNGs `dataweb.bmkg.go.id/cuaca/spartan/{region}_{index}_{step}.png` 200 [T]; the tile and model-run API is behind Cloudflare 403 (see data-indonesia-official.md) | **Official.** Link to it and embed the PNGs; never contradict it silently. Our GFWED numbers are a separate, open, numeric estimate. [BMKG news, 23 Jun 2026](https://www.bmkg.go.id/berita/utama/bmkg-spartan-dukung-pemantauan-dan-pencegahan-potensi-karhutla) [D] |
| BMKG HTH (consecutive dry days) | BMKG Climate Change Directorate | Station map, dasarian (10-day) updates; classes 1–5, 6–10, 11–20, 21–30, 31–60, > 60 days | PNG 200 [T]; numbers need a `dataonline.bmkg.go.id` login | We compute our own gridded equivalent and link to BMKG's. |
| **ASEAN FDRS** | Malaysian Meteorological Department, shown by ASMC | Daily FWI codes for the region; 7-day forecast since Jan 2023; DC classes by dry days until the haze threshold | `asmc.asean.org/asmc-fire-dc/` [D]; `asmc-fdrs/` 404 [T] | Regional reference. Its class wording is reused in feature 2. |
| **Fire Risk System (FRS)** | CCROM-SEAP, IPB with UNOPS, UNEP and Columbia (not BRIN) | 1–6-month probabilistic fire forecasts from hotspot history, biophysical and socio-economic factors, and ENSO/rain. 5 km for provinces, 1 km for kabupaten; ten provinces. | No open feed found [S]: [IPB news](https://www.ipb.ac.id/?p=56496), [CCROM news](https://ccromseap.ipb.ac.id/web/singlepost/news/90) | The closest analogue to our "desa waspada". Approach them for a comparison or partnership rather than duplicating it. |
| GFW fire alerts | WRI Global Forest Watch | VIIRS/MODIS alerts, email subscription by area, dashboards | `data-api.globalforestwatch.org/dataset/nasa_viirs_fire_alerts` 206 [T]; queries need an API key | Our alerts add Indonesian-language, desa-level context and smoke. Link to GFW for area statistics. |
| PRIMS (Peatland Restoration Information and Monitoring System) | BRG/BRGM, launched 2019 | Restoration progress (canal blocks, wells, revegetation) and hotspots on peat in 7 provinces | `prims.brg.go.id` no connection [T] | Restoration infrastructure data is the main missing piece (section 6.5). |
| SiPALAGA (peat water-table telemetry) | BRGM | About 140+ water-table loggers | 403 Cloudflare [T] | No public API. Ask the successor agency. |
| Pantau Gambut | NGO coalition | Peat maps, commitment tracking, news. No live "sistem peringatan" pages found. | `pantaugambut.id` 200 [T]; `/peringatan` 404 [T] | Partner for outreach, not a data source. |
| SiPongi+ | Kemenhut (Gakkum / PKHL) | Official hotspots tagged by desa; burned area; **Daops suppression reports** | `opsroom.sipongidata.my.id/api/...` 200 [T] | Use the Daops feed to show "handled" fires. |
| InaRISK | BNPB | Static karhutla hazard, vulnerability and risk rasters (100 m) | ImageServer 200 [T] | Show alongside our static susceptibility, for comparison. |

---

## 5. Who prevents fires, and what they need from us

| User | Decisions they make before or early in a fire | What would help | Feature |
| --- | --- | --- | --- |
| **BPBD / Pemda** (bupati, provinsi) | Declare *Siaga Darurat*, open posko, budget, burning bans, request water-bombing and cloud seeding (OMC) | Season outlook, danger trend per kabupaten, comparison with 2015/2019/2023, printable weekly brief | 1, 2, 7.10 |
| **Manggala Agni Daops** | Patrol routes, pre-positioning pumps, ground-check hotspots | Ranked desa and peat blocks, new-fire alerts, repeat-burn areas, what other crews already handle | 3, 5, 6, 7.7 |
| **MPA / Desa Mandiri Peduli Gambut** | Patrols, initial attack in the first hours, canal-block checks, community warnings | An alert on a phone when a fire starts in or near the desa; a plain-language danger level; dry-days count | 2, 6 |
| **BRGM → BPGMN**, KPH, dinas lingkungan | Where to block canals, rewet and revegetate; post-fire restoration | Repeat-burn by KHG and desa, canal density, burned-again areas | 3, 7.9 |
| **Dinas kesehatan / pendidikan** | School mode, masks, *Rumah Oksigen*, health-facility readiness | ISPU forecast by city with SE 20/2026 actions; schools and clinics in the affected area | 4 |
| **Journalists, researchers** | Explain risk early, hold institutions to account | Seasonal context, repeat burning, open CSVs, method notes | 1, 3, 5 |

---

## 6. Data sources (tested)

### 6.1 Climate and seasonal

| Data | Endpoint | Test | Licence | Notes |
| --- | --- | --- | --- | --- |
| ONI (monthly 3-month means) | `https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt` | 206 [T] | US public domain | Last row `JAS 2026 29.12 2.16`. Monthly. |
| Weekly Niño 1+2, 3, 3.4, 4 (OISST) | `https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for` | 206 [T] | public domain | Weekly; last row 07 Oct 2026, Niño3.4 anomaly 3.3 |
| Monthly Niño regions | `https://www.cpc.ncep.noaa.gov/data/indices/sstoi.indices` | 206 [T] | public domain | Up to Sep 2026 |
| CPC ENSO discussion (alert status, synopsis) | `https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml` | 206 [T] | public domain | HTML; scrape "ENSO Alert System Status" and "Synopsis" |
| IRI ENSO plume | `https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/` | 200 [T] | IRI terms (credit) | HTML; monthly. The old `~forecast/ensofcst/Data/archive/ensofcst_cpc_ALL` is 404 [T]. |
| **BoM weekly IOD** | `https://reg.bom.gov.au/clim_data/IDCK000072/iod_1.txt` | 200 [T] | © BoM, attribution | CSV `start,end,value`; last `20261005,20261011,0.88`. `www.bom.gov.au` is 403 here; `reg.` works. |
| BoM SOI (30-day) | `https://reg.bom.gov.au/clim_data/IDCKGSM000/soi.txt` | 200 [T] | © BoM | Daily; −19.0 on 15 Oct |
| BoM climate driver text | `https://reg.bom.gov.au/climate/enso/` | 200 [T] | © BoM | Fortnightly; quote a sentence and link to it |
| **Open-Meteo seasonal** (ensemble daily rain to ~2 months) | `https://seasonal-api.open-meteo.com/v1/seasonal?latitude=..&longitude=..&daily=precipitation_sum&forecast_days=60` | 200 [T]; 50 members, 17 Oct → 15 Dec | CC BY 4.0 (Open-Meteo); underlying model per their docs | Gives P(mean rain < 4 mm/day). Already a provider in `smoke.py`. |
| BMKG HTH, SST and SPARTAN images | `dataweb.bmkg.go.id/iklim/hari-tanpa-hujan.png`, `…/cuaca/spartan/36_indonesia_{ffmc,dc,fwi}_{obs,00..07}.png` | 206/200 [T] | BMKG open data, **credit BMKG** | Province PNG names in data-indonesia-official.md. `14_kalteng_*` is 404 [T], so read the real list there. |
| BMKG seasonal outlook (ZOM onset) | `https://iklim.bmkg.go.id/` | 200 [T] | credit BMKG | Bulletins and PDFs; no API found. Link only. |

### 6.2 Fire danger and rain

| Data | Endpoint | Test | Res. / latency | Notes |
| --- | --- | --- | --- | --- |
| **GFWED GEOS-5 FWI, DC, DMC, FFMC, ISI, BUI** | `https://portal.nccs.nasa.gov/datashare/GlobalFWI/v2.0/fwiCalcs.GEOS-5/Default/GEOS-5/2026/` (latest run dir `2026101400/`) | 206 [T] | ~0.25°; analysis 1–3 days behind; **+8-day forecast** | NASA open. 16 MB per global day; subset to the bbox. |
| GFWED MERRA2 archive | `…/fwiCalcs.MERRA2/Default/MERRA2/{2000..2026}/` | tested in data-gis-layers.md | daily since 1980 | Gives a day-of-year DC climatology and percentiles, and 2015/2019/2023 analogues. |
| CHIRPS 2.0 daily (prelim) | `https://data.chc.ucsb.edu/products/CHIRPS-2.0/prelim/global_daily/tifs/p05/2026/` | 200 [T]; last file 2026-10-10 | 0.05°, ~1 week behind | Public domain. Best gauge-blended rain for dry-day counts. Final product to 30 Sep. CHIRPS v3 also listed (200 [T]). |
| Open-Meteo forecast and archive (daily rain) | `api.open-meteo.com/v1/forecast?...&past_days=..`, `archive-api.open-meteo.com/v1/archive` | Archive 200 [T]; forecast timed out once [T] but already used in production | ~0.1–0.25°; archive ~5 days behind; forecast 16 d | Fills the last week before CHIRPS and the 16-day outlook. |
| NASA IMERG Early | `jsimpsonhttps.pps.eosdis.nasa.gov/imerg/gis/` | 401 [T] | 0.1°, ~4 h | Needs a free Earthdata/PPS login. Optional upgrade for near-real-time rain. |
| InaRISK karhutla hazard | `https://gis.bnpb.go.id/server/rest/services/inarisk/layer_bahaya_kebakaran_hutan_dan_lahan/ImageServer?f=json` | 200 [T] | 100 m, static | Compare with our susceptibility. Credit BNPB. |

### 6.3 Village boundaries and codes

| Data | Endpoint | Test | Count / fields | Licence | Use |
| --- | --- | --- | --- | --- | --- |
| **BIG Batas Desa/Kelurahan 1:10k** | `https://geoservices.big.go.id/rbi/rest/services/BATASWILAYAH/Administrasi_AR_KelDesa_10K/MapServer/0/query` | 200 [T]; count **83,486**; point query at Palangka Raya returns `NAMOBJ Palangka`, `KDEPUM 62.71.03.1001`; `f=geojson` with geometry 200 [T]; maxRecordCount 4000 | `NAMOBJ`, `KDEPUM` (Kemendagri code), `KDEBPS` (often blank), `WADMKC/KK/PR`, `METADATA TASWIL1000020230928…` (2023 release). Kalteng: 1,571 desa [T]. | No licence on the service; "Badan Informasi Geospasial" copyright text. Credit BIG and ask about redistribution. | **Primary desa layer.** `KDEPUM` equals BMKG's `adm4` key. Page it in 4,000-feature chunks by province once a year. |
| **HDX COD-AB Indonesia** (BPS 2020, ADM0–ADM4) | `https://data.humdata.org/api/3/action/package_show?id=cod-ab-idn` → `idn_admin_boundaries.gdb.zip` (219 MB), `.shp.zip`, `.geojson.zip`, `.xlsx` | 200 [T]; GDB 206 [T]; xlsx downloaded: sheet `idn_admin4` has **81,912** rows | `adm4_pcode` like `ID1671060006` (BPS code), names, area, centre lat/lon, `valid_on` 2020-04-01 | **CC BY-IGO** | Clear licence, the fallback, and the same pcodes HOT's OSM layers carry (`adm4_pcode`). |
| geoBoundaries IDN ADM3/ADM4 | `https://www.geoboundaries.org/api/current/gbOpen/IDN/ADM3/` | 404 [T] | — | — | Not available; geoBoundaries stops at ADM2 for IDN (which we already use). |
| **BPS ↔ Kemendagri code bridge** | `https://sig.bps.go.id/rest-bridging/getwilayah?level=desa&parent={kode_kec_bps}` | 200 [T] (the site root is 403) | `kode_bps`, `nama_bps`, `kode_dagri`, `nama_dagri` | public site | Joins HDX/BPS desa to the BMKG `adm4` forecast and BIG `KDEPUM`. |
| Kemendagri code list (Kepmendagri 300.2.2-2138/2025) | `https://raw.githubusercontent.com/cahyadsn/wilayah/master/db/wilayah.sql` | 206 [T] | All codes and names to desa | MIT (compiler); source is a public decree | Names and code validation |
| BMKG desa forecast | `https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4=16.71.06.1006` | 200 [T] | 3-day, 3-hourly, incl. weather code 45 "Kabut/Asap" | BMKG open data, credit; 60 req/min | Official weather line on each desa page (fetch on demand, cache 1 h) |

Desa boundaries in Indonesia are partly indicative; many are not yet fixed by Permendagri. Say this
on the map.

### 6.4 Exposure, access and drainage (OSM via HOT, weekly)

Base `https://production-raw-data-api.s3.amazonaws.com/ISO3/IDN/_layers/osm/` (bucket listing 200 [T], all updated 2026-10-11, ODbL). Each layer carries `adm1..adm4_pcode` from COD-AB, so joins are free.

| Layer | Size | Kalteng check [T] (DuckDB over HTTPS) | Use |
| --- | --- | --- | --- |
| `populated_places.parquet` | 55 MB | 1,598 `place=village`, 944 `landuse=residential`, 81 hamlets | Settlement points and areas: distance to settlement, "near a village" alerts |
| `roads.parquet` | 1.1 GB | not counted | Access (distance to road), a known ignition and response factor |
| `waterways.parquet` | 271 MB | **75,967 `ditch`, 2,784 `canal`, 1,106 `drain`**, 974 river | Canal density (complements Dadap 2017, `stacks.stanford.edu/file/druid:yj761xk5815/geotiffs.zip` 206 [T], CC BY 3.0) |
| `education_facilities.parquet` | 15 MB | **833 schools** in 205 desa | Schools under smoke. **Incomplete**: Kemendikdasmen lists ~3,810 schools in Kalteng (below). |
| `health_facilities.parquet` | 2.8 MB | 147 | Clinics and hospitals under smoke |
| `buildings.parquet` | 4.3 GB | not counted | Optional: building density for exposure |

Official school list: `https://sekolah.data.kemendikdasmen.go.id/` 200 [T] (search UI; no bulk
API found). `dapo.kemendikdasmen.go.id` is 403 [T]. A community mirror,
`api-sekolah-indonesia.vercel.app/sekolah?provinsi=140000`, 200 [T], returns NPSN and lat/lon
(`total_data 3810` for Kalteng). It is unofficial and of unknown freshness, so use it only to show
OSM's coverage gap, and ask Pusdatin Kemendikdasmen for the official extract.

Population: WorldPop R2025A constrained 100 m,
`https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2025/IDN/v1/100m/constrained/idn_pop_2025_CN_100m_R2025A_v1.tif`
200 [T] (88 MB, CC BY 4.0).

### 6.5 Fire history, land cover and restoration

| Data | Endpoint | Test | Use |
| --- | --- | --- | --- |
| FIRMS VIIRS S-NPP yearly country CSV | `https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/{2012..2025}/viirs-snpp_{Y}_Indonesia.csv` | 206 for 2012, 2015, 2019, 2023, 2025 [T] | Repeat-burn (375 m), 14 seasons, one consistent sensor |
| FIRMS MODIS yearly | `…/data/country/modis/{2002..}/modis_{Y}_Indonesia.csv` | 206 for 2002 [T] | Extends history back to 2002 at 1 km (the 1997–98 fires are before any FIRMS record) |
| ESA FireCCI S311 burned area 300 m | `https://dap.ceda.ac.uk/neodc/esacci/fire/data/burned_area/Sentinel3_SYN/pixel/v1.1/compressed/2023/` | 200 [T] | Burned *area* for 2019–2024, to back up hotspot-based repeat burns |
| Hansen GFC v1.13 loss year | `https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/Hansen_GFC-2025-v1.13_lossyear_00N_100E.tif` | 206 [T] | Recent clearing (Sloan: conversion drives fire) |
| MapBiomas Indonesia C3 | `https://storage.googleapis.com/mapbiomas-public/initiatives/indonesia/collection_3/coverage_indonesia_2024.tif` | 206 [T] | Non-forest / shrub / plantation shares per desa |
| KHG peat | already in `regions.py` | — | Peat share per desa |
| **Sumsel peat GeoNode** (`datagambut.sumselprov.go.id`) | `https://datagambut.sumselprov.go.id/api/layers/?limit=200` | 200 [T]: 82 layers, including `desa_peduli_api`, `desa_peduli_gambut`, `BRGM_DPG2017…2021`, `implementasi_sekat_kanal_2018/19/20`, `implementasi_sumur_bor_2018/19`, `rencana_sekat_kanal`, `rawan_karhutla`, `area_terbakar_2015…2021`, `tp_tmat_*` (water-table compliance points) | **The data store is broken**: WFS returns "password authentication failed for user geonode" and `/download/...` is 500 [T]. Only the catalogue (names, dates, bboxes) works. Contact the province; this is exactly the canal-block, MPA-village and water-table data we lack. |
| SiPALAGA water table (BRGM) | `https://sipalaga.brg.go.id/` | 403 [T] | Not open |
| Hooijer & Vernimmen water-table maps (10 km, CC BY 4.0) | `https://doi.org/10.17632/69mbg22fxf.1` | DOI resolves 200 [T]; the metadata API returned nothing usable [T] | Cited in data-gis-layers.md. Possible open proxy for peat wetness; check the files before planning on it. |
| SiPongi Daops suppression reports | `https://opsroom.sipongidata.my.id/api/daops/pemadaman` | 200 [T]; GeoJSON points with `nama_daops`, `tanggal`, `lokasi` (desa/kec/kab text), `luas_bakar`, `luas_padam`, `catatan` | "Being handled" layer; patrol context |

---

## 7. Feature catalogue

Each feature lists the data, the algorithm, how it looks in the app, the effort, and how we would check it.

### 7.1 Seasonal outlook card ("Prospek musim")

- **Data.**
  - CPC ONI and weekly Niño3.4, plus the CPC alert text.
  - BoM weekly IOD and its driver sentence.
  - IRI plume probability.
  - Open-Meteo seasonal ensemble rain at each province's peat centroid.
  - BMKG ZOM onset text, as a link.
- **Algorithm.**
  - ENSO state: El Niño if ONI ≥ +0.5 for the latest season (and say "strong" at ≥ 1.5).
  - IOD state follows BoM: positive if the weekly value is ≥ +0.4 for 8 weeks; otherwise call it "trending positive".
  - Per province, P(next-30-day and next-60-day mean rain < 4 mm/day) is the share of the 50 members below 4 mm/day (Field 2016).
  - Analogues: list past years with the same ENSO/IOD sign and their S-NPP fire counts. Use the 2015/2019/2023 curves already in `dashboard.json`.
- **UI.**
  - Dashboard card: "El Niño sangat kuat, IOD positif berkembang".
  - Per province: "Peluang hujan < 4 mm/hari selama 30 hari: 78%".
  - Mini chart of this season against 2015/2019/2023.
  - Credits and links: BMKG prakiraan musim, CPC and BoM.
  - Updated weekly.
- **Effort.** S: 3 text fetches, one ensemble call per province (~10 calls), and a JSON file.
- **Check.** Back-test the 4 mm/day probability against MERRA2/CHIRPS outcomes; at least show the hit rate for 2015/2019/2023.
- **Prevention value.** Gives budget and *siaga* decisions weeks to months of lead. It matters most in April–June for the following dry season.

### 7.2 Fire danger and dry days per kabupaten ("Bahaya kebakaran & hari tanpa hujan")

- **Data.**
  - GFWED GEOS-5 daily DC, FFMC and FWI (analysis plus 8-day forecast).
  - MERRA2 GFWED 2001–2025 for climatology.
  - CHIRPS prelim plus Open-Meteo for rain.
  - KHG peat mask; geoBoundaries ADM2 (already used).
- **Algorithm.**
  - **Dry days**: per 0.05–0.1° cell, count consecutive days with rain < 1 mm, using the BMKG HTH idea (the < 1 mm threshold is our assumption; confirm against BMKG's definition). Aggregate per kabupaten as the median and 90th percentile over peat cells and over all land. Classes are BMKG's: 1–5, 6–10, 11–20, 21–30, 31–60, > 60 days.
  - **Danger**: area mean of DC over peat cells, and of FFMC/FWI over all land.
    - Classify DC into four classes with the same names and colours as BMKG's SPARTAN legend (Aman / Tidak mudah / Mudah / Sangat mudah).
    - Take the breakpoints from the Indonesian FDRS (de Groot 2006). Check them against SPARTAN PNGs for a few days and tune until the maps agree, so we never show a calmer class than BMKG.
  - **Percentile**: today's DC against the same day of year in 2001–2025 (MERRA2), e.g. "DC lebih tinggi dari 95% hari serupa sejak 2001".
  - **Outlook**: GFWED +8 days. Also show "hari kering tersisa sebelum kelas Sangat mudah" by stepping DC forward with forecast temperature and zero rain. This is the ASMC "dry days to threshold" idea.
- **UI.**
  - Kabupaten choropleth layer: DC class or dry days.
  - Kabupaten panel: 60-day sparkline plus 8-day forecast, a dry-days number, the percentile line, and the BMKG SPARTAN PNG for the province (embedded, credited) with "Rujukan resmi: BMKG SPARTAN".
  - Fills the PRD F8 "days since rain" gap and V2-4.
- **Effort.** M: one NetCDF subset per day, zonal statistics, and a JSON file per day. Rain from Open-Meteo reuses existing code.
- **Check.**
  - Hindcast 2015/2019/2023: correlation of weekly kabupaten DC with next-week VIIRS counts.
  - Agreement with the SPARTAN class (pixel sample of the PNG legend colours).

### 7.3 Repeat-burn layer ("Pernah terbakar")

- **Data.**
  - FIRMS VIIRS S-NPP yearly archives 2012–2025. Use S-NPP only, for consistency over time; NOAA-20 and NOAA-21 would inflate recent years.
  - Our static mask and low-confidence filter.
  - Current season events.
  - Optional: FireCCI 300 m burned area for 2019–2024, MODIS 2002–2011.
- **Algorithm.**
  - Snap detections to the 375 m cell grid the pipeline already uses for area.
  - Per cell: `fire_years` (distinct years with ≥ 1 detection), `years` (a list), `last_year`.
  - Aggregate to KHG, desa and kabupaten: the share of peat area burned ≥ 2 times, and the 2015 ∩ 2019 ∩ 2023 overlap.
  - Live flag: an event whose cells have `fire_years ≥ 1` before this season gets "terbakar lagi (2015, 2019)".
  - Publish as PMTiles or as H3 res-8 hexagons (~0.7 km²) to keep size down.
- **UI.**
  - Map layer with 4 classes (1, 2, 3, ≥ 4 years) in a single hue.
  - Badge on the event panel: "Area ini juga terbakar pada 2015 dan 2019".
  - Stats per KHG for restoration staff.
  - Caveat line: "berdasarkan titik panas satelit, bukan luas terbakar terukur".
- **Effort.** S–M: the archives are already loaded by `haze archive`; this is a SQL group-by plus tiles.
- **Check.** Share of 2023 detections that fell in cells that burned 2012–2022, compared with the share of land those cells cover. The lift is the headline. Vetrita 2019 suggests a large lift (about 25% of the land holds nearly all burning).

### 7.4 Health advice from the ISPU forecast ("Saran kesehatan")

- **Data.**
  - Station-corrected CAMS PM2.5 (already in `smoke.py` and `stations.py`) and KLH ISPU stations.
  - OSM schools and health facilities, plus the Kemendikdasmen list when obtained.
  - WorldPop.
- **Rules** (quote the source next to each):
  - ISPU PM2.5 breakpoints (Permen LHK P.14/2020, already in `smoke.ISPU_PM25`): 15.5 / 55.4 / 150.4 / 250.4 µg/m³ map to Baik / Sedang / Tidak sehat / Sangat tidak sehat / Berbahaya. The legal text is [peraturan.go.id BN 774/2020](https://peraturan.go.id/files/bn774-2020.pdf).
  - **Schools (SE Mendikdasmen 20/2026)** [S]:
    - Baik: normal.
    - Sedang: classes as usual, limit outdoor activity.
    - Tidak sehat (101–200): face-to-face strictly limited, and vulnerable pupils learn from home.
    - Above 200: all learning remote.
    - Schools check ISPU twice a day and use the nearest kabupaten/kota station if they have none.
  - **Kemenkes (26 Aug 2026)**: reduce outdoor activity, seal rooms, use indoor air filters, wear N95-type respirators, protect children, older people, pregnant women and people with comorbidities, and use *Rumah Oksigen* for acute breathlessness ([kemkes.go.id](https://kemkes.go.id/id/kemenkes-perkuat-perlindungan-kelompok-rentan-hadapi-karhutla) [D]). Mask fit: [kemkes.go.id mask page](https://www.kemkes.go.id/id/penggunaan-masker-pada-asap-kebakaran-hutan) [S].
- **Algorithm.**
  - Per city or kabupaten: the 24 h mean of forecast PM2.5 for tomorrow. ISPU is defined on 24 h averages, not hourly peaks.
  - Map it to an ISPU category and show the matching SE 20/2026 action as "panduan", not a decision.
  - Count schools, clinics and people in each category.
- **UI.**
  - A row in the "cities in smoke" table: "Besok: Tidak sehat → sekolah: tatap muka dibatasi, siswa rentan belajar dari rumah (SE Mendikdasmen 20/2026)".
  - A big disclaimer: the school decision belongs to the dinas pendidikan, and measured ISPU from KLH comes first.
- **Effort.** S, since the data exists. Mostly copy-writing and review by a health professional.
- **Check.** Category hit rate of the 24 h forecast against KLH stations; publish it next to the card.

### 7.5 Desa waspada: villages to prioritise for patrols and support

- **Unit.** BIG 1:10k desa (83,486, `KDEPUM`), falling back to COD-AB ADM4 (CC BY-IGO). Restrict to desa that intersect KHG peat or had ≥ 1 detection in 2012–2025 (roughly 10–15k desa).
- **Static susceptibility** (recomputed yearly) per desa:

  | Feature | Source |
  | --- | --- |
  | Peat share, and peat depth class if available | KHG 2017 (in repo) |
  | Canal and ditch length per km² | OSM waterways; Dadap 2017 raster |
  | Repeat-burn share and last fire year | 7.3 |
  | Non-forest/shrub share; recent loss (3 years) | MapBiomas 2024; Hansen v1.13 |
  | Intact-forest edge length within 2 km | Hansen tree cover 2000 + loss; Nikonovas 2020 |
  | Road density; distance from settlement centroid to peat | OSM roads, populated places |
  | Population | WorldPop 2025 |

  - Model: logistic regression or gradient-boosted trees (scikit-learn or LightGBM).
  - Target: "≥ 3 VIIRS S-NPP detections in the desa in the season".
  - Train on 2015 + 2019 features built only from data up to the year before; test on 2023.
  - Report AUC and **top-10% capture**: the share of 2023 detections that fell in the top-decile desa.
  - Keep the model interpretable: publish coefficients or SHAP-style "alasan" per desa.
- **Dynamic layer** (daily). Combine three things:
  - static rank;
  - danger now (DC percentile and dry days from 7.2);
  - activity: detections within 5 km in the last 72 h, and spread-model probability of reaching the desa.

  The output is a priority tier (1–3), not a "probability of fire" number.
- **Patrol priority.**
  - Within each Daops or kabupaten, sort tier-1 desa by "no fire yet but high danger and high susceptibility": prevention patrol.
  - Separately, sort "active fire within 5 km": ground-check and initial attack.
  - Daops working areas can be approximated from the `nama_daops` names and points in the SiPongi Daops feed; confirm them with Kemenhut.
- **UI.**
  - "Desa waspada" tab with a kabupaten filter.
  - Table: desa, kecamatan, tier, reasons ("gambut 82% · terbakar 2015, 2019 · 23 hari tanpa hujan · 2 titik panas dalam 5 km").
  - CSV export and a printable A4 list for the posko.
  - On the map, desa outlines tinted by tier.
  - Each desa page: BMKG 3-day forecast (adm4 API), repeat-burn history and nearest active fires.
- **Effort.** L: new boundary ingest, feature build, model, validation, review with users.
- **Check.**
  - 2023 hold-out results, published as they are, even if they are modest.
  - Before launch, ask 2–3 BPBD/Daops staff whether the tier-1 desa match their own knowledge.

### 7.6 New-fire alerts by kabupaten or desa ("Peringatan titik api baru", wording in section 9)

- **Trigger.**
  - A new event (first detection) or a new detection > 1 km from an event's previous footprint.
  - Filters chosen by the subscriber: kabupaten, desa, or a point plus radius.
  - Optional conditions: on peat, within X km of a settlement, school or clinic, or DC class ≥ Mudah.
- **Payload.**
  - Time (WIB/WITA), satellite and confidence, desa/kecamatan, distance to the nearest village and school.
  - Map link and Google Maps coordinates; repeat-burn note; smoke direction from the plume model.
  - "Belum terverifikasi: cek lapangan; jangan mendekati api; lapor 112 / BPBD / Manggala Agni".
  - Already-reported Daops actions nearby.
- **Channels.**
  - Telegram bot (free API, works on cheap Android).
  - RSS/Atom per kabupaten, which also feeds newsrooms and other bots.
  - Email digest.
  - WhatsApp needs the paid Business API, so later.
- **Engineering.**
  - A step after `haze run` diffs new events against the last run.
  - A small subscription store: Cloudflare Worker + D1/KV, or a GitHub-hosted list for RSS-only.
  - Rate-limit to one message per desa per 6 h with a digest.
  - FIRMS NRT latency (~3 h) plus our cadence (2 h now, 30 min target) bounds speed. Say "~3–5 jam setelah satelit lewat".
- **Effort.** M (RSS alone is S).
- **Check.** Log alert-to-Daops-report matches (SiPongi) to estimate usefulness. Track the false-alarm share (static or industrial heat).

### 7.7 Response overlay ("Sudah ditangani")

- **Data.** SiPongi Daops points and BNPB `mv_prov_karhutla_2026` (sporadic).
- **Algorithm.** Match Daops points to events within 2 km and ±2 days.
- **UI.** A small extinguisher icon on events with a crew report, plus a list of reports by date.
- **Effort.** S.

Avoid any "unattended fires" ranking: the feed is incomplete, and such a list would read as blame.

### 7.8 Pre-season land-clearing watch

- **Data.** Hansen annual loss; GFW integrated deforestation alerts (`data-api…/gfw_integrated_alerts` 206 [T]; queries need a key; tiles need checking).
- **Algorithm.** New clearing on peat between March and July, aggregated to desa and KHG, as an early "fuel prepared" signal (Sloan 2017).
- **UI.** Layer plus counts per kabupaten.
- **Effort.** M.
- **Caution.** High risk of being read as blame. Show areas, never owners, consistent with data-land-ownership.md.

### 7.9 Peat wetness and canal context (for restoration staff)

- **Data.** Canal density (OSM + Dadap), DC on peat, repeat-burn; canal blocks and water-table points if the Sumsel GeoNode or BPGMN opens them.
- **UI.** KHG panel: canal km per km², share burned more than once, DC trend, and the line "Target tinggi muka air ≤ 40 cm di bawah permukaan (PP 57/2016); data TMAT belum terbuka untuk publik".
- Restoration techniques (canal blocking, rewetting, revegetation) are reviewed in Dohong et al. 2018; the app should show where they would matter, not prescribe them.
- **Effort.** M, mostly blocked on data.

### 7.10 Weekly kabupaten brief

- One printable or shareable page per kabupaten, combining 7.1–7.7: danger, dry days, outlook, active fires, tier-1 desa, health category.
- Generated as static HTML with print CSS and an OG image.
- **Effort.** S–M once the parts exist. High value for BPBD meetings and newsrooms.

---

## 8. Ranking

Impact is for prevention (1–5); effort is S/M/L. Data readiness is whether every input is open and reachable today.

| Rank | Feature | Impact | Effort | Data ready? | Why this rank |
| --- | --- | --- | --- | --- | --- |
| 1 | 7.1 Seasonal outlook | 4 | S | Yes | Cheapest lead time there is; the literature (Field, Spessa, Shawki) backs it; urgent with this El Niño |
| 2 | 7.2 Danger + dry days per kabupaten | 5 | M | Yes | Daily operational signal for bans, *siaga* and patrol intensity; fills PRD F8 and V2-4 |
| 3 | 7.3 Repeat-burn layer | 4 | S–M | Yes (already ingested) | Strongest cheap "where" predictor; restoration targeting; journalists |
| 4 | 7.4 Health advice | 4 (health) | S | Yes | Data exists; national school rule is new (SE 20/2026); protects children |
| 5 | 7.5 Desa waspada / patrol priority | 5 | L | Mostly (BIG licence to confirm) | Highest prevention value, but needs 7.2 and 7.3 first plus validation and user review |
| 6 | 7.6 New-fire alerts | 5 | M | Yes | First-hours response is what MPA can do; needs subscription infrastructure |
| 7 | 7.7 Response overlay | 3 | S | Yes | Quick win; avoids duplicate trips |
| 8 | 7.10 Weekly kabupaten brief | 3 | S–M | after 1–6 | Packaging that gets used |
| 9 | 7.9 Peat wetness and canal context | 3 | M | No (canal blocks, TMAT closed) | Ask BPGMN and Sumsel first |
| 10 | 7.8 Land-clearing watch | 3 | M | Partly (GFW key) | Useful pre-season but sensitive; after the rest |

---

## 9. Cautions

**No blame.**

- Rank desa as *priority for support*: patrols, pumps, outreach, restoration funds. Never present them as places where people start fires.
- Cattau 2016 found most ignitions on degraded non-forest. Fewer than 10% start within 5 km of settlements, and most of those stay put.
- Use words like *waspada*, *prioritas*, *perlu dukungan*. Avoid *pelaku*, *penyebab*, *rawan karena warga*.
- Do not name companies or permit holders in prevention products (see data-land-ownership.md).
- Before launch, show the desa list to people from the communities it ranks (MPA, kepala desa) and to BPBD.

**Not an official warning.**

- BMKG is the national source for meteorological and climatological early warnings; the legal basis is UU 31/2009 on MKG [S, confirm the article].
- KLH publishes ISPU, and BNPB/BPBD declare emergency status.
- Every danger, outlook and health card links to the official product and says "Informasi pendukung, bukan peringatan resmi. Ikuti arahan BMKG, BPBD dan dinas setempat."
- Never use *peringatan dini* alone for our model outputs; use *indikasi* or *prakiraan model*.
- Where our class is calmer than SPARTAN, show SPARTAN's.
- BMKG data must be credited (data.bmkg.go.id terms). BMKG's robots.txt disallows `/alerts`, so do not scrape CAP alerts without permission.

**Uncertainty, shown not hidden.**

- Hotspots miss fires under smoke and cloud. MODIS omission on peat is 34–60% (cited in Cattau 2016), and VIIRS also misses smouldering peat.
- GFWED is ~25 km; DC averages hide local wet and dry patches.
- Desa boundaries are partly indicative.
- OSM schools are about 22% complete in Kalteng (833 vs about 3,810).
- CAMS needs station correction and still misses peaks.
- Publish each model's hold-out skill next to it (as `models.md` does for spread). Show data dates ("DC per 15 Okt; hujan per 10 Okt").

**Alert hygiene.**

- Rate limits and digests, so people do not mute us in the peak weeks.
- Always "verify on the ground".
- Store subscribers' contacts minimally (Telegram chat id, kabupaten codes) and never publish them.

**Safety.** Alert text tells people not to approach fires and to call 112, BPBD or Manggala Agni.

---

## 10. Validation plan

| Feature | Test | Pass bar (to publish without an "eksperimental" label) |
| --- | --- | --- |
| 7.1 | P(rain < 4 mm/day) vs observed in 2015/2019/2023 and in non-El Niño years 2016/2020/2022 | Higher probabilities in the bad years, in each province |
| 7.2 | Weekly kabupaten DC vs next-week S-NPP counts, 2015–2025 | Spearman ρ > 0.5 in peat kabupaten; class agreement with SPARTAN ≥ 80% |
| 7.3 | Lift: 2023 detections in previously burned cells ÷ the area share of those cells | Report the number as it is; no bar |
| 7.4 | 24 h category hit rate against KLH stations | ≥ 60% exact, ≥ 90% within one class |
| 7.5 | 2023 hold-out AUC and top-10% capture, against InaRISK hazard and "peat share only" baselines | Must beat both baselines |
| 7.6 | Share of alerts within 2 km / 2 days of a Daops report; false alarms from static sources | Track; no bar |

---

## 11. Open requests to make

| To | Ask |
| --- | --- |
| BIG | Redistribution terms for `Administrasi_AR_KelDesa_10K` (or confirm that a derived, simplified desa layer may be published with credit). |
| Pemprov Sumsel (datagambut) | Fix the GeoNode data store, or send the `sekat_kanal`, `sumur_bor`, `desa_peduli_api`, `desa_peduli_gambut` and `tp_tmat_*` layers. |
| BPGMN (new peat agency) / ex-BRGM | SiPALAGA water-table data and the PRIMS canal-block inventory, even daily summaries per KHG. |
| BMKG | Numeric SPARTAN grids (or permission to read the tile API), and HTH station values. |
| Kemendikdasmen Pusdatin | School coordinates (NPSN, lat/lon) for Sumatra and Kalimantan. |
| CCROM-SEAP IPB | Compare FRS kabupaten forecasts with our desa ranking; possible collaboration. |
| Kemenhut PKHL | Daops working-area polygons, so patrol lists can be grouped by Daops. |

---

## References (verified DOIs via Crossref, 17 Oct 2026)

- Cattau, M.E. et al. 2016. Sources of anthropogenic fire ignitions on the peat-swamp landscape in Kalimantan, Indonesia. *Global Environmental Change* 39, 205–219. https://doi.org/10.1016/j.gloenvcha.2016.05.005
- Sloan, S. et al. 2017. Fire activity in Borneo driven by industrial land conversion and drought during El Niño periods, 1982–2010. *Global Environmental Change* 47, 95–109. https://doi.org/10.1016/j.gloenvcha.2017.10.001
- Prasetyo, L.B. et al. 2016. Historical forest fire occurrence analysis in Jambi Province during the period of 2000–2015: its distribution and land cover trajectories. *Procedia Environmental Sciences* 33. https://doi.org/10.1016/j.proenv.2016.03.096
- Field, R.D. et al. 2016. Indonesian fire activity and smoke pollution in 2015 show persistent nonlinear sensitivity to El Niño-induced drought. *PNAS* 113, 9204–9209. https://doi.org/10.1073/pnas.1524888113
- Field, R.D., van der Werf, G.R., Shen, S.S.P. 2009. Human amplification of drought-induced biomass burning in Indonesia since 1960. *Nature Geoscience* 2. https://doi.org/10.1038/ngeo443
- Fernandes, K. et al. 2017. Heightened fire probability in Indonesia in non-drought conditions: the effect of increasing temperatures. *Environ. Res. Lett.* 12, 054002. https://doi.org/10.1088/1748-9326/aa6884
- Spessa, A.C. et al. 2015. Seasonal forecasting of fire over Kalimantan, Indonesia. *NHESS* 15, 429–442. https://doi.org/10.5194/nhess-15-429-2015
- Shawki, D. et al. 2017. Long-lead prediction of the 2015 fire and haze episode in Indonesia. *GRL* 44. https://doi.org/10.1002/2017GL073660
- de Groot, W.J. et al. 2006. Development of the Indonesian and Malaysian Fire Danger Rating Systems. *Mitig. Adapt. Strateg. Glob. Change* 12, 165–180. https://doi.org/10.1007/s11027-006-9043-8
- Field, R.D. et al. 2015. Development of a Global Fire Weather Database. *NHESS* 15, 1407–1423. https://doi.org/10.5194/nhess-15-1407-2015
- Taufik, M. et al. 2017. Amplification of wildfire area burnt by hydrological drought in the humid tropics. *Nature Climate Change* 7. https://doi.org/10.1038/nclimate3280
- Wösten, J.H.M. et al. 2008. Peat–water interrelationships in a tropical peatland ecosystem in Southeast Asia. *Catena* 73, 212–224. https://doi.org/10.1016/j.catena.2007.07.010
- Putra, E.I. et al. 2018. Determining critical groundwater level to prevent degraded peatland from severe peat fire. *IOP Conf. Ser.: EES* 149, 012027. https://doi.org/10.1088/1755-1315/149/1/012027
- Dadap, N.C. et al. 2021. Drainage canals in Southeast Asian peatlands increase carbon emissions. *AGU Advances* 2. https://doi.org/10.1029/2020AV000321
- Konecny, K. et al. 2016. Variable carbon losses from recurrent fires in drained tropical peatlands. *Global Change Biology* 22. https://doi.org/10.1111/gcb.13186
- Lu, Y. et al. 2021. Drainage canal impacts on smoke aerosol emissions for Indonesian peatland and non-peatland fires. *Environ. Res. Lett.* 16. https://doi.org/10.1088/1748-9326/ac2011
- Hoscilo, A. et al. 2011. Effect of repeated fires on land-cover change on peatland in southern Central Kalimantan, Indonesia, from 1973 to 2005. *Int. J. Wildland Fire* 20. https://doi.org/10.1071/WF10029
- Vetrita, Y., Cochrane, M.A. 2019. Fire frequency and related land-use and land-cover changes in Indonesia's peatlands. *Remote Sensing* 12, 5. https://doi.org/10.3390/rs12010005
- Nikonovas, T. et al. 2020. Near-complete loss of fire-resistant primary tropical forest cover in Sumatra and Kalimantan. *Communications Earth & Environment* 1. https://doi.org/10.1038/s43247-020-00069-4
- Dohong, A., Aziz, A.A., Dargusch, P. 2018. A review of techniques for effective tropical peatland restoration. *Wetlands* 38. https://doi.org/10.1007/s13157-018-1017-6
- Tacconi, L. 2016. Preventing fires and haze in Southeast Asia. *Nature Climate Change* 6, 640–643. https://doi.org/10.1038/nclimate3008
- Carmenta, R. et al. 2017. Perceptions across scales of governance and the Indonesian peatland fires. *Global Environmental Change* 46. https://doi.org/10.1016/j.gloenvcha.2017.08.001
- Purnomo, H. et al. 2017. Fire economy and actor network of forest and land fires in Indonesia. *Forest Policy and Economics* 78. https://doi.org/10.1016/j.forpol.2017.01.001
- Edwards, R.B. et al. 2020. Causes of Indonesia's forest fires. *World Development* 127, 104717. https://doi.org/10.1016/j.worlddev.2019.104717
- Tan-Soo, J.-S., Pattanayak, S.K. 2019. Seeking natural capital projects: forest fires, haze, and early-life exposure in Indonesia. *PNAS* 116. https://doi.org/10.1073/pnas.1802876116

Regulations and guidance:

- Permen LHK P.14/2020 on ISPU: [BN 774/2020](https://peraturan.go.id/files/bn774-2020.pdf); [BPK JDIH](https://peraturan.bpk.go.id/Details/163466/p).
- Permen LHK P.32/2016 on forest and land fire control (defines MPA and the brigade structure): [BPK JDIH](https://peraturan.bpk.go.id/Details/298069).
- PP 57/2016 (amends PP 71/2014), Art. 23: 0.4 m water-table criterion ([Mongabay summary](https://mongabay.co.id/2016/12/15/catatan-hukum-peraturan-gambut-lama-vs-baru/amp/) [S]).
- SE Mendikdasmen No. 20/2026 on schools in haze-affected areas ([news report](https://www.rctiplus.com/news/detail/terkini/5464704/kemendikdasmen-terbitkan-aturan-sekolah-di-wilayah-terdampak-karhutla--ispu-jadi-penentu-) [S]; the PDF copy found is a scanned image, so check the official text).
- Kemenkes, 26 Aug 2026, protection of vulnerable groups during karhutla: [kemkes.go.id](https://kemkes.go.id/id/kemenkes-perkuat-perlindungan-kelompok-rentan-hadapi-karhutla).
