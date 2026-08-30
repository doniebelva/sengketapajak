#!/usr/bin/env python3
"""
tema_viz.py

Palet, tema bagan, gaya halaman, dan potongan kerangka untuk
Dashboard Analitik Sengketa Pajak.

Ditulis ulang dari spesifikasi_redesign_dashboard.md. Seluruh keputusan warna
dan tata letak berasal dari dokumen itu, dan tidak boleh diubah di sini tanpa
mengubah dokumennya lebih dulu.

Tiga aturan yang paling sering dilanggar pada versi sebelumnya, karena itu
ditulis paling awal:

  1. Tinta redup tidak pernah dipakai untuk tulisan, hanya untuk garis.
     Pelanggaran aturan ini yang menghasilkan tujuh titik kontras di bawah
     ambang keterbacaan pada penyisiran terakhir.
  2. Tema Plotly bawaan Streamlit harus dimatikan pada setiap pemanggilan
     bagan. Kalau tidak, ia menimpa seluruh aturan di sini tanpa terlihat.
  3. Paling banyak tiga kategori berwarna dalam satu bagan. Selebihnya
     digabung menjadi Lainnya atau dipecah menjadi bagan terpisah.
"""

from __future__ import annotations

import base64
import os
import re

import plotly.graph_objects as go
import plotly.io as pio

ASET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aset")


# ---------------------------------------------------------------------------
# Palet
# ---------------------------------------------------------------------------
#
# Rona diambil dari warna kelembagaan pada laman Pengadilan Pajak, yaitu biru
# tua, emas, dan hijau. Tingkat terang dan pekatnya disetel ulang, karena warna
# aslinya tidak lolos pemeriksaan: biru tuanya terbaca abu abu dan emasnya
# tenggelam pada latar putih.
#
# Susunan slotnya bukan urusan selera. Emas dan hijau, bila keduanya dibawa ke
# tingkat terang yang benar, hampir tidak dapat dibedakan oleh pembaca buta
# warna merah hijau, selisihnya hanya 2,3 dari ambang 8. Karena itu hijau
# ditaruh di slot ketiga, sehingga bagan berkategori dua hanya memakai biru dan
# emas yang selisihnya 27,0, dan hijau baru muncul ketika kategori ketiga
# memang diperlukan. Selisih terburuk pada susunan tiga slot ini 11,4 pada mode
# terang dan 8,1 pada mode gelap, keduanya lolos.

TERANG = {
    "seri": ["#2f6cc0", "#b8890a", "#1f7a4d"],
    # Ujung terang gradasi kop, biru royal khas Kemenkeu. Tulisan putih di
    # atasnya berkontras sekitar sembilan banding satu, jauh di atas ambang.
    "navy_terang": "#0f4c8f",
    "navy": "#1e3a6e",
    "navy_2": "#142a52",
    "permukaan": "#ffffff",
    "bidang": "#eef1f5",
    "tinta": "#0b0b0b",
    "tinta_2": "#52514e",
    "tinta_redup": "#898781",   # hanya untuk garis, tidak pernah untuk tulisan
    "garis_bantu": "#e1e0d9",
    "sumbu": "#c3c2b7",
    "tepi": "rgba(11,11,11,0.10)",
    "baik": "#0ca30c",
    "awas": "#fab219",
    "genting": "#d03b3b",
}

GELAP = {
    "seri": ["#4a8ae0", "#ad8110", "#2f9c68"],
    "navy_terang": "#0d3a6e",
    "navy": "#16243f",
    "navy_2": "#0c1a30",
    "permukaan": "#1c1f26",
    "bidang": "#12141a",
    "tinta": "#ffffff",
    "tinta_2": "#c3c2b7",
    "tinta_redup": "#898781",
    "garis_bantu": "#2c2c2a",
    "sumbu": "#383835",
    "tepi": "rgba(255,255,255,0.10)",
    "baik": "#0ca30c",
    "awas": "#fab219",
    "genting": "#d03b3b",
}

# Warna yang maknanya tetap, berlaku di seluruh halaman.
#
# Sebelum ini warna dibagikan menurut urutan deret pada tiap bagan, sehingga
# warna yang sama berarti hal berbeda di halaman yang berbeda, dan bahkan di
# halaman yang sama bisa bertukar ketika pemakai menukar unit di kiri dengan
# yang di kanan. Pembaca yang sudah hafal biru berarti DJP mendadak keliru
# membaca. Dengan makna yang tetap, unit dikenali tanpa membaca legenda.
#
# Kemenkeu memakai biru tua, bukan biru deret, karena ia gabungan DJP dan
# DJBC dan tidak boleh tertukar dengan DJP saja.
def warna_unit(gelap: bool = False) -> dict:
    p = GELAP if gelap else TERANG
    return {
        "djp": p["seri"][0], "DJP": p["seri"][0],
        "djbc": p["seri"][1], "DJBC": p["seri"][1],
        "pemda": p["seri"][2], "Pemda": p["seri"][2],
        "Kemenkeu": p["navy_terang"],
        "Belum terbaca": p["sumbu"],
    }


SANS = '"Inter", system-ui, -apple-system, "Segoe UI", sans-serif'
# Naskah putusan memakai Aptos, huruf baku dokumen pada lingkungan kerja ini.
# Aptos tidak tersedia sebagai huruf web, jadi yang terpasang di perangkat
# pembacalah yang dipakai; pada perangkat tanpa Aptos, cadangannya huruf
# sistem yang bentuknya paling berdekatan.
APTOS = ('"Aptos", "Aptos Display", "Segoe UI Variable Text", "Segoe UI", '
         '"Inter", system-ui, sans-serif')
FONT_URL = ("https://fonts.googleapis.com/css2?"
            "family=Inter:wght@400;500;600;700&display=swap")

SISI = "2.2rem"       # jarak tepi bidang isi, dipakai juga oleh kop dan kaki
TINGGI_KOP = 66
TINGGI_KAKI = 43


def palet(gelap: bool) -> dict:
    return GELAP if gelap else TERANG


def lembut(hex_warna: str, alpha: float) -> str:
    """
    Warna yang sama dengan sebagian tembus pandang, untuk isian batang.

    Warna yang bukan susunan enam angka heksadesimal dikembalikan apa adanya.
    Fungsi ini kini menerima warna dari lebih banyak tempat, termasuk warna
    yang sudah berbentuk rgba, dan memaksakan pembacaan heksadesimal atasnya
    menghentikan seluruh halaman dengan pesan yang tidak menunjuk sebabnya.
    """
    if not isinstance(hex_warna, str) or not hex_warna.startswith("#"):
        return hex_warna
    h = hex_warna.lstrip("#")
    if len(h) not in (3, 6):
        return hex_warna
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return hex_warna
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# Tema bagan
# ---------------------------------------------------------------------------

def pasang_template(gelap: bool) -> str:
    p = palet(gelap)
    nama = "tdad_gelap" if gelap else "tdad_terang"

    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=SANS, size=13, color=p["tinta_2"]),
        title=dict(font=dict(size=15, color=p["tinta"]), x=0,
                   xanchor="left", pad=dict(b=12)),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=p["seri"],
        # Margin kiri sengaja tidak dikunci. Nama kategori pada bagan
        # mendatar panjang panjang, dan margin tetap yang kecil
        # memotongnya sampai tersisa satu huruf terakhir.
        margin=dict(r=18, t=44, b=6),
        hoverlabel=dict(font=dict(family=SANS, size=12, color=p["tinta"]),
                        bgcolor=p["permukaan"], bordercolor=p["sumbu"]),
        # Legenda dirata kanan, judul tetap rata kiri. Sebelumnya keduanya
        # sama sama ditempatkan pada titik nol sumbu mendatar, sehingga pada
        # bagan berjudul panjang legendanya menimpa judulnya.
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, title=dict(text=""),
                    font=dict(size=12, color=p["tinta_2"])),
        # Label sumbu memakai tinta kedua, bukan tinta redup. Pada dua belas
        # piksel, tinta redup di atas latar putih hanya mencapai rasio 3,2.
        xaxis=dict(showgrid=True, gridcolor=p["garis_bantu"], gridwidth=1,
                   zeroline=False, showline=False, ticks="",
                   automargin=True,
                   tickfont=dict(size=12, color=p["tinta_2"]),
                   title=dict(font=dict(size=12, color=p["tinta_2"]))),
        yaxis=dict(showgrid=False, zeroline=False, showline=False, ticks="",
                   automargin=True,
                   tickfont=dict(size=12, color=p["tinta_2"]),
                   title=dict(font=dict(size=12, color=p["tinta_2"]))),
        bargap=0.34,
        barcornerradius=6,
    )
    pio.templates[nama] = t
    pio.templates.default = nama
    return nama


