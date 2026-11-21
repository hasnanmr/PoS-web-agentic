// Cart helpers for display (C2-C4). The amounts shown before the summary are an estimate from
// the menu; the summary and the order always use the server quote.
import type { CartLine, ChatMenuItem } from './types'

export function lineUnitPrice(item: ChatMenuItem, optionIds: string[]): number {
  const options = item.addon_groups.flatMap((g) => g.options)
  return item.price + options.filter((o) => optionIds.includes(o.id)).reduce((s, o) => s + o.price, 0)
}

export function addonNames(item: ChatMenuItem, optionIds: string[]): string[] {
  return item.addon_groups.flatMap((g) => g.options).filter((o) => optionIds.includes(o.id)).map((o) => o.name)
}

/** "1× Es Kopi Susu Senja (Oat milk, Extra shot) · ✎ kurang manis". */
export function describeLine(item: ChatMenuItem | undefined, line: CartLine): string {
  const name = item?.name ?? 'Item'
  const addons = item ? addonNames(item, line.addon_option_ids) : []
  return `${line.quantity}× ${name}${addons.length ? ` (${addons.join(', ')})` : ''}${line.note ? ` · ✎ ${line.note}` : ''}`
}

export function cartTotal(lines: CartLine[], byId: Map<string, ChatMenuItem>): { count: number; amount: number } {
  return lines.reduce((acc, l) => {
    const item = byId.get(l.product_id)
    return { count: acc.count + l.quantity, amount: acc.amount + (item ? lineUnitPrice(item, l.addon_option_ids) * l.quantity : 0) }
  }, { count: 0, amount: 0 })
}
