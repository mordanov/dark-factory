import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { ApproveModal } from '../src/components/sessions/ApproveModal'
import type { Session } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  sessionsApi: {
    approve: vi.fn().mockResolvedValue({
      data: { session: {}, ticket_id: 'tkt-999', project_id: 'proj-1' },
    }),
  },
}))

const mockSession: Session = {
  id: 'sess-1',
  session_type: 'new_project',
  tm_project_id: null,
  tm_project_name: 'My Project',
  tm_ticket_id: null,
  tm_ticket_title: null,
  status: 'in_progress',
  created_at: '',
  updated_at: '',
}

const onClose = vi.fn()
const onApproved = vi.fn()

function wrap(ui: React.ReactNode) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>)
}

describe('ApproveModal', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('pre-fills suggested title', () => {
    wrap(
      <ApproveModal
        session={mockSession}
        suggestedTitle="Add OAuth login"
        onClose={onClose}
        onApproved={onApproved}
      />
    )
    expect(screen.getByDisplayValue('Add OAuth login')).toBeInTheDocument()
  })

  it('shows project description field for new_project', () => {
    wrap(
      <ApproveModal
        session={mockSession}
        suggestedTitle="Title"
        onClose={onClose}
        onApproved={onApproved}
      />
    )
    expect(screen.getByLabelText(/project description/i)).toBeInTheDocument()
  })

  it('hides project description for existing_project', () => {
    wrap(
      <ApproveModal
        session={{ ...mockSession, session_type: 'existing_project' }}
        suggestedTitle="Title"
        onClose={onClose}
        onApproved={onApproved}
      />
    )
    expect(screen.queryByLabelText(/project description/i)).not.toBeInTheDocument()
  })

  it('calls onApproved with ticket id after confirm', async () => {
    wrap(
      <ApproveModal
        session={mockSession}
        suggestedTitle="My Ticket"
        onClose={onClose}
        onApproved={onApproved}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /create ticket/i }))
    await waitFor(() => expect(onApproved).toHaveBeenCalledWith('tkt-999'))
  })

  it('disables submit when title is empty', () => {
    wrap(
      <ApproveModal
        session={mockSession}
        suggestedTitle=""
        onClose={onClose}
        onApproved={onApproved}
      />
    )
    expect(screen.getByRole('button', { name: /create ticket/i })).toBeDisabled()
  })
})
