# Dashboard Analitik Sengketa Pajak

Purwarupa analitik risalah putusan Pengadilan Pajak untuk UAT. Sumber data: https://setpp.kemenkeu.go.id/risalah, serta daftar resmi putusan 2021 sampai 2025 dari Sekretariat Pengadilan Pajak, Kementerian Keuangan.

Aplikasi Streamlit. Basis datanya tidak disimpan di repo, melainkan diunduh otomatis dari aset Release saat aplikasi dinyalakan, dan diunduh ulang sendiri ketika asetnya berganti. Alamatnya diatur melalui secrets `SETPP_DATA_URL`.

## Isi data

Cuplikan per 8 Agustus 2026:

| Lapis | Jumlah |
| --- | ---: |
| Berkas arsip terkumpul | 20.918 |
| Putusan terurai ke dataset | 14.001 |
| Rujukan dasar hukum | 513.307 |
| Daftar resmi putusan 2021 sampai 2025 | 77.041 |

Amar hasil penguraian cocok 88,2 persen dan tanggal ucap 96,3 persen terhadap daftar resmi, dihitung dari putusan yang terhubung ke daftar tersebut.

## Modul pengguna

Tiga belas halaman, dikelompokkan ke dalam modul Pimpinan, Fiskus, dan Wajib pajak, yang dipilih melalui bilah samping. Empat dimensi analitik: deskriptif, diagnostik, prediktif, dan preskriptif.

## Menjalankan lokal

```
pip install -r requirements.txt
set SETPP_DATA_URL=<alamat aset setpp_uat.db.gz>
streamlit run streamlit_app.py
```

Status data: purwarupa, cakupan arsip sebagian, angka bersifat taksiran kecuali dinyatakan bersumber daftar resmi. Rincian pada halaman Metodologi di dalam aplikasi.

(c) 2026 Donny Maha Putra
