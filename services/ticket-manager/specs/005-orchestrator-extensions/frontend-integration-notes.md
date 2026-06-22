# Frontend Integration Notes: Orchestrator Extensions (005)

**Feature**: `005-orchestrator-extensions`
**Author**: Frontend Developer agent
**Date**: 2026-06-21
**Scope**: Review of `contracts/openapi-orchestrator.yaml` for future UI integration readiness.
**No frontend changes in this release** — these notes target the *next* UI work that consumes these endpoints.

---

## 1. Response Shape / Naming Issues

### 1.1 Mixed-case `FsmStatus` enum
`FsmStatus` uses lowercase for all values except `BLOCKED` (uppercase). A UI rendering status badges or filter dropdowns must special-case `BLOCKED` vs the rest. Recommendation: either normalise to all-lowercase or all-SCREAMING_SNAKE in the enum and apply display labels separately in the UI layer.

### 1.2 Two pagination paradigms in the same API
The existing ticket list endpoint uses **offset pagination** (`page` / `page_size`). The new `/orchestrator/pending` endpoint uses **keyset cursor pagination** (`after_cursor` / `next_cursor`). A unified pagination component cannot serve both — the UI will need two separate implementations. Document this explicitly; do not try to abstract them into one hook.

### 1.3 `BatchFsmStatusResponse` is a map, not an array
`POST /tickets/batch-fsm-status` returns `additionalProperties` (a `Record<string, BatchFsmStatusEntry>`). React state and rendering code iterating over the result should use `Object.entries()`. React Query / SWR will not cache this (it's a POST) — callers must handle stale-data scenarios manually or wrap in a client-side cache keyed by ticket IDs.

### 1.4 Inconsistent path depth for audit endpoints
Most ticket-scoped endpoints use `/projects/{project_id}/tickets/{ticket_id}/…`. Audit endpoints break this: they use `/tickets/{ticket_id}/audit` (no project prefix). A UI API client layer will need separate path builders for audit vs. other ticket operations.

### 1.5 `event` in `AuditEventCreate` has no enum constraint
The `event` field accepts any string up to 50 chars (`ADVANCE`, `BLOCK`, `ASSIGN`, `WAIT`, etc.). A UI rendering an audit timeline must handle arbitrary unknown event type strings gracefully — do not switch/case on a fixed list without a fallback renderer.

---

## 2. Missing Fields for Dashboard Use

### 2.1 `TicketSummary` missing `override` / `override_reason`
`TicketSummary` (used by `PendingTicketsResponse`) does not include `override` or `override_reason` — those fields live in `FsmFields`. An admin dashboard showing pending tickets would want to surface which tickets have an active gate override. The `/full` and FSM PATCH responses include these via `allOf FsmFields`, but the pending list does not.

**Recommendation**: Add `override: boolean` and `override_reason: string | null` to `TicketSummary`, or create a separate `TicketPendingItem` schema that explicitly includes all fields a polling dashboard needs.

### 2.2 `TicketSummary` missing assignee info
`TicketSummary` carries `assigned_agent` (orchestrator assignment) but not a human `assignee_id`. A triage dashboard needs both to show the full ownership picture.

### 2.3 `TicketSummary` missing priority signals
The full ticket model includes `urgent`, `blocker`, `bugfix` boolean flags and `ticket_spec`. These are absent from `TicketSummary`. A triage or pending-ticket view would benefit from these for visual prioritisation.

### 2.4 `AuditLogResponse` has no pagination
`GET /tickets/{ticket_id}/audit` returns all events with no `limit`/cursor. For tickets with many automated cycles this could produce large payloads and slow UI renders. Recommend adding `limit` + `before_cursor` pagination before exposing in a UI, or at minimum a server-side cap (e.g. 500 events max).

### 2.5 `BatchFsmStatusEntry` missing `project_id`
`BatchFsmStatusEntry` contains `fsm_status`, `title`, and `blocked_reason` but no `project_id`. A UI calling batch status with IDs spanning multiple projects cannot construct per-ticket deep-links without a follow-up lookup. Recommend adding `project_id` to `BatchFsmStatusEntry`.

---

## 3. Confirmation: `include_fsm=true` Sufficiency for List View (US8)

**Finding**: `include_fsm=true` on `GET /projects/{project_id}/tickets` is **sufficient** for a per-project ticket list view showing FSM state, with one caveat.

**What it provides**: `fsm_status`, `blocked_reason`, `brainstorm_round`, `assigned_agent`, `last_orchestrator_run`, `dependencies`, `follow_ups` — enough to render an FSM state column, a BLOCKED badge with reason tooltip, and a "last run" timestamp.

**Caveat**: `override` and `override_reason` are NOT part of `TicketSummary`; they only appear in `FsmFields` (used in `/full` and FSM PATCH responses). A ticket list view will not show override status even with `include_fsm=true` unless the backend explicitly includes those fields in the `TicketSummary` schema (see §2.1 above).

**Cross-project view**: For a cross-project FSM dashboard (e.g. showing all pending tickets in the whole system), the `/orchestrator/pending` endpoint is required — the list extension is per-project only.

---

## 4. Positive Notes (Integration Strengths)

- `fsm_status` uses consistent `snake_case` throughout — straightforward `camelCase` transformation in a TypeScript client.
- Keyset pagination cursor is opaque (base64 JSON) — the UI never needs to parse or construct it.
- Tag delta endpoint (`POST /tags/delta`) is idempotent — safe to retry from a UI without risk of duplicate tags.
- FSM PATCH is partial (`exclude_unset`) — UI components can send only the field they change rather than the full FSM object.
- All new endpoints use the same Bearer JWT auth as the rest of the API — no new auth integration work required.

---

## 5. Summary Table

| Finding | Severity for UI | Actionable Now? |
|---|---|---|
| Mixed-case `BLOCKED` in `FsmStatus` enum | Low | Apply display label mapping in UI layer |
| Two pagination paradigms | Medium | Implement two separate pagination hooks; do not abstract |
| POST batch status not cached by default | Low | Wrap in client-side cache or use SWR `mutate` pattern |
| Audit endpoint path inconsistency | Low | Use separate path builder for audit routes |
| `override` missing from `TicketSummary` | Medium | Request backend schema addition before admin UI build |
| No `assignee_id` in `TicketSummary` | Low | Accept limitation or request schema addition |
| `AuditLogResponse` unbounded | Medium | Request pagination before exposing in UI |
| `BatchFsmStatusEntry` missing `project_id` | Low | Request addition if multi-project UI needed |
| `include_fsm=true` sufficient for list view | ✅ Good | No action needed (with caveat on `override`) |
