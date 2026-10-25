# Migrasi SIPETA ke pure Streamlit (tanpa FastAPI)

Dikerjakan di project backup `c:\skripsi\sipeta_v2` pada 25 Oktober 2026 sebagai uji coba sebelum diterapkan ke project utama (`c:\skripsi\sipeta`).

Dokumen ini punya dua bagian:

- **Bagian A** untuk Claude (atau siapa pun) yang memindahkan perubahan ke project utama: daftar perubahan per berkas dan cara memindahkannya.
- **Bagian B** untuk pemilik proyek: langkah uji lokal dan langkah deploy online.

## Ringkasan

| | Sebelum | Sesudah |
|---|---|---|
| Program yang dijalankan | `uvicorn api.main:app` + `streamlit run app.py` | `streamlit run app.py` saja |
| Logika (PCHIP, RF, ConvLSTM) | `api/` dipanggil lewat HTTP | `core/` dipanggil langsung |
| Job latar belakang | thread di proses FastAPI | thread di proses Streamlit (perilaku sama) |
| Berkas permanen | folder `storage/` | `core/storage.py`: mode `lokal` (folder `storage/`) atau `s3` (bucket + cache lokal) |
| Database | PostgreSQL lokal, satu koneksi per query | PostgreSQL lokal atau cloud, lewat connection pool |
| Pengaturan | env `SIPETA_DB`, `SIPETA_STORAGE`, `SIPETA_API` | env atau `.streamlit/secrets.toml` (lihat B.2) |
| Fitur dan tampilan | | **tidak berubah** |

---

# Bagian A: daftar perubahan dan cara memindahkannya

## A.1 Cara memindahkan ke project utama

1. Pastikan project utama tidak sedang menjalankan uvicorn/streamlit.
2. Bandingkan dulu berkas project utama dengan berkas yang disebut di A.2. Project ini adalah salinan project utama, jadi sebelum migrasi isinya sama. Jika ada berkas yang sudah diubah di project utama setelah backup dibuat, gabungkan manual: terapkan perubahan di A.2 ke versi project utama, jangan ditimpa begitu saja.
3. Jika tidak ada perbedaan, cara tercepat adalah menyalin berkas dari backup ini. Kecualikan:
   - `.streamlit/secrets.toml` (khusus backup, mengarah ke database uji `sipeta_v2`),
   - `venv/`, `storage/`, dan `__pycache__/`.
4. Hapus berkas yang ditandai **hapus** di A.2.
5. `pip install -r requirements.txt` di venv project utama (paket baru: `psycopg-pool`, `boto3`).
6. Tanpa `secrets.toml`, `core/config.py` memakai bawaan `postgresql://postgres:lambo@localhost:5432/sipeta`, yaitu database project utama. Database tidak perlu diubah karena skema sama persis.
7. Jalankan `python -m streamlit run app.py`, lalu periksa halaman-halaman seperti di A.4.

## A.2 Perubahan per berkas

### Folder `api/` diganti nama menjadi `core/`

Folder itu tidak lagi berisi API. Semua `from api import ...` / `from api.x import ...` diganti `from core ...`, dan `python -m api.daftar_arsip` menjadi `python -m core.daftar_arsip` (termasuk di docstring, pesan, dan `schema.sql`). Nama fungsi di dalamnya tidak berubah, jadi rujukan di skripsi cukup mengganti `api/` menjadi `core/`.

### `core/` (dulu `api/`)

