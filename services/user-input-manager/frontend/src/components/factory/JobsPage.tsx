import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { jobsApi, type OrchestratorJob } from '../../api/orchestrator'

const STATUS_BADGE: Record<string, string> = {
  pending: 'badge-amber',
  running: 'badge-blue',
  done: 'badge-green',
  failed: 'badge-red',
}

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation()
  return (
    <span className={`badge ${STATUS_BADGE[status] ?? 'badge-muted'}`}>
      {t(`factory.status_${status}` as any, status)}
    </span>
  )
}

function duration(start: string | null, end: string | null): string {
  if (!start) return '—'
  const s = new Date(start)
  const e = end ? new Date(end) : new Date()
  const sec = Math.round((e.getTime() - s.getTime()) / 1000)
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec / 60)}m ${sec % 60}s`
}

const STATUSES = ['pending', 'running', 'done', 'failed']

export function JobsPage() {
  const { t } = useTranslation()
  const [jobs, setJobs] = useState<OrchestratorJob[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [ticketFilter, setTicketFilter] = useState('')
  const [ticketInput, setTicketInput] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await jobsApi.list({
        status: statusFilter || undefined,
        ticket_id: ticketFilter || undefined,
        limit: 50,
      })
      setJobs(data.items)
      setTotal(data.total)
    } catch {
      setError(t('common.error'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [statusFilter, ticketFilter])

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('factory.jobs')}</h1>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
          ↺ {t('factory.refresh')}
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-12 mb-16" style={{ flexWrap: 'wrap' }}>
        <div style={{ minWidth: 160 }}>
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            style={{ fontSize: '0.8rem' }}
          >
            <option value="">{t('factory.all_statuses')}</option>
            {STATUSES.map(s => (
              <option key={s} value={s}>{t(`factory.status_${s}` as any)}</option>
            ))}
          </select>
        </div>
        <div className="flex gap-8">
          <input
            style={{ minWidth: 200, fontSize: '0.8rem' }}
            placeholder={t('factory.enter_ticket_id')}
            value={ticketInput}
            onChange={e => setTicketInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && setTicketFilter(ticketInput)}
          />
          <button className="btn btn-secondary btn-sm" onClick={() => setTicketFilter(ticketInput)}>
            {t('factory.search')}
          </button>
          {ticketFilter && (
            <button className="btn btn-ghost btn-sm" onClick={() => { setTicketFilter(''); setTicketInput('') }}>
              ✕
            </button>
          )}
        </div>
      </div>

      {error && <div className="error-banner mb-16">{error}</div>}

      {loading ? (
        <div className="empty-state"><span className="spinner" /></div>
      ) : jobs.length === 0 ? (
        <div className="empty-state">{t('factory.no_jobs')}</div>
      ) : (
        <>
          <div className="text-muted mb-16" style={{ fontSize: '0.75rem' }}>
            {total} total
          </div>
          <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
            <table className="sessions-table">
              <thead>
                <tr>
                  <th>{t('factory.job_status')}</th>
                  <th>Ticket</th>
                  <th>{t('factory.job_type')}</th>
                  <th>{t('factory.triggered_by')}</th>
                  <th>Duration</th>
                  <th>{t('factory.attempts')}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <tr key={job.id} style={{ cursor: 'default' }}>
                    <td><StatusBadge status={job.status} /></td>
                    <td>
                      <div className="mono" style={{ fontSize: '0.75rem' }}>{job.ticket_id}</div>
                      <div className="text-muted" style={{ fontSize: '0.7rem' }}>{job.project_id}</div>
                      {job.error_message && (
                        <div style={{ color: 'var(--red)', fontSize: '0.7rem', marginTop: 3 }}>
                          ✗ {job.error_message.slice(0, 80)}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className="badge badge-muted mono">{job.job_type}</span>
                    </td>
                    <td className="text-muted mono" style={{ fontSize: '0.75rem' }}>
                      {job.triggered_by}
                    </td>
                    <td className="mono" style={{ fontSize: '0.75rem' }}>
                      {duration(job.started_at, job.finished_at)}
                    </td>
                    <td className="mono" style={{ fontSize: '0.75rem', textAlign: 'center' }}>
                      {job.attempts}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
