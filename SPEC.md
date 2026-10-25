# SIPETA — Spesifikasi Frontend (Tahap 1: tampilan saja, tanpa backend)

> Brief untuk Claude Code. Baca seluruhnya sebelum menulis kode.

## 0. Cara memakai dokumen ini

- **Wireframe (PDF terlampir)** = sumber utama **tata letak**: sidebar, kartu, tab, posisi field.
- **Dokumen ini** = sumber utama **isi, perilaku, dan hak akses**.
- Penanda: ✅ ada di wireframe · ➕ tambahan hasil diskusi (belum ada di wireframe, tetap harus dibuat).
- Jika bertentangan: tata letak ikut wireframe, hal teknis ikut dokumen ini (contoh: satuan "km" di wireframe menjadi **km²**).
- Halaman **"Prapemrosesan"** di wireframe adalah frame kosong dan tidak ada di sidebar → **jangan dibuat**. Prapemrosesan berjalan di dalam proses latih/klasifikasi, bukan modul UI.
- Untuk keputusan besar yang tidak dicakup dokumen ini, tanyakan dulu. Untuk hal kecil, pilih default yang masuk akal dan catat di `NOTES.md`.

---

## 1. Gambaran sistem

**SIPETA** (Sistem Pemantauan Tutupan Lahan Terbangun) adalah aplikasi web skripsi. Sistem menghitung luas **lahan terbangun** dan **nonterbangun** dari citra satelit Sentinel-2 di tiga wilayah, dengan hasil sampai tingkat **kecamatan**:

- Kota Tangerang
- Kota Tangerang Selatan
- Kabupaten Tangerang

Empat fungsi utama:

| Modul       | Algoritma     | Fungsi                                                                   |
| ----------- | ------------- | ------------------------------------------------------------------------ |
| Klasifikasi | Random Forest | Latih model, lalu klasifikasi 1 citra menjadi terbangun/nonterbangun     |
| Prediksi    | ConvLSTM      | Latih model, lalu prediksi lahan terbangun tahun berikutnya              |
| Pemantauan  | -             | Bandingkan hasil klasifikasi antar tanggal (luas, peta, grafik, riwayat) |
| Informasi   | -             | Beranda, Panduan Pengguna, Tentang Penulis                               |

### Cakupan tahap 1

| Dikerjakan                                         | Tidak dikerjakan                         |
| -------------------------------------------------- | ---------------------------------------- |
| Semua halaman dan navigasi antar halaman           | Backend / FastAPI                        |
| Login, register, peran, pembatasan menu            | Database sungguhan                       |
| Form, validasi sisi tampilan, dialog               | Model ML dan pengolahan raster sungguhan |
| Hasil dan progres **tiruan** (mock) yang konsisten | Unggah berkas sungguhan ke server        |
|                                                    | Deployment                               |

Tampilkan lencana kecil **"Mode demo — data tiruan"** di sidebar agar tidak ada yang mengira hasilnya nyata.

---

## 2. Tech stack dan struktur proyek

- **Streamlit** (multipage dengan `st.navigation` + `st.Page`), Python 3.11+.
- Pendukung: `numpy`, `pandas`, `matplotlib` atau `plotly` (peta dan grafik tiruan).
- Navigasi antar halaman memakai `st.switch_page` / `st.navigation`. Tidak perlu server lain.
- Boleh memakai CSS kustom agar mirip wireframe (sidebar abu-abu, kartu putih bersudut membulat).

```text
sipeta/
├── app.py                  # entry: set_page_config, st.navigation, guard peran
├── pages/                  # satu berkas per halaman
│   ├── landing.py  login.py  register.py  beranda.py
│   ├── klasifikasi_latih.py  klasifikasi_citra.py
│   ├── prediksi_latih.py     prediksi_citra.py
│   ├── pemantauan.py  panduan.py  tentang.py  kelola_pengguna.py
├── services/               # SEMUA akses data lewat sini (lihat aturan di bawah)
│   ├── auth.py  models.py  datasets.py  classify.py  predict.py  monitoring.py
├── mock/                   # data tiruan + seed
│   ├── store.py  seed.py  raster.py
├── ui/                     # komponen bersama: sidebar, kartu, tab, lencana peran
├── data/authors.json       # data Tentang Penulis (mudah diedit)
├── NOTES.md  README.md
```

