import '@fontsource-variable/inter'
import './index.css'
import { createClient } from '@supabase/supabase-js'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { AppRoutes } from './app/routes'
import { AuthGate } from './auth/AuthGate'
import { parseEnv } from './env'
import { EnvErrorScreen } from './EnvErrorScreen'

const envResult = parseEnv(import.meta.env)
const root = createRoot(document.getElementById('root')!)

if (!envResult.ok) {
  console.error('Invalid admin configuration', envResult.issues)
  root.render(<EnvErrorScreen issues={envResult.issues} />)
} else {
  const { env } = envResult
  // Supabase is used for sign-in only; data goes through the FastAPI backend.
  const supabase = createClient(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_ANON_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  })
  root.render(
    <StrictMode>
      <AuthGate supabase={supabase} apiBaseUrl={env.VITE_API_BASE_URL}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthGate>
    </StrictMode>,
  )
}
