"""Model tersimpan dan pelatihan.

Random Forest (Klasifikasi) dan ConvLSTM (Prediksi) sama-sama dilatih sebagai job latar
belakang (core.jobs); `train` memantau statusnya. Keduanya menghasilkan kejadian progres
dengan bentuk yang sama, jadi halaman tidak perlu membedakan.
"""

import re
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Iterator

from core import operasi
from services import arsip, auth, backend, regions, roles
from services.errors import ServiceError

RF = "rf"
CONVLSTM = "convlstm"
ALGORITMA = {RF: "Random Forest", CONVLSTM: "ConvLSTM"}

OPTIMIZER = {"adam": "Adam", "adamw": "AdamW", "nadam": "Nadam", "rmsprop": "RMSprop", "sgd": "SGD"}
SUMBER_ARSIP, SUMBER_UNGGAH = "arsip", "unggah"
SUMBER_DATA = {SUMBER_ARSIP: "Arsip di server", SUMBER_UNGGAH: "Unggah folder"}  # data latih ConvLSTM

BANDS_LATIH = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B11", "B12", "SCL"]
TANGGAL_MIN, TANGGAL_MAKS = date(2016, 1, 1), date(2025, 12, 31)
_SALURAN_RE = re.compile(r"(?<![A-Za-z0-9])(B0[2-8]|B1[12]|SCL)(?![A-Za-z0-9])", re.IGNORECASE)
_TANGGAL_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def default_params(algoritma: str) -> dict:
    if algoritma == RF:
        # Titik awal dari Grid Search notebook (dituning pada 384.000 sampel gabungan 40 kecamatan).
        return {
            "n_trees": 30,
            "max_depth": 16,
            "min_samples_split": 10,
            "n_features": 3,
            "max_thresholds": 20,
            "train_ratio": 0.8,
            "test_ratio": 0.2,
            "sampel_per_tanggal": 1000,  # None = seluruh piksel cerah
        }
    # Konfigurasi terpilih notebook v7 (catatan bagian 14); ganti dengan hasil grid search v8 jika sudah ada.
    return {
        "sequence_length": 4,
        "n_layers": 2,
        "filters": 40,
        "kernel_size": 5,
        "dropout": 0.0,
        "learning_rate": 0.0005,
        "optimizer": "adam",
        "max_epochs": 100,
        "batch_size": 8,
        "train_ratio": 0.5,
        "val_ratio": 0.17,
        "test_ratio": 0.33,
    }


# Keterangan di bawah label tiap hyperparameter pada form Latih Model:
# (penjelasan singkat, nilai yang direkomendasikan).
REKOMENDASI = {
    RF: {
        "n_trees": ("Banyaknya pohon keputusan dalam model", "30"),
        "max_depth": ("Kedalaman maksimum tiap pohon", "16"),
        "min_samples_split": ("Sampel minimum untuk memecah simpul", "10"),
        "n_features": ("Saluran yang dicoba di tiap percabangan", "3"),
        "max_thresholds": ("Batas nilai yang dicoba per saluran", "20"),
        "train_ratio": ("Porsi blok spasial untuk melatih model", "0,8"),
        "test_ratio": ("Porsi blok spasial untuk menguji model", "0,2"),
        "sampel_per_tanggal": ("Piksel acak yang diambil dari tiap tanggal", "1.000"),
    },
    CONVLSTM: {
        "sequence_length": ("Jumlah peta tahunan berurutan sebagai masukan", "4"),
        "n_layers": ("Banyaknya layer ConvLSTM", "2"),
        "filters": ("Jumlah filter di tiap layer ConvLSTM", "40"),
        "kernel_size": ("Ukuran jendela konvolusi, dalam sel 64×64", "5"),
        "dropout": ("Porsi masukan yang dinolkan acak saat latih", "0"),
        "learning_rate": ("Besar langkah pembaruan bobot", "0,0005"),
        "optimizer": ("Algoritma pembaruan bobot", "Adam"),
        "max_epochs": ("Batas epoch; early stopping bisa berhenti lebih awal", "100"),
        "batch_size": ("Jumlah sampel per langkah latih", "8"),
        "train_ratio": ("Porsi tahun target untuk melatih", "0,5"),
        "val_ratio": ("Porsi tahun target untuk memilih epoch", "0,17"),
        "test_ratio": ("Porsi tahun target untuk menguji", "0,33"),
    },
}


# --- Baca -------------------------------------------------------------------

