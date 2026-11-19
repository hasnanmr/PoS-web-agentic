import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { todayIn } from '../lib/format'
import type { PoDashboard, PoDetail, PoPage, PoRow } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import DashboardPage from './DashboardPage'

const MONTH = todayIn('Asia/Jakarta').slice(0, 7)
const b = (count: number, amount: number) => ({ count, amount })
const DAGO = { id: 'o-dago', name: 'Bandung – Dago' }

const DASH: PoDashboard = {
  po_summary: {
    month: MONTH,
    total: b(6, 960000),
    status: { open: b(3, 300000), closed: b(3, 660000) },
    goods: { not_arrived: b(2, 200000), partly_arrived: b(1, 100000), arrived: b(3, 660000) },
    payment: { unpaid: b(3, 300000), partially_paid: b(1, 160000), paid: b(2, 300000) },
    by_term: { pay_later: b(5, 760000), pay_in_advance: b(1, 200000) },
  },
  supplier_payments: {
    debt_total: 410000, overdue_count: 1, due_7d_amount: 160000, due_7d_count: 1,
    prepaid_not_received: 1500000, prepaid_not_received_count: 1,
    items: [
      { po_id: 'po-7', number: 'PO-R-0007', supplier: { id: 's2', name: 'CV Kopi Priangan' }, outlet: { id: 'o-riau', name: 'Bandung – Riau' },
        payment_term: 'pay_later', reason: 'overdue', status: 'closed', due_date: '2026-11-15', expected_date: null, days_overdue: 3,
        total: 250000, amount_paid: 0, amount_owed: 250000, created_by: 'Rina' },
      { po_id: 'po-12', number: 'PO-A-0012', supplier: { id: 's1', name: 'Toko Susu Segar' }, outlet: DAGO,
        payment_term: 'pay_later', reason: 'due', status: 'closed', due_date: '2026-11-30', expected_date: null, days_overdue: null,
        total: 360000, amount_paid: 200000, amount_owed: 160000, created_by: 'Olga' },
    ],
  },
  po_differences: [
    { po_id: 'po-3', number: 'PO-C-0003', supplier: { id: 's3', name: 'Bali Fresh Supply' }, outlet: DAGO, payment_term: 'pay_later',
      short_lines: [{ item: 'Kentang beku', ordered: '10.000', received: '6.000', short: '4.000', unit: 'kg' }],
      last_received_on: '2026-11-21', last_received_at: '2026-11-21T03:00:00Z', days_since_last_received: 0 },
  ],
}

const ROW: PoRow = {
  id: 'po-12', number: 'PO-A-0012', supplier: { id: 's1', name: 'Toko Susu Segar' }, outlet: DAGO,
  payment_term: 'pay_later', ordered_on: '2026-11-18', due_date: '2026-11-30', expected_date: null,
  status: 'closed', goods_status: 'arrived', payment_status: 'partially_paid', overdue: false, total: 360000,
  created_at: '2026-11-18T03:12:00Z', created_by: 'Olga', amount_paid: 200000, amount_owed: 160000,
}
const PAGE: PoPage = { items: [ROW], next_cursor: null }
const DETAIL: PoDetail = {
  ...ROW, note: null, close_note: null, cancel_reason: null,
  lines: [{ id: 'l1', item: 'Susu UHT', stock_item_id: 'st1', quantity: '20.000', unit: 'L', unit_price: 18000, subtotal: 360000,
    received_quantity: '20.000', remaining_quantity: '0.000', check: 'match' }],
  events: [
    { at: '2026-11-18T03:12:00Z', kind: 'opened', actor: { name: 'Olga', role: 'owner' }, data: { total: 360000 } },
    { at: '2026-11-22T07:30:00Z', kind: 'received', actor: { name: 'Rina', role: 'staff' },
      data: { received_on: '2026-11-22', note: null, lines: [{ item: 'Susu UHT', quantity: 20, unit: 'L' }] } },
    { at: '2026-11-25T02:05:00Z', kind: 'paid', actor: { name: 'Olga', role: 'owner' },
      data: { paid_on: '2026-11-25', amount: 200000, method: 'transfer', from_drawer: false } },
  ],
  allowed_actions: ['record_payment'],
}

const BASE = {
  [`GET /owner/dashboard/purchase-orders?month=${MONTH}`]: DASH,
  'GET /owner/purchase-orders': PAGE,
}

function renderTab(api: ReturnType<typeof fakeApi>, entry = '/dashboard?tab=po') {
  render(
    <MemoryRouter initialEntries={[entry]}>
      <WithSession session={fakeSession('owner', { api })}><DashboardPage /></WithSession>
    </MemoryRouter>,
  )
}

