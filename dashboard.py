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


@st.cache_data(ttl=120)
def muat_putusan() -> pd.DataFrame:
    with sambung() as c:
        df = pd.read_sql_query("SELECT * FROM putusan", c)
    for k, peta in (("amar", LABEL_AMAR),
                    ("instansi_terbanding", LABEL_INSTANSI),
                    ("jenis_perkara", LABEL_PERKARA)):
        if k in df:
            df[k + "_label"] = df[k].map(peta).fillna("Tidak dikenali")
    return df


@st.cache_data(ttl=120)
def muat_corong() -> dict:
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


@st.cache_data(ttl=600)
def muat_resmi() -> pd.DataFrame:
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


@st.cache_data(ttl=300)
def peta_kode() -> dict:
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


def label_kode(kode, peta: dict) -> str:
    if kode is None or (isinstance(kode, float) and math.isnan(kode)):
        return "tidak dikenali"
    info = peta.get(str(kode))
    if not info:
        return f"{kode} · belum teridentifikasi"
    return f"{kode} · {info['label']}" + (" (?)" if info["pangsa"] < 80 else "")


@st.cache_data(ttl=30)
def keadaan_tarikan() -> dict:
    import datetime as _dt

    with sambung() as c:
        try:
            terakhir = c.execute(
                "SELECT MAX(fetched_at) FROM docs").fetchone()[0]
        except sqlite3.OperationalError:
            terakhir = None
    if not terakhir:
        return {"aktif": False, "menit": None}
    try:
        t = _dt.datetime.fromisoformat(terakhir)
        menit = (_dt.datetime.now(_dt.timezone.utc) - t).total_seconds() / 60
    except ValueError:
        return {"aktif": False, "menit": None}
    return {"aktif": menit < 5, "menit": menit}


@st.cache_data(ttl=120)
def muat_dasar_hukum() -> pd.DataFrame:
    with sambung() as c:
        return pd.read_sql_query(
            "SELECT doc_id, pasal, ayat, uu_nomor, uu_tahun, uu_nama, "
            "asal_konteks FROM dasar_hukum", c)


def cari_teks(kueri: str, batas: int) -> pd.DataFrame:
    with sambung() as c:
        return pd.read_sql_query(
            """SELECT f.doc_id,
                      snippet(putusan_fts, 2, '**', '**', ' … ', 24) AS cuplikan
               FROM putusan_fts f WHERE putusan_fts MATCH ?
               ORDER BY rank LIMIT ?""", c, params=(kueri, batas))


@st.cache_data(ttl=300)
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
            st.html(TV.tabel(tabel))
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

st.html(TV.kop("Dashboard Analitik Sengketa Pajak",
               "Analitik Risalah Putusan Pengadilan Pajak · Sumber data: "
               "https://setpp.kemenkeu.go.id/risalah", ""))

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
           "Sengketa Berulang", "Mutu Ketetapan",
           "Pasal Penentu", "Unit Penerbit Ketetapan",
           "Profil Hakim", "Durasi Penyelesaian Sengketa", "Metodologi"]
DIMENSI = {"Nilai Sengketa": "Deskriptif, data resmi",
           "Pola Putusan Sejenis": "Prediktif, frekuensi historis",
           "Pilihan Upaya Hukum": "Preskriptif",
           "Konsistensi Putusan Hakim": "Diagnostik",
           "Sengketa Berulang": "Diagnostik",
           "Mutu Ketetapan": "Diagnostik",
           "Pasal Penentu": "Diagnostik",
           "Unit Penerbit Ketetapan": "Diagnostik",
           "Profil Hakim": "Deskriptif",
           "Durasi Penyelesaian Sengketa": "Prediktif"}