def rapikan(fig, tinggi: int | None = None, gelap: bool = False):
    """
    Sentuhan akhir yang sama untuk setiap bagan.

    Isian batang memakai warna kategori pada kepekatan rendah dengan garis tepi
    warna penuh. Bidang berwarna pekat berukuran besar membuat halaman terasa
    berat, sedangkan isian kosong sama sekali membuat batang terlihat belum
    jadi. Kepekatan dibedakan menurut jumlah deret, karena pada bagan bertumpuk
    isian yang terlalu pucat membuat segmen bersebelahan kehilangan batas.
    """
    p = palet(gelap)

    # Latar dipaksa tembus pandang pada setiap bagan, tidak cukup lewat
    # template saja. Streamlit menyisipkan warna latar halamannya sendiri ke
    # dalam gambar, sehingga kertas bagan menjadi abu abu sedangkan bidang
    # gambarnya putih, dan hasilnya terlihat seperti kotak putih menimpa kotak
    # abu abu di dalam satu kartu.
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)",
                      # Nama kolom pewarna ikut tercetak sebagai judul
                      # legenda oleh plotly express, dan itu selalu berupa
                      # nama ruas basis data yang tidak berarti bagi pembaca.
                      legend_title_text="")
    if tinggi:
        fig.update_layout(height=tinggi)

    batang = [t for t in fig.data if getattr(t, "type", None) == "bar"]
    satu_deret = len(batang) <= 1

    # Penjaga jumlah kategori berwarna. Palet ini hanya lolos pemeriksaan
    # keterbacaan sampai tiga rona. Kategori keempat dan seterusnya akan
    # memakai warna yang tidak pernah diuji, jadi kalau sampai muncul, itu
    # kesalahan penyiapan data yang harus diperbaiki di sumbernya.
    if len(batang) > len(p["seri"]):
        fig.add_annotation(
            text=(f"Peringatan penyiapan data: {len(batang)} kategori berwarna, "
                  f"batas palet {len(p['seri'])}. Gabungkan sisanya."),
            xref="paper", yref="paper", x=0, y=1.14, showarrow=False,
            font=dict(size=11, color=p["genting"]))

    for i, t in enumerate(fig.data):
        if getattr(t, "type", None) != "bar":
            continue
        warna = getattr(t.marker, "color", None)
        if not isinstance(warna, str):
            warna = p["seri"][i % len(p["seri"])]
        if satu_deret:
            t.marker.color = lembut(warna, 0.26 if gelap else 0.16)
            t.marker.line.color = warna
            t.marker.line.width = 1.6
        else:
            t.marker.color = lembut(warna, 0.55 if gelap else 0.45)
            t.marker.line.color = warna
            t.marker.line.width = 1.2

        # Plotly memilih sendiri warna tulisan berdasarkan kepekatan isian, dan
        # pada isian lembut ia memilih putih sehingga angkanya lenyap. Karena
        # itu warnanya dipaksa, dan letaknya dipaksa di luar ujung batang.
        if getattr(t, "text", None) is not None:
            t.textposition = "outside"
            t.cliponaxis = False
            t.textfont = dict(color=p["tinta"], size=12)
            t.outsidetextfont = dict(color=p["tinta"], size=12)
            t.insidetextfont = dict(color=p["tinta"], size=12)
        t.hoverlabel = dict(bordercolor=warna)

    # Deret garis. Bagan bersumbu waktu digambar sebagai garis, bukan batang,
    # karena yang dibaca pembaca adalah arah pergerakannya. Titik penanda
    # diberi tepi sewarna permukaan supaya tetap terbaca ketika dua deret
    # saling berdekatan, dan bidang di bawah garis diberi warna sangat lembut
    # agar tidak menutupi garis lain.
    garis = [t for t in fig.data if getattr(t, "type", None) == "scatter"]
    for i, t in enumerate(garis):
        # Deret yang lebar garisnya sengaja disetel nol dibiarkan apa adanya.
        # Deret seperti itu bukan garis yang ingin dilihat pembaca, melainkan
        # pembatas atas dan bawah sebuah pita, misalnya pita selang keyakinan,
        # yang hanya dipakai sebagai penyangga bidang berwarna. Memaksakan
        # lebar dan warna baku atasnya menggambar dua garis penuh yang tidak
        # pernah dimaksudkan ada, dan pita yang seharusnya lembut justru
        # menjadi bagian paling mencolok pada bagannya.
        if getattr(t, "line", None) is not None and t.line.width == 0:
            continue
        # Deret titik yang warnanya atau ukurannya dipetakan dari data
        # dibiarkan apa adanya. Pemaksaan satu warna dan satu ukuran di
        # bawah menghapus pemetaan itu tanpa jejak: peta sebaran yang
        # warnanya menyatakan satu ukuran dan besar titiknya menyatakan
        # ukuran lain berubah menjadi kerumunan titik seragam yang tidak
        # lagi memberi keterangan apa pun.
        mk = getattr(t, "marker", None)
        if mk is not None:
            dipetakan = (
                getattr(mk, "coloraxis", None) is not None
                or (getattr(mk, "color", None) is not None
                    and not isinstance(mk.color, str))
                or (getattr(mk, "size", None) is not None
                    and not isinstance(mk.size, (int, float))))
            if dipetakan:
                continue
        warna = None
        if getattr(t, "line", None) is not None:
            warna = getattr(t.line, "color", None)
        if not isinstance(warna, str):
            warna = p["seri"][i % len(p["seri"])]
            t.line.color = warna
        t.line.width = 2.6
        t.marker.size = 7
        t.marker.color = warna
        t.marker.line.color = p["permukaan"]
        t.marker.line.width = 1.6
        if getattr(t, "fill", None) in ("tozeroy", "tonexty"):
            t.fillcolor = lembut(warna, 0.20 if gelap else 0.13)
        t.hoverlabel = dict(bordercolor=warna)

    # Label di luar ujung batang memerlukan ruang yang tidak disediakan Plotly.
    # Tanpa kelonggaran ini, angka pada batang terpanjang terpotong tepi kartu.
    mendatar = any(getattr(t, "orientation", None) == "h"
                   and getattr(t, "text", None) is not None for t in batang)
    if mendatar:
        maks = 0.0
        for t in batang:
            # Nilai sumbu datang sebagai larik numpy. Menuliskannya sebagai
            # larik atau daftar kosong akan memanggil penilaian kebenaran atas
            # seluruh lariknya, dan numpy menolak itu karena tidak jelas
            # maksudnya. Pemeriksaan None harus dilakukan tersendiri.
            xs = getattr(t, "x", None)
            if xs is None:
                continue
            for v in xs:
                try:
                    maks = max(maks, float(v))
                except (TypeError, ValueError):
                    pass
        if maks > 0:
            fig.update_xaxes(range=[0, maks * (1.30 if maks < 50 else 1.20)])
    return fig


# ---------------------------------------------------------------------------
# Gaya halaman
# ---------------------------------------------------------------------------

