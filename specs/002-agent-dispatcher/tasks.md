---

description: "Task list for Agent Dispatcher service implementation"
---

# Tasks: Agent Dispatcher Service

**Input**: Design documents from `/specs/002-agent-dispatcher/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/api.md ✅, research.md ✅

**Tests**: Test tasks are included — the spec requires ≥ 80% coverage and explicitly lists unit and integration test cases.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Paths are relative to `services/agent-dispatcher/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Service scaffold, configuration, and database plumbing. No user story work can begin until this phase is complete.

- [ ] T001 Create full directory structure: `src/core/`, `src/db/`, `src/models/`, `src/schemas/`, `src/repositories/`, `src/services/runner/`, `src/workers/`, `src/api/v1/`, `prompts/`, `tests/unit/`, `tests/integration/`, `alembic/versions/`
- [ ] T002 Create `Dockerfile` with `python:3.12-slim` base image, non-root user `appuser`, working dir `/app`
- [ ] T003 [P] Create `docker-compose.yml` for standalone dev (Postgres 16 + service)
- [ ] T004 [P] Create `requirements.txt` with canonical monorepo versions: fastapi=0.115.5, uvicorn=0.32.1, sqlalchemy=2.0.36, asyncpg=0.30.0, alembic=1.14.0, pydantic=2.10.3, pydantic-settings=2.6.1, python-jose=3.3.0, passlib=1.7.4, httpx=0.28.0, openai=1.57.0, pytest=8.3.4, pytest-asyncio=0.24.0, pytest-cov=6.0.0, ruff=0.8.3
- [ ] T005 [P] Create `.pre-commit-config.yaml` at service root with ruff lint+format hooks pinned to ruff=0.8.3
- [ ] T006 [P] Create `pytest.ini` with asyncio_mode=auto and testpaths for unit and integration
- [ ] T007 [P] Create `.coveragerc` with source=src, omit patterns for migrations and `__init__.py`
- [ ] T008 [P] Create placeholder prompt files in `prompts/`: `backend.md`, `software_architect.md`, `security_architect.md`, `project_manager.md`, `frontend.md`, `designer.md`, `code_reviewer.md`, `autotester.md`, `devops.md`, `project_administrator.md` (each with a one-line placeholder; do not overwrite if files already exist)
- [ ] T009 Create `src/core/config.py`: Pydantic Settings with all env vars from the constitution table; `agent_timeout_for(agent_id)` method reading `AGENT_TIMEOUT_{ID_UPPER}` with fallback to `AGENT_TIMEOUT_DEFAULT`; `brainstorm_agents_list` property splitting `BRAINSTORM_AGENTS` by comma
- [ ] T010 [P] Create `src/core/exceptions.py`: `AppError`, `PromptNotFoundError`, `AgentRunConflictError`, `OrchestratorError`, `TMCommentError`
- [ ] T011 [P] Create `src/core/security.py`: `create_service_token()` generating HS256 JWT with `sub=service:agent-dispatcher`; `verify_access_token(token)` for incoming Bearer validation
- [ ] T012 [P] Create `src/core/auth_adapter.py`: `AuthAdapter` class with `async verify(token)`, supporting `AUTH_MODE=local` (calls `verify_access_token`) and `keycloak` (raises `NotImplementedError`) — mirrors `services/orchestrator/src/core/auth_adapter.py`
- [ ] T013 Create `src/db/session.py`: async SQLAlchemy engine from `DATABASE_URL`, `AsyncSessionLocal`, `get_db` FastAPI dependency yielding `AsyncSession`
- [ ] T014 Create `alembic.ini` and `alembic/env.py` targeting `df_dispatcher` database with async engine support
- [ ] T015 Create `src/models/models.py`: `agent_run_status` enum, `AgentRun` ORM model (table `agent_runs`), `BrainstormSession` ORM model (table `brainstorm_sessions`) — exact schema from `data-model.md`
- [ ] T016 Create Alembic migration `alembic/versions/0001_create_agent_dispatcher_tables.py`: creates `agent_run_status` enum, `agent_runs` table with indexes, `brainstorm_sessions` table with indexes, NOTIFY trigger `trg_notify_new_agent_run` on `agent_runs`
- [ ] T017 Create `src/schemas/schemas.py`: `AgentResult`, `AgentContext`, `AgentRunResponse`, `AgentRunListResponse`, `BrainstormSessionResponse` — exact field definitions from `data-model.md`
- [ ] T018 Create `tests/conftest.py`: async test database engine (`df_dispatcher_test`), `db_session` fixture with rollback, `mock_settings` fixture, base async client fixture for FastAPI app

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core repositories, parsers, and startup recovery that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T019 Create `src/repositories/run_repo.py`: `AgentRunRepository` with async methods: `create()`, `get_by_id()`, `has_running()`, `mark_running()`, `mark_done()`, `mark_failed()`, `mark_needs_review()`, `sweep_orphaned_running()` (bulk-updates all `running` rows to `needs_review` with `error_message="Service restarted; run orphaned"`, returns list of affected `ticket_id` values), `list_all()`
- [ ] T020 Create `src/repositories/brainstorm_repo.py`: `BrainstormSessionRepository` with async methods: `get_or_create()`, `increment_round()`, `conclude()`
- [ ] T021 Create `src/services/result_parser.py`: pure function `parse_result(stdout: str) -> AgentResult`; extracts last `[RESULT]...[/RESULT]` block; graceful fallback to `needs_review` + `tm_comment=stdout[:2000]` on any failure; never raises
- [ ] T022 [P] Write unit tests `tests/unit/test_result_parser.py`: valid block → correct `AgentResult`; missing block → `needs_review` + `stdout[:2000]`; invalid JSON → graceful fallback; block with trailing text → correct extraction; `brainstorm_consensus: "agreed"` parsed correctly; extra unknown fields ignored
- [ ] T023 Write integration tests `tests/integration/test_run_repo.py`: create → `mark_running` → `mark_done` lifecycle; `has_running` returns true for `running` / false for `completed`; `list_all` filters by `ticket_id` and by `status`; `sweep_orphaned_running` updates all `running` rows and returns their `ticket_id` values; `sweep_orphaned_running` is a no-op when no `running` rows exist
- [ ] T024 Write integration tests `tests/integration/test_brainstorm_repo.py`: `get_or_create` creates on first call, returns existing on second; `increment_round` increments `current_round`; `conclude` sets `status=concluded` and `consensus`
- [ ] T025 Implement startup orphan sweep in `src/main.py` lifespan startup handler: call `AgentRunRepository.sweep_orphaned_running(db)`; for each returned `ticket_id` call `Reporter.report_result()` with `AgentResult(status="needs_review", tm_comment="Service restarted; run orphaned")`; log count at INFO level; execute before `DispatchWorker` starts

