import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from '../../store/auth'

export function Sidebar() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()

  const isActive = (path: string) => location.pathname.startsWith(path)

  const toggleLang = () => {
    i18n.changeLanguage(i18n.language === 'en' ? 'ru' : 'en')
  }

  const kcBase = import.meta.env.VITE_KEYCLOAK_URL as string | undefined
  const kcConsoleUrl = kcBase ? `${kcBase}/admin/dark-factory/console` : null

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="tagline">{t('app.tagline')}</div>
        <div className="name">{t('app.name')}</div>
      </div>

      <nav className="sidebar-nav">
        <button
          className={`nav-item ${isActive('/sessions') ? 'active' : ''}`}
          onClick={() => navigate('/sessions')}
        >
          <span>⬡</span>
          {t('nav.sessions')}
        </button>

        <button
          className={`nav-item ${isActive('/queue') ? 'active' : ''}`}
          onClick={() => navigate('/queue')}
        >
          <span>◎</span>
          {t('nav.queue')}
        </button>

        {user?.isAdmin && kcConsoleUrl && (
          <a
            className="nav-item"
            href={kcConsoleUrl}
            target="_blank"
            rel="noreferrer noopener"
            aria-label={`${t('nav.admin')} (opens in new tab)`}
          >
            <span aria-hidden="true">◈</span>
            {t('nav.admin')}
          </a>
        )}
      </nav>

      <div className="sidebar-footer">
        <button className="btn btn-ghost btn-sm" onClick={toggleLang} style={{ justifyContent: 'flex-start' }}>
          {t('common.language')}: {i18n.language.toUpperCase()}
        </button>
        <div className="user-info">{user?.email}</div>
        <button className="btn btn-ghost btn-sm" onClick={() => void logout()}>
          {t('nav.logout')}
        </button>
      </div>
    </aside>
  )
}
