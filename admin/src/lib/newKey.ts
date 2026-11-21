/** A random id for Idempotency-Keys and list keys. `crypto.randomUUID` is missing on iOS Safari
 * before 15.4, some in-app browsers and non-HTTPS origins, so fall back instead of crashing. */
export function newKey(): string {
  const c = typeof crypto !== 'undefined' ? crypto : undefined
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  if (c && typeof c.getRandomValues === 'function') {
    const b = c.getRandomValues(new Uint8Array(16))
    b[6] = (b[6] & 0x0f) | 0x40
    b[8] = (b[8] & 0x3f) | 0x80
    const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
  }
  return `k-${Date.now()}-${Math.random().toString(36).slice(2)}`
}
