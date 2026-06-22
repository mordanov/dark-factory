import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { LoginPage } from '../src/components/auth/LoginPage'
import { useAuthStore } from '../src/store/auth'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

const fakeToken = [
  btoa(JSON.stringify({ alg: 'HS256' })),
  btoa(JSON.stringify({ sub: 'uid-1', is_admin: false })),
  'signature',
].join('.')

vi.mock('../src/api/client', async () => {
  const actual = await vi.importActual('../src/api/client')
  return {
    ...actual,
    authApi: {
      login: vi.fn(),
      refresh: vi.fn(),
    },
  }
})

function renderLogin() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </I18nextProvider>
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({ accessToken: null, currentUser: null, refreshToken: null, isRestoring: false })
  })

  it('renders email and password fields', () => {
    renderLogin()
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('calls authApi.login and stores token in Zustand on submit', async () => {
    const { authApi } = await import('../src/api/client')
    vi.mocked(authApi.login).mockResolvedValueOnce({
      data: { access_token: fakeToken, refresh_token: 'rt', token_type: 'bearer' },
    } as never)

    renderLogin()
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'test@test.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret123' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(authApi.login).toHaveBeenCalledWith('test@test.com', 'secret123'))
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/sessions'))
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(useAuthStore.getState().accessToken).toBe(fakeToken)
  })

  it('shows error on 401', async () => {
    const { authApi } = await import('../src/api/client')
    vi.mocked(authApi.login).mockRejectedValueOnce({ response: { status: 401 } })
    renderLogin()

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'x@x.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument())
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('shows error on 403', async () => {
    const { authApi } = await import('../src/api/client')
    vi.mocked(authApi.login).mockRejectedValueOnce({ response: { status: 403 } })
    renderLogin()

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'blocked@x.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'pass' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByText(/disabled/i)).toBeInTheDocument())
  })
})
