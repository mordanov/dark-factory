---
description: "Task list for Ticket Management System — multi-agent execution via Brainstorm MCP"
---

# Tasks: Ticket Management System

**Input**: Design documents from `/specs/001-ticket-management-system/`
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/openapi.yaml ✅

---

## Brainstorm MCP Coordination

This task list is designed for eight-agent parallel execution. Before starting:

1. Each agent runs `bash run-agents.sh` to join the Brainstorm project.
2. **Read first**: `specs/001-ticket-management-system/spec.md`, `plan.md`, `data-model.md`,
   and `contracts/openapi.yaml`.
3. **Claim tasks**: broadcast via Brainstorm which task ID you are starting.
4. **Handoff**: when a task is done, post a summary to the channel and mark any tasks
   you unblock.
5. **Security-critical gate** (`[SECURITY-CRITICAL]`): security-architect reviews
   before downstream work may merge. Post a review result to the channel.
6. **Review gate** (`[REVIEW]`): code-reviewer reviews the output and must post
   APPROVE or CHANGES REQUESTED before that phase is considered done.

### Agent → Task Tag Mapping

| Agent | Claims tasks tagged |
|-------|-------------------|
| `software-architect` | `[ARCH]` |
| `security-architect` | `[SECURITY]`, reviews all `[SECURITY-CRITICAL]` |
| `backend` | `[BACKEND]`, `[DATA]` |
| `frontend` | `[FRONTEND]` |
| `devops` | `[PLATFORM]`, `[OPS]` |
| `code-reviewer` | `[REVIEW]` |
| `autotester` | `[TEST]` |
| `product-manager` | `[PM]`, coordinates milestones |

---

## Format: `[ID] [P?] [Story?] [ROLE] [SECURITY-CRITICAL?] Description — file path`

