import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { ToastProvider } from './components/ui'
import { Home } from './routes/Home'
import { Lab } from './routes/Lab'

/**
 * Root component: router + global providers + responsive application shell.
 * `/lab` is the in-app component interaction lab (TSC-UX-001); feature routes
 * are added by later tasks.
 */
function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/lab" element={<Lab />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
    </ToastProvider>
  )
}

export default App
