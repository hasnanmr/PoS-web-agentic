import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { offsetAt } from '../lib/format'
import type { OwnerTable, ReservationBoard, ReservationDetail, ReservationSettings } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import ReservationsPage from './ReservationsPage'
import TablesPage from './TablesPage'

const TABLES: OwnerTable[] = [
  { id: 't1', name: 'M01', capacity: 2, area: 'Indoor', is_bookable: true },
  { id: 't9', name: 'M09', capacity: 6, area: 'Indoor', is_bookable: true },
  { id: 't12', name: 'M12', capacity: 4, area: 'Outdoor', is_bookable: false },
]

const SETTINGS: ReservationSettings = {
  is_enabled: true, bookable_from: '10:00:00', bookable_until: '20:00:00', default_duration_minutes: 90,
  booking_window_days: 14, max_party_size: 10, reminder_offset_minutes: 120, cancellation_cutoff_minutes: 180,
  hold_minutes: 15,
}

describe('O8 Meja & Aturan Reservasi', () => {
  it('replaces a table QR token after confirming; no QR target choice any more', async () => {
    const api = fakeApi({
      'GET /owner/outlets/o-dago/tables': TABLES,
      'GET /owner/outlets/o-dago/reservation-settings': SETTINGS,
      'GET /owner/outlets/o-dago/public-link': { slug: 'kopisenja-dago', url: 'https://thinker.id/o/kopisenja-dago' },
      'POST /owner/tables/t1/qr-token': { qr_token: 'new', url: 'https://admin.test/t/new' },
    })
    render(<WithSession session={fakeSession('owner', { api })}><TablesPage /></WithSession>)
    expect(await screen.findByRole('button', { name: /Unduh semua QR \(PDF\)/ })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ganti QR meja M01' }))
    expect(screen.getByText('Ganti QR M01? QR lama tidak berlaku.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ya, ganti' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/owner/tables/t1/qr-token', {}]))
    expect(await screen.findByText('QR baru dibuat. Unduh & cetak ulang.')).toBeInTheDocument()
    expect(screen.queryByText('Tujuan QR meja')).not.toBeInTheDocument()
    expect(api.calls.some(([, path]) => path.includes('table-qr-settings'))).toBe(false)
  })

  it('O8 link outlet: copy, change the slug after confirming, download the outlet QR and poster', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const api = fakeApi({
      'GET /owner/outlets/o-dago/tables': TABLES,
      'GET /owner/outlets/o-dago/reservation-settings': SETTINGS,
      'GET /owner/outlets/o-dago/public-link': { slug: 'kopisenja-dago', url: 'https://thinker.id/o/kopisenja-dago' },
      'PUT /owner/outlets/o-dago/public-link': { slug: 'kopi-senja', url: 'https://thinker.id/o/kopi-senja' },
      'BLOB /owner/outlets/o-dago/outlet-qr.png': new Blob(['png']),
      'BLOB /owner/outlets/o-dago/outlet-poster.pdf': new Blob(['pdf']),
    })
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    render(<WithSession session={fakeSession('owner', { api })}><TablesPage /></WithSession>)
    const slug = await screen.findByLabelText('Slug outlet')
    expect(slug).toHaveValue('kopisenja-dago')
    expect(screen.getByText('thinker.id/o/')).toBeInTheDocument()
    expect(screen.getByText('QR meja (3 meja) — dine-in')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Simpan link outlet' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'Salin link outlet' }))
    expect(writeText).toHaveBeenCalledWith('https://thinker.id/o/kopisenja-dago')

    await userEvent.click(screen.getByRole('button', { name: '↓ Unduh PNG' }))
    await userEvent.click(screen.getByRole('button', { name: '↓ Poster PDF' }))
    expect(api.calls).toContainEqual(['BLOB', '/owner/outlets/o-dago/outlet-qr.png', 'image/png'])
    expect(api.calls).toContainEqual(['BLOB', '/owner/outlets/o-dago/outlet-poster.pdf', 'application/pdf'])

    await userEvent.clear(slug)
    await userEvent.type(slug, 'Kopi-Senja')
    // While the slug is edited the old link can't be copied or downloaded by mistake.
    expect(screen.getByRole('button', { name: 'Salin link outlet' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '↓ Unduh PNG' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Simpan link outlet' }))
    const confirm = screen.getByRole('alertdialog', { name: 'Konfirmasi ganti link' })
    expect(confirm).toHaveTextContent('Ganti link ke kopi-senja? Link & QR outlet lama langsung tidak berlaku.')
    expect(api.calls.some(([m]) => m === 'PUT')).toBe(false)
    await userEvent.click(within(confirm).getByRole('button', { name: 'Ya, ganti' }))
    await waitFor(() => expect(api.calls).toContainEqual(['PUT', '/owner/outlets/o-dago/public-link', { slug: 'kopi-senja' }]))
    expect(await screen.findByText(/Link outlet disimpan/)).toBeInTheDocument()
  })

  it('O8 link outlet: a taken slug shows the error and keeps the old link', async () => {
    const api = fakeApi({
      'GET /owner/outlets/o-dago/tables': TABLES,
      'GET /owner/outlets/o-dago/reservation-settings': SETTINGS,
      'GET /owner/outlets/o-dago/public-link': { slug: 'kopisenja-dago', url: 'https://thinker.id/o/kopisenja-dago' },
      'PUT /owner/outlets/o-dago/public-link': new ApiError(409, 'slug_taken', 'this link is already used by another outlet'),
    })
    render(<WithSession session={fakeSession('owner', { api })}><TablesPage /></WithSession>)
    const slug = await screen.findByLabelText('Slug outlet')
    await userEvent.clear(slug)
    await userEvent.type(slug, 'kopi')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan link outlet' }))
    await userEvent.click(screen.getByRole('button', { name: 'Ya, ganti' }))
    expect(await screen.findByText('Link ini sudah dipakai outlet lain. Pilih slug lain.')).toBeInTheDocument()
    expect(screen.getByText('thinker.id/o/')).toBeInTheDocument()
  })

  it('lists tables with their QR download and adds a table', async () => {
    const api = fakeApi({
      'GET /owner/outlets/o-dago/tables': TABLES,
      'GET /owner/outlets/o-dago/reservation-settings': SETTINGS,
    })
    render(<WithSession session={fakeSession('owner', { api })}><TablesPage /></WithSession>)
    expect(await screen.findByRole('button', { name: 'Ubah meja M09' })).toBeInTheDocument()
    expect(screen.getByText('✕ (tidak via reservasi)')).toBeInTheDocument()
    for (const t of TABLES) expect(screen.getByRole('button', { name: `Unduh QR meja ${t.name}` })).toBeEnabled()

    await userEvent.click(screen.getByRole('button', { name: '+ Meja' }))
    await userEvent.type(screen.getByLabelText('Nama meja'), 'VIP')
    await userEvent.clear(screen.getByLabelText('Kapasitas'))
    await userEvent.type(screen.getByLabelText('Kapasitas'), '10')
    await userEvent.type(screen.getByLabelText('Area'), 'Lantai 2')
    await userEvent.click(screen.getAllByRole('button', { name: 'Simpan' })[0]) // the table form's
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/owner/outlets/o-dago/tables',
      { name: 'VIP', capacity: 10, area: 'Lantai 2', is_bookable: true }]))
  })

  it('keeps stored minutes that are not whole tenths of an hour when another field is saved', async () => {
    const api = fakeApi({
      'GET /owner/outlets/o-dago/tables': TABLES,
      'GET /owner/outlets/o-dago/reservation-settings': { ...SETTINGS, reminder_offset_minutes: 45, cancellation_cutoff_minutes: 20 },
    })
    render(<WithSession session={fakeSession('owner', { api })}><TablesPage /></WithSession>)
    expect(await screen.findByLabelText('Reminder dikirim')).toHaveValue('0,75')
    await userEvent.clear(screen.getByLabelText('Maks. jumlah orang'))
    await userEvent.type(screen.getByLabelText('Maks. jumlah orang'), '12')
    const saves = screen.getAllByRole('button', { name: 'Simpan' })
    await userEvent.click(saves[saves.length - 1])
    await waitFor(() => expect(api.calls).toContainEqual(['PUT', '/owner/outlets/o-dago/reservation-settings',
      expect.objectContaining({ max_party_size: 12, reminder_offset_minutes: 45, cancellation_cutoff_minutes: 20 })]))
  })

  it('saves reservation rules with hours converted to minutes', async () => {
    const api = fakeApi({
      'GET /owner/outlets/o-dago/tables': TABLES,
      'GET /owner/outlets/o-dago/reservation-settings': SETTINGS,
    })
    render(<WithSession session={fakeSession('owner', { api })}><TablesPage /></WithSession>)
    expect(await screen.findByText('15 menit (tetap)')).toBeInTheDocument()
    expect(screen.getByText('Semua jam dalam zona waktu outlet (WIB).')).toBeInTheDocument()
    expect(screen.getByLabelText('Reminder dikirim')).toHaveValue('2')
    await userEvent.clear(screen.getByLabelText('Batas batal / reschedule'))
    await userEvent.type(screen.getByLabelText('Batas batal / reschedule'), '1,5')
    const saves = screen.getAllByRole('button', { name: 'Simpan' })
    await userEvent.click(saves[saves.length - 1])
    await waitFor(() => expect(api.calls).toContainEqual(['PUT', '/owner/outlets/o-dago/reservation-settings', {
      is_enabled: true, bookable_from: '10:00', bookable_until: '20:00', default_duration_minutes: 90,
      booking_window_days: 14, max_party_size: 10, reminder_offset_minutes: 120, cancellation_cutoff_minutes: 90,
    }]))
    expect(await screen.findByText('Aturan reservasi disimpan.')).toBeInTheDocument()
  })
})

// 2026-11-17 in WIB; the clock is fixed at 11:35 WIB so Lina (11:30) is on hold.
const BOARD: ReservationBoard = {
  date: '2026-11-17',
  timezone: 'Asia/Jakarta',
  settings: { bookable_from: '10:00:00', bookable_until: '20:00:00', default_duration_minutes: 90,
    max_party_size: 10, booking_window_days: 14, hold_minutes: 15 },
  tables: TABLES,
  reservations: [
    { id: 'r-walk', table_id: 't1', table_name: 'M01', guest_name: null, party_size: 2,
      starts_at: '2026-11-17T03:00:00Z', ends_at: '2026-11-17T04:30:00Z', status: 'seated', source: 'walk_in',
      hold_until: null, no_show_at: null, allowed_actions: ['complete', 'move', 'cancel'] },
    { id: 'r-lina', table_id: 't9', table_name: 'M09', guest_name: 'Lina', party_size: 3,
      starts_at: '2026-11-17T04:30:00Z', ends_at: '2026-11-17T06:00:00Z', status: 'booked', source: 'whatsapp',
      hold_until: '2026-11-17T04:45:00Z', no_show_at: null, allowed_actions: ['seat', 'move', 'cancel', 'no_show'] },
    { id: 'r-tono', table_id: 't12', table_name: 'M12', guest_name: 'Tono', party_size: 2,
      starts_at: '2026-11-17T03:30:00Z', ends_at: '2026-11-17T05:00:00Z', status: 'no_show', source: 'phone',
      hold_until: null, no_show_at: '2026-11-17T03:45:00Z', allowed_actions: [] },
  ],
}

const LINA: ReservationDetail = {
  ...BOARD.reservations[1], phone_masked: '+62 813-xxxx-090', timezone: 'Asia/Jakarta',
  events: [
    { event: 'created', from_status: null, to_status: 'booked', from_table: null, to_table: null, reason: null,
      actor_type: 'system', actor_name: null, created_at: '2026-11-17T02:12:00Z' },
  ],
}

describe('S6 / M4 Reservasi & Meja', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true, now: new Date('2026-11-17T04:35:00Z') })
  })
  afterEach(() => vi.useRealTimers())

  it('draws the day timeline per table with status labels', async () => {
    const api = fakeApi({ 'GET /ops/outlets/o-dago/reservations': BOARD })
    render(<WithSession session={fakeSession('staff', { api })}><ReservationsPage /></WithSession>)
    const timeline = await screen.findByRole('region', { name: 'Timeline meja' })
    expect(within(timeline).getByText('M12 · 4 org (Outdoor)')).toBeInTheDocument()
    expect(within(timeline).getByText('Tanpa reservasi · terisi')).toBeInTheDocument()
    expect(within(timeline).getByText('10:00–11:30')).toBeInTheDocument()
    expect(within(timeline).getByText('Lina · 3 · hold 15 mnt ⏱')).toBeInTheDocument()
    expect(within(timeline).getByText('11:30 — no-show 11:45')).toBeInTheDocument()
    expect(within(timeline).getByText('10:30 (dilepas)')).toBeInTheDocument()
    expect(screen.getByText(/Selasa, 17 Nov 2026/)).toBeInTheDocument()
    const list = screen.getByRole('region', { name: 'Daftar reservasi' })
    expect(within(list).getByText('Hold — auto no-show 11:45')).toBeInTheDocument()
  })

  it('shows the detail with only the allowed actions and seats the guest', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/reservations': BOARD,
      'GET /ops/reservations/r-lina': LINA,
    })
    render(<WithSession session={fakeSession('staff', { api })}><ReservationsPage /></WithSession>)
    const timeline = await screen.findByRole('region', { name: 'Timeline meja' })
    await userEvent.click(within(timeline).getByTitle(/^Lina/))
    expect(await screen.findByText('Detail: Lina · 3 orang · 11:30–13:00 · M09')).toBeInTheDocument()
    expect(await screen.findByText('Sumber: WhatsApp · +62 813-xxxx-090')).toBeInTheDocument()
    expect(screen.getByText('Status: booked → hold (auto no-show 11:45)')).toBeInTheDocument()
    expect(screen.getByText('Riwayat: 09:12 dibuat via WA')).toBeInTheDocument()
    const detail = screen.getByText(/^Detail: Lina/).closest('section')!
    expect(within(detail).queryByRole('button', { name: 'Selesai' })).toBeNull()
    await userEvent.click(within(detail).getByRole('button', { name: 'Seated' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/reservations/r-lina/seat', undefined]))
  })

  it('opens a web chat booking without crashing (source web_chat)', async () => {
    const hasnan = { ...BOARD.reservations[1], id: 'r-web', guest_name: 'Hasnan', source: 'web_chat' as const }
    const api = fakeApi({
      'GET /ops/outlets/o-dago/reservations': { ...BOARD, reservations: [hasnan] },
      'GET /ops/reservations/r-web': { ...LINA, ...hasnan },
    })
    render(<WithSession session={fakeSession('staff', { api })}><ReservationsPage /></WithSession>)
    const timeline = await screen.findByRole('region', { name: 'Timeline meja' })
    await userEvent.click(within(timeline).getByTitle(/^Hasnan/))
    expect(await screen.findByText('Sumber: Web chat · +62 813-xxxx-090')).toBeInTheDocument()
    expect(screen.getByText('Riwayat: 09:12 dibuat via web chat')).toBeInTheDocument()
  })

  it('M4 mobile: tapping a card opens its detail and actions inline', async () => {
    const matchMedia = vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
    vi.stubGlobal('matchMedia', matchMedia)
    try {
      const api = fakeApi({
        'GET /ops/outlets/o-dago/reservations': BOARD,
        'GET /ops/reservations/r-walk': { ...LINA, ...BOARD.reservations[0], events: [] },
      })
      render(<WithSession session={fakeSession('staff', { api })}><ReservationsPage /></WithSession>)
      const list = await screen.findByRole('region', { name: 'Daftar reservasi' })
      // The hold card shows its actions without a tap (wireframe M4).
      expect(within(list).getByRole('button', { name: 'Seated' })).toBeInTheDocument()
      expect(within(list).queryByRole('button', { name: 'Selesai' })).toBeNull()
      const walk = within(list).getByRole('button', { name: /Tanpa reservasi · 2 org · M01/ })
      expect(walk).toHaveAttribute('aria-expanded', 'false')
      await userEvent.click(walk)
      expect(walk).toHaveAttribute('aria-expanded', 'true')
      expect(within(list).getByRole('button', { name: 'Selesai' })).toBeInTheDocument()
      expect(await within(list).findByText('Status: terisi tanpa reservasi')).toBeInTheDocument()
      // No hidden desktop detail card is mounted on a phone.
      expect(screen.queryByText(/^Detail:/)).toBeNull()
      await userEvent.click(walk)
      expect(within(list).queryByRole('button', { name: 'Selesai' })).toBeNull()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('books by phone with the outlet offset and explains a clash', async () => {
    const api = fakeApi({ 'GET /ops/outlets/o-dago/reservations': BOARD })
    render(<WithSession session={fakeSession('staff', { api })}><ReservationsPage /></WithSession>)
    await screen.findByRole('region', { name: 'Timeline meja' })
    await userEvent.click(screen.getAllByRole('button', { name: /\+ Booking/ })[0])
    await userEvent.type(screen.getByLabelText('Nama tamu'), 'Dewi')
    await userEvent.clear(screen.getByLabelText('Jam booking'))
    await userEvent.type(screen.getByLabelText('Jam booking'), '11:00')
    api.post = vi.fn(async () => { throw new ApiError(409, 'conflict', 'taken') })
    await userEvent.click(screen.getByRole('button', { name: 'Simpan booking' }))
    expect(api.post).toHaveBeenCalledWith('/ops/outlets/o-dago/reservations', {
      guest_name: 'Dewi', guest_phone: null, party_size: 2, starts_at: '2026-11-17T11:00:00+07:00',
      table_id: null, source: 'phone',
    })
    expect(await screen.findByText('Meja sudah dibooking atau terisi di jam itu (bentrok).')).toBeInTheDocument()
  })

  it('falls back to automatic when the chosen table no longer fits the party', async () => {
    const api = fakeApi({ 'GET /ops/outlets/o-dago/reservations': BOARD })
    render(<WithSession session={fakeSession('staff', { api })}><ReservationsPage /></WithSession>)
    await screen.findByRole('region', { name: 'Timeline meja' })
    await userEvent.click(screen.getAllByRole('button', { name: /\+ Booking/ })[0])
    await userEvent.type(screen.getByLabelText('Nama tamu'), 'Dewi')
    await userEvent.selectOptions(screen.getByLabelText('Meja booking'), 't1')
    await userEvent.clear(screen.getByLabelText('Jumlah orang'))
    await userEvent.type(screen.getByLabelText('Jumlah orang'), '4')
    expect(screen.getByLabelText('Meja booking')).toHaveValue('')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan booking' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/outlets/o-dago/reservations',
      expect.objectContaining({ party_size: 4, table_id: null })]))
  })

  it('disables the walk-in button when the chosen table no longer fits', async () => {
    const api = fakeApi({ 'GET /ops/outlets/o-dago/reservations': BOARD })
    render(<WithSession session={fakeSession('staff', { api })}><ReservationsPage /></WithSession>)
    await screen.findByRole('region', { name: 'Timeline meja' })
    await userEvent.click(screen.getAllByRole('button', { name: /Tandai meja terisi/ })[0])
    await userEvent.selectOptions(screen.getByLabelText('Meja terisi'), 't1')
    await userEvent.clear(screen.getByLabelText('Jumlah orang terisi'))
    await userEvent.type(screen.getByLabelText('Jumlah orang terisi'), '3')
    expect(screen.getByLabelText('Meja terisi')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Tandai terisi' })).toBeDisabled()
  })

  it('marks a table occupied without a reservation', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/reservations': BOARD,
      'POST /ops/outlets/o-dago/walk-ins': { ...BOARD.reservations[0], id: 'r-new', table_name: 'M09' },
    })
    render(<WithSession session={fakeSession('staff', { api })}><ReservationsPage /></WithSession>)
    await screen.findByRole('region', { name: 'Timeline meja' })
    await userEvent.click(screen.getAllByRole('button', { name: /Tandai meja terisi/ })[0])
    await userEvent.selectOptions(screen.getByLabelText('Meja terisi'), 't9')
    await userEvent.click(screen.getByRole('button', { name: 'Tandai terisi' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/outlets/o-dago/walk-ins', { table_id: 't9', party_size: 2 }]))
    expect(await screen.findByText('M09 ditandai terisi (tanpa reservasi).')).toBeInTheDocument()
  })
})

describe('offsetAt', () => {
  it('uses the outlet zone offset', () => {
    expect(offsetAt('Asia/Jakarta', '2026-11-17', '11:00')).toBe('+07:00')
    expect(offsetAt('Asia/Makassar', '2026-11-17', '11:00')).toBe('+08:00')
    expect(offsetAt('Asia/Jayapura', '2026-11-17', '11:00')).toBe('+09:00')
  })
})
