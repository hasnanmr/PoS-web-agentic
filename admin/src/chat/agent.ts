// The web chat agent (C9 AI, C14, C15): POST …/agent/messages answered as server-sent events
// (screen-endpoint map → C9 / C14 / C15 Agent). Read with fetch + a stream reader, not
// EventSource: it is a POST with the X-Chat-Session header. Events: `delta` {text} while the
// reply is written, then one `final` or one `error` (the chat falls back to its buttons).

export type AgentContext = 'recommend' | 'order' | 'book' | 'auto'

export interface AgentCard {
  product_id: string
  name: string
  description: string | null
  price: number
  photo_url: string | null
  badge: 'owner_pick' | null
}

export interface AgentOrderLine {
  product_id: string
  name: string
  quantity: number
  addon_option_ids: string[]
  addons: string[]
  note: string | null
  line_total: number
}

export interface AgentOrderDraft {
  fulfillment: 'pickup' | 'delivery' | null
  lines: AgentOrderLine[]
  subtotal: number
  pb1_amount: number
  delivery_fee: number
  total: number
}

export interface AgentBookingDraft {
  party_size: number
  start_at: string
  label: string
  timezone: string
}

export interface AgentFinal {
  reply_text: string
  cards: AgentCard[]
  quick_replies: string[]
  order_draft: AgentOrderDraft | null
  booking_draft: AgentBookingDraft | null
  out_of_scope: boolean
}

export type AgentResult =
  | { kind: 'final'; final: AgentFinal }
  | { kind: 'error'; code: string; fallback: 'buttons' | 'cards' }

/** Longer than the server's 30-second turn limit, so the server's own error event arrives first. */
const CLIENT_TIMEOUT_MS = 40_000

export async function sendToAgent({ apiBaseUrl, base, session, text, context, onDelta, fetchImpl = fetch }: {
  apiBaseUrl: string
  base: string
  session: string
  text: string
  context: AgentContext
  onDelta: (text: string) => void
  fetchImpl?: typeof fetch
}): Promise<AgentResult> {
  const fallback = context === 'recommend' ? 'cards' : 'buttons'
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), CLIENT_TIMEOUT_MS)
  try {
    const res = await fetchImpl(`${apiBaseUrl.replace(/\/+$/, '')}/api/v1${base}/agent/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', 'X-Chat-Session': session },
      body: JSON.stringify({ text, context }),
      signal: controller.signal,
    })
    if (!res.ok || !res.body) {
      const err = await res.json().catch(() => null) as { error?: { code?: string } } | null
      return { kind: 'error', code: err?.error?.code ?? 'agent_unavailable', fallback }
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (value) buffer += decoder.decode(value, { stream: true })
      let cut = buffer.indexOf('\n\n')
      while (cut >= 0) {
        const block = buffer.slice(0, cut)
        buffer = buffer.slice(cut + 2)
        const event = parseEvent(block)
        if (event?.event === 'delta' && typeof event.data.text === 'string') onDelta(event.data.text)
        if (event?.event === 'final') return { kind: 'final', final: event.data as unknown as AgentFinal }
        if (event?.event === 'error') {
          return { kind: 'error', code: String(event.data.code ?? 'agent_unavailable'),
            fallback: event.data.fallback === 'cards' ? 'cards' : 'buttons' }
        }
        cut = buffer.indexOf('\n\n')
      }
      if (done) break
    }
    return { kind: 'error', code: 'agent_unavailable', fallback }
  } catch {
    return { kind: 'error', code: 'agent_unavailable', fallback }
  } finally {
    clearTimeout(timer)
  }
}

function parseEvent(block: string): { event: string; data: Record<string, unknown> } | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (data.length === 0) return null
  try {
    return { event, data: JSON.parse(data.join('\n')) as Record<string, unknown> }
  } catch {
    return null
  }
}
