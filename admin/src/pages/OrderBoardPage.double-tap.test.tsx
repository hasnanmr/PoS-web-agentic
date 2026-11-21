// #71: a double tap on a forward action sends the transition once, with no false error.
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import type { Board, OrderCard } from '../lib/types'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import OrderBoardPage from './OrderBoardPage'

const CARD: OrderCard = {
  id: 'o1', order_no: '#A-1039', channel: 'counter', type: 'takeaway', payment_mode: 'pay_first', status: 'confirmed',
  payment_status: 'paid', payment_method: 'cash', payment_id: null, qris_checked: null, table: null, customer_name: null,
  note: null, proof_id: null, payment_claimed_at: null,
  item_summary: '1× Americano', total: 22000, bill_id: null, created_at: '2026-11-18T03:00:00Z',
  auto_cancel_at: null, allowed_actions: ['preparing', 'reversal'],
}
const EMPTY: Board = { awaiting_payment: [], confirmed: [], preparing: [], ready: [], done_today: [] }

describe('S2 Order Board: double tap (#71)', () => {
  it('sends "Mulai siapkan" once and keeps the button disabled while it runs', async () => {
    let release: (v: unknown) => void = () => {}
    const api = fakeApi({ 'GET /ops/outlets/o-dago/orders/board': { ...EMPTY, confirmed: [CARD] } })
    const base = api.post
    api.post = vi.fn(async (path: string, body?: unknown) => {
      if (path === '/ops/orders/o1/transitions') {
        api.calls.push(['POST', path, body])
        return new Promise((resolve) => { release = resolve })
      }
      return base(path, body)
    }) as typeof api.post
    render(<MemoryRouter><WithSession session={fakeSession('staff', { api })}><OrderBoardPage /></WithSession></MemoryRouter>)
    const column = await screen.findByRole('region', { name: 'CONFIRMED' })
    const start = within(column).getByRole('button', { name: 'Mulai siapkan →' })
    await userEvent.dblClick(start)
    expect(api.calls.filter(([m, p]) => m === 'POST' && p === '/ops/orders/o1/transitions')).toHaveLength(1)
    expect(start).toBeDisabled()
    await act(async () => { release({}) })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
