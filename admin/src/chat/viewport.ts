// Keeps the web chat shell (page 07) inside the part of the screen the customer can really see.
// When the on-screen keyboard opens, phones shrink only the *visual* viewport: Chrome on Android
// (Galaxy S25) and Safari on iPhone leave `100dvh` as it was, so the text box and the newest
// bubbles end up behind the keyboard or the header slides off the top. Here the shell takes the
// visual viewport's height and position, so header, conversation, and text box always fit above
// the keyboard.
import { useEffect, type RefObject } from 'react'

/** Below this the height change is a browser toolbar, not a keyboard. */
const KEYBOARD_MIN_PX = 120

export function fitToVisualViewport(el: HTMLElement, vv: Pick<VisualViewport, 'height' | 'offsetTop' | 'scale'>, fullHeight: number) {
  // Pinch-zoomed: leave the page alone, the customer is looking at a detail.
  if (vv.scale > 1.01) return
  el.style.height = `${Math.round(vv.height)}px`
  // iPhone moves the visible area down the page instead of resizing it; follow it.
  el.style.transform = vv.offsetTop > 0.5 ? `translateY(${Math.round(vv.offsetTop)}px)` : ''
  el.dataset.keyboard = fullHeight - vv.height > KEYBOARD_MIN_PX ? 'open' : 'closed'
}

/**
 * Sizes `ref` to the visible viewport and calls `onShrink` when it gets smaller (keyboard
 * opened), so the caller can keep the newest bubble in view.
 */
export function useVisualViewport(ref: RefObject<HTMLElement | null>, onShrink: () => void) {
  useEffect(() => {
    const vv = window.visualViewport
    const el = ref.current
    if (!vv || !el) return

    // Chrome on Android: let the keyboard resize the page itself (smoother than following it
    // from script). Other browsers ignore this and use the listeners below.
    const meta = document.querySelector<HTMLMetaElement>('meta[name="viewport"]')
    const before = meta?.content
    if (meta && before !== undefined && !before.includes('interactive-widget')) {
      meta.content = `${before}, interactive-widget=resizes-content`
    }

    // The tallest the viewport has been: with the keyboard open Chrome also shrinks innerHeight.
    let full = Math.max(window.innerHeight, vv.height)
    let last = vv.height
    let frame = 0
    const apply = () => {
      frame = 0
      full = Math.max(full, window.innerHeight, vv.height)
      fitToVisualViewport(el, vv, full)
      if (vv.height < last - 1) onShrink()
      last = vv.height
    }
    const schedule = () => { if (!frame) frame = window.requestAnimationFrame(apply) }
    const rotate = () => { full = 0; schedule() }
    apply()
    vv.addEventListener('resize', schedule)
    vv.addEventListener('scroll', schedule)
    window.addEventListener('orientationchange', rotate)
    return () => {
      if (frame) window.cancelAnimationFrame(frame)
      vv.removeEventListener('resize', schedule)
      vv.removeEventListener('scroll', schedule)
      window.removeEventListener('orientationchange', rotate)
      el.style.height = ''
      el.style.transform = ''
      delete el.dataset.keyboard
      if (meta && before !== undefined) meta.content = before
    }
    // onShrink is read at call time through the closure of the first render; callers pass a stable ref reader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref])
}
