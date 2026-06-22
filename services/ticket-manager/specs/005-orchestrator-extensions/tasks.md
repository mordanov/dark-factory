# Tasks: Workflow Orchestrator Integration Extensions

**Input**: Design documents from `specs/005-orchestrator-extensions/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅ | quickstart.md ✅

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story this task belongs to (US1–US8 from spec.md)
- Tests are included per Constitution Principle VIII (mandatory for all API and service boundaries)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Minimal project setup needed before foundational work. This is an existing project — no scaffolding required.

- [ ] T001 Add `ticket_manager_service_email: str` setting to `backend/src/core/config.py` and document in `backend/.env.example`
- [ ] T002 [P] Create stub file `backend/src/api/v1/orchestrator.py` with empty FastAPI `APIRouter(prefix="", tags=["Orchestrator"])` and register it in `backend/src/api/v1/router.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database schema, models, auth dependency, and shared schemas that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 Write Alembic migration `backend/alembic/versions/015_add_fsm_fields.py`: create `fsm_status_enum` PostgreSQL type; add columns `fsm_status`, `blocked_reason`, `brainstorm_round` (default 0), `assigned_agent`, `override` (default false), `override_reason`, `last_orchestrator_run`, `orchestrator_errors` (JSONB) to `tickets`; add indexes `idx_tickets_fsm_status` and `idx_tickets_pending (updated_at, id)`; include full `downgrade()` path
- [ ] T004 Write Alembic migration `backend/alembic/versions/016_add_orchestrator_audit_events.py`: create table `orchestrator_audit_events` with columns `id` (UUID PK), `ticket_id` (FK tickets.id), `event` (VARCHAR 50), `actor` (VARCHAR 255), `from_state` (TEXT nullable), `to_state` (TEXT nullable), `details` (TEXT nullable), `timestamp` (TIMESTAMPTZ server_default now()); add indexes `idx_orchestrator_audit_ticket_id` and `idx_orchestrator_audit_timestamp`; include full `downgrade()` path
- [ ] T005 [P] Add `FsmStatus` enum class and 8 mapped columns to `backend/src/models/ticket.py` matching migration 015 (see data-model.md §1 for exact column types and defaults)
- [ ] T006 [P] Create `backend/src/models/orchestrator_audit_event.py` with `OrchestratorAuditEvent` SQLAlchemy model matching migration 016 schema (see data-model.md §2)
- [ ] T007 Add `OrchestratorAuditEvent` import to `backend/src/models/__init__.py` so Alembic autodiscovery includes the new model
- [ ] T008 [P] Add `require_service_account_or_admin` FastAPI dependency to `backend/src/core/security.py`: grants access if `current_user.email == settings.ticket_manager_service_email` OR `current_user.role == UserRole.administrator`; raises HTTP 403 otherwise
- [ ] T009 [P] Add FSM Pydantic schemas to `backend/src/schemas/ticket.py`: `FsmPatchRequest` (all fields optional), `TicketFsmResponse` (extends `TicketResponse` with all FSM fields including `override`), `TagDeltaRequest` (add/remove string lists), `TagDeltaResponse` (tags list), `OverrideRequest` (override bool + reason), `BatchFsmStatusRequest` (ticket_ids list), `BatchFsmStatusEntry` (fsm_status + title + blocked_reason), `BatchFsmStatusResponse` (dict mapping)
- [ ] T010 [P] Create `backend/src/schemas/orchestrator.py` with: `AuditEventCreate`, `AuditEventResponse`, `AuditLogResponse`, `PendingTicketsResponse`, `TicketPendingSummary`; add cursor encode/decode utility functions (base64 JSON of `{"updated_at": ISO8601, "id": UUID-str}`)

**Checkpoint**: Run `alembic upgrade head` and `mypy src/` — both must pass before proceeding.

---

## Phase 3: User Story 1 — Orchestrator Polls for Pending Tickets (Priority: P1) 🎯 MVP

**Goal**: The orchestrator can discover all tickets that need processing via a single paginated endpoint.