def gaya(gelap: bool) -> str:
    p = palet(gelap)
    return f"""
<link rel="stylesheet" href="{FONT_URL}">
<style>
  html, body, [class*="css"], .stApp, button, input, select, textarea {{
    font-family: {SANS}; -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    /* Angka dibuat sama lebar di seluruh dashboard supaya deret bilangan
       pada tabel dan kartu berbaris lurus, dan huruf dirapatkan sedikit,
       lazim pada huruf berukuran layar. */
    font-variant-numeric: tabular-nums; font-synthesis-weight: none;
    letter-spacing: -.006em;
  }}
  h1, h2, h3, h4, .kop-judul {{ letter-spacing: -.018em; }}
  .stApp {{ background: {p["bidang"]}; }}
  .block-container {{
    padding: calc({TINGGI_KOP}px + 20px) {SISI}
             calc({TINGGI_KAKI}px + 26px) {SISI};
    max-width: 100%;
  }}
  footer {{ visibility: hidden; }}

  /* --- Bilah judul, dipaku di puncak jendela ---------------------------- */
  .kop {{
    position: fixed; top: 0; left: 0; right: 0; z-index: 1000000;
    display: flex; align-items: center; gap: 16px;
    height: {TINGGI_KOP}px; padding: 0 {SISI};
    /* Gradasi biru Kemenkeu: biru royal di sisi logo turun ke navy dalam di
       sisi kanan. Gradasi lama memakai dua navy yang nyaris sama sehingga
       tampak polos; tiga perhentian ini memberi kedalaman tanpa mengurangi
       kontras tulisan putih, yang pada titik paling terang pun masih jauh
       di atas ambang keterbacaan. */
    background: linear-gradient(115deg, {p["navy_terang"]} 0%,
                                {p["navy"]} 48%, {p["navy_2"]} 100%);
    box-shadow: 0 1px 6px rgba(0,0,0,.22);
  }}
  .kop img {{ height: 40px; width: auto; }}
  .kop-garis {{ width: 1px; height: 36px; background: rgba(255,255,255,.24); }}
  .kop-judul {{ font-size: 19px; font-weight: 600; color: #fff;
                line-height: 1.25; letter-spacing: .005em; }}
  .kop-sub {{ font-size: 12px; color: rgba(255,255,255,.80); margin-top: 3px; }}
  .kop-kanan {{ margin-left: auto; text-align: right;
                font-size: 11.5px; color: rgba(255,255,255,.84);
                line-height: 1.45;
                /* Diberi jarak dari pemilih tema yang menimpa pojok kanan
                   bilah judul, supaya cap pembaruannya tidak tertutup. */
                padding-right: 78px; }}
  .kop-kanan b {{ color: #fff; font-weight: 650; }}

  /* Bilah alat bawaan Streamlit dikosongkan, bukan dihapus. Isinya tombol
     tiga titik berisi muat ulang, rekam layar, dan setelan pengembang, yang
     tidak berguna bagi pemakai dashboard ini dan letaknya bertabrakan
     dengan bilah judul. Namun di dalam bilah alat itu juga bersarang tombol
     pembuka bilah samping. Menyembunyikan seluruh bilah alat pernah membuat
     bilah samping yang sudah ditutup tidak dapat dibuka lagi sama sekali,
     jadi kerangkanya dibiarkan hidup, isinya saja yang dimatikan. */
  header[data-testid="stHeader"] {{
    background: transparent !important; height: 0 !important;
    min-height: 0 !important; pointer-events: none !important;
    z-index: 1000002 !important;
  }}
  header[data-testid="stHeader"] div[data-testid="stToolbar"] {{
    background: transparent !important; pointer-events: none !important;
  }}
  /* Yang dimatikan hanya isi bilah alat yang tidak berguna bagi pemakai:
     menu tiga titik, tombol sebar, dan penanda proses. Kerangka bilah
     alatnya tetap hidup karena tombol pembuka bilah samping ada di dalamnya.
     Pemilihnya sengaja tanpa nama elemen: menu tiga titik digambar sebagai
     span, bukan div, dan pemilih bernama div sempat meleset sehingga
     ikonnya menyembul di pojok kanan atas. */
  [data-testid="stMainMenu"],
  [data-testid="stMainMenuButton"],
  [data-testid="stStatusWidget"],
  [data-testid="stAppDeployButton"] {{ display: none !important; }}

  /* Tombol pembuka bilah samping dikembalikan sebagai tombol tersendiri di
     bawah bilah judul, cukup besar untuk ditekan dan jelas terlihat. */
  button[data-testid="stExpandSidebarButton"] {{
    pointer-events: auto !important;
    position: fixed !important;
    top: calc({TINGGI_KOP}px + 12px) !important; left: 12px !important;
    width: 34px !important; height: 34px !important;
    display: inline-flex !important; align-items: center !important;
    justify-content: center !important;
    background: {p["permukaan"]} !important; color: {p["tinta"]} !important;
    border: 1px solid {p["tepi"]} !important; border-radius: 9px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.12) !important;
    z-index: 1000002 !important;
  }}
  button[data-testid="stExpandSidebarButton"]:hover {{
    background: {p["bidang"]} !important;
  }}

  /* Tombol bawaan Streamlit Cloud, yaitu Fork beserta pranala menuju
     repositori GitHub, dimatikan sama sekali.

     Alasannya keamanan, bukan tampilan. Tombol Fork memungkinkan siapa pun
     yang membuka dashboard ini menyalin seluruh aplikasi ke akunnya sendiri,
     dan pranala di sebelahnya membawa pemakai langsung ke repositori
     pemiliknya. Dashboard ini dibuka pemakai luar untuk membaca angka, dan
     tidak satu pun dari kedua tombol itu berguna bagi mereka.

     Ini penanganan lapis kedua. Penanganan di sumbernya berupa toolbarMode
     bernilai viewer pada berkas setelan, yang membuat peladen tidak
     mengirimkan tombolnya sejak awal. Keduanya dipasang bersamaan karena
     setelan itu ditafsirkan peladen Streamlit Cloud, sehingga perubahan di
     pihak mereka tidak boleh membuat tombolnya muncul kembali diam diam.

     Pemilihnya menyasar tombolnya, bukan seluruh bilah alat. Menyembunyikan
     seluruh bilah alat pernah membuat bilah samping yang sudah ditutup tidak
     dapat dibuka lagi, karena tombol pembukanya bersarang di dalamnya. */
  [data-testid="stToolbarActions"],
  [data-testid="stToolbarActionButton"],
  [data-testid="stToolbarActionButtonLabel"],
  [data-testid="stToolbarActionButtonIcon"] {{
    display: none !important;
    /* Penjaga terakhir. Seandainya suatu saat unsurnya tetap tergambar
       karena perubahan di pihak Streamlit, ia tetap tidak dapat ditekan. */
    pointer-events: none !important;
    visibility: hidden !important;
  }}

  /* Keterangan kapan di atas kartu angka. */
  .kapan {{
    font-size: 12px; color: {p["tinta_2"]}; margin: 2px 0 12px;
  }}
  .kapan b {{ color: {p["tinta"]}; font-weight: 620; }}
  .kapan .pisah {{ margin: 0 8px; color: {p["sumbu"]}; }}

  /* Temuan utama ditegaskan. Kalimat pembuka tiap temuan adalah inti
     halaman depan, dan pada ukuran biasa ia tenggelam di antara paragraf
     lain yang sama tebalnya. */
  .temuan {{
    font-size: 15.5px; line-height: 1.6; color: {p["tinta_2"]};
    margin: 0 0 14px 0;
  }}
  .temuan b {{
    font-size: 17.5px; font-weight: 700; color: {p["tinta"]};
    line-height: 1.5;
  }}

  /* --- Pita keandalan data ---------------------------------------------- */
  /* Pita keandalan dijadikan satu baris tipis tanpa kotak. Sebagai kotak
     setinggi delapan puluh piksel di kepala halaman, ia merebut perhatian
     dari judul padahal isinya keterangan pendukung. */
  .andal-pita {{
    display: flex; flex-wrap: wrap; align-items: center; gap: 6px;
    margin: 2px 0 16px; padding: 0 0 10px;
    border-bottom: 1px solid {p["tepi"]};
    font-size: 11.5px; color: {p["tinta_2"]};
  }}
  .andal-judul {{ margin-right: 3px; }}
  .andal {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 1px 8px; border-radius: 999px;
    background: {p["bidang"]}; border: 1px solid {p["tepi"]};
    color: {p["tinta"]}; font-weight: 550; white-space: nowrap;
  }}
  .andal i {{ width: 7px; height: 7px; border-radius: 50%; }}
  .andal-baik i {{ background: {p["baik"]}; }}
  .andal-awas i {{ background: {p["awas"]}; }}
  .andal-genting i {{ background: {p["genting"]}; }}
  /* Kalimat penutup pita hanya tampil saat ada bagian kuning atau merah,
     karena hanya di situ ia menambah keterangan. */
  .andal-ket {{ font-size: 11px; color: {p["tinta_2"]}; }}

  /* Kepala halaman terpadu: nama halaman lebih dulu, keterangan pendukung
     menjadi label kecil di sampingnya. */
  .kepala-hal {{
    display: flex; align-items: baseline; flex-wrap: wrap; gap: 10px;
    margin: 2px 0 2px;
  }}
  .kepala-hal h3 {{
    font-size: 21px !important; font-weight: 700 !important;
    letter-spacing: -.012em; margin: 0 !important; padding: 0 !important;
    color: {p["tinta"]};
  }}
  .kh-dim, .kh-lingkup {{
    font-size: 10.5px; font-weight: 700; letter-spacing: .05em;
    text-transform: uppercase; padding: 3px 9px; border-radius: 999px;
    white-space: nowrap;
  }}
  .kh-dim {{ color: {p["tinta_2"]}; background: {p["bidang"]};
             border: 1px solid {p["tepi"]}; }}
  .kh-lingkup {{ color: #fff; background: {p["navy"]}; }}

  /* Judul sisi pada mode banding. Dua sisi yang tampil bersebelahan harus
     dapat dibedakan sekali pandang, dan tanpa judul bergaris pemisah
     pembaca mudah tertukar membaca angka kiri sebagai angka kanan. */
  .banding-judul {{
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 10px; margin: 4px 0 12px;
    padding: 9px 13px; border-radius: 10px;
    background: {p["bidang"]}; border: 1px solid {p["tepi"]};
    border-left: 3px solid {p["navy"]};
    font-size: 13.5px; font-weight: 680; color: {p["tinta"]};
  }}
  .banding-judul span {{
    font-size: 11.5px; font-weight: 550; color: {p["tinta_2"]};
    white-space: nowrap;
  }}

  /* --- Pemilih unit analisis -------------------------------------------- */
  /* Daftar jatuh di puncak bilah samping. Karena inilah pilihan analisis
     utama dashboard, tampilannya ditegaskan: berlatar navy Kemenkeu dengan
     tulisan putih, sehingga unit yang sedang dibaca terlihat sekali pandang
     tanpa perlu membuka daftarnya. */
  .st-key-lingkup_instansi div[data-baseweb="select"] > div {{
    background: {p["navy"]} !important;
    border-color: {p["navy"]} !important;
    border-radius: 10px !important;
    min-height: 40px !important;
  }}
  .st-key-lingkup_instansi div[data-baseweb="select"] div,
  .st-key-lingkup_instansi div[data-baseweb="select"] span,
  .st-key-lingkup_instansi div[data-baseweb="select"] svg {{
    color: #fff !important; fill: #fff !important;
  }}
  .st-key-lingkup_instansi div[data-baseweb="select"] > div > div:first-child {{
    font-size: 14px !important; font-weight: 650 !important;
  }}

  /* --- Penanda pemuatan ------------------------------------------------- */
  /* Data tumbuh mengikuti arsip, dan jeda pemuatan ikut memanjang. Penanda
     pemuatan diseragamkan dengan tema supaya jeda itu terasa sebagai bagian
     aplikasi yang sedang bekerja, bukan sebagai halaman yang membeku. */
  div[data-testid="stSpinner"] {{
    background: {p["permukaan"]}; border: 1px solid {p["tepi"]};
    border-radius: 10px; padding: 10px 16px;
    box-shadow: 0 1px 5px rgba(0,0,0,.08);
  }}
  div[data-testid="stSpinner"] i {{
    border-color: {p["seri"][0]} rgba(0,0,0,0) rgba(0,0,0,0) !important;
  }}
  div[data-testid="stSpinner"] > div {{
    color: {p["tinta_2"]}; font-size: 13px;
  }}
  div[data-testid="stProgress"] div[role="progressbar"] > div {{
    background: {p["seri"][0]} !important;
  }}
  div[data-testid="stProgress"] p {{
    color: {p["tinta_2"]} !important; font-size: 12.5px !important;
  }}

  /* --- Tab penelaahan --------------------------------------------------- */
  /* Satu halaman kerap memuat beberapa sudut telaah atas pokok yang sama.
     Menaruh semuanya berderet ke bawah membuat halaman sangat panjang dan
     memaksa pembaca menggulir melewati bagian yang tidak dicarinya, padahal
     tiap sudut berdiri sendiri. Tab memisahkannya tanpa menambah menu, dan
     tanpa memecah pokok yang sebenarnya satu.

     Bentuknya sengaja bilah bergaris bawah, bukan kotak bersusun. Tab
     berbentuk kotak mudah tertukar dengan tombol, sedangkan garis bawah
     pada tab terpilih adalah tanda baku yang langsung terbaca sebagai
     penunjuk bagian yang sedang dibuka. */
  div[data-testid="stTabs"] {{ margin-top: 2px; }}
  div[data-testid="stTabs"] div[role="tablist"] {{
    gap: 2px !important;
    border-bottom: 1px solid {p["tepi"]} !important;
    margin-bottom: 18px !important;
    /* Pada layar sempit tab yang tidak muat digeser mendatar, bukan
       dilipat ke baris berikutnya, supaya tingginya tetap terduga. */
    overflow-x: auto !important; overflow-y: hidden !important;
    scrollbar-width: none !important;
  }}
  div[data-testid="stTabs"] div[role="tablist"]::-webkit-scrollbar {{
    display: none;
  }}
  div[data-testid="stTabs"] button[role="tab"] {{
    padding: 9px 16px !important; margin: 0 !important;
    border-radius: 8px 8px 0 0 !important;
    color: {p["tinta_2"]} !important;
    white-space: nowrap !important;
  }}
  div[data-testid="stTabs"] button[role="tab"] p {{
    font-size: 13.5px !important; font-weight: 550 !important;
    letter-spacing: .005em !important;
  }}
  div[data-testid="stTabs"] button[role="tab"]:hover {{
    background: {p["bidang"]} !important; color: {p["tinta"]} !important;
  }}
  div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
    color: {p["tinta"]} !important; background: transparent !important;
  }}
  div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] p {{
    font-weight: 680 !important;
  }}
  /* Penanda tab terpilih digambar sendiri. Penanda bawaan Streamlit
     mewarisi warna utama yang berbeda antar tema, dan pernah tampil nyaris
     tidak terlihat pada tema gelap. */
  div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {{
    background: {p["seri"][0]} !important; height: 2.5px !important;
  }}
  div[data-testid="stTabs"] div[data-baseweb="tab-border"] {{
    display: none !important;
  }}

  /* --- Kaki, dipaku di dasar jendela, satu baris ------------------------ */
  .kaki {{
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 1000001;
    display: grid; grid-template-columns: auto 1fr auto; align-items: center;
    gap: 20px; height: {TINGGI_KAKI}px; padding: 0 {SISI};
    background: {p["permukaan"]}; border-top: 1px solid {p["tepi"]};
    box-shadow: 0 -1px 6px rgba(0,0,0,.07);
    font-size: 11.5px; color: {p["tinta_2"]};
  }}
  .kaki b {{ color: {p["tinta"]}; font-weight: 620; }}
  .kaki .kiri {{ display: flex; align-items: center; gap: 9px;
                 white-space: nowrap; }}
  .kaki .tengah {{ justify-self: center; text-align: center; min-width: 0;
                   overflow: hidden; text-overflow: ellipsis;
                   white-space: nowrap; }}
  .kaki .kanan {{ justify-self: end; white-space: nowrap; }}
  .kaki .pisah {{ color: {p["sumbu"]}; }}
  .kaki .purwarupa {{
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    font-size: 9.5px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; color: {p["tinta_2"]};
    background: {p["bidang"]}; border: 1px solid {p["tepi"]};
  }}
  .titik {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%;
            margin-right: 6px; vertical-align: -1px; }}
  @media (max-width: 1150px) {{
    .kaki {{ grid-template-columns: auto 1fr; }}
    .kaki .kanan {{ display: none; }}
  }}

  /* --- Bilah samping ---------------------------------------------------- */
  section[data-testid="stSidebar"] {{
    background: {p["permukaan"]}; border-right: 1px solid {p["tepi"]};
    position: relative;
  }}
  /* Ruang atas diberi jatah lebih untuk baris tombol pelipat, supaya kotak
     pencarian di bawahnya tidak tertindih. */
  section[data-testid="stSidebar"] > div {{
    padding-top: calc({TINGGI_KOP}px + 48px);
    padding-bottom: calc({TINGGI_KAKI}px + 20px);
  }}
  section[data-testid="stSidebar"] div[data-testid="stSidebarHeader"] {{
    padding: 0 !important; height: 0 !important; min-height: 0 !important;
  }}
  /* Tombol pelipat bilah samping. Dulu dipatok pada titik empat piksel dari
     atas, yang berada di belakang bilah judul, sehingga menu samping tidak
     pernah bisa ditutup sama sekali. Kini digantung tepat di bawah bilah
     judul di pojok kanan bilah samping, dibingkai serupa tombol pembukanya
     di sisi kiri supaya keduanya terbaca sepasang. */
  div[data-testid="stSidebarCollapseButton"],
  button[data-testid="stSidebarCollapseButton"] {{
    position: absolute !important;
    top: calc({TINGGI_KOP}px + 9px) !important; right: 10px !important;
    width: 32px !important; height: 32px !important;
    display: inline-flex !important; align-items: center !important;
    justify-content: center !important;
    background: {p["permukaan"]} !important; color: {p["tinta"]} !important;
    border: 1px solid {p["tepi"]} !important; border-radius: 9px !important;
    box-shadow: 0 1px 4px rgba(0,0,0,.12) !important;
    z-index: 6 !important; pointer-events: auto !important;
  }}
  div[data-testid="stSidebarCollapseButton"]:hover {{
    background: {p["bidang"]} !important;
  }}
  /* Tombol di dalam pembungkusnya dibuat polos; pembungkusnya yang menjadi
     pil, supaya tidak ada bingkai ganda. */
  div[data-testid="stSidebarCollapseButton"] button {{
    border: none !important; background: transparent !important;
    color: inherit !important; width: 100% !important;
    height: 100% !important; padding: 0 !important;
  }}
  div[data-testid="stSidebarCollapsedControl"],
  div[data-testid="collapsedControl"] {{
    position: fixed !important;
    top: calc({TINGGI_KOP}px + 10px) !important; left: 10px !important;
    z-index: 1000001 !important;
  }}

  /* Ikon menu digambar sebagai bentuk bertopeng, sehingga warnanya mengikuti
     warna tulisan dan selalu satu warna. Emoji tidak dipakai karena selalu
     tampil berwarna penuh dan bentuknya berbeda antar sistem. Topeng tiap
     halaman dibangkitkan ikon_nav(), disasar lewat kunci tombolnya, bukan
     lewat urutan, supaya susunan menu boleh berubah menurut modul dan
     tampilannya tidak bergantung struktur dalam Streamlit. */
  section[data-testid="stSidebar"] div[class*="st-key-nav-"]
    button p::before {{
    content: ""; display: inline-block; width: 17px; height: 17px;
    margin-right: 10px; background-color: currentColor;
    flex: 0 0 17px;
  }}

  /* Pemilih tema, ditempatkan di sudut kanan atas menimpa bilah judul.
     Lapisannya di atas bilah judul supaya tetap dapat ditekan, dan warnanya
     dibuat terang karena latarnya biru tua. */
  /* Pemilih tema, ikon saja, tanpa latar maupun bingkai.
     Tulisan Terang dan Gelap dibuang karena ikon matahari dan bulan sudah
     dipahami tanpa keterangan, dan di atas bilah judul yang sempit setiap
     kata tambahan hanya membuatnya ramai. Lambangnya dipaksa tampil sebagai
     huruf, bukan sebagai emoji berwarna. */
  /* Pemilih tema diturunkan sedikit dari tepi atas. Pada peladen Streamlit
     Cloud, tombol Fork milik peladen digambar menempel di tepi atas kanan,
     di luar bingkai aplikasi sehingga tidak dapat disentuh dari sini, dan
     pada posisi semula kedua unsur itu tampak bertumpuk. */
  .st-key-tema {{
    position: fixed !important; top: 27px !important; right: 22px !important;
    z-index: 1000003 !important; width: auto !important;
  }}
  .st-key-tema div[data-testid="stElementContainer"] {{ margin: 0 !important; }}
  .st-key-tema div[data-baseweb="button-group"],
  .st-key-tema div[role="group"] {{
    background: transparent !important; border: none !important;
    gap: 2px !important;
  }}
  .st-key-tema button {{
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 4px 8px !important;
    min-width: 0 !important;
  }}
  .st-key-tema button p, .st-key-tema button span {{
    color: rgba(255,255,255,.62) !important; font-size: 17px !important;
    font-variant-emoji: text; line-height: 1 !important;
  }}
  .st-key-tema button:hover p, .st-key-tema button:hover span {{
    color: rgba(255,255,255,.92) !important;
  }}
  .st-key-tema button[aria-checked="true"] p,
  .st-key-tema button[aria-pressed="true"] p,
  .st-key-tema button[aria-checked="true"] span,
  .st-key-tema button[aria-pressed="true"] span {{
    color: #ffffff !important;
  }}

  .sb-judul {{
    font-size: 10.5px; font-weight: 700; letter-spacing: .08em;
    text-transform: uppercase; color: {p["tinta_2"]};
    margin: 10px 0 6px 2px;
  }}

  /* Nama kelompok di dalam menu. Dibedakan dari judul bagian di atasnya lewat
     ukuran dan garis pemisah, bukan lewat warna yang lebih pudar: tulisan
     sekecil ini akan jatuh di bawah ambang kontras kalau diredupkan. */
  section[data-testid="stSidebar"] .menu-kelompok {{
    font-size: 9.5px; font-weight: 700; letter-spacing: .07em;
    text-transform: uppercase; color: {p["tinta_2"]};
    margin: 12px 0 4px 3px; padding-top: 8px;
    border-top: 1px solid {p["garis_bantu"]};
  }}
  section[data-testid="stSidebar"] .st-key-menu-nav
    div[data-testid="stHtml"]:first-child .menu-kelompok {{
    margin-top: 0;
  }}

  /* Label pada penggeser tahun. Streamlit menuliskannya dengan warna utama
     dan dengan tembus pandang enam puluh persen, dan keduanya jatuh di bawah
     ambang kontras. Warnanya dipaksa memakai tinta yang berlaku di sini. */
  div[data-testid="stSliderThumbValue"] {{
    color: {p["tinta"]} !important; opacity: 1 !important;
    font-size: 11.5px !important; font-weight: 600 !important;
    background: {p["permukaan"]}; padding: 0 5px; border-radius: 5px;
  }}
  /* Angka tahun terkecil dan terbesar di ujung penggeser. Streamlit menamai
     kedua ujung itu berbeda beda antar versi, sehingga yang disasar adalah
     wadah pembungkusnya beserta seluruh tulisan di dalamnya. Warna bawaannya
     tembus enam puluh persen dan jatuh di bawah ambang kontras. */
  div[data-testid="stSliderTickBar"],
  div[data-testid="stSliderTickBar"] p,
  div[data-testid="stSliderTickBarMin"],
  div[data-testid="stSliderTickBarMax"] {{
    color: {p["tinta_2"]} !important; opacity: 1 !important;
    font-size: 11.5px !important;
  }}
  /* Tombol Deploy disembunyikan. Dashboard ini dijalankan setempat, tombolnya
     tidak ada gunanya, dan tulisannya putih di atas latar terang sehingga
     jatuh jauh di bawah ambang kontras. */
  div[data-testid="stAppDeployButton"],
  button[data-testid="stAppDeployButton"] {{ display: none !important; }}

  /* Daftar halaman berupa tombol, bukan pilihan bulat. Lingkaran radio
     membuat pembaca mengira harus mencentang dulu, padahal maksudnya
     berpindah halaman, jadi bentuknya dibuat seperti menu yang tinggal
     diklik. Keadaan terpilih ditandai latar dan bayangan lembut. */
  /* Jarak antar baris menu dirapatkan. Streamlit memberi jarak seragam
     antar unsur di bilah samping, yang pada deretan tiga belas tombol
     membuat menunya renggang dan memaksa pengguna menggulir. */
  section[data-testid="stSidebar"] .st-key-menu-nav,
  section[data-testid="stSidebar"] .st-key-menu-nav
    div[data-testid="stVerticalBlock"] {{
    gap: 0 !important; row-gap: 0 !important;
  }}
  section[data-testid="stSidebar"] div[class*="st-key-nav-"] {{
    margin: 0 !important; padding: 0 !important;
  }}
  section[data-testid="stSidebar"] div[class*="st-key-nav-"] button {{
    display: flex !important;
    justify-content: flex-start !important; text-align: left !important;
    padding: 8px 12px !important; border-radius: 9px !important;
    width: 100% !important; border: 1px solid transparent !important;
    background: transparent !important; box-shadow: none !important;
    min-height: 0 !important;
    transition: background .12s ease, box-shadow .12s ease;
  }}
  /* Tombol Streamlit membungkus labelnya dua lapis, dan kedua lapis itu
     memusatkan isinya sendiri. Rata kiri pada tombol saja tidak cukup:
     pembungkusnya harus ikut dilebarkan penuh dan dirata kiri, kalau tidak
     labelnya tetap mengambang di tengah. */
  section[data-testid="stSidebar"] div[class*="st-key-nav-"] button > div,
  section[data-testid="stSidebar"] div[class*="st-key-nav-"] button > div
    > span,
  section[data-testid="stSidebar"] div[class*="st-key-nav-"] button
    div[data-testid="stMarkdownContainer"] {{
    width: 100% !important; justify-content: flex-start !important;
    text-align: left !important;
  }}
  section[data-testid="stSidebar"] div[class*="st-key-nav-"] button p {{
    font-size: 13.5px !important; font-weight: 500 !important;
    color: {p["tinta_2"]} !important; margin: 0 !important;
    text-align: left !important; width: 100% !important;
    display: flex !important; align-items: center !important;
    letter-spacing: -.004em !important; line-height: 1.35 !important;
  }}
  section[data-testid="stSidebar"] div[class*="st-key-nav-"] button:hover {{
    background: {lembut(p["seri"][0], .10)} !important;
  }}
  section[data-testid="stSidebar"] div[class*="st-key-nav-"]
    button:hover p {{ color: {p["tinta"]} !important; }}
  section[data-testid="stSidebar"] div[class*="st-key-nav-"] button:focus,
  section[data-testid="stSidebar"] div[class*="st-key-nav-"]
    button:focus-visible {{ outline: none !important; }}

  /* --- Kartu angka ------------------------------------------------------ */
  /* Tinggi kartu angka disamakan. Keterangan yang panjangnya berbeda beda
     membuat satu kartu memanjang sendiri dan barisnya terlihat bergerigi.
     Tinggi minimal ditetapkan, dan kolomnya dipaksa saling menyamakan
     tinggi supaya bingkainya rata. */
  div[data-testid="stHorizontalBlock"] {{ align-items: stretch; }}
  div[data-testid="stColumn"] > div,
  div[data-testid="stColumn"] div[data-testid="stElementContainer"] {{
    height: 100%;
  }}
  /* Kartu angka. Garis aksen di tepi atas pernah dipasang dan dicabut atas
     permintaan pemilik; identitas kartu cukup dari bayangan yang sedikit
     terangkat, tanpa hiasan berwarna. */
  .kpi {{
    background: {p["permukaan"]}; border: 1px solid {p["tepi"]};
    border-radius: 12px; padding: 15px 17px 14px;
    height: 100%; min-height: 116px;
    display: flex; flex-direction: column; justify-content: flex-start;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
    transition: box-shadow .18s ease;
  }}
  .kpi:hover {{ box-shadow: 0 4px 14px rgba(0,0,0,.10); }}
  /* Bingkai warna tipis pada kartu angka, berputar tiga warna deret bagan:
     biru, emas, hijau. Warnanya dilembutkan supaya terasa sebagai aksen,
     bukan hiasan ramai, dan bagan maupun tabel sengaja tetap berbingkai
     netral supaya kartunya yang menonjol. Putarannya per kolom dalam satu
     baris kartu, sehingga kartu bersebelahan tidak pernah sewarna. */
  div[data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"]:nth-of-type(3n+1) .kpi {{
    border-color: {lembut(p["seri"][0], .55)};
  }}
  div[data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"]:nth-of-type(3n+2) .kpi {{
    border-color: {lembut(p["seri"][1], .55)};
  }}
  div[data-testid="stHorizontalBlock"]
    > div[data-testid="stColumn"]:nth-of-type(3n) .kpi {{
    border-color: {lembut(p["seri"][2], .55)};
  }}
  .kpi-ket {{ margin-top: auto; }}
  .kpi-label {{ font-size: 10.5px; font-weight: 700; letter-spacing: .06em;
                text-transform: uppercase; color: {p["tinta_2"]}; }}
  .kpi-nilai {{ font-size: 27px; font-weight: 650; color: {p["tinta"]};
                line-height: 1.15; margin-top: 6px;
                overflow-wrap: anywhere; }}
  /* Nilai berupa nama, bukan angka, kerap jauh lebih panjang daripada
     ruang kartunya. Ukurannya diturunkan menurut panjang tulisan supaya
     namanya utuh terbaca, bukan terpenggal di tengah kata. */
  .kpi-nilai.panjang {{ font-size: 19px; line-height: 1.25; }}
  .kpi-nilai.sangat-panjang {{ font-size: 15px; line-height: 1.3;
                               font-weight: 620; }}
  .kpi-ket {{ font-size: 11.5px; color: {p["tinta_2"]}; margin-top: 4px; }}

  /* Pembanding pada kartu. Warnanya netral, bukan hijau merah, karena naik
     turunnya angka yang sama berarti kabar baik bagi satu pihak dan kabar
     buruk bagi pihak lain: tingkat dikabulkan yang naik menguntungkan wajib
     pajak dan merugikan fiskus. Yang diberikan hanya penunjuk arah. */
  .kpi-banding {{
    font-size: 11.5px; font-weight: 600; color: {p["tinta_2"]};
    margin-top: 5px;
  }}
  .kpi-arah {{ margin-right: 4px; font-size: 10px; }}

  /* Penanda ruas yang kelengkapannya rendah, menempel pada kartunya sendiri.
     Peringatan di kepala halaman mudah tertinggal ketika pembaca menyalin
     satu angka dari tengah halaman untuk bahan rapat. */
  .kpi-andal {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 13px; height: 13px; margin-left: 6px; border-radius: 50%;
    background: {p["awas"]}; color: #1a1a1a;
    font-size: 9px; font-weight: 800; cursor: help;
    vertical-align: middle;
  }}

  /* --- Bagan dan tabel -------------------------------------------------- */
  div[data-testid="stPlotlyChart"] {{
    background: {p["permukaan"]}; border: 1px solid {p["tepi"]};
    border-radius: 12px; padding: 10px 14px 14px 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
  }}

  /* Tata huruf: judul halaman dan judul bagian ditegaskan mengikuti
     patokan dashboard admin modern, isi menu sedikit dibesarkan supaya
     nyaman ditunjuk, dan hierarkinya terbaca dari beratnya, bukan dari
     hiasan. */
  div[data-testid="stMainBlockContainer"] h3 {{
    font-size: 21px !important; font-weight: 700 !important;
    letter-spacing: -.012em !important; padding-bottom: 2px !important;
  }}
  section[data-testid="stSidebar"] div[class*="st-key-nav-"] button p {{
    font-size: 14px !important; font-weight: 550 !important;
  }}

  /* Lebar isi dibatasi pada layar sangat lebar. Baris tulisan yang
     membentang penuh pada monitor lebar menjadi terlalu panjang untuk
     diikuti mata, dan halaman terasa kosong di tengah. */
  div[data-testid="stMainBlockContainer"] {{
    max-width: 1560px; margin: 0 auto;
  }}
  /* Tulisan naratif utama dibuat sedikit lebih besar dan lapang. Ukuran
     bawaan terasa padat untuk paragraf penjelasan yang panjang, padahal
     paragraf itulah yang membedakan dashboard ini dari sekadar bagan. */
  div[data-testid="stMainBlockContainer"]
      div[data-testid="stMarkdownContainer"] p {{
    font-size: 14px; line-height: 1.68;
  }}
  div[data-testid="stDataFrame"] {{
    border-radius: 12px; overflow: hidden; border: 1px solid {p["tepi"]};
  }}
  div[data-testid="stDataFrame"] * {{ font-size: 12.5px !important; }}

  /* Kolom kotak centang pada tabel yang dapat dipilih disembunyikan.
     Kotak centang menyatakan pilihan boleh lebih dari satu, padahal di sini
     hanya satu baris yang dapat dipilih dan gunanya untuk turun ke tingkat
     berikutnya. Barisnya tetap dapat diklik seperti biasa. */
  div[data-testid="stDataFrame"] div[data-testid="stDataFrameSelectionCell"],
  div[data-testid="stDataFrame"] [aria-label="Select row"],
  div[data-testid="stDataFrame"] [data-testid="stDataFrameSelectAllCheckbox"] {{
    display: none !important;
  }}

  /* Tabel informasi, dibuat sendiri sebagai HTML supaya perataan kolomnya
     dapat diatur. Tabel bawaan Streamlit digambar di atas kanvas, sehingga
     perataan tidak dapat disentuh dari gaya halaman. */
  table.tabel {{
    width: 100%; border-collapse: collapse; font-size: 13px;
    background: {p["permukaan"]}; border: 1px solid {p["tepi"]};
    border-radius: 12px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,.06);
  }}
  table.tabel th {{
    text-align: center; font-weight: 650; font-size: 11px;
    letter-spacing: .05em; text-transform: uppercase;
    color: {p["tinta_2"]}; background: {p["bidang"]};
    padding: 10px 14px; border-bottom: 1px solid {p["tepi"]};
  }}
  table.tabel th.kiri, table.tabel td.kiri {{ text-align: left; }}
  table.tabel th.kanan, table.tabel td.kanan {{ text-align: right; }}
  table.tabel td {{
    text-align: center; padding: 9px 14px; color: {p["tinta"]};
    border-bottom: 1px solid {p["tepi"]};
    font-variant-numeric: tabular-nums;
  }}
  /* Baris belang tipis memudahkan mata menyusuri baris panjang, dan warna
     sorot saat ditunjuk membuat baris yang sedang dibaca tidak hilang. */
  table.tabel tbody tr:nth-child(even) td {{
    background: {lembut(p["seri"][0], .035)};
  }}
  table.tabel tr:last-child td {{ border-bottom: none; }}
  table.tabel tr:hover td {{ background: {lembut(p["seri"][0], .09)}; }}

  /* Batang tipis di dalam sel persentase.
     Panjangnya sebanding dengan nilainya terhadap nilai terbesar di kolom
     yang sama, sehingga urutan peringkat terbaca sekali pandang tanpa
     membaca angkanya baris demi baris. Batangnya digambar sebagai lapisan
     di belakang tulisan, bukan menggantikan angkanya, karena yang dituju
     mempercepat perbandingan, bukan menghilangkan besaran sebenarnya.
     Warnanya sangat pudar supaya tidak bersaing dengan angka di atasnya. */
  table.tabel td.berbatang {{ position: relative; }}
  table.tabel td.berbatang::before {{
    content: ""; position: absolute; left: 0; top: 3px; bottom: 3px;
    width: var(--isi, 0%); background: {lembut(p["seri"][0], .20)};
    border-radius: 0 3px 3px 0; z-index: 0;
  }}
  table.tabel td.berbatang > span {{ position: relative; z-index: 1; }}

  /* Kaki halaman berisi langkah lanjutan. Dipisahkan garis tipis supaya
     terbaca sebagai ajakan berpindah, bukan sebagai bagian dari sajian di
     atasnya, dan alasan berpindahnya dicetak lebih kecil daripada nama
     halamannya karena yang harus menonjol tujuannya, bukan alasannya. */
  /* Kartu baris kedua dibuat lebih kecil daripada baris pertama.
     Ringkasan Eksekutif memuat sepuluh kartu berukuran sama persis, dan mata
     tidak punya petunjuk mana yang utama. Empat kartu pertama adalah angka
     yang paling sering dikutip, sedangkan baris berikutnya penopang, jadi
     tingkatannya dinyatakan lewat ukuran, bukan lewat urutan saja. */
  div[class*="st-key-kartu-kedua"] .kpi {{
    padding: 12px 14px;
  }}
  div[class*="st-key-kartu-kedua"] .kpi-nilai {{
    font-size: 21px;
  }}
  div[class*="st-key-kartu-kedua"] .kpi-label {{
    font-size: 9.5px;
  }}
  div[class*="st-key-kartu-kedua"] .kpi-ket {{
    font-size: 11px;
  }}

  /* Kalimat temuan di atas bagan.
     Tiga puluh tujuh bagan pada dashboard ini punya judul dan keterangan
     panjang di bawahnya, tetapi tidak satu pun menyebutkan apa yang harus
     dilihat. Pembaca dibiarkan menyimpulkan sendiri, dan yang tergesa
     menyimpulkan keliru. Satu kalimat yang dihitung dari data yang sedang
     tampil mengubah bagan dari sajian menjadi temuan, dan menghemat waktu
     lebih banyak daripada seluruh keterangan di bawahnya.
     Dicetak sebagai pita bergaris kiri, bukan tulisan biasa, supaya terbaca
     sebagai simpulan dan bukan sebagai judul kedua. */
  .temuan-bagan {{
    margin: 10px 0 6px 0; padding: 9px 14px;
    border-left: 3px solid {p["seri"][0]};
    background: {lembut(p["seri"][0], .07)};
    border-radius: 0 8px 8px 0;
    font-size: 13.5px; line-height: 1.6; color: {p["tinta"]};
  }}
  .temuan-bagan b {{ font-weight: 680; }}

  /* Tanda bahwa sesuatu dapat diklik.
     Sebelum ini tidak ada tanda apa pun: bagan dan tabel tampak sebagai
     gambar, sehingga pemakai tidak pernah mencoba menekannya, dan seluruh
     kemampuan drill yang sudah dibangun tidak pernah ditemukan. Kursor
     berubah, baris menyala saat disentuh, dan bagan yang dapat diklik
     diberi tepi tipis yang menegas ketika didekati. */
  div[data-testid="stPlotlyChart"]:has(+ div .ajakan-klik),
  div[data-testid="stPlotlyChart"] {{
    border-radius: 12px; transition: box-shadow .15s ease;
  }}
  div[data-testid="stPlotlyChart"] .cursor-pointer,
  div[data-testid="stPlotlyChart"] .points path {{ cursor: pointer; }}

  /* Ajakan memilih di bawah bagan yang dapat diklik. Dicetak kecil dan
     berwarna aksen supaya terbaca sebagai tawaran, bukan sebagai catatan
     kaki yang boleh dilewati. */
  .ajakan-klik {{
    display: inline-flex; align-items: center; gap: 6px;
    margin: 2px 0 6px 0; font-size: 12.5px; font-weight: 600;
    color: {p["seri"][0]};
  }}
  .ajakan-klik::before {{
    content: "◉"; font-size: 10px; opacity: .85;
  }}

  /* Baris tabel yang dapat diklik. Streamlit menggambar tabelnya di atas
     kanvas, sehingga yang dapat disentuh gaya hanyalah wadahnya; tepi yang
     menegas saat didekati sudah cukup memberi tahu bahwa ia hidup. */
  div[data-testid="stDataFrame"] {{
    border-radius: 10px; transition: box-shadow .15s ease;
  }}
  div[data-testid="stDataFrame"]:hover {{
    box-shadow: 0 0 0 2px {lembut(p["seri"][0], .35)};
  }}

  /* Daftar kutipan pokok sengketa pada drill tematik. Tiap butir berasal
     dari naskah yang berbeda, jadi jaraknya dilebarkan supaya tidak terbaca
     sebagai satu paragraf yang menyambung. */
  ol.pokok-daftar, ul.pokok-daftar {{
    margin: 6px 0 4px 0; padding-left: 20px;
    font-size: 13px; line-height: 1.65; color: {p["tinta"]};
  }}
  ol.pokok-daftar li, ul.pokok-daftar li {{
    margin-bottom: 9px; padding-left: 4px;
  }}
  ol.pokok-daftar li::marker {{ font-weight: 700; color: {p["seri"][0]}; }}

  /* Isi tiap bab pada anatomi sengketa. Dibuat serapat naskah hukum, dengan
     lebar baris terbatas supaya mata tidak kehilangan baris pada kalimat
     panjang khas risalah yang kerap melampaui seratus kata. */
  .anatomi-isi {{
    font-size: 13.5px; line-height: 1.75; color: {p["tinta"]};
    text-align: left; max-width: 78ch; hyphens: none;
    background: {p["bidang"]}; padding: 12px 14px; border-radius: 9px;
    border-left: 3px solid {p["seri"][0]};
  }}
  .anatomi-isi mark {{
    background: {lembut(p["awas"], .55)}; color: {p["tinta"]};
    padding: 0 2px; border-radius: 3px;
  }}

  /* Pintu pencarian di Beranda. Dibuat menonjol karena bagi wajib pajak
     inilah pekerjaan pertama, bukan pelengkap di ujung bilah samping. */
  .cari-beranda-judul {{
    margin: 18px 0 4px 0; font-size: 15px; font-weight: 650;
    color: {p["tinta"]};
  }}
  .cari-beranda-ket {{
    font-size: 12.5px; color: {p["tinta_2"]}; line-height: 1.55;
    margin-bottom: 8px;
  }}

  .lanjut-judul {{
    margin: 26px 0 10px 0; padding-top: 16px;
    border-top: 1px solid {p["tepi"]};
    font-size: 11px; font-weight: 700; letter-spacing: .07em;
    text-transform: uppercase; color: {p["tinta_2"]};
  }}
  .lanjut-sebab {{
    font-size: 12.5px; color: {p["tinta_2"]}; line-height: 1.5;
    margin-bottom: 7px; min-height: 38px;
  }}

  /* Ragam tabel berkolom sama lebar, untuk tabel berkolom banyak yang harus
     tampil penuh selebar halaman tanpa geser mendatar. Lebarnya dibagi rata,
     kepala kolom boleh melipat menjadi dua baris, dan kolom pertama, yang
     berisi nama, diberi jatah lebih. Dibungkus div.gulung supaya tabel
     panjang menggulung sendiri dengan kepala kolom menempel di atas. */
  div.gulung {{
    max-height: 560px; overflow-y: auto;
    border-radius: 12px; border: 1px solid {p["tepi"]};
  }}
  /* Keterangan halaman pada tabel bernavigasi. */
  .nav-tabel {{
    text-align: center; font-size: 12px; color: {p["tinta_2"]};
    padding-top: 9px;
  }}
  div.gulung table.tabel {{ border: none; border-radius: 0; }}
  table.tabel.rata {{ table-layout: fixed; font-size: 11.5px; }}
  table.tabel.rata th {{
    /* Kepala kolom boleh melipat pada spasi, tetapi tidak di tengah kata.
       Lipatan bebas pernah memenggal DIUCAPKAN menjadi DIUCAPKA dan N,
       yang terbaca seperti salah cetak. */
    white-space: normal; overflow-wrap: break-word; vertical-align: bottom;
    font-size: 9.5px; padding: 8px 4px;
    position: sticky; top: 0; z-index: 2;
  }}
  table.tabel.rata td {{ overflow-wrap: anywhere; padding: 7px 5px; }}
  /* Seluruh kolom dirata tengah, termasuk yang berjenis angka, kecuali kolom
     pertama yang berisi nama: dirata kiri, diberi jatah lebar lebih, dan
     dipaksa satu baris supaya tinggi barisnya seragam. */
  table.tabel.rata td.kanan, table.tabel.rata th.kanan,
  table.tabel.rata td.kiri, table.tabel.rata th.kiri {{
    text-align: center;
  }}
  table.tabel.rata th:first-child,
  table.tabel.rata td:first-child {{
    width: 24%; text-align: left; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
  }}
  /* Kolom kedua memuat rentang tahun seperti 2013-2025, yang harus utuh
     dalam satu baris. Tanpa jatah lebar tersendiri, kolom itu ikut dibagi
     rata dan rentangnya terpotong menjadi dua baris. */
  table.tabel.rata th:nth-child(2),
  table.tabel.rata td:nth-child(2) {{
    width: 11%; white-space: nowrap;
  }}

  /* Ragam uraian: tabel dua lajur berisi kata dan penjelasannya.
     Ragam rata di atas dibuat untuk tabel peringkat berangka, dan dipakai
     di sini hasilnya kacau. Lajur kedua di sana diberi lebar sebelas persen
     serta dilarang melipat, sebab isinya rentang tahun, sehingga kalimat
     penjelasan terpotong di tepi kanan. Lajur pertamanya diberi jatah dua
     puluh empat persen, sehingga di antara kata pendek seperti Amar dan
     penjelasannya menganga ruang kosong selebar seperempat halaman. Dan
     seluruh lajur teksnya dirata tengah, yang membuat kalimat panjang tidak
     punya tepi kiri yang sama untuk diikuti mata. */
  table.tabel.uraian {{ table-layout: fixed; }}
  table.tabel.uraian th,
  table.tabel.uraian td {{
    text-align: left; vertical-align: top; white-space: normal;
    overflow-wrap: break-word; padding: 9px 12px; line-height: 1.55;
  }}
  table.tabel.uraian th:first-child,
  table.tabel.uraian td:first-child {{
    width: 26%; font-weight: 600;
  }}

  /* --- Panel lipat ------------------------------------------------------ */
  div[data-testid="stExpander"] {{
    border: none !important; border-top: 1px solid {p["tepi"]} !important;
    border-radius: 0 !important; background: transparent;
  }}
  div[data-testid="stExpander"] summary {{ font-size: 13px; }}

  /* Lipatan penjelasan. Bentuknya sengaja dibuat sekecil tautan, bukan
     sepanjang panel: yang dilipat adalah lanjutan alinea yang sudah dimulai
     tepat di atasnya, sehingga sebuah kotak bergaris justru memutus bacaan
     yang seharusnya menyambung. Garis atas bawaan panel dicabut, dan tepinya
     dirapatkan supaya sejajar dengan alinea pembukanya. */
  div[class*="st-key-lipat-"] div[data-testid="stExpander"],
  div[class*="st-key-lipat-"] div[data-testid="stExpander"] details {{
    border: none !important; background: transparent !important;
    box-shadow: none !important; margin: -8px 0 2px 0 !important;
  }}
  div[class*="st-key-lipat-"] summary {{
    padding: 2px 0 !important; font-size: 12.5px !important;
    font-weight: 600 !important; color: {p["seri"][0]} !important;
    width: fit-content; background: transparent !important;
  }}
  div[class*="st-key-lipat-"] summary p {{
    color: {p["seri"][0]} !important; font-weight: 600 !important;
  }}
  div[class*="st-key-lipat-"] summary:hover {{ text-decoration: underline; }}
  div[class*="st-key-lipat-"] summary svg {{
    fill: {p["seri"][0]} !important;
  }}
  div[class*="st-key-lipat-"] details > div {{
    padding: 0 !important; border: none !important;
  }}

  /* --- Tulisan ---------------------------------------------------------- */
  h3 {{ font-size: 16px !important; font-weight: 620 !important;
        color: {p["tinta"]} !important; margin: 4px 0 2px 0 !important; }}
  .stCaption, div[data-testid="stCaptionContainer"] p {{
    color: {p["tinta_2"]} !important; font-size: 12px !important;
    line-height: 1.55 !important;
  }}
  /* Judul bagian polos tanpa penggal aksen; hiasan berwarna pada judul
     dicabut atas permintaan pemilik. */
  .tingkat {{
    font-size: 11.5px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; color: {p["tinta_2"]};
    margin: 22px 0 6px 0;
  }}
  .jejak {{
    font-size: 13px; color: {p["tinta_2"]}; margin: 0 0 12px 0;
    padding: 9px 14px; border-radius: 10px;
    background: {p["permukaan"]}; border: 1px solid {p["tepi"]};
  }}
  .jejak b {{ color: {p["tinta"]}; font-weight: 620; }}
  .jejak i {{ color: {p["sumbu"]}; font-style: normal; margin: 0 7px; }}
  .saring {{ display: flex; flex-wrap: wrap; gap: 7px; margin: 2px 0 14px 0; }}
  .saring .chip {{
    display: inline-block; padding: 3px 11px; border-radius: 999px;
    font-size: 11.5px; color: {p["tinta_2"]};
    background: {p["permukaan"]}; border: 1px solid {p["tepi"]};
  }}
  .saring .chip b {{ color: {p["tinta_2"]}; font-weight: 700;
                     margin-right: 5px; }}

  /* --- Keterangan kesiapan halaman -------------------------------------- */
  .siap {{
    background: {p["permukaan"]}; border: 1px solid {p["tepi"]};
    border-left: 3px solid {p["awas"]}; border-radius: 10px;
    padding: 14px 18px; margin: 6px 0 18px 0;
    font-size: 13px; color: {p["tinta_2"]}; line-height: 1.6;
  }}
  .siap b {{ color: {p["tinta"]}; }}

  /* --- Isi putusan, disusun menyerupai naskah aslinya ------------------- */
  /* Huruf serif, badan dirata kiri kanan, dan lembar putih bertepi seperti
     kertas. Tata letak asli PDF tidak terbawa oleh ekstraksi teks, jadi ini
     susunan ulang yang menyerupai dokumen putusan, bukan salinan persis. */
  .isi-putusan {{
    max-height: 620px; overflow-y: auto; padding: 34px 44px;
    border: 1px solid {p["tepi"]}; border-radius: 6px;
    background: {p["permukaan"]}; line-height: 1.65; font-size: 13px;
    color: {p["tinta"]};
    font-family: {APTOS};
    font-variant-numeric: normal; letter-spacing: 0;
    box-shadow: 0 1px 4px rgba(0,0,0,.08);
  }}
  /* Baris naskah dibatasi lebarnya. Kolom teks selebar layar besar melelahkan
     dibaca karena mata kehilangan awal baris berikutnya. */
  .isi-putusan p {{
    margin: 0 auto 12px auto; max-width: 78ch;
    text-align: justify; text-justify: inter-word; hyphens: auto;
  }}
  .isi-putusan p.doc-judul {{ text-align: center; font-weight: 700;
                              font-size: 14px; hyphens: none;
                              margin: 2px auto 16px auto; }}
  .isi-putusan p.doc-tengah {{ text-align: center; font-weight: 700;
                               letter-spacing: .04em; hyphens: none;
                               margin: 16px auto; }}
  .isi-putusan p.doc-bagian {{ font-weight: 700; margin-top: 16px;
                               hyphens: none; }}
  .isi-putusan mark {{ background: {lembut(p["awas"], .45)}; color: inherit;
                       padding: 0 2px; border-radius: 3px; }}
</style>
"""


