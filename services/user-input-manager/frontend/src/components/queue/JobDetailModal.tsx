import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { orchestratorApi, type AuditEntry, type OrchestratorJob } from '../../api/orchestratorClient'

interface Props {
  job: OrchestratorJob
  onClose: () => void
}

const ACTION_COLORS: Record<string, string> = {
  ADVANCE: 'badge-green',
  BLOCK: 'badge-red',
  WAIT: 'badge-amber',
  ASSIGN: 'badge-amber',
  GENERATE_ADR: 'badge-muted',
  OVERRIDE_ACCEPTED: 'badge-amber',
  ERROR: 'badge-red',
  WAIT_DEPS: 'badge-muted',
}

function duration(job: OrchestratorJob): string {
  if (!job.started_at || !job.finished_at) return '—'
  const ms = new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

export function JobDetailModal({ job, onClose }: Props) {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    orchestratorApi.getAuditTrail(job.ticket_id)
      .then(r => setEntries(r.data.items))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [job.ticket_id])

  const statusBadge = (s: string) => {
    const cls = s === 'done' ? 'badge-green' : s === 'failed' ? 'badge-red'
      : s === 'running' ? 'badge-amber' : 'badge-muted'
    return <span className={`badge ${cls}`}>{s}</span>
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: 620, maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h2 className="modal-title" style={{ margin: 0 }}>
            {t('queue.job_detail')}
          </h2>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        {/* Job summary */}
        <div className="card" style={{ marginBottom: 16, padding: '12px 16px' }}>
          <div className="flex gap-12" style={{ flexWrap: 'wrap' }}>
            <div>
              <div className="meta-label">{t('queue.ticket_id')}</div>
              <div className="mono" style={{ fontSize: '0.8rem' }}>{job.ticket_id}</div>
            </div>
            <div>
              <div className="meta-label">{t('queue.status')}</div>
              {statusBadge(job.status)}
            </div>
            <div>
              <div className="meta-label">{t('queue.job_type')}</div>
              <span className="badge badge-muted">{job.job_type}</span>
            </div>
            <div>
              <div className="meta-label">{t('queue.duration')}</div>
              <div className="mono" style={{ fontSize: '0.8rem' }}>{duration(job)}</div>
            </div>
            <div>
              <div className="meta-label">{t('queue.triggered_by')}</div>
              <div className="mono" style={{ fontSize: '0.8rem' }}>{job.triggered_by}</div>
            </div>
          </div>

          {job.error_message && (
            <div className="error-banner mt-8" style={{ fontSize: '0.8rem' }}>
              {job.error_message}
            </div>
          )}
        </div>

        {/* Audit trail */}
        <div className="card-title mb-16">{t('queue.audit_trail')}</div>
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {loading ? (
            <div className="empty-state"><span className="spinner" /></div>
          ) : entries.length === 0 ? (
            <div className="empty-state text-muted">{t('queue.no_audit')}</div>
          ) : (
            <div className="flex flex-col gap-8">
              {entries.map(e => (
                <div key={e.id} className="iteration-card" style={{ borderLeftColor: 'var(--border-light)', marginBottom: 0 }}>
                  <div className="iteration-header">
                    <span className={`badge ${ACTION_COLORS[e.action] ?? 'badge-muted'}`}>
                      {e.action}
                    </span>
                    {e.from_state && (
                      <span className="text-muted">
                        {e.from_state}
                        {e.to_state && <> → <span style={{ color: 'var(--green)' }}>{e.to_state}</span></>}
                      </span>
                    )}
                    {e.assigned_agent && (
                      <span className="badge badge-muted">{e.assigned_agent}</span>
                    )}
                    <span className="mono" style={{ marginLeft: 'auto', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      {new Date(e.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="meta-text" style={{ marginTop: 6 }}>{e.details}</div>
                  {e.blocked_reason && (
                    <div style={{ marginTop: 4, fontSize: '0.78rem', color: 'var(--red)' }}>
                      ⊘ {e.blocked_reason}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
