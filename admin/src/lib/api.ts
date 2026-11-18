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
  get<T>(path: string): Promise<T>
  post<T>(path: string, body?: unknown): Promise<T>
  put<T>(path: string, body: unknown): Promise<T>
  patch<T>(path: string, body: unknown): Promise<T>
  del<T = void>(path: string): Promise<T>
}

export function createApi(baseUrl: string, token: TokenSource): Api {
  const root = baseUrl.replace(/\/+$/, '') + '/api/v1'

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' }
    const access = await token()
    if (access) headers.Authorization = `Bearer ${access}`
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    let res: Response
    try {
      res = await fetch(root + path, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    } catch {
      throw new ApiError(0, 'network_error', 'Tidak bisa terhubung ke server')
    }
    if (res.status === 204) return undefined as T
    const data: unknown = await res.json().catch(() => null)
    if (!res.ok) {
      const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | null)
        ?.error
      throw new ApiError(res.status, err?.code ?? 'http_error', err?.message ?? res.statusText, err?.details)
    }
    return data as T
  }

  return {
    get: (path) => request('GET', path),
    post: (path, body) => request('POST', path, body ?? {}),
    put: (path, body) => request('PUT', path, body),
    patch: (path, body) => request('PATCH', path, body),
    del: (path) => request('DELETE', path),
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
  addon_group_in_use: 'Opsi grup ini sudah dipakai di order; ubah opsinya saja.',
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'validation_failed' && error.details.field === 'pb1_rate_bps') {
      return 'Isi tarif PB1 saat PB1 aktif.'
    }
    return ERROR_COPY[error.code] ?? error.message
  }
  return 'Terjadi kesalahan. Coba lagi.'
}