**Checkpoint**: Foundation ready — repositories, parser, and restart recovery in place. User story work can now begin.

---

## Phase 3: User Story 1 — Automatic Agent Execution (Priority: P1) 🎯 MVP

**Goal**: Poll for assigned tickets, execute single agent, persist results, notify TM + Orchestrator.

**Independent Test**: Create a ticket with `assigned_agent = "backend"` via the Orchestrator. Within `POLL_INTERVAL_SECONDS + 5s` a run record appears in `agent_runs` with `status = running`. After mock agent exits with valid `[RESULT]`, record transitions to `completed`, TM comment is posted, Orchestrator job is triggered.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T026 [P] [US1] Write unit tests `tests/unit/test_context_builder.py`: all sections present when all services respond; missing project memory → empty section, no error; missing ADRs → empty section; agent config override applied; SERVICE_JWT present in context text but absent from `context_snapshot` dict; `CONTEXT_MAX_TOKENS` truncation applied; "## Completion and Metrics Reporting" section present with correct `report-task-metrics.sh` invocation and brainstorm `task-metrics` message template
- [ ] T027 [P] [US1] Write integration tests `tests/integration/test_poller.py` (mocked Orchestrator httpx client): returns only tickets with `assigned_agent` set; filters out tickets where `has_running=True`; handles Orchestrator 503 gracefully (returns empty list, no exception)
- [ ] T028 [US1] Write integration tests `tests/integration/test_dispatcher_service.py` (mocked runners and reporter): single agent run — context built, runner called, result parsed, reporter called; missing prompt file → run marked `failed`, reporter called; runner returns non-zero exit → run marked `failed`, reporter called

