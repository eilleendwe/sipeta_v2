"""Operasi SIPETA yang dipanggil langsung oleh services/ (pengganti endpoint FastAPI api/main.py).

Isi dan urutan fungsinya sama dengan endpoint lama; nama endpoint ditulis di komentar tiap
fungsi. Galat yang aman ditampilkan dilempar sebagai ProsesError. Berkas yang disimpan
permanen selalu lewat core.storage, jadi berjalan sama di mode lokal maupun s3.

Modul ConvLSTM (convlstm, latih_prediksi, prediksi) baru diimpor di dalam fungsi yang memakainya,
karena ketiganya memuat TensorFlow (±0,2–0,4 GB RAM, ±10 detik). Dengan begitu app cepat menyala
dan hemat memori selama tidak ada yang memakai Latih Prediksi atau Prediksi Citra.
"""

import base64
import json
import re
import shutil
from datetime import date
from functools import lru_cache
from pathlib import Path, PurePosixPath

import numpy as np
import rasterio
from pydantic import BaseModel, Field, ValidationError
from rasterio.io import MemoryFile

from core import citra, db, jobs, klasifikasi, latih, peta_tahunan, storage
from core.config import (CACHE_TAHUNAN_DIR, CITRA_DIR, HASIL_DIR, LABEL_NODATA, MODEL_DIR, PREDIKSI_DIR,
                         TANGGAL_MAKS, TANGGAL_MIN, TMP_DIR)
from core.jobs import ProsesError

# Berkas unggahan: (nama berkas beserta subfolder, mis. "2019-07-04/T48_B02_10m.tif", isi).
Unggahan = list[tuple[str, bytes]]


def siapkan() -> None:
    """Sekali saat app dinyalakan: sisa unggahan dan hasil yang belum disimpan dari sesi
    sebelumnya dibuang, folder dibuat, dan pengaturan storage diperiksa."""
    storage.periksa()
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    for folder in (TMP_DIR, MODEL_DIR, HASIL_DIR, CITRA_DIR, PREDIKSI_DIR):
        folder.mkdir(parents=True, exist_ok=True)


class ParamLatih(BaseModel):
    n_trees: int = Field(30, ge=1, le=500)
    max_depth: int = Field(16, ge=1, le=100)
    min_samples_split: int = Field(10, ge=2)
    n_features: int = Field(3, ge=1, le=7)
    max_thresholds: int = Field(20, ge=2, le=1000)
    test_ratio: float = Field(0.2, gt=0, lt=1)
    sampel_per_tanggal: int | None = Field(1000, ge=10, le=100_000)  # None = seluruh piksel cerah


@lru_cache(maxsize=1)
def _param_prediksi() -> type[BaseModel]:
    """Model validasi parameter ConvLSTM. Dibuat saat pertama dipakai, karena batasnya diambil dari
    modul yang memuat TensorFlow."""
    from core import convlstm, latih_prediksi

    class ParamPrediksi(BaseModel):
        sequence_length: int = Field(4, ge=2, le=latih_prediksi.SEQ_MAKS)
        n_layers: int = Field(2, ge=1, le=3)
        filters: int = Field(40, ge=1, le=128)
        kernel_size: int = Field(5, ge=1, le=9)
        dropout: float = Field(0.0, ge=0, lt=1)
        learning_rate: float = Field(0.0005, gt=0, le=1)
        optimizer: str = Field("adam", pattern=f"^({'|'.join(convlstm.OPTIMIZERS)})$")
        max_epochs: int = Field(100, ge=1, le=500)
        batch_size: int = Field(8, ge=1, le=128)
        train_ratio: float = Field(0.5, gt=0, lt=1)
        val_ratio: float = Field(0.17, gt=0, lt=1)
        test_ratio: float = Field(0.33, gt=0, lt=1)

    return ParamPrediksi


def _params(model: type[BaseModel], params: dict) -> dict:
    try:
        return model.model_validate(params).model_dump()
    except ValidationError as e:
        raise ProsesError(f"Parameter latih tidak valid: {e.errors()[0]['msg']}")


# --- Bantuan ------------------------------------------------------------------

def _kecamatan(kecamatan_id: str) -> dict:
    row = db.fetch_one(
        "SELECT k.id, k.nama, k.wilayah_id, w.nama AS wilayah_nama "
        "FROM kecamatan k JOIN wilayah w ON w.id = k.wilayah_id WHERE k.id = %s",
        (kecamatan_id,),
    )
    if row is None:
        raise ProsesError("Kecamatan tidak ditemukan.")
    return row


