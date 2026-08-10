#!/usr/bin/env python3
"""
dashboard.py

Dashboard Analitik Sengketa Pajak.
Analitik risalah putusan Pengadilan Pajak.

Dibangun dari rancangan_dashboard_insight.md. Delapan halaman disusun menurut
perjalanan pembaca dengan prioritas wajib pajak, lalu pimpinan, lalu fiskus.
Dimensi analitik deskriptif, diagnostik, prediktif, dan preskriptif menjadi
sifat tiap halaman, bukan nama menunya. Prediktif berarti frekuensi historis
atas perkara serupa, bukan penebakan amar untuk perkara tertentu.

Basis data dibuka baca saja, sehingga dashboard dapat dijalankan kapan saja
tanpa mengganggu penarikan maupun ekstraksi yang sedang berlangsung.

Menjalankan:
    pip install streamlit plotly pandas
    cd "C:\\CLAUDE-WORKSPACE\\Sengketa Pajak\\Output\\data"
    streamlit run "..\\scripts\\dashboard.py"
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
import sys

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tema_viz as TV

DB_PATH = os.environ.get("SETPP_DB", "setpp.db")

# Batas atas pengenal saat penarikan, dasar seluruh hitungan cakupan.
ID_MAKS = int(os.environ.get("SETPP_ID_MAKS", "150000"))

LABEL_AMAR = {
    "kabul_seluruhnya": "Dikabulkan seluruhnya",
    "kabul_sebagian": "Dikabulkan sebagian",
    "tolak": "Ditolak",
    "tidak_dapat_diterima": "Tidak dapat diterima",
    "batal": "Dibatalkan",
    "cabut": "Dicabut",
    "gugur": "Gugur",
    "pembetulan": "Pembetulan kesalahan tulis",
}
LABEL_INSTANSI = {"djp": "Direktorat Jenderal Pajak",
                  "djbc": "Direktorat Jenderal Bea dan Cukai",
                  "pemda": "Pemerintah daerah"}
LABEL_PERKARA = {"banding": "Banding", "gugatan": "Gugatan",
                 "pk": "Peninjauan kembali"}
LABEL_KOREKSI = {
    "peredaran_usaha": "Peredaran usaha", "hpp": "Harga pokok penjualan",
    "biaya": "Biaya", "pajak_masukan": "Pajak masukan", "dpp_ppn": "DPP PPN",
    "penyusutan": "Penyusutan dan amortisasi",
    "hubungan_istimewa": "Hubungan istimewa", "kredit_pajak": "Kredit pajak",
    "kompensasi_rugi": "Kompensasi kerugian",
    "pph_potput": "PPh potong pungut", "nilai_pabean": "Nilai pabean",
    "klasifikasi_tarif": "Klasifikasi dan tarif",
    "fasilitas": "Fasilitas dan pembebasan", "sanksi": "Sanksi administrasi",
    "formal": "Aspek formal",
}
AMAR_MENANG = ("kabul_seluruhnya", "kabul_sebagian")

# Alamat berkas asli pada peladen Sekretariat. Dipakai sebagai tujuan tombol
# unduh ketika arsip lokal tidak terjangkau, misalnya pada peladen UAT, agar
# pembaca tetap bisa mengambil dokumen resminya dari sumber aslinya.
URL_BERKAS_ASLI = "https://setpp.kemenkeu.go.id/risalah/ambilFileDariDisk/{id}"


# ---------------------------------------------------------------------------
# Lapis data
# ---------------------------------------------------------------------------

def sambung() -> sqlite3.Connection:
    uri = "file:" + os.path.abspath(DB_PATH).replace("\\", "/") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=30, check_same_thread=False)


def usia_db() -> float:
    """
    Cap waktu berkas basis data, dipakai sebagai kunci singgahan.

    Singgahan pemuat data pernah diberi masa hidup dua menit, dan itu
    keliru arah: berkas datanya statis sepanjang hidup wadah, hanya
    berganti ketika paket rilis baru terpasang. Akibat masa hidup pendek,
    tiap dua menit ada satu klik yang membayar muat ulang penuh sekitar
    satu detik, dan aplikasi terasa tersendat berkala tanpa sebab yang
    terlihat. Dengan cap waktu berkas sebagai kunci, singgahan hidup
    selamanya dan baru dibuang tepat ketika berkasnya benar benar berganti.
    """
    try:
        return os.path.getmtime(DB_PATH)
    except OSError:
        return 0.0


def kolom_nomor_tampil(r: pd.DataFrame) -> pd.Series:
    """
    Nomor putusan untuk ditampilkan, dirangkai kembali bila perlu.

    Nomor yang ditampilkan selama ini diambil hanya dari nomor mentah, yaitu
    nomor yang terbaca utuh di dalam teks dokumennya sendiri. Ketika
    pembacaan itu gagal, kolomnya tertulis tidak dikenali, padahal pada
    sebagian besar dokumen tersebut nomornya sebenarnya diketahui: peladen
    Sekretariat menyertakan nomor sengketa, kode jenis pajak, dan tahun pada
    nama berkasnya, dan ketiganya sudah tersimpan sebagai ruas tersendiri.
    Yang hilang hanya perangkaiannya menjadi satu tulisan.

    Dari 820 putusan yang nomor mentahnya kosong, 770 di antaranya nomor
    sengketanya diketahui. Menuliskan tidak dikenali pada seluruhnya
    membuang keterangan yang sudah ada di tangan.

    Bagian yang tidak diketahui memang tidak dikarang. Nomor hasil
    perangkaian dapat lebih pendek daripada nomor penuh, misalnya tanpa kode
    majelis, dan itu memang sebagaimana adanya.

    Dikerjakan per kolom, bukan per baris. Perangkaian baris demi baris atas
    enam belas ribu putusan memakan waktu beberapa detik pada tiap penyegaran
    singgahan, dan itu cukup untuk membuat uji halaman kehabisan waktu ketika
    mesin sedang sibuk mengerjakan pengenalan karakter optis.
    """
    ns = r["nomor_sengketa"].fillna("").astype(str)
    kj = r["kode_jenis_pajak"].fillna("").astype(str)
    km = r["kode_majelis"].fillna("").astype(str)

    s = "PUT-" + ns
    s = s.where(kj == "", s + "." + kj)
    s = s + r["tahun_sengketa_masuk"].map(
        lambda v: f"/{int(v)}/PP" if pd.notna(v) else "")
    s = s.where(km == "", s + "/" + km)
    s = s + r["tahun_putusan"].map(
        lambda v: f" Tahun {int(v)}" if pd.notna(v) else "")

    # Tanpa nomor sengketa tidak ada yang dapat dirangkai sama sekali, dan
    # pengenal dokumen dipakai supaya barisnya tetap dapat dirujuk.
    s = s.mask(ns == "", "Dokumen " + r["doc_id"].astype(str))

    raw = r["nomor_putusan_raw"]
    utuh = raw.notna() & (raw.fillna("").astype(str).str.strip() != "")
    return raw.where(utuh, s)


# Singgahan pemuatan tabel utama. Dekorator ini pernah tergeser ke fungsi
# perangkaian nomor ketika fungsi itu disisipkan di antara dekorator dan
# fungsi aslinya, sehingga tabel utama dibaca ulang dari basis data pada
# setiap gerakan pengguna dan seluruh dashboard terasa berat. Pesan
# pemuatannya ditulis sendiri, karena pesan bawaan menampilkan nama fungsi
# dalam bahasa Inggris yang tidak berarti bagi pemakai.
@st.cache_resource(show_spinner="Memuat data putusan...")
def _muat_putusan(usia: float) -> pd.DataFrame:
    with sambung() as c:
        df = pd.read_sql_query("SELECT * FROM putusan", c)
    for k, peta in (("amar", LABEL_AMAR),
                    ("instansi_terbanding", LABEL_INSTANSI),
                    ("jenis_perkara", LABEL_PERKARA)):
        if k in df:
            df[k + "_label"] = df[k].map(peta).fillna("Tidak dikenali")
    # Pagar kewajaran tahun. Pengadilan Pajak berdiri tahun 2002, sehingga
    # tahun putusan di luar 2002 sampai tahun berjalan pasti salah baca,
    # hampir selalu dari dokumen pindai yang angkanya terbaca meleset. Satu
    # putusan bertahun 2055 pernah lolos dan sendirian merentangkan sumbu
    # seluruh bagan tahunan sampai tiga dasawarsa ke depan, sekaligus
    # melebarkan penggeser tahun di bilah samping. Nilai mustahil dibuang
    # menjadi kosong, bukan dibetulkan, karena tebakannya tidak dapat
    # dipertanggungjawabkan.
    import datetime as _dt
    kini = _dt.date.today().year
    for k in ("tahun_putusan", "tahun_sengketa_masuk"):
        if k in df:
            salah = df[k].notna() & ~df[k].between(2002, kini)
            df.loc[salah, k] = float("nan")
    for k in ("tanggal_ucap", "tanggal_musyawarah"):
        if k in df:
            th = pd.to_numeric(df[k].str[:4], errors="coerce")
            salah = th.notna() & ~th.between(2002, kini)
            df.loc[salah, k] = None

    df["nomor_tampil"] = kolom_nomor_tampil(df)
    # Ruas nama yang tampil di layar dirapikan kapitalnya di satu tempat,
    # supaya seluruh halaman menerima bentuk yang sama. Nomor putusan tidak
    # disentuh karena nomor memang berkapital penuh.
    for k in ("nama_pemohon", "unit_penerbit", "nama_terbanding",
              "jenis_pajak_teks"):
        if k in df:
            df[k] = df[k].map(rapikan_kapital)
    return df


@st.cache_data(show_spinner="Menghitung cakupan arsip...")
def _muat_corong(usia: float) -> dict:
    def satu(c, sql):
        try:
            v = c.execute(sql).fetchone()[0]
            return int(v or 0)
        except sqlite3.OperationalError:
            return 0

    with sambung() as c:
        return {
            "unduh": satu(c, "SELECT COUNT(*) FROM docs WHERE status='ok'"),
            "gb": satu(c, "SELECT COALESCE(SUM(n_bytes),0) FROM docs") / 1e9,
            "teks": satu(c, "SELECT COUNT(*) FROM texts"),
            "urai": satu(c, "SELECT COUNT(*) FROM putusan"),
        }


@st.cache_resource(show_spinner="Memuat daftar resmi Sekretariat...")
def _muat_resmi(usia: float) -> pd.DataFrame:
    """Daftar resmi putusan 2021 sampai 2025, dimuat setpp_resmi.py impor.
    Kosong bila tabelnya belum ada, dan halaman pemakainya wajib bersikap
    baik pada keadaan itu."""
    try:
        with sambung() as c:
            return pd.read_sql_query(
                "SELECT kunci, tahun_ucap, terbanding, jenis_pajak, amar, "
                "amar_resmi, nama_pemohon, tanggal_ucap, nilai_awal, "
                "nilai_akhir, mata_uang FROM resmi", c)
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner="Memuat peta kode jenis pajak...")
def _peta_kode(usia: float) -> dict:
    """
    Nama jenis pajak dibangun dari data itu sendiri, dengan menyilangkan kode
    dua digit pada nomor putusan terhadap ruas jenis pajak di dalam dokumen.
    Tabel kode resmi belum diperoleh, dan menuntut pembaca menghafal kode dua
    digit bukan pilihan.
    """
    import re as _re

    with sambung() as c:
        t = pd.read_sql_query(
            """SELECT kode_jenis_pajak AS kode, jenis_pajak_teks AS label,
                      COUNT(*) AS n FROM putusan
               WHERE kode_jenis_pajak IS NOT NULL
                 AND jenis_pajak_teks IS NOT NULL AND jenis_pajak_teks != ''
               GROUP BY 1, 2""", c)

    def baku(label: str) -> str:
        """
        Bakukan penulisan sebelum menghitung kesepakatan. Tanpa ini, PPh
        Pasal 21 dan Pajak Penghasilan Pasal 21 terhitung sebagai dua label
        yang berbeda, sehingga kesepakatan tampak rendah dan tanda tanya
        muncul di hampir semua kode padahal maknanya sama.
        """
        b = " ".join(str(label).split()).upper()
        # Garis tegak dan titik koma adalah sisa penanda tabel dari keluaran
        # antiword pada risalah era Word, bukan bagian dari nama pajak.
        b = _re.sub(r"[.,()|;:]", " ", b)
        b = _re.sub(r"\bPPH\b", "PAJAK PENGHASILAN", b)
        b = _re.sub(r"\bPPN\b(?:\s+BM)?", "PAJAK PERTAMBAHAN NILAI", b)
        b = _re.sub(r"\bPBB\b", "PAJAK BUMI DAN BANGUNAN", b)
        b = _re.sub(r"\bBARANG DAN JASA\b", "", b)
        b = _re.sub(r"\bFINAL\b|\bPASAL\b|\bATAS\b", "", b)
        return " ".join(b.split())

    peta = {}
    for kode, g in t.groupby("kode"):
        kel: dict = {}
        for _, r in g.iterrows():
            k = baku(r["label"])
            if k not in kel:
                kel[k] = {"n": 0, "asli": str(r["label"])}
            kel[k]["n"] += int(r["n"])
        total = sum(v["n"] for v in kel.values())
        juara = max(kel.values(), key=lambda v: v["n"])
        peta[str(kode)] = {
            "label": " ".join(juara["asli"].split())[:42],
            "n": total, "pangsa": 100 * juara["n"] / total}
    return peta


# Singkatan resmi yang penulisannya baku dan tidak boleh diubah oleh
# perapi kapital di bawah. PPh dan PPnBM punya huruf kecil di tengah, dan
# menuliskannya sebagai Pph atau Ppnbm langsung terbaca salah oleh siapa pun
# yang bekerja di bidang pajak.
SINGKATAN_BAKU = {
    "PPH": "PPh", "PPN": "PPN", "PPNBM": "PPnBM", "PBB": "PBB",
    "BPHTB": "BPHTB", "PTLL": "PTLL", "DJP": "DJP", "DJBC": "DJBC",
    "KPP": "KPP", "KPU": "KPU", "PIB": "PIB", "SPT": "SPT",
    "STP": "STP", "SKP": "SKP", "SKPKB": "SKPKB", "SKPLB": "SKPLB",
    "SKPN": "SKPN", "SKPKBT": "SKPKBT", "SPTNP": "SPTNP", "SPKTNP": "SPKTNP",
    "CIF": "CIF", "FOB": "FOB", "USD": "USD", "NJOP": "NJOP",
    "PT": "PT", "CV": "CV", "PD": "PD", "UD": "UD", "TBK": "Tbk",
    "PMA": "PMA", "PMDN": "PMDN", "KSO": "KSO", "WP": "WP",
    "DPP": "DPP", "HPP": "HPP", "BM": "BM",
}


def rapikan_kapital(s):
    """
    Tulisan SERBA KAPITAL dari dokumen dirapikan menjadi huruf awal besar.

    Data hasil penguraian mewarisi gaya penulisan dokumen sumbernya, dan
    sebagian dokumen menulis nama jenis pajak, unit, maupun pemohon dengan
    kapital semua. Pada tampilan, PAJAK PERTAMBAHAN NILAI berdampingan
    dengan Bea Masuk sehingga terlihat seperti dua kelas data yang berbeda,
    padahal isinya setara. Yang diubah hanya kata yang seluruhnya kapital;
    kata yang sudah rapi dibiarkan, dan singkatan baku dikembalikan ke
    penulisan resminya. Nomor putusan tidak pernah melewati fungsi ini,
    karena nomor memang ditulis kapital seluruhnya.
    """
    if not isinstance(s, str) or not s:
        return s
    hubung = {"DAN": "dan", "ATAS": "atas", "DARI": "dari", "KE": "ke",
              "DI": "di", "YANG": "yang", "UNTUK": "untuk", "PADA": "pada",
              "DALAM": "dalam", "SERTA": "serta", "ATAU": "atau"}
    hasil = []
    for kata in s.split():
        inti = kata.strip(".,;:()")
        if inti.isupper() and len(inti) > 1:
            ganti = (SINGKATAN_BAKU.get(inti) or hubung.get(inti)
                     or inti.capitalize())
            hasil.append(kata.replace(inti, ganti, 1))
        else:
            hasil.append(kata)
    return " ".join(hasil)


def label_kode(kode, peta: dict) -> str:
    if kode is None or (isinstance(kode, float) and math.isnan(kode)):
        return "tidak dikenali"
    info = peta.get(str(kode))
    if not info:
        return f"{kode} · belum teridentifikasi"
    return (f"{kode} · {rapikan_kapital(info['label'])}"
            + (" (?)" if info["pangsa"] < 80 else ""))




def muat_putusan() -> pd.DataFrame:
    return _muat_putusan(usia_db())


def muat_corong() -> dict:
    return _muat_corong(usia_db())


def muat_resmi() -> pd.DataFrame:
    return _muat_resmi(usia_db())


def peta_kode() -> dict:
    return _peta_kode(usia_db())


def muat_dasar_hukum() -> pd.DataFrame:
    return _muat_dasar_hukum(usia_db())


@st.cache_data(ttl=30, show_spinner=False)
def keadaan_tarikan() -> dict:
    import datetime as _dt

    with sambung() as c:
        try:
            terakhir = c.execute(
                "SELECT MAX(fetched_at) FROM docs").fetchone()[0]
        except sqlite3.OperationalError:
            terakhir = None
    if not terakhir:
        return {"aktif": False, "menit": None, "terakhir": None}
    try:
        t = _dt.datetime.fromisoformat(terakhir)
        menit = (_dt.datetime.now(_dt.timezone.utc) - t).total_seconds() / 60
    except ValueError:
        return {"aktif": False, "menit": None, "terakhir": None}
    # Cap waktu disajikan dalam WIB, karena pemakainya di Indonesia dan
    # cap mentahnya tercatat dalam UTC.
    wib = t + _dt.timedelta(hours=7) if t.tzinfo is None else         t.astimezone(_dt.timezone(_dt.timedelta(hours=7)))
    return {"aktif": menit < 5, "menit": menit,
            "terakhir": t.strftime("%d-%m-%Y"),
            "cap": wib.strftime("%d-%m-%Y %H.%M")}


def rentang_tahun(df_: pd.DataFrame) -> str:
    """Rentang tahun putusan pada lingkup yang sedang tampil."""
    th = df_["tahun_putusan"].dropna()
    if th.empty:
        return "-"
    a, b = int(th.min()), int(th.max())
    return f"{a}" if a == b else f"{a} sampai {b}"


@st.cache_resource(show_spinner="Memuat rujukan dasar hukum...")
def _muat_dasar_hukum(usia: float) -> pd.DataFrame:
    """
    Rujukan dasar hukum dalam bentuk sehemat mungkin.

    Tabel ini 871 ribu baris, dan memuatnya utuh tujuh kolom pernah
    menghabiskan ratusan megabita sampai aplikasi di peladen jatuh
    kehabisan memori. Kedua halaman pemakainya hanya membutuhkan dua hal:
    pengenal dokumen dan tulisan rujukannya. Rujukan dirangkai di SQL, dan
    karena isinya sangat berulang, disimpan sebagai kategori: dari ratusan
    megabita menjadi belasan.
    """
    with sambung() as c:
        df_ = pd.read_sql_query(
            "SELECT doc_id, 'Pasal ' || pasal || ' ' || "
            "COALESCE(uu_nama, 'UU ' || uu_nomor) AS rujukan "
            "FROM dasar_hukum "
            "WHERE uu_nomor IS NOT NULL AND pasal IS NOT NULL", c)
    df_["doc_id"] = df_["doc_id"].astype("int32")
    df_["rujukan"] = df_["rujukan"].astype("category")
    return df_


def cari_teks(kueri: str, batas: int) -> pd.DataFrame:
    with sambung() as c:
        return pd.read_sql_query(
            """SELECT f.doc_id,
                      snippet(putusan_fts, 2, '**', '**', ' … ', 24) AS cuplikan
               FROM putusan_fts f WHERE putusan_fts MATCH ?
               ORDER BY rank LIMIT ?""", c, params=(kueri, batas))


# Isi putusan bisa sebesar beberapa megabita per dokumen; singgahannya
# dibatasi ketat supaya pembacaan beruntun tidak menumpuk di memori.
@st.cache_data(ttl=120, max_entries=6,
               show_spinner="Membuka isi putusan...")
def muat_isi(doc_id: int) -> tuple[str, str]:
    with sambung() as c:
        b = c.execute(
            """SELECT t.text_path, d.path FROM texts t
               JOIN docs d ON d.doc_id = t.doc_id WHERE t.doc_id = ?""",
            (doc_id,)).fetchone()
    if not b:
        return "", ""
    try:
        with open(b[0], encoding="utf-8") as fh:
            return fh.read(), (b[1] or "")
    except (OSError, TypeError):
        pass
    # Cadangan untuk paket rilis: pada peladen UAT tidak ada folder teks,
    # tetapi isi penuh setiap dokumen sudah ada di indeks pencarian.
    try:
        with sambung() as c:
            r = c.execute("SELECT teks FROM putusan_fts WHERE doc_id = ?",
                          (int(doc_id),)).fetchone()
        if r and r[0]:
            return r[0], (b[1] or "")
    except (sqlite3.OperationalError, TypeError, ValueError):
        pass
    return "", (b[1] or "")


# ---------------------------------------------------------------------------
# Alat bantu
# ---------------------------------------------------------------------------

def tampil(v, kosong: str = "-") -> str:
    if v is None:
        return kosong
    if isinstance(v, float) and math.isnan(v):
        return kosong
    s = str(v).strip()
    return s if s and s.lower() != "nan" else kosong


def tampil_tahun(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    try:
        return str(int(v))
    except (TypeError, ValueError):
        return "-"


def tampil_tanggal(v, alt: str = "-") -> str:
    """Tanggal ucap tersimpan sebagai YYYY-MM-DD, ditampilkan DD-MM-YYYY.
    Bila tanggalnya tidak terbaca, tampilkan cadangan, biasanya tahunnya,
    supaya risalah era lama yang tak bertanggal tetap terjangkarkan waktu."""
    s = tampil(v, "")
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}-{s[5:7]}-{s[0:4]}"
    return alt


# ---------------------------------------------------------------------------
# Pembakuan nama hakim
#
# Nama yang sama tertulis berbeda-beda antar risalah: gelarnya berubah ubah,
# tanda bacanya tidak konsisten, dan pengenalan karakter optis sesekali salah
# satu huruf. Tanpa pembakuan, satu hakim terhitung sebagai empat baris.
# ---------------------------------------------------------------------------

GELAR_HAKIM = {
    "se", "sh", "st", "si", "sos", "sst", "sip", "spi", "ssi", "sag",
    "ak", "akt", "ca", "cma", "cpa", "cfra", "cfe", "bkp", "cn",
    "mm", "msi", "mh", "mhum", "mec", "ec", "mba", "mpa", "msc", "mt",
    "ma", "map", "mkn", "mak", "mafis", "llm", "dess", "mip", "dev",
    "drs", "dra", "ir", "dr", "prof", "hj", "raden", "bsc", "int", "tax"}

RE_BUKAN_HURUF = re.compile(r"[^a-z]+")

# Kata sambung dan sebutan jabatan yang ikut terbawa ketika susunan majelis
# dibaca dari kalimat, misalnya "Usman Pasaribu sebagai Hakim Ketua" atau
# "Uming dan Sulaiman masing-masing sebagai Hakim Anggota".
KATA_IKUT = {
    "sebagai", "selaku", "masing", "dan", "serta", "yang", "adalah",
    "dengan", "para", "sdr", "bapak", "ibu", "hakim", "ketua", "anggota",
    "majelis", "panitera", "pengganti", "sidang", "pengadilan", "pajak"}

# Gelar pendek yang kerap salah terbaca, misalnya M.Si menjadi M.Sin atau
# M.Sj. Kesalahan seperti itu tidak ada di dalam daftar gelar, sehingga
# dikenali lewat kemiripan satu huruf terhadap gelar yang sah.
GELAR_PENDEK = tuple(g for g in
                     ("se", "sh", "st", "si", "ak", "ca", "mm", "msi", "mh",
                      "ma", "mt", "mba", "msc", "ir", "dr", "sos", "mkn")
                     )


def _gelar(kata: str) -> bool:
    if kata in GELAR_HAKIM:
        return True
    if len(kata) > 4:
        return False
    return any(_selisih_satu(kata, g) for g in GELAR_PENDEK)


# Nama samaran dan sisa penanda dokumen. Risalah era lama menyamarkan nama
# dengan huruf berulang seperti XXX dan AAA, dan pemindaian sesekali
# meninggalkan penanda seperti tanda kutip di tengah nama. Tak satu pun
# merupakan nama orang, sehingga barisnya dikeluarkan seluruhnya.
RE_NAMA_PALSU = re.compile(
    r"\b(?:([a-z])\1{2,}|abcd?|xyz|pqr|def)\b"
    r"|\bdst\b|\bdll\b|\bnama\b|\btidak\s+terbaca\b", re.IGNORECASE)


def _nama_sah(nama: str) -> bool:
    """Salah bila tangkapan jelas bukan nama orang."""
    s = str(nama)
    if RE_NAMA_PALSU.search(s):
        return False
    # Tanda kutip, tanda kurung, dan angka tidak pernah muncul di dalam nama
    # orang, dan kehadirannya menandakan tangkapan yang rusak.
    if re.search(r"[\"'()\[\]{}<>@#$%^*_=+/\\|~`0-9]", s):
        return False
    huruf = sum(c.isalpha() for c in s)
    return huruf >= 4


def kunci_hakim(nama: str) -> str:
    """Bentuk baku untuk pencocokan.

    Yang dibuang: tanda baca, gelar termasuk gelar yang salah terbaca, kata
    sambung dan sebutan jabatan, serta pengulangan kata yang berdampingan
    seperti "Ruwaidah Ruwaidah Afiyati". Nama yang tidak menyisakan apa pun
    menjadi kunci kosong dan dikeluarkan pemanggilnya.
    """
    # Huruf yang kerap salah terbaca mesin pemindai dipulihkan lebih dulu,
    # supaya Ra§ono dan Rasono tidak terhitung sebagai dua hakim.
    bersih = (str(nama).lower().replace("§", "s").replace("ß", "s")
              .replace("¢", "c").replace("|", "l").replace("0", "o"))
    kata = RE_BUKAN_HURUF.sub(" ", bersih).split()
    inti = [k for k in kata
            if len(k) > 1 and k not in KATA_IKUT and not _gelar(k)]
    hasil: list[str] = []
    for k in inti:
        if not hasil or hasil[-1] != k:
            hasil.append(k)
    return " ".join(hasil)


def nama_tanpa_gelar(nama: str) -> str:
    """Nama tampilan yang bersih dari gelar, dengan inisial nama tetap.

    Tiap penggal dinilai dari kandungan hurufnya: penggal yang memuat kata
    utuh bukan gelar dipertahankan, penggal yang seluruhnya gelar dibuang.
    Penggal inisial seperti J.B. hanya dipertahankan selama belum melewati
    koma, karena sebelum koma dia bagian nama, sesudah koma dia gelar."""
    token = str(nama).split()
    huruf = [RE_BUKAN_HURUF.sub(" ", t.lower()).split() for t in token]
    inti = [any(len(s) > 1 and s not in KATA_IKUT and not _gelar(s)
                for s in h)
            for h in huruf]
    hasil = []
    lewat_koma = False
    for i, t in enumerate(token):
        if inti[i]:
            bersih = t.strip(",")
            if huruf[i] and len(huruf[i][-1]) > 1:
                bersih = bersih.rstrip(".,")
            hasil.append(bersih)
        elif (not lewat_koma and huruf[i]
              and all(len(s) == 1 for s in huruf[i]) and any(inti[i + 1:])):
            hasil.append(t.strip(","))
        if "," in t:
            lewat_koma = True
    return " ".join(hasil).strip(" ,")


def _selisih_satu(a: str, b: str) -> bool:
    """Benar bila kedua untai berbeda paling banyak satu huruf, baik ganti,
    sisip, maupun hapus. Cukup untuk menangkap salah baca optis tunggal."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(x != y for x, y in zip(a, b)) == 1
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = beda = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        else:
            beda += 1
            if beda > 1:
                return False
            j += 1
    return True


