import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import type { AuditPage, AuditRow } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import AuditLogPage from './AuditLogPage'

const row = (over: Partial<AuditRow>): AuditRow => ({
  id: 1, created_at: '2026-11-17T03:40:00Z', timezone: 'Asia/Jakarta', outlet_id: 'o-dago', order_id: 'x',
  order_no: '#A-1034', kind: 'reversal', change: 'paid → refunded',
  actor: { type: 'user', id: 'rina', name: 'Rina', role: 'staff' }, reason: 'Salah input item, tamu batal', ...over,
})

const PAGE: AuditPage = {
  date_from: '2026-11-01', date_to: '2026-11-17', next_cursor: 'c1',
  items: [
    row({}),
    row({ id: 2, created_at: '2026-11-17T02:55:00Z', order_no: '#A-1032', kind: 'status', change: 'unpaid → cancelled',
      actor: { type: 'system', id: null, name: null, role: null }, reason: 'Tidak ada bukti bayar 15 mnt' }),
    row({ id: 3, created_at: '2026-11-16T13:12:00Z', timezone: 'Asia/Makassar', order_no: '#C-887', kind: 'payment',
      change: 'marked paid (QRIS)', actor: { type: 'user', id: 'own', name: 'Olga', role: 'owner' }, reason: null }),
  ],
}

function renderO11(api: ReturnType<typeof fakeApi>) {
  render(<MemoryRouter><WithSession session={fakeSession('owner', { api })}><AuditLogPage /></WithSession></MemoryRouter>)
}

describe('O11 Audit Log', () => {
  it('shows rows like the wireframe and loads more', async () => {
    const api = fakeApi({
      'GET /owner/audit-log': PAGE,
      'GET /owner/staff': [{ id: 'rina', display_name: 'Rina', email: 'r@x.id', outlets: [], status: 'active' }],
      'GET /owner/audit-log?cursor=c1': { ...PAGE, next_cursor: null, items: [row({ id: 4, order_no: '#A-0998', kind: 'status', change: 'ready → completed', reason: null })] },
    })
    renderO11(api)
    const first = await screen.findByRole('row', { name: /#A-1034/ })
    expect(within(first).getByText('17 Nov 10:40 WIB')).toBeInTheDocument()
    expect(within(first).getByText('REVERSAL · paid → refunded')).toBeInTheDocument()
    expect(within(first).getByText('Rina (staf)')).toBeInTheDocument()
    expect(within(first).getByText('Salah input item, tamu batal')).toBeInTheDocument()
    const system = screen.getByRole('row', { name: /#A-1032/ })
    expect(within(system).getByText('system')).toBeInTheDocument()
    const bali = screen.getByRole('row', { name: /#C-887/ })
    expect(within(bali).getByText('16 Nov 21:12 WITA')).toBeInTheDocument()
    expect(within(bali).getByText('PAYMENT · marked paid (QRIS)')).toBeInTheDocument()
    expect(within(bali).getByText('Owner')).toBeInTheDocument()
    expect(within(bali).getByText('—')).toBeInTheDocument()
    expect(screen.getByText(/Log bersifat append-only/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Muat lagi' }))
    expect(await screen.findByText('#A-0998')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Muat lagi' })).not.toBeInTheDocument()
  })

  it('sends outlet, staff, and kind filters', async () => {
    const api = fakeApi({ 'GET /owner/staff': [{ id: 'rina', display_name: 'Rina', email: 'r@x.id', outlets: [], status: 'active' }] })
    renderO11(api)
    await userEvent.selectOptions(screen.getByLabelText('Outlet'), 'o-riau')
    await waitFor(() => expect(screen.getByRole('option', { name: 'Staf: Rina' })).toBeInTheDocument())
    await userEvent.selectOptions(screen.getByLabelText('Staf'), 'rina')
    const kinds = screen.getByRole('group', { name: 'Jenis' })
    await userEvent.click(within(kinds).getByRole('button', { name: 'Status' }))
    expect(within(kinds).getByRole('button', { name: 'Status' })).toHaveAttribute('aria-pressed', 'false')
    await waitFor(() => expect(api.calls.map((c) => c[1]).filter((u) => u.startsWith('/owner/audit-log')).at(-1))
      .toBe('/owner/audit-log?outlet_id=o-riau&actor_id=rina&kind=reversal%2Cpayment'))
  })

  it('starts from a fresh first page after switching filters back', async () => {
    const api = fakeApi({
      'GET /owner/audit-log': PAGE,
      'GET /owner/audit-log?cursor=c1': { ...PAGE, next_cursor: null, items: [row({ id: 4, order_no: '#A-0998' })] },
      'GET /owner/audit-log?outlet_id=o-riau': { ...PAGE, next_cursor: null, items: [] },
    })
    renderO11(api)
    await userEvent.click(await screen.findByRole('button', { name: 'Muat lagi' }))
    expect(await screen.findByText('#A-0998')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Outlet'), 'o-riau')
    expect(await screen.findByText('Belum ada perubahan order di periode ini.')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Outlet'), '')
    expect(await screen.findByText('#A-1034')).toBeInTheDocument()
    expect(screen.queryByText('#A-0998')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Muat lagi' })).toBeInTheDocument()
  })

  it('shows an error when the log cannot load', async () => {
    renderO11(fakeApi({ 'GET /owner/audit-log': new Error('boom') }))
    expect(await screen.findByText(/Audit log belum bisa dimuat/)).toBeInTheDocument()
  })
})
