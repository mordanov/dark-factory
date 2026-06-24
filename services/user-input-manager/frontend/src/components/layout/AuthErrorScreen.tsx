import { useRef, useEffect } from 'react'

interface Props {
  onRetry: () => void
}

export function AuthErrorScreen({ onRetry }: Props) {
  const retryRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { retryRef.current?.focus() }, [])

  return (
    <div
      role="alert"
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '1rem',
        background: 'var(--bg-primary)',
        color: 'var(--text-primary)',
        padding: '2rem',
        textAlign: 'center',
      }}
    >
      <h1 style={{ fontSize: '1.125rem', fontWeight: 600, margin: 0 }}>Unable to connect</h1>
      <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', maxWidth: '24rem', margin: 0 }}>
        Dark Factory could not reach the authentication server. Please check your network
        connection and try again.
      </p>
      <button ref={retryRef} className="btn btn-primary btn-sm" onClick={onRetry}>
        Retry
      </button>
    </div>
  )
}
