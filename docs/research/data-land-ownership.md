# Research basis: "whose land is burning?" (data pemilik tanah)

Compiled 2026-10-17. The question: can each fire event be attributed to the concession or permit (and the company and group) it overlaps? This note lists the data sources, says which were tested from the build container, and recommends a plan.

How each claim was checked:

- **[T]** tested from this container with curl (HTTP result given).
- **[V]** read in the source's own text or metadata.
- **[S]** web search snippet only.
- **[M]** from memory; check before relying on it.

## Summary

- **The forest-permit side is answerable now, from official data.** The Ministry of Forestry (Kementerian Kehutanan, split from KLHK in late 2024) runs a new public ArcGIS Server at `geoportal.planologi.kehutanan.go.id`. Its PBPH layer (all forest utilisation permits, "definitif s.d. Mei 2026", 541 polygons) answers point and polygon queries with the holder's name, SK number, SK date and area [T]. It does **not** return geometry (`geometry: null`), so we can query it but not download it. PIPPIB 2026-I, Hutan Adat, the four Perhutanan Sosial permit types and the ministry's own burned-area polygons (2025 and Jan–Jul 2026) all return geometry and can be downloaded [T].
- **Oil palm is the hard gap.** HGU (plantation land title) holder data is still closed. ATR/BPN has not complied with the 2017 Supreme Court ruling. GFW's Indonesia oil palm layer dates from 2012, and GFW marks every Indonesian concession layer "view only, not for download". RSPO publishes boundaries for every country except Indonesia, citing Indonesian law. The only rich, current concession-to-group map is Nusantara Atlas (TheTreeMap), which is behind a login and has no open licence.
- **Group ownership comes from joins, not from permit data.** Kemenhut gives only the PT name. Trase gives PT → corporate group for pulpwood suppliers (105 suppliers) and for palm mills (1,452 mills); both are open downloads [T].
- **Old domains are dead.** `geoportal.menlhk.go.id`, `sigap.menlhk.go.id` and `sipongi.menlhk.go.id` no longer resolve in DNS from here [T]. Every GFW citation that points at them is stale. `geoportal.esdm.go.id` also fails to resolve, and ESDM's MOMI WIUP layers need a token [T].

## Sources

### Official government sources

