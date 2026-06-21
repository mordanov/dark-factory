import axios from 'axios'

export const api = axios.create({ baseURL: '/api/v1' })

// Attach JWT from localStorage to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// On 401 — clear tokens and redirect to login
api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ------------------------------------------------------------------
// Error extraction
// ------------------------------------------------------------------

export function extractError(err: unknown, fallback = 'Something went wrong'): string {
  if (!err || typeof err !== 'object') return fallback
  const e = err as any
  const detail = e?.response?.data?.detail
  if (detail) {
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d: any) => d?.msg || String(d)).join('; ')
  }
  if (e?.message) return e.message
  return fallback
}

// ------------------------------------------------------------------
// Types
// ------------------------------------------------------------------

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface User {
  id: string
  email: string
  full_name: string
  is_admin: boolean
  is_active: boolean
  created_at: string
  updated_at: string
}

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
  status: 'in_progress' | 'approved' | 'cancelled'
  created_at: string
  updated_at: string
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

export const authApi = {
  login: (email: string, password: string) =>
    api.post<TokenResponse>('/auth/login', { email, password }),
  refresh: (refresh_token: string) =>
    api.post<TokenResponse>('/auth/refresh', { refresh_token }),
}

export const usersApi = {
  list: (offset = 0, limit = 50) =>
    api.get<{ items: User[]; total: number }>('/users', { params: { offset, limit } }),
  create: (data: { email: string; password: string; full_name: string; is_admin: boolean }) =>
    api.post<User>('/users', data),
  update: (id: string, data: Partial<{ email: string; password: string; full_name: string; is_admin: boolean; is_active: boolean }>) =>
    api.patch<User>(`/users/${id}`, data),
}

export const tmApi = {
  listProjects: () => api.get<TmProject[]>('/ticket-manager/projects'),
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
