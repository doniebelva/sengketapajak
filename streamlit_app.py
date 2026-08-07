"""
Titik masuk Streamlit Community Cloud.

Basis data tidak disimpan di repo karena ukurannya. Saat aplikasi pertama
dinyalakan, berkas setpp_uat.db.gz diunduh dari aset GitHub Release lalu
dibongkar menjadi setpp.db di folder kerja. Alamat unduhan dibaca dari
secrets SETPP_DATA_URL bila ada, atau dari nilai bawaan di bawah.
"""

import gzip
import os
import shutil
import urllib.request

import streamlit as st

BAWAAN = ("https://github.com/doniebelva/sengketapajak/releases/download/"
          "data-v1/setpp_uat.db.gz")


def siapkan_data() -> None:
    if os.path.exists("setpp.db"):
        return
    url = ""
    try:
        url = st.secrets.get("SETPP_DATA_URL", "")
    except Exception:
        pass
    url = url or os.environ.get("SETPP_DATA_URL", "") or BAWAAN
    if not url:
        st.error("Alamat data belum diatur. Isi SETPP_DATA_URL pada "
                 "secrets aplikasi dengan alamat aset setpp_uat.db.gz.")
        st.stop()
    with st.spinner("Menyiapkan basis data UAT, sekali saja saat "
                    "pertama dinyalakan..."):
        urllib.request.urlretrieve(url, "setpp_uat.db.gz")
        with gzip.open("setpp_uat.db.gz", "rb") as fmasuk, \
                open("setpp.db", "wb") as fkeluar:
            shutil.copyfileobj(fmasuk, fkeluar)
        os.remove("setpp_uat.db.gz")


siapkan_data()
with open(os.path.join(os.path.dirname(__file__), "dashboard.py"),
          encoding="utf-8") as fh:
    exec(compile(fh.read(), "dashboard.py", "exec"))
