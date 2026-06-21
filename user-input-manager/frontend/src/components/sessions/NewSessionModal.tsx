import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { sessionsApi, tmApi, extractError, type TmProject } from '../../api/client'

interface Props {
  onClose: () => void
  onCreated: (sessionId: string) => void
}

export function NewSessionModal({ onClose, onCreated }: Props) {
  const { t } = useTranslation()

  const [sessionType, setSessionType] = useState<'new_project' | 'existing_project'>('new_project')
  const [projectName, setProjectName] = useState('')
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [prompt, setPrompt] = useState('')
  const [projects, setProjects] = useState<TmProject[]>([])
  const [loadingProjects, setLoadingProjects] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (sessionType === 'existing_project') {
      setLoadingProjects(true)
      tmApi.listProjects()
        .then(r => setProjects(r.data))
        .catch((err) => setError(extractError(err)))
        .finally(() => setLoadingProjects(false))
    }
  }, [sessionType])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const payload: any = { session_type: sessionType, initial_prompt: prompt }
      if (sessionType === 'new_project') payload.tm_project_name = projectName
      else payload.tm_project_id = selectedProjectId

      const { data } = await sessionsApi.create(payload)
      onCreated(data.session.id)
    } catch (err) {
      setError(extractError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <h2 className="modal-title">{t('session.new')}</h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-16">
          {/* Session type */}
          <div className="form-group">
            <label>{t('session.project_type')}</label>
            <div className="flex gap-8" style={{ marginTop: 4 }}>
              {(['new_project', 'existing_project'] as const).map(type => (
                <button
                  key={type}
                  type="button"
                  className={`btn ${sessionType === type ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setSessionType(type)}
                >
                  {t(`session.${type}`)}
                </button>
              ))}
            </div>
          </div>

          {/* Project name or selector */}
          {sessionType === 'new_project' ? (
            <div className="form-group">
              <label htmlFor="proj-name">{t('session.project_name')}</label>
              <input
                id="proj-name"
                value={projectName}
                onChange={e => setProjectName(e.target.value)}
                required
              />
            </div>
          ) : (
            <div className="form-group">
              <label htmlFor="proj-select">{t('session.select_project')}</label>
              {loadingProjects ? (
                <div className="text-muted">{t('session.loading_projects')}</div>
              ) : (
                <select
                  id="proj-select"
                  value={selectedProjectId}
                  onChange={e => setSelectedProjectId(e.target.value)}
                  required
                >
                  <option value="">—</option>
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              )}
            </div>
          )}

          {/* Initial prompt */}
          <div className="form-group">
            <label htmlFor="initial-prompt">{t('session.initial_prompt')}</label>
            <textarea
              id="initial-prompt"
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              rows={5}
              required
              placeholder="E.g. Add OAuth 2.0 login with Google to the mobile app"
            />
          </div>

          {error && <div className="error-banner">{error}</div>}

          <div className="modal-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              {t('common.close')}
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? <><span className="spinner" />{t('session.starting')}</> : t('session.start')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
