import type { FsmStatus, JobStatus } from '../../api/orchestrator'

export const FSM_ORDER: FsmStatus[] = [
  'backlog', 'triage', 'specification', 'architecture_review',
  'implementation', 'code_review', 'security_review',
  'testing', 'release', 'done',
]

export function fsmBadgeClass(status: FsmStatus | null): string {
  if (!status) return 'badge-muted'
  if (status === 'done') return 'badge-green'
  if (status === 'BLOCKED') return 'badge-red'
  return 'badge-amber'
}

export function jobBadgeClass(status: JobStatus): string {
  const map: Record<JobStatus, string> = {
    pending: 'badge-muted',
    running: 'badge-amber',
    done: 'badge-green',
    failed: 'badge-red',
  }
  return map[status] ?? 'badge-muted'
}

export function fsmProgress(status: FsmStatus | null): number {
  if (!status || status === 'BLOCKED') return 0
  const idx = FSM_ORDER.indexOf(status)
  return idx < 0 ? 0 : Math.round(((idx + 1) / FSM_ORDER.length) * 100)
}

export function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '—'
  const ms = new Date(end ?? new Date()).getTime() - new Date(start).getTime()
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`
}
