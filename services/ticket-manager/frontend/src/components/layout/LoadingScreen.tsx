export function LoadingScreen() {
  return (
    <div
      role="status"
      aria-label="Connecting to Dark Factory"
      className="min-h-screen flex flex-col items-center justify-center gap-4 bg-background text-muted-foreground"
    >
      <div aria-hidden="true" className="h-8 w-8 rounded-full border-2 border-border border-t-foreground animate-spin" />
      <span className="text-sm tracking-wide">Connecting to Dark Factory…</span>
    </div>
  )
}