_DAFTAR = {RF: operasi.daftar_model, CONVLSTM: operasi.daftar_model_prediksi}
_DETAIL = {RF: operasi.detail_model, CONVLSTM: operasi.detail_model_prediksi}
_SIMPAN = {RF: operasi.simpan_model, CONVLSTM: operasi.simpan_model_prediksi}


def _dari_baris(algoritma: str, row: dict) -> dict:
    """Baris model_klasifikasi / model_prediksi -> bentuk model yang dipakai halaman."""
    return {
        "id": row["id"],
        "nama": row["nama"],
        "algoritma": algoritma,
        "wilayah_id": None,
        "kecamatan_ids": [row["kecamatan_id"]] if algoritma == RF else row["kecamatan_ids"],
        "evaluasi": row["evaluasi"],
        "params": row["hyperparameter"],
        "tanggal_latih": datetime.fromisoformat(row["dibuat_pada"]).date(),
        "dibuat_oleh": row["dibuat_oleh"],
    }


def covers(model: dict, kecamatan_id: str) -> bool:
    return kecamatan_id in model["kecamatan_ids"]


def list_models(algoritma: str, kecamatan_id: str | None = None) -> list[dict]:
    """Model tersimpan, terbaru dulu. Jika `kecamatan_id` diisi, hanya model
    yang cakupannya memuat kecamatan itu."""
    return [_dari_baris(algoritma, r) for r in backend.panggil(_DAFTAR[algoritma], kecamatan_id)]


def get(algoritma: str, model_id: int | None) -> dict | None:
    if model_id is None:
        return None
    try:
        return _dari_baris(algoritma, backend.panggil(_DETAIL[algoritma], model_id))
    except ServiceError:
        return None


def coverage_label(model: dict) -> str:
    """Ringkasan cakupan kecamatan sebuah model."""
    ids = model["kecamatan_ids"]
    if len(ids) == len(regions.list_kecamatan()):
        return "semua kecamatan"
    if model.get("wilayah_id"):
        wilayah = regions.get_wilayah(model["wilayah_id"])
        if wilayah and len(ids) == len(regions.list_kecamatan(model["wilayah_id"])):
            return f"{wilayah['nama']} ({len(ids)} kecamatan)"
    if len(ids) <= 2:
        return ", ".join(regions.nama_kecamatan(i) for i in ids)
    return f"{len(ids)} kecamatan"


# --- Folder citra latih (Random Forest) ----------------------------------------

def scan_folder(nama_berkas: list[str], kecamatan_id: str | None) -> dict:
    """Memeriksa struktur folder citra latih dari nama berkas saja. Isi berkas
    (grid, CRS) diperiksa core.latih saat pelatihan dimulai.

    Struktur yang diharapkan: <kecamatan>/<YYYY-MM-DD>/<...>_B02_10m.tif (9 band + SCL)."""
    akar, per_tanggal, diabaikan = set(), {}, []
    for nama in nama_berkas:
        bagian = PurePosixPath(nama.replace("\\", "/")).parts
        akar.add(bagian[0] if len(bagian) > 1 else "")
        cocok = _SALURAN_RE.search(bagian[-1])
        if len(bagian) < 3 or not _TANGGAL_RE.fullmatch(bagian[-2]) or not cocok:
            diabaikan.append(nama)
            continue
        per_tanggal.setdefault(bagian[-2], {}).setdefault(cocok.group(1).upper(), []).append(nama)

    baris, berkas_valid = [], []
    for tanggal, saluran in sorted(per_tanggal.items()):
        kurang = [b for b in BANDS_LATIH if b not in saluran]
        ganda = [b for b, daftar in saluran.items() if len(daftar) > 1]
        try:
            t = date.fromisoformat(tanggal)
        except ValueError:
            t = None
        if t is None:
            status, ket = "gagal", "nama folder bukan tanggal yang valid"
        elif not TANGGAL_MIN <= t <= TANGGAL_MAKS:
            status, ket = "gagal", f"di luar rentang arsip {TANGGAL_MIN.year}–{TANGGAL_MAKS.year}"
        elif kurang:
            status, ket = "gagal", f"{', '.join(kurang)} tidak ada"
        elif ganda:
            status, ket = "gagal", f"{', '.join(ganda)} ganda"
        else:
            status, ket = "valid", "9 band + SCL"
            berkas_valid += [daftar[0] for b, daftar in saluran.items() if b in BANDS_LATIH]
        baris.append({"tanggal": tanggal, "saluran": ket, "status": status})

    nama_akar = next(iter(akar)) if len(akar) == 1 else None
    kecamatan = regions.get_kecamatan(kecamatan_id)
    akar_cocok = bool(nama_akar and kecamatan and (regions.nama_sama(nama_akar, kecamatan["id"])
                                                    or regions.nama_sama(nama_akar, kecamatan["nama"])))
    return {
        "akar": nama_akar,
        "akar_cocok": akar_cocok,
        "baris": baris,
        "jumlah_valid": sum(b["status"] == "valid" for b in baris),
        "berkas_valid": berkas_valid,
        "diabaikan": diabaikan,
    }


