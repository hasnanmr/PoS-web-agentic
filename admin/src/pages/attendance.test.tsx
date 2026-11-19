import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { AttendanceDetail, AttendanceRecord, AttendanceReport, MyAttendanceHistory, MyAttendanceToday } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import { toInstant } from './attendance/util'
import MyAttendancePage from './MyAttendancePage'
import StaffAttendancePage from './StaffAttendancePage'

const rec = (over: Partial<AttendanceRecord>): AttendanceRecord => ({
  id: 'r', date: '2026-11-16', user: { id: 'u-rina', name: 'Rina' }, outlet: { id: 'o-dago', name: 'Bandung – Dago' },
  timezone: 'Asia/Jakarta', clock_in_at: '2026-11-16T01:00:00Z', clock_out_at: '2026-11-16T09:30:00Z',
  duration_minutes: 510, has_selfie_in: true, has_selfie_out: true, status: 'closed', ...over,
})

const REPORT: AttendanceReport = {
  from: '2026-11-11', to: '2026-11-17',
  summary: [
    { user: { id: 'u-rina', name: 'Rina' }, outlets: ['Bandung – Dago'], worked_minutes: 2780, days: 6 },
    { user: { id: 'u-maya', name: 'Maya' }, outlets: ['Bali – Canggu'], worked_minutes: 2320, days: 5 },
  ],
  needs_correction_count: 1,
  records: [
    rec({ id: 'r-open', date: '2026-11-17', clock_in_at: '2026-11-17T01:02:00Z', clock_out_at: null,
      duration_minutes: null, has_selfie_out: false, status: 'open' }),
    rec({ id: 'r-flag', user: { id: 'u-dodi', name: 'Dodi' }, outlet: { id: 'o-riau', name: 'Bandung – Riau' },
      clock_in_at: '2026-11-16T07:00:00Z', clock_out_at: null, duration_minutes: null, has_selfie_out: false,
      status: 'needs_correction' }),
    rec({ id: 'r-maya', user: { id: 'u-maya', name: 'Maya' }, outlet: { id: 'o-canggu', name: 'Bali – Canggu' },
      timezone: 'Asia/Makassar', clock_in_at: '2026-11-16T01:00:00Z', clock_out_at: '2026-11-16T09:10:00Z',
      duration_minutes: 490 }),
  ],
}

const FLAGGED_DETAIL: AttendanceDetail = {
  ...REPORT.records[1],
  devices: { clock_in: 'Riau 1', clock_out: null },
  original: { clock_in_at: '2026-11-16T07:00:00Z', clock_out_at: null },
  flag: { at: '2026-11-16T16:00:00Z', closes_at: '22:00', grace_minutes: 60 },
  corrections: [],
}

describe('O14 Kehadiran Staf', () => {
  it('shows totals, flagged records and corrects a forgotten clock-out with a reason', async () => {
    const api = fakeApi({
      'GET /owner/attendance': REPORT,
      'GET /owner/staff': [],
      'GET /owner/attendance/r-flag': FLAGGED_DETAIL,
      'POST /owner/attendance/r-flag/corrections': { ...FLAGGED_DETAIL, status: 'corrected' },
      'BLOB /owner/attendance/r-flag/selfies/in': new Blob(['x']),
    })
    render(<WithSession session={fakeSession('owner', { api })}><StaffAttendancePage /></WithSession>)
    expect(await screen.findByText('Rina · Dago')).toBeInTheDocument()
    expect(screen.getByText('46 j 20 mnt · 6 hari')).toBeInTheDocument()
    expect(screen.getByText('1 catatan')).toBeInTheDocument()
    expect(screen.getByText('09:00 WITA')).toBeInTheDocument()
    expect(screen.getByText('berjalan')).toBeInTheDocument()
    expect(screen.getByText('● Bekerja')).toBeInTheDocument()
    expect(screen.getByText('⚠ Koreksi')).toBeInTheDocument()

    // The flagged record opens by default.
    expect(await screen.findByText('Koreksi catatan · Dodi, 16 Nov')).toBeInTheDocument()
    expect(screen.getByText('Selfie masuk 14:00 · tablet Riau 1')).toBeInTheDocument()
    expect(screen.getByText('Nilai asli: masuk 14:00 · pulang —')).toBeInTheDocument()
    expect(screen.getByText('Ditandai otomatis 23:00 (tutup 22:00 + 1 jam)')).toBeInTheDocument()
    expect(screen.queryByLabelText('Jam masuk')).not.toBeInTheDocument()

    const save = screen.getByRole('button', { name: 'Simpan koreksi' })
    await userEvent.type(screen.getByLabelText('Jam pulang'), '22:15')
    expect(save).toBeDisabled() // reason required
    await userEvent.type(screen.getByLabelText('Alasan koreksi'), 'Lupa clock out, dikonfirmasi via chat')
    await userEvent.click(save)
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/owner/attendance/r-flag/corrections', {
      reason: 'Lupa clock out, dikonfirmasi via chat', clock_out_at: '2026-11-16T22:15:00+07:00' }]))
  })

  it('filters by outlet and opens another record', async () => {
    const api = fakeApi({ 'GET /owner/attendance': REPORT, 'GET /owner/attendance?outlet_id=o-riau': REPORT,
      'GET /owner/staff': [],
      'GET /owner/attendance/r-flag': FLAGGED_DETAIL,
      'GET /owner/attendance/r-maya': { ...REPORT.records[2], devices: { clock_in: 'Tablet 1', clock_out: 'Tablet 1' },
        original: { clock_in_at: REPORT.records[2].clock_in_at, clock_out_at: REPORT.records[2].clock_out_at },
        flag: null, corrections: [{ at: '2026-11-17T02:12:00Z', by: 'Olga',
          from: { clock_in_at: null, clock_out_at: null }, to: { clock_in_at: null, clock_out_at: '2026-11-16T09:10:00Z' },
          reason: 'lupa clock out' }] },
    })
    render(<WithSession session={fakeSession('owner', { api })}><StaffAttendancePage /></WithSession>)
    await userEvent.selectOptions(await screen.findByLabelText('Outlet'), 'o-riau')
    await waitFor(() => expect(api.calls.some(([m, p]) => m === 'GET' && p === '/owner/attendance?outlet_id=o-riau')).toBe(true))
    await userEvent.click(await screen.findByRole('button', { name: 'Buka catatan Maya 16 Nov' }))
    expect(await screen.findByText('Koreksi catatan · Maya, 16 Nov')).toBeInTheDocument()
    expect(screen.getByLabelText('Jam masuk')).toHaveValue('09:00')
    expect(screen.getByText(/pulang — → 17:10/)).toBeInTheDocument()
    expect(screen.getByText(/oleh Olga · 17 Nov 10:12 · “lupa clock out”/)).toBeInTheDocument()
  })

  it('puts a clock-out at or before the clock-in on the next day', () => {
    expect(toInstant('2026-11-16', '01:30', 'Asia/Jakarta', '18:00')).toBe('2026-11-17T01:30:00+07:00')
    expect(toInstant('2026-11-16', '17:10', 'Asia/Makassar', '09:00')).toBe('2026-11-16T17:10:00+08:00')
  })
})