### Implementation for User Story 1

- [ ] T029 Create `src/services/runner/base.py`: `AgentRunner` ABC with `async run(agent_id, system_prompt, context, timeout_seconds) -> tuple[int, str]`; runner factory function `get_runner() -> AgentRunner` returning `ClaudeCodeRunner` or `ApiRunner` based on `AGENT_RUNNER_MODE`
- [ ] T030 [P] Create `src/services/runner/claude_code.py`: `ClaudeCodeRunner(AgentRunner)` using `asyncio.create_subprocess_exec`; flags `--print`, `--mcp-config {CLAUDE_MCP_CONFIG_PATH}`, `--system-prompt`; context as positional arg; `asyncio.wait_for(proc.communicate(), timeout_seconds)`; kill subprocess on timeout, return `(-1, captured_so_far)`; reads `CLAUDE_CODE_PATH`
- [ ] T031 [P] Create `src/services/runner/api_runner.py`: `ApiRunner(AgentRunner)` using `openai.AsyncOpenAI`; messages array `[{"role":"system",...},{"role":"user",...}]`; model from `OPENAI_MODEL`; returns `(0, response_text)` on success, `(-1, error_str)` on `openai.APIError`
- [ ] T032 Create `src/services/context_builder.py`: `async build_context(ticket, agent_id, agent_briefing, brainstorm_session=None) -> str`; fetches project memory, ADRs, agent config from ContextDistiller (5s timeout each, fail-silent on any error); generates service JWT via `create_service_token()`; assembles markdown document per `contracts/api.md` Context Building Contract; includes "## Completion and Metrics Reporting" section with `report-task-metrics.sh` call template and brainstorm `task-metrics` message template; returns `context_for_agent` string only — does NOT include SERVICE_JWT in the `AgentContext` schema used for DB storage
- [ ] T033 Create `src/services/reporter.py`: `async report_result(ticket_id, project_id, result: AgentResult) -> None`; POST TM comment (log and continue on failure); POST Orchestrator trigger (retry once, raise `OrchestratorError` on second failure); uses service JWT from `create_service_token()`
- [ ] T034 Create `src/services/poller.py`: `async poll_once(db: AsyncSession) -> list[TmTicket]`; GET `{ORCHESTRATOR_BASE_URL}/api/v1/jobs/pending-tickets` with service JWT; parse response into `list[TmTicket]`; filter to `assigned_agent is not None`; filter out tickets with `has_running=True`; return empty list on any HTTP or parse error (log warning)
- [ ] T035 Create `src/services/dispatcher_service.py`: `async process_ticket(ticket, db)` — `has_running` double-run guard; load prompt file, fail gracefully with `mark_failed` if missing; build context via `context_builder`; `AgentRunRepository.create()` with `context_snapshot` (SERVICE_JWT stripped); `mark_running()`; call `runner.run()` with agent timeout; parse result; call appropriate `mark_*` method; call `reporter.report_result()`
- [ ] T036 Create `src/workers/dispatch_worker.py`: `DispatchWorker` with `asyncio.Semaphore(WORKER_MAX_CONCURRENT_RUNS)`; `async start()` polling loop: `poll_once()` → dispatch each ticket as `asyncio.create_task(process_ticket(...))` under semaphore → `asyncio.sleep(POLL_INTERVAL_SECONDS)`; `async stop()` cancels loop task
- [ ] T037 Create `src/api/v1/runs.py`: `GET /api/v1/runs` with query params `ticket_id`, `status`, `offset`, `limit`; `GET /api/v1/runs/{run_id}` with `raw_output` included; both protected by `AuthAdapter.verify()` via FastAPI `Depends`
- [ ] T038 Create `src/main.py`: FastAPI app with lifespan (startup: run orphan sweep T025 then start `DispatchWorker`; shutdown: stop worker); include `runs` router at prefix `/api/v1`; `GET /api/health` returning `{"status":"ok","runner_mode":"..."}` (no auth); `AppError` exception handler returning 400/500 with detail; CORS from `CORS_ALLOW_ORIGINS`

