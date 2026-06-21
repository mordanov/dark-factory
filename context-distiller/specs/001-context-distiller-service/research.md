# Research: ContextDistiller Service

**Feature**: 001-context-distiller-service
**Date**: 2026-06-20

---

## D-001 — PostgreSQL DB Schema Ownership

**Decision**: ContextDistiller shares the Orchestrator's PostgreSQL database.
It reads `jobs` (WHERE job_type='distill') and `audit_log` (read-only). ORM
models are copied locally to avoid import coupling across service boundaries;
the copies are kept in sync with the Orchestrator's schema by convention.

**Rationale**: The constitution explicitly states the jobs table schema is owned
by the Orchestrator. ContextDistiller only "reads and updates job status." Using
the same DB avoids a second migration history and additional infrastructure.

**Alternatives considered**:
- Dedicated `distill_jobs` table — cleaner ownership but violates constitution;
  Orchestrator would need to write to a table it doesn't own.
- Message broker (Redis/RabbitMQ) — would decouple services but adds
  infrastructure; constitution permits PostgreSQL queue pattern.

---

## D-002 — Job Claiming Pattern

**Decision**: `SELECT ... FOR UPDATE SKIP LOCKED` on `jobs` filtered by
`job_type='distill' AND status='pending'`, with asyncpg LISTEN/NOTIFY
(`df_new_job` channel) as the primary wake-up and a `WORKER_POLL_INTERVAL_SECONDS`
fallback poll. This is the exact same pattern the Orchestrator job_worker uses.

**Rationale**: Already proven in the codebase. SKIP LOCKED is the standard
PostgreSQL advisory lock pattern for job queues — prevents two workers claiming
the same row. No additional dependencies needed.

**Alternatives considered**:
- Celery + Redis — fully-featured task queue but requires Redis infrastructure
  (the architecture.md mentions this as original design; constitution supercedes
  with "PostgreSQL jobs table" as the mandated approach).
- asyncpg advisory locks — more complex, SKIP LOCKED is simpler and sufficient.

---

## D-003 — MongoDB Driver and Test Isolation

**Decision**: Motor 3.5 (async) as the MongoDB driver, matching the Orchestrator.
`mongomock-motor 0.0.21` for all test isolation — no shared real MongoDB in CI.
Collection names are fixed per the constitution:
`project_memory`, `project_memory_history`, `adrs`.

**Rationale**: Motor is already in the requirements baseline. mongomock-motor
provides a full in-process MongoDB mock that supports Motor's async API, enabling
reliable unit and integration tests without external dependencies.

**Alternatives considered**:
- beanie (ODM on top of Motor) — cleaner models but adds a dependency and
  abstracts away the raw collection operations that the constitution mandates
  by name. Rejected for simplicity.
- testcontainers-python + real MongoDB — more faithful but slower CI and
  requires Docker-in-Docker. mongomock-motor is sufficient for this service's
  query patterns.

---

## D-004 — ADR Immutability Enforcement

**Decision**: The `adrs` collection document is write-once for content fields
(`title`, `content`, `decision`). Only `status` and `updated_at` are mutable.
A dedicated `PATCH /memory/{project_id}/adrs/{adr_id}/status` endpoint handles
status transitions. No PUT/PATCH on the full ADR document is exposed.
The repository layer raises `ConflictError` (HTTP 409) on any attempt to update
content fields regardless of caller.

**Rationale**: Constitution Principle 6 is a hard constraint — "ADR content is
write-once." Enforcing this at the repository layer (not just the API) means
it cannot be bypassed by future endpoint additions without a deliberate change.

**Alternatives considered**:
- Immutability only at API layer — rejected; could be bypassed by future
  internal calls.
- MongoDB validator rule on the collection — useful defence-in-depth but
  adds operational complexity. Will be considered for Phase 2 hardening.

---

## D-005 — LLM Retry Strategy

**Decision**: On YAML parse failure (`yaml.safe_load` raises an exception),
retry the same prompt up to 2 additional times (3 total attempts, `temperature=0.2`
for low variance). On LLM timeout or API error: no retry, immediate fail.
After all retries exhausted: mark job `failed`, store raw LLM output in
`error_message`, leave `project_memory` untouched.

**Rationale**: Constitution Principle 7 — stale memory is preferable to a
blocked workflow. Principle 4 — the LLM is responsible for truncation; we
must not salvage malformed YAML with heuristic parsing.

**Alternatives considered**:
- Prompt repair on parse failure (inject the error into a second prompt) —
  more aggressive recovery but complicates the prompt engineering and risks
  compound hallucinations. Deferred to Phase 3.
- More than 2 retries — increases latency and OpenAI cost with diminishing
  returns. Two retries is the minimum meaningful safety net.

---

## D-006 — No Alembic Migrations in Phase 1

**Decision**: ContextDistiller owns no PostgreSQL tables in Phase 1. Alembic
is scaffolded (directory + env.py) but contains no migration files. The service
connects to the Orchestrator's database and reads existing tables only.

**Rationale**: Clean schema ownership boundary. Avoids migration conflicts with
the Orchestrator. If Phase 3 introduces embeddings or other ContextDistiller-
owned PG tables, Alembic will be activated then.

**Alternatives considered**:
- Separate PostgreSQL database — full isolation but doubles infra; the
  constitution permits sharing the jobs table.

---

## Integration Points Confirmed

| System | How ContextDistiller integrates | Auth |
|--------|--------------------------------|------|
| PostgreSQL (Orchestrator DB) | SQLAlchemy async session, shared DATABASE_URL | DB credentials |
| MongoDB | Motor async client, MONGO_URL / MONGO_DB_NAME | DB credentials |
| Ticket Manager API | httpx AsyncClient to TICKET_MANAGER_BASE_URL | Service account JWT obtained via /auth/login |
| OpenAI API | openai AsyncOpenAI client | OPENAI_API_KEY |
| JWT validation | python-jose, shared JWT_SECRET_KEY (HS256) | Issued by Prompt Studio |

---

## Ticket Manager API Endpoints Needed

Based on reading `../ticket-manager/backend/src/`:

- `GET /api/v1/tickets/{ticket_id}` — fetch full ticket snapshot
- `GET /api/v1/tickets/{ticket_id}/events` — fetch ticket events (audit trail)
- `POST /api/v1/auth/login` — obtain service account JWT

TM uses `TicketStatus` enum values: `OPEN`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`, `CLOSED`.
ContextDistiller triggers on jobs where `ticket_snapshot.fsm_status = "done"`.
