// #73: F9 while the add-on popup is open does not submit the cart behind it.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import type { MenuItem } from '../lib/types'
import { fakeApi, fakeSession, OUTLETS } from '../test/fakes'
import { WithSession } from '../test/session'
import CounterPage from './CounterPage'

const KOPI: MenuItem = {
  product_id: 'p-kopi', name: 'Es Kopi Susu Senja', category: 'Kopi', is_owner_pick: true, price: 25000,
  photo_url: null, sold_out: false, sold_out_reason: null,
  addon_groups: [{ id: 'g-size', name: 'Ukuran', selection: 'single', is_required: true, options: [
    { id: 'o-reg', name: 'Regular', price: 0, available: true }] }],
}
const ROTI: MenuItem = { ...KOPI, product_id: 'p-roti', name: 'Roti Bakar', category: 'Makanan', is_owner_pick: false,
  price: 20000, addon_groups: [] }

describe('S1 Counter: F9 with the add-on popup open (#73)', () => {
  it('ignores F9 until the popup is closed', async () => {
    const shift = { id: 's1', drawer_id: 'd1', drawer_name: 'Kasir depan', drawer_number: 1,
      opened_at: '2026-11-18T01:00:00Z', starting_cash: 500000, opened_by: 'u1', opened_by_name: 'Rina' }
    const api = fakeApi({
      'GET /ops/outlets/o-dago/menu': [KOPI, ROTI],
      'GET /ops/outlets/o-dago/tables': [],
      'GET /ops/outlets/o-dago/shifts/current': [shift],
      'POST /ops/outlets/o-dago/quotes': { lines: [], subtotal: 20000, pb1_rate_bps: null, pb1_amount: 0, total: 20000 },
    })
    const outlet = { ...OUTLETS[0], payment_mode: 'pay_first' as const }
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api, outlet })}><CounterPage /></WithSession></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Tambah Roti Bakar' }))
    await userEvent.click(screen.getByRole('button', { name: '▤ Cash' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Buat order & terima bayar (F9)' })).toBeEnabled())

    await userEvent.click(screen.getByRole('button', { name: 'Tambah Es Kopi Susu Senja' }))
    expect(screen.getByRole('dialog', { name: 'Add-on Es Kopi Susu Senja' })).toBeInTheDocument()
    await userEvent.keyboard('{F9}')
    expect(screen.queryByRole('dialog', { name: 'Pembayaran cash' })).not.toBeInTheDocument()

    // Once the popup closes, F9 submits again.
    await userEvent.click(screen.getByRole('button', { name: 'Batal' }))
    await userEvent.keyboard('{F9}')
    expect(screen.getByRole('dialog', { name: 'Pembayaran cash' })).toBeInTheDocument()
  })
})