| Source | Endpoint | Test | Format | Licence or terms | Freshness | Key fields | Ingest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Kemenhut PBPH** (ex IUPHHK-HA/HT, HPH + HTI + PBPH-HL) | `https://geoportal.planologi.kehutanan.go.id/server/rest/services/Peta_Interaktif_2026/PBPH_AR_50K/MapServer/0/query` | [T] 200. `returnCountOnly` = 541. A point query returns the permit holder's name. Envelope and multipoint queries work. Geometry comes back `null` (suppressed). | ArcGIS REST JSON, GeoJSON, PBF; maxRecordCount 2000 | No licence stated. One Map Policy (KSP) IGT; credit "Dit. Bina Usaha Pemanfaatan Hutan, Ditjen PHL, Kemenhut" [V] | "Perkembangan PBPH definitif s.d. Mei 2026" [V] | `NAMOBJ` (holder), `NO_SK`, `TGL_SK`, `LSSK` (ha), `JENIS` (PBPH HP/HL), `KEGIATAN` (PHHK, PJL, PHHBK…), `KODE_PROV` | Medium. No bulk download: one query per point or cell, cached. HA (natural forest) and HT (plantation) are not split cleanly (the `KEGIATAN` codes and FCODE may help). |
| **Kemenhut PIPPIB 2026-I** (moratorium: primary forest + peat) | `…/Peta_Interaktif_2026/PIPPIB_AR_250K/MapServer/0` | [T] 200, 156,426 features, geometry returned | as above | Kepmenhut 2438/2026 [V] | 2026 period I | `PIPPIB` ∈ {GAMBUT, PRIMER, KAWASAN} | Easy: paged download (≈79 pages). Gives a "fire in moratorium area" flag. |
| **Kemenhut Kawasan Hutan** (forest area status) | `…/Peta_Interaktif_2026/KWSHUTAN_AR_250K/MapServer` | [T] capability `Map` only. Query and identify both give 400 "not supported" | image only | — | June 2026 rev 1 [V] | `FUNGSIKWS`, `NOSKKWS` (from layer JSON) | Not ingestible. Fallback: GFW `idn_forest_area` v201709 (downloadable asset, fields `fungsikawa`, `kelas`) [T]. |
| **Kemenhut Areal Karhutla** (official burned area) | `…/Areal_Kebakaran_Hutan_dan_Lahan_2025/MapServer/0` and `…_Periode_Berjalan/MapServer/0` | [T] 200. 67,237 polygons (2025) and 30,112 (2026, max `KET` = 20260731). Geometry returned. | as above | Dit. Pengendalian Karhutla, Ditjen Gakkum [V] | 2026 data through end of July | `KET` (date YYYYMMDD), `PERIODE` (month), `AKURASI` | Easy. Useful for validating our area estimate. Not ownership data. |
| **Kemenhut Hutan Adat** (designated customary forest) | `…/HUTAN_ADAT_AR_50K/MapServer/0` | [T] 200, 168 features, geometry returned | as above | Dit. PKTHA [V] | Jan 2026 | `NAMA_MHA`, `NOMOR_SK`, `TGL_SK`, `LUAS_SK`, `KODE_KAB` | Easy. |
| **Kemenhut Perhutanan Sosial** permits: PPHD (village forest), PPHKm, PPHTR, PKK | `…/PPHD_AR_50K`, `…/PPHKm_AR_50K`, `…/PPHTR_AR_50K`, `…/PKK_AR_50K` (`/MapServer/0`) | [T] 200 (PPHD: 2,391 features, geometry returned) | as above | Dit. PKPS [V] | 2026 | PPHD: `NAMA_LD` (village forest institution), `NO_SK_PPHD`, `NAMA_DESA`, `LUAS_PPHD` | Easy. These holders are communities, so the label must be worded with care (see cautions). |
| Kemenhut PIAPS rev X, PPKH (borrow-use permits, e.g. mining in forest), KHKP, PPTPKH | `…/PIAPS_AR_250K`, `…/PPKH_AR_50K_012026` (layers 0–2), … | [T] PIAPS queryable. PPKH layer 0 has no fields and returns 400; layers 1–2 were not tested | as above | — | Jan 2026 | — | PPKH is worth a follow-up: it is the forest-side record of mining and infrastructure permits. |
| Kemenhut INTERAKTIF_SIGAP folder | `…/server/rest/services/INTERAKTIF_SIGAP` | [T] 499 Token Required | — | login | — | — | No. |
| Old KLHK hosts: `geoportal.menlhk.go.id`, `sigap.menlhk.go.id`, `sipongi.menlhk.go.id`, `pskl.menlhk.go.id` | — | [T] no DNS or proxy 502. WebFetch: ENOTFOUND | — | — | dead | — | Replace every reference with `*.kehutanan.go.id`. |
| **ATR/BPN BHUMI** (land parcels, HGU) | `https://bhumi.atrbpn.go.id/peta` | [T] 200. The parcel layer `umum:Persil` is served through a session-token proxy (`/expapi/loginApi`, `/expapi/getPersil`) | proxied WMS/JSON | Viewer only; no open data terms | live | Parcel boundary and type of right. The viewer does not show the holder name [M] | No. Scraping a tokenised proxy is out of bounds, and it would not give HGU holders anyway. |
| **ESDM MOMI** (mining WIUP/IUP) | `https://momi.minerba.esdm.go.id/gisserver/rest/services` | [T] 200 at the root. The `Pusat`, `Daerah`, `FS`, `EDW` and `Hosted` folders all give 499 Token Required. Only auction (`Lelang`) points are public. | ArcGIS 10.61 | Registration needed ("Pengguna Umum" account) | live | (not visible) | Hard. Needs an account; terms of reuse unknown. `geoportal.esdm.go.id`: [T] resolve_failed / 503. |

### NGO and aggregator sources

