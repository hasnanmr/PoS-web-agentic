# User Stories — SME Business Automation Platform

Dokumen ini menerjemahkan `PRD-SME-Automation-Platform.md` menjadi backlog user story (baseline PRD v0.21: kanal pelanggan MVP adalah web chat; WhatsApp pindah ke Phase 3; agent Phase 2 di web chat terdiri dari supervisor agent dan worker agent, PRD §5.13). Acceptance criteria merujuk ke ID AC pada PRD; seluruh AC yang dirujuk wajib lulus sebelum story dianggap selesai.

## Konvensi

- **MVP** = Phase 0–1
- **P2** = Phase 2, agent layer
- **P3** = Phase 3, scale & expansion
- **Prioritas**: P0 wajib untuk rilis fase tersebut, P1 penting setelah alur utama stabil, P2 perluasan

## Epic A — Tenant, outlet, dan akses pengguna

### US-001 — Membuat bisnis

**Sebagai** pemilik UMKM, **saya ingin** membuat profil bisnis restoran atau cafe, **sehingga** saya dapat mengelola operasional bisnis dalam satu tenant.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Pemilik dapat memasukkan nama dan tipe bisnis `restaurant` atau `cafe`.
  - Sistem membuat tenant dan menetapkan pembuat sebagai owner.
  - Tipe `dropshipper` belum tersedia pada MVP.
- **Traceability:** FR1.1, AC1.1

### US-002 — Mengelola banyak outlet

**Sebagai** pemilik bisnis, **saya ingin** menambahkan dan mengonfigurasi beberapa outlet, **sehingga** setiap cabang dapat beroperasi dengan pengaturan lokalnya sendiri.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Setiap outlet memiliki alamat, jam buka, zona waktu, link outlet publik (`/o/<slug>`), meja, cash drawer, QRIS, pengaturan reservasi, PB1, mode pembayaran dine-in, dan biaya delivery flat sendiri.
  - Item menu, add-on, resep, dan owner's picks digunakan bersama oleh seluruh outlet; harga item dan opsi add-on diatur per outlet.
  - Perubahan pengaturan outlet A tidak memengaruhi outlet B.
- **Traceability:** FR1.2, FR2.10, AC1.2, AC2.11

### US-003 — Mengelola akun staf dan hak akses

**Sebagai** owner, **saya ingin** membuat, menugaskan, dan menonaktifkan akun staf, **sehingga** akses operasional dapat dikendalikan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Hanya owner yang dapat membuat akun staf melalui email yang ditentukan owner.
  - Owner dapat menugaskan staf ke satu atau beberapa outlet dan menonaktifkannya.
  - Staf hanya melihat data outlet yang ditugaskan.
  - Owner-only actions ditolak untuk staf dan tidak mengubah data.
  - Sesi aktif staf yang dinonaktifkan segera ditolak.
  - Akun staf dibuat melalui undangan email Supabase Auth; penonaktifan memblokir login baru dan mencabut sesi aktif.
  - Pendaftaran publik dinonaktifkan; email yang tidak diundang owner tidak dapat membuat akun.
- **Traceability:** FR1.3–FR1.5, FR7.1–FR7.2, AC1.3–AC1.6, AC7.1

### US-004 — Audit reversal dan perubahan penting

**Sebagai** owner, **saya ingin** melihat siapa, kapan, dan mengapa suatu order dibalik atau statusnya diubah, **sehingga** operasional dapat diaudit.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Reversal tanpa alasan wajib ditolak.
  - Reversal menyimpan order, aktor, waktu, dan alasan.
  - Perubahan status order juga menyimpan status lama, status baru, aktor, dan waktu.
- **Traceability:** FR1.6, FR10.2, AC1.7, AC10.3

## Epic B — Menu, add-on, resep, dan stok

### US-005 — Mengelola menu dan harga per outlet

**Sebagai** owner, **saya ingin** mengelola menu, foto, deskripsi, add-on, dan harga per outlet, **sehingga** pelanggan melihat penawaran yang benar di setiap cabang.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Owner dapat menambah, mengubah, dan menghapus item menu, grup add-on, opsi add-on, dan harga outlet.
  - Foto dianjurkan tetapi opsional; item tanpa foto memakai placeholder.
  - Setiap grup add-on memiliki maksimal 10 opsi.
  - Grup dapat bersifat required/optional dan memilih satu atau beberapa opsi.
  - Harga dan ketersediaan mengikuti outlet tempat order dibuat.
- **Traceability:** FR2.11, FR4.1, FR4.8, FR4.9, AC4.5, AC4.6, AC4.8

### US-006 — Mengelola resep dan pergerakan stok

**Sebagai** owner atau staf, **saya ingin** mencatat resep dan pergerakan stok, **sehingga** pemakaian bahan dapat dihitung secara akurat.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Setiap menu memiliki resep berupa bahan, jumlah, dan satuan; produk as-is tetap memiliki minimal satu bahan.
  - Restock, waste, adjustment, penjualan, dan pembatalan dicatat sebagai stock movement.
  - Stok tidak dapat diedit langsung.
  - Movement tidak dapat diubah atau dihapus dan menyimpan tipe, jumlah, outlet, aktor, dan waktu.
- **Traceability:** FR4.1, FR4.2, FR4.5, AC4.1, AC4.2, AC4.4

### US-007 — Menangani stok rendah dan sold out

**Sebagai** owner atau staf, **saya ingin** melihat stok dan peringatan stok rendah, **sehingga** saya dapat mengambil tindakan sebelum bahan habis.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Sistem menampilkan stok bahan per outlet dan threshold yang dapat dikonfigurasi.
  - Item menu menjadi sold out jika salah satu bahan tidak cukup untuk satu porsi.
  - Add-on yang bahan-bahannya tidak cukup menjadi unavailable.
  - Status sold out hanya berlaku pada outlet terkait dan kembali tersedia setelah restock.
- **Traceability:** FR4.3, FR4.7, AC4.3, AC4.7

### US-008 — Memulai tenant dengan sample menu

**Sebagai** owner baru, **saya ingin** langsung mendapat sample menu yang tampil di web chat, **sehingga** saya dapat mencoba alur produk sebelum memasukkan menu asli.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Tenant baru mendapat item, foto, harga outlet, dan add-on sample di sistem kita.
  - Sample menu langsung tampil saat link outlet dibuka; tidak ada katalog eksternal yang perlu disinkronkan.
  - Owner dapat mengedit atau menghapus semua sample item.
  - Perubahan harga atau ketersediaan langsung terlihat saat menu ditampilkan berikutnya, dan hanya di outlet terkait.
- **Traceability:** FR2.11, FR2.12, AC2.12, AC2.13

## Epic C — Pemesanan melalui web chat

### US-009 — Menampilkan menu utama web chat

**Sebagai** pelanggan, **saya ingin** membuka chat outlet dari browser HP tanpa install aplikasi dan tanpa login, lalu melihat semua pilihan layanan sebagai tombol, **sehingga** saya dapat memilih kebutuhan saya dengan cepat.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Web chat terbuka dari link outlet (`/o/<slug>`) atau QR meja (`/t/<token>`), berbahasa Indonesia, nyaman di layar 360 px tanpa scroll horizontal, dan berbentuk percakapan: pesan outlet, pilihan pelanggan sebagai balasan, tombol, kartu menu, dan kotak teks.
  - Dari link outlet dengan reservasi aktif, menu utama menampilkan tepat: `Pesan`, `Rekomendasi`, `Reservasi`, `Reservasi Saya`; tanpa reservasi hanya `Pesan` dan `Rekomendasi`.
  - Dari QR meja, chat menampilkan outlet dan nomor meja dengan `Pesan` dan `Rekomendasi` saja.
  - Tombol `Pesanan Saya` muncul selama HP ini punya order yang masih aktif.
  - Tombol `Menu utama` selalu terlihat; tombol itu atau mengetik "menu" kembali ke menu utama tanpa membuat apa pun dari alur yang belum selesai, dan keranjang tetap.
- **Traceability:** FR2.0, FR6.1, AC2.1, AC2.14, AC6.1

### US-010 — Menjelajah menu dan membuat keranjang

**Sebagai** pelanggan, **saya ingin** melihat menu outlet di chat dan menambahkan produk ke keranjang, **sehingga** saya dapat membuat pesanan tanpa login ke aplikasi lain.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - `Pesan` menampilkan kartu menu per kategori dengan foto (atau placeholder), deskripsi, dan harga outlet terkait.
  - Item sold out ditandai tidak tersedia dan tidak dapat ditambahkan.
  - Keranjang dapat dibuka, diubah, atau dikosongkan kapan saja.
- **Traceability:** FR2.1, FR2.2, AC2.2

### US-011 — Memilih add-on dan mengonfirmasi pesanan

**Sebagai** pelanggan, **saya ingin** memilih add-on saat menambah item, memberi catatan dapur, dan memeriksa ringkasan, **sehingga** total pesanan saya jelas sebelum dibuat.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Saat item dengan grup add-on ditambahkan, chat menanyakan tiap grup dengan tombol; grup required harus dipilih sebelum item masuk keranjang, grup optional dapat dilewati.
  - Pelanggan dapat menambahkan catatan dapur per item.
  - Ringkasan menampilkan item, kuantitas, add-on, catatan, subtotal, PB1, biaya delivery jika ada, dan total.
  - Order belum dibuat sebelum pelanggan menekan `Pesan & bayar`; harga, PB1, dan biaya delivery dihitung ulang di server.
- **Traceability:** FR2.2, FR2.3, AC2.3–AC2.5

### US-012 — Memilih pickup atau delivery

