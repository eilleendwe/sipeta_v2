"""Autentikasi dan pengelolaan pengguna (tabel pengguna di PostgreSQL, lewat core.pengguna).

Sesi login disimpan di `st.session_state` (hanya id pengguna); data akunnya
dibaca ulang dari database di setiap rerun.
"""

import re
from datetime import date

import streamlit as st

from core import pengguna
from services import backend, roles
from services.errors import ServiceError

_SESSION_KEY = "auth_user_id"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
ATURAN_SANDI = f"Minimal {MIN_PASSWORD} karakter, memuat 1 huruf besar dan 1 angka."


def _password_error(password: str) -> str | None:
    """Aturan kata sandi yang belum terpenuhi, atau None jika sudah memenuhi semuanya."""
    kurang = []
    if len(password) < MIN_PASSWORD:
        kurang.append(f"minimal {MIN_PASSWORD} karakter")
    if not any(c.isupper() for c in password):
        kurang.append("1 huruf besar")
    if not any(c.isdigit() for c in password):
        kurang.append("1 angka")
    return f"Kata sandi harus memuat {', '.join(kurang)}." if kurang else None


def _rapikan(user: dict) -> dict:
    return {**user, "tanggal_daftar": date.fromisoformat(user["tanggal_daftar"])}


# --- Sesi -------------------------------------------------------------------

def current_user() -> dict | None:
    """Pengguna yang sedang masuk. Dibaca dari database di setiap rerun,
    jadi perubahan peran oleh Super Admin langsung berlaku."""
    uid = st.session_state.get(_SESSION_KEY)
    if not uid:
        return None
    user = backend.panggil(pengguna.detail, uid)
    if user is None:
        st.session_state.pop(_SESSION_KEY, None)
        return None
    return _rapikan(user)


def login(email: str, password: str) -> dict:
    if not email.strip() or not password:
        raise ServiceError("Email dan kata sandi wajib diisi.")
    user = backend.panggil(pengguna.masuk, email, password)
    st.session_state[_SESSION_KEY] = user["id"]
    return _rapikan(user)


def logout() -> None:
    """Mengakhiri sesi dan membuang seluruh state sesi: isian form, hasil
    klasifikasi/prediksi, dan evaluasi yang belum disimpan. Tanpa ini, akun
    berikutnya di peramban yang sama akan melihat sisa pekerjaan akun sebelumnya."""
    st.session_state.clear()


def register(nama: str, email: str, password: str, konfirmasi: str) -> dict:
    """Membuat akun baru. Peran selalu Pengguna; tidak ada cara memilih peran."""
    nama, email = nama.strip(), email.strip().lower()
    fields: dict[str, str] = {}
    if not nama:
        fields["nama"] = "Nama lengkap wajib diisi."
    if not email:
        fields["email"] = "Email wajib diisi."
    elif not _EMAIL_RE.match(email):
        fields["email"] = "Format email tidak valid."
    if not password:
        fields["password"] = "Kata sandi wajib diisi."
    elif _password_error(password):
        fields["password"] = _password_error(password)
    if not konfirmasi:
        fields["konfirmasi"] = "Konfirmasi kata sandi wajib diisi."
    elif password and konfirmasi != password:
        fields["konfirmasi"] = "Konfirmasi kata sandi tidak cocok."
    if fields:
        raise ServiceError("Periksa kembali isian form.", fields)

    # Email yang sudah terdaftar ditolak core.pengguna dengan pesan untuk field email.
    user = backend.panggil(pengguna.daftar, nama, email, password)
    st.session_state[_SESSION_KEY] = user["id"]
    return _rapikan(user)


# --- Kelola Pengguna (Super Admin) ------------------------------------------

def list_users(cari: str = "", role: str | None = None) -> list[dict]:
    hasil = [_rapikan(u) for u in backend.panggil(pengguna.daftar_pengguna, cari, role)]
    return sorted(hasil, key=lambda u: (-roles.level(u["role"]), u["tanggal_daftar"], u["nama"]))


def role_change_blocker(actor: dict, target: dict) -> str | None:
    """Alasan peran `target` tidak boleh diubah oleh `actor`, atau None jika boleh.
    Pengecekan Super Admin terakhir dilakukan core.pengguna saat peran disimpan."""
    if not roles.has_role(actor["role"], roles.SUPERADMIN):
        return "Hanya Super Admin yang dapat mengubah peran."
    if actor["id"] == target["id"]:
        return "Anda tidak dapat mengubah peran sendiri."
    return None


def change_role(target_id: int, new_role: str) -> dict:
    actor = current_user()
    if actor is None:
        raise ServiceError("Sesi berakhir. Silakan masuk kembali.")
    user = backend.panggil(pengguna.ubah_peran, target_id, new_role, actor["id"])
    return _rapikan(user)
