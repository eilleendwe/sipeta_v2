---
title: SIPETA
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

<!-- Header di atas dibaca Hugging Face Spaces (deploy). Di GitHub cukup diabaikan. -->

# SIPETA: Sistem Pemantauan Tutupan Lahan Terbangun

Perancangan sistem pemantauan perubahan dan prediksi tutupan lahan terbangun di Kota Tangerang, Kota Tangerang Selatan, dan Kabupaten Tangerang.

**Metodologi:**
- **Data:** Menggunakan citra Sentinel-2 Level-2A.
- **Prapemrosesan:** Menggunakan *Piecewise Cubic Hermite Interpolation Polynomial* (PCHIP) untuk *cloud masking* dan mengisi *gap* tutupan awan.
- **Klasifikasi:** Menggunakan Random Forest untuk klasifikasi lahan terbangun dan nonterbangun.
- **Prediksi:** Menggunakan Convolutional LSTM untuk memprediksi perubahan lahan terbangun pada periode berikutnya pada tingkat kecamatan.

## Status

Aplikasi **pure Streamlit**: satu program, tanpa backend FastAPI. Proses berat (PCHIP, Random Forest, ConvLSTM) berjalan sebagai job latar belakang di dalam proses Streamlit. Data disimpan di PostgreSQL, berkas di folder `storage/` (lokal) atau object storage S3-compatible (deploy).

Spesifikasi tampilan ada di [SPEC.md](SPEC.md), alur klasifikasi dan ConvLSTM di [catatan_latih_klasifikasi.md](catatan_latih_klasifikasi.md), keputusan pengerjaan di [NOTES.md](NOTES.md), dan rincian migrasi dari FastAPI serta langkah deploy di [MIGRASI_STREAMLIT.md](MIGRASI_STREAMLIT.md).

## Menjalankan (lokal)

Butuh Python 3.11 dan PostgreSQL.

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Di Windows, TensorFlow (untuk ConvLSTM) hanya berjalan di CPU.

1. **Database** (sekali): buat database, lalu jalankan skema:

   ```powershell
   psql -U postgres -d sipeta -f core\schema.sql
   ```

2. **Pengaturan**: tulis di `.streamlit\secrets.toml` (tidak masuk git), atau sebagai environment variable dengan nama yang sama. Environment variable didahulukan.

   ```toml
   SIPETA_DB = "postgresql://postgres:KATASANDI@localhost:5432/sipeta"
   SIPETA_STORAGE_MODE = "lokal"
   ```