| Berkas | Aksi | Isi perubahan |
|---|---|---|
| `main.py` | **hapus** | Diganti `core/operasi.py`. |
| `operasi.py` | baru | Satu fungsi per endpoint `main.py`, logika dan query SQL sama. `HTTPException` diganti `ProsesError`. Unggahan berupa list `(nama berkas dengan subfolder, isi bytes)`, bukan `UploadFile`. Validasi pydantic tetap (`ParamLatih`, `ParamPrediksi`), ditambah cek nama model 1–100 karakter dan minimal satu kecamatan (dulu lewat model pydantic `SimpanModel`/`LatihPrediksi`). `lifespan` FastAPI menjadi `siapkan()`. Semua penyimpanan berkas permanen lewat `core.storage` (lihat tabel A.3). |
| `pengguna.py` | ubah | `APIRouter`, `HTTPException`, dan model pydantic dibuang. Fungsi menerima argumen biasa: `daftar(nama, email, password)`, `masuk(email, password)`, `daftar_pengguna(cari, peran)`, `detail(id)`, `ubah_peran(id, peran, oleh)`. Pesan galat dan aturan peran sama. Ditambah cek panjang nama (≤ 100) dan email (≤ 150), yang dulu dilakukan pydantic. |
| `storage.py` | baru | Lapisan penyimpanan: `ambil`, `ambil_folder`, `kirim`, `hapus`, `daftar`, `relatif`, `periksa`. Mode `lokal` = semua hanya di folder `STORAGE`. Mode `s3` = bucket S3-compatible (boto3) dengan kunci = path relatif terhadap `STORAGE` (sama dengan kolom `path_*` di database), dan folder `STORAGE` menjadi cache. Klien boto3 memakai path-style addressing (diwajibkan Supabase Storage), checksum `when_required` (checksum bawaan botocore baru belum didukung semua layanan S3-compatible), dan retry 5 kali. |
| `config.py` | ubah | `_pengaturan(nama, bawaan)`: baca environment variable, lalu `.streamlit/secrets.toml` di folder proyek (dibaca langsung dengan `tomllib`, karena `st.secrets` hanya mencari di folder kerja, jadi perintah dari folder lain jatuh ke nilai bawaan), lalu `st.secrets` (Streamlit Community Cloud), lalu bawaan. `_ENV = dict(os.environ)` disalin saat import, karena membaca `st.secrets` menimpa `os.environ` dengan isi secrets.toml. `S3_ENDPOINT` tanpa skema diberi `https://` (dashboard B2/R2 sering menampilkan endpoint tanpa skema). `tujuan_db(url)`: host:port/database tanpa kata sandi, dicetak `daftar_arsip` dan `unggah_cloud` sebelum mulai. Pengaturan baru: `STORAGE_MODE`, `S3_ENDPOINT`, `S3_BUCKET`, `S3_KEY`, `S3_SECRET`, `S3_REGION`. Komentar `ARSIP_DIR` diperbaiki (ada `<kecamatan>`). |
| `db.py` | ubah | `psycopg_pool.ConnectionPool` (min 1, maks 4, timeout 15 s, `prepare_threshold=None` untuk pooler Supabase, `check_connection`). API `fetch_all`/`fetch_one`/`execute`/`json` sama. |
| `jobs.py` | ubah | `ProsesError(pesan, fields=None)`: bisa membawa galat per field form (dipakai pendaftaran: email ganda). Docstring: job kini di proses Streamlit. |
| `citra.py` | ubah | `muat_anchor`: folder anchor diambil lewat `storage.ambil_folder(...)`. Import `storage`. |
| `klasifikasi.py` | ubah | `muat_model`/`muat_config` lewat `storage.ambil(path)`, bukan `STORAGE / path`. Pesan "arsip belum didaftarkan" menyebut `python -m core.unggah_cloud anchor` untuk versi online. |
| `prediksi.py` | ubah | `muat_model`/`muat_config` lewat `storage.ambil(path)`. |
| `peta_tahunan.py` | ubah | `muat()` mengambil folder kecamatan lewat `storage.ambil_folder` dulu. Fungsi baru `tahun_arsip()`: tahun per `(wilayah, kecamatan)` dari daftar berkas storage, tanpa mengunduh peta. `daftar_berkas` memakai `RF_LABEL_RE` (bukan `glob("RF_LABEL_*.tif")`), supaya sama dengan pengecekan saat unggah di Linux yang peka huruf besar/kecil. |
| `daftar_arsip.py` | ubah | Wajib berkas = `FITUR` (7 band) + SCL, bukan `BANDS_LATIH` (9 band) + SCL. B08/B11 tidak dibaca Klasifikasi. Penentuan anchor sama (persentase awan wilayah per tanggal). Docstring menjelaskan bahwa folder boleh hanya berisi tanggal anchor. |
| `unggah_cloud.py` | baru | CLI: `anchor [--ukur] [--kecamatan ...]` mengunggah hanya tanggal `is_anchor` dengan 7 band + SCL. `folder <nama> [--ukur]` mengunggah satu subfolder `storage/` apa adanya. Berkas yang sudah ada di bucket dengan ukuran sama dilewati. |
| `schema.sql` | ubah | Komentar saja (`api/` menjadi `core/`). |
| `operasi.py` (lanjutan) | ubah | Modul yang memuat TensorFlow (`convlstm`, `latih_prediksi`, `prediksi`) diimpor di dalam fungsi yang memakainya, dan `ParamPrediksi` dibuat lewat `_param_prediksi()` (`lru_cache`). App menyala tanpa TensorFlow (±0,2–0,4 GB RAM dan ±10 detik lebih hemat) sampai Latih Prediksi/Prediksi Citra dipakai. Penting untuk Streamlit Community Cloud (RAM ±2,7 GB). |
| `__init__.py` | ubah | `TF_CPP_MIN_LOG_LEVEL=2` sebelum TensorFlow diimpor: TensorFlow kini dimuat di proses Streamlit, jadi log INFO/WARNING C++-nya ikut tampil di terminal Streamlit. Pesan oneDNN saat import tetap muncul (tidak bisa disembunyikan tanpa mematikan oneDNN). |
| `convlstm.py` | ubah | `tf.get_logger().setLevel("ERROR")`: menyembunyikan peringatan deprecation dari dalam Keras (`tf.reset_default_graph`). |
| `requirements.txt` | **hapus** | Digabung ke `requirements.txt` di root. |