def bakukan_hakim(seri: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Kembalikan kunci baku sejajar masukan, dan peta kunci ke nama tampilan.

    Varian yang kuncinya persis sama langsung menyatu. Varian yang kuncinya
    berselisih satu huruf, pada nama yang cukup panjang, dianggap salah baca
    optis dan dilebur ke varian yang lebih sering muncul. Nama tampilan tiap
    kelompok adalah penulisan mentah yang paling sering digunakan."""
    kunci = seri.map(kunci_hakim)
    utama: list[str] = []
    peta: dict[str, str] = {}
    for k in kunci.value_counts().index:
        # Kunci kosong berarti hanya gelar. Kunci tiga huruf atau kurang,
        # seperti jja, adalah potongan yang tidak sahih hasil salah baca, bukan
        # nama orang, dan ikut dikeluarkan dari daftar maupun hitungan.
        if not k or len(k.replace(" ", "")) <= 3 or not _nama_sah(k):
            peta[k] = ""
            continue
        tujuan = k
        for u in utama:
            if _serupa(k, u):
                tujuan = u
                break
        if tujuan == k:
            utama.append(k)
        peta[k] = tujuan
    kunci_final = kunci.map(peta)
    isi = pd.DataFrame({"k": kunci_final, "n": seri})
    tampilan = (isi[isi["k"] != ""].groupby("k")["n"]
                .agg(lambda x: _rapi_kapital(
                    nama_tanpa_gelar(x.value_counts().index[0])
                    or str(x.value_counts().index[0]))))
    return kunci_final, tampilan


def _rapi_kapital(nama: str) -> str:
    """Awal kata dibesarkan, supaya penulisan yang berbeda hurufnya tampil
    seragam. Nama yang seluruhnya kapital dibiarkan menjadi kapital awal
    juga, karena risalah menulis nama yang sama dengan dua gaya berbeda."""
    kata = []
    for w in str(nama).split():
        if "." in w and len(w) <= 6:      # inisial seperti J.B. atau L.Y.
            kata.append(w.upper())
        else:
            kata.append(w[:1].upper() + w[1:].lower())
    return " ".join(kata)


def _serupa(a: str, b: str) -> bool:
    """Dua kunci dianggap satu orang bila hampir sama.

    Ambangnya bergantung panjang nama. Nama pendek diperlakukan ketat karena
    dua nama berbeda bisa saja hanya selisih satu huruf, sedangkan nama
    panjang diberi kelonggaran dua huruf, karena pemindaian pada nama panjang
    kerap salah lebih dari satu huruf sekaligus, seperti Ruwaidah Afiyati
    yang terbaca Rirvaidah Afiyati.
    """
    if len(a) < 8 or len(b) < 8:
        return False
    if _selisih_satu(a, b):
        return True

    ka, kb = a.split(), b.split()
    pendek, panjang = (ka, kb) if len(ka) <= len(kb) else (kb, ka)

    # Satu penulisan membawa kata tambahan di belakang, misalnya sisa
    # jabatan atau nama yang tertulis lebih lengkap, sementara seluruh kata
    # awalnya sama persis. Contoh nyata: "yohanes silverius winoto" dan
    # "yohanes silverius winoto ali".
    if (len(pendek) >= 2 and len(panjang) - len(pendek) <= 2
            and panjang[:len(pendek)] == pendek):
        return True

    # Jumlah katanya sama dan hanya satu kata yang berbeda, sedangkan kata
    # itu masih berdekatan ejaannya. Ini pola salah baca pada satu kata,
    # misalnya "ruwaidah afiyati" terbaca "rirvaidah afiyati", sementara
    # nama keluarganya tetap sama persis.
    if len(ka) == len(kb) and len(ka) >= 2:
        beda = [(x, y) for x, y in zip(ka, kb) if x != y]
        if len(beda) == 1:
            x, y = beda[0]
            if min(len(x), len(y)) >= 6 and _jarak_maks(x, y, 3):
                return True

    if min(len(a), len(b)) >= 13 and abs(len(a) - len(b)) <= 2:
        return _jarak_maks(a, b, 2)
    return False


def _jarak_maks(a: str, b: str, batas: int) -> bool:
    """Benar bila jarak sunting kedua untai tidak melebihi batas."""
    sebelum = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        kini = [i]
        for j, cb in enumerate(b, 1):
            kini.append(min(sebelum[j] + 1, kini[j - 1] + 1,
                            sebelum[j - 1] + (ca != cb)))
        if min(kini) > batas:
            return False
        sebelum = kini
    return sebelum[-1] <= batas


def selang_wilson(k: int, n: int) -> tuple[float, float]:
    """Selang kepercayaan Wilson untuk proporsi, dalam persen."""
    if n == 0:
        return 0.0, 0.0
    z, p = 1.96, k / n
    d_ = 1 + z * z / n
    tengah = (p + z * z / (2 * n)) / d_
    lebar = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d_
    return max(0.0, tengah - lebar) * 100, min(1.0, tengah + lebar) * 100


def sorot(teks: str, istilah: list[str]) -> str:
    import html
    import re as _re

    aman = html.escape(teks)
    for kata in sorted({k.strip('"') for k in istilah if len(k.strip('"')) >= 3},
                       key=len, reverse=True):
        aman = _re.sub(f"({_re.escape(html.escape(kata))})",
                       r"<mark>\1</mark>", aman, flags=_re.IGNORECASE)
    return aman


def bagan(fig, tinggi: int | None = None, tabel: pd.DataFrame | None = None,
          catatan: str | None = None, kunci: str | None = None):
    """
    Satu pintu untuk menampilkan bagan.

    theme=None wajib, karena Streamlit menimpa tema Plotly dengan temanya
    sendiri tanpa terlihat. Panel tabel hanya disertakan kalau bagannya tidak
    dapat menuliskan seluruh nilainya sendiri. Kalau kunci diberikan, bagannya
    dapat diklik dan yang terpilih dikembalikan.
    """
    if kunci:
        ev = st.plotly_chart(TV.rapikan(fig, tinggi, GELAP), width="stretch",
                             theme=None, key=kunci, on_select="rerun",
                             selection_mode="points",
                             config={"displayModeBar": False})
    else:
        ev = None
        st.plotly_chart(TV.rapikan(fig, tinggi, GELAP), width="stretch",
                        theme=None, config={"displayModeBar": False})
    if catatan:
        st.caption(catatan)
    if tabel is not None and not tabel.empty:
        with st.expander("Lihat angka lengkapnya sebagai tabel"):
            judul_fig = ""
            try:
                judul_fig = fig.layout.title.text or ""
            except Exception:
                pass
            tabel_bernavigasi(
                tabel, "bg_" + re.sub(r"\W+", "-", judul_fig.lower())[:36])
    return ev


def titik_terpilih(ev) -> str | None:
    try:
        titik = ev.selection.points
    except AttributeError:
        return None
    if not titik:
        return None
    t = titik[0]
    return t.get("y") if t.get("y") is not None else t.get("x")


def tabel_bernavigasi(df_: pd.DataFrame, kunci: str, per: int = 10,
                      kolom_persen: tuple = (), kelas: str = "") -> None:
    """
    Tabel yang ditampilkan sepuluh baris sekaligus, dengan tombol maju mundur.

    Tabel panjang yang ditampilkan sekaligus memaksa pembaca menggulir, dan
    begitu ia menggulir, kepala kolomnya hilang dari pandangan sehingga
    angka pada kolom kelima tidak lagi diketahui artinya. Dengan sepuluh
    baris, seluruh tabel beserta kepala kolomnya selalu muat dalam satu
    layar.
    """
    n = len(df_)
    if n == 0:
        return
    total = (n + per - 1) // per
    simpan = f"hal_{kunci}"
    hal = max(0, min(int(st.session_state.get(simpan, 0)), total - 1))

    potong = df_.iloc[hal * per:(hal + 1) * per]
    st.html('<div class="gulung">'
            + TV.tabel(potong, kolom_persen=kolom_persen, kelas=kelas)
            + "</div>")
    if total <= 1:
        return

    # Tombol yang tidak dapat dipakai tidak digambar, bukan digambar dalam
    # keadaan mati. Tombol mati bawaan Streamlit memakai tulisan yang sangat
    # pudar, rasio kontrasnya 2,65 sehingga di bawah ambang keterbacaan, dan
    # kehadirannya pun tidak menambah keterangan apa pun bagi pembaca.
    kiri, tengah, kanan = st.columns([1, 3, 1])
    with kiri:
        if hal > 0 and st.button("Sebelumnya", key=f"mundur_{kunci}",
                                 width="stretch"):
            st.session_state[simpan] = hal - 1
            st.rerun()
    with tengah:
        st.html(
            f'<div class="nav-tabel">Baris {hal * per + 1} sampai '
            f'{min(n, (hal + 1) * per)} dari {n:,} · halaman {hal + 1} '
            f'dari {total}</div>')
    with kanan:
        if hal < total - 1 and st.button("Berikutnya", key=f"maju_{kunci}",
                                         width="stretch"):
            st.session_state[simpan] = hal + 1
            st.rerun()
    unduh_tabel(df_, kunci)


def potong_halaman(df_: pd.DataFrame, kunci: str,
                   per: int = 10) -> tuple[pd.DataFrame, dict]:
    """
    Memotong bingkai sumber menjadi sepuluh baris yang sedang tampil.

    Pasangan gambar_nav() di bawah. Dipisah dua supaya daftar yang barisnya
    dapat diklik ikut aturan sepuluh baris yang sama dengan tabel biasa:
    pemanggil memotong sumbernya dulu, menggambar daftarnya sendiri dari
    potongan itu, lalu menggambar tombol maju mundurnya. Nomor baris pilihan
    dengan sendirinya mengacu pada potongan, bukan bingkai penuh.
    """
    n = len(df_)
    total = max(1, (n + per - 1) // per)
    simpan = f"hal_{kunci}"
    hal = max(0, min(int(st.session_state.get(simpan, 0)), total - 1))
    return (df_.iloc[hal * per:(hal + 1) * per],
            {"kunci": kunci, "hal": hal, "total": total, "n": n, "per": per})


def gambar_nav(nav: dict) -> None:
    """Tombol maju mundur untuk potongan dari potong_halaman()."""
    if nav["total"] <= 1:
        return
    hal, per, n, kunci = nav["hal"], nav["per"], nav["n"], nav["kunci"]
    kiri, tengah, kanan = st.columns([1, 3, 1])
    with kiri:
        if hal > 0 and st.button("Sebelumnya", key=f"mundur_{kunci}",
                                 width="stretch"):
            st.session_state[f"hal_{kunci}"] = hal - 1
            st.rerun()
    with tengah:
        st.html(
            f'<div class="nav-tabel">Baris {hal * per + 1} sampai '
            f'{min(n, (hal + 1) * per)} dari {n:,} · halaman {hal + 1} '
            f'dari {nav["total"]}</div>')
    with kanan:
        if hal < nav["total"] - 1 and st.button(
                "Berikutnya", key=f"maju_{kunci}", width="stretch"):
            st.session_state[f"hal_{kunci}"] = hal + 1
            st.rerun()


def unduh_laporan(judul: str, ringkas: list, tabel_df: pd.DataFrame | None,
                  catatan: str, kunci: str) -> None:
    """
    Berkas ringkasan halaman yang siap dilampirkan ke nota dinas.

    Tombol unduh CSV melayani pengolah data, tetapi bahan rapat memerlukan
    bentuk lain: satu berkas rapi berisi angka kunci halaman beserta catatan
    batasnya. Berkasnya HTML yang dibuka Microsoft Word sebagai dokumen
    biasa, sehingga tidak memerlukan pustaka pembentuk dokumen apa pun di
    peladen, dan hurufnya Aptos sesuai standar dokumen kantor.
    """
    import datetime as _dt

    kini = _dt.date.today().strftime("%d-%m-%Y")
    baris = "".join(
        f"<tr><td style='width:38%'><b>{lab}</b></td>"
        f"<td style='width:22%;text-align:right'><b>{val}</b></td>"
        f"<td style='color:#444'>{ket}</td></tr>"
        for lab, val, ket in ringkas)
    isi_tabel = ""
    if tabel_df is not None and not tabel_df.empty:
        isi_tabel = ("<h3>Data pendukung</h3>"
                     + tabel_df.head(30).to_html(index=False, border=0))
    html = f"""<html><head><meta charset="utf-8"><style>
      body {{ font-family: Aptos, Calibri, sans-serif; font-size: 11pt;
              margin: 2.2cm; color: #111; }}
      h1 {{ font-size: 15pt; margin-bottom: 2pt; }}
      h2 {{ font-size: 13pt; margin-top: 4pt; }}
      h3 {{ font-size: 11.5pt; margin-top: 14pt; }}
      .sumber {{ color: #555; font-size: 9.5pt; }}
      table {{ border-collapse: collapse; width: 100%; margin-top: 8pt; }}
      td, th {{ padding: 4pt 8pt; border-bottom: 1pt solid #ccc;
                text-align: left; font-size: 10.5pt; }}
      .catatan {{ margin-top: 14pt; padding: 8pt 10pt;
                  border-left: 3pt solid #1e3a6e; background: #f2f5fa;
                  font-size: 10pt; }}
    </style></head><body>
      <h1>Dashboard Analitik Sengketa Pajak</h1>
      <h2>{judul}</h2>
      <p class="sumber">Disusun otomatis pada {kini} dari arsip risalah
      putusan Pengadilan Pajak, sumber setpp.kemenkeu.go.id/risalah.
      Cakupan arsip saat penyusunan {cakupan:.1f} persen,
      {corong['urai']:,} putusan terurai.</p>
      <table>{baris}</table>
      {isi_tabel}
      <div class="catatan"><b>Batas data yang wajib disebut bila angka ini
      dikutip.</b><br>{catatan}</div>
    </body></html>"""
    st.download_button(
        "Unduh ringkasan halaman untuk lampiran (Word)",
        html.encode("utf-8"),
        file_name=f"ringkasan_{kunci}_{kini}.doc",
        mime="application/msword", key=f"lampir_{kunci}")


def unduh_tabel(df_: pd.DataFrame, kunci: str) -> None:
    """
    Tombol unduh seluruh isi tabel, bukan hanya halaman yang tampak.

    Tanpa ini, angka pada dashboard hanya dapat dibaca, tidak dapat dibawa
    ke dalam nota dinas maupun bahan paparan tanpa disalin ulang satu per
    satu. Pemisah titik koma dipakai supaya berkasnya langsung terbuka rapi
    pada Excel berlokal Indonesia.
    """
    if df_.empty:
        return
    isi = df_.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button(
        f"Unduh seluruh {len(df_):,} baris sebagai CSV", isi,
        file_name=f"{kunci}.csv", mime="text/csv",
        key=f"unduh_{kunci}", icon=":material/table_view:")


def saring_tahun(df_: pd.DataFrame, kolom: str, kunci: str,
                 label: str = "Rentang tahun ucap") -> pd.DataFrame:
    """
    Penyaring rentang tahun untuk halaman bersumber daftar resmi.

    Penyaring lingkup di bilah samping hanya mengatur arsip risalah, yang
    rentang tahunnya jauh lebih panjang daripada daftar resmi. Menyatukan
    keduanya di bawah satu kendali akan membuat pilihan tahun di luar
    jangkauan daftar resmi mengosongkan halaman tanpa penjelasan, jadi
    halaman yang bersumber daftar resmi diberi penyaringnya sendiri.
    """
    th = df_[kolom].dropna()
    if th.empty:
        return df_
    awal, akhir = int(th.min()), int(th.max())
    if awal >= akhir:
        return df_
    pilih = st.slider(label, awal, akhir, (awal, akhir), key=kunci)
    hasil = df_[df_[kolom].between(pilih[0], pilih[1])]
    if pilih != (awal, akhir):
        st.caption(f"Menampilkan tahun ucap {pilih[0]} sampai {pilih[1]}, "
                   f"yaitu {len(hasil):,} dari {len(df_):,} putusan pada "
                   "daftar resmi.")
    return hasil


def garis_waktu(t: pd.DataFrame, kolom_x: str, kolom_y: str, judul: str,
                teks: str | None = None, isi: bool = True):
    """
    Bagan garis untuk deret bersumbu waktu.

    Deret tahunan digambar sebagai garis, bukan batang, karena yang dicari
    pembaca adalah arah pergerakannya dari tahun ke tahun. Batang menyuruh
    mata membandingkan tinggi antar kategori yang sebenarnya bersambung.
    """
    fig = px.line(t, x=kolom_x, y=kolom_y, markers=True, title=judul,
                  text=teks)
    if isi:
        fig.update_traces(fill="tozeroy")
    if teks:
        fig.update_traces(textposition="top center",
                          textfont=dict(size=11, color=P["tinta"]))
    # Kelonggaran di kedua ujung sumbu waktu. Tanpa ini titik pertama dan
    # terakhir menempel tepat di tepi kartu, dan angka tahunnya terpotong.
    try:
        xs = pd.to_numeric(t[kolom_x])
        fig.update_xaxes(range=[float(xs.min()) - 0.6,
                                float(xs.max()) + 0.6])
    except (TypeError, ValueError):
        pass
    fig.update_xaxes(showgrid=False, title="", dtick=1)
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"], title="")
    return fig


def batang_peringkat(t: pd.DataFrame, kolom_label: str, kolom_nilai: str,
                     judul: str, teks: str | None = None):
    fig = px.bar(t.sort_values(kolom_nilai), x=kolom_nilai, y=kolom_label,
                 orientation="h", text=teks or kolom_nilai, title=judul)
    # Sumbu mendatar dimatikan. Tiap batang sudah menuliskan nilainya sendiri
    # di ujungnya, sehingga deret angka di bawahnya hanya mengulang, dan
    # angka terakhirnya kerap tersundul keluar kartu lalu terpotong.
    fig.update_xaxes(title="", showticklabels=False, showgrid=False,
                     zeroline=False)
    fig.update_yaxes(title="")
    return fig


def beramar(df_: pd.DataFrame) -> pd.DataFrame:
    """Putusan yang amarnya dikenali dan bukan pembetulan kesalahan tulis."""
    return df_[df_["amar"].notna() & (df_["amar"] != "pembetulan")]


def ledak_koreksi(df_: pd.DataFrame) -> pd.DataFrame:
    """Satu baris per pasangan putusan dan jenis koreksi."""
    k = (df_[["doc_id", "kode_jenis_pajak", "jenis_koreksi", "amar",
              "tahun_putusan"]]
         .dropna(subset=["jenis_koreksi"])
         .assign(k=lambda x: x["jenis_koreksi"].str.split("|")).explode("k"))
    k["Jenis koreksi"] = k["k"].map(lambda x: LABEL_KOREKSI.get(x, x))
    k["menang"] = k["amar"].isin(AMAR_MENANG)
    return k


def jeda_hari(df_: pd.DataFrame) -> pd.Series:
    """Jeda musyawarah ke pengucapan dalam hari, tersaring kewajaran."""
    t = df_.dropna(subset=["tanggal_ucap", "tanggal_musyawarah"])
    if t.empty:
        return pd.Series(dtype=float)
    u = pd.to_datetime(t["tanggal_ucap"], errors="coerce")
    m = pd.to_datetime(t["tanggal_musyawarah"], errors="coerce")
    j = (u - m).dt.days.dropna()
    return j[(j >= 0) & (j <= 1500)]


# ---------------------------------------------------------------------------
# Tema dan kerangka
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Dashboard Analitik Sengketa Pajak",
                   page_icon="🔷", layout="wide",
                   initial_sidebar_state="expanded")


def tema_terpakai() -> str:
    try:
        jenis = getattr(st.context.theme, "type", None)
        if jenis in ("light", "dark"):
            return jenis
    except Exception:
        pass
    return "light"


# Hanya terang dan gelap. Lambang diberi U+FE0E supaya tampil satu warna.
TEMA_PILIHAN = ["light", "dark"]
TEMA_LABEL = {"light": "\u2600\ufe0e", "dark": "\u263e\ufe0e"}
TEMA_BROWSER = {"light": "Light", "dark": "Dark"}


def ganti_tema(pilihan: str) -> None:
    st.components.v1.html(
        f"""
        <script>
          try {{
            const w = window.parent;
            const kunci = [];
            for (let i = 0; i < w.localStorage.length; i++) {{
              const k = w.localStorage.key(i);
              if (k && k.startsWith('stActiveTheme')) kunci.push(k);
            }}
            if (kunci.length === 0) kunci.push('stActiveTheme-/-v2');
            kunci.forEach(k => w.localStorage.setItem(
                k, JSON.stringify("{TEMA_BROWSER.get(pilihan, 'Light')}")));
            w.location.reload();
          }} catch (e) {{}}
        </script>
        """, height=0)


if "tema_pilihan" not in st.session_state:
    st.session_state.tema_pilihan = tema_terpakai()

GELAP = tema_terpakai() == "dark"
P = TV.palet(GELAP)
TV.pasang_template(GELAP)
st.html(TV.gaya(GELAP))

try:
    corong = muat_corong()
    df = muat_putusan()
except Exception as exc:
    st.error(f"Basis data belum siap: {exc}")
    st.stop()

cakupan = 100 * corong["unduh"] / max(1, ID_MAKS)

# Cap pembaruan data di sisi kanan bilah judul. Diambil dari cap waktu
# unduhan terakhir yang terbawa di dalam paket data, sehingga otomatis
# berganti setiap paket baru terpasang, dan menjawab pertanyaan pertama
# pembaca angka: data ini per kapan.
_cap_data = keadaan_tarikan().get("cap")
st.html(TV.kop("Dashboard Analitik Sengketa Pajak",
               "Analitik Risalah Putusan Pengadilan Pajak · Sumber data: "
               "https://setpp.kemenkeu.go.id/risalah",
               (f"Pembaruan data terakhir<br><b>{_cap_data} WIB</b>"
                if _cap_data else "")))

with st.container(key="tema"):
    pilih_tema = st.segmented_control(
        "Mode tampilan", TEMA_PILIHAN, format_func=lambda x: TEMA_LABEL[x],
        default=st.session_state.tema_pilihan, label_visibility="collapsed")
if pilih_tema and pilih_tema != st.session_state.tema_pilihan:
    st.session_state.tema_pilihan = pilih_tema
    ganti_tema(pilih_tema)
    st.stop()

if df.empty:
    st.warning("Belum terdapat putusan yang terurai. Jalankan setpp_teks.py extract "
               "lalu setpp_parse.py parse.")
    st.stop()


# ---------------------------------------------------------------------------
# Bilah samping
# ---------------------------------------------------------------------------

HALAMAN = ["Ringkasan Eksekutif", "Nilai Sengketa", "Risalah Putusan", "Pola Putusan Sejenis",
           "Pilihan Upaya Hukum", "Konsistensi Putusan Hakim",
           "Sengketa Berulang", "Tema Sengketa", "Mutu Ketetapan",
           "Pasal Penentu", "Unit Penerbit Ketetapan",
           "Profil Hakim", "Karakter Memutus", "Banding Unit",
           "Durasi Penyelesaian Sengketa",
           "Panduan Analisis", "Metodologi"]
DIMENSI = {"Nilai Sengketa": "Deskriptif, data resmi",
           "Pola Putusan Sejenis": "Prediktif, frekuensi historis",
           "Pilihan Upaya Hukum": "Preskriptif",
           "Konsistensi Putusan Hakim": "Diagnostik",
           "Sengketa Berulang": "Diagnostik",
           "Tema Sengketa": "Diagnostik",
           "Mutu Ketetapan": "Diagnostik",
           "Pasal Penentu": "Diagnostik",
           "Unit Penerbit Ketetapan": "Diagnostik",
           "Profil Hakim": "Deskriptif",
           "Karakter Memutus": "Diagnostik",
           "Banding Unit": "Diagnostik",
           "Durasi Penyelesaian Sengketa": "Prediktif"}

# Tiga modul pengguna. Telusur putusan dan Catatan metode ada di semua modul:
# yang pertama tujuan setiap drill, yang kedua kejujuran metodologis yang
# tidak boleh disembunyikan dari siapa pun.
# Tiap modul peran dibuka dengan Beranda, halaman pembuka yang menyajikan
# tiga angka terpenting bagi peran itu beserta pertanyaan yang dapat dijawab
# halaman lain. Tanpa ini, semua peran mendarat di Ringkasan Eksekutif yang
# sama, dan menit pertama pemakaian habis untuk menebak nebak menu. Modul
# Semua sengaja tanpa Beranda, karena isinya memang untuk penjelajahan bebas.
MODUL = {
    "Semua": HALAMAN,
    "Pimpinan": ["Beranda", "Ringkasan Eksekutif", "Nilai Sengketa",
                 "Risalah Putusan", "Konsistensi Putusan Hakim",
                 "Sengketa Berulang", "Tema Sengketa", "Profil Hakim",
                 "Karakter Memutus", "Banding Unit",
                 "Durasi Penyelesaian Sengketa",
                 "Panduan Analisis",
                 "Metodologi"],
    "Fiskus": ["Beranda", "Ringkasan Eksekutif", "Tema Sengketa",
               "Mutu Ketetapan",
               "Pasal Penentu", "Unit Penerbit Ketetapan",
               "Konsistensi Putusan Hakim", "Karakter Memutus",
               "Banding Unit", "Risalah Putusan", "Panduan Analisis", "Metodologi"],
    "Wajib pajak": ["Beranda", "Ringkasan Eksekutif", "Pola Putusan Sejenis",
                    "Pilihan Upaya Hukum", "Risalah Putusan",
                    "Panduan Analisis", "Metodologi"],
}
# Nama halaman yang sah untuk tautan dan perpindahan, termasuk Beranda yang
# tidak berada pada daftar induk karena isinya bergantung modul.
HALAMAN_SAH = set(HALAMAN) | {"Beranda"}

# Modul dan halaman dititipkan pada alamat halaman, sehingga tampilan yang
# sedang dilihat dapat dikirim ke rekan dan dibuka kembali persis sama.
# Tanpa ini, seluruh pilihan hilang begitu halaman dimuat ulang, dan tidak
# ada cara menunjukkan tampilan tertentu dalam rapat selain menyuruh orang
# lain menyusuri menunya sendiri. Alamat hanya dibaca sekali pada kunjungan
# pertama, supaya perpindahan halaman sesudahnya tidak saling menimpa.
if not st.session_state.get("alamat_terbaca"):
    st.session_state["alamat_terbaca"] = True
    _q = st.query_params
    if _q.get("modul") in MODUL:
        st.session_state["modul"] = _q["modul"]
    if _q.get("halaman") in HALAMAN_SAH:
        st.session_state["nav"] = _q["halaman"]

# Urutan tampil bilah samping diatur lewat wadah, terlepas dari urutan
# kode: saklar instansi tampil paling atas karena itu pilihan analisis
# utama, menu halaman di bawahnya, lalu pencarian dan modul pengguna, dan
# penyaring lanjutan di paling bawah. Kodenya sendiri tetap berjalan dengan
# urutan lama, karena pemilih modul harus dihitung sebelum menu halaman.
bagian_instansi = st.sidebar.container()
bagian_menu = st.sidebar.container()
bagian_bawah = st.sidebar.container()
bagian_lingkup = st.sidebar.container()

bagian_bawah.html('<div class="sb-judul">Cari isi putusan</div>')
cari_cepat = bagian_bawah.text_input(
    "Cari cepat", key="cari_cepat", placeholder="Cari isi putusan...",
    label_visibility="collapsed")
if cari_cepat.strip():
    st.session_state["q_isi"] = cari_cepat.strip()
    # Kata kunci baru langsung membawa ke halaman telusur.
    if st.session_state.get("cari_lalu") != cari_cepat.strip():
        st.session_state["cari_lalu"] = cari_cepat.strip()
        st.session_state["nav_tujuan"] = "Risalah Putusan"

kode_peta = peta_kode()

# Saklar lingkup instansi: satu kendali yang membelah seluruh dashboard.
#
# Letaknya di sini, sebelum tombol menu digambar, dan itu bukan soal
# selera. Tombol menu memanggil muat ulang seketika begitu ditekan,
# sehingga baris apa pun sesudahnya tidak pernah dijalankan pada putaran
# itu. Ketika kendali ini berada sesudahnya, ia tidak ikut digambar,
# Streamlit menganggapnya sudah tidak dipakai lalu membuang keadaannya,
# dan pilihan pemakai kembali ke Semua setiap kali berpindah halaman.
# Urutan tampilnya tetap di puncak karena diarahkan ke wadahnya sendiri.
# DJP, DJBC, dan pemerintah daerah berbeda watak perkaranya, dan pemakai
# perlu dapat membaca setiap halaman untuk satu instansi saja. Dibuat
# sebagai lingkup di bilah samping, bukan tab per halaman, supaya seluruh
# enam belas halaman beserta tabnya ikut serentak tanpa digandakan.
# Lima pilihan: Semua sebagai bawaan yang memuat seluruh arsip termasuk
# putusan yang instansinya belum terbaca, lalu empat kluster analisis:
# Kemenkeu sebagai gabungan DJP dan DJBC, DJP sendiri, DJBC sendiri, dan
# pemerintah daerah.
LINGKUP_INSTANSI = {"Semua": None, "Kemenkeu": ("djp", "djbc"),
                    "DJP": ("djp",), "DJBC": ("djbc",),
                    "Pemda": ("pemda",),
                    "Belum terbaca": ("__kosong__",)}
# Bentuknya daftar jatuh, bukan deret pil. Lima pilihan tidak muat pada
# satu baris bilah samping, dan pilihan terakhirnya melipat sendiri menjadi
# baris penuh yang tampak seperti salah susun. Daftar jatuh selalu setinggi
# satu baris berapa pun banyak pilihannya, dan menyisakan ruang bagi
# pilihan baru di kemudian hari.
bagian_instansi.html('<div class="sb-judul">Unit analisis</div>')
pilih_instansi = bagian_instansi.selectbox(
    "Unit analisis", list(LINGKUP_INSTANSI), index=0,
    key="lingkup_instansi", label_visibility="collapsed",
    help="Membatasi seluruh halaman pada perkara melawan unit ini. "
         "Kemenkeu adalah gabungan DJP dan DJBC. Putusan yang unitnya "
         "belum terbaca hanya termuat pada pilihan Semua.")
pilih_instansi = pilih_instansi or "Semua"
kode_instansi = LINGKUP_INSTANSI.get(pilih_instansi)


# Bila tujuan drill tidak tersedia pada modul terpilih, modul dipulangkan ke
# Semua lebih dulu, sebelum pemilih modulnya digambar.
_tujuan = st.session_state.get("nav_tujuan")
if (_tujuan in HALAMAN
        and _tujuan not in MODUL.get(st.session_state.get("modul", "Semua"),
                                     HALAMAN)):
    st.session_state["modul"] = "Semua"

bagian_bawah.html('<div class="sb-judul">Modul pengguna</div>')
modul = bagian_bawah.selectbox("Modul pengguna", list(MODUL), key="modul",
                               label_visibility="collapsed")
daftar_hal = MODUL[modul]

# Perpindahan halaman lewat kode, misalnya drill dari daftar nomor putusan
# di halaman lain, dititipkan pada nav_tujuan lalu diterapkan di sini,
# sebelum pemilih halamannya digambar. Menulis langsung ke keadaan pemilih
# setelah pemilihnya tergambar dilarang Streamlit.
if st.session_state.get("nav_tujuan") in HALAMAN_SAH:
    st.session_state["nav"] = st.session_state.pop("nav_tujuan")
# Pilihan baris pada daftar asal drill dibersihkan di sini, sebelum daftarnya
# digambar ulang, supaya drill tidak terpicu lagi saat pengguna kembali.
if st.session_state.get("hapus_kunci"):
    st.session_state.pop(st.session_state.pop("hapus_kunci"), None)
# Halaman terpilih dapat hilang dari daftar ketika modul berganti.
if st.session_state.get("nav") not in daftar_hal:
    st.session_state["nav"] = daftar_hal[0]

bagian_menu.html('<div class="sb-judul">Halaman</div>')
# Menu berupa tombol, bukan pilihan bulat: yang dimaksud pengguna adalah
# berpindah halaman, bukan mencentang sesuatu. Kuncinya juga menjadi sasaran
# gaya, sehingga ikon dan penanda terpilih tidak bergantung urutan unsur.
halaman = st.session_state["nav"]
# Alamat halaman disamakan dengan tampilan yang sedang aktif, sehingga
# tautannya dapat langsung disalin dari bilah alamat peramban.
if (st.query_params.get("halaman") != halaman
        or st.query_params.get("modul") != modul):
    st.query_params.update({"modul": modul, "halaman": halaman})
st.html(TV.ikon_nav(daftar_hal, halaman, GELAP))
# Seluruh tombol menu dikumpulkan dalam satu wadah bernama, supaya jarak
# antar barisnya dapat dirapatkan sekaligus tanpa mengganggu jarak antar
# unsur lain di bilah samping.
with bagian_menu, st.container(key="menu-nav"):
    for _h in daftar_hal:
        if st.button(_h, key=TV.kunci_nav(_h), width="stretch"):
            if _h != halaman:
                st.session_state["nav"] = _h
                st.session_state.pop("buka_doc", None)
                st.rerun()

tahun_ada = sorted(int(t) for t in df["tahun_putusan"].dropna().unique())
if len(tahun_ada) > 1:
    # Penggeser rentang tidak dikenali semua orang. Keterangan pendek di
    # bawahnya menyebutkan gunanya, karena pemakai yang tidak terbiasa
    # cenderung mengira ini penunjuk, bukan alat.
    bagian_lingkup.html('<div class="sb-judul">Ruang lingkup data</div>')
    th = bagian_lingkup.slider(
        "Tahun putusan", min(tahun_ada), max(tahun_ada),
        (min(tahun_ada), max(tahun_ada)),
        help="Tarik salah satu ujungnya untuk mempersempit tahun. Seluruh "
             "halaman ikut menyesuaikan.")
    bagian_lingkup.caption("Geser untuk melihat tren tahunan.")
else:
    th = None

hanya_teks = bagian_lingkup.checkbox(
    "Hanya dokumen berlapis teks asli", value=False,
    help="Mengeluarkan dokumen hasil pengenalan karakter optis, yang "
         "keandalannya pada angka dan nomor pasal lebih rendah.")

# Tanpa penyaring aktif, bingkai singgahan dipakai langsung tanpa disalin.
# Salinan 24 MB per gerakan per sesi adalah salah satu penekan memori di
# peladen berjatah satu gigabita, dan seluruh halaman memang membaca tanpa
# mengubah. Ketika penyaring aktif, penyaringan itu sendiri sudah
# menghasilkan bingkai baru, jadi salinan tersendiri tetap tidak perlu.
d = df
if th and (th[0] > min(tahun_ada) or th[1] < max(tahun_ada)):
    d = d[d["tahun_putusan"].between(th[0], th[1]) | d["tahun_putusan"].isna()]
if hanya_teks:
    d = d[d["sumber_teks"] != "ocr"]
if kode_instansi == ("__kosong__",):
    # Perkara yang unit terbandingnya gagal terbaca dari dokumennya. Mereka
    # termuat pada pilihan Semua tetapi hilang dari keempat kluster, dan
    # tanpa pilihan ini tidak ada cara melihat apa yang hilang itu.
    d = d[d["instansi_terbanding"].isna()]
elif kode_instansi:
    d = d[d["instansi_terbanding"].isin(kode_instansi)]


def lingkup_unit(kode: tuple) -> pd.DataFrame:
    """Bingkai arsip untuk satu unit, memakai penyaring lain yang sedang
    aktif. Dipakai mode banding untuk menyiapkan dua sisi sekaligus."""
    b_ = df
    if th and (th[0] > min(tahun_ada) or th[1] < max(tahun_ada)):
        b_ = b_[b_["tahun_putusan"].between(th[0], th[1])
                | b_["tahun_putusan"].isna()]
    if hanya_teks:
        b_ = b_[b_["sumber_teks"] != "ocr"]
    return b_[b_["instansi_terbanding"].isin(kode)]


def resmi_lingkup() -> pd.DataFrame:
    """
    Daftar resmi yang mengikuti saklar lingkup instansi.

    Dipakai seluruh halaman penyaji angka, supaya pilihan DJP atau DJBC di
    bilah samping juga membelah angka resmi, bukan hanya arsip risalah.
    Validasi silang pada Metodologi sengaja tetap memakai daftar penuh,
    karena yang diuji di sana kecocokan arsip terhadap populasi, dan
    populasi tidak boleh ikut tersaring.
    """
    rs_ = muat_resmi()
    if kode_instansi and not rs_.empty and "terbanding" in rs_:
        peta_balik = {"djp": "DJP", "djbc": "DJBC", "pemda": "Pemda"}
        sasaran = [peta_balik[k] for k in kode_instansi]
        return rs_[rs_["terbanding"].isin(sasaran)]
    return rs_

bagian_lingkup.caption(
    f"{len(d):,} dari {len(df):,} putusan dalam lingkup.")

# Kepala halaman terpadu. Nama halaman didahulukan, karena itu penanda
# terpenting bagi pembaca yang baru berpindah; dimensi analisis dan lingkup
# unit menjadi label kecil di sampingnya, bukan baris tersendiri. Beranda
# dikecualikan karena judulnya menyebut peran, bukan nama halaman.
NAMA_LINGKUP = {
    "Kemenkeu": "Kemenkeu, DJP dan DJBC",
    "DJP": "hanya DJP",
    "DJBC": "hanya DJBC",
    "Pemda": "hanya Pemda",
    "Belum terbaca": "unit belum terbaca"}
if halaman != "Beranda":
    if halaman == "Metodologi":
        # Halaman ini memotret pipa data secara keseluruhan dan sengaja
        # tidak mengikuti unit analisis. Labelnya harus menyebut itu, sebab
        # label lingkup di atas angka seluruh arsip akan menyesatkan.
        label = "seluruh arsip" if kode_instansi else None
    else:
        label = NAMA_LINGKUP.get(pilih_instansi) if kode_instansi else None
    st.html(TV.kepala_halaman(halaman, DIMENSI.get(halaman), label))


# ---------------------------------------------------------------------------
# 1. Ringkasan eksekutif
# ---------------------------------------------------------------------------

def hal_ikhtisar() -> None:
    t1, t2 = st.tabs(["Ringkasan", "Proyeksi beban perkara"])
    with t1:
        _ikhtisar_ringkas()
    with t2:
        _ikhtisar_proyeksi()


def _ikhtisar_proyeksi() -> None:
    """
    Perkiraan jumlah perkara tahun berikutnya, untuk perencanaan peralihan.

    Pada 31 Desember 2026 Pengadilan Pajak beralih ke Mahkamah Agung, dan
    pertanyaan yang pasti muncul dalam rapat peralihan adalah berapa perkara
    yang akan diwarisi dan berapa yang akan masuk sesudahnya. Sumbernya
    daftar resmi Sekretariat 2021 sampai 2025, populasi penuh lima tahun,
    sehingga trennya bukan taksiran dari contoh.
    """
    rs = resmi_lingkup()
    if rs.empty or "tahun_ucap" not in rs:
        st.info("Daftar resmi belum tersedia untuk proyeksi.")
        return
    t = (rs.dropna(subset=["tahun_ucap"])
         .groupby(rs["tahun_ucap"].astype(int)).size()
         .rename_axis("Tahun").reset_index(name="Putusan"))
    t = t[t["Putusan"] >= 100]
    if len(t) < 3:
        st.info("Belum cukup tahun pada daftar resmi untuk proyeksi.")
        return

    # Proyeksi garis lurus sederhana beserta rentangnya. Metode yang lebih
    # rumit menuntut anggapan yang tidak dapat diperiksa pembaca; garis
    # lurus dapat diperiksa siapa pun dengan kalkulator.
    x = t["Tahun"].to_numpy(dtype=float)
    y = t["Putusan"].to_numpy(dtype=float)
    b, a = np.polyfit(x, y, 1)
    tahun_depan = int(x.max()) + 1
    taksir = a + b * tahun_depan
    sisa = y - (a + b * x)
    simpang = float(np.std(sisa, ddof=1)) if len(t) > 2 else 0.0
    bawah, atas = max(0.0, taksir - 2 * simpang), taksir + 2 * simpang

    k = st.columns(3)
    k[0].html(TV.kartu(f"Umumnya per tahun, {int(x.min())} sampai "
                       f"{int(x.max())}", f"{float(np.median(y)):,.0f}",
                       "median putusan per tahun pada daftar resmi"))
    k[1].html(TV.kartu(f"Perkiraan {tahun_depan}", f"{taksir:,.0f}",
                       "bila tren lima tahun berlanjut"))
    k[2].html(TV.kartu("Rentang wajarnya",
                       f"{bawah:,.0f} - {atas:,.0f}",
                       "dua simpangan dari garis tren"))

    arah = "naik" if b > 0 else "turun"
    st.markdown(
        f"Sepanjang {int(x.min())} sampai {int(x.max())}, jumlah putusan "
        f"bergerak **{arah} sekitar {abs(b):,.0f} per tahun**. Kalau tren "
        f"itu berlanjut, tahun {tahun_depan} akan berada di sekitar "
        f"**{taksir:,.0f} putusan**, dengan rentang wajar "
        f"{bawah:,.0f} sampai {atas:,.0f}.\n\n"
        "Angka ini untuk perencanaan kapasitas, bukan ramalan pasti: jumlah "
        "hakim, panitera, dan ruang sidang yang perlu disiapkan lembaga "
        "penerima berbanding lurus dengan angka ini.")

    # Perkiraan digambar sebagai batang, sewarna tetapi bergaris putus
    # putus, bukan sebagai wajik bergaris tegak. Bentuk wajik beserta
    # sungutnya menuntut pembaca memahami lambang statistik lebih dulu, dan
    # penguji melaporkan bagan lamanya sulit ditafsirkan. Batang bergaris
    # putus terbaca langsung: bentuknya sama dengan tahun lain sehingga
    # tingginya dapat dibandingkan, dan garis putusnya menyatakan angka ini
    # belum terjadi.
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=t["Tahun"], y=t["Putusan"], name="Sudah terjadi",
        marker_color=TV.lembut(P["seri"][0], 0.18),
        marker_line=dict(color=P["seri"][0], width=1.6),
        text=[f"{v:,.0f}" for v in t["Putusan"]], textposition="outside",
        textfont=dict(size=11),
        hovertemplate="%{x}: %{y:,} putusan<extra></extra>"))
    fig.add_trace(go.Bar(
        x=[tahun_depan], y=[taksir], name="Perkiraan, belum terjadi",
        # Garis tepi batang tidak mengenal ragam putus putus; yang
        # membedakannya dari batang lain adalah warnanya beserta pola
        # arsirnya.
        marker=dict(color=TV.lembut(P["seri"][1], 0.10),
                    line=dict(color=P["seri"][1], width=1.8),
                    pattern=dict(shape="/", size=6, solidity=0.22,
                                 fgcolor=P["seri"][1])),
        text=[f"{taksir:,.0f}"], textposition="outside",
        textfont=dict(size=11),
        error_y=dict(type="data", symmetric=False,
                     array=[atas - taksir], arrayminus=[taksir - bawah],
                     color=P["seri"][1], thickness=1.4, width=7),
        hovertemplate=(f"{tahun_depan}: perkiraan %{{y:,.0f}} putusan, "
                       f"rentang wajar {bawah:,.0f} sampai {atas:,.0f}"
                       "<extra></extra>")))
    fig.update_layout(
        title=f"Putusan per tahun, dan perkiraan {tahun_depan}",
        legend=dict(orientation="h", yanchor="top", y=-0.14,
                    xanchor="left", x=0),
        margin=dict(b=70), bargap=0.28)
    fig.update_xaxes(showgrid=False, dtick=1, title="")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"], title="",
                     rangemode="tozero")
    bagan(fig, 400, None,
          "Batang polos adalah jumlah yang sudah terjadi menurut daftar "
          "resmi. Batang berarsir di ujung kanan adalah "
          f"perkiraan tahun {tahun_depan}, yang belum terjadi. Garis tegak "
          "kecil di atasnya menunjukkan rentang wajar perkiraan itu: hasil "
          "sebenarnya dapat berada di mana saja sepanjang garis tersebut.")

    st.html(TV.catatan_siap(
        "Batas proyeksi ini.",
        "Proyeksi memakai tahun putusan diucapkan, bukan tahun perkara "
        "masuk, karena itulah yang tercatat lengkap pada daftar resmi. "
        "Peralihan kelembagaan ke Mahkamah Agung dapat mengubah laju "
        "penyelesaian pada tahun pertamanya, dan perubahan seperti itu "
        "tidak tertangkap garis tren mana pun."))


def _ikhtisar_ringkas() -> None:
    dd = beramar(d)
    n_menang = int(dd["amar"].isin(AMAR_MENANG).sum())
    pangsa = 100 * n_menang / len(dd) if len(dd) else 0
    j = jeda_hari(d)
    n_formal = int((d["amar"] == "tidak_dapat_diterima").sum())

    # Keterangan waktu di atas kartu angka. Angka tanpa keterangan kapan
    # tidak dapat dikutip: pembaca yang menyalinnya ke paparan tidak punya
    # cara menyebutkan angka itu berlaku untuk periode apa dan diambil
    # kapan. Dua duanya disebut, karena keduanya berbeda: rentang tahun
    # putusan yang diamati, dan saat arsipnya terakhir diperbarui.
    st.html(TV.keterangan_waktu(
        rentang_tahun(d), keadaan_tarikan().get("terakhir")))

    k = st.columns(4)
    k[0].html(TV.kartu("Putusan terurai", f"{len(d):,}",
                       f"dari {corong['unduh']:,} berkas terkumpul"))
    k[1].html(TV.kartu("Dikabulkan", f"{pangsa:.1f} %",
                       f"{n_menang:,} dari {len(dd):,} putusan beramar"))
    k[2].html(TV.kartu(
        "Jeda musyawarah ke pengucapan",
        f"{j.median():.0f} hari" if len(j) else "-",
        f"median dari {len(j):,} putusan bertanggal" if len(j) else ""))
    k[3].html(TV.kartu("Tidak dapat diterima", f"{n_formal:,}",
                       f"{100 * n_formal / max(1, len(d)):.1f} persen, gugur "
                       "sebelum pokok sengketa"))

    # Baris kedua dari daftar resmi 2021 sampai 2025: populasi penuh, bukan
    # contoh, sehingga angkanya boleh dikutip apa adanya.
    rs = resmi_lingkup()
    if not rs.empty:
        ada_rs = (rs[rs["mata_uang"] == "Rupiah"]
                  .dropna(subset=["nilai_awal", "nilai_akhir"]))
        kor = float((ada_rs["nilai_awal"] - ada_rs["nilai_akhir"]).sum())
        th0, th1 = int(rs["tahun_ucap"].min()), int(rs["tahun_ucap"].max())
        m0 = rs[rs["tahun_ucap"] == th0]["amar"].isin(AMAR_MENANG)
        m1 = rs[rs["tahun_ucap"] == th1]["amar"].isin(AMAR_MENANG)
        k2 = st.columns(3)
        k2[0].html(TV.kartu("Dikoreksi pengadilan",
                            f"Rp {kor / 1e12:,.1f} T",
                            f"nilai resmi {th0} sampai {th1}, rincian pada "
                            "halaman Nilai Sengketa"))
        k2[1].html(TV.kartu("Populasi resmi", f"{len(rs):,}",
                            f"putusan {th0} sampai {th1} pada daftar resmi "
                            "Sekretariat"))
        k2[2].html(TV.kartu(
            f"Dikabulkan {th1}, resmi",
            f"{100 * int(m1.sum()) / max(1, len(m1)):.1f} %",
            f"naik dari {100 * int(m0.sum()) / max(1, len(m0)):.1f} persen "
            f"pada {th0}"))

    st.html('<div class="tingkat">Temuan Utama</div>')
    kj = d[d["jenis_ketetapan"].notna() & d["amar"].notna()]
    kj_menang = (100 * kj["amar"].isin(AMAR_MENANG).sum() / len(kj)
                 if len(kj) else 0)
    norm = d[(d["nama_disamarkan"] == 0) & d["nama_pemohon_norm"].notna()]
    ulang = 0.0
    if len(norm):
        vc = norm["nama_pemohon_norm"].value_counts()
        ulang = 100 * int(vc[vc >= 2].sum()) / len(norm)
    # Tiap temuan disajikan sebagai satu blok: kalimat inti berhuruf besar,
    # keterangan pendukung di bawahnya, lalu tombol yang membawa langsung ke
    # halaman rinciannya. Sebelumnya rincian hanya disebut namanya, dan
    # pembaca harus mencarinya sendiri di menu samping.
    for inti, keterangan, tujuan in (
            (f"{kj_menang:.0f} persen ketetapan yang disengketakan "
             "berujung dikabulkan",
             f"seluruhnya atau sebagian. Dihitung dari {len(kj):,} putusan "
             f"yang jenis ketetapannya terbaca, bagian dari {len(d):,} "
             "putusan dalam lingkup; pada sisanya jenis ketetapan tidak "
             "tertulis terbaca di dokumennya.",
             "Mutu Ketetapan"),
            (f"{ulang:.0f} persen sengketa datang dari wajib pajak yang "
             "bersengketa lebih dari sekali",
             "Persoalan yang sama kembali ke pengadilan berulang kali, dan "
             "sebagian besar berakhir dengan amar yang sama pula.",
             "Sengketa Berulang"),
            ("Terdapat kelompok perkara yang putusannya bervariasi tiga arah",
             "pada perkara yang jenis pajak dan jenis koreksinya sama "
             "persis, sementara sebagian kelompok lain justru sangat "
             "seragam.",
             "Konsistensi Putusan Hakim")):
        st.html(f'<div class="temuan"><b>{inti}</b> {keterangan}</div>')
        if st.button(f"Buka halaman {tujuan}", icon=":material/arrow_forward:",
                     key=f"temuan-{TV.kunci_nav(tujuan)}"):
            st.session_state["nav_tujuan"] = tujuan
            st.rerun()

    t = (d.dropna(subset=["tahun_putusan"])["tahun_putusan"].astype(int)
         .value_counts().sort_index()
         .rename_axis("Tahun").reset_index(name="Putusan"))
    if not t.empty:
        fig = garis_waktu(t, "Tahun", "Putusan",
                          "Putusan terurai menurut tahun")
        bagan(fig, 320, None,
              "Tinggi batang mencerminkan seberapa banyak yang sudah "
              "terkumpul "
              f"(cakupan {cakupan:.1f} persen), bukan jumlah perkara yang sesungguhnya. Penarikan berjalan dengan urutan acak merata, "
              "sehingga proporsi antar kategori sudah bermakna sebagai "
              "taksiran, tetapi jumlah mutlak belum.")

    if not rs.empty:
        tren = (rs.assign(menang=rs["amar"].isin(AMAR_MENANG))
                .groupby("tahun_ucap")["menang"].agg(["sum", "size"])
                .reset_index())
        tren["Dikabulkan"] = 100 * tren["sum"] / tren["size"]
        tren["Ket"] = [f"{v:.1f}%" for v in tren["Dikabulkan"]]
        tren = tren.rename(columns={"tahun_ucap": "Tahun"})
        # Bagan ini tetap berupa batang meski bersumbu tahun, karena tepat di
        # atasnya sudah ada bagan garis. Dua garis berurutan membuat halaman
        # terasa seragam, dan pada rentang yang sempit seperti ini bentuk
        # batang lebih mudah dibandingkan antar tahunnya.
        fig = px.bar(tren, x="Tahun", y="Dikabulkan", text="Ket",
                     title="Tingkat dikabulkan menurut tahun ucap, data resmi")
        fig.update_xaxes(showgrid=False, dtick=1, title="")
        fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                         ticksuffix="%", range=[0, 100], title="")
        bagan(fig, 300, None,
              "Dihitung dari seluruh putusan resmi, bukan dari contoh arsip, "
              "sehingga angkanya dapat dikutip. Hampir dua dari tiga sengketa "
              "berakhir dengan ketetapan yang dikoreksi, dan angkanya terus "
              "naik dari tahun ke tahun.")

    unduh_laporan(
        "Ringkasan Eksekutif",
        [("Putusan terurai", f"{len(d):,}",
          f"dari {corong['unduh']:,} berkas terkumpul"),
         ("Tingkat dikabulkan", f"{pangsa:.1f} persen",
          f"{n_menang:,} dari {len(dd):,} putusan beramar"),
         ("Median jeda musyawarah ke pengucapan",
          f"{j.median():.0f} hari" if len(j) else "-",
          f"dari {len(j):,} putusan bertanggal"),
         ("Gugur sebelum pokok sengketa", f"{n_formal:,}",
          f"{100 * n_formal / max(1, len(d)):.1f} persen dari putusan "
          "terurai"),
         ("Ketetapan bersengketa berujung dikabulkan",
          f"{kj_menang:.0f} persen",
          f"dari {len(kj):,} putusan berjenis ketetapan"),
         ("Sengketa dari WP berulang", f"{ulang:.0f} persen",
          "wajib pajak yang bersengketa lebih dari sekali")],
        None,
        "Angka arsip dihitung dari cakupan "
        f"{cakupan:.1f} persen dan akan bergeser seiring penarikan; angka "
        "berlabel resmi dihitung dari populasi penuh 2021 sampai 2025 dan "
        "boleh dikutip apa adanya.",
        "ikhtisar")


# ---------------------------------------------------------------------------
# Nilai sengketa, dari daftar resmi
# ---------------------------------------------------------------------------

def hal_nilai() -> None:
    rs = resmi_lingkup()
    if rs.empty:
        st.info("Daftar resmi belum dimuat ke basis data. Jalankan "
                "setpp_resmi.py impor terlebih dahulu.")
        return
    st.caption(
        f"Sumber: daftar resmi putusan Sekretariat, {len(rs):,} putusan "
        "2021 sampai 2025. Angka ini mencakup populasi lengkap lima tahun, "
        "bukan contoh, sehingga halaman ini memakai penyaring tahunnya "
        "sendiri, bukan penyaring lingkup di bilah samping yang mengatur "
        "arsip risalah. Nilai dihitung dari putusan Rupiah yang nilai awal "
        "dan akhirnya terisi; amar tolak dan tidak dapat diterima umumnya "
        "tidak memuat nilai akhir, sehingga angka koreksi cenderung taksiran "
        "bawah.")

    rs = saring_tahun(rs, "tahun_ucap", "tahun_nilai")
    if rs.empty:
        st.info("Tidak terdapat putusan pada rentang tahun tersebut.")
        return

    rp = rs[rs["mata_uang"] == "Rupiah"]
    ada = rp.dropna(subset=["nilai_awal", "nilai_akhir"]).copy()
    ada["koreksi"] = ada["nilai_awal"] - ada["nilai_akhir"]

    t1, t2, t3 = st.tabs(["Ikhtisar nilai", "Konsentrasi nilai",
                          "Simulasi dampak"])
    with t1:
        _nilai_ikhtisar(ada)
    with t2:
        _nilai_konsentrasi(rs, rp, ada)
    with t3:
        _nilai_simulasi(ada)


def _nilai_ikhtisar(ada: pd.DataFrame) -> None:
    k = st.columns(3)
    k[0].html(TV.kartu("Nilai sengketa awal",
                       f"Rp {ada['nilai_awal'].sum() / 1e12:,.1f} T",
                       f"{len(ada):,} putusan Rupiah bernilai lengkap"))
    k[1].html(TV.kartu("Nilai setelah putusan",
                       f"Rp {ada['nilai_akhir'].sum() / 1e12:,.1f} T",
                       "jumlah nilai akhir menurut amar"))
    k[2].html(TV.kartu("Dikoreksi pengadilan",
                       f"Rp {ada['koreksi'].sum() / 1e12:,.1f} T",
                       "selisihnya, sepanjang 2021 sampai 2025"))

    # Dua garis, bukan satu batang selisih. Jarak antar garis itulah nilai
    # yang dikoreksi pengadilan, dan menggambarkannya sebagai bidang di
    # antara keduanya membuat besaran koreksi terbaca tanpa perlu dihitung
    # sendiri oleh pembaca, sekaligus menunjukkan skala sengketa awalnya.
    t = (ada.groupby("tahun_ucap")[["nilai_awal", "nilai_akhir"]]
         .sum().div(1e12).rename_axis("Tahun").reset_index())
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t["Tahun"], y=t["nilai_akhir"], name="Nilai setelah putusan",
        mode="lines+markers",
        hovertemplate="%{x}: Rp %{y:.1f} T<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=t["Tahun"], y=t["nilai_awal"], name="Nilai sengketa awal",
        mode="lines+markers", fill="tonexty",
        hovertemplate="%{x}: Rp %{y:.1f} T<extra></extra>"))
    fig.update_layout(
        title="Nilai sengketa sebelum dan sesudah putusan, per tahun ucap",
        legend=dict(orientation="h", yanchor="top", y=-0.12,
                    xanchor="left", x=0),
        margin=dict(b=64))
    fig.update_xaxes(showgrid=False, dtick=1, title="")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     title="Rp triliun")
    bagan(fig, 360, None,
          "Bidang di antara kedua garis adalah nilai yang dikoreksi "
          "pengadilan pada tahun itu. Lonjakan 2022 sebagian besar berasal "
          "dari satu putusan bernilai Rp 16,7 triliun. Nilai sengketa "
          "terpusat pada sedikit perkara bernilai sangat besar, dan itu "
          "merupakan sifat sebarannya.")

    unduh_laporan(
        "Nilai Sengketa",
        [("Nilai sengketa awal",
          f"Rp {ada['nilai_awal'].sum() / 1e12:,.1f} T",
          f"{len(ada):,} putusan Rupiah bernilai lengkap, 2021-2025"),
         ("Nilai setelah putusan",
          f"Rp {ada['nilai_akhir'].sum() / 1e12:,.1f} T",
          "jumlah nilai akhir menurut amar"),
         ("Dikoreksi pengadilan",
          f"Rp {ada['koreksi'].sum() / 1e12:,.1f} T",
          "selisih keduanya")],
        None,
        "Nilai dihitung dari putusan Rupiah yang nilai awal dan akhirnya "
        "terisi; amar tolak dan tidak dapat diterima umumnya tidak memuat "
        "nilai akhir, sehingga angka koreksi cenderung taksiran bawah. "
        "Sengketa bervaluta asing tidak dijumlahkan ke total Rupiah.",
        "nilai")


def _nilai_konsentrasi(rs: pd.DataFrame, rp: pd.DataFrame,
                       ada: pd.DataFrame) -> None:
    g = (ada.groupby("jenis_pajak")["koreksi"].agg(["sum", "count"])
         .sort_values("sum", ascending=False).head(10).reset_index()
         .rename(columns={"jenis_pajak": "Jenis pajak"}))
    g["Triliun"] = g["sum"] / 1e12
    g["Ket"] = [f"Rp {v:,.1f} T  (n={int(n):,})"
                for v, n in zip(g["Triliun"], g["count"])]
    bagan(batang_peringkat(g, "Jenis pajak", "Triliun",
                           "Nilai dikoreksi menurut jenis pajak, sepuluh "
                           "terbesar", "Ket"),
          max(280, 34 * len(g) + 120), None,
          "PPh Badan menyumbang koreksi terbesar dari jumlah perkara yang "
          "jauh lebih sedikit daripada PPN. Jumlah perkara badan sedikit, "
          "namun nilainya sangat besar, "
            "sehingga di sanalah risiko fiskal terbesar berada.")

    st.html('<div class="tingkat">Mutu Ketetapan Bernilai Besar</div>')
    isi = rp.dropna(subset=["nilai_awal"]).copy()
    isi["menang"] = isi["amar"].isin(AMAR_MENANG)
    tepi = [0, 1e8, 1e9, 1e10, 1e11, float("inf")]
    label = ["< Rp 100 jt", "Rp 100 jt - 1 M", "Rp 1 - 10 M",
             "Rp 10 - 100 M", "> Rp 100 M"]
    isi["Kelas"] = pd.cut(isi["nilai_awal"], bins=tepi, labels=label,
                          include_lowest=True)
    gs = (isi.groupby("Kelas", observed=True)["menang"]
          .agg(["sum", "size"]).reset_index())
    gs["Dikabulkan"] = 100 * gs["sum"] / gs["size"]
    gs["Ket"] = [f"{v:.1f}%  (n={n:,})"
                 for v, n in zip(gs["Dikabulkan"], gs["size"])]
    # Kelas besaran sengketa dibandingkan satu sama lain, bukan diikuti
    # pergerakannya sepanjang waktu, sehingga bentuk batang yang tepat.
    # Garis hanya cocok bila sumbunya benar benar berjalan, seperti tahun.
    fig = px.bar(gs, x="Kelas", y="Dikabulkan", text="Ket",
                 title="Tingkat dikabulkan menurut besaran sengketa")
    fig.update_xaxes(showgrid=False, title="")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     ticksuffix="%", range=[0, 100], title="")
    # Garis lima puluh persen menjadi patokan baca: di atasnya, lebih dari
    # separuh ketetapan yang dilawan berakhir dikoreksi. Keterangannya
    # ditaruh di kiri karena di kanan tersundul keluar kartu.
    fig.add_hline(y=50, line_dash="dot", line_color=P["sumbu"],
                  annotation_text="separuh perkara",
                  annotation_position="top left",
                  annotation_font=dict(size=11, color=P["tinta_2"]))
    bagan(fig, 340, None,
          "Polanya konsisten: semakin besar nilai ketetapan yang dilawan, "
          "semakin besar peluangnya dikoreksi pengadilan. Di kelas paling "
          "atas hampir sembilan dari sepuluh berujung koreksi.")
    st.html(TV.catatan_siap(
        "Implikasi kebijakan atas mutu ketetapan bernilai besar.",
        "Ketetapan bernilai besar yang kalah hampir pasti bukan soal "
        "administrasi, melainkan mutu koreksi. Penelaahan mutu sebelum "
        "penerbitan untuk setiap ketetapan di atas Rp 10 miliar berpotensi "
        "menghemat kerugian nilai terbesar dengan beban kerja tambahan "
        "paling kecil, karena jumlah ketetapannya sedikit."))

    st.html('<div class="tingkat">Instansi Terbanding</div>')
    rr = rs.assign(menang=rs["amar"].isin(AMAR_MENANG))
    gt = (rr.groupby("terbanding")["menang"].agg(["sum", "size"])
          .reset_index().rename(columns={"terbanding": "Terbanding"}))
    gt["Dikabulkan"] = 100 * gt["sum"] / gt["size"]
    gt["Ket"] = [f"{v:.1f}%  (n={n:,})"
                 for v, n in zip(gt["Dikabulkan"], gt["size"])]
    fig = batang_peringkat(gt, "Terbanding", "Dikabulkan",
                           "Tingkat dikabulkan menurut instansi terbanding",
                           "Ket")
    fig.update_xaxes(ticksuffix="%", range=[0, 118], dtick=20)
    bagan(fig, 250, None,
          "Ketetapan DJP dikoreksi jauh lebih sering daripada DJBC, dan "
          "hampir seluruh nilai koreksi lima tahun terhimpun pada DJP. "
          "Keduanya memerlukan pendekatan pembenahan yang berbeda.")

    st.html('<div class="tingkat">Pemohon dengan Nilai Terbesar</div>')
    gp = (ada.groupby("nama_pemohon")
          .agg(Putusan=("koreksi", "size"),
               awal=("nilai_awal", "sum"), kor=("koreksi", "sum"))
          .sort_values("awal", ascending=False).head(8).reset_index()
          .rename(columns={"nama_pemohon": "Pemohon"}))
    gp["Nilai sengketa, Rp triliun"] = (gp["awal"] / 1e12).round(2)
    gp["Dikoreksi, Rp triliun"] = (gp["kor"] / 1e12).round(2)
    tabel_bernavigasi(
        gp[["Pemohon", "Putusan", "Nilai sengketa, Rp triliun",
            "Dikoreksi, Rp triliun"]], "pemohon_nilai")
    va = rs[rs["mata_uang"].notna() & (rs["mata_uang"] != "Rupiah")]
    st.caption(
        f"Di luar seluruh angka halaman ini terdapat {len(va):,} sengketa "
        "bervaluta asing, hampir semuanya dolar AS, umumnya perkara "
        "kepabeanan dan transfer pricing, yang tidak dijumlahkan ke total "
        "Rupiah.")


def _nilai_simulasi(ada: pd.DataFrame) -> None:
    """
    Mengubah temuan menjadi angka yang dapat diperjuangkan.

    Seluruh halaman lain berhenti pada pernyataan bahwa mutu ketetapan perlu
    dibenahi. Pernyataan itu benar tetapi tidak dapat dimasukkan ke dalam
    usulan anggaran maupun nota kebijakan, karena tidak menyebut berapa
    besar manfaatnya. Bagian ini menghitung besarnya, dengan cara yang
    sederhana dan dinyatakan terbuka batasnya.
    """
    if ada.empty:
        st.info("Belum terdapat putusan bernilai lengkap pada rentang ini.")
        return

    n = len(ada)
    menang = ada["amar"].isin(AMAR_MENANG)
    n_kabul = int(menang.sum())
    if n_kabul == 0:
        st.info("Belum terdapat putusan yang dikabulkan pada rentang ini.")
        return
    laju = 100 * n_kabul / n
    koreksi = float(ada["koreksi"].sum())
    per_putusan = koreksi / n_kabul

    st.markdown(
        "Bagian ini menjawab pertanyaan yang selalu muncul dalam rapat: "
        "**kalau mutu ketetapan diperbaiki, berapa nilainya?**\n\n"
        f"Dasarnya keadaan sekarang. Dari {n:,} putusan bernilai lengkap, "
        f"{n_kabul:,} dikabulkan, yaitu {laju:.1f} persen, dan nilai yang "
        f"dikoreksi pengadilan berjumlah Rp {koreksi / 1e12:,.1f} triliun. "
        f"Jadi satu putusan yang dikabulkan rata rata membawa koreksi "
        f"Rp {per_putusan / 1e9:,.1f} miliar.\n\n"
        "Geser tuas di bawah untuk melihat dampaknya bila tingkat "
        "dikabulkan berhasil diturunkan sekian poin.")

    turun = st.slider(
        "Penurunan tingkat dikabulkan, dalam poin persen", 1, 20, 5,
        key="sim_turun",
        help="Lima poin berarti tingkat dikabulkan turun dari, misalnya, "
             "enam puluh persen menjadi lima puluh lima persen.")

    laju_baru = max(0.0, laju - turun)
    kabul_baru = n * laju_baru / 100
    selamat = n_kabul - kabul_baru
    nilai_selamat = selamat * per_putusan

    k = st.columns(3)
    k[0].html(TV.kartu("Tingkat dikabulkan menjadi", f"{laju_baru:.1f} %",
                       f"turun {turun} poin dari {laju:.1f} persen"))
    k[1].html(TV.kartu("Ketetapan yang bertahan", f"{selamat:,.0f}",
                       f"dari {n_kabul:,} yang kini dikabulkan"))
    k[2].html(TV.kartu("Nilai yang tidak jadi dikoreksi",
                       f"Rp {nilai_selamat / 1e12:,.1f} T",
                       "sepanjang rentang tahun yang dipilih"))

    # Bagan tangga, bukan satu angka tunggal. Yang menentukan keputusan
    # bukan hasil satu pilihan penurunan, melainkan bentuk hubungan antara
    # besar perbaikan dan nilai yang diselamatkan, karena dari situ terbaca
    # apakah perbaikan kecil sudah cukup berarti atau tidak.
    langkah = list(range(1, 21))
    t = pd.DataFrame({
        "Penurunan": langkah,
        "Triliun": [(n_kabul - n * max(0.0, laju - x) / 100) * per_putusan / 1e12
                    for x in langkah]})
    fig = px.bar(t, x="Penurunan", y="Triliun",
                 title="Nilai yang tidak jadi dikoreksi menurut besar perbaikan")
    fig.update_traces(marker_color=P["seri"][0],
                      hovertemplate="turun %{x} poin: Rp %{y:.1f} triliun"
                                    "<extra></extra>")
    fig.update_xaxes(showgrid=False, dtick=1,
                     title="Penurunan tingkat dikabulkan, poin persen")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     title="Rp triliun")
    # Ruang bawah ditambah; tanpa ini judul sumbunya terpotong tepi kartu.
    fig.update_layout(margin=dict(b=74))
    # Pilihan yang sedang aktif ditandai supaya tuas di atas dan bagan di
    # bawah terbaca sebagai satu kesatuan, bukan dua sajian terpisah.
    fig.add_vline(x=turun, line_dash="dot", line_color=P["tinta_2"])
    bagan(fig, 380, None,
          "Hubungannya lurus, karena perhitungannya memang lurus. Yang "
          "perlu dibaca adalah besarannya: berapa triliun yang bergantung "
          "pada tiap satu poin perbaikan.")

    st.html(TV.catatan_siap(
        "Batas taksiran ini, yang harus disebut ketika angkanya dikutip.",
        "Perhitungannya lurus dan sengaja dibuat sederhana, sehingga "
        "seluruh anggapannya dapat diperiksa. Nilai koreksi dianggap "
        "tersebar merata pada seluruh putusan yang dikabulkan, padahal "
        "kenyataannya terpusat pada sedikit perkara bernilai sangat besar, "
        "sehingga hasil sebenarnya bergantung pada perkara mana yang "
        "berhasil dipertahankan. Perhitungan ini juga menganggap perbaikan "
        "mutu tidak mengubah jumlah perkara yang masuk, padahal ketetapan "
        "yang lebih kuat semestinya justru mengurangi jumlah sengketa. "
        "Karena itu angka ini sebaiknya disebut sebagai taksiran urutan "
        "besaran, bukan sebagai proyeksi penerimaan."))


# ---------------------------------------------------------------------------
# 2. Telusur putusan
# ---------------------------------------------------------------------------

# Ikon tombol unduh mengikuti bentuk berkasnya, supaya sekilas terlihat apa
# yang akan diterima: teks hasil ekstraksi, PDF asli, atau dokumen Word.
IKON_BERKAS = {".pdf": ":material/picture_as_pdf:",
               ".doc": ":material/description:",
               ".docx": ":material/description:"}


def ikon_berkas(nama: str) -> str:
    return IKON_BERKAS.get(os.path.splitext(str(nama))[1].lower(),
                           ":material/draft:")


# Dua pergantian baris sebagai tetapan, supaya untai panjang di bawah tidak
# perlu memuat lambang pelarian yang mudah rusak ketika disunting.
NL2 = chr(10) + chr(10)


def belum_ada(pesan: str) -> None:
    """
    Pemberitahuan bahwa tidak ada data, yang menyebut sebabnya.

    Keterangan kosong yang hanya berbunyi belum terdapat data membuat
    pembaca menduga dashboardnya rusak. Ketika penyebabnya penyaring yang
    sedang aktif, penyaring itu wajib disebut namanya, beserta jalan
    keluarnya. Unit analisis disebut lebih dulu karena itu penyaring paling
    sering menyempitkan populasi sampai kosong.
    """
    sebab = []
    if kode_instansi:
        sebab.append(f"unit analisis **{pilih_instansi}**")
    if th and (th[0] > min(tahun_ada) or th[1] < max(tahun_ada)):
        sebab.append(f"tahun **{th[0]} sampai {th[1]}**")
    if hanya_teks:
        sebab.append("**hanya dokumen berlapis teks asli**")
    if sebab:
        st.info(pesan + NL2 + "Penyaring yang sedang aktif: "
                + ", ".join(sebab)
                + ". Melonggarkan salah satunya, misalnya memilih unit "
                  "analisis Semua, kemungkinan memunculkan datanya.")
    else:
        st.info(pesan + NL2 + "Seluruh penyaring sedang terbuka, jadi data "
                "ini memang belum tersedia pada arsip yang sudah "
                "terkumpul.")


def tombol_kembali(kunci_daftar: str, label: str) -> None:
    """
    Tombol pulang untuk drill di dalam halaman.

    Drill yang berpindah halaman sudah punya tombol kembali di tampilan isi
    putusan, tetapi drill bertingkat di dalam satu halaman, dari daftar ke
    rincian, selama ini hanya bisa ditutup dengan menghapus centang pada
    barisnya, dan tidak ada yang menebak itu. Tombol ini menghapus pilihan
    barisnya lalu menggambar ulang, sehingga rinciannya menutup dan
    daftarnya kembali seperti semula.
    """
    if st.button(label, icon=":material/arrow_back:",
                 key=f"balik_{kunci_daftar}"):
        st.session_state.pop(kunci_daftar, None)
        st.rerun()


def buka_putusan(doc_id, kunci_daftar: str | None = None) -> None:
    """Drill dari daftar nomor putusan di halaman mana pun: catat dokumen
    yang dituju lalu pindah ke halaman telusur, tempat isinya digambar.

    Kunci daftar asalnya ikut dititipkan untuk dihapus pada awal putaran
    berikutnya. Tanpa itu pilihan barisnya tersimpan terus, dan setiap kali
    pengguna kembali ke halaman asal, drill yang sama terpicu lagi.

    Halaman asal juga dicatat, supaya tombol kembali pada tampilan isi
    putusan membawa pengguna pulang ke halaman tempat dia berangkat."""
    st.session_state["buka_doc"] = int(doc_id)
    st.session_state["asal_drill"] = st.session_state.get("nav")
    st.session_state["nav_tujuan"] = "Risalah Putusan"
    if kunci_daftar:
        st.session_state["hapus_kunci"] = kunci_daftar
    st.rerun()


def tampil_detail(r, cuplikan=None, q_isi: str = "") -> None:
    """Tingkat paling dalam: identitas perkara, majelis, isi putusan yang
    disusun seperti naskah aslinya, dan tombol unduh."""
    cuplikan = cuplikan or {}
    judul = tampil(r.get("nomor_tampil"), f"Dokumen {r['doc_id']}")

    kol = st.columns(3)
    kol[0].markdown(f"**Pemohon**  \n{tampil(r['nama_pemohon'])}\n\n"
                    f"**Jenis perkara**  \n{r['jenis_perkara_label']}\n\n"
                    f"**Tanggal putusan**  \n"
                    f"{tampil_tanggal(r['tanggal_ucap'], tampil_tahun(r['tahun_putusan']))}")
    kol[1].markdown(f"**Instansi terbanding**  \n"
                    f"{LABEL_INSTANSI.get(r['instansi_terbanding'], '-')}\n\n"
                    f"**Ketetapan**  \n{tampil(r['jenis_ketetapan'])} "
                    f"{tampil(r['nomor_ketetapan'], '')}\n\n"
                    f"**Amar**  \n{LABEL_AMAR.get(r['amar'], 'tidak dikenali')}")
    kol[2].markdown(f"**Jenis pajak**  \n"
                    f"{label_kode(r['kode_jenis_pajak'], kode_peta)}\n\n"
                    f"**Tahun pajak**  \n{tampil(r['tahun_pajak'])}\n\n"
                    f"**Pengenal berkas**  \n{r['doc_id']}")

    st.markdown("**Majelis hakim**")
    ketua = tampil(r["hakim_ketua"], "")
    anggota_mentah = tampil(r["hakim_anggota"], "")
    panitera = tampil(r["panitera"], "")
    if ketua or anggota_mentah:
        st.markdown(
            f"- Ketua: {ketua or 'tidak terbaca'}\n"
            + "".join(f"- Anggota: {a}\n"
                      for a in anggota_mentah.split("|") if a)
            + (f"- Panitera pengganti: {panitera}\n" if panitera else ""))
    else:
        st.caption("Susunan majelis tidak tersedia. Risalah era lama yang berformat Word tidak memuat susunan "
            "majelis. Hal tersebut merupakan sifat dokumennya, bukan "
            "kegagalan "
            "pembacaan.")

    if r["doc_id"] in cuplikan:
        st.markdown("**Cuplikan yang cocok**")
        st.markdown(str(cuplikan[r["doc_id"]]).replace("\n", " "))

    isi, berkas = muat_isi(int(r["doc_id"]))
    if not isi:
        st.warning("Teks belum tersedia. Kemungkinan masih menunggu OCR.")
        return
    st.caption(f"{len(isi):,} karakter. Sumber teks {r['sumber_teks']}. "
               f"Berkas asli: {berkas}")
    istilah = [t for t in q_isi.replace('"', " ").split()
               if t.upper() not in ("OR", "AND", "NOT")]
    # Tiap alinea diberi kelas tampilan yang meniru susunan naskah aslinya:
    # kepala putusan dirata tengah dan ditebalkan, badan dirata kiri kanan.
    potongan = []
    for a in TV.alinea(isi[:200000]):
        kls = TV.kelas_alinea(a)
        atribut = f' class="{kls}"' if kls else ""
        potongan.append(f"<p{atribut}>{sorot(a, istilah)}</p>")
    st.html(f"<div class='isi-putusan'>{''.join(potongan)}</div>")
    if len(isi) > 200000:
        st.caption("Teks dipotong pada dua ratus ribu karakter. Naskah lengkapnya tersedia melalui tombol unduh.")

    # Tampilan web di atas adalah susunan ulang untuk membaca cepat. Untuk
    # kutipan resmi, yang disediakan adalah berkas asli dari Sekretariat apa
    # adanya, karena teks hasil ekstraksi dapat memuat salah baca dan tidak
    # boleh menjadi rujukan hukum.
    u1, u2 = st.columns(2)
    with u1:
        st.download_button("Unduh teks hasil ekstraksi", isi,
                           file_name=f"{judul.replace('/', '-')}.txt",
                           icon=":material/article:")
    with u2:
        if berkas and os.path.exists(berkas):
            try:
                ukuran = os.path.getsize(berkas)
                if ukuran <= 80 * 1024 * 1024:
                    with open(berkas, "rb") as fh:
                        st.download_button(
                            f"Unduh berkas asli "
                            f"({ukuran / 1e6:.1f} MB)",
                            fh.read(),
                            file_name=os.path.basename(berkas),
                            icon=ikon_berkas(berkas))
                else:
                    st.caption(f"Berkas asli {ukuran / 1e6:.0f} MB, terlalu "
                               f"besar untuk tombol unduh. Lokasinya: "
                               f"{berkas}")
            except OSError:
                st.link_button(
                    "Unduh berkas asli dari situs Sekretariat",
                    URL_BERKAS_ASLI.format(id=int(r["doc_id"])),
                    icon=":material/open_in_new:")
        else:
            # Arsip lokal tidak ada di mesin ini. Berkasnya publik, jadi
            # tombolnya menuju dokumen yang sama di peladen resmi.
            st.link_button(
                "Unduh berkas asli dari situs Sekretariat",
                URL_BERKAS_ASLI.format(id=int(r["doc_id"])),
                icon=":material/open_in_new:")
            st.caption("Arsip lokal tidak tersedia di peladen ini. Tombol "
                       "di atas mengambil berkas yang sama langsung dari "
                       "peladen Sekretariat Pengadilan Pajak.")


def hal_telusur() -> None:
    # Kedatangan dari drill di halaman lain: dokumen yang dititipkan dibuka
    # langsung, tanpa melewati tingkat pengelompokan. Dicari pada data utuh,
    # bukan lingkup tersaring, supaya penyaring tahun tidak menyembunyikannya.
    buka = st.session_state.get("buka_doc")
    if buka is not None:
        r_buka = df[df["doc_id"] == buka]
        if not r_buka.empty:
            r = r_buka.iloc[0]
            judul = tampil(r.get("nomor_tampil"), f"Dokumen {r['doc_id']}")
            asal = st.session_state.get("asal_drill")
            asal = asal if asal in HALAMAN else "Risalah Putusan"
            st.subheader("Risalah Putusan")
            st.html(f'<div class="jejak">{asal}<i>›</i>'
                    f'Putusan <b>{judul}</b></div>')
            if st.button(f"Kembali ke {asal}", icon=":material/arrow_back:"):
                st.session_state.pop("buka_doc", None)
                st.session_state["nav_tujuan"] = st.session_state.pop(
                    "asal_drill", None) or "Risalah Putusan"
                st.rerun()
            tampil_detail(r)
            return
        st.session_state.pop("buka_doc", None)

    kiri, kanan = st.columns([3, 2])
    with kanan:
        panel = st.popover("Saring dan cari", width="stretch")

    with panel:
        st.caption("Lima jalur penyaringan dapat digunakan sekaligus dan saling "
                   "mempersempit. Kolom yang tidak diperlukan dapat "
                   "dikosongkan.")
        q_nomor = st.text_input("Nomor putusan",
                                placeholder="misalnya 30938 atau PUT-000123")
        q_wp = st.text_input("Nama wajib pajak", placeholder="misalnya PT")
        q_hakim = st.text_input("Hakim pemutus",
                                placeholder="misalnya Dian Dahtiar")
        q_unit = st.text_input("Unit penerbit",
                               placeholder="misalnya Setiabudi atau KPU")
        q_isi = st.text_input(
            "Kata di dalam isi putusan", key="q_isi",
            placeholder='pajak masukan, atau "nilai pabean" OR royalti',
            help="Pencarian menjangkau seluruh isi dokumen. Tanda kutip untuk "
                 "frasa persis, kata OR dan NOT untuk menggabungkan.")

        # Penyaring terstruktur berdampingan dengan pencarian teks. Pencari
        # perkara serupa berpikir dalam gabungan: putusan yang memuat kata
        # faktur pajak, jenisnya banding PPN, amarnya dikabulkan. Tanpa
        # gabungan ini, hasil pencarian teks harus disisir manual satu satu.
        st.caption("Persempit lagi menurut hasil dan jenisnya.")
        kol_s = st.columns(3)
        q_amar = kol_s[0].selectbox(
            "Amar putusan",
            ["Semua"] + sorted(v for v in d["amar_label"].dropna().unique()
                               if v != "Tidak dikenali"),
            key="q_amar")
        _kode_sering = (d["kode_jenis_pajak"].dropna().astype(str)
                        .value_counts().head(15).index.tolist())
        q_jp = kol_s[1].selectbox(
            "Jenis pajak",
            ["Semua"] + [label_kode(k, kode_peta) for k in _kode_sering],
            key="q_jp")
        q_perkara = kol_s[2].selectbox(
            "Jenis perkara", ["Semua", "Banding", "Gugatan"],
            key="q_perkara")

    aktif = [(n, v.strip()) for n, v in (
        ("Nomor", q_nomor), ("Wajib pajak", q_wp), ("Hakim", q_hakim),
        ("Unit", q_unit), ("Isi", q_isi)) if v and v.strip()]
    aktif += [(n, v) for n, v in (
        ("Amar", q_amar), ("Jenis pajak", q_jp), ("Perkara", q_perkara))
        if v != "Semua"]
    if aktif:
        st.html('<div class="saring">' + "".join(
            f'<span class="chip"><b>{n}</b> {v[:28]}</span>'
            for n, v in aktif) + "</div>")

    h = d.copy()
    if q_nomor.strip():
        h = h[h["nomor_tampil"].fillna("").str.contains(
                  q_nomor.strip(), case=False, regex=False)
              | h["nomor_sengketa"].fillna("").str.contains(
                  q_nomor.strip(), case=False, regex=False)]
    if q_wp.strip():
        h = h[h["nama_pemohon"].fillna("").str.contains(
            q_wp.strip(), case=False, regex=False)]
    if q_hakim.strip():
        gab = (h["hakim_ketua"].fillna("") + "|"
               + h["hakim_anggota"].fillna("") + "|" + h["panitera"].fillna(""))
        h = h[gab.str.contains(q_hakim.strip(), case=False, regex=False)]
    if q_unit.strip():
        h = h[h["unit_penerbit"].fillna("").str.contains(
            q_unit.strip(), case=False, regex=False)]
    if q_amar != "Semua":
        h = h[h["amar_label"] == q_amar]
    if q_jp != "Semua":
        h = h[h["kode_jenis_pajak"].astype(str) == q_jp.split(" · ")[0]]
    if q_perkara != "Semua":
        h = h[h["jenis_perkara"] == q_perkara.lower()]

    cuplikan = {}
    if q_isi.strip():
        try:
            fts = cari_teks(q_isi.strip(), 800)
            h = h[h["doc_id"].isin(fts["doc_id"])]
            cuplikan = dict(zip(fts["doc_id"], fts["cuplikan"]))
        except Exception as exc:
            st.error(f"Indeks pencarian belum dibangun atau kueri tidak sah. "
                     f"Jalankan setpp_parse.py fts. ({exc})")

    if h.empty:
        st.warning("Tidak terdapat putusan yang cocok. Kriteria pencarian dapat diperlonggar atau penyaring "
            "dikosongkan.")
        return

    st.html('<div class="tingkat">Tahap 1 · Pengelompokan</div>')
    PETA_DIM = {"Jenis pajak": "kode_jenis_pajak", "Amar putusan": "amar_label",
                "Instansi terbanding": "instansi_terbanding_label",
                "Jenis perkara": "jenis_perkara_label",
                "Tahun putusan": "tahun_putusan", "Majelis": "kode_majelis",
                "Jenis koreksi": "jenis_koreksi"}
    dim_nama = st.radio("Dasar pengelompokan", list(PETA_DIM), horizontal=True,
                        label_visibility="collapsed")
    dim = PETA_DIM[dim_nama]

    if dim == "jenis_koreksi":
        sumber = (h[["doc_id", "jenis_koreksi"]].dropna()
                  .assign(nilai=lambda x: x["jenis_koreksi"].str.split("|"))
                  .explode("nilai"))
        sumber["nilai"] = sumber["nilai"].map(lambda x: LABEL_KOREKSI.get(x, x))
    else:
        sumber = h[["doc_id", dim]].rename(columns={dim: "nilai"}).dropna()
        if dim == "kode_jenis_pajak":
            sumber["nilai"] = sumber["nilai"].astype(str).map(
                lambda k: label_kode(k, kode_peta))
        elif dim == "tahun_putusan":
            sumber["nilai"] = sumber["nilai"].map(tampil_tahun)

    kel = (sumber.groupby("nilai")["doc_id"].nunique()
           .sort_values(ascending=False)
           .rename_axis(dim_nama).reset_index(name="Putusan"))
    if kel.empty:
        belum_ada(f"Ruas {dim_nama.lower()} belum terisi pada putusan terpilih.")
        return

    # Kelompok beranggota kurang dari lima digabungkan menjadi Lainnya.
    # Pengelompokan menurut majelis misalnya menghasilkan lima puluhan
    # kelompok berisi dua tiga putusan, dan deretan batang sependek itu tidak
    # menolong siapa pun. Gabungannya tidak dapat dimasuki, karena isinya
    # memang campuran.
    LAINNYA = "Lainnya, kelompok kecil"
    kel_penuh = kel.copy()
    kel_penuh["Bagian"] = (100 * kel_penuh["Putusan"] / len(h)).round(1)
    kecil = kel[kel["Putusan"] < 5]
    if len(kecil) >= 3:
        kel = kel[kel["Putusan"] >= 5].copy()
        kel.loc[len(kel)] = {dim_nama: LAINNYA,
                             "Putusan": int(kecil["Putusan"].sum())}
        kel = kel.sort_values("Putusan", ascending=False).reset_index(
            drop=True)
    kel["Bagian"] = (100 * kel["Putusan"] / len(h)).round(1)

    pot = kel.head(14)
    # Panel tabel memuat rincian penuh sebelum penggabungan, supaya kelompok
    # kecil yang dilipat tetap dapat diperiksa satu per satu.
    ev = bagan(batang_peringkat(pot, dim_nama, "Putusan",
                                f"Sebaran menurut {dim_nama.lower()}"),
               max(260, 34 * len(pot) + 120), kel_penuh,
               "Pilih salah satu batang untuk menampilkan rincian "
               "kelompoknya.",
               kunci=f"kel_{dim}")

    nilai_kel = titik_terpilih(ev)
    if nilai_kel is None:
        belum_ada(f"{len(h):,} putusan terbagi ke dalam {len(kel)} kelompok "
                f"menurut {dim_nama.lower()}. Pilih salah satu batang untuk menampilkan rinciannya.")
        return
    if nilai_kel == LAINNYA:
        belum_ada("Kelompok gabungan ini berisi campuran kelompok kecil dan "
                "tidak dapat dimasuki. Rinciannya tersedia pada panel tabel "
                "di "
                "bawah bagan, atau populasinya dipersempit melalui panel "
                "penyaringan.")
        return
    if len(kel) > 14 and nilai_kel not in set(pot[dim_nama]):
        belum_ada("Kelompok itu di luar empat belas terbesar. Populasi perlu dipersempit terlebih dahulu melalui panel "
            "penyaringan.")
        return

    hk = h[h["doc_id"].isin(set(sumber[sumber["nilai"] == nilai_kel]["doc_id"]))]
    hk = hk.sort_values("tahun_putusan", ascending=False, na_position="last")

    st.html(f'<div class="jejak">Dalam lingkup <b>{len(h):,}</b><i>›</i>'
            f'{dim_nama} <b>{nilai_kel}</b><i>›</i><b>{len(hk):,}</b> '
            'putusan</div>')
    st.html('<div class="tingkat">Tahap 2 · Daftar Putusan</div>')
    st.caption("Pilih salah satu baris untuk menampilkan isi putusannya.")

    # Sumbernya dipotong dulu, sepuluh baris per halaman, supaya nomor baris
    # pilihan langsung mengacu pada potongan yang sedang tampil.
    hk, nav2 = potong_halaman(
        hk, f"l2_{abs(hash((dim, nilai_kel))) & 0xffffff}")
    ringkas = pd.DataFrame({
        "Nomor putusan": hk["nomor_tampil"],
        "Tanggal putusan": [tampil_tanggal(u, tampil_tahun(t)) for u, t in
                            zip(hk["tanggal_ucap"], hk["tahun_putusan"])],
        "Pemohon": hk["nama_pemohon"].fillna("-"),
        "Amar": hk["amar_label"],
        "Hakim ketua": hk["hakim_ketua"].fillna("-")})
    pilih2 = st.dataframe(
        ringkas, width="stretch", hide_index=True, on_select="rerun",
        selection_mode="single-row", key=f"list_{dim}_{nilai_kel}",
        column_config={
            "Nomor putusan": st.column_config.TextColumn(width="medium"),
            "Tanggal putusan": st.column_config.TextColumn(
                width="small", alignment="center"),
            "Pemohon": st.column_config.TextColumn(width="medium"),
            "Amar": st.column_config.TextColumn(width="small"),
            "Hakim ketua": st.column_config.TextColumn(width="medium")})
    gambar_nav(nav2)

    baris2 = pilih2.selection.rows if pilih2 and pilih2.selection else []
    if not baris2:
        return
    r = hk.iloc[baris2[0]]

    judul = tampil(r.get("nomor_tampil"), f"Dokumen {r['doc_id']}")
    st.html(f'<div class="jejak">{dim_nama} <b>{nilai_kel}</b><i>›</i>'
            f'Putusan <b>{judul}</b></div>')
    tombol_kembali(f"list_{dim}_{nilai_kel}", "Kembali ke daftar putusan")
    st.html('<div class="tingkat">Tahap 3 · Isi Putusan</div>')
    tampil_detail(r, cuplikan, q_isi)


# ---------------------------------------------------------------------------
# 3. Pola putusan sejenis
# ---------------------------------------------------------------------------

def hal_belajar() -> None:
    st.caption(
        "Pilih ciri perkara, dan halaman menunjukkan rekam jejaknya: "
        "bagaimana perkara serupa diputus, argumen apa yang menyertai "
        "yang menang, dan kesalahan formal apa yang membuat perkara "
        "gugur. Semua angka adalah catatan masa lalu, bukan ramalan atas "
        "perkara Anda.")

    kode_ada = sorted(d["kode_jenis_pajak"].dropna().astype(str).unique())
    kor_ada = sorted({LABEL_KOREKSI.get(x, x)
                      for v in d["jenis_koreksi"].dropna()
                      for x in str(v).split("|")})
    ket_ada = sorted(d["jenis_ketetapan"].dropna().unique())

    k1, k2, k3 = st.columns(3)
    p_kode = k1.selectbox("Jenis pajak", ["Semua"] + kode_ada,
                          format_func=lambda k: k if k == "Semua"
                          else label_kode(k, kode_peta))
    p_kor = k2.selectbox("Jenis koreksi", ["Semua"] + kor_ada)
    p_ket = k3.selectbox("Jenis ketetapan", ["Semua"] + list(ket_ada))

    s = d.copy()
    if p_kode != "Semua":
        s = s[s["kode_jenis_pajak"].astype(str) == p_kode]
    if p_kor != "Semua":
        balik = {v: k for k, v in LABEL_KOREKSI.items()}
        kunci_kor = balik.get(p_kor, p_kor)
        s = s[s["jenis_koreksi"].fillna("").str.contains(kunci_kor,
                                                         regex=False)]
    if p_ket != "Semua":
        s = s[s["jenis_ketetapan"] == p_ket]

    ss = beramar(s)
    if len(ss) < 10:
        st.warning(
            f"Hanya {len(ss)} putusan serupa yang beramar pada pilihan ini. "
            "Terlalu sedikit untuk dibaca sebagai pola. Salah satu pilihan "
            "dapat diperlonggar, atau penelaahan ditunda "
            "sampai cakupan data bertambah.")
        return

    n_menang = int(ss["amar"].isin(AMAR_MENANG).sum())
    bawah, atas = selang_wilson(n_menang, len(ss))
    n_formal = int((s["amar"] == "tidak_dapat_diterima").sum())

    k = st.columns(3)
    k[0].html(TV.kartu("Perkara serupa", f"{len(ss):,}",
                       "putusan beramar pada pilihan ini"))
    k[1].html(TV.kartu("Dikabulkan secara historis",
                       f"{100 * n_menang / len(ss):.0f} %",
                       f"rentang wajar {bawah:.0f} sampai {atas:.0f} persen"))
    k[2].html(TV.kartu("Gugur karena formal", f"{n_formal:,}",
                       "tidak diperiksa sampai pokok sengketa"))

    t = (ss["amar_label"].value_counts()
         .rename_axis("Amar").reset_index(name="Putusan"))
    t["Ket"] = [f"{n:,} ({100 * n / len(ss):.0f}%)" for n in t["Putusan"]]
    bagan(batang_peringkat(t, "Amar", "Putusan",
                           "Bagaimana perkara serupa diputus", "Ket"),
          max(240, 42 * len(t) + 110))

    st.html('<div class="tingkat">Argumen Hukum pada Putusan yang Dikabulkan</div>')
    dh = muat_dasar_hukum()
    menang_id = set(ss[ss["amar"].isin(AMAR_MENANG)]["doc_id"])
    dh = dh[dh["doc_id"].isin(menang_id)]
    if dh.empty:
        belum_ada("Belum terdapat rujukan dasar hukum pada kelompok ini.")
    else:
        r = (dh.groupby("rujukan", observed=True)["doc_id"].nunique()
             .sort_values(ascending=False).head(8)
             .rename_axis("Rujukan").reset_index(name="Putusan"))
        bagan(batang_peringkat(r, "Rujukan", "Putusan",
                               "Pasal yang paling sering menyertai putusan "
                               "yang dikabulkan"),
              max(240, 36 * len(r) + 110), None,
              "Hubungan yang tersaji berupa kemunculan bersama, bukan sebab "
              "akibat. Pasal ini yang paling "
              "sering dirujuk pada perkara serupa yang dikabulkan, dan layak "
              "dipelajari ketika menyusun argumen.")

    j = jeda_hari(s)
    if len(j) >= 10:
        st.html('<div class="tingkat">Lama Proses Penyelesaian</div>')
        st.markdown(
            f"Pada perkara serupa yang tanggalnya terbaca ({len(j):,} "
            f"putusan), jeda dari putusan diambil sampai diucapkan median "
            f"**{j.median():.0f} hari**, dan sepersepuluh terlama menunggu "
            f"lebih dari **{j.quantile(0.9):.0f} hari**.")

    st.html('<div class="tingkat">Daftar Putusan Terkait</div>')
    daftar = ss.sort_values("tahun_putusan", ascending=False).head(30)
    daftar, nav_baca = potong_halaman(daftar, "belajar_terkait")
    pilih_baca = st.dataframe(
        pd.DataFrame({
            "Nomor putusan": daftar["nomor_tampil"]
            .fillna("tidak dikenali"),
            "Tanggal putusan": [
                tampil_tanggal(u, tampil_tahun(t)) for u, t in
                zip(daftar["tanggal_ucap"], daftar["tahun_putusan"])],
            "Amar": daftar["amar_label"],
            "Pengenal berkas": daftar["doc_id"].astype(str)}),
        width="stretch", hide_index=True, on_select="rerun",
        selection_mode="single-row", key="belajar_baca",
        column_config={
            "Tanggal putusan": st.column_config.TextColumn(
                alignment="center"),
            "Pengenal berkas": st.column_config.TextColumn(
                alignment="center")})
    gambar_nav(nav_baca)
    st.caption("Tiga puluh terbaru. Pilih salah satu baris untuk menampilkan "
                                    "isi putusannya pada halaman Risalah "
                                    "Putusan. Pengenal berkas "
               "adalah nomor arsip pada peladen Sekretariat, kunci untuk "
               "menelusuri sampai berkas aslinya.")
    b = pilih_baca.selection.rows if pilih_baca and pilih_baca.selection else []
    if b:
        buka_putusan(daftar.iloc[b[0]]["doc_id"], "belajar_baca")


# ---------------------------------------------------------------------------
# Pilihan upaya hukum, untuk wajib pajak
# ---------------------------------------------------------------------------

def hal_jalur() -> None:
    st.caption(
        "Bekal menentukan jalur sebelum perkara didaftarkan: peluang "
        "tiap jalur menurut putusan yang sudah ada, tenggat yang "
        "mengikat, dan risiko yang jarang disadari. Semua angka adalah "
        "catatan masa lalu, bukan nasihat hukum atas perkara tertentu.")

    rs = resmi_lingkup()
    if rs.empty:
        belum_ada("Halaman ini membutuhkan daftar resmi. Jalankan "
                "setpp_resmi.py impor terlebih dahulu.")
        return

    rs = saring_tahun(rs, "tahun_ucap", "tahun_jalur")
    if rs.empty:
        belum_ada("Tidak terdapat putusan pada rentang tahun tersebut.")
        return

    # Proksi jalur pada daftar resmi: baris berjenis pajak Gugatan Pajak
    # adalah perkara gugatan, sisanya perkara banding.
    rr = rs.assign(jalur=rs["jenis_pajak"].map(
        lambda v: "Gugatan" if v == "Gugatan Pajak" else "Banding"))
    rr["menang"] = rr["amar"].isin(AMAR_MENANG)
    b = rr[rr["jalur"] == "Banding"]
    g = rr[rr["jalur"] == "Gugatan"]

    k = st.columns(3)
    k[0].html(TV.kartu("Banding dikabulkan",
                       f"{100 * int(b['menang'].sum()) / max(1, len(b)):.1f}"
                       " %", f"dari {len(b):,} putusan banding resmi"))
    k[1].html(TV.kartu("Gugatan dikabulkan",
                       f"{100 * int(g['menang'].sum()) / max(1, len(g)):.1f}"
                       " %", f"dari {len(g):,} putusan gugatan resmi"))
    n_add = int((rs["amar"] == "menambah").sum())
    k[2].html(TV.kartu("Penambahan Nilai Putusan", f"{n_add:,}",
                       "putusan menambah pajak yang harus dibayar, 2021 "
                       "sampai 2025"))

    baris = []
    for nama, grp in (("Banding", b), ("Gugatan", g)):
        n = max(1, len(grp))
        baris += [
            {"Jalur": nama, "Amar": "Dikabulkan",
             "Bagian": 100 * int(grp["menang"].sum()) / n},
            {"Jalur": nama, "Amar": "Ditolak",
             "Bagian": 100 * int((grp["amar"] == "tolak").sum()) / n},
            {"Jalur": nama, "Amar": "Tidak dapat diterima",
             "Bagian": 100 * int((grp["amar"]
                                  == "tidak_dapat_diterima").sum()) / n}]
    tj = pd.DataFrame(baris)
    tj["Ket"] = tj["Bagian"].map(lambda v: f"{v:.1f}%")
    fig = px.bar(tj, x="Jalur", y="Bagian", color="Amar", barmode="group",
                 text="Ket", title="Hasil Putusan menurut jalur, data resmi")
    fig.update_xaxes(showgrid=False, title="")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     ticksuffix="%", range=[0, 100], title="")
    # Legenda diletakkan mendatar di bawah bagan. Di sudut kanan atas,
    # keterangan terpanjang tersundul keluar dari kartu dan terpotong.
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=-0.08,
                    xanchor="left", x=0),
        margin=dict(b=70))
    bagan(fig, 380, None,
          "Banding mempersoalkan materi ketetapan, sedangkan gugatan "
           "mempersoalkan keabsahan penetapan beserta prosedurnya. Perbedaan "
           "peluangnya sangat tajam: dua dari "
          "tiga banding dikabulkan, gugatan sebaliknya lebih sering ditolak "
          "atau gugur di aspek formal tanpa pernah diperiksa pokoknya.")

    st.html(TV.catatan_siap(
        "Pemilihan jalur perkara dan ketaatan pada tenggat waktu.",
        "Surat ketetapan pajak dan keputusan keberatan dilawan melalui jalur "
        "banding. Surat tagihan, tindakan penagihan, dan cacat prosedur "
        "penerbitan dilawan melalui jalur gugatan. Perkara yang diajukan "
        "melalui jalur yang keliru atau melampaui "
            "tenggat waktu berakhir dengan amar Tidak dapat diterima tanpa "
            "pemeriksaan pokok sengketa. Tenggat banding tiga bulan sejak "
        "keputusan diterima; tenggat gugatan jauh lebih pendek, empat belas "
        "hari untuk penagihan dan tiga puluh hari untuk keputusan lainnya."))

    st.html('<div class="tingkat">Risiko yang jarang disadari: pajak dapat '
            'bertambah</div>')
    ra = (rs[rs["amar"] == "menambah"].groupby("tahun_ucap").size()
          .rename_axis("Tahun").reset_index(name="Putusan"))
    if not ra.empty:
        fig = garis_waktu(ra, "Tahun", "Putusan",
                          "Putusan menambah pajak menurut tahun",
                          teks="Putusan")
        bagan(fig, 280, None,
              "Pengadilan berwenang menetapkan pajak lebih besar daripada "
              "ketetapan yang dilawan, dan penggunaan kewenangan tersebut "
                                       "menunjukkan kecenderungan naik. "
                                       "Jumlahnya kecil, namun maknanya "
                                       "penting. Mengajukan perkara "
            "bukan tanpa risiko, terutama apabila pembukuan memuat persoalan "
            "lain yang turut terungkap dalam persidangan.")

    st.html('<div class="tingkat">Lama menunggu pengucapan, dari arsip '
            'risalah</div>')
    baris = []
    for label_j, kunci_j in (("Banding", "banding"), ("Gugatan", "gugatan")):
        j = jeda_hari(d[d["jenis_perkara"] == kunci_j])
        if len(j) >= 10:
            baris.append({
                "Jalur": label_j,
                "Putusan bertanggal": len(j),
                "Median hari": int(j.median()),
                "Sepersepuluh terlama mulai": int(j.quantile(0.9))})
    if baris:
        tabel_bernavigasi(pd.DataFrame(baris), "wp_berulang",
                      kolom_persen=("Dikabulkan",))
        st.caption(
            "Jeda dari putusan diambil di musyawarah sampai diucapkan di "
            "sidang terbuka, dihitung dari arsip risalah yang tanggalnya "
            "terbaca. Perencanaan arus kas sebaiknya menggunakan angka "
                      "median, dengan memperhitungkan kemungkinan skenario "
                      "terlama.")
    else:
        st.caption("Putusan bertanggal lengkap pada lingkup ini belum cukup "
                   "untuk membandingkan lama proses per jalur.")


# ---------------------------------------------------------------------------
# 4. Konsistensi putusan
# ---------------------------------------------------------------------------

def hal_konsistensi() -> None:
    st.caption(
        "Perkara yang sejenis semestinya diputus serupa, siapa pun yang "
        "memutus. Halaman ini memeriksanya dari tiga sisi: antar kelompok "
        "perkara, antar hakim, dan antar majelis.")

    t1, t2 = st.tabs(["Perkara dan hakim", "Antar majelis"])
    with t1:
        _konsistensi_perkara()
    with t2:
        _konsistensi_majelis()


def _konsistensi_majelis() -> None:
    """
    Apakah perkara sejenis diputus serupa oleh majelis yang berbeda.

    Ini pertanyaan paling sensitif sekaligus paling penting menjelang
    peralihan ke Mahkamah Agung: keadilan menuntut hasil perkara tidak
    bergantung pada majelis mana yang kebagian memeriksanya. Kode majelis
    terisi 95 persen tetapi belum pernah dipakai untuk pertanyaan ini.

    Penyajiannya dijaga dua hal. Pertama, perbandingan hanya dilakukan di
    dalam kelompok perkara yang sama, karena majelis memang mengampu jenis
    perkara berbeda dan membandingkan lintas jenis berarti membandingkan
    apel dengan jeruk. Kedua, tiap angka disertai selang keyakinan, supaya
    majelis berperkara sedikit tidak dihakimi oleh angka kecil.
    """
    dd = beramar(d).dropna(subset=["kode_majelis", "kode_jenis_pajak"]).copy()
    dd["menang"] = dd["amar"].isin(AMAR_MENANG)
    if dd.empty:
        belum_ada("Belum terdapat putusan bermajelis pada lingkup ini.")
        return

    # Kelompok pembanding: jenis pajak berputusan terbanyak.
    urut = (dd.groupby("kode_jenis_pajak")["doc_id"].nunique()
            .sort_values(ascending=False))
    pilihan = [label_kode(k, kode_peta) for k in urut.head(12).index]
    pilih = st.selectbox(
        "Kelompok perkara yang dibandingkan", pilihan, key="maj_kelompok",
        help="Perbandingan hanya sah di dalam kelompok perkara yang sama.")
    kode = pilih.split(" · ")[0]
    grup = dd[dd["kode_jenis_pajak"].astype(str) == kode]

    g = (grup.groupby("kode_majelis")
         .agg(Putusan=("menang", "size"), menang=("menang", "sum"))
         .reset_index().rename(columns={"kode_majelis": "Majelis"}))
    g = g[g["Putusan"] >= 20].copy()
    if len(g) < 2:
        belum_ada("Belum terdapat dua majelis dengan minimal dua puluh "
                "putusan pada kelompok ini.")
        return
    g["Dikabulkan"] = (100 * g["menang"] / g["Putusan"]).round(1)
    batas = [selang_wilson(int(m), int(n))
             for m, n in zip(g["menang"], g["Putusan"])]
    g["Batas bawah"] = [round(b[0], 1) for b in batas]
    g["Batas atas"] = [round(b[1], 1) for b in batas]
    g = g.sort_values("Dikabulkan", ascending=False)

    tinggi, rendah = g.iloc[0], g.iloc[-1]
    rentang = tinggi["Dikabulkan"] - rendah["Dikabulkan"]
    terpisah = rendah["Batas atas"] < tinggi["Batas bawah"]
    k = st.columns(3)
    k[0].html(TV.kartu("Majelis dibandingkan", f"{len(g):,}",
                       f"masing masing minimal 20 putusan {pilih}"))
    k[1].html(TV.kartu("Rentang antar majelis", f"{rentang:.0f} poin",
                       f"dari {rendah['Dikabulkan']:.0f} sampai "
                       f"{tinggi['Dikabulkan']:.0f} persen dikabulkan"))
    k[2].html(TV.kartu(
        "Kesimpulannya",
        "berbeda nyata" if terpisah else "belum dapat disimpulkan",
        "selang keyakinan ujung atas dan bawah "
        + ("tidak bersinggungan" if terpisah else "masih bersinggungan")))

    st.markdown(
        "Tiap batang adalah satu majelis, dan panjangnya adalah persentase "
        f"perkara {pilih} yang dikabulkan pada majelis itu. Garis melintang "
        "di ujung batang adalah rentang ketidakpastiannya.\n\n"
        "Cara membacanya hati hati: **dua majelis baru boleh disebut "
        "berbeda bila rentang keduanya tidak bersinggungan.** Dan kalaupun "
        "berbeda nyata, itu belum tentu berarti ada yang keliru; komposisi "
        "perkara di dalam satu jenis pajak pun dapat berbeda antar majelis. "
        "Yang pasti layak ditelaah adalah majelis yang berbeda jauh dari "
        "seluruh rekannya secara terus menerus.")

    u = g.sort_values("Dikabulkan").reset_index(drop=True)
    fig = go.Figure(go.Bar(
        x=u["Dikabulkan"], y=u["Majelis"], orientation="h",
        marker_color=P["seri"][0],
        error_x=dict(type="data", symmetric=False,
                     array=(u["Batas atas"] - u["Dikabulkan"]).tolist(),
                     arrayminus=(u["Dikabulkan"] - u["Batas bawah"]).tolist(),
                     color=P["tinta_2"], thickness=1.2, width=5),
        hovertemplate="<b>%{y}</b><br>%{x:.1f} persen dikabulkan"
                      "<extra></extra>"))
    tepi = float(u["Batas atas"].max())
    for _, r in u.iterrows():
        fig.add_annotation(
            x=tepi + 3, y=r["Majelis"], xanchor="left", showarrow=False,
            text=f"{r['Dikabulkan']:.1f}%  (n={int(r['Putusan']):,})",
            font=dict(size=12, color=P["tinta"]))
    fig.update_layout(title=f"Tingkat dikabulkan per majelis, {pilih}")
    fig.update_xaxes(title="", showticklabels=False, showgrid=False,
                     zeroline=False, range=[0, tepi + 30])
    fig.update_yaxes(title="")
    bagan(fig, max(280, 34 * len(u) + 120), None,
          "Majelis dengan batang terpendek dan terpanjang itulah yang "
          "paling layak dibaca putusannya berdampingan: perbedaan "
          "penafsiran yang melatarinya adalah bahan pedoman yang paling "
          "konkret.")

    tabel_bernavigasi(
        g[["Majelis", "Putusan", "Dikabulkan", "Batas bawah", "Batas atas"]],
        "maj_tabel",
        kolom_persen=("Dikabulkan", "Batas bawah", "Batas atas"))


def _konsistensi_perkara() -> None:
    st.html('<div class="tingkat">Keseragaman Antar Kelompok Perkara</div>')
    k = ledak_koreksi(beramar(d))
    dom = []
    for (kode, kor), grp in k.groupby(["kode_jenis_pajak", "Jenis koreksi"]):
        cnt = grp.groupby("amar")["doc_id"].nunique()
        n = int(cnt.sum())
        if n < 15:
            continue
        amar_dom = cnt.idxmax()
        dom.append({
            "Kelompok": f"{label_kode(kode, kode_peta)} · {kor}",
            "Putusan": n,
            "Amar dominan": LABEL_AMAR.get(amar_dom, amar_dom),
            "Keseragaman": round(100 * int(cnt.max()) / n, 1)})
    if not dom:
        belum_ada("Belum terdapat kelompok dengan sedikitnya lima belas putusan.")
        return
    t = pd.DataFrame(dom).sort_values("Keseragaman")

    _rendah, _tinggi = t.iloc[0], t.iloc[-1]
    st.markdown(
        "**Keseragaman** adalah persentase amar yang paling sering muncul "
        "dalam satu kelompok. Seratus persen berarti semua perkara di "
        "kelompok itu berakhir sama. Sekitar sepertiga berarti putusannya "
        "terbelah ke tiga arah.\n\n"
        f"Contohnya, kelompok {_tinggi['Kelompok']} mencapai "
        f"{_tinggi['Keseragaman']:.0f} persen dari "
        f"{int(_tinggi['Putusan']):,} putusan. Hampir semuanya berakhir "
        f"{str(_tinggi['Amar dominan']).lower()}, sehingga hasilnya sudah "
        "bisa diperkirakan sejak awal.\n\n"
        f"Sebaliknya kelompok {_rendah['Kelompok']} hanya "
        f"{_rendah['Keseragaman']:.0f} persen dari "
        f"{int(_rendah['Putusan']):,} putusan. Perkara yang jenis pajak dan "
        "jenis koreksinya sama persis bisa berakhir dikabulkan, ditolak, "
        "atau tidak dapat diterima. Kelompok seperti inilah yang perlu "
        "didahulukan pembenahan aturannya, karena wajib pajak maupun fiskus "
        "sama-sama tidak bisa memperkirakan hasilnya.")

    c1, c2 = st.columns(2)
    with c1:
        pecah = t.head(7).copy()
        # Keterangan cukup persentasenya. Kartu ini hanya separuh lebar
        # halaman, dan menambahkan jumlah putusan di ujung batang membuat
        # tulisannya tersundul keluar kartu. Jumlahnya tetap ada pada tabel
        # di bawah bagan.
        pecah["Ket"] = [f"{v:.0f}%" for v in pecah["Keseragaman"]]
        fig = batang_peringkat(pecah, "Kelompok", "Keseragaman",
                               "Paling bervariasi", "Ket")
        fig.update_xaxes(ticksuffix="%", range=[0, 118], dtick=20)
        bagan(fig, max(260, 44 * len(pecah) + 110), None,
              "Amar dominan di bawah lima puluh persen berarti perkara "
              "sejenis diputus berbeda-beda arah.")
    with c2:
        seragam = t.tail(7).copy()
        seragam["Ket"] = [f"{v:.0f}%" for v in seragam["Keseragaman"]]
        fig = batang_peringkat(seragam, "Kelompok", "Keseragaman",
                               "Paling seragam", "Ket")
        fig.update_xaxes(ticksuffix="%", range=[0, 118], dtick=20)
        bagan(fig, max(260, 44 * len(seragam) + 110))

    with st.expander("Seluruh kelompok sebagai tabel"):
        tabel_bernavigasi(t.sort_values("Keseragaman"), "kelompok_norma",
                          kolom_persen=("Keseragaman",))

    st.html('<div class="tingkat">Konsistensi Putusan Antar Hakim Ketua</div>')
    dd = beramar(d)
    dd = dd[dd["hakim_ketua"].notna() & dd["kode_jenis_pajak"].notna()].copy()
    if len(dd):
        kunci_f, nama_tampil = bakukan_hakim(dd["hakim_ketua"])
        dd["hakim_ketua"] = kunci_f.map(nama_tampil)
        dd = dd[dd["hakim_ketua"].notna()]
    if len(dd) < 100:
        belum_ada("Belum cukup putusan berhakim untuk analisis ini.")
    else:
        dd["menang"] = dd["amar"].isin(AMAR_MENANG)
        laju_kel = dd.groupby("kode_jenis_pajak")["menang"].mean()
        dd["harapan"] = dd["kode_jenis_pajak"].map(laju_kel)
        h = (dd.groupby("hakim_ketua")
             .agg(n=("menang", "size"), aktual=("menang", "mean"),
                  harapan=("harapan", "mean")).reset_index())
        h = h[h["n"] >= 20].copy()
        if h.empty:
            belum_ada("Belum terdapat hakim ketua dengan dua puluh putusan beramar.")
        else:
            h["Dikabulkan"] = (100 * h["aktual"]).round(1)
            h["Harapan"] = (100 * h["harapan"]).round(1)
            h["Selisih"] = (h["Dikabulkan"] - h["Harapan"]).round(1)
            # Urutan tabel mengikuti besar simpangan tanpa memandang arahnya,
            # dari yang polanya paling sejalan dengan rerata sampai yang
            # paling menyimpang. Mengurutkan menurut selisih bertanda
            # menempatkan dua ujung yang sama sama menyimpang pada dua tepi
            # tabel, sehingga pembaca kehilangan urutan konsistensinya.
            h["Simpangan"] = h["Selisih"].abs().round(1)
            h = (h.rename(columns={"hakim_ketua": "Hakim ketua",
                                   "n": "Putusan"})
                 [["Hakim ketua", "Putusan", "Dikabulkan", "Harapan",
                   "Selisih", "Simpangan"]]
                 .sort_values("Simpangan").reset_index(drop=True))

            # Contoh diambil dari data yang sedang tampil, bukan angka
            # karangan, supaya penjelasannya selalu cocok dengan tabelnya.
            paling = h.iloc[-1]
            arah = ("lebih sering" if paling["Selisih"] > 0
                    else "lebih jarang")
            st.markdown(
                "Kolom **Dikabulkan** adalah tingkat pengabulan yang "
                "sebenarnya terjadi pada perkara yang ditangani hakim "
                "tersebut. Kolom **Harapan** adalah tingkat pengabulan yang "
                "wajar apabila perkara dengan campuran jenis pajak yang sama "
                "ditangani oleh rerata hakim lain. **Selisih** keduanya "
                "menunjukkan arah penyimpangan, sedangkan **Simpangan** "
                "adalah besarnya tanpa memandang arah, dan menjadi dasar "
                "urutan tabel.\n\n"
                f"Sebagai contoh, {paling['Hakim ketua']} memutus "
                f"{int(paling['Putusan']):,} perkara dengan tingkat "
                f"pengabulan {paling['Dikabulkan']:.1f} persen, sementara "
                f"nilai harapan bagi campuran perkara yang ditanganinya "
                f"{paling['Harapan']:.1f} persen. Selisihnya "
                f"{paling['Selisih']:+.1f} poin, yang berarti beliau {arah} "
                "mengabulkan permohonan dibandingkan rerata rekan pada "
                "perkara sejenis.\n\n"
                "**Simpangan mendekati nol** berarti pola putusannya sejalan "
                "dengan rerata rekan pada jenis perkara yang sama, dan "
                "itulah yang dimaksud konsisten. **Selisih positif besar** "
                "berarti hakim tersebut jauh lebih sering mengabulkan "
                "daripada rerata rekan, sedangkan **selisih negatif besar** "
                "berarti jauh lebih jarang. Keduanya sama-sama layak "
                "ditelaah, karena keduanya menandakan perkara sejenis "
                "berpeluang berakhir berbeda bergantung pada majelis yang "
                "menanganinya.\n\n"
                "Tabel diurutkan dari hakim yang polanya paling sejalan "
                "dengan rerata sampai yang paling menyimpang.")

            tabel_bernavigasi(
                h, "simpangan_hakim",
                kolom_persen=("Dikabulkan", "Harapan", "Selisih",
                              "Simpangan"))
            st.caption(
                "Penyesuaian baru memperhitungkan campuran jenis pajak, "
                "belum tahun perkara dan jenis perkara, sehingga simpangan "
                "kecil belum bermakna. Simpangan puluhan poin pada puluhan "
                "putusan layak ditindaklanjuti sebagai bahan diskusi "
                "konsistensi. Sajian ini merupakan bahan pembelajaran, bukan "
                "pemeringkatan hakim, dan sebaiknya beredar terbatas.")

    st.html(TV.catatan_siap(
        "Implikasi kebijakan dari halaman ini.",
        "Kelompok paling bervariasi adalah daftar prioritas pembenahan "
        "norma, "
        "melalui surat edaran, pedoman internal, atau usulan peraturan "
        "pelaksana. Penanganan sebaiknya dimulai dari kelompok dengan jumlah "
        "perkara terbesar, "
        "karena pada kelompok itulah ketidakpastian hukum menimbulkan biaya "
        "terbesar."))


# ---------------------------------------------------------------------------
# 5. Sengketa berulang
# ---------------------------------------------------------------------------

def hal_berulang() -> None:
    st.caption(
        "Wajib pajak yang bersengketa berulang kali dengan pokok serupa "
        "menandakan persoalan yang tidak selesai di tingkat keberatan lalu "
        "membebani pengadilan berulang-ulang.")

    n_samar = int((d["nama_disamarkan"] == 1).sum())
    dn = d[(d["nama_disamarkan"] == 0) & d["nama_pemohon_norm"].notna()]
    if dn.empty:
        belum_ada("Belum terdapat nama pemohon yang terbaca pada lingkup ini.")
        return
    st.html(TV.catatan_siap(
        "Cakupan analisis pada halaman ini.",
        f"Sebanyak {n_samar:,} putusan menggunakan nama samaran era lama seperti "
        "XXX dan AAA, sebagaimana dilakukan Sekretariat pada risalah lama, "
        "dan dikeluarkan dari analisis ini karena tidak dapat dikenali "
        f"sebagai entitas. Analisis berjalan atas {len(dn):,} putusan yang "
        "namanya terbaca utuh."))

    vc = dn["nama_pemohon_norm"].value_counts()
    ulang_pangsa = 100 * int(vc[vc >= 2].sum()) / len(dn)
    k = st.columns(3)
    k[0].html(TV.kartu("Dari WP berulang", f"{ulang_pangsa:.0f} %",
                       "putusan berasal dari WP yang bersengketa lebih dari "
                       "sekali"))
    k[1].html(TV.kartu("WP dengan 3 sengketa atau lebih",
                       f"{int((vc >= 3).sum()):,}", "entitas"))
    k[2].html(TV.kartu("Sengketa terbanyak satu WP", f"{int(vc.max()):,}",
                       "putusan"))

    dd = beramar(dn)
    dd = dd.assign(menang=dd["amar"].isin(AMAR_MENANG))

    # Hanya yang benar benar berulang pada lingkup terpilih. Penyaring tahun
    # dapat memangkas sengketa seorang WP hingga tersisa satu, dan WP
    # bersengketa tunggal tidak pantas tampil di halaman berjudul berulang.
    vc2 = vc[vc >= 2]
    if vc2.empty:
        belum_ada("Tidak terdapat wajib pajak dengan dua sengketa atau lebih pada "
                "lingkup ini. Penyaring tahun pada bilah samping dapat "
                "diperlonggar.")
        return

    t1, t2 = st.tabs(["Peringkat wajib pajak", "Peringatan dini"])
    with t1:
        _ulang_peringkat(dn, dd, vc2)
    with t2:
        _ulang_dini(dn, dd, vc2)


def _ulang_peringkat(dn: pd.DataFrame, dd: pd.DataFrame,
                     vc2: pd.Series) -> None:
    # Kunci drill adalah bentuk baku nama, sejajar baris tabel lewat urutan,
    # bukan lewat potongan nama tampilan. Dua varian penulisan yang bentuk
    # bakunya berbeda dapat menghasilkan tampilan terpotong yang sama, dan
    # kunci tampilan akan menabrakkan keduanya.
    baris = []
    urutan: list[str] = []
    for nama, n in vc2.head(15).items():
        grp = dn[dn["nama_pemohon_norm"] == nama]
        ga = dd[dd["nama_pemohon_norm"] == nama]
        kor = (grp["jenis_koreksi"].dropna().str.split("|").explode()
               .map(lambda x: LABEL_KOREKSI.get(x, x)).value_counts())
        urutan.append(nama)
        baris.append({
            "Wajib pajak": str(grp["nama_pemohon"].iloc[0])[:40],
            "Sengketa": int(n),
            "Rentang tahun": f"{tampil_tahun(grp['tahun_putusan'].min())}"
                             f" sampai "
                             f"{tampil_tahun(grp['tahun_putusan'].max())}",
            "Pokok terbanyak": kor.index[0] if len(kor) else "-",
            "Dikabulkan": round(100 * ga["menang"].mean(), 2)
            if len(ga) else 0.0})
    st.html('<div class="tingkat">Lima Belas Wajib Pajak Teratas</div>')
    st.caption("Pilih salah satu baris untuk menampilkan daftar sengketa "
                "wajib pajak tersebut.")
    tampil15, nav15 = potong_halaman(pd.DataFrame(baris), "wp_teratas_nav")
    pilih15 = st.dataframe(
        tampil15, width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row", key="wp_teratas",
        column_config={
            "Dikabulkan": st.column_config.NumberColumn(
                format="%.2f %%", alignment="center")})
    gambar_nav(nav15)

    b15 = pilih15.selection.rows if pilih15 and pilih15.selection else []
    if b15:
        # Daftar urutan sejajar dengan bingkai penuh; nomor baris pilihan
        # mengacu pada potongan, jadi digeser sebesar awal halamannya.
        nama = urutan[nav15["hal"] * nav15["per"] + b15[0]]
        target = dn[dn["nama_pemohon_norm"] == nama]
        t = target.sort_values("tahun_putusan", na_position="last")
        st.html(f'<div class="jejak">Wajib pajak '
                f'<b>{str(target["nama_pemohon"].iloc[0])[:40]}</b><i>›</i>'
                f'<b>{len(t):,}</b> sengketa</div>')
        tombol_kembali("wp_teratas", "Kembali ke daftar wajib pajak")
        t, nav_sen = potong_halaman(
            t, f"wpsen_{abs(hash(nama)) & 0xffffff}")
        pilih_sen = st.dataframe(
            pd.DataFrame({
                "Nomor putusan": t["nomor_tampil"]
                .fillna("tidak dikenali"),
                "Tanggal putusan": [
                    tampil_tanggal(u, tampil_tahun(th_)) for u, th_ in
                    zip(t["tanggal_ucap"], t["tahun_putusan"])],
                "Jenis pajak": t["kode_jenis_pajak"].map(
                    lambda k: label_kode(k, kode_peta)),
                "Amar": t["amar_label"]}),
            width="stretch", hide_index=True, on_select="rerun",
            selection_mode="single-row", key=f"wp_{nama}",
            column_config={
                "Tanggal putusan": st.column_config.TextColumn(
                    alignment="center")})
        gambar_nav(nav_sen)
        st.caption("Pilih salah satu baris untuk menampilkan isi putusannya. Perlu diperhatikan apakah pokok sengketa dan hasilnya sama dari "
            "tahun ke tahun. "
                   "Sengketa yang sama diputus sama berulang kali adalah "
                   "pemborosan yang dapat dihentikan melalui pedoman.")
        b = (pilih_sen.selection.rows
             if pilih_sen and pilih_sen.selection else [])
        if b:
            buka_putusan(t.iloc[b[0]]["doc_id"], f"wp_{nama}")

    st.html(TV.catatan_siap(
        "Tindakan yang disarankan dari halaman ini.",
        "Untuk pimpinan, sengketa berulang dengan hasil yang konsisten sama "
        "berpotensi diselesaikan pada tahap keberatan, melalui pedoman atau "
        "kesepakatan penafsiran dengan unit teknis, supaya perkara serupa "
        "tidak terus dikirim ke pengadilan."))


def _ulang_dini(dn: pd.DataFrame, dd: pd.DataFrame, vc2: pd.Series) -> None:
    """
    Wajib pajak yang sengketanya selalu berakhir sama.

    Ini bagian paling langsung berguna dari seluruh halaman. Kalau seorang
    wajib pajak sudah tiga kali bersengketa dan ketiganya berakhir dengan
    amar yang sama, sengketa keempatnya dapat diperkirakan tanpa perlu
    diramal: persoalannya bukan pada perkara yang satu satu, melainkan pada
    penafsiran yang belum disepakati antara unit penerbit dan wajib pajak
    tersebut.

    Yang dihitung di sini bukan peluang menang, melainkan keseragaman hasil
    yang sudah terjadi. Itu sebabnya bagian ini tetap sah disebut analitik,
    bukan peramalan amar.
    """
    if dd.empty:
        belum_ada("Belum terdapat putusan beramar pada lingkup ini.")
        return

    baris = []
    for nama in vc2.index:
        ga = dd[dd["nama_pemohon_norm"] == nama]
        if len(ga) < 2:
            continue
        hitung = ga["amar"].value_counts()
        seragam = 100 * int(hitung.iloc[0]) / len(ga)
        grp = dn[dn["nama_pemohon_norm"] == nama]
        kor = (grp["jenis_koreksi"].dropna().str.split("|").explode()
               .map(lambda x: LABEL_KOREKSI.get(x, x)).value_counts())
        baris.append({
            "Wajib pajak": str(grp["nama_pemohon"].iloc[0])[:38],
            "Sengketa beramar": len(ga),
            "Hasil terbanyak": LABEL_AMAR.get(hitung.index[0], hitung.index[0]),
            "Keseragaman": round(seragam, 1),
            "Pokok terbanyak": kor.index[0] if len(kor) else "-",
            "Rentang tahun": f"{tampil_tahun(grp['tahun_putusan'].min())}"
                             f" sampai "
                             f"{tampil_tahun(grp['tahun_putusan'].max())}"})
    if not baris:
        belum_ada("Belum terdapat wajib pajak dengan dua putusan beramar atau "
                "lebih pada lingkup ini.")
        return

    tb = pd.DataFrame(baris)
    # Yang benar benar dapat ditindaklanjuti adalah yang hasilnya sama sekali
    # tidak pernah berbeda, dan yang perkaranya sudah cukup banyak sehingga
    # keseragaman itu bukan kebetulan dua kali berturut turut.
    pasti = tb[(tb["Keseragaman"] >= 100) & (tb["Sengketa beramar"] >= 3)]
    n_hemat = int((pasti["Sengketa beramar"] - 1).sum()) if len(pasti) else 0

    k = st.columns(3)
    k[0].html(TV.kartu("WP dengan hasil selalu sama", f"{len(pasti):,}",
                       "tiga sengketa atau lebih, amarnya tidak pernah "
                       "berbeda"))
    k[1].html(TV.kartu("Putusan yang sebenarnya dapat dicegah",
                       f"{n_hemat:,}",
                       "sengketa kedua dan seterusnya pada kelompok itu"))
    rerata = tb["Keseragaman"].mean()
    k[2].html(TV.kartu("Keseragaman rata rata", f"{rerata:.0f} %",
                       f"pada {len(tb):,} wajib pajak berulang"))

    st.markdown(
        "Kolom **Keseragaman** adalah bagian putusan seorang wajib pajak "
        "yang amarnya sama. Seratus persen berarti seluruh sengketanya "
        "berakhir dengan amar yang sama persis, tanpa satu pun "
        "pengecualian.\n\n"
        "Contohnya begini. Sebuah perusahaan sudah empat kali bersengketa, "
        "keempatnya mengenai pajak masukan, dan keempatnya dikabulkan "
        "seluruhnya. Keseragamannya seratus persen. Sengketa kelima mengenai "
        "pokok yang sama hampir dapat dipastikan berakhir serupa, sehingga "
        "mengirimkannya ke pengadilan berarti menghabiskan waktu sidang "
        "untuk memperoleh jawaban yang sudah diketahui. **Yang seharusnya "
        "ditangani bukan perkaranya, melainkan penafsiran yang membuat "
        "perkara itu terus terbit.**\n\n"
        f"Pada arsip yang sedang tampil terdapat {len(pasti):,} wajib pajak "
        f"seperti itu, dan {n_hemat:,} putusan pada kelompok tersebut "
        "sebenarnya mengulang jawaban yang sudah ada.")

    tb = tb.sort_values(["Keseragaman", "Sengketa beramar"], ascending=False)
    tabel_bernavigasi(tb, "ulang_dini", kolom_persen=("Keseragaman",))
    st.caption("Diurutkan dari yang hasilnya paling seragam. Baris teratas "
               "adalah calon penyelesaian di tahap keberatan.")

    st.html(TV.catatan_siap(
        "Cara membaca daftar ini tanpa salah kesimpulan.",
        "Keseragaman seratus persen tidak berarti sengketa berikutnya pasti "
        "berakhir sama, karena pokok sengketanya dapat berbeda walaupun "
        "wajib pajaknya sama. Karena itu kolom pokok terbanyak perlu dibaca "
        "bersamaan: yang layak ditindaklanjuti adalah wajib pajak yang "
        "hasilnya seragam sekaligus pokok sengketanya berulang. Daftar ini "
        "juga terbatas pada perkara yang sudah sampai ke pengadilan, "
        "sehingga wajib pajak yang persoalannya selesai di tahap keberatan "
        "memang tidak muncul di sini, dan itu memang sebagaimana mestinya."))


# ---------------------------------------------------------------------------
# 6. Ketetapan dan koreksi
# ---------------------------------------------------------------------------

def hal_ketetapan() -> None:
    st.caption(
        "Melihat sengketa dari sisi penerbit ketetapan: jenis ketetapan "
        "dan koreksi apa yang paling sering gugur di pengadilan. Lima "
        "tab tersusun dari memotret keadaan sampai menunjukkan arah "
        "perbaikannya.")

    t1, t2, t3, t4, t5 = st.tabs([
        "Jenis ketetapan", "Jenis koreksi", "Tren hasil putusan",
        "DJP dan DJBC", "Kegagalan formal"])
    with t1:
        _mutu_jenis_ketetapan()
    with t2:
        _mutu_jenis_koreksi()
    with t3:
        _mutu_arah()
    with t4:
        _mutu_instansi()
    with t5:
        _mutu_formal()


def _mutu_jenis_ketetapan() -> None:
    kj = beramar(d)
    kj = kj[kj["jenis_ketetapan"].notna()].copy()
    kj["menang"] = kj["amar"].isin(AMAR_MENANG)
    if kj.empty:
        belum_ada("Belum terdapat ketetapan yang teridentifikasi jenisnya.")
        return

    g = (kj.groupby("jenis_ketetapan")
         .agg(Putusan=("menang", "size"), menang=("menang", "sum"))
         .reset_index().rename(columns={"jenis_ketetapan": "Jenis ketetapan"}))
    g = g[g["Putusan"] >= 10]
    g["Dikabulkan"] = (100 * g["menang"] / g["Putusan"]).round(1)
    g["Ket"] = [f"{v:.0f}%  (n={n:,})" for v, n in
                zip(g["Dikabulkan"], g["Putusan"])]
    # Contoh dibaca dari data yang sedang tampil, sehingga penjelasannya
    # selalu cocok dengan bagannya walau cakupan arsip bertambah.
    puncak = g.sort_values("Dikabulkan").iloc[-1]
    st.markdown(
        "Bagan ini menjawab satu pertanyaan: **dari ketetapan yang dibawa ke "
        "pengadilan, berapa persen yang akhirnya dikoreksi?** Panjang batang "
        "adalah persentasenya, dan angka dalam kurung adalah jumlah putusan "
        "yang dihitung.\n\n"
        f"Contohnya {puncak['Jenis ketetapan']}, yang mencapai "
        f"{puncak['Dikabulkan']:.0f} persen dari "
        f"{int(puncak['Putusan']):,} putusan. Jadi dari setiap sepuluh "
        f"{puncak['Jenis ketetapan']} yang disengketakan, sekitar "
        f"{puncak['Dikabulkan'] / 10:.0f} dikoreksi pengadilan. Perlu "
        "dicatat, angka ini hanya untuk ketetapan yang disengketakan, bukan "
        "untuk semua ketetapan yang diterbitkan.\n\n"
        "Patokan bacanya lima puluh persen. Di atas angka itu, lebih dari "
        "separuh ketetapan jenis tersebut gagal dipertahankan. Itu petunjuk "
        "bahwa persoalannya ada pada mutu ketetapannya, bukan pada wajib "
        "pajak yang gemar berperkara.")
    fig = batang_peringkat(g, "Jenis ketetapan", "Dikabulkan",
                           "Tingkat dikabulkan menurut jenis ketetapan", "Ket")
    fig.update_xaxes(ticksuffix="%", range=[0, 118], dtick=20)
    bagan(fig, max(240, 44 * len(g) + 110), None,
          "SPTNP dan SPKTNP adalah penetapan kepabeanan, sedangkan SKPKB dan "
          "STP adalah penetapan pajak.")

    unduh_laporan(
        "Mutu Ketetapan menurut Jenis",
        [(str(r["Jenis ketetapan"]), f"{r['Dikabulkan']:.1f} persen",
          f"dikabulkan, dari {int(r['Putusan']):,} putusan")
         for _, r in g.sort_values("Dikabulkan", ascending=False).iterrows()],
        None,
        "Persentase dihitung hanya atas ketetapan yang disengketakan, bukan "
        "atas seluruh ketetapan yang diterbitkan, dan hanya jenis dengan "
        "sedikitnya sepuluh putusan yang disertakan. Arsipnya contoh "
        f"bercakupan {cakupan:.1f} persen, bukan populasi penuh.",
        "mutu_jenis")


def _mutu_jenis_koreksi() -> None:
    kor = ledak_koreksi(beramar(d))
    gk = (kor.groupby("Jenis koreksi")
          .agg(Putusan=("doc_id", "nunique"), menang=("menang", "sum"))
          .reset_index())
    gk = gk[gk["Putusan"] >= 5].copy()
    gk["Tingkat dikabulkan"] = (100 * gk["menang"] / gk["Putusan"]).round(1)
    batas = [selang_wilson(int(m), int(n))
             for m, n in zip(gk["menang"], gk["Putusan"])]
    gk["Batas bawah"] = [round(b[0], 1) for b in batas]
    gk["Batas atas"] = [round(b[1], 1) for b in batas]
    gk["Bobot"] = (gk["Putusan"] * gk["Tingkat dikabulkan"] / 100).round(1)
    gk = gk.drop(columns=["menang"]).sort_values("Bobot", ascending=False)
    teratas = gk.iloc[0]
    st.markdown(
        "Tabel ini menjawab pertanyaan lain: **koreksi jenis apa yang paling "
        "banyak menimbulkan pembatalan?** Persentase saja belum cukup untuk "
        "menentukan prioritas. Koreksi yang hampir selalu batal tetapi hanya "
        "muncul lima kali setahun bukan masalah besar. Karena itu ada kolom "
        "**Bobot**, yaitu jumlah putusan dikalikan persentase dikabulkan. "
        "Bobot menaksir berapa banyak ketetapan yang benar-benar batal.\n\n"
        f"Contohnya koreksi {teratas['Jenis koreksi']}. Koreksi ini muncul "
        f"pada {int(teratas['Putusan']):,} putusan, dan "
        f"{teratas['Tingkat dikabulkan']:.1f} persen di antaranya "
        f"dikabulkan, sehingga bobotnya {teratas['Bobot']:,.0f}. Bacanya: "
        f"sekitar {teratas['Bobot']:,.0f} ketetapan batal karena koreksi "
        "jenis ini. Itu sebabnya ia berada di urutan teratas.\n\n"
        "Kolom **Batas bawah** dan **Batas atas** menunjukkan rentang "
        "ketidakpastian angkanya. Kalau rentang dua jenis koreksi saling "
        "bersinggungan, perbedaan keduanya belum bisa disimpulkan.")
    tabel_bernavigasi(gk, "koreksi_bobot",
                      kolom_persen=("Tingkat dikabulkan", "Batas bawah",
                                    "Batas atas"))
    st.caption("Diurutkan menurut bobot, dari yang paling banyak "
               "menimbulkan pembatalan.")

    # Peta empat kuadran. Prioritas penanganan ditentukan dua hal sekaligus,
    # yaitu seberapa sering koreksi itu muncul dan seberapa sering ia batal.
    # Tabel menyusunnya berurutan, sedangkan peta ini memperlihatkan kedua
    # sumbunya bersamaan sehingga kelompok penanganannya langsung terbaca.
    st.html('<div class="tingkat">Peta Prioritas Penanganan</div>')
    batas_x = float(gk["Putusan"].median())
    # Titik berdesakan di sisi kiri karena sebagian besar jenis koreksi
    # jumlahnya kecil sementara beberapa sangat besar. Sumbu mendatar dibuat
    # berskala lipat agar kerumunan itu merenggang, dan letak tulisan
    # diselang seling atas bawah supaya label yang berdekatan tidak
    # bertumpuk sampai tidak terbaca.
    # Nama koreksi dipendekkan khusus untuk peta ini. Nama penuh sepanjang
    # dua tiga kata membuat label titik yang berdekatan saling menutupi
    # sampai tidak satu pun terbaca, sedangkan pada tabel di atas nama
    # penuhnya tetap tersaji.
    RINGKAS = {"Penyusutan dan amortisasi": "Penyusutan",
               "Harga pokok penjualan": "HPP",
               "Fasilitas dan pembebasan": "Fasilitas",
               "Kompensasi kerugian": "Kompensasi",
               "Hubungan istimewa": "Hub. istimewa",
               "Klasifikasi dan tarif": "Klasifikasi",
               "Sanksi administrasi": "Sanksi",
               "PPh potong pungut": "PPh potput",
               "Peredaran usaha": "Peredaran",
               "Kredit pajak": "Kredit",
               "Pajak masukan": "Pajak masukan",
               "Nilai pabean": "Nilai pabean",
               "Aspek formal": "Formal"}
    q = gk.sort_values("Putusan").reset_index(drop=True)
    # Yang diberi label hanya titik yang menentukan keputusan, yaitu seluruh
    # penghuni kuadran prioritas di kanan atas, ditambah titik tertinggi dan
    # terendah sebagai penanda ujung. Titik lain yang berdesakan dibiarkan
    # tanpa tulisan, karena label yang saling menutupi tidak terbaca dan
    # nama lengkapnya sudah tersaji pada tabel di atas serta pada keterangan
    # yang muncul saat titiknya disentuh.
    penting = ((q["Putusan"] >= batas_x) & (q["Tingkat dikabulkan"] >= 50))
    penting.iloc[int(q["Tingkat dikabulkan"].argmax())] = True
    penting.iloc[int(q["Tingkat dikabulkan"].argmin())] = True
    q["Label"] = [RINGKAS.get(v, v) if p else ""
                  for v, p in zip(q["Jenis koreksi"], penting)]
    letak = ["top center" if i % 2 == 0 else "bottom center"
             for i in range(len(q))]
    fig = px.scatter(q, x="Putusan", y="Tingkat dikabulkan",
                     text="Label", log_x=True,
                     hover_name="Jenis koreksi",
                     title="Frekuensi dibandingkan tingkat pembatalan")
    fig.update_traces(mode="markers+text", textposition=letak,
                      textfont=dict(size=10, color=P["tinta_2"]),
                      hovertemplate="<b>%{hovertext}</b><br>%{x:,} putusan"
                                    "<br>%{y:.1f} persen dikabulkan"
                                    "<extra></extra>")
    fig.add_vline(x=batas_x, line_dash="dot", line_color=P["sumbu"])
    fig.add_hline(y=50, line_dash="dot", line_color=P["sumbu"])
    fig.update_xaxes(showgrid=False, title="Jumlah putusan, skala lipat")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     ticksuffix="%", range=[0, 112],
                     title="Tingkat dikabulkan")
    fig.update_layout(margin=dict(t=64, r=40, b=58, l=40))
    for x_, y_, teks_, ax_ in (
            (0.99, 1.02, "Sering dan sering batal", "right"),
            (0.01, 1.02, "Jarang tetapi sering batal", "left")):
        fig.add_annotation(text=teks_, xref="paper", yref="paper",
                           x=x_, y=y_, showarrow=False, xanchor=ax_,
                           font=dict(size=11, color=P["tinta_2"]))
    bagan(fig, 560, None,
          "Garis mendatar berada pada lima puluh persen, garis tegak pada "
          "jumlah putusan pertengahan. Titik di kanan atas adalah koreksi "
          "yang sering dipakai sekaligus sering batal, dan itulah prioritas "
          "pembenahan pedoman pemeriksaan. Titik di kiri atas sering batal "
          "tetapi jarang dipakai, sehingga cukup ditangani melalui penegasan "
          "teknis. Titik di bawah garis mendatar berarti koreksinya lebih "
          "sering bertahan di pengadilan.")

    st.html(TV.catatan_siap(
        "Tindakan yang disarankan dari halaman ini.",
        "Penelaahan sebaiknya dimulai dari koreksi berbobot terbesar. "
         "Sepuluh putusan teratasnya dapat dibaca melalui halaman Risalah "
         "Putusan untuk mengenali dasar pembatalannya, yang kemudian "
         "dituangkan ke dalam pedoman pemeriksaan atau penelaahan keberatan. "
         "Koreksi "
        "yang jarang tetapi hampir selalu batal cukup ditangani melalui "
        "penegasan teknis, koreksi yang sering dan sering batal perlu "
        "pembenahan pedoman."))


def _deret_tahunan(dd: pd.DataFrame) -> pd.DataFrame:
    """Tingkat dikabulkan per tahun beserta selang keyakinannya."""
    t = (dd.dropna(subset=["tahun_putusan"])
         .assign(menang=lambda x: x["amar"].isin(AMAR_MENANG))
         .groupby("tahun_putusan")
         .agg(Putusan=("menang", "size"), menang=("menang", "sum"))
         .reset_index())
    # Tahun berisi sangat sedikit putusan menghasilkan persentase yang
    # bergoyang liar, misalnya satu dari dua putusan terbaca lima puluh
    # persen. Ambangnya dipasang supaya garisnya menggambarkan mutu
    # ketetapan, bukan menggambarkan kelangkaan datanya.
    t = t[t["Putusan"] >= 30].copy()
    if t.empty:
        return t
    t["Tahun"] = t["tahun_putusan"].astype(int)
    t["Dikabulkan"] = (100 * t["menang"] / t["Putusan"]).round(1)
    batas = [selang_wilson(int(m), int(n))
             for m, n in zip(t["menang"], t["Putusan"])]
    t["Batas bawah"] = [round(b[0], 1) for b in batas]
    t["Batas atas"] = [round(b[1], 1) for b in batas]
    return t.sort_values("Tahun")


def _mutu_arah() -> None:
    """
    Apakah mutu ketetapan membaik atau memburuk dari tahun ke tahun.

    Halaman lain menjawab keadaan sekarang. Pertanyaan ini berbeda dan lebih
    penting bagi pimpinan: pembenahan yang sudah berjalan bertahun tahun itu
    berhasil atau tidak. Tanpa deret waktu, angka enam puluh satu persen
    hanya potret, dan potret tidak dapat dipakai menilai kebijakan.
    """
    t = _deret_tahunan(beramar(d))
    if len(t) < 3:
        belum_ada("Belum terdapat cukup tahun bermuatan putusan memadai untuk "
                "menggambarkan arah pergerakannya.")
        return

    awal, akhir = t.iloc[0], t.iloc[-1]
    n_awal = t.head(3)
    n_akhir = t.tail(3)
    r_awal = 100 * n_awal["menang"].sum() / n_awal["Putusan"].sum()
    r_akhir = 100 * n_akhir["menang"].sum() / n_akhir["Putusan"].sum()
    selisih = r_akhir - r_awal

    k = st.columns(3)
    k[0].html(TV.kartu(
        f"Tiga tahun pertama, {int(n_awal['Tahun'].min())} sampai "
        f"{int(n_awal['Tahun'].max())}", f"{r_awal:.1f} %",
        f"dari {int(n_awal['Putusan'].sum()):,} putusan beramar"))
    k[1].html(TV.kartu(
        f"Tiga tahun terakhir, {int(n_akhir['Tahun'].min())} sampai "
        f"{int(n_akhir['Tahun'].max())}", f"{r_akhir:.1f} %",
        f"dari {int(n_akhir['Putusan'].sum()):,} putusan beramar"))
    k[2].html(TV.kartu(
        "Perubahan",
        f"{selisih:+.1f} poin",
        "naik berarti ketetapan makin sering batal"
        if selisih > 0 else "turun berarti ketetapan makin tahan uji"))

    st.markdown(
        "Bagan ini menjawab pertanyaan yang tidak dapat dijawab satu angka "
        "saja: **mutu ketetapan membaik atau memburuk?** Garis tengah adalah "
        "persentase ketetapan yang dikoreksi pengadilan pada tahun itu, dan "
        "pita di sekelilingnya adalah rentang ketidakpastiannya.\n\n"
        "Pita itu penting. Tahun yang putusannya sedikit menghasilkan pita "
        "lebar, dan pada tahun seperti itu naik turunnya garis belum tentu "
        "berarti apa apa. Aturan bacanya sederhana: **kalau pita dua tahun "
        "masih saling bersinggungan, perbedaan keduanya belum dapat "
        "disimpulkan.** Yang layak disebut perubahan adalah pergerakan yang "
        "pitanya sudah terpisah.\n\n"
        f"Pada arsip yang sedang tampil, tahun {int(awal['Tahun'])} berada "
        f"di {awal['Dikabulkan']:.1f} persen dan tahun "
        f"{int(akhir['Tahun'])} di {akhir['Dikabulkan']:.1f} persen. "
        f"Dibandingkan per tiga tahun, perubahannya {selisih:+.1f} poin.")

    # Warna tiap deret disebut tegas, tidak diserahkan pada putaran warna
    # bawaan. Kalau diserahkan, kedua garis batas ikut memperoleh warna
    # penuh dan pita ketidakpastiannya menjadi lebih mencolok daripada garis
    # utamanya, sehingga yang pertama tertangkap mata justru bagian yang
    # paling tidak penting.
    warna = P["seri"][0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t["Tahun"], y=t["Batas atas"], mode="lines",
        line=dict(width=0, color="rgba(0,0,0,0)"),
        showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=t["Tahun"], y=t["Batas bawah"], mode="lines",
        name="Rentang ketidakpastian",
        line=dict(width=0, color="rgba(0,0,0,0)"), fill="tonexty",
        fillcolor=TV.lembut(warna, 0.30 if GELAP else 0.18),
        hovertemplate="%{x}: batas bawah %{y:.1f} persen<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=t["Tahun"], y=t["Dikabulkan"], mode="lines+markers",
        name="Tingkat dikabulkan",
        line=dict(color=warna, width=2.4),
        marker=dict(color=warna, size=7),
        hovertemplate="%{x}: %{y:.1f} persen dikabulkan<extra></extra>"))
    fig.add_hline(y=50, line_dash="dot", line_color=P["sumbu"])
    fig.update_layout(
        title="Tren hasil putusan menurut tahun putusan",
        legend=dict(orientation="h", yanchor="top", y=-0.14,
                    xanchor="left", x=0),
        margin=dict(b=70))
    fig.update_xaxes(showgrid=False, dtick=1, title="")
    # Judul sumbu tegak sengaja dikosongkan. Tulisan tegak di sisi kiri
    # terpotong menjadi potongan kata yang tidak berarti ketika kartunya
    # menyempit, sedangkan tanda persen pada tiap angka sudah menyatakan
    # satuannya dan judul bagan sudah menyatakan pokoknya.
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     ticksuffix="%", title="")
    bagan(fig, 420, None,
          "Garis putus putus berada pada lima puluh persen. Di atas garis "
          "itu, lebih dari separuh ketetapan yang disengketakan gagal "
          "dipertahankan pada tahun tersebut.")

    tt = t[["Tahun", "Putusan", "Dikabulkan", "Batas bawah", "Batas atas"]]
    tabel_bernavigasi(tt, "arah_mutu",
                      kolom_persen=("Dikabulkan", "Batas bawah", "Batas atas"))

    st.html(TV.catatan_siap(
        "Cara membaca bagan ini ketika dipakai menilai kebijakan.",
        "Tahun putusan bukan tahun terbitnya ketetapan. Sengketa memerlukan "
        "waktu bertahun tahun sampai diputus, sehingga putusan tahun ini "
        "menilai ketetapan yang terbit beberapa tahun sebelumnya. Perbaikan "
        "yang dijalankan sekarang baru akan terbaca pada bagan ini beberapa "
        "tahun mendatang, dan sebaliknya, penurunan yang terlihat hari ini "
        "berasal dari praktik lama, bukan dari kebijakan yang baru "
        "diberlakukan."))


def _mutu_instansi() -> None:
    """
    Direktorat Jenderal Pajak dibandingkan Direktorat Jenderal Bea dan Cukai.

    Keduanya kerap disebut dalam satu tarikan napas sebagai penerimaan
    negara, padahal ketetapannya berbeda sifat, dasar hukumnya berbeda, dan
    tingkat bertahannya di pengadilan juga berbeda. Menyajikan keduanya
    berdampingan membuat perbedaan itu terbaca, dan yang lebih penting,
    membuat jelas bahwa keduanya memerlukan pembenahan yang berlainan.
    """
    LABEL = {"djp": "Direktorat Jenderal Pajak",
             "djbc": "Direktorat Jenderal Bea dan Cukai",
             "pemda": "Pemerintah daerah"}
    dd = beramar(d).dropna(subset=["instansi_terbanding"]).copy()
    if dd.empty:
        belum_ada("Belum terdapat putusan yang instansi terbandingnya "
                "teridentifikasi.")
        return
    dd["menang"] = dd["amar"].isin(AMAR_MENANG)

    g = (dd.groupby("instansi_terbanding")
         .agg(Putusan=("menang", "size"), menang=("menang", "sum"))
         .reset_index())
    g = g[g["Putusan"] >= 20].copy()
    if g.empty:
        belum_ada("Belum terdapat instansi dengan putusan yang memadai.")
        return
    g["Instansi"] = [LABEL.get(v, v) for v in g["instansi_terbanding"]]
    g["Dikabulkan"] = (100 * g["menang"] / g["Putusan"]).round(1)
    batas = [selang_wilson(int(m), int(n))
             for m, n in zip(g["menang"], g["Putusan"])]
    g["Batas bawah"] = [round(b[0], 1) for b in batas]
    g["Batas atas"] = [round(b[1], 1) for b in batas]
    g = g.sort_values("Putusan", ascending=False)

    kolom = st.columns(len(g))
    for kol, (_, r) in zip(kolom, g.iterrows()):
        kol.html(TV.kartu(
            r["Instansi"], f"{r['Dikabulkan']:.1f} %",
            f"dikabulkan, dari {int(r['Putusan']):,} putusan beramar"))

    utama = g.head(2)
    if len(utama) == 2:
        a, b = utama.iloc[0], utama.iloc[1]
        beda = a["Dikabulkan"] - b["Dikabulkan"]
        # Selisih dinyatakan bermakna hanya bila kedua selang tidak
        # bersinggungan. Tanpa penjaga ini, selisih beberapa poin pada
        # kelompok kecil akan terbaca sebagai perbedaan nyata.
        terpisah = (a["Batas bawah"] > b["Batas atas"]
                    or b["Batas bawah"] > a["Batas atas"])
        st.markdown(
            f"**{a['Instansi']}** dan **{b['Instansi']}** berbeda "
            f"{abs(beda):.1f} poin. "
            + ("Selang keyakinan keduanya tidak bersinggungan, sehingga "
               "perbedaannya dapat dinyatakan nyata, bukan kebetulan "
               "sebaran."
               if terpisah else
               "Namun selang keyakinan keduanya masih bersinggungan, "
               "sehingga perbedaan itu belum dapat dinyatakan nyata.")
            + "\n\nPerbedaan ini bermakna kebijakan. Ketetapan kepabeanan "
            "bertumpu pada nilai pabean dan klasifikasi barang, yang "
            "sengketanya berkisar pada bukti transaksi dan penggolongan. "
            "Ketetapan pajak bertumpu pada koreksi penghasilan dan pajak "
            "masukan, yang sengketanya berkisar pada pembuktian dokumen. "
            "Keduanya tidak dapat dibenahi dengan satu pedoman yang sama.")

    # Datanya diurutkan sekali lalu dipakai berulang. Memanggil pengurutan
    # di dalam tiap ruas bagan pernah membuat panjang deret galat tidak
    # sepadan dengan panjang deret batangnya, dan bagannya gagal digambar.
    u = g.sort_values("Dikabulkan").reset_index(drop=True)
    fig = go.Figure(go.Bar(
        x=u["Dikabulkan"], y=u["Instansi"], orientation="h",
        marker_color=P["seri"][0],
        error_x=dict(type="data", symmetric=False,
                     array=(u["Batas atas"] - u["Dikabulkan"]).tolist(),
                     arrayminus=(u["Dikabulkan"] - u["Batas bawah"]).tolist(),
                     color=P["tinta_2"], thickness=1.2, width=5),
        hovertemplate="<b>%{y}</b><br>%{x:.1f} persen dikabulkan"
                      "<extra></extra>"))
    # Angka tiap batang ditulis sebagai keterangan pada satu garis tegak yang
    # sama, bukan menempel di ujung batangnya.
    #
    # Batang di sini memanjang sampai ujung selang keyakinannya, dan tulisan
    # yang menempel di ujung batang jatuh tepat di tengah garis selang itu,
    # sehingga garisnya menembus angkanya dan keduanya menjadi sulit dibaca.
    # Dengan disejajarkan pada satu garis tegak di kanan seluruh selang,
    # tabrakan itu tidak mungkin terjadi lagi, dan angkanya sekaligus lebih
    # mudah dibandingkan karena berbaris lurus.
    tepi = float(u["Batas atas"].max())
    for _, r in u.iterrows():
        fig.add_annotation(
            x=tepi + 3, y=r["Instansi"], xanchor="left", showarrow=False,
            text=f"{r['Dikabulkan']:.1f}%  (n={int(r['Putusan']):,})",
            font=dict(size=12, color=P["tinta"]))
    fig.update_layout(title="Tingkat dikabulkan menurut instansi")
    fig.update_xaxes(title="", showticklabels=False, showgrid=False,
                     zeroline=False, range=[0, tepi + 32])
    fig.update_yaxes(title="")
    bagan(fig, max(240, 60 * len(g) + 110), None,
          "Garis melintang pada ujung tiap batang adalah selang keyakinan. "
          "Batang yang selangnya saling bersinggungan belum dapat dinyatakan "
          "berbeda satu sama lain.")

    st.html('<div class="tingkat">Tren Hasil Putusan Tiap Instansi</div>')
    fig = go.Figure()
    ada_deret = False
    for kode in g["instansi_terbanding"]:
        t = _deret_tahunan(dd[dd["instansi_terbanding"] == kode])
        if len(t) < 3:
            continue
        ada_deret = True
        fig.add_trace(go.Scatter(
            x=t["Tahun"], y=t["Dikabulkan"], mode="lines+markers",
            name=LABEL.get(kode, kode),
            hovertemplate="%{x}: %{y:.1f} persen<extra></extra>"))
    if ada_deret:
        fig.add_hline(y=50, line_dash="dot", line_color=P["sumbu"])
        fig.update_layout(
            title="Tingkat dikabulkan menurut tahun putusan, tiap instansi",
            legend=dict(orientation="h", yanchor="top", y=-0.14,
                        xanchor="left", x=0),
            margin=dict(b=70))
        fig.update_xaxes(showgrid=False, dtick=1, title="")
        fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                         ticksuffix="%", title="")
        bagan(fig, 400, None,
              "Dua garis yang bergerak berlawanan arah menandakan sebabnya "
              "bukan keadaan umum perekonomian maupun perubahan sikap "
              "pengadilan, melainkan sesuatu di dalam instansinya sendiri.")
    else:
        belum_ada("Belum terdapat cukup tahun bermuatan putusan memadai untuk "
                "menggambarkan arah tiap instansi.")


def _mutu_formal() -> None:
    """
    Perkara yang gugur tanpa pernah diperiksa pokok sengketanya.

    Amar tidak dapat diterima berarti pengadilan tidak pernah sampai menilai
    benar salahnya koreksi, karena perkaranya sudah gugur lebih dulu pada
    syarat formal, misalnya lewat tenggat, salah jalur, atau kuasa tidak
    sah. Bagi kedua pihak ini kerugian murni: wajib pajak menanggung biaya
    tanpa memperoleh pemeriksaan, dan negara menanggung waktu sidang tanpa
    memperoleh putusan yang menyelesaikan pokok sengketanya.

    Angkanya kecil dalam persen, tetapi seluruhnya dapat dicegah, dan itu
    yang membuatnya layak menjadi sudut telaah tersendiri.
    """
    dd = d[d["amar"].notna()].copy()
    if dd.empty:
        belum_ada("Belum terdapat putusan beramar pada lingkup ini.")
        return
    gagal = dd[dd["amar"] == "tidak_dapat_diterima"]
    n, ng = len(dd), len(gagal)
    if ng == 0:
        belum_ada("Tidak terdapat putusan beramar tidak dapat diterima pada "
                "lingkup ini.")
        return

    k = st.columns(3)
    k[0].html(TV.kartu("Gugur sebelum pokok sengketa", f"{ng:,}",
                       f"dari {n:,} putusan beramar"))
    k[1].html(TV.kartu("Persentasenya", f"{100 * ng / n:.1f} %",
                       "seluruhnya dapat dicegah sejak awal"))
    jeda = jeda_hari(gagal)
    k[2].html(TV.kartu(
        "Waktu sidang yang terpakai",
        f"{jeda.median():,.0f} hari" if len(jeda) else "-",
        f"median jeda musyawarah ke pengucapan, {len(jeda):,} putusan"
        if len(jeda) else "tanggalnya belum terbaca"))

    st.markdown(
        "Amar **tidak dapat diterima** berarti pengadilan tidak pernah "
        "sampai menilai benar salahnya koreksi. Perkaranya sudah gugur lebih "
        "dulu pada syarat formal, misalnya diajukan lewat tenggat, ditempuh "
        "melalui jalur yang keliru, surat kuasanya tidak sah, atau berkasnya "
        "kurang.\n\n"
        "Contohnya begini. Wajib pajak menerima ketetapan, tidak setuju, "
        "lalu mengajukan banding pada hari ke seratus sembilan. Tenggat "
        "banding tiga bulan. Perkaranya diterima, diregistrasi, dijadwalkan, "
        "dan disidangkan, tetapi berakhir dengan amar tidak dapat diterima "
        "tanpa satu pun koreksi diperiksa. Biaya sudah keluar dari kedua "
        "sisi, dan pokok sengketanya tetap tidak terselesaikan.\n\n"
        "Itu sebabnya bagian ini disajikan terpisah. Berbeda dari perkara "
        "yang kalah karena koreksinya memang benar, **seluruh perkara di "
        "kelompok ini dapat dicegah**, dan pencegahannya tidak memerlukan "
        "perubahan aturan, cukup pemberitahuan yang jelas kepada wajib pajak "
        "beserta penelitian kelengkapan berkas di tahap pendaftaran.")

    st.html('<div class="tingkat">Tren dari Tahun ke Tahun</div>')
    t = (dd.dropna(subset=["tahun_putusan"])
         .assign(gagal=lambda x: x["amar"] == "tidak_dapat_diterima")
         .groupby("tahun_putusan")
         .agg(Putusan=("gagal", "size"), Gugur=("gagal", "sum"))
         .reset_index())
    t = t[t["Putusan"] >= 30].copy()
    if len(t) >= 3:
        t["Tahun"] = t["tahun_putusan"].astype(int)
        t["Bagian"] = (100 * t["Gugur"] / t["Putusan"]).round(1)
        t = t.sort_values("Tahun")
        puncak = t.loc[t["Bagian"].idxmax()]
        st.markdown(
            "Garis ini menunjukkan berapa persen putusan tiap tahun yang "
            "gugur sebelum pokok sengketanya diperiksa. Tahun tertinggi pada "
            f"arsip yang tampil adalah {int(puncak['Tahun'])}, sebesar "
            f"{puncak['Bagian']:.1f} persen, yaitu "
            f"{int(puncak['Gugur']):,} dari {int(puncak['Putusan']):,} "
            "putusan.")
        fig = garis_waktu(t[["Tahun", "Bagian"]], "Tahun", "Bagian",
                          "Bagian putusan yang gugur sebelum pokok sengketa")
        fig.update_yaxes(ticksuffix="%")
        bagan(fig, 340, None,
              "Garis yang menurun berarti penyaringan di tahap pendaftaran "
              "membaik, atau wajib pajak makin memahami tenggat dan "
              "jalurnya. Garis yang naik menandakan sebaliknya.")

    st.html('<div class="tingkat">Di Mana Kegagalan Formal Terpusat</div>')
    LABEL_INS = {"djp": "Direktorat Jenderal Pajak",
                 "djbc": "Direktorat Jenderal Bea dan Cukai",
                 "pemda": "Pemerintah daerah"}
    LABEL_PERKARA = {"banding": "Banding", "gugatan": "Gugatan", "pk": "Peninjauan kembali"}
    for kolom, label_peta, judul, kunci in (
            ("instansi_terbanding", LABEL_INS, "instansi terbanding", "formal_ins"),
            ("jenis_perkara", LABEL_PERKARA, "jenis perkara", "formal_jns")):
        b = (dd.dropna(subset=[kolom])
             .assign(gagal=lambda x: x["amar"] == "tidak_dapat_diterima")
             .groupby(kolom)
             .agg(Putusan=("gagal", "size"), Gugur=("gagal", "sum"))
             .reset_index())
        b = b[b["Putusan"] >= 30].copy()
        if b.empty:
            continue
        b[judul.capitalize()] = [label_peta.get(v, v) for v in b[kolom]]
        b["Bagian"] = (100 * b["Gugur"] / b["Putusan"]).round(1)
        b = b.drop(columns=[kolom]).sort_values("Bagian", ascending=False)
        b = b[[judul.capitalize(), "Putusan", "Gugur", "Bagian"]]
        tabel_bernavigasi(b, kunci, kolom_persen=("Bagian",))
        st.caption(f"Bagian putusan yang gugur sebelum pokok sengketa, "
                   f"menurut {judul}.")

    st.html(TV.catatan_siap(
        "Tindakan yang disarankan dari bagian ini.",
        "Sepuluh putusan pada kelompok ini dapat dibaca melalui halaman "
        "Risalah Putusan untuk mengenali sebab gugurnya, apakah tenggat, "
        "jalur, kuasa, atau kelengkapan berkas. Sebab yang paling sering "
        "muncul kemudian dituangkan menjadi pemberitahuan baku yang "
        "dilampirkan pada tiap surat ketetapan, memuat tenggat beserta "
        "tanggal jatuh temponya, jalur yang tepat, dan daftar berkas yang "
        "harus dilengkapi. Pencegahan di titik ini jauh lebih murah daripada "
        "menyidangkan perkara yang sudah pasti tidak akan diperiksa."))


# ---------------------------------------------------------------------------
# Dasar hukum yang menentukan, untuk fiskus
# ---------------------------------------------------------------------------

def hal_dasar() -> None:
    st.caption(
        "Pasal yang paling sering dirujuk ketika ketetapan dikoreksi "
        "pengadilan. Bagi penelaah keberatan, pasal pasal inilah yang "
        "paling menentukan arah pembuktian. Yang tersaji adalah "
        "kemunculan bersama, bukan sebab akibat.")

    dh = muat_dasar_hukum()
    dd = beramar(d)
    if dh.empty or dd.empty:
        belum_ada("Belum terdapat rujukan dasar hukum pada lingkup ini.")
        return

    k1, k2 = st.columns(2)
    kode_ada = sorted(dd["kode_jenis_pajak"].dropna().astype(str).unique())
    p_kode = k1.selectbox("Jenis pajak", ["Semua"] + kode_ada,
                          format_func=lambda k: k if k == "Semua"
                          else label_kode(k, kode_peta), key="dh_kode")
    kor_ada = sorted({LABEL_KOREKSI.get(x, x)
                      for v in dd["jenis_koreksi"].dropna()
                      for x in str(v).split("|")})
    p_kor = k2.selectbox("Jenis koreksi", ["Semua"] + kor_ada, key="dh_kor")

    s = dd
    if p_kode != "Semua":
        s = s[s["kode_jenis_pajak"].astype(str) == p_kode]
    if p_kor != "Semua":
        balik = {v: k for k, v in LABEL_KOREKSI.items()}
        s = s[s["jenis_koreksi"].fillna("").str.contains(
            balik.get(p_kor, p_kor), regex=False)]

    menang_id = set(s[s["amar"].isin(AMAR_MENANG)]["doc_id"])
    tolak_id = set(s[s["amar"] == "tolak"]["doc_id"])
    du = dh.rename(columns={"rujukan": "Rujukan"})
    rk = (du[du["doc_id"].isin(menang_id)]
          .groupby("Rujukan", observed=True)["doc_id"].nunique())
    rt = (du[du["doc_id"].isin(tolak_id)]
          .groupby("Rujukan", observed=True)["doc_id"].nunique())
    # Bagian kehadiran tidak bermakna pada populasi yang sangat kecil. Ketika
    # penyaring menyempit sampai tersisa segelintir putusan dikabulkan, tiap
    # pasal yang kebetulan dirujuk satu putusan akan tampil seratus persen,
    # dan seluruh batang menjadi sama panjang tanpa memberi keterangan apa
    # pun. Karena itu populasinya dijaga, dan pasal yang dirujuk kurang dari
    # tiga putusan tidak ikut ditampilkan.
    if len(menang_id) < 10:
        belum_ada(
            f"Hanya {len(menang_id)} putusan dikabulkan pada pilihan ini, "
            "terlalu sedikit untuk membaca pasal mana yang menentukan. "
            "Salah satu pilihan dapat diperlonggar.")
        return
    rk = rk[rk >= 3]
    if rk.empty:
        belum_ada("Belum terdapat pasal yang dirujuk sedikitnya tiga putusan "
                "dikabulkan pada pilihan ini. Salah satu pilihan dapat "
                "diperlonggar.")
        return

    t = (pd.DataFrame({"Dikabulkan merujuk": rk, "Ditolak merujuk": rt})
         .fillna(0).astype(int))
    n_m, n_t = max(1, len(menang_id)), max(1, len(tolak_id))
    t["% putusan dikabulkan"] = (100 * t["Dikabulkan merujuk"] / n_m)
    t["% putusan ditolak"] = (100 * t["Ditolak merujuk"] / n_t)
    t["Selisih poin"] = (t["% putusan dikabulkan"]
                         - t["% putusan ditolak"])
    t = t.sort_values("Dikabulkan merujuk", ascending=False)

    atas = t.head(10).reset_index()
    # Keterangan menyebut kedua sisinya secara utuh. Sebelumnya ditulis
    # "53% lawan 56%", dan kata lawan tidak menerangkan apa yang sedang
    # dibandingkan, sehingga pembaca harus menebak.
    atas["Ket"] = [
        f"{r['% putusan dikabulkan']:.0f}% dikabulkan, "
        f"{r['% putusan ditolak']:.0f}% ditolak"
        for _, r in atas.iterrows()]

    unggul = t.assign(_s=t["Selisih poin"]).sort_values(
        "_s", ascending=False).iloc[0]
    st.markdown(
        "Bagan ini membandingkan **seberapa sering suatu pasal muncul pada "
        "putusan yang dikabulkan dibandingkan pada putusan yang ditolak.** "
        "Panjang batang adalah jumlah putusan dikabulkan yang merujuk pasal "
        "tersebut, sedangkan dua angka di ujungnya adalah bagian "
        "kehadirannya pada masing-masing kelompok.\n\n"
        f"Sebagai contoh, {unggul.name} hadir pada "
        f"{unggul['% putusan dikabulkan']:.0f} persen putusan yang "
        f"dikabulkan, tetapi hanya {unggul['% putusan ditolak']:.0f} "
        "persen putusan yang ditolak. Selisih "
        f"{unggul['Selisih poin']:.0f} poin itulah yang menjadikannya "
        "penanda arah: ketika pasal ini dibahas dalam pertimbangan, "
        "perkaranya cenderung berakhir dikabulkan.\n\n"
        "Pasal yang bagiannya hampir sama pada kedua kelompok, misalnya 50 "
        "persen berbanding 49 persen, tidak membedakan apa pun. Pasal "
        "seperti itu memang selalu dirujuk pada perkara jenis ini, sehingga "
        "kehadirannya tidak memberi petunjuk tentang arah putusannya. Yang "
        "layak ditelaah adalah pasal yang selisihnya besar.")

    bagan(batang_peringkat(atas, "Rujukan", "Dikabulkan merujuk",
                           "Pasal yang paling sering menyertai koreksi "
                           "pengadilan", "Ket"),
          max(300, 36 * len(atas) + 120), None,
          "Hanya pasal yang dirujuk sedikitnya tiga putusan dikabulkan yang "
          "ditampilkan, karena bagian yang dihitung dari satu dua putusan "
          "selalu tampak seratus persen tanpa berarti apa pun. Hubungan yang "
          "tersaji berupa kemunculan bersama, bukan sebab akibat.")

    with st.expander("Dua puluh rujukan teratas sebagai tabel"):
        tabel_bernavigasi(
            t.head(20).reset_index()
            .round({"% putusan dikabulkan": 2, "% putusan ditolak": 2,
                    "Selisih poin": 2}),
            "pasal_atas",
            kolom_persen=("% putusan dikabulkan", "% putusan ditolak",
                          "Selisih poin"))

    st.html(TV.catatan_siap(
        "Tindakan yang disarankan dari halaman ini.",
        "Daftar ini dapat menjadi acuan materi penelaahan keberatan. Koreksi "
        "yang "
        "bersinggungan dengan pasal berselisih besar perlu argumen dan "
        "dokumentasi paling kuat sebelum dipertahankan ke pengadilan, "
        "karena di pasal itulah otoritas paling sering kalah. Sepuluh putusan "
        "teratasnya dapat dibaca melalui halaman "
            "Putusan untuk memahami pola penalarannya."))


# ---------------------------------------------------------------------------
# Peta unit penerbit, untuk fiskus
# ---------------------------------------------------------------------------

# Nama unit hasil penguraian kerap berekor potongan kalimat dokumen, seperti
# "dengan perhitungan" atau "sebagaimana diubah terakhir dengan Keputusan".
# Ekor itu dipangkas untuk tampilan, tanpa mengubah data tersimpan, supaya
# unit yang sama tidak terpecah menjadi beberapa baris.
RE_EKOR_UNIT = re.compile(
    r"\s+(?:dengan\s+perhitungan|dengan\s+perhi\w*|sebagaimana\b|"
    r"berdasarkan\b|sesuai\b|yang\s+diwakili\b|nomor\b|nomer\b|no\.)"
    r".*$", re.IGNORECASE)

# Singkatan baku administrasi perpajakan dan kepabeanan. Nama panjang seperti
# Kantor Pengawasan dan Pelayanan Bea dan Cukai memakan seluruh lebar kartu
# dan label bagan, padahal singkatannya justru lebih dikenal pembacanya.
SINGKAT_UNIT = (
    ("Kantor Pengawasan dan Pelayanan Bea dan Cukai", "KPPBC"),
    ("Kantor Pelayanan Utama Bea dan Cukai", "KPUBC"),
    ("Kantor Pelayanan Pajak Penanaman Modal Asing", "KPP PMA"),
    ("Kantor Pelayanan Pajak", "KPP"),
    ("Kantor Wilayah Direktorat Jenderal Pajak", "Kanwil DJP"),
    ("Kantor Wilayah DJP", "Kanwil DJP"),
    ("Kantor Wilayah", "Kanwil"),
    ("Direktorat Jenderal Bea dan Cukai", "DJBC"),
    ("Direktorat Jenderal Pajak", "DJP"),
)


def rapikan_unit(v) -> str:
    s = " ".join(str(v).split())
    s = RE_EKOR_UNIT.sub("", s).strip(" ,.;:-")
    for panjang, pendek in SINGKAT_UNIT:
        if s.lower().startswith(panjang.lower()):
            s = pendek + s[len(panjang):]
            break
    if len(s) > 46:
        s = s[:46].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return s


def hal_unit() -> None:
    st.caption(
        "Menelaah sengketa menurut unit penerbitnya, yaitu unit mana yang "
         "ketetapannya paling sering disengketakan dan bagaimana hasilnya di "
         "pengadilan. "
        "Sumbernya arsip risalah yang sudah terurai, cakupan "
        f"{cakupan:.1f} persen, sehingga angka per unit adalah taksiran "
        "yang akan bergeser saat arsip bertambah. Selang keyakinan pada "
        "tabel menunjukkan seberapa lebar ketidakpastiannya.")

    du = beramar(d)
    du = du[du["unit_penerbit"].notna()].copy()
    if du.empty:
        belum_ada("Belum terdapat unit penerbit yang terbaca pada lingkup ini.")
        return
    du["unit"] = du["unit_penerbit"].map(rapikan_unit)
    du = du[du["unit"] != ""]
    du["menang"] = du["amar"].isin(AMAR_MENANG)

    inst = st.radio("Instansi", ["Semua", "DJP", "DJBC"], horizontal=True,
                    key="unit_inst")
    if inst != "Semua":
        du = du[du["instansi_terbanding"] == inst.lower()]

    g = (du.groupby("unit")["menang"].agg(["size", "sum"]).reset_index()
         .rename(columns={"unit": "Unit penerbit", "size": "Putusan"}))
    g = g[g["Putusan"] >= 15].copy()
    if g.empty:
        belum_ada("Belum terdapat unit dengan sedikitnya lima belas putusan "
                "beramar pada pilihan ini. Penelaahan dapat ditunda sampai "
                "cakupan arsip bertambah, atau "
            "penyaring diperlonggar.")
        return
    g["Dikabulkan"] = (100 * g["sum"] / g["Putusan"]).round(2)
    batas = [selang_wilson(int(m), int(n))
             for m, n in zip(g["sum"], g["Putusan"])]
    g["Batas bawah"] = [round(b[0], 2) for b in batas]
    g["Batas atas"] = [round(b[1], 2) for b in batas]
    g = g.drop(columns=["sum"])

    k = st.columns(3)
    k[0].html(TV.kartu("Unit terhitung", f"{len(g):,}",
                       "dengan lima belas putusan beramar atau lebih"))
    k[1].html(TV.kartu("Paling banyak dilawan",
                       str(g.sort_values('Putusan').iloc[-1]
                           ['Unit penerbit']),
                       f"{int(g['Putusan'].max()):,} putusan beramar"))
    tertinggi = g.sort_values("Dikabulkan").iloc[-1]
    k[2].html(TV.kartu("Tingkat koreksi tertinggi",
                       f"{tertinggi['Dikabulkan']:.0f} %",
                       f"{tertinggi['Unit penerbit']}, "
                       f"n={int(tertinggi['Putusan'])}"))

    atas = g.sort_values("Putusan", ascending=False).head(12).copy()
    atas["Ket"] = [f"{n:,} · {v:.0f}% dikabulkan" for v, n in
                   zip(atas["Dikabulkan"], atas["Putusan"])]
    bagan(batang_peringkat(atas, "Unit penerbit", "Putusan",
                           "Unit dengan sengketa terbanyak di arsip", "Ket"),
          max(300, 34 * len(atas) + 120), None,
          "Panjang batang adalah banyaknya putusan di arsip, keterangan "
          "menunjukkan berapa persen yang berujung ketetapan dikoreksi. "
          "Jumlah sengketa yang banyak tidak dengan sendirinya menunjukkan "
           "mutu yang rendah, karena unit besar memang lebih sering "
           "disengketakan; yang layak ditelaah adalah tingkat koreksi yang "
           "tinggi "
          "pada jumlah perkara yang besar.")

    st.html('<div class="tingkat">Rekapitulasi Seluruh Unit</div>')
    tabel_bernavigasi(
        g.sort_values(["Dikabulkan", "Putusan"], ascending=False),
        "unit_penerbit",
        kolom_persen=("Dikabulkan", "Batas bawah", "Batas atas"))
    st.caption(
        "Diurutkan dari tingkat koreksi tertinggi. Bila rentang batas bawah "
        "dan atas dua unit saling tumpang tindih, perbedaan keduanya belum "
        "berarti apa apa.")

    st.html(TV.catatan_siap(
        "Tindakan yang disarankan dari halaman ini.",
        "Sajian ini merupakan alat pembinaan, bukan penilaian kinerja. Unit "
        "dengan tingkat koreksi "
        "tinggi pada banyak perkara adalah prioritas telaah: sepuluh "
        "putusannya dapat dibaca melalui halaman Risalah "
            "Putusan untuk mengenali apakah polanya berupa koreksi yang "
            "lemah, penanganan keberatan yang tergesa, atau sengketa berulang "
            "dari wajib pajak yang sama, dan temuannya dibawa ke pembinaan "
            "teknis unit tersebut. Peringkat ini akan bergeser saat arsip "
        "bertambah, sehingga belum layak dikutip sebagai angka final."))


# ---------------------------------------------------------------------------
# 7. Kinerja hakim
# ---------------------------------------------------------------------------

def hal_hakim() -> None:
    st.caption(
        "Rekapitulasi putusan yang telah diucapkan menurut hakim, dipilah "
        "per kategori amar. Susunan majelis hanya termuat pada risalah era "
        "PDF, sehingga yang terhitung adalah putusan yang majelisnya "
        "terbaca. Sajian ini merupakan bahan pembelajaran konsistensi dan "
                  "beban kerja, bukan pemeringkatan hakim perorangan, dan "
                  "sebaiknya beredar terbatas.")

    pr, ph = st.columns([2, 3])
    with pr:
        peran = st.radio("Peran dalam majelis",
                         ["Hakim ketua", "Hakim anggota"], horizontal=True)
    with ph:
        # Penyaring tahun tersendiri, supaya susunan majelis dapat dilihat
        # per periode tanpa mengubah lingkup halaman lain.
        th_ada = sorted(int(x) for x in d["tahun_putusan"].dropna().unique())
        rentang_th = None
        if len(th_ada) > 1:
            rentang_th = st.slider("Tahun putusan", min(th_ada), max(th_ada),
                                   (min(th_ada), max(th_ada)),
                                   key="tahun_hakim")
    dh = d
    if rentang_th:
        dh = d[d["tahun_putusan"].between(rentang_th[0], rentang_th[1])]
        if dh.empty:
            belum_ada("Tidak terdapat putusan pada rentang tahun tersebut.")
            return

    if peran == "Hakim ketua":
        s = dh[dh["hakim_ketua"].notna()].copy()
        s["hakim"] = s["hakim_ketua"]
    else:
        s = dh[dh["hakim_anggota"].notna()].copy()
        s = s.assign(hakim=s["hakim_anggota"].str.split("|")).explode("hakim")
        s["hakim"] = s["hakim"].str.strip()
        # Pemecahan anggota menggandakan label indeks, satu per anggota,
        # dan crosstab menolak indeks kembar. Indeksnya ditata ulang.
        s = s[s["hakim"] != ""].reset_index(drop=True)

    # Varian penulisan nama yang sama disatukan sebelum dihitung. Tanpa ini
    # satu hakim tampil sebagai beberapa baris hanya karena beda tanda baca,
    # beda gelar, atau salah baca satu huruf. Jumlah baris yang dibersihkan
    # dihitung di sini dan dilaporkan terbuka di bawah tabel.
    mentah = s["hakim"].astype(str)
    kunci_mentah = mentah.map(kunci_hakim)
    inti = kunci_mentah.str.replace(" ", "", regex=False)
    n_gelar = int((kunci_mentah == "").sum())
    n_pendek = int(((kunci_mentah != "") & (inti.str.len() <= 3)).sum())
    n_varian = int(mentah[inti.str.len() > 3].nunique())
    kunci_f, nama_tampil = bakukan_hakim(mentah)
    s["hakim"] = kunci_f.map(nama_tampil)
    s = s[s["hakim"].notna()]
    if s.empty:
        belum_ada("Belum terdapat putusan yang susunan majelisnya terbaca pada "
                "lingkup ini.")
        return

    per_hakim = s.groupby("hakim")["doc_id"].nunique()
    k = st.columns(3)
    k[0].html(TV.kartu("Hakim terhitung", f"{per_hakim.size:,}",
                       f"pada peran {peran.lower()}"))
    k[1].html(TV.kartu("Putusan bermajelis", f"{s['doc_id'].nunique():,}",
                       f"dari {len(dh):,} putusan dalam lingkup"))
    k[2].html(TV.kartu("Median putusan per hakim",
                       f"{per_hakim.median():.0f}", "putusan diucapkan"))

    atas = (per_hakim.sort_values(ascending=False).head(15)
            .rename_axis("Hakim").reset_index(name="Putusan"))
    bagan(batang_peringkat(atas, "Hakim", "Putusan",
                           "Lima belas hakim dengan putusan terbanyak"),
          max(280, 34 * len(atas) + 120), None,
          "Jumlah putusan mencerminkan sebaran perkara pada arsip yang "
          f"sudah terkumpul, dengan cakupan {cakupan:.1f} persen), bukan beban "
          "kerja sesungguhnya.")

    st.html('<div class="tingkat">Rincian menurut Kategori Amar</div>')
    URUT_AMAR = [LABEL_AMAR[a] for a in
                 ("kabul_seluruhnya", "kabul_sebagian", "tolak",
                  "tidak_dapat_diterima", "cabut", "batal", "gugur",
                  "pembetulan")]
    s["Amar"] = s["amar"].map(LABEL_AMAR).fillna("Tidak terbaca")
    tab = pd.crosstab(s["hakim"], s["Amar"])
    for c in URUT_AMAR + ["Tidak terbaca"]:
        if c not in tab.columns:
            tab[c] = 0
    tab = tab[URUT_AMAR + ["Tidak terbaca"]]
    tab.insert(0, "Putusan diucapkan", tab.sum(axis=1))

    # Kolom amar diberi nama pendek supaya seluruh tabel muat dalam satu
    # layar. Makna lengkapnya sudah dinyatakan judul bagian, yaitu rincian
    # menurut kategori amar, sehingga tidak perlu diulang pada tiap kepala
    # kolom. Kategori yang seluruhnya nol tidak ditampilkan.
    PENDEK = {LABEL_AMAR["kabul_seluruhnya"]: "Kabul penuh",
              LABEL_AMAR["kabul_sebagian"]: "Kabul sebagian",
              LABEL_AMAR["tolak"]: "Tolak",
              LABEL_AMAR["tidak_dapat_diterima"]: "Tidak diterima",
              LABEL_AMAR["cabut"]: "Cabut",
              LABEL_AMAR["batal"]: "Batal",
              LABEL_AMAR["gugur"]: "Gugur",
              LABEL_AMAR["pembetulan"]: "Pembetulan"}

    # Bagian dikabulkan dihitung atas putusan beramar substantif saja,
    # yaitu tanpa pembetulan kesalahan tulis dan tanpa amar yang tidak terbaca.
    n_substantif = (tab["Putusan diucapkan"] - tab["Tidak terbaca"]
                    - tab[LABEL_AMAR["pembetulan"]])
    tab["Dikabulkan"] = (
        100 * (tab[LABEL_AMAR["kabul_seluruhnya"]]
               + tab[LABEL_AMAR["kabul_sebagian"]])
        / n_substantif.clip(lower=1)).round(2)

    kosong = [c for c in URUT_AMAR + ["Tidak terbaca"] if int(tab[c].sum()) == 0]
    tab = tab.drop(columns=kosong)
    tab = tab.rename(columns=PENDEK)

    # Diurutkan dari hakim yang paling sering mengabulkan, yaitu yang paling
    # sering memenangkan wajib pajak, sesuai pertanyaan yang paling lazim
    # diajukan pembaca halaman ini.
    tab = (tab.sort_values("Dikabulkan", ascending=False)
           .rename_axis("Hakim").reset_index())

    # Ambang jumlah putusan diambil dari rata-rata putusan per hakim, bukan
    # dari angka yang ditetapkan sendiri, sehingga ikut menyesuaikan ketika
    # arsip bertambah. Tanpa ambang, urutan teratas dipenuhi hakim dengan
    # satu dua putusan yang otomatis tercatat seratus persen, benar secara
    # hitungan tetapi menyesatkan sebagai bacaan.
    ambang = max(2, int(round(tab["Putusan diucapkan"].mean())))
    n_semua = len(tab)
    semua = st.checkbox(
        f"Tampilkan seluruh hakim, termasuk yang putusannya kurang dari "
        f"{ambang}", value=False, key="hakim_semua")
    if not semua:
        tab = tab[tab["Putusan diucapkan"] >= ambang]
    if tab.empty:
        belum_ada("Belum terdapat hakim yang memenuhi ambang tersebut.")
        return

    # Rentang tahun bertugas menurut arsip: tahun putusan tertua sampai
    # termuda yang memuat nama hakim itu.
    rentang = (s.dropna(subset=["tahun_putusan"])
               .groupby("hakim")["tahun_putusan"].agg(["min", "max"]))
    per = {h: (f"{int(a)}" if int(a) == int(b) else f"{int(a)}-{int(b)}")
           for h, (a, b) in rentang.iterrows()}
    tab.insert(1, "Periode putusan", tab["Hakim"].map(per).fillna("-"))

    tabel_bernavigasi(tab, "profil_hakim",
                      kolom_persen=("Dikabulkan",), kelas="rata")
    st.caption(
        f"Menampilkan {len(tab):,} dari {n_semua:,} hakim, yaitu yang "
        f"putusannya sedikitnya {ambang}. Ambang itu adalah rata-rata jumlah "
        "putusan per hakim pada lingkup ini, sehingga ikut menyesuaikan saat "
        "arsip bertambah. Hakim dengan putusan sangat sedikit dikeluarkan "
        "dari pemeringkatan karena persentasenya otomatis menjadi nol atau "
        "seratus persen, dan angka seperti itu belum menggambarkan pola. "
        "Seluruh hakim tetap dapat ditampilkan melalui kotak centang di "
        "atas.\n\n"
        "Diurutkan dari hakim yang paling sering mengabulkan permohonan, "
        "yaitu yang paling sering memenangkan wajib pajak. Nama kolom "
        "dipendekkan agar seluruh kategori muat dalam satu layar, dan "
        "kategori yang seluruhnya nol tidak ditampilkan. Varian penulisan "
        "nama yang sama, termasuk perbedaan gelar, perbedaan tanda baca, dan "
        "salah baca satu huruf, "
        "disatukan ke penulisan yang paling sering digunakan, dan potongan "
        "yang hanya berisi gelar dikeluarkan. Bagian dikabulkan dihitung "
        "atas putusan beramar substantif, tanpa pembetulan kesalahan tulis "
        "dan tanpa amar yang tidak terbaca. Hakim dengan jumlah putusan "
        "sedikit wajar memperlihatkan bagian "
            "ekstrem, yaitu nol atau seratus persen, sehingga belum dapat "
            "dibaca sebagai pola. Untuk perbandingan yang memperhitungkan "
            "campuran "
        "jenis perkara tiap hakim, lihat bagian Pola antar hakim ketua di "
        "halaman Konsistensi Putusan Hakim.")

    n_buang = n_gelar + n_pendek
    if n_buang or n_varian:
        st.html(TV.catatan_siap(
            "Catatan pembersihan data.",
            f"Sebanyak {n_buang:,} baris nama dikeluarkan dari tampilan dan "
            f"seluruh hitungan: {n_gelar:,} hanya memuat gelar tanpa nama, "
            f"dan {n_pendek:,} berupa potongan yang tidak sahih seperti Jja. "
            f"Sisanya {n_varian:,} varian penulisan disatukan menjadi "
            f"{s['hakim'].nunique():,} nama hakim baku."))


# ---------------------------------------------------------------------------
# 8. Kinerja proses
# ---------------------------------------------------------------------------

def hal_kinerja() -> None:
    st.caption(
        "Lama penyelesaian perkara dan titik proses yang paling lama "
        "tertahan. Temuan utamanya terletak pada jeda yang jarang dilaporkan, "
        "yaitu antara "
        "putusan diambil di musyawarah dan diucapkan di sidang terbuka.")

    j = jeda_hari(d)
    if len(j) < 20:
        belum_ada("Belum cukup putusan yang kedua tanggalnya terbaca.")
        return

    t1, t2 = st.tabs(["Keadaan durasi", "Perkiraan menurut ciri perkara"])
    with t1:
        _durasi_keadaan(j)
    with t2:
        _durasi_perkiraan()


def _durasi_perkiraan() -> None:
    """
    Rentang lama proses yang wajar menurut ciri perkara yang dipilih.

    Ini dimensi prediktif yang sah tanpa meramal amar: yang diperkirakan
    adalah durasi, dari sebaran nyata perkara sejenis yang sudah selesai.
    Bagi wajib pajak angka ini langsung terpakai untuk perencanaan arus
    kas, karena uang yang disengketakan tertahan selama proses berjalan.
    """
    dd = d.dropna(subset=["tanggal_ucap", "tanggal_musyawarah"]).copy()
    u = pd.to_datetime(dd["tanggal_ucap"], errors="coerce")
    m = pd.to_datetime(dd["tanggal_musyawarah"], errors="coerce")
    dd["jeda"] = (u - m).dt.days
    dd = dd[dd["jeda"].between(0, 1500)]
    if len(dd) < 50:
        belum_ada("Belum cukup putusan bertanggal lengkap untuk perkiraan.")
        return

    st.markdown(
        "Pilih ciri perkara, dan halaman menunjukkan **berapa lama perkara "
        "seperti itu biasanya menunggu pengucapan**, dihitung dari sebaran "
        "nyata perkara sejenis yang sudah diputus. Yang disajikan rentang, "
        "bukan satu angka, karena durasi memang beragam, dan yang jujur "
        "adalah menunjukkan seberapa beragamnya.")

    kol = st.columns(2)
    pilih_perkara = kol[0].selectbox(
        "Jenis perkara", ["Semua", "Banding", "Gugatan"], key="dur_perkara")
    pilih_pajak = kol[1].selectbox(
        "Jenis pajak",
        ["Semua"] + [label_kode(k, kode_peta) for k in
                     sorted(dd["kode_jenis_pajak"].dropna().unique(),
                            key=str)],
        key="dur_pajak")

    tersaring = dd
    if pilih_perkara != "Semua":
        tersaring = tersaring[tersaring["jenis_perkara"]
                              == pilih_perkara.lower()]
    if pilih_pajak != "Semua":
        kode = pilih_pajak.split(" · ")[0]
        tersaring = tersaring[tersaring["kode_jenis_pajak"].astype(str)
                              == kode]

    n = len(tersaring)
    if n < 30:
        st.warning(
            f"Hanya {n:,} perkara sejenis pada arsip. Di bawah tiga puluh "
            "perkara, rentangnya belum layak dijadikan pegangan; pilihan "
            "yang lebih longgar memberi perkiraan yang lebih kokoh.")
        return

    q = tersaring["jeda"].quantile([0.25, 0.5, 0.75, 0.9])
    k = st.columns(3)
    k[0].html(TV.kartu("Umumnya sekitar", f"{q[0.5]:.0f} hari",
                       f"median dari {n:,} perkara sejenis"))
    k[1].html(TV.kartu("Separuh perkara berada di",
                       f"{q[0.25]:.0f} - {q[0.75]:.0f} hari",
                       "rentang tengah, seperempat di bawah sampai "
                       "seperempat di atas"))
    k[2].html(TV.kartu("Bersiap untuk", f"{q[0.9]:.0f} hari",
                       "satu dari sepuluh perkara selama ini atau lebih"))

    fig = px.histogram(tersaring, x="jeda", nbins=40,
                       title="Sebaran jeda musyawarah ke pengucapan pada "
                             "perkara sejenis")
    fig.update_traces(hovertemplate="%{x} hari: %{y} putusan<extra></extra>")
    fig.add_vline(x=float(q[0.5]), line_dash="dot", line_color=P["tinta_2"],
                  annotation_text="median", annotation_position="top",
                  annotation_font=dict(size=11, color=P["tinta_2"]))
    fig.update_xaxes(showgrid=False, title="Hari")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     title="Jumlah putusan")
    # Ruang bawah ditambah; tanpa ini judul sumbunya terpotong tepi kartu.
    fig.update_layout(margin=dict(b=64))
    bagan(fig, 340, None,
          "Perkiraan ini menyangkut jeda musyawarah sampai pengucapan, "
          "bagian proses yang tanggalnya terbaca paling lengkap di arsip. "
          "Waktu dari pengajuan sampai musyawarah belum termasuk, sehingga "
          "keseluruhan proses lebih lama dari angka ini.")

    st.html(TV.catatan_siap(
        "Batas perkiraan ini.",
        "Angkanya dihitung dari perkara yang sudah selesai, sehingga tidak "
        "memperhitungkan perubahan beban kerja pengadilan ke depan, "
        "termasuk peralihan ke Mahkamah Agung pada akhir 2026. Perkara yang "
        "ditarik dari arsip juga condong ke yang sudah diputus; perkara "
        "yang masih berjalan panjang belum terwakili."))


def _durasi_keadaan(j: pd.Series) -> None:
    k = st.columns(3)
    k[0].html(TV.kartu("Median jeda musyawarah ke pengucapan", f"{j.median():.0f} hari",
                       f"dari {len(j):,} putusan bertanggal lengkap"))
    k[1].html(TV.kartu("Sepuluh persen terlama", f"{j.quantile(0.9):.0f} hari",
                       "atau lebih lama lagi"))
    k[2].html(TV.kartu("Lebih dari setahun",
                       f"{100 * (j > 365).mean():.0f} %",
                       "putusan menunggu pengucapan lebih dari 365 hari"))

    tepi = [0, 30, 60, 90, 180, 365, 1500]
    label = ["0-30", "31-60", "61-90", "91-180", "181-365", "lebih dari 365"]
    kelas = pd.cut(j, bins=tepi, labels=label, include_lowest=True)
    t = (kelas.value_counts().reindex(label).fillna(0).astype(int)
         .rename_axis("Jeda (hari)").reset_index(name="Putusan"))
    fig = px.bar(t, x="Jeda (hari)", y="Putusan", text="Putusan",
                 title="Sebaran jeda musyawarah sampai pengucapan")
    fig.update_xaxes(showgrid=False, title="")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"], title="")
    bagan(fig, 320, None,
          "Putusan yang sudah diambil belum berkekuatan hukum bagi para pihak "
          "sebelum diucapkan. Jeda panjang pada ekor kanan adalah "
          "temuan tata kelola proses yang tidak tampak pada statistik resmi.")

    # Kotak sebaran per tahun. Bagan batang di atas hanya memperlihatkan
    # berapa banyak putusan pada tiap rentang jeda, tanpa menjawab apakah
    # keadaannya membaik. Kotak sebaran menjawab itu: garis di tengah kotak
    # adalah median, kotaknya memuat separuh putusan yang paling khas, dan
    # titik di luar sungutnya adalah putusan yang jauh tertinggal.
    jt = d.dropna(subset=["tanggal_ucap", "tanggal_musyawarah",
                          "tahun_putusan"]).copy()
    if len(jt) >= 60:
        jt["Jeda"] = (pd.to_datetime(jt["tanggal_ucap"], errors="coerce")
                      - pd.to_datetime(jt["tanggal_musyawarah"],
                                       errors="coerce")).dt.days
        jt = jt[jt["Jeda"].between(0, 1500)]
        jt["Tahun"] = jt["tahun_putusan"].astype(int).astype(str)
        cukup = jt["Tahun"].value_counts()
        jt = jt[jt["Tahun"].isin(cukup[cukup >= 20].index)]
    if len(jt) >= 60:
        st.html('<div class="tingkat">Sebaran Jeda Menurut Tahun</div>')
        st.markdown(
            "Bagan kotak berikut membaca hal yang tidak terlihat pada bagan "
            "di atas, yaitu apakah keadaannya membaik dari tahun ke tahun. "
            "Garis di tengah setiap kotak adalah **median**, yaitu jeda yang "
            "paling khas pada tahun itu. Kotaknya memuat separuh putusan "
            "yang paling umum, sedangkan garis panjang di atas dan bawahnya "
            "menunjukkan rentang yang masih wajar. Titik yang berdiri "
            "sendiri di atas adalah putusan yang jauh tertinggal, dan "
            "justru titik-titik itulah yang perlu ditelusuri satu per satu.")
        fig = px.box(jt.sort_values("Tahun"), x="Tahun", y="Jeda",
                     points="outliers",
                     title="Sebaran jeda musyawarah ke pengucapan per tahun")
        fig.update_xaxes(showgrid=False, title="")
        fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                         title="Hari")
        bagan(fig, 380, None,
              "Hanya tahun dengan sedikitnya dua puluh putusan bertanggal "
              "lengkap yang ditampilkan. Kotak yang memendek dari tahun ke "
              "tahun berarti prosesnya makin seragam, sedangkan kotak yang "
              "tetap tinggi berarti percepatan belum menyentuh sebagian "
              "besar perkara.")

    st.html('<div class="tingkat">Lama Sengketa dari Masuk sampai Putus</div>')
    lag = d.dropna(subset=["lag_tahun"])
    lag = lag[lag["lag_tahun"].between(0, 15)]
    if len(lag) >= 20:
        t = (lag.groupby(lag["lag_tahun"].astype(int)).size()
             .rename_axis("Selisih tahun").reset_index(name="Putusan"))
        fig = px.bar(t, x="Selisih tahun", y="Putusan", text="Putusan",
                     title="Selisih tahun masuk sampai tahun putus, "
                           "pola nomor baru")
        fig.update_xaxes(showgrid=False, dtick=1, title="")
        fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"], title="")
        bagan(fig, 300, None,
              "Sebaran ini mengandung penyensoran kanan. Perkara yang lambat "
              "belum muncul di arsip karena belum diputus, sehingga batang "
              "kiri terlihat lebih tinggi daripada keadaan sebenarnya. Karena "
              "itu rata-rata tidak ditampilkan, dan perbandingan "
              "antar kohort menunggu data lengkap.")
    else:
        belum_ada("Putusan berpola nomor baru dengan tahun lengkap belum cukup "
                "untuk sebaran lama penyelesaian.")


# ---------------------------------------------------------------------------
# 9. Catatan metode
# ---------------------------------------------------------------------------

def hal_metode() -> None:
    st.markdown(
        "Seluruh dokumen diambil dari laman Sekretariat Pengadilan Pajak, "
        "yang menyediakannya untuk diakses umum. Setiap berkas disimpan tanpa "
        "perubahan beserta nilai hash SHA-256, sehingga setiap angka pada "
        "dashboard ini dapat ditelusuri mundur sampai ke berkas aslinya.")

    st.html('<div class="tingkat">Tahapan Pengolahan Data</div>')
    st.caption("Menggambarkan seluruh arsip yang terkumpul, tidak mengikuti "
               "unit analisis maupun penyaring tahun, karena yang "
               "digambarkan di sini pipa pengolahannya, bukan populasi yang "
               "sedang ditelaah.")
    baris = [("Berkas terkumpul", corong["unduh"]),
             ("Punya lapis teks", corong["teks"]),
             ("Masuk dataset terstruktur", corong["urai"])]
    t = pd.DataFrame(baris, columns=["Tahap", "Jumlah"])
    t["Terhadap tahap sebelumnya"] = [""] + [
        f"{100 * baris[i][1] / max(1, baris[i - 1][1]):.1f} persen"
        for i in range(1, len(baris))]
    tabel_bernavigasi(t, "tahap_olah")

    st.html('<div class="tingkat">Kelengkapan Ruas Data</div>')
    # Bagian ini justru mengikuti unit analisis, karena mutu pembacaan ruas
    # berbeda nyata antar unit dan pembaca perlu tahu keandalan datanya pada
    # unit yang sedang ditelaahnya.
    sumber_ruas = d if kode_instansi else df
    if kode_instansi:
        st.caption(f"Dihitung pada unit analisis {pilih_instansi}, "
                   f"{len(sumber_ruas):,} putusan. Bagian lain pada halaman "
                   "ini memotret seluruh arsip.")
    n = len(sumber_ruas)
    # Nama ruas ditampilkan sebagai istilah, bukan nama kolom basis data.
    ruas = [("nomor_putusan_raw", "Nomor putusan"),
            ("amar", "Amar putusan"),
            ("tahun_putusan", "Tahun putusan"),
            ("tanggal_ucap", "Tanggal ucap"),
            ("tanggal_musyawarah", "Tanggal musyawarah"),
            ("jenis_ketetapan", "Jenis ketetapan"),
            ("nomor_kep_terbanding", "Nomor keputusan terbanding"),
            ("nama_pemohon", "Nama pemohon"),
            ("hakim_ketua", "Hakim ketua"),
            ("jenis_koreksi", "Jenis koreksi"),
            ("masa_pajak", "Masa pajak")]
    t = pd.DataFrame([
        {"Ruas": label,
         "Terisi": int(sumber_ruas[k].notna().sum()),
         "Persen": round(100 * sumber_ruas[k].notna().sum() / max(n, 1), 1)}
        for k, label in ruas if k in sumber_ruas])
    tabel_bernavigasi(t, "lengkap_ruas", kolom_persen=("Persen",))

    st.html('<div class="tingkat">Peta Kode Jenis Pajak</div>')
    if kode_peta:
        tabel_bernavigasi(pd.DataFrame([
            {"Kode": k, "Jenis pajak menurut data": v["label"],
             "Putusan": v["n"], "Keyakinan": v["pangsa"],
             "Perlu diperiksa": "ya" if v["pangsa"] < 80 else ""}
            for k, v in sorted(kode_peta.items())]),
            "peta_kode", kolom_persen=("Keyakinan",))
        st.caption("Nama disusun dari data yang terbaca, bukan dari tabel kode resmi. "
                   "Keyakinan di bawah delapan puluh persen ditandai tanda "
                   "tanya di seluruh halaman.")

    rs = muat_resmi()
    if not rs.empty:
        st.html('<div class="tingkat">Validasi Silang dengan Daftar Resmi'
                '</div>')
        kiri = df.dropna(subset=["nomor_sengketa", "kode_jenis_pajak",
                                 "tahun_sengketa_masuk"]).copy()

        def _kunci(n, kd, th):
            try:
                return (f"{int(str(n).lstrip('0') or 0):06d}."
                        f"{int(float(kd)):02d}.{int(float(th))}")
            except (TypeError, ValueError):
                return None

        kiri["kunci"] = [
            _kunci(n, kd, th) for n, kd, th in
            zip(kiri["nomor_sengketa"], kiri["kode_jenis_pajak"],
                kiri["tahun_sengketa_masuk"])]
        gab = (kiri.dropna(subset=["kunci"])
               .merge(rs[["kunci", "amar", "tanggal_ucap"]], on="kunci",
                      suffixes=("", "_resmi")))
        a = gab.dropna(subset=["amar", "amar_resmi"])
        tg = gab.dropna(subset=["tanggal_ucap", "tanggal_ucap_resmi"])
        c_amar = (100 * int((a["amar"] == a["amar_resmi"]).sum())
                  / max(1, len(a)))
        c_tgl = (100 * int((tg["tanggal_ucap"]
                            == tg["tanggal_ucap_resmi"]).sum())
                 / max(1, len(tg)))
        st.markdown(
            f"Daftar resmi 2021 sampai 2025 memuat {len(rs):,} putusan dan "
            "menjadi pembanding kebenaran otomatis bagi penguraian teks. "
            f"Dari arsip yang sudah terurai, {len(gab):,} putusan terhubung "
            "ke daftar itu melalui nomor sengketanya. Pada baris yang "
            f"terhubung, amar hasil penguraian cocok **{c_amar:.1f} persen** "
            f"dan tanggal ucap cocok **{c_tgl:.1f} persen** dengan catatan "
            "resmi. Ketidakcocokan amar terbanyak terpusat pada kelas "
            "pembetulan "
            "dan pada risalah yang memuat lebih dari satu amar, dan menjadi "
            "antrean perbaikan penguraian.")

    st.html('<div class="tingkat">Keterbatasan Data dan Metode</div>')
    st.markdown(
        f"**Data belum lengkap.** Cakupan baru {cakupan:.1f} persen dari "
        "perkiraan seluruh arsip. Penarikan berjalan dengan urutan acak "
        "merata, sehingga proporsi bermakna sebagai taksiran, jumlah mutlak "
        "belum. Kecuali dinyatakan bersumber daftar resmi, angka sebaiknya "
        "dikutip sebagai taksiran.\n\n"
        "**Nama era lama disamarkan oleh sumbernya.** Risalah lama "
        "menggunakan "
        "XXX, AAA, dan sejenisnya, sehingga analisis sengketa berulang hanya "
        "menjangkau era yang namanya utuh.\n\n"
        "**Susunan majelis hanya termuat pada risalah era PDF.** Risalah era "
        "Word tidak memuatnya sepenuhnya.\n\n"
        "**Nilai sengketa dari ekstraksi teks tidak pernah digunakan**, "
        "karena "
        "hasilnya hanya proksi. Nilai yang tampil pada halaman Nilai "
        "sengketa seluruhnya berasal dari daftar resmi Sekretariat.\n\n"
        "**Pola antar hakim disajikan dengan penyesuaian kasar** dan "
        "berlabel bahan pembelajaran, bukan penilaian kinerja, serta "
        "sebaiknya beredar terbatas.")

    st.html('<div class="tingkat">Rencana Validasi Manual</div>')
    st.markdown(
        "Amar dan tanggal kini tervalidasi otomatis terhadap daftar resmi "
        "di atas. Yang tersisa untuk validasi manual adalah ruas yang tidak "
        "tercakup daftar resmi: jenis ketetapan, jenis koreksi, susunan "
        "majelis, dan dasar hukum, pada contoh acak berlapis kira-kira "
        "seratus putusan. Tingkat kesalahannya nanti dicantumkan di sini.")


# ---------------------------------------------------------------------------
# Tema sengketa, dari ruas pokok sengketa yang selama ini belum dipakai
# ---------------------------------------------------------------------------

# Tema dikenali lewat kata kunci pada teks pokok sengketa. Daftarnya lahir
# dari penghitungan pasangan kata tersering pada 7.374 pokok sengketa nyata,
# bukan dikarang dari dugaan, dan diurutkan dari yang paling khusus supaya
# tema umum tidak menelan tema khusus. Satu putusan boleh menyandang lebih
# dari satu tema, karena satu perkara memang kerap memuat beberapa pokok.
TEMA_SENGKETA = [
    ("PPN wajib dipungut sendiri", r"dipungut\s+sendiri"),
    ("DPP penyerahan PPN",
     r"dpp\s+(?:penyerahan|ppn)|penyerahan\s+ppn|pengenaan\s+penyerahan|"
     r"dasar\s+pengenaan\s+pajak\s+pertambahan"),
    ("Pajak masukan",
     r"pajak\s+masukan|masukan\s+(?:diperhitungkan|dikreditkan)"),
    ("Penetapan nilai pabean", r"nilai\s+pabean"),
    ("Klasifikasi dan tarif barang",
     r"klasifikasi|pos\s+tarif|pembebanan\s+tarif"),
    ("Bea masuk dan pungutan impor", r"bea\s+masuk|pungutan\s+impor|\bpib\b"),
    ("Penyesuaian fiskal", r"penyesuaian\s+fiskal|fiskal\s+(?:positif|negatif)"),
    ("Peredaran usaha", r"peredaran\s+usaha|omzet|penjualan\s+bruto"),
    ("Objek dan DPP PPh",
     r"dpp\s+pph|objek\s+pph|pengenaan\s+pph|pph\s+(?:final|terutang)|"
     r"pengenaan\s+penghasilan"),
    ("Biaya dan pengurang penghasilan",
     r"koreksi\s+biaya|biaya\s+(?:usaha|jabatan|promosi|bunga|royalti)|"
     r"pengurang\s+penghasilan"),
    ("Kompensasi kerugian", r"kompensasi\s+kerugian"),
    ("Hubungan istimewa", r"hubungan\s+istimewa|transfer\s+pricing"),
    ("Kredit pajak", r"kredit\s+pajak"),
    ("Sanksi administrasi", r"sanksi\s+administrasi|denda\s+administrasi"),
    ("Pajak bumi dan bangunan", r"pajak\s+bumi|\bpbb\b|\bnjop\b"),
    ("Syarat formal pengajuan",
     r"formal|daluwarsa|kedaluwarsa|jangka\s+waktu\s+pengajuan"),
]


# Tema juga dipetakan dari ruas jenis koreksi, yang diurai dari teks penuh
# dan terisi 76 persen. Uraian pokok sengketa lebih kaya, tetapi tangkapan
# arsip saat ini banyak yang terpotong pendek sehingga hanya sebagian kecil
# yang temanya terkenali dari sana. Kedua sumber digabung: koreksi memberi
# cakupan, pokok memberi tema yang lebih halus seperti PPN wajib dipungut
# sendiri, yang tidak dibedakan pada taksonomi koreksi.
PETA_KOREKSI_TEMA = {
    "pajak_masukan": "Pajak masukan",
    "dpp_ppn": "DPP penyerahan PPN",
    "nilai_pabean": "Penetapan nilai pabean",
    "klasifikasi_tarif": "Klasifikasi dan tarif barang",
    "peredaran_usaha": "Peredaran usaha",
    "hpp": "Harga pokok penjualan",
    "biaya": "Biaya dan pengurang penghasilan",
    "penyusutan": "Penyusutan dan amortisasi",
    "hubungan_istimewa": "Hubungan istimewa",
    "kredit_pajak": "Kredit pajak",
    "kompensasi_rugi": "Kompensasi kerugian",
    "pph_potput": "PPh potong pungut",
    "fasilitas": "Fasilitas dan pembebasan",
    "sanksi": "Sanksi administrasi",
    "formal": "Syarat formal pengajuan",
}


@st.cache_data(ttl=300, show_spinner="Mengelompokkan tema sengketa...")
def petakan_tema(pokok: pd.Series, koreksi: pd.Series) -> pd.DataFrame:
    """Satu baris per pasangan putusan dan tema yang dikenali padanya."""
    baris = []
    teks = pokok.fillna("").astype(str).str.lower()
    for label, pola in TEMA_SENGKETA:
        for doc_id in teks[teks.str.contains(pola, regex=True)].index:
            baris.append({"doc_id": doc_id, "Tema": label})
    pecah = koreksi.dropna().astype(str).str.split("|").explode()
    for doc_id, kode in pecah.items():
        label = PETA_KOREKSI_TEMA.get(kode)
        if label:
            baris.append({"doc_id": doc_id, "Tema": label})
    if not baris:
        return pd.DataFrame(columns=["doc_id", "Tema"])
    return pd.DataFrame(baris).drop_duplicates()


def hal_tema() -> None:
    st.caption(
        "Apa yang sebenarnya dipersengketakan, dibaca dari uraian pokok "
        "sengketa dan jenis koreksi pada tiap putusan. Dua pertanyaannya "
        "sederhana: tema apa yang terus berulang, dan tema mana yang "
        "paling sering dimenangkan wajib pajak.")

    punya = d[(d["pokok_sengketa"].notna()
               & (d["pokok_sengketa"].str.len() > 15))
              | d["jenis_koreksi"].notna()].copy()
    if punya.empty:
        belum_ada("Belum terdapat putusan yang tema sengketanya terbaca pada "
                "lingkup ini.")
        return
    st.markdown(
        f"Tema terbaca pada **{len(punya):,}** dari {len(d):,} putusan "
        "dalam lingkup, dari dua sumber sekaligus: uraian pokok sengketa "
        "dan jenis koreksi yang dikenali di dalam teks putusan. Angkanya "
        "paling tepat dibaca sebagai perbandingan antar tema, bukan sebagai "
        "jumlah mutlak seluruh arsip.")

    indeks = punya.set_index("doc_id")
    peta = petakan_tema(indeks["pokok_sengketa"], indeks["jenis_koreksi"])
    if peta.empty:
        belum_ada("Tidak ada tema yang dikenali pada lingkup ini.")
        return
    gabung = peta.merge(
        punya[["doc_id", "amar", "amar_label", "tahun_putusan",
               "nomor_tampil", "tanggal_ucap", "kode_jenis_pajak"]],
        on="doc_id", how="left")
    beramar_t = gabung[gabung["amar"].notna()
                       & (gabung["amar"] != "pembetulan")].copy()
    beramar_t["menang"] = beramar_t["amar"].isin(AMAR_MENANG)

    t1, t2, t3 = st.tabs(["Peta tema", "Tren tema", "Telusuri per tema"])

    with t1:
        g = (beramar_t.groupby("Tema")
             .agg(Putusan=("doc_id", "nunique"), menang=("menang", "sum"))
             .reset_index())
        g = g[g["Putusan"] >= 10].copy()
        g["Dikabulkan"] = (100 * g["menang"] / g["Putusan"]).round(1)
        batas = [selang_wilson(int(m), int(n))
                 for m, n in zip(g["menang"], g["Putusan"])]
        g["Batas bawah"] = [round(b[0], 1) for b in batas]
        g["Batas atas"] = [round(b[1], 1) for b in batas]
        g = g.drop(columns=["menang"]).sort_values("Putusan", ascending=False)

        sering = g.iloc[0]
        rawan = g.loc[g["Dikabulkan"].idxmax()]
        st.markdown(
            "Tabel ini memperlihatkan dua hal sekaligus: **seberapa sering "
            "sebuah tema muncul**, dan **seberapa sering wajib pajak "
            "menang** pada tema itu.\n\n"
            f"Contoh membacanya: tema {sering['Tema']} adalah yang paling "
            f"sering muncul, {int(sering['Putusan']):,} putusan, dan "
            f"{sering['Dikabulkan']:.0f} persen di antaranya dimenangkan "
            f"wajib pajak. Sedangkan tema dengan tingkat kemenangan "
            f"tertinggi adalah {rawan['Tema']}, "
            f"{rawan['Dikabulkan']:.0f} persen dari "
            f"{int(rawan['Putusan']):,} putusan. Bagi fiskus, tema seperti "
            "itu adalah tempat pedoman paling perlu dibenahi; bagi wajib "
            "pajak, itu tema yang secara historis paling sering berhasil "
            "dilawan.")
        tabel_bernavigasi(g, "tema_peta",
                          kolom_persen=("Dikabulkan", "Batas bawah",
                                        "Batas atas"))
        st.caption("Diurutkan dari tema yang paling sering muncul. Satu "
                   "putusan dapat menyandang lebih dari satu tema.")

        atas = g.head(10).sort_values("Putusan")
        fig = px.bar(atas, x="Putusan", y="Tema", orientation="h",
                     text=[f"{int(n):,}  ({v:.0f}% dikabulkan)"
                           for n, v in zip(atas["Putusan"],
                                           atas["Dikabulkan"])],
                     title="Sepuluh tema tersering")
        fig.update_xaxes(title="", showticklabels=False, showgrid=False,
                         zeroline=False)
        fig.update_yaxes(title="")
        bagan(fig, max(300, 38 * len(atas) + 110), None,
              "Panjang batang adalah banyaknya putusan bertema itu, dan "
              "angka dalam kurung adalah bagian yang dimenangkan wajib "
              "pajak.")

        unduh_laporan(
            "Tema Sengketa",
            [(str(r["Tema"]), f"{int(r['Putusan']):,} putusan",
              f"{r['Dikabulkan']:.1f} persen dikabulkan")
             for _, r in g.head(12).iterrows()],
            None,
            "Satu putusan dapat menyandang lebih dari satu tema, sehingga "
            "jumlah antar tema tidak boleh dijumlahkan. Tema dipetakan dari "
            "uraian pokok sengketa dan jenis koreksi pada teks putusan, dan "
            "angkanya paling tepat dibaca sebagai perbandingan antar tema.",
            "tema")

    with t2:
        st.markdown(
            "Bagan ini mengikuti tiga tema tersering dari tahun ke tahun. "
            "Tema yang naik berarti persoalannya makin sering sampai ke "
            "pengadilan, dan itu isyarat paling dini bahwa ada aturan atau "
            "praktik yang menimbulkan tafsir berbeda secara meluas.")
        tiga_besar = (beramar_t.groupby("Tema")["doc_id"].nunique()
                      .sort_values(ascending=False).head(3).index.tolist())
        tt = (beramar_t[beramar_t["Tema"].isin(tiga_besar)]
              .dropna(subset=["tahun_putusan"]))
        tt = (tt.groupby(["Tema", "tahun_putusan"])["doc_id"].nunique()
              .reset_index(name="Putusan"))
        tt["Tahun"] = tt["tahun_putusan"].astype(int)
        cukup = tt.groupby("Tahun")["Putusan"].sum()
        tt = tt[tt["Tahun"].isin(cukup[cukup >= 20].index)]
        if tt.empty or tt["Tahun"].nunique() < 3:
            belum_ada("Belum terdapat cukup tahun untuk menggambarkan tren "
                    "tema pada lingkup ini.")
        else:
            fig = px.line(tt, x="Tahun", y="Putusan", color="Tema",
                          markers=True,
                          title="Tiga tema tersering menurut tahun putusan")
            fig.update_layout(
                legend=dict(orientation="h", yanchor="top", y=-0.14,
                            xanchor="left", x=0),
                margin=dict(b=76))
            fig.update_xaxes(showgrid=False, dtick=1, title="")
            fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                             title="Jumlah putusan")
            bagan(fig, 400, None,
                  "Jumlah per tahun mengikuti cakupan arsip yang sedang "
                  "tersedia, jadi yang layak dibandingkan adalah bentuk "
                  "pergerakan antar tema, bukan tinggi mutlaknya.")

    with t3:
        pilih_tema = st.selectbox(
            "Pilih tema yang ingin ditelusuri",
            sorted(gabung["Tema"].unique()), key="tema_pilih")
        isi = (gabung[gabung["Tema"] == pilih_tema]
               .drop_duplicates("doc_id")
               .sort_values("tahun_putusan", ascending=False))
        st.markdown(f"**{len(isi):,} putusan** bertema {pilih_tema}. Pilih "
                    "salah satu baris untuk membaca isi putusannya.")
        isi, nav_tema = potong_halaman(
            isi, f"temal_{abs(hash(pilih_tema)) & 0xffffff}")
        pilih_baris = st.dataframe(
            pd.DataFrame({
                "Nomor putusan": isi["nomor_tampil"],
                "Tanggal putusan": [
                    tampil_tanggal(u, tampil_tahun(th_)) for u, th_ in
                    zip(isi["tanggal_ucap"], isi["tahun_putusan"])],
                "Jenis pajak": isi["kode_jenis_pajak"].map(
                    lambda k: label_kode(k, kode_peta)),
                "Amar": isi["amar_label"]}),
            width="stretch", hide_index=True, on_select="rerun",
            selection_mode="single-row", key=f"tema_{pilih_tema}",
            column_config={
                "Tanggal putusan": st.column_config.TextColumn(
                    alignment="center")})
        gambar_nav(nav_tema)
        b = (pilih_baris.selection.rows
             if pilih_baris and pilih_baris.selection else [])
        if b:
            buka_putusan(isi.iloc[b[0]]["doc_id"], f"tema_{pilih_tema}")


# ---------------------------------------------------------------------------
# Banding unit: dua unit disandingkan pada satu halaman
# ---------------------------------------------------------------------------

def hal_banding() -> None:
    """
    Membandingkan dua unit berdampingan, tanpa berpindah pilihan.

    Rancangan awalnya menggandakan halaman yang sudah ada ke dua kolom.
    Cara itu ditinggalkan karena dua sebab. Pertama, kendali pada halaman
    yang sama digambar dua kali dengan kunci yang sama, dan Streamlit
    melarangnya. Kedua, dan ini yang lebih menentukan, halaman penuh yang
    dijejalkan ke kolom separuh lebar menjadi sempit dan berulang, sedangkan
    yang dicari pembaca justru angka intinya saja bersisian.

    Karena itu halaman ini dibangun tersendiri: satu deret pembanding yang
    memang dipilih untuk disandingkan, berikut selisih dan penilaian apakah
    selisih itu berarti.
    """
    st.caption(
        "Dua unit disandingkan pada satu layar agar dapat dibandingkan tanpa "
        "berpindah pilihan. Mengikuti penyaring tahun di bilah samping, "
        "tetapi tidak mengikuti unit analisis, karena unitnya justru dipilih "
        "di sini.")

    NAMA = {"DJP": ("djp",), "DJBC": ("djbc",), "Pemda": ("pemda",),
            "Kemenkeu": ("djp", "djbc")}
    kol = st.columns(2)
    kiri_nama = kol[0].selectbox("Unit di kiri", list(NAMA), index=0,
                                 key="banding_kiri")
    kanan_nama = kol[1].selectbox("Unit di kanan", list(NAMA), index=1,
                                  key="banding_kanan")
    if kiri_nama == kanan_nama:
        belum_ada("Kedua sisi menunjuk unit yang sama, sehingga tidak ada "
                  "yang dapat dibandingkan.")
        return

    a, b = lingkup_unit(NAMA[kiri_nama]), lingkup_unit(NAMA[kanan_nama])
    if a.empty or b.empty:
        belum_ada("Salah satu unit tidak memiliki putusan pada rentang ini.")
        return

    def ukur(x: pd.DataFrame) -> dict:
        dd = beramar(x)
        menang = dd["amar"].isin(AMAR_MENANG)
        j = jeda_hari(x)
        kor = (x["jenis_koreksi"].dropna().str.split("|").explode()
               .map(lambda v: LABEL_KOREKSI.get(v, v)).value_counts())
        pajak = x["kode_jenis_pajak"].dropna().astype(str).value_counts()
        return {
            "Putusan terurai": (len(x), f"{len(x):,}"),
            "Dikabulkan": (100 * menang.mean() if len(dd) else 0,
                           f"{100 * menang.mean():.1f} %" if len(dd) else "-"),
            "Kabul sebagian dari yang dikabulkan": (
                100 * (dd["amar"] == "kabul_sebagian").sum()
                / max(int(menang.sum()), 1),
                f"{100 * (dd['amar'] == 'kabul_sebagian').sum() / max(int(menang.sum()), 1):.1f} %"),
            "Gugur sebelum pokok sengketa": (
                100 * (x["amar"] == "tidak_dapat_diterima").mean(),
                f"{100 * (x['amar'] == 'tidak_dapat_diterima').mean():.1f} %"),
            "Median jeda musyawarah ke ucap": (
                float(j.median()) if len(j) else 0,
                f"{j.median():,.0f} hari" if len(j) else "-"),
            "Sepuluh persen terlama": (
                float(j.quantile(0.9)) if len(j) else 0,
                f"{j.quantile(0.9):,.0f} hari" if len(j) else "-"),
            "Jenis pajak tersering": (
                0, label_kode(pajak.index[0], kode_peta) if len(pajak) else "-"),
            "Koreksi tersering": (0, kor.index[0] if len(kor) else "-"),
            "Wilson bawah": (0, ""), "Wilson atas": (0, ""),
        }

    ua, ub = ukur(a), ukur(b)
    dda, ddb = beramar(a), beramar(b)
    ma = int(dda["amar"].isin(AMAR_MENANG).sum())
    mb = int(ddb["amar"].isin(AMAR_MENANG).sum())
    la, ha = selang_wilson(ma, max(len(dda), 1))
    lb, hb = selang_wilson(mb, max(len(ddb), 1))
    terpisah = lb > ha or la > hb

    k = st.columns(3)
    k[0].html(TV.kartu(f"{kiri_nama} dikabulkan", ua["Dikabulkan"][1],
                       f"dari {len(dda):,} putusan beramar"))
    k[1].html(TV.kartu(f"{kanan_nama} dikabulkan", ub["Dikabulkan"][1],
                       f"dari {len(ddb):,} putusan beramar"))
    beda = ua["Dikabulkan"][0] - ub["Dikabulkan"][0]
    k[2].html(TV.kartu(
        "Selisihnya", f"{beda:+.1f} poin",
        "selang keyakinan tidak bersinggungan, perbedaannya nyata"
        if terpisah else "selang keyakinan masih bersinggungan, "
                         "perbedaannya belum dapat disimpulkan"))

    st.markdown(
        f"Tabel di bawah menyandingkan **{kiri_nama}** dan **{kanan_nama}** "
        "pada delapan hal yang paling sering ditanyakan. Kolom selisih "
        "dihitung sebagai nilai kiri dikurangi nilai kanan, sehingga "
        "tanda positif berarti sisi kiri lebih tinggi.\n\n"
        "Perlu diingat, angka yang berbeda belum tentu berarti salah satunya "
        "keliru: kedua unit menerbitkan jenis ketetapan yang berbeda dan "
        "menghadapi jenis sengketa yang berbeda pula. Yang layak ditelaah "
        "adalah selisih yang besar dan menetap.")

    baris = []
    for nama in ("Putusan terurai", "Dikabulkan",
                 "Kabul sebagian dari yang dikabulkan",
                 "Gugur sebelum pokok sengketa",
                 "Median jeda musyawarah ke ucap", "Sepuluh persen terlama",
                 "Jenis pajak tersering", "Koreksi tersering"):
        va, vb = ua[nama], ub[nama]
        if isinstance(va[0], (int, float)) and va[0] and vb[0]:
            selisih = f"{va[0] - vb[0]:+,.1f}"
        else:
            selisih = "-"
        baris.append({"Pembanding": nama, kiri_nama: va[1],
                      kanan_nama: vb[1], "Selisih": selisih})
    tabel_bernavigasi(pd.DataFrame(baris), "banding_ringkas", per=10)

    st.html('<div class="tingkat">Arah Dikabulkan dari Tahun ke Tahun</div>')
    fig = go.Figure()
    ada = False
    for nama, bingkai in ((kiri_nama, a), (kanan_nama, b)):
        t = _deret_tahunan(beramar(bingkai))
        if len(t) < 3:
            continue
        ada = True
        fig.add_trace(go.Scatter(
            x=t["Tahun"], y=t["Dikabulkan"], mode="lines+markers", name=nama,
            hovertemplate="%{x}: %{y:.1f} persen<extra></extra>"))
    if ada:
        fig.add_hline(y=50, line_dash="dot", line_color=P["sumbu"])
        fig.update_layout(
            title="Tingkat dikabulkan menurut tahun putusan",
            legend=dict(orientation="h", yanchor="top", y=-0.14,
                        xanchor="left", x=0),
            margin=dict(b=70))
        fig.update_xaxes(showgrid=False, dtick=1, title="")
        fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                         ticksuffix="%", title="")
        bagan(fig, 400, None,
              "Dua garis yang bergerak berlawanan arah menandakan sebabnya "
              "ada di dalam unitnya masing masing, bukan pada keadaan umum "
              "maupun perubahan sikap pengadilan.")
    else:
        belum_ada("Belum cukup tahun bermuatan putusan memadai pada salah "
                  "satu unit untuk menggambarkan arahnya.")

    st.html('<div class="tingkat">Tema Sengketa Teratas Tiap Unit</div>')
    kol2 = st.columns(2)
    for kolom, nama, bingkai in ((kol2[0], kiri_nama, a),
                                 (kol2[1], kanan_nama, b)):
        with kolom:
            st.html(f'<div class="banding-judul">{nama}<span>'
                    f'{len(bingkai):,} putusan</span></div>')
            kor = (bingkai["jenis_koreksi"].dropna().str.split("|").explode()
                   .map(lambda v: LABEL_KOREKSI.get(v, v)).value_counts()
                   .head(8))
            if kor.empty:
                belum_ada("Jenis koreksi belum terbaca pada unit ini.")
                continue
            t = (kor.rename_axis("Jenis koreksi").reset_index(name="Putusan"))
            st.html(TV.tabel(t))

    unduh_laporan(
        f"Banding Unit, {kiri_nama} dan {kanan_nama}",
        [(r["Pembanding"], f"{r[kiri_nama]} lawan {r[kanan_nama]}",
          f"selisih {r['Selisih']}") for r in baris],
        None,
        "Kedua unit menerbitkan jenis ketetapan yang berbeda dan menghadapi "
        "jenis sengketa yang berbeda, sehingga selisih angka tidak dengan "
        "sendirinya berarti salah satunya keliru. Yang layak ditelaah adalah "
        "selisih yang besar dan menetap dari tahun ke tahun.",
        "banding")


# ---------------------------------------------------------------------------
# Karakter memutus: keragaman antar hakim setelah campuran perkara dikendalikan
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Menyusun profil karakter memutus...")
def profil_karakter(kunci: tuple, min_n: int) -> pd.DataFrame:
    """
    Empat perilaku memutus tiap hakim ketua, dengan campuran perkara
    dikendalikan.

    Pengendalian itu inti halaman ini. Hakim yang banyak menangani perkara
    kepabeanan akan tampak lebih sering menolak daripada rekannya yang
    menangani perkara pajak, dan itu bukan sifat hakimnya melainkan sifat
    perkaranya. Karena itu tiap putusan dibandingkan dengan harapan
    kelompoknya sendiri, yaitu rata rata dikabulkan pada gabungan jenis
    pajak dan instansi yang sama, lalu selisihnya yang dirata ratakan.

    Pengukuran pada arsip ini menunjukkan campuran perkara menjelaskan 46
    persen keragaman antar hakim, dan 54 persen sisanya tetap melekat pada
    hakimnya. Tanpa pengendalian, hampir separuh angka yang dibaca pemakai
    sebenarnya menggambarkan perkaranya, bukan yang memutusnya.

    Masukannya sengaja tuple, bukan bingkai, supaya singgahan dapat
    mengenali panggilan yang sama tanpa menyalin data besar.
    """
    dd = beramar(d).dropna(subset=["hakim_ketua"]).copy()
    if dd.empty:
        return pd.DataFrame()
    dd["menang"] = dd["amar"].isin(AMAR_MENANG)
    kunci_baku, nama_tampil = bakukan_hakim(dd["hakim_ketua"])
    dd["kunci"] = kunci_baku
    dd = dd[dd["kunci"] != ""]
    if dd.empty:
        return pd.DataFrame()

    dd["kelompok"] = (dd["kode_jenis_pajak"].astype(str) + "|"
                      + dd["instansi_terbanding"].astype(str))
    harap = dd.groupby("kelompok")["menang"].transform("mean")
    dd["selisih"] = dd["menang"].astype(float) - harap

    u = pd.to_datetime(dd["tanggal_ucap"], errors="coerce")
    m = pd.to_datetime(dd["tanggal_musyawarah"], errors="coerce")
    dd["jeda"] = (u - m).dt.days
    dd.loc[~dd["jeda"].between(0, 1500), "jeda"] = float("nan")

    g = dd.groupby("kunci")
    n_kabul = g["menang"].sum()
    prof = pd.DataFrame({
        "Putusan": g.size(),
        "menang": n_kabul,
        "Dikabulkan": 100 * g["menang"].mean(),
        "Selisih dari harapan": 100 * g["selisih"].mean(),
        "Kabul sebagian": 100 * g.apply(
            lambda x: (x["amar"] == "kabul_sebagian").sum()
            / max(int(x["amar"].isin(AMAR_MENANG).sum()), 1),
            include_groups=False),
        "Gugur formal": 100 * g.apply(
            lambda x: (x["amar"] == "tidak_dapat_diterima").mean(),
            include_groups=False),
        "Median jeda hari": g["jeda"].median(),
        "awal": g["tahun_putusan"].min(),
        "akhir": g["tahun_putusan"].max(),
    })
    prof = prof[prof["Putusan"] >= min_n].copy()
    if prof.empty:
        return prof
    batas = [selang_wilson(int(a), int(b))
             for a, b in zip(prof["menang"], prof["Putusan"])]
    prof["Batas bawah"] = [round(x[0], 1) for x in batas]
    prof["Batas atas"] = [round(x[1], 1) for x in batas]
    prof["Hakim"] = [nama_tampil.get(k, k) for k in prof.index]
    prof["Periode"] = [
        f"{int(a)}" if pd.notna(a) and a == b else
        (f"{int(a)}-{int(b)}" if pd.notna(a) and pd.notna(b) else "-")
        for a, b in zip(prof["awal"], prof["akhir"])]
    return prof.drop(columns=["menang", "awal", "akhir"]).reset_index(drop=True)


def hal_karakter() -> None:
    st.caption(
        "Bagaimana pola tiap hakim dalam memutus, bukan siapa yang benar. "
        "Empat perilaku diukur, dan tingkat dikabulkannya sudah disesuaikan "
        "dengan jenis perkara yang ditangani, supaya yang terbaca sifat "
        "memutusnya, bukan sifat perkaranya.")

    min_n = st.slider(
        "Jumlah putusan minimal per hakim", 20, 120, 40, step=10,
        key="kar_min",
        help="Hakim dengan putusan sedikit menghasilkan persentase yang "
             "bergoyang liar. Ambang yang lebih tinggi memberi angka lebih "
             "kokoh, tetapi hakim yang dinilai lebih sedikit.")
    # Kunci singgahan wajib memuat seluruh penyaring lingkup. Kunci tetap
    # yang lama membuat pergantian saklar instansi tidak berpengaruh pada
    # halaman ini: hitungan lingkup Semua yang tersimpan terus disajikan,
    # dan pemakai yang memilih DJBC tetap membaca profil gabungan.
    prof = profil_karakter((pilih_instansi, th, hanya_teks), min_n)
    if prof.empty or len(prof) < 5:
        belum_ada("Belum terdapat cukup hakim yang memenuhi ambang tersebut "
                "pada lingkup ini. Ambang dapat diturunkan.")
        return

    t1, t2, t3 = st.tabs(["Seberapa beragam", "Peta karakter",
                          "Tabel lengkap"])
    with t1:
        _karakter_ragam(prof)
    with t2:
        _karakter_peta(prof)
    with t3:
        _karakter_tabel(prof)

    st.html(TV.catatan_siap(
        "Batas yang wajib disebut ketika angka halaman ini dikutip.",
        "Yang terukur adalah hakim ketua, sedangkan putusan diambil majelis "
        "secara bersama, sehingga sebenarnya yang tergambar kecenderungan "
        "majelis yang dipimpinnya. Pengendali campuran perkara baru mencakup "
        "jenis pajak dan instansi, belum kerumitan maupun nilai perkara, "
        "sehingga sebagian keragaman yang tersisa masih mungkin berasal dari "
        "perbedaan perkara yang belum terukur. Dan yang terpenting, tingkat "
        "dikabulkan tinggi atau rendah tidak berarti benar atau salah: "
        "halaman ini menyajikan keragaman sebagai bahan pembicaraan "
        "konsistensi, bukan sebagai penilaian kinerja perorangan. Karena itu "
        "halaman ini sengaja tidak memuat peringkat."))


def _karakter_ragam(prof: pd.DataFrame) -> None:
    """Apakah keragaman antar hakim nyata, dan seberapa besar."""
    dd = beramar(d).dropna(subset=["hakim_ketua"]).copy()
    dd["menang"] = dd["amar"].isin(AMAR_MENANG).astype(float)
    p = float(dd["menang"].mean())
    n = prof["Putusan"].to_numpy(dtype=float)
    laju = prof["Dikabulkan"].to_numpy(dtype=float) / 100
    ragam_ada = float(np.var(laju, ddof=1))
    ragam_acak = float(np.mean(p * (1 - p) / n))
    lipat = ragam_ada / max(ragam_acak, 1e-12)

    k = st.columns(3)
    k[0].html(TV.kartu("Hakim yang dinilai", f"{len(prof):,}",
                       f"mencakup {int(prof['Putusan'].sum()):,} putusan "
                       "beramar"))
    k[1].html(TV.kartu("Keragaman dibanding kebetulan", f"{lipat:.0f} kali",
                       "satu kali berarti seluruh perbedaan hanya kebetulan"))
    p10 = prof["Selisih dari harapan"].quantile(0.10)
    p90 = prof["Selisih dari harapan"].quantile(0.90)
    k[2].html(TV.kartu("Jarak antar hakim", f"{p90 - p10:.0f} poin",
                       "setelah jenis perkara dikendalikan, persentil 10 "
                       "sampai 90"))

    st.markdown(
        "Pertanyaan pertama yang harus dijawab sebelum apa pun: **apakah "
        "perbedaan antar hakim ini nyata, atau sekadar kebetulan?** Hakim "
        "dengan empat puluh putusan wajar berbeda beberapa poin hanya "
        "karena kebetulan, seperti melempar koin empat puluh kali tidak "
        "selalu menghasilkan dua puluh sisi gambar.\n\n"
        f"Jawabannya: keragaman yang terlihat **{lipat:.0f} kali lipat lebih "
        "besar** daripada yang dapat dijelaskan kebetulan. Jadi hasil "
        "perkara memang bergantung pada siapa yang memutus.\n\n"
        "Pertanyaan kedua yang lebih tajam: **berapa banyak dari perbedaan "
        "itu sekadar karena hakim menangani jenis perkara yang berbeda?** "
        "Ini yang dikendalikan pada seluruh halaman. Tiap putusan "
        "dibandingkan dengan harapan kelompoknya sendiri, dan selisihnya "
        "itulah yang diukur. Nol berarti hakim tersebut memutus persis "
        "seperti kebiasaan pada jenis perkara yang ditanganinya; positif "
        "berarti lebih sering mengabulkan daripada kebiasaan itu.")

    t = prof.sort_values("Selisih dari harapan")
    fig = px.histogram(t, x="Selisih dari harapan", nbins=24,
                       title="Sebaran selisih dari harapan kelompoknya")
    fig.update_traces(hovertemplate="%{x:.0f} poin: %{y} hakim<extra></extra>")
    fig.add_vline(x=0, line_dash="dot", line_color=P["tinta_2"],
                  annotation_text="memutus seperti kebiasaan kelompoknya",
                  annotation_position="top",
                  annotation_font=dict(size=11, color=P["tinta_2"]))
    fig.update_xaxes(showgrid=False, title="Poin persen dari harapan")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     title="Jumlah hakim")
    fig.update_layout(margin=dict(b=64))
    bagan(fig, 340, None,
          "Sebaran yang melebar jauh dari nol berarti perkara setara dapat "
          "berakhir berbeda tergantung majelis yang memeriksanya. Ini bahan "
          "pembakuan pedoman, bukan penilaian perorangan.")

    st.html('<div class="tingkat">Tiga Keragaman yang Paling Layak Dibahas</div>')
    for kolom, judul, ket in (
            ("Gugur formal", "Ketatnya syarat formal",
             "Menentukan perkara diperiksa atau tidak, sebelum pokok "
             "sengketanya tersentuh sama sekali."),
            ("Kabul sebagian", "Gaya mengabulkan",
             "Sebagian hakim cenderung memutus penuh ke satu arah, sebagian "
             "lain cenderung membelah. Keduanya sah, tetapi berakibat sangat "
             "berbeda bagi perencanaan arus kas wajib pajak."),
            ("Median jeda hari", "Kecepatan pengucapan",
             "Tidak menyangkut isi putusan sama sekali, dan justru itu yang "
             "paling mudah diseragamkan.")):
        v = prof[kolom].dropna()
        if v.empty:
            continue
        satuan = " hari" if "jeda" in kolom else " persen"
        st.markdown(
            f"**{judul}.** Dari {v.quantile(.1):,.0f}{satuan} pada persentil "
            f"sepuluh sampai {v.quantile(.9):,.0f}{satuan} pada persentil "
            f"sembilan puluh, dengan median {v.median():,.0f}{satuan}. {ket}")


def _karakter_peta(prof: pd.DataFrame) -> None:
    """Peta dua sumbu: kecenderungan mengabulkan dan gaya mengabulkan."""
    st.markdown(
        "Peta ini menempatkan tiap hakim menurut dua perilaku sekaligus. "
        "Sumbu mendatar adalah **selisih dari harapan kelompoknya**: ke "
        "kanan berarti lebih sering mengabulkan daripada kebiasaan pada "
        "jenis perkara yang ditanganinya. Sumbu tegak adalah **gaya "
        "mengabulkan**: ke atas berarti lebih sering mengabulkan sebagian "
        "daripada seluruhnya. Besar titik menunjukkan banyaknya putusan, dan "
        "warnanya menunjukkan ketatnya pada syarat formal.\n\n"
        "Yang penting dibaca di sini bukan posisi satu hakim, melainkan "
        "**seberapa tersebar titiknya**. Titik yang berkerumun rapat berarti "
        "praktik sudah seragam; titik yang tersebar luas berarti hasil "
        "perkara bergantung pada majelis mana yang kebagian memeriksanya.")

    t = prof.copy()
    t["Ketat formal"] = t["Gugur formal"].round(1)
    fig = px.scatter(
        t, x="Selisih dari harapan", y="Kabul sebagian",
        size="Putusan", color="Ketat formal",
        color_continuous_scale=[[0, P["seri"][2]], [0.5, P["seri"][1]],
                                [1, P["genting"]]],
        hover_name="Hakim", size_max=34,
        title="Peta karakter memutus")
    fig.update_traces(
        hovertemplate="<b>%{hovertext}</b><br>"
                      "selisih dari harapan %{x:.1f} poin<br>"
                      "kabul sebagian %{y:.1f} persen<br>"
                      "gugur formal %{marker.color:.1f} persen"
                      "<extra></extra>")
    fig.add_vline(x=0, line_dash="dot", line_color=P["sumbu"])
    fig.add_hline(y=float(t["Kabul sebagian"].median()), line_dash="dot",
                  line_color=P["sumbu"])
    fig.update_xaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     title="Selisih dari harapan, poin persen")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     ticksuffix="%", title="")
    fig.update_layout(margin=dict(b=70, t=64),
                      coloraxis_colorbar=dict(title="Gugur<br>formal %"))
    bagan(fig, 520, None,
          "Garis tegak berada pada nol, yaitu memutus persis seperti "
          "kebiasaan kelompok perkaranya. Garis mendatar pada gaya "
          "mengabulkan yang paling lazim. Titik berwarna merah adalah hakim "
          "yang paling sering menggugurkan perkara pada syarat formal.")


def _karakter_tabel(prof: pd.DataFrame) -> None:
    st.markdown(
        "Tabel lengkapnya, **diurutkan menurut nama, bukan menurut peringkat "
        "apa pun.** Urutan menurut angka akan mengundang pembacaan sebagai "
        "papan peringkat, padahal tingkat dikabulkan tinggi atau rendah "
        "tidak berarti benar atau salah.\n\n"
        "Kolom **Batas bawah** dan **Batas atas** adalah rentang "
        "ketidakpastian tingkat dikabulkan. Dua hakim yang rentangnya masih "
        "bersinggungan belum dapat dinyatakan berbeda.")
    t = prof[["Hakim", "Periode", "Putusan", "Dikabulkan",
              "Selisih dari harapan", "Kabul sebagian", "Gugur formal",
              "Median jeda hari", "Batas bawah", "Batas atas"]].copy()
    t = t.round({"Dikabulkan": 1, "Selisih dari harapan": 1,
                 "Kabul sebagian": 1, "Gugur formal": 1,
                 "Median jeda hari": 0}).sort_values("Hakim")
    tabel_bernavigasi(
        t, "karakter_hakim", kelas="rata",
        kolom_persen=("Dikabulkan", "Selisih dari harapan", "Kabul sebagian",
                      "Gugur formal", "Batas bawah", "Batas atas"))


# ---------------------------------------------------------------------------
# Panduan analisis: menjelaskan empat dimensi dengan bahasa sehari hari
# ---------------------------------------------------------------------------

def hal_panduan() -> None:
    """
    Halaman penjelasan dimensi analisis, ditulis untuk orang awam.

    Tiap halaman dashboard membawa penanda dimensi seperti diagnostik atau
    prediktif, dan istilah itu tidak pernah dijelaskan di mana pun. Pembaca
    yang tidak berlatar analitik hanya bisa menebak. Halaman ini menjelaskan
    keempatnya dengan satu perumpamaan yang sudah dikenal semua orang, yaitu
    urutan berpikir seorang dokter, lalu menunjukkan halaman mana menjawab
    pertanyaan apa.
    """
    st.caption(
        "Arti penanda dimensi yang tampil di tiap halaman, dijelaskan "
        "dengan bahasa sehari hari, beserta peta halaman mana menjawab "
        "pertanyaan apa.")

    st.markdown(
        "Dashboard ini menyusun analisisnya dalam empat tingkatan, dan "
        "cara paling mudah memahaminya adalah urutan berpikir seorang "
        "dokter.\n\n"
        "Dokter mulai dengan **memeriksa keadaan**: berapa tekanan darah, "
        "berapa suhu badan. Lalu **mencari sebab**: kenapa demamnya tidak "
        "turun. Lalu **memperkirakan ke depan**: berapa lama pemulihannya. "
        "Terakhir **menentukan tindakan**: obat apa yang diminum. Empat "
        "langkah itu persis empat dimensi di dashboard ini.")

    def bagian(judul, tanya, isi, daftar):
        st.html(f'<div class="tingkat">{judul}</div>')
        st.markdown(f"**Pertanyaannya: {tanya}**\n\n{isi}")
        for tanya_hal, tujuan in daftar:
            if st.button(tanya_hal, key=f"pandu-{TV.kunci_nav(tujuan)}-"
                         f"{hash(tanya_hal) & 0xffff}", width="stretch"):
                st.session_state["nav_tujuan"] = tujuan
                st.rerun()

    bagian(
        "Deskriptif · Memeriksa Keadaan",
        "apa yang sedang terjadi?",
        "Menghitung dan menyajikan keadaan apa adanya, tanpa menafsirkan. "
        "Seperti dokter membaca hasil laboratorium: angkanya dulu, "
        "kesimpulannya belakangan. Contohnya berapa banyak sengketa per "
        "tahun, berapa nilai yang diperebutkan, dan siapa saja hakimnya.",
        [("Berapa nilai sengketa dan berapa yang dikoreksi pengadilan?",
          "Nilai Sengketa"),
         ("Bagaimana keadaan sengketa secara keseluruhan?",
          "Ringkasan Eksekutif"),
         ("Siapa hakimnya dan bagaimana rekam jejaknya?", "Profil Hakim")])

    bagian(
        "Diagnostik · Mencari Sebab",
        "mengapa itu terjadi?",
        "Membedah keadaan untuk menemukan sumber persoalannya. Kalau enam "
        "dari sepuluh ketetapan yang disengketakan berujung dikoreksi, "
        "dimensi ini mencari di mana persisnya: jenis koreksi apa yang "
        "paling sering gugur, unit mana yang paling sering kalah, tema apa "
        "yang terus berulang. Ini bahan utama pembenahan.",
        [("Ketetapan jenis apa yang paling sering dikoreksi, dan kenapa?",
          "Mutu Ketetapan"),
         ("Apa yang sebenarnya paling sering dipersengketakan?",
          "Tema Sengketa"),
         ("Siapa yang bersengketa berulang kali dengan hasil sama?",
          "Sengketa Berulang"),
         ("Apakah perkara sejenis diputus serupa?",
          "Konsistensi Putusan Hakim"),
         ("Pasal apa yang paling menentukan kalah menang?", "Pasal Penentu"),
         ("Unit mana yang ketetapannya paling sering gugur?",
          "Unit Penerbit Ketetapan")])

    bagian(
        "Prediktif · Memperkirakan ke Depan",
        "apa yang kira kira akan terjadi?",
        "Memperkirakan yang belum terjadi dari pola yang sudah terjadi, "
        "selalu dengan rentang, bukan angka tunggal. Ada satu batas yang "
        "dijaga ketat di seluruh dashboard ini: **hasil perkara "
        "perseorangan tidak pernah diramalkan**, karena tiap perkara punya "
        "bukti dan keadaannya sendiri. Yang diperkirakan hanya hal yang "
        "sah diperkirakan: lamanya proses, banyaknya perkara, dan pola "
        "kelompok perkara sejenis.",
        [("Perkara seperti punya saya biasanya berakhir bagaimana?",
          "Pola Putusan Sejenis"),
         ("Berapa lama perkara saya kira kira berproses?",
          "Durasi Penyelesaian Sengketa"),
         ("Berapa banyak perkara yang akan masuk tahun depan?",
          "Ringkasan Eksekutif")])

    bagian(
        "Preskriptif · Menentukan Tindakan",
        "lalu sebaiknya berbuat apa?",
        "Mengubah temuan menjadi saran tindakan beserta taksiran "
        "dampaknya. Di dashboard ini bentuknya tiga: saran jalur upaya "
        "hukum bagi wajib pajak, catatan tindakan bertanda biru di kaki "
        "halaman analisis, dan simulasi yang menghitung berapa rupiah "
        "nilai yang terselamatkan bila mutu ketetapan diperbaiki.",
        [("Jalur mana yang sebaiknya saya tempuh?", "Pilihan Upaya Hukum"),
         ("Kalau mutu diperbaiki, berapa nilai dampaknya?",
          "Nilai Sengketa")])

    st.html(TV.catatan_siap(
        "Satu hal yang berlaku di seluruh dashboard.",
        "Setiap angka berdiri di atas data yang kelengkapannya berbeda, dan "
        "pita di kaki tiap halaman menyatakan seberapa lengkap data di "
        "balik halaman itu. Angka pada bagian hijau boleh dipegang, angka "
        "pada bagian kuning atau merah sebaiknya dibaca sebagai perkiraan. "
        "Membaca dashboard dengan sehat berarti membaca angkanya bersama "
        "batas datanya."))


# ---------------------------------------------------------------------------
# Beranda tiap modul peran
# ---------------------------------------------------------------------------

def _beranda_tanya(daftar: list) -> None:
    """
    Daftar pertanyaan yang tiap barisnya membawa ke halaman jawabannya.

    Tombolnya memakai jalur nav_tujuan yang sama dengan drill antar halaman,
    sehingga tujuan yang tidak tersedia pada modul terpilih otomatis
    memulangkan modul ke Semua lebih dulu.
    """
    st.html('<div class="tingkat">Pertanyaan yang Dapat Dijawab</div>')
    for tanya, tujuan in daftar:
        if st.button(tanya, key=f"beranda-{TV.kunci_nav(tujuan)}-{hash(tanya) & 0xffff}",
                     width="stretch"):
            st.session_state["nav_tujuan"] = tujuan
            st.rerun()


def hal_beranda() -> None:
    """
    Halaman pembuka per peran: tiga angka terpenting beserta peta jalannya.

    Tanpa halaman ini semua peran mendarat di Ringkasan Eksekutif yang sama,
    dan menit pertama pemakaian habis untuk menebak nebak menu. Tiga angka
    di atas dipilih menurut pertanyaan yang paling sering diajukan peran
    itu, bukan menurut apa yang paling mudah dihitung.
    """
    dd = beramar(d)
    n_menang = int(dd["amar"].isin(AMAR_MENANG).sum())
    tingkat = 100 * n_menang / max(len(dd), 1)
    gugur = d[d["amar"] == "tidak_dapat_diterima"]
    p_gugur = 100 * len(gugur) / max(int(d["amar"].notna().sum()), 1)

    if modul == "Pimpinan":
        st.subheader("Beranda Pimpinan")
        st.caption("Keadaan sengketa dalam satu pandangan, untuk pengambilan "
                   "kebijakan.")
        rs = resmi_lingkup()
        ada = (rs[rs["mata_uang"] == "Rupiah"]
               .dropna(subset=["nilai_awal", "nilai_akhir"])
               if not rs.empty else pd.DataFrame())
        k = st.columns(3)
        if not ada.empty:
            k[0].html(TV.kartu(
                "Dikoreksi pengadilan",
                f"Rp {(ada['nilai_awal'] - ada['nilai_akhir']).sum() / 1e12:,.1f} T",
                "nilai resmi 2021 sampai 2025"))
        k[1].html(TV.kartu("Ketetapan yang disengketakan berujung dikoreksi",
                           f"{tingkat:.1f} %",
                           f"dari {len(dd):,} putusan beramar dalam lingkup"))
        t = _deret_tahunan(dd)
        if len(t) >= 6:
            r_awal = 100 * t.head(3)["menang"].sum() / t.head(3)["Putusan"].sum()
            r_akhir = 100 * t.tail(3)["menang"].sum() / t.tail(3)["Putusan"].sum()
            k[2].html(TV.kartu("Perubahan tiga tahun terakhir",
                               f"{r_akhir - r_awal:+.1f} poin",
                               "dibanding tiga tahun pertama arsip; naik "
                               "berarti makin sering dikoreksi"))
        _beranda_tanya([
            ("Berapa nilai yang dikoreksi pengadilan, dan berapa yang dapat "
             "diselamatkan bila mutu diperbaiki?", "Nilai Sengketa"),
            ("Apakah mutu ketetapan membaik atau memburuk dari tahun ke "
             "tahun?", "Mutu Ketetapan"),
            ("Siapa wajib pajak yang terus menerus bersengketa dengan hasil "
             "yang selalu sama?", "Sengketa Berulang"),
            ("Berapa lama sengketa diselesaikan, dan di mana lambatnya?",
             "Durasi Penyelesaian Sengketa"),
        ])

    elif modul == "Fiskus":
        st.subheader("Beranda Fiskus")
        st.caption("Titik masuk pembenahan mutu ketetapan, dari koreksi yang "
                   "paling sering gugur sampai pasal yang menentukannya.")
        k = st.columns(3)
        k[0].html(TV.kartu("Ketetapan yang disengketakan berujung dikoreksi",
                           f"{tingkat:.1f} %",
                           f"dari {len(dd):,} putusan beramar dalam lingkup"))
        kor = ledak_koreksi(dd)
        if not kor.empty:
            gk = (kor.groupby("Jenis koreksi")
                  .agg(n=("doc_id", "nunique"), m=("menang", "sum")))
            gk = gk[gk["n"] >= 5]
            if not gk.empty:
                gk["bobot"] = gk["m"]
                teratas = gk["bobot"].idxmax()
                k[1].html(TV.kartu("Koreksi paling banyak menimbulkan "
                                   "pembatalan", str(teratas),
                                   f"sekitar {int(gk.loc[teratas, 'bobot']):,} "
                                   "ketetapan batal karena koreksi ini"))
        k[2].html(TV.kartu("Gugur sebelum pokok sengketa",
                           f"{p_gugur:.1f} %",
                           "seluruhnya dapat dicegah sejak pendaftaran"))
        _beranda_tanya([
            ("Jenis ketetapan dan koreksi mana yang paling sering gugur di "
             "pengadilan?", "Mutu Ketetapan"),
            ("Pasal apa yang paling sering menjadi dasar pembatalan?",
             "Pasal Penentu"),
            ("Unit mana yang ketetapannya paling sering dikoreksi?",
             "Unit Penerbit Ketetapan"),
            ("Apakah perkara sejenis diputus konsisten?",
             "Konsistensi Putusan Hakim"),
        ])

    else:
        st.subheader("Beranda Wajib Pajak")
        st.caption("Bekal sebelum memutuskan mengajukan upaya hukum: peluang "
                   "historisnya, lamanya, dan jebakan yang paling merugikan.")
        k = st.columns(3)
        k[0].html(TV.kartu("Perkara serupa yang dikabulkan secara historis",
                           f"{tingkat:.1f} %",
                           f"dari {len(dd):,} putusan beramar; bukan ramalan "
                           "atas perkara mana pun"))
        jeda = jeda_hari(d)
        if len(jeda):
            k[1].html(TV.kartu("Median lama menunggu pengucapan",
                               f"{jeda.median():,.0f} hari",
                               "dari musyawarah sampai putusan diucapkan"))
        k[2].html(TV.kartu("Gugur tanpa pernah diperiksa",
                           f"{p_gugur:.1f} %",
                           "umumnya karena lewat tenggat atau salah jalur"))
        _beranda_tanya([
            ("Bagaimana nasib perkara yang mirip perkara saya?",
             "Pola Putusan Sejenis"),
            ("Jalur mana yang sebaiknya ditempuh, banding atau gugatan?",
             "Pilihan Upaya Hukum"),
            ("Bagaimana mencari putusan tentang persoalan saya?",
             "Risalah Putusan"),
            ("Apa yang membuat perkara gugur tanpa pernah diperiksa?",
             "Mutu Ketetapan"),
        ])


# ---------------------------------------------------------------------------
# Pita keandalan, digambar di kepala tiap halaman analisis.
#
# Tiap halaman bertumpu pada ruas yang berbeda, dan kelengkapannya berbeda
# jauh. Daftar di bawah menyebut ruas penopang tiap halaman, dan pitanya
# menghitung kelengkapan pada lingkup yang sedang tampil, bukan pada seluruh
# arsip, supaya angkanya ikut berubah ketika penyaring tahun digeser.
# Metodologi tidak diberi pita karena sudah memuat tabel kelengkapan
# lengkap. Letaknya di kepala halaman, bukan di kaki: pembaca perlu tahu
# seberapa lengkap datanya sebelum membaca angkanya, bukan sesudah.
# ---------------------------------------------------------------------------

RUAS_ANDAL = {
    "Ringkasan Eksekutif": [("Amar", "amar"), ("Tanggal ucap", "tanggal_ucap"),
                            ("Jenis ketetapan", "jenis_ketetapan")],
    "Risalah Putusan": [("Nomor putusan", "nomor_putusan_raw"),
                        ("Amar", "amar"), ("Nama pemohon", "nama_pemohon")],
    "Pola Putusan Sejenis": [("Amar", "amar"),
                             ("Jenis pajak", "kode_jenis_pajak"),
                             ("Jenis koreksi", "jenis_koreksi")],
    "Pilihan Upaya Hukum": [("Jenis perkara", "jenis_perkara"),
                            ("Amar", "amar"),
                            ("Tanggal ucap", "tanggal_ucap")],
    "Konsistensi Putusan Hakim": [("Amar", "amar"),
                                  ("Kode majelis", "kode_majelis"),
                                  ("Hakim ketua", "hakim_ketua")],
    "Tema Sengketa": [("Jenis koreksi", "jenis_koreksi"),
                      ("Pokok sengketa", "pokok_sengketa"),
                      ("Amar", "amar")],
    "Sengketa Berulang": [("Nama pemohon", "nama_pemohon_norm"),
                          ("Amar", "amar"),
                          ("Jenis koreksi", "jenis_koreksi")],
    "Mutu Ketetapan": [("Jenis ketetapan", "jenis_ketetapan"),
                       ("Jenis koreksi", "jenis_koreksi"), ("Amar", "amar"),
                       ("Instansi", "instansi_terbanding")],
    "Pasal Penentu": [("Amar", "amar"),
                      ("Jenis ketetapan", "jenis_ketetapan")],
    "Unit Penerbit Ketetapan": [("Unit penerbit", "unit_penerbit"),
                                ("Amar", "amar")],
    "Banding Unit": [("Amar", "amar"),
                     ("Instansi", "instansi_terbanding"),
                     ("Jenis koreksi", "jenis_koreksi")],
    "Karakter Memutus": [("Hakim ketua", "hakim_ketua"),
                         ("Amar", "amar"),
                         ("Jenis pajak", "kode_jenis_pajak")],
    "Profil Hakim": [("Hakim ketua", "hakim_ketua"),
                     ("Hakim anggota", "hakim_anggota"),
                     ("Tanggal ucap", "tanggal_ucap")],
    "Durasi Penyelesaian Sengketa": [("Tanggal ucap", "tanggal_ucap"),
                                     ("Tanggal musyawarah",
                                      "tanggal_musyawarah")],
}

if halaman in RUAS_ANDAL and not d.empty:
    isi_pita = [(lab, 100 * d[kol].notna().mean())
                for lab, kol in RUAS_ANDAL[halaman] if kol in d]
    if isi_pita:
        st.html(TV.pita_andal(isi_pita, len(d)))
elif halaman == "Nilai Sengketa":
    # Halaman ini bersumber daftar resmi, bukan arsip risalah, sehingga
    # ruas yang dinilai berbeda: nilai awal dan akhir per putusan.
    _rs = resmi_lingkup()
    if not _rs.empty:
        st.html(TV.pita_andal(
            [("Nilai awal", 100 * _rs["nilai_awal"].notna().mean()),
             ("Nilai akhir", 100 * _rs["nilai_akhir"].notna().mean()),
             ("Amar", 100 * _rs["amar"].notna().mean())], len(_rs)))


# ---------------------------------------------------------------------------
# Penyalur dan kaki
# ---------------------------------------------------------------------------

{
    "Beranda": hal_beranda,
    "Ringkasan Eksekutif": hal_ikhtisar,
    "Nilai Sengketa": hal_nilai,
    "Risalah Putusan": hal_telusur,
    "Pola Putusan Sejenis": hal_belajar,
    "Pilihan Upaya Hukum": hal_jalur,
    "Pasal Penentu": hal_dasar,
    "Unit Penerbit Ketetapan": hal_unit,
    "Konsistensi Putusan Hakim": hal_konsistensi,
    "Sengketa Berulang": hal_berulang,
    "Tema Sengketa": hal_tema,
    "Mutu Ketetapan": hal_ketetapan,
    "Profil Hakim": hal_hakim,
    "Durasi Penyelesaian Sengketa": hal_kinerja,
    "Karakter Memutus": hal_karakter,
    "Banding Unit": hal_banding,
    "Panduan Analisis": hal_panduan,
    "Metodologi": hal_metode,
}[halaman]()

_t = keadaan_tarikan()
if _t["menit"] is None:
    _ket = "belum terdapat unduhan"
elif _t["menit"] < 1:
    _ket = "baru saja"
elif _t["menit"] < 90:
    _ket = f"{_t['menit']:.0f} menit lalu"
else:
    _ket = f"{_t['menit'] / 60:.1f} jam lalu"

# Sisi kanan kaki dikosongkan. Judulnya sudah terbaca di bilah judul, dan
# mengulangnya di kaki hanya menambah tulisan tanpa menambah keterangan.
st.html(TV.kaki("Donny Maha Putra",
                f"<b>{corong['unduh']:,}</b> berkas · {corong['gb']:.0f} GB · "
                f"cakupan <b>{cakupan:.1f}%</b> · "
                f"<b>{corong['urai']:,}</b> putusan terurai",
                _ket, bool(_t["aktif"]), ""))

st.components.v1.html(TV.PAKU_TETAP, height=0)
