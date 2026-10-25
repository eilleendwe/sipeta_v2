# Catatan keputusan — SIPETA

## Tahap 4: pure Streamlit (tanpa FastAPI), siap deploy

Rincian per berkas dan langkah deploy ada di `MIGRASI_STREAMLIT.md`. Ringkasan keputusan:

- FastAPI dihapus supaya cukup satu program dan satu hosting, dan tidak ada endpoint publik tanpa autentikasi (backend lama tidak punya token). Fitur tidak berubah.
- Folder `api/` diganti nama menjadi `core/`. Catatan tahap 2–3 di bawah masih menyebut `api/...`; berkasnya sekarang di `core/...` dengan nama yang sama. `api/main.py` diganti `core/operasi.py` (fungsi per endpoint, logika sama), router di `api/pengguna.py` dibuang, `services/api_client.py` diganti `services/backend.py`.
- `services/backend.py` membentuk ulang hasil seperti JSON (tanggal jadi teks ISO, tuple jadi list, kunci dict jadi teks), jadi kode services/halaman yang dulu membaca respons API tidak perlu diubah.
- Job tetap thread latar belakang (`core/jobs.py`), sekarang di proses Streamlit. Persiapan saat backend dinyalakan (`lifespan`: kosongkan `tmp/`, buat folder) pindah ke `app.py` lewat `st.cache_resource`, jadi berjalan sekali per proses.
- Berkas permanen lewat `core/storage.py`: mode `lokal` (folder `storage/`, untuk development) atau `s3` (bucket S3-compatible; folder `storage/` menjadi cache yang boleh hilang saat restart). Kunci bucket = path relatif yang sudah disimpan di database, jadi skema tidak berubah.
- Database lewat connection pool (`psycopg-pool`), karena membuka koneksi ke database cloud mahal. `prepare_threshold=None` supaya bisa lewat pooler transaksi Supabase.
- Pengaturan dibaca dari environment variable, lalu `.streamlit/secrets.toml`. Streamlit menyalin isi secrets.toml ke `os.environ` dan menimpa nilai bernama sama, jadi `core/config.py` menyalin environment lebih dulu supaya environment variable tetap didahulukan.
- Arsip anchor online hanya tanggal anchor dengan 7 band fitur + SCL (yang dibaca Klasifikasi Citra), diunggah sekali dari laptop dengan `python -m core.unggah_cloud anchor`. `core.daftar_arsip` kini cukup mewajibkan 7 band fitur + SCL (sebelumnya 9 band + SCL), jadi folder arsip boleh hanya berisi tanggal anchor tanpa B08/B11.
- `requirements.txt` ditulis ulang (UTF-8, versi terkunci, satu berkas untuk lokal dan deploy); `api/requirements.txt` dihapus. Paket yang tidak dipakai (fastapi, uvicorn, requests, yfinance, dst.) dibuang.
- Dihapus: `pages/panduan copy.py` (salinan lama, tidak dipakai) dan `catatan_latih_klasifikasi.md` lama (isinya sudah termuat di versi `(1)`, yang kini diganti nama menjadi `catatan_latih_klasifikasi.md`).

## Tahap 3: modul Prediksi dengan ConvLSTM

Mengikuti `catatan_latih_klasifikasi.md` bagian 12–18 dan `convlstm_sipeta_v8.ipynb` tanpa grid search. Data tiruan Prediksi dan seluruh folder `mock/` dihapus.