### Endpoint lama → fungsi baru

| Endpoint FastAPI | `core.operasi` / `core.pengguna` |
|---|---|
| `GET /wilayah` | `operasi.daftar_wilayah()` |
| `GET /jobs/{id}`, `DELETE /jobs/{id}` | `operasi.status_job(id)`, `operasi.buang_job(id)` |
| `POST /latih` | `operasi.mulai_latih(kecamatan_id, params, files)` |
| `POST /model`, `GET /model`, `GET /model/{id}` | `operasi.simpan_model(job_id, nama, dibuat_oleh)`, `daftar_model(kecamatan_id)`, `detail_model(id)` |
| `POST /klasifikasi`, `GET /klasifikasi/{job}/{nama}` | `operasi.mulai_klasifikasi(model_id, kecamatan_id, tanggal, files)`, `berkas_klasifikasi(job_id, nama)` |
| `POST /hasil`, `GET /hasil`, `GET /hasil/{id}/klasifikasi.tif` | `operasi.simpan_hasil(job_id, oleh)`, `daftar_hasil(kec, model)`, `unduh_hasil(id)` |
| `GET /pemantauan` | `operasi.bandingkan(awal, akhir)` |
| `GET /arsip-klasifikasi`, `POST /arsip-klasifikasi/{id}` | `operasi.arsip_klasifikasi()`, `unggah_arsip_klasifikasi(kecamatan_id, files)` |
| `POST /latih-prediksi`, `POST /latih-prediksi/unggah` | `operasi.mulai_latih_prediksi(kecamatan_ids, params)`, `mulai_latih_prediksi_unggah(params, files)` |
| `POST /model-prediksi`, `GET /model-prediksi[/{id}]` | `operasi.simpan_model_prediksi(...)`, `daftar_model_prediksi(kec)`, `detail_model_prediksi(id)` |
| `POST /prediksi`, `GET /prediksi/{job}/{nama}` | `operasi.mulai_prediksi(model_id, kecamatan_id, tahun)`, `berkas_prediksi(job_id, nama)` |
| `POST /hasil-prediksi`, `GET /hasil-prediksi/{id}/prediksi.tif` | `operasi.simpan_hasil_prediksi(job_id, oleh)`, `unduh_hasil_prediksi(id)` |
| `POST /pengguna`, `POST /masuk`, `GET /pengguna[/{id}]`, `PUT /pengguna/{id}/peran` | `pengguna.daftar`, `masuk`, `daftar_pengguna` / `detail`, `ubah_peran` |

