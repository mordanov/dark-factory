# Security Review: Feature #004 — Frontend Design System (Tailwind + shadcn/ui)

**Date**: 2026-05-25
**Reviewer**: Security Architect Agent
**Branch**: `004-ui-design-system`
**Spec**: `specs/004-ui-design-system/`

---

## Scope Reviewed

- All spec documents: `plan.md`, `tasks.md`, `research.md`, `contracts/theming-integration.md`, `contracts/component-api.md`
- Existing source: `frontend/src/store/auth.ts`, `frontend/src/api/client.ts`, `frontend/src/api/auth.ts`, `frontend/src/components/common/ProtectedRoute.tsx`, `frontend/src/router.tsx`, `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/TicketDetailPage.tsx`, `frontend/src/main.tsx`, `frontend/src/types.ts`
- Review method: threat modeling (STRIDE), data flow analysis, trust boundary analysis, supply-chain assessment

---

## Decision

**APPROVED WITH INFORMATIONAL NOTES**

This is a pure frontend styling refactor. No authentication, authorization, API, or data-handling logic is changed. Security posture is unchanged. Three low-severity and two informational observations are documented below; none block implementation.

---

## Threat Model Summary

### Assets

| Asset | Sensitivity | Scope impact |
|---|---|---|
| JWT access token (in-memory Zustand store) | High | Unchanged — not touched by this feature |
| Refresh token (sessionStorage) | High | Unchanged — not touched by this feature |
| Theme preference (localStorage) | None | Read by new anti-FOSC script (T022) |
| User role/email (decoded from JWT) | Medium | Unchanged — client-side display only |

### Trust Boundaries

All trust boundaries are unchanged by this feature:
- Browser ↔ Backend API: JWT Bearer authentication, enforced server-side
- Client-side role checks (AdminRoute, Navbar admin link) are UI conveniences only; server enforces actual authorization

### New Attack Surface Introduced

| Item | What's new | Risk |
|---|---|---|
| Anti-FOSC inline script (T022) | Reads localStorage, sets `data-theme` and `.dark` class | Informational |
| 5 new npm dependency chains (Tailwind, shadcn, Framer Motion, Lucide, Radix) | Supply chain | Low |
| Framer Motion page/modal animations | DOM transforms/opacity only | None |
| `document.getElementById().textContent` ARIA announcer (T021) | Safe `.textContent` assignment | None |

---

## Findings

### Finding 1: Anti-FOSC Inline Script — Safe, with future CSP note
**Severity**: Low
**Task**: T022
**Description**: The inline script added to `index.html` reads `localStorage.getItem("theme")`, sets `document.documentElement.dataset.theme`, and toggles `classList.add("dark")`. The script does no `eval`, no `innerHTML`, no dynamic script injection. The DOM APIs used (`dataset`, `classList`) are safe — values are interpreted as attribute strings and class names, not HTML or code.

**Future concern**: Inline scripts are blocked by Content Security Policy (CSP) `default-src` or `script-src` directives without `'unsafe-inline'` or a nonce/hash. When a CSP is added to this application (a recommended future hardening), this script will require:
- A nonce: `<script nonce="...">` with matching CSP `script-src 'nonce-...'`, or
- A hash: `script-src 'sha256-...'` computed over the exact script content

**Required action**: None for this feature. Document this for when CSP is introduced.
**Recommendation for future CSP work**: Add the nonce or hash at CSP-implementation time. Consider extracting this to a small external JS file if nonce management adds complexity.

---

### Finding 2: Supply-Chain Risk from New Dependencies
**Severity**: Low
**Tasks**: T001, T006, T007, T008
**New packages**: `tailwindcss@3`, `postcss`, `autoprefixer`, `@radix-ui/*` (via shadcn/ui), `framer-motion@11`, `lucide-react`, `clsx`, `tailwind-merge`, `shadcn` CLI

**Assessment**: All packages are well-established:
- `tailwindcss`: ~12M weekly downloads, Tailwind Labs maintained
- `@radix-ui/*`: ~3-8M weekly downloads, Radix UI / WorkOS maintained
- `framer-motion`: ~6M weekly downloads, Framer maintained
- `lucide-react`: ~5M weekly downloads, community maintained
- `shadcn/ui`: CLI tool — generates **static code into the repo** (no runtime dependency); the CLI itself is only run during setup

Shadcn/ui is particularly noteworthy: the installed components are copied into `frontend/src/components/ui/` as plain TypeScript files. There is no runtime npm module for shadcn/ui primitives — only Radix UI is the runtime dependency.

**Required action**: Run `npm audit` from `frontend/` as part of T047 final verification. If high/critical vulnerabilities are found, assess and patch before release.

---

### Finding 3: Role-Based UI Gating Preserved Correctly
**Severity**: None (verification note)
**Tasks**: T014 (Navbar), T016 (ProtectedRoute)
**Description**: The existing `AdminRoute` pattern (router.tsx) redirects non-administrators at the client side. `ProtectedRoute` guards all authenticated routes. T014 adds admin nav link gating `role !== "administrator"` in `Navbar`. These are UI conveniences only — the backend enforces real RBAC on every API request.

