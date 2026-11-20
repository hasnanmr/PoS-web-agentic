import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { ApiError } from '../lib/api'
import type { OwnerPick, ProductRow, RecommendationPreview } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import RecommendationsPage from './RecommendationsPage'

const pick = (id: string, name: string, tags: string[] = []): OwnerPick =>
  ({ product_id: id, name, category: null, is_active: true, tags })

const PICKS = [
  pick('p1', 'Es Kopi Susu Senja', ['coffee', 'sweet']),
  pick('p2', 'Matcha Latte', ['sweet']),
  pick('p3', 'Roti Bakar Cokelat', ['sweet', 'sharing']),
]

const PREVIEW: RecommendationPreview = {
  picks: [
    { product_id: 'p1', name: 'Es Kopi Susu Senja', position: 1, skipped_reason: null },
    { product_id: 'p2', name: 'Matcha Latte', position: 2, skipped_reason: null },
    { product_id: 'p3', name: 'Roti Bakar Cokelat', position: null, skipped_reason: 'sold_out' },
  ],
  best_sellers: [
    { product_id: 'p4', name: 'Americano', position: 3, skipped_reason: null, units_30d: 412 },
    { product_id: 'p1', name: 'Es Kopi Susu Senja', position: null, skipped_reason: 'duplicate', units_30d: 300 },
  ],
  listed_count: 3,
  max_items: 30,
}

const product = (id: string, name: string, status: ProductRow['status'] = 'active'): ProductRow => ({
  id, name, category: null, is_owner_pick: false, is_sample: false, has_photo: true, photo_url: null,
  addon_group_count: 0, ingredient_count: 0, price: 20000, status,
})

const routes = (extra: Record<string, unknown> = {}) => ({
  'GET /owner/owner-picks': PICKS,
  'GET /owner/tags': ['coffee', 'sharing', 'sweet'],
  'GET /owner/products': [
    ...PICKS.map((p) => product(p.product_id, p.name)),
    product('p4', 'Americano'),
    product('p5', 'Teh Tarik', 'inactive'),
  ],
  'GET /owner/outlets/o-dago/recommendation-preview': PREVIEW,
  ...extra,
})

function renderPage(api = fakeApi(routes())) {
  render(
    <MemoryRouter>
      <WithSession session={fakeSession('owner', { api })}><RecommendationsPage /></WithSession>
    </MemoryRouter>,
  )
  return api
}

describe('O7 Rekomendasi', () => {
  it('shows the picks with tags and the WhatsApp preview with skipped items', async () => {
    renderPage()
    expect(await screen.findByText('Es Kopi Susu Senja', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('Tag tersedia: coffee · sharing · sweet ·', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Seret ≡ untuk mengatur urutan.')).toBeInTheDocument()

    const card = (await screen.findByText('Preview menu Rekomendasi WhatsApp · Bandung – Dago')).closest('section')!
    const preview = within(card)
    expect(preview.getByText('1. Es Kopi Susu Senja')).toBeInTheDocument()
    expect(preview.getByText('— Roti Bakar Cokelat (dilewati: sold out)')).toBeInTheDocument()
    expect(preview.getByText('3. Americano · 412 unit')).toBeInTheDocument()
    expect(preview.getByText('— Es Kopi Susu Senja (duplikat, dihapus)')).toBeInTheDocument()
    expect(preview.getByText('Maks. 30 item · sold out dikecualikan · tanpa duplikat')).toBeInTheDocument()
  })

  it('removes a pick with ✕ and saves the new list', async () => {
    const api = renderPage()
    await userEvent.click(await screen.findByRole('button', { name: "Hapus Matcha Latte dari owner's picks" }))
    await waitFor(() => expect(api.calls).toContainEqual(['PUT', '/owner/owner-picks', { product_ids: ['p1', 'p3'] }]))
    // The preview is fetched again after the save.
    await waitFor(() => expect(api.calls.filter((c) => c[1].endsWith('recommendation-preview')).length).toBe(2))
  })

  it('reorders by dragging ≡ and with the arrow keys', async () => {
    const api = renderPage()
    const rows = await screen.findAllByRole('listitem')
    const first = rows.find((r) => within(r).queryByText('Es Kopi Susu Senja'))!
    const third = rows.find((r) => within(r).queryByText('Roti Bakar Cokelat'))!
    fireEvent.dragStart(first)
    fireEvent.drop(third)
    await waitFor(() => expect(api.calls).toContainEqual(['PUT', '/owner/owner-picks', { product_ids: ['p2', 'p3', 'p1'] }]))

    await userEvent.click(screen.getByRole('button', { name: 'Atur urutan Matcha Latte' }))
    await userEvent.keyboard('{ArrowUp}')
    await waitFor(() => expect(api.calls).toContainEqual(['PUT', '/owner/owner-picks', { product_ids: ['p2', 'p1', 'p3'] }]))
  })

  it('adds a pick from the products that are not picks yet (inactive ones are not offered)', async () => {
    const api = renderPage()
    await userEvent.click(await screen.findByRole('button', { name: "+ Tambah owner's pick" }))
    const select = screen.getByLabelText('Produk')
    expect(within(select).queryByRole('option', { name: 'Teh Tarik' })).not.toBeInTheDocument()
    expect(within(select).queryByRole('option', { name: 'Matcha Latte' })).not.toBeInTheDocument()
    await userEvent.selectOptions(select, 'Americano')
    await userEvent.click(screen.getByRole('button', { name: 'Tambah' }))
    await waitFor(() => expect(api.calls).toContainEqual(
      ['PUT', '/owner/owner-picks', { product_ids: ['p1', 'p2', 'p3', 'p4'] }]))
  })

  it('shows the error and keeps the server list when saving fails', async () => {
    const api = renderPage(fakeApi(routes({
      'PUT /owner/owner-picks': new ApiError(422, 'validation_failed', 'unknown product'),
    })))
    await userEvent.click(await screen.findByRole('button', { name: "Hapus Matcha Latte dari owner's picks" }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: "Hapus Matcha Latte dari owner's picks" })).toBeInTheDocument()
    expect(api.calls.some((c) => c[0] === 'PUT')).toBe(true)
  })
})
