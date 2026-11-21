// Page 07 · C9 AI, C14, C15: one reply of the web chat agent ("◆ ASISTEN AI").
// Canvas rules: "Sebentar ya…" with a typing indicator at once; the agent only reads data and
// never creates a cart, order, or booking — items go to the cart only on "+ Tambah" (C3/C4),
// the order draft becomes the summary with Ubah / Pesan & bayar (prices and total from the
// server quote), the booking draft continues to name + phone + privacy and "Cek lagi" (C10);
// out of scope → a short refusal and the main menu buttons; failure or > 30 s → the buttons
// (or the owner's pick + best seller cards in Rekomendasi).
// Only the latest reply's buttons work (`active`); older ones stay visible but greyed out, so an
// old quick reply or draft can't be tapped by mistake. "+ Tambah" on cards always works.
import { formatRupiah } from '../lib/format'
import { Photo } from '../ui/Photo'
import type { AgentBookingDraft, AgentContext, AgentOrderDraft, AgentResult } from './agent'
import type { ChatMenuItem } from './types'
import { Action, Bubble, Chip, TextLink } from './ui'

export interface AgentTurn {
  context: AgentContext
  text: string
  result: AgentResult | null
}

const WAITING: Record<AgentContext, string> = {
  recommend: 'Sebentar ya, lagi cariin rekomendasi…',
  order: 'Sebentar ya, lagi cek menunya…',
  book: 'Sebentar ya, lagi cek meja yang kosong…',
  auto: 'Sebentar ya…',
}

