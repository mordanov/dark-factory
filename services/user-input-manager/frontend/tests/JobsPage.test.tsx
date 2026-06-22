import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { JobsPage } from '../src/components/factory/JobsPage'

vi.mock('../src/api/orchestrator', () => ({
  jobsApi: { list: vi.fn() },
}))

const mockJobs = [
  {
    id: 'job-1', job_type: 'orchestrate', ticket_id: 't-1', project_id: 'p-1',
    status: 'done', priority: 0, triggered_by: 'uid-abc',
    error_message: null, attempts: 1,
    created_at: '2024-01-01T10:00:00Z',
    started_at: '2024-01-01T10:00:01Z',
    finished_at: '2024-01-01T10:00:45Z',
  },
  {
    id: 'job-2', job_type: 'distill', ticket_id: 't-2', project_id: 'p-1',
    status: 'failed', priority: 2, triggered_by: 'orchestrator',
    error_message: 'LLM timeout after 120s', attempts: 3,
    created_at: '2024-01-01T11:00:00Z',
    started_at: '2024-01-01T11:00:01Z',
    finished_at: '2024-01-01T11:02:01Z',
  },
]

function wrap(ui: React.ReactNode) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>)
}

describe('JobsPage', () => {
  beforeEach(async () => {
    const { jobsApi } = await import('../src/api/orchestrator')
    vi.mocked(jobsApi.list).mockResolvedValue(
      { data: { items: mockJobs, total: 2 } } as never
    )
  })

  it('renders job list', async () => {
    wrap(<JobsPage />)
    await waitFor(() => expect(screen.getByText('t-1')).toBeInTheDocument())
    expect(screen.getByText('t-2')).toBeInTheDocument()
  })

  it('shows done badge', async () => {
    wrap(<JobsPage />)
    await waitFor(() => expect(screen.getByText('Done')).toBeInTheDocument())
  })

  it('shows failed badge and error message', async () => {
    wrap(<JobsPage />)
    await waitFor(() => expect(screen.getByText('Failed')).toBeInTheDocument())
    expect(screen.getByText(/LLM timeout/)).toBeInTheDocument()
  })

  it('filters by status via select', async () => {
    const { jobsApi } = await import('../src/api/orchestrator')
    wrap(<JobsPage />)
    await waitFor(() => screen.getByText('t-1'))
    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'done' } })
    await waitFor(() => expect(jobsApi.list).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'done' })
    ))
  })

  it('filters by ticket id', async () => {
    const { jobsApi } = await import('../src/api/orchestrator')
    wrap(<JobsPage />)
    await waitFor(() => screen.getByText('t-1'))
    const input = screen.getByPlaceholderText(/ticket id/i)
    fireEvent.change(input, { target: { value: 't-specific' } })
    fireEvent.click(screen.getByRole('button', { name: /search/i }))
    await waitFor(() => expect(jobsApi.list).toHaveBeenCalledWith(
      expect.objectContaining({ ticket_id: 't-specific' })
    ))
  })

  it('shows empty state when no jobs', async () => {
    const { jobsApi } = await import('../src/api/orchestrator')
    vi.mocked(jobsApi.list).mockResolvedValueOnce({ data: { items: [], total: 0 } } as never)
    wrap(<JobsPage />)
    await waitFor(() => expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument())
  })
})