# ---------------------------------------------------------------------------
# Potongan kerangka
# ---------------------------------------------------------------------------

BERKAS_LOGO = ["kemenkeu.png"]

# Bilah judul dan kaki dipindahkan menjadi anak langsung akar dokumen.
# Position fixed hanya terpaku ke jendela selama tidak ada wadah induk yang
# membentuk konteks penampung baru. Streamlit menerapkan transform pada
# beberapa wadahnya, dan begitu salah satunya berada di atas kedua unsur ini,
# fixed berubah perilakunya menjadi seperti absolute sehingga ikut menggulir.
PAKU_TETAP = """
<script>
  (function () {
    try {
      const w = window.parent, d = w.document;

      function pindah() {
        ['.kop', '.kaki'].forEach(function (sel) {
          const semua = Array.prototype.slice.call(d.querySelectorAll(sel));
          if (!semua.length) return;
          // Yang baru dibangun Streamlit selalu berada di dalam pohonnya,
          // bukan sebagai anak langsung akar dokumen. Itu yang dipindahkan,
          // dan salinan lama di akar dokumen dibuang.
          const dalam = semua.filter(function (n) {
            return n.parentElement !== d.body;
          });
          const sasaran = dalam.length ? dalam[dalam.length - 1]
                                       : semua[semua.length - 1];
          semua.forEach(function (n) {
            if (n !== sasaran && n.parentElement === d.body) { n.remove(); }
          });
          if (sasaran.parentElement !== d.body) { d.body.appendChild(sasaran); }
        });
      }

      pindah();

      // Pengawas dipasang sekali dan terus bekerja. Tanpa ini, bilah judul
      // dan kaki hilang begitu berpindah halaman, karena Streamlit membangun
      // ulang seluruh isi sedangkan skrip ini hanya dijalankan sekali pada
      // saat pertama dimuat.
      if (!w.__pakuTetapAktif) {
        w.__pakuTetapAktif = true;
        const pengawas = new MutationObserver(function () {
          clearTimeout(w.__pakuTimer);
          w.__pakuTimer = setTimeout(pindah, 30);
        });
        pengawas.observe(d.body, { childList: true, subtree: true });
      }
    } catch (e) {}
  })();
</script>
"""


