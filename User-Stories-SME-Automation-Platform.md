# User Stories — SME Business Automation Platform

Dokumen ini menerjemahkan `PRD-SME-Automation-Platform.md` menjadi backlog user story (baseline PRD v0.14). Acceptance criteria merujuk ke ID AC pada PRD; seluruh AC yang dirujuk wajib lulus sebelum story dianggap selesai.

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
  - Setiap outlet memiliki alamat, jam buka, zona waktu, nomor WhatsApp, katalog, meja, cash drawer, QRIS, pengaturan reservasi, PB1, mode pembayaran dine-in, dan biaya delivery flat sendiri.
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
  - Setiap item menu memiliki foto.
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

### US-008 — Memulai tenant dengan sample menu dan sinkronisasi katalog

**Sebagai** owner baru, **saya ingin** menerima sample menu yang langsung tersinkron ke katalog WhatsApp, **sehingga** saya dapat mencoba alur produk sebelum memasukkan menu asli.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Tenant baru mendapat item, foto, harga outlet, dan add-on sample.
  - Sample menu dikirim ke katalog setiap outlet melalui mekanisme sinkronisasi yang sama dengan perubahan menu.
  - Owner dapat mengedit atau menghapus semua sample item.
  - Perubahan harga/ketersediaan mengantre, retry sampai berhasil, dan hanya memengaruhi katalog outlet terkait.
- **Traceability:** FR2.11, FR2.12, NFR4, AC2.12, AC2.13

## Epic C — Pemesanan melalui WhatsApp

### US-009 — Menampilkan menu utama WhatsApp

**Sebagai** pelanggan, **saya ingin** melihat semua pilihan layanan dari chat outlet, **sehingga** saya dapat memilih kebutuhan saya dengan cepat.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Menu utama berupa list message.
  - Outlet dengan reservasi aktif menampilkan tepat: `Pesan`, `Rekomendasi`, `Reservasi`, `Reservasi Saya`, `Data Saya`.
  - Outlet tanpa reservasi hanya menampilkan `Pesan`, `Rekomendasi`, dan `Data Saya`.
  - Mengetik "menu" kapan saja menampilkan menu utama lagi tanpa membuat apa pun dari alur yang belum selesai.
- **Traceability:** FR2.0, AC2.1, AC2.14

### US-010 — Menjelajah katalog dan membuat cart

**Sebagai** pelanggan, **saya ingin** menjelajah katalog outlet dan menambahkan produk ke cart, **sehingga** saya dapat membuat pesanan tanpa login ke aplikasi lain.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Katalog menampilkan item aktif dengan foto, deskripsi, dan harga outlet terkait.
  - Item sold out diberi tanda unavailable dan tidak dapat dipesan.
- **Traceability:** FR2.1, AC2.2

### US-011 — Memilih add-on dan mengonfirmasi pesanan

**Sebagai** pelanggan, **saya ingin** memilih add-on setelah mengirim cart dan memeriksa ringkasan, **sehingga** total pesanan saya jelas sebelum dibuat.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Semua grup required harus dipilih; grup optional dapat dilewati.
  - Ringkasan menampilkan item, kuantitas, add-on, subtotal, PB1, biaya delivery jika ada, dan total.
  - Order belum dibuat sebelum pelanggan menekan `Confirm`.
- **Traceability:** FR2.2, FR2.3, AC2.3–AC2.5

### US-012 — Memilih pickup atau delivery

**Sebagai** pelanggan online, **saya ingin** memilih pickup atau delivery, **sehingga** pesanan saya diproses sesuai cara pengambilan yang saya inginkan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Delivery mewajibkan alamat dan menambahkan biaya flat outlet sebagai baris terpisah.
  - Biaya delivery tidak masuk dasar perhitungan PB1 dan dicatat terpisah di ledger.
  - Pickup tidak meminta alamat dan tidak menambahkan biaya delivery.
- **Traceability:** FR2.6, AC2.7

### US-013 — Memesan dari table QR

**Sebagai** pelanggan dine-in, **saya ingin** memesan dengan memindai QR di meja, **sehingga** order otomatis terhubung ke outlet dan meja saya.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - QR membuka chat nomor WhatsApp outlet yang benar dengan table identifier.
  - Order diberi channel `whatsapp_table`, tipe dine-in, dan table yang benar.
  - Order mengikuti mode pembayaran dine-in outlet.
- **Traceability:** FR2.7, FR2.10, AC2.8

