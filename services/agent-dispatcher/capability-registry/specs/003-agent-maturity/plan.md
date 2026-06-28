# Implementation Plan: Agent Maturity Platform

**Branch**: `003-agent-maturity` | **Date**: 2026-06-28 | **Spec**: [spec.md](spec.md)

## Summary

Extend `agent-dispatcher` with four capabilities: capability-based run assignment (using a new runtime layer on top of the existing YAML registry), logical worker lifecycle registration with heartbeat-based liveness detection, synchronous peer consultation via a new mediated HTTP endpoint, and append-only per-ticket shared working memory readable by the Orchestrator. All state lives in `df_dispatcher`; no new services are created; all existing brainstorm and single-agent flows remain unchanged.

---

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI 0.115.5, SQLAlchemy 2.0.36, asyncpg 0.30.0, pydantic 2.10.3, Alembic  
**Storage**: PostgreSQL 16 (`df_dispatcher`) — 3 new tables via Alembic migration  
**Testing**: pytest, pytest-asyncio (Mode.AUTO), pytest-cov (≥80% coverage gate)  
**Target Platform**: Linux server (Docker container, `agent-dispatcher` service)  
**Project Type**: HTTP web service (FastAPI)  
**Performance Goals**: Capability resolution ≤ 100ms p95; consultation ≤ 60s p95; working memory read ≤ 50ms p95  
**Constraints**: No cross-service DB access; all new state in `df_dispatcher`; all new communication via HTTP; backward-compatible payload extension  
**Scale/Scope**: Single-service change; ~10 new endpoints; ~3 new DB tables; affects `agent-dispatcher` + minor Orchestrator payload extension

---

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| Registry is single source of truth for agent metadata | ✅ PASS | YAML remains source for static declarations; DB adds runtime state only |
| No hardcoded role IDs outside registry | ✅ PASS | All new code references `role_id` values loaded from YAML |
| LLM selects, registry constrains | ✅ PASS | Orchestrator LLM receives `matched_capability_record` in result payload |
| Credentials written by Dispatcher before spawn | ✅ PASS | `_write_credentials` in `dispatcher_service.py` unchanged |
| Registry loaded once at startup | ✅ PASS | YAML still loaded at startup; DB state queried per-request |
| No cross-service DB access | ✅ PASS | All new tables in `df_dispatcher`; Orchestrator reads via HTTP |
| Service boundaries over HTTP | ✅ PASS | All new cross-service calls via HTTP endpoints |
| FSM sovereignty in Orchestrator | ✅ PASS | Dispatcher never mutates FSM; Orchestrator specifies capabilities |

**Gate result**: ALL PASS — no constitution violations.

---

## Project Structure

### Documentation (this feature)