**Aturan terpenting: lapisan `services/`.** Halaman **tidak boleh** membuat data tiruan sendiri. Halaman hanya memanggil fungsi di `services/`, misalnya `services.classify.run(model_id, kecamatan_id, tanggal)`. Di tahap ini fungsi itu mengembalikan data tiruan. Nanti isinya diganti panggilan HTTP ke FastAPI **tanpa mengubah halaman**.

**Penyimpanan tiruan:** satu _store_ bersama (misalnya `st.cache_resource` yang berisi dict) untuk pengguna, model tersimpan, dataset, dan hasil klasifikasi. Dengan begitu perubahan peran atau model yang disimpan terlihat di halaman lain selama server hidup. Sesi login memakai `st.session_state`, jadi login hilang saat halaman di-refresh. Itu wajar untuk tahap ini.

---

## 3. Peta halaman dan navigasi

### Sidebar (persisten di kiri, abu-abu, seperti wireframe)

```text
SIPETA
• Beranda
• Klasifikasi
    ○ Latih model         ← hanya Admin & Super Admin
    ○ Klasifikasi citra
• Prediksi
    ○ Latih model         ← hanya Admin & Super Admin
    ○ Prediksi citra
• Pemantauan
• Panduan Pengguna
• Tentang Penulis
• Kelola Pengguna         ← ➕ hanya Super Admin
───────────────
[Nama pengguna · lencana peran]   [Keluar]
[Mode demo — data tiruan]
```

- Landing, Login, dan Register **tidak** memakai sidebar (halaman penuh).
- ✅ Di wireframe, "Klasifikasi" dan "Prediksi" masing-masing adalah satu halaman berisi **dua tab** (Latih Model | Klasifikasi Citra, dan Latih Model | Prediksi Citra). Sub-menu sidebar dan tab **harus sinkron**: klik "Latih model" di sidebar membuka halaman pada tab itu, dan klik tab di dalam halaman memperbarui item aktif di sidebar.
- Untuk peran **Pengguna**, tab "Latih Model" **tidak ditampilkan** (hanya tab "Klasifikasi Citra" / "Prediksi Citra").
- Item menu yang tidak boleh diakses **disembunyikan**, dan setiap halaman tetap memiliki _guard_ (lihat bagian 4).

### Alur antar halaman

```text
Landing ──[Mulai]──► (belum login) Login ──► Beranda
                     (sudah login)  ───────► Beranda
Login ──[Daftar]──► Register ──► (otomatis masuk atau kembali ke Login) ──► Beranda
Keluar ──► Landing
```

### Akses per halaman

| Halaman                                                  | Publik | Pengguna | Admin | Super Admin |
| -------------------------------------------------------- | :----: | :------: | :---: | :---------: |
| Landing, Login, Register                                 |   ✓    |   ✓\*    |  ✓\*  |     ✓\*     |
| Beranda, Panduan, Tentang Penulis                        |        |    ✓     |   ✓   |      ✓      |
| Klasifikasi citra, Prediksi citra                        |        |    ✓     |   ✓   |      ✓      |
| Pemantauan                                               |        |    ✓     |   ✓   |      ✓      |
| **Latih model** (Klasifikasi & Prediksi) + Impor dataset |        |          |   ✓   |      ✓      |
| **Kelola Pengguna**                                      |        |          |       |      ✓      |

\* jika sudah login, Login/Register mengalihkan ke Beranda.

---

## 4. Autentikasi dan peran

### 4.1 Tiga peran

| Kunci        | Label UI    | Didapat dengan                                                          | Hak khusus                                    |
| ------------ | ----------- | ----------------------------------------------------------------------- | --------------------------------------------- |
| `user`       | Pengguna    | **Otomatis** saat register                                              | Klasifikasi citra, Prediksi citra, Pemantauan |
| `admin`      | Admin       | Diberikan **Super Admin**                                               | + Latih model, + Impor dataset                |
| `superadmin` | Super Admin | **Tidak bisa** didapat lewat register; hanya dari seed (pemilik sistem) | + Kelola Pengguna (mengubah peran)            |

> Catatan penamaan: di diskusi awal ketiga peran ini disebut "admin", "super admin", dan "super super admin". Nama di tabel di atas yang dipakai di kode dan UI. Taruh kunci dan label peran di **satu berkas konstanta** (mis. `services/roles.py`) supaya mudah diganti.