| Source | Endpoint | Test | Format | Licence or terms | Freshness | Key fields | Ingest |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **GFW oil palm concessions** | Data API `https://data-api.globalforestwatch.org/dataset/gfw_oil_palm/v2025`; tiles `https://tiles.globalforestwatch.org/gfw_oil_palm/v2025/{default,dynamic}/{z}/{x}/{y}.pbf` | [T] metadata 200. `/query` → 403 "missing valid API key". Tiles 200; a decoded Riau z8 tile has 61 IDN features with attributes. | MVT, SQL query, ndjson / shp / gpkg (with API key) | "CC BY 4.0 (**excluding Indonesia**)". "Indonesia … obtained from the Ministry of Forestry in **2012** … restricted this dataset to view only" [V] | IDN `source_yr` 2012 | `conc_name`, `company`, `comp_group` (e.g. "Surya Dumai Group", "RGE Group", "No group"), `cont_type` (e.g. Pencadangan), `gfw_area__ha` | Technically easy (tiles), but republishing the attributes in our JSON goes against "view only". Showing GFW tiles as a map overlay is closer to "view"; confirm with GFW before doing that. Ten or more years out of date. |
| **GFW wood fiber (HTI)** | `gfw_wood_fiber/v2025` (same pattern) | [T] as above. Tile: 25 IDN features. | as above | Same "excluding Indonesia, view only"; IDN from KLHK **2021** [V] | 2021 | `conc_name`, `notes` (HT). For IDN, `company` and `comp_group` are **empty** | Superseded by Kemenhut PBPH (May 2026). |
| **GFW logging (HPH)** | `gfw_managed_forests/v2025` | [T] metadata 200; z8 Riau tile empty | as above | "Excluding Indonesia and Gabon", view only; IDN 2021 [V] | 2021 | same schema | Superseded by PBPH. |
| **GFW mining** | `gfw_mining_concessions/v2025` | [T] metadata 200. All assets `is_downloadable: false`. Tile has `cont_id`, `cont_type` (OPERASI PRODUKSI) and `mineral`, but no company for the sample. | as above | "Excluding Indonesia", view only; IDN from ESDM **2021** [V] | 2021 | `conc_name`, `cont_id` (IUP no.), `cont_type`, `mineral`, `company` (often empty) | View only. Best available open-ish mining data, but stale. |
| GFW `idn_forest_moratorium` v20200923, `idn_wood_fiber` v20200725 | Data API | [T] 200 | — | "View-Only, Not for Download" [V] | 2020 | — | Superseded by Kemenhut PIPPIB 2026 and PBPH. |
| **GFW / WRI Universal Mill List** | `…/dataset/gfw_universal_mill_list/v202508/download/csv?sql=SELECT … FROM data WHERE country='Indonesia'` | [T] 200 **without an API key**; 1,396 IDN mills | CSV, SHP, MVT | CC BY 4.0 [V] | Aug 2025 (GFW copy). Rainforest Alliance hosts a monthly Excel [S] | `uml_id`, `parent_com`, `mill_name`, `rspo_statu`, lat/lon, `province`, `district` | Easy. Group lookup and "nearest mill" context. |
| **Trase Indonesia palm oil mills** | `https://resources.trase.earth/data/facilities-data/IDN_PO_mills_clean.geo.json` | [T] 200, 970 KB, 1,452 mills; Last-Modified 2026-10-08 | GeoJSON | CC BY 4.0 for site data; commercial use: contact Trase [V] | 2025 coverage | `trase_code`, `uml_id`, `group` (411 "UNKNOWN"), `company`, `mill_name`, `capacity_tonnes_ffb_hour`, `active`, `kabupaten_name` | Easy. PT → group dictionary for palm. |
| **Trase Indonesia wood pulp v3.2.0** | `https://resources.trase.earth/20261008/data/supply-chains/indonesia_wood_pulp_v3_2_0.zip` | [T] 200, 2.4 MB zip → 18 MB CSV | CSV | as above | 2015–2024, released 2026-10 | `wood_supplier` (concession PT), `wood_supplier_corporate_group` (SINAR MAS 38, RGE 20, UNKNOWN 33 …), `concession_permit_year`, `wood_supplier_trase_id`, `pulp_mill`, `importer` | Easy. A **PT → group** join key for PBPH-HT holders (105 suppliers). Also: pulp mills GeoJSON `id_wood_mills_facilities_v2026_02_10.geo.json` [T link]. |
| Trase Indonesia palm oil v1.2.5 | `…/indonesia_palm_oil_v1_2_5.zip` | [T] 200, 163 MB zip, 1.2 GB CSV | CSV | as above | 2018–2024 | `mill`, `mill_group`, `exporter_group`, `kabupaten_of_production`. No concessions. | Not needed; the mill file is enough. |
| **Nusantara Atlas / TheTreeMap** | `https://map.nusantara-atlas.org/` | [T] 200. The app bundle defines concession layers `oilpalm`, `pulpwood`, `mining`, `timber`, `pbph`, `logging`, `hgu`, `psnmerauke`, with fields `groupcom`, `parentgroup`, `subgroup`, `license_number`, `license_status`, `group_parent`. Data goes through an authenticated API (`auth.nusantara-atlas.org`). | web app | Terms of Use plus "Premium Terms"; no open licence found [V] | live (2026) | rich: name, group, licence no. | Do not scrape. **Ask TheTreeMap (David Gaveau) for a data-sharing licence**; this is the only current source with HGU-like oil palm boundaries and groups. |
| **RSPO / GeoRSPO** | `https://rspo.org/as-an-organisation/tools/georspo/`; GFW `rspo_oil_palm/v2025` | [T] rspo.org 200; `georspo.rspo.org` no connection | SHP | Download excludes Indonesia: "Indonesian national laws … prohibit parties other than government agencies from publishing and sharing plantation boundaries in shapefile format" [V] | Sep 2026 | — | None for Indonesia. Strong legal signal; see cautions. |
| Greenpeace **Kepo Hutan** | `kepohutan.greenpeace.org` | [T] no DNS | — | — | 2016 data | — | Offline. 2016 shapefiles digitised from ministry maps; KLHK took Greenpeace to court over them [S]. |
| **Auriga Nusantara** | `https://auriga.or.id/` | [T] 200; no data portal or download found [S] | reports | — | — | — | Partner or ask, not ingest. |
| **MapHubs** (ex mapforenvironment.org) | `https://www.maphubs.com/` | [T] 200 at the root; search URL 404 | user-hosted layers | per layer | varies | — | Not verified; low priority. |
| **BRWA wilayah adat** (indigenous territories, registered and indicative) | `https://brwa.id/data-wilayah-adat`; WMS `https://peta.brwa.or.id/map/wa4.map`; MVT `…/wav.map?…&map.imagetype=mvt` | [T] site 200. WMS and MVT both 403 (Cloudflare challenge). | MapServer WMS/MVT | No open licence; data on request [M] | live | name of community, status | Request data, or use LandMark (below). |
| **LandMark** (includes Indonesian customary lands) | GFW `landmark_ip_lc_and_indicative_poly/v20260617` | [T] metadata 200 | vector | CC BY-SA 4.0 + LandMark ToS [V] | Jun 2026 | — | Medium. Indonesian coverage and its source (BRWA?) not verified. |

