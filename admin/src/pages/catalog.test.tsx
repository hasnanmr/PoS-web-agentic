import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import type { ProductDetail, ProductRow, StockResponse } from '../lib/types'
import { formatQty, plainQuantity } from '../lib/format'
import MenuPage from './MenuPage'
import RecipesPage from './RecipesPage'
import StockPage from './StockPage'

const STOCK: StockResponse = {
  counts: { low: 1, out: 1 },
  items: [
    { stock_item_id: 'kopi', name: 'Biji kopi house blend', unit: 'g', display_unit: 'kg', on_hand: '2400.000',
      low_threshold: '1000.000', status: 'ok', affected_products: [] },
    { stock_item_id: 'matcha', name: 'Bubuk matcha', unit: 'g', display_unit: 'g', on_hand: '180.000',
      low_threshold: '200.000', status: 'low', affected_products: [{ name: 'Matcha Latte', kind: 'product', sold_out: false }] },
    { stock_item_id: 'croissant', name: 'Croissant (frozen)', unit: 'pcs', display_unit: 'pcs', on_hand: '0.000',
      low_threshold: '10.000', status: 'out', affected_products: [{ name: 'Croissant Butter', kind: 'product', sold_out: true }] },
  ],
}

describe('format', () => {
  it('shows quantities like the wireframe', () => {
    expect(formatQty('2400', 'g', 'kg')).toBe('2,4 kg')
    expect(formatQty('800', 'ml', 'L')).toBe('0,8 L')
    expect(formatQty('180', 'g', 'g')).toBe('180 g')
    expect(formatQty('140', 'pcs', 'pcs')).toBe('140 pcs')
  })

  it('shows decimal strings from the API as editable id-ID text without rounding', () => {
    expect(plainQuantity('125.000')).toBe('125')
    expect(plainQuantity('0.125')).toBe('0,125')
    expect(plainQuantity('10.050')).toBe('10,05')
    expect(plainQuantity('999999999.123')).toBe('999999999,123')
  })
})