Peran bersifat **kumulatif**: Super Admin dapat melakukan semua yang dapat dilakukan Admin, dan Admin semua yang dapat dilakukan Pengguna.

### 4.2 Halaman Login

- Field: **Email**, **Kata sandi**; tombol **Masuk**; tautan "Belum punya akun? Daftar".
- Galat: "Email atau kata sandi salah." (jangan menyebut mana yang salah).
- Setelah berhasil: simpan `user`, `role` di `st.session_state`, alihkan ke Beranda.
- ➕ Kotak lipat "Akun demo" berisi akun seed (hanya karena mode demo).

### 4.3 Halaman Register

- Field: **Nama lengkap**, **Email**, **Kata sandi**, **Konfirmasi kata sandi**; tombol **Daftar**.
- Validasi: semua wajib, format email, kata sandi ≥ 8 karakter, konfirmasi cocok, email belum terdaftar.
- Akun baru **selalu** berperan `user`. Tidak ada pilihan peran di form ini.
- Setelah berhasil: pesan "Akun dibuat" lalu alihkan ke Beranda (atau Login).

### 4.4 Halaman Kelola Pengguna (➕, hanya Super Admin)

- Tabel: Nama, Email, Peran (lencana), Tanggal daftar. Ada kolom pencarian dan filter peran.
- Ubah peran lewat dropdown per baris (Pengguna / Admin / Super Admin), dengan **dialog konfirmasi** ("Ubah peran Budi dari Pengguna ke Admin?") lalu notifikasi singkat.
- Aturan: tidak bisa mengubah peran **diri sendiri**; tidak bisa menurunkan Super Admin **terakhir**.
- Perubahan berlaku pada login berikutnya, atau langsung jika pengguna yang bersangkutan sedang aktif (cukup baca peran dari _store_ di setiap _rerun_).

### 4.5 Guard (wajib)

Selain menyembunyikan menu, setiap halaman terbatas memeriksa peran di awal. Jika tidak berhak, tampilkan kartu **"Akses ditolak — halaman ini khusus Admin"** dan tombol kembali ke Beranda. Jika belum login, alihkan ke Login.

### 4.6 Akun seed (demo)

| Email                    | Kata sandi  | Peran       |
| ------------------------ | ----------- | ----------- |
| `superadmin@sipeta.test` | `Super123!` | Super Admin |
| `admin@sipeta.test`      | `Admin123!` | Admin       |
| `user@sipeta.test`       | `User123!`  | Pengguna    |

Seed juga beberapa pengguna lain (berperan Pengguna) agar tabel Kelola Pengguna tidak kosong.

---

## 5. Spesifikasi halaman

Gaya umum kartu: judul halaman di atas, lalu satu **kartu putih bersudut membulat** berisi tab dan konten (seperti wireframe). Label field mengikuti wireframe.

### 5.1 Landing (publik, tanpa sidebar)

- ✅ Judul tengah **"SIPETA: Sistem Pemantauan Tutupan Lahan Terbangun"** dan tombol **Mulai**.
- ➕ Tautan kecil **Masuk** / **Daftar** di pojok kanan atas.

### 5.2 Beranda

- ✅ Judul "SIPETA: Sistem Pemantauan Tutupan Lahan Terbangun" dan blok teks singkat. Teks awal:
  > SIPETA membantu memantau perubahan lahan terbangun di Kota Tangerang, Kota Tangerang Selatan, dan Kabupaten Tangerang menggunakan citra Sentinel-2. Sistem mengklasifikasikan citra menjadi lahan terbangun dan nonterbangun dengan _Random Forest_, memprediksi kondisi tahun berikutnya dengan _ConvLSTM_, dan menyajikan hasilnya sampai tingkat kecamatan.

### 5.3 Klasifikasi → tab **Latih Model** (Admin & Super Admin)

Algoritma: **Random Forest**.