**Independent Test**: Call `GET /api/v1/orchestrator/pending` and verify correct filtering, pagination cursor, and `total_pending` count.

### Tests for User Story 1

- [ ] T011 [P] [US1] Write contract tests for `GET /api/v1/orchestrator/pending` in `backend/tests/contract/test_orchestrator.py`: test pending filter logic (fsm_status != done AND updated_at > last_orchestrator_run), pagination with cursor, project_id filter, limit param, empty result case, and response schema

### Implementation for User Story 1

- [ ] T012 [US1] Create `backend/src/services/fsm_service.py` with `get_pending_tickets(db, project_id, limit, after_cursor) → PendingTicketsResponse`: implement pending filter query (`fsm_status IS DISTINCT FROM 'done' AND (last_orchestrator_run IS NULL OR updated_at > last_orchestrator_run)`), keyset pagination on `(updated_at, id)`, cursor decode/encode, `total_pending` count query, and full `TicketPendingSummary` projection (including dependencies as follow-up ticket IDs via `parent_ticket_id`)
- [ ] T013 [US1] Add `GET /orchestrator/pending` endpoint to `backend/src/api/v1/orchestrator.py` wired to `fsm_service.get_pending_tickets`; accepts `project_id` (optional UUID query), `limit` (default 20, max 100), `after_cursor` (optional string query); authenticated but no role restriction

**Checkpoint**: `pytest tests/contract/test_orchestrator.py -k pending` must pass.

---

## Phase 4: User Story 2 — Orchestrator Updates FSM State (Priority: P1)

**Goal**: The orchestrator can atomically update FSM fields on any ticket without touching native TM fields.

**Independent Test**: Call `PATCH /api/v1/projects/{id}/tickets/{id}/fsm` and verify only FSM fields change; native fields (title, description, status) are unchanged; non-service-account gets 403.

### Tests for User Story 2

- [ ] T014 [P] [US2] Add contract tests to `backend/tests/contract/test_orchestrator.py`: test FSM patch updates only FSM fields, partial update (send only one field), service account allowed, non-service-account gets 403, unknown ticket gets 404, response includes full FSM fields

### Implementation for User Story 2

- [ ] T015 [US2] Add `patch_fsm_fields(db, project_id, ticket_id, body, current_user) → TicketFsmResponse` to `backend/src/services/fsm_service.py`: verify ticket belongs to project, apply only provided fields (exclude_unset pattern), update `updated_at`, return `TicketFsmResponse`
- [ ] T016 [US2] Add `PATCH /projects/{project_id}/tickets/{ticket_id}/fsm` endpoint to `backend/src/api/v1/orchestrator.py` using `require_service_account_or_admin` dependency; wired to `fsm_service.patch_fsm_fields`

**Checkpoint**: `pytest tests/contract/test_orchestrator.py -k fsm` must pass.

---

## Phase 5: User Story 3 — Orchestrator Writes and Reads Audit Log (Priority: P1)

**Goal**: Every orchestrator action is recorded as an immutable audit event retrievable by ticket.

**Independent Test**: POST an audit event, then GET the log — event appears with correct fields in chronological order.

### Tests for User Story 3

- [ ] T017 [P] [US3] Add contract tests to `backend/tests/contract/test_orchestrator.py`: test POST audit creates event (201 + audit_entry_id), GET audit returns entries sorted by timestamp, GET audit for ticket with no events returns empty list, GET audit for unknown ticket returns 404

### Implementation for User Story 3

- [ ] T018 [P] [US3] Create `backend/src/services/audit_service.py` with `create_audit_event(db, ticket_id, body) → AuditEventResponse`: verify ticket exists, create `OrchestratorAuditEvent` row, commit, return response; use `body.timestamp` if provided else `datetime.now(UTC)`
- [ ] T019 [P] [US3] Add `get_audit_log(db, ticket_id) → AuditLogResponse` to `backend/src/services/audit_service.py`: verify ticket exists, query `orchestrator_audit_events` ordered by `timestamp ASC`, return entries list
- [ ] T020 [US3] Add `POST /tickets/{ticket_id}/audit` endpoint to `backend/src/api/v1/orchestrator.py` wired to `audit_service.create_audit_event`; authenticated, no role restriction
- [ ] T021 [P] [US3] Add `GET /tickets/{ticket_id}/audit` endpoint to `backend/src/api/v1/orchestrator.py` wired to `audit_service.get_audit_log`; authenticated, no role restriction

