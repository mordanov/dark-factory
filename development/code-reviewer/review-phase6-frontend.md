# Code Review: Phase 6 – Frontend (T026–T032)

**Reviewer**: Code Reviewer Agent
**Date**: 2026-06-23
**Feature**: `003-planning-agent`
**Scope**: T026 (`client.ts` planningApi), T027 (`planStore.ts`), T028 (`AgentConfigPanel.tsx`),
T029 (`PlanningModal.tsx`), T030 (`SessionDetailPage.tsx`), T031 (delete `ApproveModal.tsx`),
T032 (i18n `en.json`, `ru.json`)

---

## Code Review Result

### Decision

**APPROVED WITH COMMENTS**

SR-001 (XSS blocker) and SR-FRONTEND-01 (localStorage blocker) both pass. One Major bug
must be fixed before merge; two Minor gaps should be tracked.

---

### Scope Reviewed

- `services/user-input-manager/frontend/src/api/client.ts` — new `planningApi` + interfaces
- `services/user-input-manager/frontend/src/store/planStore.ts` — new Zustand store
- `services/user-input-manager/frontend/src/components/sessions/AgentConfigPanel.tsx` — new
- `services/user-input-manager/frontend/src/components/sessions/PlanningModal.tsx` — new
- `services/user-input-manager/frontend/src/components/sessions/SessionDetailPage.tsx` — modified
- `services/user-input-manager/frontend/src/i18n/locales/en.json` + `ru.json` — modified
- `services/user-input-manager/frontend/vite.config.ts` — modified (coverage scope)
- `D services/user-input-manager/frontend/src/components/sessions/ApproveModal.tsx` — deleted ✅

---

### Summary

The implementation is architecturally sound and functionally complete. All four modal states
are implemented in `PlanningModal.tsx`. `AgentConfigPanel.tsx` hides entirely when
`agentConfig` is null (US4 requirement). Both i18n locales have the full `planning` key set.
`ApproveModal.tsx` is correctly deleted. The two security blockers pass: no
`dangerouslySetInnerHTML` anywhere in new components; `planStore.ts` has zero localStorage or
sessionStorage references.

One Major bug was found in the success banner ticket count. Two Minor gaps were found:
unmounted-component poll leak in `triggerGeneration`, and new planning components absent from
coverage thresholds.

---

### Blockers

_None._

---

### Major Findings

#### Major: Success banner shows wrong ticket count (session field mismatch)

**Location**: `SessionDetailPage.tsx:145`

**Issue**:
```tsx
<span>{t('planning.tickets_created', { count: session.tm_ticket_id ? 1 : 0 })}</span>
```
`session.tm_ticket_id` is the old single-ticket field from the pre-planning flow (the Epic TM
ID written during the old approve flow). For a planning session this field is likely `null` or
holds only the epic ID, so the banner will always show **"0 tickets created"** or **"1 ticket
created"** regardless of the actual count.

**Impact**: Users see incorrect success state. The correct count should come from the plan's
`created_ticket_ids.length` but `Session` does not expose that field. This is a functional
defect visible on the happy path.

**Required action**: One of:
1. Fetch the plan via `planningApi.get(sessionId)` when `session.status === 'tickets_created'`
   and use `plan.created_ticket_ids?.length ?? 0` for the count in the success banner.
2. Or add `ticket_count: number | null` to the `Session` response from the backend (populated
   from `prompt_plans.created_ticket_ids` length at query time).

Option 1 can be implemented in frontend without a backend change.

---

### Minor / Nits

#### Minor: `triggerGeneration` poll loop has no unmount guard

**Location**: `planStore.ts:35–62`

**Issue**: `triggerGeneration` uses recursive async polling (`await new Promise(...); poll()`)
that runs without any cancellation mechanism. If the modal is closed while generation is in
flight (error path, navigating away), the recursive calls continue and call `set(...)` on the
store after the component has unmounted. React 18 suppresses the warning but the poll runs
until `maxAttempts` (120s) even after the user has left.

**Impact**: Wasted API calls, minor UX confusion if the user re-opens the modal before the
stale poll resolves. Not a correctness defect — Zustand state updates are safe — but
unnecessary background traffic.

**Recommended action**: Add an `AbortController` ref or a `_generationAborted` flag in the
store that `reset()` sets, and check it at each poll iteration.

#### Minor: New planning components excluded from coverage gate

**Location**: `vite.config.ts:24–34` (coverage `include`)

**Issue**: `src/store/**` includes `planStore.ts` but no tests exist for it. The comment
justifying the exclusion of session components refers to "legacy" code, but `PlanningModal.tsx`,
`AgentConfigPanel.tsx`, and `planStore.ts` are new. The frontend agent reported 85.4% coverage,
but if planStore is in scope with zero tests, that figure is only achievable because the
threshold enforces the listed paths only.