- **[P]**: safe to run in parallel with other [P] tasks in the same phase
- **[US#]**: user story from spec.md
- **[ROLE]**: agent responsible (see table above)
- **[SECURITY-CRITICAL]**: must be reviewed by security-architect before downstream merge

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Create the scaffolding every agent needs before any domain code is written.

- [ ] T001 [ARCH] Create repository directory structure: `backend/`, `frontend/`, `devops/`, `backend/alembic/versions/`, `backend/src/{core,models,schemas,services,api/v1}/`, `backend/tests/{contract,integration,unit}/`, `frontend/src/{api,components/{tickets,projects,common},pages,store}/`, `frontend/tests/{components,pages}/`
- [ ] T002 [PLATFORM] Initialize Python 3.11 FastAPI backend project — `backend/pyproject.toml` (or `requirements.txt`/`requirements-dev.txt`) with: fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, pydantic[email], pydantic-settings, python-jose[cryptography], bcrypt, structlog, httpx, pytest, pytest-asyncio, pytest-httpx
- [ ] T003 [P] [PLATFORM] Initialize React 18 TypeScript frontend project with Vite — `frontend/` scaffold with: react, react-dom, react-router-dom v6, @tanstack/react-query v5, zustand, typescript, vitest, @testing-library/react, @testing-library/user-event
- [ ] T004 [P] [ARCH] Initialize Alembic in `backend/alembic/` — configure `env.py` to read `DATABASE_URL` from environment and use async engine
- [ ] T005 [P] [PLATFORM] Create `backend/.env.example` with all required vars: `DATABASE_URL`, `SECRET_KEY`, `REFRESH_TOKEN_SECRET`, `ENVIRONMENT`, `LOG_LEVEL`, `ACCESS_TOKEN_EXPIRE_MINUTES=30`
- [ ] T006 [P] [PLATFORM] Create `frontend/.env.local.example` with: `VITE_API_BASE_URL=http://localhost:8000`

**Checkpoint**: All agents can install dependencies and directory structure is in place.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story can begin.

> **⚠ CRITICAL**: No user story work can begin until this phase is complete and review
> gates T028–T029 have passed.

### Database Migrations (backend agent, sequential order)

- [ ] T007 [DATA] Create `backend/alembic/versions/001_create_enum_types.py` — PostgreSQL ENUM types: `user_role` ('administrator','user') and `ticket_status` ('OPEN','IN_PROGRESS','IN_REVIEW','DONE','CLOSED'). Include `upgrade()` and `downgrade()`.
- [ ] T008 [DATA] Create `backend/alembic/versions/002_create_users.py` — `users` table per data-model.md (id UUID PK, email UNIQUE, hashed_password, role user_role, created_at, updated_at). Include rollback.
- [ ] T009 [DATA] Create `backend/alembic/versions/003_create_projects.py` — `projects` table (id, name, slug UNIQUE, created_by FK→users, created_at). Include rollback.
- [ ] T010 [DATA] Create `backend/alembic/versions/004_create_tickets.py` — `tickets` table with soft-delete (`deleted_at`), self-referential `parent_ticket_id`, status enum, all indexes. Include rollback.
- [ ] T011 [DATA] Create `backend/alembic/versions/005_create_ticket_assignments.py` — `ticket_assignments` table with UNIQUE(ticket_id, user_id). Include rollback.
- [ ] T012 [DATA] Create `backend/alembic/versions/006_create_progress_updates.py` — `progress_updates` table with UNIQUE(ticket_id, user_id). Include rollback.
- [ ] T013 [DATA] Create `backend/alembic/versions/007_create_ticket_events.py` — `ticket_events` append-only table (id, ticket_id, event_type, actor_id, actor_role, prev_state JSONB, new_state JSONB, metadata JSONB, occurred_at). Include rollback. Add all indexes from data-model.md.
- [ ] T014 [DATA] [SECURITY-CRITICAL] Create `backend/alembic/versions/008_create_refresh_tokens.py` — `refresh_tokens` table (id, user_id, token_hash UNIQUE, expires_at, revoked_at, created_at). Include rollback.

### Backend Core Services

- [ ] T015 [P] [BACKEND] Implement `backend/src/core/config.py` — Pydantic BaseSettings reading all env vars from `.env.example`: database_url, secret_key, refresh_token_secret, environment, log_level, access_token_expire_minutes
- [ ] T016 [BACKEND] Implement `backend/src/core/database.py` — async SQLAlchemy engine via asyncpg, async session factory, `get_db` FastAPI dependency
- [ ] T017 [P] [BACKEND] Implement `backend/src/core/logging.py` — structlog JSON renderer, request middleware binding `request_id` and `actor_id` per request. PII redaction processor must strip: `password`, `hashed_password`, `token`, `token_hash`, `access_token`, `refresh_token` fields from log output.
- [ ] T018 [BACKEND] [SECURITY-CRITICAL] Implement `backend/src/core/security.py` — bcrypt password hash/verify, JWT access token sign/verify (HS256, 30-min TTL), `get_current_user` FastAPI dependency, `require_role(role)` dependency factory. No plaintext secrets in logs or errors.
- [ ] T019 [BACKEND] Implement SQLAlchemy ORM models in `backend/src/models/` — one file per entity: `user.py`, `project.py`, `ticket.py`, `ticket_assignment.py`, `progress_update.py`, `ticket_event.py`, `refresh_token.py`. All models must match schema in data-model.md exactly (column names, types, constraints, relationships).
- [ ] T020 [BACKEND] Implement `backend/src/services/event_service.py` — `emit_event(session, ticket_id, event_type, actor, prev_state, new_state, metadata)` helper that writes one immutable row to `ticket_events`. Must support all 8 event types from data-model.md event catalogue. No UPDATE/DELETE permitted.
- [ ] T021 [BACKEND] Implement `backend/src/services/workflow_service.py` — `WORKFLOW_TRANSITIONS` dict matching data-model.md workflow table. `validate_transition(from_status, to_status)` raises 409 if invalid. Progress gate check is in T050 (US3 phase).
- [ ] T022 [BACKEND] [SECURITY-CRITICAL] Implement auth endpoints in `backend/src/api/v1/auth.py` — POST /api/v1/auth/login (verify bcrypt, issue JWT + refresh token, store refresh_token hash), POST /api/v1/auth/refresh (verify hash in DB, check revoked_at/expires_at, issue new JWT), POST /api/v1/auth/logout (set revoked_at on refresh token). Emit no auditable ticket event (auth is outside ticket domain). Structured error responses — no stack traces.
- [ ] T023 [BACKEND] Implement `backend/src/main.py` — FastAPI app, include /api/v1 router, add structlog middleware, `/health` (200 ok), `/ready` (200 ready / 503 if DB unreachable). Register all v1 sub-routers.

### Frontend Core

- [ ] T024 [FRONTEND] [SECURITY-CRITICAL] Implement `frontend/src/store/auth.ts` — Zustand store with: access_token (memory only, NOT localStorage), current user object, login/logout actions. Tokens must not be stored in localStorage or sessionStorage (XSS risk).
- [ ] T025 [FRONTEND] Implement `frontend/src/api/client.ts` — axios or fetch wrapper that: injects `Authorization: Bearer <token>` header from Zustand store, intercepts 401 to attempt token refresh via POST /api/v1/auth/refresh, retries original request once, redirects to login if refresh fails.
- [ ] T026 [FRONTEND] Implement `frontend/src/pages/LoginPage.tsx` — email/password form with validation, error display, calls POST /api/v1/auth/login, stores token in Zustand, redirects to project list.
- [ ] T027 [FRONTEND] Implement `frontend/src/components/common/ProtectedRoute.tsx` — redirects to /login if no auth token in Zustand store.
- [ ] T028 [FRONTEND] Implement `frontend/src/router.tsx` — React Router config: `/login` (public), `/projects` (protected), `/projects/:id` (protected), `/tickets/:id` (protected). Wrap protected routes with ProtectedRoute.

### Security Gate (blocks all US implementation)

- [ ] T029 [SECURITY] [SECURITY-CRITICAL] Security architect: review auth implementation (T014, T018, T022, T024, T025) — produce threat model for authentication flow covering: token storage XSS risk, refresh token revocation path, bcrypt cost factor, JWT signing algorithm, RBAC enforcement layer. Post APPROVED or CHANGES REQUIRED to Brainstorm channel before any US phase begins.

### Foundational Review Gate

- [ ] T030 [REVIEW] Code reviewer: review Phase 2 backend (T015–T023) — verify: migrations have downgrade(), event_service has no UPDATE/DELETE, RBAC dependency is applied before handlers, no secrets in logs. Post review result to Brainstorm channel.

**Checkpoint**: Foundation ready — all US phases can now begin in parallel.

---

## Phase 3: User Story 1 — Ticket Creation and Organization (Priority: P1) 🎯 MVP

**Goal**: Product owners create primary tickets; any user creates follow-ups; edit and
delete work with the follow-up guard.

**Independent Test**: Create a primary ticket, create a follow-up linked to it, edit
the primary ticket's title, then attempt deletion (blocked) — all without assignments
or status transitions.

### Implementation for User Story 1

- [ ] T031 [P] [BACKEND] [US1] Implement Pydantic schemas in `backend/src/schemas/ticket.py`: TicketCreate, TicketUpdate, FollowUpTicketCreate, AssigneeSummary, TicketResponse, TicketListResponse — match shapes in `contracts/openapi.yaml` exactly.
- [ ] T032 [BACKEND] [US1] Implement `TicketService.create_ticket(session, project_id, data, actor)` in `backend/src/services/ticket_service.py` — create Ticket row, call `emit_event(ticket.created)`, return TicketResponse.
- [ ] T033 [BACKEND] [US1] Implement `TicketService.create_follow_up(session, parent_ticket_id, data, actor)` — validate parent exists and not deleted, create child Ticket row, emit `ticket.created` event.
- [ ] T034 [BACKEND] [US1] Implement `TicketService.update_ticket(session, ticket_id, data, actor)` — verify caller is creator or admin, update fields, emit `ticket.updated` event with prev/new state snapshot.
- [ ] T035 [BACKEND] [US1] Implement `TicketService.delete_ticket(session, ticket_id, actor)` — verify caller is creator or admin, check no active follow-ups (raise 409 if any), set `deleted_at`, emit `ticket.deleted` event.
- [ ] T036 [BACKEND] [US1] Implement `GET /api/v1/projects/{project_id}/tickets` and `POST /api/v1/projects/{project_id}/tickets` endpoints in `backend/src/api/v1/projects.py` — apply `get_current_user` dependency on all routes.
- [ ] T037 [BACKEND] [US1] Implement `GET /api/v1/tickets/{ticket_id}`, `PATCH /api/v1/tickets/{ticket_id}`, `DELETE /api/v1/tickets/{ticket_id}`, `POST /api/v1/tickets/{ticket_id}/follow-ups` in `backend/src/api/v1/tickets.py`. All routes apply `get_current_user`. GET returns 404 when `deleted_at IS NOT NULL`.
- [ ] T038 [P] [FRONTEND] [US1] Implement `frontend/src/components/tickets/TicketForm.tsx` — controlled form for create/edit (title required, description optional), validation errors displayed, calls onSubmit prop. Works for both new ticket and edit.
- [ ] T039 [P] [FRONTEND] [US1] Implement `frontend/src/api/tickets.ts` — `createTicket(projectId, data)`, `createFollowUp(parentId, data)`, `getTicket(id)`, `updateTicket(id, data)`, `deleteTicket(id)` using `client.ts`.
- [ ] T040 [FRONTEND] [US1] Implement `frontend/src/components/tickets/TicketCard.tsx` — display ticket title, status badge, assignee avatars/names, follow-up count. Links to ticket detail page.

### Tests for User Story 1

- [ ] T041 [P] [TEST] [US1] Write contract tests for ticket CRUD endpoints in `backend/tests/contract/test_tickets.py` — test: 201 on create, 200 on get, 200 on patch, 204 on delete, 409 on delete with follow-ups, 404 on deleted ticket GET, 403 on edit by non-creator.
- [ ] T042 [P] [TEST] [US1] Write integration tests for TicketService in `backend/tests/integration/test_ticket_service.py` — test: create emits ticket.created event, delete blocked by follow-up, delete emits ticket.deleted event, update emits ticket.updated event with correct prev/new state.

**Checkpoint**: User Story 1 independently functional and testable.

---

## Phase 4: User Story 2 — Ticket Assignment and Per-Assignee Progress (Priority: P1)

**Goal**: Tickets assigned to multiple users; each assignee submits their own progress
record; prior records preserved after unassignment.

**Independent Test**: Assign a ticket to two users, each submits a progress update,
view ticket — two separate records shown. Unassign one user — their record remains
visible in history.

### Implementation for User Story 2

- [ ] T043 [P] [BACKEND] [US2] Implement `backend/src/schemas/assignment.py` — AssignRequest, AssignmentResponse (ticket_id, user_id, assigned_at).
- [ ] T044 [P] [BACKEND] [US2] Implement `backend/src/schemas/progress.py` — ProgressUpdateRequest (content), ProgressUpdateResponse, ProgressListResponse.
- [ ] T045 [BACKEND] [US2] Implement `AssignmentService.assign_user(session, ticket_id, user_id, actor)` in `backend/src/services/assignment_service.py` — verify ticket exists, verify user exists, check not already assigned (409), insert TicketAssignment row, emit `ticket.assigned` event.
- [ ] T046 [BACKEND] [US2] Implement `AssignmentService.unassign_user(session, ticket_id, user_id, actor)` — verify assignment exists, delete row (hard delete), emit `ticket.unassigned` event. Must NOT delete corresponding progress_update record.
- [ ] T047 [BACKEND] [US2] Implement `ProgressService.submit_update(session, ticket_id, user_id, content)` in `backend/src/services/progress_service.py` — verify caller is active assignee (403 otherwise), upsert progress_updates row on UNIQUE(ticket_id, user_id), emit `ticket.progress_updated` event with prev content (null on first submission).
- [ ] T048 [BACKEND] [US2] Implement `POST /api/v1/tickets/{id}/assignments` and `DELETE /api/v1/tickets/{id}/assignments/{user_id}` in `backend/src/api/v1/assignments.py` — assignment requires caller to be creator, existing assignee, or admin.
- [ ] T049 [BACKEND] [US2] Implement `GET /api/v1/tickets/{id}/progress` (list all) and `PUT /api/v1/tickets/{id}/progress` (caller's own) in `backend/src/api/v1/progress.py`.
- [ ] T050 [FRONTEND] [US2] Implement `frontend/src/components/tickets/AssigneeProgressList.tsx` — renders one row per assignee: name, has_progress_update indicator, progress content (if any). Used in TicketDetailPage.
- [ ] T051 [FRONTEND] [US2] Extend `frontend/src/api/tickets.ts` — `assignUser(ticketId, userId)`, `unassignUser(ticketId, userId)`, `listProgress(ticketId)`, `submitProgress(ticketId, content)`.

### Tests for User Story 2

- [ ] T052 [P] [TEST] [US2] Write contract tests in `backend/tests/contract/test_assignments.py` — test: assign 201, unassign 204, duplicate assign 409, unassign preserves progress records, progress PUT 200 (upsert), GET progress lists all assignees.
- [ ] T053 [P] [TEST] [US2] Write integration tests in `backend/tests/integration/test_progress_service.py` — test: submit_update emits progress_updated with null prev on first submit, emits prev content on update, unassign leaves progress record intact.

**Checkpoint**: User Stories 1 AND 2 both independently testable.

---

## Phase 5: User Story 3 — Status Transitions and Workflow Rules (Priority: P2)

**Goal**: Assigned users move tickets through defined statuses. All assignees must have
submitted progress updates before any transition is permitted (FR-008a).

**Independent Test**: Assign ticket to two users. Attempt transition with only one
progress update — blocked (422 with missing user list). Submit second update —
transition succeeds. Attempt invalid transition (e.g. OPEN → DONE) — blocked (409).

### Implementation for User Story 3

- [ ] T054 [BACKEND] [US3] [SECURITY-CRITICAL] Implement `WorkflowService.transition(session, ticket_id, to_status, actor)` in `backend/src/services/workflow_service.py` — (1) call `validate_transition()` (raises 409 on invalid path), (2) load all active assignments for ticket, (3) load all progress_updates for ticket, (4) if any assignee is missing a progress record, emit `ticket.transition_blocked` event and raise 422 with `TransitionBlockedError` listing missing user IDs and emails, (5) otherwise update ticket.status, emit `ticket.status_changed` event with prev/new state. All steps in a single DB transaction.
- [ ] T055 [BACKEND] [US3] Implement `backend/src/schemas/transition.py` — TransitionRequest (to_status), TransitionBlockedError (detail, missing_updates list of {user_id, email}) per `contracts/openapi.yaml`.
- [ ] T056 [BACKEND] [US3] Implement `POST /api/v1/tickets/{id}/transitions` in `backend/src/api/v1/transitions.py` — require `get_current_user`, verify caller is active assignee (403 otherwise), call WorkflowService.transition(), return updated TicketResponse on 200, TransitionBlockedError on 422.
- [ ] T057 [FRONTEND] [US3] Implement `frontend/src/components/tickets/StatusTransitionButton.tsx` — renders available next statuses as buttons (from WORKFLOW_TRANSITIONS), calls transition API, on 422 renders a list of assignees who have not submitted progress updates, on 409 shows "Invalid transition" message.
- [ ] T058 [FRONTEND] [US3] Extend `frontend/src/api/tickets.ts` — `transitionTicket(ticketId, toStatus): Promise<TicketResponse | TransitionBlockedError>`.

### Tests for User Story 3

- [ ] T059 [P] [TEST] [US3] Write contract tests in `backend/tests/contract/test_transitions.py` — test: 200 on valid transition with all progress submitted, 422 on missing progress (lists correct missing users), 409 on invalid workflow path (e.g. OPEN→DONE), 403 for non-assignee caller.
- [ ] T060 [P] [TEST] [US3] Write integration tests in `backend/tests/integration/test_workflow_service.py` — test: transition emits `ticket.status_changed` event, blocked transition emits `ticket.transition_blocked` event, CLOSED is terminal (no transition from CLOSED), transaction rollback on gate failure.
- [ ] T061 [SECURITY] [SECURITY-CRITICAL] [US3] Security architect: review T054 and T056 — verify transition gate cannot be bypassed by race condition (concurrent assignee removal), confirm RBAC check prevents non-assignee from transitioning. Post result to Brainstorm channel.

**Checkpoint**: User Stories 1, 2, and 3 all independently testable.

---

## Phase 6: User Story 4 — Auditable Activity History (Priority: P2)

**Goal**: Every ticket action is recorded; any authenticated user can view the full
chronological history with actor identity and timestamp.

**Independent Test**: Create ticket, assign it, submit progress update, transition
status — then fetch GET /api/v1/tickets/{id}/events and verify 4+ entries in
chronological order with correct event_types and actor info.

### Implementation for User Story 4

- [ ] T062 [P] [BACKEND] [US4] Implement `backend/src/schemas/event.py` — TicketEventResponse, EventListResponse per `contracts/openapi.yaml`. Actor must be a UserSummary (id, email, role).
- [ ] T063 [BACKEND] [US4] Implement `GET /api/v1/tickets/{id}/events` in `backend/src/api/v1/events.py` — paginated (page, page_size), ordered by `occurred_at ASC`, apply `get_current_user` dependency.
- [ ] T064 [BACKEND] [US4] Audit all service files (ticket_service.py, assignment_service.py, progress_service.py, workflow_service.py) — verify every method listed in the data-model.md event catalogue emits the correct event type with correct prev_state and new_state. Fix any gaps.
- [ ] T065 [FRONTEND] [US4] Implement `frontend/src/components/tickets/TicketEventHistory.tsx` — chronological list of events: event_type label, actor name, `occurred_at` formatted as relative time (e.g. "2 hours ago") with absolute time on hover. Empty state when no events.
- [ ] T066 [FRONTEND] [US4] Implement `frontend/src/pages/TicketDetailPage.tsx` — assemble full ticket detail: TicketCard header, AssigneeProgressList, StatusTransitionButton, TicketEventHistory. Use React Query for data fetching.

### Tests for User Story 4

- [ ] T067 [TEST] [US4] Write contract tests in `backend/tests/contract/test_events.py` — test: GET events returns chronological list, all 8 event types appear when triggered, each event has actor id/email/role and occurred_at, pagination works (page/page_size).

**Checkpoint**: All P1 and P2 user stories independently testable.

---

## Phase 7: User Story 5 — Project Ticket Overview and Discovery (Priority: P3)

**Goal**: Team members browse all project tickets with status and assignee visible,
filter by status or assignee.

**Independent Test**: Create 5 tickets with varying statuses and assignees, open the
project view, apply status filter "IN_PROGRESS" — only matching tickets shown.

### Implementation for User Story 5

- [ ] T068 [BACKEND] [US5] Implement `GET /api/v1/projects/{project_id}/tickets` with optional query params `status` (TicketStatus enum) and `assignee_id` (UUID) in `backend/src/api/v1/projects.py`. Filter on `WHERE deleted_at IS NULL` always. Paginate with page/page_size.
- [ ] T069 [BACKEND] [US5] Implement `GET /api/v1/projects` (list all projects) in `backend/src/api/v1/projects.py` — returns ProjectSummary list.
- [ ] T070 [FRONTEND] [US5] Implement `frontend/src/components/common/FilterBar.tsx` — status dropdown (all TicketStatus values + "All"), assignee dropdown (populated from ticket data), emits onChange with current filter state.
- [ ] T071 [FRONTEND] [US5] Implement `frontend/src/components/projects/ProjectTicketList.tsx` — renders list of TicketCards, accepts filters, passes to React Query. Shows empty state when no tickets match.
- [ ] T072 [FRONTEND] [US5] Implement `frontend/src/pages/ProjectPage.tsx` — loads project info, renders ProjectTicketList with FilterBar. Clicking a ticket navigates to TicketDetailPage.

### Tests for User Story 5

- [ ] T073 [TEST] [US5] Write component tests for FilterBar and ProjectTicketList in `frontend/tests/components/` — test: FilterBar onChange fires with correct values, ProjectTicketList renders correct count, empty state shown when no results.

**Checkpoint**: All user stories independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Operational readiness, CI/CD, final quality gates.

- [ ] T074 [P] [TEST] Write frontend component tests for TicketForm (validation), TicketCard (states), StatusTransitionButton (blocked/unblocked states) in `frontend/tests/components/`
- [ ] T075 [P] [TEST] Write frontend page tests for LoginPage (submit, error state) and TicketDetailPage (loading/error/success states) in `frontend/tests/pages/`
- [ ] T076 [PLATFORM] Write GitHub Actions CI workflow in `.github/workflows/ci.yml` — stages: (1) backend: lint (ruff), type-check (mypy), unit+contract+integration tests (pytest), (2) frontend: type-check (tsc), lint (eslint), test (vitest), build (vite build), (3) run on every PR and push to main
- [ ] T077 [P] [PLATFORM] Write `docker-compose.yml` at repo root — services: postgres:15, backend (uvicorn), frontend (vite dev or nginx). Include env_file, health checks, depends_on.
- [ ] T078 [P] [PLATFORM] Write `backend/scripts/seed_dev.py` — inserts: 1 admin user (admin@example.com / admin123), 1 regular user (user@example.com / user123), 1 project, 3 tickets in various statuses.
- [ ] T079 [OPS] Write `devops/runbook.md` — covers: /health and /ready probe behavior, JWT token expiry and refresh flow, how to revoke all sessions for a user, how to diagnose missing transition (check progress_updates table), structured log field reference.
- [ ] T080 [P] [TEST] Autotester: produce acceptance criteria verification report at `devops/qa-report.md` — trace each acceptance scenario from spec.md (US1–US5) to a passing test or explicit gap note.
- [ ] T081 [SECURITY] [SECURITY-CRITICAL] Security architect: final threat model and security review of complete implementation at `devops/security-review.md` — cover: IDOR on ticket/event endpoints, event store tamper resistance, SQL injection (SQLAlchemy ORM), token revocation completeness. Post APPROVED or CHANGES REQUIRED.
- [ ] T082 [REVIEW] Code reviewer: end-to-end code review of all implementation phases — post final review decision. Block merge on any BLOCKER or unresolved MAJOR finding.
- [ ] T083 [P] [ARCH] Update `specs/001-ticket-management-system/quickstart.md` with any deviations from plan discovered during implementation (e.g. changed env var names, updated dependency versions, new setup steps).
- [ ] T084 [PM] Product manager: verify delivered behavior against all acceptance scenarios in spec.md. Post a release readiness note to the Brainstorm channel: GO / NO-GO / GO WITH RISKS.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No blockers — start immediately
- **Phase 2 (Foundational)**: Requires Phase 1 completion; T007–T014 sequential (migration order matters); T015–T023 can run in parallel after T007; T024–T028 parallel after T015
- **T029 (Security Gate)** and **T030 (Review Gate)**: Must pass before any Phase 3+ work begins
- **Phase 3 (US1)** and **Phase 4 (US2)**: Both require Phase 2 + gates; can run concurrently
- **Phase 5 (US3)**: Requires Phase 4 complete (workflow gate needs progress records)
- **Phase 6 (US4)**: Requires Phases 3–5 complete (all event types must exist)
- **Phase 7 (US5)**: Requires Phase 3 complete (ticket list endpoint built); parallelizable with US4
- **Phase 8 (Polish)**: Requires all user stories complete

### Parallel Opportunities

- Phase 1: T003–T006 all `[P]`
- Phase 2: T015, T017 parallel after T016; T024–T028 parallel after T018
- After gates pass: frontend agent (US1 frontend tasks) and backend agent (US1 backend tasks) run in parallel
- US3 and US4 phases can overlap once US2 is complete
- Phase 8: T074–T075, T076–T078 all parallel

---

## Implementation Strategy

### MVP First (User Stories 1–2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (pass T029 + T030 gates)
3. Complete Phase 3: US1 — verify ticket CRUD independently
4. Complete Phase 4: US2 — verify multi-assignee progress independently
5. **STOP and VALIDATE** — demo ticket lifecycle with progress records
6. Deploy MVP

### Full Delivery (All Stories)

1. MVP (above) → Phase 5: US3 (transitions)
2. Phase 6: US4 (activity history)
3. Phase 7: US5 (project overview)
4. Phase 8: Polish + final gates (T080–T084)

---

## Notes

- `[P]` = different files, no cross-task dependencies within the phase
- `[SECURITY-CRITICAL]` = do not merge downstream work until security-architect posts APPROVED
- `[REVIEW]` = do not proceed to next phase until code-reviewer posts decision
- All `[DATA]` migration tasks must run `alembic upgrade head` successfully before backend starts
- Event emission is **synchronous within the same DB transaction** as the state change — no async queue in v1
- `ticket_events` rows must never be UPDATEd or DELETEd by application code — enforce via code review
- Backend agents work from `./backend/` directory; frontend from `./frontend/`; devops from `./devops/`
