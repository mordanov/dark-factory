import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { sessionsApi, extractError, type Iteration, type Session } from '../../api/client'
import { usePlanStore } from '../../store/planStore'
import { PlanningModal } from './PlanningModal'

export function SessionDetailPage() {
  const { t } = useTranslation()
  const { sessionId } = useParams<{ sessionId: string }>()

  const [session, setSession] = useState<Session | null>(null)
  const [iterations, setIterations] = useState<Iteration[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [comment, setComment] = useState('')
  const [showPlanning, setShowPlanning] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { reset: resetPlan } = usePlanStore()

  const loadFull = async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const [sessResp, itersResp] = await Promise.all([
        sessionsApi.list(0, 100),
        sessionsApi.getIterations(sessionId),
      ])
      const found = sessResp.data.items.find(s => s.id === sessionId) || null
      setSession(found)
      setIterations(itersResp.data)
    } catch (err) {
      setError(extractError(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadFull() }, [sessionId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [iterations.length])

  const lastAssistant = [...iterations].reverse().find(i => i.role === 'assistant')
  const isInProgress = session?.status === 'in_progress'
  const pendingFeedback = isInProgress && lastAssistant && lastAssistant.is_approved === null

  const handleFeedback = async (isApproved: boolean) => {
    if (!sessionId) return
    setSubmitting(true)
    setError('')
    try {
      await sessionsApi.feedback(sessionId, {
        is_approved: isApproved,
        comment: comment || undefined,
      })
      setComment('')
      await loadFull()
    } catch (err) {
      setError(extractError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handleRevert = async (targetNumber: number) => {
    if (!sessionId) return
    setSubmitting(true)
    try {
      await sessionsApi.revert(sessionId, targetNumber)
      await loadFull()
    } catch (err) {
      setError(extractError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const handleOpenPlanning = () => {
    resetPlan()
    setShowPlanning(true)
  }

  const handlePlanningClose = async () => {
    setShowPlanning(false)
    await loadFull()
  }

  const statusBadgeClass = (status: Session['status']) => {
    switch (status) {
      case 'approved':
      case 'plan_ready':
        return 'badge-green'
      case 'in_progress':
      case 'planning':
      case 'plan_confirmed':
        return 'badge-amber'
      case 'tickets_created':
        return 'badge-green'
      default:
        return 'badge-muted'
    }
  }

  if (loading) return <div className="empty-state"><span className="spinner" /></div>
  if (!session) return <div className="error-banner">{t('common.error')}</div>

  const planningStatuses: Array<Session['status']> = ['planning', 'plan_ready', 'plan_confirmed', 'tickets_created']
  const sessionPlanActive = planningStatuses.includes(session.status)

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="text-muted mono" style={{ marginBottom: 4 }}>
            {t(`session.${session.session_type}`)} · {session.tm_project_name || session.tm_project_id}
          </div>
          <h1 className="page-title">{session.tm_ticket_title || t('session.new')}</h1>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className={`badge ${statusBadgeClass(session.status)}`}>
            {t(`session.status_${session.status}`, { defaultValue: session.status })}
          </span>
          {session.status === 'approved' && (
            <button className="btn btn-primary" onClick={handleOpenPlanning}>
              {t('planning.generate_plan')}
            </button>
          )}
          {sessionPlanActive && session.status !== 'tickets_created' && (
            <button className="btn btn-secondary" onClick={handleOpenPlanning}>
              {t('planning.plan_title')}
            </button>
          )}
        </div>
      </div>

      {error && <div className="error-banner mb-16">{error}</div>}

      {/* Tickets created success banner */}
      {session.status === 'tickets_created' && (
        <div className="success-box mb-16" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>{t('planning.tickets_created', { count: session.tm_ticket_id ? 1 : 0 })}</span>
          {session.tm_project_id && (
            <a href={`/ticket-manager/projects/${session.tm_project_id}`} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
              {t('planning.view_in_tm')} ↗
            </a>
          )}
        </div>
      )}

      {/* Iterations */}
      <div className="flex flex-col gap-12">
        {iterations.map((iter, idx) => {
          const isCurrent = idx === iterations.length - 1
          const isAssistant = iter.role === 'assistant'

          return (
            <div
              key={iter.id}
              className={`iteration-card role-${iter.role} ${isCurrent ? 'is-current' : ''}`}
            >
              <div className="iteration-header">
                <span className={`badge ${isAssistant ? 'badge-amber' : 'badge-muted'}`}>
                  {isAssistant ? 'AI' : 'You'}
                </span>
                <span>{t('session.version')} {iter.iteration_number}</span>
                {iter.is_approved === true && <span className="badge badge-green">✓</span>}
                {isAssistant && !isCurrent && isInProgress && (
                  <button
                    className="btn btn-ghost btn-sm"
                    style={{ marginLeft: 'auto' }}
                    onClick={() => handleRevert(iter.iteration_number)}
                    disabled={submitting}
                  >
                    ↩ {t('session.revert_to')}
                  </button>
                )}
              </div>

              <div className="iteration-prompt">{iter.prompt_text}</div>

              {isAssistant && (iter.llm_assessment || iter.llm_questions) && (
                <div className="iteration-meta">
                  {iter.llm_assessment && (
                    <div>
                      <div className="meta-label">{t('session.assessment')}</div>
                      <div className="meta-text">{iter.llm_assessment}</div>
                    </div>
                  )}
                  {iter.llm_questions && (
                    <div>
                      <div className="meta-label">{t('session.questions')}</div>
                      <div className="meta-text">{iter.llm_questions}</div>
                    </div>
                  )}
                </div>
              )}

              {iter.user_comment && (
                <div className="iteration-meta">
                  <div>
                    <div className="meta-label" style={{ color: 'var(--text-muted)' }}>Comment</div>
                    <div className="meta-text">{iter.user_comment}</div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Feedback section */}
      {pendingFeedback && (
        <div className="feedback-section">
          <div className="form-group">
            <label htmlFor="comment">{t('session.your_comment')}</label>
            <textarea
              id="comment"
              value={comment}
              onChange={e => setComment(e.target.value)}
              rows={3}
              placeholder={lastAssistant?.llm_questions || ''}
            />
          </div>

          <div className="feedback-actions">
            <button
              className="btn btn-primary"
              onClick={() => handleFeedback(true)}
              disabled={submitting}
            >
              {submitting ? <span className="spinner" /> : '✓'} {t('session.approve')}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => handleFeedback(false)}
              disabled={submitting}
            >
              {t('session.refine_more')}
            </button>
          </div>
        </div>
      )}

      <div ref={bottomRef} />

      {showPlanning && session && (
        <PlanningModal
          sessionId={session.id}
          tmProjectId={session.tm_project_id}
          onClose={handlePlanningClose}
        />
      )}
    </div>
  )
}
