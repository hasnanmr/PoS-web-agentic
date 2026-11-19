// Small UI pieces shared by the purchase-order screens (O15–O17, O16/S12, S10, S11).
import type { ReactNode } from 'react'
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

export function Dialog({ label, onClose, children, wide = false }: {
  label: string
  onClose: () => void
  children: ReactNode
  wide?: boolean
}) {
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-text/40 p-4 sm:items-center" role="dialog"
      aria-modal="true" aria-label={label} onKeyDown={(e) => e.key === 'Escape' && onClose()}>
      <div className={`max-h-[90vh] w-full overflow-y-auto rounded-lg border-2 border-primary bg-surface p-5 ${wide ? 'max-w-[680px]' : 'max-w-[620px]'}`}>
        {children}
      </div>
    </div>
  )
}
