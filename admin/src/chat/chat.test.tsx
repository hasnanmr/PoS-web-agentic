import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { todayIn } from '../lib/format'
import { fakeApi } from '../test/fakes'
import { ChatScreens, type HashLocation } from './ChatApp'
import type { ChatMenuItem, OrderStatus } from './types'

const SLUG = 'kopi-senja-dago'
const O = `/public/o/${SLUG}`
const TOKEN = 'tok_m05_0123456789abcdef'
const T = `/public/t/${TOKEN}`
const TODAY = todayIn('Asia/Jakarta')

const OUTLET = {
  name: 'Kopi Senja – Dago', short_name: 'KS', timezone: 'Asia/Jakarta',
  opening_hours: [1, 2, 3, 4, 5, 6, 7].map((weekday) => ({ weekday, opens_at: '08:00', closes_at: '22:00' })),
  is_open_now: true,
}
const PRIVACY = { version: '2026-11-20', url: '/privasi' }
const PAGE_O = { outlet: OUTLET, reservations_enabled: true, web_ordering: true, delivery_fee: 10000, agent_enabled: false, privacy_notice: PRIVACY }
const PAGE_T = { outlet: OUTLET, table: { name: 'M05', area: 'Indoor' }, web_ordering: true, agent_enabled: false, privacy_notice: PRIVACY, target: 'web', whatsapp_url: null }
const SESSION = { step: 'main_menu', cart: { lines: [] }, fulfillment: null, last_activity_at: null, cart_expired: false }

const KOPI: ChatMenuItem = {
  product_id: 'p-kopi', name: 'Es Kopi Susu Senja', category: 'Kopi', description: 'Espresso, susu, gula aren',
  is_owner_pick: true, price: 25000, photo_url: null, sold_out: false, sold_out_reason: null,
  addon_groups: [{
    id: 'g-susu', name: 'Pilih susu', selection: 'single', is_required: true,
    options: [
      { id: 'o-segar', name: 'Susu segar', price: 0, available: true },
      { id: 'o-oat', name: 'Oat milk', price: 5000, available: true },
    ],
  }],
}
const AMERICANO: ChatMenuItem = { ...KOPI, product_id: 'p-americano', name: 'Americano', description: null, addon_groups: [], price: 22000, is_owner_pick: false }
const CROISSANT: ChatMenuItem = { ...AMERICANO, product_id: 'p-cro', name: 'Croissant Butter', category: 'Makanan', sold_out: true }
const MENU = [KOPI, AMERICANO, CROISSANT]
const QUOTE = { lines: [], subtotal: 30000, pb1_rate_bps: 1000, pb1_amount: 3000, delivery_fee: 0, total: 33000 }

function status(over: Partial<OrderStatus> = {}): OrderStatus {
  return {
    id: 'ord-1', order_no: '#A-1050', created_at: '2026-11-21T05:41:00Z', fulfillment: 'pickup', customer_name: 'Rina',
    delivery_address: null, note: null, status: 'pending_payment', payment_status: 'unpaid', claimed_at: null,
    pay_by: '2026-11-21T05:56:00Z', items: [{ name: 'Es Kopi Susu Senja', quantity: 1, addons: ['Oat milk'], note: 'kurang manis', line_total: 30000 }],
    subtotal: 30000, pb1_amount: 3000, delivery_fee: 0, total: 33000, reject_reason: null, cancel_reason: null,
    events: [{ status: 'pending_payment', at: '2026-11-21T05:41:00Z' }], timezone: 'Asia/Jakarta', ...over,
  }
}

function memoryLocation(initial = ''): HashLocation & { value: string } {
  const loc = { value: initial, read: () => loc.value, write: (h: string) => { loc.value = h }, href: (h: string) => `https://x.test/o${h}` }
  return loc
}

function renderChat(routes: Record<string, unknown>, scope: 'o' | 't' = 'o', location = memoryLocation()) {
  const base = scope === 'o' ? O : T
  const api = fakeApi({
    [`GET ${base}`]: scope === 'o' ? PAGE_O : PAGE_T,
    [`GET ${base}/menu`]: MENU,
    [`GET ${base}/chat-session`]: SESSION,
    [`PUT ${base}/chat-session`]: SESSION,
    [`POST ${base}/orders/status`]: [],
    ...routes,
  })
  render(<ChatScreens api={api} apiBaseUrl="https://api.test"
    scope={scope === 'o' ? { kind: 'o', slug: SLUG } : { kind: 't', token: TOKEN }} location={location} />)
  return { api, location }
}

