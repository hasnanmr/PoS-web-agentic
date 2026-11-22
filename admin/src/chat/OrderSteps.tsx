// Order steps of the web chat: C2 menu cards, C3 add-ons + kitchen note, C4 cart + pickup /
// delivery + summary, C5 customer details + privacy notice (outlet link), C8 name (table QR).
// Canvas rules: required add-on groups must be answered before the item goes in the cart,
// optional ones can be skipped; the kitchen note is per item; amounts in the summary come from
// the server quote; nothing is ordered before "Pesan & bayar".
import { useMemo, useState } from 'react'
import { formatRupiah } from '../lib/format'
import { Photo } from '../ui/Photo'
import { addonNames, lineUnitPrice } from './cart'
import type { CartLine, ChatMenuItem, ChatQuote } from './types'
import { Action, Bubble, Chip, Choice, Field, FromPhone, TextLink, inputClass } from './ui'

// C2 ------------------------------------------------------------------------------------------------

export function MenuCards({ outletName, menu, cart, webOrdering, canBook = false, onAdd }: {
  outletName: string; menu: ChatMenuItem[]; cart: CartLine[]; webOrdering: boolean; canBook?: boolean; onAdd: (item: ChatMenuItem) => void
}) {
  const [category, setCategory] = useState<string | null>(null)
  const categories = useMemo(() => [...new Set(menu.map((m) => m.category).filter((c): c is string => Boolean(c)))], [menu])
  const shown = category ? menu.filter((m) => m.category === category) : menu
  const inCart = (id: string) => cart.filter((l) => l.product_id === id).reduce((s, l) => s + l.quantity, 0)
  return (
    <div className="space-y-2">
      <Bubble>
        <p>Ini menu {outletName}. Pilih kategori:</p>
        {categories.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Chip selected={category === null} onClick={() => setCategory(null)}>Semua</Chip>
            {categories.map((c) => <Chip key={c} selected={category === c} onClick={() => setCategory(c)}>{c}</Chip>)}
          </div>
        )}
      </Bubble>
      {!webOrdering && (
        <Bubble tone="warning">
          🧾 Untuk outlet ini, pesanan dilayani langsung di kasir ya. Menunya bisa kamu lihat dulu di sini{canBook ? ', dan reservasi meja tetap bisa.' : '.'}
        </Bubble>
      )}
      <ul className="space-y-2" aria-label="Menu">
        {shown.map((item) => {
          const count = inCart(item.product_id)
          const hint = item.description || (item.addon_groups.length ? 'ada pilihan' : '')
          return (
            <li key={item.product_id}
              className="flex items-center gap-3 rounded-xl border border-border bg-surface p-2.5">
              {item.photo_url ? (
                <Photo src={item.photo_url} className="h-14 w-14 shrink-0 rounded-lg" />
              ) : (
                <span aria-hidden="true" className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-page text-[20px]">☕</span>
              )}
              <div className="min-w-0 flex-1 text-[13px]">
                <p className="font-semibold">{item.name}</p>
                {hint && <p className="truncate text-[11px] text-text-muted">{item.description && item.addon_groups.length ? `${item.description} · ada pilihan` : hint}</p>}
                <p className={item.sold_out ? 'text-[12px] text-text-muted' : 'font-semibold'}>{formatRupiah(item.price)}</p>
              </div>
              {item.sold_out ? (
                <span className="shrink-0 rounded-full bg-danger-soft px-2 py-1 text-[11px] font-semibold text-danger">Habis</span>
              ) : webOrdering ? (
                count > 0 ? (
                  <button type="button" onClick={() => onAdd(item)} aria-label={`Tambah lagi ${item.name}`}
                    className="shrink-0 rounded-lg bg-primary-soft px-2.5 py-1.5 text-[11px] font-semibold text-primary">
                    {count} di keranjang
                  </button>
                ) : (
                  <button type="button" onClick={() => onAdd(item)} aria-label={`Tambah ${item.name}`}
                    className="shrink-0 rounded-lg border border-primary px-2.5 py-1.5 text-[12px] font-semibold text-primary">
                    + Tambah
                  </button>
                )
              ) : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// C3 ------------------------------------------------------------------------------------------------

export function AddonPicker({ item, onDone }: { item: ChatMenuItem; onDone: (optionIds: string[], note: string | null) => void }) {
  const [note, setNote] = useState('')
  const kitchenNote = () => note.trim().slice(0, 200) || null
  const [picked, setPicked] = useState<Record<string, string[]>>(() => {
    // A required single-choice group starts empty: the customer must answer it (AC2.3).
    return Object.fromEntries(item.addon_groups.map((g) => [g.id, []]))
  })
  const missing = item.addon_groups.some((g) => g.is_required && (picked[g.id] ?? []).length === 0)
  function toggle(groupId: string, optionId: string, single: boolean) {
    setPicked((p) => {
      const cur = p[groupId] ?? []
      if (single) return { ...p, [groupId]: cur[0] === optionId ? [] : [optionId] }
      if (cur.includes(optionId)) return { ...p, [groupId]: cur.filter((o) => o !== optionId) }
      const max = item.addon_groups.find((g) => g.id === groupId)?.max_select
      return max && cur.length >= max ? p : { ...p, [groupId]: [...cur, optionId] }
    })
  }
  const requiredOnly = () => item.addon_groups.filter((g) => g.is_required).flatMap((g) => picked[g.id] ?? [])
  return (
    <div className="space-y-2">
      {item.addon_groups.map((g) => {
        const single = g.selection === 'single'
        // C3: "Pilih susu · wajib, pilih 1", "Tambahan · opsional, maks 2".
        const limit = single ? 'pilih 1' : g.max_select ? `maks ${g.max_select}` : ''
        const full = !single && !!g.max_select && (picked[g.id] ?? []).length >= g.max_select
        return (
          <Bubble key={g.id}>
            <p className="mb-2 font-semibold">
              {g.name} · {[g.is_required ? 'wajib' : 'opsional', limit].filter(Boolean).join(', ')}
            </p>
            <div role={single ? 'radiogroup' : 'group'} aria-label={g.name} className="space-y-1.5">
              {g.options.map((o) => {
                const on = (picked[g.id] ?? []).includes(o.id)
                const mark = single ? (on ? '✓ ' : '') : on ? '☑ ' : '☐ '
                return (
                  <button key={o.id} type="button" role={single ? 'radio' : 'checkbox'} aria-checked={on}
                    disabled={!o.available || (full && !on)} onClick={() => toggle(g.id, o.id, single)}
                    className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-[13px] disabled:opacity-40 ${
                      on ? 'border-primary bg-primary-soft font-semibold text-primary' : 'border-primary/40 bg-surface text-primary'}`}>
                    <span>{mark}{o.name}{!o.available ? ' · habis' : ''}</span>
                    <span className="text-[12px] text-text-muted">+{formatRupiah(o.price)}</span>
                  </button>
                )
              })}
            </div>
          </Bubble>
        )
      })}
      {/* Same bubble flow as Q2a: the kitchen note is chosen together with the add-ons. */}
      <Bubble>
        <label className="block">
          <span className="mb-1 block font-semibold">Catatan untuk dapur (opsional)</span>
          <input aria-label="Catatan untuk dapur" value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="Mis. kurang manis, tanpa es" maxLength={200} enterKeyHint="done" autoComplete="off"
            className={inputClass} />
        </label>
        <p className="mt-1 text-[11px] text-text-muted">Untuk item ini saja. Item sama dengan catatan beda jadi baris terpisah.</p>
      </Bubble>
      <div className="grid max-w-[92%] grid-cols-[auto_1fr] gap-2">
        <Action tone="quiet" disabled={missing} onClick={() => onDone(requiredOnly(), kitchenNote())}>Lewati</Action>
        <Action disabled={missing} onClick={() => onDone(Object.values(picked).flat(), kitchenNote())}>
          Tambah ke keranjang · {formatRupiah(lineUnitPrice(item, Object.values(picked).flat()))}
        </Action>
      </div>
    </div>
  )
}

// The note is typed in the same bubble as "Tanpa catatan" (owner request): customers did not see
// that the bottom text box took the note.
export function NotePrompt({ onSkip, onNote }: { onSkip: () => void; onNote: (note: string) => void }) {
  const [note, setNote] = useState('')
  const value = note.trim()
  return (
    <Bubble>
      <p>Catatan untuk dapur? (opsional, untuk item ini saja)</p>
      <form className="mt-2 space-y-2" onSubmit={(e) => { e.preventDefault(); if (value) onNote(value) }}>
        <input aria-label="Catatan untuk dapur" value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Mis. kurang manis, tanpa es" maxLength={200} enterKeyHint="done" autoComplete="off"
          className={inputClass} />
        {value
          ? <Action type="submit">Tambah dengan catatan</Action>
          : <Choice className="text-center" onClick={onSkip}>Tanpa catatan</Choice>}
      </form>
    </Bubble>
  )
}

// C4 ------------------------------------------------------------------------------------------------

export function CartCard({ cart, byId, onQuantity, onNote, onAddMore, onEmpty }: {
  cart: CartLine[]; byId: Map<string, ChatMenuItem>; onQuantity: (index: number, quantity: number) => void
  onNote?: (index: number, note: string | null) => void; onAddMore: () => void; onEmpty: () => void
}) {
  const [editing, setEditing] = useState<number | null>(null)
  return (
    <Bubble>
      <p className="mb-2 font-semibold">Keranjang kamu</p>
      {cart.length === 0 ? (
        <p className="text-text-muted">Keranjangmu masih kosong.</p>
      ) : (
        <ul className="space-y-2">
          {cart.map((l, i) => {
            const item = byId.get(l.product_id)
            const addons = item ? addonNames(item, l.addon_option_ids) : []
            return (
              <li key={`${l.product_id}-${i}`} className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <p>{l.quantity}× {item?.name ?? 'Item'}</p>
                  {addons.length > 0 && <p className="text-[11px] text-text-muted">+ {addons.join(', ')}</p>}
                  {/* Q3: "✎ kurang manis" / "✎ + Catatan" on every line, editable in place. */}
                  {onNote && editing === i ? (
                    <NoteEditor initial={l.note ?? ''} name={item?.name ?? 'item'}
                      onSave={(note) => { onNote(i, note); setEditing(null) }} onCancel={() => setEditing(null)} />
                  ) : onNote ? (
                    <button type="button" onClick={() => setEditing(i)}
                      aria-label={l.note ? `Ubah catatan ${item?.name ?? 'item'}: ${l.note}` : `Tambah catatan ${item?.name ?? 'item'}`}
                      className={`-mx-1 mt-0.5 rounded px-1 py-0.5 text-left text-[11px] active:bg-primary-soft ${l.note ? 'text-text-muted' : 'font-semibold text-primary'}`}>
                      ✎ {l.note ?? '+ Catatan'}
                    </button>
                  ) : l.note && <p className="text-[11px] text-text-muted">✎ {l.note}</p>}
                </div>
                {/* Same "− 1 +" as the wireframe, with a finger-sized tap area around each sign. */}
                <div className="-my-2 flex shrink-0 items-center font-semibold text-primary">
                  <button type="button" aria-label={`Kurangi ${item?.name ?? 'item'}`} onClick={() => onQuantity(i, l.quantity - 1)}
                    className="flex h-9 w-8 items-center justify-center rounded-lg text-[16px] active:bg-primary-soft">−</button>
                  <span className="min-w-4 text-center text-text">{l.quantity}</span>
                  <button type="button" aria-label={`Tambah ${item?.name ?? 'item'}`} onClick={() => onQuantity(i, l.quantity + 1)}
                    className="flex h-9 w-8 items-center justify-center rounded-lg text-[16px] active:bg-primary-soft">+</button>
                </div>
                <span className="w-20 shrink-0 text-right">{item ? formatRupiah(lineUnitPrice(item, l.addon_option_ids) * l.quantity) : ''}</span>
              </li>
            )
          })}
        </ul>
      )}
      <p className="mt-2">
        <TextLink onClick={onAddMore}>+ Tambah menu</TextLink>
        {cart.length > 0 && <> <span className="text-text-muted">·</span> <TextLink onClick={onEmpty}>Kosongkan keranjang</TextLink></>}
      </p>
    </Bubble>
  )
}

function NoteEditor({ initial, name, onSave, onCancel }: {
  initial: string; name: string; onSave: (note: string | null) => void; onCancel: () => void
}) {
  const [note, setNote] = useState(initial)
  return (
    <form className="mt-1 space-y-1.5" onSubmit={(e) => { e.preventDefault(); onSave(note.trim() || null) }}>
      <input aria-label={`Catatan untuk dapur · ${name}`} value={note} onChange={(e) => setNote(e.target.value)} autoFocus
        placeholder="Mis. kurang manis, tanpa es" maxLength={200} enterKeyHint="done" autoComplete="off"
        className={`${inputClass} py-1.5 text-[12px]`} />
      <div className="flex gap-3">
        <TextLink type="submit">Simpan catatan</TextLink>
        <TextLink className="text-text-muted" onClick={onCancel}>Batal</TextLink>
      </div>
    </form>
  )
}

export function FulfillmentChoice({ value, deliveryFee, onPick }: {
  value: 'pickup' | 'delivery' | null; deliveryFee: number; onPick: (v: 'pickup' | 'delivery') => void
}) {
  return (
    <Bubble>
      <p className="mb-2">Mau diambil atau diantar?</p>
      <div className="grid grid-cols-2 gap-2">
        <Choice className="text-center" selected={value === 'pickup'} onClick={() => onPick('pickup')}>🛍 Ambil di outlet</Choice>
        <Choice className="text-center" selected={value === 'delivery'} onClick={() => onPick('delivery')}>
          🛵 Diantar{deliveryFee > 0 ? ` +${formatRupiah(deliveryFee)}` : ''}
        </Choice>
      </div>
    </Bubble>
  )
}

// C5 / C8 --------------------------------------------------------------------------------------------

export interface Details {
  name: string
  phone: string
  address: string
}

export function DetailsForm({ mode, initial, typedAddress, prefilled, remember, privacyUrl, error, onRemember, onClearSaved, onSubmit }: {
  mode: 'pickup' | 'delivery' | 'table'
  initial: Details
  /** C5: an address typed in the bottom text box ("Ketik alamat…") fills the address field. */
  typedAddress?: { text: string; seq: number }
  prefilled: boolean
  remember: boolean
  privacyUrl: string
  error: string | null
  onRemember: (on: boolean) => void
  onClearSaved: () => void
  onSubmit: (d: Details) => void
}) {
  const [d, setD] = useState<Details>(initial)
  const [touched, setTouched] = useState(false)
  const [addressSeq, setAddressSeq] = useState(typedAddress?.seq ?? 0)
  if (typedAddress && typedAddress.seq !== addressSeq) {
    setAddressSeq(typedAddress.seq)
    setD({ ...d, address: typedAddress.text.slice(0, 300) })
  }
  const needPhone = mode !== 'table'
  const needAddress = mode === 'delivery'
  const ok = d.name.trim() && (!needPhone || d.phone.trim()) && (!needAddress || d.address.trim())
  const fromPhone = (v: string, key: keyof Details) => prefilled && v === initial[key] && v !== ''
  if (mode === 'table') {
    return (
      <form className="max-w-[92%] space-y-2" onSubmit={(e) => { e.preventDefault(); setTouched(true); if (ok) onSubmit(d) }}>
        <Bubble>
          <Field label="Nama untuk dipanggil staf? (no HP tidak perlu)" hint={fromPhone(d.name, 'name') ? <FromPhone /> : undefined}>
            <input className={inputClass} value={d.name} maxLength={40} autoComplete="given-name"
              onChange={(e) => setD({ ...d, name: e.target.value })} />
          </Field>
          {touched && !d.name.trim() && <p className="mt-1 text-[12px] text-danger">Isi nama dulu ya, biar staf bisa memanggilmu.</p>}
          <p className="mt-2 text-[11px] text-primary">
            🔒 Nama hanya untuk pesanan ini dan dihapus setelah selesai.{' '}
            <a href={privacyUrl} target="_blank" rel="noreferrer" className="font-semibold text-primary">Kebijakan privasi ›</a>
          </p>
          {prefilled && <TextLink className="mt-1" onClick={onClearSaved}>Hapus data tersimpan</TextLink>}
        </Bubble>
        {error && <Bubble tone="danger">{error}</Bubble>}
        <Action type="submit">Lanjut ke ringkasan</Action>
      </form>
    )
  }
  return (
    <div className="max-w-[92%] space-y-2">
      <Bubble><p>Biar staf bisa menghubungi kamu, isi data di bawah ya.</p></Bubble>
      <Bubble tone="info">
        <p className="font-semibold">🔒 Privasi</p>
        <p className="mt-1 text-[12px]">
          Nama, no HP{needAddress ? ', dan alamat' : ''} dipakai hanya untuk pesanan ini, disimpan di server (Singapura), dan
          dihapus otomatis setelah pesanan selesai atau batal.
        </p>
        <a href={privacyUrl} target="_blank" rel="noreferrer" className="mt-1 inline-block text-[12px] font-semibold text-primary">
          Kebijakan privasi lengkap ›
        </a>
      </Bubble>
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); setTouched(true); if (ok) onSubmit(d) }}>
        <Bubble>
          <div className="space-y-2.5">
            <Field label="Nama *" hint={fromPhone(d.name, 'name') ? <FromPhone /> : undefined}>
              <input className={inputClass} value={d.name} maxLength={60} autoComplete="name"
                onChange={(e) => setD({ ...d, name: e.target.value })} />
            </Field>
            <Field label="No HP * (tanpa OTP)" hint={fromPhone(d.phone, 'phone') ? <FromPhone /> : undefined}>
              <input className={inputClass} value={d.phone} inputMode="tel" autoComplete="tel" maxLength={20}
                onChange={(e) => setD({ ...d, phone: e.target.value })} />
            </Field>
            {needAddress && (
              <Field label="Alamat antar * (hanya delivery)" hint={fromPhone(d.address, 'address') ? <FromPhone /> : undefined}>
                <textarea className={inputClass} rows={2} value={d.address} maxLength={300} autoComplete="street-address"
                  onChange={(e) => setD({ ...d, address: e.target.value })} />
              </Field>
            )}
            {touched && !ok && <p className="text-[12px] text-danger">Lengkapi data yang bertanda * dulu ya.</p>}
            <label className="flex items-center gap-2 text-[12px]">
              <input type="checkbox" checked={remember} onChange={(e) => onRemember(e.target.checked)} />
              Ingat data di HP ini (tidak disimpan di server)
            </label>
            {prefilled && <TextLink onClick={onClearSaved}>Hapus data tersimpan</TextLink>}
          </div>
        </Bubble>
        {error && <Bubble tone="danger">{error}</Bubble>}
        <Action type="submit">Lanjut ke ringkasan</Action>
      </form>
    </div>
  )
}

function maskPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '')
  return digits.length >= 8 ? `${digits.slice(0, 4)}-xxxx-${digits.slice(-3)}` : phone
}

export function SummaryCard({ quote, mode, details, tableName, items, onEdit }: {
  quote: ChatQuote | null; mode: 'pickup' | 'delivery' | 'table'; details: Details; tableName: string | null
  items: string[]; onEdit: () => void
}) {
  return (
    <Bubble>
      <p className="mb-1 font-semibold">Ringkasan pesanan</p>
      {mode === 'table' && (
        <p className="mb-1">Dine-in · {tableName} · a.n. {details.name}</p>
      )}
      <ul className="mb-2 text-[12px] text-text-muted">{items.map((t, i) => <li key={i}>{t}</li>)}</ul>
      {quote ? (
        <dl className="space-y-0.5 text-[12px]">
          <Row label="Subtotal" value={formatRupiah(quote.subtotal)} />
          {quote.pb1_amount > 0 && <Row label={`PB1 ${(quote.pb1_rate_bps ?? 0) / 100}%`} value={formatRupiah(quote.pb1_amount)} />}
          {quote.delivery_fee > 0 && <Row label="Ongkir (tidak kena PB1)" value={formatRupiah(quote.delivery_fee)} />}
          <div className="flex justify-between pt-1 text-[14px] font-bold"><dt>Total</dt><dd>{formatRupiah(quote.total)}</dd></div>
        </dl>
      ) : (
        <p className="text-[12px] text-text-muted">Menghitung total…</p>
      )}
      {mode !== 'table' && (
        <p className="mt-2 text-[11px] text-text-muted">
          {mode === 'delivery' ? `Delivery → ${details.address} · ` : 'Ambil di outlet · '}
          {details.name} · {maskPhone(details.phone)}{' '}
          <TextLink className="text-[11px]" onClick={onEdit}>(ubah)</TextLink>
        </p>
      )}
    </Bubble>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between"><dt>{label}</dt><dd>{value}</dd></div>
}
