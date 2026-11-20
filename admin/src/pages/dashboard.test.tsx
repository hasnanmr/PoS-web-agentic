import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { hourRanges } from '../lib/format'
import type { DashboardOrders, DashboardSummary, OrderDetail, TopItems } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import DashboardPage from './DashboardPage'

const TODAY: TopItems = {
  period: 'day',
  top_items: [
    { product_id: 'p-kopi', name: 'Es Kopi Susu Senja', quantity_sold: 42, revenue: 1050000 },
    { product_id: 'p-croissant', name: 'Croissant Butter', quantity_sold: 31, revenue: 806000 },
  ],
}

function renderO2(api: ReturnType<typeof fakeApi>) {
  render(<MemoryRouter><WithSession session={fakeSession('owner', { api })}><DashboardPage /></WithSession></MemoryRouter>)
}

describe('O2 Dashboard · Item terlaris', () => {
  it('shows today by default, then switches period and outlet', async () => {
    const api = fakeApi({
      'GET /owner/dashboard/top-items?period=day': TODAY,
      'GET /owner/dashboard/top-items?period=year': { period: 'year', top_items: [] },
      'GET /owner/dashboard/top-items?period=year&outlet_id=o-riau': {
        period: 'year', top_items: [{ product_id: 'p-americano', name: 'Americano', quantity_sold: 1200, revenue: 26400000 }],
      },
    })
    renderO2(api)
    const card = screen.getByRole('region', { name: 'Item terlaris' })
    const first = await within(card).findByRole('row', { name: /Es Kopi Susu Senja/ })
    expect(within(first).getByText('1')).toBeInTheDocument()
    expect(within(first).getByText('42')).toBeInTheDocument()
    expect(within(first).getByText('Rp 1.050.000')).toBeInTheDocument()
    expect(within(card).getByRole('button', { name: 'Hari ini' })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(within(card).getByRole('button', { name: 'Tahun ini' }))
    expect(await within(card).findByText('Belum ada item terjual di periode ini.')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Outlet'), 'o-riau')
    expect(await within(card).findByText('Americano')).toBeInTheDocument()
    expect(within(card).getByText('1.200')).toBeInTheDocument()
    expect(within(card).getByText('Rp 26.400.000')).toBeInTheDocument()
    await waitFor(() => expect(api.calls.map((c) => c[1]).filter((u) => u.includes('top-items'))).toEqual([
      '/owner/dashboard/top-items?period=day',
      '/owner/dashboard/top-items?period=year',
      '/owner/dashboard/top-items?period=year&outlet_id=o-riau',
    ]))
  })

  it('shows an error when the card cannot load', async () => {
    const api = fakeApi({ 'GET /owner/dashboard/top-items?period=day': new Error('boom') })
    renderO2(api)
    expect(await screen.findByText(/Item terlaris belum bisa dimuat/)).toBeInTheDocument()
  })
})

const WIREFRAME_HOURS = [2, 4, 6, 9, 14, 12, 7, 3, 4, 8, 12, 14, 10, 4]
const BUSY = [12, 13, 18, 19]
const QUIET = [8, 9, 15, 16, 21]

function summary(overrides: Partial<DashboardSummary> = {}): DashboardSummary {
  return {
    period: 'today',
    from: '2026-11-19',
    to: '2026-11-19',
    hours: 'all',
    as_of: '2026-11-19T05:40:00Z',
    kpis: {
      revenue_excl_pb1: 12450000, change_pct: 8, orders: 109, cash_count: 38, qris_count: 71,
      pb1_collected: 1245000, delivery_fee: 475000, delivery_orders: 19,
    },
    busyness_map: [1, 2, 3, 4, 5, 6, 7].flatMap((weekday) =>
      Array.from({ length: 14 }, (_, i) => ({ weekday, hour: 8 + i, avg_orders: weekday === 6 && i === 4 ? 9.5 : 1 }))),
    current_crowd: [
      { outlet_id: 'o-dago', name: 'Bandung – Dago', timezone: 'Asia/Jakarta', occupied_tables: 10, total_tables: 12, active_orders: 8, level: 'ramai' },
      { outlet_id: 'o-canggu', name: 'Bali – Canggu', timezone: 'Asia/Makassar', occupied_tables: 5, total_tables: 9, active_orders: 3, level: 'normal' },
      { outlet_id: 'o-kemang', name: 'Jakarta – Kemang', timezone: 'Asia/Jakarta', occupied_tables: 0, total_tables: 0, active_orders: 1, level: 'sepi' },
    ],
    orders_per_hour: WIREFRAME_HOURS.map((orders, i) => ({
      hour: 8 + i, orders, mark: BUSY.includes(8 + i) ? 'busy' : QUIET.includes(8 + i) ? 'quiet' : null,
    })),
    busy_summary: { hours: BUSY, orders: 52, share_pct: 48 },
    quiet_summary: { hours: QUIET, orders: 17, share_pct: 16 },
    low_stock: [
      { stock_item: 'Croissant', outlet_id: 'o-kemang', outlet: 'Kemang', on_hand: '0.000', low_threshold: '5.000', unit: 'pcs', display_unit: null, status: 'out' },
      { stock_item: 'Susu oat', outlet_id: 'o-dago', outlet: 'Dago', on_hand: '800.000', low_threshold: '2000.000', unit: 'ml', display_unit: 'L', status: 'low' },
    ],
    channel_mix: [
      { channel: 'whatsapp_online', orders: 49, share_pct: 45 },
      { channel: 'whatsapp_table', orders: 33, share_pct: 30 },
      { channel: 'counter', orders: 27, share_pct: 25 },
    ],
    payment_methods: [
      { method: 'cash', amount: 4100000, transactions: 38 },
      { method: 'qris', amount: 9120000, transactions: 71 },
    ],
    ...overrides,
  }
}

describe('O2 Dashboard · Ringkasan', () => {
  it('formats busy and quiet hour ranges like the wireframe', () => {
    expect(hourRanges(BUSY)).toBe('12–14 & 18–20')
    expect(hourRanges(QUIET)).toBe('08–10, 15–17, 21–22')
    expect(hourRanges([23])).toBe('23–00')
    expect(hourRanges([0, 1, 22, 23])).toBe('22–02')
    expect(hourRanges([19, 23, 0])).toBe('19–20 & 23–01')
  })

  it('shows every card from GET /owner/dashboard', async () => {
    renderO2(fakeApi({ 'GET /owner/dashboard?period=today&hours=all': summary() }))
    expect(await screen.findByText('Revenue hari ini (excl. PB1)')).toBeInTheDocument()
    expect(screen.getByText('Rp 12.450.000')).toBeInTheDocument()
    expect(screen.getByText('▲ 8% vs kemarin')).toBeInTheDocument()
    expect(screen.getByText('38 cash · 71 QRIS')).toBeInTheDocument()
    expect(screen.getByText('Rp 1.245.000')).toBeInTheDocument()
    expect(screen.getByText('Terpisah dari revenue')).toBeInTheDocument()
    expect(screen.getByText('19 order delivery')).toBeInTheDocument()

    const map = screen.getByRole('region', { name: 'Peta keramaian · hari × jam' })
    expect(within(map).getAllByRole('row')).toHaveLength(8) // hour header + Sen..Min
    expect(within(map).getByTitle('Sab 12: 9,5 order')).toHaveClass('bg-accent-orange')

    const crowd = screen.getByRole('region', { name: 'Keramaian outlet sekarang' })
    expect(within(crowd).getByText('Pukul 12.40 WIB · dari meja terisi dan order aktif')).toBeInTheDocument()
    expect(within(crowd).getByText('Bali – Canggu (WITA 13.40)')).toBeInTheDocument()
    expect(within(crowd).getByText('10/12 meja · 8 order aktif')).toBeInTheDocument()
    expect(within(crowd).getByText('1 order aktif')).toBeInTheDocument()
    expect(within(crowd).getByText('Ramai')).toBeInTheDocument()

    const hours = screen.getByRole('region', { name: 'Order per jam · hari ini' })
    expect(within(hours).getAllByRole('listitem')).toHaveLength(14)
    expect(within(hours).getByRole('listitem', { name: '12:00 14 order, jam ramai' })).toBeInTheDocument()
    expect(within(hours).getByText('Jam ramai 12–14 & 18–20 · 52 order (48%)')).toBeInTheDocument()
    expect(within(hours).getByText('Jam sepi 08–10, 15–17, 21–22 · 17 order (16%)')).toBeInTheDocument()

    const stock = screen.getByRole('region', { name: 'Stok rendah & sold out' })
    expect(within(stock).getByText('0 pcs tersisa · Kemang')).toBeInTheDocument()
    expect(within(stock).getByText('0,8 L tersisa · min 2 L · Dago')).toBeInTheDocument()
    expect(within(stock).getByText('Sold out')).toBeInTheDocument()
    expect(within(stock).getByRole('link', { name: 'Buka stok →' })).toHaveAttribute('href', '/stock')

    const channels = screen.getByRole('region', { name: 'Komposisi per kanal' })
    expect(within(channels).getByText('109 order hari ini')).toBeInTheDocument()
    expect(within(channels).getByText('49 order · 45%')).toBeInTheDocument()
    expect(within(channels).getByText('Rp 9.120.000 · 71 trx')).toBeInTheDocument()
    expect(within(channels).getByRole('link', { name: 'Lihat laporan cashflow →' })).toHaveAttribute('href', '/finance/cashflow')
  })

  it('sends the header outlet, period, and hours filters', async () => {
    const week = summary({ period: 'week', kpis: { ...summary().kpis, change_pct: -3 } })
    const busy = summary({ period: 'week', hours: 'busy', kpis: { ...summary().kpis, change_pct: null } })
    const api = fakeApi({
      'GET /owner/dashboard?period=today&hours=all': summary(),
      'GET /owner/dashboard?period=week&hours=all': week,
      'GET /owner/dashboard?period=week&hours=busy': busy,
      'GET /owner/dashboard?period=week&hours=busy&outlet_id=o-riau': busy,
    })
    renderO2(api)
    await screen.findByText('▲ 8% vs kemarin')
    await userEvent.click(within(screen.getByRole('group', { name: 'Periode' })).getByRole('button', { name: 'Minggu' }))
    expect(await screen.findByText('▼ 3% vs minggu lalu')).toBeInTheDocument()
    expect(screen.getByText('Revenue minggu ini (excl. PB1)')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Jam ramai' }))
    expect(await screen.findByText('Belum ada data minggu lalu')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Jam ramai' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.selectOptions(screen.getByLabelText('Outlet'), 'o-riau')
    await waitFor(() => expect(api.calls.map((c) => c[1]).filter((u) => !u.includes('top-items'))).toEqual([
      '/owner/dashboard?period=today&hours=all',
      '/owner/dashboard?period=week&hours=all',
      '/owner/dashboard?period=week&hours=busy',
      '/owner/dashboard?period=week&hours=busy&outlet_id=o-riau',
    ]))
  })

  it('shows empty states and a load error', async () => {
    const empty = summary({
      busyness_map: [], orders_per_hour: [], low_stock: [], current_crowd: [],
      busy_summary: { hours: [], orders: 0, share_pct: 0 }, quiet_summary: { hours: [], orders: 0, share_pct: 0 },
    })
    renderO2(fakeApi({ 'GET /owner/dashboard?period=today&hours=all': empty }))
    expect(await screen.findByText('Atur jam buka outlet untuk melihat peta keramaian.')).toBeInTheDocument()
    expect(screen.getByText('Belum ada order di periode ini.')).toBeInTheDocument()
    expect(screen.getByText('Semua stok aman.')).toBeInTheDocument()
    expect(screen.getByText('Belum ada outlet aktif.')).toBeInTheDocument()
  })

  it('shows an error when the summary cannot load', async () => {
    renderO2(fakeApi({ 'GET /owner/dashboard?period=today&hours=all': new Error('boom') }))
    expect(await screen.findByText(/Ringkasan belum bisa dimuat/)).toBeInTheDocument()
  })
})

function orders(overrides: Partial<DashboardOrders> = {}): DashboardOrders {
  return {
    period: 'today',
    summary: { orders: 109, revenue_excl_pb1: 12450000, cash_count: 38, qris_count: 71 },
    item: null,
    by_outlet: [
      { outlet_id: 'o-dago', name: 'Bandung – Dago', orders: 79, revenue_excl_pb1: 9040000 },
      { outlet_id: 'o-riau', name: 'Bandung – Riau', orders: 30, revenue_excl_pb1: 3410000 },
    ],
    orders: [
      { id: 'ord-1', order_no: '#A-1036', outlet_id: 'o-dago', outlet: 'Bandung – Dago', timezone: 'Asia/Jakarta',
        created_at: '2026-11-19T05:41:00Z', channel: 'whatsapp_table', type: 'dine_in', table: 'Meja 4', customer_name: null,
        payment_method: 'qris', item_summary: '2× Es Kopi Susu Senja, 1× Croissant Butter', revenue_excl_pb1: 86000, total: 94600 },
      { id: 'ord-2', order_no: '#R-0412', outlet_id: 'o-riau', outlet: 'Bandung – Riau', timezone: 'Asia/Jakarta',
        created_at: '2026-11-19T05:38:00Z', channel: 'counter', type: 'takeaway', table: null, customer_name: null,
        payment_method: 'cash', item_summary: '1× Americano', revenue_excl_pb1: 22000, total: 24200 },
    ],
    next_cursor: 'c1',
    ...overrides,
  }
}

const DRAWER_TODAY = '/owner/dashboard/orders?period=today&hours=all&limit=30'

describe('O2b Dashboard · drawer detail Revenue / Order', () => {
  it('opens from the Revenue tile with the summary, per outlet, list, chips, paging, and S3', async () => {
    const more = orders({
      orders: [{ ...orders().orders[1], id: 'ord-3', order_no: '#R-0411', item_summary: '1× Matcha Latte' }],
      next_cursor: null,
    })
    const detail = {
      id: 'ord-1', order_no: '#A-1036', channel: 'whatsapp_table', type: 'dine_in', payment_mode: 'pay_first',
      status: 'completed', payment_status: 'paid', payment_method: 'qris', payment_id: 'pay-1', qris_checked: true,
      table: 'Meja 4', customer_name: null, note: null, proof_id: null, payment_claimed_at: null, item_summary: '',
      total: 94600, bill_id: null, created_at: '2026-11-19T05:41:00Z', auto_cancel_at: null, allowed_actions: [],
      items: [], subtotal: 86000, pb1_rate_bps: 1000, pb1_amount: 8600, delivery_fee: 0, timezone: 'Asia/Jakarta', events: [],
    } as unknown as OrderDetail
    const api = fakeApi({
      'GET /owner/dashboard?period=today&hours=all': summary(),
      [`GET ${DRAWER_TODAY}`]: orders(),
      [`GET ${DRAWER_TODAY}&cursor=c1`]: more,
      'GET /owner/dashboard/orders?period=today&hours=all&method=cash&limit=30': orders({ orders: [orders().orders[1]], next_cursor: null }),
      'GET /ops/orders/ord-1': detail,
    })
    renderO2(api)
    await userEvent.click(await screen.findByRole('button', { name: /Revenue hari ini \(excl\. PB1\)/ }))
    const drawer = await screen.findByRole('dialog', { name: 'Revenue · Hari ini' })
    expect(within(drawer).getByText(/^Semua outlet · .* · Semua jam$/)).toBeInTheDocument()
    expect(await within(drawer).findByText('Revenue (excl. PB1)')).toBeInTheDocument()
    expect(within(drawer).getByText('Rp 12.450.000')).toBeInTheDocument()
    expect(within(drawer).getByText('▲ 8% vs kemarin')).toBeInTheDocument()
    expect(within(drawer).getByText('rata-rata Rp 114.220')).toBeInTheDocument()
    const perOutlet = within(drawer).getByRole('region', { name: 'Per outlet' })
    expect(within(perOutlet).getByText('Rp 3.410.000 · 30 order')).toBeInTheDocument()
    expect(within(drawer).getByText('#A-1036 · Meja 4')).toBeInTheDocument()
    expect(within(drawer).getByText('12.41 · WhatsApp meja (QR) · Bandung – Dago')).toBeInTheDocument()
    expect(within(drawer).getByText('#R-0412 · Takeaway')).toBeInTheDocument()
    expect(within(drawer).getByText('Menampilkan 2 dari 109')).toBeInTheDocument()

    await userEvent.click(within(drawer).getByRole('button', { name: 'Muat lagi' }))
    expect(await within(drawer).findByText('#R-0411 · Takeaway')).toBeInTheDocument()
    expect(within(drawer).queryByRole('button', { name: 'Muat lagi' })).not.toBeInTheDocument()

    await userEvent.click(within(drawer).getByRole('button', { name: 'Cash 38' }))
    await waitFor(() => expect(within(drawer).queryByText('#A-1036 · Meja 4')).not.toBeInTheDocument())
    expect(within(drawer).getByText('Menampilkan 1 dari 38')).toBeInTheDocument()
    expect(within(drawer).getByRole('button', { name: 'Semua 109' })).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(within(drawer).getByRole('button', { name: 'Semua 109' }))
    await userEvent.click(await within(drawer).findByText('#A-1036 · Meja 4'))
    expect(await within(drawer).findByRole('heading', { name: /^#A-1036 · Dine-in · Meja 4/ })).toBeInTheDocument()
    await userEvent.click(within(drawer).getByRole('button', { name: '← Kembali' }))
    expect(await within(drawer).findByText('Menampilkan 3 dari 109')).toBeInTheDocument() // the loaded page stays

    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument()) // after the slide-out
  })

  it('opens the Order tile, a bar of Order per jam, and an Item terlaris row with their filters', async () => {
    const api = fakeApi({
      'GET /owner/dashboard?period=today&hours=busy': summary({ hours: 'busy' }),
      'GET /owner/dashboard?period=today&hours=all': summary(),
      'GET /owner/dashboard/orders?period=today&hours=busy&limit=30': orders(),
      'GET /owner/dashboard/orders?period=today&hours=all&hour=12&limit=30': orders({ summary: { orders: 14, revenue_excl_pb1: 1600000, cash_count: 4, qris_count: 10 } }),
      'GET /owner/dashboard/top-items?period=day': TODAY,
      'GET /owner/dashboard/top-items?period=month': TODAY,
      'GET /owner/dashboard/orders?period=month&hours=all&product_id=p-kopi&limit=30': orders({
        item: { product_id: 'p-kopi', name: 'Es Kopi Susu Senja', quantity: 42, revenue: 1050000 },
      }),
    })
    renderO2(api)
    await userEvent.click(await screen.findByRole('button', { name: 'Jam ramai' }))
    await userEvent.click(await screen.findByRole('button', { name: /^Order\s*109/ }))
    let drawer = await screen.findByRole('dialog', { name: 'Order · Hari ini' })
    expect(within(drawer).getByText(/· Jam ramai$/)).toBeInTheDocument()
    expect(await within(drawer).findByText('revenue excl. PB1')).toBeInTheDocument()
    await userEvent.click(within(drawer).getByRole('button', { name: 'Tutup' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Semua jam' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Lihat order jam 12:00' }))
    drawer = await screen.findByRole('dialog', { name: 'Order · jam 12.00–12.59 · Hari ini' })
    expect(await within(drawer).findByRole('button', { name: 'Semua 14' })).toBeInTheDocument()
    await userEvent.click(within(drawer).getByRole('button', { name: 'Tutup drawer' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    const card = screen.getByRole('region', { name: 'Item terlaris' })
    await userEvent.click(within(card).getByRole('button', { name: 'Bulan ini' }))
    await userEvent.click(await within(card).findByRole('button', { name: 'Es Kopi Susu Senja' }))
    drawer = await screen.findByRole('dialog', { name: 'Es Kopi Susu Senja · Bulan ini' })
    expect(await within(drawer).findByText('Terjual')).toBeInTheDocument()
    expect(within(drawer).getByText('42')).toBeInTheDocument()
    expect(within(drawer).getByText('dari 109 order')).toBeInTheDocument()
    await waitFor(() => expect(api.calls.map((c) => c[1]).filter((u) => u.startsWith('/owner/dashboard/orders'))).toEqual([
      '/owner/dashboard/orders?period=today&hours=busy&limit=30',
      '/owner/dashboard/orders?period=today&hours=all&hour=12&limit=30',
      '/owner/dashboard/orders?period=month&hours=all&product_id=p-kopi&limit=30',
    ]))
  })

  it('searches by order number and shows the empty state', async () => {
    const api = fakeApi({
      'GET /owner/dashboard?period=today&hours=all': summary(),
      [`GET ${DRAWER_TODAY}`]: orders(),
      'GET /owner/dashboard/orders?period=today&hours=all&q=9999&limit=30': orders({ orders: [], next_cursor: null }),
    })
    renderO2(api)
    await userEvent.click(await screen.findByRole('button', { name: /Revenue hari ini/ }))
    const drawer = await screen.findByRole('dialog', { name: 'Revenue · Hari ini' })
    await userEvent.type(await within(drawer).findByLabelText('Cari no. order'), '9999')
    expect(await within(drawer).findByText('Belum ada order di periode ini.')).toBeInTheDocument()
    expect(within(drawer).getByText('Rp 12.450.000')).toBeInTheDocument() // the summary ignores the search
  })
})

describe('O2 Dashboard · Rentang', () => {
  it('sends a custom range and labels the tiles with it', async () => {
    const ranged = summary({ period: 'range', from: '2026-11-01', to: '2026-11-17', kpis: { ...summary().kpis, change_pct: 12 } })
    const api = fakeApi({
      'GET /owner/dashboard?period=today&hours=all': summary(),
      'GET /owner/dashboard?period=range&from=2026-11-01&to=2026-11-17&hours=all': ranged,
      'GET /owner/dashboard/orders?period=range&from=2026-11-01&to=2026-11-17&hours=all&limit=30': orders({ period: 'range' }),
    })
    renderO2(api)
    await screen.findByText('▲ 8% vs kemarin')
    const group = screen.getByRole('group', { name: 'Periode' })
    await userEvent.click(within(group).getByRole('button', { name: 'Rentang ▾' }))
    await userEvent.type(screen.getByLabelText('Dari tanggal'), '2026-11-01')
    await userEvent.type(screen.getByLabelText('Sampai tanggal'), '2026-11-17')
    await userEvent.click(screen.getByRole('button', { name: 'Terapkan' }))
    expect(await screen.findByText('Revenue 1–17 Nov (excl. PB1)')).toBeInTheDocument()
    expect(screen.getByText('▲ 12% vs periode sebelumnya')).toBeInTheDocument()
    expect(within(group).getByRole('button', { name: '1–17 Nov ▾' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(group).getByRole('button', { name: 'Hari ini' })).toHaveAttribute('aria-pressed', 'false')

    await userEvent.click(screen.getByRole('button', { name: /Revenue 1–17 Nov/ }))
    const drawer = await screen.findByRole('dialog', { name: 'Revenue · 1–17 Nov' })
    expect(within(drawer).getByText('Semua outlet · 1–17 Nov 2026 · Semua jam')).toBeInTheDocument()
  })

  it('refuses a range longer than 92 days', async () => {
    renderO2(fakeApi({ 'GET /owner/dashboard?period=today&hours=all': summary() }))
    await userEvent.click(await screen.findByRole('button', { name: 'Rentang ▾' }))
    await userEvent.type(screen.getByLabelText('Dari tanggal'), '2026-01-01')
    await userEvent.type(screen.getByLabelText('Sampai tanggal'), '2026-06-30')
    expect(screen.getByText('Maksimal 92 hari.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Terapkan' })).toBeDisabled()
  })
})
