# Code Review: Agent Dispatcher — Phases 1–3 + Infra (T001–T044, T051–T054)

**Reviewer**: code-reviewer  
**Date**: 2026-06-23  
**Branch**: 002-agent-dispatcher  
**Scope**: All files under `services/agent-dispatcher/` (Phase 1–3 implementation) and `infra/` additions (T051–T054)  
**Spec reference**: `specs/002-agent-dispatcher/spec.md`, `plan.md`, `contracts/api.md`, `data-model.md`

---

## Code Review Result

### Decision

**APPROVED WITH COMMENTS**

The implementation is architecturally sound, follows the monorepo patterns, and satisfies the core functional requirements for US1–US2. No blockers were found. There are two Major findings that must be fixed before Phase 6 closes, and several Minor/Nit items.

---

### Scope Reviewed

| Area | Files |
|------|-------|
| Core | `src/core/{config,security,auth_adapter,exceptions}.py` |
| DB layer | `src/db/session.py`, `src/models/models.py`, `alembic/versions/0001_*` |
| Repositories | `src/repositories/{run_repo,brainstorm_repo}.py` |
| Services | `src/services/{result_parser,context_builder,dispatcher_service,reporter,poller,brainstorm_coordinator}.py` |
| Runners | `src/services/runner/{base,claude_code,api_runner}.py` |
| Worker | `src/workers/dispatch_worker.py` |
| API | `src/api/v1/runs.py`, `src/main.py` |
| Tests | `tests/conftest.py`, `tests/unit/test_{result_parser,context_builder,runners}.py`, `tests/integration/test_{run_repo,brainstorm_repo,dispatcher_service,poller}.py` |
| Infra | `infra/docker-compose.yml`, `infra/postgres/init/01_create_databases.sh`, `infra/.env.example`, `infra/docker-compose.override.yml` |
| Config | `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.pre-commit-config.yaml`, `pytest.ini`, `.coveragerc` |

---

### Summary

The implementation correctly models the three-layer architecture (worker → dispatcher → runner/reporter), enforces the double-run guard via `has_running()`, handles all five failure paths, cleans up orphaned records on startup, and never persists `SERVICE_JWT` in the database. The migration is complete and correct. The test suite covers the critical paths including the result parser edge cases and the repository lifecycle.

Two correctness issues need fixing: the `list_all` count query loads all rows into memory instead of using `SELECT COUNT(*)`, and the SQLite test engine cannot evaluate the `agent_run_status` PostgreSQL enum at ORM level, causing the integration tests to produce misleading results for enum-typed fields. Neither is a security or data-loss risk but both must be fixed before the coverage gate (T055) is meaningful.

---

### Blockers

None.

---

### Major Findings

#### Major: `list_all` total count fetches all rows instead of using COUNT(*)

**Location**: `src/repositories/run_repo.py:152–161`  
**Issue**: The count query executes `SELECT * FROM agent_runs` (possibly thousands of rows) and counts the Python list rather than issuing a `SELECT COUNT(*) FROM agent_runs`.  
**Impact**: Under load (many runs), this query will be slow and wasteful. On a table with 100k rows the pagination call loads all rows into the ORM just to return a count integer.  
**Required action**: Replace with `select(func.count()).select_from(AgentRun)` and use `scalar()`.  
**Evidence**:
```python
# Current (wrong):
total_result = await self.db.execute(count_query)
total = len(total_result.scalars().all())  # loads all rows

# Fix:
from sqlalchemy import func
count_q = select(func.count()).select_from(AgentRun)
if ticket_id:
    count_q = count_q.where(AgentRun.ticket_id == ticket_id)
if status:
    count_q = count_q.where(AgentRun.status == status)
total = (await self.db.execute(count_q)).scalar_one()
```

---

#### Major: Integration tests run against SQLite — PostgreSQL enum type incompatible

