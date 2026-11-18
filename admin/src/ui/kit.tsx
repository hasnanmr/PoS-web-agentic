// Small building blocks matching the wireframe look (cards, labelled fields, buttons).
// Tokens come from index.css; sizes follow CLAUDE.md (13px labels/body, 16–20px headings).
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

export function Card({ title, actions, children, className = '' }: {
  title?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`rounded-lg border border-border bg-surface p-4 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-[13px] font-semibold text-text">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

/** Label on the left, control on the right (O3 "Umum" layout); stacks on mobile. */
export function FieldRow({ label, htmlFor, children, hint }: {
  label: string
  htmlFor?: string
  children: ReactNode
  hint?: ReactNode
}) {
  return (
    <div className="grid gap-1 py-1.5 sm:grid-cols-[140px_1fr] sm:items-center sm:gap-3">
      <label htmlFor={htmlFor} className="text-[12px] text-text-muted">
        {label}
      </label>
      <div className="min-w-0">
        {children}
        {hint && <p className="mt-1 text-[11px] text-text-muted">{hint}</p>}
      </div>
    </div>
  )
}

/** Label above the control (O1, O4 forms). */
export function Field({ label, htmlFor, children, hint }: {
  label: string
  htmlFor?: string
  children: ReactNode
  hint?: ReactNode
}) {
  return (
    <div className="mb-3">
      <label htmlFor={htmlFor} className="mb-1 block text-[13px] font-semibold text-text">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-[11px] text-text-muted">{hint}</p>}
    </div>
  )
}

const control =
  'h-9 w-full rounded-md border border-border bg-surface px-2.5 text-[13px] text-text ' +
  'placeholder:text-text-muted focus:border-primary focus:outline-none disabled:bg-page'

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${control} ${props.className ?? ''}`} />
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${control} ${props.className ?? ''}`} />
}

type Variant = 'action' | 'primary' | 'ghost' | 'danger'
const VARIANTS: Record<Variant, string> = {
  action: 'bg-action text-white hover:opacity-90',
  primary: 'bg-primary text-white hover:opacity-90',
  ghost: 'border border-border bg-surface text-text hover:bg-page',
  danger: 'border border-danger bg-surface text-danger hover:bg-danger-soft',
}

export function Button({ variant = 'primary', className = '', ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex h-9 items-center justify-center gap-1.5 rounded-md px-3 text-[13px] font-semibold disabled:cursor-not-allowed disabled:opacity-60 ${VARIANTS[variant]} ${className}`}
    />
  )
}

export function LinkButton({ className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className={`text-[13px] font-medium text-primary hover:underline disabled:opacity-60 ${className}`}
    />
  )
}

export function Alert({ tone = 'danger', children }: { tone?: 'danger' | 'success' | 'info'; children: ReactNode }) {
  const tones = {
    danger: 'bg-danger-soft text-danger',
    success: 'bg-success-soft text-success',
    info: 'bg-primary-soft text-text',
  }
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={`rounded-md px-3 py-2 text-[12px] ${tones[tone]}`}>
      {children}
    </div>
  )
}

export function StatusDot({ tone, children }: { tone: 'success' | 'muted' | 'warning' | 'danger'; children: ReactNode }) {
  const color = { success: 'text-success', muted: 'text-text-muted', warning: 'text-warning', danger: 'text-danger' }[tone]
  return <span className={`text-[12px] ${color}`}>{children}</span>
}

export function Loading({ label = 'Memuat…' }: { label?: string }) {
  return <p className="p-6 text-[13px] text-text-muted">{label}</p>
}
