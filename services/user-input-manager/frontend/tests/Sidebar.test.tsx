import { render, screen } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { Sidebar } from '../src/components/layout/Sidebar'
import { useAuthStore } from '../src/store/auth'

vi.mock('../src/keycloak', () => ({
  default: {
    init: vi.fn().mockResolvedValue(true),
    updateToken: vi.fn().mockResolvedValue(true),
    logout: vi.fn().mockResolvedValue(undefined),
    token: 'mock-token',
    tokenParsed: null,
    onTokenExpired: undefined,
  },
}))

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

const adminUser = { sub: 'uid-admin', email: 'admin@test.com', username: 'admin', isAdmin: true }
const regularUser = { sub: 'uid-user', email: 'user@test.com', username: 'user', isAdmin: false }

function wrap(user: typeof adminUser) {
  useAuthStore.setState({ initialized: true, user })
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    </I18nextProvider>
  )
}

describe('Sidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({ initialized: false, user: null })
  })

  it('shows Sessions link for all users', () => {
    wrap(regularUser)
    expect(screen.getByText(/sessions/i)).toBeInTheDocument()
  })

  it('shows admin link only for admin users', () => {
    wrap(adminUser)
    expect(screen.getByRole('link', { name: /admin/i })).toBeInTheDocument()
  })

  it('hides admin link for regular users', () => {
    wrap(regularUser)
    expect(screen.queryByRole('link', { name: /admin/i })).not.toBeInTheDocument()
  })

  it('displays user email', () => {
    wrap(regularUser)
    expect(screen.getByText('user@test.com')).toBeInTheDocument()
  })
})
