# Panduan Langkah demi Langkah: dari Uji Lokal sampai SIPETA Online

Panduan ini untuk pemilik proyek. Urutannya dari awal sampai akhir, dan setiap tahap selesai dulu sebelum lanjut ke tahap berikutnya. Semua layanan yang dipakai gratis.

> Tampilan dashboard Supabase, GitHub, Streamlit, dan layanan lain bisa sedikit berubah dari waktu ke waktu. Kalau nama tombol tidak persis sama, cari menu dengan arti yang sama. Batas gratis yang disebut di sini adalah kondisi Oktober 2026; cek lagi di situs resminya.

## Gambaran akhir

```
Penguji (browser) ──▶ Streamlit Community Cloud (app SIPETA, gratis; kode dari repo GitHub privat)
                            │
                            ├──▶ Supabase PostgreSQL  (akun, model, hasil, daftar anchor)
                            └──▶ Storage S3           (berkas model, hasil, citra, anchor, arsip klasifikasi)
                                   = Supabase Storage (jika total ≤ ±900 MB)
                                   atau Cloudflare R2 / Backblaze B2 (jika lebih besar)
```

| Tahap | Isi | Perkiraan waktu |
|---|---|---|
| 1 | Uji di laptop (mode lokal) | sesuai kebutuhan UAT |
| 2 | Ukur besar anchor, pilih storage | 5 menit |
| 3 | Buat database Supabase | 15 menit |
| 4 | Buat bucket storage | 15 menit |
| 5 | Siapkan berkas pengaturan cloud di laptop | 10 menit |
| 6 | Isi database dan storage cloud dari laptop | 30–90 menit (tergantung internet) |
| 7 | Uji app di laptop memakai cloud | 15 menit |
| 8 | Unggah kode ke GitHub (repo privat) | 15 menit |
| 9 | Buat app di Streamlit Community Cloud dan isi Secrets | 10 menit + instalasi ±5–15 menit |
| 10 | Amankan akun, uji online, bagikan ke penguji | 20 menit |

Semua perintah dijalankan di **PowerShell**, di folder proyek, dengan venv aktif:

```powershell
cd C:\skripsi\sipeta_v2
venv\Scripts\activate
```

> **Penting:** folder `venv` di project backup adalah salinan venv project utama. Launcher `streamlit.exe` dan `pip.exe` di dalamnya menyimpan alamat Python project utama (`C:\skripsi\sipeta\venv`), sehingga perintah `streamlit ...` atau `pip ...` biasa bisa diam-diam memakai venv project utama. Gejalanya: `ModuleNotFoundError: No module named 'psycopg_pool'`. Karena itu, selalu tulis **`python -m streamlit ...`** dan **`python -m pip ...`**. Bentuk ini selalu memakai Python dari venv yang aktif.

---

## Tahap 1: Uji di laptop (mode lokal)

Tahap ini memastikan versi pure Streamlit sudah benar sebelum ada yang di-online-kan. Database yang dipakai adalah database uji `sipeta_v2` (sudah dibuat, diatur di `.streamlit\secrets.toml`).