def _model(model_id: int) -> dict:
    row = db.fetch_one("SELECT * FROM model_klasifikasi WHERE id = %s", (model_id,))
    if row is None:
        raise ProsesError("Model tidak ditemukan.")
    return row


def _job_selesai(job_id: str, jenis: str) -> dict:
    job = jobs.get(job_id)
    if job is None or job["jenis"] != jenis:
        raise ProsesError("Hasil proses tidak ditemukan. Mungkin app sudah dijalankan ulang.")
    if job["status"] != "selesai":
        raise ProsesError("Proses belum selesai.")
    return job


def _bagian(nama: str) -> tuple[str, ...]:
    return PurePosixPath((nama or "").replace("\\", "/")).parts


def _simpan_unggahan(files: Unggahan, folder: Path, pakai_subfolder_tanggal: bool) -> int:
    """Tulis berkas unggahan ke folder job. Nama berkas tidak dipakai langsung sebagai path:
    hanya nama dasar berkas (+ subfolder tanggal untuk latih) yang diambil."""
    jumlah = 0
    for nama, isi in files:
        bagian = _bagian(nama)
        if not bagian or citra.kenali_band(bagian[-1]) is None:
            continue
        tujuan = folder
        if pakai_subfolder_tanggal:
            if len(bagian) < 2 or not latih.TANGGAL_RE.fullmatch(bagian[-2]):
                continue
            tujuan = folder / bagian[-2]
        tujuan.mkdir(parents=True, exist_ok=True)
        (tujuan / Path(bagian[-1]).name).write_bytes(isi)
        jumlah += 1
    return jumlah


