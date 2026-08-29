---
title: Dashboard Analitik Sengketa Pajak
emoji: ⚖️
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: 1.58.0
app_file: streamlit_app.py
pinned: false
license: other
short_description: Analitik risalah putusan Pengadilan Pajak, 25 ribu putusan
---

# Dashboard Analitik Sengketa Pajak

Analitik risalah putusan Pengadilan Pajak. Sumber data laman publik
Sekretariat Pengadilan Pajak, Kementerian Keuangan, beserta daftar resmi
putusan 2021 sampai 2025.

Basis datanya tidak disimpan di dalam repositori ini, melainkan diunduh
otomatis dari aset GitHub Release saat aplikasi dinyalakan, dan diunduh ulang
sendiri ketika asetnya berganti. Cakram Spaces yang terhapus tiap kali wadah
dibangun ulang justru cocok dengan cara kerja itu.

Alamat asetnya dapat diatur lewat rahasia `SETPP_DATA_URL` bila kelak
berpindah, dan bila tidak diatur akan memakai alamat bawaan di dalam kode.

Status: purwarupa. Cakupan arsip masih sebagian, dan angkanya taksiran
kecuali dinyatakan bersumber daftar resmi. Rinciannya ada pada halaman
Metodologi di dalam aplikasi.

(c) 2026 Donny Maha Putra
