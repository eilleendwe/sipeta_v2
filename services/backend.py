"""Pemanggilan core/ dari services/. Pengganti services/api_client.py, yang dulu memanggil
backend FastAPI lewat HTTP; sekarang fungsi core.operasi dipanggil langsung di proses Streamlit.

Hasil tiap panggilan dibentuk ulang seperti JSON (tanggal menjadi teks ISO, tuple menjadi list,
kunci dict menjadi teks), jadi services lain menerima data dengan bentuk yang sama persis seperti
saat masih lewat API.
"""

import json
import logging
import time
from datetime import date, datetime

import numpy as np
import psycopg

from core import operasi
from core.jobs import ProsesError
from services.errors import ServiceError

log = logging.getLogger("sipeta")


def _json(nilai):
    def lain(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if isinstance(o, np.generic):
            return o.item()
        raise TypeError(f"{type(o).__name__} tidak bisa diubah ke JSON")
    return json.loads(json.dumps(nilai, default=lain))


def panggil(fungsi, *args, **kwargs):
    """Jalankan `fungsi(*args, **kwargs)`. Galat diubah menjadi ServiceError yang aman ditampilkan."""
    try:
        hasil = fungsi(*args, **kwargs)
    except ProsesError as e:
        raise ServiceError(str(e), e.fields) from None
    except psycopg.Error as e:
        pesan = str(e).strip().splitlines()[0] if str(e).strip() else e.__class__.__name__
        raise ServiceError(f"Database tidak dapat diakses: {pesan}") from None
    except FileNotFoundError as e:
        raise ServiceError(f"Berkas tidak ditemukan di storage: {e}") from None
    except Exception as e:  # galat tak terduga: catat lengkap di log, tampilkan ringkas
        log.exception("Gagal menjalankan %s", getattr(fungsi, "__name__", fungsi))
        raise ServiceError(f"Terjadi kesalahan saat memproses: {e}") from None
    return hasil if hasil is None or isinstance(hasil, bytes) else _json(hasil)


def pantau_job(job_id: str, jeda: float = 1.0):
    """Ambil status job berulang sampai selesai atau gagal. Menghasilkan status terbaru."""
    while True:
        job = panggil(operasi.status_job, job_id)
        yield job
        if job["status"] in ("selesai", "gagal"):
            return
        time.sleep(jeda)
