# Tax Dispute Analytic Dashboard

Purwarupa analitik risalah putusan Pengadilan Pajak untuk UAT. Sumber data: laman publik Sekretariat Pengadilan Pajak, Kementerian Keuangan, serta daftar resmi putusan 2021 sampai 2025.

Aplikasi Streamlit. Basis datanya tidak disimpan di repo, melainkan diunduh otomatis dari aset Release saat aplikasi pertama dinyalakan; alamatnya diatur lewat secrets `SETPP_DATA_URL`.

## Isi data

Cuplikan per 7 Agustus 2026:

| Lapis | Jumlah |
| --- | ---: |
| Berkas arsip terkumpul | 12.920 |
| Putusan terurai ke dataset | 8.685 |
| Rujukan dasar hukum | 310.950 |
| Daftar resmi putusan 2021 sampai 2025 | 77.041 |

Amar hasil penguraian cocok 88,2 persen dan tanggal ucap 96,3 persen terhadap daftar resmi, dihitung dari putusan yang terhubung ke daftar itu.

## Modul pengguna

Tiga belas halaman, dikelompokkan ke dalam modul Pimpinan, Fiskus, dan Wajib pajak, dipilih lewat bilah samping. Empat dimensi analitik: deskriptif, diagnostik, prediktif, dan preskriptif.

## Menjalankan lokal

```
pip install -r requirements.txt
set SETPP_DATA_URL=<alamat aset setpp_uat.db.gz>
streamlit run streamlit_app.py
```

Status data: purwarupa, cakupan arsip sebagian, angka taksiran kecuali dinyatakan bersumber daftar resmi. Rincian pada halaman Catatan metode di dalam aplikasi.

(c) 2026 Donny Maha Putra
