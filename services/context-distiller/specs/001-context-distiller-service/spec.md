# Feature Specification: ContextDistiller Service

**Feature Branch**: `001-context-distiller-service`
**Created**: 2026-06-20
**Status**: Draft
**Input**: Implement ContextDistiller service — a standalone async microservice that
compresses completed ticket histories into structured project memory for consumption
by the Orchestrator and other Dark Factory agents.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Distillation job runs after a ticket is closed (Priority: P1)

When the Orchestrator marks a ticket as `done` and enqueues a `distill` job, the
ContextDistiller worker picks it up, calls the LLM, and persists an updated project
memory document in MongoDB. The Orchestrator can then retrieve that memory for the
next ticket cycle.

**Why this priority**: This is the core value proposition. Without it, the service
does nothing. Every other story depends on distillation being functional.

**Independent Test**: Enqueue a `distill` job via `POST /distill` with a mock ticket
payload, poll `GET /status/{job_id}` until `done`, then verify `GET /memory/{project_id}`
returns a valid YAML document containing facts derived from the ticket.

**Acceptance Scenarios**:

1. **Given** a ticket with `fsm_status = done` and a full audit trail,
   **When** a `distill` job is enqueued via `POST /distill`,
   **Then** the service returns `202 Accepted` with a `job_id` immediately (not after LLM completes).

2. **Given** a queued `distill` job,
   **When** the worker processes it successfully,
   **Then** `GET /status/{job_id}` returns `{ "status": "done" }` and
   `GET /memory/{project_id}` returns a YAML document matching the output schema
   (fields: `project_id`, `last_updated`, `last_ticket_id`, `architecture`,
   `recent_changes`, `open_risks`, `known_constraints`, `tech_stack`).

3. **Given** a `distill` job is triggered twice for the same ticket,
   **When** both jobs complete,
   **Then** both succeed without error, and the final memory document reflects the
   ticket correctly (idempotent — no duplicate `recent_changes` entries for the
   same ticket).

4. **Given** a project that has no prior memory document,
   **When** the first `distill` job completes,
   **Then** a new memory document is created from scratch; the service does not
   error on missing prior memory.

---

### User Story 2 — Orchestrator retrieves project memory (Priority: P1)

The Orchestrator reads the current project memory before assembling context for an
agent invocation. It must be able to fetch the memory document and the accepted ADR
list via stable API endpoints.

**Why this priority**: Equal priority to US1 — distillation without retrieval is
useless. Both form the complete read/write cycle of project memory.

**Independent Test**: Write a known memory document directly to MongoDB, then call
`GET /memory/{project_id}` and `GET /memory/{project_id}/adrs?status=accepted`
and verify both responses match the stored data.

**Acceptance Scenarios**:

1. **Given** a project memory document exists in MongoDB,
   **When** `GET /memory/{project_id}` is called with a valid JWT,
   **Then** the response contains `project_id`, `content` (YAML string),
   `version` (integer), `last_ticket_id`, and `updated_at`.

2. **Given** no memory document exists for a project,
   **When** `GET /memory/{project_id}` is called,
   **Then** the service returns `404 Not Found`.

3. **Given** ADRs exist for a project with statuses `accepted`, `proposed`,
   and `superseded`,
   **When** `GET /memory/{project_id}/adrs?status=accepted` is called,
   **Then** only ADRs with `status = accepted` are returned.

4. **Given** `GET /memory/{project_id}/adrs` is called without a `status` filter,
   **Then** only `accepted` ADRs are returned (default filter).

---

### User Story 3 — ADR creation and immutability (Priority: P2)

The Orchestrator creates new ADR documents via the ContextDistiller API. Once
created, ADR content is never modified. Only the status field can transition
through its lifecycle.

**Why this priority**: ADRs are referenced by `known_constraints` in project memory.
They must be reliably created and protected from mutation before memory reads
become meaningful.

**Independent Test**: Create an ADR via `POST /memory/{project_id}/adrs`, then
attempt to overwrite its content — the service must reject the mutation while
still allowing a status transition.

**Acceptance Scenarios**:

1. **Given** a valid ADR markdown body and a `ticket_id`,
   **When** `POST /memory/{project_id}/adrs` is called,
   **Then** the service returns `201` with `{ "adr_id": "ADR-NNN" }` where NNN
   is the next sequential number for that project.

2. **Given** an existing ADR `ADR-001`,
   **When** any caller attempts to update its `title`, `decision`, or `content`
   fields,
   **Then** the service returns `405 Method Not Allowed` or `403 Forbidden`
   (content is write-once).

