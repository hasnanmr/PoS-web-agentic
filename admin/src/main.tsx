import '@fontsource-variable/inter'
import './index.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { RoleProvider } from './app/role'
import { AppRoutes } from './app/routes'
import { parseEnv } from './env'
import { EnvErrorScreen } from './EnvErrorScreen'

const envResult = parseEnv(import.meta.env)
const root = createRoot(document.getElementById('root')!)

if (!envResult.ok) {
  console.error('Invalid admin configuration', envResult.issues)
  root.render(<EnvErrorScreen issues={envResult.issues} />)
} else {
  root.render(
    <StrictMode>
      <RoleProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </RoleProvider>
    </StrictMode>,
  )
}
