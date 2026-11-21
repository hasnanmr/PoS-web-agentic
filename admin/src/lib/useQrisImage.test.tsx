// #72: the QRIS image never points at a revoked URL, nor shows another outlet's QRIS.
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeApi, fakeSession } from '../test/fakes'
import { WithSession } from '../test/session'
import { useQrisImage } from './useQrisImage'

describe('useQrisImage (#72)', () => {
  const create = URL.createObjectURL
  const revoke = URL.revokeObjectURL
  afterEach(() => { URL.createObjectURL = create; URL.revokeObjectURL = revoke })

  it('keeps the old image until the new version loads, then revokes the old URL', async () => {
    let n = 0
    URL.createObjectURL = vi.fn(() => `blob:qris-${++n}`)
    const revoked: string[] = []
    URL.revokeObjectURL = vi.fn((u: string) => { revoked.push(u) })
    const pending: ((b: Blob) => void)[] = []
    const api = fakeApi()
    api.blob = vi.fn(() => new Promise<Blob>((resolve) => { pending.push(resolve) })) as typeof api.blob
    const wrapper = ({ children }: { children: ReactNode }) => (
      <WithSession session={fakeSession('owner', { api })}>{children}</WithSession>)
    const { result, rerender } = renderHook(({ outlet, version }) => useQrisImage(outlet, version),
      { wrapper, initialProps: { outlet: 'o-dago', version: 0 } })

    await act(async () => { pending[0](new Blob(['a'])) })
    expect(result.current.url).toBe('blob:qris-1')

    rerender({ outlet: 'o-dago', version: 1 })
    expect(result.current.url).toBe('blob:qris-1')
    expect(revoked).toEqual([])
    await act(async () => { pending[1](new Blob(['b'])) })
    await waitFor(() => expect(result.current.url).toBe('blob:qris-2'))
    expect(revoked).toEqual(['blob:qris-1'])

    // Another outlet: the previous outlet's QRIS is hidden right away.
    rerender({ outlet: 'o-riau', version: 1 })
    expect(result.current.url).toBeUndefined()
    await act(async () => { pending[2](new Blob(['c'])) })
    await waitFor(() => expect(result.current.url).toBe('blob:qris-3'))
  })
})
