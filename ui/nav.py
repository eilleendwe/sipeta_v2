"""Registri halaman: satu sumber untuk app.py, sidebar, bilah tab, dan guard."""

from dataclasses import dataclass

import streamlit as st

from services import roles

_STATE_KEY = "_page_key"


@dataclass(frozen=True)
class PageDef:
    key: str
    file: str
    title: str
    url_path: str
    min_role: str | None = None  # None = publik
    icon: str | None = None
    group: str | None = None  # halaman segrup tampil sebagai tab dalam satu kartu
    menu_label: str | None = None
    tab_label: str | None = None
    chrome: bool = True  # False = halaman penuh tanpa sidebar


PAGES = [
    PageDef("landing", "pages/landing.py", "SIPETA", "", chrome=False),
    PageDef("login", "pages/login.py", "Masuk", "masuk", chrome=False),
    PageDef("register", "pages/register.py", "Daftar", "daftar", chrome=False),
    PageDef("beranda", "pages/beranda.py", "Beranda", "beranda", roles.USER,
            icon=":material/home:", menu_label="Beranda"),
    PageDef("klasifikasi_latih", "pages/klasifikasi_latih.py", "Klasifikasi", "klasifikasi-latih", roles.ADMIN,
            group="klasifikasi", menu_label="Latih model", tab_label="Latih Model"),
    PageDef("klasifikasi_citra", "pages/klasifikasi_citra.py", "Klasifikasi", "klasifikasi-citra", roles.USER,
            group="klasifikasi", menu_label="Klasifikasi citra", tab_label="Klasifikasi Citra"),
    PageDef("prediksi_latih", "pages/prediksi_latih.py", "Prediksi", "prediksi-latih", roles.ADMIN,
            group="prediksi", menu_label="Latih model", tab_label="Latih Model"),
    PageDef("prediksi_citra", "pages/prediksi_citra.py", "Prediksi", "prediksi-citra", roles.USER,
            group="prediksi", menu_label="Prediksi citra", tab_label="Prediksi Citra"),
    PageDef("pemantauan", "pages/pemantauan.py", "Pemantauan", "pemantauan", roles.USER,
            icon=":material/monitoring:", menu_label="Pemantauan"),
    PageDef("panduan", "pages/panduan.py", "Panduan Pengguna", "panduan", roles.USER,
            icon=":material/menu_book:", menu_label="Panduan Pengguna"),
    PageDef("tentang", "pages/tentang.py", "Tentang Penulis", "tentang", roles.USER,
            icon=":material/groups:", menu_label="Tentang Penulis"),
    PageDef("kelola_pengguna", "pages/kelola_pengguna.py", "Kelola Pengguna", "kelola-pengguna", roles.SUPERADMIN,
            icon=":material/manage_accounts:", menu_label="Kelola Pengguna"),
]

# Induk menu untuk halaman bergrup. `default` = halaman yang dibuka saat induk diklik.
GROUPS = {
    "klasifikasi": {"label": "Klasifikasi", "icon": ":material/layers:", "default": "klasifikasi_citra"},
    "prediksi": {"label": "Prediksi", "icon": ":material/timeline:", "default": "prediksi_citra"},
}

# Urutan sidebar. Nama grup diperluas menjadi induk + sub-menu.
MENU = ["beranda", "klasifikasi", "prediksi", "pemantauan", "panduan", "tentang", "kelola_pengguna"]

_BY_KEY = {p.key: p for p in PAGES}


def get(key: str) -> PageDef:
    return _BY_KEY[key]


def path(key: str) -> str:
    """Jalur berkas halaman, untuk `st.page_link` dan `st.switch_page`."""
    return _BY_KEY[key].file


def allowed(key: str, role: str | None) -> bool:
    min_role = _BY_KEY[key].min_role
    return min_role is None or roles.has_role(role, min_role)


def group_pages(group: str, role: str | None) -> list[PageDef]:
    """Halaman dalam satu grup yang boleh diakses `role`, urut seperti di PAGES."""
    return [p for p in PAGES if p.group == group and allowed(p.key, role)]


def run_navigation():
    """Mendaftarkan semua halaman dan mengembalikan (kunci halaman aktif, halaman).

    Semua halaman selalu didaftarkan, termasuk yang tidak boleh diakses peran
    saat ini, supaya alamatnya menampilkan "Akses ditolak" dari guard dan bukan
    "Page not found". Menu yang tampil disaring terpisah di sidebar.
    """
    pages = {
        p.key: st.Page(p.file, title=f"{p.title} · SIPETA" if p.key != "landing" else "SIPETA",
                       url_path=p.url_path, default=(p.key == "landing"))
        for p in PAGES
    }
    current = st.navigation(list(pages.values()), position="hidden")
    key = next((k for k, page in pages.items() if page is current), None)
    if key is None:
        key = next((k for k, page in pages.items() if page.url_path == current.url_path), "landing")
    st.session_state[_STATE_KEY] = key
    return key, current


def current_key() -> str:
    return st.session_state.get(_STATE_KEY, "landing")
