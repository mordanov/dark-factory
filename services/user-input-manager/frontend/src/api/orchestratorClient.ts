import { api } from './client'

// ── Types ────────────────────────────────────────────────────────────────────

export interface PendingTicket {
  id: string
  project_id: string
  title: string
  description: string
  ticket_type: string | null
  tags: string[]
  fsm_status: string | null
  blocked_reason: string | null
  assigned_agent: string | null
  brainstorm_round: number
  dependencies: string[]
  updated_at: string | null
}

export interface OrchestratorJob {
  id: string
  job_type: 'orchestrate' | 'distill'
  ticket_id: string
  project_id: string
  status: 'pending' | 'running' | 'done' | 'failed'
  priority: number
  triggered_by: string
  error_message: string | null
  attempts: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface AuditEntry {
  id: string
  job_id: string | null
  ticket_id: string
  project_id: string
  action: string
  from_state: string | null
  to_state: string | null
  assigned_agent: string | null
  blocked_reason: string | null
  override_logged: boolean
  details: string
  created_at: string
}

export interface ProjectMemory {
  project_id: string
  content: string
  version: number
  last_ticket_id: string | null
  updated_at: string | null
}

export interface AdrSummary {
  id: string
  project_id: string
  title: string
  status: string
  summary: string | null
  ticket_id: string | null
  created_at: string | null
}

// ── API calls ────────────────────────────────────────────────────────────────

export const orchestratorApi = {
  getPendingTickets: (projectId?: string) =>
    api.get<{ tickets: PendingTicket[]; total: number }>(
      '/orchestrator/pending-tickets',
      { params: projectId ? { project_id: projectId } : {} }
    ),

  triggerJob: (ticketId: string, projectId: string, priority = 0) =>
    api.post<OrchestratorJob>('/orchestrator/jobs/trigger', {
      ticket_id: ticketId,
      project_id: projectId,
      priority,
    }),

  listJobs: (params?: { status?: string; ticket_id?: string; offset?: number; limit?: number }) =>
    api.get<{ items: OrchestratorJob[]; total: number }>('/orchestrator/jobs', { params }),

  getJob: (jobId: string) =>
    api.get<OrchestratorJob>(`/orchestrator/jobs/${jobId}`),

  getAuditTrail: (ticketId: string) =>
    api.get<{ items: AuditEntry[]; total: number }>(`/orchestrator/audit/${ticketId}`),

  getProjectMemory: (projectId: string) =>
    api.get<ProjectMemory>(`/orchestrator/memory/${projectId}`),

  getAdrs: (projectId: string, status = 'accepted') =>
    api.get<{ adrs: AdrSummary[] }>(`/orchestrator/memory/${projectId}/adrs`, {
      params: { status },
    }),
}
