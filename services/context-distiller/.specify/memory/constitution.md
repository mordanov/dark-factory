<!--
SYNC IMPACT REPORT
==================
Version change: unversioned → 1.0.0
Bump rationale: MINOR — first formal adoption; Governance section and versioning
  metadata added to a previously-unversioned document.

Modified principles: none (all seven principles retained as-is)
Added sections:
  - Governance (amendment procedure, versioning policy, compliance review)
  - Version/Ratification footer

Removed sections: none

Templates reviewed:
  ✅ .specify/templates/plan-template.md — "Constitution Check" gate is generic;
     no hard-coded principle names. No update needed.
  ✅ .specify/templates/spec-template.md — No constitution-specific references.
     No update needed.
  ✅ .specify/templates/tasks-template.md — No constitution-specific references.
     No update needed.

Deferred TODOs: none
-->

# ContextDistiller — Project Constitution

## Identity

ContextDistiller is a standalone async microservice within the Dark Factory system.
Its sole responsibility is progressive compression: it transforms the complete history
of a closed ticket (audit trail, ticket data, agent outputs) into a compact,
structured YAML "project memory" that fits within the LLM context window of any
subsequent Orchestrator invocation.

ContextDistiller does not make decisions. It does not govern workflow.
It only distills facts.

---

## Core Principles

### 1. Async-first, never blocking

ContextDistiller MUST never be called synchronously in the critical path of
ticket processing. It is always triggered via a job queue (PostgreSQL jobs table,
job_type = "distill") after the Orchestrator confirms a ticket has reached `done`.
Any implementation that introduces synchronous coupling to the Orchestrator or
Ticket Manager violates this principle.

### 2. Idempotent distillation

Running distillation twice on the same ticket MUST produce equivalent (not necessarily
identical) output. The service MUST NOT error or produce corrupted state if triggered
more than once for the same ticket. The latest version always wins in MongoDB.

### 3. Lossless risk propagation

Open risks and known constraints identified in any ticket MUST be carried forward
into project memory, even if the risk was not resolved. A risk is only removed from
project memory if a subsequent ticket explicitly resolves it. When in doubt, keep
the risk.

### 4. Bounded output

Every distillation call MUST respect `DISTILLER_MAX_MEMORY_TOKENS` (default: 2000).
The LLM prompt MUST enforce this limit explicitly. Output that exceeds the budget
MUST be truncated by the LLM, not post-processed by code. The schema defines which
sections to trim first: `recent_changes` (oldest entries first), then `architecture`
(least recently referenced), never `open_risks` or `known_constraints`.

### 5. History before overwrite

Before overwriting `project_memory` in MongoDB, the current version MUST always be
archived to `project_memory_history`. The history collection retains the last
`DISTILLER_MEMORY_HISTORY_KEEP` versions (default: 20). Violation of this principle
makes rollback impossible.

### 6. ADRs are immutable append-only records

ContextDistiller MAY create new ADR documents in MongoDB but MUST never modify or
delete existing ones. Status changes (proposed → accepted → superseded) are the
only permitted mutation, and only via an explicit `update_adr_status` call.
ADR content (title, decision, consequences) is write-once.

### 7. Graceful degradation on missing context

If project memory does not exist yet (first ticket), distillation proceeds with
reduced context and produces a fresh memory document. This is not an error.
If the LLM call fails, the job MUST be marked `failed` in the jobs table and the
error recorded. The Orchestrator continues functioning without updated memory —
stale memory is preferable to a blocked workflow.

---

## Technology Stack

These choices are non-negotiable for the initial implementation:

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.12 | Consistency with all other Dark Factory services |
| API framework | FastAPI (async) | Consistency; auto-generated OpenAPI |
| Job queue | PostgreSQL jobs table + `asyncpg` LISTEN/NOTIFY | No additional infrastructure; same pattern as Orchestrator |
| Document store | MongoDB via Motor (async) | Chosen for document-oriented project memory |
| LLM | OpenAI API (`openai` Python SDK, async) | Configurable model via `OPENAI_MODEL` env var |
| Configuration | Pydantic Settings + `.env` | Same pattern as all Dark Factory services |
| Containerisation | Docker + Docker Compose | Required for all services |