### `services/`

| Berkas | Aksi | Isi perubahan |
|---|---|---|
| `api_client.py` | **hapus** | Diganti `backend.py`. |
| `backend.py` | baru | `panggil(fungsi, *args)` menjalankan fungsi core dan mengubah galat menjadi `ServiceError`: `ProsesError` (pesan + fields), `psycopg.Error` ("Database tidak dapat diakses: …"), `FileNotFoundError`, dan galat lain (dicatat di log, pesan ringkas). Hasil selain bytes dibentuk ulang lewat JSON round-trip (tanggal → ISO, tuple → list, kunci → teks), jadi bentuk datanya sama persis dengan respons API lama. `pantau_job(job_id, jeda)` sama dengan versi `api_client`. Pada `PoolTimeout` (pool hanya melapor "couldn't get a connection after 15 sec"), satu koneksi langsung dicoba untuk mengambil sebab aslinya, lalu pesan galat menyebut host:port/database tujuan (tanpa kata sandi) dan sebab itu. |
| `auth.py` | ubah | `api_client.get/post/put` diganti `backend.panggil(pengguna.<fungsi>, ...)`. |
| `regions.py` | ubah | `backend.panggil(operasi.daftar_wilayah)`. |
| `models.py` | ubah | Peta endpoint `_ENDPOINT` diganti `_DAFTAR`/`_DETAIL`/`_SIMPAN` (fungsi `operasi`). `_dari_backend` diganti nama menjadi `_dari_baris`. `_berkas_rf` mengembalikan `(nama, isi)`. `import json` dibuang. Label progres awal "Mengunggah … ke server…" menjadi "Menyiapkan … berkas citra…" / "Memeriksa … peta klasifikasi…". |
| `classify.py`, `predict.py` | ubah | Mulai job, ambil PNG/GeoTIFF, simpan, dan unduh lewat `operasi`. Label "Mengunggah citra ke server…" menjadi "Menyiapkan citra…". |
| `monitoring.py` | ubah | `operasi.daftar_hasil`, `operasi.bandingkan`. |
| `arsip.py` | ubah | `operasi.arsip_klasifikasi`, `operasi.unggah_arsip_klasifikasi`. `kemas_berkas` mengembalikan `(path, isi)`. |

Halaman (`pages/`) dan komponen (`ui/`) **tidak diubah**.

### Root

| Berkas | Aksi | Isi perubahan |
|---|---|---|
| `app.py` | ubah | `_siapkan()` dengan `@st.cache_resource` memanggil `operasi.siapkan()` sekali per proses (pengganti `lifespan`). `RuntimeError` dari pengaturan storage ditampilkan sebagai galat. |
| `requirements.txt` | tulis ulang | UTF-8 (dulu UTF-16, berisi paket tak terpakai seperti yfinance dan fastapi). Satu berkas untuk lokal dan deploy, versi terkunci sesuai venv: streamlit, altair, pandas, numpy, scipy, pillow, rasterio, pydantic, psycopg[binary], psycopg-pool, tensorflow, boto3. |
| `Dockerfile`, `.dockerignore` | baru | Image untuk Hugging Face Spaces (port 7860, user 1000, `--server.enableXsrfProtection=false` supaya unggahan di iframe Spaces tidak ditolak 403). |
| `.gitignore` | baru | `venv/`, `__pycache__/`, `storage/`, `.streamlit/secrets.toml`, `.claude/`, `.vscode/`, `cloud.ps1` (berkas pengaturan cloud lokal dari `PANDUAN_DEPLOY.md`; `.dockerignore` juga mengecualikannya). |
| `PANDUAN_DEPLOY.md` | baru | Panduan langkah demi langkah untuk pemilik proyek: uji lokal, Supabase, bucket, unggah data, Hugging Face Spaces. |
| `.streamlit/secrets.toml` | baru, **khusus backup** | `SIPETA_DB` ke database uji `sipeta_v2`. Jangan disalin ke project utama. |
| `README.md` | ubah | Header YAML Hugging Face Spaces, cara menjalankan tanpa uvicorn, struktur `core/`, akun awal, ringkasan deploy. |
| `NOTES.md` | ubah | Bagian "Tahap 4" di atas. |
| `MIGRASI_STREAMLIT.md` | baru | Dokumen ini. |
| `pages/panduan copy.py` | **hapus** | Salinan lama Panduan (isi tahap 1), tidak didaftarkan di navigasi. |
| `catatan_latih_klasifikasi.md` (lama) | **hapus** | Versi lama; seluruh isinya ada di `catatan_latih_klasifikasi (1).md`. |
| `catatan_latih_klasifikasi (1).md` | ganti nama | Menjadi `catatan_latih_klasifikasi.md`. Rujukan di README/NOTES ikut diubah. |