1. **Isi arsip anchor.** Salin folder citra ke `storage\arsip\<wilayah>\<kecamatan>\<YYYY-MM-DD>\`.
   - `<wilayah>`: `kota_tangerang`, `kota_tangerang_selatan`, atau `kabupaten_tangerang`.
   - `<kecamatan>`: id kecamatan huruf kecil dengan garis bawah, misalnya `serpong_utara`.
   - Isi tiap folder tanggal minimal B02, B03, B04, B05, B06, B07, B12, dan SCL (nama berkas `*_B02_10m.tif` dst.). B08/B11 boleh ada.
   - Boleh hanya tanggal anchor saja, atau semua tanggal.

2. **Daftarkan arsip** ke database:

   ```powershell
   python -m core.daftar_arsip
   ```

   Di akhir tiap wilayah muncul ringkasan, misalnya `Total kota_tangerang_selatan: 7 kecamatan, 25 tanggal, 25 anchor`. Jumlah anchor harus sama dengan notebook: Kota Tangerang 14, Kota Tangerang Selatan 25, Kabupaten Tangerang 13.

3. **Jalankan app** (tidak perlu uvicorn lagi):

   ```powershell
   python -m streamlit run app.py
   ```

4. **Uji semua skenario** di `Form_UAT_SIPETA.md`. Masuk dengan akun awal (`admin@sipeta.test` / `Admin123!`, `superadmin@sipeta.test` / `Super123!`). Unggah arsip klasifikasi lewat Prediksi → Latih Model → "Arsip klasifikasi di server".

5. Kalau semua lancar, lanjut ke Tahap 2. Kalau ada yang salah, perbaiki dulu di sini.

---

## Tahap 2: Ukur besar anchor dan pilih storage

```powershell
python -m core.unggah_cloud anchor --ukur
```

Perintah ini hanya menghitung, tidak mengunggah apa pun. Contoh keluaran:

```
kabupaten_tangerang: 13 tanggal anchor, 29 kecamatan, 1.850,2 MB
kota_tangerang: 14 tanggal anchor, 13 kecamatan, 410,5 MB
kota_tangerang_selatan: 25 tanggal anchor, 7 kecamatan, 520,3 MB
Total: 2.592 berkas, 2.781,0 MB
```

Tambahkan ±250 MB untuk arsip klasifikasi (222 MB), model, dan hasil. Lalu pilih:

| Total | Pilih storage | Catatan |
|---|---|---|
| ≤ ±900 MB | **Supabase Storage** (Tahap 4, Opsi A) | Satu akun dengan database. Batas gratis 1 GB. |
| > ±900 MB dan ≤ 10 GB | **Cloudflare R2** (Opsi B) atau **Backblaze B2** (Opsi C) | Gratis sampai 10 GB. R2 biasanya meminta kartu pembayaran terdaftar walau tidak ditagih. |

**Catat angka total ini.**

---

## Tahap 3: Buat database Supabase

1. Buka <https://supabase.com>, lalu **Start your project**. Daftar dengan akun GitHub atau email.
2. **New project**:
   - **Name**: `sipeta`.
   - **Database Password**: buat kata sandi yang kuat **tanpa** karakter `@ : / ? # %`, karena karakter ini merusak connection string. Contoh pola yang aman: huruf, angka, dan `_` atau `-`. **Catat kata sandinya.**
   - **Region**: pilih yang terdekat, misalnya *Southeast Asia (Singapore)*.
   - Plan **Free**, lalu **Create new project**. Tunggu ±2 menit.
3. **Jalankan skema**:
   - Buka menu **SQL Editor**, lalu **New query**.
   - Buka berkas `core\schema.sql` di VS Code, salin **seluruh** isinya, tempel ke SQL Editor, lalu tekan **Run**.
   - Harus muncul *Success*. Cek di menu **Table Editor**: ada tabel `pengguna` (3 baris), `wilayah`, `kecamatan` (49 baris), `citra_arsip`, `model_klasifikasi`, `hasil_klasifikasi`, `model_prediksi`, dan `hasil_prediksi`.
4. **Ambil connection string**:
   - Tekan tombol **Connect** di bagian atas project.
   - Pilih **Session pooler**, bukan *Direct connection*. Koneksi langsung Supabase hanya lewat IPv6, sedangkan Streamlit Cloud, Hugging Face, dan banyak jaringan rumah hanya IPv4.
   - Salin URI-nya. Bentuknya kira-kira:

     ```
     postgresql://postgres.abcdefghijkl:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
     ```

   - Ganti `[YOUR-PASSWORD]` dengan kata sandi database (tanpa kurung siku), lalu tambahkan `?sslmode=require` di akhir.
   - **Catat sebagai `SIPETA_DB`.**

> Project Supabase gratis di-*pause* jika ±1 minggu tidak dipakai. Datanya tidak hilang. Kalau web menampilkan "Database tidak dapat diakses", buka dashboard Supabase lalu tekan **Restore project**.

---

## Tahap 4: Buat bucket storage

Pilih **satu** opsi sesuai hasil Tahap 2.

### Opsi A: Supabase Storage (total ≤ ±900 MB)

