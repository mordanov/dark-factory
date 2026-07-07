import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { usePlanStore } from '../../store/planStore'
import { AgentConfigPanel } from './AgentConfigPanel'
import type { PlanContent, PlanStory, PlanTask } from '../../api/client'

interface Props {
  sessionId: string
  tmProjectId: string | null
  onClose: () => void
}

// ---------- Inline editable field ----------

interface EditableFieldProps {
  value: string
  multiline?: boolean
  readOnly?: boolean
  maxLength?: number
  onSave: (v: string) => void
}

function EditableField({ value, multiline, readOnly, maxLength, onSave }: EditableFieldProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const ref = useRef<HTMLTextAreaElement & HTMLInputElement>(null)

  useEffect(() => { if (editing) ref.current?.focus() }, [editing])

  if (readOnly) {
    return <span style={{ color: 'var(--text-primary)' }}>{value}</span>
  }

  if (!editing) {
    return (
      <span
        role="button"
        tabIndex={0}
        style={{ cursor: 'text', color: 'var(--text-primary)', borderBottom: '1px dashed var(--border-light)' }}
        onClick={() => { setDraft(value); setEditing(true) }}
        onKeyDown={e => e.key === 'Enter' && (setDraft(value), setEditing(true))}
      >
        {value}
      </span>
    )
  }

  const save = () => { setEditing(false); if (draft !== value) onSave(draft) }
  const cancel = () => { setEditing(false); setDraft(value) }

  const sharedProps = {
    ref: ref as React.RefObject<HTMLTextAreaElement>,
    value: draft,
    maxLength,
    onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => setDraft(e.target.value),
    onBlur: save,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') cancel()
      if (!multiline && e.key === 'Enter') { e.preventDefault(); save() }
    },
    style: { width: '100%', minWidth: 200, background: 'var(--bg-2)', border: '1px solid var(--amber)', borderRadius: 'var(--radius)', color: 'var(--text-primary)', padding: '4px 8px', fontSize: 'inherit', fontFamily: 'var(--font-ui)', resize: (multiline ? 'vertical' : 'none') as React.CSSProperties['resize'] },
    rows: multiline ? 3 : 1,
  }

  return <textarea {...sharedProps} />
}

// ---------- Task node ----------

interface TaskNodeProps {
  task: PlanTask
  readOnly: boolean
  onChangeTitle: (v: string) => void
  onChangeDesc: (v: string) => void
  onDelete: () => void
}

