// O1 note "Pertama kali? Buka link undangan di email untuk atur password.": the invitation
// link signs the user in; they choose a password here before continuing.
import type { SupabaseClient } from '@supabase/supabase-js'
import { useState, type FormEvent } from 'react'
import { Alert, Button, Card, Field, TextInput } from '../ui/kit'

export function SetPasswordCard({ supabase, onDone }: { supabase: SupabaseClient; onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (password.length < 8) return setError('Password minimal 8 karakter.')
    if (password !== confirm) return setError('Konfirmasi password tidak sama.')
    setBusy(true)
    setError(undefined)
    const { error: authError } = await supabase.auth.updateUser({ password })
    setBusy(false)
    if (authError) return setError('Password gagal disimpan. Coba lagi.')
    window.history.replaceState(null, '', window.location.pathname)
    onDone()
  }

  return (
    <Card>
      <h1 className="text-[18px] font-bold">Atur password</h1>
      <p className="mb-4 text-[12px] text-text-muted">Pakai password ini untuk masuk berikutnya.</p>
      <form onSubmit={submit} noValidate>
        <Field label="Password" htmlFor="new-password">
          <TextInput id="new-password" type="password" autoComplete="new-password"
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label="Ulangi password" htmlFor="confirm-password">
          <TextInput id="confirm-password" type="password" autoComplete="new-password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </Field>
        {error && <div className="mb-3"><Alert>{error}</Alert></div>}
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? 'Menyimpan…' : 'Simpan password'}
        </Button>
      </form>
    </Card>
  )
}
