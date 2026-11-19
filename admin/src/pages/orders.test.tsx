import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { usePolling } from '../lib/usePolling'
import { ApiError } from '../lib/api'
import type { Quote } from '../lib/types'
import { fakeApi, fakeSession, OUTLETS } from '../test/fakes'
import { WithSession } from '../test/session'
import type { Board, MenuItem, OrderCard, OrderDetail } from '../lib/types'
import CounterPage from './CounterPage'
import OpenBillsPage from './OpenBillsPage'
import OrderBoardPage from './OrderBoardPage'
import ShiftsPage from './ShiftsPage'

const KOPI: MenuItem = {
  product_id: 'p-kopi', name: 'Es Kopi Susu Senja', category: 'Kopi', is_owner_pick: true, price: 25000,
  photo_url: null, sold_out: false, sold_out_reason: null,
  addon_groups: [{ id: 'g-size', name: 'Ukuran', selection: 'single', is_required: true, options: [
    { id: 'o-reg', name: 'Regular', price: 0, available: true },
    { id: 'o-large', name: 'Large', price: 5000, available: false }] }],
}
const CROISSANT: MenuItem = { ...KOPI, product_id: 'p-cro', name: 'Croissant Butter', category: 'Makanan',
  is_owner_pick: false, price: 24000, sold_out: true, sold_out_reason: 'Bahan tidak cukup', addon_groups: [] }

const PAY_FIRST = { ...OUTLETS[0], payment_mode: 'pay_first' as const }

describe('S1 Counter', () => {
  it('requires the add-on, quotes on the server, and pays cash with change', async () => {
    const shift = { id: 's1', drawer_id: 'd1', drawer_name: 'Kasir depan', drawer_number: 1,
      opened_at: '2026-11-18T01:00:00Z', starting_cash: 500000, opened_by: 'u1', opened_by_name: 'Rina' }
    const api = fakeApi({
      'GET /ops/outlets/o-dago/menu': [KOPI, CROISSANT],
      'GET /ops/outlets/o-dago/tables': [],
      'GET /ops/outlets/o-dago/shifts/current': [shift],
      'POST /ops/outlets/o-dago/quotes': { lines: [{ product_id: 'p-kopi', name: 'Es Kopi Susu Senja', unit_price: 25000,
        quantity: 1, line_total: 25000, addons: [] }], subtotal: 25000, pb1_rate_bps: 1000, pb1_amount: 2500, total: 27500 },
      'POST /ops/outlets/o-dago/orders': { id: 'ord1', order_no: '#A-1001', status: 'confirmed', payment_status: 'paid',
        subtotal: 25000, pb1_amount: 2500, total: 27500, change_due: 22500, bill_id: null },
    })
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api, outlet: PAY_FIRST })}><CounterPage /></WithSession></MemoryRouter>)
    expect(await screen.findByText('● Shift aktif · Drawer 1 · 08:00')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Tambah Croissant Butter' })).toBeDisabled()
    expect(screen.getByText('Bahan tidak cukup')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Tambah Es Kopi Susu Senja' }))
    const modal = screen.getByRole('dialog', { name: 'Add-on Es Kopi Susu Senja' })
    expect(within(modal).getByRole('button', { name: 'Tambah' })).toBeDisabled()
    expect(within(modal).getByLabelText(/Large/)).toBeDisabled()
    await userEvent.click(within(modal).getByLabelText(/Regular/))
    await userEvent.click(within(modal).getByRole('button', { name: 'Tambah' }))

    expect(await screen.findByText('Rp 27.500')).toBeInTheDocument()
    expect(screen.getByText('PB1 10%')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '▤ Cash' }))
    await userEvent.type(screen.getByLabelText('Uang diterima'), '50000')
    expect(screen.getByText('Rp 22.500')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Buat order & terima bayar (F9)' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/outlets/o-dago/orders', {
      type: 'dine_in', table_id: null,
      items: [{ product_id: 'p-kopi', quantity: 1, addon_option_ids: ['o-reg'] }],
      payment: { method: 'cash', cash_received: 50000, drawer_id: 'd1' } }]))
    expect(await screen.findByText('Order #A-1001 dibuat · Rp 27.500 · Kembalian Rp 22.500')).toBeInTheDocument()
  })

  it('lets an optional single-choice add-on be unselected; a required one stays chosen', async () => {
    const chicken: MenuItem = { ...KOPI, product_id: 'p-chk', name: 'Italian chicken', addon_groups: [
      KOPI.addon_groups[0],
      { id: 'g-jamur', name: 'Jamur', selection: 'single', is_required: false, options: [
        { id: 'o-jamur', name: 'Jamur H', price: 6000, available: true }] }] }
    const api = fakeApi({
      'GET /ops/outlets/o-dago/menu': [chicken],
      'GET /ops/outlets/o-dago/tables': [],
      'GET /ops/outlets/o-dago/shifts/current': [],
    })
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api, outlet: PAY_FIRST })}><CounterPage /></WithSession></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Tambah Italian chicken' }))
    const modal = screen.getByRole('dialog', { name: 'Add-on Italian chicken' })
    const jamur = within(modal).getByLabelText(/Jamur H/)
    await userEvent.click(jamur)
    expect(jamur).toBeChecked()
    await userEvent.click(jamur)
    expect(jamur).not.toBeChecked()
    const regular = within(modal).getByLabelText(/Regular/)
    await userEvent.click(regular)
    await userEvent.click(regular)
    expect(regular).toBeChecked()
  })

  it('disables cash without a shift and sends dine-in to the open bill', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/menu': [{ ...KOPI, addon_groups: [] }],
      'GET /ops/outlets/o-dago/tables': [{ id: 't5', name: 'Meja 05', area: 'Indoor', open_bill: { id: 'b1', total: 64000 } }],
      'GET /ops/outlets/o-dago/shifts/current': [],
      'POST /ops/outlets/o-dago/quotes': { lines: [], subtotal: 25000, pb1_rate_bps: null, pb1_amount: 0, total: 25000 },
    })
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api })}><CounterPage /></WithSession></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Tambah Es Kopi Susu Senja' }))
    expect(screen.getByRole('button', { name: '▤ Cash' })).toBeDisabled()
    expect(screen.getByRole('option', { name: 'Meja 05 · Indoor — open bill aktif (Rp 64.000)' })).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Meja'), 't5')
    await userEvent.click(screen.getByRole('button', { name: 'Buat order ke open bill (F9)' }))
    await waitFor(() => expect(api.calls.find(([m, p]) => m === 'POST' && p.endsWith('/orders'))?.[2])
      .toMatchObject({ table_id: 't5', payment: { to_open_bill: true } }))
  })
})

