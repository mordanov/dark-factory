import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { authApi, type User } from '../../api/client'
import { useAuthStore } from '../../store/auth'

export function LoginPage() {
  const { t } = useTranslation()
  const login = useAuthStore((s) => s.login)
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await authApi.login(email, password)
      const [, payload] = data.access_token.split('.')
      const claims = JSON.parse(atob(payload))
      const partialUser: User = {
        id: claims.sub,
        email,
        full_name: '',
        is_admin: claims.is_admin,
        is_active: true,
        created_at: '',
        updated_at: '',
      }
      login(data.access_token, data.refresh_token, partialUser)
      navigate('/sessions')
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 401) setError(t('auth.invalid_credentials'))
      else if (status === 403) setError(t('auth.account_disabled'))
      else setError(t('common.error'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-box">
        <div className="login-header">
          <div className="login-tagline">{t('app.tagline')}</div>
          <h1 className="login-title">{t('auth.login')}</h1>
        </div>

        <div className="card">
          <form onSubmit={handleSubmit} className="flex flex-col gap-16">
            <div className="form-group">
              <label htmlFor="email">{t('auth.email')}</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="form-group">
              <label htmlFor="password">{t('auth.password')}</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
              />
            </div>

            {error && <div className="error-banner">{error}</div>}

            <button className="btn btn-primary w-full" type="submit" disabled={loading}>
              {loading ? (
                <><span className="spinner" />{t('auth.signing_in')}</>
              ) : t('auth.login')}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
