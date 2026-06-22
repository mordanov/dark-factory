import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useAuthStore } from '../src/store/auth'

const fakeToken = [
  btoa(JSON.stringify({ alg: 'HS256' })),
  btoa(JSON.stringify({ sub: 'uid-1', is_admin: false, type: 'access' })),
  'signature',
].join('.')

const fakeUser = {
  id: 'uid-1', email: 'user@test.com', full_name: '', is_admin: false,
  is_active: true, created_at: '', updated_at: '',
}

describe('useAuthStore', () => {
  beforeEach(() => {
    sessionStorage.clear()
    useAuthStore.setState({ accessToken: null, currentUser: null, refreshToken: null, isRestoring: false })
  })
  afterEach(() => sessionStorage.clear())

  it('starts with no token or user', () => {
    const s = useAuthStore.getState()
    expect(s.accessToken).toBeNull()
    expect(s.currentUser).toBeNull()
    expect(s.isRestoring).toBe(false)
  })

  it('login stores accessToken in memory only (not localStorage)', () => {
    useAuthStore.getState().login(fakeToken, 'rt-value', fakeUser)
    const s = useAuthStore.getState()
    expect(s.accessToken).toBe(fakeToken)
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(sessionStorage.getItem('rt')).toBe('rt-value')
  })

  it('login sets currentUser', () => {
    useAuthStore.getState().login(fakeToken, 'rt-value', fakeUser)
    expect(useAuthStore.getState().currentUser?.email).toBe('user@test.com')
  })

  it('logout clears in-memory token and sessionStorage', () => {
    useAuthStore.getState().login(fakeToken, 'rt-value', fakeUser)
    useAuthStore.getState().logout()
    const s = useAuthStore.getState()
    expect(s.accessToken).toBeNull()
    expect(s.currentUser).toBeNull()
    expect(sessionStorage.getItem('rt')).toBeNull()
  })

  it('setAccessToken updates only the token', () => {
    useAuthStore.getState().login(fakeToken, 'rt', fakeUser)
    useAuthStore.getState().setAccessToken('new-token')
    expect(useAuthStore.getState().accessToken).toBe('new-token')
    expect(useAuthStore.getState().currentUser?.email).toBe('user@test.com')
  })

  it('setRestored sets isRestoring to false', () => {
    useAuthStore.setState({ isRestoring: true })
    useAuthStore.getState().setRestored()
    expect(useAuthStore.getState().isRestoring).toBe(false)
  })
})