**MongoDB collections (names are fixed, do not rename):**

- `project_memory` — one document per project, `_id = project_id`
- `project_memory_history` — versioned snapshots, never deleted beyond `HISTORY_KEEP`
- `adrs` — one document per ADR, `_id = "ADR-{NNN}"`, append-only content

---

## Service Boundaries

ContextDistiller owns:
- All read/write access to `project_memory`, `project_memory_history`, `adrs` in MongoDB
- The distillation LLM prompt and its response parsing
- The `/distill`, `/memory/*`, `/adrs/*` API endpoints

ContextDistiller does NOT own:
- The jobs table (it reads and updates job status, but schema is owned by the Orchestrator)
- Ticket data in the Ticket Manager (read-only access via TM API)
- Any FSM state (read-only via job payload; never writes to TM FSM fields)
- JWT issuance (validates tokens issued by Prompt Studio)

---

## API Contract (non-negotiable endpoints)

All endpoints require `Authorization: Bearer <token>` (Prompt Studio JWT).

```
POST /distill
  Body: { "ticket_id": string, "project_id": string }
  Response: 202 { "job_id": string }
  Semantics: Enqueues a distill job. Does NOT run distillation synchronously.

GET /status/{job_id}
  Response: { "job_id": string, "status": "queued|running|done|failed", "error": string|null }

GET /memory/{project_id}
  Response: { "project_id", "content": "yaml string", "version": int, "last_ticket_id", "updated_at" }
  On missing: 404

GET /memory/{project_id}/adrs
  Query: ?status=accepted|proposed|all  (default: accepted)
  Response: { "adrs": [ { "id", "title", "status", "summary", "ticket_id", "created_at" } ] }

POST /memory/{project_id}/adrs
  Body: { "content": "full ADR markdown", "ticket_id": string }
  Response: 201 { "adr_id": "ADR-NNN" }
  Auth: All authenticated users (Orchestrator calls this internally)
```

No other endpoints are permitted in v1. Future endpoints require a constitution amendment.

---

## Input Contract (distill job payload)

The Orchestrator writes this payload into the jobs table when enqueuing a distill job:

```json
{
  "ticket_id": "string",
  "project_id": "string",
  "audit_trail": [
    { "action": "string", "details": "string", "created_at": "ISO8601" }
  ],
  "ticket_snapshot": {
    "title": "string",
    "description": "string",
    "ticket_type": "feature|bugfix|improvement",
    "tags": ["string"],
    "fsm_status": "done"
  }
}
```

If `audit_trail` is empty or `ticket_snapshot` is minimal, distillation proceeds
with reduced context. Never error on missing optional fields.

---

## Output Schema (project memory YAML — enforced by LLM prompt)

The LLM must produce valid YAML conforming exactly to this schema.
The distiller service validates the output with `yaml.safe_load` before saving.
If parsing fails, the job is marked `failed` and the raw LLM output is stored
in `jobs.error_message` for debugging.

```yaml
project_id: "string"
last_updated: "ISO8601"
last_ticket_id: "string"

architecture:
  - "Single declarative string per architectural fact"

recent_changes:
  - ticket_id: "string"
    summary: "One sentence"
    files_changed: ["path/to/file.py"]
    risks:
      - "string"                     # risks that remain open from this ticket

open_risks:
  - "string"                         # accumulated across all tickets

known_constraints:
  - "string"                         # rules agents must not violate (from ADRs etc.)

tech_stack:
  backend: "string"
  frontend: "string"
  database: "string"
  infra: "string"
```

Deviation from this schema by the LLM must cause a retry (max 2 retries), then
job failure. Do not attempt to salvage malformed YAML with heuristic parsing.

---

## Testing Requirements

- Minimum **80% line coverage** enforced by `.coveragerc` (`fail_under = 80`)
- Unit tests MUST cover: YAML schema validation, ADR markdown parsing,
  project memory versioning logic, history pruning, output token budget enforcement
- Integration tests MUST cover: full job lifecycle (enqueue → run → done),
  MongoDB write/read round-trip (using `mongomock-motor`), 404 on missing memory,
  idempotent re-distillation
