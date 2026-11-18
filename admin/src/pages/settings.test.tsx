import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
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
        { id: 'd1', name: 'Kasir depan', has_open_shift: false },
        { id: 'd2', name: 'Bar', has_open_shift: false },
      ],
    })
    render(<WithSession session={fakeSession('owner', { api })}><BusinessPage /></WithSession>)
    expect(await screen.findByDisplayValue('Bandung – Dago')).toBeInTheDocument()
    expect(screen.getByText('Sen–Min 08:00 – 22:00')).toBeInTheDocument()
    expect(await screen.findByText('Drawer 1 · Kasir depan (default)')).toBeInTheDocument()
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