1. Di project Supabase yang sama, buka menu **Storage**, lalu **New bucket**.
   - Name: `sipeta`.
   - **Public bucket: matikan** (bucket privat).
   - **Create**.
2. Buka **Storage → Settings** (bagian *S3 Connection* / *S3 Access Keys*):
   - Pastikan **S3 connection** aktif.
   - Catat **Endpoint** (bentuknya `https://abcdefghijkl.supabase.co/storage/v1/s3`) sebagai `SIPETA_S3_ENDPOINT`.
   - Catat **Region** (misalnya `ap-southeast-1`) sebagai `SIPETA_S3_REGION`.
   - Tekan **New access key**, beri nama `sipeta`. Catat **Access key ID** sebagai `SIPETA_S3_KEY` dan **Secret access key** sebagai `SIPETA_S3_SECRET`. Secret hanya ditampilkan sekali.
3. `SIPETA_S3_BUCKET` = `sipeta`.

### Opsi B: Cloudflare R2 (sampai 10 GB)

1. Daftar di <https://dash.cloudflare.com>, lalu buka **R2 Object Storage**. Cloudflare biasanya meminta kartu pembayaran untuk mengaktifkan R2; pemakaian di bawah 10 GB tidak ditagih.
2. **Create bucket**: nama `sipeta`, lokasi otomatis, lalu **Create**.
3. **Manage API tokens** (di halaman R2), lalu **Create API token**:
   - Permission **Object Read & Write**, berlaku untuk bucket `sipeta`.
   - **Create**. Catat **Access Key ID** (`SIPETA_S3_KEY`), **Secret Access Key** (`SIPETA_S3_SECRET`), dan endpoint **S3 API** (`https://<account-id>.r2.cloudflarestorage.com`, tanpa nama bucket di belakangnya) sebagai `SIPETA_S3_ENDPOINT`.
4. `SIPETA_S3_BUCKET` = `sipeta`, `SIPETA_S3_REGION` = `auto`.

### Opsi C: Backblaze B2 (sampai 10 GB)

1. Daftar di <https://www.backblaze.com/cloud-storage>, lalu buka **B2 Cloud Storage → Buckets → Create a Bucket**:
   - Nama unik, misalnya `sipeta-eilleen`.
   - **Private**, lalu **Create**.
2. Di daftar bucket, catat **Endpoint** (misalnya `s3.us-west-004.backblazeb2.com`):
   - `SIPETA_S3_ENDPOINT` = `https://s3.us-west-004.backblazeb2.com`.
   - `SIPETA_S3_REGION` = `us-west-004` (bagian tengah endpoint).
3. **Application Keys → Add a New Application Key**:
   - Akses **Read and Write**, hanya untuk bucket tadi.
   - Catat **keyID** (`SIPETA_S3_KEY`) dan **applicationKey** (`SIPETA_S3_SECRET`). Hanya ditampilkan sekali.
4. `SIPETA_S3_BUCKET` = nama bucket tadi.

---

## Tahap 5: Siapkan berkas pengaturan cloud di laptop

Supaya tidak mengetik ulang, simpan semua nilai dari Tahap 3–4 di satu berkas. Berkas ini **rahasia** dan sudah dikecualikan dari git dan Docker.

1. Buat berkas `C:\skripsi\sipeta_v2\cloud.ps1` berisi (ganti nilainya):

   ```powershell
   # Pengaturan cloud SIPETA. RAHASIA: jangan dibagikan atau diunggah.
   $env:SIPETA_DB = "postgresql://postgres.abcdefghijkl:SANDI@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require"
   $env:SIPETA_STORAGE_MODE = "s3"
   $env:SIPETA_S3_ENDPOINT = "https://abcdefghijkl.supabase.co/storage/v1/s3"
   $env:SIPETA_S3_BUCKET = "sipeta"
   $env:SIPETA_S3_KEY = "isi-access-key"
   $env:SIPETA_S3_SECRET = "isi-secret-key"
   $env:SIPETA_S3_REGION = "ap-southeast-1"
   ```

