import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import type { MenuItem } from '../lib/types'
import { fakeApi } from '../test/fakes'
import { TableScreens, type WebOrderStatus } from './TableApp'
import { loadOrders } from './storage'

const TOKEN = 'tok_m05_0123456789abcdef'
const BASE = `/public/t/${TOKEN}`

const PAGE = {
  outlet: { name: 'Kopi Senja – Dago', timezone: 'Asia/Jakarta' },
  table: { name: 'M05', area: 'Indoor' },
  target: 'web',
  web_ordering: true,
  whatsapp_url: null,
}

const AMERICANO: MenuItem = {
  product_id: 'p-americano', name: 'Americano', category: 'Kopi', is_owner_pick: false, price: 22000,
  photo_url: null, sold_out: false, sold_out_reason: null, addon_groups: [],
}
const KOPI: MenuItem = {
  product_id: 'p-kopi', name: 'Es Kopi Susu', category: 'Kopi', is_owner_pick: true, price: 25000, photo_url: null,
  sold_out: false, sold_out_reason: null,
  addon_groups: [{
    id: 'g-susu', name: 'Pilih susu', selection: 'single', is_required: true,
    options: [
      { id: 'o-segar', name: 'Susu segar', price: 0, available: true },
      { id: 'o-oat', name: 'Oat milk', price: 5000, available: true },
    ],
  }],
}
const CROISSANT: MenuItem = { ...AMERICANO, product_id: 'p-croissant', name: 'Croissant', category: 'Makanan', sold_out: true }
const MENU = [KOPI, AMERICANO, CROISSANT]

const QUOTE = {
  lines: [], subtotal: 44000, pb1_rate_bps: 1000, pb1_amount: 4400, total: 48400,
}

function status(over: Partial<WebOrderStatus> = {}): WebOrderStatus {
  return {
    id: 'ord-1', order_no: '#A-1050', created_at: '2026-11-20T05:41:00Z', customer_name: 'Rina', note: null,
    status: 'pending_payment', payment_status: 'unpaid', claimed_at: null, pay_by: '2026-11-20T05:56:00Z',
    items: [{ name: 'Americano', quantity: 2, addons: [], note: null, line_total: 44000 }],
    subtotal: 44000, pb1_amount: 4400, total: 48400, reject_reason: null, cancel_reason: null,
    events: [{ status: 'pending_payment', at: '2026-11-20T05:41:00Z' }], timezone: 'Asia/Jakarta',
    ...over,
  }
}

beforeEach(() => {
  localStorage.clear()
  window.history.replaceState(null, '', '/')
  URL.createObjectURL = vi.fn(() => 'blob:qris')
  URL.revokeObjectURL = vi.fn()
})

afterEach(() => vi.restoreAllMocks())

function renderPage(routes: Record<string, unknown>, redirect = vi.fn()) {
  const api = fakeApi({ [`GET ${BASE}`]: PAGE, [`GET ${BASE}/menu`]: MENU, ...routes })
  render(<TableScreens api={api} token={TOKEN} redirect={redirect} />)
  return { api, redirect }
}

describe('Q0 / Q1', () => {
  it('shows Q0 for an unknown or replaced token, with no menu', async () => {
    renderPage({ [`GET ${BASE}`]: new ApiError(404, 'table_qr_invalid', 'gone') })
    expect(await screen.findByText('QR ini sudah tidak berlaku.')).toBeInTheDocument()
    expect(screen.getByText('Minta QR baru ke staf.')).toBeInTheDocument()
    expect(screen.queryByText('Americano')).not.toBeInTheDocument()
  })

  it('offers web or WhatsApp when the outlet allows both', async () => {
    renderPage({
      [`GET ${BASE}`]: { ...PAGE, target: 'web_whatsapp', whatsapp_url: 'https://wa.me/62812?text=MEJA%20M05' },
    })
    expect(await screen.findByText('Mau pesan lewat mana?')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Pesan via WhatsApp/ })).toHaveAttribute('href', 'https://wa.me/62812?text=MEJA%20M05')
    await userEvent.click(screen.getByRole('button', { name: /Pesan di sini/ }))
    expect(await screen.findByText('Americano')).toBeInTheDocument()
  })

  it('goes straight to WhatsApp when the QR target is WhatsApp only', async () => {
    const { redirect } = renderPage({ [`GET ${BASE}`]: { ...PAGE, target: 'whatsapp', whatsapp_url: 'https://wa.me/62812' } })
    await waitFor(() => expect(redirect).toHaveBeenCalledWith('https://wa.me/62812'))
  })
})