describe('Dashboard tab PO & Supplier (O17 + O15)', () => {
  it('switches tabs from Ringkasan and shows the three O17 cards and the list', async () => {
    const api = fakeApi({ ...BASE, 'GET /owner/dashboard/top-items?period=day': { period: 'day', top_items: [] } })
    renderTab(api, '/dashboard')
    expect(screen.getByRole('tab', { name: 'Ringkasan' })).toHaveAttribute('aria-selected', 'true')
    await userEvent.click(screen.getByRole('tab', { name: 'PO & Supplier' }))

    const summary = await screen.findByRole('region', { name: 'Ringkasan PO' })
    expect(within(summary).getByText(/6 PO · Rp 960.000/)).toBeInTheDocument()
    expect(within(summary).getByRole('button', { name: 'Sebagian: 1 PO' })).toHaveTextContent('1 PO · sisa Rp 160.000')
    expect(within(summary).getByText(/Bayar mundur 5 PO · Bayar di muka 1 PO/)).toBeInTheDocument()

    const pay = screen.getByRole('region', { name: 'Pembayaran supplier' })
    expect(within(pay).getByText(/Hutang supplier Rp 410.000 · 1 overdue · Rp 160.000 jatuh tempo 7 hari/)).toBeInTheDocument()
    expect(within(pay).getByText('OVERDUE 3 HARI · bayar mundur')).toBeInTheDocument()
    expect(within(pay).getByText('Sisa Rp 160.000 dari Rp 360.000')).toBeInTheDocument()
    expect(within(pay).getByText(/Sudah dibayar, barang belum diterima: Rp 1.500.000/)).toBeInTheDocument()

    const diff = screen.getByRole('region', { name: 'PO ada selisih' })
    expect(within(diff).getByText(/Kentang beku 6 \/ 10 kg \(kurang 4 kg\)/)).toBeInTheDocument()

    const list = screen.getByRole('region', { name: 'Daftar PO' })
    const row = await within(list).findByRole('row', { name: /PO-A-0012/ })
    expect(within(row).getByText('Menunggu bayar')).toBeInTheDocument()
    expect(row).toHaveTextContent('Bayar mundurJT 30 Nov')
  })

  it('opens the list with exactly the POs of a Ringkasan figure, and status chips', async () => {
    const api = fakeApi({
      ...BASE,
      [`GET /owner/purchase-orders?month=${MONTH}&payment=partially_paid`]: PAGE,
      'GET /owner/purchase-orders?status=overdue': { items: [], next_cursor: null },
    })
    renderTab(api)
    const summary = await screen.findByRole('region', { name: 'Ringkasan PO' })
    await userEvent.click(within(summary).getByRole('button', { name: 'Sebagian: 1 PO' }))
    expect(await screen.findByText(/Dari Ringkasan PO: Dibayar sebagian/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Overdue' }))
    expect(await screen.findByText('Belum ada PO untuk filter ini.')).toBeInTheDocument()
    expect(api.calls.map((c) => c[1])).toEqual(expect.arrayContaining([
      `/owner/purchase-orders?month=${MONTH}&payment=partially_paid`,
      '/owner/purchase-orders?status=overdue',
    ]))
  })

  it('shows the detail and records an instalment from the detail panel', async () => {
    const api = fakeApi({
      ...BASE,
      'GET /owner/purchase-orders/po-12': DETAIL,
      'GET /ops/outlets/o-dago/shifts/current': [],
      'POST /owner/purchase-orders/po-12/payments': DETAIL,
    })
    renderTab(api)
    const list = await screen.findByRole('region', { name: 'Daftar PO' })
    await userEvent.click(await within(list).findByRole('button', { name: 'PO-A-0012' }))
    const detail = await screen.findByRole('region', { name: 'Detail PO-A-0012' })
    expect(within(detail).getByText(/Barang dicek: Susu UHT 20 L · Rina \(staf\)/)).toBeInTheDocument()
    expect(within(detail).getByText(/Bayar Rp 200.000 · transfer · Owner/)).toBeInTheDocument()
    expect(within(detail).getByText('Sisa hutang (JT 30 Nov)')).toBeInTheDocument()
    expect(within(detail).queryByRole('button', { name: 'Batalkan PO' })).not.toBeInTheDocument()

    await userEvent.click(within(detail).getByRole('button', { name: 'Catat pembayaran' }))
    const dialog = screen.getByRole('dialog', { name: 'Catat pembayaran PO-A-0012' })
    expect(within(dialog).getByLabelText('Nominal (maks. sisa)')).toHaveValue(160000)
    expect(within(dialog).getByLabelText('Cash — dari laci')).toBeDisabled()
    await userEvent.clear(within(dialog).getByLabelText('Nominal (maks. sisa)'))
    await userEvent.type(within(dialog).getByLabelText('Nominal (maks. sisa)'), '100000')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Simpan pembayaran' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const post = (api.post as unknown as { mock: { calls: unknown[][] } }).mock.calls.find((c) => String(c[0]).endsWith('/payments'))!
    expect(post[1]).toEqual({ paid_on: todayIn('Asia/Jakarta'), amount: 100000, method: 'transfer', drawer_id: null })
    expect(post[2]).toEqual({ 'Idempotency-Key': expect.any(String) })
  })

  it('closes a PO with a difference with a required note', async () => {
    const api = fakeApi({ ...BASE, 'POST /owner/purchase-orders/po-3/close': {} })
    renderTab(api)
    const diff = await screen.findByRole('region', { name: 'PO ada selisih' })
    await userEvent.click(within(diff).getByRole('button', { name: 'Tutup dengan catatan PO-C-0003' }))
    const dialog = screen.getByRole('dialog', { name: 'Tutup dengan catatan PO-C-0003' })
    const submit = within(dialog).getByRole('button', { name: 'Tutup PO' })
    expect(submit).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText('Catatan *'), 'supplier kehabisan stok')
    await userEvent.click(submit)
    await waitFor(() => expect(api.calls).toContainEqual(
      ['POST', '/owner/purchase-orders/po-3/close', { note: 'supplier kehabisan stok' }]))
  })

  it('opens a PO from O16 and comes back to the tab with it selected', async () => {
    const opened: PoDetail = { ...DETAIL, id: 'po-new', number: 'PO-A-0013', status: 'open', goods_status: 'not_arrived',
      payment_status: 'unpaid', amount_paid: 0, amount_owed: 215000, total: 215000, allowed_actions: ['receive', 'cancel'] }
    const api = fakeApi({
      ...BASE,
      'GET /ops/suppliers': [{ id: 's1', name: 'Toko Susu Segar' }],
      'GET /ops/outlets/o-dago/stock': { counts: { low: 0, out: 0 }, items: [] },
      'POST /ops/outlets/o-dago/purchase-orders': opened,
      'GET /owner/purchase-orders/po-new': opened,
    })
    renderTab(api)
    await userEvent.click(await screen.findByRole('button', { name: '+ Buka PO' }))
    expect(screen.getByRole('heading', { name: 'Buka Purchase Order' })).toBeInTheDocument()
    expect(screen.getByText('Dashboard › PO & Supplier')).toBeInTheDocument()
    const form = screen.getByRole('region', { name: 'Form Buka PO' })
    await within(form).findByRole('option', { name: 'Toko Susu Segar' })
    await userEvent.selectOptions(within(form).getByLabelText('Supplier *'), 's1')
    await userEvent.type(within(form).getByLabelText('Jatuh tempo'), '2099-12-31')
    await userEvent.type(within(form).getByLabelText('Nama item 1'), 'Gas LPG 12 kg')
    await userEvent.type(within(form).getByLabelText('Qty 1'), '1')
    await userEvent.type(within(form).getByLabelText('Satuan 1'), 'tabung')
    await userEvent.type(within(form).getByLabelText('Harga satuan 1'), '215000')
    expect(within(form).getByText('Total PO').parentElement).toHaveTextContent('Rp 215.000')
    await userEvent.click(within(form).getByRole('button', { name: 'Buka PO' }))

    expect(await screen.findByRole('region', { name: 'Detail PO-A-0013' })).toBeInTheDocument()
    const post = (api.post as unknown as { mock: { calls: unknown[][] } }).mock.calls[0]
    expect(post[0]).toBe('/ops/outlets/o-dago/purchase-orders')
    expect(post[1]).toEqual({
      supplier_id: 's1', ordered_on: todayIn('Asia/Jakarta'), payment_term: 'pay_later', due_date: '2099-12-31',
      expected_date: null, lines: [{ item_name: 'Gas LPG 12 kg', quantity: '1', unit: 'tabung', unit_price: 215000 }], note: null,
    })
  })

  it('adds a supplier from Daftar supplier', async () => {
    const api = fakeApi({
      ...BASE,
      'GET /owner/suppliers': [{ id: 's9', name: 'Kemasan Jaya', phone: null, note: null, is_active: false }],
      'POST /owner/suppliers': { id: 's10', name: 'Bali Fresh Supply', phone: null, note: null, is_active: true },
    })
    renderTab(api)
    await userEvent.click(await screen.findByRole('button', { name: '☰ Daftar supplier' }))
    const dialog = screen.getByRole('dialog', { name: 'Daftar supplier' })
    expect(await within(dialog).findByText('○ Nonaktif')).toBeInTheDocument()
    await userEvent.type(within(dialog).getByLabelText('Nama *'), 'Bali Fresh Supply')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Simpan supplier' }))
    await waitFor(() => expect(api.calls).toContainEqual(
      ['POST', '/owner/suppliers', { name: 'Bali Fresh Supply', phone: null, note: null }]))
  })
})
