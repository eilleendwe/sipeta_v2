from html import escape
from pathlib import Path

import streamlit as st

from services import classify, regions, roles
from services.errors import ServiceError
from ui import guard, layout, nav

guard.require_role(roles.USER)

_PETA_DIR = Path(__file__).resolve().parent.parent / "data" / "wilayah"

_ALUR = [
    ("satellite_alt", "Citra Sentinel-2 Level-2A",
     "Citra Level-2A resolusi 10 m: saluran B02–B08, B11, B12, dan SCL untuk penanda awan."),
    ("cloud_off", "Pra-pemrosesan",
     "Awan dan bayangannya ditandai dari SCL (diperlebar 30 m), lalu nilainya diisi dengan interpolasi "
     "Hermite (PCHIP) dari tanggal lain yang cerah."),
    ("layers", "Klasifikasi",
     "Random Forest memetakan tiap piksel menjadi lahan terbangun atau nonterbangun."),
    ("timeline", "Prediksi",
     "ConvLSTM membaca urutan peta tahunan untuk memperkirakan lahan terbangun tahun berikutnya."),
    ("monitoring", "Pemantauan",
     "Dua tanggal dibandingkan untuk melihat di mana lahan terbangun bertambah atau berkurang."),
]

def _wilayah_kajian(wilayah: list[dict]) -> None:
    nama = {w["id"]: w["nama"] for w in wilayah}
    pilih = st.segmented_control("Wilayah", list(nama), format_func=nama.get, default=wilayah[0]["id"],
                                 key="beranda_wilayah", label_visibility="collapsed") or wilayah[0]["id"]
    kecamatan = regions.list_kecamatan(pilih)

    c_peta, c_info = st.columns([1.7, 1], gap="large")
    with c_peta.container(key="beranda_peta"):
        peta = _PETA_DIR / f"{pilih}.jpg"
        if peta.is_file():
            st.image(str(peta), width="stretch")
        else:
            layout.empty_state("Peta wilayah belum tersedia.", "map")
    with c_info:
        st.html(f'<div class="sp-lead">{escape(nama[pilih])}</div>')
        layout.metric_cards([("Jumlah kecamatan", str(len(kecamatan)))], min_width=140)
        layout.section("Kecamatan")
        st.html('<div class="sp-kec-list">'
                + "".join(f"<span>{escape(k['nama'])}</span>" for k in kecamatan) + "</div>")


layout.page_header("Beranda")
with layout.card("beranda"):
    try:
        wilayah = regions.list_wilayah()
        jumlah_kec = len(regions.list_kecamatan())
    except ServiceError as e:
        st.error(e.message, icon=":material/cloud_off:")
        st.stop()

    c_teks, c_angka = st.columns([1.6, 1], gap="large", vertical_alignment="center")
    c_teks.html(
        '<div class="sp-lead">SIPETA: Sistem Pemantauan Tutupan Lahan Terbangun</div>'
        '<p class="sp-body">SIPETA memantau perubahan lahan terbangun di Kota Tangerang, Kota Tangerang Selatan, '
        "dan Kabupaten Tangerang dari citra Sentinel-2. Piksel yang tertutup awan diisi lebih dulu dengan "
        "interpolasi PCHIP, kemudian citra diklasifikasikan dengan <em>Random Forest</em>. Urutan hasil "
        "klasifikasi dipakai <em>ConvLSTM</em> untuk memprediksi kondisi tahun berikutnya. Semua hasil "
        "disajikan per kecamatan.</p>"
    )
    with c_angka:
        layout.metric_cards([
            ("Wilayah", str(len(wilayah))),
            ("Kecamatan", str(jumlah_kec)),
            ("Rentang citra", f"{classify.TANGGAL_MIN.year}–{classify.TANGGAL_MAKS.year}"),
        ], min_width=120)

    st.divider()
    layout.section("Alur pengolahan")
    st.html('<ol class="sp-alur">' + "".join(
        f'<li><span class="sp-alur-ic material-symbols-rounded">{ikon}</span>'
        f"<b>{escape(judul)}</b><p>{escape(teks)}</p></li>"
        for ikon, judul, teks in _ALUR
    ) + "</ol>")

    st.divider()
    layout.section("Wilayah kajian")
    if wilayah:
        _wilayah_kajian(wilayah)
