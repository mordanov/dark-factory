# UX Guidance: Keycloak Frontend Migration

**Feature**: 004-keycloak-iam-migration  
**Scope**: Phase 3 (T025–T036) and Phase 5 (T047–T052)  
**Author**: designer agent  
**Date**: 2026-06-24

---

## 1. Scope and Approach

This is an **infrastructure-invisible migration**. Users must not perceive any change in their
login experience except the removal of the local login form (replaced by Keycloak's hosted page).
Design work is limited to:

1. `LoadingScreen` component spec (T029, T030)
2. Auth error states and user-facing copy (displayed by Keycloak or caught by `authStore`)
3. SSO interaction flow (behaviour parity verification)
4. Admin console link in the Sidebar (T049, T050)
5. UX acceptance criteria for Autotester and Code Reviewer

No new navigation, layouts, or visual redesigns are in scope.

---

## 2. LoadingScreen Component (T029, T030)

### Purpose

Block application content while `keycloak.init()` is resolving. The user must never see
a partial render or unauthenticated content flash before the session is established.

### Behaviour Specification

| State | Trigger | Visual |
|-------|---------|--------|
| **Loading** | `initialized === false` after `App.tsx` mounts | Full-viewport centred spinner + message |
| **Ready** | `initialized === true` | Unmount LoadingScreen, render application routes |
| **Auth redirect** | Keycloak redirects to login page | Browser navigates away; LoadingScreen is irrelevant |

### Layout

```
┌─────────────────────────────────────┐
│                                     │
│                                     │
│          ◌  (spinner)               │
│    Connecting to Dark Factory…      │
│                                     │
│                                     │
└─────────────────────────────────────┘
```

- Background: match application dark theme (`#0f1117` or equivalent root background token)
- Spinner: 40px, brand accent colour, continuous rotation animation
- Text: `"Connecting to Dark Factory…"` — exact string, sentence-case, ellipsis included
- Font: same as application body text, 14–16px, muted colour (secondary text token)
- Centred vertically and horizontally via flexbox
- No other UI elements (no logo, no nav, no error copy)
- No timeout behaviour — the loading state resolves via `keycloak.init()` completing or the
  browser redirecting; do not add a manual timeout or retry button

### Accessibility

- Root element: `role="status"` `aria-label="Connecting to Dark Factory"`
- Spinner: `aria-hidden="true"` (decorative)
- Text node: visible to screen readers via the `role="status"` container
- No focus management required (no interactive elements)

---

## 3. Auth Error States and User-Facing Copy

These states are surfaced either by Keycloak's own hosted pages (login errors) or caught by
`authStore` / Axios interceptors (session expiry, network failure). In all cases, users must
see human-readable messages — no stack traces, API error codes, or HTTP status numbers.

### 3.1 Login Errors (Keycloak Hosted Page)

Keycloak handles wrong-credential errors natively on its hosted login page. No custom error
UI is required in the frontend applications for login failures.

**Validation**: Confirm Keycloak's default `dark-factory` realm displays an error message in
English on bad credentials (not a blank page or raw JSON). If Keycloak's default message is
not user-readable, a custom realm theme may be needed — flag to security-architect.

### 3.2 Session Expiry (Token Refresh Failed)

**When**: `keycloak.updateToken(30)` rejects because the refresh token has expired or the
account has been disabled.

**Required behaviour**: Call `keycloak.logout()` immediately. The user is redirected to the
Keycloak login page. No in-app error dialog is required — the redirect is the recovery path.

**Rationale**: Silent redirect is the correct pattern for expired sessions. An in-app modal
adds friction with no benefit; the user cannot recover without re-authenticating.

**`onTokenExpired` implementation constraint** (keycloak-js 25.x):
`keycloak.init()` must be called exactly once per page load. The `onTokenExpired` handler must
NOT call `initialize()` — doing so triggers a double-init error in keycloak-js 25.x. The
correct handler is:

```ts
keycloak.onTokenExpired = () => {
  keycloak.updateToken(30).catch(() => {
    keycloak.logout()
  })
}
```

This attempts a silent token refresh; on failure (session gone, account disabled) it redirects
to login. `initialize()` is not called again.

### 3.3 Network Error During Auth Init

**When**: `keycloak.init()` fails due to network unavailability (Keycloak unreachable).

**Required behaviour**:
1. Unmount `LoadingScreen`
2. Display a full-viewport error message:
   - Heading: `"Unable to connect"`
   - Body: `"Dark Factory could not reach the authentication server. Please check your network connection and try again."`
   - Action: `"Retry"` button — calls `initialize()` again
3. Do not expose Keycloak URL, realm name, or error object to the user

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

**Accessibility**:
- Container: `role="alert"` (announced immediately by screen readers)
- Heading: `<h1>` or `role="heading" aria-level="1"`
- Retry button: focusable, keyboard-activatable (`Enter`/`Space`)
- On render: move focus to the heading or the Retry button

### 3.4 API 401 Response Mid-Session

**When**: An API call returns 401 after the session appeared valid.

**Required behaviour**: Axios response interceptor calls `await initialize()` (which calls
`keycloak.init()` or `keycloak.updateToken()`). If recovery succeeds, the interceptor retries
the original request transparently. If recovery fails, redirect to login via `keycloak.logout()`.

**User-visible impact**: None on successful retry. On failure, the user is redirected to login
without an in-app error message.

---

## 4. SSO Interaction Flow (Behaviour Parity)

These are the behavioural contracts the frontend must maintain after migration.
All were in place before migration; this section documents them for Autotester verification.

### 4.1 Unauthenticated Access

| Step | Expected Behaviour |
|------|--------------------|
| User opens any protected route | `LoadingScreen` renders; `keycloak.init({onLoad:'login-required'})` fires |
| Keycloak session absent | Browser redirects to Keycloak login page |
| User authenticates | Keycloak redirects back to the original URL (`redirectUri`) |
| App resumes | `initialized` becomes `true`; `LoadingScreen` unmounts; user lands on requested route |

### 4.2 SSO Across Both Frontends

| Step | Expected Behaviour |
|------|--------------------|
| User logs in via UIM frontend | Keycloak session cookie set for `dark-factory` realm |
| User opens TM frontend | `keycloak.init()` detects existing session (Keycloak SSO) |
| Result | No login prompt; user lands directly in TM app |

**Implementation note for frontend agent**: Both apps must use the same Keycloak realm and
configure `keycloak.init()` with `checkLoginIframe: true` (default) so the session check works
cross-origin. Do not set `checkLoginIframe: false` without flagging to the team.

### 4.3 Logout

| Step | Expected Behaviour |
|------|--------------------|
| User clicks "Logout" | `useAuthStore.getState().logout()` called |
| `logout()` | Calls `keycloak.logout()` with `redirectUri` pointing to the app root |
| Result | Keycloak session destroyed; user redirected to Keycloak login page |
| Subsequent navigation | Any protected route triggers login redirect again |

### 4.4 Page Refresh with Valid Session

| Step | Expected Behaviour |
|------|--------------------|
| User refreshes page | `App.tsx` re-mounts; `initialize()` called in `useEffect` |
| Keycloak session still valid | `keycloak.init()` resolves with authenticated session |
| Result | `LoadingScreen` clears; user stays on current route; no login prompt |

### 4.5 Page Refresh with Expired Session

| Step | Expected Behaviour |
|------|--------------------|
| User refreshes page | `App.tsx` re-mounts; `initialize()` called |
| Keycloak session expired | `keycloak.init({onLoad:'login-required'})` redirects to login |
| Result | User sees Keycloak login page |

---

## 5. Admin Console Link (T049, T050)

### Placement

In the Sidebar (or equivalent navigation component), add a conditional link after the existing
nav items:

- **Visible when**: `user?.isAdmin === true`
- **Hidden when**: `user?.isAdmin === false` or `user === null`
- **Label**: `"Admin Console"`
- **Destination**: `${VITE_KEYCLOAK_URL}/admin/dark-factory/console`
- **Target**: `target="_blank" rel="noopener noreferrer"`

### Behaviour

- The link opens the Keycloak Admin Console in a new tab
- No confirmation dialog before opening
- No in-app admin management screens remain — the link is the only admin entry point
- If `VITE_KEYCLOAK_URL` is not set, the link must not render (guard against empty `href`)

### Accessibility

- Link must be keyboard-focusable and activatable with `Enter`
- Include `aria-label="Open Admin Console (opens in new tab)"` or equivalent visible indicator
  that the link opens a new tab (e.g., an icon with accessible label)
- Focus indicator must be visible (at least 2px outline, contrast ≥ 3:1 against background)

### Logout Button

Replace the existing logout handler with `useAuthStore.getState().logout()`. No visual change
to the logout control is required.

---

## 6. Removed Routes and Navigation

### Routes to Remove (T047, T048)

| Route | Current Purpose | After Migration |
|-------|----------------|-----------------|
| `/login` | Local login form | Delete — Keycloak handles login via redirect |
| `/admin` | Local user management | Delete — replaced by Keycloak Admin Console link |

### `RequireAuth` Wrapper

Remove from AppRoutes. `keycloak.init({onLoad:'login-required'})` already enforces
authentication at the application entry point. A separate `RequireAuth` higher-order component
is redundant and may conflict with the Keycloak init flow.

### LoginPage Component (T051)

Delete `LoginPage.tsx`. Confirm no other component imports it before deletion.

---

## 7. Accessibility Baseline (All Touched Components)

Applies to `LoadingScreen`, the `authStore`-driven auth-error state, the Sidebar logout
button, and the Admin Console link.

| Requirement | Standard |
|-------------|---------|
| Keyboard operability | All interactive elements reachable and activatable via keyboard (`Tab`, `Enter`, `Space`) |
| Focus indicator | Visible on all focusable elements; ≥ 2px outline; contrast ratio ≥ 3:1 (WCAG 2.1 SC 1.4.11) |
| Screen reader labels | `aria-label` or visible text label on all controls; no icon-only buttons without accessible name |
| Error announcement | Auth error container uses `role="alert"` for immediate SR announcement |
| Loading announcement | LoadingScreen uses `role="status"` for polite SR announcement |
| Colour independence | No state communicated by colour alone (spinner is paired with text) |
| Focus management | On auth-error render: move focus to heading or primary action |

---

## 8. UX Acceptance Criteria

These are testable conditions that Autotester and Code Reviewer can verify.

### AC-UX-001: LoadingScreen renders while keycloak is initialising

**Given** the app mounts  
**When** `initialized === false` in `authStore`  
**Then** `LoadingScreen` is rendered and application routes are not visible  
**And** the screen contains the text "Connecting to Dark Factory…"  
**And** the root element has `role="status"`

### AC-UX-002: Application content renders after keycloak resolves

**Given** `keycloak.init()` resolves successfully  
**When** `initialized` transitions to `true`  
**Then** `LoadingScreen` unmounts  
**And** the application routes render  
**And** no login form is rendered in the application

### AC-UX-003: Unauthenticated user is redirected to login

**Given** no valid Keycloak session exists  
**When** the app initialises (`keycloak.init({onLoad:'login-required'})`)  
**Then** the browser is redirected to the Keycloak login page  
**And** the application content is never displayed to the unauthenticated user

### AC-UX-004: SSO — second frontend skips login

**Given** a user is authenticated in one Dark Factory frontend  
**When** they open the other frontend  
**Then** `keycloak.init()` detects the existing session  
**And** the user is not prompted to log in again  
**And** `LoadingScreen` resolves to application content without a login redirect

### AC-UX-005: Logout terminates session and redirects

**Given** a user is authenticated  
**When** they trigger the Logout action  
**Then** `keycloak.logout()` is called  
**And** the browser is redirected to the Keycloak login page  
**And** navigating back to the app root triggers a new login prompt

### AC-UX-006: Page refresh with valid session restores without login

**Given** a user has a valid Keycloak session  
**When** they refresh the page  
**Then** `LoadingScreen` renders briefly  
**And** resolves to the application content without a login redirect  
**And** `authStore.user` is populated with the same identity as before refresh

### AC-UX-007: Admin Console link visible for administrator role

**Given** a user with the `administrator` realm role is logged in  
**When** the Sidebar renders  
**Then** a link labelled "Admin Console" is visible  
**And** clicking it opens the Keycloak Admin Console in a new tab  
**And** the link is keyboard-focusable with a visible focus indicator

### AC-UX-008: Admin Console link hidden for non-admin users

**Given** a user without the `administrator` role is logged in  
**When** the Sidebar renders  
**Then** no "Admin Console" link is present in the DOM

### AC-UX-009: No local login page exists

**Given** the frontend is loaded  
**When** the user navigates to `/login`  
**Then** no login form is rendered  
**And** the route either redirects to the app root or returns a 404 navigation state

### AC-UX-010: No local admin route exists

**Given** the frontend is loaded  
**When** the user navigates to `/admin`  
**Then** no user management interface is rendered  
**And** the route does not exist in the application router

### AC-UX-011: Network error during auth init shows retry UI

**Given** Keycloak is unreachable when the app mounts  
**When** `keycloak.init()` rejects  
**Then** the `LoadingScreen` is replaced by an error state  
**And** the error contains the heading "Unable to connect"  
**And** a "Retry" button is present and keyboard-activatable  
**And** no Keycloak URL, realm, or technical error detail is displayed to the user  
**And** the error container has `role="alert"`

### AC-UX-012: Access tokens not in browser storage

**Given** the user is authenticated  
**When** browser localStorage, sessionStorage, and cookies are inspected  
**Then** no access token or refresh token value is present in any browser storage  
**And** tokens are held in memory via the Zustand `authStore` / keycloak-js internal state

### AC-UX-013: Logout clears in-memory auth state

**Given** a user is authenticated (`authStore.user` is non-null)  
**When** `logout()` is called  
**Then** `authStore.user` becomes `null`  
**And** `authStore.initialized` resets to `false`

---

## 9. Out of Scope

- Custom Keycloak login page themes (default Keycloak theme is acceptable)
- MFA prompt UX
- Password reset flow UI within the application (handled entirely by Keycloak)
- Mobile-specific layout changes
- Any new screens beyond LoadingScreen and the auth-error state
- Chart, form, or table component changes