2. Cara memakainya: buka jendela PowerShell **baru**, masuk ke folder proyek, aktifkan venv, lalu muat berkas itu. Ada titik dan spasi di depannya:

   ```powershell
   cd C:\skripsi\sipeta_v2
   venv\Scripts\activate
   . .\cloud.ps1
   ```

   - Jika muncul galat *running scripts is disabled*, jalankan dulu `Set-ExecutionPolicy -Scope Process Bypass`. Ini hanya berlaku untuk jendela itu.
   - Pengaturan ini hanya berlaku di jendela PowerShell tersebut. Jendela lain, termasuk `streamlit run` biasa, tetap memakai database uji lokal dari `secrets.toml`.

3. Cek koneksi database:

   ```powershell
   python -c "from core import db; print(db.fetch_one('select count(*) as n from kecamatan'))"
   ```

   Harus tercetak `{'n': 49}`.

---

## Tahap 6: Isi database dan storage cloud dari laptop

Masih di jendela PowerShell yang sudah memuat `cloud.ps1`:

1. **Daftarkan anchor ke database cloud.** Skrip membaca `storage\arsip\` di laptop dan menulis ke Supabase:

   ```powershell
   python -m core.daftar_arsip
   ```

   Ringkasan jumlah anchor harus sama dengan Tahap 1.

2. **Unggah anchor** (hanya tanggal anchor, 7 band + SCL):

   ```powershell
   python -m core.unggah_cloud anchor --ukur
   python -m core.unggah_cloud anchor
   ```

   Lamanya tergantung internet. Kalau terputus, jalankan ulang perintah yang sama; berkas yang sudah terunggah dilewati.

3. **Unggah arsip klasifikasi** (masukan ConvLSTM). Pilih satu cara:
   - Dari laptop, jika folder `storage\arsip_klasifikasi\` sudah terisi (misalnya dari Tahap 1):

     ```powershell
     python -m core.unggah_cloud folder arsip_klasifikasi
     ```

   - Atau nanti lewat web online: Prediksi → Latih Model → "Arsip klasifikasi di server".

4. **Cek di dashboard storage**: bucket `sipeta` sekarang berisi folder `arsip/` dan (jika langkah 3 dilakukan) `arsip_klasifikasi/`.

> Model RF/ConvLSTM dan hasil yang dibuat saat Tahap 1 **tidak** ikut ke cloud, karena database lokal dan cloud terpisah. Latih ulang lewat web setelah online.

---

## Tahap 7: Uji app di laptop memakai cloud

Tahap ini memastikan database dan bucket cloud benar sebelum deploy. Kalau ada masalah, lebih mudah dicari di laptop daripada di server online.

Di jendela PowerShell yang sudah memuat `cloud.ps1`:

```powershell
$env:SIPETA_STORAGE = "C:\skripsi\cache_cloud"   # folder cache terpisah, supaya storage\ lokal tidak tercampur
python -m streamlit run app.py
```

Lalu coba:
1. Masuk sebagai `admin@sipeta.test` / `Admin123!`.
2. Latih model RF kecil (misalnya jumlah pohon 5), lalu **Simpan model**.
3. Klasifikasi citra berawan pada kecamatan yang punya anchor. Persentase awan yang **terisi PCHIP** harus muncul, bukan peringatan "arsip belum didaftarkan". Lalu **Simpan hasil**.
4. Cek di dashboard storage: muncul folder `model/`, `hasil/`, dan `citra/`.
5. Hentikan app (Ctrl+C), **hapus folder `C:\skripsi\cache_cloud`**, lalu jalankan lagi. Buka Pemantauan atau klasifikasi lagi; semuanya harus tetap ada. Ini sama dengan kondisi saat app online di-restart.

Kalau semua lancar, cloud sudah siap.

---

## Tahap 8: Unggah kode ke GitHub (repo privat)

Streamlit Community Cloud mengambil kode dari GitHub. Repo dibuat **privat**, jadi kode skripsimu tidak terlihat orang lain, tetapi app-nya tetap bisa dibuka publik.

1. **Buat akun GitHub** di <https://github.com/signup> (lewati jika sudah punya).
2. **Atur identitas git** (sekali saja, jika belum pernah):

   ```powershell
   git config --global user.name "Eilleen"
   git config --global user.email "eilleen309@gmail.com"
   ```

3. **Buat repo kosong** di <https://github.com/new>:
   - Repository name: `sipeta`.
   - Pilih **Private**.
   - **Jangan** centang *Add a README*, *.gitignore*, atau *license*, karena semuanya sudah ada di proyek.
   - **Create repository**.
4. **Jadikan folder proyek repo git**, lalu periksa berkas yang akan diunggah:

   ```powershell
   cd C:\skripsi\sipeta_v2
   git init -b main
   git add .
   git status
   ```

   Periksa daftar `git status`. Yang **tidak boleh** muncul: `venv/`, `storage/`, `.streamlit/secrets.toml`, dan `cloud.ps1`. Semuanya sudah dikecualikan lewat `.gitignore`. Kalau salah satunya muncul, berhenti dan tanyakan dulu.
5. **Commit dan push.** Ganti `USERNAME` dengan username GitHub-mu:

   ```powershell
   git commit -m "SIPETA pure Streamlit"
   git remote add origin https://github.com/USERNAME/sipeta.git
   git push -u origin main
   ```

   Saat push pertama, Windows membuka jendela login GitHub. Pilih **Sign in with your browser**, lalu izinkan.
6. Buka `https://github.com/USERNAME/sipeta`. Berkas proyek sudah ada di sana, dan di samping nama repo tertulis **Private**.