- Keputusan terbuka bagian 17 yang diambil pemilik proyek: masukan = arsip klasifikasi notebook (`kecamatan_masked_rf_classified`, 17.3); ConvLSTM dilatih di web (17.1); peta dan luas hasil Prediksi = versi 10 m, versi 64×64 hanya pembanding (17.4); prediksi boleh berkurang seperti notebook (17.7). Lainnya mengikuti notebook: evaluasi terhadap label yang sudah melewati aturan konsistensi (17.5), kecamatan latih dipilih di form dengan bawaan semua (17.2).
- Arsip klasifikasi dibaca langsung dari disk (`storage/arsip_klasifikasi/<wilayah>/<kecamatan>/<tanggal>/RF_LABEL_*.tif`), tanpa tabel database. Endpoint `/arsip-klasifikasi` melaporkan tahun yang tersedia per kecamatan; form Latih menampilkan berapa kecamatan terpilih yang lengkap.
- Arsip bisa diunggah Admin lewat panel "Arsip klasifikasi di server" di Latih Model Prediksi (revisi, supaya web bisa di-deploy tanpa menyalin berkas ke server). Yang dipilih boleh folder induk, satu wilayah, atau satu kecamatan; kecamatan dikenali dari nama folder di atas folder tanggal (`services/arsip.py`). Dikirim per kecamatan (`POST /arsip-klasifikasi/{kecamatan}`). Backend memeriksa semua berkas dulu (GeoTIFF valid, nilai 0/1/255, ukuran seragam); jika satu tidak valid, kecamatan itu ditolak seluruhnya dan kecamatan lain tetap diunggah. Tanggal yang sudah ada diganti, lalu cache peta tahunan kecamatan itu dihapus.
- Latih Model Prediksi punya dua sumber data latih (revisi, permintaan pemilik proyek): **Arsip di server** (pilih kecamatan, baca arsip + cache) atau **Unggah folder** (seperti Latih RF: folder `RF_LABEL` diunggah di form, kecamatan dikenali dari nama folder, hanya kecamatan lengkap 2016–2025 yang dikirim lewat `POST /latih-prediksi/unggah`, berkas diperiksa sama seperti unggah arsip, disimpan di `tmp/<job>/input/` dan dihapus setelah latih; tidak masuk arsip dan tanpa cache). Sumber tercatat di konfigurasi model (`data_source`) dan panel evaluasi. Prediksi Citra tetap selalu membaca arsip server, jadi kecamatan yang diprediksi harus ada di arsip.
- `api/peta_tahunan.py` = modul bersama bagian 13 (komposit mayoritas, konsistensi waktu, resize 64×64), dipakai Latih dan Prediksi. Resize nearest ditulis dengan numpy dan diuji identik dengan `scipy.ndimage.zoom(grid_mode=True)`, cara yang dipakai `skimage.transform.resize(order=0)` di notebook, jadi scikit-image tidak perlu dipasang. Cache per kecamatan (`storage/cache_tahunan/<kecamatan>.npz`) dibangun ulang otomatis jika jumlah berkas arsip berubah (prosedur data tahun baru, 17.8, belum dibuat).
- `api/convlstm.py` = salinan notebook bagian 3–4: `ConvLSTMManual` (Persamaan 2.39–2.44), loss bertopeng, `build_convlstm_model`, metrik peta + luas, confusion matrix, prediksi rekursif, dan penempelan perubahan ke peta 10 m. Yang diubah hanya fungsi yang dulu memakai variabel global notebook; datanya kini lewat parameter. Nama fungsi dibiarkan sama dengan notebook supaya mudah dirujuk di skripsi.
- `api/latih_prediksi.py` mengikuti notebook bagian 2, 7, 8: tahun target selalu 2020–2025 (seperti `MAX_SEQ = 4`), dipotong urut waktu menurut rasio (bawaan 0,5/0,17/0,33 → train 2020–2022, validasi 2023, test 2024–2025); latih dengan early stopping (patience 15, mulai epoch 20, bobot terbaik dipulihkan); latih ulang sampai 2023 dengan epoch terbaik lalu uji 2024 (1 langkah) dan 2025 (rekursif); latih ulang sampai 2025 sebagai model final. Urutan sampel dan seed (42) sama dengan notebook.
- Nilai bawaan form = konfigurasi terpilih v7 (40 filter, kernel 5, lr 0,0005, L 4, 2 layer, dropout 0, Adam, batch 8, maks. 100 epoch), karena grid v8 belum dijalankan. Ganti di `default_params` dan `REKOMENDASI` (`services/models.py`) setelah grid v8 selesai. `filters` ditambahkan ke form (catatan bagian 14). Sequence length dibatasi 2–4, jumlah layer 1–3.
- Evaluasi yang ditampilkan per tahun test: confusion matrix model, tabel model vs persistensi (accuracy, precision, recall, F1, IoU, FoM, MAE/RMSE/MAPE/R²/bias luas), confusion matrix persistensi, confusion matrix khusus piksel nonterbangun di 2023, dan kurva loss. Metrik NaN dikirim sebagai kosong ("-").
- Latih RF dan latih ConvLSTM berbagi satu antrean job (keduanya berat di CPU). Prediksi punya antrean sendiri, jadi tetap bisa jalan selama pelatihan. `clear_session()` notebook tidak dipanggil karena bisa mengganggu model yang sedang dipakai thread prediksi; nama layer sudah eksplisit.
- Halaman Latih (RF dan ConvLSTM) kini melanjutkan pemantauan job jika pengguna pindah halaman lalu kembali (revisi; sebelumnya dianggap batal). `job_id` disimpan di sesi Streamlit, jadi menutup tab atau me-refresh peramban tetap memutus pemantauan; job di server tetap selesai tetapi hasilnya tidak bisa diambil dari halaman.
- Prediksi Citra: pilih model, kecamatan (hanya kecamatan yang ikut melatih model; centang "di luar cakupan" tidak ada untuk ConvLSTM), dan tahun 2026/2027. Sumber "katalog/unggah raster" dihapus; masukan selalu peta tahunan L tahun terakhir dari arsip. Tampilan seperti Klasifikasi Citra: peta aktual 2025 dan prediksi berdampingan (10 m), tombol "Tampilkan perubahan", luas utama dari peta 10 m, luas 64×64 sebagai pembanding, dan keterangan bahwa detail halus berasal dari peta 2025 (catatan 15.6).
- Hasil prediksi yang disimpan: tabel `hasil_prediksi` + GeoTIFF 10 m dan `.npz` (peluang + biner 64×64 semua langkah) di `storage/prediksi/<kecamatan>/`. Belum ditampilkan di Pemantauan.
- Tabel baru: `model_prediksi` dan `hasil_prediksi` (lihat `api/schema.sql`). Model `.keras` + `.json` disimpan di `storage/model/`.

