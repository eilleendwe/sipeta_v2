# Lanjutan Konteks SIPETA — Alur Latih Model, Klasifikasi Citra, dan Prediksi ConvLSTM

Dokumen ini melanjutkan `Catatan.md` dan `alur_cloudmask_pchip_sipeta.md`. Isinya mencatat keputusan terbaru tentang halaman **Latih Model Klasifikasi** dan **Klasifikasi Citra**, termasuk posisi PCHIP di dalam kedua proses tersebut, serta alur **ConvLSTM** untuk halaman **Latih Model Prediksi** dan **Prediksi Lahan Terbangun** (bagian 12–18). Bagian yang belum final ditandai jelas pada bagian 9 (klasifikasi) dan bagian 17 (ConvLSTM), dan tidak boleh dianggap sudah diputuskan.

---

## 1. Keputusan Terbaru

1. **Latih model memakai data satu kecamatan.** Pengguna memilih satu kecamatan, lalu memasukkan citra kecamatan tersebut saja. Alasannya: mengunggah citra seluruh wilayah dalam jumlah besar lewat peramban tidak praktis (volume file besar, aplikasi berjalan di web, bukan aplikasi desktop yang bisa membaca folder lokal).
2. **PCHIP menjadi bagian internal proses Latih dan proses Klasifikasi.** Tidak ada halaman atau modul prapemrosesan terpisah di antarmuka.
3. Pemotongan citra per kecamatan tetap dilakukan **di luar web** (skrip terpisah). Web menerima citra yang sudah berupa potongan kecamatan.
4. Citra yang dipakai harus berada **di dalam rentang arsip (2016–2025)**, karena PCHIP hanya mengisi data hilang di antara observasi yang ada, bukan memprediksi masa depan.

---

## 2. Perbedaan dengan Notebook Colab

Notebook Random Forest (Colab) dan Latih di web adalah dua rancangan yang berbeda. Hasil notebook tidak otomatis berlaku untuk web.

| Aspek                            | Notebook Colab                                                | Latih di web                                                        |
| -------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------- |
| Data latih                       | Gabungan 40 kecamatan (384.000 sampel)                        | Satu kecamatan terpilih                                             |
| Prapemrosesan                    | Sudah dikerjakan sebelumnya (folder `kecamatan_masked_pchip`) | _Cloud masking_ + PCHIP dikerjakan di dalam proses Latih            |
| Evaluasi                         | Uji pada 9 kecamatan yang tidak pernah dilihat model          | Uji pada blok spasial di dalam kecamatan yang sama (lihat bagian 7) |
| Hyperparameter                   | Hasil Grid Search (36 kombinasi)                              | Titik awal dari Grid Search, belum diuji untuk data sekecil ini     |
| Angka akurasi yang boleh dikutip | Validasi silang 0,9138 (model gabungan)                       | Belum ada, harus dihitung sendiri                                   |

Angka dari notebook tidak boleh dikutip sebagai akurasi model per kecamatan.

---

## 3. Ringkasan Alur

```text
ARSIP (sekali)  : citra → cloud mask → % awan → anchor → DB
LATIH           : pilih kecamatan + citra latih
                  → cloud mask → PCHIP isi awan → NDBI → label acuan
                  → sampel piksel → split blok spasial → Random Forest
                  → evaluasi → (opsional) simpan model + config
KLASIFIKASI     : pilih model + unggah citra (7 band + SCL)
                  → cloud mask → anchor dari DB → PCHIP isi awan
                  → Random Forest → peta 0/1 → luas per kecamatan
LATIH PREDIKSI  : pilih wilayah/kecamatan + hyperparameter ConvLSTM
                  → peta 0/1 per tanggal (arsip klasifikasi) → peta tahunan
                    (komposit mayoritas + konsistensi waktu) → resize 64×64
                  → jendela L tahun → ConvLSTM → evaluasi test 2024–2025
                  → latih ulang sampai 2025 → (opsional) simpan model + config
PREDIKSI        : pilih model ConvLSTM + kecamatan
                  → peta tahunan L tahun terakhir → ConvLSTM → peluang 0–1
                  → ambang 0,5 → peta 2026 → (rekursif) peta 2027 → luas per kecamatan
```

PCHIP memakai satu implementasi yang sama pada kedua proses (bagian 6). Pembuatan peta tahunan untuk ConvLSTM juga memakai satu implementasi yang sama pada Latih Prediksi dan Prediksi (bagian 13). Grid search ConvLSTM tidak dijalankan di web.

---

## 4. Persiapan Arsip (rujukan singkat)

Rincian lengkap ada di `alur_cloudmask_pchip_sipeta.md`. Yang dibutuhkan di sini:

- 64 tanggal Sentinel-2 L2A (2016–2025), resolusi 10 m, per wilayah (Kota Tangerang, Kota Tangerang Selatan, Kabupaten Tangerang).
- _Cloud mask_ boolean dari SCL kelas 3, 8, 9, 10 + _buffer_ 30 m. SCL = 0 dianggap NoData.
- **Anchor** = tanggal dengan awan ≤ 6% setelah _buffer_, ditentukan per wilayah (14 / 25 / 13 anchor).
- Database hanya menyimpan metadata dan lokasi file (`wilayah`, `tanggal`, `path_folder`, `cloud_pct_buffer`, `is_anchor`, dst.). File GeoTIFF disimpan di penyimpanan file.
- Perlu tabel pemetaan **kecamatan → wilayah**, supaya anchor yang benar dapat dipilih untuk kecamatan yang dipilih pengguna.

**Koreksi terhadap dokumen alur:** pada bagian "Hal yang perlu dipastikan" dokumen alur menyebut anchor cukup menyimpan 7 band + SCL. Itu benar untuk **Klasifikasi**, tetapi **Latih membutuhkan 9 band + SCL** (B08 dan B11 untuk NDBI), kecuali sampel latih hanya diambil dari piksel cerah (lihat keputusan terbuka 9.2). Arsip anchor sebaiknya tetap menyimpan 9 band + SCL.

---

## 5. Alur Latih Model Klasifikasi

### Dari sisi pengguna

1. Pilih **kecamatan**.
2. Masukkan **citra latih** kecamatan tersebut (sumber citra: lihat keputusan terbuka 9.1).
3. Klik **Latih**, lalu lihat progres.
4. Lihat **hasil evaluasi** (_confusion matrix_, _accuracy_, _precision_, _recall_, F1-score).
5. Pilih **simpan model** atau tidak.

### Dari sisi sistem

Masukan: kecamatan K, himpunan tanggal latih, per tanggal 9 band (B02, B03, B04, B05, B06, B07, B08, B11, B12) + SCL.

1. **Validasi masukan.** Grid sama dengan arsip (CRS, resolusi 10 m, _transform_); jika tidak sama, baca bagian anchor yang sesuai dengan `rasterio.windows.from_bounds(...)` atau tolak. Semua band dan SCL tersedia. Tanggal berada dalam rentang arsip.
2. **Cloud mask** setiap tanggal latih dari file SCL tanggal itu (kelas 3/8/9/10 + _buffer_ 30 m). Hasilnya array boolean terpisah. Raster band tidak diubah dan tidak diberi NaN.
3. **Isi piksel berawan (PCHIP, modul bersama).**
   - Anchor wilayah kecamatan K diambil dari database (kecuali tanggal target sendiri), dibaca pada jendela kecamatan K.
   - Per piksel berawan: 2 donor cerah sebelum + 2 donor cerah sesudah → PCHIP; hanya sesudah → _backward fill_; hanya sebelum → _forward fill_.
   - Donor selalu dari raster **asli**, bukan hasil isian.
4. **NDBI** = (B11 − B08) / (B11 + B08), lalu label acuan: NDBI > 0 → 1 (terbangun), NDBI ≤ 0 → 0 (nonterbangun). Sebut sebagai **label/acuan berbasis NDBI**, bukan _ground truth_.
5. **Ambil sampel piksel** per tanggal (default mengikuti notebook: 150 piksel valid per tanggal). Aturan piksel cerah atau terisi: keputusan terbuka 9.2.
6. **Split spasial berbasis blok** di dalam kecamatan (bagian 7).
7. **Latih Random Forest** dengan fitur B02, B03, B04, B05, B06, B07, B12. B08 dan B11 **tidak** menjadi fitur (menghindari _target leakage_).
8. **Evaluasi** pada blok uji. Tampilkan _confusion matrix_ (jumlah dan persentase per kelas aktual) dan metrik.
9. **Jika pengguna memilih simpan**, simpan:
   - file model;
   - **konfigurasi prapemrosesan** (JSON);
   - satu baris metadata di database (nama model, kecamatan latih, tanggal, metrik, path model, path config).

Estimasi waktu: sekitar 9.600 baris latih (64 tanggal × 150) berarti kira-kira satu menit untuk 30 pohon. Ini hasil penskalaan dari log Colab (±50 detik per pohon pada 384.000 baris), belum diukur. Random Forest buatan sendiri lambat, jadi jalankan sebagai **proses latar belakang** dengan indikator progres, bukan satu permintaan HTTP.

### Contoh konfigurasi yang disimpan

Berdasarkan contoh di dokumen alur, dengan tambahan untuk Latih per kecamatan:

```json
{
  "model_file": "rf_batuceper_20261015.pkl",
  "preprocessing_version": "pchip_manual_cloudbuffer30m_v2",
  "scl_cloud_classes": [3, 8, 9, 10],
  "cloud_buffer_m": 30,
  "anchor_cloud_max_pct": 6.0,
  "gap_fill": "pchip_2before_2after",
  "resolution_m": 10,
  "features": ["B02", "B03", "B04", "B05", "B06", "B07", "B12"],
  "label_rule": "NDBI = (B11-B08)/(B11+B08) > 0",
  "training_kecamatan": ["batuceper"],
  "training_dates": ["2017-07-04", "..."],
  "sampling": { "n_per_date": 150, "source": "belum_final" },
  "hyperparameters": {
    "n_trees": 30,
    "max_depth": 16,
    "min_samples_split": 10,
    "n_features": 3,
    "max_thresholds": 20,
    "bootstrap": true
  },
  "evaluation": {
    "split": "blok_spasial",
    "block_size_px": 50,
    "test_fraction": 0.2
  }
}
```

