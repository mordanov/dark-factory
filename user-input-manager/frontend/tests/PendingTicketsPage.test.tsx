import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { PendingTicketsPage } from '../src/components/factory/PendingTicketsPage'

vi.mock('../src/api/orchestrator', () => ({
  pendingApi: {
    list: vi.fn().mockResolvedValue({
      data: {
        tickets: [
          {
            id: 't-1', project_id: 'p-1', title: 'Add OAuth login',
            description: '', ticket_type: 'feature',
            tags: ['needs-estimation'], fsm_status: 'backlog',
            blocked_reason: null, brainstorm_round: 0,
            assigned_agent: null, override: false,
            dependencies: [], updated_at: null,
          },
          {
            id: 't-2', project_id: 'p-1', title: 'Fix null pointer',
            description: '', ticket_type: 'bugfix',
            tags: [], fsm_status: 'triage',
            blocked_reason: 'Gate failed', brainstorm_round: 0,
            assigned_agent: 'project_manager', override: false,
            dependencies: [], updated_at: null,
          },
        ],
        total: 2,
      },
    }),
  },
  jobsApi: {
    trigger: vi.fn().mockResolvedValue({ data: { id: 'job-1', status: 'pending' } }),
  },
}))

function wrap(ui: React.ReactNode) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>)
}

describe('PendingTicketsPage', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders ticket list', async () => {
    wrap(<PendingTicketsPage />)
    await waitFor(() => expect(screen.getByText('Add OAuth login')).toBeInTheDocument())
    expect(screen.getByText('Fix null pointer')).toBeInTheDocument()
  })

  it('shows needs-estimation badge', async () => {
    wrap(<PendingTicketsPage />)
    await waitFor(() => expect(screen.getByText('needs-estimation')).toBeInTheDocument())
  })

  it('shows blocked_reason', async () => {
    wrap(<PendingTicketsPage />)
    await waitFor(() => expect(screen.getByText(/Gate failed/)).toBeInTheDocument())
  })

  it('shows assigned agent badge', async () => {
    wrap(<PendingTicketsPage />)
    await waitFor(() => expect(screen.getByText('project_manager')).toBeInTheDocument())
  })

  it('trigger button calls jobsApi.trigger', async () => {
    const { jobsApi } = await import('../src/api/orchestrator')
    wrap(<PendingTicketsPage />)
    const buttons = await screen.findAllByRole('button', { name: /send to work/i })
    fireEvent.click(buttons[0])
    await waitFor(() => expect(jobsApi.trigger).toHaveBeenCalledWith('t-1', 'p-1', 0))
  })

  it('shows success flash after trigger', async () => {
    wrap(<PendingTicketsPage />)
    const buttons = await screen.findAllByRole('button', { name: /send to work/i })
    fireEvent.click(buttons[0])
    await waitFor(() => expect(screen.getByText(/Job started/i)).toBeInTheDocument())
  })
})