def logo_tersedia() -> list[str]:
    keluar = []
    for nama in BERKAS_LOGO:
        jalur = os.path.join(ASET, nama)
        if os.path.exists(jalur):
            with open(jalur, "rb") as fh:
                keluar.append("data:image/png;base64,"
                              + base64.b64encode(fh.read()).decode("ascii"))
    return keluar


def kop(judul: str, sub: str, kanan: str) -> str:
    gambar = "".join(f'<img src="{s}" alt="">' for s in logo_tersedia())
    garis = '<div class="kop-garis"></div>' if gambar else ""
    # Disusun sebagai satu untai tanpa baris kosong. Baris kosong menutup blok
    # HTML pada penerjemah markdown, sehingga sisa tandanya tercetak sebagai
    # tulisan biasa.
    return (
        '<div class="kop">'
        f'{gambar}{garis}'
        f'<div><div class="kop-judul">{judul}</div>'
        f'<div class="kop-sub">{sub}</div></div>'
        f'<div class="kop-kanan">{kanan}</div>'
        '</div>'
    )


def kaki(nama: str, status_data: str, status_tarik: str, aktif: bool,
         kanan: str) -> str:
    warna = TERANG["baik"] if aktif else TERANG["tinta_2"]
    nyala = "berjalan" if aktif else "berhenti"
    return (
        '<div class="kaki">'
        f'<span class="kiri">&copy; 2026 Dikembangkan oleh <b>{nama}</b>'
        '<span class="purwarupa">Purwarupa</span></span>'
        f'<span class="tengah">{status_data}<span class="pisah"> · </span>'
        f'<span class="titik" style="background:{warna}"></span>'
        f'Penarikan <b>{nyala}</b>, {status_tarik}</span>'
        f'<span class="kanan">{kanan}</span>'
        '</div>'
    )