**Sebagai** pelanggan online, **saya ingin** memilih pickup atau delivery dan mengisi nama serta no HP, **sehingga** pesanan saya diproses sesuai cara pengambilan yang saya inginkan dan staf bisa menghubungi saya.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Order dari link outlet meminta nama dan no HP (tanpa verifikasi/OTP).
  - Delivery juga mewajibkan alamat dan menambahkan biaya flat outlet sebagai baris terpisah.
  - Biaya delivery tidak masuk dasar perhitungan PB1 dan dicatat terpisah di ledger.
  - Pickup tidak meminta alamat dan tidak menambahkan biaya delivery.
- **Traceability:** FR2.6, AC2.7

### US-013 — Memesan dari QR meja

**Sebagai** pelanggan dine-in, **saya ingin** memesan dengan memindai QR di meja, **sehingga** order otomatis terhubung ke outlet dan meja saya tanpa menunggu pelayan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - QR membuka web chat untuk meja itu (`/t/<token>`); token acak dan unik per meja, bukan nomor meja.
  - Pelanggan mengisi nama untuk dipanggil staf; no HP tidak diminta.
  - Order diberi channel `web_table`, tipe dine-in, meja yang benar, dan selalu bayar dulu (US-062), juga di outlet open bill; order web tidak pernah masuk open bill meja.
  - Mengirim keranjang yang sama dua kali (double tap, retry) hanya membuat satu order.
  - Outlet tanpa QRIS statis menampilkan menu tanpa tombol tambah dengan catatan "Pesan di kasir" (dari QR meja maupun link outlet); reservasi tetap bisa.
- **Traceability:** FR2.7, FR2.13, AC2.8, AC2.15–AC2.17 · wireframe Q1–Q5 (perlu digambar ulang sebagai web chat) · issue #44

### US-062 — Membayar pesanan web chat dengan QRIS statis

**Sebagai** pelanggan, **saya ingin** langsung membayar pesanan di chat dengan QRIS outlet, **sehingga** pesanan saya segera diproses.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Berlaku untuk kedua kanal web (`web_online`, `web_table`): setelah order dibuat, chat menampilkan nomor order, item, total, QRIS statis outlet, dan batas waktu bayar.
  - "Saya sudah bayar" mengubah payment status menjadi `proof_submitted` tanpa upload bukti dan menghentikan batas waktu; tanpa itu, order batal otomatis di batas waktu.
  - Pelanggan dapat membatalkan order sampai menekan "Saya sudah bayar".
  - Staf mengonfirmasi lunas setelah menemukan transaksi di akun merchant, atau menolak dengan alasan (order batal, stok kembali, alasan tampil di chat).
  - Order dari web tampil di Order Board dengan label kanal, meja atau tipe pickup/delivery, nama pemesan, dan tanda "Pelanggan bilang sudah bayar".
- **Traceability:** FR2.5, FR2.14, FR11.2, FR11.3, FR11.10, AC2.6, AC2.18, AC11.1–AC11.3, AC11.9 · wireframe S2 kartu web

### US-063 — Mengatur link outlet dan QR

**Sebagai** owner, **saya ingin** mengatur link outlet, mengunduh QR outlet dan QR meja, dan mengganti QR yang bocor, **sehingga** pelanggan bisa membuka chat outlet dari poster, kasir, Instagram, Google Maps, atau meja.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Owner menentukan slug link outlet (`/o/<slug>`), unik di seluruh platform; setelah slug diganti, link lama menampilkan bahwa halaman tidak ada dan link baru langsung berlaku.
  - Owner dapat mengunduh QR outlet, QR per meja, dan semua QR meja outlet dalam satu PDF.
  - "Ganti" membuat token baru untuk meja itu; QR lama langsung tidak berlaku dan menampilkan pesan bahwa QR tidak berlaku.
  - Link atau token menentukan outlet dan tenant chat; order dan booking dari link outlet B milik outlet B.
  - Staf tidak dapat mengubah pengaturan ini, termasuk lewat API langsung.
- **Traceability:** FR2.10, FR2.16, AC2.11, AC2.21 · wireframe O8 (perlu diperbarui: pilihan tujuan QR WhatsApp dihapus, slug link outlet ditambah) · issue #44

### US-014 — Membuat order secara konsisten dan aman terhadap stok

**Sebagai** owner, **saya ingin** seluruh kanal memakai fungsi pembuatan order yang sama, **sehingga** stok dan status order konsisten.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Channel yang disimpan adalah `web_online`, `web_table`, atau `counter`; `whatsapp_online` dan `whatsapp_table` dicadangkan untuk Phase 3 dan tidak dibuat oleh alur MVP.
  - Pembuatan order memeriksa dan mengurangi seluruh bahan item dan add-on dalam satu transaksi database.
  - Jika stok tidak cukup saat `Pesan & bayar`, order tidak dibuat dan chat menyebut item yang habis dengan pilihan menghapus atau mengganti.
  - Dua konfirmasi bersamaan untuk porsi terakhir hanya menghasilkan satu order; stok tidak pernah negatif.
  - Sale belum masuk ledger sebelum pembayaran dikonfirmasi.
- **Traceability:** FR2.3, FR2.8, FR2.9, FR4.6, AC2.5, AC2.9, AC2.10

### US-015 — Melihat status pesanan di chat

**Sebagai** pelanggan, **saya ingin** melihat status pesanan saya di chat yang sama, **sehingga** saya mengetahui progres pesanan tanpa menerima pesan di aplikasi lain.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Selama chat terbuka, status (menunggu konfirmasi bayar, disiapkan, siap, dalam pengantaran, ditolak/batal dengan alasan) ter-update sendiri paling lambat 10 detik setelah berubah, tanpa reload.
  - Sistem tidak mengirim pesan apa pun di luar chat (tidak ada WhatsApp, SMS, email, atau push notification).
  - HP yang memesan dapat membuka ulang pesanannya dari `Pesanan Saya` (link outlet atau QR meja yang sama) sampai satu jam setelah order selesai atau batal; chat juga menawarkan link pesanan yang bisa disimpan.
  - Order hanya bisa dibaca dengan access key milik HP pemesan; HP lain yang memindai QR meja yang sama tidak melihat pesanan itu, dan tidak ada bill meja di chat.
  - Pesanan yang sudah dibayar tidak bisa diubah pelanggan; perubahan lewat staf (reversal).
- **Traceability:** FR2.15, FR6.5, FR10.3, AC2.19, AC2.20, AC6.7, AC10.4

## Epic D — Siklus order, pembayaran, dan kasir

### US-016 — Mengelola lifecycle order

**Sebagai** staf, **saya ingin** memindahkan order melalui status yang valid, **sehingga** dapur, bar, pelanggan, dan pembayaran memiliki progres yang selaras.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Order status dan payment status disimpan terpisah.
  - Transisi mengikuti alur sesuai channel dan mode pembayaran outlet.
  - Order unpaid tidak dapat diprepare atau diselesaikan.
  - Setiap transisi tercatat dengan aktor dan waktu.
- **Traceability:** FR10.1, FR10.2, AC10.1–AC10.3

### US-017 — Mengonfirmasi pembayaran QRIS

**Sebagai** staf, **saya ingin** mengecek pembayaran QRIS di akun merchant sebelum menandai lunas, **sehingga** hanya pesanan yang benar-benar dibayar yang diproses dan masuk ledger.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Order web chat yang pelanggannya menekan "Saya sudah bayar" berstatus `proof_submitted` dan tampil dengan tanda "Pelanggan bilang sudah bayar"; tidak ada screenshot.
  - Staf hanya dapat menandai paid setelah mengecek transaksi di akun merchant QRIS.
  - Ledger dibuat saat payment ditandai paid dan menyimpan aktor serta waktu.
  - Jika dana tidak ditemukan, staf menolak dengan alasan wajib; order langsung dibatalkan, bahan dikembalikan dengan reversal movement, tidak ada ledger entry, dan chat pelanggan menampilkan alasan serta ajakan menghubungi outlet.
- **Traceability:** FR10.1, FR11.1–FR11.3, FR11.10, AC11.1–AC11.3, AC11.9

### US-018 — Menerima pembayaran cash dan mengelola shift kasir

**Sebagai** staf kasir, **saya ingin** menerima pembayaran cash dan membuka/menutup shift, **sehingga** kas outlet dapat direkonsiliasi.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Order counter (dine-in dan takeaway) dapat memilih cash atau QRIS; order web chat tidak menawarkan cash.
  - Pembayaran cash meminta nominal diterima dan menampilkan kembalian.
  - Owner mengatur cash drawer per outlet; outlet baru otomatis memiliki satu drawer.
  - Cash hanya dapat diterima jika shift kasir terbuka; satu drawer hanya memiliki satu shift aktif, dan setiap drawer dihitung terpisah di akhir shift.
  - End-of-shift menggunakan blind count, membandingkan cash aktual dengan ekspektasi, mencatat selisih dan penghitung, lalu mem-post shortage/surplus ke ledger.
  - Owner dapat melihat laporan cash count setiap shift beserta selisihnya.
- **Traceability:** FR11.4, FR11.6–FR11.8, AC11.4, AC11.6–AC11.8, AC11.10

### US-019 — Menghitung PB1 dengan benar

**Sebagai** owner, **saya ingin** mengatur PB1 per outlet, **sehingga** pajak dihitung dan dilaporkan terpisah dari pendapatan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - PB1 dapat diaktifkan dengan rate tertentu atau dimatikan per outlet.
  - PB1 dihitung dari subtotal termasuk add-on, tidak termasuk delivery fee, dan dibulatkan ke rupiah terdekat.
  - Ringkasan/bill menampilkan PB1 sebagai baris tersendiri.
  - Ledger memisahkan PB1 dari revenue.
