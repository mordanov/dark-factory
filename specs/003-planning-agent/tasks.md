# Tasks: Planning Agent for Prompt Studio

**Input**: Design documents from `specs/003-planning-agent/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/api.md ✅, quickstart.md ✅

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to
- All paths relative to `services/user-input-manager/` unless prefixed with `services/context-distiller/`

---

## Phase 1: Setup

**Purpose**: Database migration, config, and ContextDistiller endpoint — shared prerequisites

- [ ] T001 Write Alembic migration `backend/alembic/versions/0002_add_planning_agent.py` extending `session_status` enum with `planning|plan_ready|plan_confirmed|tickets_created`, creating `plan_status` enum (`draft|ready|confirmed|tickets_created|error`), and creating `prompt_plans` table per data-model.md
- [ ] T002 Add `PromptPlan` ORM model to `backend/src/models/models.py`; extend `SessionStatus` constants and `SESSION_STATUS_ENUM` with four new values; add `plan` relationship to `PromptSession`
- [ ] T003 [P] Add `PLANNING_MODEL`, `CONTEXT_DISTILLER_BASE_URL`, `CONTEXT_DISTILLER_TIMEOUT_SECONDS` settings to `backend/src/core/config.py`
- [ ] T004 [P] Add `PlanTask`, `PlanStory`, `PlanEpic`, `PlanContent`, `AgentOverride`, `AgentConfig`, `PlanResponse`, `PlanUpdateRequest`, `PlanStatusResponse` Pydantic schemas to `backend/src/schemas/schemas.py`
- [ ] T005 [P] Add two new endpoints to `services/context-distiller/src/api/v1/memory.py`: `POST /memory/{project_id}/agent-config` (upsert into `agent_configs` MongoDB collection) and `GET /memory/{project_id}/agent-config` (return doc or 404); add `AgentConfigStored` response schema to context-distiller schemas

**Checkpoint**: Migration, ORM model, schemas, config, and ContextDistiller endpoints ready

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core backend services and repository that ALL user stories depend on

**⚠️ CRITICAL**: Phase 3+ cannot start until this phase is complete

- [ ] T006 Implement `PlanRepository` in `backend/src/repositories/plan_repo.py` with methods: `get_by_session_id(session_id) → PromptPlan | None`, `create(session_id, plan_content, agent_config) → PromptPlan`, `update_content(plan, plan_content) → PromptPlan`, `update_status(plan, status, **kwargs) → PromptPlan`, `append_created_ticket(plan, local_id, tm_id) → PromptPlan`
- [ ] T007 [P] Implement `PlanValidator` pure function in `backend/src/services/planning/validator.py`: `validate_plan(data: dict) → tuple[PlanContent | None, list[str]]`; validate required keys at all levels, allowed `ticket_type` values, `depends_on` within-story references exist, no circular deps (DFS), story count ≤ 10, tasks per story ≤ 10, title ≤ 200 chars, description ≤ 500 chars
- [ ] T008 [P] Implement `TMPlanClient` in `backend/src/services/ticket_manager/plan_client.py` extending `TicketManagerClient` pattern; methods: `create_epic(project_id, epic) → str`, `create_story(project_id, story, epic_tm_id) → str`, `create_task(project_id, task, story_tm_id, dep_tm_ids) → str`; no `needs-estimation` tag; stories tagged `story`, tasks tagged `complexity-{S|M|L|XL}`
- [ ] T009 Implement `PlanningLLMService` in `backend/src/services/llm/planning_llm.py` with two async functions: `generate_plan(refined_prompt) → PlanContent` (OpenAI `json_object` format, validates via `PlanValidator`, retries once, raises `UpstreamError` after two failures) and `generate_agent_config(refined_prompt, plan, project_id) → AgentConfig | None` (uses `PLANNING_MODEL`, returns `None` on any failure — never raises)
- [ ] T010 Add `conftest.py` fixtures for planning tests in `backend/tests/conftest.py` (extend existing): async DB session for `PromptPlan`, mock `AsyncOpenAI`, mock `TicketManagerClient`, mock `httpx.AsyncClient` for ContextDistiller calls

**Checkpoint**: Repository, validator, TM client, LLM service, and test fixtures ready — user story work can now begin

---

## Phase 3: User Story 1 — Plan Generation (Priority: P1) 🎯 MVP

**Goal**: Session `approved` → user triggers generation → plan persisted and shown; browser-close-safe

**Independent Test**: `POST /sessions/{id}/plan` on an approved session returns 202; polling `GET /sessions/{id}/plan` eventually returns `status = "ready"` with a non-null `plan_content`; re-fetching after a new request still returns the same plan without regeneration.

- [ ] T011 [US1] Implement `PlanningService.generate(session_id, user_id)` in `backend/src/services/planning_service.py`: verify session `status == "approved"`, set session `status = "planning"`, call `PlanningLLMService.generate_plan()`, call `generate_agent_config()` (best-effort), validate via `PlanValidator`, create `PromptPlan` row via `PlanRepository`, set session `status = "plan_ready"`, return `PlanResponse`; on LLM/DB failure reset session to `approved`
- [ ] T012 [US1] Implement `POST /sessions/{session_id}/plan` endpoint in `backend/src/api/v1/planning.py`: require `status == "approved"`, call `PlanningService.generate()`, return 202; register router in `backend/src/main.py`
- [ ] T013 [P] [US1] Implement `GET /sessions/{session_id}/plan` endpoint in `backend/src/api/v1/planning.py`: fetch plan via `PlanRepository.get_by_session_id()`, return `PlanResponse` or 404 if no plan exists
- [ ] T014 [P] [US1] Write unit tests for `PlanningLLMService` in `backend/tests/unit/test_planning_llm.py`: test `generate_plan` with valid JSON response, with invalid JSON (retry path), with two failures (raises `UpstreamError`); test `generate_agent_config` with failure (returns None, does not raise)
- [ ] T015 [P] [US1] Write unit tests for `PlanValidator` in `backend/tests/unit/test_plan_validator.py`: valid plan passes, missing required fields fails, `depends_on` to non-existent task fails, circular dependency detected, story count > 10 fails, task count per story > 10 fails, title > 200 chars fails

**Checkpoint**: Plan generation and retrieval endpoints work end-to-end; plan is persisted before returning; session stays `approved` on failure

---

## Phase 4: User Story 2 — Plan Review and Edit (Priority: P2)

**Goal**: User can edit node titles/descriptions, delete Stories/Tasks; confirmation gate prevents TM calls before explicit confirm

**Independent Test**: `PUT /sessions/{id}/plan` with an edited `plan_content` returns 200 and updated plan; `DELETE` of a task is reflected; `POST /sessions/{id}/plan/confirm` transitions plan to `confirmed` without creating any TM tickets during the request.

- [ ] T016 [US2] Implement `PlanningService.update(session_id, user_id, plan_content)` in `backend/src/services/planning_service.py`: verify plan `status == "ready"`, validate via `PlanValidator`, call `PlanRepository.update_content()`, return updated `PlanResponse`; return 409 if not in `ready` state
- [ ] T017 [US2] Implement `PUT /sessions/{session_id}/plan` endpoint in `backend/src/api/v1/planning.py`: call `PlanningService.update()`, return 200 or 422 (validation errors) or 409 (wrong state)
- [ ] T018 [US2] Implement `PlanningService.confirm(session_id, user_id, background_tasks)` in `backend/src/services/planning_service.py`: verify plan `status == "ready"`, set plan `status = "confirmed"` and session `status = "plan_confirmed"`, add `_create_tickets(session_id)` to FastAPI `BackgroundTasks`, return immediately
- [ ] T019 [US2] Implement `POST /sessions/{session_id}/plan/confirm` endpoint in `backend/src/api/v1/planning.py` injecting `BackgroundTasks`; call `PlanningService.confirm()`, return 202

**Checkpoint**: Edit and confirm endpoints work; calling confirm returns 202 immediately; no TM tickets created by the confirm request itself

---

## Phase 5: User Story 3 — Ticket Creation Progress and Recovery (Priority: P3)

**Goal**: Tickets created Epic→Stories→Tasks in order with live progress polling; partial failure is retryable without duplicates

**Independent Test**: After confirm, `GET /sessions/{id}/plan/status` increments `created_count`; on full success `status = "tickets_created"`; simulating TM failure after 3 tickets: status endpoint shows partial count; retry confirm skips already-created tickets; no duplicates in TM.

- [ ] T020 [US3] Implement `PlanningService._create_tickets(session_id)` in `backend/src/services/planning_service.py`: background method that creates epic → each story → each story's tasks in order; before each TM call checks if `local_id` in `ticket_id_map` (skip if so); calls `PlanRepository.append_created_ticket()` immediately after each success; on full success sets plan `status = "tickets_created"` and session `status = "tickets_created"`; on partial failure records error in `validation_errors`, keeps `confirmed` state with `created_ticket_ids` populated for retry; calls `_store_agent_config()` after full success
- [ ] T021 [US3] Implement `PlanningService._store_agent_config(project_id, agent_config)` in `backend/src/services/planning_service.py`: `POST` to `CONTEXT_DISTILLER_BASE_URL/memory/{project_id}/agent-config` via `httpx.AsyncClient` with `CONTEXT_DISTILLER_TIMEOUT_SECONDS`; any exception logged only, never raised
- [ ] T022 [US3] Implement `PlanningService.get_creation_status(session_id, user_id)` in `backend/src/services/planning_service.py`: compute `total` = 1 + len(stories) + sum(task counts), `created_count` = len(`created_ticket_ids` or []), return `PlanStatusResponse`
- [ ] T023 [US3] Implement `GET /sessions/{session_id}/plan/status` endpoint in `backend/src/api/v1/planning.py`: call `PlanningService.get_creation_status()`, return `PlanStatusResponse`
- [ ] T024 [P] [US3] Write integration tests for `PlanningService` in `backend/tests/integration/test_planning_service.py`: test full generate→confirm→ticket creation flow with mocked TM and ContextDistiller; test partial failure retry (mock TM failure at task 3, verify `created_ticket_ids`, retry skips first 3, no duplicates); test `_store_agent_config` failure does not block ticket creation
- [ ] T025 [P] [US3] Write integration tests for `PlanRepository` in `backend/tests/integration/test_plan_repo.py`: test `create`, `update_content`, `update_status`, `append_created_ticket` (idempotent when same local_id called twice), `get_by_session_id`

**Checkpoint**: Full backend flow works end-to-end; retry is idempotent; agent config failure does not block

---

## Phase 6: User Story 4 — Frontend (Priority: P2/P3 combined)

**Goal**: Zustand store + API client + PlanningModal (4 states) + AgentConfigPanel + session detail update + i18n

**Independent Test**: Load session detail page for an `approved` session → "Generate Plan" button visible → click → modal shows generating overlay → polling shows plan tree → edit a title → click confirm → progress bar shows ticket count → success state with TM link shown.

- [ ] T026 [US2] [US3] Add `planningApi` to `frontend/src/api/client.ts`: `trigger`, `get`, `update`, `confirm`, `getStatus` methods per contracts/api.md; export `PlanResponse`, `PlanStatusResponse`, `PlanContent` TypeScript interfaces
- [ ] T027 [US1] [US2] [US3] Implement `planStore` in `frontend/src/store/planStore.ts` with state: `plan`, `planStatus`, `agentConfig`, `creationProgress`, `isGenerating`, `isConfirming`, `error`; actions: `triggerGeneration`, `fetchPlan`, `updateNode`, `confirmPlan`, `pollCreationStatus` (polls every 3s, auto-stops on `tickets_created` or `error`), `reset`
- [ ] T028 [US4] Implement `AgentConfigPanel` in `frontend/src/components/sessions/AgentConfigPanel.tsx`: collapsible (collapsed by default), shows table of agent name + override text, hidden entirely when `agentConfig` is null
- [ ] T029 [US1] [US2] [US3] [US4] Implement `PlanningModal` in `frontend/src/components/sessions/PlanningModal.tsx` with four visual states driven by Zustand store: **generating** (non-dismissable spinner), **ready** (plan tree — Epic at top, Stories collapsible with task count, Tasks nested; inline-editable titles/descriptions on click; type badge; complexity badge; depends_on chips read-only; "Regenerate" button top-right; `AgentConfigPanel` below tree; "Confirm plan & create tickets" primary; "Cancel" ghost), **confirming** (plan tree greyed, progress bar "Creating tickets: X / N", non-dismissable), **done** (success icon, ticket count, TM link in new tab, "Back to sessions" button); error state with "Retry" button and already-created tickets listed
- [ ] T030 [US1] [US2] Update `frontend/src/components/sessions/SessionDetailPage.tsx`: remove "Approve & create ticket" button and `ApproveModal` import; when `session.status === "approved"` show "Generate Plan" primary button that opens `PlanningModal` (auto-triggers generation on mount); when `session.status === "tickets_created"` show success banner with ticket count and TM link
- [ ] T031 [P] Delete `frontend/src/components/sessions/ApproveModal.tsx` entirely
- [ ] T032 [P] Add `"planning"` i18n key namespace to `frontend/src/i18n/en.json` and `frontend/src/i18n/ru.json` with all keys per planning-agent-specify-prompt.md (generate_plan, generating, generating_hint, plan_title, epic_label, story_label, task_label, complexity, depends_on, confirm_plan, regenerate, creating_tickets, tickets_created, view_in_tm, agent_config_title, agent_config_hint, retry_creation, cancel, error_generation, error_validation, error_creation)

**Checkpoint**: Full frontend flow works in browser; all four modal states reachable; i18n keys present in both locales

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, removal of old approve endpoint, final wiring, coverage, lint

- [ ] T033 Remove `POST /sessions/{session_id}/approve` endpoint from `backend/src/api/v1/sessions.py` and remove `approve_and_create_ticket` method from `backend/src/services/session_service.py`; remove `ApproveRequest` schema from `backend/src/schemas/schemas.py`; delete any tests that tested the removed endpoint
- [ ] T034 [P] Run backend linting across all modified files: `ruff check --fix backend/src/` and `ruff format backend/src/`; fix any remaining violations
- [ ] T035 [P] Run frontend linting: `npm run lint` in `services/user-input-manager/frontend`; fix any TypeScript or ESLint errors introduced
- [ ] T036 Verify backend test coverage ≥ 80%: `pytest --cov=src --cov-report=term-missing -q` in `backend/`; add targeted unit tests if coverage < 80% for `planning_service.py` or `validator.py`
- [ ] T037 [P] Validate the quickstart walkthrough: run `docker compose up --build`, apply migrations, create a session, trigger plan generation, confirm, verify TM tickets created per `specs/003-planning-agent/quickstart.md`
- [ ] T038 [P] Update `infra/.env.example` adding `PLANNING_MODEL`, `CONTEXT_DISTILLER_BASE_URL`, `CONTEXT_DISTILLER_TIMEOUT_SECONDS` with comments

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup (T001–T005) — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational completion (T006–T010)
- **US2 (Phase 4)**: Depends on US1 completion (confirmation gate builds on generation)
- **US3 (Phase 5)**: Depends on US2 completion (ticket creation uses confirmed state)
- **US4 Frontend (Phase 6)**: T026–T027 can start after Foundational; T028–T032 can run in parallel within Phase 6 after T026–T027 are done
- **Polish (Phase 7)**: Depends on Phases 3–6 complete

### User Story Dependencies

- **US1 (Plan Generation)**: No dependency on other user stories
- **US2 (Plan Edit/Confirm)**: Depends on US1 (plan must exist to edit/confirm)
- **US3 (Ticket Creation)**: Depends on US2 (confirm endpoint must exist)
- **US4 (Agent Config Panel)**: Backend-independent; depends on US1 for plan data to display

### Parallel Opportunities Within Each Phase

**Phase 1**: T002, T003, T004, T005 can run in parallel after T001 lands
**Phase 2**: T007, T008, T009, T010 can run in parallel after T006 starts; T006 must finish before Phase 3
**Phase 3**: T013, T014, T015 can run in parallel after T011–T012 land
**Phase 5**: T024, T025 can run in parallel after T020–T023 land
**Phase 6**: T028, T031, T032 can run in parallel; T029 requires T027; T030 requires T029

---

## Parallel Example: Phase 2 (Foundational)

```
Launch in parallel (all independent files):
  Task T007: PlanValidator in backend/src/services/planning/validator.py
  Task T008: TMPlanClient in backend/src/services/ticket_manager/plan_client.py
  Task T009: PlanningLLMService in backend/src/services/llm/planning_llm.py
  Task T010: conftest.py fixtures for planning tests