- LLM calls MUST be mocked in all tests — no real API calls in CI
- Every test that writes to MongoDB MUST use an isolated collection prefix or
  `mongomock-motor` — never a shared real MongoDB instance in tests

---

## Environment Variables (all required unless marked optional)

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL async URL (jobs table) |
| `MONGO_URL` | `mongodb://mongo:27017` | |
| `MONGO_DB_NAME` | `dark_factory_docs` | Must match Orchestrator |
| `JWT_SECRET_KEY` | — | **Must match Prompt Studio exactly** |
| `JWT_ALGORITHM` | `HS256` | |
| `OPENAI_API_KEY` | — | |
| `OPENAI_MODEL` | `gpt-4o-mini` | Any OpenAI chat model |
| `OPENAI_TIMEOUT_SECONDS` | `120` | |
| `TICKET_MANAGER_BASE_URL` | — | For fetching ticket context |
| `TICKET_MANAGER_SERVICE_EMAIL` | — | |
| `TICKET_MANAGER_SERVICE_PASSWORD` | — | |
| `DISTILLER_MAX_MEMORY_TOKENS` | `2000` | Hard cap on LLM output |
| `DISTILLER_MEMORY_HISTORY_KEEP` | `20` | Versions to retain per project |
| `WORKER_MAX_CONCURRENT_JOBS` | `3` | asyncio.Semaphore limit |
| `WORKER_POLL_INTERVAL_SECONDS` | `5` | Fallback poll if NOTIFY missed |

---

## Definition of Done

A feature or change to ContextDistiller is considered complete when:

1. All existing tests pass with no regressions
2. New code reaches ≥ 80% line coverage
3. The distillation LLM prompt has been tested with at least two representative
   ticket payloads (feature + bugfix) and produces valid YAML conforming to the schema
4. Docker build succeeds (`docker build .`)
5. The service starts cleanly in `docker compose up` alongside the existing
   Dark Factory services (postgres, mongo, orchestrator, backend, frontend)
6. The `/api/health` endpoint returns `{ "status": "ok" }` under load
7. No direct coupling to Orchestrator internals has been introduced —
   ContextDistiller communicates only via the jobs table and MongoDB

---

## Principles That Must Never Be Violated

These are hard constraints. No feature, deadline, or convenience justifies
breaking them:

- **Never call the Orchestrator synchronously.** ContextDistiller is downstream.
- **Never delete project memory.** Archive to history, then overwrite.
- **Never mutate ADR content.** Only status transitions are permitted.
- **Never swallow LLM errors silently.** Failed jobs must be visible in the jobs table.
- **Never write to TM FSM fields.** ContextDistiller is read-only toward TM.
- **Never block the test suite on real external services.** Mock everything.

---

## Governance

### Amendment Procedure

1. Any amendment to this constitution MUST be proposed as a pull request against
   `main` and MUST update the `CONSTITUTION_VERSION` and `LAST_AMENDED_DATE` fields.
2. Amendments that add new principles or materially expand existing ones are MINOR
   version bumps. Backward-incompatible removals or redefinitions are MAJOR bumps.
   Clarifications and wording fixes are PATCH bumps.
3. Any PR that introduces implementation changes conflicting with an existing
   principle MUST amend the constitution first — not the other way around.
4. The `Principles That Must Never Be Violated` section requires unanimous team
   agreement to modify and MUST be recorded as a MAJOR version bump.

### Versioning Policy

Semantic versioning applies: `MAJOR.MINOR.PATCH`

| Change type | Bump |
|---|---|
| Governance restructure, principle removal or redefinition | MAJOR |
| New principle, new mandatory section, material guidance expansion | MINOR |
| Clarification, wording fix, formatting, typo | PATCH |

### Compliance Review

- Every implementation plan (`/speckit-plan`) MUST include a Constitution Check gate
  before Phase 0 research and re-check after Phase 1 design.
- CI MUST fail if a new endpoint is added to the service without a corresponding
  constitution amendment adding it to the API Contract section.
- Deviations from the Technology Stack table are not permitted without a MINOR
  amendment documenting the rationale.

---

**Version**: 1.0.0 | **Ratified**: 2026-06-20 | **Last Amended**: 2026-06-20