| Field                              |       Status       | Perilaku / default                                                                                                                                                                |
| ---------------------------------- | :----------------: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nama model                         |         ✅         | Wajib; ➕ harus unik (cek terhadap model tersimpan)                                                                                                                               |
| Wilayah                            |         ✅         | Dropdown; ➕ label "Kota/Kabupaten"                                                                                                                                               |
| Kecamatan                          |         ✅         | ➕ **Multi-pilih**, bawaan semua kecamatan pada wilayah terpilih (model boleh mencakup banyak kecamatan)                                                                          |
| Data latih                         | ✅ "Unggah folder" | ➕ **Diganti dropdown "Dataset"** (dataset terdaftar; tiap opsi menampilkan jumlah tanggal, rentang waktu, status prapemrosesan) + tombol **"+ Impor dataset baru"** (lihat 5.3a) |
| Jumlah decision tree               |         ✅         | 100                                                                                                                                                                               |
| Max depth                          |         ✅         | ➕ pilihan "Tidak dibatasi" atau angka                                                                                                                                            |
| Max features                       |         ✅         | ➕ dropdown: `sqrt` (bawaan), `log2`, semua                                                                                                                                       |
| Min sample split                   |         ✅         | 2                                                                                                                                                                                 |
| Min sample leaf                    |         ✅         | 1                                                                                                                                                                                 |
| Train ratio / Test ratio           |         ✅         | 0.8 / 0.2. ➕ Jumlah selalu = 1: mengubah satu otomatis mengubah yang lain                                                                                                        |
| ➕ _Parameter lanjutan_ (expander) |         ➕         | Jumlah sampel per tanggal (50.000), Random seed (42), Pembagian data uji: **Blok spasial** (bawaan) / Acak per piksel                                                             |

- Tombol **Latih model** (✅). Saat ditekan: tampilkan **progres bertahap tiruan** (±5–8 detik) dengan label tahap: _Memvalidasi dataset → Prapemrosesan (cloud masking + PCHIP) → Membentuk label NDBI → Melatih Random Forest → Evaluasi_. Tombol dinonaktifkan selama berjalan.
- ✅ Panel **Evaluasi model** (muncul setelah selesai). ➕ Isinya:
  - 4 kartu metrik: Accuracy, Precision, Recall, F1-score
  - _Confusion matrix_ (peta panas 2×2)
  - _Feature importance_ (diagram batang untuk B02, B03, B04, B05, B06, B07, B12)
  - Tabel metrik **per kecamatan** (F1, precision, recall)
  - Dua tombol: **Simpan model** dan **Buang**
- **Simpan model** → masuk daftar model tersimpan (mempengaruhi dropdown model di tab Klasifikasi Citra) + notifikasi. **Buang** → panel dikosongkan, tidak ada yang tersimpan.
- Pengguna tidak boleh kehilangan hasil evaluasi karena _rerun_: simpan hasil sementara di `st.session_state` sampai Simpan/Buang ditekan.

#### 5.3a Dialog "Impor dataset baru" (➕, Admin & Super Admin)

1. Sumber: **Unggah ZIP** atau **Folder di server** (pilih salah satu).
2. Tombol **Pindai** → tampilkan **laporan validasi** (tiruan) sebelum apa pun disimpan:

   | Tanggal    | Saluran                   | Grid | Status       |
   | ---------- | ------------------------- | ---- | ------------ |
   | 2019-03-15 | 9 saluran + SCL           | sama | ✅           |
   | 2019-05-20 | B11 tidak ada             | -    | ❌           |
   | -          | `foto.tif` tidak dikenali | -    | ⚠️ diabaikan |

3. Tombol **Impor yang valid saja** → dataset muncul di dropdown "Dataset".

- Aturan validasi yang ditampilkan di dialog: tiap tanggal wajib B02–B08, B11, B12, dan SCL; tidak ada duplikat saluran; CRS/resolusi/ukuran sama; tanggal terbaca dari nama berkas.

### 5.4 Klasifikasi → tab **Klasifikasi Citra** (semua peran)

