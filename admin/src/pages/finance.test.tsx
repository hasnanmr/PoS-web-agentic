import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { describe, expect, it } from 'vitest'
import type { CashCount, Cashflow, DrawerCard, ExpensePage, ExpenseSummary, ProofDetail, ProofQueueItem, ShiftClosed } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import CashCountPage from './CashCountPage'
import CashflowPage from './CashflowPage'
import ExpensesPage from './ExpensesPage'
import PaymentReviewPage from './PaymentReviewPage'
import ShiftsPage from './ShiftsPage'

const QUEUE: ProofQueueItem[] = [
  { proof_id: 'pr1', kind: 'screenshot', order_id: 'o1', order_no: '#A-1043', channel: 'whatsapp_table', order_type: 'dine_in', table: 'Meja 07',
    total: 30800, received_at: '2026-11-18T03:21:00Z', timezone: 'Asia/Jakarta' },
  { proof_id: 'pr2', kind: 'screenshot', order_id: 'o2', order_no: '#A-1044', channel: 'whatsapp_online', order_type: 'delivery', table: null,
    total: 87500, received_at: '2026-11-18T03:23:00Z', timezone: 'Asia/Jakarta' },
]

const DETAIL: ProofDetail = {
  proof_id: 'pr1', kind: 'screenshot', status: 'pending', image_url: null, order_id: 'o1', order_no: '#A-1043', channel: 'whatsapp_table',
  order_type: 'dine_in', table: 'Meja 07', total: 30800, order_status: 'pending_payment', payment_status: 'proof_submitted',
  customer_phone_masked: '+62 812-xxxx-221', received_at: '2026-11-18T03:21:00Z', timezone: 'Asia/Jakarta',
  timer_stopped: true, reviewed_by: null, reviewed_at: null, rejection_reason: null,
}

function renderS4(api: ReturnType<typeof fakeApi>, path = '/payment-review') {
  render(<MemoryRouter initialEntries={[path]}><WithSession session={fakeSession('staff', { api })}><PaymentReviewPage /></WithSession></MemoryRouter>)
}

describe('S4 Review Pembayaran QRIS', () => {
  it('lists the queue and enables "Tandai paid" only after the merchant check', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/payment-proofs?status=pending': QUEUE,
      'GET /ops/payment-proofs/pr1': DETAIL,
      'POST /ops/payment-proofs/pr1/accept': { ...DETAIL, status: 'accepted' },
    })
    renderS4(api)
    expect(await screen.findByText('Antrian · proof_submitted (2)')).toBeInTheDocument()
    expect(screen.getByText('#A-1043 · Meja 07 · Rp 30.800')).toBeInTheDocument()
    expect(screen.getByText('#A-1044 · Delivery · Rp 87.500')).toBeInTheDocument()
    expect(await screen.findByText('Pelanggan: +62 812-xxxx-221')).toBeInTheDocument()
    expect(screen.getByText(/10:21 WIB \(timer auto-cancel berhenti\)/)).toBeInTheDocument()
    expect(screen.getByText(/Cek mutasi di akun merchant QRIS untuk nominal Rp 30\.800/)).toBeInTheDocument()

    const paid = screen.getByRole('button', { name: '✓ Tandai paid' })
    expect(paid).toBeDisabled()
    await userEvent.click(screen.getByLabelText('Saya sudah menemukan transaksi ini di akun merchant QRIS'))
    await userEvent.click(paid)
    await waitFor(() => expect(api.calls).toContainEqual(
      ['POST', '/ops/payment-proofs/pr1/accept', { merchant_account_checked: true }]))
    expect(await screen.findByText('#A-1043 ditandai paid (QRIS).')).toBeInTheDocument()
  })

  it('requires a reason to reject, and opens the order chosen on the board', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/payment-proofs?status=pending': QUEUE,
      'GET /ops/payment-proofs/pr2': { ...DETAIL, proof_id: 'pr2', order_id: 'o2', order_no: '#A-1044', table: null },
      'POST /ops/payment-proofs/pr2/reject': { ...DETAIL, status: 'rejected' },
    })
    renderS4(api, '/payment-review?order=o2')
    expect(await screen.findByText('#A-1044 · whatsapp_table')).toBeInTheDocument()
    const reject = screen.getByRole('button', { name: '✕ Tolak bukti bayar & batalkan order' })
    expect(reject).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Alasan penolakan'), 'Dana tidak masuk')
    await userEvent.click(reject)
    await waitFor(() => expect(api.calls).toContainEqual(
      ['POST', '/ops/payment-proofs/pr2/reject', { reason: 'Dana tidak masuk' }]))
  })
})