3. **Arsip anchor** (sekali, dibutuhkan PCHIP): salin citra per kecamatan ke `storage\arsip\<wilayah>\<kecamatan>\<YYYY-MM-DD>\` (minimal 7 band fitur B02, B03, B04, B05, B06, B07, B12 + SCL; nama berkas `*_B02_10m.tif` dst.; `<wilayah>` = `kota_tangerang`, `kota_tangerang_selatan`, atau `kabupaten_tangerang`; `<kecamatan>` = id kecamatan, mis. `serpong_utara`). Boleh semua tanggal atau hanya tanggal anchor. Lalu:

   ```powershell
   python -m core.daftar_arsip
   ```

4. **Arsip klasifikasi** (sekali, masukan ConvLSTM): masuk sebagai Admin, buka Prediksi → Latih Model → "Arsip klasifikasi di server", lalu unggah folder notebook `kecamatan_masked_rf_classified` (boleh juga satu folder wilayah atau kecamatan). Berkas disimpan ke `storage\arsip_klasifikasi\<wilayah>\<kecamatan>\<YYYY-MM-DD>\RF_LABEL_*.tif`; menyalin folder itu langsung ke sana juga bisa. Kecamatan yang tidak punya peta 2016–2025 lengkap tidak bisa dipakai melatih atau memprediksi. Peta tahunan dibuat otomatis saat pertama dipakai dan disimpan di `storage\cache_tahunan\`.

5. **Aplikasi**: `python -m streamlit run app.py` → <http://localhost:8501>

## Deploy online

Ringkasnya: database ke PostgreSQL cloud (Supabase/Neon), berkas ke object storage S3-compatible (mode `s3`), anchor diunggah sekali dari laptop dengan `python -m core.unggah_cloud anchor`, lalu app di Hugging Face Spaces (memakai `Dockerfile`) atau Streamlit Community Cloud. Langkah lengkapnya di [MIGRASI_STREAMLIT.md](MIGRASI_STREAMLIT.md).

## Akun awal

| Email | Kata sandi | Peran | Yang bisa dibuka |
|---|---|---|---|
| `superadmin@sipeta.test` | `Super123!` | Super Admin | Semua halaman, termasuk Kelola Pengguna |
| `admin@sipeta.test` | `Admin123!` | Admin | Semua kecuali Kelola Pengguna |
| `user@sipeta.test` | `User123!` | Pengguna | Klasifikasi citra, Prediksi citra, Pemantauan, Panduan, Tentang |

Tiga akun ini diisi oleh `core/schema.sql` ke tabel `pengguna` (tidak ditampilkan di halaman Masuk). **Ganti kata sandinya sebelum aplikasi dipakai orang lain**, terutama sebelum deploy. Akun baru dari halaman Daftar tersimpan di tabel yang sama dan selalu berperan Pengguna. Peran Admin diberikan Super Admin lewat Kelola Pengguna.

## Format citra masukan

- **Latih model**: unggah satu folder kecamatan. Nama folder = nama kecamatan, isinya subfolder per tanggal (`2019-07-04/`), masing-masing berisi B02, B03, B04, B05, B06, B07, B08, B11, B12, dan SCL.
- **Klasifikasi citra**: unggah B02, B03, B04, B05, B06, B07, B12, dan SCL dari satu tanggal.
- Semua citra kecamatan harus dipotong dari raster wilayah yang sama dengan arsip (grid sejajar, 10 m). Pemotongan dilakukan di luar web.
- **Latih model prediksi**: pilih sumber data latih. *Arsip di server* memakai arsip klasifikasi yang sudah diunggah; *Unggah folder* (seperti Latih RF) menerima folder `<kecamatan>\<YYYY-MM-DD>\RF_LABEL_*.tif` (nilai 0/1/255) yang hanya dipakai untuk pelatihan itu.
- **Prediksi citra** selalu membaca arsip klasifikasi di server (diunggah Admin lewat panel "Arsip klasifikasi di server" di Latih Model Prediksi).

## Struktur

```text
app.py            titik masuk: navigasi, sidebar, guard peran, persiapan sekali per proses
core/             logika: PCHIP, Random Forest, ConvLSTM, latih, klasifikasi, prediksi, job, storage, skema SQL
  operasi.py      semua operasi yang dipanggil services/ (pengganti endpoint FastAPI)
  storage.py      penyimpanan berkas: mode lokal (folder storage/) atau s3 (bucket + cache lokal)
  daftar_arsip.py CLI: daftarkan arsip anchor ke database
  unggah_cloud.py CLI: unggah anchor (7 band + SCL) atau folder storage/ ke bucket
pages/            satu berkas per halaman
services/         semua akses data; halaman hanya memanggil fungsi di sini (lewat services/backend.py)
storage/          arsip, model, hasil, dan berkas sementara (tidak masuk git)
ui/               komponen bersama: sidebar, tab, kartu, lencana, form, grafik, CSS
data/             authors.json (Tentang Penulis), wilayah/*.jpg (peta wilayah di Beranda)
.streamlit/       tema (config.toml) dan pengaturan lokal (secrets.toml, tidak masuk git)
Dockerfile        image untuk Hugging Face Spaces
```

Halaman tidak pernah membuat data sendiri. Semua isi `services/*` memanggil `core.operasi` lewat `services/backend.py`.

## Mengisi Tentang Penulis

Edit `data/authors.json`: `judul` (judul skripsi), `deskripsi` (daftar paragraf), dan `penulis`. Untuk foto, taruh berkas gambar di folder `data/` lalu isi `"foto"` dengan nama berkasnya, misalnya `"foto/penulis.jpg"`. Jika `"foto"` kosong, inisial nama ditampilkan.
