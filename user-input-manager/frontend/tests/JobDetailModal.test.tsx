import { render, screen, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { JobDetailModal } from '../src/components/queue/JobDetailModal'
import type { OrchestratorJob } from '../src/api/orchestratorClient'

vi.mock('../src/api/orchestratorClient', () => ({
  orchestratorApi: {
    getAuditTrail: vi.fn().mockResolvedValue({
      data: {
        items: [
          {
            id: 'a-1', job_id: 'job-1', ticket_id: 't-1', project_id: 'p-1',
            action: 'ADVANCE', from_state: 'triage', to_state: 'specification',
            assigned_agent: 'project_manager', blocked_reason: null,
            override_logged: false,
            details: 'Advanced to specification',
            created_at: '2024-01-01T10:00:00Z',
          },
          {
            id: 'a-2', job_id: 'job-1', ticket_id: 't-1', project_id: 'p-1',
            action: 'BLOCK', from_state: 'specification', to_state: null,
            assigned_agent: 'project_manager',
            blocked_reason: 'Gate triage_complete failed',
            override_logged: false,
            details: 'Blocked at specification',
            created_at: '2024-01-01T10:05:00Z',
          },
        ],
        total: 2,
      },
    }),
  },
}))

const mockJob: OrchestratorJob = {
  id: 'job-1', job_type: 'orchestrate', ticket_id: 't-1', project_id: 'p-1',
  status: 'done', priority: 0, triggered_by: 'user@test.com',
  error_message: null, attempts: 1,
  created_at: '2024-01-01T10:00:00Z',
  started_at: '2024-01-01T10:00:01Z',
  finished_at: '2024-01-01T10:00:03Z',
}

function wrap() {
  return render(
    <I18nextProvider i18n={i18n}>
      <JobDetailModal job={mockJob} onClose={vi.fn()} />
    </I18nextProvider>
  )
}

describe('JobDetailModal', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows job summary info', () => {
    wrap()
    expect(screen.getByText('t-1')).toBeInTheDocument()
    expect(screen.getByText('done')).toBeInTheDocument()
    expect(screen.getByText('user@test.com')).toBeInTheDocument()
  })

  it('shows duration', () => {
    wrap()
    expect(screen.getByText('2.0s')).toBeInTheDocument()
  })

  it('loads and shows audit trail', async () => {
    wrap()
    await waitFor(() => {
      expect(screen.getByText('Advanced to specification')).toBeInTheDocument()
      expect(screen.getByText('Blocked at specification')).toBeInTheDocument()
    })
  })

  it('shows ADVANCE and BLOCK action badges', async () => {
    wrap()
    await waitFor(() => {
      expect(screen.getByText('ADVANCE')).toBeInTheDocument()
      expect(screen.getByText('BLOCK')).toBeInTheDocument()
    })
  })

  it('shows blocked reason', async () => {
    wrap()
    await waitFor(() => {
      expect(screen.getByText(/Gate triage_complete failed/)).toBeInTheDocument()
    })
  })

  it('shows state transitions', async () => {
    wrap()
    await waitFor(() => {
      expect(screen.getByText('triage')).toBeInTheDocument()
      expect(screen.getByText('specification')).toBeInTheDocument()
    })
  })
})
