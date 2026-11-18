import { vi } from 'vitest'
import type { Session } from '../app/session'
import type { Api } from '../lib/api'
import type { Me } from '../lib/types'

export const OUTLETS: Me['outlets'] = [
  { id: 'o-dago', name: 'Bandung – Dago', timezone: 'Asia/Jakarta', order_prefix: 'A', payment_mode: 'open_bill' },
  { id: 'o-riau', name: 'Bandung – Riau', timezone: 'Asia/Jakarta', order_prefix: 'R', payment_mode: 'pay_first' },
]

export function fakeApi(routes: Record<string, unknown> = {}): Api & { calls: [string, string, unknown][] } {
  const calls: [string, string, unknown][] = []
  const handle = (method: string) => async (path: string, body?: unknown) => {
    calls.push([method, path, body])
    const key = `${method} ${path}`
    if (key in routes) {
      const value = routes[key]
      if (value instanceof Error) throw value
      return value
    }
    return undefined
  }
  return {
    calls,
    get: vi.fn(handle('GET')) as Api['get'],
    post: vi.fn(handle('POST')) as Api['post'],
    put: vi.fn(handle('PUT')) as Api['put'],
    patch: vi.fn(handle('PATCH')) as Api['patch'],
    del: vi.fn(handle('DELETE')) as Api['del'],
  }
}

export function fakeSession(role: 'owner' | 'staff', overrides: Partial<Session> = {}): Session {
  const me: Me = {
    user: { id: 'u1', email: role === 'owner' ? 'olga@kopisenja.id' : 'rina@kopisenja.id',
      display_name: role === 'owner' ? 'Olga' : 'Rina' },
    role,
    onboarding_required: false,
    tenant: { id: 't1', name: 'Kopi Senja', type: 'cafe' },
    outlets: role === 'owner' ? OUTLETS : OUTLETS.slice(0, 1),
  }
  return {
    me,
    role,
    api: fakeApi(),
    outlet: me.outlets[0],
    setOutletId: vi.fn(),
    reload: vi.fn(async () => {}),
    signOut: vi.fn(async () => {}),
    ...overrides,
  }
}

