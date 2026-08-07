# Tax Dispute Analytic Dashboard

Purwarupa analitik risalah putusan Pengadilan Pajak untuk UAT. Sumber data: laman publik Sekretariat Pengadilan Pajak, Kementerian Keuangan, serta daftar resmi putusan 2021 sampai 2025.

Aplikasi Streamlit. Basis datanya tidak disimpan di repo, melainkan diunduh otomatis dari aset Release saat aplikasi pertama dinyalakan; alamatnya diatur lewat secrets `SETPP_DATA_URL`.

Menjalankan lokal:

```
pip install -r requirements.txt
set SETPP_DATA_URL=<alamat aset setpp_uat.db.gz>
streamlit run streamlit_app.py
```

Status data: purwarupa, cakupan arsip sebagian, angka taksiran kecuali dinyatakan bersumber daftar resmi. Rincian pada halaman Catatan metode di dalam aplikasi.

(c) 2026 Donny Maha Putra
