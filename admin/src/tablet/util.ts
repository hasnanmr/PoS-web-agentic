// Helpers for the attendance tablet (K0–K4): stored pairing, outlet-local time labels, error copy.
import { ApiError } from '../lib/api'

export interface Pairing {
  token: string
  device_name: string
  outlet: { name: string; timezone: string }
}

export const PAIRING_STORAGE_KEY = 'thinker.tablet'

export function loadPairing(): Pairing | null {
  try {
    const raw = localStorage.getItem(PAIRING_STORAGE_KEY)
    if (!raw) return null
    const value = JSON.parse(raw) as Partial<Pairing>
    return typeof value.token === 'string' && value.outlet ? (value as Pairing) : null
  } catch {
    return null
  }
}

export function savePairing(p: Pairing): void {
  try { localStorage.setItem(PAIRING_STORAGE_KEY, JSON.stringify(p)) } catch { /* private mode */ }
}

export function clearPairing(): void {
  try { localStorage.removeItem(PAIRING_STORAGE_KEY) } catch { /* private mode */ }
}

const ZONE_LABEL: Record<string, string> = { 'Asia/Jakarta': 'WIB', 'Asia/Makassar': 'WITA', 'Asia/Jayapura': 'WIT' }

/** "08:01 WIB" in the outlet zone (label optional). */
export function timeLabel(at: Date, timeZone: string, withZone = true): string {
  const hm = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone }).format(at)
  return withZone ? `${hm} ${ZONE_LABEL[timeZone] ?? ''}`.trim() : hm
}

/** "Selasa, 17 Nov 2026" in the outlet zone. */
export function dateLabel(at: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('id-ID', { weekday: 'long', day: 'numeric', month: 'short', year: 'numeric', timeZone })
    .formatToParts(at)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('weekday')}, ${get('day')} ${get('month').replace('.', '')} ${get('year')}`
}

/** "8 j 32 mnt" */
export function durationLabel(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h} j ${String(m).padStart(2, '0')} mnt` : `${m} mnt`
}

/** K4 error copy (canvas "State error"). */
export function tabletErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case 'network_error':
        return 'Absen belum tercatat. Periksa internet lalu coba lagi.'
      case 'device_revoked':
      case 'device_unpaired':
        return 'Tablet ini tidak lagi terhubung ke outlet. Minta kode pairing baru dari owner.'
      case 'pairing_code_invalid':
        return 'Kode salah, sudah dipakai, atau kedaluwarsa. Minta kode baru dari owner.'
      case 'too_many_attempts':
        return 'Terlalu banyak kode salah. Tunggu beberapa menit lalu coba lagi.'
      case 'selfie_required':
        return 'Selfie wajib untuk absen. Ulangi foto lalu simpan lagi.'
      case 'not_assigned':
        return 'Nama ini tidak lagi ditugaskan ke outlet ini.'
      case 'open_elsewhere':
        return 'Kamu masih tercatat bekerja di outlet lain. Clock out dulu di tablet outlet itu.'
      case 'validation_failed':
        return 'Foto tidak bisa dipakai (hanya JPEG/WebP, maks 2 MB). Ulangi foto.'
    }
    return error.message
  }
  return 'Terjadi kesalahan. Coba lagi.'
}