export function AgentReply({ turn, active = true, byId, webOrdering, canBook, onAdd, onQuick, onOrder, onBook, onPick }: {
  turn: AgentTurn
  active?: boolean
  byId: Map<string, ChatMenuItem>
  webOrdering: boolean
  canBook: boolean
  onAdd: (item: ChatMenuItem) => void
  onQuick: (text: string) => void
  onOrder: (draft: AgentOrderDraft, edit: boolean) => void
  onBook: (draft: AgentBookingDraft) => void
  onPick: (target: 'menu' | 'recs' | 'book') => void
}) {
  const result = turn.result
  if (result === null) {
    return (
      <Bubble label="◆ ASISTEN AI">
        {turn.text ? <p className="whitespace-pre-line">{turn.text}</p> : (
          <p>{WAITING[turn.context]} <span aria-label="sedang mengetik" className="animate-pulse text-text-muted">•••</span></p>
        )}
      </Bubble>
    )
  }

  if (result.kind === 'error') {
    return (
      <div className="max-w-[92%] space-y-2">
        <Bubble label="◆ ASISTEN AI">
          {result.code === 'too_many_requests'
            ? 'Pesannya kebanyakan dalam waktu singkat. Tunggu sebentar ya, atau pakai tombol di bawah.'
            : result.fallback === 'cards'
              ? 'Maaf, asistennya lagi belum bisa jawab. Ini pilihan owner & terlaris di outlet ini ya.'
              : 'Maaf, asistennya lagi belum bisa jawab. Pakai tombol di bawah dulu ya, tetap bisa pesan seperti biasa.'}
        </Bubble>
        {(result.fallback === 'buttons' || result.code === 'too_many_requests') && <MenuButtons canBook={canBook} disabled={!active} onPick={onPick} />}
      </div>
    )
  }

  const final = result.final
  const label = final.out_of_scope ? '◆ ASISTEN AI · di luar lingkup'
    : final.order_draft ? '◆ ASISTEN AI · harga & total dihitung sistem' : '◆ ASISTEN AI'
  return (
    <div className="max-w-[92%] space-y-2">
      <Bubble label={label}>
        {final.reply_text && <p className="whitespace-pre-line">{final.reply_text}</p>}
        {final.order_draft && <OrderDraft draft={final.order_draft} webOrdering={webOrdering} disabled={!active} onOrder={onOrder} />}
        {final.booking_draft && (
          <div className="mt-2 rounded-lg bg-page px-2 py-1.5 text-[12px]">
            <p className="font-semibold">{final.booking_draft.party_size} orang · {final.booking_draft.label}</p>
            <Action className="mt-2" disabled={!active} onClick={() => onBook(final.booking_draft!)}>Lanjut isi nama &amp; no HP</Action>
          </div>
        )}
      </Bubble>
      {final.cards.length > 0 && (
        <ul className="flex gap-2 overflow-x-auto pb-1" aria-label="Rekomendasi asisten">
          {final.cards.map((c) => {
            const item = byId.get(c.product_id)
            return (
              <li key={c.product_id} className="w-36 shrink-0 rounded-xl border border-border bg-surface p-2 text-[12px]">
                {c.photo_url
                  ? <Photo src={c.photo_url} className="mb-1 h-20 w-full rounded-lg" />
                  : <span aria-hidden="true" className="mb-1 flex h-20 w-full items-center justify-center rounded-lg bg-page text-[20px]">☕</span>}
                {c.badge === 'owner_pick' && <p className="text-[11px] text-text-muted">★ Pilihan owner</p>}
                <p className="font-semibold">{c.name}</p>
                <p>{formatRupiah(c.price)}</p>
                {webOrdering && item && !item.sold_out && (
                  <TextLink onClick={() => onAdd(item)} aria-label={`Tambah ${c.name}`}>+ Tambah</TextLink>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {final.quick_replies.length > 0 && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Pilihan cepat">
          {final.quick_replies.map((q) => <Chip key={q} disabled={!active} onClick={() => onQuick(q)}>{q}</Chip>)}
        </div>
      )}
      {final.out_of_scope && <MenuButtons canBook={canBook} disabled={!active} onPick={onPick} />}
    </div>
  )
}

function OrderDraft({ draft, webOrdering, disabled, onOrder }: {
  draft: AgentOrderDraft; webOrdering: boolean; disabled: boolean; onOrder: (draft: AgentOrderDraft, edit: boolean) => void
}) {
  return (
    <div className="mt-2 space-y-1 text-[12px]">
      <ul className="space-y-0.5">
        {draft.lines.map((l, i) => (
          <li key={`${l.product_id}-${i}`}>
            {l.quantity}× {l.name}{l.addons.length ? ` (${l.addons.join(', ')})` : ''}{l.note ? ` — ${l.note} ✎` : ''}
          </li>
        ))}
      </ul>
      {draft.fulfillment && <p className="text-text-muted">{draft.fulfillment === 'delivery' ? 'Delivery' : 'Pickup'}</p>}
      <p className="font-semibold">
        Subtotal {formatRupiah(draft.subtotal)}
        {draft.pb1_amount > 0 ? ` · PB1 ${formatRupiah(draft.pb1_amount)}` : ''}
        {draft.delivery_fee > 0 ? ` · Ongkir ${formatRupiah(draft.delivery_fee)}` : ''}
        {' · '}Total {formatRupiah(draft.total)}
      </p>
      <div className="grid grid-cols-2 gap-2 pt-1">
        <Action tone="ghost" disabled={disabled} onClick={() => onOrder(draft, true)}>Ubah</Action>
        <Action tone="action" disabled={disabled || !webOrdering} onClick={() => onOrder(draft, false)}>Pesan &amp; bayar</Action>
      </div>
    </div>
  )
}

function MenuButtons({ canBook, disabled, onPick }: {
  canBook: boolean; disabled: boolean; onPick: (target: 'menu' | 'recs' | 'book') => void
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <Chip disabled={disabled} onClick={() => onPick('menu')}>Pesan</Chip>
      <Chip disabled={disabled} onClick={() => onPick('recs')}>Rekomendasi</Chip>
      {canBook && <Chip disabled={disabled} onClick={() => onPick('book')}>Reservasi</Chip>}
    </div>
  )
}