### US-014 — Membuat order secara konsisten dan aman terhadap stok

**Sebagai** owner, **saya ingin** seluruh kanal memakai fungsi pembuatan order yang sama, **sehingga** stok dan status order konsisten.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Channel yang disimpan adalah `whatsapp_online`, `whatsapp_table`, atau `counter`.
  - Pembuatan order memeriksa dan mengurangi seluruh bahan item dan add-on dalam satu transaksi database.
  - Jika stok tidak cukup saat konfirmasi, order tidak dibuat dan pelanggan dapat menghapus item atau memilih pengganti.
  - Dua konfirmasi bersamaan untuk porsi terakhir hanya menghasilkan satu order; stok tidak pernah negatif.
  - Sale belum masuk ledger sebelum pembayaran dikonfirmasi.
- **Traceability:** FR2.3, FR2.8, FR2.9, FR4.6, AC2.5, AC2.9, AC2.10

### US-015 — Menerima konfirmasi dan notifikasi order

**Sebagai** pelanggan, **saya ingin** menerima konfirmasi dan pembaruan status order di WhatsApp, **sehingga** saya mengetahui progres pesanan saya.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Setelah order berhasil dibuat, pelanggan menerima satu pesan berisi nomor order, item, dan total.
  - Pelanggan menerima pembaruan saat order confirmed, ready, out for delivery, atau cancelled.
  - Pesan yang dikirim di luar jendela 24 jam memakai template Meta yang telah disetujui.
- **Traceability:** FR2.5, FR6.2, FR10.3, AC2.6, AC6.1, AC10.4

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

**Sebagai** pelanggan, **saya ingin** menerima QRIS dan total pembayaran yang tepat, **sehingga** saya dapat membayar pesanan online atau dine-in pay-first.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Bot mengirim gambar QRIS outlet, total tepat termasuk PB1, dan meminta screenshot.
  - Screenshot dilampirkan ke order dan membuat order menunggu pemeriksaan.
  - Setelah screenshot masuk, payment status menjadi `proof_submitted`.
  - Staf hanya dapat menandai paid setelah mengecek transaksi di akun merchant QRIS, bukan berdasarkan screenshot saja.
  - Ledger dibuat saat payment ditandai paid dan menyimpan aktor serta waktu.
  - Jika dana tidak ditemukan, staf menolak bukti bayar dengan alasan wajib; order langsung dibatalkan, bahan dikembalikan dengan reversal movement, tidak ada ledger entry, dan pelanggan diberi tahu untuk menghubungi outlet.
- **Traceability:** FR10.1, FR11.1–FR11.3, FR11.10, AC11.1–AC11.3, AC11.9

### US-018 — Menerima pembayaran cash dan mengelola shift kasir

**Sebagai** staf kasir, **saya ingin** menerima pembayaran cash dan membuka/menutup shift, **sehingga** kas outlet dapat direkonsiliasi.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Counter dan dine-in dapat memilih cash atau QRIS; online tidak menawarkan cash.
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
  - Outlet dapat diatur ke mode `pay first` atau `open bill`; pelanggan tidak memilih mode.
  - Meja/guest hanya boleh memiliki satu open bill.
  - Order berikutnya dari meja atau counter bergabung ke bill yang sama.
  - Bill menampilkan item, total berjalan, dan durasi terbuka.
  - Penutupan bill hanya menerima satu pembayaran penuh; semua order menjadi completed dan sale masuk ledger.
  - Jika mode outlet berubah, order baru mengikuti mode baru, sedangkan order yang sudah dibuat mempertahankan flow asalnya.
- **Traceability:** FR10.6–FR10.8, AC10.7–AC10.10

### US-021 — Membatalkan dan membalik order

**Sebagai** owner atau staf berwenang, **saya ingin** membatalkan atau membalik order sesuai statusnya, **sehingga** stok dan keuangan tetap dapat ditelusuri.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Unpaid pay-first order dibatalkan otomatis setelah batas waktu outlet jika belum ada screenshot; timer berhenti setelah screenshot dikirim.
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

### US-023 — Memesan meja melalui WhatsApp

**Sebagai** pelanggan, **saya ingin** memesan meja dengan memilih jumlah orang, tanggal, dan waktu melalui WhatsApp, **sehingga** saya tidak perlu menelepon outlet.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Alur meminta party size → tanggal → waktu tersedia → konfirmasi.
  - Sistem hanya menawarkan waktu yang sesuai aturan outlet dan meja yang tersedia.
  - Sistem menetapkan meja terkecil yang cukup untuk party.
  - Party di atas batas maksimum ditolak dengan informasi batas tersebut.