```text
specs/003-agent-maturity/
├── plan.md              ← This file
├── spec.md              ← Feature specification
├── research.md          ← Phase 0: architecture decisions
├── data-model.md        ← Phase 1: entities, migrations, extensions
├── quickstart.md        ← Phase 1: integration scenarios
├── contracts/
│   ├── worker-lifecycle.md       ← POST/GET /api/v1/workers/*
│   ├── capability-assignment.md  ← Extended run trigger + result payload
│   ├── consultation.md           ← POST /api/v1/consult
│   └── working-memory.md         ← GET/POST /api/v1/working-memory/*
└── tasks.md             ← Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root from `services/agent-dispatcher/`)

```text
src/
├── models/
│   └── models.py                ← ADD: AgentWorkerRecord, AgentLifecycleEvent, WorkingMemoryEntry
├── schemas/
│   └── schemas.py               ← ADD: WorkerRegisterRequest/Response, HeartbeatRequest/Response,
│                                        DrainRequest/Response, WorkerListResponse,
│                                        ConsultRequest/Response,
│                                        WorkingMemoryEntryCreate/Response/ListResponse,
│                                        RunRequest (add required_capabilities),
│                                        AgentResult (add matched_capability_record)
├── services/
│   ├── capability_registry.py   ← EXTEND: add confidence field to AgentCapability,
│   │                                        add get_by_capability(), get_candidates_with_confidence()
│   ├── dispatcher_service.py    ← EXTEND: add capability-based resolution before static fallback
│   ├── worker_service.py        ← NEW: AgentWorkerService (register, heartbeat, drain, list, liveness sweep)
│   ├── consultation_service.py  ← NEW: ConsultationService (resolve peer, forward question, record in WM)
│   └── working_memory_service.py ← NEW: WorkingMemoryService (append, read, cleanup)
├── repositories/
│   ├── worker_repository.py     ← NEW: AgentWorkerRepository (CRUD for worker records + lifecycle events)
│   └── working_memory_repository.py ← NEW: WorkingMemoryRepository (append-only + expiry cleanup)
└── api/v1/
    ├── runs.py                  ← EXTEND: accept required_capabilities in trigger; add matched record to result
    ├── workers.py               ← NEW: /api/v1/workers/* endpoints
    ├── consultation.py          ← NEW: /api/v1/consult endpoint
    └── working_memory.py        ← NEW: /api/v1/working-memory/* endpoints

alembic/versions/
└── 0002_add_agent_maturity_tables.py  ← NEW migration

tests/
├── unit/
│   ├── test_capability_registry.py    ← EXTEND: test confidence + new query methods
│   ├── test_worker_service.py         ← NEW
│   ├── test_consultation_service.py   ← NEW
│   └── test_working_memory_service.py ← NEW
└── integration/
    ├── test_capability_assignment.py  ← NEW
    ├── test_worker_lifecycle.py       ← NEW
    ├── test_consultation.py           ← NEW
    └── test_working_memory.py         ← NEW
```

**Orchestrator side** (minimal changes, `services/orchestrator/`):
```text
src/services/
├── dispatcher_client.py  ← EXTEND: add required_capabilities derivation + consume matched_capability_record
└── fsm/engine.py         ← NO CHANGE (candidate_agents already present; required_capabilities derived in client)
```

---

## Implementation Notes

### Migration (0002)

Three tables created in one migration. Down migration drops all three. No data migration needed (all new tables). See `data-model.md` for full schema.

### `capability_registry.py` Changes

- Add `confidence: dict[str, int] = field(default_factory=dict)` to `AgentCapability`
- YAML loader: read `confidence` key from YAML; default to `{}` if absent
- Add `get_by_capability(required_capabilities, min_confidence=0)` — filters by all required capabilities at or above min_confidence
- Add `get_candidates_with_confidence(state, required_capabilities, min_confidence=0)` — combines FSM eligibility with capability requirement
- All existing methods unchanged

### `dispatcher_service.py` Changes

In `process_ticket()`, after `registry = get_registry()`:
1. If `run_request.required_capabilities` is non-empty → call `worker_service.resolve_capable_worker(required_capabilities)`
2. If a match is found → use matched `role_id` for `_resolve_prompt_path()`; set `matched_capability_record` on the result
3. If no match → fall back to existing static `to_state`-based assignment; log warning; `matched_capability_record = None`

### `worker_service.py` (new)

`AgentWorkerService`:
- `register_worker(role_id, version, capabilities_snapshot, db)` → create `AgentWorkerRecord`, emit `registered` event
- `heartbeat(worker_id, role_id, status, db)` → update `last_heartbeat_at`; return next deadline
- `drain(worker_id, role_id, db)` → set status `draining`, emit `drain_requested`
- `list_workers(status_filter, role_id_filter, db)` → query with optional filters
- `liveness_sweep(db)` → mark workers offline if `last_heartbeat_at < now() - 2×interval`; emit `offline_liveness` events
- `resolve_capable_worker(required_capabilities, db)` → join registry + available workers; return best match

Background task: `liveness_sweep` runs every 60 seconds via `asyncio.create_task` in `main.py` lifespan.

### `consultation_service.py` (new)

`ConsultationService`:
- `consult(request, db)`:
  1. Resolve peer via registry + `worker_service.resolve_capable_worker()`
  2. If none: raise 404
  3. `asyncio.wait_for(peer_runner.ask(question, context), timeout=request.timeout_seconds)`
  4. Write two `WorkingMemoryEntry` rows (question + answer)
  5. Return response with `latency_ms`

Peer runner implementation: a lightweight prompt-and-return wrapper around the existing `claude_code` runner that returns a text string rather than full artifact output.

### `working_memory_service.py` (new)

`WorkingMemoryService`:
- `append(ticket_id, run_id, author_role_id, entry_type, content, tags, db)` → verify run belongs to ticket; create entry with 30-day expiry
- `read(ticket_id, filters, db)` → query with optional author/type/since/limit filters
- `cleanup_expired(db)` → delete entries where `expires_at < now()`

Background task: `cleanup_expired` runs daily via `asyncio.create_task` in `main.py` lifespan.

### API Router Changes

`main.py`:
- Include `workers.router`, `consultation.router`, `working_memory.router`
- Add `liveness_sweep` and `cleanup_expired` background tasks to lifespan

`runs.py`:
- `RunRequest` schema: add `required_capabilities: list[str] = []`
- `POST /api/v1/runs` handler: pass `required_capabilities` to `process_ticket()`
- Result response: include `matched_capability_record` if present

### Orchestrator Side

`dispatcher_client.py`:
- Add `derive_required_capabilities(to_state, ticket_tags)` function with `STATE_CAPABILITIES` mapping
- Pass result as `required_capabilities` in run trigger payload
- Extract and log `matched_capability_record` from result

No changes to `fsm/engine.py`.

### Test Strategy

- Unit tests mock DB (use existing `autouse` fixture in `tests/integration/conftest.py`)
- Integration tests use the existing in-memory SQLite setup (`aiosqlite`) for non-PostgreSQL-specific tests
- Contract tests validate request/response shapes against `contracts/` specs
- Coverage gate: ≥80% (same as existing)

---

## Complexity Tracking

No constitution violations. No additional complexity justification needed.
