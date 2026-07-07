import { create } from 'zustand'
import keycloak from '../keycloak'

interface AuthUser {
  sub: string
  email: string
  username: string
  isAdmin: boolean
}

interface AuthState {
  initialized: boolean
  initError: boolean
  user: AuthUser | null
  initialize: () => Promise<void>
  logout: () => Promise<void>
  getToken: () => Promise<string | null>
  getAuthHeader: () => Promise<{ Authorization: string }>
}

export const useAuthStore = create<AuthState>((set) => ({
  initialized: false,
  initError: false,
  user: null,

  async initialize() {
    try {
      await keycloak.init({ onLoad: 'login-required', pkceMethod: 'S256', checkLoginIframe: false })

      keycloak.onTokenExpired = () => {
        keycloak.updateToken(30).catch(() => {
          keycloak.logout({ redirectUri: window.location.origin })
        })
      }

      const profile = keycloak.tokenParsed
      const roles: string[] = (profile?.realm_access as { roles?: string[] })?.roles ?? []

      set({
        initialized: true,
        initError: false,
        user: {
          sub: profile?.sub ?? '',
          email: (profile?.email as string | undefined) ?? '',
          username: (profile?.preferred_username as string | undefined) ?? (profile?.email as string | undefined) ?? '',
          isAdmin: roles.includes('administrator'),
        },
      })
    } catch {
      set({ initialized: false, initError: true })
    }
  },

  async logout() {
    set({ initialized: false, user: null })
    await keycloak.logout({ redirectUri: window.location.origin })
  },

  async getToken() {
    await keycloak.updateToken(30)
    return keycloak.token ?? null
  },

  async getAuthHeader() {
    await keycloak.updateToken(30)
    return { Authorization: `Bearer ${keycloak.token ?? ''}` }
  },
}))
