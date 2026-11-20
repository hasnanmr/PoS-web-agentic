import '@fontsource-variable/inter'
import './index.css'
import { createClient } from '@supabase/supabase-js'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { areaForPath } from './app/nav'
import { AppRoutes } from './app/routes'
import { AuthGate } from './auth/AuthGate'
import { parseEnv } from './env'
import { EnvErrorScreen } from './EnvErrorScreen'
import { TabletApp } from './tablet/TabletApp'
import { TableApp } from './table/TableApp'

const envResult = parseEnv(import.meta.env)
const root = createRoot(document.getElementById('root')!)

if (!envResult.ok) {
  console.error('Invalid admin configuration', envResult.issues)
  root.render(<EnvErrorScreen issues={envResult.issues} />)
} else if (window.location.pathname.replace(/\/+$/, '') === '/tablet') {
  // K0–K4: the outlet attendance tablet, a separate full-screen app with its own device session.
  root.render(
    <StrictMode>
      <TabletApp apiBaseUrl={envResult.env.VITE_API_BASE_URL} />
    </StrictMode>,
  )
} else if (/^\/t\/[^/]+\/?$/.test(window.location.pathname)) {
  // Q0–Q5: the customer table web page from the table QR, public (no sign-in, no sidebar).
  const token = decodeURIComponent(window.location.pathname.split('/')[2])
  root.render(
    <StrictMode>
      <TableApp apiBaseUrl={envResult.env.VITE_API_BASE_URL} token={token} />
    </StrictMode>,
  )
} else {
  const { env } = envResult
  // Owner app at the root, staff app under /admin. Each area keeps its own sign-in in its own
  // storage key, so an owner tab and a staff tab can stay signed in on the same device.
  const area = areaForPath(window.location.pathname)
  // Supabase is used for sign-in only; data goes through the FastAPI backend.
  const supabase = createClient(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_ANON_KEY, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
      // Owner keeps the default key so existing owner sign-ins survive this change.
      ...(area === 'staff' ? { storageKey: 'thinker-staff-auth' } : {}),
    },
  })
  root.render(
    <StrictMode>
      <AuthGate supabase={supabase} apiBaseUrl={env.VITE_API_BASE_URL} area={area}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthGate>
    </StrictMode>,
  )
}