## Tahap 2: modul Klasifikasi dengan backend (FastAPI + PostgreSQL)

Mengikuti `catatan_latih_klasifikasi.md`. Login/peran, Klasifikasi (Latih + Klasifikasi Citra), dan Pemantauan kini memakai data nyata. (Modul Prediksi menyusul di tahap 3.)

- Backend ada di folder `api/` (bukan `backend/`, karena `backend.py` lama di root akan bentrok nama). Jalankan `uvicorn api.main:app --reload`. Frontend memanggilnya lewat `services/api_client.py` (alamat: env `SIPETA_API`).
- Skema database: `api/schema.sql` (tabel `pengguna` + 3 akun demo, `wilayah`, `kecamatan` + 49 data, `citra_arsip`, `model_klasifikasi`, `hasil_klasifikasi`). Koneksi: env `SIPETA_DB`.
- Arsip disimpan per kecamatan: `storage/arsip/<wilayah>/<kecamatan>/<tanggal>/` (revisi; sebelumnya raster per wilayah). Status anchor tetap per wilayah seperti notebook: % awan (SCL + buffer 30 m) dihitung dari gabungan semua kecamatan di wilayah pada tanggal itu. Donor untuk kecamatan K dibaca dari folder K. Hasil pada data asli sama dengan notebook (Kota Tangerang 14 anchor, Kota Tangerang Selatan 25). Buffer tidak menyeberang batas kecamatan, jadi % awan bisa berbeda sangat sedikit dari perhitungan raster wilayah utuh.
- Berkas disimpan di `storage/` (env `SIPETA_STORAGE`): `arsip/` (citra wilayah untuk anchor), `model/` (.pkl + .json konfigurasi), `hasil/` (GeoTIFF hasil), `citra/` (citra masukan dari hasil yang disimpan), `tmp/` (dibersihkan tiap backend dinyalakan). Database hanya menyimpan path relatif.
- PCHIP disalin apa adanya dari `PCHIP_V2.ipynb` ke `api/prapemrosesan.py` dan dipakai bersama oleh Latih dan Klasifikasi. Random Forest disalin dari `randomforest_v2.ipynb` ke `api/rf.py`; algoritma latih sama. `predict` diubah agar memproses semua piksel sekaligus (diuji identik dengan versi per baris, termasuk aturan seri voting). Metrik dihitung manual (tanpa sklearn).
- Pelatihan dan klasifikasi berjalan sebagai job latar belakang (thread, satu antrean per jenis). Status job ada di memori: jika backend dimatikan, job berjalan dan hasil yang belum disimpan hilang. Jika pengguna pindah halaman saat pelatihan berjalan, job tetap selesai di server tetapi hasilnya tidak tampil di halaman.
- Latih memakai **satu folder kecamatan** yang diunggah (`accept_multiple_files="directory"`). Nama folder harus sama dengan kecamatan terpilih (tanpa membedakan huruf besar/kecil, spasi, `_`/`-`). Isinya subfolder `YYYY-MM-DD` berisi 9 band + SCL. Saluran dikenali dari nama berkas. Tanggal yang tidak lengkap dilewati, bukan menggagalkan semuanya. Citra latih dihapus setelah pelatihan; yang disimpan hanya model + konfigurasi.
- **Sampel per tanggal tetap dipakai (bawaan 1.000), bukan seluruh piksel.** Satu kecamatan 9–48 km² = 90 rb–480 rb piksel; × 64 tanggal = 6–30 juta baris. RF manual ±50 detik/pohon pada 384 rb baris (log Colab), jadi seluruh piksel butuh puluhan jam dan beberapa GB memori. Piksel bertetangga juga sangat mirip, jadi tambahan informasinya kecil. 1.000 × 64 = 64 rb baris (±1/6 data notebook). Pilihan **Pakai seluruh piksel** tetap disediakan (dengan keterangan bahwa latih bisa berjam-jam); diukur di laptop: 30 pohon ±13 menit pada 51 rb baris, ±71 menit pada 800 rb baris.
- Evaluasi: split blok spasial (50 × 50 piksel, test ratio 0,2, seed 42). Ukuran blok dan seed tetap di backend (`api/latih.py`), tidak lagi di form. Semua tanggal dari satu blok masuk ke sisi yang sama. **Tanpa blok buffer**: dengan 20% blok uji acak, sebagian besar blok latih bersebelahan dengan blok uji, jadi buffer akan membuang terlalu banyak data.
- Open decision 9.2: sampel latih **hanya dari piksel cerah** (sesuai saran dokumen alur). PCHIP tidak dijalankan saat Latih, sehingga Latih tidak butuh arsip anchor; PCHIP mengisi awan saat Klasifikasi. Pilihan "Sumber sampel", ukuran blok, dan random seed dihapus dari form (Parameter lanjutan ditiadakan).
- Keputusan lain mengikuti kondisi saat ini: donor hanya dari anchor (9.3), anchor per wilayah (9.4), model boleh dipakai di kecamatan lain dengan peringatan (9.5), format model `.pkl` (9.8). Belum ditangani: offset reflektansi `BOA_ADD_OFFSET` (9.9) dan model mana yang menjadi masukan ConvLSTM (9.6).
- Form Latih RF disesuaikan dengan RF manual: jumlah pohon 30, max depth 16, min samples split 10, jumlah fitur per split 3, max thresholds 20 (nilai Grid Search notebook). Bootstrap sampling selalu aktif (bagian dasar Random Forest), jadi tidak lagi ditampilkan sebagai pilihan. Min samples leaf, max features sqrt/log2, dan pembagian acak per piksel dihapus karena tidak ada di RF manual atau tidak sesuai alur. Feature importance dan tabel per kecamatan diganti ringkasan sampel/blok latih-uji.
- Confusion matrix kini menampilkan persentase per kelas aktual (per baris), sama seperti plot notebook. Berlaku juga untuk panel ConvLSTM.
- Klasifikasi Citra: tanggal dipilih bebas lewat kalender, dibatasi rentang arsip 2016–2025 (PCHIP tidak mengekstrapolasi). Sumber "Katalog" dihapus; citra selalu diunggah (7 band + SCL). Citra harus sejajar dengan grid arsip (dipotong dari raster wilayah yang sama); jika tidak, backend menolak.
- Jika arsip anchor wilayah belum didaftarkan, klasifikasi tetap jalan tetapi piksel berawan menjadi NoData dan muncul peringatan.
- Gambar hasil: PNG berukuran sama dengan raster (1 piksel = 10 m), NoData transparan, ditampilkan dengan `image-rendering: pixelated` supaya tidak dihaluskan saat diperbesar. Unduhan GeoTIFF adalah raster asli (uint8, 0/1, NoData 255, bergeoreferensi).
- Menyimpan hasil untuk model + kecamatan + tanggal yang sudah ada akan menimpa hasil lama.
- Pemantauan membaca `hasil_klasifikasi`. Luas bertambah/berkurang dihitung dari piksel yang valid di kedua tanggal, jadi selisihnya bisa sedikit berbeda dari perubahan bersih.
- Pemantauan kini satu tampilan (revisi): baris atas citra asli kedua tanggal + kartu Bertambah/Berkurang/Perubahan bersih, baris bawah klasifikasi kedua tanggal + peta perubahan. Pilihan mode tampilan dan dropdown tanggal terkunci di atas kanvas dihapus; tanggal tertulis di judul tiap gambar. Citra asli dibuat dari citra masukan yang ikut tersimpan (`path_citra`).
- Klasifikasi Citra: awan yang tidak bisa diisi diberi warna abu di peta hasil (sebelumnya transparan seperti area di luar kecamatan, jadi terlihat seolah cloud mask tidak jalan). Tombol "Tampilkan masker awan" menumpuk hasil cloud masking (SCL + buffer 30 m) di atas citra asli: teal = terisi, oranye = tidak terisi. GeoTIFF tetap 0/1/255.
- Model tersimpan dipakai bersama semua peran: daftar model di backend tidak disaring menurut pengguna. Hanya melatih dan menyimpan yang khusus Admin. Model Prediksi nanti mengikuti pola yang sama (tabel model + berkas di `storage/model/`).
- Semua data dan kode tiruan untuk Klasifikasi, Pemantauan, dan login dihapus: model/hasil/evaluasi RF seed, dataset Sentinel-2 (jenis dataset ini juga dihapus dari dialog impor), pengguna seed, kotak "Akun demo" di halaman Masuk, contoh pratinjau Klasifikasi/Pemantauan, serta fungsi gambar tiruan yang hanya dipakai klasifikasi (citra asli, overlay, peta perubahan, piksel terisi). (Sisa `mock/` untuk Prediksi dihapus di tahap 3.)
- Daftar wilayah/kecamatan di semua halaman dibaca dari database, jadi backend wajib berjalan. Id kecamatan memakai huruf kecil + garis bawah (`pondok_aren`), sama dengan gaya nama folder notebook.
- Pengguna disimpan di tabel `pengguna` (revisi; sebelumnya di memori Streamlit dan hilang saat server dimatikan). Endpoint di `api/pengguna.py`: daftar, masuk, daftar pengguna, ubah peran. Kata sandi di-hash PBKDF2-SHA256 (pustaka standar Python, tanpa dependensi baru). Email disimpan huruf kecil dan unik. Backend juga memeriksa aturan ubah peran (hanya Super Admin, bukan diri sendiri, Super Admin terakhir tidak bisa diturunkan). Sesi Streamlit hanya menyimpan id; data akun dibaca ulang tiap rerun supaya perubahan peran langsung berlaku.
- Belum ada token/sesi di backend: endpoint lain belum memeriksa siapa yang memanggil, pembatasan peran masih dilakukan di Streamlit. Nama pengguna dikirim sebagai `dibuat_oleh` / `disimpan_oleh`.

