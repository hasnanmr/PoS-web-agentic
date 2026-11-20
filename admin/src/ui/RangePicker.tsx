// Date range dropdown used by O9 and O10 ("1–17 Nov 2026 ▾") and by O2's "Rentang ▾".
import { useState } from 'react'
import { formatRange } from '../lib/format'
import { Button, TextInput } from './kit'

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000) + 1
}

export function RangePicker({ value, onChange, label = 'Periode', withYear = true, max, maxDays, align = 'left', buttonClassName, pressed }: {
  value: { from: string; to: string } | undefined
  onChange: (range: { from: string; to: string }) => void
  /** Button text while no range is chosen. */
  label?: string
  withYear?: boolean
  /** Latest selectable day ("YYYY-MM-DD"). */
  max?: string
  /** Longest range allowed, in days (both ends included). */
  maxDays?: number
  align?: 'left' | 'right'
  buttonClassName?: string
  /** For a picker inside a toggle group (O2 header): whether it is the selected option. */
  pressed?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const tooLong = Boolean(maxDays && from && to && from <= to && daysBetween(from, to) > maxDays)
  return (
    <div className="relative">
      <button type="button" className={buttonClassName ?? 'h-8 rounded-md border border-border bg-surface px-3'} aria-expanded={open}
        aria-pressed={pressed} onClick={() => { setFrom(value?.from ?? ''); setTo(value?.to ?? ''); setOpen(!open) }}>
        {value ? formatRange(value.from, value.to, withYear) : label} ▾
      </button>
      {open && (
        <div className={`absolute ${align === 'right' ? 'right-0' : 'left-0'} z-20 mt-1 w-64 space-y-2 rounded-md border border-border bg-surface p-3 text-left text-text shadow-lg`}>
          <label className="block text-[12px]">Dari
            <TextInput type="date" aria-label="Dari tanggal" value={from} max={to || max} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="block text-[12px]">Sampai
            <TextInput type="date" aria-label="Sampai tanggal" value={to} min={from || undefined} max={max} onChange={(e) => setTo(e.target.value)} />
          </label>
          {tooLong && <p className="text-[11px] text-danger">Maksimal {maxDays} hari.</p>}
          <Button className="h-8 w-full" disabled={!from || !to || from > to || tooLong || Boolean(max && to > max)}
            onClick={() => { onChange({ from, to }); setOpen(false) }}>Terapkan</Button>
        </div>
      )}
    </div>
  )
}