3. **Given** an existing ADR with `status = proposed`,
   **When** a status transition to `accepted` is requested,
   **Then** the ADR's `status` field is updated and `updated_at` is refreshed,
   while all other fields remain unchanged.

---

### User Story 4 — History archival and rollback visibility (Priority: P2)

Before every memory overwrite, the prior version is archived. The history
collection retains a configurable number of versions. No version is silently
dropped.

**Why this priority**: Without history, a bad distillation can permanently corrupt
project memory. This is the safety net required by the constitution's Principle 5.

**Independent Test**: Trigger distillation 3 times on the same project, verify that
`project_memory_history` contains 3 documents (version N-2, N-1, N-current archived
before overwrite) and that the current `project_memory` reflects the latest run.

**Acceptance Scenarios**:

1. **Given** a project memory at version 5,
   **When** a new distillation completes,
   **Then** version 5 is archived to `project_memory_history` before version 6
   is written to `project_memory`.

2. **Given** `DISTILLER_MEMORY_HISTORY_KEEP = 3` and a project with 4 completed
   distillations,
   **When** the 5th distillation completes,
   **Then** `project_memory_history` contains exactly 3 entries (the three most
   recent prior versions); the oldest is pruned.

---

### User Story 5 — Graceful failure and job observability (Priority: P3)

When the LLM call fails or returns malformed output, the job is marked `failed`
with the error recorded. The Orchestrator can poll job status and detect failures
without blocking its own workflow.

**Why this priority**: The Dark Factory Orchestrator continues operating on stale
memory if distillation fails (per Principle 7). Visibility into failures is needed
for ops, but it does not block P1/P2 delivery.

**Independent Test**: Configure the LLM mock to return invalid YAML on the second
call. Trigger a distill job, verify status transitions to `failed`, and confirm
the raw LLM output is stored in `error_message`.

**Acceptance Scenarios**:

1. **Given** the LLM returns invalid YAML (not parseable by `yaml.safe_load`),
   **When** the distiller attempts 2 retries and all fail,
   **Then** the job status is set to `failed`, `error_message` contains the raw
   LLM output, and `project_memory` is NOT overwritten.

2. **Given** the LLM call times out (exceeds `OPENAI_TIMEOUT_SECONDS`),
   **When** the job fails,
   **Then** the job status is `failed` with an appropriate error message, and
   the worker is ready to accept the next job immediately.

3. **Given** a `failed` job,
   **When** `GET /status/{job_id}` is called,
   **Then** the response contains `{ "status": "failed", "error": "<message>" }`.

---

### Edge Cases

- What happens if `audit_trail` is empty in the job payload? Distillation
  proceeds with reduced context; this is not an error (per Principle 7).
- What happens if `project_memory` is corrupted in MongoDB? The worker treats it
  as absent (proceeds as first-ticket fresh start) and logs a warning.
- What happens if `DISTILLER_MAX_MEMORY_TOKENS` is set very low (e.g., 100)?
  The LLM truncates output according to the priority order defined in Principle 4;
  the result may be minimal but must still be valid YAML.
- What happens if the Ticket Manager API is unreachable during data collection?
  The job fails with a clear error; it does not partially save degraded memory.
- What happens if two workers race on the same job? Each job row is claimed via
  a PostgreSQL `FOR UPDATE SKIP LOCKED` pattern; only one worker runs it.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The service MUST expose `POST /distill` that accepts `ticket_id` and
  `project_id`, enqueues a `distill` job in the PostgreSQL jobs table, and returns
  `202 Accepted` with a `job_id` without waiting for the LLM.
- **FR-002**: The service MUST run an async worker that claims `distill` jobs via
  `LISTEN/NOTIFY` (primary) and periodic polling (fallback), with concurrency
  bounded by `WORKER_MAX_CONCURRENT_JOBS`.
- **FR-003**: The worker MUST collect ticket data from Ticket Manager API and
  audit trail entries from the orchestrator's `audit_log` table before calling the LLM.
- **FR-004**: The LLM call MUST include the current project memory (if it exists)
  as incremental merge context.
- **FR-005**: The LLM output MUST be validated with `yaml.safe_load` against the
  output schema; on parse failure the worker MUST retry up to 2 times before
  marking the job `failed`.
- **FR-006**: Before writing a new memory document to `project_memory`, the service
  MUST archive the previous version to `project_memory_history`.