**Checkpoint**: User Story 1 fully functional — single agent runs detected, executed, and reported. Orphaned records resolved on restart.

---

## Phase 4: User Story 2 — Graceful Failure Handling (Priority: P2)

**Goal**: Timeouts, missing prompt files, and unparseable output all handled without crashes. Every failure case posts a TM comment and triggers Orchestrator.

**Independent Test**: Mock the runner to return stdout with no `[RESULT]` block. Dispatcher records `needs_review`, posts raw stdout (≤ 2000 chars) as TM comment, triggers Orchestrator. No exception propagates to the polling loop.

### Tests for User Story 2

- [ ] T039 [P] [US2] Extend `tests/integration/test_dispatcher_service.py`: runner timeout → `timed_out` status, TM comment posted, Orchestrator triggered; missing prompt file → `failed` status, TM comment posted; runner exits non-zero → `failed` status; run with no `[RESULT]` block → `needs_review`, `tm_comment = stdout[:2000]`
- [ ] T040 [P] [US2] Add runner-level unit tests `tests/unit/test_runners.py` (mocked subprocess and httpx): `ClaudeCodeRunner` success with valid exit code; timeout kills subprocess, returns `(-1, captured)`; subprocess OSError on start returns `(-1, error_str)`; `ApiRunner` success returns `(0, text)`; `ApiRunner` `openai.APIError` returns `(-1, error_str)`

### Implementation for User Story 2

- [ ] T041 [US2] Add timeout handling to `src/services/dispatcher_service.py`: wrap `runner.run()` in `asyncio.wait_for(timeout_seconds + 5)`; on `asyncio.TimeoutError` call `mark_failed(run_id, "Timed out")`, set status `timed_out` explicitly, call reporter, return without raising
- [ ] T042 [US2] Add missing prompt guard in `src/services/dispatcher_service.py`: check `prompt_path.exists()` before creating run record; if missing, create a `failed` run record immediately, call reporter with `AgentResult(status="needs_review", tm_comment=f"No prompt for agent '{agent_id}'")`, return
- [ ] T043 [US2] Verify `result_parser` fallback in `src/services/result_parser.py`: confirm that stdout > 2000 chars is truncated to exactly 2000 chars in `tm_comment` when no `[RESULT]` block found (add assertion to T022 if not already present)
- [ ] T044 [US2] Add task-level error isolation in `src/workers/dispatch_worker.py`: wrap `process_ticket` coroutine in `try/except Exception`; log unhandled exceptions at ERROR level with ticket_id; do not cancel other running tasks or crash the polling loop

**Checkpoint**: User Stories 1 and 2 both independently testable. All failure paths produce observable TM comments and Orchestrator triggers.

---

## Phase 5: User Story 3 — Multi-Agent Brainstorm Coordination (Priority: P3)

**Goal**: Architecture-review tickets run two agents sequentially in a shared brainstorm session. Early consensus exit works. API mode injects previous responses.

