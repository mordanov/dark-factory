import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AgentConfig } from '../../api/client'

interface Props {
  agentConfig: AgentConfig | null
}

export function AgentConfigPanel({ agentConfig }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  if (!agentConfig) return null

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <button
        className="card-header"
        style={{ width: '100%', cursor: 'pointer', background: 'none', border: 'none', padding: 0, textAlign: 'left' }}
        onClick={() => setExpanded(e => !e)}
        aria-expanded={expanded}
      >
        <span className="card-title">{t('planning.agent_config_title')}</span>
        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <div style={{ marginTop: 12 }}>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 12 }}>
            {t('planning.agent_config_hint')}
          </p>
          {(agentConfig.tech_stack?.length ?? 0) > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div className="meta-label">Tech stack</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 6 }}>
                {agentConfig.tech_stack.map(s => (
                  <span key={s} className="badge badge-muted">{s}</span>
                ))}
              </div>
            </div>
          )}
          {(agentConfig.agent_overrides?.length ?? 0) > 0 && (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', padding: '6px 8px', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', borderBottom: '1px solid var(--border)' }}>Agent</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px', fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', borderBottom: '1px solid var(--border)' }}>Override</th>
                </tr>
              </thead>
              <tbody>
                {agentConfig.agent_overrides.map(ov => (
                  <tr key={ov.agent_id}>
                    <td style={{ padding: '8px 8px', fontSize: '0.8rem', color: 'var(--amber)', fontFamily: 'var(--font-mono)', borderBottom: '1px solid var(--border)', verticalAlign: 'top', whiteSpace: 'nowrap' }}>
                      {ov.agent_id}
                    </td>
                    <td style={{ padding: '8px 8px', fontSize: '0.8rem', color: 'var(--text-secondary)', borderBottom: '1px solid var(--border)', lineHeight: 1.5 }}>
                      {ov.override_text}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