**Checkpoint**: `pytest tests/contract/test_orchestrator.py -k audit` must pass. US1+US2+US3 now form a complete orchestrator polling + state-update + audit loop.

---

## Phase 6: User Story 4 — Human Admin Overrides a Failed Gate (Priority: P2)

**Goal**: An admin can set `override: true` on a ticket so the orchestrator skips the failed gate on the next poll cycle.

**Independent Test**: Admin POSTs override, ticket shows `override: true`; non-admin gets 403; orchestrator clears the flag via FSM PATCH.

### Tests for User Story 4

- [ ] T022 [P] [US4] Add contract tests to `backend/tests/contract/test_orchestrator.py`: test admin can set override (200 + override=true in response), non-admin gets 403, unknown ticket gets 404, override_reason is stored

### Implementation for User Story 4

- [ ] T023 [US4] Add `set_override(db, project_id, ticket_id, body, current_user) → TicketFsmResponse` to `backend/src/services/fsm_service.py`: verify ticket belongs to project, set `ticket.override = body.override`, set `ticket.override_reason = body.override_reason`, commit, return `TicketFsmResponse`
- [ ] T024 [US4] Add `POST /projects/{project_id}/tickets/{ticket_id}/override` endpoint to `backend/src/api/v1/orchestrator.py` using `require_role("administrator")` dependency; wired to `fsm_service.set_override`

**Checkpoint**: `pytest tests/contract/test_orchestrator.py -k override` must pass.

---

## Phase 7: User Story 5 — Batch Dependency Status Check (Priority: P2)

**Goal**: The orchestrator can check FSM statuses for multiple ticket IDs in a single request.

**Independent Test**: POST batch request with 3 known IDs and 1 unknown ID — response map contains exactly 3 entries, unknown ID absent.

### Tests for User Story 5

- [ ] T025 [P] [US5] Add contract tests to `backend/tests/contract/test_orchestrator.py`: test batch returns correct status map, unknown IDs omitted, empty input returns empty map, BLOCKED ticket includes blocked_reason in entry

### Implementation for User Story 5

- [ ] T026 [US5] Add `batch_fsm_status(db, ticket_ids) → BatchFsmStatusResponse` to `backend/src/services/ticket_service.py`: query tickets by ID list in one DB call, build response dict mapping `str(ticket.id)` to `BatchFsmStatusEntry(fsm_status, title, blocked_reason)`, silently omit missing IDs
- [ ] T027 [US5] Add `POST /tickets/batch-fsm-status` endpoint to `backend/src/api/v1/orchestrator.py` wired to `ticket_service.batch_fsm_status`; accepts `BatchFsmStatusRequest`; authenticated, no role restriction

**Checkpoint**: `pytest tests/contract/test_orchestrator.py -k batch` must pass.

---

## Phase 8: User Story 6 — Atomic Tag Delta (Priority: P2)

**Goal**: The orchestrator can add and remove tags in a single atomic operation without overwriting the full tag list.

**Independent Test**: POST tag delta with `add: ["needs-estimation"]` and `remove: ["old-tag"]` — both applied atomically, idempotent on re-call.

### Tests for User Story 6

- [ ] T028 [P] [US6] Add contract tests to `backend/tests/contract/test_tickets.py`: test add tag via delta (200 + tag present), remove tag via delta (tag absent), add+remove in same call, add existing tag is idempotent, remove absent tag is idempotent, unknown ticket returns 404

### Implementation for User Story 6

