// Date range dropdown used by O9 and O10 ("1–17 Nov 2026 ▾").
import { useState } from 'react'
import { formatRange } from '../lib/format'
import { Button, TextInput } from './kit'

export function RangePicker({ value, onChange }: {
  value: { from: string; to: string } | undefined
  onChange: (range: { from: string; to: string }) => void
}) {
  const [open, setOpen] = useState(false)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  return (
    <div className="relative">
      <button type="button" className="h-8 rounded-md border border-border bg-surface px-3" aria-expanded={open}
        onClick={() => { setFrom(value?.from ?? ''); setTo(value?.to ?? ''); setOpen(!open) }}>
        {value ? formatRange(value.from, value.to) : 'Periode'} ▾
      </button>
      {open && (
        <div className="absolute left-0 z-20 mt-1 w-64 space-y-2 rounded-md border border-border bg-surface p-3 shadow-lg">
          <label className="block text-[12px]">Dari
            <TextInput type="date" aria-label="Dari tanggal" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="block text-[12px]">Sampai
            <TextInput type="date" aria-label="Sampai tanggal" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
          </label>
          <Button className="h-8 w-full" disabled={!from || !to || from > to}
            onClick={() => { onChange({ from, to }); setOpen(false) }}>Terapkan</Button>
        </div>
      )}
    </div>
  )
}
