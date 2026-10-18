// How every number in the app is made: one section per metric, opened from
// the (i) link next to it. Mirrors docs/models.md; validation figures are
// fixed hindcast results, live values stay in the cards themselves.
import type { Lang } from "./i18n";

export const METHOD_IDS = [
  "hotspots",
  "events",
  "counts",
  "area",
  "danger",
  "outlook",
  "repeat",
  "desa",
  "alerts",
  "health",
  "haze",
  "stations",
  "cities",
  "transboundary",
  "progression",
  "spread",
  "history",
  "compare",
  "place",
] as const;
export type MethodId = (typeof METHOD_IDS)[number];

export interface MethodSection {
  title: string;
  /** one sentence: what the number is */
  what: string;
  /** how it is computed, in order */
  how: string[];
  /** inputs, with their source */
  data: string[];
  /** how well it did when tested against data it was not fitted on */
  tested?: string[];
  limits: string[];
}

type Methods = Record<MethodId, MethodSection>;

const id: Methods = {
  hotspots: {
    title: "Titik panas",
    what: "Satu titik panas = satu piksel citra satelit yang jauh lebih panas daripada sekitarnya pada satu kali lintasan satelit.",
    how: [
      "Deteksi dari NASA FIRMS: VIIRS (satelit S-NPP, NOAA-20, NOAA-21; piksel 375 m) dan MODIS (Terra, Aqua; piksel 1 km), data hampir real-time (NRT).",
      "Ditambah DEA Hotspots (Geoscience Australia): deteksi VIIRS yang sama dari stasiun penerima langsung, tersedia ±1 jam setelah satelit lewat, sedangkan FIRMS 2–4 jam dan kadang melewatkan lintasan. DEA hanya menggantikan sementara: begitu FIRMS mengirim lintasan yang sama, deteksi DEA untuk lintasan itu dihapus dan diganti FIRMS. Pengolahan DEA menandai sedikit piksel tambahan di tepi api, jadi tanpa aturan ini angka 2026 akan lebih tinggi daripada data pembanding 2012–2025 yang hanya dari FIRMS.",
      "Yang ditampilkan: hanya di daratan/perairan dekat pantai Indonesia, tingkat kepercayaan sedang atau tinggi (MODIS ≥ 30%).",
      "Sumber panas tetap disaring: sel yang panas terus-menerus (≥ 6 bulan berbeda dalam setahun, atau ditandai FIRMS sebagai gunung api, industri, atau lepas pantai) beserta radius 750 m di sekitarnya. Contoh: PLTU, kilang, smelter, suar gas.",
      "Diperbarui tiap 2 jam. Satelit melintas Indonesia sekitar 10–12 kali sehari, dengan jeda di antara lintasan.",
    ],
    data: ["NASA FIRMS (area API, atau berkas regional Asia Tenggara 7 hari tanpa kunci).", "DEA Hotspots, Geoscience Australia (CC BY 4.0).", "Daftar sumber panas tetap: diturunkan dari arsip FIRMS 2019–2026."],
    limits: [
      "Satu kebakaran bisa menghasilkan banyak titik panas, dan satu titik panas belum tentu kebakaran (pantulan matahari, atap panas).",
      "Awan dan asap tebal menutupi api; api kecil atau api gambut di bawah permukaan sering tidak terdeteksi.",
      "Posisi piksel bisa bergeser hingga satu piksel antar lintasan.",
    ],
  },
  events: {
    title: "Kebakaran (pengelompokan titik panas)",
    what: "Titik panas yang berdekatan dalam ruang dan waktu digabung menjadi satu 'kebakaran' yang bisa diikuti dari hari ke hari.",
    how: [
      "Nama kebakaran = desa yang memuat titik panas terbanyak, diikuti kabupatennya (batas desa BPS/OCHA). Kota terdekat ditulis terpisah di panel.",
      "Dua titik panas masuk satu kebakaran bila jaraknya ≤ 1,5 km dan selisih waktunya ≤ 48 jam (berantai: A–B dan B–C berarti A, B, C satu kebakaran).",
      "Status: aktif bila terdeteksi dalam 24 jam terakhir; 'tak terlihat 1–3 hari' bila terakhir terdeteksi 24–72 jam lalu; 'tak terlihat > 3 hari' bila lebih dari 72 jam.",
      "Tingkat bukti 'kuat' bila ada ≥ 2 lintasan satelit, ≥ 2 piksel dalam satu lintasan, deteksi malam hari, atau piksel VIIRS jenuh. Angka utama hanya menghitung kebakaran dengan bukti kuat.",
      "Provinsi dan kabupaten: provinsi dengan titik panas terbanyak, lalu kabupaten dengan titik panas terbanyak di dalam provinsi itu.",
      "Lahan gambut: ≥ 50% titik panasnya di dalam Kesatuan Hidrologis Gambut (KHG 2017).",
    ],
    data: ["Titik panas (lihat atas).", "Batas wilayah: 38 provinsi. Kabupaten/kota dari geoBoundaries (BPS 2020); kabupaten Papua dan Papua Barat dikelompokkan ke Papua Selatan, Papua Tengah, Papua Pegunungan (UU 14–16/2022) dan Papua Barat Daya (UU 29/2022). Tidak ada kabupaten baru sejak 2020, jadi batasnya sama dengan peta resmi.", "KHG 2017 (KLHK)."],
    tested: [
      "Aturan 1,5 km / 48 jam dipilih dengan memeriksa kebakaran 2019 dan 2023 secara visual (docs/clustering-evaluation.md).",
      "'Tak terdeteksi' belum tentu padam. Dari 71.172 kebakaran Jul–Sep 2026, titik yang sama (sel ~1,6 km) terdeteksi lagi dalam 7 hari pada 33% kebakaran non-gambut dan 43% kebakaran gambut yang tak terlihat 1 hari, dan pada 31% / 39% yang tak terlihat 3 hari (46% / 55% dalam 14 hari). Karena itu status ditulis 'tak terlihat', bukan 'padam'.",
    ],
    limits: ["Dua kebakaran berbeda yang berdekatan bisa tergabung; satu kebakaran yang terpotong awan beberapa hari bisa terpisah."],
  },
  counts: {
    title: "Jumlah titik panas dan kebakaran aktif",
    what: "Hitungan titik panas 24 jam terakhir dalam tiga versi, dan jumlah kebakaran aktif.",
    how: [
      "Hitungan kami: semua titik panas yang ditampilkan (5 satelit, kepercayaan sedang–tinggi).",
      "Setara SiPongi: hanya Terra, Aqua, S-NPP dan NOAA-20 (tanpa NOAA-21), semua tingkat kepercayaan — supaya bisa dibandingkan dengan angka Kemenhut.",
      "Kepercayaan tinggi saja: hanya deteksi VIIRS/MODIS kategori tinggi.",
      "Grafik musim memakai satelit S-NPP saja, karena NOAA-20 (2018) dan NOAA-21 (2023) menaikkan jumlah mentah; dengan satu satelit, tahun-tahun bisa dibandingkan secara adil.",
    ],
    data: ["NASA FIRMS."],
    limits: ["Jumlah titik panas bukan luas terbakar dan bukan jumlah kebakaran; satu kebakaran besar bisa menghasilkan ribuan titik panas."],
  },
  area: {
    title: "Perkiraan luas terbakar",
    what: "Rentang luas lahan terbakar musim ini, dihitung dari piksel api satelit dan dicek dengan citra satelit.",
    how: [
      "Untuk tiap satelit VIIRS, hitung sel 375 m unik yang pernah terdeteksi panas musim ini (sekali per musim, bukan per kebakaran).",
      "Rata-ratakan antar satelit yang aktif musim itu, supaya bertambahnya satelit tidak menaikkan angka.",
      "Kalikan 14,06 ha per sel, lalu dengan faktor k. k = 0,49 dicocokkan ke angka resmi KLHK 2019 & 2023 (batas bawah); k = 0,90 dicocokkan ke peta luas terbakar Sentinel-2 independen tahun 2019 (Gaveau dkk. 2021, batas atas).",
      "Uji independen Kalimantan Tengah: 700 titik sampel acak berstrata, tiap titik dinilai terbakar/tidak dari citra Sentinel-1, Sentinel-2 dan Landsat, lalu luas dihitung dengan penduga sampel (Olofsson/Stehman) beserta selang kepercayaan 95%.",
      "'Area terdeteksi panas' pada satu kebakaran = jumlah sel 375 m unik × 14,06 ha: batas atas, bukan luas terbakar terukur.",
    ],
    data: ["NASA FIRMS VIIRS.", "Angka resmi SiPongi (Kemenhut), diambil otomatis.", "Gaveau dkk. 2021, ESSD 13:5353.", "Citra Sentinel-1/2 (Copernicus), Landsat (USGS)."],
    tested: ["Kalibrasi KLHK: k dari 2019 memprediksi 2023 (dan sebaliknya) dalam ±4%.", "Uji sampel Kalimantan Tengah 2026 (sementara): ≈664 ribu ha (95%: 374 ribu–1,06 juta ha)."],
    limits: ["Perkiraan per provinsi bisa meleset hingga 2×.", "Api kecil dan api di bawah awan tidak terlihat; piksel yang terdeteksi tidak terbakar seluruhnya."],
  },
  danger: {
    title: "Risiko kebakaran (model)",
    what: "Peluang munculnya minimal satu titik panas pada suatu hari di sel ±25 km (prakiraan untuk hari ini dan beberapa hari ke depan).",
    how: [
      "Kode cuaca kebakaran sistem Kanada (FFMC, DMC, DC, ISI) — sistem yang sama dengan SPARTAN BMKG — dari NASA GFWED (GEOS-5).",
      "NASA menerbitkan GFWED terlambat beberapa hari, jadi kode hari pertama terbitan terbarunya dibawa maju hari demi hari dengan persamaan FWI Kanada dan cuaca ECMWF terbaru (suhu, kelembapan, dan angin pukul 12 siang setempat, hujan 24 jam sebelumnya), sampai 7 hari ke depan. Prakiraan ini terbit hari ini; bila cuaca ECMWF gagal diambil, yang dipakai prakiraan GFWED apa adanya.",
      "Nilai prakiraan disesuaikan sebarannya (quantile mapping) ke data latih MERRA-2.",
      "Model regresi logistik memakai kode tersebut, porsi lahan gambut, dan jumlah titik panas 1, 7 dan 30 hari terakhir (di Indonesia hampir semua api dinyalakan manusia, jadi tempat yang baru terbakar sangat menentukan).",
      "Kelas mengikuti warna BMKG: Rendah < 5%, Sedang 5–15%, Tinggi 15–40%, Ekstrem ≥ 40%.",
      "Persentase provinsi = bagian sel provinsi itu yang berisiko Ekstrem, dan yang berisiko Tinggi (dua kolom terpisah).",
    ],
    data: ["NASA GFWED (GEOS-5 prakiraan; MERRA-2 untuk pelatihan).", "Cuaca ECMWF IFS lewat Open-Meteo.", "KHG 2017.", "Titik panas VIIRS."],
    tested: [
      "Dilatih pada 2019, diuji pada musim 2023 dengan prakiraan GEOS-5 sungguhan: AUC 0,90 untuk esok hari.",
      "Di sel yang tidak terbakar 7 hari terakhir: AUC 0,82 (kode DC saja: 0,78).",
      "Sel 'Ekstrem' benar-benar terbakar keesokan harinya pada 65% kasus; sel 'Rendah' 1,5%.",
      "Diuji lagi pada Jul–Sep 2026 (tidak dipakai untuk melatih), dengan prakiraan cuaca 1, 3, 5 dan 7 hari: AUC 0,894 / 0,892 / 0,889 / 0,885; sel 'Ekstrem' terbakar pada 73% kasus, sel 'Rendah' 2–3%. Prakiraan NASA yang terbit terlambat hampir tidak mengurangi ketepatan.",
      "Sebagai pembanding, jumlah titik panas 7 hari terakhir saja mencapai AUC 0,866: cuaca menambah ketepatan, tetapi sebagian besar sinyal datang dari tempat yang baru terbakar.",
    ],
    limits: ["Model statistik, bukan peringatan resmi BMKG.", "Sel 25 km terlalu kasar untuk desa; lihat 'Desa waspada'."],
  },
  outlook: {
    title: "Prospek musim",
    what: "Keadaan iklim yang menentukan seberapa panjang dan kering musim kebakaran.",
    how: [
      "ENSO dari indeks ONI NOAA (anomali suhu muka laut Niño3.4 rata-rata 3 bulan): ≥ 2,0 °C El Niño sangat kuat, ≥ 1,5 kuat, ≥ 0,5 El Niño, ≤ −0,5 La Niña.",
      "Dipol Samudra Hindia (IOD) mingguan dari Biro Meteorologi Australia; ≥ 0,4 °C dianggap positif (lebih kering di Sumatra dan Kalimantan).",
      "Peluang tetap kering = bagian dari 51 anggota ansambel musiman ECMWF yang rata-rata hujannya < 4 mm/hari selama 30 atau 60 hari ke depan; di bawah ambang ini api meningkat tajam (Field dkk. 2016).",
    ],
    data: ["NOAA CPC (ONI, Niño3.4 mingguan).", "Bureau of Meteorology (IOD).", "ECMWF SEAS5 via Open-Meteo."],
    tested: [
      "Aturan < 4 mm/hari diuji pada 2012–2025: 896 jendela 30 hari (Jul–Okt) di 8 titik, hujan dari NASA POWER, titik panas VIIRS S-NPP dalam ±1° (~110 km). Jendela kering: median 1.388 titik panas; jendela basah: 178 (≈ 8×). 78% jendela dengan api terbanyak (10% teratas) adalah jendela kering.",
      "Aturan ini lebih lemah di Kalimantan Barat dan Riau (42% dan 50% jendela api terbanyak kering) dan hampir tak berguna di Merauke, yang kering hampir sepanjang musim.",
      "Ketepatan prakiraan hujan ECMWF sendiri tidak kami uji ulang (data uji ulang ansambel tidak tersedia bebas); lihat verifikasi ECMWF.",
    ],
    limits: ["Satu titik per provinsi (ibu kota atau sabuk kebakaran), bukan seluruh provinsi.", "Prakiraan musim resmi: BMKG."],
  },
  repeat: {
    title: "Terbakar berulang (riwayat kebakaran)",
    what: "Bagian titik panas musim ini yang jatuh di lahan yang sudah pernah terbakar 2012–2025.",
    how: [
      "Riwayat dari arsip VIIRS S-NPP 2012–2025 — satu satelit untuk semua tahun supaya adil — hanya api vegetasi (tipe 0) dengan kepercayaan sedang–tinggi, diringkas per sel 375 m.",
      "Titik panas S-NPP musim ini dicocokkan ke sel yang sama.",
      "Lift = bagian titik panas di lahan yang pernah terbakar ÷ bagian daratan Indonesia yang pernah terbakar.",
      "Lapisan peta menampilkan jumlah tahun terbakar per sel ~1 km.",
    ],
    data: ["Arsip tahunan NASA FIRMS VIIRS S-NPP."],
    tested: ["Uji balik 2023: 52% titik panas 2023 jatuh di 10% daratan yang terbakar 2012–2022 (lift 5,1×)."],
    limits: ["Piksel api, bukan luas terbakar terukur.", "'Sel yang sama' adalah syarat ketat; posisi piksel bergeser antar tahun, jadi angkanya cenderung terlalu rendah."],
  },
  desa: {
    title: "Desa waspada",
    what: "Dua daftar desa untuk prioritas patroli dan pencegahan, masing-masing dengan tingkat ketepatan yang terukur.",
    how: [
      "Batas desa (81.912 desa/kelurahan) dipetakan ke grid ~1 km; setiap titik panas dimasukkan ke desa tempat ia jatuh.",
      "Daftar 1: desa dengan titik panas dalam 7 hari terakhir.",
      "Daftar 2: desa tanpa titik panas minggu ini, tetapi ada bagian desa yang terbakar di ≥ 3 tahun berbeda sejak 2012.",
      "Tiap baris diberi risiko kebakaran untuk tanggal di judul kolom dan 2 hari sesudahnya (nilai model tertinggi di wilayah desa) serta porsi gambut.",
    ],
    data: ["Batas desa COD-AB OCHA/BPS (CC BY-IGO).", "Titik panas VIIRS, riwayat 2012–2025, model risiko."],
    tested: [
      "Uji balik musim 2023 (mingguan): desa daftar 1 terbakar lagi minggu berikutnya pada 39% kasus; desa daftar 2: 11,6%; rata-rata semua desa tanpa api: 2,2%; desa yang tidak pernah terbakar: 0,1%.",
      "Penempatan desa: titik panas masuk desa yang benar pada 93% kasus, kecamatan yang benar 98% (dibanding poligon asli).",
    ],
    limits: ["Desa di dekat batas bisa tertukar dengan tetangganya.", "Bukan penetapan resmi."],
  },
  alerts: {
    title: "Peringatan",
    what: "Daftar kejadian penting 7 hari terakhir, juga tersedia sebagai feed RSS/Atom per provinsi.",
    how: [
      "Kebakaran baru: ≥ 10 titik panas dalam 48 jam pertama di lahan gambut, ≥ 20 di luar gambut (feed nasional: 20 / 50).",
      "Meluas: ≥ 50 piksel 375 m baru dalam satu hari.",
      "Risiko ekstrem: provinsi dengan ≥ 25% wilayah berisiko Ekstrem pada hari prakiraan pertama (biasanya hari ini; tanggalnya disebut di peringatan) (feed nasional: satu ringkasan harian).",
      "Udara: kota dengan prakiraan rata-rata PM2,5 24 jam kategori Tidak sehat atau lebih buruk.",
      "Dihitung ulang setiap 2 jam; tiap peringatan punya ID tetap, jadi pembaca RSS menampilkannya sekali.",
    ],
    data: ["Semua data di atas."],
    tested: [
      "Peringatan tidak diuji sendiri; masing-masing mewarisi uji sumbernya: kebakaran baru dan meluas adalah hitungan deteksi satelit; risiko ekstrem dari model risiko kebakaran (lihat 'Risiko kebakaran'); udara dari prakiraan kota (lihat 'Prakiraan kota').",
    ],
    limits: ["Otomatis, bukan peringatan resmi pemerintah."],
  },
  health: {
    title: "Saran kesehatan",
    what: "Saran untuk sekolah dan warga berdasarkan kategori ISPU prakiraan 24 jam ke depan.",
    how: [
      "Kategori dari rata-rata PM2,5 24 jam prakiraan (sudah disesuaikan dengan stasiun), memakai batas ISPU Permen LHK P.14/2020: 15,5 / 55,4 / 150,4 / 250,4 µg/m³.",
      "Saran sekolah mengikuti SE Mendikdasmen No. 20/2026; saran warga mengikuti Kemenkes (26 Agustus 2026).",
      "Setiap prakiraan dicatat, lalu setelah harinya lewat dibandingkan dengan stasiun ISPU dalam radius 25 km, berikut pembanding 'memakai angka hari ini saja'.",
    ],
    data: ["Prakiraan PM2,5 (lihat 'Kabut asap').", "Stasiun ISPU (KLH)."],
    tested: [
      "Belum ada skor kategori: riwayat stasiun ISPU tidak tersedia bebas, jadi pengujian berjalan ke depan sejak 17 Okt 2026. Skornya (kategori tepat, meleset ≤ 1 kategori, dan pembanding 'angka hari ini saja') tampil di kartu setelah 20 perbandingan.",
      "Yang sudah teruji: koreksi stasiun pada hari pertama (lihat 'Prakiraan kota').",
    ],
    limits: ["Bisa meleset satu kategori.", "Keputusan moda belajar ada di dinas pendidikan berdasarkan ISPU harian resmi."],
  },
  haze: {
    title: "Kabut asap (PM2,5)",
    what: "Peta konsentrasi PM2,5 sekarang hingga 72 jam ke depan.",
    how: [
      "Prakiraan CAMS (Copernicus) global, grid 0,75°, semua sumber polusi.",
      "Dikoreksi dengan stasiun: rasio stasiun/CAMS (log) disebar dengan bobot jarak — penuh hingga 150 km, nol di luar 300 km, dibatasi 0,1–10×. Koreksi lokal dipertahankan 24 jam, lalu perlahan mendekati faktor regional.",
      "Asap kebakaran (garis/sebaran putih) dari model puff kami: emisi dari daya radiasi api (FRP) dengan faktor gambut dan non-gambut, dibawa angin 10 m, melebar, dan tercuci hujan.",
      "Arah asap satu kebakaran (garis putus-putus saat kebakaran dibuka): lintasan 24 jam dari titik tengah kebakaran mengikuti prakiraan angin 10 m, dihitung tiap jam. Kota pertama yang dilewati dalam 30 km disebut di panel.",
      "Lapisan 'Kabut asap teramati satelit': ketebalan aerosol (AOD) harian dari satelit MODIS Terra dan Aqua (NASA GIBS), hari lengkap terbaru (biasanya 2–3 hari lalu; hari terbaru masih diisi NASA). Ini pengamatan, bukan model: kosong di bawah awan dan di celah lintasan satelit.",
      "Lapisan 'Citra satelit terkini': kanal merah tampak satelit Himawari-9 (JMA; resolusi 1 km) lewat NASA GIBS, satu citra tiap 10 menit, ±40 menit setelah dipindai. Awan tampak putih, kabut asap abu-abu di atas tanah yang gelap. Kanal tampak gelap di malam hari, jadi dari 15.30 sampai 06.00 WIB yang ditampilkan citra pukul 15.30 (waktunya tertulis di legenda).",
    ],
    data: ["CAMS via Open-Meteo.", "Stasiun ISPU, DOE Malaysia, NEA Singapura.", "Angin dan hujan: Open-Meteo."],
    tested: [
      "Dalam asap tebal (stasiun di atas 100 µg/m³), CAMS hanya membaca sekitar 35% angka stasiun; koreksi menurunkan galat (uji leave-one-out: tiap stasiun bergantian disisihkan) dari 1,05 ke 0,61 (median galat log absolut).",
      "Model asap vs CAMS (uji satu hari, 17 Okt 2026): CSI rata-rata 0,41 (0,25–0,52) hingga 72 jam ke depan.",
      "Model asap vs kabut asap teramati satelit (AOD MODIS ≥ 1, 96 hari Jul–Okt 2026, Sumatra–Kalimantan): AUC 0,86–0,87 untuk 6 dan 30 jam ke depan, dibanding 0,74 bila angin dimatikan, jadi arah angin memang menambah ketepatan. Kabut asap teramati kemarin saja mencapai AUC 0,93: kabut bertahan lama, jadi peta kabut asap memakai CAMS yang memadukan pengamatan satelit, dan model asap dipakai untuk ke mana asap baru bergerak.",
      "Parameter model asap disetel ulang pada Jul–Agu 2026 lalu diuji pada Sep–Okt: setelan baru tidak lebih tepat (AUC 0,810 vs 0,811), jadi model tetap memakai nilai dari literatur.",
      "Garis asap sebuah kebakaran: diuji pada 2.038 kebakaran Jul–Okt 2026 terhadap angin reanalisis ERA5. Setelah 24 jam (asap menempuh median 193 km), ujung garis meleset median 33 km dengan prakiraan terbaru dan 43 km dengan prakiraan sehari lebih tua; arah yang disebut tepat pada 73–80% kasus dan meleset paling banyak satu arah mata angin pada 97–99% kasus. Menganggap angin tetap seperti sekarang: meleset 121 km.",
    ],
    limits: ["Jauh dari stasiun, peta kembali ke CAMS yang cenderung terlalu rendah di kabut asap gambut.", "Lapisan satelit: asap yang sangat tebal sering dianggap awan oleh algoritme MODIS dan tampak kosong, justru di tempat kabut asap terparah; kotak kosong bukan berarti udara bersih."],
  },
  stations: {
    title: "Stasiun pemantau udara",
    what: "Hasil ukur PM2,5 terbaru dari stasiun.",
    how: [
      "ISPU (KLH): rata-rata bergerak 24 jam. Bacaan yang dikecualikan KLH, dan PM2,5 yang lebih tinggi dari PM10 (kesalahan alat), tidak ditampilkan.",
      "Malaysia (DOE): PM2,5 diperkirakan dari indeks API 24 jam (≈).",
      "Singapura (NEA): rata-rata per jam.",
    ],
    data: ["ISPU (KLH), DOE Malaysia APIMS, NEA Singapura."],
    limits: ["Dalam asap sangat tebal alat ukur bisa meleset ±30–50%.", "Kategori bisa berbeda dari kategori resmi di ispu.kemenlh.go.id."],
  },
  cities: {
    title: "Prakiraan kota",
    what: "Rata-rata PM2,5 harian untuk 3 hari ke depan per kota, dan kapan asap kebakaran tiba.",
    how: [
      "Rata-rata 24 jam dari peta kabut asap terkoreksi di titik kota.",
      "Hari pertama ditampilkan sebagai kisaran ÷1,7 sampai ×1,7 (galat khas di dekat stasiun); hari ke-2 dan ke-3 hanya kategori.",
      "Asap kebakaran 'tiba' ketika indeks model asap di kota melewati 15.",
    ],
    data: ["Kabut asap (lihat atas)."],
    tested: [
      "Hari pertama: koreksi stasiun diuji dengan meninggalkan satu stasiun (111 stasiun, 17 Okt 2026): 56% dalam ×2 dari angka stasiun, CAMS mentah 29%. Baru diuji satu hari, jadi buktinya masih tipis.",
      "Hari ke-2 dan ke-3 belum teruji. Setiap prakiraan dicatat sejak 17 Okt 2026 dan dinilai terhadap stasiun ISPU; skornya tampil di kartu Saran kesehatan setelah 20 perbandingan.",
    ],
    limits: ["Galat lebih besar jauh dari stasiun.", "Angka di atas 500 ditampilkan '> 500'."],
  },
  transboundary: {
    title: "Asap lintas batas",
    what: "Dari provinsi mana asap kebakaran yang sampai ke tiap kota berasal.",
    how: [
      "Model asap dijalankan mulai 4 hari sebelumnya (spin-up), jadi asap yang sudah dalam perjalanan ikut terhitung; karena modelnya linier, kontribusi tiap sumber api bisa dipisahkan tepat.",
      "Kebakaran di luar Indonesia ikut dimodelkan sebagai sumber.",
      "Pembagian hanya ditampilkan bila asap model cukup (rata-rata ≥ 10) dan menjelaskan ≥ 20% kelebihan PM2,5 terukur; dibulatkan ke 10%.",
    ],
    data: ["Model asap, titik panas, stasiun."],
    tested: [
      "Pembagian per sumber tidak bisa diuji langsung (tidak ada pengukuran asal asap). Yang teruji adalah model asap di baliknya: AUC 0,86–0,87 terhadap kabut asap teramati satelit, 0,74 tanpa angin (lihat 'Kabut asap').",
    ],
    limits: ["Perkiraan model, bukan pengukuran sumber."],
  },
  progression: {
    title: "Perkembangan api",
    what: "Kapan api mencapai tiap bagian area kebakaran: titik awal, garis depan harian, laju perluasan, dan api yang menyebar ke lokasi baru.",
    how: [
      "Waktu tiba tiap sel = deteksi VIIRS pertama dikurangi setengah jeda antar lintasan, dihaluskan (median 5 sel terdekat).",
      "Garis depan digambar tiap pukul 14.00 WIB.",
      "Laju perluasan = jarak majunya garis depan dalam sehari (persentil ke-90); deteksi > 2 km dari garis depan dicatat sebagai api yang menyebar ke lokasi baru (2–10 km), tidak dihitung dalam laju perluasan. Arahnya diukur dari sel terbakar terdekat sebelumnya ke tempat api muncul; itu asal yang paling mungkin, bukan yang pasti (bara bisa terbawa dari tempat lain).",
    ],
    data: ["Titik panas VIIRS."],
    tested: ["Diuji pada kebakaran 2019/2023; ketepatan waktu ditampilkan di catatan tiap kebakaran."],
    limits: ["Resolusi 375 m dan jeda lintasan membuat garis depan kasar; awan bisa menyembunyikan perluasan."],
  },
  spread: {
    title: "Prakiraan sebaran api (uji coba)",
    what: "Peluang api mencapai lahan baru dalam +24/+48/+72 jam untuk 40 kebakaran paling aktif.",
    how: ["Simulasi sel dengan pengaruh angin dan hujan prakiraan; garis = peluang 20% / 40% / 60%."],
    data: ["Titik panas, angin dan hujan Open-Meteo."],
    tested: [
      "Dikalibrasi pada 2019, diuji pada 2023 (142 kebakaran-hari, angin dan hujan dari NASA POWER/MERRA-2): presisi rata-rata (AP) 0,108 berbanding 0,053 bila api dianggap tetap di tempatnya; tanpa data cuaca 0,100.",
      "Sebagai peta ya/tidak hampir setara dengan menganggap api tetap (CSI 0,13 berbanding 0,126): sebagian besar titik baru adalah penyalaan baru di dalam atau dekat api yang ada.",
    ],
    limits: ["Masih uji coba; jangan dipakai untuk keputusan evakuasi."],
  },
  history: {
    title: "Riwayat sejak 1 Juli",
    what: "Titik panas dan PM2,5 harian untuk diputar ulang.",
    how: ["Titik panas per hari (WIB) diringkas per sel.", "PM2,5 harian dari CAMS tanpa koreksi stasiun (riwayat stasiun tidak tersedia)."],
    data: ["NASA FIRMS, CAMS."],
    limits: ["Kabut asap gambut kemungkinan lebih pekat daripada yang terlihat."],
  },
  compare: {
    title: "Indonesia vs Asia Tenggara",
    what: "Jumlah titik panas per negara Asia Tenggara dari satu satelit yang sama, untuk 7 hari terakhir dan untuk setiap tahun 2012–2025.",
    how: [
      "Hanya satelit VIIRS S-NPP (piksel 375 m), yang mengorbit sejak 2012. Satu satelit untuk semua tahun dan negara, supaya satelit yang lebih baru (NOAA-20, NOAA-21) tidak menggelembungkan tahun-tahun terakhir.",
      "2012–2025: arsip tahunan per negara dari NASA FIRMS (pemrosesan standar). Hanya deteksi yang diduga kebakaran vegetasi (tipe 0: gunung api, sumber panas tetap, dan lepas pantai dibuang) dengan kepercayaan sedang atau tinggi. Negaranya ditentukan oleh FIRMS.",
      "7 hari terakhir: berkas S-NPP Asia Tenggara 7 hari dari FIRMS (hampir real-time, NRT). Berkas ini tidak punya tanda tipe, jadi sumber panas tetap (suar gas, smelter, gunung api) dibuang dengan daftar yang sama seperti peta ini; hasilnya 94–100% dari hitungan tipe 0 pada data 2025. Titik dipetakan ke negara dengan batas Natural Earth (titik ≤ 3 km dari pantai ikut negara terdekat).",
      "Per 1.000 km²: jumlah titik panas dibagi luas daratan (Bank Dunia, 2024), supaya negara besar dan kecil bisa dibandingkan.",
      "Tahun ini untuk Indonesia: titik panas S-NPP sejak 1 Januari dari basis data peta ini, disaring dengan cara yang sama. Negara lain belum punya sumber tahun berjalan yang setara tanpa kunci API, jadi tidak dibandingkan.",
      "Papua Nugini ditampilkan sebagai tetangga (satu pulau dengan Papua) tetapi tidak ikut diperingkat.",
    ],
    data: [
      "NASA FIRMS: arsip negara VIIRS S-NPP 2012–2025 dan berkas NRT Asia Tenggara 7 hari.",
      "Natural Earth 10m (batas negara, disederhanakan); Bank Dunia AG.LND.TOTL.K2 (luas daratan).",
    ],
    tested: [
      "Jumlah sel 375 m terbakar Indonesia per tahun sama persis dengan arsip yang dipakai lapisan 'Pernah terbakar' (14 dari 14 tahun).",
      "Pada titik 2025, penentuan negara dengan batas kami cocok 99,8–100% dengan penentuan FIRMS sendiri.",
    ],
    limits: [
      "Titik panas bukan luas terbakar: satu kebakaran besar menghasilkan ribuan titik, banyak api kecil bisa tidak terdeteksi.",
      "Jenis api berbeda: negara daratan (Myanmar, Laos, Kamboja, Thailand) terbakar terutama Feb–Apr, sebagian besar pembakaran sisa panen yang singkat; Indonesia Agu–Okt, sering di gambut yang membara lama dan menghasilkan asap paling banyak.",
      "Satelit melintas sekitar pukul 13.30 dan 01.30 waktu setempat: api yang menyala dan padam di antaranya terlewat. Awan dan asap tebal menutupi api.",
      "Perbandingan 7 hari mencerminkan musim: pada Oktober Indonesia sedang puncak, negara daratan tidak. Untuk perbandingan adil, lihat per tahun.",
    ],
  },
  place: {
    title: "Cek lokasimu",
    what: "Ringkasan untuk satu titik: prakiraan udara, risiko kebakaran hari ini, riwayat terbakar, kebakaran aktif di sekitar, dan dari arah mana udara datang.",
    how: [
      "Lokasi dibaca dari GPS perangkat (hanya di browser, tidak dikirim atau disimpan), dari titik yang diketuk di peta, atau dari titik tengah kabupaten/kota yang dicari.",
      "Udara: PM2,5 dari prakiraan CAMS yang disesuaikan dengan stasiun (lapisan Kabut asap), diambil di titik ini, dirata-rata per hari WIB. Hanya hari yang tercakup penuh oleh prakiraan. Kategori dan saran mengikuti ISPU dan Kemenkes, sama seperti kartu Saran kesehatan.",
      "Arah datangnya udara: udara yang akan tiba di titik ini 24 jam lagi dilacak mundur 24 jam melalui prakiraan angin 10 m (Open-Meteo), langkah per jam (metode titik tengah). Arah = dari titik ini ke ujung lintasan.",
      "Kebakaran di jalur angin: kebakaran aktif yang berjarak ≤ 25 km dari lintasan itu. Asapnya kemungkinan terbawa ke titik ini.",
      "Kebakaran di sekitar: kebakaran aktif (bukan 'tak terlihat 1–3 hari') dalam 100 km, dengan jarak dan arah dari titik ini.",
      "Risiko kebakaran: prakiraan hari pertama (biasanya hari ini, tanggalnya ditampilkan), nilai sel model risiko (±25 km) yang memuat titik ini. Riwayat terbakar: jumlah tahun 2012–2025 dengan titik panas S-NPP di sel 1 km ini.",
    ],
    data: ["Semua data sama dengan yang tampil di peta; tidak ada data tambahan yang diambil untuk titik ini."],
    tested: [
      "Kualitas udara: lihat 'Prakiraan kota'. Jalur udara yang tiba: angin yang sama dengan garis asap kebakaran, yang meleset median 33–43 km setelah 24 jam (lihat 'Kabut asap'). Risiko kebakaran: lihat 'Risiko kebakaran'.",
    ],
    limits: [
      "Grid prakiraan kasar (PM2,5 ±80 km, angin ±160 km): nilai di satu titik adalah rata-rata wilayah sekitarnya, bukan kondisi di halaman rumah.",
      "Lintasan angin dari model, bisa meleset terutama saat angin lemah atau berubah arah; angin 10 m tidak mewakili asap yang naik tinggi.",
      "Kebakaran yang tertutup awan/asap atau terlalu kecil tidak terdeteksi satelit, jadi 'tidak ada kebakaran' bukan jaminan.",
    ],
  },
};

