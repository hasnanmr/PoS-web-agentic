import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { todayIn } from '../lib/format'
import type { PoDetail, PoRow } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import PurchaseOrdersPage from './PurchaseOrdersPage'

const DAGO = { id: 'o-dago', name: 'Bandung – Dago' }
const base: Omit<PoRow, 'id' | 'number'> = {
  supplier: { id: 's1', name: 'Bandung Fresh Supply' }, outlet: DAGO, payment_term: 'pay_later',
  ordered_on: '2026-11-10', due_date: '2099-11-28', expected_date: null, status: 'open', goods_status: 'not_arrived',
  payment_status: 'unpaid', overdue: false, total: 1090000, created_at: '2026-11-20T03:00:00Z', created_by: 'Rina',
  amount_paid: null, amount_owed: null,
}
const ROWS: PoRow[] = [
  { ...base, id: 'po-14', number: 'PO-A-0014', status: 'difference_found', goods_status: 'partly_arrived' },
  { ...base, id: 'po-15', number: 'PO-A-0015', payment_term: 'pay_in_advance', due_date: null, expected_date: '2099-11-26',
    total: 1500000, supplier: { id: 's2', name: 'CV Kopi Priangan' } },
  { ...base, id: 'po-12', number: 'PO-A-0012', status: 'closed', goods_status: 'arrived', payment_status: 'partially_paid',
    total: 360000, supplier: { id: 's3', name: 'Toko Susu Segar' } },
]

const line = (id: string, item: string, qty: string, unit: string, received: string, stock: string | null) => ({
  id, item, stock_item_id: stock, quantity: qty, unit, unit_price: 1000, subtotal: 1000,
  received_quantity: received, remaining_quantity: (Number(qty) - Number(received)).toFixed(3),
  check: (Number(received) === Number(qty) ? 'match' : 'short') as 'match' | 'short',
})

const OPEN: PoDetail = {
  ...base, id: 'po-14', number: 'PO-A-0014', note: null, close_note: null, cancel_reason: null,
  lines: [line('l1', 'Kentang beku', '10.000', 'kg', '0.000', 'st1'), line('l2', 'Susu UHT', '12.000', 'L', '0.000', 'st2'),
    line('l3', 'Gelas plastik', '40.000', 'pcs', '0.000', null)],
  events: [{ at: '2026-11-20T03:00:00Z', kind: 'opened', actor: { name: 'Rina', role: 'staff' }, data: { total: 1090000 } }],
  allowed_actions: ['receive'],
}
const SHORT: PoDetail = {
  ...OPEN, status: 'difference_found', goods_status: 'partly_arrived',
  lines: [line('l1', 'Kentang beku', '10.000', 'kg', '10.000', 'st1'), line('l2', 'Susu UHT', '12.000', 'L', '8.000', 'st2'),
    line('l3', 'Gelas plastik', '40.000', 'pcs', '40.000', null)],
  events: [...OPEN.events, { at: '2026-11-22T03:05:00Z', kind: 'received', actor: { name: 'Rina', role: 'staff' },
    data: { received_on: '2026-11-22', note: null, lines: [{ item: 'Kentang beku', quantity: 10, unit: 'kg' }] } }],
  allowed_actions: ['receive'],
}
const MATCHED: PoDetail = {
  ...SHORT, status: 'open', goods_status: 'arrived',
  lines: SHORT.lines.map((l) => ({ ...l, received_quantity: l.quantity, remaining_quantity: '0.000', check: 'match' as const })),
  allowed_actions: ['receive', 'close'],
}

function renderPage(api: ReturnType<typeof fakeApi>, entry = '/purchase-orders') {
  render(
    <MemoryRouter initialEntries={[entry]}>
      <WithSession session={fakeSession('staff', { api })}><PurchaseOrdersPage /></WithSession>
    </MemoryRouter>,
  )
}

const posts = (api: ReturnType<typeof fakeApi>) => (api.post as unknown as { mock: { calls: unknown[][] } }).mock.calls