**Location**: `tests/conftest.py:16`  
**Issue**: `TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_dispatcher.db"` combined with `AGENT_RUN_STATUS_ENUM = Enum(... name="agent_run_status")` in models causes the test database to either silently skip type validation or fail when migrating if `native_enum=True` is used. SQLite has no native `ENUM` type. The ORM `Enum` with `native_enum` (default `True` in PostgreSQL dialect) falls back to `VARCHAR` in SQLite but the `check_constraint` behaviour diverges.  
**Impact**: Integration tests pass on SQLite even when they would fail on PostgreSQL due to invalid status values or enum migration issues. The coverage numbers produced by this suite are not a reliable gate for production correctness.  
**Required action**: Either (a) run integration tests against a real `df_dispatcher_test` PostgreSQL database (preferred — consistent with the spec requirement "no real LLM credentials"), or (b) add `native_enum=False` to the `Enum` definition to make it portable and note the divergence. Option (a) is strongly preferred.  
**Evidence**: `AGENT_RUN_STATUS_ENUM = Enum(..., name="agent_run_status")` at `src/models/models.py:23`. The `conftest.py` uses `Base.metadata.create_all` which will create a `VARCHAR` column in SQLite, not the enum type — meaning `mark_timed_out` storing `"timed_out"` will succeed in tests but the migration creates a strict PG enum.

---

### Minor Findings

#### Minor: `sweep_orphaned_running` signature accepts an unused `db` parameter

**Location**: `src/repositories/run_repo.py:121`  
**Issue**: `sweep_orphaned_running(self, db: Optional[AsyncSession] = None)` always uses `session = db or self.db`, but `self.db` is always set and all call sites pass nothing. The optional `db` parameter adds confusion about which session is actually used.  
**Required action**: Remove the `db` parameter and use `self.db` directly.

---

#### Minor: `OPENAI_BASE_URL` env var is wired in docker-compose but missing from `config.py`

**Location**: `src/core/config.py`, `infra/docker-compose.yml:66`  
**Issue**: `docker-compose.yml` passes `OPENAI_BASE_URL: ${OPENAI_BASE_URL:-}` into the container, but `config.py` has no `openai_base_url` field and `api_runner.py` does not pass a `base_url` to `AsyncOpenAI(...)`. This means the env var is silently ignored.  
**Impact**: Integration test overrides (`OPENAI_BASE_URL` pointing at `llm-mock`) will have no effect for the `api` runner mode.  
**Required action**: Add `openai_base_url: str = ""` to `Settings` and pass it to `AsyncOpenAI(base_url=settings.openai_base_url or None, ...)` in `api_runner.py`. Pass `None` when empty to use SDK default.

---

#### Minor: Orphan sweep in `main.py` reports with `project_id="unknown"` — Orchestrator will reject

**Location**: `src/main.py:41`  
**Issue**: When sweeping orphaned runs, `Reporter.report_result` is called with `project_id="unknown"`. The Orchestrator trigger endpoint (`POST /api/v1/jobs/trigger`) requires a valid `project_id` to identify the ticket. Sending `"unknown"` will cause the Orchestrator to log a 404/422, though the exception is caught.  
**Impact**: Orphaned runs post a TM comment with `project_id="unknown"` (likely 404 from TM too) and the Orchestrator trigger silently fails. The ticket remains un-re-triggered, which is the primary goal of FR-017.  
**Required action**: `sweep_orphaned_running` should return `(ticket_id, project_id)` tuples. The ORM model has `project_id` available — include it in the sweep result so the reporter can use the real value.  
**Evidence**: `AgentRun.project_id` is persisted at create time (`run_repo.py:34`); it is available during the sweep.

---

#### Minor: `verify_access_token` re-raises bare `JWTError as exc; raise exc` — loses context

**Location**: `src/core/security.py:30–31`  
**Issue**: `raise exc` inside `except JWTError as exc` is equivalent to `raise` but suppresses the original traceback in some Python versions. Use `raise` or `raise JWTError("...") from exc` for clarity.  
**Required action**: Replace `raise exc` with `raise`.

