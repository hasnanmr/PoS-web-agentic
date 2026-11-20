import { afterEach, describe, expect, it, vi } from 'vitest'
import { resizeImage } from './resizeImage'

function stubBrowser(width: number, height: number, output: Blob | null) {
  const drawImage = vi.fn()
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ({ fillStyle: '', fillRect: vi.fn(), drawImage }),
    toBlob: (cb: (b: Blob | null) => void) => cb(output),
  }
  const close = vi.fn()
  vi.stubGlobal('createImageBitmap', vi.fn(async () => ({ width, height, close })))
  vi.spyOn(document, 'createElement').mockReturnValue(canvas as unknown as HTMLCanvasElement)
  return { canvas, close }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('resizeImage', () => {
  const big = new Blob(['x'.repeat(5000)], { type: 'image/png' })
  const small = new Blob(['jpeg'], { type: 'image/jpeg' })

  it('scales the longest side down to 800 px and returns the JPEG', async () => {
    const { canvas, close } = stubBrowser(4000, 3000, small)
    expect(await resizeImage(big)).toBe(small)
    expect([canvas.width, canvas.height]).toEqual([800, 600])
    expect(close).toHaveBeenCalled()
  })

  it('does not enlarge a small picture', async () => {
    const { canvas } = stubBrowser(400, 300, small)
    await resizeImage(big)
    expect([canvas.width, canvas.height]).toEqual([400, 300])
  })

  it('keeps the original when the result is not smaller or the browser cannot encode', async () => {
    stubBrowser(400, 300, new Blob(['x'.repeat(9000)], { type: 'image/jpeg' }))
    expect(await resizeImage(big)).toBe(big)
    stubBrowser(400, 300, null)
    expect(await resizeImage(big)).toBe(big)
  })

  it('keeps the original when the browser cannot decode it', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn(async () => { throw new Error('bad image') }))
    expect(await resizeImage(big)).toBe(big)
  })
})
