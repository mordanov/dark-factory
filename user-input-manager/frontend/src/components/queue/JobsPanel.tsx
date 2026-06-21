import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { orchestratorApi, type OrchestratorJob } from '../../api/orchestratorClient'
import { JobDetailModal } from './JobDetailModal'

const STATUS_BADGE: Record<string, string> = {
  pending: 'badge-muted',
  running: 'badge-amber',
  done: 'badge-green',
  failed: 'badge-red',
}

function duration(job: OrchestratorJob): string {
  if (!job.started_at || !job.finished_at) return '—'
  const ms = new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}

interface Props {
  refreshSignal: number   // incremented externally to trigger reload
}

export function JobsPanel({ refreshSignal }: Props) {
  const { t } = useTranslation()
  const [jobs, setJobs] = useState<OrchestratorJob[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [selectedJob, setSelectedJob] = useState<OrchestratorJob | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const load = async () => {
    try {
      const params: any = { limit: 50 }
      if (statusFilter !== 'all') params.status = statusFilter
      const { data } = await orchestratorApi.listJobs(params)
      setJobs(data.items)
      setTotal(data.total)
    } catch {
      // silent refresh failures
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setLoading(true)
    load()
  }, [statusFilter, refreshSignal])

  // Auto-refresh every 8s if any job is running
  useEffect(() => {
    const hasRunning = jobs.some(j => j.status === 'running' || j.status === 'pending')
    if (hasRunning && !intervalRef.current) {
      intervalRef.current = setInterval(load, 8000)
    }
    if (!hasRunning && intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [jobs])

  const FILTERS = ['all', 'pending', 'running', 'done', 'failed']

  return (
    <div>
      <div className="flex" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div className="card-title">{t('queue.job_history')} {!loading && `(${total})`}</div>
        <div className="flex gap-8">
          {FILTERS.map(f => (
            <button
              key={f}
              className={`btn btn-sm ${statusFilter === f ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setStatusFilter(f)}
            >
              {t(`queue.filter_${f}`)}
            </button>
          ))}
          <button className="btn btn-ghost btn-sm" onClick={() => { setLoading(true); load() }}>
            ↻
          </button>
        </div>
      </div>

      {loading ? (
        <div className="empty-state"><span className="spinner" /></div>
      ) : jobs.length === 0 ? (
        <div className="empty-state">{t('queue.no_jobs')}</div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="sessions-table">
            <thead>
              <tr>
                <th>{t('queue.ticket_id')}</th>
                <th>{t('queue.job_type')}</th>
                <th>{t('queue.status')}</th>
                <th>{t('queue.triggered_by')}</th>
                <th>{t('queue.duration')}</th>
                <th>{t('admin.created')}</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <tr key={job.id} style={{ cursor: 'default' }}>
                  <td className="mono" style={{ fontSize: '0.78rem' }}>{job.ticket_id}</td>
                  <td>
                    <span className="badge badge-muted">{job.job_type}</span>
                  </td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[job.status] ?? 'badge-muted'}`}>
                      {job.status === 'running' && <span className="spinner" style={{ width: 10, height: 10, marginRight: 4 }} />}
                      {job.status}
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: '0.78rem' }}>{job.triggered_by}</td>
                  <td className="mono" style={{ fontSize: '0.78rem' }}>{duration(job)}</td>
                  <td className="mono" style={{ fontSize: '0.78rem' }}>
                    {new Date(job.created_at).toLocaleString()}
                  </td>
                  <td>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setSelectedJob(job)}
                    >
                      {t('queue.view_audit')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedJob && (
        <JobDetailModal job={selectedJob} onClose={() => setSelectedJob(null)} />
      )}
    </div>
  )
}
