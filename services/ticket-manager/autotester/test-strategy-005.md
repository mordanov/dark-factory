# Test Strategy: Workflow Orchestrator Integration Extensions

**Branch**: `005-orchestrator-extensions` | **Date**: 2026-06-21
**Agent**: autotester
**Input**: spec.md, plan.md, data-model.md, contracts/openapi-orchestrator.yaml, tasks.md

---

## Scope

All eight user stories (US1–US8) plus cross-cutting concerns: authentication, audit log integrity, FSM atomicity, tag idempotency, pagination correctness, and performance smoke checks.

---

## Test Levels and Tools

| Level | Tool | Location |
|-------|------|----------|
| Backend contract | pytest + httpx AsyncClient | `backend/tests/contract/` |
| Backend integration | pytest + asyncpg (real DB) | `backend/tests/integration/` |

**No mocks for DB in integration tests** — integration tests hit a real PostgreSQL instance.

---

## Test Data Strategy

- UUID fixtures generated deterministically per test to ease debugging.
- Shared helpers: `_user(session)`, `_project(session, owner)`, `_ticket(session, project, creator)` — same pattern as existing integration tests.
- Database reset between integration tests via transaction rollback (`await session.rollback()` in conftest fixture).
- No production data. No sensitive data in fixtures.
- Service account simulated by setting `settings.ticket_manager_service_email` to match a test user's email.

---

## Task Coverage Map

### T011 — Contract Tests: Pending Endpoint (US1)
**File**: `backend/tests/contract/test_orchestrator.py`

Scenarios:
- `GET /api/v1/orchestrator/pending` returns only tickets where `fsm_status != done` AND (`last_orchestrator_run` IS NULL OR `updated_at > last_orchestrator_run`)
- Pagination: `limit=20` returns correct count; `next_cursor` enables retrieval of next page
- `project_id` filter: only tickets from that project returned
- Empty result: `total_pending: 0` and empty `tickets` list returned
- Response schema: all TicketPendingSummary fields present (including FSM fields and follow-up IDs)
- Unauthenticated → 401

### T014 — Contract Tests: FSM Patch (US2)
**File**: `backend/tests/contract/test_orchestrator.py`

Scenarios:
- `PATCH /api/v1/projects/{id}/tickets/{id}/fsm` updates only FSM fields; `title`/`description`/`status` unchanged
- Partial update: send only `fsm_status` → only `fsm_status` changes, other FSM fields remain null
- Service account (email matches `TICKET_MANAGER_SERVICE_EMAIL`) → 200
- Non-service-account, non-admin user → 403
- Unknown ticket ID → 404
- Response: full `TicketFsmResponse` with all FSM fields

### T017 — Contract Tests: Audit Log (US3)
**File**: `backend/tests/contract/test_orchestrator.py`

Scenarios:
- `POST /api/v1/tickets/{id}/audit` → 201 with audit entry ID
- `GET /api/v1/tickets/{id}/audit` → entries in chronological order (ascending `timestamp`)
- `GET /api/v1/tickets/{id}/audit` with no events → empty `entries` list
- `GET /api/v1/tickets/{id}/audit` for unknown ticket → 404
- Audit event immutability: no UPDATE/DELETE endpoint exposed

### T022 — Contract Tests: Override (US4)
**File**: `backend/tests/contract/test_orchestrator.py`

Scenarios:
- Admin `POST /api/v1/projects/{id}/tickets/{id}/override` with `override: true` → 200, `override=true` in response
- Non-admin user → 403
- Unknown ticket → 404
- `override_reason` stored correctly in response

### T025 — Contract Tests: Batch FSM Status (US5)
**File**: `backend/tests/contract/test_orchestrator.py`

Scenarios:
- `POST /api/v1/tickets/batch-fsm-status` with 3 known IDs → response map with 3 entries
- Unknown ID in batch → silently omitted from response map
- Empty `ticket_ids` array → empty `statuses` map (no error)
- BLOCKED ticket → `blocked_reason` included in entry

### T028 — Contract Tests: Tag Delta (US6)
**File**: `backend/tests/contract/test_tickets.py`

Scenarios:
- `POST /api/v1/projects/{id}/tickets/{id}/tags/delta` with `add: ["needs-estimation"]` → tag added, others unchanged
- `remove: ["needs-estimation"]` → tag removed, others unchanged
- `add` + `remove` in same call → both applied atomically
- Add tag that already exists → idempotent (200, no duplicate)
- Remove tag that doesn't exist → idempotent (200, no error)
- Unknown ticket → 404

