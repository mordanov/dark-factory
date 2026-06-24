# Code Review: Phase 3+5 — Frontend keycloak-js Integration + Admin UI Cleanup

**Feature**: 004-keycloak-iam-migration  
**Phase**: 3 (T025–T036) + 5 (T047–T051)  
**Reviewer**: code-reviewer agent  
**Date**: 2026-06-24  
**Scope**: `keycloak.ts` (UIM + TM), `store/auth.ts` (UIM + TM), `components/layout/LoadingScreen.tsx` (UIM + TM),
`App.tsx` (UIM), `main.tsx` (TM), `api/client.ts` (UIM + TM), `pages/AppRoutes.tsx` (UIM),
`router.tsx` (TM), `components/layout/Sidebar.tsx` (UIM), `components/layout/Navbar.tsx` (TM),
`.env.example` (UIM + TM)

---

## Code Review Result

### Decision

**CHANGES REQUESTED**

Two blocker-level issues and one major finding must be addressed before this phase can ship.
All other aspects of the implementation are correct and well-structured.

---

### Scope Reviewed

- T025–T026 `keycloak.ts` (both frontends)
- T027–T028 `store/auth.ts` (both frontends — note: implemented as `auth.ts`, not `authStore.ts`)
- T029–T030 `LoadingScreen.tsx` (both frontends)
- T031–T032 `App.tsx` (UIM) / `main.tsx` (TM)
- T033–T034 `api/client.ts` (both frontends)
- T035–T036 `.env.example` (both frontends)
- T047–T048 `AppRoutes.tsx` (UIM) / `router.tsx` (TM)
- T049–T050 `Sidebar.tsx` (UIM) / `Navbar.tsx` (TM)
- T051 `LoginPage.tsx` — deletion confirmed via frontend agent message

---

### Summary

The keycloak-js integration follows the correct PKCE+`login-required` pattern. Tokens are
held in-memory by the keycloak-js object; no `localStorage`/`sessionStorage` writes were
found. Both frontends correctly guard application content behind `!initialized`. The admin
console link is correctly conditional on `user?.isAdmin` and guarded against empty
`VITE_KEYCLOAK_URL`. Route cleanup is complete — `/login` and `/admin` routes are absent from
both routers.

Two blocker issues remain: (1) `initialize()` has no error handling for Keycloak init failure,
leaving the app stuck on `LoadingScreen` forever with no user-visible recovery path (violates
AC-UX-011 and spec FR-019); (2) `logout()` does not clear `user` and `initialized` state in
the Zustand store before calling `keycloak.logout()`, meaning AC-UX-013 fails. One major
finding: the `onTokenExpired` handler calls `initialize()` on refresh failure, which re-runs
`keycloak.init()` — this can cause a double-init error in keycloak-js.

---

### Blockers

#### Blocker: `initialize()` does not handle `keycloak.init()` failure — no error state, no retry UI (AC-UX-011 violated)

**Location**: `services/user-input-manager/frontend/src/store/auth.ts:24`,
`services/ticket-manager/frontend/src/store/auth.ts:24`  
**Issue**: `initialize()` calls `await keycloak.init(...)` with no `try/catch`. If
`keycloak.init()` rejects (Keycloak unreachable), the Promise rejects silently. The store
stays at `initialized: false` permanently and `LoadingScreen` is never replaced. The user
sees a spinner forever with no "Unable to connect" message, no Retry button, and no way to
recover without a hard refresh.  
**Impact**: Violates AC-UX-011, FR-019, and the UX guidance Section 3.3. The app is
completely broken when Keycloak is unreachable — users cannot tell if the page loaded or
crashed.  
**Required action**: Add error state to the store and catch `keycloak.init()` failure:

```typescript
// In AuthState interface:
error: string | null
setError: (msg: string | null) => void

// In initialize():
async initialize() {
  set({ error: null })
  try {
    await keycloak.init({ onLoad: 'login-required', pkceMethod: 'S256' })
    // ... existing state setup ...
    set({ initialized: true, user: { ... }, error: null })
  } catch {
    set({ initialized: false, error: 'Unable to connect' })
  }
}
```

And in `App.tsx` / `main.tsx`, render the error state when `error` is non-null:

