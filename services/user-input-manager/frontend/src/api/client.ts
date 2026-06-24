import axios from 'axios'
import { useAuthStore } from '../store/auth'

export const api = axios.create({ baseURL: '/api/v1' })

api.interceptors.request.use(async (config) => {
  const header = await useAuthStore.getState().getAuthHeader()
  config.headers.Authorization = header.Authorization
  return config
})

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    if (err.response?.status === 401) {
      await useAuthStore.getState().initialize()
    }
    return Promise.reject(err)
  }
)

// ------------------------------------------------------------------
// Error extraction
// ------------------------------------------------------------------

export function extractError(err: unknown, fallback = 'Something went wrong'): string {
  if (!err || typeof err !== 'object') return fallback
  const e = err as Record<string, unknown>
  const detail = (e?.response as Record<string, unknown> | undefined)?.data as Record<string, unknown> | undefined
  const detailValue = detail?.detail
  if (detailValue) {
    if (typeof detailValue === 'string') return detailValue
    if (Array.isArray(detailValue)) return detailValue.map((d: unknown) => (d as Record<string, unknown>)?.msg || String(d)).join('; ')
  }
  if (typeof (e as Record<string, unknown>)?.message === 'string') return (e as Record<string, unknown>).message as string
  return fallback
}

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

export interface TmProject {
  id: string
  name: string
  description?: string
}

export interface Session {
  id: string
  session_type: 'new_project' | 'existing_project'
  tm_project_id: string | null
  tm_project_name: string | null
  tm_ticket_id: string | null
  tm_ticket_title: string | null
  status: 'in_progress' | 'approved' | 'cancelled' | 'planning' | 'plan_ready' | 'plan_confirmed' | 'tickets_created'
  created_at: string
  updated_at: string
}

export interface PlanTask {
  local_id: string
  title: string
  description: string
  ticket_type: 'task' | 'implementation' | 'investigation'
  complexity: 'S' | 'M' | 'L' | 'XL'
  depends_on: string[]
}

export interface PlanStory {
  local_id: string
  title: string
  description: string
  ticket_type: 'story'
  tasks: PlanTask[]
}

export interface PlanEpic {
  local_id: string
  title: string
  description: string
  ticket_type: 'epic'
}

export interface PlanContent {
  epic: PlanEpic
  stories: PlanStory[]
}

export interface AgentOverride {
  agent_id: string
  override_text: string
}

export interface AgentConfig {
  project_id: string
  tech_stack: string[]
  agent_overrides: AgentOverride[]
}

export interface PlanResponse {
  id: string
  session_id: string
  status: 'draft' | 'ready' | 'confirmed' | 'tickets_created' | 'error'
  plan_content: PlanContent | null
  agent_config: AgentConfig | null
  validation_errors: string[] | null
  created_ticket_ids: string[] | null
  ticket_id_map: Record<string, string> | null
  tm_epic_id: string | null
  created_at: string
  updated_at: string
}

export interface PlanStatusResponse {
  status: 'confirmed' | 'tickets_created' | 'error'
  created_count: number
  total: number
  errors: string[]
}

export interface Iteration {
  id: string
  session_id: string
  iteration_number: number
  role: 'user' | 'assistant'
  prompt_text: string
  llm_assessment: string | null
  llm_questions: string | null
  llm_suggested_title: string | null
  user_comment: string | null
  is_approved: boolean | null
  created_at: string
}

// ------------------------------------------------------------------
// API calls
// ------------------------------------------------------------------

export const tmApi = {
  listProjects: () => api.get<TmProject[]>('/ticket-manager/projects'),
}

export const planningApi = {
  trigger: (sessionId: string) =>
    api.post<{ session_id: string; plan_id: string; status: string }>(
      `/sessions/${sessionId}/plan`
    ),
  get: (sessionId: string) =>
    api.get<PlanResponse>(`/sessions/${sessionId}/plan`),
  update: (sessionId: string, content: PlanContent) =>
    api.put<PlanResponse>(`/sessions/${sessionId}/plan`, { plan_content: content }),
  confirm: (sessionId: string) =>
    api.post<{ session_id: string; plan_id: string; status: string }>(
      `/sessions/${sessionId}/plan/confirm`
    ),
  getStatus: (sessionId: string) =>
    api.get<PlanStatusResponse>(`/sessions/${sessionId}/plan/status`),
}

export const sessionsApi = {
  list: (offset = 0, limit = 20) =>
    api.get<{ items: Session[]; total: number }>('/sessions', { params: { offset, limit } }),
  create: (data: {
    session_type: string
    tm_project_id?: string
    tm_project_name?: string
    initial_prompt: string
  }) => api.post<{ session: Session; latest_iteration: Iteration }>('/sessions', data),
  getIterations: (sessionId: string) =>
    api.get<Iteration[]>(`/sessions/${sessionId}/iterations`),
  feedback: (sessionId: string, data: { is_approved: boolean; comment?: string }) =>
    api.post<{ session: Session; latest_iteration: Iteration; awaiting_approval: boolean }>(
      `/sessions/${sessionId}/feedback`, data
    ),
  revert: (sessionId: string, target_iteration_number: number) =>
    api.post<{ session: Session; latest_iteration: Iteration }>(
      `/sessions/${sessionId}/revert`, { target_iteration_number }
    ),
  approve: (sessionId: string, data: { ticket_title: string; project_description?: string }) =>
    api.post<{ session: Session; ticket_id: string; project_id: string }>(
      `/sessions/${sessionId}/approve`, data
    ),
}