### HGU legal status

| Item | Status |
| --- | --- |
| Supreme Court ruling | Forest Watch Indonesia v. ATR/BPN: the Court held that HGU documents (holder name, location, area, map) are public information under UU 14/2008 KIP. Cited as **121 K/TUN/2017** (Mongabay, Aceh Information Commission) and as **122 K/TUN/2017**, 6 March 2017 (Ombudsman); the review **61 PK/TUN/KI/2020** (26 March 2020) upheld it [S]. |
| Compliance | ATR/BPN still refused in 2018. The Ombudsman issued a formal recommendation. In 2023 ATR/BPN said it "could not yet" comply, citing conflicting laws, and planned a second review [S]. |
| Recent | March 2026: the Aceh Information Commission ordered HGU data opened, citing the MA ruling as jurisprudence [S]. Disclosure is province by province and on request; there is no national dataset. |
| Practical | No public HGU polygons with holders exist. Leaked or partial copies circulate in NGO circles; do not use them. |

## What can be attributed today

| Land type | Share of fire risk [M] | Best usable source | Holder known? | Group known? |
| --- | --- | --- | --- | --- |
| Pulpwood (PBPH-HT) | high on Sumatra and Kalimantan peat | Kemenhut PBPH (query) | yes (PT, SK) | via Trase wood pulp join (~70% of suppliers) |
| Natural-forest logging (PBPH-HA) | medium | Kemenhut PBPH (query) | yes | rarely (no open source) |
| Oil palm (HGU / IUP-B) | high | none open and current; GFW 2012 view only; Nusantara Atlas by licence | **no** | via UML/Trase mills only as context |
| Mining (IUP) | low for fire | GFW 2021 view only; MOMI with account | partly | no |
| Social forestry, Hutan Adat | medium | Kemenhut PS + Hutan Adat (download) | yes (community) | n/a |
| Moratorium / peat | — | PIPPIB 2026-I (download) | n/a | n/a |
| Forest vs non-forest (APL) | — | GFW kawasan hutan 2017 (download); Kemenhut 2026 map-only | n/a | n/a |

## Legal and ethical cautions