beforeEach(() => {
  localStorage.clear()
  URL.createObjectURL = vi.fn(() => 'blob:qris')
  URL.revokeObjectURL = vi.fn()
})

describe('C1 / C8 main menu', () => {
  it('shows the outlet greeting with reservations, and the header hours', async () => {
    renderChat({})
    expect(await screen.findByText(/Selamat datang di Kopi Senja – Dago/)).toBeInTheDocument()
    expect(screen.getByText('Buka · 08.00–22.00 · biasanya balas instan')).toBeInTheDocument()
    for (const label of [/Pesan$/, /Rekomendasi/, /Reservasi meja/, /Reservasi Saya/]) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })

  it('table QR: table greeting, only Pesan and Rekomendasi', async () => {
    renderChat({}, 't')
    expect(await screen.findByText(/Kamu di Meja 05 Kopi Senja – Dago/)).toBeInTheDocument()
    expect(screen.getByText('Meja 05 · Indoor · dine-in')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Reservasi/ })).not.toBeInTheDocument()
  })

  it('an old link shows friendly copy and nothing technical (C13)', async () => {
    renderChat({ [`GET ${O}`]: new ApiError(404, 'outlet_link_invalid', 'gone') })
    expect(await screen.findByText('Waduh, halamannya tidak ketemu 🙏')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/outlet_link_invalid|404|\/o\//)
  })

  it('a replaced table QR shows its own card', async () => {
    renderChat({ [`GET ${T}`]: new ApiError(404, 'table_qr_invalid', 'gone') }, 't')
    expect(await screen.findByText('QR ini sudah tidak bisa dipakai')).toBeInTheDocument()
  })

  it('an idle cart comes back empty with a card (C13)', async () => {
    renderChat({ [`GET ${O}/chat-session`]: { ...SESSION, cart_expired: true } })
    expect(await screen.findByText('Keranjangmu sudah kosong lagi')).toBeInTheDocument()
  })

  it('Pesanan Saya appears while this phone has an active order', async () => {
    localStorage.setItem('thinker.chat.orders.v1', JSON.stringify({
      [`o:${SLUG}`]: [{ order_id: 'ord-1', access_key: 'k'.repeat(40), order_no: '#A-1050', saved_at: new Date().toISOString() }],
    }))
    renderChat({ [`POST ${O}/orders/status`]: [{ order_id: 'ord-1', order_no: '#A-1050', fulfillment: 'delivery',
      status: 'preparing', payment_status: 'paid', total: 102400, created_at: '2026-11-21T05:41:00Z' }] })
    expect(await screen.findByRole('button', { name: /Pesanan Saya · #A-1050 disiapkan/ })).toBeInTheDocument()
  })
})

describe('C2–C6 ordering from the outlet link', () => {
  it('menu → required add-on → note → cart → pickup → details → summary → Pesan & bayar', async () => {
    const user = userEvent.setup()
    const { api, location } = renderChat({
      [`POST ${O}/quote`]: QUOTE,
      [`POST ${O}/orders`]: { order_id: 'ord-1', access_key: 'echo', order_no: '#A-1050', status: 'pending_payment',
        payment_status: 'unpaid', subtotal: 30000, pb1_amount: 3000, delivery_fee: 0, total: 33000, pay_by: '2026-11-21T05:56:00Z' },
      [`GET ${O}/orders/ord-1`]: status(),
      [`BLOB ${O}/orders/ord-1/qris`]: new Blob(['png']),
    })
    await user.click(await screen.findByRole('button', { name: /Pesan$/ }))
    const menu = await screen.findByRole('list', { name: 'Menu' })
    expect(within(menu).getByText('Habis')).toBeInTheDocument()
    expect(within(menu).queryByRole('button', { name: 'Tambah Croissant Butter' })).not.toBeInTheDocument()
    await user.click(within(menu).getByRole('button', { name: 'Tambah Es Kopi Susu Senja' }))

    // AC2.3: the required group must be answered first.
    expect(screen.getByRole('button', { name: 'Lanjut' })).toBeDisabled()
    await user.click(screen.getByRole('radio', { name: /Oat milk/ }))
    await user.click(screen.getByRole('button', { name: 'Lanjut' }))
    expect(await screen.findByText(/Catatan untuk dapur\?/)).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Ketik pesan' }), 'kurang manis{Enter}')
    expect(await screen.findByText(/Masuk keranjang: 1× Es Kopi Susu Senja \(Oat milk\) · ✎ kurang manis — Rp 30.000/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /3?1 item · Rp 30.000/ }))
    await user.click(await screen.findByRole('button', { name: /Ambil di outlet/ }))
    expect(screen.getByText(/dihapus otomatis setelah pesanan selesai atau batal/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Nama *'), 'Rina')
    await user.type(screen.getByLabelText('No HP * (tanpa OTP)'), '0812-3456-7221')
    await user.click(screen.getByRole('button', { name: 'Lanjut ke ringkasan' }))
    expect(await screen.findByText('Rp 33.000')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Pesan & bayar · Rp 33.000/ }))
    await waitFor(() => expect(api.calls.some(([m, p]) => m === 'POST' && p === `${O}/orders`)).toBe(true))
    const call = vi.mocked(api.post).mock.calls.find(([p]) => p === `${O}/orders`)!
    expect(call[1]).toEqual({
      items: [{ product_id: 'p-kopi', quantity: 1, addon_option_ids: ['o-oat'], note: 'kurang manis' }],
      fulfillment: 'pickup', privacy_notice_version: '2026-11-20', expected_total: 33000,
      customer: { name: 'Rina', phone: '0812-3456-7221' },
    })
    const headers = call[2] as Record<string, string>
    expect(headers['X-Order-Key'].length).toBeGreaterThanOrEqual(32)
    expect(headers['Idempotency-Key'].length).toBeGreaterThanOrEqual(32)
    expect(headers['X-Chat-Session']).toBeTruthy()

    // C6: exact total, deadline, and the fragment to come back to the order.
    expect(await screen.findByText(/Pesanan #A-1050 dibuat · 1 item · pickup/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Saya sudah bayar' })).toBeInTheDocument()
    expect(screen.getByText(/Bayar sebelum 12:56 \(15 menit\)/)).toBeInTheDocument()
    expect(location.value).toContain('order=ord-1')
  })

  it('a lost connection retries with the same keys, so only one order is made', async () => {
    const user = userEvent.setup()
    localStorage.setItem('thinker.chat.details.v1', JSON.stringify({ name: 'Rina', phone: '081234567221', address: '' }))
    const { api } = renderChat({
      [`GET ${O}/chat-session`]: { ...SESSION, step: 'summary', fulfillment: 'pickup',
        cart: { lines: [{ product_id: 'p-americano', quantity: 1, addon_option_ids: [], note: null }] } },
      [`POST ${O}/quote`]: QUOTE,
      [`POST ${O}/orders`]: new ApiError(0, 'network_error', 'x'),
    })
    await user.click(await screen.findByRole('button', { name: /Ambil di outlet/ }))
    expect(screen.getAllByText('dari HP ini')).toHaveLength(2) // name + phone prefilled from this phone
    await user.click(screen.getByRole('button', { name: 'Lanjut ke ringkasan' }))
    await user.click(await screen.findByRole('button', { name: /Pesan & bayar · Rp 33.000/ }))
    expect(await screen.findByText(/Sinyalnya lagi putus-putus/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Coba lagi' }))
    await waitFor(() => expect(vi.mocked(api.post).mock.calls.filter(([p]) => p === `${O}/orders`)).toHaveLength(2))
    const [first, second] = vi.mocked(api.post).mock.calls.filter(([p]) => p === `${O}/orders`)
    expect(second[2]).toEqual(first[2])
  })

  it('an item that sold out at confirm is named, and can be removed (C6)', async () => {
    const user = userEvent.setup()
    localStorage.setItem('thinker.chat.details.v1', JSON.stringify({ name: 'Rina', phone: '081234567221', address: '' }))
    renderChat({
      [`GET ${O}/chat-session`]: { ...SESSION, step: 'cart', fulfillment: 'pickup', cart: { lines: [
        { product_id: 'p-americano', quantity: 1, addon_option_ids: [], note: null },
        { product_id: 'p-kopi', quantity: 1, addon_option_ids: ['o-segar'], note: null },
      ] } },
      [`POST ${O}/quote`]: QUOTE,
      [`POST ${O}/orders`]: new ApiError(409, 'item_sold_out', 'x', { product_id: 'p-americano', name: 'Americano' }),
    })
    await user.click(await screen.findByRole('button', { name: /Ambil di outlet/ }))
    await user.click(screen.getByRole('button', { name: 'Lanjut ke ringkasan' }))
    await user.click(await screen.findByRole('button', { name: /Pesan & bayar/ }))
    expect(await screen.findByText(/Yah, Americano baru saja habis/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Hapus item & lanjut' }))
    await waitFor(() => expect(screen.queryByText(/1× Americano/)).not.toBeInTheDocument())
  })

  it('no static QRIS: menu without add buttons and the kasir note (C13)', async () => {
    const user = userEvent.setup()
    renderChat({ [`GET ${O}`]: { ...PAGE_O, web_ordering: false } })
    await user.click(await screen.findByRole('button', { name: /Pesan$/ }))
    expect(await screen.findByText(/pesanan dilayani langsung di kasir/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Tambah / })).not.toBeInTheDocument()
  })

  it('typing "menu" returns to the main menu and keeps the cart', async () => {
    const user = userEvent.setup()
    renderChat({})
    await user.click(await screen.findByRole('button', { name: /Pesan$/ }))
    await user.click(await screen.findByRole('button', { name: 'Tambah Americano' }))
    await user.click(screen.getByRole('button', { name: 'Tanpa catatan' }))
    await user.type(screen.getByRole('textbox', { name: 'Ketik pesan' }), 'menu{Enter}')
    expect(await screen.findByText(/Mau ngapain hari ini\?/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Pesan$/ }))
    expect(await screen.findByRole('button', { name: 'Tambah lagi Americano' })).toHaveTextContent('1 di keranjang')
  })
})

describe('C8 table order', () => {
  it('asks only a name and sends it with the privacy notice version', async () => {
    const user = userEvent.setup()
    const { api } = renderChat({
      [`GET ${T}/chat-session`]: { ...SESSION, step: 'cart', cart: { lines: [{ product_id: 'p-americano', quantity: 2, addon_option_ids: [], note: null }] } },
      [`POST ${T}/quote`]: { ...QUOTE, subtotal: 44000, pb1_amount: 4400, total: 48400 },
      [`POST ${T}/orders`]: new ApiError(409, 'web_ordering_unavailable', 'x'),
    }, 't')
    await user.click(await screen.findByRole('button', { name: 'Lanjut' }))
    expect(screen.queryByLabelText(/No HP/)).not.toBeInTheDocument()
    await user.type(screen.getByLabelText(/Nama untuk dipanggil staf/), 'Rina')
    await user.click(screen.getByRole('button', { name: 'Lanjut ke ringkasan' }))
    expect(await screen.findByText('Dine-in · Meja 05 · a.n. Rina')).toBeInTheDocument()
    await user.click(await screen.findByRole('button', { name: /Pesan & bayar · Rp 48.400/ }))
    await waitFor(() => expect(vi.mocked(api.post).mock.calls.some(([p]) => p === `${T}/orders`)).toBe(true))
    const call = vi.mocked(api.post).mock.calls.find(([p]) => p === `${T}/orders`)!
    expect(call[1]).toMatchObject({ customer_name: 'Rina', privacy_notice_version: '2026-11-20', expected_total: 48400 })
    expect(await screen.findByText(/pesanan dilayani langsung di kasir/)).toBeInTheDocument()
  })
})

describe('C7 status', () => {
  const saved = '#order=ord-1&key=' + 'k'.repeat(40) + '&no=%23A-1050'

  it('shows the live timeline after the claim', async () => {
    renderChat({ [`GET ${O}/orders/ord-1`]: status({ status: 'preparing', payment_status: 'paid', claimed_at: '2026-11-21T05:44:00Z',
      events: [{ status: 'pending_payment', at: '2026-11-21T05:41:00Z' }, { status: 'confirmed', at: '2026-11-21T05:47:00Z' },
        { status: 'preparing', at: '2026-11-21T05:48:00Z' }] }) }, 'o', memoryLocation(saved))
    expect(await screen.findByText('Pesanan #A-1050')).toBeInTheDocument()
    const timeline = screen.getByRole('list', { name: 'Status pesanan' })
    expect(within(timeline).getByText('Kamu bilang sudah bayar')).toBeInTheDocument()
    expect(within(timeline).getByText('Siap diambil')).toBeInTheDocument()
    expect(screen.getByText('● Live')).toBeInTheDocument()
  })

  it('a rejected payment explains it in plain words with the staff note', async () => {
    renderChat({ [`GET ${O}/orders/ord-1`]: status({ status: 'cancelled', reject_reason: 'Pembayaran tidak ditemukan' }) },
      'o', memoryLocation(saved))
    expect(await screen.findByText(/pembayaranmu belum kami temukan, jadi pesanan #A-1050 kami batalkan/)).toBeInTheDocument()
    expect(screen.getByText('Catatan dari staf: Pembayaran tidak ditemukan')).toBeInTheDocument()
  })
})

describe('C10–C12 reservations', () => {
  const avail = (times: { start_at: string; label: string }[]) => ({ date: TODAY, timezone: 'Asia/Jakarta', max_party_size: 6, last_date: TODAY, times })
  const BOOKING = {
    reservation_id: 'r1', booking_code: '7Q2KXM', start_at: `${TODAY}T11:30:00Z`, label: '18:30', timezone: 'Asia/Jakarta',
    party_size: 4, status: 'booked', guest_name: 'Rina', hold_until: `${TODAY}T11:45:00Z`, change_until: `${TODAY}T08:30:00Z`,
    can_change: true, reminder_at: `${TODAY}T09:30:00Z`, outlet_name: 'Kopi Senja – Dago',
  }

  it('party → date → time → name → Cek lagi → Konfirmasi booking → C11', async () => {
    const user = userEvent.setup()
    const { api } = renderChat({
      [`GET ${O}/availability?party_size=1&date=${TODAY}`]: avail([]),
      [`GET ${O}/availability?party_size=4&date=${TODAY}`]: avail([{ start_at: `${TODAY}T11:30:00Z`, label: '18:30' }]),
      [`POST ${O}/reservations`]: { ...BOOKING, access_key: 'echo' },
    })
    await user.click(await screen.findByRole('button', { name: /Reservasi meja/ }))
    await user.click(await screen.findByRole('button', { name: '4' }))
    await user.click(screen.getByRole('button', { name: /Hari ini/ }))
    await user.click(await screen.findByRole('button', { name: '18:30' }))
    await user.type(screen.getByLabelText('Nama'), 'Rina')
    await user.type(screen.getByLabelText('No HP'), '081234567221')
    await user.click(screen.getByRole('button', { name: 'Lanjut' }))
    expect(screen.getByText(/Cek lagi: Kopi Senja – Dago · .* · 18:30 WIB · 4 orang · a.n. Rina/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Konfirmasi booking' }))
    expect(await screen.findByText('7Q2KXM')).toBeInTheDocument()
    expect(screen.getByText(/Pengingat di kalender HP: 16:30 \(2 jam sebelum, setelan outlet\)/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Tambah ke kalender/ }).getAttribute('href'))
      .toMatch(/^https:\/\/api\.test\/api\/v1\/public\/o\/kopi-senja-dago\/reservations\/r1\/calendar\.ics\?key=/)
    const call = vi.mocked(api.post).mock.calls.find(([p]) => p === `${O}/reservations`)!
    expect((call[2] as Record<string, string>)['X-Booking-Key'].length).toBeGreaterThanOrEqual(32)
  })

  it('the 2-booking limit is explained without a code', async () => {
    const user = userEvent.setup()
    renderChat({
      [`GET ${O}/availability?party_size=1&date=${TODAY}`]: avail([]),
      [`GET ${O}/availability?party_size=2&date=${TODAY}`]: avail([{ start_at: `${TODAY}T11:30:00Z`, label: '18:30' }]),
      [`POST ${O}/reservations`]: new ApiError(409, 'booking_limit_reached', 'x'),
    })
    await user.click(await screen.findByRole('button', { name: /Reservasi meja/ }))
    await user.click(await screen.findByRole('button', { name: '2' }))
    await user.click(screen.getByRole('button', { name: /Hari ini/ }))
    await user.click(await screen.findByRole('button', { name: '18:30' }))
    await user.type(screen.getByLabelText('Nama'), 'Rina')
    await user.type(screen.getByLabelText('No HP'), '081234567221')
    await user.click(screen.getByRole('button', { name: 'Lanjut' }))
    await user.click(screen.getByRole('button', { name: 'Konfirmasi booking' }))
    expect(await screen.findByText(/Nomor ini sudah punya 2 reservasi yang akan datang/)).toBeInTheDocument()
  })

  it('Reservasi Saya: a wrong code or phone gets one friendly message', async () => {
    const user = userEvent.setup()
    renderChat({ [`POST ${O}/reservations/lookup`]: new ApiError(404, 'booking_not_found', 'x') })
    await user.click(await screen.findByRole('button', { name: /Reservasi Saya/ }))
    expect(await screen.findByText('Belum ada booking dari HP ini.')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Kode booking'), '7q2kxm')
    await user.type(screen.getByLabelText('No HP yang dipakai saat booking'), '081234567221')
    await user.click(screen.getByRole('button', { name: 'Cari booking' }))
    expect(await screen.findByText('Reservasinya tidak ketemu. Cek lagi kode booking dan nomor HP-nya ya.')).toBeInTheDocument()
  })
})
