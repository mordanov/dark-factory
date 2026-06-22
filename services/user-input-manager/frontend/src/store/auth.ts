import { create } from 'zustand'
import type { User } from '../api/client'

const RT_KEY = 'rt'

interface AuthState {
  accessToken: string | null
  currentUser: User | null
  refreshToken: string | null
  isRestoring: boolean
  login: (accessToken: string, refreshToken: string | undefined, user: User) => void
  setAccessToken: (token: string) => void
  setRestored: () => void
  logout: () => void
}

const storedRefreshToken = sessionStorage.getItem(RT_KEY)

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  currentUser: null,
  refreshToken: storedRefreshToken,
  isRestoring: storedRefreshToken !== null,

  login(accessToken, refreshToken, user) {
    if (refreshToken) {
      sessionStorage.setItem(RT_KEY, refreshToken)
    }
    set({ accessToken, refreshToken: refreshToken ?? null, currentUser: user, isRestoring: false })
  },

  setAccessToken(token) {
    set({ accessToken: token })
  },

  setRestored() {
    set({ isRestoring: false })
  },

  logout() {
    sessionStorage.removeItem(RT_KEY)
    set({ accessToken: null, refreshToken: null, currentUser: null, isRestoring: false })
  },
}))