- **Traceability:** FR9.2, AC9.1–AC9.3

### US-024 — Mencegah double booking

**Sebagai** owner, **saya ingin** sistem mencegah dua reservasi yang waktunya tumpang tindih, **sehingga** pelanggan tidak mendapat meja yang sama.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Pencegahan diterapkan di level database.
  - Request bersamaan atau write yang melewati validasi aplikasi tetap menolak reservasi kedua.
- **Traceability:** FR9.3, AC9.4

### US-025 — Menerima konfirmasi, reminder, pembatalan, dan reschedule

**Sebagai** pelanggan, **saya ingin** menerima konfirmasi/reminder dan mengelola reservasi via WhatsApp, **sehingga** saya dapat mengatur rencana kunjungan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Konfirmasi dikirim segera dengan outlet, tanggal, waktu, dan party size.
  - Reminder dikirim sesuai konfigurasi outlet; pesan di luar jendela 24 jam memakai template Meta.
  - Pembatalan/reschedule dilakukan dari `Reservasi Saya` di menu utama dan diizinkan sampai cancellation cutoff.
  - Setelah cutoff, bot menolak perubahan dan mengarahkan pelanggan menghubungi outlet.
- **Traceability:** FR9.4–FR9.5, AC9.5–AC9.6

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

**Sebagai** pelanggan, **saya ingin** menambahkan item dari pesan rekomendasi ke cart, **sehingga** saya dapat memesan tanpa mencari ulang di katalog.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Product message berasal dari katalog outlet.
  - Item dapat ditambahkan ke cart dan melanjutkan alur add-on, ringkasan, dan konfirmasi normal.
- **Traceability:** FR8.3, AC8.3

### US-052 — Meminta rekomendasi dengan bantuan AI

**Sebagai** pelanggan, **saya ingin** menceritakan selera saya di menu Rekomendasi (misalnya "yang manis buat berdua"), **sehingga** saya mendapat saran menu yang cocok tanpa harus menelusuri seluruh katalog.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - AI hanya berjalan di alur Rekomendasi; alur Pesan, Reservasi, dan lainnya tetap berbasis tombol tanpa AI.
  - Saran hanya berisi item aktif yang tersedia di outlet tersebut dengan harga outlet; owner's picks diutamakan bila sesuai permintaan.
  - AI hanya membaca data (menu, tag, ketersediaan, penjualan 30 hari) dan tidak membuat cart, order, atau perubahan stok.
  - Item yang dipilih pelanggan masuk ke alur add-on, ringkasan, dan Confirm yang normal (US-029, US-011).
  - Bot langsung membalas "Sebentar ya, lagi cariin rekomendasi…" sebelum AI selesai, supaya chat tidak terasa diam selama proses yang bisa sampai 30 detik.
  - Jika AI gagal atau lebih dari 30 detik, bot mengirim owner's picks dan best sellers (US-028).
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
  - Pengeluaran langsung ini berada di tab **Pengeluaran**; pembelian ke supplier lewat PO ada di tab **Purchase Order** (US-057–US-061).
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

### US-061 — Tab Purchase Order dan pengingat pembayaran di dashboard

**Sebagai** owner, **saya ingin** melihat seluruh PO di tab tersendiri dan semua pembayaran supplier yang perlu dilakukan di dashboard, **sehingga** saya tahu apa yang harus dibayar dan barang apa yang masih ditunggu.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Layar Pengeluaran owner memiliki tab **Pengeluaran** (pengeluaran langsung) dan **Purchase Order**; staf mendapat layar Purchase Order untuk outletnya (daftar PO, buka PO, cross-check barang) tanpa pembayaran dan hutang.
  - Tab Purchase Order memiliki filter terbuka (menunggu barang), ada selisih, menunggu pembayaran, overdue, dan ditutup, serta detail PO berisi baris item, riwayat pengecekan barang, dan riwayat pembayaran beserta pencatatnya.
  - Dashboard owner memiliki kartu **Pembayaran supplier**: PO tempo yang sudah ditutup dan belum lunas (overdue dulu, lalu jatuh tempo terdekat) dan PO bayar di muka yang terbuka dan belum dibayar, masing-masing dengan tombol catat pembayaran.
  - Dashboard owner memiliki daftar **PO ada selisih** (supplier, outlet, baris yang kurang, sejak kapan) dengan tombol **Tutup dengan catatan** yang hanya tersedia untuk owner.
  - Kartu itu dan laporan cashflow menampilkan total hutang supplier (jumlah overdue dan jatuh tempo 7 hari) serta barang yang sudah dibayar tetapi belum diterima, terpisah dari kas keluar.
  - Dashboard owner memiliki laporan **Ringkasan PO** per outlet dan periode: jumlah dan nilai PO yang dibuka vs ditutup, barang belum datang / sebagian / sudah datang, dan pembayaran belum dibayar / sebagian / lunas, dipisah bayar mundur dan bayar di muka; setiap angka membuka daftar PO yang sesuai.
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
  - Order menggunakan fungsi yang sama dengan WhatsApp, termasuk validasi stok dan lifecycle.