**Required**: The Navbar admin link must use the **same condition** as the existing `AdminRoute`: `currentUser?.role !== "administrator"`. Verify this in the T014 implementation.
**Status**: Specified correctly in tasks.md T014. Mark as verified during code review.

---

### Finding 4: JWT Client-Side Parsing — Existing Pattern, Acceptable
**Severity**: Informational
**Affected files**: `LoginPage.tsx`, `main.tsx` (both unchanged by this feature)
**Description**: `parseJwtPayload` decodes the JWT payload client-side using `atob`. The decoded values (`sub`, `email`, `role`) are used for client-side display and routing convenience only. No security decision relies solely on the client-decoded payload without server-side enforcement.

This is an existing pattern and is not changed by this feature. It is acceptable for a browser SPA — the server validates every API request with the actual signed JWT.

**Required action**: None. No change needed.

---

### Finding 5: Window.confirm() Replace with Dialog — Security Improvement
**Severity**: Informational (improvement)
**Task**: T038
**Description**: The current `handleDelete` in `TicketDetailPage.tsx` uses `window.confirm()` for delete confirmation (line 87). The plan replaces this with a shadcn `<Dialog>` component. This is a security improvement: native `window.confirm()` dialogs can be suppressed in some browser contexts and have inconsistent behavior. The Dialog replacement:
- Is always visible and styled consistently
- Requires explicit confirm/cancel interaction
- Is not suppressible by browser settings

No action required — this is a positive change.

---

### Finding 6: ThemeSwitcher Swatch Color Prop — Safe Exception
**Severity**: None
**Task**: T023
**Description**: The plan permits one `style` prop exception: `style={{ background: swatch }}` in `ThemeSwitcher`. The `swatch` value is derived from predefined theme color objects in the application code (not user input). This is a data-driven presentational value and introduces no XSS or injection risk.

**Required**: Confirm during code review that the swatch value comes only from the static theme configuration, not from any API response or URL parameter.

---

## Security Requirements for Implementation

The following requirements apply to this feature's implementation agents:

### Must-Have (block completion if violated)

1. **No new auth logic**: Confirm zero changes to `api/auth.ts`, `store/auth.ts`, JWT parsing functions, or token storage.
2. **Admin route preserved**: Verify `AdminRoute` and ProtectedRoute auth guard logic is byte-for-byte preserved during refactor.
3. **No sensitive data in new components**: Confirm no tokens, passwords, or PII appear in any new component's props, state names, or i18n keys beyond what already existed.
4. **`textContent` not `innerHTML`**: The ARIA announcer (T021) must use `.textContent` assignment, never `.innerHTML`.
5. **No eval or dynamic script creation**: Framer Motion and Lucide usage must not involve `eval`, `Function()`, or dynamic `<script>` injection.

### Recommended (track and address)

6. **`npm audit` in T047**: Run and review before final sign-off.
7. **Nonce/hash noted for future CSP**: Document the anti-FOSC script (T022) as requiring a nonce or hash when CSP is added.

---

## Security Tests Required

The following must be verified in T047 (quickstart verification):

| Test | How to verify |
|---|---|
| Admin route still enforced | Log in as `role: "user"`, navigate to `/admin/users` → confirm redirect to `/projects` |
| Admin nav link hidden for non-admin | Log in as regular user → confirm no "Admin" link in Navbar |
| Logout clears session | Logout → confirm `sessionStorage` cleared, `/projects` redirects to `/login` |
| No credentials in DOM | Inspect page source → confirm no tokens, passwords in rendered HTML |
| No `innerHTML` in announcer | Grep: `grep -rn "innerHTML" frontend/src/components/layout/AppShell.tsx` → zero results |
| npm audit clean | `npm audit --audit-level=high` from `frontend/` → zero high/critical |

---

## Residual Risks

| # | Risk | Severity | Owner | Due |
|---|---|---|---|---|
| R1 | Inline anti-FOSC script incompatible with CSP | Low | DevOps (when CSP added) | At CSP implementation |
| R2 | New npm dependency chain untested for zero-days | Low | DevOps | Continuous (npm audit in CI) |

---

## Follow-Up Items

1. **For DevOps**: When adding CSP headers in future, add nonce or hash for the anti-FOSC inline script in `index.html` (T022). Document this as a known CSP touch-point.
2. **For Code Reviewer**: Verify admin route gating condition is identical before/after refactor. Verify swatch color source is static.
3. **For Autotester**: Include admin route redirect test and logout-clears-session test in the test suite.

---

## Constitution Principle X Verification

> **X. Security and Privacy Baseline**: No auth, credentials, or data handling changes.

Confirmed: Feature #004 makes zero changes to:
- Authentication flow or token handling
- Authorization checks (backend enforced)
- Data storage patterns (localStorage for theme, sessionStorage for refresh token — both existing)
- API endpoints or request/response shapes
- User PII handling

**Principle X: PASS**
