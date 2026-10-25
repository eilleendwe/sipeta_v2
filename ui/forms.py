"""Widget form bersama. Semua widget diberi kunci dan `persist_state="session"`
supaya isian tidak hilang saat berpindah tab (tiap tab adalah halaman sendiri)."""

from html import escape

import streamlit as st

from services import models, regions
from services.errors import ServiceError
from ui import fmt

SEMUA_WILAYAH = "semua"
_PERSIST = {"persist_state": "session"}


def field_error(errors: dict, field: str, container=st) -> None:
    """Pesan galat kecil di bawah sebuah field, jika ada."""
    if errors.get(field):
        container.html(f'<div class="sp-field-error">{escape(errors[field])}</div>')


def select(container, label: str, options: list, key: str, *, format_func=str,
           placeholder: str = "Pilih…", disabled: bool = False, help: str | None = None,
           on_change=None, args=None):
    """Dropdown tanpa pilihan awal (seperti wireframe). Nilai tersimpan yang
    sudah tidak ada di `options` dibuang dulu supaya tidak memicu galat."""
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]
    return container.selectbox(
        label, options, index=None, key=key, format_func=format_func, placeholder=placeholder,
        disabled=disabled or not options, help=help, on_change=on_change, args=args, **_PERSIST,
    )


def region_select(c_wilayah, c_kecamatan, prefix: str, *, multi: bool = False,
                  semua_wilayah: bool = False, disabled: bool = False,
                  errors: dict | None = None):
    """Pasangan Kota/Kabupaten -> Kecamatan.

    Mengembalikan (wilayah_id, kecamatan). `kecamatan` berupa satu id (atau
    None), atau daftar id jika `multi`. Mengganti wilayah mengosongkan pilihan
    kecamatan.
    """
    k_wil, k_kec = f"{prefix}_wilayah", f"{prefix}_kecamatan"
    try:
        wilayah = regions.list_wilayah()
    except ServiceError as e:
        st.error(e.message, icon=":material/cloud_off:")
        st.stop()
    nama_wil = {w["id"]: w["nama"] for w in wilayah}
    opsi_wil = [w["id"] for w in wilayah]
    if semua_wilayah:
        opsi_wil = [SEMUA_WILAYAH, *opsi_wil]
        nama_wil[SEMUA_WILAYAH] = "Semua kota/kabupaten"

    def _kecamatan(wilayah_id):
        if not wilayah_id:
            return []
        return regions.list_kecamatan(None if wilayah_id == SEMUA_WILAYAH else wilayah_id)

    def _ganti_wilayah():
        # Kecamatan dikosongkan saat wilayah diganti; pengguna memilihnya sendiri.
        if multi:
            st.session_state[k_kec] = []
        else:
            st.session_state.pop(k_kec, None)

    wilayah_id = select(c_wilayah, "Kota/Kabupaten", opsi_wil, k_wil, format_func=nama_wil.get,
                        placeholder="Pilih kota/kabupaten", disabled=disabled, on_change=_ganti_wilayah)

    daftar = _kecamatan(wilayah_id)
    nama_kec = {k["id"]: k["nama"] for k in daftar}
    opsi_kec = list(nama_kec)
    if multi:
        if k_kec in st.session_state:
            st.session_state[k_kec] = [i for i in st.session_state[k_kec] if i in opsi_kec]
        kecamatan = c_kecamatan.multiselect(
            "Kecamatan", opsi_kec, key=k_kec, format_func=nama_kec.get,
            placeholder="Pilih kota/kabupaten dahulu" if not wilayah_id else "Pilih kecamatan",
            disabled=disabled or not opsi_kec, **_PERSIST,
        )
    else:
        kecamatan = select(c_kecamatan, "Kecamatan", opsi_kec, k_kec, format_func=nama_kec.get,
                           placeholder="Pilih kecamatan", disabled=disabled)
    if errors:
        field_error(errors, "kecamatan", c_kecamatan)
    return (None if wilayah_id == SEMUA_WILAYAH else wilayah_id), kecamatan


def model_select(container, prefix: str, algoritma: str, kecamatan_id: str | None,
                 luar_cakupan: bool = True) -> tuple[dict | None, list[str]]:
    """Dropdown model yang difilter menurut kecamatan terpilih. Jika `luar_cakupan`, ada centang
    untuk membuka model di luar cakupan. Mengembalikan (model, daftar peringatan);
    peringatan ditampilkan halaman di bawah baris form."""
    k_model, k_semua = f"{prefix}_model", f"{prefix}_semua_model"
    semua = luar_cakupan and st.session_state.get(k_semua, False)
    daftar = {m["id"]: m for m in models.list_models(algoritma, None if semua else kecamatan_id)}
    sebelumnya = st.session_state.get(k_model)
    terbuang = models.get(algoritma, sebelumnya) if sebelumnya and sebelumnya not in daftar else None

    model_id = select(
        container, "Model", list(daftar), k_model,
        format_func=lambda i: fmt.model_label(daftar[i], models.coverage_label(daftar[i])),
        placeholder="Pilih model" if daftar else "Belum ada model untuk kecamatan ini",
    )
    if luar_cakupan:
        container.checkbox("Tampilkan model di luar cakupan", key=k_semua, **_PERSIST,
                           help="Bawaan: hanya model yang dilatih untuk kecamatan terpilih.")

    model = daftar.get(model_id)
    peringatan = []
    if kecamatan_id:
        kecamatan = regions.nama_kecamatan(kecamatan_id)
        if terbuang:
            peringatan.append(
                f"Model “{terbuang['nama']}” tidak mencakup kecamatan {kecamatan}, jadi pilihan model dikosongkan."
            )
        if model and not models.covers(model, kecamatan_id):
            peringatan.append(
                f"Model “{model['nama']}” tidak dilatih untuk kecamatan {kecamatan}. "
                "Hasil di luar cakupan model bisa kurang akurat."
            )
    return model, peringatan


def row_error(errors: dict, field: str, kolom: int = 1, jumlah_kolom: int = 4) -> None:
    """Pesan galat di bawah satu baris field, mulai dari kolom ke-`kolom` supaya
    terbaca di bawah field yang dimaksud. Dipakai untuk baris yang fieldnya
    diratakan ke bawah: pesan di dalam kolom akan mendorong kotak isiannya naik."""
    if not errors.get(field):
        return
    if kolom <= 1:
        field_error(errors, field)
    else:
        _, wadah = st.columns([kolom - 1, jumlah_kolom - kolom + 1])
        field_error(errors, field, wadah)