- **Traceability:** FR7.4, FR2.8, AC7.3, AC2.9

### US-035 — Menggunakan admin app di desktop dan mobile

**Sebagai** staf, **saya ingin** menyelesaikan pekerjaan operasional dari browser mobile maupun desktop, **sehingga** saya tetap dapat bekerja saat berada di area outlet.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Counter, order board, open bills, stok, dan reservasi dapat digunakan pada viewport 360 px.
  - Tidak ada tindakan utama yang memerlukan horizontal scrolling.
  - MVP membutuhkan koneksi internet dan tidak menyediakan offline mode.
- **Traceability:** FR7.3, NFR7, AC7.2, ACN9

## Epic H — WhatsApp, keamanan, dan ketahanan sistem

### US-036 — Memproses WhatsApp melalui API resmi dan queue

**Sebagai** owner, **saya ingin** pesan WhatsApp diproses melalui API resmi, queue, dan worker yang andal, **sehingga** pesan tidak hilang saat traffic tinggi atau terjadi kegagalan sementara.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Webhook memverifikasi request, mengidentifikasi outlet dari nomor penerima, memasukkan event ke RabbitMQ, lalu segera merespons sukses.
  - Pesan keluar dan sinkronisasi katalog juga melalui queue dan di-retry saat gagal/rate-limited.
  - Event yang masuk saat worker berhenti tidak hilang dan diproses saat worker kembali.
  - Signature webhook tidak valid ditolak dan tidak masuk queue.
  - Topologi antrean, retry bertingkat, dan dead-letter mengikuti US-050.
- **Traceability:** FR6.1, FR6.4, NFR4, ACN4–ACN5

### US-037 — Menjamin pemrosesan pesan idempotent

**Sebagai** owner, **saya ingin** setiap pesan WhatsApp diproses maksimal sekali, **sehingga** satu tap tidak menggandakan order, pengurangan stok, atau ledger.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Message ID Meta disimpan sebagai processed message.
  - Redelivery webhook atau RabbitMQ diabaikan setelah message ID pernah berhasil diproses.
  - Confirm yang terkirim dua kali menghasilkan tepat satu order, satu stock deduction, dan satu set ledger entry.
- **Traceability:** NFR8, ACN7

### US-038 — Mengisolasi tenant, outlet, dan API

**Sebagai** owner, **saya ingin** data bisnis dan outlet terisolasi di level database serta endpoint terlindungi token, **sehingga** data tidak bocor antar tenant atau antar staf.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - PostgreSQL RLS mencegah tenant 1 membaca baris tenant 2, termasuk query tanpa tenant filter.
  - Akses staf ke outlet ditegakkan oleh database, bukan hanya filter frontend/backend.
  - Endpoint FastAPI selain webhook menolak token hilang, invalid, atau expired.
  - Record operasional membawa tenant_id dan outlet_id.
  - Service API dan worker bersifat stateless, containerized, memakai pooled PostgreSQL connections, dan dapat diskalakan tanpa redesign schema/arsitektur.
  - Login dan token dikelola Supabase Auth; token membawa klaim `tenant_id` dan `app_role`; RLS membaca tenant dan pengguna dari sesi database yang diisi backend setelah token diverifikasi, akses outlet dan status aktif dicek langsung ke database, dan backend tidak memakai service role untuk membaca atau menulis data tenant.
  - Token ditandatangani dengan kunci asimetris dan diverifikasi lewat public key; token dengan kunci atau algoritma yang salah ditolak.
