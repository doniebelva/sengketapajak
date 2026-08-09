"""
Titik masuk Streamlit Community Cloud.

Basis data tidak disimpan di repo karena ukurannya. Berkas setpp_uat.db.gz
diunduh dari aset GitHub Release lalu dibongkar menjadi setpp.db di folder
kerja. Alamat unduhan dibaca dari secrets SETPP_DATA_URL bila ada, atau dari
nilai bawaan di bawah.

Unduhan diulang ketika asetnya berganti, bukan hanya ketika berkasnya belum
ada. Peladen kadang memakai ulang wadah beserta isi cakramnya, dan tanpa
pemeriksaan ini basis data lama akan bertahan diam diam walaupun aset barunya
sudah terbit, sehingga dashboard menampilkan angka usang tanpa tanda apa pun.
Penanda yang dibandingkan adalah ukuran dan cap versi aset, dibaca lewat
permintaan kepala yang murah, bukan dengan mengunduh ulang isinya.
"""

import gzip
import os
import shutil
import urllib.request

import streamlit as st

BAWAAN = ("https://github.com/doniebelva/sengketapajak/releases/download/"
          "data-v1/setpp_uat.db.gz")
PENANDA = "setpp.penanda"


def alamat_data() -> str:
    url = ""
    try:
        url = st.secrets.get("SETPP_DATA_URL", "")
    except Exception:
        pass
    return url or os.environ.get("SETPP_DATA_URL", "") or BAWAAN


def penanda_aset(url: str) -> str:
    """Sidik ringan aset di peladen: ukuran dan cap versinya."""
    try:
        permintaan = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(permintaan, timeout=60) as jawab:
            k = jawab.headers
            return f"{k.get('Content-Length', '')}|{k.get('ETag', '')}"
    except Exception:
        return ""


def siapkan_data() -> None:
    # Pemeriksaan pembaruan tidak boleh berjalan pada setiap gerakan
    # pengguna. Skrip ini dijalankan ulang oleh Streamlit pada setiap klik,
    # dan permintaan kepala ke GitHub memakan sekitar satu detik, sehingga
    # setiap perpindahan menu tertahan selama itu sebelum halaman mulai
    # digambar. Aplikasi terasa lambat bukan karena datanya, melainkan
    # karena menunggu jaringan pada setiap klik. Kini pemeriksaan hanya
    # berjalan saat sesi dimulai dan paling cepat tiap lima belas menit
    # sesudahnya; data baru tetap terpasang, hanya saja paling lambat lima
    # belas menit setelah terbit.
    import time
    kini = time.time()
    if (os.path.exists("setpp.db")
            and kini - st.session_state.get("cek_data", 0.0) < 900):
        return
    st.session_state["cek_data"] = kini

    url = alamat_data()
    if not url:
        st.error("Alamat data belum diatur. Isi SETPP_DATA_URL pada "
                 "secrets aplikasi dengan alamat aset setpp_uat.db.gz.")
        st.stop()

    penanda_baru = penanda_aset(url)
    penanda_lama = ""
    if os.path.exists(PENANDA):
        try:
            with open(PENANDA, encoding="utf-8") as fh:
                penanda_lama = fh.read().strip()
        except OSError:
            penanda_lama = ""

    sudah_ada = os.path.exists("setpp.db")
    # Kalau penanda peladen tidak terbaca, misalnya jaringan sedang bermasalah,
    # basis data yang sudah ada tetap dipakai daripada aplikasinya mati.
    if sudah_ada and (not penanda_baru or penanda_baru == penanda_lama):
        return

    pesan = ("Menyiapkan basis data, hanya pada penyalaan pertama."
             if not sudah_ada else
             "Data baru terbit, mengunduh pembaruan basis data.")

    # Unduhan disajikan sebagai bilah kemajuan berpersentase, bukan putaran
    # bisu. Basis datanya tumbuh mengikuti arsip, dan makin besar berkasnya
    # makin lama pula jeda yang harus ditunggu pemakai pada penyalaan
    # pertama. Putaran tanpa keterangan membuat jeda itu terasa seperti
    # aplikasi macet, sedangkan persentase beserta ukuran berjalannya
    # memberi tahu bahwa semuanya bekerja dan kira kira berapa lama lagi.
    tempat = st.empty()
    tempat.markdown(f"**{pesan}**")
    batang = st.progress(0, text="Menghubungi peladen data...")
    try:
        with urllib.request.urlopen(url, timeout=300) as jawab, \
                open("setpp_uat.db.gz", "wb") as fkeluar:
            total = int(jawab.headers.get("Content-Length") or 0)
            terunduh = 0
            while True:
                potong = jawab.read(1 << 20)
                if not potong:
                    break
                fkeluar.write(potong)
                terunduh += len(potong)
                if total:
                    batang.progress(
                        min(terunduh / total, 1.0),
                        text=f"Mengunduh data {terunduh / 1e6:,.0f} dari "
                             f"{total / 1e6:,.0f} MB "
                             f"({100 * terunduh / total:.0f} persen)")
                else:
                    batang.progress(
                        0.5, text=f"Mengunduh data, "
                                  f"{terunduh / 1e6:,.0f} MB diterima...")

        batang.progress(1.0, text="Membongkar berkas data...")
        with gzip.open("setpp_uat.db.gz", "rb") as fmasuk, \
                open("setpp.db.baru", "wb") as fkeluar:
            shutil.copyfileobj(fmasuk, fkeluar)
        os.remove("setpp_uat.db.gz")
        # Berkas lama baru diganti setelah yang baru utuh, supaya unduhan
        # yang putus di tengah tidak meninggalkan basis data rusak.
        os.replace("setpp.db.baru", "setpp.db")
        if penanda_baru:
            with open(PENANDA, "w", encoding="utf-8") as fh:
                fh.write(penanda_baru)
    finally:
        batang.empty()
        tempat.empty()


siapkan_data()
with open(os.path.join(os.path.dirname(__file__), "dashboard.py"),
          encoding="utf-8") as fh:
    exec(compile(fh.read(), "dashboard.py", "exec"))
