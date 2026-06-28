# Tasks: Agent Maturity Platform

**Input**: Design documents from `specs/003-agent-maturity/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Organization**: Tasks grouped by user story (US1=Capability-Based Assignment, US2=Lifecycle Registration, US3=Peer Consultation, US4=Shared Working Memory). Each story is independently implementable and testable.

**Affected services**: `services/agent-dispatcher/` (primary), `services/orchestrator/` (minor payload extension)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in this phase)
- **[Story]**: Which user story this task belongs to (US1–US4)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the Alembic migration and extend the YAML registry model — both are required before any user story work can begin.

- [X] T001 Write Alembic migration `0002_add_agent_maturity_tables.py` in `alembic/versions/` creating `agent_worker_records`, `agent_lifecycle_events`, and `working_memory_entries` tables with all indexes and constraints from `data-model.md`
- [X] T002 [P] Add `AgentWorkerRecord`, `AgentLifecycleEvent`, and `WorkingMemoryEntry` ORM models to `src/models/models.py` (new SQLAlchemy declarative classes; no changes to existing `AgentRun` or `BrainstormSession`)
- [X] T003 [P] Extend `AgentCapability` dataclass in `src/services/capability_registry.py` with `confidence: dict[str, int] = field(default_factory=dict)` and update YAML loader to read the optional `confidence` key (backward-compatible — existing agents get `{}`)

**Checkpoint**: Migration applies cleanly; ORM models importable; YAML loader handles both old and new registry.yaml formats.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Repositories, shared service base, and schema extensions needed by all user stories. **No user story work may begin until this phase is complete.**

- [X] T004 Create `src/repositories/worker_repository.py` with `AgentWorkerRepository` class providing: `create(role_id, version, capabilities_snapshot)`, `get_by_id(worker_id)`, `get_by_role_status(role_id, status)`, `update_status(worker_id, new_status)`, `update_heartbeat(worker_id)`, `list_all(status_filter, role_id_filter)`, `get_stale(threshold_dt)` — all async SQLAlchemy 2.0 style
- [X] T005 Create `src/repositories/working_memory_repository.py` with `WorkingMemoryRepository` class providing: `append(ticket_id, run_id, author_role_id, entry_type, content, tags)`, `list_for_ticket(ticket_id, filters)`, `delete_expired()` — append-only; no update/delete except expiry cleanup
- [X] T006 [P] Add `get_by_capability(required_capabilities, min_confidence=0)` and `get_candidates_with_confidence(state, required_capabilities, min_confidence=0)` methods to `CapabilityRegistry` in `src/services/capability_registry.py`
- [X] T007 [P] Add new Pydantic schemas to `src/schemas/schemas.py`: `WorkerRegisterRequest`, `WorkerRegisterResponse`, `HeartbeatRequest`, `HeartbeatResponse`, `DrainRequest`, `DrainResponse`, `WorkerListResponse`, `WorkerRecord` (individual worker DTO)
- [X] T008 [P] Add new Pydantic schemas to `src/schemas/schemas.py`: `ConsultRequest`, `ConsultResponse`, `WorkingMemoryEntryCreate`, `WorkingMemoryEntryResponse`, `WorkingMemoryListResponse`
- [X] T009 [P] Extend `RunRequest` in `src/schemas/schemas.py` with `required_capabilities: list[str] = []`; extend `AgentResult` with `matched_capability_record: dict | None = None`

**Checkpoint**: All repositories importable; all new schemas validate; `CapabilityRegistry` new methods return correct filtered results from test YAML data.

---

## Phase 3: User Story 1 — Capability-Based Assignment (Priority: P1) 🎯 MVP

**Goal**: Orchestrator sends `required_capabilities` in run payload; Dispatcher resolves best-matched available worker; matched record returned in result.

**Independent Test**: Send `POST /api/v1/runs` with `required_capabilities=["python_backend"]`; verify result contains `matched_capability_record.role_id == "backend"` and worker `status` transitions `idle→busy→idle`.

### Implementation for User Story 1

- [X] T010 [US1] Create `src/services/worker_service.py` with `AgentWorkerService.resolve_capable_worker(required_capabilities, db)` that: calls `CapabilityRegistry.get_by_capability()`, cross-references `AgentWorkerRepository.list_all(status="idle")`, ranks by capability coverage + average confidence, returns best-matched `AgentCapability` (or `None` for fallback)
- [X] T011 [US1] Extend `src/services/dispatcher_service.py` `process_ticket()`: after `registry = get_registry()`, if `run_request.required_capabilities` is non-empty → call `worker_service.resolve_capable_worker()`; if match found use matched `role_id` for prompt path; mark worker busy; store `matched_capability_record`; if no match → continue static assignment + log warning
- [X] T012 [US1] Extend `src/services/reporter.py` (or result assembly in `dispatcher_service.py`) to include `matched_capability_record` in the `AgentResult` payload returned to the Orchestrator
- [X] T013 [US1] Extend `services/orchestrator/src/services/dispatcher_client.py` to call `derive_required_capabilities(to_state, ticket_tags)` and include result as `required_capabilities` in run trigger payload; add `STATE_CAPABILITIES` mapping dict; extract and log `matched_capability_record` from result
- [X] T014 [US1] Write integration tests `tests/integration/test_capability_assignment.py` covering: happy path (match found), fallback (no capable worker), fallback (registry empty list), backward compatibility (no `required_capabilities` field sent)

**Checkpoint**: Full assignment flow works end-to-end; empty `required_capabilities` produces identical behavior to pre-feature code.

---

## Phase 4: User Story 2 — Agent Lifecycle Registration (Priority: P2)

**Goal**: Workers register on startup, send heartbeats, drain gracefully; liveness sweep marks stale workers offline.

**Independent Test**: Register a worker via `POST /api/v1/workers/register`, send two heartbeats, call drain, verify `GET /api/v1/workers` reflects status transitions `idle→draining→offline`; stop heartbeats and verify liveness sweep marks worker `offline`.

### Implementation for User Story 2

- [X] T015 [P] [US2] Add lifecycle event write helpers to `AgentWorkerRepository`: `write_lifecycle_event(worker_id, role_id, event_type, metadata)` using `AgentLifecycleEvent` ORM model; called on every status transition
- [X] T016 [US2] Extend `src/services/worker_service.py` with full `AgentWorkerService` methods: `register_worker(role_id, version, capabilities_snapshot, db)`, `record_heartbeat(worker_id, role_id, status, db)`, `drain_worker(worker_id, role_id, db)`, `list_workers(status_filter, role_id_filter, db)`, `run_liveness_sweep(threshold_seconds, db)` — each calling the matching repository method and emitting lifecycle events
- [X] T017 [US2] Create `src/api/v1/workers.py` FastAPI router with endpoints: `POST /api/v1/workers/register`, `POST /api/v1/workers/{role_id}/heartbeat`, `POST /api/v1/workers/{role_id}/drain`, `GET /api/v1/workers` — all require service token auth via existing `KeycloakValidator`
- [X] T018 [US2] Register `workers.router` in `src/main.py` lifespan; add `asyncio.create_task` for liveness sweep background loop (every 60 seconds); sweep threshold configurable via `settings` (default: 2× heartbeat interval = 120s)
- [X] T019 [US2] Extend `src/services/dispatcher_service.py` to check `AgentWorkerRepository` status before issuing a run: skip workers with `status IN ('unhealthy', 'draining', 'offline')`; on run completion set worker status back to `idle`; on crash-detected timeout set worker `unhealthy` and mark run `timed_out`
- [X] T020 [US2] Write integration tests `tests/integration/test_worker_lifecycle.py` covering: register → heartbeat → drain → offline transitions; liveness sweep marks stale worker; no assignment to non-idle worker; lifecycle event audit trail; crash detection sets run `timed_out`

**Checkpoint**: All four worker status transitions observable; liveness sweep correctly marks stale workers; no new assignments go to non-idle workers.

---

## Phase 5: User Story 3 — Peer Consultation (Priority: P3)

**Goal**: Agent submits a synchronous consultation request via `agent-dispatcher`; dispatcher resolves peer, forwards question, returns answer; exchange auto-written to working memory.

**Independent Test**: Register a `security-architect` worker as idle; call `POST /api/v1/consult` with `required_peer_capabilities=["security_assessment"]`; verify response contains `answer` and `GET /api/v1/working-memory/{ticket_id}` returns both `question` and `answer` entries.

### Implementation for User Story 3

- [X] T021 [US3] Create `src/services/consultation_service.py` with `ConsultationService.consult(request, db)`: (1) resolve peer via `worker_service.resolve_capable_worker(required_peer_capabilities)`, (2) if none: raise HTTP 404, (3) `asyncio.wait_for(peer_runner.ask(question, context), timeout=request.timeout_seconds)`, (4) write two `WorkingMemoryEntry` rows (question + answer), (5) return `ConsultResponse` with `latency_ms`
- [X] T022 [US3] Implement lightweight peer runner helper in `src/services/consultation_service.py` (`_call_peer_agent(role_id, question, context, timeout)`) that invokes the existing `claude_code` subprocess runner with a targeted question prompt and captures text output (no FSM state change, no artifact generation)
- [X] T023 [US3] Create `src/api/v1/consultation.py` FastAPI router with `POST /api/v1/consult`; require service token auth; delegate to `ConsultationService`; return 404 if no peer, 408 on timeout, 200 with answer
- [X] T024 [US3] Register `consultation.router` in `src/main.py`
- [X] T025 [US3] Write integration tests `tests/integration/test_consultation.py` covering: happy path (peer available, answer returned), no peer available (404), timeout (408), auto-write to working memory, consultation does not change requesting agent's status

**Checkpoint**: Full consultation round-trip completes within 60s; both WM entries written; 404 returned when no peer; 408 on timeout.

---

## Phase 6: User Story 4 — Shared Working Memory (Priority: P4)

**Goal**: Agents append entries to per-ticket shared memory; Orchestrator reads all entries for a ticket at gate evaluation; cross-ticket isolation enforced; 30-day expiry.

**Independent Test**: Write two entries to `TICKET-TEST` from different `run_id` values; `GET /api/v1/working-memory/TICKET-TEST` returns both in creation order; attempt cross-ticket write (run belongs to different ticket) returns 403.

### Implementation for User Story 4

- [X] T026 [US4] Create `src/services/working_memory_service.py` with `WorkingMemoryService`: `append(ticket_id, run_id, author_role_id, entry_type, content, tags, db)` — validates run belongs to ticket, creates `WorkingMemoryEntry` with `expires_at = now() + 30 days`; `read(ticket_id, author_filter, type_filter, since, limit, db)` — ordered by `created_at ASC`; `cleanup_expired(db)` — deletes entries where `expires_at < now()`
- [X] T027 [US4] Create `src/api/v1/working_memory.py` FastAPI router: `GET /api/v1/working-memory/{ticket_id}` (query params: `author_role_id`, `entry_type`, `since`, `limit`), `POST /api/v1/working-memory/{ticket_id}` — both require service token; POST validates run-to-ticket ownership and returns 403 on cross-ticket attempt
- [X] T028 [US4] Register `working_memory.router` in `src/main.py`; add daily `cleanup_expired` background task via `asyncio.create_task`
- [X] T029 [US4] Write integration tests `tests/integration/test_working_memory.py` covering: append and read by single agent, two agents append to same ticket and both visible, cross-ticket isolation (403), `since` and `limit` filters, expiry cleanup deletes old entries, content too long (400)

**Checkpoint**: Two agents' entries co-exist for the same ticket; chronological ordering preserved; cross-ticket write rejected; cleanup removes expired entries.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Unit test coverage, settings additions, observability logging.

- [X] T030 [P] Write unit tests `tests/unit/test_capability_registry.py` extending existing tests: `get_by_capability()` single match, multi-match, confidence threshold filtering, no-match empty list; `get_candidates_with_confidence()` combines FSM state + capability filter
- [X] T031 [P] Write unit tests `tests/unit/test_worker_service.py`: register creates record and lifecycle event, heartbeat updates timestamp, drain transitions status, resolve_capable_worker ranking logic, liveness sweep threshold math
- [X] T032 [P] Write unit tests `tests/unit/test_working_memory_service.py`: append validates run ownership, read applies filters correctly, cleanup only deletes expired rows
- [X] T033 Add `heartbeat_interval_seconds: int = 30` and `worker_liveness_threshold_multiplier: float = 2.0` to `src/core/config.py` Settings class
- [X] T034 [P] Add structured log lines for: capability resolution (role selected, fallback triggered), worker status transitions, consultation request (peer role, latency), working memory writes (ticket_id, entry_type, author) — use existing logger in each service file
- [X] T035 Run `pytest --cov --cov-fail-under=80` from `services/agent-dispatcher/` and confirm all 4 new integration test files pass; address any coverage gaps

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **blocks all user stories**
- **Phase 3 (US1)**: Depends on Phase 2; uses `worker_service.resolve_capable_worker()`
- **Phase 4 (US2)**: Depends on Phase 2; builds out full `worker_service`; US1 T010 must complete first (partial worker_service)
- **Phase 5 (US3)**: Depends on Phase 4 (peer routing requires worker availability model)
- **Phase 6 (US4)**: Depends on Phase 2; independent of US1/US3 (shares only repositories)
- **Phase 7 (Polish)**: Depends on all user story phases

### User Story Dependencies

- **US1 (P1)**: After Phase 2. Partially builds `worker_service` (T010). Independent otherwise.
- **US2 (P2)**: After Phase 2. Completes `worker_service` — T016 extends what T010 started.
- **US3 (P3)**: After US2 (T016) — needs full worker availability model for peer routing.
- **US4 (P4)**: After Phase 2. Fully independent of US1/US2/US3 (separate service + repository).

### Within Each Phase

- Models before services (T002 before T010)
- Repository before service before router (T004 → T016 → T017)
- Service before endpoint (T021 → T023)
- Implementation before tests (tests at end of each phase validate the full story)

### Parallel Opportunities

- T002 + T003 (Phase 1) — different files, no dependency
- T006 + T007 + T008 + T009 (Phase 2) — all touch different files
- T004 + T005 (Phase 2) — different repository files
- T015 (Phase 4) — lifecycle event helpers independent of main service methods
- T030 + T031 + T032 + T034 (Phase 7) — all different test/log files

---

## Parallel Example: Phase 2 Foundational

```bash
# Launch all in parallel (different files, no cross-dependencies):
Task T004: "Create src/repositories/worker_repository.py"
Task T005: "Create src/repositories/working_memory_repository.py"
Task T006: "Add get_by_capability() methods to src/services/capability_registry.py"
Task T007: "Add Worker schemas to src/schemas/schemas.py"
Task T008: "Add Consultation + WorkingMemory schemas to src/schemas/schemas.py"
# NOTE: T007 and T008 both touch schemas.py — run sequentially
Task T009: "Extend RunRequest + AgentResult in src/schemas/schemas.py"
# NOTE: T009 also touches schemas.py — run after T007+T008
```

## Parallel Example: Phase 7 Polish

```bash
# All unit test files are independent:
Task T030: "tests/unit/test_capability_registry.py"
Task T031: "tests/unit/test_worker_service.py"
Task T032: "tests/unit/test_working_memory_service.py"
Task T034: "Logging additions across service files"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T009)
3. Complete Phase 3: US1 — Capability-Based Assignment (T010–T014)
4. **STOP and VALIDATE**: Send a run with `required_capabilities` and confirm `matched_capability_record` in result; confirm fallback works with empty list
5. Merge US1 — this is the highest-value standalone increment