---

## 6. Alur Klasifikasi Citra

### Dari sisi pengguna

1. Pilih **model** yang sudah disimpan.
2. Unggah **satu citra** (kecamatan K, tanggal D) **beserta file SCL-nya**. Tanpa SCL, awan tidak dapat dideteksi.
3. Klik **Klasifikasi**, lalu lihat peta biner dan luas terbangun per kecamatan.
4. Hasil dapat disimpan untuk modul Pemantauan dan diunduh.

### Dari sisi sistem

Masukan: model M, citra tanggal D (7 band fitur + SCL).

1. Baca **konfigurasi model** M. Parameter prapemrosesan (kelas SCL, _buffer_, aturan _gap filling_, daftar fitur) **selalu diambil dari konfigurasi model**, bukan dari nilai bawaan kode.
2. Periksa grid citra terhadap arsip (ukuran, CRS, _transform_).
3. **Cloud mask** citra D dari SCL citra D, dengan aturan yang sama seperti saat Latih.
4. Ada piksel berawan?
   - Tidak → langsung klasifikasi.
   - Ya → ambil **semua anchor wilayah** dari database (kecuali tanggal D), buka band fitur + SCL anchor pada jendela citra, isi piksel berawan dengan PCHIP (atau _backward/forward fill_).
5. Fitur B02–B07 dan B12 → _Random Forest_ → raster biner **0/1** (`uint8`), piksel di luar wilayah diberi NoData 255.
6. Luas terbangun: jumlah piksel kelas 1 × 100 m², dikonversi ke km², lalu diagregasikan per kecamatan dan disimpan.

Semua anchor wilayah diambil, bukan hanya 2 sebelum dan 2 sesudah, karena anchor terdekat bisa berawan pada piksel tertentu sehingga piksel itu harus "melompat" ke anchor berikutnya.

Klasifikasi seluruh piksel kecamatan dengan Random Forest buatan sendiri juga lambat (log Colab sebelumnya: ±260 detik per raster untuk model lama). Jalankan sebagai proses latar belakang.

```sql
SELECT tanggal, path_folder
FROM citra
WHERE wilayah = :wilayah_dari_kecamatan
  AND is_anchor = true
  AND tanggal <> :D
ORDER BY tanggal;
```

---

## 7. PCHIP sebagai Modul Bersama

PCHIP dipakai pada Latih dan Klasifikasi, jadi harus berupa **satu fungsi yang sama**, bukan dua salinan. Aturan yang harus identik:

- Piksel yang diisi hanya yang ber-_mask_ `True` pada tanggal target.
- Donor layak jika cerah pada piksel itu (dicek dari _cloud mask_ anchor); anchor berawan pada piksel itu dilewati.
- Donor diambil dari raster asli, tidak pernah dari hasil isian.
- Sumbu waktu PCHIP adalah **hari** (ordinal tanggal), bukan tahun.
- PCHIP tidak melakukan ekstrapolasi. Ketika donor hanya ada di satu sisi, dipakai _backward fill_ atau _forward fill_, yang **bukan** PCHIP dan proporsinya dilaporkan terpisah.
- PCHIP **tidak disimpan sebagai model**; yang disimpan adalah konfigurasinya.
- Gunakan implementasi PCHIP yang sudah ada di skrip arsip (versi prapemrosesan `pchip_manual_cloudbuffer30m_v2`), jangan menulis ulang dengan perilaku berbeda.

---

## 8. Evaluasi Model Satu Kecamatan

Evaluasi notebook (uji pada kecamatan lain) tidak bisa dipakai, karena model hanya melihat satu kecamatan. Rancangannya:

- Bagi raster kecamatan menjadi **blok spasial** yang tidak tumpang tindih (contoh 50 × 50 piksel; ukuran belum final), lalu bagi blok secara acak ke latih dan uji (contoh 80:20, _seed_ tetap).
- **Semua tanggal dari satu blok masuk ke sisi yang sama.** Piksel di lokasi yang sama pada tanggal berbeda sangat mirip. Jika sebagian masuk latih dan sebagian masuk uji, akurasi menjadi terlalu optimis.
- Sebaiknya beri jarak (blok _buffer_) antara blok latih dan uji yang bertetangga.
- Hasilnya tetap lebih optimis daripada uji pada kecamatan asing, karena uji dan latih berasal dari kecamatan yang sama. **Jangan membandingkan angka ini langsung dengan angka notebook.**
- Akurasi mengukur **kesesuaian dengan label berbasis NDBI**, bukan kebenaran lapangan. B07 dan B12 berkorelasi dengan B08 dan B11, sehingga akurasi tinggi sebagian mencerminkan model yang menebak ulang aturan NDBI.