- **Traceability:** NFR2, NFR5, NFR6, ACN2, ACN6, ACN8

### US-039 — Memenuhi data residency dan auditability

**Sebagai** owner dan pelanggan, **saya ingin** data disimpan di Indonesia dan perubahan penting dapat diaudit, **sehingga** platform memenuhi kebutuhan kepatuhan dan kepercayaan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Auth, database, backup, object storage, dan payment screenshot berada di Supabase. Supabase tidak punya region Indonesia, sehingga region terdekat (Singapura) dipakai.
  - Data nyata hanya boleh disimpan setelah dasar transfer lintas negara yang ditinjau legal dicatat (T-108) dan privacy notice menyebutkan lokasi penyimpanan; sebelum itu semua environment hanya berisi data dummy.
  - Ledger dan stock movement bersifat append-only.
  - Setiap write pada ledger/stock mencatat actor dan timestamp.
  - Agent tidak memiliki akses tulis langsung ke tabel ledger atau stock.
- **Traceability:** NFR1, NFR3, ACN1, ACN3

## Epic I — Membership dan consent PDP

### US-040 — Meminta consent membership

**Sebagai** pelanggan, **saya ingin** mengetahui dan menyetujui penggunaan data saya, **sehingga** saya dapat berinteraksi dengan bisnis secara transparan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Pesan pertama ke bisnis meminta consent dan menampilkan link privacy notice.
  - Consent berlaku lintas outlet dalam tenant yang sama dan tidak diminta ulang.
  - Pelanggan tetap dapat order atau reservasi jika menolak membership.
- **Traceability:** FR12.1–FR12.2, FR12.5, AC12.1, AC12.4

### US-041 — Mengakhiri membership dan menganonimkan data

**Sebagai** pelanggan, **saya ingin** mengakhiri membership dari WhatsApp, **sehingga** data pribadi saya tidak lagi disimpan saat consent dicabut.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Membership dapat diakhiri dari `Data Saya` di menu utama.
  - Nama, nomor WhatsApp, alamat, dan data personal lain dihapus atau dianonimkan.
  - Order, total ledger, dan riwayat keuangan tetap utuh dengan customer anonim.
  - Data personal hanya disimpan pada customer tables, bukan ledger atau stock movement.
  - Pelanggan yang menolak consent dianonimkan setelah order selesai/dibatalkan atau booking selesai.
- **Traceability:** FR12.3–FR12.5, AC12.2–AC12.4

## Epic J — Agent layer (Phase 2)

### US-042 — Memproses order free-text dengan konfirmasi

**Sebagai** pelanggan, **saya ingin** menulis order dengan bahasa natural, **sehingga** saya tidak harus mengikuti format menu yang kaku.

- **Fase/Prioritas:** P2 / P0 untuk Phase 2
- **Acceptance criteria:**
  - Agent mengekstrak item, add-on, kuantitas, dan total termasuk PB1.
  - Agent menampilkan ringkasan terstruktur dan menunggu konfirmasi eksplisit.
  - Sebelum konfirmasi tidak ada order dan tidak ada pengurangan stok.
  - Setelah konfirmasi, agent memanggil fungsi pembuatan order deterministik yang sama dengan staff.
- **Traceability:** FR2.4, FR6.3, AC6.2, AC6.4

### US-043 — Memproses reservasi free-text dengan konfirmasi

**Sebagai** pelanggan, **saya ingin** meminta reservasi dengan bahasa natural, **sehingga** saya dapat memesan meja dengan lebih mudah.

- **Fase/Prioritas:** P2 / P0 untuk Phase 2
- **Acceptance criteria:**
  - Agent mengekstrak jumlah orang, tanggal, waktu, dan konteks outlet.
  - Agent mengonfirmasi detail kepada pelanggan sebelum membuat booking.
  - Booking dibuat melalui fungsi deterministik yang sama dengan alur terstruktur dan tetap tunduk pada aturan kapasitas/ketersediaan.
- **Traceability:** FR9.9, FR6.3, AC6.4

### US-044 — Menjawab FAQ dan upsell

**Sebagai** pelanggan, **saya ingin** bertanya secara bebas tentang menu, jam buka, dan info outlet lainnya, **sehingga** saya mendapat bantuan yang relevan dalam percakapan.