# --- Pembagian tahun (ConvLSTM) -----------------------------------------------------

def pembagian_tahun(p: dict) -> dict[str, list[int]] | None:
    """Tahun target 2020–2025 dipotong urut waktu menurut rasio (sama dengan split_years_by_ratio
    di core/latih_prediksi.py). None jika tidak ada tahun yang tersisa untuk train."""
    tahun = list(range(arsip.TAHUN_DATA[0] + 4, arsip.TAHUN_DATA[-1] + 1))
    total = p["train_ratio"] + p["val_ratio"] + p["test_ratio"]
    n_test = max(1, round(len(tahun) * p["test_ratio"] / total))
    n_val = max(1, round(len(tahun) * p["val_ratio"] / total))
    n_train = len(tahun) - n_val - n_test
    if n_train < 1:
        return None
    return {"train": tahun[:n_train], "val": tahun[n_train:n_train + n_val], "test": tahun[n_train + n_val:]}


# --- Validasi ---------------------------------------------------------------

def _name_taken(algoritma: str, nama: str) -> bool:
    kunci = nama.strip().lower()
    return any(m["nama"].lower() == kunci for m in list_models(algoritma))


def validate(algoritma: str, spec: dict) -> dict[str, str]:
    """Galat per field (kunci = nama field). Dict kosong berarti valid."""
    galat: dict[str, str] = {}
    p = spec["params"]

    nama = (spec.get("nama") or "").strip()
    if not nama:
        galat["nama"] = "Nama model wajib diisi."
    elif _name_taken(algoritma, nama):
        galat["nama"] = "Nama model sudah dipakai."

    if algoritma == RF:
        if not spec.get("kecamatan_id"):
            galat["kecamatan"] = "Pilih kecamatan."
        laporan = scan_folder([f.name for f in spec.get("berkas") or []], spec.get("kecamatan_id"))
        if not spec.get("berkas"):
            galat["folder"] = "Unggah folder citra kecamatan."
        elif spec.get("kecamatan_id") and not laporan["akar_cocok"]:
            galat["folder"] = "Nama folder harus sama dengan kecamatan yang dipilih."
        elif laporan["jumlah_valid"] == 0:
            galat["folder"] = "Tidak ada subfolder tanggal yang lengkap (9 band + SCL)."
        if abs(p["train_ratio"] + p["test_ratio"] - 1) > 1e-6:
            galat["rasio"] = "Jumlah train ratio dan test ratio harus 1."
        return galat

    if spec.get("sumber") == SUMBER_UNGGAH:
        laporan = arsip.scan_folder([f.name for f in spec.get("berkas") or []])
        if not spec.get("berkas"):
            galat["folder"] = "Unggah folder peta klasifikasi."
        elif not any(b["lengkap"] for b in laporan["baris"]):
            galat["folder"] = (f"Tidak ada kecamatan di folder yang punya peta lengkap "
                               f"{arsip.TAHUN_DATA[0]}–{arsip.TAHUN_DATA[-1]}.")
    elif not spec.get("kecamatan_ids"):
        galat["kecamatan"] = "Pilih minimal satu kecamatan."
    elif not arsip.lengkap(spec["kecamatan_ids"]):
        galat["kecamatan"] = (f"Belum ada kecamatan terpilih yang punya arsip klasifikasi lengkap "
                              f"{arsip.TAHUN_DATA[0]}–{arsip.TAHUN_DATA[-1]}.")
    if min(p["train_ratio"], p["test_ratio"], p["val_ratio"]) <= 0:
        galat["rasio"] = "Train, validation, dan test ratio harus lebih dari 0."
    elif abs(p["train_ratio"] + p["test_ratio"] + p["val_ratio"] - 1) > 1e-6:
        galat["rasio"] = "Jumlah train, validation, dan test ratio harus 1."
    if p["kernel_size"] % 2 == 0:
        galat["kernel_size"] = "Kernel size harus ganjil."
    return galat