- [ ] T029 [US6] Add `apply_tag_delta(db, project_id, ticket_id, add, remove, current_user) → TagDeltaResponse` to `backend/src/services/ticket_service.py`: load ticket, resolve `add` tag names (create Tag rows if new), remove specified tags from association, add new tags, commit in single transaction, return `TagDeltaResponse(tags=[t.name for t in ticket.tags])`
- [ ] T030 [US6] Add `POST /projects/{project_id}/tickets/{ticket_id}/tags/delta` endpoint to `backend/src/api/v1/tickets.py` wired to `ticket_service.apply_tag_delta`; accepts `TagDeltaRequest`; authenticated with standard `get_current_user`

**Checkpoint**: `pytest tests/contract/test_tickets.py -k delta` must pass.

---

## Phase 9: User Story 7 — Full Ticket with FSM Fields (Priority: P3)

**Goal**: A single endpoint returns a ticket's complete data including all FSM fields.

**Independent Test**: GET `/full` for a ticket with FSM fields set — response contains all 8 FSM fields plus all native fields.

### Tests for User Story 7

- [ ] T031 [P] [US7] Add contract tests to `backend/tests/contract/test_orchestrator.py`: test /full response includes all FSM fields when set, includes default values when FSM fields are null/zero, returns 404 for unknown ticket

### Implementation for User Story 7

- [ ] T032 [US7] Add `get_ticket_full(db, project_id, ticket_id) → TicketFsmResponse` to `backend/src/services/fsm_service.py`: load ticket (verify project membership), return `TicketFsmResponse` including all FSM columns
- [ ] T033 [US7] Add `GET /projects/{project_id}/tickets/{ticket_id}/full` endpoint to `backend/src/api/v1/orchestrator.py` wired to `fsm_service.get_ticket_full`; authenticated, no role restriction

**Checkpoint**: `pytest tests/contract/test_orchestrator.py -k full` must pass.

---

## Phase 10: User Story 8 — List Tickets with FSM Status (Priority: P3)

**Goal**: The existing ticket list endpoint optionally includes FSM fields on each ticket when `include_fsm=true` is passed.

**Independent Test**: GET list with `include_fsm=true` — FSM fields present on each item; GET without param — response identical to current behavior (no regressions).

### Tests for User Story 8

- [ ] T034 [P] [US8] Add contract tests to `backend/tests/contract/test_tickets.py` (or `test_orchestrator.py`): test list with `include_fsm=true` returns FSM fields on tickets, list without `include_fsm` returns no FSM fields (backwards compatibility), FSM field values match those set via PATCH /fsm

### Implementation for User Story 8

- [ ] T035 [US8] Extend `list_tickets(db, project_id, status, assignee_id, page, page_size, include_fsm=False)` in `backend/src/services/ticket_service.py`: when `include_fsm=True`, return `list[TicketFsmResponse]` instead of `list[TicketResponse]`; when `False`, preserve existing behavior exactly
- [ ] T036 [US8] Add `include_fsm: bool = Query(default=False)` parameter to `GET /projects/{project_id}/tickets` in `backend/src/api/v1/projects.py`; update `list_tickets` call to pass `include_fsm`; update response model to `Union[TicketListResponse, TicketFsmListResponse]` or use generic dict response

**Checkpoint**: `pytest tests/contract/test_tickets.py` full suite must pass with zero regressions.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Integration tests, observability, and final validation across all user stories.

