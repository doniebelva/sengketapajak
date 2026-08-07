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

    pesan = ("Menyiapkan basis data UAT, sekali saja saat pertama dinyalakan..."
             if not sudah_ada else
             "Data baru terbit, mengunduh pembaruan basis data UAT...")
    with st.spinner(pesan):
        urllib.request.urlretrieve(url, "setpp_uat.db.gz")
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


siapkan_data()
with open(os.path.join(os.path.dirname(__file__), "dashboard.py"),
          encoding="utf-8") as fh:
    exec(compile(fh.read(), "dashboard.py", "exec"))