| Field                                  |      Status      | Perilaku                                                                                                                                                                                                                                                                                                                 |
| -------------------------------------- | :--------------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Model                                  |        ✅        | Dropdown. ➕ Tiap opsi menampilkan: nama · cakupan kecamatan · F1 · tanggal latih. ➕ Difilter: hanya model yang cakupannya memuat kecamatan terpilih; jika pengguna memaksa model di luar cakupan, tampilkan peringatan                                                                                                 |
| Wilayah                                |        ✅        | ➕ label "Kota/Kabupaten"                                                                                                                                                                                                                                                                                                |
| Kecamatan                              |        ✅        | Dropdown tunggal                                                                                                                                                                                                                                                                                                         |
| Tanggal                                |        ✅        | Dropdown tanggal yang **tersedia di katalog** untuk kecamatan itu                                                                                                                                                                                                                                                        |
| B02, B03, B04, B05, B06, B07, B12, SCL | ✅ "atau" unggah | ➕ **Sumber citra** dipilih eksplisit lewat _radio_: **Katalog** / **Unggah citra**. Mode Unggah memakai **satu kotak unggah banyak berkas** (bukan 8 kotak) + daftar centang saluran terdeteksi (B02 ✓ … SCL ✓, yang belum ada ditandai ✗), dan field **Tanggal akuisisi** (isi otomatis dari nama berkas, bisa diedit) |
| Tombol **Klasifikasi**                 |        ✅        | Spinner/progres singkat                                                                                                                                                                                                                                                                                                  |

Hasil (setelah Klasifikasi):

- ✅ Dua kanvas berdampingan: **Citra asli** dan **Citra hasil klasifikasi**; _toggle_ **Tampilkan overlay** (hasil ditumpuk di atas citra asli).
- ✅ Teks: **Kota/Kabupaten**, **Kecamatan**, **Luas Lahan Terbangun** (km²), **Luas Lahan nonterbangun** (km²). Tulis "nonterbangun" (tanpa tanda hubung).
- ➕ Legenda (Terbangun / Nonterbangun / Awan atau piksel terisi), _slider_ opasitas overlay, dan baris informasi **"Piksel terisi interpolasi: x%"** (dengan peringatan jika > 30%).
- ➕ Tombol **Simpan hasil** (agar muncul di Pemantauan) dan **Unduh** (PNG / GeoTIFF / CSV; tiruan cukup mengunduh berkas contoh). Hasil yang disimpan **mencatat model yang dipakai**.

### 5.5 Prediksi → tab **Latih Model** (Admin & Super Admin)

Algoritma: **ConvLSTM**.

| Field                           |       Status       | Default                                                           |
| ------------------------------- | :----------------: | ----------------------------------------------------------------- |
| Nama model                      |         ✅         | wajib, unik                                                       |
| Wilayah / Kecamatan             |         ✅         | ➕ Kecamatan multi-pilih (sama seperti 5.3)                       |
| Data latih                      | ✅ "Unggah folder" | ➕ dropdown **"Dataset raster tahunan"** + "+ Impor dataset baru" |
| Sequence length                 |         ✅         | 4                                                                 |
| Train / Test / Validation ratio |         ✅         | 0.7 / 0.15 / 0.15; ➕ jumlah selalu = 1                           |
| Jumlah layers                   |         ✅         | 2                                                                 |
| Kernel size                     |         ✅         | 3                                                                 |
| Dropout                         |         ✅         | 0.2                                                               |
| Epoch                           |         ✅         | 50                                                                |
| Batch size                      |         ✅         | 8                                                                 |
| Learning rate                   |         ✅         | 0.001                                                             |
| Optimizer                       |    ✅ dropdown     | Adam (opsi: Adam, AdamW, RMSprop, SGD)                            |

- Tombol **Latih model** → progres tiruan **per epoch** (label "Epoch 12/50 · loss 0.18"), ±8–10 detik.
- ✅ Panel **Evaluasi model**. ➕ Isinya: kartu **IoU** dan **FoM**, _confusion matrix_, kurva _loss_ (latih vs validasi), tombol **Simpan model** / **Buang**.

### 5.6 Prediksi → tab **Prediksi Citra** (semua peran)

| Field                  | Status | Perilaku                                                                                                                                                                   |
| ---------------------- | :----: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Model                  |   ✅   | Dropdown model ConvLSTM tersimpan                                                                                                                                          |
| Wilayah / Kecamatan    |   ✅   | seperti sebelumnya                                                                                                                                                         |
| Tahun                  |   ✅   | ➕ Hanya **2026** dan **2027**. 2027 diberi lencana **"prediksi rekursif — akurasi lebih rendah"**                                                                         |
| ➕ Sumber data masukan |   ➕   | _Radio_: **Ambil dari katalog** (bawaan) / **Unggah raster sendiri** (jumlah berkas harus sama dengan _sequence length_ model; tampilkan validasi jumlah dan urutan tahun) |
| Tombol **Prediksi**    |   ✅   |                                                                                                                                                                            |

