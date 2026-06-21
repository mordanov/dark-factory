/**
 * Orchestrator API client.
 *
 * Calls are proxied through Prompt Studio nginx at /orchestrator-api/
 * so the browser never needs a separate origin (no CORS issues).
 */
import axios from 'axios'

export const orchestratorApi = axios.create({
  baseURL: import.meta.env.VITE_ORCHESTRATOR_BASE_URL ?? '/orchestrator-api/v1',
})

orchestratorApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

orchestratorApi.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('current_user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export type FsmStatus =
  | 'backlog' | 'triage' | 'specification' | 'architecture_review'
  | 'implementation' | 'code_review' | 'security_review'
  | 'testing' | 'release' | 'done' | 'BLOCKED'

export type JobStatus = 'pending' | 'running' | 'done' | 'failed'
export type JobType = 'orchestrate' | 'distill'

export interface OrchestratorTicket {
  id: string
  project_id: string
  title: string
  description: string
  ticket_type: string | null
  tags: string[]
  status: string | null
  fsm_status: FsmStatus | null
  blocked_reason: string | null
  brainstorm_round: number
  assigned_agent: string | null
  override: boolean
  override_reason: string | null
  last_orchestrator_run: string | null
  orchestrator_errors: string[]
  dependencies: string[]
  created_at: string | null
  updated_at: string | null
}

export interface OrchestratorJob {
  id: string
  job_type: JobType
  ticket_id: string
  project_id: string
  status: JobStatus
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

export const pendingApi = {
  list: (project_id?: string) =>
    orchestratorApi.get<{ tickets: OrchestratorTicket[]; total: number }>(
      '/jobs/pending-tickets',
      { params: project_id ? { project_id } : {} }
    ),
}

export const jobsApi = {
  trigger: (ticket_id: string, project_id: string, priority = 0) =>
    orchestratorApi.post<OrchestratorJob>('/jobs/trigger', {
      ticket_id, project_id, priority,
    }),
  list: (params?: { status?: string; ticket_id?: string; offset?: number; limit?: number }) =>
    orchestratorApi.get<{ items: OrchestratorJob[]; total: number }>('/jobs', { params }),
  get: (job_id: string) =>
    orchestratorApi.get<OrchestratorJob>(`/jobs/${job_id}`),
}

export const auditApi = {
  list: (ticket_id: string) =>
    orchestratorApi.get<{ items: AuditEntry[]; total: number }>(`/audit/${ticket_id}`),
}

export const memoryApi = {
  get: (project_id: string) =>
    orchestratorApi.get<ProjectMemory>(`/memory/${project_id}`),
  adrs: (project_id: string, status = 'accepted') =>
    orchestratorApi.get<{ adrs: AdrSummary[] }>(`/memory/${project_id}/adrs`, {
      params: { status },
    }),
}

export const workflowApi = {
  getPendingTickets: (project_id?: string) =>
    orchestratorApi.get<{ tickets: OrchestratorTicket[]; total: number }>(
      '/jobs/pending-tickets',
      { params: project_id ? { project_id } : {} }
    ),

  triggerJob: (ticket_id: string, project_id: string, priority = 0) =>
    orchestratorApi.post<OrchestratorJob>('/jobs/trigger', {
      ticket_id, project_id, priority,
    }),

  listJobs: (params?: { status?: string; ticket_id?: string; offset?: number; limit?: number }) =>
    orchestratorApi.get<{ items: OrchestratorJob[]; total: number }>('/jobs', { params }),

  getJob: (job_id: string) =>
    orchestratorApi.get<OrchestratorJob>(`/jobs/${job_id}`),

  getAudit: (ticket_id: string) =>
    orchestratorApi.get<{ items: AuditEntry[]; total: number }>(`/audit/${ticket_id}`),

  getMemory: (project_id: string) =>
    orchestratorApi.get<ProjectMemory>(`/memory/${project_id}`),

  getAdrs: (project_id: string, status = 'accepted') =>
    orchestratorApi.get<{ adrs: AdrSummary[] }>(`/memory/${project_id}/adrs`, {
      params: { status },
    }),
}
