# User Stories — SME Business Automation Platform

Dokumen ini menerjemahkan `PRD-SME-Automation-Platform.md` menjadi backlog user story. Acceptance criteria merujuk ke ID AC pada PRD; seluruh AC yang dirujuk wajib lulus sebelum story dianggap selesai.

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
  - Setiap outlet memiliki alamat, jam buka, zona waktu, nomor WhatsApp, katalog, tabel, QRIS, pengaturan reservasi, PB1, mode pembayaran dine-in, dan biaya delivery flat sendiri.
  - Harga, add-on, resep, dan owner's picks dapat digunakan bersama oleh seluruh outlet.
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
- **Traceability:** FR4.1, FR4.6, FR4.8, FR4.9, AC4.5–AC4.8

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

**Sebagai** pelanggan, **saya ingin** melihat pilihan Pesan, Rekomendasi, dan Reservasi dari chat outlet, **sehingga** saya dapat memilih kebutuhan saya dengan cepat.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Outlet dengan reservasi aktif menampilkan tepat tiga pilihan: `Pesan`, `Rekomendasi`, `Reservasi`.
  - Outlet tanpa reservasi hanya menampilkan `Pesan` dan `Rekomendasi`.
- **Traceability:** FR2.0, AC2.1

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
  - Staf hanya dapat menandai paid setelah mengecek transaksi di akun merchant QRIS, bukan berdasarkan screenshot saja.
  - Ledger dibuat saat payment ditandai paid dan menyimpan aktor serta waktu.
- **Traceability:** FR11.1–FR11.3, AC11.1–AC11.3

### US-018 — Menerima pembayaran cash dan mengelola shift kasir

**Sebagai** staf kasir, **saya ingin** menerima pembayaran cash dan membuka/menutup shift, **sehingga** kas outlet dapat direkonsiliasi.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Counter dan dine-in dapat memilih cash atau QRIS; online tidak menawarkan cash.
  - Pembayaran cash meminta nominal diterima dan menampilkan kembalian.
  - Cash hanya dapat diterima jika shift kasir terbuka; satu drawer hanya memiliki satu shift aktif.
  - End-of-shift menggunakan blind count, membandingkan cash aktual dengan ekspektasi, mencatat selisih dan penghitung, lalu mem-post shortage/surplus ke ledger.
- **Traceability:** FR11.4, FR11.6–FR11.8, AC11.4, AC11.6–AC11.8

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
  - Pembatalan/reschedule diizinkan sampai cancellation cutoff.
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
- **Traceability:** FR3.3, FR7.2, AC3.4, AC7.1

### US-033 — Menggunakan dashboard admin sesuai peran

**Sebagai** owner atau staf, **saya ingin** menggunakan web app yang menampilkan fungsi sesuai peran dan outlet, **sehingga** pekerjaan saya cepat dan data tetap terbatas.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Owner melihat sales, cashflow, dan stok per outlet serta gabungan.
  - Staff melihat order, open bill, reservasi, dan stok hanya untuk outlet yang ditugaskan.
  - Menu, resep, harga, expense, laporan, outlet, dan akun staf hanya tersedia bagi owner sesuai matriks akses.
- **Traceability:** FR1.4–FR1.5, FR7.1–FR7.2, AC1.5–AC1.6, AC7.1

### US-034 — Memasukkan order dari counter

**Sebagai** staf, **saya ingin** membuat order dine-in, takeaway, dan walk-in dari counter screen, **sehingga** pelanggan yang datang langsung tetap menggunakan proses order dan stok yang sama.

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
- **Traceability:** FR7.3, NFR7, AC7.2

## Epic H — WhatsApp, keamanan, dan ketahanan sistem

### US-036 — Memproses WhatsApp melalui API resmi dan queue