- **Traceability:** FR11.5, AC11.5

### US-020 — Mengelola open bill dine-in

**Sebagai** staf, **saya ingin** menggabungkan beberapa order dalam satu open bill dan menutupnya saat tamu membayar, **sehingga** layanan dine-in dapat berjalan tanpa pembayaran di awal.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Outlet dapat diatur ke mode `pay first` atau `open bill`; mode ini hanya berlaku untuk order dari counter, karena order web chat selalu bayar dulu.
  - Meja/guest hanya boleh memiliki satu open bill.
  - Order counter berikutnya untuk meja atau tamu yang sama bergabung ke bill yang sama; order web chat dari QR meja tidak pernah masuk bill.
  - Bill menampilkan item, total berjalan, dan durasi terbuka.
  - Bill ditutup dengan satu pembayaran penuh, atau di-split per item (US-064); saat lunas semua order menjadi completed dan sale masuk ledger. PB1 dihitung sekali dari subtotal bill.
  - Jika mode outlet berubah, order baru mengikuti mode baru, sedangkan order yang sudah dibuat mempertahankan flow asalnya.
- **Traceability:** FR10.6–FR10.8, AC10.7–AC10.10

### US-064 — Split bill per item

**Sebagai** staf, **saya ingin** membagi open bill per item sehingga tiap tamu membayar item yang dia pesan, **sehingga** meja dengan banyak tamu tidak perlu menghitung patungan di luar sistem.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Dari open bill (S5, M3) staf memilih "Split per item", lalu memilih item yang belum lunas atau sebagian porsi dari item dengan jumlah lebih dari satu; add-on ikut porsinya.
  - Tiap bagian dibayar cash atau QRIS lewat popup pembayaran yang sama dengan tutup bill; bagian tercatat lunas hanya saat "Pembayaran selesai". Metode boleh berbeda per bagian.
  - QRIS statis: popup menampilkan QRIS outlet dengan item, PB1, dan total bagian itu saja; tamu mengetik nominal bagiannya; staf mengecek mutasi merchant (nominal persis, masuk setelah popup dibuka, belum dipakai bagian lain) sebelum konfirmasi; satu bagian dalam satu waktu. Bagian QRIS tidak menambah uang tunai di shift kasir.
  - Cash: uang diterima dan kembalian dihitung dari total bagian, dan uangnya masuk ke shift kasir yang terbuka.
  - PB1 bagian = PB1 dari semua item yang sudah lunas termasuk bagian ini dikurangi PB1 yang sudah dibayar; tidak pernah negatif dan jumlah semua bagian sama persis dengan total bill.
  - Tiap bagian adalah satu pembayaran dengan entri ledger sendiri (revenue dan PB1, metode bayar, shift kasir untuk cash).
  - Item yang sudah lunas tidak bisa dipilih lagi atau dipindah; dua kasir membayar porsi yang sama bersamaan → hanya satu yang berhasil.
  - Selama bill terbuka, bagian lunas bisa dibatalkan dengan alasan wajib: entri refund, audit log, item kembali belum lunas. Order yang punya item lunas tidak bisa dibatalkan sebelum bagiannya dibatalkan.
  - Order baru tetap bisa masuk bill dan menambah sisa; daftar open bill menampilkan total dan sisa. "Tutup bill & bayar" setelah ada bagian lunas menagih tepat sisanya.
  - Saat item terakhir lunas, semua order completed dan bill tertutup. Tombol mengikuti `allowed_actions` dari server.
  - Web chat pelanggan tidak punya split (tidak menampilkan bill).
- **Traceability:** FR10.6, FR10.9, FR11.4–FR11.6, AC10.8, AC10.11–AC10.15 · wireframe S5, S5a, S5b, S5c, M3, M3a, M3b · issue #42

### US-021 — Membatalkan dan membalik order

**Sebagai** owner atau staf berwenang, **saya ingin** membatalkan atau membalik order sesuai statusnya, **sehingga** stok dan keuangan tetap dapat ditelusuri.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Unpaid pay-first order (web chat, dan counter dine-in di outlet pay-first) dibatalkan otomatis setelah batas waktu outlet jika pelanggan belum menekan "Saya sudah bayar"; timer berhenti setelah itu.
  - Pembatalan unpaid mengembalikan bahan dengan reversal movement.
  - Reversal paid order wajib memiliki alasan, membuat refund ledger entry, dan mengembalikan bahan jika belum diprepare.
  - Order yang sudah diprepare mencatat bahan sebagai waste; uang dikembalikan manual di luar sistem.
- **Traceability:** FR10.4–FR10.5, AC10.5–AC10.6

## Epic E — Reservasi dan meja

### US-022 — Mengonfigurasi meja dan aturan reservasi

**Sebagai** owner, **saya ingin** mengatur meja dan aturan reservasi per outlet, **sehingga** ketersediaan meja sesuai kapasitas dan jam operasional.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Owner dapat mengatur nomor/nama meja, kapasitas, area, jam booking, durasi default, booking window, maksimum party size, waktu reminder, dan cancellation cutoff.
  - Semua waktu disimpan dan ditampilkan dalam zona waktu outlet: WIB, WITA, atau WIT.
- **Traceability:** FR9.1, FR9.8, AC9.1, AC9.3, AC9.9

### US-023 — Memesan meja melalui web chat

**Sebagai** pelanggan, **saya ingin** memesan meja dengan memilih jumlah orang, tanggal, dan waktu di web chat outlet, **sehingga** saya tidak perlu menelepon outlet.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - `Reservasi` dari link outlet meminta party size → tanggal → waktu tersedia → nama dan no HP (tanpa verifikasi) → konfirmasi.
  - Sistem hanya menawarkan waktu yang sesuai aturan outlet dan meja yang tersedia.
  - Sistem menetapkan meja terkecil yang cukup untuk party.
  - Party di atas batas maksimum ditolak dengan informasi batas tersebut.
  - Satu no HP maksimal punya 2 booking mendatang per outlet; booking ketiga ditolak dengan ajakan menghubungi outlet dan tidak menahan meja.
  - Konfirmasi booking dua kali (double tap, retry) hanya membuat satu booking.
- **Traceability:** FR9.2, FR6.4, AC9.1–AC9.3, AC9.11, AC6.6

### US-024 — Mencegah double booking

**Sebagai** owner, **saya ingin** sistem mencegah dua reservasi yang waktunya tumpang tindih, **sehingga** pelanggan tidak mendapat meja yang sama.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Pencegahan diterapkan di level database.
  - Request bersamaan atau write yang melewati validasi aplikasi tetap menolak reservasi kedua.
- **Traceability:** FR9.3, AC9.4

### US-025 — Menerima konfirmasi booking dan mengelola reservasi

**Sebagai** pelanggan, **saya ingin** mendapat kode booking dan pengingat di kalender HP, lalu bisa membatalkan atau menjadwal ulang dari chat, **sehingga** saya dapat mengatur rencana kunjungan tanpa menelepon.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Setelah konfirmasi, chat menampilkan outlet, tanggal, waktu, party size, dan **kode booking**, serta link booking yang bisa disimpan.
  - `Tambah ke kalender` mengunduh file kalender berisi booking dengan alert sesuai waktu reminder outlet, dalam zona waktu outlet; sistem tidak mengirim reminder sendiri.
  - Pembatalan/reschedule dilakukan dari `Reservasi Saya` dan diizinkan sampai cancellation cutoff; setelah cutoff, chat menolak dan mengarahkan pelanggan menghubungi outlet.
  - `Reservasi Saya` menampilkan booking mendatang yang dibuat dari HP ini; di HP lain, booking ditemukan dengan kode booking dan no HP yang dipakai saat booking.
  - Kode atau no HP yang salah tidak menampilkan apa pun, dan percobaan salah berulang dibatasi (rate limit).
- **Traceability:** FR9.4–FR9.5, FR6.5, AC9.5, AC9.6, AC9.12

### US-026 — Mengelola reservasi oleh staf

**Sebagai** staf, **saya ingin** melihat dan mengubah reservasi hari ini, **sehingga** saya dapat mengatur meja selama operasional.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Staf dapat melihat reservasi per meja, menambah booking dari telepon/in-person, dan memindahkan meja.
  - Staf dapat menandai seated, completed, cancelled, atau no-show.
  - Setiap perubahan menyimpan aktor dan waktu.
- **Traceability:** FR9.6, AC9.7

### US-027 — Mengelola walk-in dan hold no-show

**Sebagai** staf, **saya ingin** menandai meja walk-in dan membebaskan meja yang no-show setelah 15 menit, **sehingga** inventaris meja selalu mencerminkan kondisi nyata.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Meja yang ditandai occupied oleh walk-in tidak ditawarkan untuk booking overlap.
  - Booking menahan meja selama 15 menit setelah waktu booking.
  - Jika belum seated pada menit ke-15, sistem otomatis menandai no-show dan melepas meja.
  - Jika seated sebelum batas waktu, booking tetap seated.
  - Tidak ada deposit reservasi.
- **Traceability:** FR9.7, FR9.10, AC9.8, AC9.10

## Epic F — Rekomendasi produk

### US-028 — Menampilkan owner's picks dan best sellers

**Sebagai** owner, **saya ingin** menandai produk pilihan dan memberi tag, **sehingga** pelanggan mendapat rekomendasi yang sesuai strategi outlet.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Owner dapat menandai owner's picks dan memberi tag seperti coffee, sweet, atau sharing.
  - Menu Rekomendasi menampilkan owner's picks yang tersedia terlebih dahulu.
  - Berikutnya ditampilkan best sellers berdasarkan unit terjual di outlet tersebut selama 30 hari terakhir.
  - Item sold out dikecualikan, duplikasi dihapus, dan jumlah maksimal 30 item.
