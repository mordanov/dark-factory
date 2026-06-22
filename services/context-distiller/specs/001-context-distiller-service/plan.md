# Implementation Plan: ContextDistiller Service

**Branch**: `001-context-distiller-service` | **Date**: 2026-06-20
**Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/001-context-distiller-service/spec.md`

## Summary

Implement ContextDistiller as a standalone FastAPI async microservice that picks
up `distill` jobs from the shared PostgreSQL jobs table (LISTEN/NOTIFY + poll
fallback), fetches ticket data from Ticket Manager and audit entries from the
orchestrator DB, calls the OpenAI API to produce project memory YAML, and
persists results to MongoDB (`project_memory`, `project_memory_history`, `adrs`).
The service exposes a minimal REST API (5 endpoints) for job submission, status
polling, memory retrieval, and ADR management. All patterns are inherited
directly from the Orchestrator service to maintain consistency across Dark Factory.

---

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI 0.111, asyncpg 0.29, Motor 3.5 (async MongoDB),
  SQLAlchemy 2.0 (async), Pydantic Settings, openai 1.35, httpx 0.27
**Storage**: PostgreSQL (jobs + audit_log tables — shared with Orchestrator, read/update only),
  MongoDB (project_memory, project_memory_history, adrs — owned by this service)
**Testing**: pytest + pytest-asyncio + pytest-cov, mongomock-motor, respx (mock httpx)
**Target Platform**: Linux container (Docker), same Compose network as Dark Factory
**Project Type**: Async web service + background worker
**Performance Goals**: Job completes within 30s under normal load;
  `GET /api/health` < 500ms; worker sustains `WORKER_MAX_CONCURRENT_JOBS=3` concurrent LLM calls
**Constraints**: Never block Orchestrator critical path (async-only); no new
  infrastructure (reuse PG + Mongo already in Compose); ≥ 80% test line coverage;
  LLM calls mocked in all tests
**Scale/Scope**: Phase 1 — single project initially, designed for multi-project
  isolation in MongoDB from day one; no git diff enrichment in this phase

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| 1. Async-first, never blocking | ✅ PASS | POST /distill returns 202 immediately; worker is background asyncio task |
| 2. Idempotent distillation | ✅ PASS | Worker uses FOR UPDATE SKIP LOCKED; duplicate jobs produce valid output, latest wins |
| 3. Lossless risk propagation | ✅ PASS | LLM system prompt explicitly mandates keeping open_risks; validated in output schema |
| 4. Bounded output | ✅ PASS | max_tokens=DISTILLER_MAX_MEMORY_TOKENS enforced in OpenAI call; trim order in prompt |
| 5. History before overwrite | ✅ PASS | archive_memory() called before every write_memory(); tested in integration suite |
| 6. ADRs immutable append-only | ✅ PASS | POST /adrs creates only; no PUT/PATCH on content fields; status transitions via dedicated endpoint |
| 7. Graceful degradation | ✅ PASS | Missing memory → fresh start (not error); LLM failure → job marked failed, memory unchanged |

**Pre-Phase-0 gate: PASS.** No violations require justification.

---

## Project Structure

### Documentation (this feature)

```text
specs/001-context-distiller-service/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── api.md           # REST endpoint contracts
│   └── job-payload.md   # Distill job payload schema
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── api/
│   ├── __init__.py
│   ├── dependencies.py       # JWT validation, DB session, Mongo DB
│   └── v1/
│       ├── __init__.py
│       ├── distill.py         # POST /distill, GET /status/{job_id}
│       └── memory.py          # GET /memory/{id}, GET+POST /memory/{id}/adrs
├── core/
│   ├── __init__.py
│   ├── config.py              # Pydantic Settings (env vars)
│   ├── exceptions.py          # UpstreamError, NotFoundError, ConflictError
│   └── security.py            # JWT decode (validate only, no issue)
├── db/
│   ├── __init__.py
│   ├── postgres.py            # Async SQLAlchemy engine + session factory
│   └── mongo.py               # Motor client + db handle
├── models/
│   └── __init__.py            # Re-exports Job, AuditLog from orchestrator models
│                              #   (or local copies — see research.md)
├── repositories/
│   ├── __init__.py
│   ├── job_repo.py            # claim_distill_job(), mark_running/done/failed()
│   ├── audit_repo.py          # get_audit_trail(ticket_id)
│   └── memory_repo.py         # get/write project_memory, ADR CRUD
├── schemas/
│   ├── __init__.py
│   └── schemas.py             # DistillRequest, JobStatusResponse, MemoryResponse,
│                              #   AdrCreate, AdrResponse, HealthResponse
├── services/
│   ├── __init__.py
│   ├── distiller.py           # LLM call + YAML validation (max 2 retries)
│   ├── data_collector.py      # TM API fetch + audit_log read
│   └── tm_client.py           # httpx AsyncClient for Ticket Manager API
├── workers/
│   ├── __init__.py
│   └── job_worker.py          # asyncpg LISTEN/NOTIFY + poll + Semaphore
└── main.py                    # FastAPI app, lifespan (worker start/stop), routers