- Logo SIPETA ada di `ui/logo.svg` (favicon: `ui/logo.png`, 256 px): penanda lokasi teal berisi ikon `satellite_alt` dari Material Symbols (Google, Apache License 2.0; boleh dipakai dan diubah gratis, atribusi tidak wajib, tetapi tidak eksklusif). Dipasang di navbar Landing, hero Landing, sidebar, dan kartu Masuk/Daftar lewat `layout.logo()`. Logo dipasang sebagai `<img>` ber-data URI karena `st.html` membuang tag `<svg>`.

---

# Catatan tahap 1 (frontend, data tiruan)

Keputusan kecil yang diambil saat mengerjakan `SPEC.md`, terutama di tempat SPEC ambigu atau berbeda dari wireframe (`docs/wireframe sipeta.pdf`). Tata letak mengikuti wireframe, isi dan perilaku mengikuti SPEC.

## Berkas dan cakupan

- Wireframe yang dibaca adalah `docs/wireframe sipeta.pdf` (9 frame). Frame kosong "Prapemrosesan" yang disebut SPEC §0 tidak ada di PDF.
- Login, Register, Kelola Pengguna, dan bagian bawah sidebar (nama, lencana peran, Keluar, lencana mode demo) tidak ada di wireframe. Dirancang dengan bahasa visual yang sama.
- `main.py`, `backend.py`, dan `requirements.txt` yang sudah ada tidak diubah dan tidak dipakai. Titik masuk aplikasi adalah `app.py`.
- Tidak ada dependensi baru. Grafik memakai Altair dan raster memakai `st.image` dari array numpy; keduanya sudah ikut terpasang bersama Streamlit. SPEC menyebut matplotlib atau plotly; jika diinginkan, cukup ganti isi `ui/charts.py`.