- [ ] T037 [P] Write integration tests for FSM service in `backend/tests/integration/test_fsm_service.py`: test get_pending_tickets filter correctness with real DB, FSM patch atomicity (concurrent updates don't corrupt native fields), cursor pagination stability under inserts
- [ ] T038 [P] Write integration tests for audit service in `backend/tests/integration/test_audit_service.py`: test create + retrieve round-trip, chronological ordering, ticket-not-found error
- [ ] T039 Add structured `structlog` log entries to `backend/src/services/fsm_service.py` and `backend/src/services/audit_service.py` for FSM state transitions and audit event creation (log: ticket_id, from_state, to_state, actor — no PII per Principle IX)
- [ ] T040 [P] Run full type-check and lint: `uv run mypy backend/src/` and `uv run ruff check backend/src/` must both pass with zero errors
- [ ] T041 [P] Run full test suite: `uv run pytest backend/tests/` must pass with zero failures; verify new endpoints appear in FastAPI's `/docs` OpenAPI UI

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1; **BLOCKS all user story phases**
- **Phase 3–10 (User Stories)**: All depend on Phase 2; can proceed in any order or parallel after Phase 2
- **Phase 11 (Polish)**: Depends on all desired user story phases complete

### User Story Dependencies

- **US1 (Polling)** — independent after Phase 2
- **US2 (FSM Patch)** — independent after Phase 2; US1 tests benefit from US2 existing (to set FSM state for polling)
- **US3 (Audit Log)** — independent after Phase 2
- **US4 (Override)** — independent after Phase 2; uses same `override` column added in Phase 2
- **US5 (Batch Status)** — independent after Phase 2
- **US6 (Tag Delta)** — independent after Phase 2; uses existing Tag model
- **US7 (Full Ticket)** — independent after Phase 2; effectively a read-only view of US2's data
- **US8 (List with FSM)** — independent after Phase 2; builds on list_tickets from existing code

### Within Each User Story

- Contract tests (T011, T014, etc.) written first — they document intent
- Models/services before endpoints
- Endpoint added last (wires to already-tested service)

### Parallel Opportunities

All tasks marked `[P]` within the same phase have no file conflicts and can run concurrently.

After Phase 2 completes, all user story phases (3–10) can be worked in parallel by different team members.

---

## Parallel Example: Phase 2 Foundational

```bash
# These can run in parallel (different files):
Task T003: "Add FsmStatus enum + columns in backend/src/models/ticket.py"
Task T004: "Add FsmStatus enum + columns in backend/src/models/ticket.py"
# Wait — T003 and T004 are different files, truly parallel:
Task T005: "backend/src/models/ticket.py"
Task T006: "backend/src/models/orchestrator_audit_event.py"
Task T008: "backend/src/core/security.py"
Task T009: "backend/src/schemas/ticket.py"
Task T010: "backend/src/schemas/orchestrator.py"
```

## Parallel Example: P1 User Stories (after Phase 2)

```bash
# Three teams can work simultaneously:
Team A → Phase 3 (US1: Polling endpoint)
Team B → Phase 4 (US2: FSM PATCH)
Team C → Phase 5 (US3: Audit log)
```

---

## Implementation Strategy

### MVP First (P1 Stories: US1 + US2 + US3)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T010) — run migrations
3. Complete Phase 3: US1 Polling (T011–T013)
4. Complete Phase 4: US2 FSM Patch (T014–T016)
5. Complete Phase 5: US3 Audit Log (T017–T021)
6. **STOP and VALIDATE**: Full orchestrator poll → patch → audit cycle works end-to-end
7. Deploy/demo — orchestrator can now operate against a live TM instance

### Incremental Delivery

1. Setup + Foundational → schema ready
2. US1 + US2 + US3 → core orchestrator loop (**MVP**)
3. US4 + US5 + US6 → operational controls (override, batch, tag delta)
4. US7 + US8 → convenience read endpoints
5. Polish → integration tests, logging, final validation

### Parallel Team Strategy

With 3+ developers after Phase 2:
- Developer A: US1 (polling) → US5 (batch)
- Developer B: US2 (FSM patch) → US4 (override) → US7 (full ticket)
- Developer C: US3 (audit) → US6 (tag delta) → US8 (list with FSM)

---

## Notes

- `[P]` tasks touch different files — no merge conflicts when run in parallel
- `[Story]` labels map tasks to spec.md user stories for traceability
- Migrations (T003, T004) must run sequentially in order (015 before 016)
- T005 and T003 must be consistent — run migration then update model
- Contract tests can be written before implementation (they will fail until the endpoint exists — that's intentional)
- `override` boolean column (added in T003) is cleared by the orchestrator via FSM PATCH (T015/T016), not by TM logic
- Batch endpoint path is `/api/v1/tickets/batch-fsm-status` (not `/api/tickets/fsm-status-batch` as in spec.md — aligned with v1 prefix per research.md §8)
