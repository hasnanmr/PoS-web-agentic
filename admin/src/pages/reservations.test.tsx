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
  it('replaces a table QR token after confirming and saves the QR target', async () => {
    const api = fakeApi({
      'GET /owner/outlets/o-dago/tables': TABLES,
      'GET /owner/outlets/o-dago/reservation-settings': SETTINGS,
      'GET /owner/outlets/o-dago/table-qr-settings': { target: 'web_whatsapp', whatsapp_connected: false },
      'POST /owner/tables/t1/qr-token': { qr_token: 'new', url: 'https://admin.test/t/new' },
      'PUT /owner/outlets/o-dago/table-qr-settings': { target: 'web', whatsapp_connected: false },
    })
    render(<WithSession session={fakeSession('owner', { api })}><TablesPage /></WithSession>)
    expect(await screen.findByRole('button', { name: /Unduh semua QR \(PDF\)/ })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ganti QR meja M01' }))
    expect(screen.getByText('Ganti QR M01? QR lama tidak berlaku.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ya, ganti' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/owner/tables/t1/qr-token', {}]))
    expect(await screen.findByText('QR baru dibuat. Unduh & cetak ulang.')).toBeInTheDocument()

    // Without WhatsApp the WhatsApp options are disabled; "Web saja" can be chosen.
    expect(await screen.findByLabelText('WhatsApp saja')).toBeDisabled()
    await userEvent.click(screen.getByLabelText('Web saja'))
    await waitFor(() => expect(api.calls).toContainEqual(['PUT', '/owner/outlets/o-dago/table-qr-settings', { target: 'web' }]))
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
