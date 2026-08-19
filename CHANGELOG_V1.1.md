# Kasirqu V1.1

## Fokus: mesin transaksi yang lebih aman
- Metode pembayaran: Tunai, QRIS, Transfer, Debit/Kredit.
- Diskon transaksi nominal dan batas maksimum subtotal.
- Checkout memakai transaksi SQLite atomic; jika gagal, perubahan stok dibatalkan.
- Stok tidak boleh menjadi negatif dan divalidasi ulang saat checkout.
- Riwayat pergerakan stok untuk setiap penjualan.
- Menyimpan harga modal pada detail penjualan untuk perhitungan laba historis.
- Dashboard menampilkan laba kotor hari ini.
- Laporan CSV menambahkan laba kotor.
- Migrasi database otomatis menambahkan kolom/tabel baru tanpa menghapus data lama.

## Yang sengaja tidak diubah
- Workflow GitHub Actions.
- Dependency Kivy/build environment.
- Struktur utama aplikasi dan database lama.
- Printer Bluetooth yang sudah ada.
