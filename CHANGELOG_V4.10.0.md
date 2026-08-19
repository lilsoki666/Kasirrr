# V4.10.0 — Professional POS UI

Fokus versi ini adalah peningkatan UI halaman Kasir tanpa mengubah mesin transaksi, database, stok, gallery/foto produk, printer, kategori, laporan, riwayat, atau navigasi yang sudah berjalan.

## Perubahan
- Kartu produk Kasir dibuat lebih jelas dan touch-friendly.
- Area foto produk dibuat konsisten untuk produk dengan foto maupun tanpa foto.
- Ditambahkan indikator aksi `+` pada sisi kanan kartu; seluruh kartu tetap dapat diketuk untuk menambahkan produk ke keranjang.
- Tampilan nama, harga, dan stok dibuat lebih mudah dibaca.
- Daftar produk Kasir menjadi responsif: 1 kolom pada portrait dan 2 kolom pada landscape pada lebar yang memadai.
- Kategori tetap menggunakan horizontal scroll agar tidak memotong kategori.
- Ringkasan keranjang dibuat sedikit lebih tinggi dan tetap berada di bawah daftar produk.
- Tidak mengubah alur pemilihan foto/gallery yang sudah berhasil pada V4.9.8/V4.9.9.

## Kompatibilitas
- Database dan struktur data lama dipertahankan.
- Buildozer workflow tidak diubah.
- Tidak menambahkan dependency Python baru.