```tsx
if (error) return <AuthErrorScreen onRetry={initialize} />
if (!initialized) return <LoadingScreen />
```

`AuthErrorScreen` must show "Unable to connect" heading, the body copy from UX guidance 3.3,
a focusable "Retry" button, `role="alert"`, and must not expose Keycloak URL.

**Evidence**: UX guidance AC-UX-011; spec FR-019; security review FIND-02 (user must not see
technical error detail).

---

#### Blocker: `logout()` does not reset Zustand store state — AC-UX-013 violated

**Location**: `services/user-input-manager/frontend/src/store/auth.ts:47`,
`services/ticket-manager/frontend/src/store/auth.ts:47`  
**Issue**: The `logout()` implementation is:
```typescript
async logout() {
  await keycloak.logout()
}
```
It calls `keycloak.logout()` (which navigates away) but never calls `set({ user: null, initialized: false })`.
If `keycloak.logout()` resolves before the redirect completes (which can happen in some
timing windows), or if the page doesn't navigate (e.g., network error during logout redirect),
`authStore.user` remains non-null and `initialized` remains `true`.  
**Impact**: Violates AC-UX-013. Any component that reads `authStore.user` after logout triggers
could see stale identity. Also breaks the `logout()` unit test contract.  
**Required action**: Clear store state before the Keycloak redirect:

```typescript
async logout() {
  set({ user: null, initialized: false })
  await keycloak.logout()
}
```

**Evidence**: UX guidance AC-UX-013; auth-adapter contract C-AUTH-01 (user identity is only valid during authenticated session).

---

### Major Findings

#### Major: `onTokenExpired` handler calls `initialize()` — double-init risk in keycloak-js

**Location**: `services/user-input-manager/frontend/src/store/auth.ts:27–30`,
`services/ticket-manager/frontend/src/store/auth.ts:27–30`  
**Issue**: When `keycloak.updateToken(30)` fails (refresh token expired), the handler calls
`useAuthStore.getState().initialize()`, which calls `keycloak.init()` again. Calling
`keycloak.init()` on an already-initialized keycloak-js instance is an error — keycloak-js
throws `"A 'Keycloak' instance can only be initialized once"` in keycloak-js 25.x.  
**Impact**: On session expiry, the app crashes with an unhandled JS exception rather than
redirecting to login. This is a functional regression for long-running sessions.  
**Required action**: On refresh failure, call `keycloak.logout()` directly instead of
`initialize()`:

```typescript
keycloak.onTokenExpired = () => {
  keycloak.updateToken(30).catch(() => {
    keycloak.logout()
  })
}
```

This correctly implements the UX guidance Section 3.2 (session expiry → silent redirect to
login).

**Evidence**: keycloak-js 25.x API; UX guidance 3.2; arch-review notes on 401 retry.

---

### Minor Findings

#### Minor: `logout()` is missing a `redirectUri` argument — user may land on Keycloak login with no redirect back to app

**Location**: `store/auth.ts:48`  
**Issue**: `keycloak.logout()` called without `redirectUri`. The Keycloak default may redirect
to the realm login page without pointing back to the application root.  
**Required action**: Pass `redirectUri` to ensure the user is returned to the app after
logout, triggering a clean login flow:

```typescript
await keycloak.logout({ redirectUri: window.location.origin })
```

**Evidence**: UX guidance Section 4.3; keycloak-js docs.

---

#### Minor: `getToken()` returns empty string on `keycloak.token === undefined`

**Location**: `store/auth.ts:52–54`  
**Issue**: `return keycloak.token ?? ''` returns an empty string if the token is not available
after `updateToken(30)`. Any API call with an empty bearer token will get a 401 from the
backend, which triggers another `initialize()` call — a potential loop.  
**Required action**: Throw an error if `keycloak.token` is falsy after `updateToken(30)`:

```typescript
async getToken() {
  await keycloak.updateToken(30)
  if (!keycloak.token) throw new Error('No token available')
  return keycloak.token
}
```

**Evidence**: auth-adapter contract C-AUTH-02 (invalid token → 401); Axios interceptor logic.

---

#### Minor: `VITE_KEYCLOAK_CLIENT_ID` env var name mismatch between infra and task spec