def _require_admin() -> dict:
    user = auth.current_user()
    if user is None or not roles.has_role(user["role"], roles.ADMIN):
        raise ServiceError("Hanya Admin yang dapat melatih dan menyimpan model.")
    return user


# --- Latih dan simpan -------------------------------------------------------

def _event(progress: float, label: str, result: dict | None = None) -> dict:
    return {"progress": min(max(progress, 0.0), 1.0), "label": label, "result": result}


def train(algoritma: str, spec: dict) -> Iterator[dict]:
    """Menjalankan pelatihan. Menghasilkan kejadian
    `{"progress": 0..1, "label": str, "result": dict | None}`; kejadian terakhir
    membawa `result` = calon model (belum tersimpan) beserta evaluasinya.
    Satu kejadian membawa `job_id`, supaya halaman bisa melanjutkan pemantauan (`resume`)."""
    _require_admin()
    galat = validate(algoritma, spec)
    if galat:
        raise ServiceError("Periksa kembali isian form.", galat)
    if algoritma == RF:
        files = _berkas_rf(spec)
        yield _event(0.0, f"Menyiapkan {len(files)} berkas citra…")
        params = {k: v for k, v in spec["params"].items() if k != "train_ratio"}
        job_id = backend.panggil(operasi.mulai_latih, spec["kecamatan_id"], params, files)
    elif spec.get("sumber") == SUMBER_UNGGAH:
        # Hanya kecamatan yang lengkap 2016–2025 yang dikirim; yang lain tidak akan dipakai.
        laporan = arsip.scan_folder([f.name for f in spec["berkas"]])
        files = [berkas for b in laporan["baris"] if b["lengkap"]
                 for berkas in arsip.kemas_berkas(laporan, spec["berkas"], b["kecamatan_id"], folder_kecamatan=True)]
        yield _event(0.0, f"Memeriksa {len(files)} peta klasifikasi…")
        job_id = backend.panggil(operasi.mulai_latih_prediksi_unggah, spec["params"], files)
    else:
        job_id = backend.panggil(operasi.mulai_latih_prediksi, spec["kecamatan_ids"], spec["params"])
    yield {**_event(0.0, "Menunggu giliran…"), "job_id": job_id}
    yield from resume(algoritma, spec, job_id)


def resume(algoritma: str, spec: dict, job_id: str) -> Iterator[dict]:
    """Memantau job latih sampai selesai. Job tetap berjalan di latar belakang walau
    halaman ditinggalkan, jadi pemantauan bisa dilanjutkan saat halaman dibuka lagi."""
    for job in backend.pantau_job(job_id):
        yield _event(job["progress"], job["label"])
    if job["status"] == "gagal":
        raise ServiceError(job["pesan"])

    hasil = job["hasil"]
    draft = {
        "nama": spec["nama"].strip(),
        "algoritma": algoritma,
        "job_id": job_id,
        "wilayah_id": spec.get("wilayah_id"),
        "params": spec["params"],
        "evaluasi": hasil["evaluasi"],
    }
    if algoritma == RF:
        draft["kecamatan_ids"] = [spec["kecamatan_id"]]
    else:
        draft["kecamatan_ids"] = hasil["kecamatan_ids"]
    yield _event(1.0, "Selesai", draft)


def _berkas_rf(spec: dict) -> list:
    """Berkas valid dari folder unggahan sebagai (nama, isi). Hanya subfolder tanggal + nama berkas
    yang dipakai; nama folder kecamatan dibuang."""
    dipakai = set(scan_folder([f.name for f in spec["berkas"]], spec["kecamatan_id"])["berkas_valid"])
    return [
        ("/".join(PurePosixPath(f.name.replace("\\", "/")).parts[-2:]), f.getvalue())
        for f in spec["berkas"] if f.name in dipakai
    ]


def save(draft: dict) -> dict:
    """Menyimpan calon model hasil `train` ke daftar model tersimpan."""
    user = _require_admin()
    row = backend.panggil(_SIMPAN[draft["algoritma"]], draft["job_id"], draft["nama"], user["nama"])
    return _dari_baris(draft["algoritma"], row)


def discard(draft: dict) -> None:
    """Membuang calon model. Berkas sementaranya ikut dihapus."""
    if draft.get("job_id"):
        try:
            backend.panggil(operasi.buang_job, draft["job_id"])
        except ServiceError:
            pass  # app mungkin sudah dijalankan ulang; tidak ada yang perlu dibuang
