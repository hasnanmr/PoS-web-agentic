// Wireframe O1 · "Masuk" card (invite-only login, Supabase Auth email + password).
// The password field has a Lihat / Sembunyikan toggle (same as the Atur password card).
import type { SupabaseClient } from '@supabase/supabase-js'
import { useState, type FormEvent } from 'react'
import { Alert, Button, Card, Field, PasswordInput, TextInput } from '../ui/kit'
import { authErrorCopy } from './errors'

export function LoginCard({ supabase, error }: { supabase: SupabaseClient; error?: string }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | undefined>(error)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage(undefined)
    const { error: authError } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
    setBusy(false)
    if (authError) setMessage(authErrorCopy(authError.message))
  }

  return (
    <Card>
      <h1 className="text-[18px] font-bold">Masuk</h1>
      <p className="mb-4 text-[12px] text-text-muted">Akun dibuat lewat undangan email (Supabase Auth).</p>
      <form onSubmit={submit} noValidate>
        <Field label="Email" htmlFor="login-email">
          <TextInput
            id="login-email"
            type="email"
            autoComplete="email"
            placeholder="nama@bisnis.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <Field label="Password" htmlFor="login-password">
          <PasswordInput
            id="login-password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        {message && <div className="mb-3"><Alert>{message}</Alert></div>}
        <Button type="submit" variant="primary" className="w-full" disabled={busy || !email || !password}>
          {busy ? 'Memproses…' : 'Masuk'}
        </Button>
      </form>
      <p className="mt-3 text-[12px] text-text-muted">
        Pertama kali? Buka link undangan di email untuk atur password.
      </p>
    </Card>
  )
}
