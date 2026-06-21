import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { AuditTrailPage } from '../src/components/factory/AuditTrailPage'

const mockEntries = [
  {
    id: 'e-1', job_id: 'job-1', ticket_id: 't-1', project_id: 'p-1',
    action: 'ADVANCE', from_state: 'triage', to_state: 'specification',
    assigned_agent: 'project_manager', blocked_reason: null,
    override_logged: false, details: 'Advanced to specification',
    created_at: '2024-01-01T10:00:00Z',
  },
  {
    id: 'e-2', job_id: 'job-2', ticket_id: 't-1', project_id: 'p-1',
    action: 'BLOCK', from_state: 'specification', to_state: null,
    assigned_agent: null, blocked_reason: 'Gate code_review failed',
    override_logged: false, details: 'Blocked at specification',
    created_at: '2024-01-01T11:00:00Z',
  },
]

const listMock = vi.fn().mockResolvedValue({ data: { items: mockEntries, total: 2 } })

vi.mock('../src/api/orchestrator', () => ({
  auditApi: { list: listMock },
}))

function wrap(ui: React.ReactNode) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>)
}

describe('AuditTrailPage', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows search input initially', () => {
    wrap(<AuditTrailPage />)
    expect(screen.getByPlaceholderText(/ticket id/i)).toBeInTheDocument()
  })

  it('loads audit entries after search', async () => {
    wrap(<AuditTrailPage />)
    fireEvent.change(screen.getByPlaceholderText(/ticket id/i), { target: { value: 't-1' } })
    fireEvent.click(screen.getByRole('button', { name: /search/i }))
    await waitFor(() => expect(screen.getByText('Advanced to specification')).toBeInTheDocument())
  })

  it('shows ADVANCE and BLOCK badges', async () => {
    wrap(<AuditTrailPage />)
    fireEvent.change(screen.getByPlaceholderText(/ticket id/i), { target: { value: 't-1' } })
    fireEvent.click(screen.getByRole('button', { name: /search/i }))
    await waitFor(() => {
      expect(screen.getByText('ADVANCE')).toBeInTheDocument()
      expect(screen.getByText('BLOCK')).toBeInTheDocument()
    })
  })

  it('shows blocked reason', async () => {
    wrap(<AuditTrailPage />)
    fireEvent.change(screen.getByPlaceholderText(/ticket id/i), { target: { value: 't-1' } })
    fireEvent.click(screen.getByRole('button', { name: /search/i }))
    await waitFor(() => expect(screen.getByText(/Gate code_review failed/)).toBeInTheDocument())
  })

  it('triggers search on Enter key', async () => {
    wrap(<AuditTrailPage />)
    const input = screen.getByPlaceholderText(/ticket id/i)
    fireEvent.change(input, { target: { value: 't-enter' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(listMock).toHaveBeenCalledWith('t-enter', undefined))
  })

  it('shows empty state when no entries', async () => {
    listMock.mockResolvedValueOnce({ data: { items: [], total: 0 } })
    wrap(<AuditTrailPage />)
    fireEvent.change(screen.getByPlaceholderText(/ticket id/i), { target: { value: 't-empty' } })
    fireEvent.click(screen.getByRole('button', { name: /search/i }))
    await waitFor(() => expect(screen.getByText(/no audit entries/i)).toBeInTheDocument())
  })
})