- **Traceability:** FR8.1–FR8.2, AC8.1–AC8.2

### US-029 — Menambahkan rekomendasi langsung ke cart

**Sebagai** pelanggan, **saya ingin** menambahkan item dari kartu rekomendasi ke keranjang, **sehingga** saya dapat memesan tanpa mencari ulang di menu.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Rekomendasi tampil sebagai kartu menu outlet di chat, dengan harga dan ketersediaan outlet itu.
  - Item dapat ditambahkan ke keranjang dan melanjutkan alur add-on, ringkasan, dan `Pesan & bayar` normal.
- **Traceability:** FR8.3, AC8.3

### US-052 — Meminta rekomendasi dengan bantuan AI

**Sebagai** pelanggan, **saya ingin** menceritakan selera saya di menu Rekomendasi (misalnya "yang manis buat berdua"), **sehingga** saya mendapat saran menu yang cocok tanpa harus menelusuri seluruh menu.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - AI hanya berjalan di alur Rekomendasi; alur Pesan, Reservasi, dan lainnya tetap berbasis tombol tanpa AI.
  - Saran hanya berisi item aktif yang tersedia di outlet tersebut dengan harga outlet; owner's picks diutamakan bila sesuai permintaan.
  - AI hanya membaca data (menu, tag, ketersediaan, penjualan 30 hari) dan tidak membuat cart, order, atau perubahan stok.
  - Saran tampil sebagai kartu menu; item masuk keranjang hanya saat pelanggan menekannya, lalu mengikuti alur add-on, ringkasan, dan `Pesan & bayar` yang normal (US-029, US-011).
  - Chat langsung menampilkan "Sebentar ya, lagi cariin rekomendasi…" dengan indikator mengetik sebelum AI selesai, sekali per permintaan, supaya chat tidak terasa diam selama proses yang bisa sampai 30 detik.
  - Jika AI gagal atau lebih dari 30 detik, chat menampilkan owner's picks dan best sellers (US-028).
  - Pemanggilan tool AI tercatat dengan aktor `agent`.
- **Traceability:** FR8.4, FR6.3, AC8.4–AC8.7

## Epic G — Ledger, laporan, dan admin web

### US-030 — Menyimpan ledger append-only

**Sebagai** owner, **saya ingin** setiap transaksi keuangan dicatat sebagai ledger append-only, **sehingga** catatan keuangan dapat diaudit dan tidak dapat dihapus diam-diam.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Sale, refund, reversal, expense, delivery fee, PB1, shortage, dan surplus dicatat sebagai entry yang sesuai.
  - Entry tidak dapat diedit atau dihapus oleh UI, API, atau agent.
  - Koreksi hanya dilakukan melalui entry reversal yang merujuk entry asal.
  - Entry mencatat outlet, metode pembayaran jika relevan, aktor, dan waktu.
- **Traceability:** FR3.1, NFR3, AC3.1–AC3.2, ACN3

### US-031 — Mencatat pengeluaran manual

**Sebagai** owner, **saya ingin** mencatat expense cash untuk outlet tertentu, **sehingga** cashflow mencakup pengeluaran operasional.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Layar Pengeluaran hanya untuk pengeluaran langsung; pembelian ke supplier lewat PO ada di tab **PO & Supplier** pada Dashboard (US-057–US-061).
  - Owner dapat memasukkan nominal, deskripsi, tanggal, dan outlet.
  - Sistem membuat ledger entry dengan identitas owner.
  - Staff tidak dapat membuka atau menggunakan layar expense.
- **Traceability:** FR3.2, AC3.3

### US-032 — Melihat laporan cashflow

**Sebagai** owner, **saya ingin** melihat cashflow harian, mingguan, dan bulanan per outlet maupun gabungan, **sehingga** saya dapat memantau kesehatan bisnis.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Ringkasan dan tren dihitung dari ledger, bukan dari nilai yang dapat diedit langsung.
  - Cash, QRIS, revenue, delivery fee, dan PB1 ditampilkan terpisah.
  - Batas hari mengikuti zona waktu masing-masing outlet.
  - Staff tidak dapat melihat angka cashflow owner.
  - Laporan menampilkan kas masuk, kas keluar, dan kas bersih beserta perubahan terhadap periode sebelumnya, pengeluaran per outlet, dan daftar pengeluaran terbaru.
- **Traceability:** FR3.3, FR7.2, AC3.4–AC3.5, AC7.1

### US-057 — Membuat purchase order ke supplier

**Sebagai** owner atau staf outlet, **saya ingin** mencatat pesanan barang ke supplier sebagai purchase order (PO) per outlet, **sehingga** pembelian bahan tercatat sejak dipesan, bukan hanya saat dibayar.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Owner dapat mengelola daftar supplier (nama, nomor telepon opsional, catatan) untuk seluruh bisnis.
  - Owner, atau staf untuk outlet yang ditugaskan kepadanya, membuka PO untuk satu outlet dan satu supplier: tanggal order, baris item (bahan dari daftar stok atau item teks bebas, jumlah, satuan, harga satuan dalam rupiah bulat), dan total; PO mendapat nomor per outlet (mis. `PO-A-0012`).
  - Pembuat PO memilih satu termin pembayaran: **bayar mundur (tempo)** dengan tanggal jatuh tempo, atau **bayar di muka** dengan perkiraan tanggal barang datang.
  - Membuat PO tidak membuat ledger entry dan tidak mengubah stok.
  - PO tanpa pembayaran dan tanpa penerimaan barang dapat dibatalkan dengan alasan wajib; PO yang sudah dibayar atau sudah menerima barang tidak dapat dibatalkan.
  - PO yang dibuka staf langsung berstatus terbuka tanpa persetujuan dan mencatat pembuatnya; PO bayar di muka langsung memunculkan permintaan bayar di dashboard owner.
  - Staf tidak dapat membuka PO untuk outlet lain, membatalkan PO, mengelola supplier, atau mencatat pembayaran, termasuk lewat API langsung.
- **Traceability:** FR1.5, FR3.5, FR3.6, FR3.9, AC3.6, AC3.11, AC3.13
- **Catatan alur:** Skema 1 (bayar mundur): PO dibuka → barang datang dan dicek → PO ditutup → pengingat bayar di dashboard owner. Skema 2 (bayar di muka): PO dibuka → notifikasi bayar di dashboard owner → barang tiba dan dicek → PO ditutup.

### US-058 — PO bayar mundur: cek barang, tutup PO, lalu bayar

**Sebagai** owner, **saya ingin** PO tempo baru muncul sebagai pengingat bayar setelah barangnya dicek dan PO ditutup, **sehingga** saya hanya membayar barang yang benar-benar diterima dan tidak melewatkan jatuh tempo.

- **Fase/Prioritas:** MVP / P0
- **Alur:** PO dibuka → barang datang → admin cek qty sesuai PO → PO ditutup → pengingat pembayaran muncul di dashboard owner → owner mencatat pembayaran.
- **Acceptance criteria:**
  - Setelah PO tempo ditutup, kartu **Pembayaran supplier** di dashboard owner menampilkan PO tersebut dengan supplier, outlet, sisa hutang, dan tanggal jatuh tempo.
  - Owner mencatat satu atau beberapa pembayaran (tanggal, nominal, metode cash atau transfer bank) sampai lunas; pembayaran yang melebihi sisa hutang ditolak.
  - Setiap pembayaran membuat satu ledger entry `expense` pada tanggal bayar dengan metode, nomor PO, dan supplier.
  - Pembayaran cash dapat diambil dari laci shift kasir yang sedang terbuka sehingga ekspektasi kas shift itu berkurang; jika tidak, dianggap dibayar di luar laci.
  - Lewat tanggal jatuh tempo (zona waktu outlet) dengan sisa hutang, pengingat ditandai **overdue** dan tampil paling atas; pengingat hilang setelah lunas.
  - Pembayaran tidak dapat diedit atau dihapus.
- **Traceability:** FR3.7, FR3.9, FR3.11, FR11.8, AC3.7, AC3.8, AC3.10

### US-059 — PO bayar di muka: notifikasi bayar, barang tiba, cek, tutup PO

**Sebagai** owner, **saya ingin** diingatkan membayar PO bayar di muka begitu PO dibuka, lalu PO ditutup setelah barang tiba dan dicek, **sehingga** pembayaran di muka tidak terlupa dan barang yang ditunggu tetap terpantau.

- **Fase/Prioritas:** MVP / P0
- **Alur:** PO dibuka → notifikasi pembayaran muncul di dashboard owner → owner membayar → barang tiba → admin cek qty sesuai PO → PO ditutup.
- **Acceptance criteria:**
  - Begitu PO bayar di muka dibuka, kartu **Pembayaran supplier** di dashboard owner menampilkan permintaan bayar untuk PO itu.
  - Owner mencatat pembayaran penuh; ledger `expense` diposting pada tanggal bayar dan permintaan bayar hilang dari dashboard.
  - Setelah dibayar, PO berstatus **menunggu barang**; PO bayar di muka yang belum dibayar tidak dapat ditutup.
  - Laporan menampilkan nilai barang yang sudah dibayar tetapi belum diterima, terpisah dari kas keluar, sampai PO ditutup.
- **Traceability:** FR3.8, FR3.9, FR3.11, AC3.9

### US-060 — Mengecek barang datang terhadap PO dan menutup PO