describe('S1 Counter: stale quote', () => {
  it('does not show or submit the previous cart total while the new quote is loading', async () => {
    const quote = (total: number): Quote => ({ lines: [], subtotal: total, pb1_rate_bps: null, pb1_amount: 0, total })
    const pending: ((q: Quote) => void)[] = []
    const api = fakeApi({
      'GET /ops/outlets/o-dago/menu': [{ ...KOPI, addon_groups: [] }],
      'GET /ops/outlets/o-dago/tables': [],
      'GET /ops/outlets/o-dago/shifts/current': [],
    })
    const base = api.post
    api.post = vi.fn(async (path: string, body?: unknown) => {
      if (path.endsWith('/quotes')) return new Promise<Quote>((resolve) => { pending.push(resolve) })
      return base(path, body)
    }) as typeof api.post
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api, outlet: PAY_FIRST })}><CounterPage /></WithSession></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Tambah Es Kopi Susu Senja' }))
    await userEvent.click(screen.getByRole('button', { name: '▦ QRIS' }))
    await act(async () => { pending[0](quote(25000)) })
    const submit = () => screen.getByRole('button', { name: /Buat order/ })
    await waitFor(() => expect(screen.getAllByText('Rp 25.000', { selector: 'dd' }).length).toBeGreaterThan(0))
    expect(submit()).toBeEnabled()

    await userEvent.click(screen.getByRole('button', { name: 'Tambah jumlah Es Kopi Susu Senja' }))
    expect(screen.getByText('Total').nextSibling).toHaveTextContent('…')
    expect(submit()).toBeDisabled()
    await act(async () => { pending[1](quote(50000)) })
    await waitFor(() => expect(screen.getByText('Total').nextSibling).toHaveTextContent('Rp 50.000'))
    expect(submit()).toBeEnabled()
  })
})