**Independent Test**: Mock runner returns `"brainstorm_consensus": "agreed"` for the first agent. Second agent is not invoked. `brainstorm_sessions` record shows `status=concluded`, `consensus=agreed`, `current_round=1`.

### Tests for User Story 3

- [ ] T045 [P] [US3] Write unit tests `tests/unit/test_brainstorm_coordinator.py`: two agents run sequentially in correct order (`software_architect` before `security_architect`); early exit when first agent returns `"agreed"` (second not invoked, verified via mock call count); max rounds enforced — no extra rounds beyond `BRAINSTORM_MAX_ROUNDS`; `api` mode injects first agent's `tm_comment` as "Previous agent responses:" prefix into second agent's context; `round_number` incremented in DB after each round
- [ ] T046 [P] [US3] Extend `tests/integration/test_dispatcher_service.py`: `architecture_review` ticket routes to `BrainstormCoordinator`; aggregated result posted to TM and Orchestrator after session concludes; non-`architecture_review` ticket does NOT invoke coordinator

### Implementation for User Story 3

- [ ] T047 [US3] Create `src/services/brainstorm_coordinator.py`: `BrainstormCoordinator(runner: AgentRunner)` class; `async run_brainstorm(ticket, agent_briefing, db) -> dict`; `get_or_create` brainstorm session; for each round up to `max_rounds`: for each agent in `brainstorm_agents_list`: load prompt, build context with `brainstorm_session` included (and previous `tm_comment` prepended in `api` mode), run agent, parse result, save `AgentRun` row with correct `round_number` and `brainstorm_session_id`; check `brainstorm_consensus == "agreed"` → call `conclude(session, "agreed")` and break; after all rounds call `conclude(session, "disagreed")`; return `{"concluded": bool, "consensus": str|None, "rounds_completed": int, "agent_results": list}`
- [ ] T048 [US3] Update `src/services/context_builder.py`: add brainstorm section when `brainstorm_session` is not None — include `project_name`, `round_number`, `max_rounds`, and "Previous agent messages are available in the brainstorm project" note; in `api` mode accept optional `previous_responses: str` param and prepend as "Previous agent responses:" block before the task description
- [ ] T049 [US3] Update `src/services/dispatcher_service.py`: add `needs_brainstorm` check — `ticket.fsm_status == "architecture_review"` and `ticket.ticket_type in ("feature", "improvement")`; if true, call `BrainstormCoordinator(get_runner()).run_brainstorm()`; aggregate results into single `AgentResult` using `aggregate_brainstorm()` helper for reporter
- [ ] T050 [US3] Add `aggregate_brainstorm(result_data: dict) -> AgentResult` helper in `src/services/dispatcher_service.py`: concatenates all agent summaries; sets final `status` from last agent's `status`; preserves `brainstorm_consensus`; collects all `errors`

**Checkpoint**: All three user stories independently functional and testable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Monorepo wiring, final coverage pass, and documentation.