**Sebagai** owner atau staf outlet, **saya ingin** mengecek apakah qty barang yang datang sesuai PO lalu menutup PO jika sesuai, **sehingga** stok bertambah sesuai barang yang benar-benar diterima dan selisih tidak terlewat.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Saat barang datang, staf (atau owner) melakukan cross-check: mengisi qty yang datang di samping qty PO untuk setiap baris, beserta tanggal terima dan catatan opsional; aplikasi menandai baris yang sesuai dan yang kurang.
  - Baris yang terhubung ke bahan menambah stok lewat movement restock yang merujuk PO, dikonversi ke satuan dasar bahan; baris teks bebas tidak mengubah stok.
  - Barang boleh datang dalam beberapa kali pengiriman; qty yang diterima tidak boleh melebihi qty PO.
  - Jika semua baris sesuai, staf **menutup PO**.
  - Jika ada selisih, staf tidak dapat menutup PO: PO tetap terbuka dengan status **ada selisih** dan kekurangan per baris, serta muncul di daftar **PO ada selisih** pada dashboard owner. Setelah sisanya datang dan sesuai, staf dapat menutupnya; jika tidak, **hanya owner** yang dapat menutup PO itu dengan **catatan wajib**. Untuk PO tempo, hutang menjadi qty diterima × harga satuan (diputuskan). Refund supplier untuk PO bayar di muka yang kurang belum termasuk MVP.
  - Setiap pengecekan dan penutupan mencatat siapa dan kapan, dan PO yang ditutup tidak dapat dibuka lagi.
- **Traceability:** FR1.5, FR3.11, FR4.2, FR4.10, FR4.11, AC4.9, AC4.10

### US-061 — Tab PO & Supplier di dashboard dan pengingat pembayaran

**Sebagai** owner, **saya ingin** melihat seluruh PO di tab tersendiri dan semua pembayaran supplier yang perlu dilakukan di dashboard, **sehingga** saya tahu apa yang harus dibayar dan barang apa yang masih ditunggu.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Dashboard owner memiliki tab **PO & Supplier** (di samping tab Ringkasan) dengan filter outlet dan bulan sendiri, daftar supplier, dan tombol Buka PO; layar Pengeluaran hanya untuk pengeluaran langsung. Staf mendapat layar Purchase Order untuk outletnya (daftar PO, buka PO, cross-check barang) tanpa pembayaran dan hutang.
  - Daftar PO di tab itu memiliki filter terbuka (menunggu barang), ada selisih, menunggu pembayaran, overdue, dan ditutup, serta detail PO berisi baris item, riwayat pengecekan barang, dan riwayat pembayaran beserta pencatatnya.
  - Tab itu memiliki kartu **Pembayaran supplier** (semua PO yang perlu dibayar, tidak ikut filter bulan): PO tempo yang sudah ditutup dan belum lunas (overdue dulu, lalu jatuh tempo terdekat) dan PO bayar di muka yang terbuka dan belum dibayar, masing-masing dengan tombol catat pembayaran.
  - Tab itu memiliki daftar **PO ada selisih** (supplier, outlet, baris yang kurang, sejak kapan) dengan tombol **Tutup dengan catatan** yang hanya tersedia untuk owner.
  - Kartu itu dan laporan cashflow menampilkan total hutang supplier (jumlah overdue dan jatuh tempo 7 hari) serta barang yang sudah dibayar tetapi belum diterima, terpisah dari kas keluar.
  - Tab itu memiliki laporan **Ringkasan PO** per outlet dan bulan (menurut tanggal PO dibuka): jumlah dan nilai PO yang dibuka vs ditutup, barang belum datang / sebagian / sudah datang, dan pembayaran belum dibayar / sebagian / lunas, dipisah bayar mundur dan bayar di muka; setiap angka membuka daftar PO yang sesuai.
  - Staf tidak melihat kartu dan laporan ini, termasuk lewat API langsung.
- **Traceability:** FR3.10, FR3.11, FR3.12, FR7.2, AC3.12, AC3.13, AC3.14

### US-033 — Menggunakan dashboard admin sesuai peran

**Sebagai** owner atau staf, **saya ingin** menggunakan web app yang menampilkan fungsi sesuai peran dan outlet, **sehingga** pekerjaan saya cepat dan data tetap terbatas.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Owner melihat sales, cashflow, dan stok per outlet serta gabungan.
  - Staff melihat order, open bill, reservasi, dan stok hanya untuk outlet yang ditugaskan.
  - Menu, resep, harga, expense, laporan, outlet, dan akun staf hanya tersedia bagi owner sesuai matriks akses.
- **Traceability:** FR1.4–FR1.5, FR7.1–FR7.2, AC1.5–AC1.6, AC7.1

### US-034 — Memasukkan order dari counter

**Sebagai** staf, **saya ingin** membuat order dine-in dan takeaway dari counter screen, **sehingga** pelanggan yang datang langsung tetap menggunakan proses order dan stok yang sama.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Staf dapat memilih item, kuantitas, add-on, meja bila dine-in, dan metode pembayaran yang tersedia.
  - Order diberi channel `counter`.
  - Order menggunakan fungsi yang sama dengan web chat, termasuk validasi stok dan lifecycle.
- **Traceability:** FR7.4, FR2.8, AC7.3, AC2.9

### US-035 — Menggunakan admin app di desktop dan mobile

**Sebagai** staf, **saya ingin** menyelesaikan pekerjaan operasional dari browser mobile maupun desktop, **sehingga** saya tetap dapat bekerja saat berada di area outlet.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Counter, order board, open bills, stok, dan reservasi dapat digunakan pada viewport 360 px.
  - Tidak ada tindakan utama yang memerlukan horizontal scrolling.
  - MVP membutuhkan koneksi internet dan tidak menyediakan offline mode.
- **Traceability:** FR7.3, NFR7, AC7.2, ACN9

## Epic H — Web chat, keamanan, dan ketahanan sistem

### US-036 — Menyimpan sesi web chat di server lewat API publik

**Sebagai** pelanggan, **saya ingin** chat melanjutkan dari langkah terakhir saat halaman di-refresh atau link dibuka ulang di HP yang sama, **sehingga** keranjang dan isian saya tidak hilang.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Langkah, keranjang, add-on terpilih, dan isian disimpan di server dalam sesi chat yang terikat ke HP; refresh atau buka ulang dalam 2 jam melanjutkan di langkah yang sama.
  - Keranjang tanpa aktivitas selama 2 jam dikosongkan; order dan booking yang sudah dibuat tidak terpengaruh.
  - Web chat memakai endpoint publik `/api/v1/public/*` yang dibatasi oleh slug outlet atau token meja: hanya membaca menu, QRIS statis, dan ketersediaan reservasi outlet itu, membuat order pay-first dan booking untuk outlet itu, dan membaca order/booking dengan access key (atau booking dengan kode booking + no HP).
  - Rate limit per sesi HP dan per IP; request di atas batas ditolak dengan "coba lagi sebentar" tanpa membuat apa pun.
  - 95% request web chat (selain panggilan rekomendasi AI) dijawab dalam 1 detik pada beban normal; state chat tidak disimpan di memori satu instance API.
- **Traceability:** FR6.1, FR6.2, NFR4–NFR6, AC6.5, ACN4–ACN6, ACN8

### US-037 — Menjamin aksi pelanggan diproses maksimal sekali

**Sebagai** owner, **saya ingin** setiap aksi pelanggan diproses maksimal sekali, **sehingga** satu tap tidak menggandakan order, booking, pengurangan stok, atau ledger.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Setiap aksi yang membuat atau mengubah sesuatu (`Pesan & bayar`, "Saya sudah bayar", batal, booking, batal/reschedule booking) membawa idempotency key dari halaman.
  - Key yang sudah diproses mengembalikan hasil sebelumnya, bukan menjalankan ulang.
  - `Pesan & bayar` yang terkirim dua kali, atau job timer yang dikirim ulang RabbitMQ setelah worker crash, menghasilkan tepat satu order, satu stock deduction, dan satu set ledger entry.
- **Traceability:** FR6.4, NFR8, AC6.6, ACN7

### US-038 — Mengisolasi tenant, outlet, dan API

**Sebagai** owner, **saya ingin** data bisnis dan outlet terisolasi di level database serta endpoint terlindungi token, **sehingga** data tidak bocor antar tenant atau antar staf.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - PostgreSQL RLS mencegah tenant 1 membaca baris tenant 2, termasuk query tanpa tenant filter.
  - Akses staf ke outlet ditegakkan oleh database, bukan hanya filter frontend/backend.
  - Endpoint FastAPI selain endpoint publik web chat (`/api/v1/public/*`) dan health check menolak token hilang, invalid, atau expired; request publik dengan slug/token tidak dikenal atau sudah diganti, atau tanpa access key, ditolak tanpa data.
  - Record operasional membawa tenant_id dan outlet_id.
  - Service API dan worker bersifat stateless, containerized, memakai pooled PostgreSQL connections, dan dapat diskalakan tanpa redesign schema/arsitektur.
  - Login dan token dikelola Supabase Auth; token membawa klaim `tenant_id` dan `app_role`; RLS membaca tenant dan pengguna dari sesi database yang diisi backend setelah token diverifikasi, akses outlet dan status aktif dicek langsung ke database, dan backend tidak memakai service role untuk membaca atau menulis data tenant.
  - Token ditandatangani dengan kunci asimetris dan diverifikasi lewat public key; token dengan kunci atau algoritma yang salah ditolak.
- **Traceability:** NFR2, NFR5, NFR6, ACN2, ACN6, ACN8

### US-039 — Memenuhi data residency dan auditability