---

#### Minor: `dispatch_worker.py` creates tasks for all tickets without checking `has_running` at dispatch time

**Location**: `src/workers/dispatch_worker.py:48`  
**Issue**: `poll_once` filters out `running` tickets at poll time using the DB state. However, if two poll cycles happen in rapid succession before the semaphore fires (e.g., under high concurrency with a short `POLL_INTERVAL_SECONDS`), the same ticket could appear in both poll results before the first run's DB row transitions to `running`. The `has_running` guard inside `process_ticket` (not `poll_once`) is the true enforcement point, but the window between `asyncio.create_task` dispatch and the actual `mark_running` call allows re-entry.  
**Impact**: Low probability under normal settings (default 10s interval), but real under `POLL_INTERVAL_SECONDS=1`. The `has_running` guard in `process_ticket` catches this, but there is no DB-level unique constraint on `(ticket_id, status='running')` — only the application-level guard.  
**Required action**: Document the known window in a comment on `dispatch_worker.py` and add a partial unique index in a follow-up migration: `CREATE UNIQUE INDEX uq_agent_runs_ticket_running ON agent_runs (ticket_id) WHERE status = 'running';` — this makes the constraint atomic at the DB level.

---

#### Minor: `brainstorm_coordinator.py` does not commit between brainstorm runs; flushes only

**Location**: `src/services/brainstorm_coordinator.py:63–73`  
**Issue**: The coordinator uses `db.flush()` after each `run_repo.mark_running()` and `mark_done()`/`mark_needs_review()` call, but never `db.commit()`. The outer `_run_with_semaphore` in `dispatch_worker.py` calls `await db.commit()` after `process_ticket` returns, which means all brainstorm run records are committed atomically at the end. This is fine semantically, but if the process crashes mid-brainstorm, all partial run records are lost.  
**Impact**: Orphaned rows after crash would not appear in `running` state (they never committed), so the startup sweep cannot recover them. Partial brainstorm results are invisible until a full session completes.  
**Required action**: Add `await db.commit()` after each agent run within the brainstorm loop to ensure partial progress is durably recorded. This is necessary to meet FR-017's spirit for brainstorm runs.

---

### Nits

- `src/core/security.py`: `settings = get_settings()` at module level is evaluated at import time. This works but will cause test failures if settings are patched after import. Prefer lazy instantiation inside the functions, matching how other modules call `get_settings()` inside function bodies.
- `src/services/context_builder.py:84`: `build_context` accepts `agent_briefing` as a named parameter in the contract (`contracts/api.md`), but the implementation uses `agent_id` directly and reads the prompt file internally. The parameter name `agent_briefing` in the spec/contract is never materialised. This is fine — the implementation is simpler — but the discrepancy between contract and implementation should be noted.
- `src/repositories/run_repo.py:107`: `mark_timed_out` signature is `(run_id, error_message, raw_output="")` but `dispatcher_service.py:93` calls it as `mark_timed_out(run.id, "Timed out", "")`. Passing empty string for `raw_output` is intentional (no stdout captured at timeout), but the parameter should be `Optional[str]` with `None` as default to match other `mark_*` methods.
- `src/workers/dispatch_worker.py:44`: The `AsyncSessionLocal()` session used for `poll_once` is separate from the session used in `_run_with_semaphore`. This is correct — `poll_once` needs a read session and `process_ticket` needs a write session. Worth a short comment to prevent future confusion.
- `docker-compose.yml` (standalone) is missing `OPENAI_API_KEY` in the environment block. It will fail to start in `api` mode without it being set externally.

---

### Tests and Evidence Reviewed

