"""Data halaman Tentang Penulis, dibaca dari data/authors.json."""

import base64
import json
import mimetypes
from pathlib import Path

from services.errors import ServiceError

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _inisial(nama: str) -> str:
    """Huruf depan nama pertama dan terakhir, tanpa gelar ("Prof. Dr. Budi Santoso, M.Si" -> "BS")."""
    kata = [k for k in nama.split(",")[0].split() if "." not in k and k[:1].isalpha()]
    return "".join(k[0] for k in (kata[:1] + kata[1:][-1:])).upper() or "?"


def _foto(nama_berkas: str | None) -> str | None:
    """Foto sebagai data URI, atau None jika belum ada (tampilan memakai inisial)."""
    if not nama_berkas:
        return None
    jalur = (_DATA_DIR / nama_berkas).resolve()
    if _DATA_DIR not in jalur.parents or not jalur.is_file():
        return None
    mime = mimetypes.guess_type(jalur.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(jalur.read_bytes()).decode()}"


def get_authors() -> dict:
    """{"judul": str, "deskripsi": [paragraf], "penulis": [{"nama", "keterangan", "inisial", "foto"}]}.
    `foto` di JSON adalah nama berkas di folder data/ (mis. "foto/penulis.jpg")."""
    try:
        data = json.loads((_DATA_DIR / "authors.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ServiceError("Data penulis tidak dapat dibaca. Periksa berkas data/authors.json.")
    return {
        "judul": data.get("judul", ""),
        # deskripsi boleh satu teks atau daftar paragraf
        "deskripsi": [data["deskripsi"]] if isinstance(data.get("deskripsi"), str) else data.get("deskripsi", []),
        "penulis": [
            {
                "nama": p.get("nama", ""),
                "keterangan": p.get("keterangan", ""),
                "inisial": _inisial(p.get("nama", "")),
                "foto": _foto(p.get("foto")),
            }
            for p in data.get("penulis", [])
        ],
    }
