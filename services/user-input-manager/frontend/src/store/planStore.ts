import { create } from 'zustand'
import { planningApi, extractError, type PlanContent, type PlanResponse, type PlanStatusResponse } from '../api/client'

interface CreationProgress {
  created: number
  total: number
  errors: string[]
}

interface PlanState {
  plan: PlanResponse | null
  isGenerating: boolean
  isConfirming: boolean
  error: string | null
  creationProgress: CreationProgress | null
  _pollTimer: ReturnType<typeof setInterval> | null

  triggerGeneration: (sessionId: string) => Promise<void>
  fetchPlan: (sessionId: string) => Promise<void>
  updatePlan: (sessionId: string, content: PlanContent) => Promise<void>
  confirmPlan: (sessionId: string) => Promise<void>
  pollCreationStatus: (sessionId: string) => void
  stopPolling: () => void
  reset: () => void
}

export const usePlanStore = create<PlanState>((set, get) => ({
  plan: null,
  isGenerating: false,
  isConfirming: false,
  error: null,
  creationProgress: null,
  _pollTimer: null,

  async triggerGeneration(sessionId) {
    set({ isGenerating: true, error: null })
    try {
      await planningApi.trigger(sessionId)
      // Poll until plan_content is ready
      let attempts = 0
      const maxAttempts = 40 // 40 * 3s = 120s max
      const poll = async (): Promise<void> => {
        attempts++
        const { data } = await planningApi.get(sessionId)
        if (data.status === 'ready') {
          set({ plan: data, isGenerating: false })
          return
        }
        if (data.status === 'error') {
          set({ error: data.validation_errors?.join('; ') || 'Plan generation failed', isGenerating: false })
          return
        }
        if (attempts < maxAttempts) {
          await new Promise(r => setTimeout(r, 3000))
          return poll()
        }
        set({ error: 'Plan generation timed out', isGenerating: false })
      }
      await poll()
    } catch (err) {
      set({ error: extractError(err, 'Plan generation failed'), isGenerating: false })
    }
  },

  async fetchPlan(sessionId) {
    try {
      const { data } = await planningApi.get(sessionId)
      set({ plan: data, error: null })
      if (data.status === 'confirmed') {
        get().pollCreationStatus(sessionId)
      }
    } catch (err) {
      // 404 is expected when no plan exists yet — don't set error
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status !== 404) {
        set({ error: extractError(err) })
      }
    }
  },

  async updatePlan(sessionId, content) {
    set({ error: null })
    try {
      const { data } = await planningApi.update(sessionId, content)
      set({ plan: data })
    } catch (err) {
      set({ error: extractError(err) })
      throw err
    }
  },

  async confirmPlan(sessionId) {
    set({ isConfirming: true, error: null })
    try {
      await planningApi.confirm(sessionId)
      set(state => ({
        plan: state.plan ? { ...state.plan, status: 'confirmed' } : state.plan,
      }))
      get().pollCreationStatus(sessionId)
    } catch (err) {
      set({ error: extractError(err), isConfirming: false })
    }
  },

  pollCreationStatus(sessionId) {
    const { _pollTimer } = get()
    if (_pollTimer) return // already polling

    const timer = setInterval(async () => {
      try {
        const { data } = await planningApi.getStatus(sessionId)
        set({
          creationProgress: { created: data.created_count, total: data.total, errors: data.errors },
        })
        if (data.status === 'tickets_created') {
          clearInterval(timer)
          set({ _pollTimer: null, isConfirming: false })
          // Refresh plan to get latest state
          const { data: plan } = await planningApi.get(sessionId)
          set({ plan })
        } else if (data.status === 'error') {
          clearInterval(timer)
          set({ _pollTimer: null, isConfirming: false })
        }
      } catch {
        // transient error — keep polling
      }
    }, 3000)

    set({ _pollTimer: timer })
  },

  stopPolling() {
    const { _pollTimer } = get()
    if (_pollTimer) {
      clearInterval(_pollTimer)
      set({ _pollTimer: null })
    }
  },

  reset() {
    get().stopPolling()
    set({ plan: null, isGenerating: false, isConfirming: false, error: null, creationProgress: null, _pollTimer: null })
  },
}))
