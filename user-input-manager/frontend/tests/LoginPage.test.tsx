import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { LoginPage } from '../src/components/auth/LoginPage'
import { AuthContext } from '../src/context/AuthContext'

// Mock useNavigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

const mockLogin = vi.fn()

function renderLogin() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <AuthContext.Provider value={{ user: null, loading: false, login: mockLogin, logout: vi.fn() }}>
          <LoginPage />
        </AuthContext.Provider>
      </MemoryRouter>
    </I18nextProvider>
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders email and password fields', () => {
    renderLogin()
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('calls login with correct credentials on submit', async () => {
    mockLogin.mockResolvedValueOnce(undefined)
    renderLogin()

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'test@test.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret123' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith('test@test.com', 'secret123'))
    expect(mockNavigate).toHaveBeenCalledWith('/sessions')
  })

  it('shows error on 401', async () => {
    mockLogin.mockRejectedValueOnce({ response: { status: 401 } })
    renderLogin()

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'x@x.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument())
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('shows error on 403', async () => {
    mockLogin.mockRejectedValueOnce({ response: { status: 403 } })
    renderLogin()

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'blocked@x.com' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'pass' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByText(/disabled/i)).toBeInTheDocument())
  })
})