**Sebagai** owner dan pelanggan, **saya ingin** data disimpan di Indonesia dan perubahan penting dapat diaudit, **sehingga** platform memenuhi kebutuhan kepatuhan dan kepercayaan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Auth, database, backup, dan object storage berada di Supabase. Supabase tidak punya region Indonesia, sehingga region terdekat (Singapura) dipakai.
  - Data nyata hanya boleh disimpan setelah dasar transfer lintas negara yang ditinjau legal dicatat (T-108) dan privacy notice menyebutkan lokasi penyimpanan; sebelum itu semua environment hanya berisi data dummy.
  - Ledger dan stock movement bersifat append-only.
  - Setiap write pada ledger/stock mencatat actor dan timestamp.
  - Agent tidak memiliki akses tulis langsung ke tabel ledger atau stock.
- **Traceability:** NFR1, NFR3, ACN1, ACN3

## Epic I — Data pelanggan dan privasi PDP

### US-040 — Melihat pemberitahuan privasi sebelum mengisi data

**Sebagai** pelanggan, **saya ingin** tahu data apa yang diminta, untuk apa, disimpan di mana, dan kapan dihapus sebelum saya mengisinya, **sehingga** saya dapat memesan secara transparan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Sebelum nama, no HP, atau alamat dikirim, chat menampilkan pemberitahuan privasi singkat dan link pemberitahuan lengkap.
  - Data yang dikirim mencatat versi pemberitahuan yang ditampilkan dan waktunya.
  - Tidak ada akun pelanggan dan tidak ada membership di MVP.
- **Traceability:** FR12.1, FR12.3, AC12.1

### US-041 — Menganonimkan data pelanggan setelah selesai

**Sebagai** pelanggan, **saya ingin** data pribadi saya hanya disimpan selama pesanan atau booking berjalan, **sehingga** data saya tidak menumpuk di server.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Nama, no HP, dan alamat dianonimkan otomatis saat order selesai atau batal, atau booking selesai, batal, atau no-show.
  - Order, total ledger, dan riwayat keuangan tetap utuh dengan customer anonim.
  - Data personal hanya disimpan pada customer tables, bukan ledger atau stock movement.
  - HP boleh mengingat nama, no HP, dan alamat terakhir milik pelanggan di perangkat saja untuk mengisi otomatis; pelanggan bisa menghapusnya dari chat; server tidak pernah menghubungkan order dari kunjungan berbeda menjadi profil.
- **Traceability:** FR12.2–FR12.4, AC12.2–AC12.4

## Epic J — Agent layer (Phase 2)

### US-042 — Memproses order free-text dengan konfirmasi

**Sebagai** pelanggan, **saya ingin** menulis order dengan bahasa natural, **sehingga** saya tidak harus mengikuti format menu yang kaku.

- **Fase/Prioritas:** P2 / P0 untuk Phase 2
- **Acceptance criteria:**
  - Agent mengekstrak item, add-on, kuantitas, dan total termasuk PB1.
  - Agent menampilkan ringkasan terstruktur dan menunggu konfirmasi eksplisit.
  - Sebelum konfirmasi tidak ada order dan tidak ada pengurangan stok.
  - Setelah konfirmasi, agent memanggil fungsi pembuatan order deterministik yang sama dengan staff.
  - Ringkasan tampil sebagai kartu dengan tombol `Ya, pesan` dan `Ubah`; harga, PB1, dan total berasal dari quote server (US-066).
  - Item yang sold out tidak masuk proposal; agent memberi tahu dan menawarkan alternatif (US-067).
- **Traceability:** FR2.4, FR6.3, FR13.3, FR13.5, AC6.2, AC6.4, AC13.5

### US-043 — Membuat reservasi lewat chat bebas sampai booking jadi

**Sebagai** pelanggan, **saya ingin** cukup menulis "aku mau reservasi tempat dong jam 19:00 untuk 3 orang", **sehingga** agent membaca data reservasi outlet dan membuatkan booking untuk saya tanpa saya harus bingung mengikuti langkah demi langkah.

- **Fase/Prioritas:** P2 / P0 untuk Phase 2
- **Acceptance criteria:**
  - Agent mengekstrak jumlah orang, tanggal, waktu (serta area atau catatan bila ada) dalam zona waktu outlet. Jam tanpa tanggal berarti hari ini bila jam itu masih bisa dibooking; jika sudah lewat, agent menanyakan harinya. Kata seperti *besok*, *lusa*, *Sabtu ini*, *nanti malam* diubah menjadi tanggal. Untuk "jam 7", bila hanya 07:00 atau 19:00 yang masuk jam booking, itu yang dipakai; jika keduanya mungkin, agent bertanya.
  - Agent hanya menanyakan detail yang kurang, satu per pesan; nama dan nomor HP terisi dari perangkat bila pernah disimpan, dan pemberitahuan privasi tampil sebelum data dikirim.
  - Worker agent mengecek ketersediaan dengan aturan yang sama dengan alur tombol: jam booking, jangka waktu booking, maksimal jumlah orang, meja terkecil yang muat, dan maksimal 2 booking mendatang per nomor HP.
  - Jika ada meja, chat menampilkan kartu ringkasan (outlet, hari dan tanggal, jam dengan WIB/WITA/WIT, jumlah orang, nama, nomor HP) dengan tombol `Ya, buat reservasi` dan `Ubah`. Jika penuh, agent mengatakannya dan menawarkan maksimal 3 jam terdekat yang kosong sebagai tombol (atau hari berikutnya bila hari itu habis).
  - Booking baru dibuat setelah pelanggan menekan tombol konfirmasi pada kartu terakhir atau membalas hanya dengan kata setuju (*ya*, *oke*, *betul*, *gas*, dll.) yang dicocokkan oleh aturan di kode, bukan oleh model. Perubahan detail membuat kartu baru dan kartu lama tidak bisa dikonfirmasi lagi.
  - Booking dibuat melalui fungsi deterministik yang sama dengan alur tombol (US-023), dicek ulang saat konfirmasi (US-024), aktor `agent`, sumber "web chat (AI)" di board staf; chat menampilkan kode booking, link, dan `Tambah ke kalender` (US-025).
  - Pelanggan dapat mengganti jam atau membatalkan booking dari HP yang sama lewat chat bebas ("ganti jadi jam 8 ya"), dengan batas pembatalan outlet dan kartu konfirmasi yang sama.
- **Traceability:** FR9.9, FR6.3, FR13.4–FR13.6, AC6.4, AC13.1–AC13.7

### US-044 — Menjawab FAQ dan upsell

**Sebagai** pelanggan, **saya ingin** bertanya secara bebas tentang menu, jam buka, dan info outlet lainnya, **sehingga** saya mendapat bantuan yang relevan dalam percakapan.

- **Fase/Prioritas:** P2 / P1
- **Acceptance criteria:**
  - Agent menggunakan data menu, stok, tag, dan penjualan outlet yang benar.
  - Rekomendasi percakapan sudah tersedia di MVP (US-052); story ini memperluas agent ke FAQ dan upsell di luar alur Rekomendasi.
  - FAQ dapat dijawab tanpa mengubah data operasional.
  - Upsell tidak mengubah cart/order secara langsung.
  - FAQ dan upsell berjalan lewat supervisor agent dan worker agent yang sama (US-066) dan tunduk pada batas cakupan outlet.
- **Traceability:** FR6.3, FR13.1, FR13.11

### US-045 — Mendapatkan rekomendasi restock dan anomali cashflow

**Sebagai** owner, **saya ingin** menerima saran restock, timing, dan pola cashflow yang tidak biasa, **sehingga** saya dapat mengambil keputusan lebih cepat.

- **Fase/Prioritas:** P2 / P1
- **Acceptance criteria:**
  - Saran menggunakan histori sales velocity dan data cashflow.
  - Saran hanya advisory dan menampilkan dasar/reasoning yang dapat ditinjau owner.
  - Agent tidak memiliki tool untuk mengubah stok, membuat stock movement, atau membuat purchase order.
  - Restock hanya terjadi setelah owner mencatatnya melalui alur deterministik.
- **Traceability:** FR3.4, FR4.4, AC6.3–AC6.4

### US-066 — Asisten AI dengan supervisor agent dan worker agent

**Sebagai** owner, **saya ingin** asisten AI di web chat yang dibagi menjadi supervisor agent dan worker agent, **sehingga** percakapan dengan pelanggan tetap luwes tetapi setiap aksi ke sistem tetap aman, terkontrol, dan tercatat.

- **Fase/Prioritas:** P2 / P0 untuk Phase 2
- **Acceptance criteria:**
  - Saat Asisten AI outlet aktif, teks bebas di mana pun dalam web chat (link outlet dan QR meja) diproses supervisor agent; tombol menu utama dan kata "menu" tetap berfungsi.
  - **Supervisor agent** adalah satu-satunya yang berbicara dengan pelanggan: menentukan maksud (reservasi, order, info outlet, rekomendasi, FAQ, di luar cakupan), menanyakan detail yang kurang, memberi tugas terstruktur ke worker, memeriksa hasilnya, dan menyusun balasan. Supervisor tidak punya akses database dan tool lain selain menyerahkan tugas ke worker.
  - **Worker agent** hanya menjalankan tool deterministik berversi (baca, proposal, commit), tidak berbicara dengan pelanggan, tidak menyimpan memori antar tugas, dan dibatasi 8 pemanggilan tool per tugas. Tenant dan outlet ditentukan server dari slug atau token, bukan dari model.
  - Supervisor hanya menyampaikan fakta (harga, jam, ketersediaan, promo, status) yang berasal dari hasil worker yang lolos validasi skema pada pesan tersebut.
  - Tidak ada tool untuk menulis stok, ledger, pembayaran, harga, menu, atau promo, dan tidak ada tool untuk mengonfirmasi pembayaran.
  - Jika balasan lebih dari 2 detik, chat menampilkan "Sebentar ya, aku cek dulu…" dengan indikator mengetik. Jika agent gagal, lebih dari 30 detik, atau melewati batas langkah, tidak ada yang dibuat dan chat menampilkan tombol alur terkait (misalnya Reservasi dengan detail yang sudah dipahami).
  - Agent menolak topik di luar outlet, tidak membuka data pelanggan lain, prompt, atau tool, dan memperlakukan teks pelanggan maupun teks owner (deskripsi menu, promo) sebagai data, bukan instruksi.
  - Setiap pesan yang ditangani agent tercatat sebagai agent run (maksud, tugas worker, tool call beserta input/output, versi model dan prompt, latensi, alasan fallback); data pribadi di dalamnya dianonimkan bersama data pelanggan dan run dihapus setelah 30 hari.