**Kalau nanti mengubah kode**, cukup jalankan:

```powershell
git add .
git commit -m "jelaskan perubahannya"
git push
```

Streamlit Cloud akan memperbarui app secara otomatis.

> Project backup ini dipakai untuk uji coba. Setelah perubahan dipindahkan ke project utama (`C:\skripsi\sipeta`), project utama bisa di-push ke repo yang sama sebagai gantinya. App online tetap memakai database dan bucket yang sama.

---

## Tahap 9: Buat app di Streamlit Community Cloud dan isi Secrets

1. Buka <https://share.streamlit.io>, lalu **Continue with GitHub**. Izinkan Streamlit mengakses repo GitHub-mu, **termasuk repo privat** (Streamlit meminta izin tambahan untuk repo privat; setujui).
2. Tekan **Create app**, lalu pilih deploy dari repo GitHub yang sudah ada.
   - **Repository**: `USERNAME/sipeta`.
   - **Branch**: `main`.
   - **Main file path**: `app.py`.
   - **App URL**: isi nama yang mudah diingat, misalnya `sipeta-tangerang`. Alamatnya menjadi `https://sipeta-tangerang.streamlit.app`.
3. Buka **Advanced settings**:
   - **Python version**: **3.11**. Versi Python tidak bisa diganti setelah deploy kecuali app dihapus dan dibuat ulang, jadi pastikan benar.
   - **Secrets**: tempel isi berikut. Nilainya sama dengan `cloud.ps1`, tetapi formatnya TOML: `NAMA = "nilai"`, tanpa `$env:`.

     ```toml
     SIPETA_DB = "postgresql://postgres.abcdefghijkl:SANDI@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
     SIPETA_STORAGE_MODE = "s3"
     SIPETA_S3_ENDPOINT = "https://s3.eu-central-003.backblazeb2.com"
     SIPETA_S3_BUCKET = "sipeta"
     SIPETA_S3_KEY = "isi-key-id"
     SIPETA_S3_SECRET = "isi-application-key"
     SIPETA_S3_REGION = "eu-central-003"
     ```

   - **Save**.
4. Tekan **Deploy**. Layar menampilkan log instalasi. Pemasangan pertama ±5–15 menit karena TensorFlow besar. Setelah selesai, halaman Landing SIPETA tampil.
5. **Buat app bisa dibuka penguji.** App dari repo privat bisa saja hanya bisa dibuka akun yang diundang. Buka tombol **Share** di kanan atas app, lalu atur supaya app **public** (siapa pun yang punya link bisa membuka). Atau undang email penguji satu per satu.
6. Untuk melihat log atau me-restart app, buka **Manage app** di kanan bawah halaman app (hanya terlihat oleh pemilik), lalu pilih **Reboot app** jika perlu. Secrets bisa diubah lewat menu **⋮ → Settings → Secrets** di <https://share.streamlit.io>.

