import { useEffect } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AppRoutes } from './pages/AppRoutes'
import { authApi } from './api/client'
import { useAuthStore } from './store/auth'
import './i18n/i18n'
import './styles/global.css'

function AuthRestorer({ children }: { children: React.ReactNode }) {
  const { refreshToken, setAccessToken, setRestored } = useAuthStore()

  useEffect(() => {
    if (!refreshToken) {
      setRestored()
      return
    }
    authApi.refresh(refreshToken)
      .then(({ data }) => setAccessToken(data.access_token))
      .catch(() => useAuthStore.getState().logout())
      .finally(() => setRestored())
  }, []) // run once on mount

  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthRestorer>
        <AppRoutes />
      </AuthRestorer>
    </BrowserRouter>
  )
}