def kartu(label: str, nilai: str, ket: str = "", banding: str = "",
          arah: int = 0, andal: str = "") -> str:
    """
    Kartu angka, dengan pembanding dan penanda keandalan yang boleh kosong.

    Angka tunggal tidak dapat dinilai pembaca. Tingkat dikabulkan enam puluh
    persen itu tinggi atau rendah, naik atau turun, tidak ada yang memberi
    tahu, dan kartu tanpa pembanding memaksa pembaca menebak. Satu pembanding
    saja, misalnya nilai tahun sebelumnya, mengubah kartu dari sekadar angka
    menjadi keterangan.

    Arah sengaja tidak diterjemahkan menjadi baik atau buruk. Naiknya tingkat
    dikabulkan adalah kabar baik bagi wajib pajak dan kabar buruk bagi fiskus,
    sehingga warnanya netral dan yang diberikan hanya penunjuk naik turun.

    Penanda keandalan dititipkan pada kartunya sendiri, bukan hanya di kepala
    halaman, karena pembaca yang menyalin satu angka untuk bahan rapat
    membawa angka itu tanpa peringatan yang tertinggal di atas layar.
    """
    ekor = f'<div class="kpi-ket">{ket}</div>' if ket else ""
    if banding:
        tanda = "▲" if arah > 0 else "▼" if arah < 0 else "•"
        ekor = (f'<div class="kpi-banding"><span class="kpi-arah">{tanda}</span>'
                f'{banding}</div>') + ekor
    tanda_andal = (f'<span class="kpi-andal" title="{andal}">!</span>'
                   if andal else "")
    n = len(str(nilai))
    kelas = ("kpi-nilai sangat-panjang" if n > 34
             else "kpi-nilai panjang" if n > 18 else "kpi-nilai")
    return (f'<div class="kpi"><div class="kpi-label">{label}'
            f'{tanda_andal}</div>'
            f'<div class="{kelas}">{nilai}</div>{ekor}</div>')


