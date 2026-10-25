from html import escape

import streamlit as st

from services import about, roles
from services.errors import ServiceError
from ui import guard, layout

guard.require_role(roles.USER)


def _profil(p: dict) -> str:
    if p["foto"]:
        avatar = f'<img class="sp-avatar" src="{p["foto"]}" alt="Foto {escape(p["nama"])}">'
    else:
        avatar = f'<div class="sp-avatar sp-avatar-inisial">{escape(p["inisial"])}</div>'
    return (
        f'<div class="sp-author">{avatar}'
        f'<div class="sp-author-name">{escape(p["nama"])}</div>'
        f'<div class="sp-author-role">{escape(p["keterangan"])}</div></div>'
    )


layout.page_header("Tentang Penulis")
with layout.card("tentang"):
    try:
        data = about.get_authors()
    except ServiceError as e:
        st.error(e.message, icon=":material/error:")
        st.stop()

    if data["judul"]:
        layout.section("Judul skripsi")
        st.html(f'<div class="sp-judul">{escape(data["judul"])}</div>')

    layout.section("Penulis dan dosen pembimbing")
    if not data["penulis"]:
        layout.empty_state("Data penulis belum diisi.", "groups")
    else:
        st.html('<div class="sp-authors">' + "".join(_profil(p) for p in data["penulis"]) + "</div>")

    if data["deskripsi"]:
        st.divider()
        layout.section("Tentang SIPETA")
        st.html("".join(f'<p class="sp-body">{escape(par)}</p>' for par in data["deskripsi"]))