const en: Methods = {
  hotspots: {
    title: "Hotspots",
    what: "One hotspot = one satellite pixel that saw heat well above its surroundings on one overpass.",
    how: [
      "Detections from NASA FIRMS: VIIRS (S-NPP, NOAA-20, NOAA-21; 375 m pixels) and MODIS (Terra, Aqua; 1 km pixels), near real time.",
      "Plus DEA Hotspots (Geoscience Australia): the same VIIRS detections from direct-readout stations, online ~1 h after a pass where FIRMS takes 2–4 h and sometimes misses passes. DEA only stands in: once FIRMS delivers the same pass, DEA's detections for it are deleted and FIRMS's used. DEA's processing flags a few extra pixels at fire edges, so without this rule 2026 would count higher than the FIRMS-only 2012–2025 baselines.",
      "Shown: only on Indonesian land or near its coast, at nominal or high confidence (MODIS ≥ 30%).",
      "Persistent heat sources are removed: cells hot in ≥ 6 different months of a year, or flagged by FIRMS as volcano, industrial or offshore, plus 750 m around them (power plants, refineries, smelters, gas flares).",
      "Updated every 2 hours. Satellites pass over Indonesia some 10–12 times a day, with gaps in between.",
    ],
    data: ["NASA FIRMS (area API, or the keyless Southeast Asia 7-day files).", "DEA Hotspots, Geoscience Australia (CC BY 4.0).", "Persistent heat-source list: derived from the FIRMS archives 2019–2026."],
    limits: [
      "One fire can produce many hotspots, and one hotspot is not necessarily a fire (sun glint, hot roofs).",
      "Cloud and thick smoke hide fires; small fires and smouldering peat are often missed.",
      "Pixel positions can shift by up to a pixel between overpasses.",
    ],
  },
  events: {
    title: "Fires (grouping hotspots)",
    what: "Hotspots close in space and time are joined into one 'fire' that can be followed day by day.",
    how: [
      "A fire is named after the desa (village) holding most of its hotspots, then the regency (BPS/OCHA village borders). The nearest town is listed separately in the panel.",
      "Two hotspots belong to one fire if they are ≤ 1.5 km and ≤ 48 h apart (chained: A–B and B–C make A, B, C one fire).",
      "Status: active if detected in the last 24 h; 'not seen 1–3 days' if last detected 24–72 h ago; 'not seen 3+ days' after that.",
      "Evidence is 'strong' with ≥ 2 overpasses, ≥ 2 pixels in one pass, a night detection, or a saturated VIIRS pixel. Headline counts use strong fires only.",
      "Province and kabupaten: the province with most hotspots, then the kabupaten with most hotspots inside that province.",
      "Peat: ≥ 50% of its hotspots inside a peat hydrological unit (KHG 2017).",
    ],
    data: ["Hotspots (above).", "Boundaries: 38 provinces. Regencies from geoBoundaries (BPS 2020); the regencies of Papua and Papua Barat are regrouped into Papua Selatan, Papua Tengah, Papua Pegunungan (Laws 14–16/2022) and Papua Barat Daya (Law 29/2022). No regency has been created since 2020, so the lines match the official map.", "KHG 2017 (KLHK)."],
    tested: [
      "The 1.5 km / 48 h rule was chosen by reviewing 2019 and 2023 fires (docs/clustering-evaluation.md).",
      "'Not seen' is not the same as out. Of 71,172 fires in Jul–Sep 2026, the same spot (~1.6 km cell) was detected again within 7 days for 33% of non-peat and 43% of peat fires not seen for 1 day, and for 31% / 39% of those not seen for 3 days (46% / 55% within 14 days). That is why the status says 'not seen', not 'out'.",
    ],
    limits: ["Two separate fires close together can merge; one fire hidden by cloud for days can split."],
  },
  counts: {
    title: "Hotspot counts and active fires",
    what: "Hotspots in the last 24 h in three versions, and the number of active fires.",
    how: [
      "Our count: every hotspot shown (5 satellites, nominal–high confidence).",
      "SiPongi-comparable: Terra, Aqua, S-NPP and NOAA-20 only (no NOAA-21), all confidence levels — to compare with the ministry's figure.",
      "High confidence only: VIIRS/MODIS high-confidence detections.",
      "The season chart uses S-NPP only: NOAA-20 (2018) and NOAA-21 (2023) inflate raw counts, and one satellite keeps years comparable.",
    ],
    data: ["NASA FIRMS."],
    limits: ["Hotspot counts are neither burned area nor number of fires; one large fire can produce thousands."],
  },
  area: {
    title: "Burned-area estimate",
    what: "A range for the area burned this season, from satellite fire pixels, checked against satellite imagery.",
    how: [
      "For each VIIRS satellite, count the unique 375 m cells with a hotspot this season (once per season, not per fire).",
      "Average across the satellites flying that season, so new satellites do not inflate the number.",
      "Multiply by 14.06 ha per cell and a factor k. k = 0.49 is fitted to KLHK's official 2019 & 2023 totals (low end); k = 0.90 to an independent Sentinel-2 burned-area map of 2019 (Gaveau et al. 2021, high end).",
      "Independent check for Central Kalimantan: 700 stratified random sample points, each labelled burned/unburned on Sentinel-1, Sentinel-2 and Landsat imagery, with a sample-based area estimator (Olofsson/Stehman) and a 95% interval.",
      "A fire's 'detected area' = its unique 375 m cells × 14.06 ha: an upper bound, not measured burned area.",
    ],
    data: ["NASA FIRMS VIIRS.", "SiPongi official figures (Ministry of Forestry), fetched automatically.", "Gaveau et al. 2021, ESSD 13:5353.", "Sentinel-1/2 (Copernicus), Landsat (USGS) imagery."],
    tested: ["KLHK calibration: k from 2019 predicts 2023 (and vice versa) within ±4%.", "Central Kalimantan 2026 sample (provisional): ≈664k ha (95%: 374k–1.06M)."],
    limits: ["Province estimates can be off by up to 2×.", "Small fires and fires under cloud are missed; detected pixels do not burn whole."],
  },
  danger: {
    title: "Fire danger (model)",
    what: "The chance of at least one hotspot on a given day in a ~25 km cell (forecast for today and the days ahead).",
    how: [
      "Canadian fire-weather codes (FFMC, DMC, DC, ISI) — the system behind BMKG's SPARTAN — from NASA GFWED (GEOS-5).",
      "NASA publishes GFWED days late, so the first day of its newest run is brought forward one day at a time with the Canadian FWI equations and current ECMWF weather (local-noon temperature, humidity and wind, rain in the 24 h before), to 7 days ahead. The forecast is issued today; if the ECMWF weather can't be fetched, GFWED's own forecast is used as issued.",
      "Forecast values are quantile-mapped onto the MERRA-2 training data.",
      "A logistic regression uses the codes, peat share and hotspots in the last 1, 7 and 30 days (in Indonesia almost every fire is lit by people, so where it burned recently matters a lot).",
      "Classes in BMKG colours: Low < 5%, Moderate 5–15%, High 15–40%, Extreme ≥ 40%.",
      "Province shares = share of the province's cells at Extreme, and at High (two separate columns).",
    ],
    data: ["NASA GFWED (GEOS-5 forecasts; MERRA-2 for training).", "ECMWF IFS weather via Open-Meteo.", "KHG 2017.", "VIIRS hotspots."],
    tested: [
      "Trained on 2019, tested on the 2023 season with real GEOS-5 forecasts: AUC 0.90 next day.",
      "In cells with no fire in the past 7 days: AUC 0.82 (DC alone: 0.78).",
      "'Extreme' cells burned the next day 65% of the time; 'Low' cells 1.5%.",
      "Tested again on Jul–Sep 2026 (not used for fitting), with weather forecast 1, 3, 5 and 7 days ahead: AUC 0.894 / 0.892 / 0.889 / 0.885; 'Extreme' cells burned 73% of the time, 'Low' cells 2–3%. NASA publishing its runs late costs almost nothing.",
      "For comparison, the count of hotspots in the last 7 days alone reaches AUC 0.866: weather adds skill, but most of the signal is where it burned recently.",
    ],
    limits: ["A statistical model, not BMKG's official rating.", "25 km cells are too coarse for villages; see 'Villages at risk'."],
  },
  outlook: {
    title: "Seasonal outlook",
    what: "The climate state that decides how long and dry the fire season gets.",
    how: [
      "ENSO from NOAA's ONI (3-month Niño3.4 sea-surface anomaly): ≥ 2.0 °C very strong El Niño, ≥ 1.5 strong, ≥ 0.5 El Niño, ≤ −0.5 La Niña.",
      "Weekly Indian Ocean Dipole from the Australian Bureau of Meteorology; ≥ 0.4 °C counts as positive (drier over Sumatra and Kalimantan).",
      "Chance of staying dry = share of the 51 ECMWF seasonal ensemble members whose mean rain stays < 4 mm/day over the next 30 or 60 days; below that, fire rises sharply (Field et al. 2016).",
    ],
    data: ["NOAA CPC (ONI, weekly Niño3.4).", "Bureau of Meteorology (IOD).", "ECMWF SEAS5 via Open-Meteo."],
    tested: [
      "The < 4 mm/day rule, tested on 2012–2025: 896 thirty-day windows (Jul–Oct) at the 8 points, rain from NASA POWER, VIIRS S-NPP detections within ±1° (~110 km). Dry windows: median 1,388 detections; wet: 178 (≈ 8×). 78% of the biggest fire windows (top 10%) were dry.",
      "The rule is weaker in West Kalimantan and Riau (42% and 50% of the biggest fire windows were dry) and says little at Merauke, which is dry nearly all season.",
      "ECMWF's rain forecast skill itself is not re-tested here (ensemble hindcasts are not freely available); see ECMWF's own verification.",
    ],
    limits: ["One point per province (capital or fire belt), not the whole province.", "The official seasonal outlook is BMKG's."],
  },
  repeat: {
    title: "Burning again (fire history)",
    what: "The share of this season's hotspots on land that already burned in 2012–2025.",
    how: [
      "History from the VIIRS S-NPP archives 2012–2025 — one satellite for every year, to be fair — vegetation fires only (type 0), nominal–high confidence, summarised per 375 m cell.",
      "This season's S-NPP hotspots are matched to the same cells.",
      "Lift = share of hotspots on land that burned before ÷ share of Indonesia's land that burned before.",
      "The map layer shows fire years per ~1 km cell.",
    ],
    data: ["NASA FIRMS VIIRS S-NPP yearly archives."],
    tested: ["2023 hindcast: 52% of 2023 hotspots fell on the 10% of land that burned in 2012–2022 (5.1× lift)."],
    limits: ["Fire pixels, not measured burned area.", "'Same cell' is a strict test; pixel positions shift between years, so the shares lean low."],
  },
  desa: {
    title: "Villages at risk",
    what: "Two lists of villages to prioritise for patrols and prevention, each with a measured hit rate.",
    how: [
      "Village boundaries (81,912 desa/kelurahan) are mapped onto a ~1 km grid; each hotspot goes to the village it falls in.",
      "List 1: villages with hotspots in the last 7 days.",
      "List 2: villages with no hotspot this week, where part of the village burned in ≥ 3 different years since 2012.",
      "Each row carries the fire danger for the date in the column heading and the 2 days after (highest model value over the village) and the peat share.",
    ],
    data: ["OCHA/BPS COD-AB village boundaries (CC BY-IGO).", "VIIRS hotspots, 2012–2025 history, the danger model."],
    tested: [
      "2023 hindcast (weekly): list-1 villages burned again the next week 39% of the time; list-2 villages 11.6%; all villages without fire 2.2%; villages that never burned 0.1%.",
      "Village assignment: a hotspot lands in the right village 93% of the time and the right district 98% (against the exact polygons).",
    ],
    limits: ["Villages next to a boundary can swap with a neighbour.", "Not an official designation."],
  },
  alerts: {
    title: "Alerts",
    what: "Notable events of the last 7 days, also as RSS/Atom feeds per province.",
    how: [
      "New fire: ≥ 10 hotspots in its first 48 h on peat, ≥ 20 elsewhere (national feed: 20 / 50).",
      "Spreading: ≥ 50 new 375 m pixels in one day.",
      "Extreme danger: provinces with ≥ 25% of their land at Extreme on the first forecast day (usually today; the alert names the date) (national feed: one daily digest).",
      "Air: cities whose forecast 24 h mean PM2.5 is Unhealthy or worse.",
      "Recomputed every 2 hours; each alert has a stable id, so feed readers show it once.",
    ],
    data: ["Everything above."],
    tested: [
      "Alerts are not tested on their own; each inherits its source's test: new and growing fires are satellite detection counts, extreme danger comes from the fire danger model (see 'Fire danger'), air from the city forecast (see 'City forecast').",
    ],
    limits: ["Automatic; not an official government warning."],
  },
  health: {
    title: "Health advice",
    what: "Advice for schools and the public from the forecast ISPU category for the next 24 hours.",
    how: [
      "Category from the forecast 24 h mean PM2.5 (station-adjusted), with the ISPU breakpoints of regulation P.14/2020: 15.5 / 55.4 / 150.4 / 250.4 µg/m³.",
      "School advice follows Mendikdasmen circular No. 20/2026; public advice follows the Ministry of Health (26 Aug 2026).",
      "Every forecast is logged and, once its day has passed, scored against ISPU stations within 25 km, next to a 'just use today's value' baseline.",
    ],
    data: ["PM2.5 forecast (see 'Haze').", "ISPU stations (KLH)."],
    tested: [
      "No category score yet: ISPU station history is not freely available, so testing runs forward from 17 Oct 2026. The score (right category, within one category, and the 'today's value only' comparison) shows in the card after 20 comparisons.",
      "Already tested: the day-1 station correction (see 'City forecast').",
    ],
    limits: ["Can be one category off.", "School decisions belong to the education office, based on the official daily ISPU."],
  },
  haze: {
    title: "Haze (PM2.5)",
    what: "PM2.5 concentration now and up to 72 hours ahead.",
    how: [
      "CAMS (Copernicus) global forecast, 0.75° grid, all pollution sources.",
      "Corrected with stations: the station/CAMS log ratio is spread by inverse distance — full up to 150 km, none beyond 300 km, clipped to 0.1–10×. The local correction is held for 24 h, then relaxes towards the regional factor.",
      "Fire smoke (white plumes) comes from our puff model: emissions from fire radiative power (FRP) with peat and non-peat factors, carried by 10 m wind, spreading and washed out by rain.",
      "One fire's smoke direction (dashed line when a fire is opened): a 24-hour path from the fire's centre through the 10 m wind forecast, stepped hourly. The first town it passes within 30 km is named in the panel.",
      "The 'Haze seen by satellite' layer: daily aerosol optical depth (AOD) from the MODIS Terra and Aqua satellites (NASA GIBS), the newest complete day (usually 2–3 days ago; NASA is still filling in the newest). An observation, not a model: blank under cloud and between satellite swaths.",
      "The 'Latest satellite image' layer: the Himawari-9 (JMA) red visible band at 1 km via NASA GIBS, a frame every 10 minutes, ~40 minutes after the scan. Clouds look white, haze grey over dark ground. The visible band is dark at night, so from 15:30 to 06:00 WIB it shows the 15:30 frame (its time is in the legend).",
    ],
    data: ["CAMS via Open-Meteo.", "ISPU, Malaysia DOE and Singapore NEA stations.", "Wind and rain: Open-Meteo."],
    tested: [
      "In thick haze (stations above 100 µg/m³) CAMS reads about 35% of the station value; the correction cuts the leave-one-station-out error from 1.05 to 0.61 (median absolute log error).",
      "Smoke model vs CAMS (one-day test, 17 Oct 2026): mean CSI 0.41 (0.25–0.52) out to 72 h.",
      "Smoke model vs satellite-observed haze (MODIS AOD ≥ 1, 96 days Jul–Oct 2026, Sumatra–Kalimantan): AUC 0.86–0.87 at 6 and 30 h ahead, against 0.74 with the wind off, so transport adds real skill. Yesterday's observed haze alone reaches 0.93: haze lingers, which is why the haze map uses CAMS (which folds in satellite observations) and the smoke model is used for where new smoke goes.",
      "The smoke model's parameters were re-tuned on Jul–Aug 2026 and tested on Sep–Oct: the tuned setting did no better (AUC 0.810 vs 0.811), so the model keeps the literature values.",
      "A fire's smoke path: tested on 2,038 fires, Jul–Oct 2026, against ERA5 reanalysis wind. After 24 h (the smoke travelled a median 193 km), the end of the line was a median 33 km off with the newest forecast and 43 km with a day-older one; the named direction was exactly right 73–80% of the time and at most one compass point off 97–99%. Assuming the wind stays as it is now: 121 km off.",
    ],
    limits: ["Far from stations the map falls back to CAMS, which runs low in peat haze.", "Satellite layer: very thick smoke is often flagged as cloud by the MODIS algorithm and shows blank, exactly where haze is worst; a blank cell does not mean clean air."],
  },
  stations: {
    title: "Air monitoring stations",
    what: "Latest measured PM2.5 from stations.",
    how: [
      "ISPU (KLH): 24 h running mean. Readings KLH excludes, and PM2.5 above PM10 (an instrument fault), are not shown.",
      "Malaysia (DOE): PM2.5 estimated from the 24 h API index (≈).",
      "Singapore (NEA): hourly.",
    ],
    data: ["ISPU (KLH), Malaysia DOE APIMS, Singapore NEA."],
    limits: ["In very thick smoke monitors can be off by ±30–50%.", "Categories may differ from the official category at ispu.kemenlh.go.id."],
  },
  cities: {
    title: "City forecast",
    what: "Daily-mean PM2.5 for the next 3 days per city, and when fire smoke arrives.",
    how: [
      "24 h means of the corrected haze map at the city.",
      "Day 1 is shown as a range ÷1.7 to ×1.7 (typical error near stations); days 2 and 3 as categories only.",
      "Fire smoke 'arrives' when the smoke-model index at the city passes 15.",
    ],
    data: ["Haze (above)."],
    tested: [
      "Day 1: the station correction was tested leaving one station out (111 stations, 17 Oct 2026): 56% within ×2 of the station value, raw CAMS 29%. One day only, so still thin.",
      "Days 2 and 3 are not tested yet. Every forecast has been logged since 17 Oct 2026 and is scored against ISPU stations; the score shows in the Health advice card after 20 comparisons.",
    ],
    limits: ["Errors are larger far from stations.", "Values above 500 are shown as '> 500'."],
  },
  transboundary: {
    title: "Cross-border smoke",
    what: "Which provinces the fire smoke reaching each city comes from.",
    how: [
      "The smoke model runs with a 4-day spin-up; because it is linear, each fire source's contribution separates exactly.",
      "Fires outside Indonesia are modelled as sources too.",
      "Shares are shown only where modelled smoke is substantial (mean ≥ 10) and explains ≥ 20% of the measured excess PM2.5; rounded to 10%.",
    ],
    data: ["Smoke model, hotspots, stations."],
    tested: [
      "The split by source cannot be tested directly (nothing measures where smoke came from). What is tested is the smoke model behind it: AUC 0.86–0.87 against satellite-observed haze, 0.74 without wind (see 'Haze').",
    ],
    limits: ["A model estimate, not a source measurement."],
  },
  progression: {
    title: "Fire progression",
    what: "When the fire reached each part of its area: ignition, daily fronts, rate of spread and spread to new spots.",
    how: [
      "Arrival time per cell = first VIIRS detection minus half the gap between overpasses, smoothed (median of the 5 nearest cells).",
      "Fronts are drawn at 14:00 WIB each day.",
      "Rate of spread = how far the front advanced in a day (90th percentile); detections > 2 km beyond the front are listed as fire spreading to a new spot (2–10 km), not counted in the rate of spread. Its direction runs from the nearest cell that burned before it to where the fire appeared: the most likely origin, not a certain one (embers can travel from elsewhere).",
    ],
    data: ["VIIRS hotspots."],
    tested: ["Tested on 2019/2023 fires; timing accuracy is shown in each fire's note."],
    limits: ["375 m pixels and overpass gaps make fronts coarse; cloud can hide spread."],
  },
  spread: {
    title: "Spread forecast (experimental)",
    what: "The chance fire reaches new ground in +24/+48/+72 h, for the 40 most active fires.",
    how: ["A cell simulation driven by forecast wind and rain; lines = 20% / 40% / 60% chance."],
    data: ["Hotspots, Open-Meteo wind and rain."],
    tested: [
      "Calibrated on 2019, tested on 2023 (142 fire-days, wind and rain from NASA POWER/MERRA-2): average precision 0.108 against 0.053 for assuming the fire stays where it is; 0.100 without weather.",
      "As a yes/no map it about ties assuming the fire stays put (CSI 0.13 vs 0.126): most new detections are new ignitions inside or near the existing fire.",
    ],
    limits: ["Experimental; do not use for evacuation decisions."],
  },
  history: {
    title: "History since 1 July",
    what: "Daily hotspots and PM2.5 to play back.",
    how: ["Hotspots per WIB day summarised per cell.", "Daily PM2.5 from CAMS without station correction (no station history exists)."],
    data: ["NASA FIRMS, CAMS."],
    limits: ["Peat haze probably looked thicker than shown."],
  },
  compare: {
    title: "Indonesia vs Southeast Asia",
    what: "Hotspot counts per Southeast Asian country from one and the same satellite, for the last 7 days and for every year 2012–2025.",
    how: [
      "VIIRS S-NPP only (375 m pixels), in orbit since 2012. One satellite for every year and country, so newer satellites (NOAA-20, NOAA-21) do not inflate recent years.",
      "2012–2025: NASA FIRMS yearly country archives (standard processing). Only presumed vegetation fires (type 0: volcanoes, static heat sources and offshore removed) with nominal or high confidence. FIRMS assigns the country.",
      "Last 7 days: the FIRMS S-NPP Southeast Asia 7-day file (near real time). It has no type flag, so static heat sources (gas flares, smelters, volcanoes) are removed with the same list this map uses; on 2025 data this gives 94–100% of the type 0 count. Points are assigned to countries with Natural Earth borders (points within 3 km of a coast go to the nearest country).",
      "Per 1,000 km²: hotspots divided by land area (World Bank, 2024), so large and small countries compare.",
      "This year for Indonesia: S-NPP hotspots since 1 January from this map's database, filtered the same way. Other countries have no equivalent keyless year-to-date source, so they are not compared.",
      "Papua New Guinea is shown as a neighbour (it shares the island of New Guinea) but is not ranked.",
    ],
    data: [
      "NASA FIRMS: VIIRS S-NPP country archives 2012–2025 and the Southeast Asia 7-day NRT file.",
      "Natural Earth 10m (country borders, simplified); World Bank AG.LND.TOTL.K2 (land area).",
    ],
    tested: [
      "Indonesia's burned 375 m cells per year match the archive behind the 'Burned before' layer exactly (14 of 14 years).",
      "On 2025 points, country assignment with our borders agrees 99.8–100% with FIRMS' own.",
    ],
    limits: [
      "Hotspots are not burned area: one large fire makes thousands, many small fires go undetected.",
      "Fires differ: mainland countries (Myanmar, Laos, Cambodia, Thailand) burn mostly Feb–Apr, largely short crop-residue fires; Indonesia Aug–Oct, often in peat that smoulders for long and makes the most smoke.",
      "The satellite passes around 13:30 and 01:30 local time: fires that start and end in between are missed. Cloud and thick smoke hide fires.",
      "The 7-day comparison reflects the season: in October Indonesia is at its peak and the mainland is not. For a fair comparison, use the yearly view.",
    ],
  },
  place: {
    title: "Check your location",
    what: "A summary for one point: air forecast, today's fire danger, burning history, active fires nearby, and which way the air comes from.",
    how: [
      "The location comes from your device's GPS (read in the browser only, never sent or stored), from a point tapped on the map, or from the centre of a searched regency/city.",
      "Air: PM2.5 from the station-adjusted CAMS forecast (the Haze layer) at this point, averaged per WIB day. Only days the forecast fully covers. Categories and advice follow ISPU and the Ministry of Health, as in the Health advice card.",
      "Where the air comes from: the air reaching this point 24 hours from now is traced back 24 hours through the 10 m wind forecast (Open-Meteo), stepped hourly (midpoint method). Direction = from this point to the far end of the path.",
      "Fires on the wind path: active fires within 25 km of that path. Their smoke is likely carried here.",
      "Fires nearby: active fires (not 'not seen 1–3 days') within 100 km, with distance and direction from this point.",
      "Fire danger: the first forecast day (usually today, date shown), the danger model's cell (±25 km) containing this point. Burning history: years 2012–2025 with S-NPP hotspots in this 1 km cell.",
    ],
    data: ["Everything comes from the data already on the map; nothing extra is fetched for this point."],
    tested: [
      "Air quality: see 'City forecast'. Path of the arriving air: the same wind as a fire's smoke path, a median 33–43 km off after 24 h (see 'Haze'). Fire danger: see 'Fire danger'.",
    ],
    limits: [
      "Forecast grids are coarse (PM2.5 ±80 km, wind ±160 km): a value at one point is the area's average, not conditions in your yard.",
      "Wind paths come from a model and can be wrong, especially in light or shifting winds; 10 m wind does not represent smoke lofted high.",
      "Fires under cloud or smoke, or too small, are not detected, so 'no fires' is not a guarantee.",
    ],
  },
};

export const METHODS: Record<Lang, Methods> = { id, en };