# Nama kolom yang isinya persentase. Dipakai untuk memutuskan pembulatan dan
# perataan tanpa perlu disebut ulang di setiap pemanggilan.
NAMA_PERSEN = ("persen", "%", "tingkat", "bagian", "keyakinan", "pangsa",
               "cakupan", "batas bawah", "batas atas")

# Pencocokan nama kolom persentase harus utuh sebagai kata. Pencocokan
# sebagai potongan huruf membuat kolom "Dikabulkan sebagian", yang isinya
# jumlah putusan, terbaca sebagai persentase hanya karena memuat rangkaian
# huruf "bagian", sehingga 122 putusan tercetak sebagai 51,00 persen.
RE_PERSEN = re.compile(
    r"%|\b(?:persen|tingkat|bagian|keyakinan|pangsa|cakupan|"
    r"batas\s+bawah|batas\s+atas|simpangan|selisih)\b", re.IGNORECASE)

# Nama kolom yang isinya bilangan identitas, bukan besaran: tahun, pengenal
# berkas, dan kode. Angka semacam ini tidak boleh diberi pemisah ribuan,
# karena 2,025 bukan tahun dan 140,672 bukan jumlah, melainkan nomor.
NAMA_IDENTITAS = ("tahun", "pengenal", "kode", "periode")


def tabel(df, kolom_kiri: tuple = (), kolom_persen: tuple = (),
          kelas: str = "") -> str:
    """
    Tabel informasi sebagai HTML.

    Tiga aturan yang berlaku sama di seluruh dashboard.

      Tulisan dirata kiri.
      Bilangan dirata kanan, dengan pemisah ribuan, karena yang dibandingkan
      pembaca adalah besarannya dan itu paling mudah dibaca ketika satuannya
      sejajar menurun.
      Persentase dirata tengah dan selalu dibulatkan dua angka di belakang
      koma. Tanpa pembulatan, batas selang kepercayaan tercetak apa adanya
      sebagai 17,309486143904902, yang tidak berarti apa apa dan justru
      memberi kesan ketelitian yang tidak ada.

    Kolom persentase dikenali dari namanya, dan dapat ditambahkan sendiri
    lewat kolom_persen kalau namanya tidak lazim.

    Tabel bawaan Streamlit digambar di atas kanvas, sehingga perataan kolomnya
    tidak dapat disentuh dari gaya halaman sama sekali. Itu sebabnya tabel
    informasi dibuat sendiri di sini.
    """
    # Penjaga ragam rata hanya untuk tabel berlajur banyak.
    #
    # Ragam rata dibuat untuk tabel peringkat: lajur keduanya diberi lebar
    # sebelas persen dan dilarang melipat, sebab isinya rentang tahun. Pada
    # tabel dua lajur berisi kalimat, lajur kedua itu justru lajur uraiannya,
    # sehingga penjelasan terpotong di tepi kanan sedangkan di tengah tabel
    # menganga ruang kosong. Ini pernah lolos ke live pada tabel istilah.
    # Dijaga di sini, bukan hanya diperiksa alat uji, supaya kekeliruan yang
    # sama tidak dapat terulang pada tabel yang dibuat kemudian.
    if kelas == "rata" and len(df.columns) < 3:
        kelas = "uraian"

    def sebagai_angka(nilai):
        if isinstance(nilai, (int, float)) and not isinstance(nilai, bool):
            return float(nilai)
        t = str(nilai).strip().replace("%", "").replace(" persen", "")
        t = t.replace(",", "").strip()
        if not t:
            return None
        try:
            return float(t)
        except ValueError:
            return None

    jenis = {}
    for k in df.columns:
        nama = str(k).lower()
        isi = list(df[k].head(60))
        semua_angka = bool(isi) and all(sebagai_angka(v) is not None for v in isi)
        if k in kolom_kiri:
            jenis[k] = "teks"
        elif k in kolom_persen or (semua_angka
                                   and RE_PERSEN.search(nama)):
            jenis[k] = "persen"
        elif semua_angka and any(x in nama for x in NAMA_IDENTITAS):
            # Bilangan identitas: dirata tengah, tanpa pemisah ribuan.
            jenis[k] = "identitas"
        elif semua_angka:
            jenis[k] = "angka"
        else:
            jenis[k] = "teks"

    # Batas atas tiap kolom persentase, untuk menskalakan panjang batangnya.
    #
    # Yang dipakai nilai terbesar pada kolomnya, bukan seratus persen mati.
    # Pada tabel yang seluruh nilainya berkisar tiga sampai delapan persen,
    # batang berskala seratus akan tampak sama pendek semua dan tidak
    # menerangkan apa apa. Skala relatif membuat urutannya terbaca, dan
    # angkanya tetap tercetak di sel yang sama sehingga besaran sebenarnya
    # tidak pernah hilang.
    puncak = {}
    for k in df.columns:
        if jenis.get(k) != "persen":
            continue
        angka = [sebagai_angka(v) for v in df[k]]
        angka = [x for x in angka if x is not None and x > 0]
        puncak[k] = max(angka) if angka else 0

    def sel(k, v) -> str:
        if jenis[k] == "persen":
            a = sebagai_angka(v)
            if a is None:
                return f"<td>{v}</td>"
            atas = puncak.get(k) or 0
            if atas <= 0:
                return f"<td>{a:,.2f}%</td>"
            lebar = max(0.0, min(100.0, 100.0 * a / atas))
            return (f'<td class="berbatang" style="--isi:{lebar:.1f}%">'
                    f'<span>{a:,.2f}%</span></td>')
        if jenis[k] == "identitas":
            a = sebagai_angka(v)
            teks = f"{a:.0f}" if a is not None and float(a).is_integer() else v
            return f"<td>{teks}</td>"
        if jenis[k] == "angka":
            a = sebagai_angka(v)
            if a is None:
                return f'<td class="kanan">{v}</td>'
            teks = f"{a:,.0f}" if float(a).is_integer() else f"{a:,.2f}"
            return f'<td class="kanan">{teks}</td>'
        return f'<td class="kiri">{v}</td>'

    # Nama kamus ini pernah "kelas" dan menimpa parameter kelas di atasnya,
    # sehingga permintaan ragam tabel seperti rata tidak pernah sampai ke
    # HTML-nya: seluruh aturan lebar kolom dan larangan melipat baris mati
    # diam diam, dan tabel hakim menggelembung dua tiga baris per nama.
    kelas_kepala = {"persen": "", "identitas": "",
                    "angka": " class=\"kanan\"", "teks": " class=\"kiri\""}
    kepala = "".join(f"<th{kelas_kepala[jenis[k]]}>{k}</th>"
                     for k in df.columns)
    badan = "".join(
        "<tr>" + "".join(sel(k, r[k]) for k in df.columns) + "</tr>"
        for _, r in df.iterrows())
    ragam = f" {kelas}" if kelas else ""
    return (f'<table class="tabel{ragam}"><thead><tr>{kepala}</tr></thead>'
            f"<tbody>{badan}</tbody></table>")


def catatan_siap(judul: str, isi: str) -> str:
    return f'<div class="siap"><b>{judul}</b><br>{isi}</div>'


def kepala_halaman(judul: str, dimensi: str | None,
                   lingkup: str | None = None) -> str:
    """
    Kepala halaman terpadu: nama halaman, dimensi, dan lingkup dalam satu
    baris.

    Susunan lama menempatkan penanda dimensi dan pita keandalan lebih dulu,
    sehingga nama halaman baru muncul pada urutan ketiga. Pembaca yang
    berpindah halaman kehilangan penanda paling penting, yaitu ia sedang
    berada di mana. Kini namanya yang pertama, dan keterangan pendukungnya
    menjadi label kecil di sampingnya, bukan baris tersendiri.
    """
    label = ""
    if dimensi:
        label += f'<span class="kh-dim">{dimensi}</span>'
    if lingkup:
        label += f'<span class="kh-lingkup">{lingkup}</span>'
    return (f'<div class="kepala-hal"><h3>{judul}</h3>{label}</div>')


def keterangan_waktu(rentang: str, diperbarui: str | None,
                     diolah: str | None = None) -> str:
    """
    Keterangan kapan, dipasang tepat di atas deret kartu angka.

    Angka tanpa keterangan waktu tidak dapat dikutip: pembaca yang
    menyalinnya ke paparan tidak punya cara menyebutkan angka itu berlaku
    untuk periode apa dan diambil kapan. Keduanya berbeda dan keduanya
    disebut, yaitu rentang tahun putusan yang sedang diamati, dan tanggal
    arsipnya terakhir diperbarui.
    """
    # Dua tanggal, bukan satu, karena artinya berbeda dan pembaca pernah
    # salah membacanya. Yang satu tanggal berkas terakhir ditarik dari
    # peladen Sekretariat, yang satu lagi tanggal arsipnya terakhir diolah
    # ulang. Ketika hanya tanggal tarikan yang tampil, arsip yang baru
    # diolah kemarin terbaca seolah berhenti diurus tiga minggu lalu.
    ekor = (f'<span class="pisah">·</span>berkas terakhir ditarik '
            f'<b>{diperbarui}</b>' if diperbarui else "")
    if diolah:
        ekor += (f'<span class="pisah">·</span>terakhir diolah '
                 f'<b>{diolah}</b>')
    return ('<div class="kapan">Angka pada halaman ini mencakup putusan '
            f'tahun <b>{rentang}</b>{ekor}</div>')


def pita_andal(item: list, n: int) -> str:
    """
    Pita penanda keandalan di kaki tiap halaman.

    Angka pada halaman berdiri di atas ruas yang kelengkapannya berbeda
    jauh, dari 48 sampai 99 persen, dan pembaca tidak punya cara membedakan
    mana angka yang kokoh dan mana yang taksiran dari sebagian data. Pita
    ini menyatakan berapa persen putusan dalam lingkup yang ruas penopangnya
    terbaca, dengan warna sebagai isyarat cepat: hijau di atas 85, kuning di
    atas 55, merah di bawahnya.

    Dashboard analitik yang tidak menyatakan batas datanya akan kehilangan
    kepercayaan justru pada saat pertama kali angkanya dibantah orang.
    """
    biji = []
    for label, persen in item:
        kelas = ("andal-baik" if persen >= 85
                 else "andal-awas" if persen >= 55 else "andal-genting")
        biji.append(f'<span class="andal {kelas}"><i></i>'
                    f'{label} {persen:.0f}%</span>')
    # Susunan kalimatnya sengaja awam. Sebutan teknis seperti ruas penopang
    # sempat dipakai dan pembaca tidak paham maksudnya; yang ingin
    # disampaikan sederhana saja: dari semua putusan yang sedang tampil,
    # berapa persen yang bagian datanya berhasil terbaca.
    # Kalimat penutup hanya ditambahkan ketika memang ada bagian yang perlu
    # diwaspadai. Pada halaman yang seluruh ruasnya hijau, kalimat itu hanya
    # menambah panjang tanpa menambah keterangan.
    perlu = any(pr < 85 for _, pr in item)
    ekor = ('<span class="andal-ket">Bagian kuning atau merah sebaiknya '
            'dibaca sebagai perkiraan.</span>') if perlu else ""
    return ('<div class="andal-pita"><span class="andal-judul">'
            f'Kelengkapan data, dari {n:,} putusan yang tampil:</span>'
            + "".join(biji) + ekor + '</div>')


