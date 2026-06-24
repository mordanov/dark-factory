# Tasks: Project Groups, Assignee-Only Transitions, and Tokens Spent

**Input**: Design documents from `specs/006-project-groups-transitions-tokens/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/api.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.
Tests are included for all three user stories (required by Constitution Principle VIII).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: US1 = Project Groups, US2 = Assignee-Only Transitions, US3 = Tokens Spent

---

## Phase 1: Setup (Migrations)

**Purpose**: Database schema changes that all three user stories depend on.

- [X] T001 [P] Create migration 017_add_project_groups.py: create project_groups table, seed DEFAULT row, add nullable group_id to projects, backfill to DEFAULT, set NOT NULL + FK — in backend/alembic/versions/017_add_project_groups.py
- [X] T002 [P] Create migration 018_add_tokens_spent.py: add tokens_spent INTEGER NOT NULL DEFAULT 0 with CHECK (tokens_spent >= 0) to tickets — in backend/alembic/versions/018_add_tokens_spent.py

---

## Phase 2: Foundational (ORM Models + Schemas)

**Purpose**: Models and schemas that all story implementations depend on.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [X] T003 [P] Create ProjectGroup ORM model (id, identifier, name, description, is_system, created_at, projects relationship) in backend/src/models/project_group.py
- [X] T004 [P] Add tokens_spent Mapped[int] column (default=0, server_default="0") to Ticket ORM model in backend/src/models/ticket.py
- [X] T005 Add group_id FK column and group: Mapped["ProjectGroup"] relationship (lazy="joined") to Project ORM model in backend/src/models/project.py (requires T003)
- [X] T006 [P] Create project_group schemas: ProjectGroupCreate (identifier, name, description), ProjectGroupUpdate (name, description), ProjectGroupResponse (all fields + project_count), ProjectGroupListResponse (items, total) in backend/src/schemas/project_group.py
- [X] T007 [P] Add tokens_spent: int field to TicketResponse; add TokensSpentIncrementRequest (amount: int > 0) and TokensSpentIncrementResponse (ticket_id, tokens_spent, amount_added, event_id) in backend/src/schemas/ticket.py
- [X] T008 Update project schemas: add optional group_id: UUID | None to ProjectCreate; add group_id: UUID and group: ProjectGroupResponse to ProjectResponse in backend/src/schemas/project.py (requires T006)

**Checkpoint**: Models and schemas ready — user story implementation can proceed.

---

## Phase 3: User Story 1 — Project Groups (Priority: P1) 🎯 MVP

**Goal**: Full group CRUD + project group assignment + project list group filter (backend + frontend).

**Independent Test**: Create group "TEAM1", create project in TEAM1, filter project list by TEAM1 — only that project appears. Attempt to delete DEFAULT group — 409 returned.

- [X] T009 [P] [US1] Create project_group_service.py with create_group (normalize identifier to uppercase, raise 409 on duplicate), list_groups (with project_count subquery), get_group (raise 404 if missing), update_group (name/description only), delete_group (raise 409 if is_system or has projects) in backend/src/services/project_group_service.py
- [X] T010 [P] [US1] Create groups API router with 5 endpoints: POST /api/v1/groups (201), GET /api/v1/groups (200), GET /api/v1/groups/{group_id} (200/404), PATCH /api/v1/groups/{group_id} (200/404), DELETE /api/v1/groups/{group_id} (204/409) in backend/src/api/v1/groups.py
- [X] T011 [US1] Update projects API router: add optional group_id query param to GET /api/v1/projects; add PATCH /api/v1/projects/{project_id} endpoint for group reassignment; update POST /api/v1/projects to auto-assign DEFAULT group if group_id omitted in backend/src/api/v1/projects.py
- [X] T012 [US1] Register groups router (prefix="/api/v1") and tokens_spent router in backend/src/main.py (stub tokens_spent import for now — will be filled in Phase 5)
- [X] T013 [P] [US1] Contract tests for group CRUD: test create (201), duplicate identifier (409), list (includes DEFAULT), get (200/404), update (200), delete system group (409), delete group with projects (409), delete empty group (204) in backend/tests/contract/test_groups.py
- [X] T014 [P] [US1] Integration tests for project_group_service: test identifier normalization (lowercase input → uppercase stored), test project_count on list, test auto-assign DEFAULT group when group_id omitted on project create in backend/tests/integration/test_project_group_service.py

**Checkpoint**: US1 backend complete and independently testable via quickstart.md US1 walkthrough.

- [X] T015 [P] [US1] Add ProjectGroup TypeScript interface and update Project interface (add group_id, group) in frontend/src/types.ts
- [X] T016 [P] [US1] Add groupsApi object (list, create, update, delete) and update projectsApi: add group_id param to list(), add updateGroup() method to frontend/src/api/ (client file or new groupsApi.ts)
- [X] T017 [P] [US1] Create GroupFilter component: dropdown of all groups plus "All" option; calls onChange with selected group_id or null in frontend/src/components/projects/GroupFilter.tsx
- [X] T018 [US1] Update ProjectListPage: add GroupFilter, hold selected group in local state, pass group_id to projectsApi.list() query, show each project's group name in project list in frontend/src/pages/ProjectListPage.tsx
- [X] T019 [P] [US1] Add i18n keys for groups and tokens_spent in frontend/src/locales/en.json and frontend/src/locales/ru.json

**Checkpoint**: US1 complete end-to-end — group filter visible in UI, project group displayed.

---

## Phase 4: User Story 2 — Assignee-Only Transitions (Priority: P2)

**Goal**: Remove progress-update gate; assignee-only authorization check preserved.

**Independent Test**: Assign a user to a ticket. Without submitting any progress update, transition the ticket — it succeeds. Non-assignee attempt returns 403. (No 422 transition_blocked is ever returned.)

- [X] T020 [US2] Remove progress gate block from transition_service.py: delete the ProgressUpdate query (lines ~53–64), the missing-list construction (lines ~65–75), the "ticket.transition_blocked" event emission (lines ~76–85), and the 422 raise (line ~86). Keep the assignee check (lines 41–46) and status_changed event emission intact in backend/src/services/transition_service.py
- [X] T021 [P] [US2] Update transition contract tests: remove test cases that expect 422 transition_blocked / missing_updates; add test confirming transition succeeds for assignee without any progress update submitted in backend/tests/contract/test_transitions.py
- [X] T022 [P] [US2] Add integration test: confirm that (a) assignee can transition without progress update and (b) non-assignee still gets 403 after progress gate removal in backend/tests/integration/test_transition_no_gate.py

**Checkpoint**: US2 complete — transition contract tests pass; no 422 transition_blocked emitted.

---

## Phase 5: User Story 3 — Tokens Spent (Priority: P3)

**Goal**: Increment-only tokens_spent endpoint; each increment recorded as immutable TicketEvent.

**Independent Test**: Ticket starts at tokens_spent=0. Increment by 500 → total 500, event emitted. Increment by 200 → total 700, second event emitted. Attempt amount=0 or amount=-10 → 422. GET /tickets/{id} shows tokens_spent: 700.

- [X] T023 [P] [US3] Create tokens_spent_service.py: increment_tokens_spent(session, ticket_id, amount, actor) — validate amount > 0, atomic UPDATE tickets SET tokens_spent = tokens_spent + :amount, emit TicketEvent "ticket.tokens_spent_incremented" with prev/new state and metadata.amount, return TokensSpentIncrementResponse in backend/src/services/tokens_spent_service.py
- [X] T024 [P] [US3] Create tokens_spent API router: POST /api/v1/tickets/{ticket_id}/tokens-spent (200); validate amount > 0 (422 on ≤0); 404 if ticket not found/deleted in backend/src/api/v1/tokens_spent.py
- [X] T025 [US3] Register tokens_spent router in backend/src/main.py (complete the import stubbed in T012)
- [X] T026 [P] [US3] Contract tests for tokens_spent endpoint: test increment (200 + new total), amount=0 (422), amount negative (422), non-existent ticket (404), two sequential increments accumulate correctly in backend/tests/contract/test_tokens_spent.py
- [X] T027 [P] [US3] Integration tests for tokens_spent_service: test atomic increment under concurrent calls, test TicketEvent emitted with correct prev_state/new_state/metadata in backend/tests/integration/test_tokens_spent_service.py

**Checkpoint**: US3 complete — tokens_spent endpoint live; each increment visible in /events.

- [X] T028 [P] [US3] Add tokensSpentApi.increment() method to frontend/src/api/
- [X] T029 [US3] Update TicketDetailPage: display tokens_spent field; add "Add Tokens Spent" button with amount input; call tokensSpentApi.increment() on submit; invalidate ticket query on success in frontend/src/pages/TicketDetailPage.tsx

**Checkpoint**: All three user stories complete end-to-end.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T030 Run ruff linting and fix all issues across changed backend files (ruff check --fix backend/src/ backend/tests/)
- [X] T031 [P] Verify docs/api-updates.md is complete and matches contracts/api.md: all 6 new endpoints documented, modified endpoints documented, removed 422 transition_blocked response documented in docs/api-updates.md
- [X] T032 [P] Run quickstart.md end-to-end validation: verify all curl commands in quickstart.md work against a local running instance; fix any discrepancies between quickstart and implementation

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately; T001 and T002 are parallel
- **Foundational (Phase 2)**: Depends on Phase 1 completion; T003–T006 are parallel; T005 depends on T003; T008 depends on T006
- **US1 Backend (Phase 3, T009–T014)**: Depends on Phase 2 completion; T009 and T010 are parallel; T011 depends on T009/T010
- **US1 Frontend (Phase 3, T015–T019)**: Can start alongside US1 backend; T015–T017 are parallel; T018 depends on T016/T017
- **US2 (Phase 4)**: Depends on Phase 2 only; fully independent of US1 and US3
- **US3 Backend (Phase 5, T023–T027)**: Depends on Phase 2 only; T023/T024 are parallel; T025 depends on T024
- **US3 Frontend (Phase 5, T028–T029)**: T028 parallel; T029 depends on T028
- **Polish (Phase 6)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 2 — no dependency on US2 or US3
- **US2 (P2)**: Can start after Phase 2 — no dependency on US1 or US3
- **US3 (P3)**: Can start after Phase 2 — no dependency on US1 or US2

### Within Each Story

- ORM models before schemas
- Schemas before services
- Services before endpoint routers
- Routers before router registration in main.py
- Backend complete before frontend
- Contract tests can be written in parallel with service implementation (they test the endpoint interface)

---

## Parallel Execution Examples

### Phase 2 Parallel Window
```
T003 ProjectGroup ORM model          ──┐
T004 tokens_spent column on Ticket   ──┤ all in parallel
T006 ProjectGroup schemas            ──┤
T007 Ticket schemas (tokens_spent)   ──┘
T005 Project ORM add group_id FK     ─── after T003
T008 Project schemas add group       ─── after T006
```

### US1 + US2 + US3 in Parallel (after Phase 2)
```
US1: T009 group service ──→ T010 groups router ──→ T011 projects router ──→ T012 main.py
US2: T020 remove gate ──→ T021/T022 tests
US3: T023 tokens service ──→ T024 tokens router ──→ T025 main.py
```

---

## Implementation Strategy

### MVP (US1 only — Project Groups)

1. Complete Phase 1 (migrations)
2. Complete Phase 2 (models + schemas)
3. Complete Phase 3 US1 backend (T009–T014)
4. Complete Phase 3 US1 frontend (T015–T019)
5. **STOP and VALIDATE**: Create group, create project, filter — all work
6. Demo/deploy if ready

### Incremental Delivery

1. Phase 1 + 2 → Foundation ready
2. Phase 3 → Project groups live (MVP)
3. Phase 4 → Transition behaviour updated (independent)
4. Phase 5 → Tokens spent live (independent)
5. Phase 6 → Polish and docs verified

### Parallel Team Strategy

With three developers after Phase 2 completes:
- Developer A: US1 (T009–T019)
- Developer B: US2 (T020–T022)
- Developer C: US3 (T023–T029)

---

## Notes

- `[P]` tasks target different files with no cross-dependencies within the same phase
- US2 is the smallest story (3 tasks) — can be completed in a single session
- Migration 017 has 3 steps (create table → seed → add FK); all steps are in one file; test rollback explicitly
- `tokens_consumed` (system-driven, existing) must NOT be confused with `tokens_spent` (user-driven, new); they coexist on the Ticket model
- `TransitionBlockedError` schema and `MissingUpdate` schema can be left in the codebase for now (no tests use them after T021); clean up is a follow-up
- Each user story has its own contract test file and integration test file for clean separation
