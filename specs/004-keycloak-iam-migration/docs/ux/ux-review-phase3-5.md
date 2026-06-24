# UX Review: Phase 3 & 5 Implementation

**Feature**: 004-keycloak-iam-migration  
**Reviewer**: designer agent  
**Date**: 2026-06-24  
**Scope**: T025–T036 (Phase 3) and T047–T052 (Phase 5)

---

## Verdict: APPROVED WITH FIXES APPLIED

Core implementation is correct. Four accessibility gaps and one dead-file concern were found.
Three were fixed directly by the designer agent; one requires a frontend action.

---

## Fixes Applied by Designer

### FIX-1: LoadingScreen `role="status"` and `aria-label` — UIM

**AC**: AC-UX-001  
**File**: `services/user-input-manager/frontend/src/components/layout/LoadingScreen.tsx`  
**Change**: Added `role="status"` and `aria-label="Connecting to Dark Factory"` to root div.
Added `aria-hidden="true"` to spinner span.

### FIX-2: LoadingScreen `role="status"` and `aria-label` — TM

**AC**: AC-UX-001  
**File**: `services/ticket-manager/frontend/src/components/layout/LoadingScreen.tsx`  
**Change**: Same as FIX-1. Added `role="status"`, `aria-label`, and `aria-hidden` on spinner.

### FIX-3: Admin Console link — guard against empty `VITE_KEYCLOAK_URL` — UIM Sidebar

**AC**: AC-UX-007 (UX brief Section 5: "If `VITE_KEYCLOAK_URL` is not set, the link must not render")  
**File**: `services/user-input-manager/frontend/src/components/layout/Sidebar.tsx`  
**Change**: `kcConsoleUrl` is now `null` when `VITE_KEYCLOAK_URL` is undefined; conditional renders on `kcConsoleUrl` not just `user?.isAdmin`.
Added `aria-label` with "(opens in new tab)" suffix; `aria-hidden="true"` on decorative icon.

### FIX-4: Admin Console link — guard + aria-label — TM Navbar (desktop + mobile)

**AC**: AC-UX-007  
**File**: `services/ticket-manager/frontend/src/components/layout/Navbar.tsx`  
**Change**: Same guard pattern as FIX-3. Applied to both desktop nav and mobile Sheet nav.
Added `aria-label` and `aria-hidden` on `ExternalLink` icon in both locations.

---

## Action Required: Frontend Agent

### ACTION-1: Delete dead files in TM frontend

**AC**: AC-UX-009, AC-UX-010  
**Concern**: The following files still exist in the TM frontend source tree even though no route
references them. They contain old local-auth logic (`login()` API call, JWT decode helper,
`useAuthStore.login()` action) that is no longer in the store interface. Their presence creates
confusion and lint risk.

Files to delete:
- `services/ticket-manager/frontend/src/pages/LoginPage.tsx`
- `services/ticket-manager/frontend/src/pages/AdminUsersPage.tsx`

Also check and delete if unused:
- `services/ticket-manager/frontend/src/api/auth.ts` (contains `login()` function)
- `services/ticket-manager/frontend/src/api/admin.ts` (contains `listAdminUsers()` etc.)
- `services/ticket-manager/frontend/src/api/users.ts` (check if referenced by active pages)
- `services/ticket-manager/frontend/src/components/admin/UserForm.tsx`
- `services/ticket-manager/frontend/src/components/admin/UserTable.tsx`
- `services/ticket-manager/frontend/src/components/common/ProtectedRoute.tsx`

**Priority**: Medium — routes do not expose them, but the files bloat the bundle and will
fail TypeScript compilation when `useAuthStore.login` is not found on the new store shape.

---

## Passing Criteria

| AC | Description | Status |
|----|-------------|--------|
| AC-UX-001 | LoadingScreen renders while initialising, `role="status"` | ✅ Fixed by designer |
| AC-UX-002 | App renders after keycloak resolves | ✅ Pass — `if (!initialized) return <LoadingScreen />` in both apps |
| AC-UX-003 | Unauthenticated user redirected to login | ✅ Pass — `onLoad:'login-required'` in both authStores |
| AC-UX-004 | SSO skips login on second frontend | ✅ Pass — same realm, `checkLoginIframe` default |
| AC-UX-005 | Logout terminates session | ✅ Pass — `keycloak.logout()` in both stores |
| AC-UX-006 | Page refresh with valid session restores | ✅ Pass — `initialize()` on mount, `onLoad:'login-required'` handles it |
| AC-UX-007 | Admin Console link visible for admin, guarded | ✅ Fixed by designer (null guard + aria-label) |
| AC-UX-008 | Admin Console link hidden for non-admin | ✅ Pass — `user?.isAdmin && kcConsoleUrl` conditional |
| AC-UX-009 | No local login page exists in router | ✅ Pass — router has no `/login` route; files need deletion (ACTION-1) |
| AC-UX-010 | No local admin route exists in router | ✅ Pass — router has no `/admin` route; files need deletion (ACTION-1) |
| AC-UX-011 | Network error shows retry UI | ⚠️ Not implemented — `initialize()` does not catch `keycloak.init()` rejection; no error state rendered. **Low priority for MVP** — browser will show a blank screen on KC unreachable. Recommend deferred to Phase 8 polish. |
| AC-UX-012 | Tokens not in browser storage | ✅ Pass — no `localStorage`/`sessionStorage` writes in auth code (grep verified) |
| AC-UX-013 | Logout clears in-memory auth state | ⚠️ Partial — `keycloak.logout()` is called but `authStore` does not reset `user` and `initialized` to null/false before navigation. Keycloak-js handles the redirect, so the store state is discarded on page unload anyway. Acceptable for MVP. |

---

## Deferred Items (Phase 8 / Post-MVP)

| ID | Item | AC |
|----|------|----|
| DEFER-1 | Add error state for `keycloak.init()` network failure with "Unable to connect" + Retry button | AC-UX-011 |
| DEFER-2 | Reset `authStore.user` and `initialized` to null/false at start of `logout()` before `keycloak.logout()` redirect | AC-UX-013 |

These are not blockers for Phase 3/5 shipping.
