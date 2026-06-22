import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { QueuePage } from '../src/components/queue/QueuePage'
import { useAuthStore } from '../src/store/auth'
import type { User } from '../src/api/client'

// Mock orchestratorClient
vi.mock('../src/api/orchestratorClient', () => ({
  orchestratorApi: {
    getPendingTickets: vi.fn().mockResolvedValue({
      data: {
        tickets: [
          {
            id: 't-1', project_id: 'p-1', title: 'Add OAuth login',
            description: '', ticket_type: 'feature', tags: [],
            fsm_status: 'triage', blocked_reason: null,
            assigned_agent: null, brainstorm_round: 0,
            dependencies: [], updated_at: null,
          },
          {
            id: 't-2', project_id: 'p-1', title: 'Needs estimation ticket',
            description: '', ticket_type: 'feature',
            tags: ['needs-estimation'], fsm_status: 'backlog',
            blocked_reason: null, assigned_agent: null,
            brainstorm_round: 0, dependencies: [], updated_at: null,
          },
        ],
        total: 2,
      },
    }),
    triggerJob: vi.fn().mockResolvedValue({
      data: { id: 'job-1', ticket_id: 't-1', status: 'pending' },
    }),
    listJobs: vi.fn().mockResolvedValue({
      data: { items: [], total: 0 },
    }),
    getAuditTrail: vi.fn().mockResolvedValue({
      data: { items: [], total: 0 },
    }),
  },
}))

const mockUser: User = {
  id: '1', email: 'user@test.com', full_name: 'Test',
  is_admin: false, is_active: true, created_at: '', updated_at: '',
}

function wrap() {
  useAuthStore.setState({ currentUser: mockUser, accessToken: null, refreshToken: null, isRestoring: false })
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <QueuePage />
      </MemoryRouter>
    </I18nextProvider>
  )
}

const queueTickets = [
  {
    id: 't-1', project_id: 'p-1', title: 'Add OAuth login',
    description: '', ticket_type: 'feature', tags: [],
    fsm_status: 'triage', blocked_reason: null,
    assigned_agent: null, brainstorm_round: 0,
    dependencies: [], updated_at: null,
  },
  {
    id: 't-2', project_id: 'p-1', title: 'Needs estimation ticket',
    description: '', ticket_type: 'feature',
    tags: ['needs-estimation'], fsm_status: 'backlog',
    blocked_reason: null, assigned_agent: null,
    brainstorm_round: 0, dependencies: [], updated_at: null,
  },
]

describe('QueuePage', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    const { orchestratorApi } = await import('../src/api/orchestratorClient')
    vi.mocked(orchestratorApi.getPendingTickets).mockResolvedValue(
      { data: { tickets: queueTickets, total: 2 } } as never
    )
    vi.mocked(orchestratorApi.triggerJob).mockResolvedValue(
      { data: { id: 'job-1', ticket_id: 't-1', status: 'pending' } } as never
    )
    vi.mocked(orchestratorApi.listJobs).mockResolvedValue(
      { data: { items: [], total: 0 } } as never
    )
  })

  it('renders page title', async () => {
    wrap()
    await waitFor(() => expect(screen.getByText(/work queue/i)).toBeInTheDocument())
  })

  it('shows pending tickets tab by default', async () => {
    wrap()
    await waitFor(() => expect(screen.getByText('Add OAuth login')).toBeInTheDocument())
  })

  it('renders needs-estimation badge and disables send button', async () => {
    wrap()
    await waitFor(() => {
      expect(screen.getByText('needs-estimation')).toBeInTheDocument()
    })
    // The second ticket's "Send to work" button should be disabled
    const buttons = screen.getAllByRole('button', { name: /send to work/i })
    // Only the non-estimation ticket has an enabled button
    const enabledButtons = buttons.filter(b => !(b as HTMLButtonElement).disabled)
    expect(enabledButtons).toHaveLength(1)
  })

  it('triggers job and switches to history tab on success', async () => {
    const { orchestratorApi } = await import('../src/api/orchestratorClient')
    wrap()

    await waitFor(() => screen.getByText('Add OAuth login'))
    const sendButtons = screen.getAllByRole('button', { name: /send to work/i })
    const enabledButton = sendButtons.find(b => !(b as HTMLButtonElement).disabled)!

    fireEvent.click(enabledButton)
    await waitFor(() => expect(orchestratorApi.triggerJob).toHaveBeenCalledWith('t-1', 'p-1'))
    // Should switch to history tab
    await waitFor(() => expect(orchestratorApi.listJobs).toHaveBeenCalled())
  })

  it('switches to history tab on click', async () => {
    wrap()
    await waitFor(() => screen.getByText('Add OAuth login'))
    fireEvent.click(screen.getByText(/job history/i))
    await waitFor(() => expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument())
  })
})
