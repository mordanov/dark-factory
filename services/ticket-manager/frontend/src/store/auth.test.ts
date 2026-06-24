import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useAuthStore } from './auth'

const mockKeycloak = vi.hoisted(() => ({
  init: vi.fn().mockResolvedValue(true),
  updateToken: vi.fn().mockResolvedValue(true),
  logout: vi.fn().mockResolvedValue(undefined),
  token: 'mock-token' as string | undefined,
  tokenParsed: {
    sub: 'uid-1',
    email: 'user@test.com',
    preferred_username: 'user',
    realm_access: { roles: ['user'] },
  } as Record<string, unknown> | null,
  onTokenExpired: undefined as (() => void) | undefined,
}))

vi.mock('../keycloak', () => ({ default: mockKeycloak }))

describe('useAuthStore (keycloak-js)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockKeycloak.init.mockResolvedValue(true)
    mockKeycloak.updateToken.mockResolvedValue(true)
    mockKeycloak.logout.mockResolvedValue(undefined)
    mockKeycloak.token = 'mock-token'
    mockKeycloak.tokenParsed = {
      sub: 'uid-1',
      email: 'user@test.com',
      preferred_username: 'user',
      realm_access: { roles: ['user'] },
    }
    useAuthStore.setState({ initialized: false, initError: false, user: null })
    localStorage.clear()
    sessionStorage.clear()
  })

  it('starts uninitialized with no user', () => {
    const s = useAuthStore.getState()
    expect(s.initialized).toBe(false)
    expect(s.initError).toBe(false)
    expect(s.user).toBeNull()
  })

  it('initialize() sets initialized=true and populates user', async () => {
    await useAuthStore.getState().initialize()
    const s = useAuthStore.getState()
    expect(s.initialized).toBe(true)
    expect(s.initError).toBe(false)
    expect(s.user?.sub).toBe('uid-1')
    expect(s.user?.email).toBe('user@test.com')
    expect(s.user?.isAdmin).toBe(false)
  })

  it('initialize() sets isAdmin=true for administrator role', async () => {
    mockKeycloak.tokenParsed = {
      sub: 'admin-1',
      email: 'admin@test.com',
      preferred_username: 'admin',
      realm_access: { roles: ['user', 'administrator'] },
    }
    await useAuthStore.getState().initialize()
    expect(useAuthStore.getState().user?.isAdmin).toBe(true)
  })

  it('initialize() sets initError=true when keycloak.init() rejects', async () => {
    mockKeycloak.init.mockRejectedValue(new Error('Network Error'))
    await useAuthStore.getState().initialize()
    const s = useAuthStore.getState()
    expect(s.initError).toBe(true)
    expect(s.initialized).toBe(false)
    expect(s.user).toBeNull()
  })

  it('logout() clears user and initialized before calling keycloak.logout', async () => {
    useAuthStore.setState({ initialized: true, user: { sub: 'u1', email: 'a@b.com', username: 'a', isAdmin: false }, initError: false })
    let capturedUser: unknown = 'not-called'
    let capturedInitialized: unknown = 'not-called'
    mockKeycloak.logout.mockImplementation(async () => {
      capturedUser = useAuthStore.getState().user
      capturedInitialized = useAuthStore.getState().initialized
    })
    await useAuthStore.getState().logout()
    expect(capturedUser).toBeNull()
    expect(capturedInitialized).toBe(false)
    expect(mockKeycloak.logout).toHaveBeenCalledWith({ redirectUri: window.location.origin })
  })

  it('getToken() returns token string', async () => {
    const token = await useAuthStore.getState().getToken()
    expect(token).toBe('mock-token')
  })

  it('getToken() returns null when keycloak.token is undefined', async () => {
    mockKeycloak.token = undefined
    const token = await useAuthStore.getState().getToken()
    expect(token).toBeNull()
  })

  it('getAuthHeader() returns Authorization header', async () => {
    const header = await useAuthStore.getState().getAuthHeader()
    expect(header.Authorization).toMatch(/^Bearer /)
  })

  it('test_localStorage_never_written: localStorage.setItem not called during initialize() and logout() (FIND-02)', async () => {
    const spy = vi.spyOn(localStorage, 'setItem')
    await useAuthStore.getState().initialize()
    await useAuthStore.getState().logout()
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('test_sessionStorage_never_written: sessionStorage.setItem not called during initialize() and logout() (FIND-02)', async () => {
    const spy = vi.spyOn(sessionStorage, 'setItem')
    await useAuthStore.getState().initialize()
    await useAuthStore.getState().logout()
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })
})
