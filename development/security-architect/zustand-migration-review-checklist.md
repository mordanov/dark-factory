# Security Review Checklist: UIM Zustand Token Migration (T043–T050)

**Feature**: 001-monorepo-unification  
**Date**: 2026-06-22  
**Reviewer**: security-architect agent  
**Applies to**: frontend agent implementing T043–T050  
**Reference**: spec.md US3, plan.md R2, threat-model.md

---

## Critical: Token Storage (Blocker-level)

- [ ] **Z1** — `localStorage.setItem('access_token', ...)` is absent from ALL files in `services/user-input-manager/frontend/src/`. Use `grep -r "localStorage.*access_token\|setItem.*access_token" src/` to verify.
- [ ] **Z2** — `localStorage.getItem('access_token')` is absent from ALL files. Axios interceptor reads `useAuthStore.getState().accessToken` only.
- [ ] **Z3** — `sessionStorage.setItem('access_token', ...)` is absent from ALL files. Access token MUST NOT be in sessionStorage either.
- [ ] **Z4** — `localStorage.setItem('current_user', ...)` is absent. User object MUST NOT be persisted to localStorage.
- [ ] **Z5** — `localStorage.getItem('current_user')` is absent. User object is only in Zustand memory state.
- [ ] **Z6** — Refresh token is stored ONLY in `sessionStorage` under key `"rt"`. No other key, no `localStorage`.

## Zustand Store Correctness (High)

- [ ] **Z7** — `auth.ts` Zustand store holds `accessToken` in memory state only — no `persist` middleware targeting localStorage.
- [ ] **Z8** — `auth.ts` `logout()` action: clears `accessToken` to `null`, clears `currentUser` to `null`, calls `sessionStorage.removeItem("rt")`.
- [ ] **Z9** — `auth.ts` `login()` action: sets `accessToken` in memory, saves `refreshToken` to `sessionStorage.setItem("rt", ...)` only.
- [ ] **Z10** — `auth.ts` mirrors the `ticket-manager` store pattern. No custom persistence or storage adapter beyond `sessionStorage` for refresh token.
- [ ] **Z11** — `isRestoring` state correctly set to `false` after session restore completes (prevents flicker/redirect loops).

## Component Updates (Medium)

- [ ] **Z12** — `LoginPage.tsx`: calls `useAuthStore().login(...)` — no direct localStorage writes anywhere in the login flow.
- [ ] **Z13** — `App.tsx`: session restore reads `sessionStorage.getItem("rt")`, calls refresh endpoint, calls `store.setAccessToken()`. Does NOT read from localStorage.
- [ ] **Z14** — `AppRoutes.tsx`: uses `useAuthStore()` for `user` and `isRestoring`/`loading` — no `useAuth()` or AuthContext import remaining.
- [ ] **Z15** — `Sidebar.tsx`: uses `useAuthStore()` for user display and logout — no `useAuth()` or AuthContext import remaining.
- [ ] **Z16** — `client.ts` axios interceptor: reads token from `useAuthStore.getState().accessToken` — no localStorage read.
- [ ] **Z17** — `AuthContext.tsx` is deleted. No import of it anywhere in the codebase remains.

## Sweep Verification (Blocker-level)

- [ ] **Z18** — Run `grep -r "AuthContext\|useAuth()\|localStorage.*token\|sessionStorage.*access_token" services/user-input-manager/frontend/src/` — zero results.
- [ ] **Z19** — Browser DevTools verification (or Playwright/Vitest equivalent): after login, `localStorage` contains no `access_token`, `current_user` key; `sessionStorage` contains no `access_token` key.
- [ ] **Z20** — After logout: `sessionStorage.getItem("rt")` returns null. `useAuthStore.getState().accessToken` returns null.

---

## Security Test Cases

| ST | Test | Pass Criteria |
|---|---|---|
| ST-06 | No `access_token` in `localStorage` after login | DevTools: Local Storage: no `access_token` key |
| ST-07 | No `access_token` in `sessionStorage` after login | DevTools: Session Storage: no `access_token` key |
| ST-08 | Logout clears Zustand store and sessionStorage refresh token | `accessToken` null; `sessionStorage["rt"]` null |
| ST-03-UIM | Protected route inaccessible after logout | Redirect to login page |
| ST-04-UIM | Session restores from `sessionStorage["rt"]` after page refresh | If refresh token valid: user remains logged in; if expired: redirect to login |

---

## Review Result Template

```
## Security Review Result: UIM Zustand Migration

### Decision
APPROVED | APPROVED WITH RISKS | CHANGES REQUIRED

### Blockers (Z1–Z6, Z18–Z19 failures)
### High Findings (Z7–Z11 failures)
### Medium Findings (Z12–Z17, Z20 failures)
### Security Tests Status (ST-06 through ST-08)
### Residual Risks
```
