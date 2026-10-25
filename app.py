"""SIPETA — titik masuk. Jalankan dengan: streamlit run app.py"""

import streamlit as st

from core import operasi
from services import auth
from services.errors import ServiceError
from ui import layout, nav, sidebar


@st.cache_resource(show_spinner=False)
def _siapkan() -> None:
    """Sekali per proses app: bersihkan berkas sementara, buat folder, periksa pengaturan storage."""
    operasi.siapkan()


st.set_page_config(
    page_icon=layout.LOGO_PNG,
    layout="wide",
    initial_sidebar_state="expanded",
)
layout.inject_css()

try:
    _siapkan()
except RuntimeError as e:  # pengaturan database atau storage tidak valid
    st.error(str(e), icon=":material/error:")
    st.stop()

page_key, page = nav.run_navigation()

# Sidebar hanya untuk halaman aplikasi dan hanya saat sudah masuk. Halaman yang
# belum boleh dibuka akan dialihkan atau ditolak oleh guard di dalam halaman.
try:
    user = auth.current_user()
except ServiceError as e:
    st.error(e.message, icon=":material/error:")
    st.stop()
if user and nav.get(page_key).chrome:
    sidebar.render(page_key, user)

layout.show_flash()
page.run()
