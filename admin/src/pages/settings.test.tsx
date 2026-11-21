import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ApiError } from '../lib/api'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import type { OutletDetail, StaffMember } from '../lib/types'
import BusinessPage from './BusinessPage'
import StaffPage from './StaffPage'

const DAGO: OutletDetail = {
  id: 'o-dago', name: 'Bandung – Dago', address: 'Jl. Ir. H. Juanda No. 12, Bandung',
  timezone: 'Asia/Jakarta', whatsapp_phone: '+628110000001', whatsapp_status: 'connected',
  catalog_synced_at: null, order_prefix: 'A', payment_mode: 'pay_first', pb1_enabled: true,
  pb1_rate_bps: 1000, delivery_fee: 10000, unpaid_timeout_minutes: 15, attendance_grace_minutes: 60,
  is_active: true,
  opening_hours: [1, 2, 3, 4, 5, 6, 7].map((weekday) => ({ weekday, opens_at: '08:00:00', closes_at: '22:00:00' })),
}

describe('O3 Bisnis & Outlet', () => {
  it('shows the outlet and saves only changed fields', async () => {
    const api = fakeApi({
      'GET /owner/outlets/o-dago': DAGO,
      'GET /owner/outlets/o-dago/drawers': [
        // Drawer 2 was deleted: Bar keeps number 3, not its list position (#74).
        { id: 'd1', name: 'Kasir depan', number: 1, has_open_shift: false },
        { id: 'd3', name: 'Bar', number: 3, has_open_shift: false },
      ],
    })
    render(<WithSession session={fakeSession('owner', { api })}><BusinessPage /></WithSession>)
    expect(await screen.findByDisplayValue('Bandung – Dago')).toBeInTheDocument()
    expect(screen.getByText('Sen–Min 08:00 – 22:00')).toBeInTheDocument()
    expect(await screen.findByText('Drawer 1 · Kasir depan (default)')).toBeInTheDocument()
    expect(screen.getByText('Drawer 3 · Bar')).toBeInTheDocument()
    expect(screen.getByText('● Terhubung')).toBeInTheDocument()

    const save = screen.getByRole('button', { name: 'Simpan perubahan' })
    expect(save).toBeDisabled()
    await userEvent.click(screen.getByLabelText(/Open bill/))
    await userEvent.clear(screen.getByLabelText('Biaya delivery flat'))
    await userEvent.type(screen.getByLabelText('Biaya delivery flat'), '15000')
    await userEvent.click(save)
    await waitFor(() =>
      expect(api.calls).toContainEqual(['PATCH', '/owner/outlets/o-dago', { payment_mode: 'open_bill', delivery_fee: 15000 }]),
    )
    expect(api.calls.some(([m, p]) => m === 'PUT' && p.endsWith('/opening-hours'))).toBe(false)
  })
})