---

## 9. Hal yang Belum Final (_Open Decision_)

Jangan dianggap sudah diputuskan. Tanyakan kepada pengguna sebelum diimplementasikan.

1. **Sumber citra Latih untuk satu kecamatan.** Diunggah pengguna, atau diambil dari arsip server berdasarkan pilihan kecamatan? Ukuran file satu kecamatan sedang dicek (volume 64 tanggal × 9 band + SCL mungkin tetap besar). Opsi penghematan: satu GeoTIFF multi-band terkompresi per tanggal (_deflate_, _lossless_), pemotongan sampai _bounding box_ kecamatan, dan menaikkan `server.maxUploadSize` di Streamlit. Rasio kompresi pada data asli belum diukur.
2. **Sampel latih dari piksel cerah saja, atau termasuk piksel hasil isian.** Jika hanya piksel cerah, nilai band dan NDBI-nya tidak tersentuh PCHIP, sehingga PCHIP praktis tidak memengaruhi model yang dilatih (hanya relevan pada Klasifikasi). Jika termasuk piksel isian, model melihat data seperti yang akan dihadapi saat Klasifikasi, tetapi label NDBI berasal dari nilai interpolasi, bukan observasi. Dokumen alur menyarankan piksel cerah. Keputusan ini menentukan apakah PCHIP di Latih benar-benar berfungsi dan apakah B08 dan B11 anchor harus disimpan.
3. **Donor dari anchor saja atau dari semua tanggal rekaman.** Kode arsip saat ini hanya memakai anchor. Kode, sistem, dan Bab 3 harus konsisten.
4. **Anchor per wilayah atau per kecamatan.** Anchor ditentukan per wilayah (kota atau kabupaten). Untuk satu kecamatan, persentase awannya bisa berbeda dari wilayahnya. Saat ini anchor tetap per wilayah.
5. **Apakah model boleh dipakai pada kecamatan lain.** Model dicatat bersama kecamatan latihnya. Menerapkannya pada kecamatan lain tanpa evaluasi adalah klaim yang belum teruji. Pertimbangkan peringatan di halaman Klasifikasi jika kecamatan berbeda.
6. **Keterbandingan antar kecamatan dan input ConvLSTM.** Model berbeda per kecamatan dapat membuat peta antar kecamatan tidak sebanding. ConvLSTM membutuhkan raster klasifikasi yang seragam. Perlu ditetapkan model mana yang menghasilkan raster masukan ConvLSTM (misalnya satu model gabungan dari notebook).
7. **Hyperparameter untuk data kecil.** Nilai Grid Search (30/16/10/3/20) dituning pada 384.000 baris. Pada ±9.600 baris belum terbukti optimal.
8. **Format dan pemuatan model.** Dokumen alur menyebut `.joblib`, notebook memakai `.pkl`. Kelas `Node`, `DecisionTree`, dan `RandomForest` buatan sendiri harus dipindah ke satu modul yang dapat diimpor backend. Model yang di-_pickle_ dari notebook merujuk kelas di `__main__`, sehingga tidak dapat dimuat begitu saja di backend.
9. **Offset reflektansi Sentinel-2.** Produk L2A dengan _processing baseline_ ≥ 04.00 memakai `BOA_ADD_OFFSET = -1000`. Periksa `MTD_MSIL2A.xml` apakah data 2016–2021 dan 2022–2025 memakai skala yang sama.
10. **Ukuran dan jumlah sampel per tanggal, ukuran blok, dan rasio split** untuk Latih satu kecamatan.

---

## 10. Hasil Notebook sebagai Titik Awal

- Data: 49 kecamatan × 64 tanggal × 150 piksel = 470.400 sampel. Spatial split per kecamatan (40 latih, 9 uji).
- Grid Search: 36 kombinasi × 3 lipatan (`GroupKFold` per kecamatan), model terbaik dipilih berdasarkan akurasi rata-rata.
- Hyperparameter terbaik: `n_trees=30`, `max_depth=16`, `min_samples_split=10`, `n_features=3`, `max_thresholds=20`, `bootstrap=True`.
- Akurasi validasi silang kombinasi terbaik: **0,9138**. Perbedaan antar kombinasi teratas lebih kecil daripada simpangan baku antar lipatan, sehingga tidak dapat dibedakan secara statistik; yang berpengaruh adalah `n_trees` dan `max_depth`.
- Fitur: B02, B03, B04, B05, B06, B07, B12. Label: NDBI > 0.

---

## 11. Istilah dan Hal yang Harus Dijaga

- Gunakan **label/acuan berbasis NDBI**, bukan "_ground truth_ NDBI".
- Gunakan `nonterbangun` (tanpa tanda hubung), **data hilang/tidak valid** untuk piksel awan, dan **prapemrosesan**.
- PCHIP bukan model prediksi masa depan. Ia hanya mengisi data hilang di antara observasi yang tersedia.
- _Backward fill_ dan _forward fill_ bukan PCHIP; laporkan proporsinya terpisah di Bab 4.
- Sequence length bukan lama prediksi, dan 10 tahun data bukan 10 sampel ConvLSTM (lihat `Catatan.md`).

