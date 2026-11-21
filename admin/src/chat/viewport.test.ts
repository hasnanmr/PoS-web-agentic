import { describe, expect, it } from 'vitest'
import { fitToVisualViewport } from './viewport'

describe('web chat shell and the on-screen keyboard', () => {
  it('takes the visible height when the keyboard opens (Chrome on Android)', () => {
    const el = document.createElement('div')
    fitToVisualViewport(el, { height: 420.4, offsetTop: 0, scale: 1 }, 780)
    expect(el.style.height).toBe('420px')
    expect(el.style.transform).toBe('')
    expect(el.dataset.keyboard).toBe('open')
  })

  it('follows the visible area when iPhone Safari moves it down the page', () => {
    const el = document.createElement('div')
    fitToVisualViewport(el, { height: 410, offsetTop: 96, scale: 1 }, 760)
    expect(el.style.transform).toBe('translateY(96px)')
  })

  it('treats a browser toolbar change as no keyboard, and goes back to full height', () => {
    const el = document.createElement('div')
    fitToVisualViewport(el, { height: 420, offsetTop: 0, scale: 1 }, 780)
    fitToVisualViewport(el, { height: 724, offsetTop: 0, scale: 1 }, 780)
    expect(el.style.height).toBe('724px')
    expect(el.dataset.keyboard).toBe('closed')
  })

  it('leaves the page alone while pinch-zoomed', () => {
    const el = document.createElement('div')
    fitToVisualViewport(el, { height: 300, offsetTop: 40, scale: 2 }, 780)
    expect(el.style.height).toBe('')
  })
})
