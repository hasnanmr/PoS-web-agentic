import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { hourRanges } from '../lib/format'
import type { DashboardSummary, TopItems } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import DashboardPage from './DashboardPage'

const TODAY: TopItems = {
  period: 'day',
  top_items: [
    { name: 'Es Kopi Susu Senja', quantity_sold: 42, revenue: 1050000 },
    { name: 'Croissant Butter', quantity_sold: 31, revenue: 806000 },
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
        period: 'year', top_items: [{ name: 'Americano', quantity_sold: 1200, revenue: 26400000 }],
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
    expect(within(crowd).getByText('Pukul 12.40 · dari meja terisi dan order aktif')).toBeInTheDocument()
    expect(within(crowd).getByText('Bali – Canggu (WITA)')).toBeInTheDocument()
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
      busyness_map: [], orders_per_hour: [], low_stock: [],
      busy_summary: { hours: [], orders: 0, share_pct: 0 }, quiet_summary: { hours: [], orders: 0, share_pct: 0 },
    })
    renderO2(fakeApi({ 'GET /owner/dashboard?period=today&hours=all': empty }))
    expect(await screen.findByText('Atur jam buka outlet untuk melihat peta keramaian.')).toBeInTheDocument()
    expect(screen.getByText('Belum ada order di periode ini.')).toBeInTheDocument()
    expect(screen.getByText('Semua stok aman.')).toBeInTheDocument()
  })

  it('shows an error when the summary cannot load', async () => {
    renderO2(fakeApi({ 'GET /owner/dashboard?period=today&hours=all': new Error('boom') }))
    expect(await screen.findByText(/Ringkasan belum bisa dimuat/)).toBeInTheDocument()
  })
})
