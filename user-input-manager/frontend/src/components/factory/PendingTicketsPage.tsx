import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { jobsApi, pendingApi, type OrchestratorTicket } from '../../api/orchestrator'

function fsmBadge(status: string | null) {
  if (!status) return <span className="badge badge-muted">—</span>
  const map: Record<string, string> = {
    backlog: 'badge-muted', triage: 'badge-amber', specification: 'badge-amber',
    architecture_review: 'badge-amber', implementation: 'badge-blue',
    code_review: 'badge-blue', security_review: 'badge-blue',
    testing: 'badge-blue', release: 'badge-blue',
    done: 'badge-green', BLOCKED: 'badge-red',
  }
  return <span className={`badge ${map[status] ?? 'badge-muted'}`}>{status}</span>
}

export function PendingTicketsPage() {
  const { t } = useTranslation()
  const [tickets, setTickets] = useState<OrchestratorTicket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [triggering, setTriggering] = useState<string | null>(null)
  const [flash, setFlash] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await pendingApi.list()
      setTickets(data.tickets)
    } catch {
      setError(t('common.error'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleTrigger = async (ticket: OrchestratorTicket) => {
    setTriggering(ticket.id)
    setFlash(null)
    try {
      await jobsApi.trigger(ticket.id, ticket.project_id)
      setFlash(t('factory.triggered'))
      await load()
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(detail === 'A job for this ticket is already running'
        ? 'Job already running for this ticket'
        : t('common.error'))
    } finally {
      setTriggering(null)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('factory.pending')}</h1>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
          ↺ {t('factory.refresh')}
        </button>
      </div>

      {flash && (
        <div className="success-box mb-16">{flash}</div>
      )}
      {error && <div className="error-banner mb-16">{error}</div>}

      {loading ? (
        <div className="empty-state"><span className="spinner" /></div>
      ) : tickets.length === 0 ? (
        <div className="empty-state">{t('factory.no_pending')}</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="sessions-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>{t('factory.fsm_status')}</th>
                <th>{t('factory.assigned_agent')}</th>
                <th>{t('factory.tags')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {tickets.map(ticket => (
                <tr key={ticket.id} style={{ cursor: 'default' }}>
                  <td className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {ticket.id}
                  </td>
                  <td>
                    <div style={{ fontWeight: 500 }}>{ticket.title}</div>
                    {ticket.blocked_reason && (
                      <div className="text-muted" style={{ fontSize: '0.75rem', marginTop: 2 }}>
                        ⚠ {ticket.blocked_reason}
                      </div>
                    )}
                  </td>
                  <td>{fsmBadge(ticket.fsm_status)}</td>
                  <td>
                    {ticket.assigned_agent
                      ? <span className="badge badge-muted mono">{ticket.assigned_agent}</span>
                      : '—'}
                  </td>
                  <td>
                    <div className="flex gap-8" style={{ flexWrap: 'wrap' }}>
                      {ticket.tags.map(tag => (
                        <span
                          key={tag}
                          className={`badge ${tag === 'needs-estimation' ? 'badge-amber' : 'badge-muted'}`}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleTrigger(ticket)}
                      disabled={triggering === ticket.id}
                    >
                      {triggering === ticket.id
                        ? <><span className="spinner" />{t('factory.triggering')}</>
                        : t('factory.trigger')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