describe('S8 blind count', () => {
  it('hides the expected cash until the count is submitted', async () => {
    const drawers: DrawerCard[] = [{
      drawer: { id: 'd1', name: 'Kasir depan' },
      shift: { id: 's1', opened_at: '2026-11-18T01:00:00Z', starting_cash: 500000, opened_by: 'Rina', cash_in: 1240000,
        cash_in_count: 26, cash_refunds: 61600 },
    }]
    const closed: ShiftClosed = {
      id: 's1', drawer: { id: 'd1', name: 'Kasir depan' }, opened_at: '2026-11-18T01:00:00Z', closed_at: '2026-11-18T15:04:00Z',
      timezone: 'Asia/Jakarta', starting_cash: 500000, cash_in: 1240000, cash_refunds: 61600, expected_cash: 1678400,
      counted_cash: 1760400, difference: 82000, kind: 'surplus', counted_by: 'Rina',
    }
    const api = fakeApi({ 'GET /ops/outlets/o-dago/drawers': drawers, 'POST /ops/shifts/s1/close': closed })
    render(<WithSession session={fakeSession('staff', { api })}><ShiftsPage /></WithSession>)
    await userEvent.click(await screen.findByRole('button', { name: 'Tutup shift & hitung kas' }))
    const panel = screen.getByText('Tutup shift · Drawer 1').closest('section') as HTMLElement
    for (const [note, count] of [['100.000', '12'], ['50.000', '6'], ['20.000', '9'], ['10.000', '5'], ['5.000', '4'], ['2.000', '3']]) {
      await userEvent.type(within(panel).getByLabelText(`Jumlah lembar Rp ${note}`), count)
    }
    await userEvent.type(within(panel).getByLabelText('Nominal Rp 1.000 & koin'), '4400')
    expect(within(panel).getByText('Rp 1.760.400')).toBeInTheDocument()
    expect(within(panel).queryByText(/1\.678\.400/)).not.toBeInTheDocument()

    await userEvent.click(within(panel).getByRole('button', { name: 'Submit hitungan & tutup shift' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/shifts/s1/close', { count_breakdown: {
      coins: 4400, '100000': 12, '50000': 6, '20000': 9, '10000': 5, '5000': 4, '2000': 3 } }]))
    expect(await within(panel).findByText(/= Rp 1\.678\.400/)).toBeInTheDocument()
    expect(within(panel).getByText(/Selisih: \+ Rp 82\.000 \(SURPLUS\) → diposting ke ledger · dihitung oleh Rina 22:04 WIB/))
      .toBeInTheDocument()
  })
})

const CASHFLOW: Cashflow = {
  from: '2026-11-01', to: '2026-11-17', granularity: 'daily', previous: { from: '2026-10-01', to: '2026-10-17' },
  totals: {
    cash_in: { amount: 206760000, change_pct: 12 },
    cash_out: { amount: 26030000, change_pct: 8 },
    net: { amount: 180812000, change_pct: 13 },
    pb1_collected: { amount: 18240000, change_pct: null },
  },
  series: [{ date: '2026-11-01', cash_in: 12000000, cash_out: 900000 }, { date: '2026-11-02', cash_in: 16800000, cash_out: 400000 }],
  breakdown: { revenue_excl_pb1: 182400000, pb1: 18240000, delivery_fee: 6120000, cash: 61300000, qris: 145460000,
    refunds: 1230000, expenses: 24800000, cash_difference: 82000 },
  expenses_by_outlet: [{ outlet_id: 'o-dago', outlet: 'Bandung – Dago', amount: 9200000, count: 9 }],
  expenses_total: 24800000,
  expenses_count: 23,
}

const EXPENSES: ExpensePage = {
  items: [{ id: 7, business_date: '2026-11-17', outlet: { id: 'o-dago', name: 'Bandung – Dago' }, description: 'Beli es batu & gas',
    amount: 350000, recorded_by: 'Olga', created_at: '2026-11-17T04:00:00Z', reversed: false, reversal_reason: null,
    source: 'direct', payment_method: null, purchase_order: null }],
  next_cursor: null,
}

