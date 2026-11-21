/**
 * REST client for the FastAPI backend (docs/architecture/api-boundaries.md §4).
 * Sends the Supabase access token; errors arrive as {"error": {code, message, details}}.
 */

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

export type TokenSource = () => Promise<string | null>

export interface Api {
  get<T>(path: string, headers?: Record<string, string>): Promise<T>
  post<T>(path: string, body?: unknown, headers?: Record<string, string>): Promise<T>
  put<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T>
  patch<T>(path: string, body: unknown): Promise<T>
  del<T = void>(path: string): Promise<T>
  /** Raw file download (e.g. O10 "Ekspor CSV", the outlet's QRIS image). */
  blob(path: string, accept?: string, headers?: Record<string, string>): Promise<Blob>
  /** Raw file upload as the request body (O3 QRIS image). */
  upload<T>(path: string, file: Blob, contentType: string): Promise<T>
}

export function createApi(baseUrl: string, token: TokenSource): Api {
  const root = baseUrl.replace(/\/+$/, '') + '/api/v1'

  async function request<T>(method: string, path: string, body?: unknown, extra?: Record<string, string>,
    asBlob = false): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json', ...extra }
    const access = await token()
    if (access) headers.Authorization = `Bearer ${access}`
    const raw = body instanceof Blob
    if (body !== undefined && !raw) headers['Content-Type'] = 'application/json'
    let res: Response
    try {
      res = await fetch(root + path, {
        method,
        headers,
        body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
      })
    } catch {
      throw new ApiError(0, 'network_error', 'Tidak bisa terhubung ke server')
    }
    if (res.status === 204) return undefined as T
    if (asBlob && res.ok) return (await res.blob()) as T
    const data: unknown = await res.json().catch(() => null)
    if (!res.ok) {
      const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | null)
        ?.error
      throw new ApiError(res.status, err?.code ?? 'http_error', err?.message ?? res.statusText, err?.details)
    }
    return data as T
  }

  return {
    get: (path, headers) => request('GET', path, undefined, headers),
    post: (path, body, headers) => request('POST', path, body ?? {}, headers),
    put: (path, body, headers) => request('PUT', path, body, headers),
    patch: (path, body) => request('PATCH', path, body),
    del: (path) => request('DELETE', path),
    blob: (path, accept = 'text/csv', headers) =>
      request<Blob>('GET', path, undefined, { ...headers, Accept: accept }, true),
    upload: (path, file, contentType) => request('PUT', path, file, { 'Content-Type': contentType }),
  }
}

