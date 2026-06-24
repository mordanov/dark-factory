# UX Phase 8 Deferred Items

**Feature**: 004-keycloak-iam-migration  
**Author**: designer agent  
**Date**: 2026-06-24  
**Status**: Ready for implementation in Phase 8  

These two items were deferred from the Phase 3/5 review. Both are non-blocking for MVP.

---

## DEFER-1: Network Error State on `keycloak.init()` Failure (AC-UX-011)

### When

`keycloak.init()` rejects — typically because Keycloak is unreachable at the time the app loads
(network down, Keycloak container not ready, wrong `VITE_KEYCLOAK_URL`).

### Current behaviour (MVP)

`initialize()` in `authStore.ts` does not catch the rejection. The promise rejects silently,
`initialized` stays `false`, and `App.tsx` / `AppRoot` renders `<LoadingScreen />` indefinitely.
The user sees an unresponsive spinner with no recovery path.

### Required behaviour

When `keycloak.init()` rejects, the application must:
1. Exit the loading state
2. Display a human-readable error screen
3. Offer a Retry action that re-runs `initialize()`

### authStore change (both UIM and TM)

Add an `initError: boolean` field to the store. Catch the `keycloak.init()` rejection and set
`initError: true`. Example:

```ts
async initialize() {
  try {
    await keycloak.init({ onLoad: 'login-required', pkceMethod: 'S256' })
    // ... existing success path unchanged ...
    set({ initialized: true, initError: false, user: { ... } })
  } catch {
    set({ initialized: false, initError: true })
  }
},
```

The `logout()` and `getToken()` functions are unchanged.

### App.tsx / AppRoot change (both UIM and TM)

```tsx
const initialized = useAuthStore((s) => s.initialized)
const initError   = useAuthStore((s) => s.initError)
const initialize  = useAuthStore((s) => s.initialize)

if (initError)   return <AuthErrorScreen onRetry={() => void initialize()} />
if (!initialized) return <LoadingScreen />
// ... normal app ...
```

### AuthErrorScreen component

Create as `src/components/layout/AuthErrorScreen.tsx` in both frontends.

**Props**: `onRetry: () => void`

**Layout**:

```
┌─────────────────────────────────────┐
│                                     │
│       Unable to connect             │
│                                     │
│  Dark Factory could not reach the   │
│  authentication server. Please      │
│  check your network connection and  │
│  try again.                         │
│                                     │
│        [ Retry ]                    │
│                                     │
└─────────────────────────────────────┘
```

**Exact copy**:
- Heading: `Unable to connect`
- Body: `Dark Factory could not reach the authentication server. Please check your network connection and try again.`
- Button label: `Retry`

**Constraints**:
- Do NOT expose `VITE_KEYCLOAK_URL`, realm name, or the error object
- Full-viewport centred layout (same as `LoadingScreen`)
- Background: same root background token as `LoadingScreen`

**Accessibility**:
- Root element: `role="alert"` (announced immediately on render)
- Heading: `<h1>` or `role="heading" aria-level="1"`
- On mount: move focus to the Retry button (`useEffect` + `ref.current?.focus()`)
- Retry button: standard `<button>` — keyboard-operable with `Enter` and `Space`
- Visible focus indicator on button (≥ 2px outline, contrast ≥ 3:1)

### UIM-specific style

Use the same inline-style approach as `LoadingScreen.tsx`:

```tsx
export function AuthErrorScreen({ onRetry }: { onRetry: () => void }) {
  const retryRef = useRef<HTMLButtonElement>(null)
  useEffect(() => { retryRef.current?.focus() }, [])

  return (
    <div
      role="alert"
      style={{
        position: 'fixed', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
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
```

### TM-specific style

Use Tailwind + shadcn/ui `Button` (same as other TM components):

```tsx
export function AuthErrorScreen({ onRetry }: { onRetry: () => void }) {
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
```

### Acceptance criteria (replaces AC-UX-011)

**Given** Keycloak is unreachable when the app mounts  
**When** `keycloak.init()` rejects  
**Then** `LoadingScreen` is replaced by `AuthErrorScreen`  
**And** the screen contains the heading "Unable to connect"  
**And** a "Retry" button is present, has focus on render, and is keyboard-activatable  
**And** no Keycloak URL, realm, or technical error detail is shown  
**And** the root element has `role="alert"`  
**And** clicking Retry calls `initialize()` again, which re-renders `LoadingScreen` while retrying

---

## DEFER-2: Reset `authStore` State Before Logout Redirect (AC-UX-013)

### Current behaviour

`logout()` calls `keycloak.logout()` which triggers a browser redirect. The Zustand store
retains `user` and `initialized: true` until the page unloads. This is invisible to users but
means:

- If `keycloak.logout()` returns before redirect (unusual, but possible), the app briefly
  shows authenticated UI
- `authStore.user` is non-null during the logout transition
- Tests that stub `keycloak.logout` will see stale state after the call returns

### Required change (both UIM and TM `authStore.ts`)

Reset store state synchronously before calling `keycloak.logout()`:

```ts
async logout() {
  set({ initialized: false, user: null })
  await keycloak.logout()
},
```

This is a one-line change. No UI impact for real users (page navigates away immediately).

### Acceptance criteria (replaces AC-UX-013)

**Given** a user is authenticated (`authStore.user` is non-null)  
**When** `logout()` is called  
**Then** `authStore.user` is set to `null` synchronously before `keycloak.logout()` is awaited  
**And** `authStore.initialized` is set to `false` synchronously before `keycloak.logout()` is awaited  
**And** `keycloak.logout()` is still called (the redirect still happens)

---

## Vitest Test Additions (for Autotester)

### AC-UX-011 test

```ts
it('shows AuthErrorScreen when keycloak.init() rejects', async () => {
  vi.mocked(keycloak.init).mockRejectedValueOnce(new Error('Network Error'))
  render(<App />)
  // LoadingScreen first
  expect(screen.queryByRole('alert')).toBeNull()
  // After init rejects
  await waitFor(() => {
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /unable to connect/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /retry/i })).toHaveFocus()
  })
})

it('retries initialize() when Retry is clicked', async () => {
  vi.mocked(keycloak.init)
    .mockRejectedValueOnce(new Error('Network Error'))
    .mockResolvedValueOnce(true)
  render(<App />)
  await waitFor(() => screen.getByRole('button', { name: /retry/i }))
  await userEvent.click(screen.getByRole('button', { name: /retry/i }))
  expect(keycloak.init).toHaveBeenCalledTimes(2)
})
```

### AC-UX-013 test

```ts
it('resets user and initialized before calling keycloak.logout', async () => {
  const store = useAuthStore.getState()
  // Seed authenticated state
  useAuthStore.setState({ initialized: true, user: { sub: 'u1', email: 'a@b.com', username: 'a', isAdmin: false } })

  let stateAtLogout: { user: unknown; initialized: boolean } | null = null
  vi.mocked(keycloak.logout).mockImplementation(async () => {
    stateAtLogout = {
      user: useAuthStore.getState().user,
      initialized: useAuthStore.getState().initialized,
    }
  })

  await store.logout()
  expect(stateAtLogout?.user).toBeNull()
  expect(stateAtLogout?.initialized).toBe(false)
})
```