## A.3 Titik penyimpanan yang lewat `core.storage`

| Data | Ditulis | Dibaca |
|---|---|---|
| Model RF/ConvLSTM + `.json` | `operasi._simpan_berkas_model` → `kirim` | `klasifikasi`/`prediksi.muat_model`, `muat_config` → `ambil` |
| Hasil klasifikasi `.tif` + citra masukan | `operasi.simpan_hasil` → `hapus` citra lama, `kirim` | `operasi.bandingkan`, `unduh_hasil` → `ambil`, `ambil_folder` |
| Hasil prediksi `.tif` + `.npz` | `operasi.simpan_hasil_prediksi` → `kirim` | `operasi.unduh_hasil_prediksi` → `ambil` |
| Arsip klasifikasi | `operasi.unggah_arsip_klasifikasi` → `hapus` tanggal lama, `kirim` | `peta_tahunan.muat` → `ambil_folder`; daftar tahun → `tahun_arsip` (`daftar`) |
| Arsip anchor | `core.unggah_cloud anchor` (dari laptop) | `citra.muat_anchor` → `ambil_folder` |
| `tmp/`, `cache_tahunan/` | selalu lokal | selalu lokal (boleh hilang) |

## A.4 Pengujian yang sudah dilakukan di backup

Semua lulus. Skrip uji ada di scratchpad sesi dan tidak termasuk proyek.

1. **Alur lengkap, mode lokal**, dengan raster sintetis 150×150 di database uji `sipeta_v2`:
   - pengguna: masuk, sandi salah, daftar, email ganda, ubah peran, aturan ubah peran sendiri;
   - latih RF lalu simpan model, dan menyimpan ulang job yang sudah dibuang ditolak;
   - `daftar_arsip` dengan folder anchor 7 band + SCL saja;
   - klasifikasi citra berawan: awan 17,5% terisi PCHIP 100%;
   - simpan dua hasil, unduh GeoTIFF, pemantauan dengan citra asli dan peta perubahan;
   - unggah arsip klasifikasi dua kecamatan, termasuk penolakan berkas tidak valid;
   - latih ConvLSTM dari arsip dan dari unggah folder, simpan model, prediksi 2026 dan 2027, simpan dan unduh.
2. **Alur yang sama, mode s3**, terhadap server S3 tiruan lokal (moto). Ditambah simulasi restart: seluruh folder storage lokal dihapus, lalu pemantauan, unduh hasil, klasifikasi (anchor diunduh dari bucket), daftar arsip klasifikasi, dan prediksi tetap berjalan. Mengganti arsip satu tanggal menghapus berkas lama di bucket.
3. **Semua 12 halaman** dirender dengan `streamlit.testing` setelah login Super Admin lewat form Masuk: tanpa exception dan tanpa pesan galat.
4. `streamlit run app.py` menyala, dan `/_stcore/health` menjawab `ok`.