describe('S10 Purchase Order outlet (staff)', () => {
  it('lists the outlet POs with goods and read-only payment status, and filters by status', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/purchase-orders': { items: ROWS, next_cursor: null, counts: { active: 3, waiting_goods: 1 } },
      'GET /ops/outlets/o-dago/purchase-orders?status=closed': { items: [ROWS[2]], next_cursor: null, counts: { active: 3, waiting_goods: 1 } },
    })
    renderPage(api)
    const list = await screen.findByRole('region', { name: 'Daftar PO outlet' })
    const short = within(list).getByRole('row', { name: /PO-A-0014/ })
    expect(within(short).getByText('⚠ Ada selisih')).toBeInTheDocument()
    expect(within(short).getByText('— (setelah PO ditutup)')).toBeInTheDocument()
    expect(within(short).getByText(/dibuka Rina · 10 Nov/)).toBeInTheDocument()
    const advance = within(list).getByRole('row', { name: /PO-A-0015/ })
    expect(within(advance).getByText('Menunggu dibayar owner (notif di dashboard owner)')).toBeInTheDocument()
    const closed = within(list).getByRole('row', { name: /PO-A-0012/ })
    expect(within(closed).getByText('Dicicil owner')).toBeInTheDocument()
    expect(within(closed).getByRole('button', { name: 'Lihat detail PO-A-0012' })).toBeInTheDocument()
    expect(within(list).queryByText(/sisa/i)).not.toBeInTheDocument() // staff never see debt

    expect(screen.getByRole('button', { name: 'Terbuka (3)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Menunggu barang (1)' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Ditutup' }))
    await waitFor(() => expect(within(list).queryByText('PO-A-0014')).not.toBeInTheDocument())
  })

  it('opens S12 with the assigned-outlet form', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/purchase-orders': { items: [], next_cursor: null, counts: { active: 0, waiting_goods: 0 } },
      'GET /ops/suppliers': [],
      'GET /ops/outlets/o-dago/stock': { counts: { low: 0, out: 0 }, items: [] },
    })
    renderPage(api)
    await userEvent.click(await screen.findByRole('button', { name: '+ Buka PO' }))
    expect(screen.getByRole('heading', { name: 'Buka Purchase Order' })).toBeInTheDocument()
    expect(screen.getByLabelText('Outlet * (yang ditugaskan)')).toHaveValue('o-dago')
    expect(await screen.findByText(/Minta owner menambahkan supplier/)).toBeInTheDocument()
  })
})