**Location**: `infra/.env.example:215,218` vs `services/*/frontend/.env.example:3` and `keycloak.ts:6`  
**Issue**: `infra/.env.example` uses `VITE_UIM_CLIENT_ID` / `VITE_TM_CLIENT_ID` (from T035/T036 task spec), but `keycloak.ts` reads `VITE_KEYCLOAK_CLIENT_ID`, and each per-frontend `.env.example` correctly uses `VITE_KEYCLOAK_CLIENT_ID`. The infra example is inconsistent with the actual code.  
**Impact**: Developers relying solely on `infra/.env.example` to configure Vite builds will
have the wrong variable name. Per-frontend `.env.example` is correct — runtime is unaffected.  
**Required action**: Update `infra/.env.example` to document that each frontend uses
`VITE_KEYCLOAK_CLIENT_ID` (not `VITE_UIM_CLIENT_ID` / `VITE_TM_CLIENT_ID`), or add a comment
pointing to the per-frontend `.env.example` files. (Tracked in Phase 1 review as R1-02.)

---

### Nits

#### Nit: `LoadingScreen` spinner is 32px wide (UIM) vs UX spec of 40px

**Location**: `services/user-input-manager/frontend/src/components/layout/LoadingScreen.tsx:18`  
**Issue**: Spinner rendered at `width: 32px` but UX guidance specifies 40px.  
**Required action**: Optional cosmetic fix — `width: 40, height: 40`.

#### Nit: `authStore` exported as `useAuthStore` — internal store file named `auth.ts` not `authStore.ts`

No functional impact; contract is met. File naming is a minor inconsistency with the spec task
description. No change required unless team convention mandates it.

---

### Security Checklist (from security-review-004-keycloak)

- [x] No `localStorage.setItem` / `sessionStorage.setItem` in `auth.ts` (AC-UX-012 / FIND-02 — verified by grep)
- [x] `pkceMethod: 'S256'` used in `keycloak.init()` (PKCE correct)
- [x] `getToken()` calls `keycloak.updateToken(30)` with ≥30s buffer
- [ ] **FAIL**: `logout()` does not clear in-memory state before redirect (AC-UX-013)
- [x] Admin console link guarded by `user?.isAdmin && kcConsoleUrl` (both frontends)
- [x] Admin link uses `rel="noreferrer noopener"` and `target="_blank"`
- [x] `keycloak.token` never written to storage (checked in keycloak.ts and auth.ts)

---

### Tests and Evidence Reviewed

- Confirmed no `localStorage`/`sessionStorage` usage via grep across all auth-related files.
- Confirmed `/login` route absent from `AppRoutes.tsx` (UIM) and `router.tsx` (TM).
- Confirmed `RequireAuth`/`ProtectedRoute` wrapper absent from both routers.
- Confirmed `user?.isAdmin && kcConsoleUrl &&` guard in both Sidebar (UIM) and Navbar (TM)
  desktop and mobile menus.
- Confirmed `keycloak-js: "25.0.6"` in both `package.json` files (within 25.x requirement).
- `VITE_KEYCLOAK_CLIENT_ID` used in both `keycloak.ts` files.

---

### Untested or Unverified Areas

- No unit test files reviewed yet (autotester owns T070–T078; tests may not exist yet).
- `authStore.test.ts` security tests (localStorage/sessionStorage spy) — per security review
  requirement, autotester must add these.
- TM `api/client.ts` was reviewed but TM-specific API types were not checked for `UserClaims`
  compatibility (Phase 4 concern).

---

### Required Follow-Up

| ID | Action | Owner | Priority |
|----|--------|-------|----------|
| R3-01 | Add error state + catch to `initialize()` + `AuthErrorScreen` component | frontend | **Blocker** |
| R3-02 | Fix `logout()` to clear Zustand state before redirect | frontend | **Blocker** |
| R3-03 | Fix `onTokenExpired` to call `keycloak.logout()` not `initialize()` | frontend | **Major** |
| R3-04 | Add `redirectUri` to `keycloak.logout()` call | frontend | Minor |
| R3-05 | Fix `getToken()` to throw on empty token | frontend | Minor |
| R3-06 | Fix `infra/.env.example` VITE client ID var name | devops | Minor (tracked R1-02) |
| R3-07 | Autotester to add localStorage/sessionStorage spy tests in authStore.test.ts | autotester | High (security) |
