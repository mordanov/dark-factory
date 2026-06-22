---
description: "Task list for ContextDistiller service implementation"
---

# Tasks: ContextDistiller Service

**Input**: Design documents from `specs/001-context-distiller-service/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks are grouped by user story to enable independent implementation
and testing of each story.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding and configuration — must complete before any service code

- [x] T001 Create project directory structure: `src/api/v1/`, `src/core/`, `src/db/`, `src/models/`, `src/repositories/`, `src/schemas/`, `src/services/`, `src/workers/`, `tests/unit/`, `tests/integration/`
- [x] T002 Create `requirements.txt` with pinned versions: fastapi==0.111.1, uvicorn[standard]==0.30.1, sqlalchemy[asyncio]==2.0.31, asyncpg==0.29.0, alembic==1.13.2, pydantic[email]==2.8.2, pydantic-settings==2.3.4, python-jose[cryptography]==3.3.0, httpx==0.27.0, openai==1.35.13, motor==3.5.0, pymongo==4.8.0, PyYAML==6.0.1, pytest==8.3.2, pytest-asyncio==0.23.7, pytest-cov==5.0.0, anyio==4.4.0, mongomock-motor==0.0.21, respx==0.21.1
- [x] T003 [P] Create `src/core/config.py` with Pydantic Settings for all env vars: DATABASE_URL, MONGO_URL, MONGO_DB_NAME, JWT_SECRET_KEY, JWT_ALGORITHM, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TIMEOUT_SECONDS, TICKET_MANAGER_BASE_URL, TICKET_MANAGER_SERVICE_EMAIL, TICKET_MANAGER_SERVICE_PASSWORD, DISTILLER_MAX_MEMORY_TOKENS, DISTILLER_MEMORY_HISTORY_KEEP, WORKER_MAX_CONCURRENT_JOBS, WORKER_POLL_INTERVAL_SECONDS
- [x] T004 [P] Create `src/core/exceptions.py` with UpstreamError, NotFoundError, ConflictError, DistillationError custom exception classes
- [x] T005 [P] Create `src/core/security.py` — JWT decode/validate function using python-jose (HS256), raises 401 on invalid token, never issues tokens
- [x] T006 [P] Create `src/db/postgres.py` — async SQLAlchemy engine + AsyncSessionFactory + Base declarative, using DATABASE_URL from settings
- [x] T007 [P] Create `src/db/mongo.py` — Motor AsyncIOMotorClient singleton, get_mongo_db() dependency returning the configured database handle
- [x] T008 [P] Create `src/models/__init__.py` with local copies of `Job` and `AuditLog` ORM classes (mirror `../orchestrator/src/models/models.py` exactly — same table names, columns, enums)
- [x] T009 Create `.env.example` with all required env vars from `specs/001-context-distiller-service/quickstart.md`, `Dockerfile` with Python 3.12-slim base image and uvicorn entrypoint, `pytest.ini` with asyncio_mode=auto, and `.coveragerc` with `fail_under = 80`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure layers that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T010 Create `src/schemas/schemas.py` with all Pydantic DTOs: DistillRequest, JobEnqueuedResponse, JobStatusResponse, MemoryResponse, AdrCreate, AdrSummary, AdrListResponse, AdrCreatedResponse, AdrStatusUpdate, AdrStatusResponse, HealthResponse — matching `specs/001-context-distiller-service/data-model.md` Pydantic Schemas section
- [x] T011 Create `src/repositories/job_repo.py` with: `claim_distill_job()` (SELECT FOR UPDATE SKIP LOCKED, job_type='distill', status='pending'), `create_distill_job()`, `get_by_id()`, `mark_running()`, `mark_done()`, `mark_failed(error_message)` — using AsyncSession from `src/db/postgres.py`
- [x] T012 Create `src/repositories/audit_repo.py` with `get_audit_trail(ticket_id)` — SELECT from audit_log WHERE ticket_id=? ORDER BY created_at ASC, returns list of dicts
- [x] T013 Create `src/repositories/memory_repo.py` with: `get_memory(project_id)`, `archive_then_write(project_id, yaml_content, ticket_id)` (archive current → prune history to HISTORY_KEEP → upsert), `get_adrs(project_id, status_filter)`, `get_adr(project_id, adr_id)`, `create_adr(project_id, adr_data)`, `update_adr_status(project_id, adr_id, new_status)` — using Motor client from `src/db/mongo.py`; raise ConflictError on invalid status transition; raise ConflictError if content fields passed to update
- [x] T014 Create `src/api/dependencies.py` with: `get_db()` async session dependency, `get_mongo()` Motor db dependency, `get_current_user()` JWT decode dependency (raises 401 on invalid token using `src/core/security.py`)
- [x] T015 Create `tests/conftest.py` with fixtures: `test_app` (FastAPI test client), `mock_db_session` (SQLAlchemy in-memory via aiosqlite), `mock_mongo` (mongomock-motor), `mock_tm_client` (respx route mock for Ticket Manager API), `sample_job_payload` (valid distill job JSONB dict)

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — Distillation Job Runs After Ticket Closes (Priority: P1) 🎯 MVP

**Goal**: Worker picks up distill jobs, calls LLM, writes project memory to MongoDB

**Independent Test**: `POST /distill` → poll `GET /status/{job_id}` → `done` → `GET /memory/{project_id}` returns valid YAML with all required fields

### Implementation for User Story 1

- [x] T016 [P] [US1] Create `src/services/tm_client.py` — httpx AsyncClient wrapper for Ticket Manager API: `login()` service account JWT fetch, `get_ticket(ticket_id)` returning dict, `get_ticket_events(ticket_id)` returning list of dicts; raise UpstreamError on non-2xx responses
- [x] T017 [P] [US1] Create `src/services/data_collector.py` — `DataCollector.collect(ticket_id, project_id, db, mongo_db)`: fetch ticket from TM API, read audit_log rows via `audit_repo`, read current project_memory via `memory_repo`, read ADR ids+titles; return `CollectedContext` dataclass with all inputs; raise UpstreamError if TM API unreachable (do not degrade silently)
- [x] T018 [US1] Create `src/services/distiller.py` — `distill(context: CollectedContext, settings) -> str`: build LLM messages (system prompt from architecture.md + collected context), call `openai.AsyncOpenAI.chat.completions.create()` with `max_tokens=DISTILLER_MAX_MEMORY_TOKENS`, validate output with `yaml.safe_load()` checking all required keys present, retry up to 2 times on parse failure, raise DistillationError with raw output after 3rd failure (depends on T016, T017)
- [x] T019 [US1] Create `src/workers/job_worker.py` — `JobWorker` class: `start()` creates asyncpg LISTEN on `df_new_job` channel + initial `_sweep()`, `_sweep()` calls `claim_distill_job()` up to `WORKER_MAX_CONCURRENT_JOBS` times and spawns `asyncio.create_task(_run_job(job))` for each, `_run_job()` calls DataCollector → distiller → `memory_repo.archive_then_write()` → `mark_done()`; catches all exceptions → `mark_failed(str(exc))`; uses asyncio.Semaphore for concurrency control (depends on T016, T017, T018)
- [x] T020 [US1] Create `src/api/v1/distill.py` — `POST /distill` endpoint: validates DistillRequest, creates job row via `job_repo.create_distill_job()`, issues PG NOTIFY on `df_new_job`, returns `JobEnqueuedResponse(job_id=str(job.id))` with status 202; `GET /status/{job_id}` endpoint: fetches job by id via `job_repo.get_by_id()`, returns `JobStatusResponse`, raises 404 if not found (depends on T010, T011, T014)
- [x] T021 [US1] Create `src/main.py` — FastAPI app with lifespan (start `JobWorker` on startup, stop on shutdown), include `v1/distill` router, `GET /api/health` returning `HealthResponse(status="ok")`, global exception handlers for NotFoundError→404, ConflictError→409, UpstreamError→502 (depends on T019, T020)

**Checkpoint**: US1 fully functional — distill job runs end-to-end, memory written to MongoDB

---

## Phase 4: User Story 2 — Orchestrator Retrieves Project Memory (Priority: P1)

**Goal**: REST endpoints for reading current project memory and ADR list

**Independent Test**: Seed a known memory doc + ADRs in mongomock, call both endpoints, verify response shapes and filter behaviour

### Implementation for User Story 2

- [x] T022 [US2] Create `src/api/v1/memory.py` — four endpoints: `GET /memory/{project_id}` (calls `memory_repo.get_memory()`, returns MemoryResponse, raises 404 if absent); `GET /memory/{project_id}/adrs` with optional `?status=` param defaulting to `accepted` (calls `memory_repo.get_adrs()`, returns AdrListResponse); `POST /memory/{project_id}/adrs` (validates AdrCreate, calls `memory_repo.create_adr()`, returns AdrCreatedResponse 201); `PATCH /memory/{project_id}/adrs/{adr_id}/status` (validates AdrStatusUpdate, calls `memory_repo.update_adr_status()`, returns AdrStatusResponse, raises 404/409 as appropriate) (depends on T010, T013, T014)
- [x] T023 [US2] Register `v1/memory` router in `src/main.py` (depends on T021, T022)

**Checkpoint**: US1 + US2 fully functional — full read/write cycle of project memory is complete

---

## Phase 5: User Story 3 — ADR Creation and Immutability (Priority: P2)

**Goal**: Enforce write-once ADR content at the repository layer; status transitions only

**Independent Test**: Create ADR via `POST /adrs`, attempt content mutation → 409; perform status transition → 200; verify content unchanged

*Note*: ADR endpoints were implemented in T022 as part of US2 API surface. This phase covers the immutability guard and status transition validation in the repository layer, and adds targeted integration tests.

- [x] T024 [US3] Harden `src/repositories/memory_repo.py` — verify `update_adr_status()` raises ConflictError for invalid transitions (proposed→superseded is valid; accepted→proposed is invalid); add `_VALID_TRANSITIONS` constant; ensure `create_adr()` auto-increments ADR number by querying existing max; add guard in any update path that rejects non-status fields
- [x] T025 [P] [US3] Write `tests/unit/test_adr_repo.py` — unit tests for: ADR create with auto-increment NNN, duplicate _id raises error, valid status transitions succeed, invalid transitions raise ConflictError, content-field update raises ConflictError; use mongomock fixture from conftest.py

**Checkpoint**: ADR immutability fully enforced at the repository layer

---

## Phase 6: User Story 4 — History Archival and Rollback Visibility (Priority: P2)

**Goal**: Every memory overwrite archives the prior version; history pruned to HISTORY_KEEP

**Independent Test**: Run 3 distillations on same project, verify `project_memory_history` has 3 docs; set HISTORY_KEEP=2, run 4th distillation, verify only 2 history docs remain

- [x] T026 [US4] Harden `src/repositories/memory_repo.py` `archive_then_write()` — add explicit test that archive happens BEFORE upsert (use mongomock transaction simulation); add pruning query that deletes oldest history entries beyond HISTORY_KEEP; ensure version counter increments monotonically even on concurrent writes (use `$inc` on upsert)
- [x] T027 [P] [US4] Write `tests/unit/test_memory_repo.py` — unit tests for: first-ticket fresh start (no prior memory), archive-before-overwrite ordering, version increments, history pruned to HISTORY_KEEP after N+1 writes, concurrent write safety (two writes, latest version wins); use mongomock fixture

**Checkpoint**: History archival correct; rollback possible by reading `project_memory_history`

---

## Phase 7: User Story 5 — Graceful Failure and Job Observability (Priority: P3)

**Goal**: LLM failures produce visible failed jobs; Orchestrator not blocked; worker ready for next job

**Independent Test**: Mock LLM to return invalid YAML on all 3 attempts → verify job status=failed, error_message contains raw output, project_memory unchanged

- [x] T028 [P] [US5] Write `tests/unit/test_distiller.py` — unit tests for: valid YAML passes validation, missing required key raises DistillationError, invalid YAML raises DistillationError, retry count increments on each parse failure, max 2 retries then raises, LLM timeout raises UpstreamError immediately (no retry); mock openai client with respx or unittest.mock
- [x] T029 [US5] Write `tests/integration/test_distill_lifecycle.py` — integration tests for: full happy path (enqueue → worker runs → done → memory readable), idempotent re-distillation (same ticket twice, both succeed, no duplicate recent_changes), LLM failure → job failed → memory unchanged → worker accepts next job; use mock DB + mongomock + mock TM client + mock LLM (depends on T015, T019, T021)

**Checkpoint**: All 5 user stories independently functional and tested

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Integration tests for API surface, coverage enforcement, Docker validation

- [x] T030 [P] Write `tests/integration/test_memory_api.py` — integration tests for: `GET /memory/{id}` 200 with seeded doc, `GET /memory/{id}` 404, `GET /adrs?status=accepted` returns only accepted, `GET /adrs` default=accepted, `POST /adrs` 201 with correct adr_id, `PATCH /adrs/{id}/status` valid transition 200, `PATCH /adrs/{id}/status` invalid transition 409; use test_app + mongomock fixtures
- [x] T031 [P] Write `tests/integration/test_job_status.py` — integration tests for: `GET /status/{job_id}` 200 pending/running/done/failed, `GET /status/{unknown_id}` 404, failed job includes error field; use test_app + mock DB fixtures
- [x] T032 [P] Write `tests/unit/test_data_collector.py` — unit tests for: TM API success, TM API 404 raises UpstreamError, TM API unreachable raises UpstreamError, audit_log empty list proceeds without error, missing project_memory returns None (fresh start); mock httpx with respx
- [x] T033 Run `pytest tests/ --cov=src --cov-report=term-missing` and fix any modules below 80% coverage threshold enforced by `.coveragerc`
- [x] T034 Validate `docker build .` succeeds from `context-distiller/` root and `GET /api/health` returns 200 in the built image
- [x] T035 [P] Update `specs/001-context-distiller-service/quickstart.md` with any corrections discovered during implementation (actual Docker Compose snippet, corrected env var names, final endpoint URLs)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on all of Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on US2–US5
- **US2 (Phase 4)**: Depends on Phase 2 — no dependency on US1 (memory_repo already built in T013)
- **US3 (Phase 5)**: Depends on US2 (ADR endpoints in T022) — hardens T013 + T022
- **US4 (Phase 6)**: Depends on Phase 2 (memory_repo in T013) — independent of US1–US3
- **US5 (Phase 7)**: Depends on US1 (worker in T019) — tests the failure path of the worker
- **Polish (Phase 8)**: Depends on all user stories complete

### User Story Internal Dependencies

```
US1: T016 (tm_client) → T017 (data_collector) → T018 (distiller) → T019 (worker) → T020 (API) → T021 (main)
US2: T022 (memory API) → T023 (register router in main)
US3: T024 (harden repo) [parallel: T025 unit tests]
US4: T026 (harden archive_then_write) [parallel: T027 unit tests]
US5: T028 (unit tests) → T029 (integration test)
```

### Parallel Opportunities Within Each Phase

```bash
# Phase 1 — all [P] tasks run together after T001+T002 complete:
T003 (config.py)  T004 (exceptions.py)  T005 (security.py)
T006 (postgres.py)  T007 (mongo.py)  T008 (models copy)