---

## 12. ConvLSTM dalam Sistem

Bagian 12–18 menjelaskan cara kerja ConvLSTM di sistem, mengikuti notebook `convlstm_sipeta_v8.ipynb` **tanpa grid search**. Grid search hanya dijalankan di notebook. Web memakai hasilnya sebagai nilai bawaan form.

1. **Masukan ConvLSTM adalah peta klasifikasi 0/1, bukan citra.** _Cloud masking_, PCHIP, dan Random Forest sudah terjadi sebelumnya, pada tahap klasifikasi. Tahap ConvLSTM tidak membaca band Sentinel-2 sama sekali.
2. **Satu model ConvLSTM untuk banyak kecamatan** (model global), berbeda dengan Latih Random Forest yang per kecamatan. Satu kecamatan hanya punya 10 peta tahunan, sehingga dengan sequence length 4 hanya menghasilkan 6 jendela (sampel). Notebook melatih satu model dari 49 kecamatan (294 jendela sampai 2025). Rujukan model global: Montero-Manso & Hyndman (2021), *International Journal of Forecasting* 37(4):1632–1653.
3. **Rumus LSTM ditulis sendiri** (`ConvLSTMManual`, Persamaan 2.39–2.44, tanpa _peephole_). Konvolusi (`tf.nn.conv2d`), gradien, Adam, BatchNormalization, Conv2D output, dan proses `fit` memakai TensorFlow/Keras. Kesamaan dengan `ConvLSTM2D` Keras sudah dibuktikan di notebook v8 bagian 3b.
4. **Tahun prediksi 2026 (1 langkah) dan 2027 (2 langkah, rekursif).** Prediksi 2027 memakai peta 2026 hasil prediksi sebagai masukan, jadi galat 2026 ikut terbawa.

---

## 13. Peta Tahunan sebagai Modul Bersama

Latih Prediksi dan Prediksi harus memakai **satu fungsi yang sama** untuk membuat peta tahunan, seperti prinsip PCHIP pada bagian 7. Jika berbeda, model menerima data dengan aturan lain saat prediksi.

Masukan per kecamatan: semua raster klasifikasi 0/1 per tanggal 2016–2025 (nilai 255 = NoData). Jumlah tanggal per tahun: 2016 = 1, 2017 = 3, 2018 = 11, 2019 = 13, 2020 = 6, 2021 = 6, 2022 = 5, 2023 = 9, 2024 = 5, 2025 = 5 (total 64).

1. **Komposit mayoritas per tahun.** Untuk setiap piksel, hitung berapa tanggal valid (bukan 255) yang mengklasifikasikannya terbangun. Piksel = 1 jika **lebih dari 50%** tanggal valid terbangun; tepat 50% dianggap 0; 255 jika tidak pernah valid sepanjang tahun itu. Hasil: 10 peta tahunan.
2. **Konsistensi waktu.** Jika piksel terbangun pada tahun t−1 dan t−2, lalu bernilai 0 pada tahun t, nilainya diubah menjadi 1. Aturan hanya melihat tahun sebelumnya. Karena berantai, piksel yang terbangun dua tahun berturut-turut akan tetap terbangun pada tahun-tahun berikutnya.
3. **Resize ke 64×64** dengan _nearest neighbour_ (label kategorikal tidak boleh diinterpolasi). Piksel NoData menjadi −1 dan tidak ikut dihitung dalam loss maupun evaluasi.
4. **Simpan cache** per kecamatan: peta 64×64 per tahun, ukuran raster asli, dan luas terbangun resolusi asli per tahun.

Kecamatan yang tidak lengkap 10 tahunnya tidak dipakai, supaya jendela waktunya sejajar.

Ukuran satu sel 64×64 berbeda tiap kecamatan (lebar raster asli ÷ 64; sekitar 100 m untuk kecamatan sedang). Luas satu sel = (tinggi asli × lebar asli × 0,0001 km²) / 4.096.

---

## 14. Alur Latih Model Prediksi

### Dari sisi pengguna

1. Isi **nama model** dan pilih **wilayah/kecamatan** yang dipakai melatih (bawaan: semua kecamatan, lihat keputusan terbuka 17.2).
2. Isi hyperparameter. Nilai bawaan = kombinasi terbaik dari grid search notebook v8:
   - sequence length, jumlah layer ConvLSTM, jumlah filter, ukuran kernel, dropout, learning rate, optimizer;
   - epoch maksimum dan batch size;
   - rasio train/validasi/test.
3. Klik **Latih**, lihat progres.
4. Lihat **hasil evaluasi** test 2024 dan 2025.
5. Pilih **simpan model** atau tidak.

`filters` (jumlah filter) belum ada di form lama, tetapi berpengaruh dan ikut grid search, jadi perlu ditambahkan ke form.

