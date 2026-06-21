import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { auditApi, type AuditEntry } from '../../api/orchestrator'

const ACTION_BADGE: Record<string, string> = {
  ADVANCE: 'badge-green',
  BLOCK: 'badge-red',
  WAIT: 'badge-amber',
  ASSIGN: 'badge-blue',
  GENERATE_ADR: 'badge-amber',
  OVERRIDE_ACCEPTED: 'badge-amber',
  ERROR: 'badge-red',
}

function Arrow() {
  return <span style={{ color: 'var(--text-muted)', margin: '0 4px' }}>→</span>
}

export function AuditTrailPage() {
  const { t } = useTranslation()
  const [ticketId, setTicketId] = useState('')
  const [input, setInput] = useState('')
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [searched, setSearched] = useState(false)

  const search = async () => {
    if (!input.trim()) return
    setLoading(true)
    setError('')
    try {
      const { data } = await auditApi.list(input.trim())
      setEntries(data.items)
      setTotal(data.total)
      setTicketId(input.trim())
      setSearched(true)
    } catch (err: any) {
      setError(err?.response?.status === 404 ? 'No audit entries found' : t('common.error'))
      setEntries([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('factory.audit')}</h1>
      </div>

      <div className="flex gap-8 mb-24" style={{ maxWidth: 480 }}>
        <input
          placeholder={t('factory.enter_ticket_id')}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
        />
        <button className="btn btn-primary" onClick={search} disabled={loading || !input.trim()}>
          {loading ? <span className="spinner" /> : t('factory.search')}
        </button>
      </div>

      {error && <div className="error-banner mb-16">{error}</div>}

      {searched && entries.length === 0 && !loading && (
        <div className="empty-state">{t('factory.no_audit')}</div>
      )}

      {entries.length > 0 && (
        <>
          <div className="text-muted mb-16" style={{ fontSize: '0.75rem' }}>
            Ticket: <span className="mono">{ticketId}</span> — {total} entries
          </div>

          <div className="flex flex-col gap-8">
            {entries.map((entry, idx) => (
              <div key={entry.id} className="card" style={{ padding: '12px 16px' }}>
                <div className="flex gap-12" style={{ alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
                  {/* Index */}
                  <span className="mono text-muted" style={{ fontSize: '0.7rem', minWidth: 24 }}>
                    {idx + 1}
                  </span>

                  {/* Action badge */}
                  <span className={`badge ${ACTION_BADGE[entry.action] ?? 'badge-muted'}`}>
                    {entry.action}
                  </span>

                  {/* State transition */}
                  {(entry.from_state || entry.to_state) && (
                    <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                      {entry.from_state ?? '?'}
                      <Arrow />
                      {entry.to_state ?? '?'}
                    </span>
                  )}

                  {/* Agent */}
                  {entry.assigned_agent && (
                    <span className="badge badge-muted mono">{entry.assigned_agent}</span>
                  )}

                  {/* Override marker */}
                  {entry.override_logged && (
                    <span className="badge badge-amber">OVERRIDE</span>
                  )}

                  {/* Timestamp */}
                  <span className="mono text-muted" style={{ fontSize: '0.7rem', marginLeft: 'auto' }}>
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                </div>

                {/* Details */}
                {entry.details && (
                  <div className="meta-text">{entry.details}</div>
                )}

                {/* Blocked reason */}
                {entry.blocked_reason && (
                  <div style={{ marginTop: 6, fontSize: '0.8rem', color: 'var(--red)' }}>
                    ⚠ {entry.blocked_reason}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