- [ ] T051 [P] Add `services/agent-dispatcher` entry to `infra/docker-compose.yml`: service name `agent-dispatcher`, build context `services/agent-dispatcher`, port `8006:8000`, env vars from `infra/.env`, `depends_on: postgres`, healthcheck `GET /api/health`
- [ ] T052 [P] Add `df_dispatcher` database to `infra/postgres/init/01_create_databases.sql`: `CREATE DATABASE df_dispatcher;` with dedicated user and password from env
- [ ] T053 [P] Add Agent Dispatcher env section to `infra/.env.example`: all variables from constitution table with inline comments; `AGENT_RUNNER_MODE=claude_code`, `AGENT_TIMEOUT_DEFAULT=300`; per-agent timeout overrides commented out as examples
- [ ] T054 Update `CLAUDE.md` service map table: add `agent-dispatcher` row with port 8006, database `df_dispatcher` (PostgreSQL), internal URL `http://agent-dispatcher:8006`
- [ ] T055 [P] Run coverage check: `pytest --cov=src --cov-report=term-missing --cov-fail-under=80`; identify any gaps below 80% and add targeted tests to reach threshold
- [ ] T056 [P] Run linter: `ruff check src/ tests/` and `ruff format src/ tests/`; fix all lint and format issues
- [ ] T057 Run quickstart validation: follow `specs/002-agent-dispatcher/quickstart.md`; verify `docker compose up --build` starts clean with no errors; verify `GET /api/health` returns `{"status":"ok",...}`; verify `GET /api/v1/runs` returns 200 with empty `items` list
- [ ] T058 Write `README.md` at `services/agent-dispatcher/README.md` as the final deliverable: sections — Prerequisites, Environment Variables (full table from constitution), Runner Modes (claude_code vs api, when to use each), Running in Isolation (`docker compose up`), Running in the Monorepo (`infra/docker-compose.yml`), Running Tests (`pytest` commands), API Reference (`GET /api/health`, `GET /api/v1/runs`, `GET /api/v1/runs/{id}` with example responses), Troubleshooting (orphaned records, missing prompt files, Orchestrator unreachable)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Phase 2 — MVP deliverable
- **User Story 2 (Phase 4)**: Depends on Phase 3 — extends `dispatcher_service.py` with failure paths
- **User Story 3 (Phase 5)**: Depends on Phase 3 — adds `BrainstormCoordinator` reusing runner + context_builder
- **Polish (Phase 6)**: Depends on Phases 3–5

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — no story dependencies
- **US2 (P2)**: After US1 — extends dispatcher_service.py, no new files
- **US3 (P3)**: After US1 — additive: new `brainstorm_coordinator.py` + updates to existing services

### Within Each User Story

- Write tests FIRST (they must FAIL before implementation)
- Repositories before services
- Services before workers/API
- Story complete before moving to next priority

### Parallel Opportunities

- All `[P]` tasks within a phase can run simultaneously
- T030 (`ClaudeCodeRunner`) and T031 (`ApiRunner`) can be built in parallel after T029 base is done
- T026, T027 (US1 test writing) can run in parallel before T029–T038
- T051, T052, T053 (infra wiring) can run in parallel
- T055, T056 (coverage + lint) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Write tests in parallel:
Task T026: tests/unit/test_context_builder.py
Task T027: tests/integration/test_poller.py

# Build runners in parallel (after T029 base.py done):
Task T030: src/services/runner/claude_code.py
Task T031: src/services/runner/api_runner.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T018)
2. Complete Phase 2: Foundational (T019–T025) — includes startup orphan sweep
3. Complete Phase 3: User Story 1 (T026–T038)
4. **STOP and VALIDATE**: `GET /api/health` returns ok; `GET /api/v1/runs` returns 200; test ticket runs through full lifecycle; restart service and verify orphaned records swept
5. Deploy/demo if ready

### Incremental Delivery

1. Phase 1 + 2 + Phase 3 → Single agent runs work end-to-end (MVP)
2. + Phase 4 → Failure cases handled gracefully
3. + Phase 5 → Architecture review brainstorm sessions work
4. + Phase 6 → Monorepo wiring + README complete

---

## Notes

- `[P]` tasks = different files, no shared state dependencies
- `[USN]` label maps task to spec.md user story for traceability
- Tests must FAIL before implementation (T022–T024 before T019–T021, T026–T028 before T029–T038, etc.)
- `SERVICE_JWT` and TM credentials MUST NOT appear in `context_snapshot`, `raw_output`, or any API response — enforced in T032 (context_builder) and T019 (run_repo `create()`)
- Prompt files in `prompts/` are placeholders — do not overwrite if files already exist
- Metrics reporting section in context (T032) must use relative path `development/scripts/report-task-metrics.sh` from the agent's working directory, matching the `../scripts/report-task-metrics.sh` pattern used in `development/run-agents.sh`
- T058 (README.md) is the final deliverable of the entire implementation; it should be written last when all other tasks are complete
