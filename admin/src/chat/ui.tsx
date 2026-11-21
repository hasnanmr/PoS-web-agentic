// Building blocks of the web chat shell (page 07): navy header with the outlet avatar, outlet
// bubbles on the left, the customer's replies on the right (primary), full-width choice
// buttons, the orange action bar, and the bottom bar ("☰ Menu utama" + text box + ➤).
import type { ButtonHTMLAttributes, FormEvent, ReactNode } from 'react'
import { useState } from 'react'

export function ChatHeader({ initials, title, subtitle }: { initials: string; title: string; subtitle: string }) {
  return (
    <header className="sticky top-0 z-10 flex items-center gap-3 bg-primary px-3 py-2.5 text-white">
      <span aria-hidden="true"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-[13px] font-bold text-primary">
        {initials}
      </span>
      <div className="min-w-0">
        <h1 className="truncate text-[15px] font-semibold leading-tight">{title}</h1>
        <p className="truncate text-[11px] text-white/80">{subtitle}</p>
      </div>
    </header>
  )
}

/** A message from the outlet (left). */
export function Bubble({ children, tone = 'plain', label }: {
  children: ReactNode; tone?: 'plain' | 'success' | 'danger' | 'warning' | 'info'; label?: string
}) {
  const tones = {
    plain: 'bg-surface border-border',
    success: 'bg-success-soft border-transparent text-success',
    danger: 'bg-danger-soft border-danger/30 text-danger',
    warning: 'bg-warning-soft border-transparent text-warning',
    info: 'bg-primary-soft border-transparent',
  }
  return (
    <div className={`max-w-[92%] rounded-xl border px-3 py-2.5 text-[13px] ${tones[tone]}`} role={tone === 'danger' ? 'alert' : undefined}>
      {label && <p className="mb-1 text-[11px] font-semibold text-text-muted">{label}</p>}
      {children}
    </div>
  )
}

/** The customer's own reply (right). */
export function Mine({ children }: { children: ReactNode }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[80%] rounded-xl bg-primary px-3 py-2 text-[13px] text-white">{children}</p>
    </div>
  )
}

/** A full-width choice in an outlet message (C1 main menu, C4 pickup/delivery…). */
export function Choice({ selected = false, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean }) {
  return (
    <button type="button" aria-pressed={selected || undefined}
      className={`w-full rounded-lg border px-3 py-2.5 text-left text-[13px] font-semibold disabled:opacity-50 ${
        selected ? 'border-primary bg-primary-soft text-primary' : 'border-primary bg-surface text-primary'} ${className}`}
      {...props} />
  )
}

/** A small pill (categories C2, party size / date / time C10). */
export function Chip({ selected = false, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean }) {
  return (
    <button type="button" aria-pressed={selected}
      className={`rounded-full border px-3 py-1.5 text-[12px] font-semibold disabled:opacity-40 ${
        selected ? 'border-primary bg-primary text-white' : 'border-border bg-surface text-primary'} ${className}`}
      {...props} />
  )
}

/** Primary (navy) or action (orange) full-width button inside a card. */
export function Action({ tone = 'primary', className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'primary' | 'action' | 'ghost' }) {
  const tones = {
    primary: 'bg-primary text-white',
    action: 'bg-action text-white',
    ghost: 'border border-primary bg-surface text-primary',
  }
  return (
    <button type="button"
      className={`w-full rounded-lg px-3 py-2.5 text-[13px] font-semibold disabled:opacity-50 ${tones[tone]} ${className}`}
      {...props} />
  )
}

export function TextLink({ className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className={`text-[12px] font-semibold text-primary disabled:opacity-50 ${className}`} {...props} />
}

/** Orange bar above the bottom bar: "🛒 3 item · Rp 70.000 · Lihat keranjang →", "Pesan & bayar · Rp …". */
export function ActionBar({ children, onClick, disabled, label }: {
  children: ReactNode; onClick: () => void; disabled?: boolean; label?: string
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label}
      className="flex w-full items-center justify-between gap-2 bg-action px-4 py-3 text-[14px] font-semibold text-white disabled:opacity-60">
      {children}
    </button>
  )
}

export function BottomBar({ placeholder, onMainMenu, onSend }: {
  placeholder: string; onMainMenu: () => void; onSend: (text: string) => void
}) {
  const [text, setText] = useState('')
  function submit(e: FormEvent) {
    e.preventDefault()
    const value = text.trim()
    if (!value) return
    onSend(value)
    setText('')
  }
  return (
    <form onSubmit={submit} className="flex items-center gap-2 border-t border-border bg-surface px-3 py-2">
      <button type="button" onClick={onMainMenu}
        className="shrink-0 rounded-full bg-page px-3 py-2 text-[12px] font-semibold text-primary">
        ☰ Menu utama
      </button>
      <input aria-label="Ketik pesan" value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder}
        maxLength={300}
        className="min-w-0 flex-1 rounded-full border border-border bg-page px-3 py-2 text-[13px] outline-none focus:border-primary" />
      <button type="submit" aria-label="Kirim"
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-white">➤</button>
    </form>
  )
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="block text-[12px] font-semibold text-text">
      <span className="mb-1 flex items-center justify-between">{label}{hint}</span>
      {children}
    </label>
  )
}

export const inputClass =
  'w-full rounded-lg border border-border bg-surface px-3 py-2 text-[13px] font-normal outline-none focus:border-primary'

/** "dari HP ini" next to a field prefilled from this phone (C5, C8). */
export function FromPhone() {
  return <span className="text-[11px] font-normal text-success">dari HP ini</span>
}