describe('S7 Stok', () => {
  it('loads older movements with "Muat lagi"', async () => {
    const move = (id: number) => ({ id, at: '2026-11-18T03:00:00Z', type: 'restock', quantity: '100', unit: 'g',
      display_unit: 'g', stock_item: `Bahan ${id}`, order_no: null, note: null, actor_type: 'user', actor: 'Rina' })
    const api = fakeApi({
      'GET /ops/outlets/o-dago/stock': STOCK,
      'GET /ops/outlets/o-dago/stock-movements?limit=20': { items: [move(2)], next_cursor: 2 },
      'GET /ops/outlets/o-dago/stock-movements?limit=20&cursor=2': { items: [move(1)], next_cursor: null },
    })
    render(<WithSession session={fakeSession('staff', { api })}><StockPage /></WithSession>)
    await userEvent.click(await screen.findByRole('button', { name: 'Muat lagi' }))
    expect(await screen.findByText(/bahan 1/)).toBeInTheDocument()
    expect(screen.getByText(/bahan 2/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Muat lagi' })).not.toBeInTheDocument()
  })

  it('shows levels, filters, and records a restock in the display unit', async () => {
    const api = fakeApi({
      'GET /ops/outlets/o-dago/stock': STOCK,
      'GET /ops/outlets/o-dago/stock-movements?limit=20': { items: [] },
    })
    render(<WithSession session={fakeSession('staff', { api })}><StockPage /></WithSession>)
    expect(await screen.findByText('2,4 kg')).toBeInTheDocument()
    expect(screen.getByText('Croissant Butter SOLD OUT')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Habis (1)' }))
    expect(screen.queryByText('Biji kopi house blend', { selector: 'td' })).not.toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Bahan'), 'kopi')
    await userEvent.type(screen.getByLabelText('Jumlah & satuan'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan movement' }))
    await waitFor(() => expect(api.calls).toContainEqual(['POST', '/ops/outlets/o-dago/stock-movements', {
      type: 'restock', stock_item_id: 'kopi', quantity: '2000', note: null }]))
  })
})

const ROWS: ProductRow[] = [
  { id: 'p1', name: 'Es Kopi Susu Senja', category: 'Kopi', is_owner_pick: true, is_sample: true, has_photo: false, photo_url: null,
    addon_group_count: 1, ingredient_count: 4, price: 25000, status: 'active' },
]
const DETAIL: ProductDetail = {
  id: 'p1', name: 'Es Kopi Susu Senja', category: 'Kopi', description: 'Espresso, susu segar & gula aren',
  is_owner_pick: true, is_active: true, is_sample: true, has_photo: false, photo_url: null, tags: ['coffee', 'sweet'],
  prices: [{ outlet_id: 'o-dago', outlet_name: 'Bandung – Dago', price: 25000 },
    { outlet_id: 'o-riau', outlet_name: 'Bandung – Riau', price: null }],
  addon_groups: [{ id: 'g1', name: 'Ukuran', selection: 'single', is_required: true, sort_order: 1, options: [
    { id: 'large', name: 'Large', sort_order: 2, prices: [{ outlet_id: 'o-dago', price: 5000 }],
      recipe: [{ stock_item_id: 'kopi', stock_item: 'Biji kopi', unit: 'g', quantity: '6.000' }] }] }],
  catalog_sync: 'not_configured',
}

describe('O5 Menu & Add-on', () => {
  it('lists items and saves fields and per-outlet prices', async () => {
    const api = fakeApi({ 'GET /owner/products?price_outlet_id=o-dago': ROWS, 'GET /owner/products/p1': DETAIL })
    render(<MemoryRouter><WithSession session={fakeSession('owner', { api })}><MenuPage /></WithSession></MemoryRouter>)
    expect(await screen.findByText('Rp 25.000 · Aktif')).toBeInTheDocument()
    expect(await screen.findByText(/Large\s+\+Rp 5\.000 \(Dago\)/)).toBeInTheDocument()
    expect(screen.getByText(/REQUIRED/)).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Harga Bandung – Riau'), '27000')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan & sync katalog' }))
    await waitFor(() => expect(api.calls).toContainEqual(['PUT', '/owner/products/p1/prices', [
      { outlet_id: 'o-dago', price: 25000 }, { outlet_id: 'o-riau', price: 27000 }]]))
    expect(api.calls.find(([m, p]) => m === 'PATCH' && p === '/owner/products/p1')?.[2]).toMatchObject({
      tags: ['coffee', 'sweet'], is_owner_pick: true })
  })
})

describe('O5 Foto menu (T-132)', () => {
  const inactive: ProductDetail = { ...DETAIL, is_active: false, is_sample: false }

  it('uploads a photo, shows it, and only then allows switching the item on', async () => {
    const withPhoto: ProductDetail = { ...inactive, has_photo: true, photo_url: 'https://signed.test/p1.png' }
    const api = fakeApi({
      'GET /owner/products?price_outlet_id=o-dago': [{ ...ROWS[0], status: 'inactive' }],
      'GET /owner/products/p1': inactive,
      'UPLOAD /owner/products/p1/photo': withPhoto,
    })
    render(<MemoryRouter><WithSession session={fakeSession('owner', { api })}><MenuPage /></WithSession></MemoryRouter>)
    const toggle = await screen.findByRole('switch')
    expect(toggle).toBeDisabled()
    expect(screen.getByText('Tambahkan foto untuk mengaktifkan item ini.')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Deskripsi'), ' & es')
    const file = new File(['png'], 'kopi.png', { type: 'image/png' })
    await userEvent.upload(screen.getByLabelText('Foto menu'), file)
    expect(await screen.findByAltText('Foto Es Kopi Susu Senja')).toHaveAttribute('src', 'https://signed.test/p1.png')
    expect(api.calls).toContainEqual(['UPLOAD', '/owner/products/p1/photo', file])
    expect(await screen.findByText('Foto disimpan.')).toBeInTheDocument()
    expect(screen.getByRole('switch')).toBeEnabled()
    expect(screen.getByLabelText('Deskripsi')).toHaveValue('Espresso, susu segar & gula aren & es') // draft kept
  })

  it('refuses other file types and large files before uploading', async () => {
    const api = fakeApi({ 'GET /owner/products?price_outlet_id=o-dago': ROWS, 'GET /owner/products/p1': inactive })
    render(<MemoryRouter><WithSession session={fakeSession('owner', { api })}><MenuPage /></WithSession></MemoryRouter>)
    const input = await screen.findByLabelText('Foto menu')
    await userEvent.upload(input, new File(['x'.repeat(6 * 1024 * 1024)], 'big.jpg', { type: 'image/jpeg' }))
    expect(await screen.findByText('Foto harus JPG, PNG, atau WebP, maks 5 MB.')).toBeInTheDocument()
    expect(api.calls.some(([m]) => m === 'UPLOAD')).toBe(false)
  })

  it('shows list thumbnails from photo_url', async () => {
    const api = fakeApi({
      'GET /owner/products?price_outlet_id=o-dago': [{ ...ROWS[0], has_photo: true, photo_url: 'https://signed.test/t.webp' }],
      'GET /owner/products/p1': DETAIL,
    })
    const { container } = render(<MemoryRouter><WithSession session={fakeSession('owner', { api })}><MenuPage /></WithSession></MemoryRouter>)
    await screen.findByText('Rp 25.000 · Aktif')
    expect(container.querySelector('img[src="https://signed.test/t.webp"]')).not.toBeNull()
  })
})

describe('O5 add-on group editor', () => {
  it('keeps an unpriced option unpriced (null), not Rp 0', async () => {
    const detail: ProductDetail = { ...DETAIL, addon_groups: [{ ...DETAIL.addon_groups[0], options: [
      { id: 'large', name: 'Large', sort_order: 1, prices: [], recipe: [] }] }] }
    const api = fakeApi({ 'GET /owner/products?price_outlet_id=o-dago': ROWS, 'GET /owner/products/p1': detail })
    render(<MemoryRouter><WithSession session={fakeSession('owner', { api })}><MenuPage /></WithSession></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Ubah grup Ukuran' }))
    expect(screen.getByLabelText('Harga opsi 1')).toHaveValue('')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan grup' }))
    await waitFor(() => expect(api.calls.find(([m, p]) => m === 'PATCH' && p === '/owner/addon-groups/g1')?.[2])
      .toMatchObject({ options: [{ id: 'large', name: 'Large', prices: [{ outlet_id: 'o-dago', price: null }] }] }))
  })

  it('asks before deleting an item', async () => {
    const api = fakeApi({ 'GET /owner/products?price_outlet_id=o-dago': ROWS, 'GET /owner/products/p1': DETAIL })
    render(<MemoryRouter><WithSession session={fakeSession('owner', { api })}><MenuPage /></WithSession></MemoryRouter>)
    await userEvent.click(await screen.findByText('✕ Hapus item'))
    expect(api.calls.some(([m]) => m === 'DELETE')).toBe(false)
    expect(screen.getByText(/Hapus "Es Kopi Susu Senja"\?/)).toBeInTheDocument()
  })
})

describe('O6 Resep & Bahan', () => {
  it('keeps the recipe editable when only availability fails', async () => {
    const api = fakeApi({
      'GET /owner/stock-items': [{ id: 'kopi', name: 'Biji kopi house blend', unit: 'g', display_unit: 'kg', thresholds: [] }],
      'GET /owner/products': ROWS,
      'GET /owner/products/p1': DETAIL,
      'GET /owner/products/p1/recipe': [{ stock_item_id: 'kopi', stock_item: 'Biji kopi house blend', unit: 'g', quantity: '18.000' }],
      'GET /owner/products/p1/availability': new Error('boom'),
    })
    render(<WithSession session={fakeSession('owner', { api })}><RecipesPage /></WithSession>)
    expect(await screen.findByRole('button', { name: 'Simpan resep' })).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('shows the recipe, availability, and saves', async () => {
    const api = fakeApi({
      'GET /owner/stock-items': [
        { id: 'kopi', name: 'Biji kopi house blend', unit: 'g', display_unit: 'kg', thresholds: [] },
        { id: 'cup', name: 'Cup 16oz', unit: 'pcs', display_unit: 'pcs', thresholds: [] }],
      'GET /owner/products': ROWS,
      'GET /owner/products/p1': DETAIL,
      'GET /owner/products/p1/recipe': [{ stock_item_id: 'kopi', stock_item: 'Biji kopi house blend', unit: 'g', quantity: '18.000' }],
      'GET /owner/products/p1/availability': [
        { outlet_id: 'o-dago', outlet_name: 'Dago', portions_available: 133, sold_out: false, limiting_stock_item: null },
        { outlet_id: 'o-riau', outlet_name: 'Riau', portions_available: 0, sold_out: true, limiting_stock_item: 'Susu UHT' }],
    })
    render(<WithSession session={fakeSession('owner', { api })}><RecipesPage /></WithSession>)
    expect(await screen.findByText('Resep: Es Kopi Susu Senja (1 porsi)')).toBeInTheDocument()
    expect(await screen.findByText(/Dago: tersedia 133 porsi/)).toBeInTheDocument()
    expect(screen.getByText(/Riau: SOLD OUT \(susu uht habis\)/)).toBeInTheDocument()
    expect(screen.getByText('+ 6 g biji kopi')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '+ Tambah bahan' }))
    await userEvent.selectOptions(screen.getByLabelText('Bahan 2'), 'cup')
    await userEvent.type(screen.getByLabelText('Jumlah 2'), '1')
    await userEvent.click(screen.getByRole('button', { name: 'Simpan resep' }))
    await waitFor(() => expect(api.calls).toContainEqual(['PUT', '/owner/products/p1/recipe', [
      { stock_item_id: 'kopi', quantity: '18' }, { stock_item_id: 'cup', quantity: '1' }]]))
  })
})
