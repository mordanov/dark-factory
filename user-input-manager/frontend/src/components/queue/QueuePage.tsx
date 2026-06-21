import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PendingTicketsPanel } from './PendingTicketsPanel'
import { JobsPanel } from './JobsPanel'

type Tab = 'pending' | 'history'

export function QueuePage() {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('pending')
  const [refreshSignal, setRefreshSignal] = useState(0)

  const handleTriggered = () => {
    // Switch to history and trigger a reload there
    setTab('history')
    setRefreshSignal(s => s + 1)
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('queue.title')}</h1>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-8" style={{ marginBottom: 24, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {(['pending', 'history'] as Tab[]).map(t_tab => (
          <button
            key={t_tab}
            onClick={() => setTab(t_tab)}
            style={{
              padding: '8px 16px',
              background: 'none',
              border: 'none',
              borderBottom: tab === t_tab ? '2px solid var(--amber)' : '2px solid transparent',
              color: tab === t_tab ? 'var(--amber)' : 'var(--text-secondary)',
              cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.8rem',
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: -1,
              transition: 'color 0.15s',
            }}
          >
            {t(`queue.tab_${t_tab}`)}
          </button>
        ))}
      </div>

      {tab === 'pending' && (
        <PendingTicketsPanel onTriggered={handleTriggered} />
      )}

      {tab === 'history' && (
        <JobsPanel refreshSignal={refreshSignal} />
      )}
    </div>
  )
}