describe('S11 Cek barang datang', () => {
  it('saves a partial delivery, keeps Tutup PO locked while short, then closes when all match', async () => {
    const api = fakeApi({
      'GET /ops/purchase-orders/po-14': OPEN,
      'POST /ops/purchase-orders/po-14/receipts': SHORT,
      'POST /ops/purchase-orders/po-14/close': { ...MATCHED, status: 'closed', allowed_actions: [] },
    })
    renderPage(api, '/purchase-orders?po=po-14')
    const form = await screen.findByRole('region', { name: 'Cek barang PO-A-0014' })
    await userEvent.type(within(form).getByLabelText('Datang sekarang Kentang beku'), '10')
    await userEvent.type(within(form).getByLabelText('Datang sekarang Susu UHT'), '8')
    await userEvent.type(within(form).getByLabelText('Datang sekarang Gelas plastik'), '40')
    expect(within(form).getByText('⚠ Kurang 4 L')).toBeInTheDocument()
    expect(within(form).getByText(/1 baris kurang → PO tidak bisa ditutup oleh staf/)).toBeInTheDocument()
    expect(within(form).getByText(/\+10 kg Kentang beku, \+8 L Susu UHT \(ref\. PO-A-0014\)/)).toBeInTheDocument()
    expect(within(form).getByRole('button', { name: /Tutup PO terkunci — qty belum sesuai PO/ })).toBeDisabled()
    await userEvent.type(within(form).getByLabelText('Catatan'), 'Susu kurang 4 L')
    await userEvent.click(within(form).getByRole('button', { name: 'Simpan penerimaan' }))

    await waitFor(() => expect(posts(api)).toHaveLength(1))
    expect(posts(api)[0][1]).toEqual({
      received_on: todayIn('Asia/Jakarta'), note: 'Susu kurang 4 L',
      lines: [{ line_id: 'l1', quantity: '10.000' }, { line_id: 'l2', quantity: '8.000' }, { line_id: 'l3', quantity: '40.000' }],
    })
    expect(posts(api)[0][2]).toEqual({ 'Idempotency-Key': expect.any(String) })
    expect(await within(form).findByText('⚠ Kurang 4 L')).toBeInTheDocument() // server state now
    expect(screen.queryByRole('button', { name: 'Tutup PO' })).not.toBeInTheDocument()
    expect(screen.getByText(/Barang dicek: Kentang beku 10 kg · Rina \(staf\)/)).toBeInTheDocument()
  })

  it('offers Tutup PO only when the server allows it, and refuses more than the remaining qty', async () => {
    const api = fakeApi({
      'GET /ops/purchase-orders/po-14': SHORT,
      'POST /ops/purchase-orders/po-14/receipts': MATCHED,
      'POST /ops/purchase-orders/po-14/close': { ...MATCHED, status: 'closed', allowed_actions: [] },
    })
    renderPage(api, '/purchase-orders?po=po-14')
    const form = await screen.findByRole('region', { name: 'Cek barang PO-A-0014' })
    expect(within(form).getByLabelText('Datang sekarang Kentang beku')).toBeDisabled()
    await userEvent.type(within(form).getByLabelText('Datang sekarang Susu UHT'), '5')
    expect(within(form).getByText('Maks. 4 L')).toBeInTheDocument()
    expect(within(form).getByRole('button', { name: 'Simpan penerimaan' })).toBeDisabled()
    await userEvent.clear(within(form).getByLabelText('Datang sekarang Susu UHT'))
    await userEvent.type(within(form).getByLabelText('Datang sekarang Susu UHT'), '4')
    await userEvent.click(within(form).getByRole('button', { name: 'Simpan penerimaan' }))

    await userEvent.click(await screen.findByRole('button', { name: 'Tutup PO' }))
    expect(await screen.findByText('PO sudah ditutup.')).toBeInTheDocument()
    expect(api.calls.map((c) => `${c[0]} ${c[1]}`)).toContain('POST /ops/purchase-orders/po-14/close')
  })

  it('explains the lock for an unpaid pay-in-advance PO whose goods all arrived', async () => {
    const unpaid: PoDetail = { ...MATCHED, payment_term: 'pay_in_advance', due_date: null, expected_date: '2099-11-26',
      allowed_actions: [] }
    renderPage(fakeApi({ 'GET /ops/purchase-orders/po-14': unpaid }), '/purchase-orders?po=po-14')
    expect(await screen.findByRole('button', { name: /Tutup PO terkunci — PO bayar di muka belum dibayar owner/ })).toBeDisabled()
  })

  it('records a second identical delivery with a new Idempotency-Key, and sends 1000 pcs as 1000', async () => {
    const big: PoDetail = { ...OPEN, lines: [line('l9', 'Gelas', '3000.000', 'pcs', '0.000', null)] }
    const api = fakeApi({ 'GET /ops/purchase-orders/po-14': big })
    let received = 0
    api.post = (async () => {
      received += 1000
      return { ...big, lines: [line('l9', 'Gelas', '3000.000', 'pcs', `${received}.000`, null)] }
    }) as typeof api.post
    const spy = vi.spyOn(api, 'post')
    renderPage(api, '/purchase-orders?po=po-14')
    const form = await screen.findByRole('region', { name: 'Cek barang PO-A-0014' })
    for (let i = 0; i < 2; i++) {
      await userEvent.type(within(form).getByLabelText('Datang sekarang Gelas'), '1000')
      await userEvent.click(within(form).getByRole('button', { name: 'Simpan penerimaan' }))
      await waitFor(() => expect(spy).toHaveBeenCalledTimes(i + 1))
      await waitFor(() => expect(within(form).getByLabelText('Datang sekarang Gelas')).toHaveValue(''))
    }
    const [first, second] = spy.mock.calls
    expect(first[1]).toEqual(second[1]) // same body…
    expect((first[1] as { lines: { quantity: string }[] }).lines[0].quantity).toBe('1000.000')
    expect((first[2] as Record<string, string>)['Idempotency-Key'])
      .not.toBe((second[2] as Record<string, string>)['Idempotency-Key']) // …new request
  })

  it('refuses an empty receive date or one before the order date', async () => {
    renderPage(fakeApi({ 'GET /ops/purchase-orders/po-14': OPEN }), '/purchase-orders?po=po-14')
    const form = await screen.findByRole('region', { name: 'Cek barang PO-A-0014' })
    await userEvent.type(within(form).getByLabelText('Datang sekarang Kentang beku'), '2')
    const save = within(form).getByRole('button', { name: 'Simpan penerimaan' })
    expect(save).toBeEnabled()
    const date = within(form).getByLabelText('Tanggal terima')
    await userEvent.clear(date)
    expect(save).toBeDisabled()
    await userEvent.type(date, '2026-11-09') // order date is 10 Nov
    expect(save).toBeDisabled()
    expect(within(form).getByText(/Isi tanggal antara 10 Nov \(tanggal order\) dan hari ini/)).toBeInTheDocument()
  })
})
