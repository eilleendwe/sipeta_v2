"""Guard halaman: wajib masuk dan pemeriksaan peran."""

import streamlit as st

from services import auth, roles
from ui import layout, nav

_NEXT_KEY = "_next_page"


def require_login() -> dict:
    """Mengembalikan pengguna aktif, atau mengalihkan ke Login jika belum masuk."""
    user = auth.current_user()
    if user is None:
        # Ingat tujuan supaya setelah masuk pengguna dibawa ke halaman yang diminta.
        st.session_state[_NEXT_KEY] = nav.current_key()
        st.switch_page(nav.path("login"))
    return user


def require_role(minimum: str) -> dict:
    """Seperti `require_login`, lalu menghentikan halaman jika peran tidak cukup."""
    user = require_login()
    if not roles.has_role(user["role"], minimum):
        _access_denied(minimum)
        st.stop()
    return user


def redirect_if_logged_in() -> None:
    """Untuk Login dan Register: pengguna yang sudah masuk langsung ke Beranda."""
    if auth.current_user() is not None:
        st.switch_page(nav.path("beranda"))


def pop_next_page() -> str:
    """Halaman tujuan setelah masuk (bawaan Beranda)."""
    key = st.session_state.pop(_NEXT_KEY, None)
    if key is None or nav.get(key).min_role is None:
        return "beranda"
    return key


def _access_denied(minimum: str) -> None:
    with layout.card("akses_ditolak"):
        st.html(
            '<div class="sp-denied">'
            '<span class="sp-denied-ic material-symbols-rounded">lock</span>'
            f"<h2>Akses ditolak — halaman ini khusus {roles.label(minimum)}</h2>"
            "<p>Akun Anda tidak memiliki hak untuk membuka halaman ini. "
            "Hubungi Super Admin jika Anda memerlukan akses.</p>"
            "</div>"
        )
        with st.container(horizontal=True, horizontal_alignment="center"):
            if st.button("Kembali ke Beranda", icon=":material/home:", type="primary", key="btn_denied_home"):
                st.switch_page(nav.path("beranda"))
