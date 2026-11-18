/**
 * Wireframe O1 · Login (invite-only) & Buat Bisnis.
 *
 * Signed out → "Masuk" (email + password, Supabase Auth). Opening an invitation link →
 * set a password first ("Pertama kali? Buka link undangan di email untuk atur password.").
 * Invited owner without a business (`onboarding_required`) → "Buat profil bisnis".
 * Owner/staff of a business → the admin shell.
 */
import type { SupabaseClient } from '@supabase/supabase-js'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { ApiError, createApi, errorMessage, type Api } from '../lib/api'
import type { Me } from '../lib/types'
import { OUTLET_STORAGE_KEY, pickOutlet, SessionContext, type Session } from '../app/session'
import { Loading } from '../ui/kit'
import { LoginCard } from './LoginCard'
import { OnboardingCard } from './OnboardingCard'
import { SetPasswordCard } from './SetPasswordCard'

type State =
  | { kind: 'loading' }
  | { kind: 'signed_out'; error?: string }
  | { kind: 'onboarding'; me: Me }
  | { kind: 'ready'; me: Me }

// Captured before supabase-js consumes the URL hash of an invitation / recovery link.
const ARRIVED_FROM_INVITE =
  typeof window !== 'undefined' && /type=(invite|recovery)/.test(window.location.hash)

function readStoredOutlet(): string | null {
  try {
    return window.localStorage.getItem(OUTLET_STORAGE_KEY)
  } catch {
    return null
  }
}

export function AuthGate({ supabase, apiBaseUrl, children }: {
  supabase: SupabaseClient
  apiBaseUrl: string
  children: ReactNode
}) {
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [needsPassword, setNeedsPassword] = useState(ARRIVED_FROM_INVITE)
  const [outletId, setOutletIdState] = useState<string | null>(readStoredOutlet)

  const api: Api = useMemo(
    () =>
      createApi(apiBaseUrl, async () => {
        const { data } = await supabase.auth.getSession()
        return data.session?.access_token ?? null
      }),
    [apiBaseUrl, supabase],
  )

  const loadMe = useCallback(async () => {
    try {
      const me = await api.get<Me>('/me')
      setState(me.onboarding_required ? { kind: 'onboarding', me } : { kind: 'ready', me })
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        await supabase.auth.signOut()
      }
      setState({ kind: 'signed_out', error: errorMessage(error) })
    }
  }, [api, supabase])

  useEffect(() => {
    let cancelled = false
    const apply = (hasSession: boolean) => {
      if (cancelled) return
      if (!hasSession) setState((s) => (s.kind === 'signed_out' ? s : { kind: 'signed_out' }))
      else void loadMe()
    }
    void supabase.auth.getSession().then(({ data }) => apply(Boolean(data.session)))
    const { data } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY') setNeedsPassword(true)
      if (event === 'SIGNED_IN' || event === 'SIGNED_OUT') apply(Boolean(session))
    })
    return () => {
      cancelled = true
      data.subscription.unsubscribe()
    }
  }, [supabase, loadMe])

  const signOut = useCallback(async () => {
    await supabase.auth.signOut()
    setState({ kind: 'signed_out' })
  }, [supabase])

  const setOutletId = useCallback((id: string) => {
    setOutletIdState(id)
    try {
      window.localStorage.setItem(OUTLET_STORAGE_KEY, id)
    } catch {
      // storage unavailable; the choice lasts for this tab only
    }
  }, [])

  const session: Session | null = useMemo(() => {
    if (state.kind !== 'ready' || state.me.role === 'owner_pending') return null
    return {
      me: state.me,
      role: state.me.role,
      api,
      outlet: pickOutlet(state.me.outlets, outletId),
      setOutletId,
      reload: loadMe,
      signOut,
    }
  }, [state, api, outletId, setOutletId, loadMe, signOut])

  if (needsPassword && state.kind !== 'loading' && state.kind !== 'signed_out') {
    return (
      <AuthLayout>
        <SetPasswordCard supabase={supabase} onDone={() => setNeedsPassword(false)} />
      </AuthLayout>
    )
  }
  switch (state.kind) {
    case 'loading':
      return <Loading />
    case 'signed_out':
      return (
        <AuthLayout>
          <LoginCard supabase={supabase} error={state.error} />
        </AuthLayout>
      )
    case 'onboarding':
      return (
        <AuthLayout>
          <OnboardingCard
            api={api}
            onCreated={async () => {
              // New token carries tenant_id + app_role=owner from the access token hook.
              await supabase.auth.refreshSession()
              await loadMe()
            }}
            onSignOut={signOut}
          />
        </AuthLayout>
      )
    case 'ready':
      return session ? <SessionContext.Provider value={session}>{children}</SessionContext.Provider> : null
  }
}

function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center bg-page px-4 py-10 text-text">
      <div className="mb-6 text-[18px] font-bold text-primary">
        <span aria-hidden="true">◼</span> SME POS
      </div>
      <div className="w-full max-w-[440px]">{children}</div>
    </div>
  )
}