tests/
├── conftest.py                # Fixtures: test app, mock DB sessions, mongomock
├── unit/
│   ├── test_distiller.py      # YAML validation, retry logic, token budget
│   ├── test_memory_repo.py    # archive-before-overwrite, history pruning
│   ├── test_adr_repo.py       # ADR create, immutability guard, status transitions
│   └── test_data_collector.py # TM client mock, audit trail assembly
└── integration/
    ├── test_distill_lifecycle.py  # Enqueue → worker runs → done; idempotent re-run
    ├── test_memory_api.py         # GET /memory, 404, GET /adrs, POST /adrs
    └── test_job_status.py         # GET /status/{job_id}, failed job error field

alembic/                       # Migrations (only if ContextDistiller owns any PG tables)
                               #   Phase 1: none — shares Orchestrator's jobs table

Dockerfile
docker-compose.override.yml   # Add context-distiller service to existing Compose
.env.example
requirements.txt
pytest.ini
.coveragerc                   # fail_under = 80
```

**Structure Decision**: Single service layout (no frontend). Mirrors the Orchestrator
service structure exactly for consistency — same layer names, same patterns,
same testing conventions. The service runs as its own container alongside the
existing Dark Factory services.

---

## Phase 0: Research

*See [research.md](./research.md) for full findings.*

### Key Decisions

**D-001 — DB Schema ownership**
- Decision: ContextDistiller uses the Orchestrator's `jobs` and `audit_log` tables
  directly via shared DATABASE_URL. It does NOT duplicate the ORM models — it
  imports or copies them locally with a read-only stance.
- Rationale: The constitution explicitly states the jobs table schema is owned
  by the Orchestrator. Sharing the same DB avoids a second migration history.
- Alternative rejected: A dedicated `distill_jobs` table would decouple schemas
  but violates the constitution's cross-service ownership model.

**D-002 — Job claiming pattern**
- Decision: `SELECT ... FOR UPDATE SKIP LOCKED` on the `jobs` table filtered by
  `job_type='distill' AND status='pending'`, same as the Orchestrator worker.
- Rationale: asyncpg LISTEN/NOTIFY + poll fallback already proven in Orchestrator.
  FOR UPDATE SKIP LOCKED prevents two workers racing on the same job.
- Alternative rejected: Separate Redis queue would require new infrastructure.

**D-003 — MongoDB driver**
- Decision: Motor 3.5 (async) via mongomock-motor in tests. Same as Orchestrator.
- Rationale: Already in the stack; async-native; mongomock-motor provides full
  test isolation without a running MongoDB instance.

**D-004 — ADR immutability enforcement**
- Decision: In `memory_repo.py`, `update_adr` only allows updates to the `status`
  field. Any attempt to update other fields raises `ConflictError` (HTTP 409).
  There is no PUT/PATCH endpoint for ADR content — only a dedicated
  `PATCH /memory/{project_id}/adrs/{adr_id}/status` endpoint.
- Rationale: Constitution Principle 6 — content is write-once.

**D-005 — LLM retry strategy**
- Decision: Up to 2 retries (3 total attempts) on YAML parse failure. On each retry
  the same prompt is re-sent (temperature=0.2 for low variance). After all retries
  exhausted, job is marked `failed` with the raw output stored in `error_message`.
  Current memory is NOT touched.
- Rationale: Constitution Principle 7 — stale memory preferable to blocked workflow.

**D-006 — No Alembic migrations in Phase 1**
- Decision: ContextDistiller shares the Orchestrator's PostgreSQL database and
  reads existing tables. No new PG tables in Phase 1. Alembic is scaffolded but
  contains no migrations.
- Rationale: Keeps schema ownership clean. If ContextDistiller needs its own PG
  tables in future (e.g., Phase 3 embeddings), migrations will be added then.

---

## Phase 1: Design & Contracts

*See [data-model.md](./data-model.md) and [contracts/](./contracts/) for full details.*

### Data Model Summary

**PostgreSQL (read/update — Orchestrator owns schema)**

`jobs` table (relevant columns for distiller):
- `id` UUID PK
- `job_type` = `"distill"`
- `ticket_id` / `project_id` VARCHAR
- `status` = pending | running | done | failed
- `payload` JSONB — `{ ticket_id, project_id, audit_trail[], ticket_snapshot{} }`
- `error_message` TEXT — raw LLM output on parse failure
- `attempts` INT

`audit_log` table (read-only):
- `ticket_id`, `project_id`, `action`, `from_state`, `to_state`, `details`, `created_at`

**MongoDB (owned by ContextDistiller)**

`project_memory`:
```json
{
  "_id": "<project_id>",
  "content": "<yaml string>",
  "version": 1,
  "last_ticket_id": "<ticket_id>",
  "updated_at": "ISO8601"
}
```

`project_memory_history`:
```json
{
  "project_id": "<project_id>",
  "version": 0,
  "content": "<yaml string>",
  "ticket_id": "<ticket_id>",
  "created_at": "ISO8601"
}
```

`adrs`:
```json
{
  "_id": "ADR-001",
  "project_id": "<project_id>",
  "title": "<string>",
  "status": "proposed|accepted|superseded",
  "summary": "<one sentence>",
  "content": "<full markdown>",
  "ticket_id": "<ticket_id>",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

### API Endpoints Summary

See [contracts/api.md](./contracts/api.md) for full request/response schemas.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /distill | JWT | Enqueue distill job → 202 {job_id} |
| GET | /status/{job_id} | JWT | Job status + error |
| GET | /memory/{project_id} | JWT | Current project memory |
| GET | /memory/{project_id}/adrs | JWT | ADR list (filter by status) |
| POST | /memory/{project_id}/adrs | JWT | Create immutable ADR |
| PATCH | /memory/{project_id}/adrs/{adr_id}/status | JWT | Status transition only |
| GET | /api/health | None | Health check |

### Worker Flow

```
startup → JobWorker.start()
  asyncpg LISTEN "df_new_job" + initial sweep
  on NOTIFY or poll timeout → _sweep()
    SELECT jobs WHERE job_type='distill' AND status='pending'
      FOR UPDATE SKIP LOCKED LIMIT max_concurrent
    for each job:
      semaphore.acquire()
      asyncio.create_task(_run_job(job))
        mark_running()
        DataCollector.collect(ticket_id, project_id)
          → fetch ticket from TM API
          → read audit_log from PG
          → read current project_memory from Mongo
          → read ADR ids from Mongo
        distiller.distill(ticket, audit_trail, current_memory)
          → OpenAI call (max_tokens=DISTILLER_MAX_MEMORY_TOKENS)
          → yaml.safe_load() validation
          → retry up to 2x on parse failure
        memory_repo.archive_then_write(project_id, new_yaml, ticket_id)
          → write old version to project_memory_history
          → prune history to DISTILLER_MEMORY_HISTORY_KEEP
          → upsert project_memory
        mark_done()
      semaphore.release()
      on any exception → mark_failed(error_message=str(exc))
```

---

## Complexity Tracking

> No constitution violations — section intentionally blank.