### Dari sisi sistem

1. **Validasi masukan.** Setiap kecamatan terpilih punya 10 peta tahunan. Sequence length maksimum 4 supaya masih ada cukup jendela latih dari 10 tahun data.
2. **Siapkan peta tahunan** (bagian 13), memakai cache jika ada.
3. **Bentuk sampel.** Satu sampel = L peta tahunan berurutan → peta tahun berikutnya. Pembagian berdasarkan **tahun target**, bukan acak: dari target 2020–2025 dengan rasio 0,5 / 0,17 / 0,33 didapat train 2020–2022, validasi 2023, test 2024–2025.
4. **Bangun model:** `n_layers` × (`ConvLSTMManual` → `BatchNormalization`), lalu `Conv2D` 1 filter dengan sigmoid. Loss: _binary cross-entropy_ yang mengabaikan piksel −1. Optimizer: Adam.
5. **Latih dengan validasi.** Maksimum 100 epoch, _early stopping_ memantau `val_loss` (patience 15, baru memantau setelah epoch 20), bobot terbaik dipulihkan. Catat epoch terbaik.
6. **Uji.** Latih ulang dengan semua target sampai 2023 sebanyak epoch terbaik. Prediksi 2024 (1 langkah dari 2023) dan 2025 (2 langkah, rekursif), lalu bandingkan dengan peta aktual.
7. **Tampilkan evaluasi:**
   - utama: _confusion matrix_ (jumlah dan persentase per kelas aktual), _accuracy_, _precision_, _recall_, F1-score;
   - pembanding: angka yang sama untuk **persistensi** (peta 2023 disalin apa adanya);
   - pelengkap: IoU, FoM, _confusion matrix_ khusus piksel yang nonterbangun di 2023, serta MAE, RMSE, MAPE, R² luas per kecamatan.
8. **Model final.** Latih ulang dengan semua target sampai 2025, epoch sama. Model inilah yang dipakai halaman Prediksi.
9. **Jika pengguna memilih simpan**, simpan:
   - file model final `.keras`;
   - **konfigurasi** (JSON, contoh di bawah);
   - satu baris metadata di database (nama model, kecamatan latih, tanggal latih, metrik test, path model, path config).

**Estimasi waktu.** Alur ini melatih tiga kali (validasi, uji, final). Dari log notebook v7 di GPU Colab, satu pelatihan dengan _early stopping_ butuh sekitar 1,5–5,7 menit, jadi satu kali Latih kira-kira 5–15 menit di GPU. Di CPU jauh lebih lama (notebook lama tercatat sekitar 2 menit per epoch di CPU). Kecepatan layer manual di GPU belum diukur. Jalankan sebagai **proses latar belakang** dengan indikator progres, bukan satu permintaan HTTP.

### Contoh konfigurasi yang disimpan

Nilai hyperparameter di bawah adalah hasil v7 (2 layer, belum diuji jumlah layer lain). Ganti dengan hasil v8 setelah grid search v8 selesai.

```json
{
  "model_file": "convlstm_sipeta_final_f40_k5_lr0.0005_L4_nl2_do0.0_adam_e47.keras",
  "model_type": "ConvLSTMManual (Persamaan 2.39-2.44, tanpa peephole)",
  "framework": "TensorFlow/Keras (isi versi dari tf.__version__)",
  "input": "peta klasifikasi 0/1 per tanggal (arsip kecamatan_masked_rf_classified)",
  "annual_map": {
    "composite_mode": "mayoritas",
    "majority_min_frac": 0.5,
    "tie_rule": "seri = 0",
    "temporal_consistency": "terbangun di t-1 dan t-2 -> tetap terbangun di t",
    "patch_size": 64,
    "resize": "nearest",
    "nodata_in": 255,
    "nodata_model": -1
  },
  "training_kecamatan": ["semua 49 kecamatan"],
  "years": { "data": [2016, 2025], "train": [2020, 2021, 2022], "val": [2023], "test": [2024, 2025] },
  "hyperparameters": {
    "sequence_length": 4,
    "n_layers": 2,
    "filters": 40,
    "kernel_size": 5,
    "dropout": 0.0,
    "learning_rate": 0.0005,
    "optimizer": "adam",
    "batch_size": 8,
    "epochs": 47
  },
  "early_stopping": { "monitor": "val_loss", "patience": 15, "start_from_epoch": 20, "max_epochs": 100 },
  "threshold": 0.5,
  "forecast": { "last_observed_year": 2025, "years": [2026, 2027], "mode": "rekursif" },
  "evaluation_test": {
    "2024": { "accuracy": 0.9578, "precision": 0.9879, "recall": 0.9365, "f1": 0.9615 },
    "2025": { "accuracy": 0.9542, "precision": 0.9896, "recall": 0.9292, "f1": 0.9585 }
  }
}
```

---

## 15. Alur Prediksi Lahan Terbangun

### Dari sisi pengguna