Hasil:

- ✅ Kanvas **Hasil Prediksi**.
- ✅ Teks: Kota/Kabupaten, Kecamatan, **Tahun**, **Luas Lahan Terbangun**, **Luas Lahan nonterbangun** (km²).
- ➕ Selisih terhadap tahun aktual terakhir (mis. "+0,42 km² dibanding 2025") dan tombol Simpan hasil / Unduh.

### 5.7 Pemantauan (semua peran)

- ✅ Input: **Wilayah**, **Kecamatan**, **Tanggal awal**, **Tanggal akhir**; tombol **Tampilkan Data**.
- ➕ Dropdown **Model** (hasil yang dibandingkan harus dari model yang sama; daftar tanggal hanya memuat hasil yang tersimpan untuk model dan kecamatan itu). Tanggal di luar daftar tidak bisa dipilih.
- ✅ Ringkasan **Hasil:** Luas awal, Luas akhir, Perubahan (km², ➕ dengan tanda +/− dan warna).
- ✅ Kanvas besar perbandingan spasial dengan dropdown **Tanggal awal** dan **Tanggal akhir** di atasnya. ➕ Mode tampilan: _Berdampingan_ / _Peta perubahan_ (area bertambah, berkurang, tetap).
- ➕ **Grafik** garis luas lahan terbangun terhadap waktu, dan **tabel riwayat** (tanggal, model, luas terbangun, luas nonterbangun) dengan unduhan CSV.
- Keadaan kosong: jika belum ada hasil tersimpan, tampilkan pesan "Belum ada hasil klasifikasi tersimpan. Jalankan Klasifikasi citra lalu tekan Simpan hasil" dengan tautan ke halaman itu.

### 5.8 Panduan Pengguna

- ✅ Satu kartu dengan dua tab: **Klasifikasi** dan **Prediksi**, masing-masing berisi langkah-langkah bernomor. Tulis draf singkat berdasarkan perilaku halaman di atas. Langkah yang khusus Admin diberi label "(khusus Admin)".

### 5.9 Tentang Penulis

- ✅ **Tiga foto profil bulat** sejajar horizontal (placeholder; jika foto belum ada, tampilkan inisial), nama dan keterangan singkat di bawah tiap foto, lalu satu paragraf deskripsi. Data dibaca dari `data/authors.json` supaya mudah diganti.

---

## 6. Data tiruan (mock)

- **Wilayah dan kecamatan contoh** (cukup beberapa; daftar lengkap menyusul dari data batas administrasi):

  | Wilayah                | Kecamatan contoh                        |
  | ---------------------- | --------------------------------------- |
  | Kota Tangerang         | Cibodas, Karawaci, Batuceper, Cipondoh  |
  | Kota Tangerang Selatan | Serpong, Pamulang, Ciputat, Pondok Aren |
  | Kabupaten Tangerang    | Cikupa, Curug, Pasar Kemis, Teluknaga   |

- **Tanggal citra di katalog** (contoh, bisa dipakai di semua kecamatan): 2019-09-12, 2020-07-28, 2021-08-12, 2023-07-23, 2024-08-06, 2025-07-24.
- **Model seed:** 2 model Random Forest (cakupan semua kecamatan, dan 1 wilayah saja) dan 1 model ConvLSTM, lengkap dengan metadata (F1 / IoU, tanggal latih).
- **Dataset seed:** 2–3 dataset terdaftar (nama, jumlah tanggal, rentang, status).
- **Hasil klasifikasi seed:** untuk tiap kecamatan contoh dan tiap tanggal di atas, agar Pemantauan langsung punya data.
- **Konsistensi:** hasil **deterministik** (seed acak diturunkan dari model + kecamatan + tanggal). Input yang sama selalu menghasilkan angka yang sama, luas terbangun + nonterbangun = luas kecamatan, dan Pemantauan membaca hasil yang sama dengan halaman Klasifikasi. Tren sepanjang waktu cenderung naik (lahan terbangun bertambah).
- **Gambar tiruan** (`mock/raster.py`): bangkitkan dengan `numpy`, tanpa berkas gambar sungguhan. Citra asli = komposit warna sintetis (derau halus bernuansa hijau/cokelat); hasil klasifikasi = peta biner dari gumpalan terbangun; overlay = campuran alfa. Peta perubahan = selisih dua peta biner.

