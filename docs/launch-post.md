# Launch post drafts

Numbers as of 17 Oct 2026. Re-check `area.json`, `fire_history.json` and
`dashboard.json` before posting.

## Bahasa (thread)

1/ Kami bikin peta karhutla Indonesia yang independen dan terbuka metodenya: titik panas satelit NASA dikelompokkan jadi kejadian kebakaran, asap dimodelkan 72 jam ke depan, dan kualitas udara dikoreksi dengan stasiun ISPU. Ini bukan situs pemerintah. [link]

2/ Luas terbakar 2026 menurut perhitungan kami: 2,3–4,2 juta ha. Angka resmi SiPongi: ±202 ribu ha. Rentang kami berasal dari piksel api VIIRS 375 m yang dikalibrasi dua cara: ke angka resmi KLHK 2019/2023 dan ke peta Sentinel-2 independen (Gaveau dkk. 2021).

3/ Kami juga cek langsung pakai citra satelit. Di Kalimantan Tengah, 700 titik sampel Sentinel-1/2 dan Landsat memberi perkiraan ≈664 ribu ha (95%: 374 rb–1,06 jt). Angka resmi provinsi: 7.634 ha.

4/ Api kembali ke tempat yang sama: 47% titik api 2026 jatuh di lahan yang sudah pernah terbakar 2012–2025, dan 63% kalau di gambut. Lahan itu cuma ±11% daratan Indonesia. Ini peta prioritas pembasahan gambut dan patroli.

5/ Pencegahan: peta risiko kebakaran 5 hari ke depan dari kode cuaca kebakaran (sistem yang sama dengan SPARTAN BMKG) plus gambut dan api terbaru. Diuji pada musim 2023: sel "Ekstrem" benar-benar terbakar keesokan harinya 65% kali, sel "Rendah" 1,5%.

6/ Udara: di kabut tebal, model CAMS membaca hanya ±39% dari angka stasiun, jadi peta kabut kami dikoreksi dengan stasiun ISPU, DOE Malaysia dan NEA Singapura. Saran untuk sekolah dan warga mengikuti SE Mendikdasmen 20/2026 dan Kemenkes. Setiap prakiraan dicatat dan dinilai terhadap stasiun.

6b/ Untuk pencegahan di lapangan: daftar "desa waspada". Ada dua daftar: desa yang punya titik panas minggu ini (pada uji 2023, 39% terbakar lagi minggu berikutnya) dan desa yang belum terbakar tapi sudah ≥3 tahun pernah terbakar (12%, 5× rata-rata). Feed RSS per provinsi juga tersedia untuk kebakaran baru, risiko ekstrem, dan udara tidak sehat.

7/ Semua metode, angka uji dan keterbatasannya terbuka. Kalau angka kami salah, kami mau tahu. [link ke docs/models.md]

## English (single post)

We built an independent, open-method tracker for Indonesia's 2026 fires.

- NASA satellite hotspots are grouped into fire events.
- Smoke is modelled 72 h ahead, and the air-quality picture is corrected with ground stations.
- Fire danger is forecast 5 days out. Tested on 2023, "extreme" cells burned the next day 65% of the time.

Our burned-area estimate is 2.3–4.2 M ha; the official figure is ~202k ha. A 700-point satellite-image sample for Central Kalimantan alone gives ≈664k ha (95%: 374k–1.06M). Its official provincial figure is 7,634 ha.

47% of this year's fire pixels (63% on peat) are on land that already burned in 2012–2025. That land is about 11% of Indonesia.

Methods and caveats: [link]

## Before posting

- Post screenshots, not live claims, until the scheduled pipeline is running (it needs the `FIRMS_MAP_KEY` secret).
- The Central Kalimantan sample is marked *sementara* (provisional) in the app; keep that word.
- Do not name companies or permit holders. The permit layer stays off.
