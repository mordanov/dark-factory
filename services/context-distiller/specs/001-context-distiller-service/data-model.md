# Data Model: ContextDistiller Service

**Feature**: 001-context-distiller-service
**Date**: 2026-06-20

---

## PostgreSQL (shared with Orchestrator — read/update only)

### Table: `jobs` (owned by Orchestrator)

ContextDistiller reads rows where `job_type = 'distill'` and updates `status`,
`started_at`, `finished_at`, `error_message`, `attempts`. It never inserts into
this table directly — `POST /distill` inserts via the API handler, which uses the
same SQLAlchemy model.

```
Column          Type        Description
─────────────────────────────────────────────────────────────────
id              UUID PK     Job identifier
job_type        ENUM        'distill' for all ContextDistiller jobs
ticket_id       VARCHAR     TM ticket identifier
project_id      VARCHAR     Dark Factory project identifier
status          ENUM        pending | running | done | failed
priority        INT         Higher = claimed first
triggered_by    VARCHAR     Service account or user id
payload         JSONB       Distill job input (see job-payload.md)
result          JSONB       null in Phase 1 (memory stored in Mongo)
error_message   TEXT        Raw LLM output on parse failure
attempts        INT         Incremented on each worker pickup
created_at      TIMESTAMPTZ
started_at      TIMESTAMPTZ  Set on claim
finished_at     TIMESTAMPTZ  Set on done/failed
```

**Index used by worker**: `WHERE job_type='distill' AND status='pending'` + `FOR UPDATE SKIP LOCKED`

### Table: `audit_log` (owned by Orchestrator — read-only)

```
Column            Type        Description
──────────────────────────────────────────────────────────────────
id                UUID PK
job_id            UUID FK → jobs.id (nullable)
ticket_id         VARCHAR
project_id        VARCHAR
action            VARCHAR(64)  ADVANCE, BLOCK, ASSIGN, WAIT, …
from_state        VARCHAR(64)
to_state          VARCHAR(64)
assigned_agent    VARCHAR(64)
blocked_reason    TEXT
details           TEXT
decision_payload  JSONB
created_at        TIMESTAMPTZ
```

ContextDistiller queries: `SELECT * FROM audit_log WHERE ticket_id = $1 ORDER BY created_at ASC`

---

## MongoDB (owned by ContextDistiller)

### Collection: `project_memory`

One document per project. Fully overwritten on each successful distillation
(after archiving the previous version to history).

```json
{
  "_id": "<project_id>",
  "content": "<yaml string — conforming to output schema>",
  "version": 1,
  "last_ticket_id": "<ticket_id>",
  "updated_at": "2026-06-20T12:00:00Z"
}
```

**Index**: `_id` (default) — point lookups only.

**Write invariant**: Always call `archive_then_write()`:
1. Read current document
2. If exists → insert into `project_memory_history` with same version number
3. Prune history to `DISTILLER_MEMORY_HISTORY_KEEP` (keep newest)
4. Upsert `project_memory` with `version + 1`

### Collection: `project_memory_history`

Versioned archive. Never deleted individually — only pruned by the keep-count policy.

```json
{
  "_id": "<auto ObjectId>",
  "project_id": "<project_id>",
  "version": 5,
  "content": "<yaml string — the version before the overwrite>",
  "ticket_id": "<ticket_id that was current when archived>",
  "created_at": "2026-06-20T11:50:00Z"
}
```

**Index**: `{ project_id: 1, version: -1 }` — used for history listing and pruning.

**Pruning query** (after each write):
```
DELETE documents WHERE project_id = $1
ORDER BY version ASC
SKIP DISTILLER_MEMORY_HISTORY_KEEP
```
(i.e., delete all but the newest N versions)

### Collection: `adrs`

One document per ADR. Content fields are write-once.

```json
{
  "_id": "ADR-001",
  "project_id": "<project_id>",
  "title": "<short title>",
  "status": "proposed",
  "summary": "<one-sentence summary for context injection>",
  "content": "<full ADR markdown>",
  "ticket_id": "<ticket_id>",
  "created_at": "2026-06-20T10:00:00Z",
  "updated_at": "2026-06-20T10:00:00Z"
}
```

**Index**: `{ project_id: 1, status: 1 }` — supports `GET /adrs?status=accepted`.

**ID generation**: `ADR-{NNN}` where NNN is zero-padded 3-digit sequential per project.
Query: `db.adrs.find({ project_id: $1 }).sort({ _id: -1 }).limit(1)` to determine
the next number.

**Immutability rule**: `memory_repo.update_adr()` only accepts `{ status, updated_at }`.
Any other field in the update dict raises `ConflictError`.

**Status transitions** (valid only):
```
proposed → accepted
proposed → superseded
accepted → superseded
```
Any other transition raises `ConflictError`.

---

## Pydantic Schemas (service layer)

### Input

```python
class DistillRequest(BaseModel):
    ticket_id: str
    project_id: str

class AdrCreate(BaseModel):
    content: str        # full ADR markdown
    ticket_id: str
    title: str          # extracted or provided
    summary: str        # one-sentence summary
```

### Output

```python
class JobEnqueuedResponse(BaseModel):
    job_id: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"]
    error: str | None

class MemoryResponse(BaseModel):
    project_id: str
    content: str          # YAML string
    version: int
    last_ticket_id: str
    updated_at: datetime

class AdrSummary(BaseModel):
    id: str               # "ADR-NNN"
    title: str
    status: str
    summary: str
    ticket_id: str
    created_at: datetime

class AdrListResponse(BaseModel):
    adrs: list[AdrSummary]

class AdrCreatedResponse(BaseModel):
    adr_id: str           # "ADR-NNN"

class HealthResponse(BaseModel):
    status: Literal["ok"]
```

---

## Output Schema (project_memory YAML — enforced by LLM prompt)

This is the YAML structure the LLM must produce. Validated with `yaml.safe_load`.

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
      - "string"

open_risks:
  - "string"

known_constraints:
  - "string"

tech_stack:
  backend: "string"
  frontend: "string"
  database: "string"
  infra: "string"
```

**Validation logic** (`distiller.py`):
1. `yaml.safe_load(raw_output)` — raises on parse error
2. Check top-level keys present: `project_id`, `last_updated`, `last_ticket_id`,
   `architecture`, `recent_changes`, `open_risks`, `known_constraints`, `tech_stack`
3. On failure → retry (max 2 retries)
4. On 3rd failure → raise `DistillationError` with raw output as message