describe('O9 Laporan Cashflow & Pengeluaran', () => {
  it('shows the tiles, breakdown, and records an expense', async () => {
    const api = fakeApi({
      'GET /owner/reports/cashflow?granularity=daily': CASHFLOW,
      'GET /owner/expenses?limit=5': EXPENSES,
      'POST /owner/expenses': EXPENSES.items[0],
    })
    render(<WithSession session={fakeSession('owner', { api })}><CashflowPage /></WithSession>)
    expect(await screen.findByText('Rp 206.760.000')).toBeInTheDocument()
    expect(screen.getByText('▲ 12% vs 1–17 Okt')).toBeInTheDocument()
    expect(screen.getByText('Titipan pajak, bukan pendapatan')).toBeInTheDocument()
    expect(screen.getByText('Total Rp 24.800.000 · 23 entri')).toBeInTheDocument()
    expect(screen.getByText('+ Rp 82.000')).toBeInTheDocument()
    expect(screen.getByText('− Rp 1.230.000')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1–17 Nov 2026 ▾' })).toBeInTheDocument()
    expect(screen.getByText(/^Nov 2026 · dari ledger/)).toBeInTheDocument()
    expect(screen.getAllByTestId('series-bar')).toHaveLength(CASHFLOW.series.length)
    expect(await screen.findByText('17 Nov · Dago · oleh Olga')).toBeInTheDocument()
    expect(screen.getByText('Tidak bisa diedit/dihapus. Koreksi lewat reversal.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Mingguan' }))
    await waitFor(() => expect(api.calls.map((c) => c[1])).toContain('/owner/reports/cashflow?granularity=weekly'))

    await userEvent.type(screen.getByLabelText('Nominal'), '350000')
    await userEvent.type(screen.getByLabelText('Deskripsi'), 'Beli es batu & gas')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan pengeluaran' }))
    await waitFor(() => {
      const call = api.calls.find((c) => c[0] === 'POST' && c[1] === '/owner/expenses')
      expect(call?.[2]).toMatchObject({ outlet_id: 'o-dago', amount: 350000, description: 'Beli es batu & gas' })
    })
    expect(await screen.findByText('Pengeluaran tersimpan di ledger.')).toBeInTheDocument()
  })

  it('opens the full expense list from "Lihat semua pengeluaran →"', async () => {
    const api = fakeApi({
      'GET /owner/reports/cashflow?granularity=daily': CASHFLOW,
      'GET /owner/expenses?limit=5': EXPENSES,
      'GET /owner/expenses?limit=20': EXPENSES,
    })
    render(<WithSession session={fakeSession('owner', { api })}><CashflowPage /></WithSession>)
    await userEvent.click(await screen.findByRole('button', { name: 'Lihat semua pengeluaran →' }))
    await waitFor(() => expect(api.calls.map((c) => c[1])).toContain('/owner/expenses?limit=20'))
    expect(await screen.findByRole('button', { name: 'Buat entry reversal' })).toBeInTheDocument()
  })

  it('offers no reversal on supplier payments (the backend refuses them)', async () => {
    const po = { ...EXPENSES.items[0], id: 11, description: 'PO-A-0012 · Toko Susu Segar', source: 'po' as const,
      payment_method: 'transfer' as const,
      purchase_order: { id: 'po-12', number: 'PO-A-0012', supplier: { id: 'sup1', name: 'Toko Susu Segar' }, created_by: 'Rina',
        created_by_role: 'staff' as const, payment_term: 'pay_later' as const, payment_status: 'paid' as const } }
    const api = fakeApi({
      'GET /owner/reports/cashflow?granularity=daily': CASHFLOW,
      'GET /owner/expenses?limit=5': { items: [po, EXPENSES.items[0]], next_cursor: null },
      'GET /owner/expenses?limit=20': { items: [po, EXPENSES.items[0]], next_cursor: null },
    })
    render(<WithSession session={fakeSession('owner', { api })}><CashflowPage /></WithSession>)
    await userEvent.click(await screen.findByRole('button', { name: 'Lihat semua →' }))
    expect(await screen.findByText('PO-A-0012 · Toko Susu Segar')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Buat entry reversal' })).toHaveLength(1)
  })

  it('reverses an expense from the full list with a reason', async () => {
    const api = fakeApi({
      'GET /owner/reports/cashflow?granularity=daily': CASHFLOW,
      'GET /owner/expenses?limit=5': EXPENSES,
      'GET /owner/expenses?limit=20': EXPENSES,
      'POST /owner/ledger-entries/7/reversal': { reversal_id: 8, expense: { ...EXPENSES.items[0], reversed: true } },
    })
    render(<WithSession session={fakeSession('owner', { api })}><CashflowPage /></WithSession>)
    await userEvent.click(await screen.findByRole('button', { name: 'Lihat semua →' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Buat entry reversal' }))
    const reverse = screen.getByRole('button', { name: 'Buat reversal Rp 350.000' })
    expect(reverse).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Alasan reversal Beli es batu & gas'), 'Salah nominal')
    await userEvent.click(reverse)
    await waitFor(() => expect(api.calls).toContainEqual(
      ['POST', '/owner/ledger-entries/7/reversal', { reason: 'Salah nominal' }]))
  })
})

describe('O10 Laporan Cash Count', () => {
  it('shows the summary and rows with the difference kind', async () => {
    const report: CashCount = {
      from: '2026-11-01', to: '2026-11-17',
      summary: { shifts: 2, shifts_with_difference: 1, total_shortage: -50000, total_surplus: 0 },
      rows: [
        { shift_id: 's1', opened_at: '2026-11-17T01:00:00Z', closed_at: '2026-11-17T15:04:00Z', timezone: 'Asia/Jakarta',
          outlet: { id: 'o-dago', name: 'Bandung – Dago' }, drawer: { id: 'd1', name: 'Kasir depan', number: 1 },
          starting_cash: 500000, expected_cash: 1902500, counted_cash: 1852500, difference: -50000, kind: 'shortage', counted_by: 'Rina' },
        { shift_id: 's2', opened_at: '2026-11-16T09:00:00Z', closed_at: '2026-11-16T15:00:00Z', timezone: 'Asia/Makassar',
          outlet: { id: 'o-riau', name: 'Bali – Canggu' }, drawer: { id: 'd2', name: 'Kasir', number: 1 },
          starting_cash: 400000, expected_cash: 966000, counted_cash: 966000, difference: 0, kind: 'none', counted_by: 'Maya' },
      ],
    }
    const api = fakeApi({ 'GET /owner/reports/cash-count': report })
    render(<WithSession session={fakeSession('owner', { api })}><CashCountPage /></WithSession>)
    expect(await screen.findByText('− Rp 50.000')).toBeInTheDocument()
    expect(screen.getByText('Selisih otomatis diposting ke ledger sebagai shortage / surplus.')).toBeInTheDocument()
    expect(screen.getByText('17 Nov · 08:00–22:04')).toBeInTheDocument()
    expect(screen.getByText('− 50.000 shortage')).toBeInTheDocument()
    expect(screen.getByText('Canggu · Drawer 1 (WITA)')).toBeInTheDocument()
    expect(screen.getByText('16 Nov · 17:00–23:00')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Drawer' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '⭳ Ekspor CSV' })).toBeInTheDocument()
  })
})

const PO_ROW: ExpensePage['items'][number] = {
  id: 11, business_date: '2026-11-19', outlet: { id: 'o-dago', name: 'Bandung – Dago' }, description: 'PO-A-0012 · Toko Susu Segar',
  amount: 2900000, recorded_by: 'Olga', created_at: '2026-11-19T04:00:00Z', reversed: false, reversal_reason: null,
  source: 'po', payment_method: 'transfer',
  purchase_order: { id: 'po-12', number: 'PO-A-0012', supplier: { id: 'sup1', name: 'Toko Susu Segar' }, created_by: 'Rina',
    created_by_role: 'staff', payment_term: 'pay_later', payment_status: 'paid' },
}

const SUMMARY: ExpenseSummary = {
  from: '2026-11-01', to: '2026-11-20',
  total: { amount: 24800000, count: 23 }, po: { amount: 15900000, count: 9, po_count: 6 }, direct: { amount: 8900000, count: 14 },
  by_supplier: [{ supplier: { id: 'sup1', name: 'Toko Susu Segar' }, amount: 6600000, count: 3 }],
  po_owed: { amount: 4200000, count: 3, overdue_count: 1 },
}

function Where() {
  const loc = useLocation()
  return <p data-testid="where">{loc.pathname}{loc.search}</p>
}

describe('O9b Pengeluaran', () => {
  function renderO9b(api: ReturnType<typeof fakeApi>) {
    render(
      <MemoryRouter initialEntries={['/finance/expenses']}>
        <WithSession session={fakeSession('owner', { api })}>
          <Routes>
            <Route path="/finance/expenses" element={<ExpensesPage />} />
            <Route path="/dashboard" element={<Where />} />
          </Routes>
        </WithSession>
      </MemoryRouter>,
    )
  }

  it('highlights supplier payments on staff-opened POs and links to the PO', async () => {
    const api = fakeApi({
      'GET /owner/expenses/summary?': SUMMARY,
      'GET /owner/expenses?from=2026-11-01&to=2026-11-20&limit=20': { items: [PO_ROW, EXPENSES.items[0]], next_cursor: null },
      'GET /owner/expenses?from=2026-11-01&to=2026-11-20&limit=20&source=po': { items: [PO_ROW], next_cursor: null },
    })
    renderO9b(api)
    expect(await screen.findByText('Rp 15.900.000')).toBeInTheDocument()
    // The KPI counts distinct POs; the chip counts payment rows.
    expect(screen.getByText('64% dari total · 6 PO')).toBeInTheDocument()
    expect(screen.getByText('Rp 24.800.000')).toBeInTheDocument()
    expect(screen.getByText('3 PO · 1 lewat jatuh tempo')).toBeInTheDocument()
    expect(await screen.findByText('PO-A-0012 · Toko Susu Segar')).toBeInTheDocument()
    expect(screen.getByText('Dibuat Rina (staf) · Transfer · lunas')).toBeInTheDocument()
    expect(screen.getByText('Beli es batu & gas')).toBeInTheDocument()
    // PO rows are not reversed here; direct rows are.
    expect(screen.getAllByRole('button', { name: 'Reversal' })).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: 'PO supplier (9)' }))
    await waitFor(() => expect(api.calls.map((c) => c[1])).toContain('/owner/expenses?from=2026-11-01&to=2026-11-20&limit=20&source=po'))

    await userEvent.click(screen.getAllByRole('button', { name: 'Lihat PO →' })[0])
    expect(await screen.findByTestId('where')).toHaveTextContent('/dashboard?tab=po&po=po-12')
  })

  describe('Muat lagi', () => {
    const Q = '/owner/expenses?from=2026-11-01&to=2026-11-20&limit=20'
    const PAGE2_ROW = { ...EXPENSES.items[0], id: 99, description: 'Baris halaman 2' }

    function deferred<T>() {
      let resolve!: (v: T) => void
      const promise = new Promise<T>((r) => { resolve = r })
      return { promise, resolve }
    }

    it('appends the next page and blocks a second click while it loads', async () => {
      const next = deferred<ExpensePage>()
      const api = fakeApi({
        'GET /owner/expenses/summary?': SUMMARY,
        [`GET ${Q}`]: { items: [PO_ROW], next_cursor: 'c1' },
        [`GET ${Q}&cursor=c1`]: next.promise,
      })
      renderO9b(api)
      const button = await screen.findByRole('button', { name: 'Muat lagi' })
      await userEvent.click(button)
      expect(button).toBeDisabled()
      await userEvent.click(button)
      expect(api.calls.filter((c) => c[1] === `${Q}&cursor=c1`)).toHaveLength(1)

      next.resolve({ items: [PAGE2_ROW], next_cursor: null })
      expect(await screen.findByText('Baris halaman 2')).toBeInTheDocument()
      expect(screen.getByText('PO-A-0012 · Toko Susu Segar')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Muat lagi' })).not.toBeInTheDocument()
    })

    it('ignores a page that arrives after the filter changed', async () => {
      const next = deferred<ExpensePage>()
      const api = fakeApi({
        'GET /owner/expenses/summary?': SUMMARY,
        [`GET ${Q}`]: { items: [EXPENSES.items[0]], next_cursor: 'c1' },
        [`GET ${Q}&cursor=c1`]: next.promise,
        [`GET ${Q}&source=po`]: { items: [PO_ROW], next_cursor: null },
      })
      renderO9b(api)
      await userEvent.click(await screen.findByRole('button', { name: 'Muat lagi' }))
      await userEvent.click(screen.getByRole('button', { name: 'PO supplier (9)' }))
      expect(await screen.findByText('PO-A-0012 · Toko Susu Segar')).toBeInTheDocument()

      next.resolve({ items: [PAGE2_ROW], next_cursor: 'c2' })
      await next.promise
      await waitFor(() => expect(screen.queryByText('Baris halaman 2')).not.toBeInTheDocument())
      expect(screen.queryByText('Beli es batu & gas')).not.toBeInTheDocument()
      // The stale cursor must not bring the button back on the PO filter.
      expect(screen.queryByRole('button', { name: 'Muat lagi' })).not.toBeInTheDocument()
    })

    it('drops loaded pages when the filter changes and shows them again only after a new load', async () => {
      const api = fakeApi({
        'GET /owner/expenses/summary?': SUMMARY,
        [`GET ${Q}`]: { items: [EXPENSES.items[0]], next_cursor: 'c1' },
        [`GET ${Q}&cursor=c1`]: { items: [PAGE2_ROW], next_cursor: null },
        [`GET ${Q}&source=po`]: { items: [PO_ROW], next_cursor: null },
      })
      renderO9b(api)
      await userEvent.click(await screen.findByRole('button', { name: 'Muat lagi' }))
      expect(await screen.findByText('Baris halaman 2')).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'PO supplier (9)' }))
      expect(await screen.findByText('PO-A-0012 · Toko Susu Segar')).toBeInTheDocument()
      expect(screen.queryByText('Baris halaman 2')).not.toBeInTheDocument()
    })

    it('shows an error when the next page fails', async () => {
      const api = fakeApi({
        'GET /owner/expenses/summary?': SUMMARY,
        [`GET ${Q}`]: { items: [EXPENSES.items[0]], next_cursor: 'c1' },
        [`GET ${Q}&cursor=c1`]: new Error('Koneksi terputus'),
      })
      renderO9b(api)
      await userEvent.click(await screen.findByRole('button', { name: 'Muat lagi' }))
      expect(await screen.findByText(/Halaman berikutnya belum bisa dimuat/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Muat lagi' })).toBeEnabled()
    })
  })

  it('records a direct expense with the same form as O9', async () => {
    const api = fakeApi({
      'GET /owner/expenses/summary?': SUMMARY,
      'GET /owner/expenses?from=2026-11-01&to=2026-11-20&limit=20': EXPENSES,
      'POST /owner/expenses': EXPENSES.items[0],
    })
    renderO9b(api)
    await userEvent.type(await screen.findByLabelText('Nominal'), '350000')
    await userEvent.type(screen.getByLabelText('Deskripsi'), 'Beli es batu & gas')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan pengeluaran' }))
    await waitFor(() => expect(api.calls.find((c) => c[0] === 'POST' && c[1] === '/owner/expenses')?.[2])
      .toMatchObject({ amount: 350000, description: 'Beli es batu & gas' }))
    expect(screen.getByText(/pakai “Catat pembayaran” di Dashboard/)).toBeInTheDocument()
  })

  it('keeps the summary, history and "tersimpan" message on screen while it reloads after a save', async () => {
    let release!: (v: ExpenseSummary) => void
    let calls = 0
    const api = fakeApi({
      'GET /owner/expenses?from=2026-11-01&to=2026-11-20&limit=20': EXPENSES,
      'POST /owner/expenses': EXPENSES.items[0],
    })
    const get = api.get
    api.get = ((path: string) => {
      if (path !== '/owner/expenses/summary?') return get(path)
      api.calls.push(['GET', path, undefined])
      return ++calls === 1 ? Promise.resolve(SUMMARY) : new Promise<ExpenseSummary>((r) => { release = r })
    }) as typeof api.get
    renderO9b(api)
    await userEvent.type(await screen.findByLabelText('Nominal'), '350000')
    await userEvent.type(screen.getByLabelText('Deskripsi'), 'Beli es batu & gas')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan pengeluaran' }))
    expect(await screen.findByText('Pengeluaran tersimpan di ledger.')).toBeInTheDocument()
    await waitFor(() => expect(calls).toBe(2))
    // Summary reload still pending: old figures, history and the message stay.
    expect(screen.getByText('Rp 15.900.000')).toBeInTheDocument()
    expect(screen.getByText('Beli es batu & gas')).toBeInTheDocument()
    expect(screen.getByText('Pengeluaran tersimpan di ledger.')).toBeInTheDocument()
    release({ ...SUMMARY, total: { amount: 25150000, count: 24 } })
    expect(await screen.findByText('Rp 25.150.000')).toBeInTheDocument()
    expect(screen.getByText('Pengeluaran tersimpan di ledger.')).toBeInTheDocument()
  })

  it('still shows the form and history when the summary fails', async () => {
    const api = fakeApi({
      'GET /owner/expenses/summary?': new Error('Koneksi terputus'),
      'GET /owner/expenses?limit=20': EXPENSES,
    })
    renderO9b(api)
    expect(await screen.findByText(/Ringkasan belum bisa dimuat/)).toBeInTheDocument()
    expect(await screen.findByText('Beli es batu & gas')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Semua' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Simpan pengeluaran' })).toBeInTheDocument()
  })
})