1. **An overlap is not liability.** Fire inside a permit can be arson by others, spread from a neighbour, or community farming; under PP 4/2001 and the karhutla rules [M] the permit holder must prevent and control fire, but the courts decide fault. Wording: "terdeteksi di dalam areal izin" (detected inside the permit area), never "dibakar oleh" (burned by).
2. **Boundaries are imprecise.** VIIRS pixels are ~375 m and FIRMS geolocation can be off by a pixel; the permit maps are 1:50,000 (±25 m at best) and the GFW layers 1:250,000. Treat fires within ~500 m of a boundary as "near" rather than "inside".
3. **Permits change.** SKs are revoked, renamed and transferred: the January 2022 revocation of ~192 forest permits [M], and the `REMARK` "SK PERUBAHAN NOMENKLATUR" on many records [T]. Store `source`, `version`, `NO_SK` and `TGL_SK`, show the "as of" date, and re-pull monthly.
4. **Group mapping is the riskiest step.** Trase and UML group labels are analysts' judgments about corporate ties; they can be wrong or contested. Show the group with its source ("grup menurut Trase 2026") and allow "unknown".
5. **Redistribution.** GFW's Indonesia concession layers are "view only, not for download". RSPO cites Indonesian law against non-government publication of plantation boundaries in shapefile form. We should publish **attributes per fire event** (permit name, SK, overlap share), not re-host permit polygons, unless the source allows it (Kemenhut IGT under the One Map Policy is the clearest case).
6. **Community land.** Hutan Desa, HKm and Hutan Adat holders are villages and indigenous groups. Do not rank or shame them alongside corporations; label them "Perhutanan Sosial" / "Hutan Adat" and keep them out of any "companies" leaderboard.
7. **Defamation risk** (UU ITE). Naming a PT next to a fire is a factual statement about location; adding a group name is an inference. Add a visible methodology link and a correction channel.

## Recommendation

### Phase 1: use these three sources first

1. **Kemenhut PBPH** (query API): holder, SK, area for HTI and HPH. Per run, query only hotspot cells that are not yet cached (VIIRS cells rounded to ~0.0035°; cache key = cell + layer version). Expect at most a few thousand point queries in a bad week; ~1 s each, so run them in parallel with a polite limit (≤4 concurrent) and back off on errors. Polygon fallback: one envelope query per event to list candidates, then point queries.
2. **Kemenhut PIPPIB 2026-I + Perhutanan Sosial + Hutan Adat** (download once a month into `regions`, same STRtree path as KHG): flags `in_moratorium`, `social_forestry`, `hutan_adat`.
3. **Trase wood pulp v3.2.0 + Trase palm mills + UML** (download): a `company_groups.csv` dictionary of normalised PT name → group, with the source. Normalise names: strip "PT", punctuation and doubled spaces ("PT  ARARA ABADI").

Keep oil palm as "unknown holder" for now. Show `kawasan` = APL (GFW 2017) as a hint that the land is probably plantation or community. In parallel, write to **TheTreeMap** (Nusantara Atlas) and **GFW** about licensed use of their Indonesian concession attributes. Those two requests are the only realistic route to oil palm holders.

### Event-level output

The per-hotspot tag follows the existing `on_peat` pattern (each hotspot is tagged, then the event takes shares):

```json
"land": {
  "as_of": "2026-05",
  "concessions": [
    {
      "name": "PT Contoh Hutani",
      "type": "PBPH-HT",
      "permit_no": "SK.xxx/MENLHK/…",
      "permit_date": "2021-09-…",
      "group": "Grup Contoh",
      "group_source": "Trase wood pulp v3.2.0",
      "share": 0.63,
      "source": "Kemenhut PBPH_AR_50K (definitif s.d. Mei 2026)"
    }
  ],
  "outside_permits_share": 0.37,
  "moratorium_share": 0.10,
  "social_forestry": null,
  "hutan_adat": null,
  "kawasan": "HP",
  "near_boundary": false
}
```

- **UI line:** "Konsesi: PT Contoh Hutani (Grup Contoh*), PBPH-HT, 63% titik api". The asterisk links to the cautions. (Placeholder names and numbers: no real company is meant.)
- **`share`** = fraction of the event's unique VIIRS cells inside the permit, the same unit as `peat_share`.
- **`near_boundary`** = true when less than 80% of the event's cells fall in one permit and the rest are within 500 m of that permit's edge (needs geometry, so for PBPH only via a buffered point query; phase 2).
- **Dashboard:** "fires by permit type" (PBPH-HT, PBPH-HA, social forestry, outside known permits). A per-company table only after review.

