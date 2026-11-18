import { z } from 'zod'

/**
 * Build-time environment for the admin app (Vite exposes only VITE_* variables).
 * Validated once at startup; an invalid config renders <EnvErrorScreen> instead of the app.
 */
const envSchema = z.object({
  VITE_API_BASE_URL: z.url({ message: 'harus berupa URL, mis. http://localhost:8000' }),
  VITE_SUPABASE_URL: z.url({ message: 'harus berupa URL proyek Supabase' }),
  VITE_SUPABASE_ANON_KEY: z.string().trim().min(1, { message: 'wajib diisi' }),
})

export type AppEnv = z.infer<typeof envSchema>

export type EnvResult =
  | { ok: true; env: AppEnv }
  | { ok: false; issues: { key: string; message: string }[] }

export function parseEnv(raw: Record<string, unknown>): EnvResult {
  const result = envSchema.safeParse(raw)
  if (result.success) {
    return { ok: true, env: result.data }
  }
  return {
    ok: false,
    issues: result.error.issues.map((issue) => ({
      key: issue.path.join('.') || '(env)',
      message: issue.message,
    })),
  }
}