function TaskNode({ task, readOnly, onChangeTitle, onChangeDesc, onDelete }: TaskNodeProps) {
  const { t } = useTranslation()
  return (
    <div style={{ marginLeft: 24, padding: '8px 12px', borderLeft: '2px solid var(--border)', marginBottom: 6, background: 'var(--bg-2)', borderRadius: '0 var(--radius) var(--radius) 0' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
        <span className="badge badge-muted" style={{ flexShrink: 0 }}>{t('planning.task_label')}</span>
        <span className="badge badge-muted" style={{ flexShrink: 0 }}>{task.ticket_type}</span>
        <span className="badge badge-amber" style={{ flexShrink: 0 }}>{task.complexity}</span>
        <div style={{ flex: 1, fontSize: '0.875rem' }}>
          <EditableField value={task.title} maxLength={200} readOnly={readOnly} onSave={onChangeTitle} />
        </div>
        {!readOnly && (
          <button className="btn btn-ghost btn-sm" style={{ color: 'var(--red)', flexShrink: 0 }} onClick={onDelete} aria-label="Delete task">✕</button>
        )}
      </div>
      {task.description && (
        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 4, marginLeft: 0 }}>
          <EditableField value={task.description} multiline maxLength={500} readOnly={readOnly} onSave={onChangeDesc} />
        </div>
      )}
      {(task.depends_on?.length ?? 0) > 0 && (
        <div style={{ marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{t('planning.depends_on')}:</span>
          {task.depends_on.map(d => <span key={d} className="badge badge-muted">{d}</span>)}
        </div>
      )}
    </div>
  )
}

// ---------- Story node ----------

interface StoryNodeProps {
  story: PlanStory
  readOnly: boolean
  onChangeTitle: (v: string) => void
  onChangeDesc: (v: string) => void
  onDeleteTask: (taskIdx: number) => void
  onChangeTaskTitle: (taskIdx: number, v: string) => void
  onChangeTaskDesc: (taskIdx: number, v: string) => void
  onDeleteStory: () => void
}

function StoryNode({ story, readOnly, onChangeTitle, onChangeDesc, onDeleteTask, onChangeTaskTitle, onChangeTaskDesc, onDeleteStory }: StoryNodeProps) {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div style={{ marginBottom: 12, border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', background: 'var(--bg-1)', cursor: 'pointer' }} onClick={() => setCollapsed(c => !c)}>
        <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.75rem', userSelect: 'none' }}>{collapsed ? '▶' : '▼'}</span>
        <span className="badge badge-amber" style={{ flexShrink: 0 }}>{t('planning.story_label')}</span>
        <div style={{ flex: 1, fontSize: '0.9rem', fontWeight: 500 }} onClick={e => e.stopPropagation()}>
          <EditableField value={story.title} maxLength={200} readOnly={readOnly} onSave={onChangeTitle} />
        </div>
        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
          {t('planning.story_count', { count: story.tasks.length })}
        </span>
        {!readOnly && (
          <button className="btn btn-ghost btn-sm" style={{ color: 'var(--red)', flexShrink: 0 }} onClick={e => { e.stopPropagation(); onDeleteStory() }} aria-label="Delete story">✕</button>
        )}
      </div>

      {!collapsed && (
        <div style={{ padding: '8px 14px 12px' }}>
          {story.description && (
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: 8 }} onClick={e => e.stopPropagation()}>
              <EditableField value={story.description} multiline maxLength={500} readOnly={readOnly} onSave={onChangeDesc} />
            </div>
          )}
          {story.tasks.map((task, ti) => (
            <TaskNode
              key={task.local_id}
              task={task}
              readOnly={readOnly}
              onChangeTitle={v => onChangeTaskTitle(ti, v)}
              onChangeDesc={v => onChangeTaskDesc(ti, v)}
              onDelete={() => onDeleteTask(ti)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ---------- PlanningModal ----------

export function PlanningModal({ sessionId, tmProjectId, onClose }: Props) {
  const { t } = useTranslation()
  const { plan, isGenerating, isConfirming, error, creationProgress, triggerGeneration, fetchPlan, updatePlan, confirmPlan, stopPolling } = usePlanStore()
  const [saveError, setSaveError] = useState<string | null>(null)

  // On mount: if no plan exists, trigger generation; if plan exists, just display it
  useEffect(() => {
    if (!plan) {
      triggerGeneration(sessionId)
    } else if (plan.status === 'confirmed') {
      // already in progress — fetch plan triggers poll internally on store mount in fetchPlan
      fetchPlan(sessionId)
    }
    return () => stopPolling()
  }, [])

  const readOnly = !plan || plan.status !== 'ready'

  const saveUpdate = async (content: PlanContent) => {
    setSaveError(null)
    try {
      await updatePlan(sessionId, content)
    } catch {
      setSaveError(t('planning.error_validation'))
    }
  }

  // Helpers to produce updated PlanContent immutably
  const withStoryTitle = (si: number, v: string): PlanContent => {
    if (!plan?.plan_content) return plan!.plan_content!
    const stories = plan.plan_content.stories.map((s, i) => i === si ? { ...s, title: v } : s)
    return { ...plan.plan_content, stories }
  }
  const withStoryDesc = (si: number, v: string): PlanContent => {
    if (!plan?.plan_content) return plan!.plan_content!
    const stories = plan.plan_content.stories.map((s, i) => i === si ? { ...s, description: v } : s)
    return { ...plan.plan_content, stories }
  }
  const withTaskTitle = (si: number, ti: number, v: string): PlanContent => {
    if (!plan?.plan_content) return plan!.plan_content!
    const stories = plan.plan_content.stories.map((s, i) => {
      if (i !== si) return s
      const tasks = s.tasks.map((t, j) => j === ti ? { ...t, title: v } : t)
      return { ...s, tasks }
    })
    return { ...plan.plan_content, stories }
  }
  const withTaskDesc = (si: number, ti: number, v: string): PlanContent => {
    if (!plan?.plan_content) return plan!.plan_content!
    const stories = plan.plan_content.stories.map((s, i) => {
      if (i !== si) return s
      const tasks = s.tasks.map((t, j) => j === ti ? { ...t, description: v } : t)
      return { ...s, tasks }
    })
    return { ...plan.plan_content, stories }
  }
  const withDeleteStory = (si: number): PlanContent => {
    if (!plan?.plan_content) return plan!.plan_content!
    return { ...plan.plan_content, stories: plan.plan_content.stories.filter((_, i) => i !== si) }
  }
  const withDeleteTask = (si: number, ti: number): PlanContent => {
    if (!plan?.plan_content) return plan!.plan_content!
    const stories = plan.plan_content.stories.map((s, i) => {
      if (i !== si) return s
      return { ...s, tasks: s.tasks.filter((_, j) => j !== ti) }
    })
    return { ...plan.plan_content, stories }
  }

  const isDone = plan?.status === 'tickets_created' || (creationProgress && creationProgress.created >= creationProgress.total && creationProgress.total > 0)
  const isError = plan?.status === 'error' || (creationProgress && creationProgress.errors.length > 0 && !isDone)

  // ----- Generating overlay -----
  if (isGenerating || (plan && plan.status === 'draft')) {
    return (
      <div className="modal-overlay">
        <div className="modal" style={{ textAlign: 'center', maxWidth: 400 }}>
          <span className="spinner" style={{ width: 32, height: 32, borderWidth: 3, marginBottom: 16 }} />
          <h2 className="modal-title">{t('planning.generating')}</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{t('planning.generating_hint')}</p>
          {error && <div className="error-banner" style={{ marginTop: 16 }}>{error}</div>}
        </div>
      </div>
    )
  }

  // ----- Generation error (no plan) -----
  if (!plan && error) {
    return (
      <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
        <div className="modal" style={{ maxWidth: 480 }}>
          <h2 className="modal-title">{t('planning.plan_title')}</h2>
          <div className="error-banner">{error}</div>
          <div className="modal-actions">
            <button className="btn btn-ghost" onClick={onClose}>{t('planning.cancel')}</button>
            <button className="btn btn-primary" onClick={() => triggerGeneration(sessionId)}>{t('planning.generate_plan')}</button>
          </div>
        </div>
      </div>
    )
  }

  if (!plan?.plan_content) return null

  const { epic, stories } = plan.plan_content

  // ----- Confirming / Creating tickets overlay -----
  if (isConfirming || plan.status === 'confirmed') {
    return (
      <div className="modal-overlay">
        <div className="modal" style={{ maxWidth: 560 }}>
          <h2 className="modal-title">{t('planning.plan_title')}</h2>
          {isDone ? (
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>✓</div>
              <p style={{ color: 'var(--green)', fontWeight: 600, marginBottom: 8 }}>
                {t('planning.tickets_created', { count: creationProgress?.created ?? (plan.created_ticket_ids?.length ?? 0) })}
              </p>
              {tmProjectId && (
                <a href={`/ticket-manager/projects/${tmProjectId}`} target="_blank" rel="noreferrer" className="btn btn-secondary" style={{ display: 'inline-flex', marginTop: 8 }}>
                  {t('planning.view_in_tm')} ↗
                </a>
              )}
              <div className="modal-actions" style={{ justifyContent: 'center', marginTop: 16 }}>
                <button className="btn btn-primary" onClick={onClose}>{t('planning.back_to_sessions')}</button>
              </div>
            </div>
          ) : isError ? (
            <div>
              <div className="error-banner" style={{ marginBottom: 12 }}>{t('planning.error_creation')}</div>
              {creationProgress && (
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: 12 }}>
                  {t('planning.creating_tickets', { created: creationProgress.created, total: creationProgress.total })}
                </p>
              )}
              <div className="modal-actions">
                <button className="btn btn-primary" onClick={() => confirmPlan(sessionId)}>{t('planning.retry_creation')}</button>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '16px 0' }}>
              <span className="spinner" style={{ width: 24, height: 24, borderWidth: 3, marginBottom: 12 }} />
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                {creationProgress
                  ? t('planning.creating_tickets', { created: creationProgress.created, total: creationProgress.total })
                  : t('planning.creating_tickets', { created: 0, total: '…' })}
              </p>
              <div style={{ background: 'var(--bg-2)', borderRadius: 4, overflow: 'hidden', height: 6, marginTop: 12 }}>
                {creationProgress && creationProgress.total > 0 && (
                  <div style={{ background: 'var(--amber)', height: '100%', width: `${(creationProgress.created / creationProgress.total) * 100}%`, transition: 'width 0.4s' }} />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // ----- Done (tickets_created state persisted) -----
  if (plan.status === 'tickets_created') {
    return (
      <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
        <div className="modal" style={{ textAlign: 'center', maxWidth: 480 }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>✓</div>
          <p style={{ color: 'var(--green)', fontWeight: 600, marginBottom: 8 }}>
            {t('planning.tickets_created', { count: plan.created_ticket_ids?.length ?? 0 })}
          </p>
          {tmProjectId && (
            <a href={`/ticket-manager/projects/${tmProjectId}`} target="_blank" rel="noreferrer" className="btn btn-secondary" style={{ display: 'inline-flex', marginTop: 8 }}>
              {t('planning.view_in_tm')} ↗
            </a>
          )}
          <div className="modal-actions" style={{ justifyContent: 'center', marginTop: 16 }}>
            <button className="btn btn-primary" onClick={onClose}>{t('planning.back_to_sessions')}</button>
          </div>
        </div>
      </div>
    )
  }

  // ----- Plan Ready (editable) -----
  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div
        className="modal"
        style={{ maxWidth: 720, width: '100%', maxHeight: '90vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 0 }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 className="modal-title" style={{ margin: 0 }}>{t('planning.plan_title')}</h2>
          <button className="btn btn-ghost btn-sm" onClick={() => triggerGeneration(sessionId)} title={t('planning.regenerate')}>
            ↺ {t('planning.regenerate')}
          </button>
        </div>

        {(error || saveError) && (
          <div className="error-banner" style={{ marginBottom: 12 }}>{error || saveError}</div>
        )}

        {/* Epic */}
        <div className="card" style={{ marginBottom: 16, borderColor: 'var(--amber-dim)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
            <span className="badge badge-amber" style={{ flexShrink: 0 }}>{t('planning.epic_label')}</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '1rem', fontWeight: 600, marginBottom: 4 }}>
                <EditableField
                  value={epic.title}
                  maxLength={200}
                  readOnly={readOnly}
                  onSave={v => saveUpdate({ ...plan.plan_content!, epic: { ...epic, title: v } })}
                />
              </div>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                <EditableField
                  value={epic.description}
                  multiline
                  maxLength={500}
                  readOnly={readOnly}
                  onSave={v => saveUpdate({ ...plan.plan_content!, epic: { ...epic, description: v } })}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Stories */}
        <div>
          {stories.map((story, si) => (
            <StoryNode
              key={story.local_id}
              story={story}
              readOnly={readOnly}
              onChangeTitle={v => saveUpdate(withStoryTitle(si, v))}
              onChangeDesc={v => saveUpdate(withStoryDesc(si, v))}
              onDeleteStory={() => saveUpdate(withDeleteStory(si))}
              onDeleteTask={ti => saveUpdate(withDeleteTask(si, ti))}
              onChangeTaskTitle={(ti, v) => saveUpdate(withTaskTitle(si, ti, v))}
              onChangeTaskDesc={(ti, v) => saveUpdate(withTaskDesc(si, ti, v))}
            />
          ))}
        </div>

        {/* Agent config */}
        <AgentConfigPanel agentConfig={plan.agent_config} />

        {/* Actions */}
        <div className="modal-actions" style={{ marginTop: 20 }}>
          <button className="btn btn-ghost" onClick={onClose}>{t('planning.cancel')}</button>
          <button
            className="btn btn-primary"
            disabled={readOnly}
            onClick={() => confirmPlan(sessionId)}
          >
            {t('planning.confirm_plan')}
          </button>
        </div>
      </div>
    </div>
  )
}
