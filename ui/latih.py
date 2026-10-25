"""Bagian yang sama di kedua tab Latih Model (Random Forest dan ConvLSTM):
alur latih dengan progres, dan Simpan/Buang."""

import streamlit as st

from services import models
from services.errors import ServiceError
from ui import fmt, layout


def _k(prefix: str, nama: str) -> str:
    return f"{prefix}_{nama}"


def status(prefix: str) -> tuple[bool, dict]:
    """(sedang berjalan, galat validasi terakhir). Job yang belum selesai dipantau juga dihitung berjalan."""
    berjalan = st.session_state.get(_k(prefix, "berjalan"), False) or _k(prefix, "job") in st.session_state
    return berjalan, st.session_state.get(_k(prefix, "galat"), {})


def draft(prefix: str) -> dict | None:
    """Calon model hasil pelatihan terakhir yang belum disimpan atau dibuang."""
    return st.session_state.get(_k(prefix, "draft"))


def start_button(prefix: str, disabled: bool) -> None:
    def _mulai():
        st.session_state[_k(prefix, "berjalan")] = True
        st.session_state.pop(_k(prefix, "galat"), None)

    st.button("Latih model", type="primary", icon=":material/model_training:", key=_k(prefix, "latih"),
              disabled=disabled, on_click=_mulai)


def run_if_started(prefix: str, algoritma: str, spec: dict) -> None:
    """Menjalankan pelatihan jika tombol baru ditekan, atau melanjutkan pemantauan job yang
    belum selesai (mis. setelah pindah halaman; job di server tetap berjalan). Selama berjalan,
    form dan tombol nonaktif; hasil disimpan di session_state supaya tidak hilang karena rerun."""
    k_jalan, k_job = _k(prefix, "berjalan"), _k(prefix, "job")
    job = st.session_state.get(k_job)  # (job_id, spec) pelatihan yang sudah dikirim ke server
    if not st.session_state.get(k_jalan) and job is None:
        return
    st.session_state[k_jalan] = False

    if job is None:
        try:
            galat = models.validate(algoritma, spec)
        except ServiceError as e:
            galat = {"umum": e.message}
        if galat:
            st.session_state[_k(prefix, "galat")] = galat
            st.rerun()
        kejadian_list = models.train(algoritma, spec)
    else:
        job_id, spec = job
        kejadian_list = models.resume(algoritma, spec, job_id)

    bar = st.progress(0.0, text="Menyiapkan…")
    try:
        hasil = None
        for kejadian in kejadian_list:
            if "job_id" in kejadian:
                st.session_state[k_job] = (kejadian["job_id"], spec)
            bar.progress(kejadian["progress"], text=kejadian["label"])
            hasil = kejadian["result"]
    except ServiceError as e:
        st.session_state.pop(k_job, None)
        st.session_state[_k(prefix, "galat")] = e.fields or {"umum": e.message}
        st.rerun()
    st.session_state.pop(k_job, None)
    st.session_state[_k(prefix, "draft")] = hasil
    st.rerun()


def general_error(errors: dict) -> None:
    if errors.get("umum"):
        st.error(errors["umum"], icon=":material/error:")
    elif errors:
        st.error("Periksa kembali isian yang ditandai.", icon=":material/error:")


def labeled(nama: str, algoritma: str, param: str) -> str:
    """Label field hyperparameter dengan keterangan berhuruf kecil di bawahnya:
    penjelasan singkat dan nilai yang direkomendasikan."""
    penjelasan, nilai = models.REKOMENDASI[algoritma][param]
    return f"{nama}  \n:small[:gray[{penjelasan} (Direkomendasikan: {nilai})]]"


def evaluation_caption(calon: dict, satuan: str) -> None:
    """Keterangan di atas panel evaluasi: model, cakupan, ukuran data uji, status simpan."""
    status = "Sudah tersimpan." if calon.get("tersimpan") else "Belum tersimpan."
    st.caption(
        f"Hasil untuk model “{calon['nama']}” · {models.coverage_label(calon)} · "
        f"{fmt.angka(calon['evaluasi']['n_uji'], 0)} {satuan}. {status}"
    )


def save_discard(prefix: str, calon: dict) -> None:
    """Tombol Simpan model dan Buang. Setelah disimpan, evaluasi tetap tampil
    (ditandai tersimpan) sampai model lain dilatih."""
    k_draft = _k(prefix, "draft")
    if calon.get("tersimpan"):
        st.button("Tersimpan", type="primary", icon=":material/check:", key=_k(prefix, "simpan"), disabled=True)
        return
    with st.container(horizontal=True):
        if st.button("Simpan model", type="primary", icon=":material/save:", key=_k(prefix, "simpan")):
            try:
                model = models.save(calon)
            except ServiceError as e:
                st.error(e.message, icon=":material/error:")
            else:
                st.session_state[k_draft] = {**calon, "tersimpan": True}
                layout.set_flash(f"Model “{model['nama']}” disimpan.", ":material/check_circle:")
                st.rerun()
        if st.button("Buang", icon=":material/delete:", key=_k(prefix, "buang")):
            models.discard(calon)
            st.session_state.pop(k_draft, None)
            layout.set_flash("Hasil pelatihan dibuang.")
            st.rerun()
