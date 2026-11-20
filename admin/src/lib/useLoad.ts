import { useCallback, useEffect, useRef, useState } from 'react'

export interface Loaded<T> {
  data: T | undefined
  error: unknown
  loading: boolean
  /** Fetch again; resolves once the new result is in. */
  reload: () => Promise<void>
}

interface Result<T> {
  key: string
  nonce: number
  data?: T
  error?: unknown
}

/** Load data on mount and whenever `key` changes (e.g. the outlet id). */
export function useLoad<T>(load: () => Promise<T>, key: string): Loaded<T> {
  const loadRef = useRef(load)
  useEffect(() => {
    loadRef.current = load
  })
  const [nonce, setNonce] = useState(0)
  const [result, setResult] = useState<Result<T>>({ key: '\u0000', nonce: -1 })
  const waiting = useRef<(() => void)[]>([])

  useEffect(() => {
    let active = true
    const settle = (next: (prev: Result<T>) => Result<T>) => {
      if (!active) return
      setResult(next)
      waiting.current.splice(0).forEach((resolve) => resolve())
    }
    loadRef.current().then(
      (data) => settle(() => ({ key, nonce, data })),
      (error: unknown) => settle((prev) => ({ key, nonce, data: prev.key === key ? prev.data : undefined, error })),
    )
    return () => {
      active = false
    }
  }, [key, nonce])

  const reload = useCallback(
    () =>
      new Promise<void>((resolve) => {
        waiting.current.push(resolve)
        setNonce((n) => n + 1)
      }),
    [],
  )

  const sameKey = result.key === key
  return {
    data: sameKey ? result.data : undefined,
    error: sameKey ? result.error : undefined,
    loading: !sameKey || result.nonce !== nonce,
    reload,
  }
}

/** The last defined value, kept while a reload (new key) is in flight so the screen does not
 *  blank out to a spinner. Pass `undefined` to clear it (e.g. when the reload failed). */
export function useKept<T>(value: T | undefined, keep = true): T | undefined {
  const [kept, setKept] = useState(value)
  if (value !== undefined && value !== kept) setKept(value)
  return value ?? (keep ? kept : undefined)
}