1. Pilih **model ConvLSTM** yang sudah disimpan.
2. Pilih **kecamatan** (hanya kecamatan yang ikut dilatih model itu) dan **tahun prediksi** (2026 atau 2027).
3. Klik **Prediksi**, lalu lihat peta dan luas terbangun.
4. Hasil dapat disimpan dan diunduh.

### Dari sisi sistem

Masukan: model M, kecamatan K, tahun prediksi.

1. Baca **konfigurasi model** M. Sequence length, ukuran patch, ambang, dan aturan peta tahunan **selalu diambil dari konfigurasi**, bukan dari nilai bawaan kode.
2. **Siapkan peta tahunan** L tahun terakhir untuk K (misalnya 2022–2025 untuk L = 4), dengan fungsi yang sama seperti saat latih (bagian 13).
3. **Prediksi 2026.** Model mengeluarkan peta peluang 0–1 berukuran 64×64. Sel dengan peluang > 0,5 menjadi 1 (terbangun). Sel yang NoData di peta 2025 tetap NoData.
4. **Prediksi 2027 (rekursif).** Jendela digeser satu tahun: peta tertua dibuang, peta 2026 hasil prediksi dimasukkan, lalu model dijalankan lagi.
5. **Luas terbangun** = jumlah sel bernilai 1 × luas satu sel (bagian 13), per kecamatan. Sebagai pembanding, tampilkan luas 2025 versi 64×64 dan versi resolusi asli.
6. **Tampilan peta.** Model hanya menghasilkan 64×64. Untuk tampilan halus, gunakan cara notebook v8 bagian 9: peta aktual 2025 resolusi 10 m, lalu sel yang menurut model berubah diganti (bertambah atau berkurang). Detail halus berasal dari data 2025; perubahan hasil prediksi tetap berupa kotak seukuran satu sel model. Tulis keterangan ini di halaman.
7. **Simpan hasil:** luas per kecamatan (CSV/DB), peta peluang dan peta biner (`.npz`), satu baris metadata (model, kecamatan, tahun, path).

Prediksi jauh lebih ringan daripada latih: satu kali proses maju model untuk setiap tahun.

**Memuat model.** File `.keras` memakai layer buatan sendiri, jadi kelas `ConvLSTMManual` (beserta loss `masked_binary_crossentropy`) harus berada di satu modul Python yang diimpor backend **sebelum** `tf.keras.models.load_model(path, compile=False)`. Masalahnya sama seperti kelas Random Forest pada keputusan terbuka 9.8.

---

## 16. Hasil Notebook sebagai Titik Awal

**v7** (`ConvLSTM2D` Keras, jumlah layer ditetapkan 2):

- Konfigurasi terpilih: 40 filter, kernel 5×5, learning rate 0,0005, sequence length 4, 2 layer, 47 epoch.
- Test, model vs persistensi:

| Tahun | Akurasi | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| 2024 model | 0,958 | 0,988 | 0,937 | 0,962 |
| 2024 persistensi | 0,959 | 0,960 | 0,968 | 0,964 |
| 2025 model | 0,954 | 0,990 | 0,929 | 0,959 |
| 2025 persistensi | 0,960 | 0,965 | 0,964 | 0,965 |

- Model sangat jarang salah menuduh terbangun (precision tinggi), tetapi melewatkan sebagian lahan terbangun (recall lebih rendah).
- Pembangunan baru yang tertangkap di 2024: 12 dari 1.881 piksel.
- Prediksi total 2026: −1,9% dibanding 2025.

**v8** (layer manual, jumlah layer 1–3 diuji di grid): belum dijalankan. Konfigurasi web diambil dari v8 setelah selesai.

Angka v7 tidak sebanding langsung dengan v6, karena label v7 sudah dibersihkan.

---

## 17. Hal yang Belum Final untuk ConvLSTM

Jangan dianggap sudah diputuskan. Tanyakan kepada pengguna sebelum diimplementasikan.

1. **Latih ConvLSTM di web atau hanya di notebook.** Melatih di web butuh GPU di server agar waktunya wajar. Alternatifnya: model dilatih di notebook, web hanya memuat model dan menjalankan Prediksi.
2. **Kecamatan untuk melatih.** Semua 49 kecamatan (seperti notebook), per wilayah, atau subset. Melatih dari satu kecamatan saja tidak disarankan (6 jendela sampel).
3. **Sumber raster masukan** (berkaitan dengan 9.6). ConvLSTM notebook dilatih dari arsip `kecamatan_masked_rf_classified` (model RF gabungan notebook). Hasil Klasifikasi dari model RF per kecamatan di web sebaiknya tidak dicampur ke masukan ConvLSTM tanpa dikaji, karena aturan klasifikasinya bisa berbeda.
4. **Peta dan luas yang ditampilkan:** versi 64×64 atau versi 10 m (2025 aktual + perubahan prediksi). Luas keduanya bisa sedikit berbeda.
5. **Cara evaluasi test.** Saat ini label test juga melewati aturan konsistensi waktu, sehingga sebagian jawaban test ditentukan oleh peta tahun sebelumnya. Opsi: evaluasi terhadap peta mayoritas tanpa aturan konsistensi, dan/atau validasi dengan titik acuan independen (misalnya interpretasi visual citra resolusi tinggi).
6. **Kriteria pemilihan kombinasi grid.** Saat ini FoM tertinggi (IoU sebagai pemecah seri). Alternatifnya F1 tertinggi.
7. **Prediksi tidak boleh menyusut** (peta prediksi = peta terakhir + piksel baru saja). Belum diterapkan; prediksi 2026 v7 masih turun 1,9%.
8. **Data tahun baru** (misalnya 2026 aktual). Perlu prosedur: tambahkan ke arsip klasifikasi, perbarui cache peta tahunan, latih ulang model.