### Phase 2

- PPKH (forest borrow-use permits, mostly mining) from the same Kemenhut server; layers 1–2 still to be tested.
- MOMI account for mining IUPs, or the GFW 2021 layer if GFW allows.
- Oil palm via a Nusantara Atlas licence, or via HGU disclosures by province through KIP requests (Aceh 2026 precedent).
- Validate our burned-area estimate against the Kemenhut Areal Karhutla polygons.

## Endpoint checklist (tested 2026-10-17)

| Endpoint | Result |
| --- | --- |
| `geoportal.planologi.kehutanan.go.id/server/rest/services?f=json` | 200, ArcGIS 12.1, folders incl. `Peta_Interaktif_2026` |
| `…/PBPH_AR_50K/MapServer/0/query` (count / point / multipoint) | 200; 541; holder returned; geometry null |
| `…/PIPPIB_AR_250K`, `…/HUTAN_ADAT_AR_50K`, `…/PPHD_AR_50K`, `…/Areal_Kebakaran_Hutan_dan_Lahan_*` | 200, geometry returned |
| `…/KWSHUTAN_AR_250K` query / identify | 400 not supported (map only) |
| `…/INTERAKTIF_SIGAP` | 499 token required |
| `geoportal.menlhk.go.id`, `sigap.menlhk.go.id`, `sipongi.menlhk.go.id` | DNS fail / proxy 502 |
| `data-api.globalforestwatch.org/dataset/gfw_{oil_palm,wood_fiber,managed_forests,mining_concessions}/v2025` | 200 metadata; `/query` 403 without key |
| `tiles.globalforestwatch.org/gfw_oil_palm/v2025/dynamic/8/200/127.pbf` | 200, 61 features with company/group |
| `…/gfw_universal_mill_list/v202508/download/csv?sql=…` | 200 without key |
| `resources.trase.earth/data/facilities-data/IDN_PO_mills_clean.geo.json` | 200 |
| `resources.trase.earth/20261008/data/supply-chains/indonesia_wood_pulp_v3_2_0.zip` | 200 |
| `momi.minerba.esdm.go.id/gisserver/rest/services/Pusat` | 499 token required |
| `geoportal.esdm.go.id` | resolve failed / 503 |
| `bhumi.atrbpn.go.id/peta` | 200 (token-proxied parcels, no holders) |
| `map.nusantara-atlas.org` | 200 (login-gated API) |
| `peta.brwa.or.id/map/wa4.map` | 403 (Cloudflare) |
| `kepohutan.greenpeace.org` | DNS fail |

## Sources

- GFW Data API metadata: `https://data-api.globalforestwatch.org/dataset/<id>` (licence, cautions and source fields quoted above).
- Kemenhut geoportal: `https://geoportal.planologi.kehutanan.go.id/server/rest/services/Peta_Interaktif_2026`.
- Trase open data: https://trase.earth/open-data/datasets/indonesia-palm-oil-mills, https://trase.earth/open-data/datasets/supply-chains-indonesia-wood-pulp.
- RSPO GeoRSPO: https://rspo.org/as-an-organisation/tools/georspo/.
- HGU ruling: https://www.mongabay.co.id/2017/03/14/mahkamah-agung-putuskan-pemerintah-wajib-buka-data-hgu-sawit-di-kalimantan/, https://mongabay.co.id/2018/06/22/setahun-lebih-putusan-mahkamah-agung-atr-belum-buka-data-hgu-sawit/, https://ombudsman.go.id/news/r/rekomendasi-belum-dijalankan-kementerian-atrbpn-ombudsman-ri-ingatkan-pentingnya-keterbukaan-informasi-sebagai-wujud-pelayanan-publik-prima, https://mongabay.co.id/2026/03/26/komisi-informasi-aceh-putuskan-data-hgu-terbuka-untuk-publik/.
- Kepo Hutan background: https://www.greenpeace.org/southeastasia/publication/702/mapping-transparency-essential-to-stopping-indonesias-fires/, https://news.mongabay.com/2016/12/indonesias-forestry-ministry-takes-greenpeace-to-court-over-freedom-of-information-request.
- UML: https://knowledge.rainforest-alliance.org/docs/the-universal-mill-list.
