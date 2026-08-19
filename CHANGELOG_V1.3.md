# Kasir Kita V1.3

## Smart Horizontal Navigation

- Navigasi toolbar sekarang menggunakan transisi horizontal terarah.
- Menekan menu yang berada di sebelah kanan halaman aktif menggeser halaman ke kiri.
- Menekan menu yang berada di sebelah kiri halaman aktif menggeser halaman ke kanan.
- Urutan navigasi: Dashboard → Kasir → Produk → Riwayat → Laporan → Pengaturan.
- Durasi transisi dibuat singkat (0,20 detik) agar terasa responsif di Android.
- ScrollView vertikal pada isi setiap halaman tidak diubah, sehingga daftar produk/riwayat/laporan tetap dapat digulir normal.
- Mesin transaksi, database, stok, printer, laporan, dan fitur V1.2 lainnya tidak diubah.

## Technical

- Menggunakan Kivy `SlideTransition`; tidak menambah dependency eksternal.
- Versi aplikasi: 1.3.0