**Batas Streamlit Community Cloud yang perlu diingat:** RAM ±2,7 GB. TensorFlow baru dimuat saat Latih Prediksi atau Prediksi Citra pertama kali dipakai. Latih RF dengan unggah folder kecamatan besar (Kabupaten Tangerang) bisa melewati batas ini. Kalau app sering mati saat latih, pindah ke Hugging Face (Lampiran) tanpa mengubah database dan bucket.

---

## Tahap 10: Amankan akun, uji online, bagikan ke penguji

1. **Buat akun pemilik**: buka app online, lalu **Daftar** dengan email dan kata sandi sendiri.
2. **Jadikan Super Admin**: keluar, masuk sebagai `superadmin@sipeta.test` / `Super123!`, buka **Kelola Pengguna**, lalu ubah peran akunmu menjadi Super Admin.
3. **Hapus akun awal.** Kata sandinya tertulis di README. Di Supabase, buka **SQL Editor** dan jalankan:

   ```sql
   DELETE FROM pengguna WHERE email LIKE '%@sipeta.test';
   ```

   Lalu masuk ke web dengan akunmu sendiri.
4. **Buat akun Admin untuk penguji** yang perlu Skenario 4 dan 6 UAT (latih model): minta mereka mendaftar, lalu ubah perannya menjadi Admin lewat Kelola Pengguna.
5. **Latih dan simpan** minimal satu model RF dan satu model ConvLSTM, supaya penguji berperan Pengguna punya model untuk Klasifikasi dan Prediksi. Sebaiknya pakai kecamatan Kota Tangerang atau Tangsel yang lebih kecil, supaya tidak kena batas RAM.
6. **Unggah arsip klasifikasi** jika belum dilakukan di Tahap 6: Prediksi → Latih Model → "Arsip klasifikasi di server".
7. **Bagikan alamat** `https://sipeta-tangerang.streamlit.app` (sesuai App URL-mu) beserta Form UAT ke penguji.

---

## Pemeliharaan

| Kejadian | Yang terjadi | Yang dilakukan |
|---|---|---|
| App tidak dibuka beberapa waktu | App tidur | Pengunjung berikutnya melihat tombol untuk membangunkan app (*Yes, get this app back up!*), lalu menunggu ±1–3 menit. |
| Supabase tidak dipakai ±1 minggu | Database di-*pause* | Dashboard Supabase → **Restore project**. |
| Mengubah kode | | `git add .`, `git commit -m "..."`, `git push`. App diperbarui otomatis. |
| Menambah arsip klasifikasi | | Lewat web: Prediksi → Latih Model → "Arsip klasifikasi di server". |
| Menambah anchor/kecamatan | | Tambah berkas di `storage\arsip\` laptop, muat `cloud.ps1`, lalu ulangi Tahap 6 langkah 1–2. |
| Pelatihan sedang berjalan lalu app restart | Job hilang | Latih ulang. Yang sudah disimpan tetap aman. |

## Jika ada masalah

| Gejala | Kemungkinan penyebab | Solusi |
|---|---|---|
| "Database tidak dapat diakses" | Supabase di-pause, connection string salah, atau kata sandi mengandung `@ : / ? # %` | Restore project. Cek `SIPETA_DB`: pakai **Session pooler**, sertakan `?sslmode=require`. Ganti kata sandi database jika perlu. |
| `invalid sslmode value` | Salah ketik di `SIPETA_DB` | Harus `?sslmode=require`. Di laptop, muat ulang `cloud.ps1` setelah mengubahnya. |
| "Mode storage s3 butuh pengaturan: …" | Ada Secret yang belum diisi | Tambahkan di Secrets, lalu **Reboot app**. |
| `ValueError: Invalid endpoint` | Endpoint salah format | Tulis endpoint lengkap, mis. `https://s3.eu-central-003.backblazeb2.com`. |
| "Berkas tidak ditemukan di storage" | Berkas belum diunggah, atau bucket/endpoint/region salah | Ulangi Tahap 6; cek `SIPETA_S3_BUCKET`, `SIPETA_S3_ENDPOINT`, `SIPETA_S3_REGION`. |
| Klasifikasi memberi peringatan "arsip … belum didaftarkan" | Anchor kecamatan itu belum ada di database cloud | Tahap 6 langkah 1 (`daftar_arsip` dengan `cloud.ps1` dimuat). |
| *This app has gone over its resource limits* | RAM ±2,7 GB terlampaui (biasanya saat Latih RF kecamatan besar) | **Reboot app**. Latih dengan kecamatan lebih kecil atau sampel per tanggal lebih sedikit; jangan pakai "Pakai seluruh piksel". Jika tetap sering terjadi, pindah ke Hugging Face (Lampiran). |
| Gagal saat memasang requirements | Lihat log di **Manage app** | Pastikan Python 3.11 dipilih. Salin pesan galatnya untuk dicari penyebabnya. |
| Secrets tidak terbaca | Format TOML salah | Setiap baris `NAMA = "nilai"`, nilai diapit tanda kutip ganda. |
| `git push` ditolak | Belum login GitHub atau remote salah | Ulangi `git push -u origin main` dan login lewat browser; cek `git remote -v`. |
| `ModuleNotFoundError: No module named 'psycopg_pool'` di laptop | Memakai `streamlit`/`pip` dari venv project utama | Pakai `python -m streamlit run app.py` dan `python -m pip ...`. |