describe('S1 Counter: cash change and drawer', () => {
  const shift = (id: string, drawer: string, number: number, openedBy: string | null, name: string) => ({
    id, drawer_id: drawer, drawer_name: name, drawer_number: number,
    opened_at: '2026-11-18T01:00:00Z', starting_cash: 500000, opened_by: openedBy, opened_by_name: null,
  })

  it('shows no change while the next quote is still loading', async () => {
    const quote = (total: number): Quote => ({ lines: [], subtotal: total, pb1_rate_bps: null, pb1_amount: 0, total })
    const pending: ((q: Quote) => void)[] = []
    const api = fakeApi({
      'GET /ops/outlets/o-dago/menu': [{ ...KOPI, addon_groups: [] }],
      'GET /ops/outlets/o-dago/tables': [],
      'GET /ops/outlets/o-dago/shifts/current': [shift('s1', 'd1', 1, 'u1', 'Kasir depan')],
    })
    const base = api.post
    api.post = vi.fn(async (path: string, body?: unknown) => {
      if (path.endsWith('/quotes')) return new Promise<Quote>((resolve) => { pending.push(resolve) })
      return base(path, body)
    }) as typeof api.post
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api, outlet: PAY_FIRST })}><CounterPage /></WithSession></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Tambah Es Kopi Susu Senja' }))
    await userEvent.click(screen.getByRole('button', { name: '▤ Cash' }))
    await userEvent.type(screen.getByLabelText('Uang diterima'), '50000')
    // Nothing is quoted yet: the cash received must not be shown as change.
    expect(screen.getByText('Kembalian').nextSibling).toHaveTextContent('—')
    await act(async () => { pending[0](quote(25000)) })
    await waitFor(() => expect(screen.getByText('Kembalian').nextSibling).toHaveTextContent('Rp 25.000'))

    await userEvent.click(screen.getByRole('button', { name: 'Tambah jumlah Es Kopi Susu Senja' }))
    expect(screen.getByText('Kembalian').nextSibling).toHaveTextContent('—')
    await act(async () => { pending[1](quote(50000)) })
    await waitFor(() => expect(screen.getByText('Kembalian').nextSibling).toHaveTextContent('Rp 0'))
  })

  it('asks which drawer receives cash when several shifts are open', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/menu': [{ ...KOPI, addon_groups: [] }],
      'GET /ops/outlets/o-dago/tables': [],
      'GET /ops/outlets/o-dago/shifts/current': [
        shift('s1', 'd1', 1, 'u2', 'Kasir depan'),
        shift('s2', 'd2', 2, 'u3', 'Kasir belakang'),
      ],
      'POST /ops/outlets/o-dago/quotes': { lines: [], subtotal: 25000, pb1_rate_bps: null, pb1_amount: 0, total: 25000 },
      'POST /ops/outlets/o-dago/orders': { id: 'ord1', order_no: '#A-1001', status: 'confirmed', payment_status: 'paid',
        subtotal: 25000, pb1_amount: 0, total: 25000, change_due: 0, bill_id: null },
    })
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api, outlet: PAY_FIRST })}><CounterPage /></WithSession></MemoryRouter>)
    expect(await screen.findByText('2 shift terbuka · pilih drawer untuk cash')).toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Tambah Es Kopi Susu Senja' }))
    await userEvent.click(screen.getByRole('button', { name: '▤ Cash' }))
    // No single drawer can be inferred, so cash stays blocked until one is picked.
    expect(screen.getByRole('button', { name: 'Buat order & terima bayar (F9)' })).toBeDisabled()

    await userEvent.selectOptions(screen.getByLabelText('Drawer'), 'd2')
    await userEvent.type(screen.getByLabelText('Uang diterima'), '25000')
    await userEvent.click(screen.getByRole('button', { name: 'Buat order & terima bayar (F9)' }))
    await waitFor(() => expect(api.calls.find(([m, p]) => m === 'POST' && p.endsWith('/orders'))?.[2])
      .toMatchObject({ payment: { method: 'cash', cash_received: 25000, drawer_id: 'd2' } }))
  })
})

describe('S5 empty bill', () => {
  it('lets the cashier void a bill that has no orders', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/bills': { payment_mode: 'open_bill', bills: [{ id: 'b2', table_id: 't2', table_name: 'Meja 02',
        table_area: null, guest_name: null, running_total: 0, order_count: 0, opened_at: new Date().toISOString() }] },
      'GET /ops/bills/b2': { id: 'b2', table_name: 'Meja 02', table_area: null, guest_name: null, status: 'open',
        opened_at: new Date().toISOString(), orders: [], subtotal: 0, pb1_rate_bps: null, pb1_amount: 0, total: 0 },
      'GET /ops/outlets/o-dago/shifts/current': [],
    })
    render(<WithSession session={fakeSession('staff', { api })}><OpenBillsPage /></WithSession>)
    await userEvent.click(await screen.findByRole('button', { name: 'Batalkan bill' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/bills/b2/void', undefined]))
  })
})

