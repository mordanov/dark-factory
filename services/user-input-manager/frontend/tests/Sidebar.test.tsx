import { render, screen, fireEvent } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { Sidebar } from '../src/components/layout/Sidebar'
import { useAuthStore } from '../src/store/auth'
import type { User } from '../src/api/client'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

const adminUser: User = {
  id: '1', email: 'admin@test.com', full_name: 'Admin', is_admin: true,
  is_active: true, created_at: '', updated_at: '',
}
const regularUser: User = { ...adminUser, is_admin: false, email: 'user@test.com' }

function wrap(user: User) {
  useAuthStore.setState({ currentUser: user, accessToken: null, refreshToken: null, isRestoring: false })
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
    useAuthStore.setState({ currentUser: null, accessToken: null, refreshToken: null, isRestoring: false })
  })

  it('shows Sessions link for all users', () => {
    wrap(regularUser)
    expect(screen.getByText(/sessions/i)).toBeInTheDocument()
  })

  it('shows Users link only for admins', () => {
    wrap(adminUser)
    expect(screen.getByText(/users/i)).toBeInTheDocument()
  })

  it('hides Users link for regular users', () => {
    wrap(regularUser)
    expect(screen.queryByText(/^users$/i)).not.toBeInTheDocument()
  })

  it('displays user email', () => {
    wrap(regularUser)
    expect(screen.getByText('user@test.com')).toBeInTheDocument()
  })

  it('calls logout and navigates on Log out click', () => {
    const logoutSpy = vi.spyOn(useAuthStore.getState(), 'logout')
    wrap(regularUser)
    fireEvent.click(screen.getByText(/log out/i))
    expect(logoutSpy).toHaveBeenCalled()
    expect(mockNavigate).toHaveBeenCalledWith('/login')
  })
})
