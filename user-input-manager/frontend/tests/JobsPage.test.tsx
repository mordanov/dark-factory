import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { JobsPage } from '../src/components/factory/JobsPage'

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

const listMock = vi.fn().mockResolvedValue({ data: { items: mockJobs, total: 2 } })

vi.mock('../src/api/orchestrator', () => ({
  jobsApi: { list: listMock },
}))

function wrap(ui: React.ReactNode) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>)
}

describe('JobsPage', () => {
  beforeEach(() => { vi.clearAllMocks() })

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
    wrap(<JobsPage />)
    await waitFor(() => screen.getByText('t-1'))
    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: 'done' } })
    await waitFor(() => expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'done' })
    ))
  })

  it('filters by ticket id', async () => {
    wrap(<JobsPage />)
    await waitFor(() => screen.getByText('t-1'))
    const input = screen.getByPlaceholderText(/ticket id/i)
    fireEvent.change(input, { target: { value: 't-specific' } })
    fireEvent.click(screen.getByRole('button', { name: /search/i }))
    await waitFor(() => expect(listMock).toHaveBeenCalledWith(
      expect.objectContaining({ ticket_id: 't-specific' })
    ))
  })

  it('shows empty state when no jobs', async () => {
    listMock.mockResolvedValueOnce({ data: { items: [], total: 0 } })
    wrap(<JobsPage />)
    await waitFor(() => expect(screen.getByText(/no jobs yet/i)).toBeInTheDocument())
  })
})
