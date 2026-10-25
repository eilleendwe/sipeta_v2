"""Bilah tab di puncak kartu untuk halaman bergrup (Klasifikasi, Prediksi).

Tiap tab adalah tautan ke halaman saudara, bukan `st.tabs`. Halaman yang aktif
menjadi satu-satunya sumber kebenaran, sehingga tab dan sub-menu sidebar tidak
mungkin berbeda.
"""

import streamlit as st

from ui import nav


def tab_bar(group: str, role: str | None) -> None:
    aktif = nav.current_key()
    with st.container(key=f"tabbar_{group}", horizontal=True, gap="medium"):
        for page in nav.group_pages(group, role):
            state = "on" if page.key == aktif else "off"
            with st.container(key=f"tab_{state}_{page.key}", width="content"):
                st.page_link(nav.path(page.key), label=page.tab_label)