/** Bahasa Indonesia copy for stable API error codes (the API sends English messages). */
const ERROR_COPY: Record<string, string> = {
  network_error: 'Tidak bisa terhubung ke server. Periksa koneksi lalu coba lagi.',
  unauthenticated: 'Sesi berakhir. Silakan masuk lagi.',
  token_expired: 'Sesi berakhir. Silakan masuk lagi.',
  account_inactive: 'Akun dinonaktifkan',
  account_not_invited: 'Email belum diundang',
  account_unknown: 'Akun tidak ditemukan untuk bisnis ini.',
  forbidden: 'Hanya owner yang bisa melakukan ini.',
  not_found: 'Data tidak ditemukan.',
  validation_failed: 'Periksa kembali isian yang ditandai.',
  conflict: 'Data bentrok dengan data lain.',
  email_taken: 'Email ini sudah punya akun.',
  whatsapp_phone_taken: 'Nomor WhatsApp sudah dipakai outlet lain.',
  drawer_name_taken: 'Nama drawer sudah dipakai di outlet ini.',
  shift_open: 'Tutup shift yang masih berjalan sebelum menghapus drawer ini.',
  last_drawer: 'Outlet harus punya minimal satu drawer.',
  invitation_accepted: 'Staf ini sudah masuk; undangan tidak perlu dikirim ulang.',
  invite_failed: 'Email undangan gagal dikirim. Coba lagi.',
  auth_admin_not_configured: 'Undangan email belum dikonfigurasi di server.',
  already_onboarded: 'Akun ini sudah punya bisnis.',
  insufficient_stock: 'Stok tidak cukup; stok tidak boleh minus.',
  stock_item_name_taken: 'Nama bahan sudah dipakai.',
  stock_item_unit_locked: 'Satuan dasar tidak bisa diubah karena bahan ini sudah punya stok, resep, atau PO.',
  stock_item_in_recipe: 'Bahan ini masih dipakai di resep. Lepas dulu dari resep, lalu hapus.',
  item_sold_out: 'Item habis.',
  photo_required: 'Tambahkan foto dulu sebelum mengaktifkan item ini.',
  storage_not_configured: 'Penyimpanan foto belum dikonfigurasi di server.',
  storage_failed: 'Foto gagal disimpan. Coba lagi.',
  item_unavailable: 'Item tidak tersedia di outlet ini.',
  addon_required: 'Pilih add-on yang wajib.',
  addon_invalid: 'Pilihan add-on tidak valid.',
  shift_not_open: 'Buka shift kasir dulu untuk menerima cash.',
  shift_already_open: 'Drawer ini sudah punya shift aktif.',
  cash_insufficient: 'Uang diterima kurang dari total.',
  invalid_transition: 'Status order sudah berubah. Muat ulang.',
  reason_required: 'Alasan wajib diisi — reversal tanpa alasan ditolak.',
  bill_not_open: 'Bill sudah ditutup atau dibatalkan.',
  bill_empty: 'Bill belum punya order.',
  bill_not_empty: 'Bill masih punya order; cancel order-nya dulu sebelum membatalkan bill.',
  bills_open: 'Tutup atau batalkan semua open bill dulu sebelum mengubah PB1.',
  idempotency_key_reused: 'Permintaan ini sudah dikirim dengan isi berbeda. Muat ulang lalu coba lagi.',
  payment_mode_pay_first: 'Outlet ini memakai mode pay first.',
  addon_group_in_use: 'Opsi grup ini sudah dipakai di order; ubah opsinya saja.',
  proof_not_pending: 'Bukti bayar ini sudah direview atau order tidak lagi menunggu bayar. Muat ulang.',
  shift_closed: 'Shift ini sudah ditutup.',
  already_reversed: 'Entry ini sudah pernah di-reversal.',
  not_reversible: 'Hanya pengeluaran yang bisa di-reversal di sini.',
  supplier_exists: 'Supplier dengan nama ini sudah ada.',
  over_receipt: 'Jumlah diterima melebihi qty PO.',
  overpayment: 'Nominal melebihi sisa yang harus dibayar.',
  already_paid: 'PO ini sudah lunas.',
  po_cancelled: 'PO ini sudah dibatalkan.',
  not_cancellable: 'PO yang sudah dibayar, sudah ada barang diterima, atau sudah ditutup tidak bisa dibatalkan.',
  payment_required: 'PO bayar di muka harus dibayar dulu sebelum ditutup.',
  difference_found: 'Qty barang belum sesuai PO. Hanya owner yang bisa menutupnya dengan catatan.',
  goods_not_received: 'Barang belum diterima semua.',
  no_difference: 'PO ini tidak ada selisih; tutup lewat cek barang.',
  paid_above_received: 'Sudah dibayar lebih dari nilai barang yang diterima; PO tidak bisa ditutup dengan catatan.',
  owner_only: 'Hanya owner yang bisa melakukan ini.',
  table_name_taken: 'Nama meja sudah dipakai di outlet ini.',
  table_in_use: 'Meja masih punya open bill atau reservasi mendatang.',
  table_has_reservations: 'Ada reservasi mendatang yang lebih besar dari kapasitas baru.',
  no_table_available: 'Tidak ada meja kosong yang cukup untuk jumlah orang di jam itu.',
  hold_expired: 'Hold 15 menit sudah lewat; booking otomatis no-show.',
  too_early: 'Belum lewat jam booking; no-show belum bisa ditandai.',
  table_qr_invalid: 'QR ini sudah tidak berlaku. Minta QR baru ke staf.',
  web_ordering_unavailable: 'Pesan dari HP belum tersedia di outlet ini. Pesan & bayar di kasir.',
  price_changed: 'Harga berubah. Cek lagi total pesananmu.',
  order_not_payable: 'Pesanan ini sudah tidak menunggu pembayaran.',
  order_not_cancellable: 'Pesanan sudah dibayar; minta bantuan staf untuk membatalkan.',
  too_many_requests: 'Terlalu banyak permintaan. Tunggu sebentar lalu coba lagi.',
  admin_app_url_not_configured: 'Alamat aplikasi (ADMIN_APP_URL) belum diatur di server.',
  slug_taken: 'Link ini sudah dipakai outlet lain. Pilih slug lain.',
  slug_invalid: 'Slug hanya boleh huruf kecil, angka, dan tanda hubung (3–40 karakter, tanpa "--").',
  tablet_already_paired: 'Outlet ini sudah punya tablet absensi. Lupakan perangkat lama dulu untuk pairing tablet baru.',
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'validation_failed' && typeof error.details.max_rows === 'number') {
      return `Terlalu banyak data (maks ${error.details.max_rows.toLocaleString('id-ID')} baris). Persempit rentang tanggal.`
    }
    if (error.code === 'validation_failed' && error.details.field === 'pb1_rate_bps') {
      return 'Isi tarif PB1 saat PB1 aktif.'
    }
    if (error.code === 'validation_failed' && error.details.field === 'drawer_id') {
      return 'Ada lebih dari satu shift terbuka. Pilih drawer dulu.'
    }
    if (error.code === 'validation_failed' && error.details.field === 'business_date') {
      return 'Tanggal pengeluaran tidak boleh di masa depan.'
    }
    if (error.code === 'validation_failed' && error.details.field === 'merchant_account_checked') {
      return 'Centang dulu: transaksi sudah ditemukan di akun merchant QRIS.'
    }
    if (error.code === 'validation_failed' && typeof error.details.max_party_size === 'number') {
      return `Maksimal ${error.details.max_party_size} orang per reservasi.`
    }
    if (error.code === 'validation_failed' && typeof error.details.capacity === 'number') {
      return `Meja ini hanya untuk ${error.details.capacity} orang.`
    }
    if (error.code === 'validation_failed' && typeof error.details.bookable_until === 'string') {
      return `Di luar jam booking (${String(error.details.bookable_from)}–${error.details.bookable_until}).`
    }
    if (error.code === 'validation_failed' && typeof error.details.booking_window_days === 'number') {
      return `Hanya bisa booking sampai ${error.details.booking_window_days} hari ke depan.`
    }
    if (error.code === 'validation_failed' && error.details.field === 'starts_at') {
      return 'Jam booking sudah lewat.'
    }
    if (error.code === 'validation_failed' && error.details.field === 'bookable_until') {
      return 'Jam akhir booking harus setelah jam mulai.'
    }
    if (error.code === 'validation_failed' && typeof error.details.max_hours === 'number') {
      return `Shift maksimal ${error.details.max_hours} jam. Periksa jam pulang.`
    }
    if (error.code === 'item_sold_out' && typeof error.details.name === 'string') {
      return `${error.details.name} habis. Hapus atau ganti item ini.`
    }
    return ERROR_COPY[error.code] ?? error.message
  }
  return 'Terjadi kesalahan. Coba lagi.'
}
