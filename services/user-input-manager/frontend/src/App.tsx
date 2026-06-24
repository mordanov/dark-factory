import { useEffect } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './pages/AppRoutes'
import { useAuthStore } from './store/auth'
import { LoadingScreen } from './components/layout/LoadingScreen'
import { AuthErrorScreen } from './components/layout/AuthErrorScreen'
import './i18n/i18n'
import './styles/global.css'

export default function App() {
  const initialized = useAuthStore((s) => s.initialized)
  const initError = useAuthStore((s) => s.initError)
  const initialize = useAuthStore((s) => s.initialize)

  useEffect(() => {
    initialize()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (initError) return <AuthErrorScreen onRetry={() => void initialize()} />
  if (!initialized) return <LoadingScreen />

  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