describe('Q2 Menu / Q2a add-on', () => {
  it('marks sold-out items and requires the add-on group before adding', async () => {
    renderPage({})
    const croissant = (await screen.findByText('Croissant')).closest('li')!
    expect(within(croissant).getByText('Habis')).toBeInTheDocument()
    expect(within(croissant).queryByRole('button')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Tambah Es Kopi Susu' }))
    const add = screen.getByRole('button', { name: /Tambah ke pesanan · Rp 25.000/ })
    expect(add).toBeDisabled()
    await userEvent.click(screen.getByLabelText(/Oat milk/))
    await userEvent.type(screen.getByPlaceholderText('mis. kurang manis'), 'es sedikit')
    await userEvent.click(screen.getByRole('button', { name: 'Tambah Es Kopi Susu' })) // quantity 2
    await userEvent.click(screen.getByRole('button', { name: /Tambah ke pesanan · Rp 60.000/ }))
    expect(await screen.findByText(/2 item · Rp 60.000/)).toBeInTheDocument()
  })

  it('shows the menu only (no ordering) without a static QRIS', async () => {
    renderPage({ [`GET ${BASE}`]: { ...PAGE, web_ordering: false } })
    expect(await screen.findByText('Americano')).toBeInTheDocument()
    expect(screen.getByText(/Pesan dari HP belum tersedia/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Tambah Americano' })).not.toBeInTheDocument()
  })
})

describe('Q3 → Q4 → Q5', () => {
  it('orders, pays with the static QRIS and waits for staff', async () => {
    let current = status()
    const { api } = renderPage({
      [`POST ${BASE}/quote`]: QUOTE,
      [`POST ${BASE}/orders`]: { order_id: 'ord-1', access_key: 'key-1', order_no: '#A-1050', total: 48400, pay_by: current.pay_by },
      [`BLOB ${BASE}/orders/ord-1/qris`]: new Blob(['png'], { type: 'image/png' }),
    })
    api.get = vi.fn(async (path: string) => {
      if (path === BASE) return PAGE
      if (path === `${BASE}/menu`) return MENU
      if (path === `${BASE}/orders/ord-1`) return current
      throw new Error(path)
    }) as typeof api.get
    api.post = vi.fn(async (path: string, body?: unknown) => {
      api.calls.push(['POST', path, body])
      if (path === `${BASE}/quote`) return QUOTE
      if (path === `${BASE}/orders`) return { order_id: 'ord-1', access_key: 'key-1', order_no: '#A-1050', total: 48400, pay_by: current.pay_by }
      if (path === `${BASE}/orders/ord-1/payment-claim`) {
        current = status({ payment_status: 'proof_submitted', claimed_at: '2026-11-20T05:44:00Z' })
        return current
      }
      throw new Error(path)
    }) as typeof api.post

    await userEvent.click(await screen.findByRole('button', { name: 'Tambah Americano' }))
    await userEvent.click(screen.getByRole('button', { name: 'Tambah Americano' }))
    await userEvent.click(screen.getByRole('button', { name: /Lihat pesanan/ }))
    expect(await screen.findByText('Rp 4.400')).toBeInTheDocument() // PB1 from the server quote
    await userEvent.click(screen.getByRole('button', { name: '✎ + Catatan' }))
    await userEvent.type(screen.getByLabelText('Catatan Americano'), 'tanpa gula')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan' }))
    expect(screen.getByRole('button', { name: '✎ tanpa gula' })).toBeInTheDocument()
    await userEvent.type(screen.getByPlaceholderText(/mis. Rina/), 'Rina')
    await userEvent.click(screen.getByRole('button', { name: /Pesan & bayar · Rp 48.400/ }))

    const order = api.calls.find(([m, p]) => m === 'POST' && p === `${BASE}/orders`)!
    expect(order[2]).toMatchObject({
      items: [{ product_id: 'p-americano', quantity: 2, addon_option_ids: [], note: 'tanpa gula' }],
      customer_name: 'Rina', expected_total: 48400,
    })
    expect(vi.mocked(api.post).mock.calls.find(([p]) => p === `${BASE}/orders`)![2])
      .toMatchObject({ 'Idempotency-Key': expect.any(String) })
    expect(loadOrders(TOKEN).map((o) => o.order_no)).toEqual(['#A-1050'])

    // Q4: the outlet's static QRIS with the order key, total and deadline.
    expect(await screen.findByText('Bayar pesanan #A-1050')).toBeInTheDocument()
    expect(screen.getByText('Rp 48.400', { selector: 'span' })).toBeInTheDocument()
    expect(await screen.findByAltText(/QRIS Kopi Senja/)).toHaveAttribute('src', 'blob:qris')
    expect(screen.getByText(/Bayar sebelum 12:56/)).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith(`${BASE}/orders/ord-1`, { 'X-Order-Key': 'key-1' })

    await userEvent.click(screen.getByRole('button', { name: 'Saya sudah bayar' }))
    expect(await screen.findByText('◷ Menunggu konfirmasi staf')).toBeInTheDocument()
    expect(screen.getByText(/Terima kasih atas pembayarannya. Staf akan konfirmasi ke kamu setelah ini./)).toBeInTheDocument()
    expect(screen.getByLabelText('Pembayaran dikirim: sedang berjalan')).toBeInTheDocument()
    expect(screen.getByLabelText('Dikonfirmasi staf: belum')).toBeInTheDocument()
  })

  it('shows the staff rejection reason', async () => {
    localStorage.setItem('thinker.table-orders.v1', JSON.stringify({
      [TOKEN]: [{ order_id: 'ord-1', access_key: 'key-1', order_no: '#A-1050', saved_at: new Date().toISOString() }],
    }))
    renderPage({
      [`GET ${BASE}/orders/ord-1`]: status({ status: 'cancelled', reject_reason: 'Pembayaran tidak ditemukan' }),
    })
    await userEvent.click(await screen.findByRole('tab', { name: /Pesanan saya/ }))
    expect(await screen.findByText('✕ Pembayaran ditolak')).toBeInTheDocument()
    expect(screen.getByText('Pembayaran tidak ditemukan')).toBeInTheDocument()
  })
})

describe('refresh on the order page', () => {
  it('comes back to the same order from the URL fragment, even without saved site data', async () => {
    const location = { read: () => '#order=ord-1&key=key-1&no=%23A-1050', write: vi.fn() }
    const api = fakeApi({
      [`GET ${BASE}`]: PAGE,
      [`GET ${BASE}/menu`]: MENU,
      [`GET ${BASE}/orders/ord-1`]: status({ payment_status: 'proof_submitted', claimed_at: '2026-11-20T05:44:00Z' }),
    })
    render(<TableScreens api={api} token={TOKEN} redirect={vi.fn()} location={location} />)
    expect(await screen.findByText('◷ Menunggu konfirmasi staf')).toBeInTheDocument()
    expect(loadOrders(TOKEN).map((o) => o.order_id)).toEqual(['ord-1'])
    await userEvent.click(screen.getByRole('button', { name: '+ Pesan lagi' }))
    expect(location.write).toHaveBeenLastCalledWith('')
    expect(await screen.findByRole('tab', { name: 'Menu', selected: true })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: /Pesanan saya/ }))
    expect(await screen.findByText('◷ Menunggu konfirmasi staf')).toBeInTheDocument()
  })
})
