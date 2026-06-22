import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { workflowApi, type AuditEntry } from '../../api/orchestrator'

interface Props {
  ticketId: string
  ticketTitle: string
  onClose: () => void
}

const ACTION_COLORS: Record<string, string> = {
  ADVANCE: 'var(--green)',
  BLOCK: 'var(--red)',
  WAIT: 'var(--text-muted)',
  ASSIGN: 'var(--blue)',
  GENERATE_ADR: 'var(--amber)',
  OVERRIDE_ACCEPTED: 'var(--amber)',
  ERROR: 'var(--red)',
}

export function AuditTrailModal({ ticketId, ticketTitle, onClose }: Props) {
  const { t } = useTranslation()
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    workflowApi.getAudit(ticketId)
      .then(r => setEntries(r.data.items))
      .catch(() => setError(t('common.error')))
      .finally(() => setLoading(false))
  }, [ticketId])

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: 680, maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <div className="modal-title" style={{ marginBottom: 2 }}>{t('workflow.audit_trail')}</div>
            <div className="text-muted mono" style={{ fontSize: '0.75rem' }}>{ticketTitle}</div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>

        <div style={{ overflowY: 'auto', flex: 1 }}>
          {loading && <div className="empty-state"><span className="spinner" /></div>}
          {error && <div className="error-banner">{error}</div>}
          {!loading && entries.length === 0 && (
            <div className="empty-state">{t('workflow.no_audit')}</div>
          )}

          {entries.map((entry, idx) => (
            <div key={entry.id} style={{
              display: 'flex',
              gap: 12,
              padding: '10px 0',
              borderBottom: idx < entries.length - 1 ? '1px solid var(--border)' : 'none',
            }}>
              {/* Timeline dot */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                <div style={{
                  width: 28, height: 28,
                  borderRadius: '50%',
                  background: 'var(--bg-2)',
                  border: `2px solid ${ACTION_COLORS[entry.action] ?? 'var(--border-light)'}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '0.6rem', fontFamily: 'var(--font-mono)',
                  color: ACTION_COLORS[entry.action] ?? 'var(--text-muted)',
                }}>
                  {entry.action.slice(0, 2)}
                </div>
                {idx < entries.length - 1 && (
                  <div style={{ width: 2, flex: 1, background: 'var(--border)', marginTop: 4 }} />
                )}
              </div>

              {/* Content */}
              <div style={{ flex: 1, paddingBottom: 8 }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                  <span className="badge" style={{
                    background: `${ACTION_COLORS[entry.action]}22`,
                    color: ACTION_COLORS[entry.action] ?? 'var(--text-muted)',
                  }}>
                    {entry.action}
                  </span>
                  {entry.from_state && entry.to_state && (
                    <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {entry.from_state} → {entry.to_state}
                    </span>
                  )}
                  {entry.override_logged && (
                    <span className="badge badge-amber">override</span>
                  )}
                </div>

                {entry.assigned_agent && (
                  <div style={{ fontSize: '0.75rem', color: 'var(--blue)', marginBottom: 3 }}>
                    → {entry.assigned_agent}
                  </div>
                )}

                {entry.details && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                    {entry.details}
                  </div>
                )}

                {entry.blocked_reason && (
                  <div style={{
                    marginTop: 4, padding: '4px 8px',
                    background: 'rgba(224,92,92,0.08)',
                    borderRadius: 'var(--radius)',
                    fontSize: '0.75rem', color: 'var(--red)',
                  }}>
                    {entry.blocked_reason}
                  </div>
                )}

                <div className="mono" style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>
                  {new Date(entry.created_at).toLocaleString()}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