### T031 — Contract Tests: Full Ticket (US7)
**File**: `backend/tests/contract/test_orchestrator.py`

Scenarios:
- `GET /api/v1/projects/{id}/tickets/{id}/full` returns all 8 FSM fields plus all native fields
- Ticket with no FSM fields set → FSM fields present with null/zero defaults
- Unknown ticket → 404

### T034 — Contract Tests: List with FSM (US8)
**File**: `backend/tests/contract/test_tickets.py`

Scenarios:
- `GET /api/v1/projects/{id}/tickets?include_fsm=true` → each ticket includes all FSM fields
- `GET /api/v1/projects/{id}/tickets` (no param) → response identical to pre-feature behavior (no FSM fields, no regression)
- FSM field values match those set via `PATCH /fsm`

### T037 — Integration Tests: FSM Service (US1, US2)
**File**: `backend/tests/integration/test_fsm_service.py`

Scenarios:
- `get_pending_tickets()` with real DB returns only tickets matching pending filter (fsm_status IS DISTINCT FROM 'done' AND last_orchestrator_run IS NULL OR updated_at > last_orchestrator_run)
- `get_pending_tickets()` excludes tickets with `fsm_status = done` and `updated_at <= last_orchestrator_run`
- `get_pending_tickets()` with `project_id` filter returns only matching project's tickets
- Cursor pagination: page 1 cursor → page 2 returns next batch, no overlap, no missing rows
- `patch_fsm_fields()` updates FSM fields only; native `title`/`description`/`status` unchanged after concurrent call
- `patch_fsm_fields()` on ticket from wrong project → 404
- FSM patch atomicity: `brainstorm_round` increment does not corrupt native fields

### T038 — Integration Tests: Audit Service (US3)
**File**: `backend/tests/integration/test_audit_service.py`

Scenarios:
- `create_audit_event()` + `get_audit_log()` round-trip: event retrieved with all fields intact
- Multiple events for same ticket → returned in ascending `timestamp` order
- `create_audit_event()` for non-existent ticket → raises 404
- `get_audit_log()` for non-existent ticket → raises 404
- `get_audit_log()` for ticket with no events → returns empty `entries` list
- Audit event immutability: no update or delete service functions exist

---

## Critical Risk Areas

### Auth (T014, T022)
- Service account check: email comparison against `TICKET_MANAGER_SERVICE_EMAIL` env var
- Missing env var: fail-closed — only admin role passes (FR-028)
- Override endpoint: admin-only (not service account)

### FSM Atomicity (T037)
- Concurrent FSM patch + human edit must not corrupt native fields
- `patch_fsm_fields` uses `exclude_unset` pattern — only provided fields updated

### Audit Immutability (T038)
- `orchestrator_audit_events` table: no UPDATE or DELETE operations exposed at any layer
- Chronological ordering enforced at DB query level (ORDER BY timestamp ASC)

### Pending Filter Correctness (T037, T011)
- False negatives: no pending ticket missed
- False positives: no already-processed ticket appears
- Edge case: `updated_at == last_orchestrator_run` (strict `>` comparison — ticket NOT pending)
- Duplicate IDs in batch request: deduplicated in response map

### Tag Idempotency (T028)
- Add existing tag: no duplicate, no error
- Remove absent tag: no error, tags unchanged

### Performance (SC-001, SC-002)
- Pending endpoint: 50-ticket poll cycle under 10 seconds (noted; load test out of scope for v1)
- Batch status: up to 100 IDs < 500ms (noted; no load test in v1 scope)

---

## CI Integration Recommendations

| Suite | When to run | Max duration |
|-------|-------------|--------------|
| Contract tests (test_orchestrator.py + test_tickets.py) | Every commit / PR | < 2 min |
| Integration tests (test_fsm_service.py + test_audit_service.py) | Every PR (real DB in CI) | < 5 min |
| Full regression | Pre-merge to main | < 10 min |

---

## Blocking Quality Gates

**Block release when**:
- Any contract or integration test fails (T011, T014, T017, T022, T025, T028, T031, T034, T037, T038)
- Audit immutability violated (no UPDATE/DELETE exposed)
- Service account fail-closed behavior not verified (FR-028)
- `include_fsm=false` (default) regresses existing list endpoint behavior

**Track but do not block**:
- Performance targets (SC-001, SC-002) — not covered by automated tests in v1
- T040 mypy/ruff failures tracked by code-reviewer, not autotester