describe('usePolling', () => {
  it('reloads on a timer and skips a tick while a request is still running', () => {
    vi.useFakeTimers()
    try {
      const reload = vi.fn(() => Promise.resolve())
      const { rerender } = renderHook(({ loading }) => usePolling({ loading, reload }, 1000), { initialProps: { loading: false } })
      act(() => { vi.advanceTimersByTime(1000) })
      expect(reload).toHaveBeenCalledTimes(1)
      rerender({ loading: true })
      act(() => { vi.advanceTimersByTime(3000) })
      expect(reload).toHaveBeenCalledTimes(1)
      rerender({ loading: false })
      act(() => { vi.advanceTimersByTime(1000) })
      expect(reload).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })
})

const CARD: OrderCard = {
  id: 'o1', order_no: '#A-1039', channel: 'counter', type: 'takeaway', payment_mode: 'pay_first', status: 'confirmed',
  payment_status: 'paid', payment_method: 'cash', payment_id: null, qris_checked: null, table: null, customer_name: null,
  item_summary: '1× Americano, 1× Roti Bakar', total: 46200, bill_id: null, created_at: '2026-11-18T03:00:00Z',
  auto_cancel_at: null, allowed_actions: ['preparing', 'reversal'],
}
const EMPTY: Board = { awaiting_payment: [], confirmed: [], preparing: [], ready: [], done_today: [] }

describe('S2 Order Board + S3', () => {
  it('renders allowed actions only and reverses with a reason', async () => {
    const detail: OrderDetail = { ...CARD, status: 'ready', allowed_actions: ['completed', 'reversal'],
      items: [{ id: 'i1', name: 'Americano', unit_price: 22000, quantity: 1, line_total: 22000, note: null, addons: [] }],
      subtotal: 42000, pb1_rate_bps: 1000, pb1_amount: 4200, delivery_fee: 0, timezone: 'Asia/Jakarta',
      events: [{ at: '2026-11-18T03:02:00Z', kind: 'created', from: null, to: 'confirmed', from_payment: null, to_payment: null,
        reason: null, data: {}, actor: { type: 'user', name: 'Rina', role: 'staff' } }] }
    const api = fakeApi({
      'GET /ops/outlets/o-dago/orders/board': { ...EMPTY, confirmed: [CARD] },
      'GET /ops/orders/o1': detail,
      'POST /ops/orders/o1/transitions': detail,
      'POST /ops/orders/o1/reversal': { ...detail, refund: { amount: 46200, method: 'cash' } },
    })
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api })}><OrderBoardPage /></WithSession></MemoryRouter>)
    const column = await screen.findByRole('region', { name: 'CONFIRMED' })
    expect(within(column).getByText('Rp 46.200 · paid (cash)')).toBeInTheDocument()
    await userEvent.click(within(column).getByRole('button', { name: 'Mulai siapkan →' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/orders/o1/transitions', { to_status: 'preparing' }]))

    await userEvent.click(within(column).getByText('#A-1039 · counter'))
    const drawer = await screen.findByRole('dialog', { name: 'Detail order' })
    expect(await within(drawer).findByText(/created → confirmed/)).toBeInTheDocument()
    expect(within(drawer).queryByRole('button', { name: 'Batalkan' })).not.toBeInTheDocument()
    await userEvent.click(within(drawer).getByRole('button', { name: 'Reversal order…' }))
    expect(within(drawer).getByLabelText(/Sudah diprepare/)).toBeChecked()
    expect(within(drawer).getByRole('button', { name: 'Konfirmasi reversal' })).toBeDisabled()
    await userEvent.type(within(drawer).getByLabelText('Alasan reversal'), 'salah input')
    await userEvent.click(within(drawer).getByRole('button', { name: 'Konfirmasi reversal' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/orders/o1/reversal', { reason: 'salah input', ingredients: 'waste' }]))
  })
})

describe('S2 QRIS cross-check (PoC)', () => {
  it('shows "QRIS belum dicek" and confirms only after the merchant-account checkbox', async () => {
    const qris: OrderCard = { ...CARD, payment_method: 'qris', payment_id: 'pay1', qris_checked: false,
      allowed_actions: ['preparing', 'reversal', 'qris_check'] }
    const api = fakeApi({
      'GET /ops/outlets/o-dago/orders/board': { ...EMPTY, confirmed: [qris], done_today: [{ ...qris, id: 'o2', order_no: '#A-1040', status: 'completed' }] },
      'POST /ops/orders/o1/qris-check': { ...qris, qris_checked: true, allowed_actions: ['preparing', 'reversal'] },
    })
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api })}><OrderBoardPage /></WithSession></MemoryRouter>)
    const column = await screen.findByRole('region', { name: 'CONFIRMED' })
    expect(within(column).getByText('QRIS belum dicek')).toBeInTheDocument()
    const done = screen.getByRole('region', { name: 'SELESAI / BATAL HARI INI' })
    expect(within(done).getByRole('button', { name: 'QRIS belum dicek · Cek →' })).toBeInTheDocument()

    await userEvent.click(within(column).getByRole('button', { name: 'Cek →' }))
    const dialog = screen.getByRole('dialog', { name: 'Cek QRIS #A-1039' })
    expect(within(dialog).getByText(/Cek mutasi di akun merchant QRIS untuk nominal Rp 46.200/)).toBeInTheDocument()
    const confirm = within(dialog).getByRole('button', { name: '✓ Sudah masuk rekening' })
    expect(confirm).toBeDisabled()
    await userEvent.click(within(dialog).getByLabelText('Saya sudah menemukan transaksi ini di akun merchant QRIS'))
    await userEvent.click(confirm)
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/orders/o1/qris-check', { merchant_account_checked: true }]))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Cek QRIS #A-1039' })).not.toBeInTheDocument())
  })
})