- **Traceability:** FR6.3, FR13.1–FR13.3, FR13.10–FR13.12, AC13.12–AC13.15

### US-067 — Mendapat info promo, menu baru, dan menu habis di chat

**Sebagai** pelanggan, **saya ingin** agent memberi tahu promo yang sedang berjalan, menu baru, dan menu yang sedang habis, **sehingga** saya tahu apa yang menarik dan tidak kecewa memesan item yang tidak tersedia.

- **Fase/Prioritas:** P2 / P0 untuk Phase 2
- **Acceptance criteria:**
  - Pesan pertama sesi chat memuat maksimal 3 sorotan: promo aktif lebih dulu, lalu item berlabel Baru; tidak ada sorotan bila keduanya kosong.
  - Saat ditanya ("ada promo apa?", "menu baru apa aja?"), agent menampilkan promo aktif outlet ini dengan teks owner apa adanya dan menu baru sebagai kartu menu; bila tidak ada, agent mengatakannya tanpa mengarang.
  - Saat pelanggan meminta atau memesan item yang sold out di outlet ini, agent memberi tahu dan menyarankan maksimal 3 item tersedia dengan tag atau kategori yang sama; saat ditanya "apa yang lagi habis?", agent menyebut item yang sold out sekarang.
  - Semua info dibaca langsung dari sistem saat membalas; promo outlet lain, promo kedaluwarsa, atau promo nonaktif tidak pernah disebut.
  - Agent tidak menjanjikan diskon, gratis, atau syarat yang tidak tertulis di promo; total yang dibayar selalu dari quote server.
- **Traceability:** FR13.7–FR13.9, AC13.8–AC13.11

### US-068 — Mengelola promo dan label menu baru

**Sebagai** owner, **saya ingin** membuat promo per outlet dan menandai menu baru, **sehingga** agent dan web chat menyampaikan informasi yang benar kepada pelanggan.

- **Fase/Prioritas:** P2 / P0 untuk Phase 2
- **Acceptance criteria:**
  - Owner membuat, mengubah, dan menonaktifkan promo: judul, deskripsi singkat, satu atau beberapa outlet, tanggal dan jam mulai serta selesai, item menu terkait (opsional), dan saklar aktif.
  - Promo di Phase 2 hanya informasi: tidak mengubah harga, quote, PB1, pembayaran, atau ledger. Promo berbasis harga dilakukan dengan mengubah harga outlet selama periode itu.
  - Menu berlabel **Baru** di outlet selama 14 hari sejak aktif di outlet tersebut; owner dapat mengubah tanggal akhirnya atau mematikan label. Label tampil di kartu menu web chat, termasuk alur tombol.
  - Hanya owner yang dapat mengelola promo dan label Baru, di UI maupun API.
- **Traceability:** FR13.8–FR13.9, AC13.10–AC13.11

### US-069 — Mengaktifkan Asisten AI per outlet dan memantau hasilnya

**Sebagai** owner, **saya ingin** menyalakan atau mematikan Asisten AI per outlet dan melihat apa yang dikerjakan agent, **sehingga** saya bisa mencoba agent dengan aman dan kembali ke alur tombol kapan saja.

- **Fase/Prioritas:** P2 / P1
- **Acceptance criteria:**
  - Pengaturan outlet memiliki saklar **Asisten AI**, mati secara default. Saat mati, web chat berjalan persis seperti MVP dan teks bebas di luar Rekomendasi dijawab singkat dengan tombol menu utama.
  - Owner melihat per outlet dan periode: booking dan order yang dibuat agent, serta persentase pesan yang jatuh ke tombol (fallback).
  - Setiap booking atau order dari agent dapat ditelusuri ke agent run dan proposal yang dikonfirmasi.
- **Traceability:** FR13.10, FR13.12, AC13.12, AC13.15

## Epic K — Scale dan ekspansi (Phase 3)

### US-046 — Mengelola jadwal shift dan saran jadwal staf

**Sebagai** owner, **saya ingin** mencatat shift terjadwal staf (kehadiran sudah dicatat di US-053) dan menerima saran jadwal, **sehingga** kebutuhan manpower dapat direncanakan.

- **Fase/Prioritas:** P3 / P1
- **Acceptance criteria:**
  - Sistem mencatat shift terjadwal dan membandingkannya dengan kehadiran dari US-053.
  - Agent menyarankan jadwal berdasarkan pola demand historis.
  - Jadwal tetap memerlukan keputusan owner dan tidak mengubah penugasan tanpa persetujuan.
- **Traceability:** FR5.2, FR5.5

### US-047 — Mengonfirmasi pembayaran secara otomatis

**Sebagai** owner, **saya ingin** menggunakan payment gateway dynamic QRIS, **sehingga** pembayaran dapat dikonfirmasi tanpa pemeriksaan manual di akun merchant.

- **Fase/Prioritas:** P3 / P1
- **Acceptance criteria:**
  - Gateway menghasilkan QRIS dinamis dengan nominal order.
  - Payment confirmation diterima otomatis dan hanya satu kali untuk setiap transaksi.
  - Setelah confirmed, alur ledger dan order lifecycle yang sudah ada tetap digunakan.
- **Traceability:** FR11.9

### US-048 — Mendukung dropshipper dan marketplace

**Sebagai** dropshipper, **saya ingin** menghubungkan order dengan marketplace, **sehingga** penjualan dan stok dapat dikelola dari satu platform.

- **Fase/Prioritas:** P3 / P2
- **Acceptance criteria:**
  - Tenant dapat menggunakan tipe bisnis dropshipper.
  - Sistem menyediakan integrasi yang direncanakan untuk Shopee, Tokopedia, dan TikTok Shop.
  - Order marketplace memakai prinsip auditability, tenant isolation, dan duplicate-safe processing yang sama.
- **Traceability:** FR1.1, Scope item 15, §10 Phase 3

### US-065 — WhatsApp sebagai kanal pelanggan opsional

**Sebagai** owner, **saya ingin** opsi menghubungkan nomor WhatsApp outlet untuk notifikasi, pengingat, dan mungkin pemesanan, **sehingga** pelanggan yang lebih suka WhatsApp tetap terlayani.

- **Fase/Prioritas:** P3 / P2
- **Acceptance criteria:**
  - Memakai WhatsApp Cloud API resmi lewat queue dan worker dengan retry dan dead-letter; channel `whatsapp_online` dan `whatsapp_table` mulai dipakai.
  - Web chat tetap menjadi kanal utama dan berjalan tanpa WhatsApp.
  - Fondasi awal ada di branch PR #54 (ditutup tanpa merge, disimpan sebagai referensi). Sebelum dikerjakan, cek ulang batasan negara Meta untuk nomor Indonesia (error 130497 saat uji coba).
- **Traceability:** §4 Phase 3, §10 Phase 3

## Epic L — Platform, hosting, dan antrean (Supabase, Railway, RabbitMQ)

### US-049 — Menjalankan environment demo dan pilot di Supabase dan Railway

**Sebagai** tim produk, **saya ingin** menjalankan aplikasi di Supabase dan Railway, **sehingga** demo dapat diperlihatkan ke calon merchant dengan biaya rendah dan jalur yang jelas menuju pilot.

- **Fase/Prioritas:** MVP (demo dan pilot) / P0
- **Acceptance criteria:**
  - Auth, PostgreSQL, dan Storage memakai Supabase; API, worker timer, dan RabbitMQ berjalan di Railway; admin app dan web chat dapat di-host terpisah (Cloudflare Pages atau Vercel).
  - Environment demo, staging, dan produksi terpisah (project dan secret).
  - Demo hanya memakai data dummy, berjalan di Supabase Free dan Railway Hobby, dan pemakaian dipantau dengan alert.
  - Project Supabase Free tidak ter-pause saat demo karena ada keep-alive.
  - Dasar transfer lintas negara (karena Supabase dan Railway berada di Singapura) terdokumentasi sebelum data nyata masuk.
  - Sebelum pilot dengan merchant nyata, checklist promosi lulus: Supabase Pro dengan backup, volume untuk RabbitMQ, API dan worker dipisah, dan keputusan region terpenuhi.
- **Traceability:** NFR1, NFR4, NFR6. Keputusan hosting baru, perlu ditambahkan ke PRD.

### US-050 — Antrean job dengan retry bertingkat dan dead-letter

**Sebagai** owner, **saya ingin** job yang gagal diulang otomatis dan tetap terlihat jika terus gagal, **sehingga** pembatalan order, pelepasan meja, dan anonimisasi tidak hilang diam-diam.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - RabbitMQ hanya dipakai untuk job terjadwal (US-051); request web chat ditangani API langsung. Antrean durable dan pesan persisten.
  - Kegagalan sementara (timeout, deadlock database, 5xx) diulang dengan jeda bertingkat 5 detik, 30 detik, lalu 2 menit, dengan batas percobaan per antrean.
  - Kegagalan permanen (payload tidak valid) langsung masuk dead-letter dengan alasan kegagalan.
  - Pesan dead-letter dapat dilihat, diperiksa, dan diputar ulang atau dibuang oleh admin berwenang; tindakan itu tercatat.
  - Ack dikirim setelah transaksi database commit; redelivery tidak menghasilkan order, stock movement, atau ledger ganda (US-037).
  - Alert muncul jika ada pesan di dead-letter atau antrean menumpuk.
