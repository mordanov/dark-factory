import { renderHook, act } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { AuthProvider, useAuth } from '../src/context/AuthContext'

// JWT payload for a regular user: { sub: 'uid-1', is_admin: false }
const fakeToken = [
  btoa(JSON.stringify({ alg: 'HS256' })),
  btoa(JSON.stringify({ sub: 'uid-1', is_admin: false, type: 'access' })),
  'signature',
].join('.')

vi.mock('../src/api/client', () => ({
  authApi: {
    login: vi.fn().mockResolvedValue({
      data: { access_token: fakeToken, refresh_token: 'ref-token', token_type: 'bearer' },
    }),
  },
  usersApi: {},
}))

describe('AuthContext', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('starts with no user when localStorage is empty', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await act(async () => {})
    expect(result.current.user).toBeNull()
    expect(result.current.loading).toBe(false)
  })

  it('login sets user and stores tokens', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await act(async () => {
      await result.current.login('user@test.com', 'pass')
    })
    expect(localStorage.getItem('access_token')).toBe(fakeToken)
    expect(result.current.user?.email).toBe('user@test.com')
    expect(result.current.user?.is_admin).toBe(false)
  })

  it('logout clears user and tokens', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await act(async () => {
      await result.current.login('user@test.com', 'pass')
    })
    act(() => result.current.logout())
    expect(result.current.user).toBeNull()
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('restores user from localStorage on mount', async () => {
    const storedUser = { id: 'uid-1', email: 'x@x.com', is_admin: false, is_active: true, full_name: '', created_at: '', updated_at: '' }
    localStorage.setItem('access_token', fakeToken)
    localStorage.setItem('current_user', JSON.stringify(storedUser))

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await act(async () => {})
    expect(result.current.user?.email).toBe('x@x.com')
  })
})