# Tiga modul pengguna. Telusur putusan dan Catatan metode ada di semua modul:
# yang pertama tujuan setiap drill, yang kedua kejujuran metodologis yang
# tidak boleh disembunyikan dari siapa pun.
MODUL = {
    "Semua": HALAMAN,
    "Pimpinan": ["Ringkasan Eksekutif", "Nilai Sengketa", "Risalah Putusan",
                 "Konsistensi Putusan Hakim", "Sengketa Berulang", "Profil Hakim",
                 "Durasi Penyelesaian Sengketa", "Metodologi"],
    "Fiskus": ["Ringkasan Eksekutif", "Mutu Ketetapan",
               "Pasal Penentu", "Unit Penerbit Ketetapan",
               "Konsistensi Putusan Hakim", "Risalah Putusan", "Metodologi"],
    "Wajib pajak": ["Ringkasan Eksekutif", "Pola Putusan Sejenis",
                    "Pilihan Upaya Hukum", "Risalah Putusan",
                    "Metodologi"],
}

cari_cepat = st.sidebar.text_input(
    "Cari cepat", key="cari_cepat", placeholder="Cari isi putusan...",
    label_visibility="collapsed")
if cari_cepat.strip():
    st.session_state["q_isi"] = cari_cepat.strip()
    # Kata kunci baru langsung membawa ke halaman telusur.
    if st.session_state.get("cari_lalu") != cari_cepat.strip():
        st.session_state["cari_lalu"] = cari_cepat.strip()
        st.session_state["nav_tujuan"] = "Risalah Putusan"

# Bila tujuan drill tidak tersedia pada modul terpilih, modul dipulangkan ke
# Semua lebih dulu, sebelum pemilih modulnya digambar.
_tujuan = st.session_state.get("nav_tujuan")
if (_tujuan in HALAMAN
        and _tujuan not in MODUL.get(st.session_state.get("modul", "Semua"),
                                     HALAMAN)):
    st.session_state["modul"] = "Semua"

st.sidebar.html('<div class="sb-judul">Modul pengguna</div>')
modul = st.sidebar.selectbox("Modul pengguna", list(MODUL), key="modul",
                             label_visibility="collapsed")
daftar_hal = MODUL[modul]

# Perpindahan halaman lewat kode, misalnya drill dari daftar nomor putusan
# di halaman lain, dititipkan pada nav_tujuan lalu diterapkan di sini,
# sebelum pemilih halamannya digambar. Menulis langsung ke keadaan pemilih
# setelah pemilihnya tergambar dilarang Streamlit.
if st.session_state.get("nav_tujuan") in HALAMAN:
    st.session_state["nav"] = st.session_state.pop("nav_tujuan")
# Pilihan baris pada daftar asal drill dibersihkan di sini, sebelum daftarnya
# digambar ulang, supaya drill tidak terpicu lagi saat pengguna kembali.
if st.session_state.get("hapus_kunci"):
    st.session_state.pop(st.session_state.pop("hapus_kunci"), None)
# Halaman terpilih dapat hilang dari daftar ketika modul berganti.
if st.session_state.get("nav") not in daftar_hal:
    st.session_state["nav"] = daftar_hal[0]

st.sidebar.html('<div class="sb-judul">Halaman</div>')
# Menu berupa tombol, bukan pilihan bulat: yang dimaksud pengguna adalah
# berpindah halaman, bukan mencentang sesuatu. Kuncinya juga menjadi sasaran
# gaya, sehingga ikon dan penanda terpilih tidak bergantung urutan unsur.
halaman = st.session_state["nav"]
st.html(TV.ikon_nav(daftar_hal, halaman, GELAP))
# Seluruh tombol menu dikumpulkan dalam satu wadah bernama, supaya jarak
# antar barisnya dapat dirapatkan sekaligus tanpa mengganggu jarak antar
# unsur lain di bilah samping.
with st.sidebar.container(key="menu-nav"):
    for _h in daftar_hal:
        if st.button(_h, key=TV.kunci_nav(_h), width="stretch"):
            if _h != halaman:
                st.session_state["nav"] = _h
                st.session_state.pop("buka_doc", None)
                st.rerun()

st.sidebar.html('<div class="sb-judul">Ruang lingkup data</div>')
st.sidebar.caption("Menentukan populasi yang diamati pada seluruh halaman.")

kode_peta = peta_kode()
tahun_ada = sorted(int(t) for t in df["tahun_putusan"].dropna().unique())
if len(tahun_ada) > 1:
    th = st.sidebar.slider("Tahun putusan", min(tahun_ada), max(tahun_ada),
                           (min(tahun_ada), max(tahun_ada)))
