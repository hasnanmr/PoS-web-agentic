import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import type { TopItems } from '../lib/types'
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
    await waitFor(() => expect(api.calls.map((c) => c[1])).toEqual([
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
