# POS Kasir Android v1.0

Stack: Python + Kivy + SQLite + Buildozer.

Fitur:
- Dashboard penjualan harian
- Kasir/POS dan keranjang
- Diskon transaksi
- Pajak
- Tunai, QRIS, Transfer, Debit/Kredit
- Kembalian
- Produk, barcode, kategori
- Harga beli/jual
- Stok dan batas stok minimum
- Riwayat dan detail transaksi
- Laporan 30 hari
- Export CSV
- Pengaturan toko/kasir/pajak
- Backup SQLite
- Offline/local database

Build hanya dari HP:
1. Buat repository GitHub.
2. Upload seluruh isi folder ini.
3. Pastikan `.github/workflows/build-apk.yml` ikut ter-upload.
4. Buka Actions.
5. Pilih `Build POS Android APK`.
6. Tekan `Run workflow`.
7. Setelah selesai, buka Artifacts -> `POS-Kasir-APK`.
8. Download ZIP, ekstrak, lalu instal APK.

Build pertama dapat cukup lama karena toolchain Android perlu disiapkan.


## Perbaikan startup Android
Versi ini memperbaiki import Kivy yang hilang dan memindahkan refresh data dari `build()` ke `on_start()`. Kivy baru menetapkan `App.root` setelah `build()` selesai, sehingga refresh UI di dalam `build()` dapat menyebabkan crash saat startup. Jika startup tetap gagal, aplikasi mencatat traceback ke `startup_error.log` di folder data aplikasi.
