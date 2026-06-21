import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { orchestratorApi, type PendingTicket } from '../../api/orchestratorClient'

const FSM_COLORS: Record<string, string> = {
  backlog: 'badge-muted',
  triage: 'badge-amber',
  specification: 'badge-amber',
  architecture_review: 'badge-amber',
  implementation: 'badge-blue',
  code_review: 'badge-amber',
  security_review: 'badge-amber',
  testing: 'badge-amber',
  release: 'badge-amber',
  done: 'badge-green',
  BLOCKED: 'badge-red',
}

const TYPE_ICONS: Record<string, string> = {
  feature: '✦',
  bugfix: '⚠',
  improvement: '↑',
  other: '?',
}

interface Props {
  onTriggered: () => void
}

export function PendingTicketsPanel({ onTriggered }: Props) {
  const { t } = useTranslation()
  const [tickets, setTickets] = useState<PendingTicket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [triggering, setTriggering] = useState<string | null>(null)
  const [triggered, setTriggered] = useState<Set<string>>(new Set())

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await orchestratorApi.getPendingTickets()
      setTickets(data.tickets)
    } catch {
      setError(t('common.error'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleTrigger = async (ticket: PendingTicket) => {
    setTriggering(ticket.id)
    try {
      await orchestratorApi.triggerJob(ticket.id, ticket.project_id)
      setTriggered(s => new Set(s).add(ticket.id))
      onTriggered()
    } catch (err: any) {
      const detail = err?.response?.data?.detail || t('common.error')
      setError(detail)
    } finally {
      setTriggering(null)
    }
  }

  const hasTags = (t: PendingTicket, tag: string) => t.tags.includes(tag)

  return (
    <div>
      <div className="flex" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div className="card-title">{t('queue.pending_tickets')} {!loading && `(${tickets.length})`}</div>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
          ↻ {t('queue.refresh')}
        </button>
      </div>

      {error && <div className="error-banner mb-16">{error}</div>}

      {loading ? (
        <div className="empty-state"><span className="spinner" /></div>
      ) : tickets.length === 0 ? (
        <div className="empty-state">{t('queue.no_pending')}</div>
      ) : (
        <div className="flex flex-col gap-8">
          {tickets.map(ticket => {
            const isTriggered = triggered.has(ticket.id)
            const isTriggering = triggering === ticket.id
            const needsEstimation = hasTags(ticket, 'needs-estimation')
            const fsmColor = FSM_COLORS[ticket.fsm_status ?? 'backlog'] ?? 'badge-muted'

            return (
              <div
                key={ticket.id}
                className="card"
                style={{ padding: '12px 16px', display: 'flex', alignItems: 'flex-start', gap: 12 }}
              >
                {/* Type icon */}
                <div style={{
                  width: 28, height: 28, borderRadius: 4,
                  background: 'var(--bg-3)', display: 'flex',
                  alignItems: 'center', justifyContent: 'center',
                  color: 'var(--amber)', fontSize: '0.85rem', flexShrink: 0,
                }}>
                  {TYPE_ICONS[ticket.ticket_type ?? 'other'] ?? '?'}
                </div>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: '0.9rem', marginBottom: 4,
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {ticket.title}
                  </div>
                  <div className="flex gap-8" style={{ flexWrap: 'wrap' }}>
                    <span className={`badge ${fsmColor}`}>
                      {ticket.fsm_status ?? 'backlog'}
                    </span>
                    {ticket.ticket_type && (
                      <span className="badge badge-muted">{ticket.ticket_type}</span>
                    )}
                    {needsEstimation && (
                      <span className="badge badge-amber">needs-estimation</span>
                    )}
                    {ticket.blocked_reason && (
                      <span className="badge badge-red" title={ticket.blocked_reason}>⊘ blocked</span>
                    )}
                    {ticket.assigned_agent && (
                      <span className="badge badge-muted">→ {ticket.assigned_agent}</span>
                    )}
                    <span className="mono text-muted">{ticket.id}</span>
                  </div>
                </div>

                {/* Trigger button */}
                <div style={{ flexShrink: 0 }}>
                  {isTriggered ? (
                    <span className="badge badge-green">✓ {t('queue.sent')}</span>
                  ) : (
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleTrigger(ticket)}
                      disabled={isTriggering || needsEstimation}
                      title={needsEstimation ? t('queue.needs_estimation_hint') : undefined}
                    >
                      {isTriggering
                        ? <><span className="spinner" />{t('queue.sending')}</>
                        : `▶ ${t('queue.send_to_work')}`}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