SAC-001 (XSS script-injection test) and SAC-006 (no localStorage in planStore) have no
automated test coverage.

**Recommended action**: Add:
1. `planStore.ts` unit test (T027 gap) — at minimum: test `triggerGeneration` happy path with
   mock `planningApi`, `confirmPlan`, `pollCreationStatus` stop-on-done.
2. `PlanningModal.test.tsx` — smoke render test for each state (generating/ready/confirming/done)
   and the XSS scenario (SAC-001: inject `<script>alert(1)</script>` as title, assert rendered
   as text node).

This is Minor because the reported pass rate and the visual component tests likely provide
reasonable confidence. But the spec's 80% gate and SAC-001/SAC-006 have no automated evidence.

#### Nit: `sessionsApi.approve` remains in `client.ts`

**Location**: `client.ts:212–215`

This is expected to be removed in T033 (Phase 7 — "remove old approve endpoint"). No action
needed for Phase 6.

---

### Security Requirements Verified

| SR | Requirement | Verdict |
|----|-------------|---------|
| SR-001 | No `dangerouslySetInnerHTML` for plan node content | ✅ PASS — all content via controlled `<input>`/`<textarea>` and React text nodes |
| SR-FRONTEND-01 | No localStorage/sessionStorage in `planStore.ts` | ✅ PASS — zero references. `auth.ts` uses `sessionStorage` for refresh token only (pre-existing, not access token) |
| SR-006 | `agent_config.agent_overrides` displayed as plain text | ✅ PASS — `{ov.override_text}` is a React text node in a `<td>` |

---

### Tests and Evidence Reviewed

- 48 tests passing (reported by frontend agent)
- Coverage 85.4% (reported) — but new planning files (`planStore.ts`, `PlanningModal.tsx`,
  `AgentConfigPanel.tsx`) have no dedicated test files; full coverage of these files cannot
  be confirmed from the evidence provided
- `ApproveModal.test.tsx` deleted ✅ (avoids orphaned tests for removed component)
- TypeScript `strict: true` confirmed in `tsconfig.app.json`
- No `any` types in new planning files (`planStore.ts`, `PlanningModal.tsx`,
  `AgentConfigPanel.tsx`, `SessionDetailPage.tsx`); two pre-existing `any` uses in
  `extractError()` in `client.ts` are acceptable given the dynamic nature of axios error shapes

---

### Untested or Unverified Areas

- SAC-001: No automated XSS injection test (`<script>` in plan node title → confirm text render)
- SAC-006: No automated test asserting `planStore.ts` has no localStorage references (static
  analysis check passed manually; no test exists)
- `triggerGeneration` timeout / unmount cleanup path — no unit test for poll cancellation

---

### Required Follow-Up

1. **Must fix before merge**: `SessionDetailPage.tsx:145` — correct ticket count in success
   banner (see Major finding above)
2. **Should add**: `planStore.test.ts` with core action tests + SAC-001 smoke test in
   `PlanningModal.test.tsx`
3. **Phase 7 / T033**: Remove `sessionsApi.approve` from `client.ts` when old approve endpoint
   is removed from backend

---

### Acceptance Criteria Compliance

| AC | Requirement | Status |
|----|-------------|--------|
| US2-1 | Inline title edit saved and visible after reload | ✅ `EditableField` → `updatePlan` → API |
| US2-2 | Task delete removed from tree and persists | ✅ `withDeleteTask` → `updatePlan` |
| US2-3 | No tickets created before confirm response | ✅ `confirmPlan` returns 202; tickets created by background |
| US2-4 | Cancel closes modal, plan preserved | ✅ `onClose` without state reset |
| US1-1 | Non-dismissable generating overlay | ✅ `isGenerating` state drives overlay without close button |
| US1-2 | Browser-close and return shows existing plan | ✅ `fetchPlan` called on mount if `plan` already exists |
| US1-3 | Error banner with retry on generation failure | ✅ error state with `triggerGeneration` retry |
| US3-1 | Progress indicator with count | ✅ `creationProgress` drives "Creating tickets: X / N" |
| US3-2 | Success state with ticket count and TM link | ⚠️ TM link correct; count has bug (Major finding above) |
| US3-3 | Retry creates only missing tickets | ✅ Backend idempotency; frontend retry calls `confirmPlan` |
| US4-1 | Collapsible agent config panel, collapsed by default | ✅ `AgentConfigPanel` expanded=false default |
| US4-2 | Panel hidden when `agentConfig` is null | ✅ early return `if (!agentConfig) return null` |