- **FR-007**: The `project_memory_history` collection MUST be pruned to the last
  `DISTILLER_MEMORY_HISTORY_KEEP` versions per project after each distillation.
- **FR-008**: The service MUST expose `GET /status/{job_id}` returning job status
  and error message.
- **FR-009**: The service MUST expose `GET /memory/{project_id}` returning the
  current memory document, or `404` if none exists.
- **FR-010**: The service MUST expose `GET /memory/{project_id}/adrs` with an
  optional `status` query filter (default: `accepted`).
- **FR-011**: The service MUST expose `POST /memory/{project_id}/adrs` that creates
  a new, immutable ADR document with an auto-incremented `ADR-NNN` identifier.
- **FR-012**: ADR content fields (title, decision, consequences) MUST be
  write-once; only `status` transitions are permitted after creation.
- **FR-013**: All endpoints MUST require a valid Prompt Studio JWT
  (`Authorization: Bearer <token>`).
- **FR-014**: The service MUST expose `GET /api/health` returning `{ "status": "ok" }`.
- **FR-015**: No other v1 endpoints are permitted; future endpoints require a
  constitution amendment.

### Key Entities

- **Job** (`jobs` table, owned by Orchestrator): `id`, `job_type="distill"`,
  `ticket_id`, `project_id`, `status`, `payload`, `error_message`, `attempts`.
  ContextDistiller reads and updates status only.
- **ProjectMemory** (`project_memory` collection): `_id=project_id`, `content`
  (YAML string), `version`, `last_ticket_id`, `updated_at`. One document per project.
- **ProjectMemoryHistory** (`project_memory_history` collection): `project_id`,
  `version`, `content`, `ticket_id`, `created_at`. Pruned to last N versions.
- **ADR** (`adrs` collection): `_id="ADR-NNN"`, `project_id`, `title`, `status`
  (proposed|accepted|superseded), `content` (full markdown), `ticket_id`,
  `created_at`, `updated_at`. Content is immutable after creation.
- **AuditLog** (`audit_log` table, owned by Orchestrator): `ticket_id`,
  `project_id`, `action`, `from_state`, `to_state`, `details`, `created_at`.
  ContextDistiller reads only.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A distill job enqueued after a ticket closes completes within
  30 seconds under normal load (single concurrent job, LLM responding within
  its timeout).
- **SC-002**: Running distillation twice on the same ticket produces a valid
  memory document both times with no errors and no duplicate `recent_changes`
  entries for that ticket.
- **SC-003**: 100% of completed distillations have the prior memory version
  archived in `project_memory_history` before the new version is written.
- **SC-004**: A failed LLM call (invalid YAML after 2 retries) leaves the
  existing `project_memory` unchanged and records the failure in the jobs table
  within the same worker cycle.
- **SC-005**: The service sustains `WORKER_MAX_CONCURRENT_JOBS` concurrent
  distillations without deadlocks or data corruption in MongoDB.
- **SC-006**: Test suite passes with ≥ 80% line coverage and zero real LLM or
  external API calls in CI.
- **SC-007**: `GET /api/health` returns `{ "status": "ok" }` within 500ms under
  all normal operating conditions.

---

## Assumptions

- The Orchestrator is responsible for inserting the `distill` job row into the
  `jobs` table; `POST /distill` is the external trigger but the ContextDistiller
  service also inserts the job internally when called via API.
- The Ticket Manager API is available at `TICKET_MANAGER_BASE_URL` and
  authentication uses service-account credentials
  (`TICKET_MANAGER_SERVICE_EMAIL` / `TICKET_MANAGER_SERVICE_PASSWORD`).
- JWT validation uses the shared `JWT_SECRET_KEY` and `JWT_ALGORITHM` (HS256)
  issued by Prompt Studio; ContextDistiller never issues tokens.
- The PostgreSQL database is shared with the Orchestrator; ContextDistiller
  connects via `DATABASE_URL` (same DB, read/write on `jobs` and `audit_log`,
  never on FSM or ticket tables directly).
- MongoDB is shared across Dark Factory services; collection names are fixed per
  the constitution and must not be renamed.
- Phase 1 scope excludes git diff enrichment (Principle 4 roadmap item).
  `files_changed` in the output schema is populated from ticket metadata only.
- The LLM model is configurable via `OPENAI_MODEL`; the service is not coupled
  to a specific model.
- `mongomock-motor` is used for all MongoDB interactions in tests; no shared
  real MongoDB instance is used in CI.
