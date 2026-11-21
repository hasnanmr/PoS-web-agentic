import { afterEach, describe, expect, it, vi } from 'vitest'
import { newKey } from './newKey'

afterEach(() => vi.unstubAllGlobals())

describe('newKey', () => {
  it('uses crypto.randomUUID when it exists', () => {
    vi.stubGlobal('crypto', { randomUUID: () => 'uuid-from-crypto' })
    expect(newKey()).toBe('uuid-from-crypto')
  })

  it('does not crash without crypto.randomUUID (old iOS Safari, in-app browsers, http)', () => {
    vi.stubGlobal('crypto', { getRandomValues: (a: Uint8Array) => a.fill(7) })
    expect(newKey()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })

  it('still works with no crypto at all, and gives different keys', () => {
    vi.stubGlobal('crypto', undefined)
    const a = newKey()
    expect(a.length).toBeGreaterThanOrEqual(8)
    expect(newKey()).not.toBe(a)
  })
})
