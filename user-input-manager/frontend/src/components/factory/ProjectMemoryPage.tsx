import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { memoryApi, type AdrSummary, type ProjectMemory } from '../../api/orchestrator'

const ADR_STATUS_BADGE: Record<string, string> = {
  accepted: 'badge-green',
  proposed: 'badge-amber',
  superseded: 'badge-muted',
}

export function ProjectMemoryPage() {
  const { t } = useTranslation()
  const [projectId, setProjectId] = useState('')
  const [input, setInput] = useState('')
  const [memory, setMemory] = useState<ProjectMemory | null>(null)
  const [adrs, setAdrs] = useState<AdrSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [searched, setSearched] = useState(false)
  const [expandedAdr, setExpandedAdr] = useState<string | null>(null)

  const search = async () => {
    if (!input.trim()) return
    setLoading(true)
    setError('')
    setMemory(null)
    setAdrs([])
    try {
      const [memResp, adrResp] = await Promise.allSettled([
        memoryApi.get(input.trim()),
        memoryApi.adrs(input.trim(), 'all'),
      ])
      if (memResp.status === 'fulfilled') setMemory(memResp.value.data)
      if (adrResp.status === 'fulfilled') setAdrs(adrResp.value.data.adrs)
      setProjectId(input.trim())
      setSearched(true)
    } catch {
      setError(t('common.error'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{t('factory.memory')}</h1>
      </div>

      <div className="flex gap-8 mb-24" style={{ maxWidth: 480 }}>
        <input
          placeholder={t('factory.enter_project_id')}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
        />
        <button className="btn btn-primary" onClick={search} disabled={loading || !input.trim()}>
          {loading ? <span className="spinner" /> : t('factory.search')}
        </button>
      </div>

      {error && <div className="error-banner mb-16">{error}</div>}

      {searched && !memory && !loading && (
        <div className="empty-state">{t('factory.no_memory')}</div>
      )}

      {memory && (
        <div className="flex flex-col gap-24">
          {/* Memory card */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">{t('factory.content')}</span>
              <div className="flex gap-8" style={{ alignItems: 'center' }}>
                <span className="text-muted mono" style={{ fontSize: '0.7rem' }}>
                  v{memory.version}
                </span>
                {memory.last_ticket_id && (
                  <span className="text-muted mono" style={{ fontSize: '0.7rem' }}>
                    ← {memory.last_ticket_id}
                  </span>
                )}
                {memory.updated_at && (
                  <span className="text-muted" style={{ fontSize: '0.7rem' }}>
                    {new Date(memory.updated_at).toLocaleString()}
                  </span>
                )}
              </div>
            </div>
            <pre style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '0.78rem',
              lineHeight: 1.6,
              color: 'var(--text-secondary)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              background: 'var(--bg-2)',
              padding: '12px 14px',
              borderRadius: 'var(--radius)',
              maxHeight: 400,
              overflowY: 'auto',
            }}>
              {memory.content}
            </pre>
          </div>

          {/* ADRs */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">{t('factory.adrs')}</span>
              <span className="text-muted mono" style={{ fontSize: '0.7rem' }}>
                {adrs.length}
              </span>
            </div>

            {adrs.length === 0 ? (
              <div className="empty-state" style={{ padding: '24px 0' }}>
                {t('factory.no_adrs')}
              </div>
            ) : (
              <div className="flex flex-col gap-8">
                {adrs.map(adr => (
                  <div
                    key={adr.id}
                    style={{
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      overflow: 'hidden',
                    }}
                  >
                    <button
                      onClick={() => setExpandedAdr(expandedAdr === adr.id ? null : adr.id)}
                      style={{
                        width: '100%',
                        background: 'var(--bg-2)',
                        border: 'none',
                        padding: '10px 14px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        cursor: 'pointer',
                        textAlign: 'left',
                      }}
                    >
                      <span className="mono text-amber" style={{ fontSize: '0.75rem', minWidth: 64 }}>
                        {adr.id}
                      </span>
                      <span style={{ flex: 1, fontSize: '0.875rem', color: 'var(--text-primary)' }}>
                        {adr.title}
                      </span>
                      <span className={`badge ${ADR_STATUS_BADGE[adr.status] ?? 'badge-muted'}`}>
                        {adr.status}
                      </span>
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                        {expandedAdr === adr.id ? '▲' : '▼'}
                      </span>
                    </button>

                    {expandedAdr === adr.id && adr.summary && (
                      <div style={{ padding: '10px 14px', background: 'var(--bg-1)' }}>
                        <div className="meta-label" style={{ marginBottom: 4 }}>
                          {t('factory.adr_summary')}
                        </div>
                        <div className="meta-text">{adr.summary}</div>
                        {adr.ticket_id && (
                          <div className="text-muted mono" style={{ fontSize: '0.7rem', marginTop: 8 }}>
                            Ticket: {adr.ticket_id}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