Belum diuji: layanan S3 sungguhan (R2, Backblaze B2, Supabase Storage) dan database cloud sungguhan, karena butuh akun. Kodenya memakai API S3 standar (`list_objects_v2`, `upload_file`, `download_file`, `delete_objects`) dan koneksi PostgreSQL biasa.

---

# Bagian B: langkah untuk pemilik proyek

Versi lengkap langkah demi langkah (membuat akun Supabase, bucket, Hugging Face, sampai membagikan ke penguji) ada di **`PANDUAN_DEPLOY.md`**. Bagian ini ringkasannya.

## B.1 Menguji di project backup (lokal)

1. Database uji `sipeta_v2` sudah dibuat dan berisi skema + 3 akun awal. Database `sipeta` milik project utama tidak disentuh.
2. Isi `storage\arsip\` backup dengan citra anchor (atau semua tanggal) seperti biasa, lalu:

   ```powershell
   cd C:\skripsi\sipeta_v2
   venv\Scripts\activate
   python -m core.daftar_arsip
   ```

3. Jalankan aplikasi. **Tidak perlu uvicorn lagi**:

   ```powershell
   python -m streamlit run app.py
   ```

4. Uji semua skenario di `Form_UAT_SIPETA.md`.
5. Untuk mengukur berapa besar anchor yang nanti diunggah ke cloud (tanpa mengunggah apa pun):

   ```powershell
   python -m core.unggah_cloud anchor --ukur
   ```

## B.2 Pengaturan

Semua pengaturan bisa ditulis di `.streamlit\secrets.toml` (lokal / Streamlit Community Cloud) atau sebagai environment variable (Hugging Face Spaces / terminal). Jika ada di keduanya, environment variable didahulukan.

| Nama | Isi | Contoh |
|---|---|---|
| `SIPETA_DB` | connection string PostgreSQL | `postgresql://postgres:sandi@localhost:5432/sipeta` |
| `SIPETA_STORAGE_MODE` | `lokal` atau `s3` | `s3` |
| `SIPETA_S3_ENDPOINT` | endpoint S3 layanan storage | `https://<account-id>.r2.cloudflarestorage.com` |
| `SIPETA_S3_BUCKET` | nama bucket | `sipeta` |
| `SIPETA_S3_KEY`, `SIPETA_S3_SECRET` | access key dan secret | dari dashboard layanan |
| `SIPETA_S3_REGION` | region (bawaan `auto`, cocok untuk R2) | `auto` |
| `SIPETA_STORAGE` | lokasi folder storage/cache (opsional) | bawaan: `storage/` di folder proyek |

## B.3 Deploy online: urutan langkah

Langkah 1–4 dikerjakan sekali.

**1. Database cloud (gratis): Supabase atau Neon**
- Buat project.
- Buka SQL Editor, tempel seluruh isi `core/schema.sql`, lalu jalankan.
- Salin connection string. Untuk Supabase, pilih **Session pooler** (koneksi langsung Supabase hanya IPv6, sedangkan hosting gratis umumnya IPv4), dan tambahkan `?sslmode=require` di akhir.
- Catatan: project Supabase gratis di-*pause* jika ±1 minggu tidak aktif. Datanya tidak hilang, tinggal diaktifkan lagi dari dashboard.

**2. Ganti akun awal** (wajib sebelum orang lain memakai). Akun `*@sipeta.test` dan kata sandinya tertulis di README. Caranya:
- Daftar akunmu sendiri lewat halaman Daftar di web.
- Masuk sebagai `superadmin@sipeta.test`, lalu jadikan akunmu Super Admin lewat Kelola Pengguna.
- Hapus akun awal di SQL Editor:

  ```sql
  DELETE FROM pengguna WHERE email LIKE '%@sipeta.test';
  ```

**3. Object storage (gratis)**
- Pilih satu: Cloudflare R2 (10 GB gratis, biasanya minta kartu terdaftar), Backblaze B2 (10 GB gratis), atau Supabase Storage (1 GB gratis, termasuk kuota project Supabase).
- Pilih berdasarkan hasil `python -m core.unggah_cloud anchor --ukur` ditambah ±250 MB (arsip klasifikasi, model, hasil).
- Buat satu bucket privat dan buat access key (S3 API) dengan izin baca + tulis. Catat endpoint, key, dan secret.

