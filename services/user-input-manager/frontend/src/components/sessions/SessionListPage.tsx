import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { sessionsApi, extractError, type Session } from '../../api/client'
import { NewSessionModal } from './NewSessionModal'

function statusBadge(status: string, t: (k: string) => string) {
  const map: Record<string, [string, string]> = {
    in_progress: ['badge-amber', 'session.status_in_progress'],
    approved: ['badge-green', 'session.status_approved'],
    cancelled: ['badge-muted', 'session.status_cancelled'],
  }
  const [cls, key] = map[status] ?? ['badge-muted', status]
  return <span className={`badge ${cls}`}>{t(key)}</span>
}

export function SessionListPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [sessions, setSessions] = useState<Session[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showNew, setShowNew] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await sessionsApi.list()
      setSessions(data.items)
      setTotal(data.total)
    } catch (err) {
      setError(extractError(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const onCreated = (sessionId: string) => {
    setShowNew(false)
    navigate(`/sessions/${sessionId}`)
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('nav.sessions')}</h1>
        <button className="btn btn-primary" onClick={() => setShowNew(true)}>
          + {t('session.new')}
        </button>
      </div>

      {error && <div className="error-banner mb-16">{error}</div>}

      {loading ? (
        <div className="empty-state"><span className="spinner" /></div>
      ) : sessions.length === 0 ? (
        <div className="empty-state">{t('session.empty')}</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="sessions-table">
            <thead>
              <tr>
                <th>{t('session.project_type')}</th>
                <th>Status</th>
                <th>{t('session.ticket_title_label')}</th>
                <th>{t('admin.created')}</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map(s => (
                <tr key={s.id} onClick={() => navigate(`/sessions/${s.id}`)}>
                  <td>
                    <div>{s.tm_project_name || s.tm_project_id || '—'}</div>
                    <div className="text-muted">{t(`session.${s.session_type}`)}</div>
                  </td>
                  <td>{statusBadge(s.status, t)}</td>
                  <td>{s.tm_ticket_title || '—'}</td>
                  <td className="mono" style={{ fontSize: '0.75rem' }}>
                    {new Date(s.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showNew && (
        <NewSessionModal onClose={() => setShowNew(false)} onCreated={onCreated} />
      )}
    </div>
  )
}
