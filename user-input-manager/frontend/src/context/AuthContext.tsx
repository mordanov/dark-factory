import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { authApi, type User, usersApi } from '../api/client'

interface AuthState {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const loadUser = useCallback(async () => {
    const token = localStorage.getItem('access_token')
    if (!token) { setLoading(false); return }
    try {
      // Fetch current user info by listing users — simplest way without a /me endpoint
      // Since we store the token we just need any authenticated call.
      // We store user info in localStorage on login instead.
      const raw = localStorage.getItem('current_user')
      if (raw) setUser(JSON.parse(raw))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadUser() }, [loadUser])

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await authApi.login(email, password)
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)

    // Decode user info from JWT payload (base64 claims)
    const [, payload] = data.access_token.split('.')
    const claims = JSON.parse(atob(payload))
    // We need the full user object — make a quick users list call (admin) or
    // store minimal info from the JWT claims
    const partialUser: User = {
      id: claims.sub,
      email,
      full_name: '',
      is_admin: claims.is_admin,
      is_active: true,
      created_at: '',
      updated_at: '',
    }
    localStorage.setItem('current_user', JSON.stringify(partialUser))
    setUser(partialUser)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('current_user')
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