def _simpan_berkas_model(job_id: str, berkas: str, dasar: str, config: dict) -> tuple[str, str]:
    """Salin model dari folder job ke storage/model/ beserta konfigurasinya (.json). Mengembalikan path relatif."""
    path_model = MODEL_DIR / f"{dasar}{Path(berkas).suffix}"
    path_config = MODEL_DIR / f"{dasar}.json"
    shutil.copy2(TMP_DIR / job_id / berkas, path_model)
    path_config.write_text(json.dumps({**config, "model_file": path_model.name}, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    rel_model, rel_config = storage.relatif(path_model), storage.relatif(path_config)
    storage.kirim(rel_model)
    storage.kirim(rel_config)
    return rel_model, rel_config


def _slug(teks: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", teks.lower()).strip("_") or "model"


def _berkas_job(job_id: str, jenis: str, nama: str, boleh: set[str]) -> bytes:
    _job_selesai(job_id, jenis)
    if nama not in boleh:
        raise ProsesError("Berkas tidak dikenal.")
    return (TMP_DIR / job_id / nama).read_bytes()


# --- Wilayah (GET /wilayah) -----------------------------------------------------

def daftar_wilayah() -> list[dict]:
    wilayah = db.fetch_all("SELECT id, nama FROM wilayah ORDER BY nama")
    kecamatan = db.fetch_all("SELECT id, nama, wilayah_id FROM kecamatan ORDER BY nama")
    for w in wilayah:
        w["kecamatan"] = [{"id": k["id"], "nama": k["nama"]} for k in kecamatan if k["wilayah_id"] == w["id"]]
    return wilayah


# --- Job (GET/DELETE /jobs/{job_id}) ----------------------------------------------

def status_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise ProsesError("Proses tidak ditemukan. Mungkin app sudah dijalankan ulang.")
    return job


def buang_job(job_id: str) -> None:
    """Buang hasil yang belum disimpan (calon model atau hasil klasifikasi)."""
    jobs.hapus(job_id)
    shutil.rmtree(TMP_DIR / job_id, ignore_errors=True)


# --- Latih model (POST /latih, POST /model, GET /model) -----------------------------

def mulai_latih(kecamatan_id: str, params: dict, files: Unggahan) -> str:
    kecamatan = _kecamatan(kecamatan_id)
    p = _params(ParamLatih, params)
    job_id = jobs.buat("latih")
    folder = TMP_DIR / job_id
    if _simpan_unggahan(files, folder / "input", pakai_subfolder_tanggal=True) == 0:
        buang_job(job_id)
        raise ProsesError("Tidak ada berkas citra yang dikenali di folder unggahan.")
    jobs.mulai(job_id, latih.jalankan, folder, kecamatan, p)
    return job_id


def simpan_model(job_id: str, nama: str, dibuat_oleh: str | None) -> dict:
    job = _job_selesai(job_id, "latih")
    nama = nama.strip()
    if not nama or len(nama) > 100:
        raise ProsesError("Nama model wajib diisi, maksimal 100 karakter.")
    if db.fetch_one("SELECT 1 FROM model_klasifikasi WHERE lower(nama) = lower(%s)", (nama,)):
        raise ProsesError("Nama model sudah dipakai.")

    hasil = job["hasil"]
    rel_model, rel_config = _simpan_berkas_model(job_id, "model.pkl", f"rf_{_slug(nama)}_{date.today():%Y%m%d}",
                                                 hasil["config"])
    m = hasil["evaluasi"]["metrik"]
    row = db.fetch_one(
        "INSERT INTO model_klasifikasi (nama, kecamatan_id, path_model, path_config, akurasi, presisi, recall, f1, "
        "evaluasi, hyperparameter, tanggal_citra, dibuat_oleh) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (nama, hasil["kecamatan_id"], rel_model, rel_config, m["accuracy"], m["precision"],
         m["recall"], m["f1"], db.json(hasil["evaluasi"]), db.json(hasil["params"]),
         [date.fromisoformat(t) for t in hasil["tanggal_citra"]],
         dibuat_oleh),
    )
    buang_job(job_id)
    return detail_model(row["id"])


_KOLOM_MODEL = ("SELECT m.id, m.nama, m.kecamatan_id, k.nama AS kecamatan_nama, m.akurasi, m.presisi, m.recall, "
                "m.f1, m.evaluasi, m.hyperparameter, m.tanggal_citra, m.dibuat_oleh, m.dibuat_pada "
                "FROM model_klasifikasi m JOIN kecamatan k ON k.id = m.kecamatan_id ")


def daftar_model(kecamatan_id: str | None = None) -> list[dict]:
    if kecamatan_id:
        return db.fetch_all(_KOLOM_MODEL + "WHERE m.kecamatan_id = %s ORDER BY m.dibuat_pada DESC", (kecamatan_id,))
    return db.fetch_all(_KOLOM_MODEL + "ORDER BY m.dibuat_pada DESC")


def detail_model(model_id: int) -> dict:
    row = db.fetch_one(_KOLOM_MODEL + "WHERE m.id = %s", (model_id,))
    if row is None:
        raise ProsesError("Model tidak ditemukan.")
    return row


# --- Klasifikasi citra (POST /klasifikasi, GET /klasifikasi/{job}/{nama}, POST /hasil) ---

def mulai_klasifikasi(model_id: int, kecamatan_id: str, tanggal: str, files: Unggahan) -> str:
    model_row = _model(model_id)
    kecamatan = _kecamatan(kecamatan_id)
    try:
        date.fromisoformat(tanggal)
    except ValueError:
        raise ProsesError("Format tanggal harus YYYY-MM-DD.")
    if not TANGGAL_MIN <= tanggal <= TANGGAL_MAKS:
        raise ProsesError(f"Tanggal harus di dalam rentang arsip ({TANGGAL_MIN} s.d. {TANGGAL_MAKS}).")

    job_id = jobs.buat("klasifikasi")
    folder = TMP_DIR / job_id
    if _simpan_unggahan(files, folder / "input", pakai_subfolder_tanggal=False) == 0:
        buang_job(job_id)
        raise ProsesError("Tidak ada berkas saluran yang dikenali.")
    jobs.mulai(job_id, klasifikasi.jalankan, folder, model_row, kecamatan, tanggal)
    return job_id


_BERKAS_HASIL = {"asli.png", "klasifikasi.png", "awan.png", "klasifikasi.tif"}


def berkas_klasifikasi(job_id: str, nama: str) -> bytes:
    """Gambar dan GeoTIFF hasil klasifikasi yang belum disimpan."""
    return _berkas_job(job_id, "klasifikasi", nama, _BERKAS_HASIL)


def simpan_hasil(job_id: str, disimpan_oleh: str | None) -> dict:
    """Simpan hasil klasifikasi supaya muncul di Pemantauan. Hasil lama untuk model,
    kecamatan, dan tanggal yang sama diganti."""
    job = _job_selesai(job_id, "klasifikasi")
    h = job["hasil"]
    folder = TMP_DIR / job_id

    path_raster = HASIL_DIR / h["kecamatan_id"] / f"{h['tanggal']}_model{h['model_id']}.tif"
    path_citra = CITRA_DIR / h["kecamatan_id"] / h["tanggal"]
    rel_raster, rel_citra = storage.relatif(path_raster), storage.relatif(path_citra)
    path_raster.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(folder / "klasifikasi.tif", path_raster)
    storage.hapus(rel_citra)  # citra masukan lama tanggal ini diganti
    shutil.copytree(folder / "input", path_citra)
    storage.kirim(rel_raster)
    storage.kirim(rel_citra)

    row = db.fetch_one(
        "INSERT INTO hasil_klasifikasi (model_id, kecamatan_id, tanggal, luas_terbangun, luas_nonterbangun, "
        "persen_awan, persen_pchip, persen_backward, persen_forward, persen_tidak_terisi, path_raster, path_citra, "
        "disimpan_oleh) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (model_id, kecamatan_id, tanggal) DO UPDATE SET "
        "luas_terbangun = EXCLUDED.luas_terbangun, luas_nonterbangun = EXCLUDED.luas_nonterbangun, "
        "persen_awan = EXCLUDED.persen_awan, persen_pchip = EXCLUDED.persen_pchip, "
        "persen_backward = EXCLUDED.persen_backward, persen_forward = EXCLUDED.persen_forward, "
        "persen_tidak_terisi = EXCLUDED.persen_tidak_terisi, path_raster = EXCLUDED.path_raster, "
        "path_citra = EXCLUDED.path_citra, disimpan_oleh = EXCLUDED.disimpan_oleh, disimpan_pada = now() "
        "RETURNING id",
        (h["model_id"], h["kecamatan_id"], h["tanggal"], h["luas_terbangun"], h["luas_nonterbangun"],
         h["persen_awan"], h["persen_pchip"], h["persen_backward"], h["persen_forward"], h["persen_tidak_terisi"],
         rel_raster, rel_citra, disimpan_oleh),
    )
    return {"id": row["id"]}


# --- Hasil tersimpan dan Pemantauan (GET /hasil, GET /pemantauan) ------------------------

def daftar_hasil(kecamatan_id: str | None = None, model_id: int | None = None) -> list[dict]:
    sql = ("SELECT h.id, h.model_id, m.nama AS model_nama, h.kecamatan_id, h.tanggal, h.luas_terbangun, "
           "h.luas_nonterbangun, h.persen_awan, h.persen_pchip, h.persen_backward, h.persen_forward, "
           "h.persen_tidak_terisi, h.disimpan_oleh, h.disimpan_pada "
           "FROM hasil_klasifikasi h JOIN model_klasifikasi m ON m.id = h.model_id "
           "WHERE (%(kec)s::text IS NULL OR h.kecamatan_id = %(kec)s) "
           "AND (%(model)s::int IS NULL OR h.model_id = %(model)s) ORDER BY h.tanggal")
    return db.fetch_all(sql, {"kec": kecamatan_id, "model": model_id})


def _hasil(hasil_id: int) -> dict:
    row = db.fetch_one("SELECT * FROM hasil_klasifikasi WHERE id = %s", (hasil_id,))
    if row is None:
        raise ProsesError("Hasil klasifikasi tidak ditemukan.")
    return row


def unduh_hasil(hasil_id: int) -> bytes:
    """GeoTIFF hasil klasifikasi tersimpan (GET /hasil/{id}/klasifikasi.tif)."""
    return storage.ambil(_hasil(hasil_id)["path_raster"]).read_bytes()


def bandingkan(awal: int, akhir: int) -> dict:
    """Citra asli dan peta klasifikasi kedua tanggal, peta perubahan (PNG base64), dan luas yang berubah."""
    a, b = _hasil(awal), _hasil(akhir)
    path_a, path_b = storage.ambil(a["path_raster"]), storage.ambil(b["path_raster"])
    peta_a, peta_b = citra.baca(path_a), citra.baca(path_b)
    if peta_a.shape != peta_b.shape:
        raise ProsesError("Ukuran raster kedua tanggal berbeda, jadi tidak bisa dibandingkan per piksel.")
    res = citra.profil(path_a)["res"]
    km2 = res[0] * res[1] / 1e6
    valid = (peta_a != LABEL_NODATA) & (peta_b != LABEL_NODATA)

    def b64(isi: bytes | None) -> str | None:
        return base64.b64encode(isi).decode() if isi else None

    def asli(row) -> bytes | None:
        return citra.png_dari_folder_citra(storage.ambil_folder(row["path_citra"])) if row["path_citra"] else None

    return {
        "awal_asli_png": b64(asli(a)),
        "akhir_asli_png": b64(asli(b)),
        "awal_png": b64(citra.png_klasifikasi(peta_a)),
        "akhir_png": b64(citra.png_klasifikasi(peta_b)),
        "perubahan_png": b64(citra.png_perubahan(peta_a, peta_b)),
        "bertambah": round(float(np.sum(valid & (peta_a == 0) & (peta_b == 1))) * km2, 4),
        "berkurang": round(float(np.sum(valid & (peta_a == 1) & (peta_b == 0))) * km2, 4),
    }


# --- Latih model prediksi (ConvLSTM) -------------------------------------------------------

def _berkas_rf_label(files: Unggahan):
    """(bagian path, isi) untuk unggahan .../<tanggal>/RF_LABEL_*.tif; berkas lain dilewati."""
    for nama, isi in files:
        bagian = _bagian(nama)
        if (len(bagian) >= 2 and peta_tahunan.TANGGAL_RE.fullmatch(bagian[-2])
                and peta_tahunan.RF_LABEL_RE.fullmatch(bagian[-1])):
            yield bagian, isi


def _periksa_rf_label(label: str, isi: bytes, ukuran: tuple | None) -> tuple:
    """Pastikan berkas adalah peta klasifikasi 0/1/255 berukuran sama dengan berkas lain kecamatan itu.
    Mengembalikan ukuran rasternya."""
    try:
        with MemoryFile(isi) as mem, mem.open() as src:
            peta = src.read(1)
    except rasterio.errors.RasterioError:
        raise ProsesError(f"{label}: bukan GeoTIFF yang valid.")
    if not np.isin(peta, (0, 1, LABEL_NODATA)).all():
        raise ProsesError(f"{label}: nilai piksel harus 0, 1, atau 255.")
    if ukuran and peta.shape != ukuran:
        raise ProsesError(f"{label}: ukuran raster {peta.shape} berbeda dengan berkas lain {ukuran}.")
    return peta.shape


def arsip_klasifikasi() -> dict[str, list[int]]:
    """Tahun yang tersedia di arsip klasifikasi tiap kecamatan (GET /arsip-klasifikasi)."""
    tersedia = peta_tahunan.tahun_arsip()
    rows = db.fetch_all("SELECT id, wilayah_id FROM kecamatan")
    return {r["id"]: sorted(tersedia.get((r["wilayah_id"], r["id"]), ())) for r in rows}


def unggah_arsip_klasifikasi(kecamatan_id: str, files: Unggahan) -> dict:
    """Tambah atau ganti peta klasifikasi satu kecamatan (POST /arsip-klasifikasi/{id}).
    Nama berkas: <tanggal>/RF_LABEL_*.tif. Semua berkas diperiksa dulu; jika ada yang tidak valid,
    tidak ada yang ditulis."""
    kecamatan = _kecamatan(kecamatan_id)
    berkas = {bagian[-2]: (Path(bagian[-1]).name, isi) for bagian, isi in _berkas_rf_label(files)}
    if not berkas:
        raise ProsesError("Tidak ada berkas <tanggal>/RF_LABEL_*.tif yang dikenali.")
    ukuran = None
    for tanggal, (nama, isi) in sorted(berkas.items()):
        ukuran = _periksa_rf_label(f"{kecamatan['nama']} {tanggal}/{nama}", isi, ukuran)

    folder = peta_tahunan.folder_arsip(kecamatan["wilayah_id"], kecamatan["id"])
    for tanggal, (nama, isi) in berkas.items():
        rel = storage.relatif(folder / tanggal)
        storage.hapus(rel)  # tanggal yang sudah ada diganti
        (folder / tanggal).mkdir(parents=True)
        (folder / tanggal / nama).write_bytes(isi)
        storage.kirim(rel)
    # Isi arsip berubah, jadi peta tahunan kecamatan ini dibuat ulang saat dipakai berikutnya.
    (CACHE_TAHUNAN_DIR / f"{kecamatan['id']}.npz").unlink(missing_ok=True)
    tahun = peta_tahunan.tahun_arsip().get((kecamatan["wilayah_id"], kecamatan["id"]), ())
    return {"kecamatan_id": kecamatan["id"], "jumlah": len(berkas), "tahun": sorted(tahun)}


def mulai_latih_prediksi(kecamatan_ids: list[str], params: dict) -> str:
    """Latih dari arsip klasifikasi di server (POST /latih-prediksi)."""
    if not kecamatan_ids:
        raise ProsesError("Pilih minimal satu kecamatan.")
    from core import latih_prediksi
    kecamatan = [_kecamatan(k) for k in kecamatan_ids]
    p = _params(_param_prediksi(), params)
    job_id = jobs.buat("latih_prediksi")
    folder = TMP_DIR / job_id
    folder.mkdir(parents=True)
    jobs.mulai(job_id, latih_prediksi.jalankan, folder, kecamatan, p)
    return job_id


def mulai_latih_prediksi_unggah(params: dict, files: Unggahan) -> str:
    """Latih dari folder unggahan (<kecamatan>/<tanggal>/RF_LABEL_*.tif), seperti Latih RF
    (POST /latih-prediksi/unggah): data hanya dipakai untuk pelatihan ini lalu dihapus, tidak masuk arsip."""
    from core import latih_prediksi
    p = _params(_param_prediksi(), params)
    job_id = jobs.buat("latih_prediksi")
    folder = TMP_DIR / job_id
    kecamatan, ukuran = {}, {}
    try:
        for bagian, isi in _berkas_rf_label(files):
            if len(bagian) < 3:
                continue
            k = kecamatan.get(bagian[-3]) or _kecamatan(bagian[-3])
            kecamatan[k["id"]] = k
            ukuran[k["id"]] = _periksa_rf_label(f"{k['nama']} {bagian[-2]}/{bagian[-1]}", isi, ukuran.get(k["id"]))
            tujuan = folder / "input" / k["id"] / bagian[-2]
            tujuan.mkdir(parents=True, exist_ok=True)
            (tujuan / Path(bagian[-1]).name).write_bytes(isi)
        if not kecamatan:
            raise ProsesError("Tidak ada berkas <kecamatan>/<tanggal>/RF_LABEL_*.tif yang dikenali.")
    except ProsesError:
        buang_job(job_id)
        raise
    jobs.mulai(job_id, latih_prediksi.jalankan, folder, list(kecamatan.values()), p)
    return job_id


def simpan_model_prediksi(job_id: str, nama: str, dibuat_oleh: str | None) -> dict:
    """POST /model-prediksi"""
    job = _job_selesai(job_id, "latih_prediksi")
    nama = nama.strip()
    if not nama or len(nama) > 100:
        raise ProsesError("Nama model wajib diisi, maksimal 100 karakter.")
    if db.fetch_one("SELECT 1 FROM model_prediksi WHERE lower(nama) = lower(%s)", (nama,)):
        raise ProsesError("Nama model sudah dipakai.")

    hasil = job["hasil"]
    rel_model, rel_config = _simpan_berkas_model(job_id, "model.keras",
                                                 f"convlstm_{_slug(nama)}_{date.today():%Y%m%d}", hasil["config"])
    m = hasil["evaluasi"]["metrik"]
    row = db.fetch_one(
        "INSERT INTO model_prediksi (nama, kecamatan_ids, path_model, path_config, akurasi, presisi, recall, f1, "
        "evaluasi, hyperparameter, dibuat_oleh) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (nama, hasil["kecamatan_ids"], rel_model, rel_config, m["accuracy"], m["precision"],
         m["recall"], m["f1"], db.json(hasil["evaluasi"]), db.json(hasil["params"]), dibuat_oleh),
    )
    buang_job(job_id)
    return detail_model_prediksi(row["id"])


_KOLOM_MODEL_PREDIKSI = ("SELECT id, nama, kecamatan_ids, akurasi, presisi, recall, f1, evaluasi, hyperparameter, "
                         "dibuat_oleh, dibuat_pada FROM model_prediksi ")


def daftar_model_prediksi(kecamatan_id: str | None = None) -> list[dict]:
    if kecamatan_id:
        return db.fetch_all(_KOLOM_MODEL_PREDIKSI + "WHERE %s = ANY(kecamatan_ids) ORDER BY dibuat_pada DESC",
                            (kecamatan_id,))
    return db.fetch_all(_KOLOM_MODEL_PREDIKSI + "ORDER BY dibuat_pada DESC")


def detail_model_prediksi(model_id: int) -> dict:
    row = db.fetch_one(_KOLOM_MODEL_PREDIKSI + "WHERE id = %s", (model_id,))
    if row is None:
        raise ProsesError("Model tidak ditemukan.")
    return row


# --- Prediksi lahan terbangun (POST /prediksi, GET /prediksi/{job}/{nama}, POST /hasil-prediksi) ---

def mulai_prediksi(model_id: int, kecamatan_id: str, tahun: int) -> str:
    from core import prediksi
    model_row = db.fetch_one("SELECT * FROM model_prediksi WHERE id = %s", (model_id,))
    if model_row is None:
        raise ProsesError("Model tidak ditemukan.")
    kecamatan = _kecamatan(kecamatan_id)
    if kecamatan["id"] not in model_row["kecamatan_ids"]:
        raise ProsesError(f"Model ini tidak dilatih dengan kecamatan {kecamatan['nama']}.")
    tahun_boleh = prediksi.muat_config(model_row["path_config"])["forecast"]["years"]
    if tahun not in tahun_boleh:
        raise ProsesError(f"Tahun prediksi harus salah satu dari {', '.join(map(str, tahun_boleh))}.")

    job_id = jobs.buat("prediksi")
    folder = TMP_DIR / job_id
    folder.mkdir(parents=True)
    jobs.mulai(job_id, prediksi.jalankan, folder, model_row, kecamatan, tahun)
    return job_id


_BERKAS_PREDIKSI = {"prediksi.png", "aktual.png", "perubahan.png", "prediksi.tif"}


def berkas_prediksi(job_id: str, nama: str) -> bytes:
    """Gambar dan GeoTIFF hasil prediksi yang belum disimpan."""
    return _berkas_job(job_id, "prediksi", nama, _BERKAS_PREDIKSI)


def simpan_hasil_prediksi(job_id: str, disimpan_oleh: str | None) -> dict:
    """Simpan hasil prediksi. Hasil lama untuk model, kecamatan, dan tahun yang sama diganti."""
    job = _job_selesai(job_id, "prediksi")
    h = job["hasil"]
    folder = TMP_DIR / job_id
    dasar = PREDIKSI_DIR / h["kecamatan_id"] / f"{h['tahun']}_model{h['model_id']}"
    dasar.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(folder / "prediksi.tif", dasar.with_suffix(".tif"))
    shutil.copy2(folder / "peta.npz", dasar.with_suffix(".npz"))
    rel_raster, rel_peta = storage.relatif(dasar.with_suffix(".tif")), storage.relatif(dasar.with_suffix(".npz"))
    storage.kirim(rel_raster)
    storage.kirim(rel_peta)

    row = db.fetch_one(
        "INSERT INTO hasil_prediksi (model_id, kecamatan_id, tahun, luas_terbangun, luas_nonterbangun, luas_acuan, "
        "luas_terbangun_64, path_raster, path_peta, disimpan_oleh) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (model_id, kecamatan_id, tahun) DO UPDATE SET "
        "luas_terbangun = EXCLUDED.luas_terbangun, luas_nonterbangun = EXCLUDED.luas_nonterbangun, "
        "luas_acuan = EXCLUDED.luas_acuan, luas_terbangun_64 = EXCLUDED.luas_terbangun_64, "
        "path_raster = EXCLUDED.path_raster, path_peta = EXCLUDED.path_peta, "
        "disimpan_oleh = EXCLUDED.disimpan_oleh, disimpan_pada = now() RETURNING id",
        (h["model_id"], h["kecamatan_id"], h["tahun"], h["luas_terbangun"], h["luas_nonterbangun"], h["luas_acuan"],
         h["luas_terbangun_64"], rel_raster, rel_peta, disimpan_oleh),
    )
    return {"id": row["id"]}


def unduh_hasil_prediksi(hasil_id: int) -> bytes:
    """GeoTIFF hasil prediksi tersimpan (GET /hasil-prediksi/{id}/prediksi.tif)."""
    row = db.fetch_one("SELECT path_raster FROM hasil_prediksi WHERE id = %s", (hasil_id,))
    if row is None:
        raise ProsesError("Hasil prediksi tidak ditemukan.")
    return storage.ambil(row["path_raster"]).read_bytes()
