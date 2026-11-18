import { describe, expect, it } from 'vitest'
import { parseEnv } from './env'

describe('parseEnv', () => {
  it('accepts a complete config', () => {
    const result = parseEnv({
      VITE_API_BASE_URL: 'http://localhost:8000',
      VITE_SUPABASE_URL: 'https://abc.supabase.co',
      VITE_SUPABASE_ANON_KEY: 'anon-key',
    })
    expect(result.ok).toBe(true)
  })

  it('reports every missing or invalid variable', () => {
    const result = parseEnv({ VITE_API_BASE_URL: 'not a url' })
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.issues.map((i) => i.key).sort()).toEqual([
        'VITE_API_BASE_URL',
        'VITE_SUPABASE_ANON_KEY',
        'VITE_SUPABASE_URL',
      ])
    }
  })
})