**Sebagai** owner, **saya ingin** pesan WhatsApp diproses melalui API resmi, queue, dan worker yang andal, **sehingga** pesan tidak hilang saat traffic tinggi atau terjadi kegagalan sementara.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Webhook memverifikasi request, mengidentifikasi outlet dari nomor penerima, memasukkan event ke RabbitMQ, lalu segera merespons sukses.
  - Pesan keluar dan sinkronisasi katalog juga melalui queue dan di-retry saat gagal/rate-limited.
  - Event yang masuk saat worker berhenti tidak hilang dan diproses saat worker kembali.
  - Signature webhook tidak valid ditolak dan tidak masuk queue.
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
- **Traceability:** NFR2, NFR5, ACN2, ACN6

### US-039 — Memenuhi data residency dan auditability

**Sebagai** owner dan pelanggan, **saya ingin** data disimpan di Indonesia dan perubahan penting dapat diaudit, **sehingga** platform memenuhi kebutuhan kepatuhan dan kepercayaan.

- **Fase/Prioritas:** MVP / P0
- **Acceptance criteria:**
  - Database, backup, object storage, dan payment screenshot berada di region Indonesia.
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

### US-044 — Menjawab rekomendasi, FAQ, dan upsell

**Sebagai** pelanggan, **saya ingin** bertanya secara bebas tentang menu dan rekomendasi, **sehingga** saya mendapat bantuan yang relevan dalam percakapan.

- **Fase/Prioritas:** P2 / P1
- **Acceptance criteria:**
  - Agent menggunakan data menu, stok, tag, dan penjualan outlet yang benar.
  - Rekomendasi bersifat advisory; item tidak masuk order tanpa konfirmasi pelanggan.
  - FAQ dapat dijawab tanpa mengubah data operasional.
  - Upsell tidak mengubah cart/order secara langsung.
- **Traceability:** FR8.4, FR6.3

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

### US-046 — Mengelola jadwal dan kehadiran staf

**Sebagai** owner, **saya ingin** mencatat shift dan attendance staf serta menerima saran jadwal, **sehingga** kebutuhan manpower dapat direncanakan.

- **Fase/Prioritas:** P3 / P1
- **Acceptance criteria:**
  - Sistem mencatat shift dan kehadiran.
  - Agent menyarankan jadwal berdasarkan pola demand historis.
  - Jadwal tetap memerlukan keputusan owner dan tidak mengubah penugasan tanpa persetujuan.
- **Traceability:** FR5.1–FR5.2

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
- **Traceability:** FR1.1, Scope, FR5/Phase 3, roadmap Phase 3

## Traceability ringkas

| Area PRD | User story |
|---|---|
| FR1 Business, outlet, staff | US-001–US-004 |
| FR2 Order intake & WhatsApp catalog | US-008–US-015, US-034, US-042 |
| FR3 Cashflow | US-030–US-032, US-045 |
| FR4 Menu, stock, inventory | US-005–US-008, US-014, US-021, US-045 |
| FR5 Manpower / staff Phase 3 | US-046 |
| FR6 WhatsApp bot | US-015, US-036–US-037, US-042–US-045 |
| FR7 Admin web app | US-003, US-033–US-035 |
| FR8 Recommendations | US-028–US-029, US-044 |
| FR9 Reservations | US-022–US-027, US-043 |
| FR10 Order lifecycle | US-004, US-015–US-021, US-034 |
| FR11 Payments & tax | US-017–US-020, US-047 |
| FR12 Membership & consent | US-040–US-041 |
| NFR1–NFR8 | US-030, US-036–US-039, US-014 |

## Definition of Done umum

Sebuah user story selesai apabila:

1. Seluruh acceptance criteria story dan AC PRD yang dirujuk lulus pada test yang relevan.
2. Akses owner/staff, tenant, dan outlet diuji melalui UI serta API bila story menyentuh data sensitif.
3. Perubahan deterministik pada order, stock, payment, reservation, dan ledger memiliki audit trail.
4. Alur WhatsApp yang relevan diuji untuk duplicate delivery, retry queue, dan jendela pesan 24 jam.
5. Tidak ada regresi terhadap alur order dari WhatsApp online, table QR, dan counter.
