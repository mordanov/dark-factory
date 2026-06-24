import { useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'

interface Props {
  onRetry: () => void
}

export function AuthErrorScreen({ onRetry }: Props) {
  const retryRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { retryRef.current?.focus() }, [])

  return (
    <div
      role="alert"
      className="min-h-screen flex flex-col items-center justify-center gap-4 bg-background text-foreground px-6 text-center"
    >
      <h1 className="text-lg font-semibold">Unable to connect</h1>
      <p className="text-sm text-muted-foreground max-w-sm">
        Dark Factory could not reach the authentication server. Please check your network
        connection and try again.
      </p>
      <Button ref={retryRef} onClick={onRetry}>Retry</Button>
    </div>
  )
}