## Navigasi

- Tiap tab Klasifikasi dan Prediksi adalah halaman sendiri (`/klasifikasi-latih`, `/klasifikasi-citra`, `/prediksi-latih`, `/prediksi-citra`). Bilah tab di kartu adalah tautan antarhalaman, bukan `st.tabs`. Halaman aktif menjadi satu-satunya sumber kebenaran, jadi tab dan sub-menu sidebar selalu sinkron.
- Semua halaman selalu terdaftar di `st.navigation`, termasuk yang tidak boleh dibuka peran saat ini. Dengan begitu alamat Latih model menampilkan "Akses ditolak", bukan "Page not found". Menu yang tampil disaring di sidebar.
- Login tidak persisten: mengetik alamat di bilah alamat memulai sesi baru. Guard menyimpan halaman tujuan, mengalihkan ke Login, lalu setelah masuk membawa pengguna ke tujuan itu. Jadi uji "mengetik alamat Latih model sebagai Pengguna" berakhir di kartu "Akses ditolak" setelah login.
- Klik induk "Klasifikasi" / "Prediksi" di sidebar membuka tab Citra, karena tab itu bisa diakses semua peran.
- Label tab kedua Prediksi adalah "Prediksi Citra" (wireframe halaman 7 menulis "Prediksi", halaman 8 "Prediksi Citra").
- Isian form bertahan saat berpindah tab lewat `persist_state="session"` bawaan Streamlit 1.65 (rencana awal memakai penjaga kunci di `ui/state.py`; tidak jadi dibuat karena fitur bawaan sudah cukup). Unggahan berkas tidak ikut bertahan.