# Phase 3 — TM client and data_collector can start together:
T016 (tm_client)  T017 (data_collector)  [both [P]]

# Phase 5 — repo hardening + unit tests:
T024 (repo harden)  T025 (unit tests)  [T025 [P]]

# Phase 6 — archive hardening + unit tests:
T026 (archive harden)  T027 (unit tests)  [T027 [P]]

# Phase 7 — unit tests can start immediately:
T028 (unit tests)  [T028 [P]]

# Phase 8 — API integration tests + job status tests run together:
T030 (memory API tests)  T031 (job status tests)  T032 (data_collector tests)
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 — both P1)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: US1 (distillation end-to-end)
4. Complete Phase 4: US2 (memory retrieval)
5. **STOP and VALIDATE**: Run quickstart.md verification checklist
6. At this point the service is fully functional for the Orchestrator integration

### Incremental Delivery

1. Setup + Foundational → infra ready
2. US1 + US2 → full read/write cycle working (MVP)
3. US3 → ADR immutability hardened
4. US4 → history archival reliable
5. US5 → failure observability complete
6. Polish → coverage enforced, Docker validated

### Parallel Team Strategy

With two developers after Phase 2 is complete:
- Developer A: US1 (T016–T021) — distillation worker
- Developer B: US2 (T022–T023) — memory retrieval API

US3, US4, US5 can follow in any order — all unblock after Phase 2.

---

## Notes

- `[P]` = different files, no dependency on incomplete sibling tasks — safe to run in parallel
- `[USN]` label maps task to user story for traceability
- Test tasks use `mongomock-motor` — never a shared real MongoDB in CI
- LLM calls must be mocked in all tests (`respx` for httpx, `unittest.mock` for `openai`)
- Jobs table schema is owned by the Orchestrator — never add migrations for shared tables
- ADR content is write-once — enforce at repository layer, not just API layer
- Commit after each phase checkpoint