describe('O3 Tablet absensi (T-121)', () => {
  type Mockable = { mockImplementation: (f: (p: string) => Promise<unknown>) => void }

  it('allows one tablet per outlet: forget it (with confirmation) before pairing a new one', async () => {
    const recent = new Date(Date.now() - 2 * 60000).toISOString()
    const api = fakeApi({
      'GET /owner/outlets/o-dago': DAGO,
      'POST /owner/attendance-devices/dev1/revoke': {},
      'POST /owner/outlets/o-dago/attendance-pairing-codes': {
        code: '482913', expires_at: new Date(Date.now() + 10 * 60000).toISOString() },
    })
    let devices: unknown[] = [
      { id: 'dev1', name: 'Kasir Dago', paired_at: recent, last_seen_at: recent, revoked_at: null },
      { id: 'dev0', name: 'Tablet lama', paired_at: recent, last_seen_at: null, revoked_at: recent },
    ]
    ;(api.get as unknown as Mockable).mockImplementation(async (path: string) => {
      if (path === '/owner/outlets/o-dago/attendance-devices') return devices
      if (path === '/owner/outlets/o-dago') return DAGO
      return []
    })
    render(<WithSession session={fakeSession('owner', { api })}><BusinessPage /></WithSession>)
    expect(await screen.findByText(/Kasir Dago · aktif 2 menit lalu/)).toBeInTheDocument()
    expect(screen.queryByText(/Tablet lama/)).not.toBeInTheDocument()
    expect(screen.getByLabelText('Tenggang lupa clock out (jam)')).toHaveValue('1')

    // A tablet is paired: no new pairing until it is forgotten.
    expect(screen.queryByRole('button', { name: '+ Pairing tablet baru → kode 6 digit' })).not.toBeInTheDocument()
    expect(screen.getByText(/Satu outlet hanya bisa 1 tablet absensi/)).toBeInTheDocument()

    // "Lupakan perangkat" asks first; "Batal" does nothing.
    await userEvent.click(screen.getByRole('button', { name: 'Lupakan perangkat' }))
    expect(screen.getByRole('group', { name: 'Lupakan Kasir Dago' })).toHaveTextContent('staf tidak bisa absen')
    await userEvent.click(screen.getByRole('button', { name: 'Batal' }))
    expect(api.calls.some(([m]) => m === 'POST')).toBe(false)

    await userEvent.click(screen.getByRole('button', { name: 'Lupakan perangkat' }))
    devices = devices.map((d) => ({ ...(d as object), revoked_at: recent }))
    await userEvent.click(screen.getByRole('button', { name: 'Ya, lupakan' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/owner/attendance-devices/dev1/revoke', undefined]))
    expect(await screen.findByText('Belum ada tablet terhubung.')).toBeInTheDocument()

    // Now a new tablet can be paired.
    await userEvent.click(screen.getByRole('button', { name: '+ Pairing tablet baru → kode 6 digit' }))
    expect(await screen.findByLabelText('Kode pairing')).toHaveTextContent('482913')

    // Once the tablet pairs with the code, the code disappears and pairing is not offered again.
    devices = [{ id: 'dev2', name: 'Tablet 3', paired_at: new Date().toISOString(),
      last_seen_at: new Date().toISOString(), revoked_at: null }]
    expect(await screen.findByText(/Tablet 3 · aktif/, {}, { timeout: 5000 })).toBeInTheDocument()
    expect(screen.queryByLabelText('Kode pairing')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Pairing tablet baru → kode 6 digit' })).not.toBeInTheDocument()
  })

  it('shows the server refusal when the outlet already has a tablet', async () => {
    const api = fakeApi({
      'GET /owner/outlets/o-dago': DAGO,
      'GET /owner/outlets/o-dago/drawers': [],
      'GET /owner/outlets/o-dago/attendance-devices': [],
      'POST /owner/outlets/o-dago/attendance-pairing-codes': new ApiError(409, 'tablet_already_paired', 'busy'),
    })
    render(<WithSession session={fakeSession('owner', { api })}><BusinessPage /></WithSession>)
    await userEvent.click(await screen.findByRole('button', { name: '+ Pairing tablet baru → kode 6 digit' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Outlet ini sudah punya tablet absensi')
  })
})

describe('O3 QRIS statis outlet (PoC)', () => {
  it('uploads a PNG and refuses other files', async () => {
    const api = fakeApi({
      'GET /owner/outlets/o-dago': DAGO,
      'GET /owner/outlets/o-dago/drawers': [],
      'GET /owner/outlets/o-dago/qris': { image: null },
      'UPLOAD /owner/outlets/o-dago/qris?filename=qris-dago.png': {
        image: { filename: 'qris-dago.png', content_type: 'image/png', size: 10, uploaded_at: '2026-11-02T03:00:00Z' } },
    })
    render(<WithSession session={fakeSession('owner', { api })}><BusinessPage /></WithSession>)
    expect(await screen.findByText('QRIS statis outlet')).toBeInTheDocument()
    expect(await screen.findByText('Belum ada gambar QRIS.')).toBeInTheDocument()
    expect(screen.getByText('Hanya PNG/JPG, maks 2 MB.')).toBeInTheDocument()

    const input = screen.getByLabelText(/Unggah gambar/)
    await userEvent.upload(input, new File(['gif'], 'qris.gif', { type: 'image/gif' }), { applyAccept: false })
    expect(await screen.findByText('Hanya PNG/JPG, maks 2 MB.', { selector: '[role=alert] *, [role=alert]' })).toBeInTheDocument()
    expect(api.calls.some(([m]) => m === 'UPLOAD')).toBe(false)

    await userEvent.upload(input, new File(['png'], 'qris-dago.png', { type: 'image/png' }))
    await waitFor(() => expect(api.calls.map(([m, p]) => `${m} ${p}`)).toContain('UPLOAD /owner/outlets/o-dago/qris?filename=qris-dago.png'))
  })
})

describe('O4 Staf & Akses', () => {
  const RINA: StaffMember = {
    id: 's1', display_name: 'Rina', email: 'rina@kopisenja.id',
    outlets: [{ id: 'o-dago', name: 'Bandung – Dago' }], status: 'active',
  }

  it('lists staff with short outlet names and sends an invitation', async () => {
    const api = fakeApi({
      'GET /owner/staff': [RINA, { ...RINA, id: 's2', display_name: 'Maya', email: 'maya@kopisenja.id', status: 'invited' }],
      'POST /owner/staff/invitations': { ...RINA, id: 's3', display_name: 'Sari', email: 'sari@kopisenja.id', status: 'invited' },
    })
    render(<WithSession session={fakeSession('owner', { api })}><StaffPage /></WithSession>)
    expect((await screen.findAllByText('Dago')).length).toBeGreaterThan(0)
    expect(screen.getByText('✉ Diundang')).toBeInTheDocument()
    expect(screen.getByText('Matriks akses (MVP)')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Nama'), 'Sari')
    await userEvent.type(screen.getByLabelText('Email (ditentukan owner)'), 'sari@kopisenja.id')
    await userEvent.click(screen.getByLabelText('Bandung – Riau'))
    await userEvent.click(screen.getByRole('button', { name: 'Kirim undangan' }))
    await waitFor(() =>
      expect(api.calls).toContainEqual(['POST', '/owner/staff/invitations', {
        display_name: 'Sari', email: 'sari@kopisenja.id', outlet_ids: ['o-dago', 'o-riau'] }]),
    )
    expect(await screen.findByText('Undangan dikirim ke sari@kopisenja.id.')).toBeInTheDocument()
  })

  it('deactivates from the row menu', async () => {
    const api = fakeApi({ 'GET /owner/staff': [RINA] })
    render(<WithSession session={fakeSession('owner', { api })}><StaffPage /></WithSession>)
    await userEvent.click(await screen.findByRole('button', { name: 'Menu Rina' }))
    expect(screen.queryByRole('menuitem', { name: 'Kirim ulang undangan' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('menuitem', { name: 'Nonaktifkan' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/owner/staff/s1/deactivate', undefined]))
  })
})
