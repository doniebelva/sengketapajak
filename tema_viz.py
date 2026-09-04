#!/usr/bin/env python3
"""
tema_viz.py

Palet, tema bagan, gaya halaman, dan potongan kerangka untuk
Belajar Analitik Sengketa Pajak.

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
    # Warna kop dan penanda pilihan, keluarga hijau kebiruan.
    #
    # Sebelumnya biru royal dan navy, yaitu warna Kementerian Keuangan, dan
    # bersama lambangnya membuat situs ini terbaca sebagai terbitan resmi
    # padahal bukan. Warna resmi milik lembaganya, bukan milik siapa pun yang
    # mengolah datanya. Tulisan putih di atas warna paling terang di sini
    # berkontras sekitar tujuh setengah banding satu, jauh di atas ambang.
    "kop_terang": "#087274",
    "kop": "#06585b",
    "kop_2": "#04403f",
    # Tinta judul, sekeluarga dengan warna kop tetapi cukup gelap untuk
    # dibaca. Judul berwarna hitam biasa membuat halaman terasa seperti
    # naskah, bukan seperti situs, dan tidak ada satu pun tanda bahwa
    # kepalanya, judulnya, dan bagannya berasal dari satu keluarga warna.
    # Kontrasnya 8,03 di atas kartu dan 7,09 di atas latar halaman, keduanya
    # jauh di atas ambang, sehingga warnanya tidak dibayar dengan
    # keterbacaan.
    "tinta_judul": "#0d5a56",
    # Warna ajakan, lawan dari tosca.
    #
    # Tosca sendirian membuat situs ini kalem terus menerus, dan tidak ada
    # satu pun warna yang menyatakan bahwa sesuatu dapat disentuh. Jingga
    # amber dipakai khusus untuk hal yang mengajak, yaitu panah pada pintu,
    # ajakan memilih batang, dan penanda sorotan. Tosca tetap warna
    # keterangan, amber menjadi warna ajakan, sehingga pembaca belajar sekali
    # lalu tahu mana yang hanya memberi tahu dan mana yang mengajak.
    # Nadanya digelapkan sampai lolos ambang keterbacaan. Amber yang lebih
    # cerah tampak lebih bertenaga tetapi hanya mencapai 3,59 di atas latar
    # halaman, dan warna yang tidak terbaca bukan warna yang menarik,
    # melainkan warna yang menghalangi. Yang ini 5,57 di kartu dan 4,92 di
    # latar halaman.
    "ajakan": "#a35207",
    # Warna arah naik turun pada kartu angka. Warna baik dan genting yang
    # dipakai bagan terlalu muda untuk tulisan sekecil ini, hanya 3,35 dan
    # 4,80 di atas kartu putih, sehingga dipakai nada yang lebih gelap:
    # 5,32 untuk naik dan 5,62 untuk turun.
    "arah_naik": "#1f7a4d",
    "arah_turun": "#c62828",
    # Biru tua di bawah ini bukan lagi warna tampilan, melainkan warna data,
    # yaitu penanda unit gabungan pada bagan. Dibiarkan biru supaya sekeluarga
    # dengan warna DJP dan berbeda jelas dari emas DJBC.
    "navy_terang": "#0f4c8f",
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
    "kop_terang": "#076063",
    "kop": "#054749",
    "kop_2": "#033335",
    # Pada mode gelap arahnya dibalik: tinta judulnya justru lebih terang
    # daripada tulisan biasa. Kontrasnya 9,31 di atas kartu.
    "tinta_judul": "#6fd3cb",
    "ajakan": "#f0a24b",
    # Pada mode gelap arahnya dibalik, warnanya justru lebih muda supaya
    # terbaca di atas kartu gelap.
    "arah_naik": "#4fce86",
    "arah_turun": "#ff7b73",
    "navy_terang": "#0d3a6e",
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


# Huruf mengikuti situs rujukan yang diberikan pemilik, Plus Jakarta Sans.
# Bentuknya lebih bulat dan lebih ramah daripada Inter, dan pada judul tebal
# ia memberi watak yang jelas tanpa menjadi hiasan. Inter dipertahankan
# sebagai cadangan pertama, sehingga perangkat yang gagal mengunduh huruf
# utamanya tidak jatuh ke huruf sistem yang bentuknya jauh berbeda.
SANS = ('"Plus Jakarta Sans", "Inter", system-ui, -apple-system, '
        '"Segoe UI", sans-serif')
# Judul memakai keluarga huruf yang berbeda dari isinya.
#
# Satu keluarga untuk segalanya membuat halaman rata rasa: judul hanya
# tampak sebagai tulisan yang lebih tebal, bukan sebagai judul. Sora
# bentuknya geometris dan bertenaga, cocok untuk judul dan angka, sedangkan
# isi tetap memakai huruf yang nyaman dibaca berparagraf panjang. Ketegangan
# antara keduanya itulah yang memberi watak pada halaman.
JUDUL_SANS = ('"Sora", "Plus Jakarta Sans", system-ui, sans-serif')
# Naskah putusan memakai Aptos, huruf baku dokumen pada lingkungan kerja ini.
# Aptos tidak tersedia sebagai huruf web, jadi yang terpasang di perangkat
# pembacalah yang dipakai; pada perangkat tanpa Aptos, cadangannya huruf
# sistem yang bentuknya paling berdekatan.
APTOS = ('"Aptos", "Aptos Display", "Segoe UI Variable Text", "Segoe UI", '
         '"Inter", system-ui, sans-serif')
FONT_URL = ("https://fonts.googleapis.com/css2?"
            "family=Plus+Jakarta+Sans:wght@400;500;600;700;800&"
            "family=Sora:wght@600;700;800&"
            "family=Inter:wght@400;500;600;700&display=swap")

SISI = "2.2rem"       # jarak tepi bidang isi, dipakai juga oleh kop dan kaki
TINGGI_KOP = 66
# Menu duduk pada baris yang sama dengan judul, bukan pada pita tersendiri
# di bawahnya. Dua pita bertumpuk menghabiskan seratus dua puluh piksel di
# kepala tiap halaman untuk keperluan yang muat pada satu baris. Karena itu
# bilah judul bawaan Streamlit, yang memuat menunya, ditindihkan tepat di
# atas kop dengan latar tembus pandang, dan diberi jarak kiri secukupnya
# supaya menunya mulai sesudah judul situs.
TINGGI_NAV = 0
# Menu mulai tepat sesudah nama situs. Kotak pencarian sempat ditaruh di
# antara keduanya, dan itu merampas dua ratus lima puluh piksel dari menu
# sehingga dua kelompok terdorong ke dalam limpahan. Pencariannya kini
# berada di sisi kanan bersama tombol penyaring dan saklar tema.
#
# Angkanya mengikuti panjang nama situs, yang kini dua kata saja.
# Judulnya kembali panjang, jadi menu bergeser mengikutinya.
# Angkanya diukur, bukan dikira kira: pada 1366 piksel judul situs berakhir
# di piksel 324, sehingga jarak 344 sudah menyisakan dua puluh piksel jeda.
JARAK_MENU_KIRI = 344
# Ruang yang dipesan di sisi kanan untuk pencarian, tombol penyaring, dan
# saklar tema. Tanpa pesanan ini bilah menu melebar sampai ke bawah ketiganya,
# dan kelompok menu terakhir tertimpa kotak pencarian.
#
# Semula empat ratus empat, dan itu keliru besar. Perkakas kanan sesungguhnya
# hanya selebar tujuh puluh delapan piksel, jadi dua ratus sembilan puluh satu
# piksel dipesan untuk sesuatu yang tidak ada. Pada layar 1366 piksel, yang
# paling lazim dipakai, bilah menu tinggal tiga ratus empat puluh dua piksel
# padahal kelima kelompoknya perlu tujuh ratus satu, sehingga tiga kelompok
# terakhir terpotong diam diam ke dalam tombol lainnya. Cacat ini sempat luput
# karena pemeriksa hanya membaca kotak batas tiap kelompok, dan kotak batas
# tetap terbaca utuh walaupun butirnya sudah terpotong oleh wadahnya.
RUANG_KANAN = 145
# Kaki halaman kini dua baris, bukan satu.
#
# Baris keduanya memuat keterangan situs yang dahulu berada di bawah judul.
# Ketika tingginya masih dihitung untuk satu baris, baris pertamanya terdorong
# ke atas dan isinya tidak lagi berada di tengah, dan itulah yang terlihat
# sebagai kaki yang posisinya meleset.
TINGGI_KAKI = 64


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
        title=dict(font=dict(size=17, color=p["tinta_judul"], weight=700),
                   x=0,
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
        # Batang dibuat lebih tebal dan sudutnya lebih bulat.
        #
        # Batang tipis bersudut tajam adalah bahasa bagan teknis, dan pada
        # situs yang dibaca orang awam ia terbaca sebagai lampiran laporan,
        # bukan sebagai sajian. Menebalkan batang juga menambah luas warna,
        # sehingga penegasan warna pada batang teratas benar benar terlihat,
        # bukan sekadar garis tipis yang berbeda rona.
        bargap=0.22,
        barcornerradius=10,
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
        # Tebal batang dibatasi dalam piksel, bukan dalam pecahan slot.
        #
        # Jarak antar batang pada template dinyatakan sebagai pecahan lebar
        # slot, sehingga pada bagan yang isinya hanya satu dua batang, slotnya
        # menjadi sangat lebar dan batangnya melar memenuhi kartu. Cacat ini
        # muncul begitu jaraknya dirapatkan untuk menebalkan batang, dan
        # bentuknya bukan bagan lagi melainkan bidang warna besar yang tidak
        # menyatakan besaran apa pun.
        #
        # Yang dihitung di sini tebal yang pantas dalam piksel, lalu
        # dikembalikan menjadi pecahan slot menurut tinggi bagan dan banyak
        # batangnya. Batasnya hanya berlaku ke bawah: bagan berbatang banyak
        # tidak ikut dikuruskan, sebab di sana slotnya memang sudah sempit.
        n_kategori = 0
        for t in fig.data:
            if getattr(t, "type", "") != "bar":
                continue
            # Deret nilainya diperiksa dengan None, bukan dengan atau.
            #
            # Deret angka pada bagan berupa larik, dan larik tidak dapat
            # dinilai benar salah begitu saja, sehingga pemakaian atau pada
            # baris ini menghentikan seluruh halaman dengan keluhan bahwa
            # nilai kebenaran lariknya rancu. Empat halaman jatuh karenanya.
            nilai = getattr(t, "y", None)
            if nilai is None:
                nilai = getattr(t, "x", None)
            if nilai is not None:
                n_kategori = max(n_kategori, len(nilai))
        if n_kategori:
            slot = max(1.0, (tinggi - 90) / n_kategori)
            pecahan = min(0.86, 42.0 / slot)
            if pecahan < 0.86:
                fig.update_traces(width=pecahan, selector=dict(type="bar"))

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
    /* Gradasi hijau kebiruan, dari yang paling terang di sisi judul turun ke
       yang paling dalam di sisi kanan. Tiga perhentian memberi kedalaman
       tanpa mengurangi kontras tulisan putih, yang pada titik paling terang
       pun masih jauh di atas ambang keterbacaan. */
    /* Warna dasar dipasang di bawah gradasinya. Gradasi adalah gambar latar,
       bukan warna latar, sehingga ketika ia gagal digambar atau ketika
       keterbacaan diukur, yang terbaca justru latar halaman yang terang dan
       tulisan putih di atasnya menjadi putih di atas putih. */
    background-color: {p["kop"]};
    background-image: linear-gradient(115deg, {p["kop_terang"]} 0%,
                                      {p["kop"]} 48%, {p["kop_2"]} 100%);
    /* Garis aksen tipis di kaki kop, memakai emas dari palet sendiri. Ia
       memberi kop batas bawah yang tegas tanpa menambah tinggi, dan warnanya
       diambil dari deret bagan supaya kepala halaman sekeluarga dengan
       isinya. */
    border-bottom: 2px solid {p["seri"][1]};
    box-shadow: 0 1px 6px rgba(0,0,0,.22);
  }}
  .kop img {{ height: 40px; width: auto; }}
  .kop-garis {{ width: 1px; height: 36px; background: rgba(255,255,255,.24); }}
  .kop-judul {{ font-family: {JUDUL_SANS};
                font-size: 20px; font-weight: 700; color: #fff;
                line-height: 1.25; letter-spacing: -.004em;
                white-space: nowrap; }}
  /* Sub judul memakai putih 92 persen, bukan 80 persen.
     Toska yang benar benar segar itu terang, dan tulisan putih tipis di
     atasnya jatuh ke bawah ambang keterbacaan. Menebalkan tulisannya
     sedikit membuat warna kop boleh lebih hidup tanpa mengorbankan
     pembacanya: rasio kontrasnya naik dari 4,28 menjadi 5,12. */
  .kop-sub {{ font-size: 13px; color: rgba(255,255,255,.92); margin-top: 3px;
              letter-spacing: .002em; }}
  /* Keterangan situs di kaki halaman. Dahulu tercetak di bawah judul pada
     kop, dan di sana ia mengambil ruang paling mahal di seluruh halaman
     untuk keterangan yang cukup dibaca sekali. Di kaki, keterangan itu tetap
     ada bagi yang mencarinya tanpa menghalangi yang sudah tahu. */
  .kaki-ket {{
    grid-column: 1 / -1; margin-top: 0; padding-top: 5px;
    border-top: 1px solid rgba(255,255,255,.22);
    font-size: 12px; color: rgba(255,255,255,.9); line-height: 1.55;
  }}
  .kop-kanan {{ margin-left: auto; text-align: right;
                font-size: 13px; color: rgba(255,255,255,.84);
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
  /* Bilah navigasi menyambung warna kop, bukan pita putih tersendiri.
     Dua pita bertumpuk dengan warna berbeda terbaca sebagai dua benda,
     padahal keduanya kepala situs yang sama. Warnanya diambil dari ujung
     paling dalam gradasi kop, sehingga kop dan menunya menyatu menurun. */
  /* Bilah judul bawaan ditindihkan di atas kop, bukan ditaruh di bawahnya.
     Latarnya dibuat tembus pandang supaya warna kop yang tampak, dan
     sentuhan dimatikan pada bilahnya sendiri lalu dihidupkan hanya pada
     menunya, supaya bilah selebar layar ini tidak menghalangi saklar tema
     dan tombol lain yang berada di kop. */
  header[data-testid="stHeader"] {{
    background: transparent !important;
    height: {TINGGI_KOP}px !important; min-height: 0 !important;
    /* Bilahnya dipersempit dari kiri, bukan diberi jarak dalam.
       Dengan jarak dalam, lebar bilahnya tetap selebar layar sedangkan
       ruang yang benar benar tersedia bagi menu jauh lebih sempit, dan
       Streamlit yang menghitung sendiri berapa kelompok yang muat menjadi
       meleset: ia menggambar tombol lainnya yang mengaku menyimpan empat
       kelompok padahal kosong. Dengan lebar yang jujur, perhitungannya
       benar dengan sendirinya. */
    left: {JARAK_MENU_KIRI}px !important;
    width: calc(100% - {JARAK_MENU_KIRI}px - {RUANG_KANAN}px) !important;
    padding-left: 0 !important;
    pointer-events: none !important;
    top: 0 !important;
    z-index: 1000003 !important;
  }}
  /* Tiap kelompok menu diberi latar pil sendiri, bukan sekadar tulisan
     putih di atas bilah tembus pandang.
     Alasannya dua. Yang pertama keterbacaan yang dapat diukur: bilah judul
     ini tembus pandang supaya warna kop yang tampak, sehingga tulisan putih
     di atasnya secara ukuran berdiri di atas latar halaman yang terang, dan
     pengaudit tampilan benar ketika menolaknya. Latar pil memberi tulisan
     itu alas yang sungguhan. Yang kedua bentuknya memang lebih terbaca
     sebagai menu, sebab tiap kelompok punya batas yang jelas. */
  header[data-testid="stHeader"] [data-testid="stTopNavSection"] {{
    background: {p["kop"]} !important;
    border-radius: 9px !important;
    padding: 5px 11px !important;
    margin-right: 5px !important;
  }}
  header[data-testid="stHeader"] [data-testid="stTopNavSection"],
  header[data-testid="stHeader"] [data-testid="stTopNavSection"] * {{
    color: #ffffff !important;
  }}
  header[data-testid="stHeader"] [data-testid="stTopNavSection"]:hover {{
    background: {lembut(p["kop_terang"], .92)} !important;
  }}
  /* Pada layar sempit menunya dirapatkan, bukan dilipat.
     Lebar yang dibutuhkan kelima kelompok tujuh ratus satu piksel,
     sedangkan layar 1366 piksel hanya menyediakan enam ratus enam puluh
     satu. Selisihnya ditutup dengan merapatkan jarak dalam tiap kelompok
     dan memajukan pangkal menu, sebab melipat kelompok ke dalam tombol
     lainnya berarti menyembunyikannya dari pembaca, dan justru itu yang
     hendak diperbaiki. Ukuran hurufnya tidak diturunkan. */
  @media (max-width: 1460px) {{
    header[data-testid="stHeader"] {{
      left: 306px !important;
      width: calc(100% - 306px - 122px) !important;
    }}
    header[data-testid="stHeader"] [data-testid="stTopNavSection"] {{
      padding: 5px 6px !important; margin-right: 2px !important;
    }}
    .kop-judul, .kop b {{ font-size: 16px !important; }}
  }}
  /* Tingkat kedua untuk layar 1280 piksel, yang masih lazim pada laptop
     lama. Selisihnya tinggal sekitar tiga puluh piksel, jadi cukup
     dirapatkan sekali lagi tanpa mengurangi ukuran huruf menunya. */
  @media (max-width: 1330px) {{
    header[data-testid="stHeader"] {{
      left: 288px !important;
      width: calc(100% - 288px - 112px) !important;
    }}
    header[data-testid="stHeader"] [data-testid="stTopNavSection"] {{
      padding: 5px 4px !important; margin-right: 1px !important;
    }}
    .kop-judul, .kop b {{ font-size: 15px !important; }}
  }}
  /* Navigasi tetap dapat disentuh walau bilah alat di sebelahnya dimatikan.
     Keduanya bersarang di dalam bilah judul yang sama, dan aturan lama
     mematikan seluruh isinya sekaligus. */
  header[data-testid="stHeader"] [data-testid="stTopNavSection"],
  header[data-testid="stHeader"] [data-testid="stTopNavPopover"],
  header[data-testid="stHeader"] [data-testid="stTopNavLinkContainer"],
  header[data-testid="stHeader"] [data-testid="stTopNavDropdownLink"],
  header[data-testid="stHeader"] [data-testid="stTopNavSection"] * {{
    pointer-events: auto !important;
  }}
  header[data-testid="stHeader"] [data-testid="stTopNavLinkContainer"] a {{
    font-size: 13px; font-weight: 560;
  }}
  /* Lebar bilah alat tidak boleh dikosongkan. Bilah menu bersarang di
     dalamnya, sehingga mengosongkan lebarnya meruntuhkan menu itu sendiri
     menjadi tiga puluh dua piksel dan melipat seluruh kelompok ke dalam
     tombol lainnya. Ini sudah dicoba dan diukur, jadi jangan diulang. */
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
    top: calc({TINGGI_KOP}px + {TINGGI_NAV}px + 12px) !important;
    left: 12px !important;
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
    font-size: 13px; color: {p["tinta_2"]}; margin: 2px 0 12px;
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
    font-size: 13px; color: {p["tinta_2"]};
  }}
  .andal-judul {{ margin-right: 3px; }}
  /* Penanda kelengkapan ditulis sebagai kata bertitik warna, bukan kotak.
     Berkotak, tiga penanda kecil ini bersaing perhatian dengan kartu angka
     di bawahnya, padahal isinya keterangan pinggir. Titik warnanya sudah
     cukup menjadi isyarat cepat, dan tanpa bingkai keduanya berhenti saling
     berebut. */
  .andal {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 1px 0; margin-right: 14px;
    color: {p["tinta_2"]}; font-weight: 560; white-space: nowrap;
  }}
  .andal i {{ width: 7px; height: 7px; border-radius: 50%; }}
  .andal-baik i {{ background: {p["baik"]}; }}
  .andal-awas i {{ background: {p["awas"]}; }}
  .andal-genting i {{ background: {p["genting"]}; }}
  /* Kalimat penutup pita hanya tampil saat ada bagian kuning atau merah,
     karena hanya di situ ia menambah keterangan. */
  .andal-ket {{ font-size: 12.5px; color: {p["tinta_2"]}; }}

  /* Kepala halaman terpadu: nama halaman lebih dulu, keterangan pendukung
     menjadi label kecil di sampingnya. */
  /* Judul halaman mengikuti skala situs rujukan yang diberikan pemilik:
     berukuran besar, bertebal delapan ratus, dan berspasi huruf rapat.
     Judul dua puluh satu piksel tidak pernah terbaca sebagai judul, hanya
     sebagai baris tebal, sehingga halaman terasa datar sejak barisnya yang
     pertama. Skalanya dipinjam, warnanya tetap milik palet sendiri sebab
     situs ini punya mode terang dan gelap sekaligus. */
  .kepala-hal {{
    display: flex; align-items: baseline; flex-wrap: wrap; gap: 12px;
    margin: 4px 0 4px;
  }}
  .kepala-hal h3 {{
    font-family: {JUDUL_SANS};
    font-size: 38px !important; font-weight: 800 !important;
    letter-spacing: -.028em; line-height: 1.12;
    margin: 0 !important; padding: 0 !important;
    /* Warnanya ditegaskan, sebab aturan bawaan Streamlit untuk judul
       mengalahkan warna yang tidak ditegaskan, dan judul halaman tetap
       tercetak hitam walau warnanya sudah diatur. */
    color: {p["tinta_judul"]} !important;
  }}
  /* Judul halaman diberi gradasi dari tosca ke jingga.
     Gradasi pada tulisan berbahaya justru karena enak dipandang: warnanya
     berubah sepanjang kata, sehingga memeriksa satu warna saja tidak
     membuktikan apa apa. Kedua ujungnya beserta sembilan titik di antaranya
     sudah diukur terhadap latar terang dan gelap, dan yang terburuk 5.57
     pada mode terang serta 7.80 pada mode gelap, keduanya masih di atas
     ambang 4.5 untuk tulisan biasa, apalagi untuk judul sebesar ini.
     Warna dasarnya tetap disetel supaya peramban yang tidak mengenal
     pemotongan latar pada tulisan tidak menerima judul yang tak tampak. */
  @supports ((-webkit-background-clip: text) or (background-clip: text)) {{
    .kepala-hal h3 {{
      background-image: linear-gradient(96deg,
        {p["tinta_judul"]} 0%, {p["ajakan"]} 100%);
      -webkit-background-clip: text; background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
  }}
  .kh-dim, .kh-lingkup {{
    font-size: 12px; font-weight: 700; letter-spacing: .05em;
    text-transform: uppercase; padding: 3px 9px; border-radius: 999px;
    white-space: nowrap;
  }}
  .kh-dim {{ color: {p["tinta_2"]}; background: {p["bidang"]};
             border: 1px solid {p["tepi"]}; }}
  .kh-lingkup {{ color: #fff; background: {p["kop"]}; }}

  /* Judul sisi pada mode banding. Dua sisi yang tampil bersebelahan harus
     dapat dibedakan sekali pandang, dan tanpa judul bergaris pemisah
     pembaca mudah tertukar membaca angka kiri sebagai angka kanan. */
  .banding-judul {{
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 10px; margin: 4px 0 12px;
    padding: 9px 13px; border-radius: 10px;
    background: {p["bidang"]}; border: 1px solid {p["tepi"]};
    border-left: 3px solid {p["kop"]};
    font-size: 13.5px; font-weight: 680; color: {p["tinta"]};
  }}
  .banding-judul span {{
    font-size: 13px; font-weight: 550; color: {p["tinta_2"]};
    white-space: nowrap;
  }}

  /* --- Pemilih unit analisis -------------------------------------------- */
  /* Daftar jatuh di puncak bilah samping. Karena inilah pilihan analisis
     utama dashboard, tampilannya ditegaskan: berlatar warna kop dengan
     tulisan putih, sehingga unit yang sedang dibaca terlihat sekali pandang
     tanpa perlu membuka daftarnya. */
  .st-key-lingkup_instansi div[data-baseweb="select"] > div {{
    background: {p["kop"]} !important;
    border-color: {p["kop"]} !important;
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
    color: {p["tinta_2"]} !important; font-size: 13.5px !important;
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

  /* Tombol unduh dibuat mencolok, sebab ia satu satunya tombol yang
     membawa sesuatu keluar dari situs ini.
     Bentuk bawaannya kotak putih bergaris tipis, sama persis dengan tombol
     lain di sekitarnya, sehingga pembaca yang ingin membawa pulang ringkasan
     halaman harus mencarinya. Warnanya kini warna ajakan yang sama dengan
     panah pada kartu pintu, terisi penuh, sehingga terbaca sekali pandang
     sebagai satu satunya hal yang menawarkan sesuatu. Kontras tulisan
     putihnya di atas warna itu 5,57 banding satu. */
  div[data-testid="stDownloadButton"] button {{
    background: {p["ajakan"]} !important;
    border: none !important; color: #ffffff !important;
    border-radius: 999px !important;
    padding: 10px 22px !important; font-weight: 700 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,.16);
    transition: transform .18s ease, box-shadow .18s ease,
                background .18s ease;
  }}
  div[data-testid="stDownloadButton"] button:hover {{
    background: {lembut(p["ajakan"], .88)} !important;
    box-shadow: 0 8px 20px rgba(0,0,0,.2);
    transform: translateY(-1px);
  }}
  div[data-testid="stDownloadButton"] button p,
  div[data-testid="stDownloadButton"] button span,
  div[data-testid="stDownloadButton"] button div {{
    color: #ffffff !important; font-weight: 700 !important;
  }}

  /* --- Kaki, dipaku di dasar jendela, satu baris ------------------------ */
  .kaki {{
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 1000001;
    display: grid; grid-template-columns: auto 1fr auto;
    align-items: center; align-content: center;
    gap: 4px 20px; height: {TINGGI_KAKI}px; padding: 0 {SISI};
    /* Warnanya disamakan dengan kop, sehingga kop dan kaki menjadi sepasang
       penjepit yang mengapit isi halaman. Gradasinya dibalik arah, dari yang
       paling dalam di kiri menuju yang lebih terang di kanan, supaya
       keduanya terbaca sebagai pasangan dan bukan sebagai salinan. Garis
       aksen emas ikut dipasang di tepi atasnya, sejajar dengan garis yang
       sama di kaki kop.

       Ketebalan tulisannya dihitung terhadap ujung gradasi yang paling
       terang, sebab di situlah kontrasnya paling tipis. Pada putih delapan
       puluh dua persen kontrasnya hanya 4,42 dan jatuh di bawah ambang,
       sehingga dinaikkan menjadi sembilan puluh dua persen. */
    background-color: {p["kop"]};
    background-image: linear-gradient(115deg, {p["kop_2"]} 0%,
                                      {p["kop"]} 52%, {p["kop_terang"]} 100%);
    border-top: 2px solid {p["seri"][1]};
    box-shadow: 0 -1px 6px rgba(0,0,0,.22);
    font-size: 13px; color: rgba(255,255,255,.92);
  }}
  .kaki b {{ color: #ffffff; font-weight: 700; }}
  .kaki .kiri {{ display: flex; align-items: center; gap: 9px;
                 white-space: nowrap; }}
  .kaki .tengah {{ justify-self: center; text-align: center; min-width: 0;
                   overflow: hidden; text-overflow: ellipsis;
                   white-space: nowrap; }}
  .kaki .kanan {{ justify-self: end; white-space: nowrap; }}
  .kaki .pisah {{ color: rgba(255,255,255,.5); }}
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
    padding-top: calc({TINGGI_KOP}px + {TINGGI_NAV}px + 48px);
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
    top: calc({TINGGI_KOP}px + {TINGGI_NAV}px + 9px) !important;
    right: 10px !important;
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
  /* Kotak pencarian di dalam kop, bersebelahan dengan nama situs. Bentuknya
     pil putih supaya terbaca sebagai tempat mengetik di atas latar gelap,
     dan lebarnya tetap supaya menu di sebelahnya tidak bergeser geser. */
  .st-key-cari-kop {{
    position: fixed !important; top: 15px !important; right: 232px !important;
    z-index: 1000004 !important; width: 148px !important;
  }}
  .st-key-cari-kop div[data-testid="stElementContainer"] {{
    margin: 0 !important;
  }}
  .st-key-cari-kop input {{
    background: #ffffff !important; color: #16202a !important;
    border-radius: 999px !important; border: none !important;
    padding: 8px 15px !important; font-size: 13.5px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,.18);
  }}
  .st-key-cari-kop input::placeholder {{ color: #6a7480 !important; }}
  /* Panel penyaring dibuat setipis satu baris ketika tertutup, dan judulnya
     diberi warna kop supaya terbaca sebagai kendali, bukan sebagai bagian
     dari isi halaman. */
  .st-key-bilah-kendali div[data-testid="stExpander"] summary {{
    font-size: 13px !important; font-weight: 600 !important;
    color: {p["kop_terang"]} !important; padding: 5px 0 !important;
  }}
  .st-key-bilah-kendali div[data-testid="stExpander"] {{
    border-top: none !important; margin-bottom: 8px !important;
  }}
  .st-key-cari-kop div[data-baseweb="input"] {{
    background: transparent !important; border: none !important;
  }}
  @media (max-width: 1250px) {{
    .st-key-cari-kop {{ display: none !important; }}
  }}

  /* Pembungkus unsur yang letaknya sudah dipaku ke kop dikeluarkan dari
     aliran halaman.
     Kop, kotak pencarian, tombol penyaring, dan saklar tema semuanya dipaku
     ke kepala halaman lewat gaya, sehingga isinya tidak lagi berada di
     aliran. Pembungkusnya tetap ada, dan Streamlit memberi jarak enam belas
     piksel kepada tiap anak wadahnya tanpa peduli anaknya kosong. Lima
     pembungkus kosong itu bersama sama mendorong judul halaman delapan
     puluh piksel ke bawah, dan pembaca melihat ruang menganga di bawah kop
     tanpa satu pun isi di dalamnya. */
  [data-testid="stMain"] div[data-testid="stElementContainer"]:has(> .kop),
  [data-testid="stMain"]
    div[data-testid="stLayoutWrapper"]:has(> .st-key-cari-kop),
  [data-testid="stMain"]
    div[data-testid="stLayoutWrapper"]:has(> .st-key-saring-kop),
  [data-testid="stMain"]
    div[data-testid="stLayoutWrapper"]:has(> .st-key-tema) {{
    position: absolute !important; height: 0 !important;
    margin: 0 !important; padding: 0 !important;
  }}

  /* Tombol penyaring di kop, di sebelah kiri saklar tema. Bentuknya pil
     bertepi tipis di atas latar hijau, cukup terbaca sebagai tombol tanpa
     ikut berebut perhatian dengan menu. Tulisannya berubah sendiri menjadi
     sebutan penyaring yang sedang aktif, sehingga pembaca tahu angkanya
     sedang dipersempit tanpa perlu membuka tombolnya. */
  .st-key-saring-kop {{
    position: fixed !important; top: 16px !important; right: 92px !important;
    z-index: 1000004 !important; width: auto !important;
  }}
  .st-key-saring-kop div[data-testid="stElementContainer"] {{
    margin: 0 !important;
  }}
  /* Latar tombolnya pekat, bukan putih tembus.
     Kopnya sendiri tembus pandang supaya warna gradasi di belakangnya yang
     tampak, sehingga latar putih tembus pada tombol ini secara ukuran
     berdiri di atas latar halaman yang terang, dan tulisan putih di atasnya
     ditolak pengaudit dengan rasio 1,13 pada tiga puluh delapan tempat.
     Warna tosca pekat memberi tulisannya alas yang sungguhan, dan kontrasnya
     naik menjadi delapan banding satu. */
  .st-key-saring-kop button {{
    background: {p["kop"]} !important;
    border: 1px solid {lembut(p["kop_terang"], .9)} !important;
    color: #ffffff !important; border-radius: 999px !important;
    padding: 5px 14px !important; font-size: 13px !important;
    font-weight: 600 !important; min-height: 0 !important;
  }}
  .st-key-saring-kop button:hover {{
    background: {p["kop_terang"]} !important;
  }}
  .st-key-saring-kop button p, .st-key-saring-kop button span {{
    color: #ffffff !important;
  }}
  .saring-judul {{
    font-size: 12.5px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; color: {p["tinta_2"]}; margin-bottom: 8px;
  }}
  @media (max-width: 1100px) {{
    .st-key-saring-kop {{ display: none !important; }}
  }}

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
    font-size: 12px; font-weight: 700; letter-spacing: .08em;
    text-transform: uppercase; color: {p["tinta_2"]};
    margin: 10px 0 6px 2px;
  }}

  /* Nama kelompok di dalam menu. Dibedakan dari judul bagian di atasnya lewat
     ukuran dan garis pemisah, bukan lewat warna yang lebih pudar: tulisan
     sekecil ini akan jatuh di bawah ambang kontras kalau diredupkan. */
  section[data-testid="stSidebar"] .menu-kelompok {{
    font-size: 11px; font-weight: 700; letter-spacing: .07em;
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
    font-size: 13px !important; font-weight: 600 !important;
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
    font-size: 13px !important;
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
  /* Jarak antar lajur dirapatkan mengikuti situs rujukan, yang memakai
     empat belas piksel. Jarak bawaan Streamlit satu rem membuat deret kartu
     tampak berserak, dan pada layar lebar kesannya halaman berisi benda
     benda yang tidak saling berhubungan. */
  div[data-testid="stHorizontalBlock"] {{ gap: 14px !important; }}
  div[data-testid="stColumn"] > div,
  div[data-testid="stColumn"] div[data-testid="stElementContainer"] {{
    height: 100%;
  }}
  /* Pembungkus menurun di dalam lajur ikut diregangkan.
     Dua aturan di atas sudah meregangkan lajur dan wadah unsurnya, tetapi di
     antara keduanya masih ada satu pembungkus menurun yang tingginya
     mengikuti isi. Akibatnya kartu tanpa pembanding berhenti tujuh piksel
     lebih pendek daripada tetangganya, dan pada deret empat kartu
     bersebelahan ketidaksejajaran sekecil itu tetap terlihat sebagai kaki
     yang bergerigi. */
  div[data-testid="stColumn"] div[data-testid="stVerticalBlock"],
  div[data-testid="stColumn"] div[data-testid="stHtml"] {{
    height: 100%;
  }}
  /* Bagan dikecualikan dari peregangan ini, dan pengecualiannya wajib.
     Bagan Plotly membaca tinggi wadahnya lalu menyetel tingginya sendiri
     sebesar itu. Selama wadahnya berbasis tetap, keduanya diam. Begitu
     wadahnya diregangkan mengikuti isi, sedangkan isinya bagan itu sendiri,
     keduanya saling mendorong tanpa henti: tinggi bagan Paling seragam
     terukur naik dari 4.636 ke 5.996 lalu 7.322 dan 8.648 piksel hanya dalam
     dua belas detik, dan batangnya melar menjadi bidang biru sebesar kartu.
     Bagan tetangganya tetap 418 piksel semata mata karena di bawahnya ada
     satu baris keterangan, sehingga bukan bagan itu yang menjadi unsur
     terakhir.
     Yang dilakukan di sini hanya mengecualikan, bukan menimpa. Streamlit
     sudah menyetel basis tetap sebesar tinggi bagannya sendiri, dan
     percobaan menimpanya dengan flex 0 0 auto justru menghapus basis itu
     sehingga bagan yang tadinya sehat ikut lari. */
  div[data-testid="stColumn"] div[data-testid="stVerticalBlock"] > div[data-testid="stElementContainer"]:last-child:not(:has(div[data-testid="stPlotlyChart"])) {{
    flex: 1 1 auto;
  }}
  /* Kartu angka. Garis aksen di tepi atas pernah dipasang dan dicabut atas
     permintaan pemilik; identitas kartu cukup dari bayangan yang sedikit
     terangkat, tanpa hiasan berwarna. */
  /* Kartu angka dibuat rata dan tanpa bingkai.
     Pada tangkapan layar pemilik terlihat jelas dua cacat sekaligus. Yang
     pertama, kartu yang punya pembanding menjadi lebih tinggi daripada yang
     tidak, sehingga kaki kartu tidak sejajar dan barisnya tampak bergerigi.
     Yang kedua, seluruh halaman berisi kotak: penanda kelengkapan kotak,
     panel penyaring kotak, kartu kotak, sehingga tidak ada lagi yang
     menonjol dan mata tidak tahu harus mulai dari mana. Kartu kini hanya
     bidang berlatar tipis dengan sudut lembut, tanpa garis tepi, dan
     keterangan kakinya didorong ke bawah supaya seluruh kaki sejajar. */
  .kpi {{
    /* Bidangnya diberi gradasi tipis, bukan putih rata. Tanpa bingkai dan
       tanpa gradasi, kartu menghilang ke dalam latar halaman dan deretnya
       terbaca sebagai tulisan yang berserak, bukan sebagai kartu. */
    background: linear-gradient(158deg, {lembut(p["kop_terang"], .07)} 0%,
                                {p["permukaan"]} 52%);
    border: none;
    border-radius: 20px; padding: 18px 20px 17px;
    height: 100%; min-height: 128px;
    display: flex; flex-direction: column;
    box-shadow: 0 1px 2px rgba(0,0,0,.04);
    transition: box-shadow .18s ease;
  }}
  .kpi:hover {{ box-shadow: 0 4px 14px rgba(0,0,0,.09); }}
  /* Bingkai warna berputar tiga warna deret bagan sudah dicabut.
     Putarannya dihitung per tiga kolom, sedangkan baris kartu utama berisi
     empat kartu, sehingga kartu pertama dan keempat selalu sewarna dan
     urutannya patah di tengah baris. Yang lebih buruk, warna itu tidak
     menyatakan apa apa: pembaca wajar menyangka biru dan emas membedakan
     jenis angka, padahal hanya membedakan urutan kolom. Warna yang tidak
     berarti apa apa tetapi tampak berarti lebih menyesatkan daripada tidak
     ada warna sama sekali. */
  .kpi-ket {{ margin-top: auto; }}
  .kpi-label {{ font-size: 12px; font-weight: 700; letter-spacing: .07em;
                text-transform: uppercase; color: {p["tinta_2"]}; }}
  /* Angka memakai lebar digit seragam. Tanpa itu angka satu jauh lebih
     sempit daripada angka lain, sehingga deretan kartu bersebelahan tampak
     bergeser geser dan sulit dibandingkan sekilas. */
  /* Tinggi barisnya dilonggarkan mengikuti huruf judul yang baru.
     Sora berbadan lebih tinggi daripada huruf sebelumnya, sehingga pada
     tinggi baris 1,12 kaki angkanya melewati wadah empat piksel dan
     pengaudit tampilan menolaknya sebagai tulisan terpenggal pada seluruh
     kartu sekaligus. Angka memang tidak berekor, tetapi persen dan koma
     punya, dan justru itu yang terpotong. */
  .kpi-nilai {{ font-family: {JUDUL_SANS};
                font-size: 34px; font-weight: 700; color: {p["tinta"]};
                line-height: 1.28; margin-top: 8px; padding-bottom: 2px;
                font-variant-numeric: tabular-nums;
                letter-spacing: -.012em;
                overflow-wrap: anywhere; }}
  /* Nilai berupa nama, bukan angka, kerap jauh lebih panjang daripada
     ruang kartunya. Ukurannya diturunkan menurut panjang tulisan supaya
     namanya utuh terbaca, bukan terpenggal di tengah kata. */
  .kpi-nilai.panjang {{ font-size: 19px; line-height: 1.25; }}
  .kpi-nilai.sangat-panjang {{ font-size: 15px; line-height: 1.3;
                               font-weight: 620; }}
  /* Kartu utama: satu angka terpenting pada tiap halaman, dibuat jauh
     lebih besar daripada tetangganya.
     Sepuluh kartu berukuran sama membuat semuanya tampak sama penting,
     sehingga pembaca tidak punya titik masuk dan membaca kesepuluhnya
     dengan perhatian yang sama, atau tidak membaca satu pun. Satu angka
     yang jauh lebih besar memberi halaman titik mulai, dan kalimat
     tafsirnya menjawab pertanyaan yang selalu menyusul angka besar, yaitu
     lalu apa artinya. */
  .kpi.utama {{
    background: linear-gradient(152deg, {lembut(p["kop_terang"], .1)} 0%,
                                {p["permukaan"]} 55%);
  }}
  /* Angka pahlawan diwarnai gradasi, bukan tinta rata.
     Ia satu satunya angka yang berhak menonjol pada halamannya, dan gradasi
     dari tosca terang ke tosca dalam membuatnya terbaca sebagai sajian,
     bukan sebagai hasil hitungan yang dituliskan begitu saja. Warna
     cadangannya tetap dipasang lebih dahulu, sehingga peramban yang tidak
     mendukung pemotongan latar pada tulisan tetap menampilkan angkanya
     dengan warna yang terbaca, bukan tulisan tembus pandang. */
  .kpi.utama .kpi-nilai {{
    color: {p["tinta_judul"]};
    background: linear-gradient(96deg, {p["kop_terang"]} 0%,
                                {p["kop_2"]} 82%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  .kpi.utama .kpi-nilai {{
    /* Tinggi baris tidak boleh serapat itu pada huruf sebesar ini. Pada
       1,05 kaki huruf melewati wadahnya enam piksel, dan pengaudit tampilan
       menolaknya sebagai tulisan terpenggal. Angka memang tidak berekor
       panjang, tetapi persen dan koma punya, dan justru itu yang terpotong. */
    /* Angka fokus dibuat jauh lebih besar daripada tetangganya. Selisih
       yang tanggung tidak terbaca sebagai penegasan, hanya sebagai
       ketidakrataan. */
    font-size: 62px; font-weight: 800; letter-spacing: -.034em;
    line-height: 1.16; margin-top: 12px; padding-bottom: 3px;
  }}
  .kpi.utama .kpi-label {{
    color: {p["ajakan"]}; font-size: 13px; letter-spacing: .08em;
  }}
  .kpi-tafsir {{
    margin-top: 9px; padding-top: 9px;
    border-top: 1px solid {p["tepi"]};
    font-size: 13.5px; line-height: 1.55; color: {p["tinta"]};
    font-weight: 550;
  }}
  .kpi-ket {{
    font-size: 13px; color: {p["tinta_2"]}; margin-top: auto;
    padding-top: 6px; line-height: 1.5;
  }}

  /* Pembanding pada kartu. Warnanya netral, bukan hijau merah, karena naik
     turunnya angka yang sama berarti kabar baik bagi satu pihak dan kabar
     buruk bagi pihak lain: tingkat dikabulkan yang naik menguntungkan wajib
     pajak dan merugikan fiskus. Yang diberikan hanya penunjuk arah. */
  /* Pembanding ditulis sebagai baris biasa, bukan pil bertepi. Kotak kecil
     di dalam kartu menambah satu lapisan bingkai lagi, dan pada deret kartu
     lapisan itulah yang membuat halaman terasa penuh kotak. */
  /* Arah naik turun diberi warna, atas permintaan pemilik.
     Aturan lama sengaja menahan hijau merah di sini, sebab kenaikan angka
     yang sama berarti kabar baik bagi wajib pajak dan kabar buruk bagi
     fiskus, sehingga warnanya memihak. Modul bawaan situs ini kini wajib
     pajak, dan bagi mereka arahnya memang punya rasa. Kata naik dan turun
     tetap tertulis, tidak diwakili warna saja, supaya pembaca yang tidak
     dapat membedakan warna tetap memahaminya. */
  .kpi-banding {{
    display: flex; align-items: center;
    font-size: 13px; font-weight: 700; color: {p["tinta_2"]};
    margin-top: 7px;
  }}
  .kpi-banding.naik {{ color: {p["arah_naik"]}; }}
  .kpi-banding.turun {{ color: {p["arah_turun"]}; }}
  .kpi-arah {{ margin-right: 5px; font-size: 11px; }}

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
  /* Bagan keluar dari kartu berbingkai.
     Bagan adalah isi utama situs ini, tetapi selama ini ia dikurung dalam
     kartu bergaris tepi yang bahkan punya penggulung sendiri, sehingga
     bagan tampak seperti lampiran yang ditempelkan pada halaman, bukan
     seperti isi halamannya. Bingkainya dicabut, jarak dalamnya dilonggarkan,
     sudutnya disamakan dengan kartu angka, dan latarnya diberi gradasi tipis
     yang sama supaya seluruh halaman terbaca sebagai satu keluarga. */
  div[data-testid="stPlotlyChart"] {{
    background: linear-gradient(158deg, {lembut(p["kop_terang"], .07)} 0%,
                                {p["permukaan"]} 52%);
    border: none;
    border-radius: 20px; padding: 16px 20px 18px 20px;
    box-shadow: 0 1px 2px rgba(0,0,0,.04);
    overflow: visible;
  }}
  div[data-testid="stPlotlyChart"] > div,
  div[data-testid="stPlotlyChart"] .js-plotly-plot {{
    overflow: visible !important;
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
    font-size: 15.5px; line-height: 1.7;
  }}
  div[data-testid="stDataFrame"] {{
    border-radius: 12px; overflow: hidden; border: 1px solid {p["tepi"]};
  }}
  div[data-testid="stDataFrame"] * {{ font-size: 13.5px !important; }}

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
    text-align: center; font-weight: 650; font-size: 12.5px;
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
    padding: 13px 15px; min-height: 104px;
  }}
  div[class*="st-key-kartu-kedua"] .kpi-nilai {{
    font-size: 21px;
  }}
  div[class*="st-key-kartu-kedua"] .kpi-label {{
    font-size: 12px;
  }}
  div[class*="st-key-kartu-kedua"] .kpi-ket {{
    font-size: 12.5px;
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
    border-radius: 20px; transition: box-shadow .15s ease;
  }}
  div[data-testid="stPlotlyChart"]:hover {{
    box-shadow: 0 6px 20px rgba(0,0,0,.09);
  }}
  div[data-testid="stPlotlyChart"] .cursor-pointer,
  div[data-testid="stPlotlyChart"] .points path {{ cursor: pointer; }}

  /* Ajakan memilih di bawah bagan yang dapat diklik. Dicetak kecil dan
     berwarna aksen supaya terbaca sebagai tawaran, bukan sebagai catatan
     kaki yang boleh dilewati. */
  .ajakan-klik {{
    color: {p["ajakan"]} !important; font-weight: 620;
    display: inline-flex; align-items: center; gap: 6px;
    margin: 2px 0 6px 0; font-size: 13.5px; font-weight: 600;
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
  /* Kutipan naskah disajikan dua kolom bila isinya panjang.
     Satu kolom setinggi layar membuat pembaca kehilangan tempatnya, dan
     karena lebar barisnya tetap dibatasi demi kenyamanan membaca, separuh
     kanan bidang tinggal kosong. Dua kolom memakai ruang yang memang sudah
     ada dan memendekkan bloknya menjadi separuh. */
  .anatomi-isi {{
    font-size: 14.5px; line-height: 1.72; color: {p["tinta"]};
    text-align: left; hyphens: none;
    background: {p["bidang"]}; padding: 14px 18px; border-radius: 9px;
    border-left: 3px solid {p["seri"][0]};
  }}
  .anatomi-isi.dua {{
    columns: 2; column-gap: 38px;
    column-rule: 1px solid {p["tepi"]};
  }}
  .anatomi-isi p {{ margin: 0 0 10px 0; }}
  .anatomi-isi p:last-child {{ margin-bottom: 0; }}
  /* Pada layar sempit dua kolom menyisakan baris terlalu pendek. */
  @media (max-width: 1000px) {{
    .anatomi-isi.dua {{ columns: 1; }}
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
    font-size: 13.5px; color: {p["tinta_2"]}; line-height: 1.55;
    margin-bottom: 8px;
  }}

  .lanjut-judul {{
    margin: 26px 0 10px 0; padding-top: 16px;
    border-top: 1px solid {p["tepi"]};
    font-size: 12.5px; font-weight: 700; letter-spacing: .07em;
    text-transform: uppercase; color: {p["tinta_2"]};
  }}
  .lanjut-sebab {{
    font-size: 13.5px; color: {p["tinta_2"]}; line-height: 1.5;
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
    text-align: center; font-size: 13px; color: {p["tinta_2"]};
    padding-top: 9px;
  }}
  div.gulung table.tabel {{ border: none; border-radius: 0; }}
  table.tabel.rata {{ table-layout: fixed; font-size: 13px; }}
  table.tabel.rata th {{
    /* Kepala kolom boleh melipat pada spasi, tetapi tidak di tengah kata.
       Lipatan bebas pernah memenggal DIUCAPKAN menjadi DIUCAPKA dan N,
       yang terbaca seperti salah cetak. */
    white-space: normal; overflow-wrap: break-word; vertical-align: bottom;
    font-size: 12px; padding: 9px 5px;
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

  /* --- Halaman muka ----------------------------------------------------- */
  /* Halaman depan yang langsung membuka deretan kartu angka terbaca sebagai
     aplikasi pemantau, dan pembaca yang belum tahu ini situs apa tidak
     pernah diberi tahu. Bagian di bawah ini menyediakan tiga hal yang selalu
     ada pada halaman muka situs: satu kalimat yang menyatakan gunanya, pintu
     masuk menurut kebutuhan pembaca, dan keterangan isinya. */
  /* Halaman muka dibuka tanpa panel, mengikuti rujukan kedua dari pemilik.
     Panel bergradasi bertepi membuat kalimat pembuka terbaca sebagai kotak
     pengumuman yang ditempelkan pada halaman. Dilepas dari panelnya, kalimat
     itu berdiri sendiri sebagai judul, dan ruang kosong di sekelilingnya
     yang mengerjakan penegasannya, bukan bingkai. */
  .muka {{
    display: flex; align-items: center; gap: 40px;
    padding: 30px 0 26px; margin: 0 0 8px;
    background: transparent; border: none;
  }}
  .muka-judul {{
    font-family: {JUDUL_SANS};
    font-size: 52px; font-weight: 800; color: {p["tinta_judul"]};
    line-height: 1.08; letter-spacing: -.034em; margin: 0 0 16px;
    max-width: 19ch;
  }}
  .muka-sub {{
    font-size: 17.5px; color: {p["tinta_2"]}; line-height: 1.6;
    max-width: 54ch; margin: 0; font-weight: 450;
  }}
  .muka-tanda {{
    display: inline-flex; align-items: center; gap: 7px;
    margin-bottom: 13px; padding: 4px 11px; border-radius: 999px;
    background: {lembut(p["kop_terang"], .14)};
    border: 1px solid {lembut(p["kop_terang"], .3)};
    font-size: 12px; font-weight: 700; letter-spacing: .07em;
    text-transform: uppercase; color: {p["tinta"]};
  }}
  /* Pintu masuk menurut kebutuhan pembaca. Bentuknya tombol Streamlit, sebab
     hanya tombol yang dapat memanggil perpindahan halaman, tetapi gayanya
     dibuat sebagai kartu supaya terbaca sebagai pilihan jalan, bukan sebagai
     daftar perintah. */
  /* Pintu masuk pada halaman muka, dirombak menjadi kartu yang berbicara.
     Bentuk lamanya kotak putih polos dengan tulisan tiga belas piksel yang
     terpaksa tercetak di tengah, sehingga empat pertanyaan terpenting di
     seluruh situs justru tampak seperti tombol setelan. Kini tulisannya
     tujuh belas piksel bertebal tujuh ratus, rata kiri seperti kalimat yang
     memang dibaca, dengan latar bergradasi tosca dan panah di sisi kanan
     yang menyatakan bahwa kartu itu membawa ke suatu tempat. */
  div[class*="st-key-beranda-"] button {{
    position: relative;
    height: 100%; min-height: 104px;
    display: flex !important;
    justify-content: flex-start !important; align-items: center !important;
    padding: 20px 52px 20px 22px !important;
    border-radius: 20px !important;
    border: none !important;
    background: linear-gradient(140deg,
                {lembut(p["kop_terang"], .16)} 0%,
                {lembut(p["kop_terang"], .05)} 42%,
                {p["permukaan"]} 100%) !important;
    box-shadow: 0 1px 2px rgba(0,0,0,.05);
    transition: box-shadow .2s ease, transform .2s ease, background .2s ease;
  }}
  div[class*="st-key-beranda-"] button::after {{
    content: "→"; position: absolute; right: 22px; top: 50%;
    transform: translateY(-50%);
    font-size: 23px; font-weight: 700; color: {p["ajakan"]};
    transition: transform .2s ease;
  }}
  div[class*="st-key-beranda-"] button:hover {{
    background: linear-gradient(140deg,
                {lembut(p["kop_terang"], .3)} 0%,
                {lembut(p["kop_terang"], .12)} 45%,
                {p["permukaan"]} 100%) !important;
    box-shadow: 0 10px 26px rgba(0,0,0,.13);
    transform: translateY(-2px);
  }}
  div[class*="st-key-beranda-"] button:hover::after {{
    transform: translateY(-50%) translateX(4px);
  }}
  div[class*="st-key-beranda-"] button p {{
    font-size: 17px !important; font-weight: 700 !important;
    letter-spacing: -.016em !important;
    line-height: 1.38 !important; color: {p["tinta"]} !important;
    white-space: normal !important; text-align: left !important;
    width: 100% !important; margin: 0 !important;
  }}
  /* Keterangan isi situs, tiga alinea pendek berdampingan. */
  .muka-isi {{
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
    margin: 6px 0 4px;
  }}
  .muka-isi > div {{
    padding: 15px 17px; border-radius: 14px;
    background: {p["permukaan"]}; border: 1px solid {p["tepi"]};
  }}
  .muka-isi b {{
    display: block; font-size: 13.5px; font-weight: 700; color: {p["tinta"]};
    margin-bottom: 6px;
  }}
  .muka-isi span {{
    font-size: 13px; color: {p["tinta_2"]}; line-height: 1.6;
  }}
  /* Tiga angka arsip di sisi kanan halaman muka, menggantikan potret.

     Potret penyusun dilepas atas permintaan pemilik, sesudah ditimbang bahwa
     wajah pada situs yang menganalisis mutu ketetapan membuat sebagian
     pembaca membacanya sebagai orang lembaga yang berbicara, bukan sebagai
     pengolah data terbuka. Namanya tetap tercantum di kaki halaman.

     Yang menggantikannya angka arsip itu sendiri. Disusun menurun dan
     dipisah satu garis tegak, bukan sebagai kartu, supaya ia terbaca sebagai
     keterangan yang menyertai judul dan tidak bersaing dengan deretan kartu
     di bawahnya. */
  .muka-teks {{ flex: 1 1 auto; min-width: 0; }}
  .muka-angka {{
    flex: 0 0 236px; display: flex; flex-direction: column; gap: 15px;
    padding-left: 26px;
    border-left: 2px solid {lembut(p["kop_terang"], .3)};
  }}
  .muka-biji b {{
    display: block; font-family: {JUDUL_SANS};
    font-size: 30px; font-weight: 800; letter-spacing: -.028em;
    line-height: 1.16; color: {p["tinta_judul"]};
  }}
  .muka-biji span {{
    display: block; font-size: 13px; color: {p["tinta_2"]};
    line-height: 1.45; margin-top: 3px;
  }}
  @media (max-width: 1100px) {{
    .muka-angka {{ display: none; }}
  }}
  @media (max-width: 900px) {{
    .muka-isi {{ grid-template-columns: 1fr; }}
    .muka-judul {{ font-size: 32px; max-width: 100%; }}
    .muka-sub {{ font-size: 15.5px; }}
    .muka {{ flex-direction: column-reverse; align-items: flex-start; }}
  }}

  /* --- Ruang belajar ---------------------------------------------------- */
  /* Kartu langkah bernomor. Nomornya dibuat besar dan berwarna ajakan, sebab
     yang membedakan alur belajar dari daftar tautan justru urutannya, dan
     urutan yang tidak terlihat sama saja tidak ada. */
  .langkah {{
    background: linear-gradient(155deg, {lembut(p["kop_terang"], .1)} 0%,
                                {p["permukaan"]} 58%);
    border-radius: 18px; padding: 20px 22px 16px; min-height: 178px;
  }}
  .langkah-nomor {{
    font-family: {JUDUL_SANS}; font-size: 34px; font-weight: 800;
    line-height: 1; color: {p["ajakan"]}; margin-bottom: 10px;
  }}
  .langkah-judul {{
    font-family: {JUDUL_SANS}; font-size: 18px; font-weight: 700;
    line-height: 1.28; color: {p["tinta_judul"]}; margin-bottom: 8px;
  }}
  .langkah-isi {{
    font-size: 13.5px; line-height: 1.6; color: {p["tinta_2"]};
  }}
  /* Kepala perkara yang dibedah, memuat nomor dan amarnya. */
  .bedah-kepala {{
    display: flex; align-items: baseline; flex-wrap: wrap; gap: 12px;
    margin: 6px 0 14px; padding-bottom: 10px;
    border-bottom: 2px solid {lembut(p["kop_terang"], .3)};
  }}
  .bedah-kepala b {{
    font-family: {JUDUL_SANS}; font-size: 19px; font-weight: 700;
    color: {p["tinta_judul"]};
  }}
  .bedah-kepala span {{
    font-size: 12px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; color: {p["ajakan"]};
  }}
  .bedah-judul {{
    font-family: {JUDUL_SANS}; font-size: 16px; font-weight: 700;
    color: {p["tinta_judul"]}; margin: 18px 0 4px;
  }}
  /* Catatan pengajar, yaitu kalimat yang menyuruh pembaca memperhatikan apa.
     Tanpa ini naskah putusan hanya kutipan panjang; dengan ini ia menjadi
     bahan belajar, sebab pembaca diberi tahu apa yang dicari di dalamnya. */
  .bedah-catatan {{
    font-size: 13.5px; line-height: 1.6; color: {p["tinta_2"]};
    border-left: 3px solid {p["ajakan"]}; padding-left: 12px;
    margin: 0 0 10px;
  }}
  .uji-jawab {{
    margin: 12px 0 6px; padding: 13px 16px; border-radius: 14px;
    font-size: 15px; line-height: 1.55; color: {p["tinta"]};
  }}
  .uji-jawab.tepat {{ background: {lembut(p["arah_naik"], .14)}; }}
  .uji-jawab.meleset {{ background: {lembut(p["arah_turun"], .12)}; }}

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
    padding: 2px 0 !important; font-size: 13.5px !important;
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
    color: {p["tinta_2"]} !important; font-size: 13px !important;
    line-height: 1.55 !important;
  }}
  /* Judul bagian polos tanpa penggal aksen; hiasan berwarna pada judul
     dicabut atas permintaan pemilik. */
  /* Judul bagian berhenti menjadi label kapital kecil.
     Sebagai kapital kecil sebelas piksel, ia sejajar dengan keterangan
     pinggir, sehingga halaman tidak punya tingkatan sama sekali: semua
     tulisan tampak sama pentingnya. Kini ia judul sungguhan, cukup besar
     untuk memotong halaman menjadi bagian yang terbaca sekilas. */
  .tingkat {{
    font-family: {JUDUL_SANS};
    font-size: 22px; font-weight: 700; letter-spacing: -.02em;
    color: {p["tinta_judul"]}; margin: 30px 0 10px 0; line-height: 1.25;
    display: flex; align-items: center; gap: 10px;
  }}
  /* Penanda tegak kecil di depan judul bagian.
     Halaman panjang berisi banyak bagian, dan tanpa penanda apa pun mata
     tidak punya tempat berpegang ketika menggulir; judul bagian berbaur
     dengan tulisan lain di sekitarnya. Satu garis tegak bertosca cukup
     memberi irama tanpa menambah kotak baru, dan warnanya menyambungkan
     bagian bagian halaman dengan kepala situs. */
  /* Penandanya ikut bergradasi dari tosca ke jingga, senada dengan judul
     halaman, dan dibuat lebih tebal serta lebih tinggi supaya warnanya
     benar benar terbaca sebagai irama halaman, bukan sekadar garis tipis.
     Judul bagiannya sendiri tetap satu warna: empat puluh delapan judul
     bergradasi dalam satu situs berubah menjadi bising, dan yang hendak
     dicapai justru susunan yang jelas mana induk mana anak. */
  .tingkat::before {{
    content: ""; flex: 0 0 6px; width: 6px; height: 26px;
    border-radius: 999px;
    background: linear-gradient(180deg,
      {p["kop_terang"]} 0%, {p["ajakan"]} 100%);
  }}
  /* Infografik alur.
     Penjelasan yang panjang tentang urutan kejadian selalu kalah oleh
     gambar urutan itu sendiri. Pembaca yang ingin tahu di titik mana
     perkaranya bisa gugur harus menyusuri seratus dua puluh sembilan kata
     untuk menemukan jawabannya, padahal jawabannya satu langkah dalam
     rangkaian. Bentuk ini menaruh rangkaiannya di depan mata, dan langkah
     yang mematikan perkara diberi warna merah supaya langsung terlihat. */
  .alur {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 8px 0 16px; }}
  .alur-langkah {{
    flex: 1 1 200px; min-width: 200px; padding: 14px 16px;
    background: {p["permukaan"]}; border: 1px solid {p["tepi"]};
    border-radius: 13px;
  }}
  .alur-langkah.gugur {{
    border-color: {p["arah_turun"]}; border-width: 2px;
    background: {lembut(p["arah_turun"], .07)};
  }}
  .alur-nomor {{
    width: 27px; height: 27px; border-radius: 999px; color: #ffffff;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 13px; margin-bottom: 9px;
    background: linear-gradient(135deg,
      {p["kop_terang"]} 0%, {p["ajakan"]} 100%);
  }}
  .alur-langkah.gugur .alur-nomor {{
    background: {p["arah_turun"]};
  }}
  .alur-judul {{
    font-family: {JUDUL_SANS}; font-size: 15.5px; font-weight: 700;
    color: {p["tinta_judul"]}; margin-bottom: 5px; line-height: 1.3;
  }}
  .alur-langkah.gugur .alur-judul {{ color: {p["arah_turun"]}; }}
  .alur-isi {{
    font-size: 13.5px; color: {p["tinta_2"]}; line-height: 1.55;
  }}

  /* Infografik butir bertanda.
     Dipakai untuk peringatan dan pengertian pendek yang sebelumnya ditulis
     sebagai alinea beruntun. Tiga alinea beruntun dibaca sebagai satu blok
     dan yang terbaca hanya kalimat pertamanya, sedangkan tiga kartu
     bersebelahan terbaca ketiganya. */
  .poin {{
    display: grid; gap: 12px; margin: 8px 0 16px;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  }}
  .poin-kartu {{
    padding: 15px 17px; border-radius: 13px; background: {p["bidang"]};
    border-left: 5px solid {p["kop_terang"]};
  }}
  .poin-kartu.awas {{ border-left-color: {p["ajakan"]}; }}
  .poin-tanda {{
    font-family: {JUDUL_SANS}; font-size: 25px; font-weight: 800;
    line-height: 1; margin-bottom: 8px; color: {p["kop_terang"]};
  }}
  .poin-kartu.awas .poin-tanda {{ color: {p["ajakan"]}; }}
  .poin-judul {{
    font-family: {JUDUL_SANS}; font-size: 15px; font-weight: 700;
    color: {p["tinta"]}; margin-bottom: 4px; line-height: 1.3;
  }}
  .poin-isi {{ font-size: 13.5px; color: {p["tinta_2"]}; line-height: 1.55; }}

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
    font-size: 13px; color: {p["tinta_2"]};
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

# Tidak ada lambang resmi di kop.
#
# Sebelumnya lambang Kementerian Keuangan terpasang di sisi kiri, dan itu
# keliru arah. Situs ini mengolah dokumen terbuka milik publik, tetapi bukan
# terbitan lembaga mana pun, dan lambang resmi di kepala halaman menyatakan
# sebaliknya kepada tiap pembaca yang datang. Kalau kelak ada lambang, yang
# pantas dipasang adalah lambang penyusunnya sendiri.
BERKAS_LOGO: list[str] = []
BERKAS_POTRET = "muka-penyusun.webp"

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


def potret_penyusun() -> str:
    """Potret penyusun sebagai data tertanam, kosong bila berkasnya tidak ada.

    Ditanam langsung ke dalam halaman, bukan ditautkan sebagai berkas, sebab
    Streamlit tidak menyajikan berkas statis dari folder aset, dan gambar
    sembilan belas kilobita masih jauh lebih murah daripada satu permintaan
    jaringan tambahan pada tiap muat halaman.
    """
    jalur = os.path.join(ASET, BERKAS_POTRET)
    if not os.path.exists(jalur):
        return ""
    with open(jalur, "rb") as fh:
        return ("data:image/webp;base64,"
                + base64.b64encode(fh.read()).decode("ascii"))


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
        + (f'<div class="kop-sub">{sub}</div>' if sub else "")
        + '</div>'
        f'<div class="kop-kanan">{kanan}</div>'
        '</div>'
    )


KETERANGAN_SITUS = (
    "Belajar membaca putusan Pengadilan Pajak dari risalah yang terbuka "
    "untuk umum &middot; Bukan terbitan resmi lembaga mana pun &middot; "
    "Sumber data: setpp.kemenkeu.go.id/risalah")


def kaki(nama: str, status_data: str, status_tarik: str, aktif: bool,
         kanan: str, diolah: str = "") -> str:
    # Keadaan penarikan diganti tanggal pembaruan data.
    #
    # Kalimat lamanya berbunyi penarikan berhenti sekian jam lalu, dan itu
    # keterangan mesin, bukan keterangan yang dicari pembaca. Pembaca ingin
    # tahu satu hal saja, yaitu angka yang sedang dibacanya berasal dari arsip
    # kapan. Keadaan mesin penariknya sendiri tetap tercatat pada catatan
    # penyegaran, tempat yang memang untuk itu.
    _ = (aktif, status_tarik)
    # Tanggal arsip terakhir diolah ikut di kaki, bukan di sisi kanan kop.
    # Di kop ia menempati ruang yang justru diperlukan menu, sedangkan yang
    # membacanya hanya pembaca yang sedang menimbang seberapa mutakhir
    # angkanya, dan pembaca itu memang mencarinya sampai ke kaki halaman.
    tanggal = (f'<span class="pisah"> &middot; </span>'
               f'Tanggal update data <b>{diolah}</b>') if diolah else ""
    return (
        '<div class="kaki">'
        f'<span class="kiri">&copy; 2026 Dikembangkan oleh <b>{nama}</b></span>'
        f'<span class="tengah">{status_data}{tanggal}</span>'
        f'<span class="kanan">{kanan}</span>'
        f'<span class="kaki-ket">{KETERANGAN_SITUS}</span>'
        '</div>'
    )


def kartu(label: str, nilai: str, ket: str = "", banding: str = "",
          arah: int = 0, andal: str = "", utama: bool = False,
          tafsir: str = "") -> str:
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
        rasa = " naik" if arah > 0 else " turun" if arah < 0 else ""
        ekor = (f'<div class="kpi-banding{rasa}">'
                f'<span class="kpi-arah">{tanda}</span>'
                f'{banding}</div>') + ekor
    tanda_andal = (f'<span class="kpi-andal" title="{andal}">!</span>'
                   if andal else "")
    n = len(str(nilai))
    kelas = ("kpi-nilai sangat-panjang" if n > 34
             else "kpi-nilai panjang" if n > 18 else "kpi-nilai")
    # Kalimat tafsir hanya pada kartu utama, dan letaknya sesudah keterangan
    # angkanya. Angka besar selalu diikuti pertanyaan yang sama, yaitu lalu
    # apa artinya, dan kartu yang berhenti pada angkanya membiarkan pembaca
    # menjawab sendiri.
    if tafsir:
        ekor += f'<div class="kpi-tafsir">{tafsir}</div>'
    return (f'<div class="kpi{" utama" if utama else ""}">'
            f'<div class="kpi-label">{label}{tanda_andal}</div>'
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


def alur(langkah: list[tuple]) -> str:
    """
    Infografik rangkaian langkah, menggantikan penjelasan urutan yang panjang.

    Tiap langkah berupa pasangan judul dan satu kalimat. Langkah yang
    mematikan perkara ditandai dengan menambahkan True pada unsur ketiga,
    dan ia digambar merah supaya pembaca menemukan titik gugurnya tanpa
    membaca satu kalimat pun.
    """
    potong = []
    for i, butir in enumerate(langkah, start=1):
        judul, isi = butir[0], butir[1]
        gugur = len(butir) > 2 and butir[2]
        potong.append(
            f'<div class="alur-langkah{" gugur" if gugur else ""}">'
            f'<div class="alur-nomor">{i}</div>'
            f'<div class="alur-judul">{judul}</div>'
            f'<div class="alur-isi">{isi}</div></div>')
    return '<div class="alur">' + "".join(potong) + "</div>"


def poin(butir: list[tuple], awas: bool = False) -> str:
    """
    Infografik butir bertanda, menggantikan alinea beruntun.

    Tiap butir berupa tanda pendek, judul, dan satu kalimat. Tandanya boleh
    berupa angka, lambang, atau kata sangat pendek.
    """
    kelas = "poin-kartu awas" if awas else "poin-kartu"
    potong = [
        f'<div class="{kelas}"><div class="poin-tanda">{t}</div>'
        f'<div class="poin-judul">{j}</div>'
        f'<div class="poin-isi">{i}</div></div>'
        for t, j, i in butir]
    return '<div class="poin">' + "".join(potong) + "</div>"


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


def jalur_hal(halaman: str) -> str:
    """Potongan alamat untuk sebuah halaman, tanpa awalan kunci tombol.

    Kunci tombol berawalan nav supaya tidak bentrok dengan kunci unsur lain,
    dan awalan itu tidak pantas ikut tercetak pada bilah alamat yang dibaca
    dan dikirimkan orang. Yang tampil cukup namanya sendiri.
    """
    return re.sub(r"[^a-z0-9]+", "-", str(halaman).lower()).strip("-")


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

# Kepala halaman berkas asli, yang ikut terangkut oleh mesin pembaca teks.
RE_KEPALA_HAL = re.compile(
    r"\s*[Hh]alaman\s+\d+\s+dari\s+\d+\s+halaman\s*\.?\s*")
# Sisa kepala halaman hanya dibuang bila memang berbunyi seperti kepala.
RE_MULA_KEPALA = re.compile(r"^(?:Putusan|PUTUSAN|Nomor|NOMOR|PUT)\b")
# Cadangan untuk penggalan yang hanya memuat satu sisipan, sehingga tidak ada
# pembanding untuk mengukur bagian yang berulang. Yang dibuang dibatasi pada
# rangkaian yang bentuknya sudah pasti kepala halaman.
RE_SISA_KEPALA = re.compile(
    r"^\s*Putusan\s+Nomor\s+\S+(?:\s+Tahun\s+\d{4})?\s*", re.IGNORECASE)
BATAS_KEPALA = 220


def _sama_di_depan(a: str, b: str) -> int:
    """Panjang awalan yang sama persis antara dua penggal teks."""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def buang_kepala_halaman(teks: str) -> str:
    """
    Membuang kepala halaman berkas asli yang menyusup ke tengah kalimat.

    Tiap halaman berkas putusan memuat baris berjalan seperti Halaman 9 dari
    89 halaman, diikuti nomor putusan dan nama pihak. Mesin pembaca teks
    membaca baris itu sebagai isi, sehingga ia terselip di antara kata pada
    setiap pergantian halaman. Akibatnya kalimat terpotong di tengah oleh
    keterangan yang bukan bagian dari putusan, dan pembaca menyangka naskahnya
    memang kacau. Pada contoh enam ratus naskah mutakhir, lima ratus enam
    puluh enam di antaranya tercemar begini.

    Bagian yang berubah ubah, yaitu nomor halamannya, dikenali dengan pola.
    Bagian yang tetap, yaitu nomor putusan dan nama pihak, tidak dapat dipola
    sebab nama pihak berbeda tiap perkara. Maka panjangnya tidak ditebak,
    melainkan diukur: tiap sisipan dibandingkan dengan sisipan lain pada
    naskah yang sama, lalu yang dibuang hanya sepanjang bagian yang benar
    benar berulang. Cara ini aman menurut bentuknya, sebab yang tidak berulang
    tidak akan pernah terhapus. Pembandingnya diambil yang paling cocok, bukan
    yang paling pendek, supaya satu halaman yang salah baca tidak menggagalkan
    pembersihan pada halaman lainnya.
    """
    isi = teks or ""
    tanda = list(RE_KEPALA_HAL.finditer(isi))
    if not tanda:
        return isi

    ekor = [isi[m.end():m.end() + BATAS_KEPALA] for m in tanda]
    potong = []
    for i, e in enumerate(ekor):
        # Padanan terbaik, bukan yang terpendek: salah baca pada satu halaman
        # tidak boleh memendekkan pembersihan halaman yang lain.
        sama = max((_sama_di_depan(e, lain)
                    for j, lain in enumerate(ekor) if j != i), default=0)
        cuil = e[:sama]
        if not RE_MULA_KEPALA.match(cuil.strip()):
            # Tanpa pembanding, panjang bagian yang berulang tidak terukur.
            # Yang dibuang lalu dibatasi pada bentuk yang sudah pasti, dan
            # nama pihak dibiarkan daripada menebak batasnya.
            m2 = RE_SISA_KEPALA.match(e)
            potong.append(m2.end() if m2 else 0)
            continue
        # Dirapikan ke batas kata supaya tidak memenggal kata berikutnya.
        # Batasnya sembarang aksara kosong, bukan spasi saja: nama pihak
        # kerap dipisahkan baris baru dari isi halaman, sehingga mencari
        # spasi terakhir justru mundur satu kata dan menyisakan penggalan
        # nama pihak di tengah kalimat.
        if sama < len(e) and not e[sama:sama + 1].isspace():
            sama -= len(re.search(r"\S*$", cuil).group(0))
        potong.append(max(0, sama))

    keluar, jangkar = [], 0
    for m, n in zip(tanda, potong):
        # Satu spasi disisipkan agar kalimat sebelum dan sesudah kepala
        # halaman tidak menyatu menjadi satu kata.
        keluar.append(isi[jangkar:m.start()])
        keluar.append(" ")
        jangkar = m.end() + n
    keluar.append(isi[jangkar:])
    return "".join(keluar)


def alinea_padat(teks: str) -> list[str]:
    """
    Memecah teks yang sudah kehilangan baris barunya menjadi alinea kembali.

    Bab anatomi disimpan sesudah seluruh baris barunya dirapatkan, sehingga
    ia sampai ke pembaca sebagai satu blok tanpa jeda sama sekali. Naskah
    hukum menandai pergantian pokok pikirannya dengan kata pembuka yang tetap,
    terutama kata bahwa, sehingga jeda alineanya dapat dipulihkan dari kata
    itu tanpa menebak nebak isinya. Penggal yang terlalu pendek dirapatkan
    kembali supaya tidak lahir alinea sepotong kata.
    """
    isi = " ".join((teks or "").split())
    if not isi:
        return []
    batas = [m.start() for m in re.finditer(
        r"(?<=[\s.;:])(?:bahwa|Bahwa|Menimbang|Mengingat|Memperhatikan|"
        r"Menurut|Pendapat|Demikian)\b", isi)]
    titik = [0] + [b for b in batas if b > 0] + [len(isi)]
    keluar: list[str] = []
    for a, b in zip(titik, titik[1:]):
        bagian = isi[a:b].strip()
        if not bagian:
            continue
        if keluar and len(bagian) < 90:
            keluar[-1] += " " + bagian
        else:
            keluar.append(bagian)
    return keluar


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
                           buang_kepala_halaman(teks).replace("\r", ""))
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