const TODAY: MyAttendanceToday = {
  status: 'working', clock_in_at: new Date(Date.now() - (3 * 60 + 12) * 60000).toISOString(),
  device_name: 'Kasir Dago', outlet: { name: 'Bandung – Dago', timezone: 'Asia/Jakarta' },
  flagged_records: [{ id: 'r-flag', date: '2026-11-15', outlet: { name: 'Bandung – Riau' } }],
}

const HISTORY: MyAttendanceHistory = {
  from: '2026-11-16', to: '2026-11-17', total_minutes: 510,
  records: [
    rec({ id: 'r-flag', date: '2026-11-15', outlet: { id: 'o-riau', name: 'Bandung – Riau' }, clock_out_at: null,
      duration_minutes: null, has_selfie_out: false, status: 'needs_correction' }),
    rec({ id: 'r-1' }),
  ],
}

describe('S9 / M6 Absensi Saya', () => {
  it('shows today, the forgotten clock-out banner, own history and selfies', async () => {
    const api = fakeApi({
      'GET /ops/me/attendance/today': TODAY,
      'GET /ops/me/attendance': HISTORY,
      'BLOB /ops/me/attendance/r-1/selfies/in': new Blob(['x']),
      'BLOB /ops/me/attendance/r-1/selfies/out': new Blob(['x']),
    })
    render(<WithSession session={fakeSession('staff', { api })}><MyAttendancePage /></WithSession>)
    expect(await screen.findByText('● Sedang bekerja')).toBeInTheDocument()
    expect(screen.getByText('3 j 12 mnt')).toBeInTheDocument()
    expect(screen.getByText(/tablet “Kasir Dago” · Bandung – Dago/)).toBeInTheDocument()
    expect(screen.getByText('ⓘ Clock in / out hanya di tablet absensi outlet')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Kamu lupa clock out 15 Nov (Riau)')
    expect(screen.queryByRole('button', { name: /clock in/i })).not.toBeInTheDocument()

    expect(await screen.findByText('Total minggu ini: 8 j 30 mnt (tanpa catatan yang perlu dikoreksi)')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('⚠ koreksi')).toBeInTheDocument()
    await userEvent.click(within(table).getByRole('button', { name: 'Selfie 16 Nov' }))
    expect(await screen.findByText('Selfie pulang')).toBeInTheDocument()
    expect(api.calls).toContainEqual(['BLOB', '/ops/me/attendance/r-1/selfies/in', 'image/*'])
  })

  it('says to clock in at the outlet tablet when not working', async () => {
    const api = fakeApi({
      'GET /ops/me/attendance/today': { ...TODAY, status: 'not_clocked_in', clock_in_at: null, device_name: null,
        outlet: null, flagged_records: [] },
      'GET /ops/me/attendance': { ...HISTORY, records: [], total_minutes: 0 },
    })
    render(<WithSession session={fakeSession('staff', { api })}><MyAttendancePage /></WithSession>)
    expect(await screen.findByText('○ Belum clock in. Absen di tablet outlet.')).toBeInTheDocument()
    expect(await screen.findByText('Belum ada absen minggu ini.')).toBeInTheDocument()
  })
})
