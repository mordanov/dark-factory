import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { I18nextProvider } from 'react-i18next'
import i18n from '../src/i18n/i18n'
import { NewSessionModal } from '../src/components/sessions/NewSessionModal'

vi.mock('../src/api/client', () => ({
  tmApi: {
    listProjects: vi.fn().mockResolvedValue({
      data: [{ id: 'p1', name: 'Project Alpha' }],
    }),
  },
  sessionsApi: {
    create: vi.fn().mockResolvedValue({
      data: {
        session: { id: 'sess-1', session_type: 'new_project', status: 'in_progress' },
        latest_iteration: { id: 'it-1', role: 'assistant', iteration_number: 2, prompt_text: 'refined' },
      },
    }),
  },
}))

const onClose = vi.fn()
const onCreated = vi.fn()

function wrap(ui: React.ReactNode) {
  return render(<I18nextProvider i18n={i18n}>{ui}</I18nextProvider>)
}

describe('NewSessionModal', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders new project fields by default', () => {
    wrap(<NewSessionModal onClose={onClose} onCreated={onCreated} />)
    expect(screen.getByLabelText(/project name/i)).toBeInTheDocument()
  })

  it('switches to existing project mode and loads projects', async () => {
    wrap(<NewSessionModal onClose={onClose} onCreated={onCreated} />)
    fireEvent.click(screen.getByText(/existing project/i))
    await waitFor(() => expect(screen.getByText('Project Alpha')).toBeInTheDocument())
  })

  it('calls onCreated after successful submission', async () => {
    const { sessionsApi } = await import('../src/api/client')
    wrap(<NewSessionModal onClose={onClose} onCreated={onCreated} />)

    fireEvent.change(screen.getByLabelText(/project name/i), { target: { value: 'New Project' } })
    fireEvent.change(screen.getByLabelText(/describe/i), { target: { value: 'build auth system' } })
    fireEvent.click(screen.getByRole('button', { name: /start refinement/i }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith('sess-1'))
  })

  it('calls onClose when backdrop is clicked', () => {
    wrap(<NewSessionModal onClose={onClose} onCreated={onCreated} />)
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalled()
  })
})