else:
    th = None

hanya_teks = st.sidebar.checkbox(
    "Hanya dokumen berlapis teks asli", value=False,
    help="Mengeluarkan dokumen hasil pengenalan karakter optis, yang "
         "keandalannya pada angka dan nomor pasal lebih rendah.")

d = df.copy()
if th:
    d = d[d["tahun_putusan"].between(th[0], th[1]) | d["tahun_putusan"].isna()]
if hanya_teks:
    d = d[d["sumber_teks"] != "ocr"]

st.sidebar.caption(f"{len(d):,} dari {len(df):,} putusan dalam lingkup.")

if halaman in DIMENSI:
    st.html(f'<div class="tingkat">Dimensi {DIMENSI[halaman]}</div>')


# ---------------------------------------------------------------------------
# 1. Ringkasan eksekutif
# ---------------------------------------------------------------------------

def hal_ikhtisar() -> None:
    dd = beramar(d)
    n_menang = int(dd["amar"].isin(AMAR_MENANG).sum())
    pangsa = 100 * n_menang / len(dd) if len(dd) else 0
    j = jeda_hari(d)
    n_formal = int((d["amar"] == "tidak_dapat_diterima").sum())

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
    rs = muat_resmi()
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
    st.markdown(
        f"**{kj_menang:.0f} persen ketetapan yang disengketakan berujung "
        f"dikabulkan** seluruhnya atau sebagian, dihitung dari {len(kj):,} "
        "putusan yang jenis ketetapannya teridentifikasi. Rinciannya pada "
        "halaman Mutu Ketetapan.\n\n"
        f"**{ulang:.0f} persen sengketa datang dari wajib pajak yang "
        "bersengketa lebih dari sekali.** Rinciannya pada halaman Sengketa "
        "Berulang.\n\n"
        "**Terdapat kelompok perkara yang putusannya bervariasi tiga arah** "
        "pada "
        "perkara sejenis, dan sebagian lain sangat seragam. Peta lengkapnya "
        "pada "
        "halaman Konsistensi Putusan Hakim.")

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


# ---------------------------------------------------------------------------
# Nilai sengketa, dari daftar resmi
# ---------------------------------------------------------------------------