- **Fase/Prioritas:** P2 / P1
- **Acceptance criteria:**
  - Agent menggunakan data menu, stok, tag, dan penjualan outlet yang benar.
  - Rekomendasi percakapan sudah tersedia di MVP (US-052); story ini memperluas agent ke FAQ dan upsell di luar alur Rekomendasi.
  - FAQ dapat dijawab tanpa mengubah data operasional.
  - Upsell tidak mengubah cart/order secara langsung.
- **Traceability:** FR6.3

### US-045 — Mendapatkan rekomendasi restock dan anomali cashflow

**Sebagai** owner, **saya ingin** menerima saran restock, timing, dan pola cashflow yang tidak biasa, **sehingga** saya dapat mengambil keputusan lebih cepat.

- **Fase/Prioritas:** P2 / P1
- **Acceptance criteria:**
  - Saran menggunakan histori sales velocity dan data cashflow.
  - Saran hanya advisory dan menampilkan dasar/reasoning yang dapat ditinjau owner.
  - Agent tidak memiliki tool untuk mengubah stok, membuat stock movement, atau membuat purchase order.
  - Restock hanya terjadi setelah owner mencatatnya melalui alur deterministik.
- **Traceability:** FR3.4, FR4.4, AC6.3–AC6.4

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

**Sebagai** owner, **saya ingin** menggunakan payment gateway dynamic QRIS, **sehingga** pembayaran dapat dikonfirmasi tanpa pemeriksaan manual screenshot.

- **Fase/Prioritas:** P3 / P1
- **Acceptance criteria:**
  - Gateway menghasilkan QRIS dinamis dengan nominal order.
  - Payment confirmation diterima otomatis dan hanya satu kali untuk setiap transaksi.
  - Setelah confirmed, alur ledger dan order lifecycle yang sudah ada tetap digunakan.
- **Traceability:** FR11.9

### US-048 — Mendukung dropshipper dan marketplace

**Sebagai** dropshipper, **saya ingin** menghubungkan order WhatsApp dengan marketplace, **sehingga** penjualan dan stok dapat dikelola dari satu platform.

- **Fase/Prioritas:** P3 / P2
- **Acceptance criteria:**
  - Tenant dapat menggunakan tipe bisnis dropshipper.
  - Sistem menyediakan integrasi yang direncanakan untuk Shopee, Tokopedia, dan TikTok Shop.
  - Order marketplace memakai prinsip auditability, tenant isolation, dan duplicate-safe processing yang sama.
- **Traceability:** FR1.1, Scope item 15, §10 Phase 3

## Epic L — Platform, hosting, dan antrean (Supabase, Railway, RabbitMQ)

### US-049 — Menjalankan environment demo dan pilot di Supabase dan Railway

**Sebagai** tim produk, **saya ingin** menjalankan aplikasi di Supabase dan Railway, **sehingga** demo dapat diperlihatkan ke calon merchant dengan biaya rendah dan jalur yang jelas menuju pilot.

- **Fase/Prioritas:** MVP (demo dan pilot) / P0
- **Acceptance criteria:**
  - Auth, PostgreSQL, dan Storage memakai Supabase; API, worker WhatsApp, dan RabbitMQ berjalan di Railway; admin app dapat di-host terpisah (Cloudflare Pages atau Vercel).
  - Environment demo, staging, dan produksi terpisah (project, secret, dan nomor WhatsApp).
  - Demo hanya memakai data dummy, berjalan di Supabase Free dan Railway Hobby, dan pemakaian dipantau dengan alert.
  - Project Supabase Free tidak ter-pause saat demo karena ada keep-alive.
  - Dasar transfer lintas negara (karena Supabase dan Railway berada di Singapura) terdokumentasi sebelum data nyata masuk.
  - Sebelum pilot dengan merchant nyata, checklist promosi lulus: Supabase Pro dengan backup, volume untuk RabbitMQ, API dan worker dipisah, dan keputusan region terpenuhi.
- **Traceability:** NFR1, NFR4, NFR6. Keputusan hosting baru, perlu ditambahkan ke PRD.

### US-050 — Antrean pesan dengan retry bertingkat dan dead-letter