describe('S1 Counter QRIS (PoC)', () => {
  it('shows the outlet QRIS with the amount, or tells the owner to upload it', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/menu': [{ ...KOPI, addon_groups: [] }],
      'GET /ops/outlets/o-dago/tables': [],
      'GET /ops/outlets/o-dago/shifts/current': [],
      'POST /ops/outlets/o-dago/quotes': { lines: [{ product_id: 'p-kopi', name: 'Es Kopi Susu Senja', unit_price: 25000,
        quantity: 1, line_total: 25000, addons: [] }], subtotal: 25000, pb1_rate_bps: null, pb1_amount: 0, total: 25000 },
      'BLOB /ops/outlets/o-dago/qris/image': new ApiError(404, 'not_found', 'qris_image not found'),
    })
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api, outlet: PAY_FIRST })}><CounterPage /></WithSession></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Tambah Es Kopi Susu Senja' }))
    await userEvent.click(await screen.findByRole('button', { name: '▦ QRIS' }))
    expect(await screen.findByText('Scan QRIS · bayar tepat Rp 25.000')).toBeInTheDocument()
    expect(await screen.findByText('Belum ada QRIS. Owner mengunggahnya di Bisnis & Outlet.')).toBeInTheDocument()
  })
})

describe('S5 Open Bills', () => {
  it('shows the running total and closes the bill with QRIS', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/bills': { payment_mode: 'open_bill', bills: [{ id: 'b1', table_id: 't5', table_name: 'Meja 05',
        table_area: 'Indoor', guest_name: null, running_total: 116600, order_count: 3, opened_at: new Date().toISOString() }] },
      'GET /ops/bills/b1': { id: 'b1', table_name: 'Meja 05', table_area: 'Indoor', guest_name: null, status: 'open',
        opened_at: new Date().toISOString(), orders: [{ id: 'o1', order_no: '#A-1028', channel: 'whatsapp_table',
          created_at: new Date().toISOString(), status: 'served', line_total: 60000, items: [{ name: 'Es Kopi Susu Senja', quantity: 2, addons: 'Oat milk' }] }],
        subtotal: 106000, pb1_rate_bps: 1000, pb1_amount: 10600, total: 116600 },
      'GET /ops/outlets/o-dago/shifts/current': [],
      'POST /ops/bills/b1/close': { bill_id: 'b1', total: 116600, method: 'qris', change_due: null, orders_completed: 3 },
    })
    render(<WithSession session={fakeSession('staff', { api })}><OpenBillsPage /></WithSession>)
    expect(await screen.findByText('Mode outlet: Open bill')).toBeInTheDocument()
    expect(await screen.findByText('Total berjalan')).toBeInTheDocument()
    expect(screen.getByText('2× Es Kopi Susu Senja + Oat milk')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'QRIS' }))
    // Switching back to Cash must stay possible even without an open shift.
    await userEvent.click(screen.getByRole('button', { name: 'Cash' }))
    expect(screen.getByRole('button', { name: 'Cash' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'QRIS' }))
    await userEvent.click(screen.getByRole('button', { name: /Tutup bill & bayar Rp 116\.600/ }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/bills/b1/close', { method: 'qris' }]))
  })
})

describe('S8 Shift Kasir', () => {
  it('opens a shift with starting cash', async () => {
    const api = fakeApi({ 'GET /ops/outlets/o-dago/drawers': [{ drawer: { id: 'd1', name: 'Kasir depan' }, shift: null }] })
    render(<WithSession session={fakeSession('staff', { api })}><ShiftsPage /></WithSession>)
    await userEvent.type(await screen.findByLabelText('Kas awal'), '500000')
    await userEvent.click(screen.getByRole('button', { name: 'Buka shift' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/drawers/d1/shifts', { starting_cash: 500000 }]))
  })
})