- **Traceability:** NFR4, NFR8, ACN7, ACN10

### US-051 — Job terjadwal yang andal

**Sebagai** owner, **saya ingin** pembatalan order unpaid, pelepasan no-show, dan anonimisasi berjalan tepat waktu walau layanan restart, **sehingga** stok, meja, dan data pelanggan tidak tertahan karena timer hilang.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Job disimpan di database dan dipublikasikan ke RabbitMQ saat jatuh tempo; restart broker atau worker tidak menghilangkan job.
  - Handler idempotent dan memeriksa status terkini sebelum bertindak (misalnya pelanggan sudah menekan "Saya sudah bayar", atau booking sudah seated).
  - Job yang terlambat karena downtime tetap dijalankan segera setelah sistem pulih.
  - Job yang dibatalkan (misalnya setelah "Saya sudah bayar") tidak dijalankan.
  - Berlaku untuk unpaid timeout (US-021), no-show 15 menit (US-027), dan anonimisasi data pelanggan setelah order/booking selesai (US-041). Tidak ada job reminder reservasi; pengingat lewat file kalender (US-025).
- **Traceability:** FR10.4, FR9.10, FR12.2, NFR4, ACN10

## Epic M — Kehadiran staf (MVP)

### US-053 — Clock in dan clock out staf

**Sebagai** staf, **saya ingin** mencatat jam masuk dan jam pulang di tablet absensi outlet dengan foto selfie, **sehingga** kehadiran saya tercatat tanpa buku absen dan terbukti saya berada di outlet.

- **Fase/Prioritas:** MVP (Phase 1 dan pilot) / P0
- **Acceptance criteria:**
  - Clock in dan clock out hanya bisa dilakukan di tablet absensi outlet (US-055); waktu ditampilkan dalam zona waktu outlet.
  - Di tablet, staf memilih namanya (tanpa PIN) dari daftar staf yang ditugaskan ke outlet itu, lalu mengambil selfie dengan kamera depan; catatan hanya tersimpan bersama foto tersebut.
  - Jika kamera tidak tersedia atau foto dibatalkan, tidak ada yang tercatat dan tablet meminta selfie ulang.
  - Satu staf hanya memiliki satu catatan terbuka; clock in kedua ditolak. Staf yang tidak ditugaskan ke outlet itu tidak muncul di daftar, dan permintaan API langsung untuk outlet lain ditolak.
  - Clock in atau clock out dari HP staf sendiri atau admin app tidak tersedia; di admin app staf hanya melihat riwayatnya sendiri, termasuk selfie-nya.
  - Clock out tanpa catatan terbuka ditolak; setelah clock out, durasi ditampilkan.
  - Sebelum clock in pertama, staf melihat pemberitahuan bahwa selfie disimpan 45 hari dan hanya dilihat owner dan dirinya sendiri.
  - Jika staf belum clock out sampai jam tutup outlet ditambah masa tenggang (default 1 jam, diatur owner per outlet), catatan ditandai "perlu dikoreksi". Sistem tidak mengarang jam pulang, jam kerjanya belum dihitung, dan staf dapat clock in lagi.
  - Staf hanya melihat catatan kehadirannya sendiri.
- **Traceability:** FR5.1, FR5.3, FR5.7, AC5.1–AC5.3, AC5.5, AC5.6, AC5.8

### US-054 — Melihat dan mengoreksi kehadiran staf

**Sebagai** owner, **saya ingin** melihat jam kerja staf per outlet dan mengoreksi catatan yang salah, **sehingga** rekap kehadiran dapat dipercaya.

- **Fase/Prioritas:** MVP (Phase 1 dan pilot) / P0
- **Acceptance criteria:**
  - Owner melihat kehadiran semua staf per outlet, staf, dan rentang tanggal: jam kerja per hari, total, catatan yang ditandai, serta selfie clock in dan clock out untuk memeriksa apakah orangnya sesuai.
  - Batas hari mengikuti zona waktu masing-masing outlet.
  - Koreksi atau pengisian jam pulang yang hilang wajib disertai alasan; nilai asli tetap dapat dilihat, dan owner, waktu, serta alasan dicatat.
  - Staf tidak dapat membuka laporan ini atau mengoreksi catatan, termasuk lewat API langsung.
  - Perhitungan gaji dan lembur tidak termasuk MVP.
- **Traceability:** FR5.4, FR5.7, AC5.4–AC5.5, AC5.8

### US-055 — Memasang tablet absensi di outlet

**Sebagai** owner, **saya ingin** menghubungkan tablet di outlet sebagai perangkat absensi, **sehingga** staf hanya bisa absen saat benar-benar berada di outlet.

- **Fase/Prioritas:** MVP (Phase 1 dan pilot) / P0
- **Acceptance criteria:**
  - Owner membuat kode pairing sekali pakai per outlet di admin app; tablet yang memasukkan kode itu tetap login sebagai outlet tersebut.
  - Sesi tablet hanya bisa menampilkan staf outlet itu dan mencatat clock in/out; order, laporan, pengaturan, dan data outlet lain ditolak.
  - Owner melihat tablet outlet beserta aktivitas terakhirnya dan dapat melupakannya ("Lupakan perangkat", dengan konfirmasi) kapan saja; tablet yang dilupakan langsung ditolak dan harus di-pairing ulang dengan kode baru.
  - Satu outlet hanya boleh punya satu tablet aktif. Selama masih ada tablet aktif, owner tidak bisa membuat kode pairing baru dan pairing tablet lain ditolak; untuk ganti tablet, owner melupakan tablet lama dulu lalu pairing tablet baru.
- **Traceability:** FR5.6, AC5.7

### US-056 — Melihat jam ramai, jam sepi, dan keramaian outlet

**Sebagai** owner, **saya ingin** melihat jam ramai dan jam sepi serta seberapa ramai tiap outlet saat ini, **sehingga** saya dapat mengatur staf, stok, dan promo sesuai kondisi outlet.

- **Fase/Prioritas:** MVP / P1
- **Acceptance criteria:**
  - Dashboard menampilkan order per jam untuk outlet dan periode terpilih, dalam jam buka dan zona waktu outlet.
  - Jam ditandai ramai jika order ≥ 130% rata-rata per jam, dan sepi jika ≤ 60%.
  - Peta keramaian hari × jam memakai rata-rata order per jam selama 4 minggu terakhir.
  - Tiap outlet menampilkan keramaian saat ini: meja terisi dari total meja, jumlah order aktif, dan status Ramai (≥ 75% meja terisi), Sepi (≤ 25%), atau Normal.
  - Filter "Semua jam / Jam ramai / Jam sepi" membatasi revenue, jumlah order, komposisi kanal, dan metode bayar ke order pada jam tersebut; stok dan keramaian saat ini tidak terpengaruh.
  - Staf tidak dapat melihat tampilan ini, termasuk lewat API langsung.
- **Traceability:** FR7.5–FR7.8, AC7.4–AC7.7

## Traceability ringkas

| Area PRD | User story |
|---|---|
| FR1 Business, outlet, staff | US-001–US-004 |
| FR2 Order intake (web chat, link outlet, QR meja) | US-008–US-015, US-034, US-042, US-062, US-063 |
| FR3 Cashflow | US-030–US-032, US-045, US-057–US-061 |
| FR4 Menu, stock, inventory | US-005–US-008, US-014, US-021, US-045, US-060 |
| FR5 Staff attendance (MVP) and scheduling (Phase 3) | US-046, US-053–US-055 |
| FR6 Web chat | US-009, US-015, US-023, US-025, US-036–US-037, US-042–US-045, US-052, US-066 |
| FR7 Admin web app | US-003, US-033–US-035, US-056 |
| FR8 Recommendations | US-028–US-029, US-052 |
| FR9 Reservations | US-022–US-027, US-043 |
| FR10 Order lifecycle | US-004, US-015–US-021, US-034, US-064 |
| FR11 Payments & tax | US-017–US-020, US-047, US-062, US-064 |
| FR12 Customer data & privacy | US-040–US-041 |
| FR13 AI agent di web chat (Phase 2: supervisor + worker) | US-042–US-044, US-066–US-069 |
| NFR1 Data residency | US-039 |
| NFR2 Multi-tenancy | US-038 |
| NFR3 Auditability | US-030, US-039 |
| NFR4 Reliability | US-036, US-050–US-051 |
| NFR5 Security | US-036, US-038 |
| NFR6 Scalability | US-036, US-038 |
| NFR7 Connectivity | US-035 |
| NFR8 Duplicate-safe processing | US-014, US-037, US-050 |
| Hosting dan antrean (Supabase, Railway, RabbitMQ) | US-049–US-051 |
| Phase 3 WhatsApp (opsional) | US-065 |

## Definition of Done umum

Sebuah user story selesai apabila:

1. Seluruh acceptance criteria story dan AC PRD yang dirujuk lulus pada test yang relevan.
2. Akses owner/staff, tenant, dan outlet diuji melalui UI serta API bila story menyentuh data sensitif.
3. Perubahan deterministik pada order, stock, payment, reservation, dan ledger memiliki audit trail.
4. Alur web chat yang relevan diuji di layar 360 px dan untuk aksi ganda (double tap, retry setelah koneksi putus) serta rate limit.
5. Tidak ada regresi terhadap alur order dari link outlet (`web_online`), QR meja (`web_table`), dan counter.
