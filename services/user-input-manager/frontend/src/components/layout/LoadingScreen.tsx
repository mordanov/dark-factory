export function LoadingScreen() {
  return (
    <div
      role="status"
      aria-label="Connecting to Dark Factory"
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '1rem',
        background: 'var(--bg-primary)',
        color: 'var(--text-secondary)',
      }}
    >
      <span aria-hidden="true" className="spinner" style={{ width: 32, height: 32, borderWidth: 3 }} />
      <span style={{ fontSize: '0.875rem', letterSpacing: '0.05em' }}>Connecting to Dark Factory…</span>
    </div>
  )
}