**Sebagai** owner, **saya ingin** pesan yang gagal diulang otomatis dan tetap terlihat jika terus gagal, **sehingga** tidak ada pesan pelanggan atau notifikasi yang hilang diam-diam.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Antrean terpisah tersedia untuk inbound WhatsApp, outbound WhatsApp, sinkronisasi katalog, dan job terjadwal; semua durable dan pesan bersifat persisten.
  - Kegagalan sementara (timeout, HTTP 429, 5xx, deadlock database) diulang dengan jeda bertingkat 5 detik, 30 detik, lalu 2 menit, dengan batas percobaan per antrean.
  - Kegagalan permanen (HTTP 4xx selain 429, payload tidak valid) langsung masuk dead-letter dengan alasan kegagalan.
  - Pesan dead-letter dapat dilihat, diperiksa, dan diputar ulang atau dibuang oleh admin berwenang; tindakan itu tercatat.
  - Ack dikirim setelah transaksi database commit; redelivery tidak menghasilkan order, stock movement, atau ledger ganda (US-037).
  - Satu percakapan diproses berurutan sehingga cart selalu diproses sebelum konfirmasi.
  - Alert muncul jika ada pesan di dead-letter atau antrean inbound menumpuk.
- **Traceability:** NFR4, NFR8, ACN4–ACN5, ACN7

### US-051 — Job terjadwal yang andal

**Sebagai** owner, **saya ingin** pembatalan order unpaid, reminder reservasi, pelepasan no-show, dan anonimisasi berjalan tepat waktu walau layanan restart, **sehingga** stok, meja, dan data pelanggan tidak tertahan karena timer hilang.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Job disimpan di database dan dipublikasikan ke RabbitMQ saat jatuh tempo; restart broker atau worker tidak menghilangkan job.
  - Handler idempotent dan memeriksa status terkini sebelum bertindak (misalnya order sudah punya screenshot, atau booking sudah seated).
  - Job yang terlambat karena downtime tetap dijalankan segera setelah sistem pulih.
  - Job yang dibatalkan (misalnya screenshot masuk) tidak dijalankan.
  - Berlaku untuk unpaid timeout (US-021), reminder reservasi (US-025), no-show 15 menit (US-027), dan anonimisasi pelanggan yang menolak membership (US-040, US-041).
- **Traceability:** FR10.4, FR9.4, FR9.7, FR12.5, NFR4

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
  - Sebelum clock in pertama, staf melihat pemberitahuan bahwa selfie disimpan 30 hari dan hanya dilihat owner dan dirinya sendiri.
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
  - Owner melihat daftar tablet per outlet beserta aktivitas terakhirnya dan dapat mencabut tablet kapan saja; tablet yang dicabut langsung ditolak dan harus di-pairing ulang dengan kode baru.
  - Satu outlet boleh punya lebih dari satu tablet.
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
| FR2 Order intake & WhatsApp catalog | US-008–US-015, US-034, US-042 |
| FR3 Cashflow | US-030–US-032, US-045, US-057–US-061 |
| FR4 Menu, stock, inventory | US-005–US-008, US-014, US-021, US-045, US-060 |
| FR5 Staff attendance (MVP) and scheduling (Phase 3) | US-046, US-053–US-055 |
| FR6 WhatsApp bot | US-015, US-036–US-037, US-042–US-045, US-052 |
| FR7 Admin web app | US-003, US-033–US-035, US-056 |
| FR8 Recommendations | US-028–US-029, US-052 |
| FR9 Reservations | US-022–US-027, US-043 |
| FR10 Order lifecycle | US-004, US-015–US-021, US-034 |
| FR11 Payments & tax | US-017–US-020, US-047 |
| FR12 Membership & consent | US-040–US-041 |
| NFR1 Data residency | US-039 |
| NFR2 Multi-tenancy | US-038 |
| NFR3 Auditability | US-030, US-039 |
| NFR4 Reliability | US-008, US-036 |
| NFR5 Security | US-038 |
| NFR6 Scalability | US-038 |
| NFR7 Connectivity | US-035 |
| NFR8 Duplicate-safe processing | US-014, US-037, US-050 |
| Hosting dan topologi antrean (Supabase, Railway, RabbitMQ) | US-049–US-051 |

## Definition of Done umum

Sebuah user story selesai apabila:

1. Seluruh acceptance criteria story dan AC PRD yang dirujuk lulus pada test yang relevan.
2. Akses owner/staff, tenant, dan outlet diuji melalui UI serta API bila story menyentuh data sensitif.
3. Perubahan deterministik pada order, stock, payment, reservation, dan ledger memiliki audit trail.
4. Alur WhatsApp yang relevan diuji untuk duplicate delivery, retry queue, dan jendela pesan 24 jam.
5. Tidak ada regresi terhadap alur order dari WhatsApp online, table QR, dan counter.