---

## 18. Istilah dan Hal yang Harus Dijaga untuk ConvLSTM

- Rumus yang dipakai adalah Persamaan 2.39–2.44 **tanpa _peephole_**. Persamaan asli Shi dkk. (2015) memakai _peephole_; implementasi Keras dan notebook ini tidak.
- "Konvolusi" di TensorFlow dihitung tanpa membalik kernel (secara teknis _cross-correlation_). Contoh perhitungan manual di skripsi mengikuti cara ini.
- Akurasi tinggi sebagian karena ±96% piksel tidak berubah dari tahun ke tahun. **Selalu tampilkan persistensi** di samping metrik model.
- Aturan konsistensi waktu adalah **asumsi** bahwa lahan terbangun tidak kembali menjadi nonterbangun. Prinsipnya diadaptasi dari pemetaan lahan kedap air (Gong dkk., 2020, GAIA; Zhang dkk., 2022, GISD30). Syarat "2 tahun berturut-turut" adalah pilihan peneliti, bukan dari satu rujukan.
- Masukan dan keluaran ConvLSTM berukuran 64×64 per kecamatan, bukan 10 m. Ukuran sel berbeda tiap kecamatan.
- Layer = satu tahap hitung; `n_layers` hanya menghitung layer ConvLSTM. Batch = potongan data (8 sampel). Epoch = satu putaran atas semua data latih.
- Label tetap **label berbasis NDBI**, sehingga ConvLSTM memprediksi peta label itu, termasuk kesalahannya.

## DATA KECAMATAN

| Wilayah                    | Kecamatan     |
| :------------------------- | :------------ |
| **Kabupaten Tangerang**    | Balaraja      |
| Kabupaten Tangerang        | Cikupa        |
| Kabupaten Tangerang        | Cisauk        |
| Kabupaten Tangerang        | Cisoka        |
| Kabupaten Tangerang        | Curug         |
| Kabupaten Tangerang        | Gunung Kaler  |
| Kabupaten Tangerang        | Jambe         |
| Kabupaten Tangerang        | Jayanti       |
| Kabupaten Tangerang        | Kelapa Dua    |
| Kabupaten Tangerang        | Kemiri        |
| Kabupaten Tangerang        | Kosambi       |
| Kabupaten Tangerang        | Kresek        |
| Kabupaten Tangerang        | Kronjo        |
| Kabupaten Tangerang        | Legok         |
| Kabupaten Tangerang        | Mauk          |
| Kabupaten Tangerang        | Mekar Baru    |
| Kabupaten Tangerang        | Pagedangan    |
| Kabupaten Tangerang        | Pakuhaji      |
| Kabupaten Tangerang        | Panongan      |
| Kabupaten Tangerang        | Pasar Kemis   |
| Kabupaten Tangerang        | Rajeg         |
| Kabupaten Tangerang        | Sepatan       |
| Kabupaten Tangerang        | Sepatan Timur |
| Kabupaten Tangerang        | Sindang Jaya  |
| Kabupaten Tangerang        | Solear        |
| Kabupaten Tangerang        | Sukadiri      |
| Kabupaten Tangerang        | Sukamulya     |
| Kabupaten Tangerang        | Teluknaga     |
| Kabupaten Tangerang        | Tigaraksa     |
| **Kota Tangerang**         | Batuceper     |
| Kota Tangerang             | Benda         |
| Kota Tangerang             | Cibodas       |
| Kota Tangerang             | Ciledug       |
| Kota Tangerang             | Cipondoh      |
| Kota Tangerang             | Jatiuwung     |
| Kota Tangerang             | Karang Tengah |
| Kota Tangerang             | Karawaci      |
| Kota Tangerang             | Larangan      |
| Kota Tangerang             | Neglasari     |
| Kota Tangerang             | Periuk        |
| Kota Tangerang             | Pinang        |
| Kota Tangerang             | Tangerang     |
| **Kota Tangerang Selatan** | Ciputat       |
| Kota Tangerang Selatan     | Ciputat Timur |
| Kota Tangerang Selatan     | Pamulang      |
| Kota Tangerang Selatan     | Pondok Aren   |
| Kota Tangerang Selatan     | Serpong       |
| Kota Tangerang Selatan     | Serpong Utara |
| Kota Tangerang Selatan     | Setu          |