Then (depends on all above):
  Task T006: PlanRepository in backend/src/repositories/plan_repo.py
  (T006 can actually run in parallel too — all are independent)
```

## Parallel Example: Phase 6 (Frontend)

```
First (shared dependencies):
  Task T026: Add planningApi to frontend/src/api/client.ts
  Task T027: Implement planStore in frontend/src/store/planStore.ts

Then in parallel (all use T026+T027):
  Task T028: AgentConfigPanel.tsx
  Task T029: PlanningModal.tsx  (uses T028)
  Task T031: Delete ApproveModal.tsx
  Task T032: Add i18n keys to en.json and ru.json

Then (uses T028+T029):
  Task T030: Update SessionDetailPage.tsx
```

---

## Implementation Strategy

### MVP First (US1 Backend Only — ~12 tasks)

1. Complete Phase 1 (T001–T005)
2. Complete Phase 2 (T006–T010)
3. Complete Phase 3 (T011–T015)
4. **STOP and VALIDATE**: `POST /sessions/{id}/plan` → poll → get plan with valid tree
5. Plan is persisted; browser-close-safe confirmed

### Incremental Delivery

1. Setup + Foundational → T001–T010 → Backend infrastructure ready
2. US1 backend (T011–T015) → Plan generation API working
3. US2 backend (T016–T019) → Edit + confirmation gate working
4. US3 backend (T020–T025) → Full ticket creation with retry working
5. US4 frontend (T026–T032) → Full UI working
6. Polish (T033–T038) → Old endpoint removed, lint clean, coverage verified

### Total Task Count

38 tasks across 7 phases:
- Phase 1 Setup: 5 tasks
- Phase 2 Foundational: 5 tasks
- Phase 3 US1 (Plan Generation): 5 tasks
- Phase 4 US2 (Plan Edit/Confirm): 4 tasks
- Phase 5 US3 (Ticket Creation): 6 tasks
- Phase 6 US4 Frontend: 7 tasks
- Phase 7 Polish: 6 tasks

---

## Notes

- `[P]` tasks = different files, no blocking dependencies — safe to run in parallel
- `[Story]` label maps task to specific user story for traceability
- T033 (remove old approve endpoint) MUST happen; old `ApproveRequest` schema goes away too
- T005 touches a different service (`context-distiller`) — coordinate separately or in same PR
- Frontend paths: `frontend/src/` relative to `services/user-input-manager/`
- Backend paths: `backend/src/` relative to `services/user-input-manager/`
- T001 migration must run first (T002 ORM model depends on enum/table existing)
- Tests are included for critical logic (validator, LLM service, repository, service integration) per spec's 80% coverage requirement
