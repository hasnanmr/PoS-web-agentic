// What the customer reads when something goes wrong (C13 and the red cards on C6, C10, C12).
// Rule (page 07, "Pesan ke pelanggan"): everyday, friendly Bahasa Indonesia that says what
// happened and what to do — never an error code, a path, a token, or a field name.
import { ApiError } from '../lib/api'

const COPY: Record<string, string> = {
  network_error: 'Sinyalnya lagi putus-putus. Kami coba kirim ulang; pesananmu tidak akan dobel.',
  too_many_requests: 'Kamu mengirim terlalu cepat nih. Tunggu sebentar, lalu coba lagi ya.',
  web_ordering_unavailable:
    'Untuk outlet ini, pesanan dilayani langsung di kasir ya. Menunya bisa kamu lihat dulu di sini.',
  price_changed: 'Harganya baru saja berubah. Cek lagi ringkasannya ya, totalnya sudah kami perbarui.',
  order_not_payable: 'Pesanan ini sudah tidak menunggu pembayaran.',
  order_not_cancellable: 'Pesanan ini sudah tidak bisa dibatalkan dari sini. Minta bantuan kakak staf ya.',
  reservations_unavailable: 'Outlet ini belum menerima reservasi lewat chat.',
  slot_unavailable: 'Yah, jam itu baru saja terisi. Pilih jam lain ya.',
  booking_limit_reached:
    'Nomor ini sudah punya 2 reservasi yang akan datang di outlet ini. Untuk tambah lagi, hubungi outlet ya.',
  change_window_closed:
    'Reservasi ini sudah terlalu dekat dengan waktunya, jadi tidak bisa diubah lewat chat. Hubungi outlet ya.',
  booking_not_changeable: 'Reservasi ini sudah tidak bisa diubah lewat chat.',
  booking_not_found: 'Reservasinya tidak ketemu. Cek lagi kode booking dan nomor HP-nya ya.',
  not_found: 'Datanya tidak ketemu. Mungkin sudah lewat atau link-nya sudah tidak berlaku.',
}

const FIELD: Record<string, string> = {
  name: 'Nama belum diisi.',
  phone: 'Nomor HP-nya belum benar. Contoh: 0812 3456 7890.',
  address: 'Alamat antar belum diisi.',
  cart: 'Keranjangnya terlalu banyak. Kurangi beberapa item dulu ya.',
}

/** Friendly text for an error; `fallback` when nothing specific fits. */
export function friendly(error: unknown, fallback = 'Maaf, ada yang tidak beres. Coba lagi sebentar ya.'): string {
  if (!(error instanceof ApiError)) return fallback
  if (error.code === 'party_too_large' && typeof error.details.max === 'number') {
    return `Maaf, maksimal ${error.details.max} orang per reservasi lewat chat.`
  }
  if (error.code === 'validation_failed') {
    const field = typeof error.details.field === 'string' ? error.details.field : ''
    return FIELD[field] ?? 'Ada isian yang belum pas. Cek lagi ya.'
  }
  return COPY[error.code] ?? fallback
}

/** True when retrying the same request (same keys) is the right thing to offer. */
export function isRetryable(error: unknown): boolean {
  return error instanceof ApiError && (error.code === 'network_error' || error.status >= 500 || error.code === 'conflict')
}