---

## 7. Gaya dan UX umum

- Semua teks UI dalam **Bahasa Indonesia**. Istilah konsisten: **prapemrosesan**, **nonterbangun**, **km²**, **Kota/Kabupaten**, "citra", "saluran".
- Ikuti wireframe: sidebar abu-abu persisten, kartu putih dengan sudut membulat, tab di bagian atas kartu, tombol aksi ringkas. Boleh dipoles, tetapi **jangan mengubah struktur** wireframe.
- Setiap aksi yang lama punya **status memuat** (spinner/progres). Setiap halaman punya **keadaan kosong** dan **pesan galat** yang jelas (bukan _stack trace_).
- Validasi di sisi tampilan: field wajib, jumlah rasio = 1, nama model unik, kelengkapan berkas unggahan.
- Tata letak harus tetap rapi pada lebar laptop (±1280 px); tidak perlu dioptimalkan untuk ponsel di tahap ini.

---

## 8. Urutan pengerjaan (kerjakan per milestone, jalankan aplikasi di setiap akhir)

| #   | Milestone                                                                                       | Selesai jika                                                                                     |
| --- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| M1  | Kerangka: struktur folder, `app.py`, sidebar, Landing, Beranda, halaman kosong untuk semua menu | Semua menu bisa dibuka; sub-menu dan tab sinkron                                                 |
| M2  | Auth dan peran: Login, Register, seed, guard, Kelola Pengguna, menu per peran                   | 3 akun seed menampilkan menu berbeda; register menjadi Pengguna; Super Admin bisa mengubah peran |
| M3  | Klasifikasi: Latih Model (+ dialog Impor dataset) dan Klasifikasi Citra                         | Alur latih → evaluasi → simpan → dipakai di Klasifikasi citra → Simpan hasil                     |
| M4  | Prediksi: Latih Model dan Prediksi Citra                                                        | Alur latih → simpan → prediksi 2026/2027                                                         |
| M5  | Pemantauan                                                                                      | Membaca hasil tersimpan; ringkasan, peta, grafik, tabel, keadaan kosong                          |
| M6  | Panduan, Tentang Penulis, poles                                                                 | Semua halaman sesuai wireframe; `README.md` menjelaskan cara menjalankan dan akun demo           |

Sebelum M1, tulis rencana singkat (struktur dan komponen bersama yang akan dibuat) dan tunggu persetujuan.

## 9. Daftar uji penerimaan

- [ ] Pengguna baru lewat Register berperan **Pengguna** dan **tidak** melihat menu Latih model maupun Kelola Pengguna.
- [ ] Mengetik alamat halaman Latih model sebagai Pengguna menampilkan "Akses ditolak".
- [ ] Admin melihat Latih model tetapi tidak Kelola Pengguna.
- [ ] Super Admin mengubah peran seorang Pengguna menjadi Admin; Admin itu kemudian dapat melatih model.
- [ ] Super Admin tidak dapat mengubah peran sendiri atau menurunkan Super Admin terakhir.
- [ ] Model yang disimpan di Latih model muncul di dropdown Klasifikasi citra, difilter menurut kecamatan.
- [ ] Hasil yang disimpan di Klasifikasi citra muncul di Pemantauan dan angkanya sama.
- [ ] Pemantauan hanya menawarkan tanggal yang punya hasil tersimpan untuk model dan kecamatan terpilih.
- [ ] Sidebar dan tab tetap sinkron di Klasifikasi dan Prediksi.
- [ ] Tidak ada satu pun halaman yang membuat data tiruan langsung; semuanya lewat `services/`.

## 10. Catatan untuk tahap backend nanti (tidak dikerjakan sekarang)

- Ganti isi `services/*` dengan panggilan ke **FastAPI**; halaman tidak berubah.
- **Pembatasan peran harus dipaksakan di backend** (token + pemeriksaan peran di tiap endpoint), bukan hanya dengan menyembunyikan menu.
- Peran `superadmin` tetap tidak boleh dapat dibuat lewat endpoint register.
- Pelatihan berjalan sebagai _job_ latar belakang dengan status yang bisa dipantau, dan hasil disimpan sebagai metadata di database + berkas di penyimpanan.