### Incremental Delivery

1. Setup + Foundational → registry extensions + DB tables ready
2. US1 → capability-based assignment works; Orchestrator can use it
3. US2 → worker lifecycle visible; assignment skips unavailable workers
4. US4 → working memory persists across agent runs (independent of US3)
5. US3 → peer consultation possible (depends on US2 being live)
6. Polish → full coverage; observability; settings

### Parallel Team Strategy

With two developers after Phase 2 completes:
- Dev A: US1 (T010–T014) → then US2 (T015–T020)
- Dev B: US4 (T026–T029) → then US3 (T021–T025) after US2 merges

---

## Notes

- `[P]` tasks = different files, no competing dependencies
- Schemas.py (T007, T008, T009) — sequential despite [P] on T007/T008 because all modify the same file; implement in order T007 → T008 → T009
- `worker_service.py` is built incrementally: T010 adds `resolve_capable_worker`; T016 adds the remaining CRUD and lifecycle methods. Do not split into two files.
- The orchestrator change (T013) is the only cross-service task; it is a pure payload extension with no DB changes on the orchestrator side.
- US2 must complete before US3 (peer routing depends on the full availability model). US4 can be developed in parallel with US2/US3.
- Run `pytest --cov --cov-fail-under=80` after each user story phase to catch regressions early.