# ---------------------------------------------------------------------------
# Ikon menu navigasi
#
# Ikon digambar sebagai bentuk bertopeng supaya warnanya mengikuti warna
# tulisan dan selalu satu warna. Karena daftar halaman berubah ubah menurut
# modul pengguna, aturan CSS-nya, yang terikat urutan, dibangkitkan setiap
# kali menu digambar.
# ---------------------------------------------------------------------------

_IKON_NAV = {
    "Beranda": "%3Cpath d='M3 11l9-8 9 8'/%3E%3Cpath d='M5 9.5V21h14V9.5'/%3E%3Cpath d='M10 21v-6h4v6'/%3E",
    "Ringkasan Eksekutif": "%3Cpath d='M4 20V4h9l3 3h4v13z'/%3E%3Cpath d='M8 13h8M8 17h5'/%3E",
    "Nilai Sengketa": "%3Crect x='2' y='6' width='20' height='12' rx='2'/%3E%3Ccircle cx='12' cy='12' r='2.5'/%3E%3Cpath d='M5.5 9h.01M18.5 15h.01'/%3E",
    "Risalah Putusan": "%3Ccircle cx='11' cy='11' r='7'/%3E%3Cpath d='M20 20l-4-4'/%3E",
    "Pola Putusan Sejenis": "%3Cpath d='M4 20V10M10 20V4M16 20v-7M22 20H2'/%3E",
    "Konsistensi Putusan Hakim": "%3Ccircle cx='12' cy='12' r='9'/%3E%3Cpath d='M12 16v-5M12 8h.01'/%3E",
    "Sengketa Berulang": "%3Cpath d='M3 17l5-6 4 3 5-7'/%3E%3Cpath d='M17 7h4v4'/%3E",
    "Tema Sengketa": "%3Cpath d='M4 4h8l8 8-8 8-8-8z'/%3E%3Ccircle cx='8.5' cy='8.5' r='1.4'/%3E",
    "Mutu Ketetapan": "%3Cpath d='M9 11l2 2 4-5'/%3E%3Cpath d='M20 12v7H4V5h9'/%3E",
    "Pilihan Upaya Hukum": "%3Cpath d='M12 21V3'/%3E%3Cpath d='M12 5h6l2 2-2 2h-6'/%3E%3Cpath d='M12 12H6l-2 2 2 2h6'/%3E",
    "Pasal Penentu": "%3Cpath d='M12 3v18M4 21h16'/%3E%3Cpath d='M5 7l-2.5 5a3 3 0 0 0 5 0zM19 7l-2.5 5a3 3 0 0 0 5 0z'/%3E%3Cpath d='M6 7h12'/%3E",
    "Unit Penerbit Ketetapan": "%3Cpath d='M3 21h18'/%3E%3Cpath d='M5 21V4l8-2v19'/%3E%3Cpath d='M13 21h6V9l-6-2'/%3E%3Cpath d='M8 8h.01M8 12h.01M8 16h.01'/%3E",
    "Istilah Sederhana": "%3Cpath d='M3 5.5h6a3 3 0 0 1 3 3V20a2.5 2.5 0 0 0-2.5-2.5H3z'/%3E%3Cpath d='M21 5.5h-6a3 3 0 0 0-3 3V20a2.5 2.5 0 0 1 2.5-2.5H21z'/%3E",
    "Profil Hakim": "%3Cpath d='M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2'/%3E%3Ccircle cx='12' cy='7' r='4'/%3E",
    "Durasi Penyelesaian Sengketa": "%3Ccircle cx='12' cy='12' r='9'/%3E%3Cpath d='M15 9l-2 5-5 2 2-5z'/%3E",
    "Karakter Memutus": "%3Ccircle cx='7' cy='16' r='2.4'/%3E%3Ccircle cx='13' cy='9' r='2.4'/%3E%3Ccircle cx='18.5' cy='14' r='2'/%3E%3Cpath d='M3 21h18'/%3E",
    "Banding Unit": "%3Cpath d='M12 3v18'/%3E%3Crect x='3' y='7' width='6' height='11' rx='1'/%3E%3Crect x='15' y='11' width='6' height='7' rx='1'/%3E",
    "Panduan Analisis": "%3Ccircle cx='12' cy='12' r='9'/%3E%3Cpath d='M12 16v.01'/%3E%3Cpath d='M12 13a2.5 2.5 0 0 0 1.5-4.5 2.5 2.5 0 0 0-3.9 2'/%3E",
    "Metodologi": "%3Cpath d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/%3E%3Cpath d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/%3E",
}

_IKON_AWAL = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
              "viewBox='0 0 24 24' fill='none' stroke='%23000' "
              "stroke-width='1.8' stroke-linecap='round' "
              "stroke-linejoin='round'%3E")


def kunci_nav(halaman: str) -> str:
    """Kunci tombol menu, dipakai bersama oleh dashboard dan gaya menu."""
    return "nav-" + re.sub(r"[^a-z0-9]+", "-", str(halaman).lower()).strip("-")


def ikon_nav(daftar: list, terpilih: str = "", gelap: bool = False) -> str:
    """Aturan topeng ikon dan penanda halaman terpilih, disasar lewat kunci
    tombol. Halaman tanpa ikon terdaftar dibiarkan tanpa topeng, sengaja
    mencolok supaya kelalaiannya cepat ketahuan."""
    p = palet(gelap)
    aturan = []
    for h in daftar:
        isi = _IKON_NAV.get(h)
        if not isi:
            continue
        u = _IKON_AWAL + isi + "%3C/svg%3E"
        aturan.append(
            f'section[data-testid="stSidebar"] .st-key-{kunci_nav(h)} '
            f'button p::before {{'
            f'-webkit-mask: url("{u}") no-repeat center/contain;'
            f'mask: url("{u}") no-repeat center/contain;}}')
    if terpilih:
        # Halaman terpilih ditandai pil bernuansa biru lembut, mengikuti
        # bahasa dashboard admin modern: warnanya cukup jelas untuk terlihat
        # sekali pandang, tulisannya tetap tinta penuh supaya kontrasnya
        # tidak turun.
        k = kunci_nav(terpilih)
        aturan.append(
            f'section[data-testid="stSidebar"] .st-key-{k} button {{'
            f'background: {lembut(p["seri"][0], .14)} !important;'
            f'border-color: {lembut(p["seri"][0], .35)} !important;'
            f'box-shadow: none !important;}}')
        aturan.append(
            f'section[data-testid="stSidebar"] .st-key-{k} button p {{'
            f'color: {p["tinta"]} !important; font-weight: 650 !important;}}')
    return "<style>" + "\n".join(aturan) + "</style>"


# ---------------------------------------------------------------------------
# Penyusunan ulang teks putusan
# ---------------------------------------------------------------------------

RE_SPASI_HURUF = re.compile(r"\b(?:[A-Z] ){2,}[A-Z]\b")
PENANDA_ALINEA = re.compile(
    r"^(?:bahwa\b|Bahwa\b|Menimbang\b|Mengingat\b|Memutuskan\b|MENGADILI\b|"
    r"MEMUTUSKAN\b|Pendapat\b|Menurut\b|Demikian\b|DEMI\b|PUTUSAN\b|"
    r"[A-Z][A-Z\s]{4,}$)")


def alinea(teks: str) -> list[str]:
    """
    Susun ulang teks hasil ekstraksi menjadi alinea yang dapat dibaca.

    Ekstraksi PDF memotong baris mengikuti tata letak halaman, bukan mengikuti
    kalimat, sehingga rangkaian seperti Pajak Penghasilan Pasal 21 Masa Pajak
    Maret 2021 pecah menjadi satu kata per baris. Baris disambung kembali
    kecuali baris sebelumnya berakhir dengan titik, titik koma, atau titik dua,
    atau baris ini diawali penanda bagian yang lazim pada risalah.
    """
    t = RE_SPASI_HURUF.sub(lambda m: m.group(0).replace(" ", ""),
                           teks.replace("\r", ""))
    t = re.sub(r"[ \t]+", " ", t)
    # Baris yang seluruhnya huruf besar dan pendek adalah kepala bagian,
    # seperti MENGADILI atau DEMI KEADILAN BERDASARKAN KETUHANAN YANG MAHA
    # ESA. Kepala bagian berdiri sendiri: baris sesudahnya tidak boleh
    # dirapatkan kepadanya walaupun ia tidak diakhiri tanda baca.
    kepala_caps = re.compile(r"^[A-Z0-9 .,:()\-/]{4,70}$")

    keluar: list[str] = []
    for baris in (b.strip() for b in t.split("\n")):
        if not baris:
            continue
        if (keluar and not re.search(r"[.;:]$", keluar[-1])
                and not PENANDA_ALINEA.match(baris)
                and not (kepala_caps.match(keluar[-1])
                         and any(c.isalpha() for c in keluar[-1]))):
            keluar[-1] += " " + baris
        else:
            keluar.append(baris)

    # Pas akhir: potongan pendek dirapatkan ke alinea berikutnya.
    #
    # Nama pihak kerap terpecah oleh tata letak PDF menjadi baris baris
    # pendek, seperti PT, lalu SAKAE, lalu RIKEN INDONESIA beserta alamatnya.
    # Aturan huruf besar di atas menganggap potongan itu kepala bagian dan
    # memecahnya menjadi alinea sendiri sendiri. Alinea yang sangat pendek
    # dan tidak diakhiri tanda baca kalimat bukan kepala bagian, melainkan
    # serpihan, jadi disambungkan kembali.
    KEPALA_SAH = re.compile(
        r"^(?:MENGADILI|MEMUTUSKAN|DEMI KEADILAN|PUTUSAN|MENIMBANG|"
        r"MENGINGAT|DUDUK PERKARA)", re.IGNORECASE)
    rapat: list[str] = []
    for a in keluar:
        if (rapat
                and len(rapat[-1]) < 25
                and not re.search(r"[.;:]$", rapat[-1])
                and not KEPALA_SAH.match(rapat[-1])):
            rapat[-1] += " " + a
        else:
            rapat.append(a)
    return rapat


RE_KEPALA_DOK = re.compile(r"^[A-Z0-9 .,:()\-/]{4,70}$")


def kelas_alinea(a: str) -> str:
    """
    Kelas tampilan untuk satu alinea putusan, meniru susunan dokumen aslinya.

    Kepala dokumen seperti PUTUSAN Nomor, DEMI KEADILAN, dan MENGADILI pada
    naskah asli dirata tengah dan ditebalkan. Deteksinya dari bentuk, yaitu
    baris pendek yang seluruhnya huruf besar, atau pembuka baku putusan.
    Tata letak asli PDF tidak terbawa oleh ekstraksi teks, jadi ini susunan
    ulang yang menyerupai, bukan salinan persis.
    """
    ringkas = a.strip()
    if ringkas.upper().startswith(("PUTUSAN NOMOR", "PUTUSAN PENGADILAN")):
        return "doc-judul"
    if ringkas.upper().startswith("DEMI KEADILAN"):
        return "doc-tengah"
    if re.match(r"^(?:MENGADILI|MEMUTUSKAN|M E N G A D I L I)\b[:\s]*$",
                ringkas, re.IGNORECASE):
        return "doc-tengah"
    if RE_KEPALA_DOK.match(ringkas) and len(ringkas) < 60 and any(
            c.isalpha() for c in ringkas):
        return "doc-bagian"
    return ""