## Lembar catatan (isi sendiri, simpan secara pribadi)

```
Supabase project       : ____________________
Kata sandi database    : ____________________
SIPETA_DB              : ____________________
Storage                : Backblaze B2
SIPETA_S3_ENDPOINT     : ____________________
SIPETA_S3_BUCKET       : ____________________
SIPETA_S3_REGION       : ____________________
SIPETA_S3_KEY          : ____________________
SIPETA_S3_SECRET       : ____________________
Username GitHub        : ____________________
Repo                   : https://github.com/__________/sipeta (Private)
Alamat app             : https://__________.streamlit.app
```

---

## Lampiran: Hugging Face Spaces (alternatif jika RAM Streamlit Cloud tidak cukup)

Hugging Face Spaces gratis dengan RAM 16 GB, tetapi Space harus **Public** supaya penguji bisa membuka, sehingga kode sumber terlihat publik. Database dan bucket tetap sama, tidak ada data yang perlu dipindah.

1. Daftar di <https://huggingface.co/join>, lalu verifikasi email.
2. **Access token**: foto profil → **Settings → Access Tokens → Create new token**, tipe **Write**. Token ini menjadi "kata sandi" git.
3. **Buat Space** di <https://huggingface.co/new-space>: nama `sipeta`, SDK **Docker** (template Blank), hardware **CPU basic · 2 vCPU · 16 GB · FREE**, **Public**.
4. **Settings → Variables and secrets → New secret**: tambahkan ketujuh pengaturan yang sama dengan Secrets Streamlit (nama sama, nilai tanpa tanda kutip). Pakai *New secret*, bukan *New variable*.
5. **Unggah kode** (Hugging Face menolak gambar tanpa Git LFS):

   ```powershell
   cd C:\skripsi
   git clone https://huggingface.co/spaces/USERNAME_HF/sipeta sipeta-space
   robocopy C:\skripsi\sipeta_v2 C:\skripsi\sipeta-space /E /XD venv storage __pycache__ .claude .vscode .git docs /XF secrets.toml cloud.ps1 *.ipynb *.pyc
   cd C:\skripsi\sipeta-space
   git lfs install
   git lfs track "*.png" "*.jpg" "*.jpeg"
   git add .
   git commit -m "Deploy SIPETA"
   git push
   ```

   Login git: username Hugging Face, password = token. Robocopy dengan kode keluar 1 berarti berhasil.
6. Build ±10–15 menit (memakai `Dockerfile`). Alamatnya `https://USERNAME_HF-sipeta.hf.space`. Space tidur setelah ±48 jam tanpa pengunjung.
7. Jika `git push` ditolak karena *binary files*: `git add .gitattributes`, `git rm --cached -r .`, `git add .`, `git commit`, lalu `git push`. Jika unggahan berkas di web gagal (403), buka app langsung di alamat `.hf.space` (Dockerfile sudah menonaktifkan proteksi XSRF untuk iframe).
