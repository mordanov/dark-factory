import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { sessionsApi, extractError, type Session } from '../../api/client'

interface Props {
  session: Session
  suggestedTitle: string
  onClose: () => void
  onApproved: (ticketId: string) => void
}

export function ApproveModal({ session, suggestedTitle, onClose, onApproved }: Props) {
  const { t } = useTranslation()

  const [title, setTitle] = useState(suggestedTitle)
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const payload: any = { ticket_title: title }
      if (session.session_type === 'new_project' && description) {
        payload.project_description = description
      }
      const { data } = await sessionsApi.approve(session.id, payload)
      onApproved(data.ticket_id)
    } catch (err) {
      setError(extractError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <h2 className="modal-title">{t('session.approve_title')}</h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-16">
          <div className="form-group">
            <label htmlFor="ticket-title">{t('session.ticket_title_label')}</label>
            <input
              id="ticket-title"
              value={title}
              onChange={e => setTitle(e.target.value)}
              required
              maxLength={500}
            />
          </div>

          {session.session_type === 'new_project' && (
            <div className="form-group">
              <label htmlFor="proj-desc">{t('session.project_description_label')}</label>
              <textarea
                id="proj-desc"
                value={description}
                onChange={e => setDescription(e.target.value)}
                rows={3}
              />
            </div>
          )}

          {error && <div className="error-banner">{error}</div>}

          <div className="modal-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              {t('common.close')}
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting || !title}>
              {submitting ? <><span className="spinner" />{t('session.creating_ticket')}</> : t('session.confirm_approve')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
