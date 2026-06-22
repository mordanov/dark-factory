# Security Review Result: UIM Zustand Token Migration (T043–T050)

**Date**: 2026-06-22  
**Reviewer**: security-architect agent  
**Files reviewed**: `services/user-input-manager/frontend/src/`  
**Checklist applied**: zustand-migration-review-checklist.md

---

### Decision

**APPROVED**

---

### Blockers

None.

---

### Findings

All 20 checklist items (Z1–Z20) pass.

**Z1–Z3 (access_token storage sweep)**  
`grep -rn "localStorage\|sessionStorage" src/` returns:
- `i18n/i18n.ts:15–16` — `localStorage` for i18n language preference only. Not a token. **Not a finding.**
- `store/auth.ts:17,27,41` — `sessionStorage` used exclusively for `RT_KEY = 'rt'` (refresh token). No `access_token` key. **PASS.**
- Zero results for `localStorage.setItem('access_token', ...)` or `sessionStorage.setItem('access_token', ...)`. **PASS.**

**Z4–Z5 (current_user/user object storage)**  
No `localStorage.setItem('current_user', ...)` or `localStorage.getItem('current_user')` anywhere. User object held in Zustand memory state only. **PASS.**

**Z6 (refresh token in sessionStorage only)**  
`store/auth.ts` uses `const RT_KEY = 'rt'`; `sessionStorage.setItem(RT_KEY, refreshToken)` on login; `sessionStorage.removeItem(RT_KEY)` on logout. No `localStorage` for refresh token. **PASS.**

**Z7–Z11 (Zustand store correctness)**  
- No `persist` middleware. `accessToken` initialises to `null`. **PASS.**
- `logout()` clears `accessToken: null`, `refreshToken: null`, `currentUser: null`, calls `sessionStorage.removeItem(RT_KEY)`. **PASS.**
- `login()` saves refreshToken to `sessionStorage` only; sets `accessToken` in memory state only. **PASS.**
- `isRestoring` initialised to `storedRefreshToken !== null`; cleared to `false` in `login()`, `setRestored()`, `logout()`. **PASS.**

**Z12–Z16 (component updates)**  
- `api/client.ts`: interceptor reads `useAuthStore.getState().accessToken`. No localStorage. **PASS.**
- `components/auth/LoginPage.tsx`: calls `login(data.access_token, data.refresh_token, partialUser)`. No storage write. **PASS.**
- `App.tsx`: `AuthRestorer` reads `refreshToken` from store (initialised from `sessionStorage`), calls `/auth/refresh`, calls `setAccessToken()`. No localStorage. **PASS.**
- `context/` directory absent. **PASS Z17.**
- `api/orchestrator.ts` also reads from `useAuthStore.getState().accessToken`. **PASS.**

**Z18–Z20 (sweep verification)**  
- Zero `AuthContext`, `useAuth()`, `localStorage.*token`, `sessionStorage.*access_token` results across entire `src/`. **PASS.**
- Confirmed by designer's AC-UX-15 verification. **PASS.**

---

### Security Tests Status

| Test | Result |
|---|---|
| ST-06: No `access_token` in `localStorage` after login | **PASS** (no write path exists) |
| ST-07: No `access_token` in `sessionStorage` after login | **PASS** (no write path exists) |
| ST-08: Logout clears store and `sessionStorage["rt"]` | **PASS** (auth.ts:41–42) |

SC-006 (no access token in browser storage) is satisfied by this implementation.

---

### Residual Risks

None for this component.

**Cross-cutting note (documented in threat model)**: Shared `JWT_SECRET_KEY` between `user-input-manager` and `orchestrator` in the test compose is intentional architecture (orchestrator validates UIM-issued tokens). Acknowledged by autotester. This coupling exists in the design regardless of the Zustand migration; it must be managed as a secrets rotation dependency in production operations.

---

### Follow-Up Items

None required before release.