def hal_nilai() -> None:
    st.subheader("Nilai Sengketa")
    rs = muat_resmi()
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

    st.html('<div class="tingkat">Konsentrasi Nilai Sengketa</div>')
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
        f"Di luar seluruh angka halaman ini ada {len(va):,} sengketa "
        "bervaluta asing, hampir semuanya dolar AS, umumnya perkara "
        "kepabeanan dan transfer pricing, yang tidak dijumlahkan ke total "
        "Rupiah.")


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
    judul = tampil(r["nomor_putusan_raw"], f"Dokumen {r['doc_id']}")

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
            judul = tampil(r["nomor_putusan_raw"], f"Dokumen {r['doc_id']}")
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
    with kiri:
        st.subheader("Risalah Putusan")
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

    aktif = [(n, v.strip()) for n, v in (
        ("Nomor", q_nomor), ("Wajib pajak", q_wp), ("Hakim", q_hakim),
        ("Unit", q_unit), ("Isi", q_isi)) if v and v.strip()]
    if aktif:
        st.html('<div class="saring">' + "".join(
            f'<span class="chip"><b>{n}</b> {v[:28]}</span>'
            for n, v in aktif) + "</div>")

    h = d.copy()
    if q_nomor.strip():
        h = h[h["nomor_putusan_raw"].fillna("").str.contains(
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
        st.info(f"Ruas {dim_nama.lower()} belum terisi pada putusan terpilih.")
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
        st.info(f"{len(h):,} putusan terbagi ke dalam {len(kel)} kelompok "
                f"menurut {dim_nama.lower()}. Pilih salah satu batang untuk menampilkan rinciannya.")
        return
    if nilai_kel == LAINNYA:
        st.info("Kelompok gabungan ini berisi campuran kelompok kecil dan "
                "tidak dapat dimasuki. Rinciannya tersedia pada panel tabel "
                "di "
                "bawah bagan, atau populasinya dipersempit melalui panel "
                "penyaringan.")
        return
    if len(kel) > 14 and nilai_kel not in set(pot[dim_nama]):
        st.info("Kelompok itu di luar empat belas terbesar. Populasi perlu dipersempit terlebih dahulu melalui panel "
            "penyaringan.")
        return

    hk = h[h["doc_id"].isin(set(sumber[sumber["nilai"] == nilai_kel]["doc_id"]))]
    hk = hk.sort_values("tahun_putusan", ascending=False, na_position="last")

    st.html(f'<div class="jejak">Dalam lingkup <b>{len(h):,}</b><i>›</i>'
            f'{dim_nama} <b>{nilai_kel}</b><i>›</i><b>{len(hk):,}</b> '
            'putusan</div>')
    st.html('<div class="tingkat">Tahap 2 · Daftar Putusan</div>')
    st.caption("Pilih salah satu baris untuk menampilkan isi putusannya.")

    ringkas = pd.DataFrame({
        "Nomor putusan": hk["nomor_putusan_raw"].fillna("tidak dikenali"),
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

    baris2 = pilih2.selection.rows if pilih2 and pilih2.selection else []
    if not baris2:
        return
    r = hk.iloc[baris2[0]]

    judul = tampil(r["nomor_putusan_raw"], f"Dokumen {r['doc_id']}")
    st.html(f'<div class="jejak">{dim_nama} <b>{nilai_kel}</b><i>›</i>'
            f'Putusan <b>{judul}</b></div>')
    st.html('<div class="tingkat">Tahap 3 · Isi Putusan</div>')
    tampil_detail(r, cuplikan, q_isi)


# ---------------------------------------------------------------------------
# 3. Pola putusan sejenis
# ---------------------------------------------------------------------------

def hal_belajar() -> None:
    st.subheader("Pola Putusan Sejenis")
    st.caption(
        "Setelah ciri perkara dipilih, halaman ini menyajikan rekam jejak "
        "historisnya: "
        "bagaimana perkara serupa diputus, argumen hukum apa yang menyertai "
        "yang dikabulkan, serta aspek formal apa yang menggugurkan perkara. "
        "Seluruh "
        "angka adalah frekuensi historis atas putusan yang telah dijatuhkan, "
        "bukan "
        "ramalan atas perkara Anda.")

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
    dh = dh[dh["doc_id"].isin(menang_id) & dh["uu_nomor"].notna()]
    if dh.empty:
        st.info("Belum terdapat rujukan dasar hukum pada kelompok ini.")
    else:
        dh = dh.assign(rujukan="Pasal " + dh["pasal"].astype(str) + " "
                       + dh["uu_nama"].fillna("UU " + dh["uu_nomor"].astype(str)))
        r = (dh.groupby("rujukan")["doc_id"].nunique()
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
    pilih_baca = st.dataframe(
        pd.DataFrame({
            "Nomor putusan": daftar["nomor_putusan_raw"]
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
    st.subheader("Pilihan Upaya Hukum")
    st.caption(
        "Halaman ini membantu wajib pajak menentukan jalur pengajuan "
        "sengketa sebelum perkara didaftarkan. Disajikan peluang "
        "keberhasilan tiap jalur menurut putusan yang telah dijatuhkan, "
        "tenggat waktu yang mengikat, serta risiko yang jarang disadari. "
        "Seluruh angka merupakan frekuensi historis, bukan nasihat hukum "
        "atas perkara tertentu.")

    rs = muat_resmi()
    if rs.empty:
        st.info("Halaman ini membutuhkan daftar resmi. Jalankan "
                "setpp_resmi.py impor terlebih dahulu.")
        return

    rs = saring_tahun(rs, "tahun_ucap", "tahun_jalur")
    if rs.empty:
        st.info("Tidak terdapat putusan pada rentang tahun tersebut.")
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
    k[2].html(TV.kartu("Pajak justru bertambah", f"{n_add:,}",
                       "putusan menambah pajak yang harus dibayar, 2021 "
                       "sampai 2025"))

    baris = []
    for nama, grp in (("Banding", b), ("Gugatan", g)):
        n = max(1, len(grp))
        baris += [
            {"Jalur": nama, "Amar": "Dikabulkan",
             "Pangsa": 100 * int(grp["menang"].sum()) / n},
            {"Jalur": nama, "Amar": "Ditolak",
             "Pangsa": 100 * int((grp["amar"] == "tolak").sum()) / n},
            {"Jalur": nama, "Amar": "Tidak dapat diterima",
             "Pangsa": 100 * int((grp["amar"]
                                  == "tidak_dapat_diterima").sum()) / n}]
    tj = pd.DataFrame(baris)
    tj["Ket"] = tj["Pangsa"].map(lambda v: f"{v:.1f}%")
    fig = px.bar(tj, x="Jalur", y="Pangsa", color="Amar", barmode="group",
                 text="Ket", title="Nasib perkara menurut jalur, data resmi")
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
    st.subheader("Konsistensi Putusan Hakim")
    st.caption(
        "Perkara yang sejenis semestinya diputus serupa, siapa pun "
        "hakimnya. Halaman ini memeriksa hal itu dari dua sisi. Bagian "
        "pertama melihat kelompok perkara: apakah perkara dengan jenis "
        "pajak dan jenis koreksi yang sama berakhir sama. Bagian kedua "
        "melihat hakimnya: apakah ada hakim yang polanya jauh berbeda dari "
        "rekan-rekannya pada perkara sejenis.")

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
        st.info("Belum terdapat kelompok dengan sedikitnya lima belas putusan.")
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
        st.info("Belum cukup putusan berhakim untuk analisis ini.")
    else:
        dd["menang"] = dd["amar"].isin(AMAR_MENANG)
        laju_kel = dd.groupby("kode_jenis_pajak")["menang"].mean()
        dd["harapan"] = dd["kode_jenis_pajak"].map(laju_kel)
        h = (dd.groupby("hakim_ketua")
             .agg(n=("menang", "size"), aktual=("menang", "mean"),
                  harapan=("harapan", "mean")).reset_index())
        h = h[h["n"] >= 20].copy()
        if h.empty:
            st.info("Belum terdapat hakim ketua dengan dua puluh putusan beramar.")
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
    st.subheader("Sengketa Berulang")
    st.caption(
        "Wajib pajak yang bersengketa berulang kali dengan pokok serupa "
        "menandakan persoalan yang tidak selesai di tingkat keberatan lalu "
        "membebani pengadilan berulang-ulang.")

    n_samar = int((d["nama_disamarkan"] == 1).sum())
    dn = d[(d["nama_disamarkan"] == 0) & d["nama_pemohon_norm"].notna()]
    if dn.empty:
        st.info("Belum terdapat nama pemohon yang terbaca pada lingkup ini.")
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
        st.info("Tidak terdapat wajib pajak dengan dua sengketa atau lebih pada "
                "lingkup ini. Penyaring tahun pada bilah samping dapat "
                "diperlonggar.")
        return

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
    pilih15 = st.dataframe(
        pd.DataFrame(baris), width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row", key="wp_teratas",
        column_config={
            "Dikabulkan": st.column_config.NumberColumn(
                format="%.2f %%", alignment="center")})

    b15 = pilih15.selection.rows if pilih15 and pilih15.selection else []
    if b15:
        nama = urutan[b15[0]]
        target = dn[dn["nama_pemohon_norm"] == nama]
        t = target.sort_values("tahun_putusan", na_position="last")
        st.html(f'<div class="jejak">Wajib pajak '
                f'<b>{str(target["nama_pemohon"].iloc[0])[:40]}</b><i>›</i>'
                f'<b>{len(t):,}</b> sengketa</div>')
        pilih_sen = st.dataframe(
            pd.DataFrame({
                "Nomor putusan": t["nomor_putusan_raw"]
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


# ---------------------------------------------------------------------------
# 6. Ketetapan dan koreksi
# ---------------------------------------------------------------------------

def hal_ketetapan() -> None:
    st.subheader("Mutu Ketetapan")
    st.caption(
        "Menelaah sengketa dari sisi penerbitan, yaitu ketetapan yang "
         "diterbitkan unit beserta koreksi yang mendasarinya.")

    kj = beramar(d)
    kj = kj[kj["jenis_ketetapan"].notna()].copy()
    kj["menang"] = kj["amar"].isin(AMAR_MENANG)
    if kj.empty:
        st.info("Belum terdapat ketetapan yang teridentifikasi jenisnya.")
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

    st.html('<div class="tingkat">Koreksi yang Paling Layak Ditinjau</div>')
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
    fig = px.scatter(gk, x="Putusan", y="Tingkat dikabulkan",
                     text="Jenis koreksi",
                     title="Frekuensi dibandingkan tingkat pembatalan")
    fig.update_traces(mode="markers+text", textposition="top center",
                      textfont=dict(size=10, color=P["tinta_2"]),
                      hovertemplate="%{text}<br>%{x:,} putusan<br>"
                                    "%{y:.1f} persen dikabulkan<extra></extra>")
    fig.add_vline(x=batas_x, line_dash="dot", line_color=P["sumbu"])
    fig.add_hline(y=50, line_dash="dot", line_color=P["sumbu"])
    fig.update_xaxes(showgrid=False, title="Jumlah putusan")
    fig.update_yaxes(showgrid=True, gridcolor=P["garis_bantu"],
                     ticksuffix="%", range=[0, 105],
                     title="Tingkat dikabulkan")
    fig.update_layout(margin=dict(t=64, r=28))
    for x_, y_, teks_, ax_ in (
            (0.99, 1.02, "Sering dan sering batal", "right"),
            (0.01, 1.02, "Jarang tetapi sering batal", "left")):
        fig.add_annotation(text=teks_, xref="paper", yref="paper",
                           x=x_, y=y_, showarrow=False, xanchor=ax_,
                           font=dict(size=11, color=P["tinta_2"]))
    bagan(fig, 460, None,
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


# ---------------------------------------------------------------------------
# Dasar hukum yang menentukan, untuk fiskus
# ---------------------------------------------------------------------------

def hal_dasar() -> None:
    st.subheader("Pasal Penentu")
    st.caption(
        "Rekapitulasi pasal yang paling sering dirujuk ketika ketetapan "
        "dikoreksi "
        "pengadilan, dari arsip risalah yang sudah terurai. Bagi penelaah "
        "keberatan dan penyusun pedoman, pasal-pasal inilah "
            "yang paling menentukan arah pembuktian. Hubungan yang tersaji "
            "berupa kemunculan bersama, bukan sebab akibat.")

    dh = muat_dasar_hukum()
    dd = beramar(d)
    if dh.empty or dd.empty:
        st.info("Belum terdapat rujukan dasar hukum pada lingkup ini.")
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
    du = dh[dh["uu_nomor"].notna()].copy()
    du["Rujukan"] = ("Pasal " + du["pasal"].astype(str) + " "
                     + du["uu_nama"].fillna("UU "
                                            + du["uu_nomor"].astype(str)))
    rk = (du[du["doc_id"].isin(menang_id)]
          .groupby("Rujukan")["doc_id"].nunique())
    rt = (du[du["doc_id"].isin(tolak_id)]
          .groupby("Rujukan")["doc_id"].nunique())
    # Pangsa kehadiran tidak bermakna pada populasi yang sangat kecil. Ketika
    # penyaring menyempit sampai tersisa segelintir putusan dikabulkan, tiap
    # pasal yang kebetulan dirujuk satu putusan akan tampil seratus persen,
    # dan seluruh batang menjadi sama panjang tanpa memberi keterangan apa
    # pun. Karena itu populasinya dijaga, dan pasal yang dirujuk kurang dari
    # tiga putusan tidak ikut ditampilkan.
    if len(menang_id) < 10:
        st.info(
            f"Hanya {len(menang_id)} putusan dikabulkan pada pilihan ini, "
            "terlalu sedikit untuk membaca pasal mana yang menentukan. "
            "Salah satu pilihan dapat diperlonggar.")
        return
    rk = rk[rk >= 3]
    if rk.empty:
        st.info("Belum terdapat pasal yang dirujuk sedikitnya tiga putusan "
                "dikabulkan pada pilihan ini. Salah satu pilihan dapat "
                "diperlonggar.")
        return

    t = (pd.DataFrame({"Dikabulkan merujuk": rk, "Ditolak merujuk": rt})
         .fillna(0).astype(int))
    n_m, n_t = max(1, len(menang_id)), max(1, len(tolak_id))
    t["Pangsa saat dikabulkan"] = (100 * t["Dikabulkan merujuk"] / n_m)
    t["Pangsa saat ditolak"] = (100 * t["Ditolak merujuk"] / n_t)
    t["Selisih poin"] = (t["Pangsa saat dikabulkan"]
                         - t["Pangsa saat ditolak"])
    t = t.sort_values("Dikabulkan merujuk", ascending=False)

    atas = t.head(10).reset_index()
    # Keterangan menyebut kedua sisinya secara utuh. Sebelumnya ditulis
    # "53% lawan 56%", dan kata lawan tidak menerangkan apa yang sedang
    # dibandingkan, sehingga pembaca harus menebak.
    atas["Ket"] = [
        f"{r['Pangsa saat dikabulkan']:.0f}% dikabulkan, "
        f"{r['Pangsa saat ditolak']:.0f}% ditolak"
        for _, r in atas.iterrows()]

    unggul = t.assign(_s=t["Selisih poin"]).sort_values(
        "_s", ascending=False).iloc[0]
    st.markdown(
        "Bagan ini membandingkan **seberapa sering suatu pasal muncul pada "
        "putusan yang dikabulkan dibandingkan pada putusan yang ditolak.** "
        "Panjang batang adalah jumlah putusan dikabulkan yang merujuk pasal "
        "tersebut, sedangkan dua angka di ujungnya adalah pangsa "
        "kehadirannya pada masing-masing kelompok.\n\n"
        f"Sebagai contoh, {unggul.name} hadir pada "
        f"{unggul['Pangsa saat dikabulkan']:.0f} persen putusan yang "
        f"dikabulkan, tetapi hanya {unggul['Pangsa saat ditolak']:.0f} "
        "persen putusan yang ditolak. Selisih "
        f"{unggul['Selisih poin']:.0f} poin itulah yang menjadikannya "
        "penanda arah: ketika pasal ini dibahas dalam pertimbangan, "
        "perkaranya cenderung berakhir dikabulkan.\n\n"
        "Pasal yang pangsanya hampir sama pada kedua kelompok, misalnya 50 "
        "persen berbanding 49 persen, tidak membedakan apa pun. Pasal "
        "seperti itu memang selalu dirujuk pada perkara jenis ini, sehingga "
        "kehadirannya tidak memberi petunjuk tentang arah putusannya. Yang "
        "layak ditelaah adalah pasal yang selisihnya besar.")

    bagan(batang_peringkat(atas, "Rujukan", "Dikabulkan merujuk",
                           "Pasal yang paling sering menyertai koreksi "
                           "pengadilan", "Ket"),
          max(300, 36 * len(atas) + 120), None,
          "Hanya pasal yang dirujuk sedikitnya tiga putusan dikabulkan yang "
          "ditampilkan, karena pangsa yang dihitung dari satu dua putusan "
          "selalu tampak seratus persen tanpa berarti apa pun. Hubungan yang "
          "tersaji berupa kemunculan bersama, bukan sebab akibat.")

    with st.expander("Dua puluh rujukan teratas sebagai tabel"):
        st.html(TV.tabel(
            t.head(20).reset_index()
            .round({"Pangsa saat dikabulkan": 2, "Pangsa saat ditolak": 2,
                    "Selisih poin": 2}),
            kolom_persen=("Pangsa saat dikabulkan", "Pangsa saat ditolak",
                          "Selisih poin")))

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
    st.subheader("Unit Penerbit Ketetapan")
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
        st.info("Belum terdapat unit penerbit yang terbaca pada lingkup ini.")
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
        st.info("Belum terdapat unit dengan sedikitnya lima belas putusan "
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
    st.subheader("Profil Hakim")
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
            st.info("Tidak terdapat putusan pada rentang tahun tersebut.")
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
        st.info("Belum terdapat putusan yang susunan majelisnya terbaca pada "
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

    # Pangsa dikabulkan dihitung atas putusan beramar substantif saja,
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
        st.info("Belum terdapat hakim yang memenuhi ambang tersebut.")
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
        "yang hanya berisi gelar dikeluarkan. Pangsa dikabulkan dihitung "
        "atas putusan beramar substantif, tanpa pembetulan kesalahan tulis "
        "dan tanpa amar yang tidak terbaca. Hakim dengan jumlah putusan "
        "sedikit wajar memperlihatkan pangsa "
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
    st.subheader("Durasi Penyelesaian Sengketa")
    st.caption(
        "Lama penyelesaian perkara dan titik proses yang paling lama "
        "tertahan. Temuan utamanya terletak pada jeda yang jarang dilaporkan, "
        "yaitu antara "
        "putusan diambil di musyawarah dan diucapkan di sidang terbuka.")

    j = jeda_hari(d)
    if len(j) < 20:
        st.info("Belum cukup putusan yang kedua tanggalnya terbaca.")
        return

    k = st.columns(3)
    k[0].html(TV.kartu("Median jeda musyawarah ke pengucapan", f"{j.median():.0f} hari",
                       f"dari {len(j):,} putusan bertanggal lengkap"))
    k[1].html(TV.kartu("Sepersepuluh terlama", f"{j.quantile(0.9):.0f} hari",
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
        st.info("Putusan berpola nomor baru dengan tahun lengkap belum cukup "
                "untuk sebaran lama penyelesaian.")


# ---------------------------------------------------------------------------
# 9. Catatan metode
# ---------------------------------------------------------------------------

def hal_metode() -> None:
    st.subheader("Metodologi")
    st.markdown(
        "Seluruh dokumen diambil dari laman Sekretariat Pengadilan Pajak, "
        "yang menyediakannya untuk diakses umum. Setiap berkas disimpan tanpa "
        "perubahan beserta nilai hash SHA-256, sehingga setiap angka pada "
        "dashboard ini dapat ditelusuri mundur sampai ke berkas aslinya.")

    st.html('<div class="tingkat">Tahapan Pengolahan Data</div>')
    baris = [("Berkas terkumpul", corong["unduh"]),
             ("Punya lapis teks", corong["teks"]),
             ("Masuk dataset terstruktur", corong["urai"])]
    t = pd.DataFrame(baris, columns=["Tahap", "Jumlah"])
    t["Terhadap tahap sebelumnya"] = [""] + [
        f"{100 * baris[i][1] / max(1, baris[i - 1][1]):.1f} persen"
        for i in range(1, len(baris))]
    st.html(TV.tabel(t))

    st.html('<div class="tingkat">Kelengkapan Ruas Data</div>')
    n = len(df)
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
         "Terisi": int(df[k].notna().sum()),
         "Persen": round(100 * df[k].notna().sum() / n, 1)}
        for k, label in ruas if k in df])
    st.html(TV.tabel(t, kolom_persen=("Persen",)))

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
# Penyalur dan kaki
# ---------------------------------------------------------------------------

{
    "Ringkasan Eksekutif": hal_ikhtisar,
    "Nilai Sengketa": hal_nilai,
    "Risalah Putusan": hal_telusur,
    "Pola Putusan Sejenis": hal_belajar,
    "Pilihan Upaya Hukum": hal_jalur,
    "Pasal Penentu": hal_dasar,
    "Unit Penerbit Ketetapan": hal_unit,
    "Konsistensi Putusan Hakim": hal_konsistensi,
    "Sengketa Berulang": hal_berulang,
    "Mutu Ketetapan": hal_ketetapan,
    "Profil Hakim": hal_hakim,
    "Durasi Penyelesaian Sengketa": hal_kinerja,
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