## Latih Model

- Baris pertama form diubah dari empat kolom sama lebar menjadi Model, Kota/Kabupaten, Kecamatan (lebar ganda), lalu Dataset + tombol impor di baris berikutnya. Kecamatan multi-pilih butuh ruang; urutan baca tetap seperti wireframe.
- Dropdown Kota/Kabupaten di Latih Model punya opsi "Semua kota/kabupaten" supaya model bercakupan semua kecamatan (seperti model seed) bisa dibuat dari form.
- Max depth: field angka yang boleh dikosongkan. Kosong berarti tidak dibatasi.
- Rasio Random Forest: mengubah train ratio mengubah test ratio, dan sebaliknya.
- Rasio ConvLSTM: train dan test diisi, validation ratio = sisa (hanya-baca). Galat muncul jika train + test ≥ 1.
- Selama pelatihan berjalan, seluruh form dan tombol Latih model nonaktif. Jika pengguna pindah halaman di tengah proses, pelatihan dianggap batal.
- Panel Evaluasi: posisi gambar di wireframe diisi confusion matrix, posisi paragraf diisi kartu metrik dan feature importance (atau kurva loss). Tabel per kecamatan dan tombol Simpan/Buang di bawahnya.
- Dialog Impor dataset dipakai untuk dua jenis dataset: citra Sentinel-2 (Klasifikasi) dan raster tahunan (Prediksi). Laporan validasi raster tahunan berisi satu baris per tahun.
- Nama model dan nama dataset harus unik tanpa membedakan huruf besar dan kecil.
- Memilih Kota/Kabupaten tidak lagi mengisi Kecamatan otomatis (revisi; berbeda dari SPEC 5.3). Pengguna memilih kecamatan sendiri.
- Di bawah label tiap hyperparameter ada keterangan kecil: penjelasan singkat dan "(Direkomendasikan: …)". Keduanya diatur di `REKOMENDASI` pada `services/models.py`. Nilai rekomendasi saat ini sama dengan nilai bawaan SPEC; ganti dengan angka dari hasil eksperimen. Field dalam satu baris diratakan ke bawah karena panjang keterangannya berbeda-beda.
- Setelah "Simpan model", panel evaluasi tetap tampil dengan tanda "Sudah tersimpan" sampai model lain dilatih (revisi). Tombol Buang hanya ada sebelum model disimpan.