| Test file | Coverage area | Assessment |
|-----------|---------------|------------|
| `tests/unit/test_result_parser.py` | All parse paths including edge cases | Complete — all T022 requirements met |
| `tests/unit/test_context_builder.py` | Context sections, JWT exclusion from snapshot, truncation | Complete — T026 requirements met |
| `tests/unit/test_runners.py` | ClaudeCode success/timeout/OSError, API success/error | Complete — T040 requirements met |
| `tests/integration/test_run_repo.py` | Full lifecycle, has_running, sweep, list filters | Complete — T023 requirements met (runs on SQLite — see Major finding) |
| `tests/integration/test_dispatcher_service.py` | Single run success, missing prompt, non-zero exit | Complete — T028 requirements met |

**Not yet reviewed** (pending Phase 5): `tests/unit/test_brainstorm_coordinator.py`, `tests/integration/test_brainstorm_repo.py`, `tests/integration/test_poller.py`.

---

### Untested or Unverified Areas

1. **Double-run guard under concurrent load** — no test exercises simultaneous `process_ticket` calls for the same ticket via `DispatchWorker`.
2. **Startup orphan sweep with real `project_id`** — `main.py` passes `"unknown"` which will fail TM and Orchestrator calls silently.
3. **`OPENAI_BASE_URL` ignored in `api` runner mode** — no test catches this gap.
4. **Brainstorm partial commit durability** — no test verifies that partial brainstorm runs are visible in the DB after a mid-session flush.

---

### Required Follow-Up

| Priority | Owner | Finding |
|----------|-------|---------|
| Must fix before Phase 6 | backend | COUNT(*) query in `list_all` (Major) |
| Must fix before Phase 6 | backend + autotester | PostgreSQL test DB for integration tests (Major) |
| Must fix before Phase 3 checkpoint sign-off | backend | Orphan sweep passes real `project_id` to reporter (Minor) |
| Must fix before Phase 6 | backend | Wire `OPENAI_BASE_URL` through config and api_runner (Minor) |
| Track | backend | Partial unique index on `(ticket_id) WHERE status='running'` (Minor) |
| Track | backend | Brainstorm coordinator `db.commit()` after each agent run (Minor) |

---

### Acceptance Criteria Verification

| Criterion | Status |
|-----------|--------|
| FR-001 Poll Orchestrator at `POLL_INTERVAL_SECONDS` | ✅ `poller.py` + `dispatch_worker.py` |
| FR-002 `claude_code` and `api` runner modes | ✅ Both runners implemented |
| FR-003 At most one run per ticket at any time | ✅ `has_running()` guard — see Minor for DB-level gap |
| FR-004 Prompts read from disk, no caching | ✅ `prompt_path.read_text()` on each call |
| FR-005 Parse `[RESULT]` block | ✅ `result_parser.py` |
| FR-006 Graceful handling of missing/bad `[RESULT]` | ✅ Fallback to `needs_review` + `stdout[:2000]` |
| FR-007 Per-agent timeouts with fallback | ✅ `config.agent_timeout_for()` |
| FR-008 TM comment + Orchestrator trigger on every outcome | ✅ `reporter.report_result()` called on all exit paths |
| FR-009 Never modify Orchestrator FSM directly | ✅ Only `trigger` endpoint called |
| FR-013 SERVICE_JWT never in logs/DB/API | ✅ `build_context_snapshot` strips it; test verifies this |
| FR-014 `GET /api/v1/runs` and `GET /api/v1/runs/{id}` with auth | ✅ |
| FR-015 `GET /api/health` | ✅ |
| FR-017 Startup orphan sweep | ✅ Implemented — minor gap with `project_id="unknown"` |
| SC-007 `AUTH_MODE=local` | ✅ `auth_adapter.py` mirrors other services |
| Constitution: auth adapter pattern | ✅ `AUTH_MODE=local/keycloak` with `ValueError` at `__init__` |
| Constitution: structlog only, no print() | ✅ |
| Constitution: ruff .pre-commit-config.yaml | ✅ pinned to 0.8.3 |
| Constitution: no cross-service DB access | ✅ |
| Canonical versions in requirements.txt | ✅ All match spec (ruff=0.8.3 missing from requirements — dev only via pre-commit, acceptable) |
