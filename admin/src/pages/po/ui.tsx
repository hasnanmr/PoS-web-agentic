// Small UI pieces shared by the purchase-order screens (O15–O17, O16/S12, S10, S11).
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from 'react'
import type { Tone } from './util'

const TONES: Record<Tone, string> = {
  primary: 'bg-primary-soft text-primary',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  teal: 'bg-teal-soft text-teal',
  muted: 'bg-page text-text-muted',
}

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-semibold ${TONES[tone]}`}>
      {children}
    </span>
  )
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Modal dialog: takes focus when it opens (so Escape works), keeps Tab inside, and gives focus
 * back to what had it when it closes. */
export function Dialog({ label, onClose, children, wide = false }: {
  label: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}) {
  const panel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null
    panel.current?.focus()
    return () => before?.focus?.()
  }, [])

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
      return
    }
    if (e.key !== 'Tab' || !panel.current) return
    const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)]
    if (items.length === 0) {
      e.preventDefault()
      return
    }
    const first = items[0]
    const last = items[items.length - 1]
    if (e.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-text/40 p-4 pb-[max(1rem,env(safe-area-inset-bottom))] sm:items-center" role="dialog"
      aria-modal="true" aria-label={label} onKeyDown={onKeyDown}>
      <div ref={panel} tabIndex={-1}
        className={`max-h-[90dvh] w-full overflow-y-auto rounded-lg border-2 border-primary bg-surface p-5 outline-none ${wide ? 'max-w-[680px]' : 'max-w-[620px]'}`}>
        {children}
      </div>
    </div>
  )
}
