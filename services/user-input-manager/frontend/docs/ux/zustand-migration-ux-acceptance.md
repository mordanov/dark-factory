# UX Acceptance Criteria — UIM Zustand Auth Migration (US3)

**Feature**: 001-monorepo-unification — Stream 4  
**Scope**: user-input-manager frontend only  
**Design note**: This is an infrastructure migration. No new screens, dialogs, or loading states are introduced. All UX outcomes below define **behaviour parity** — the user experience must be identical before and after migration.

---

## 1. Login Flow

### AC-UX-01: Login succeeds and lands on /sessions
- **Given** the login form is shown at `/login`
- **When** the user submits valid credentials
- **Then** the user is redirected to `/sessions` (or the originally requested route if redirected from a protected route)
- **And** no access token appears in `localStorage` or `sessionStorage` under any key

### AC-UX-02: Login failure shows a user-readable error
- **Given** the login form is shown
- **When** the user submits wrong credentials (HTTP 401)
- **Then** the error message `auth.invalid_credentials` (from i18n) appears in the `.error-banner` element
- **And** the form remains interactive (no page reload, no navigation)
- **And** no technical error code or stack trace is exposed

### AC-UX-03: Disabled account shows correct error
- **Given** the login form is shown
- **When** the server returns HTTP 403
- **Then** the error message `auth.account_disabled` (from i18n) appears in the `.error-banner` element

### AC-UX-04: Network error during login shows generic error
- **Given** the login form is shown
- **When** the network request fails (no response, or unexpected status)
- **Then** the fallback error message `common.error` (from i18n) appears in the `.error-banner` element

### AC-UX-05: Submit button shows loading state
- **Given** the login form is shown
- **When** the login request is in flight
- **Then** the submit button is `disabled` and renders the spinner + `auth.signing_in` text
- **And** the button returns to normal state after success or failure

---

## 2. Protected Route Behaviour

### AC-UX-06: Unauthenticated user is redirected to /login
- **Given** the user is not authenticated (no valid session)
- **When** the user navigates to any protected route (`/sessions`, `/queue`, `/admin`)
- **Then** they are redirected to `/login`
- **And** the original route is preserved in `location.state.from` so post-login redirect works

### AC-UX-07: Authenticated user reaches protected routes without re-login
- **Given** the user is authenticated (Zustand store has a valid `accessToken`)
- **When** the user navigates to `/sessions` or `/queue`
- **Then** the route renders correctly without a login redirect

### AC-UX-08: Admin-only route enforces admin check
- **Given** an authenticated user who is not an admin
- **When** the user navigates to `/admin`
- **Then** they are redirected to `/sessions` without exposing admin content

### AC-UX-09: Loading state prevents flash of unauthenticated content
- **Given** the app is restoring session state from a stored refresh token (`isRestoring: true`)
- **When** a protected route is visited during restoration
- **Then** a spinner is displayed and no navigation occurs until restoration completes

---

## 3. Session Restore After Page Refresh

### AC-UX-10: Valid refresh token restores session silently
- **Given** the user is logged in and the refresh token is stored in `sessionStorage` under key `rt`
- **When** the page is refreshed (F5 / hard reload)
- **Then** the app silently exchanges the refresh token for a new access token
- **And** the user lands on the same route they were on before refresh
- **And** no login prompt is shown

### AC-UX-11: Invalid/expired refresh token prompts login
- **Given** the user has a stored refresh token that is expired or invalid
- **When** the page is refreshed
- **Then** the token exchange fails, session is cleared, and the user is redirected to `/login`
- **And** no access token is left in `localStorage` or `sessionStorage`

### AC-UX-12: New tab does not inherit auth session
- **Given** the user is logged in (session stored in `sessionStorage`)
- **When** the user opens a new browser tab
- **Then** the new tab is NOT authenticated (sessionStorage is tab-isolated by browser design)
- **Note**: This is expected browser behaviour, not a regression.

---

## 4. Logout

### AC-UX-13: Logout clears all auth state
- **Given** the user is authenticated
- **When** the user clicks the logout button in the Sidebar
- **Then** `useAuthStore.logout()` is called, clearing `accessToken`, `currentUser`, and `refreshToken`
- **And** `sessionStorage` key `rt` is removed
- **And** the user is redirected to `/login`

### AC-UX-14: Logout with no redirect loop
- **Given** the user has just logged out and is on `/login`
- **When** no further action is taken
- **Then** the page stays on `/login` without redirecting again

---

## 5. Token Storage Security

### AC-UX-15: Access token never touches browser storage
- **Given** any point during a user session
- **When** `localStorage` and `sessionStorage` are inspected (DevTools → Application tab)
- **Then** no access token is present under any key in either storage
- **And** only the refresh token key `rt` appears in `sessionStorage`

### AC-UX-16: Logout removes refresh token from sessionStorage
- **Given** the user is logged in with `rt` key in `sessionStorage`
- **When** the user logs out
- **Then** `sessionStorage.getItem('rt')` returns `null`

---

## 6. Accessibility Baseline (Components Touched by Migration)

### AC-UX-17: Login form is keyboard-operable
- Tab order: email field → password field → submit button
- All fields and the submit button are reachable and activatable via keyboard alone
- Pressing Enter in either field submits the form

### AC-UX-18: Error message is linked to the form
- The `.error-banner` error message is visible and screen-reader accessible after a failed login
- No ARIA live region is required given the error appears inline in the form flow, but a role of `alert` is acceptable if added

### AC-UX-19: Form fields have visible labels
- The email and password inputs have matching `<label for="...">` elements
- The `htmlFor` values match input `id` attributes (`email`, `password`)

### AC-UX-20: Focus indicator is visible on all interactive elements
- Login inputs, submit button, sidebar nav buttons, and logout button all show a visible focus ring when keyboard-focused
- No interactive element uses `outline: none` without a custom visible replacement

---

## 7. Migration Verification Matrix

| Behaviour | Pre-migration (Context API) | Post-migration (Zustand) | Must match |
|-----------|----------------------------|--------------------------|------------|
| Login → redirect to /sessions | ✅ | Must ✅ | Yes |
| Login error message | ✅ (i18n key) | Must ✅ (same i18n key) | Yes |
| Protected route guard | ✅ RequireAuth | Must ✅ RequireAuth (same logic) | Yes |
| Admin route guard | ✅ RequireAdmin | Must ✅ RequireAdmin (same logic) | Yes |
| Loading spinner during restore | ✅ `loading` state | Must ✅ `isRestoring` state | Yes |
| Logout → /login redirect | ✅ | Must ✅ | Yes |
| access_token in localStorage | ⚠️ WAS stored | Must NOT be stored | Critical |
| refresh_token in localStorage | ⚠️ WAS stored | Must NOT be stored | Critical |
| refresh_token in sessionStorage | ❌ was in localStorage | Must be in sessionStorage as `rt` | Critical |
| No new loading states introduced | — | No new loading UX added | Required |
| No new dialogs or confirmations | — | No new modals added | Required |

---

## 8. Out of Scope

- New UI screens, dialogs, or loading indicators beyond what already exists
- Keycloak auth flow UX (stub only — NotImplementedError on backend)
- SSL/TLS or certbot UI flows
- Any change to the visual appearance of the login page or sidebar
- Any change to error message copy (i18n keys must remain unchanged)