## Login dan sesi

- Kata sandi saat mendaftar: minimal 8 karakter, memuat 1 huruf besar dan 1 angka (revisi; SPEC 4.3 hanya menyebut 8 karakter). Aturannya tertulis di bawah label field.
- Petunjuk bawaan Streamlit "Press Enter to submit form" disembunyikan di halaman Masuk dan Daftar.
- Saat Keluar, seluruh state sesi dibuang: isian form, hasil klasifikasi/prediksi yang sedang tampil, dan evaluasi yang belum disimpan. Akun berikutnya di peramban yang sama mulai dari halaman kosong.
- Model, dataset, dan hasil yang sudah **disimpan** tetap terlihat oleh semua akun, karena disimpan bersama di store. Untuk tahap backend perlu diputuskan apakah hasil klasifikasi dan prediksi milik bersama atau per pengguna; jika per pengguna, tiap baris di database harus mencatat pemiliknya dan endpoint menyaring menurut pengguna dari token.

## Klasifikasi Citra dan Prediksi Citra

- Dropdown Model difilter menurut kecamatan terpilih. Centang "Tampilkan model di luar cakupan" membuka semua model; memilih model di luar cakupan memunculkan peringatan, tetapi tetap bisa dijalankan. Filter yang sama dipakai di Prediksi Citra.
- Jika kecamatan diganti dan model terpilih tidak mencakupnya, pilihan model dikosongkan dan pengguna diberi tahu.
- Mode Unggah memakai satu kotak unggah banyak berkas. Saluran dan tanggal dikenali dari nama berkas saja; isi berkas tidak dibaca (tahap 1 tidak mengolah raster).
- "Tampilkan overlay" berada di bawah kanvas kiri seperti wireframe. Saat aktif, kanvas kanan menampilkan hasil yang ditumpuk di atas citra asli, dengan slider opasitas.
- Unduhan hasil hanya PNG dan GeoTIFF (revisi; CSV dihapus). "GeoTIFF" adalah TIFF contoh tanpa georeferensi. Unduhan CSV riwayat di Pemantauan tetap ada.
- Tahun prediksi hanya 2026 dan 2027. (Aturan unggahan raster prediksi dan model acuan tiruan dihapus di tahap 3.)

## Pemantauan

- Baris atas lima kolom: Kota/Kabupaten, Kecamatan, Model, Tanggal awal, Tanggal akhir (wireframe empat kolom; Model adalah tambahan SPEC).
- Dropdown Model hanya memuat model yang punya hasil tersimpan untuk kecamatan itu. Tanggal akhir hanya menawarkan tanggal setelah tanggal awal.
- Pasangan tanggal di atas kanvas selalu sama dengan pasangan atas dan ditampilkan terkunci (revisi). Untuk membandingkan tanggal lain, ubah pilihan di atas lalu tekan "Tampilkan Data".
- Pada peta perubahan, luas "bertambah" diturunkan dari perubahan bersih + luas "berkurang", supaya selisihnya selalu sama dengan ringkasan.

## Tampilan

- Struktur wireframe dipertahankan; warna dan ikon mengikuti `CLAUDE.md`: sidebar abu-abu slate, kartu putih, aksen teal, terakota untuk lahan terbangun, hijau untuk nonterbangun.
- Warna kelas peta dan seri grafik diperiksa keterbedaannya untuk buta warna. Setiap peta punya legenda, dan selisih luas selalu ditulis dengan tanda +/−, jadi makna tidak bergantung pada warna saja.
- Font IBM Plex Sans dimuat dari Google Fonts (diatur di `.streamlit/config.toml`). Tanpa internet, tampilan memakai font bawaan Streamlit.
- Angka memakai format Indonesia (koma desimal). Berkas CSV memakai titik desimal supaya mudah dibaca program lain.

## Yang perlu diisi pemilik proyek

- `data/authors.json`: nama, keterangan, foto (nama berkas di folder `data/`), dan paragraf deskripsi. Isinya masih placeholder.
- Daftar kecamatan lengkap dan luasnya.