**4. Isi data cloud dari laptop** (PowerShell, di folder proyek):

```powershell
$env:SIPETA_DB = "<connection string database cloud>"
python -m core.daftar_arsip                      # anchor dicatat di database cloud

$env:SIPETA_STORAGE_MODE = "s3"
$env:SIPETA_S3_ENDPOINT = "<endpoint>"
$env:SIPETA_S3_BUCKET = "<bucket>"
$env:SIPETA_S3_KEY = "<access key>"
$env:SIPETA_S3_SECRET = "<secret>"
python -m core.unggah_cloud anchor --ukur        # cek ukuran
python -m core.unggah_cloud anchor               # unggah (boleh diulang; yang sudah ada dilewati)
python -m core.unggah_cloud folder arsip_klasifikasi   # opsional; bisa juga lewat panel Admin di web
```

Environment variable `$env:...` hanya berlaku di jendela PowerShell itu. Model RF/ConvLSTM yang dilatih di laptop tidak ikut. Latih ulang lewat web versi online, karena database lokal dan database cloud terpisah.

**5a. Hugging Face Spaces (disarankan: RAM 16 GB, 2 vCPU, gratis). Tidak perlu GitHub.**
1. Buat akun di huggingface.co, lalu New Space: SDK **Docker**, template Blank, hardware **CPU basic (free)**.
2. Visibility harus **Public** supaya penguji bisa membukanya. Akibatnya kode sumber ikut terlihat publik. Data dan kunci tetap aman karena tersimpan di Secrets.
3. Settings → Variables and secrets: tambahkan semua pengaturan B.2 sebagai **Secrets** (`SIPETA_DB`, `SIPETA_STORAGE_MODE=s3`, `SIPETA_S3_*`).
4. Unggah kode. Pilih salah satu:
   - lewat web: Files → Add file → Upload files;
   - lewat git: `git clone https://huggingface.co/spaces/<nama>/<space>`, salin isi proyek **tanpa** `venv/`, `storage/`, dan `.streamlit/secrets.toml`, lalu `git add .`, `git commit`, `git push`. Kata sandi git = access token Hugging Face.
5. Build pertama butuh beberapa menit (TensorFlow besar). Alamatnya `https://<nama>-<space>.hf.space`.
6. Space gratis tidur setelah ±48 jam tanpa pengunjung. Pengunjung berikutnya menunggu app menyala lagi.

**5b. Streamlit Community Cloud (alternatif). Wajib lewat GitHub.**
1. Push proyek ke repo GitHub. Repo boleh **privat**, dan app tetap bisa publik. `.gitignore` sudah mengecualikan venv, storage, dan secrets.
2. Buka share.streamlit.io → Create app → pilih repo, branch, dan `app.py`. Di Advanced settings pilih Python 3.11, lalu tempel pengaturan B.2 di kotak Secrets (format TOML).
3. Batas resource sekitar 2,7 GB RAM. Latih ConvLSTM/RF dengan banyak data bisa membuat app di-restart karena melewati batas.

## B.4 Keterbatasan versi online (gratis)

- **Job hilang jika app restart atau tidur di tengah proses.** Pelatihan yang belum disimpan harus diulang. Semua yang sudah disimpan (model, hasil, akun) aman di database dan bucket.
- **Satu pelatihan pada satu waktu** untuk semua pengguna (RF dan ConvLSTM berbagi antrean). Klasifikasi dan prediksi masing-masing punya antrean sendiri.
- **Klasifikasi pertama** per kecamatan setelah app menyala lebih lama, karena anchor diunduh dulu dari bucket ke cache.
- **Unggahan besar** (folder Latih RF) bergantung pada kecepatan internet penguji. Batas per berkas 200 MB (bawaan Streamlit).
- Hosting gratis memakai alamat bawaan (`*.hf.space` atau `*.streamlit.app`). Domain sendiri seperti `sipeta.com` berbayar.
