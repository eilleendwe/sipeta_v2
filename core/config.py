"""Pengaturan: lokasi penyimpanan, koneksi database, dan konstanta citra."""

import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Salinan diambil sebelum st.secrets dibaca: Streamlit menyalin isi secrets.toml ke os.environ
# dan menimpa environment variable bernama sama.
_ENV = dict(os.environ)

# secrets.toml di folder proyek dibaca langsung. st.secrets hanya mencari di folder kerja saat
# perintah dijalankan, jadi tanpa ini perintah dari folder lain jatuh ke nilai bawaan.
try:
    _SECRETS = tomllib.loads((ROOT / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
except (OSError, tomllib.TOMLDecodeError):
    _SECRETS = {}


def _pengaturan(nama: str, bawaan: str | None = None) -> str | None:
    """Nilai dari environment variable (Hugging Face Spaces, terminal), lalu dari
    .streamlit/secrets.toml di folder proyek (lokal), lalu st.secrets (Streamlit Community Cloud),
    lalu nilai bawaan."""
    if _ENV.get(nama):
        return _ENV[nama]
    if nama in _SECRETS:
        return str(_SECRETS[nama])
    try:
        import streamlit as st
        if nama in st.secrets:
            return str(st.secrets[nama])
    except Exception:  # secrets.toml tidak ada
        pass
    return bawaan


def tujuan_db(url: str) -> str:
    """Connection string tanpa kata sandi, untuk dicetak: host:port/nama_database."""
    from psycopg.conninfo import conninfo_to_dict
    try:
        info = conninfo_to_dict(url)
    except Exception:
        return "SIPETA_DB tidak valid"
    return f"{info.get('host', 'localhost')}:{info.get('port', 5432)}/{info.get('dbname', '?')}"


def periksa_db_url() -> None:
    """Pastikan SIPETA_DB bisa dibaca sebagai connection string. Dipanggil sekali saat app dinyalakan,
    supaya kesalahan tempel (mis. alamat terpotong ke baris baru di Secrets) langsung terlihat jelas."""
    from psycopg.conninfo import conninfo_to_dict
    try:
        conninfo_to_dict(DB_URL)
    except Exception as e:
        raise RuntimeError(
            "Pengaturan SIPETA_DB tidak valid. Biasanya karena alamatnya terpotong ke baris baru atau ada spasi "
            f"saat ditempel ke Secrets. Tulis ulang dalam satu baris tanpa spasi. Detail: {e}") from None


# Bisa diganti tanpa mengubah kode.
DB_URL = _pengaturan("SIPETA_DB", "postgresql://postgres:lambo@localhost:5432/sipeta")
STORAGE = Path(_pengaturan("SIPETA_STORAGE", str(ROOT / "storage")))

# "lokal" = berkas hanya di folder STORAGE (development). "s3" = berkas disimpan permanen di object storage
# S3-compatible (Cloudflare R2, Backblaze B2, Supabase Storage, ...); folder STORAGE menjadi cache.
STORAGE_MODE = _pengaturan("SIPETA_STORAGE_MODE", "lokal")
S3_ENDPOINT = (_pengaturan("SIPETA_S3_ENDPOINT") or "").strip().rstrip("/") or None
if S3_ENDPOINT and "://" not in S3_ENDPOINT:  # dashboard sering menampilkan endpoint tanpa https://
    S3_ENDPOINT = f"https://{S3_ENDPOINT}"
S3_BUCKET = _pengaturan("SIPETA_S3_BUCKET")
S3_KEY = _pengaturan("SIPETA_S3_KEY")
S3_SECRET = _pengaturan("SIPETA_S3_SECRET")
S3_REGION = _pengaturan("SIPETA_S3_REGION", "auto")

ARSIP_DIR = STORAGE / "arsip"    # arsip/<wilayah>/<kecamatan>/<YYYY-MM-DD>/*_B02_10m.tif ... *_SCL_10m.tif
MODEL_DIR = STORAGE / "model"    # model tersimpan (.pkl) + konfigurasi (.json)
HASIL_DIR = STORAGE / "hasil"    # raster hasil klasifikasi yang disimpan
CITRA_DIR = STORAGE / "citra"    # citra masukan dari hasil klasifikasi yang disimpan
TMP_DIR = STORAGE / "tmp"        # unggahan dan hasil yang belum disimpan
PREDIKSI_DIR = STORAGE / "prediksi"  # hasil prediksi yang disimpan (GeoTIFF 10 m + peta 64x64 .npz)

# Masukan ConvLSTM: peta klasifikasi 0/1 per tanggal dari notebook (kecamatan_masked_rf_classified),
# disalin ke arsip_klasifikasi/<wilayah>/<kecamatan>/<YYYY-MM-DD>/RF_LABEL_*.tif
ARSIP_KLASIFIKASI_DIR = STORAGE / "arsip_klasifikasi"
CACHE_TAHUNAN_DIR = STORAGE / "cache_tahunan"  # peta tahunan per kecamatan (.npz), dibuat otomatis

# Rentang arsip. PCHIP hanya mengisi di antara observasi, jadi citra di luar
# rentang ini tidak diterima.
TANGGAL_MIN = "2016-01-01"
TANGGAL_MAKS = "2025-12-31"

BANDS_LATIH = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B11", "B12"]
FITUR = ["B02", "B03", "B04", "B05", "B06", "B07", "B12"]

TAHUN_DATA = list(range(2016, 2026))  # peta tahunan aktual untuk ConvLSTM

LABEL_NODATA = 255
LUAS_PIKSEL_M2 = 100  # 10 m x 10 m
