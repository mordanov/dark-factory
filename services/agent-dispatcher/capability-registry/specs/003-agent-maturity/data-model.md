# Data Model: Agent Maturity Platform

**Branch**: `003-agent-maturity` | **Phase**: 1

---

## Overview

All new entities live in the `df_dispatcher` PostgreSQL database, extending `agent-dispatcher`'s existing schema. No new databases, no cross-service writes.

Existing tables (unchanged): `agent_runs`, `brainstorm_sessions`

New tables: `agent_worker_records`, `agent_lifecycle_events`, `working_memory_entries`

---

## Entity: AgentWorkerRecord

Logical worker registration — one row per currently-running or recently-terminated agent process instance.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | Primary key |
| `role_id` | VARCHAR(64) | NOT NULL | — | Must match a canonical role ID in the YAML registry |
| `run_id` | UUID | NULL | — | FK → `agent_runs.id`; set when executing a ticket run |
| `status` | VARCHAR(32) | NOT NULL | `'idle'` | Enum: `idle`, `busy`, `draining`, `offline` |
| `capabilities_snapshot` | JSONB | NOT NULL | `'{}'` | Copy of YAML capabilities at registration time |
| `version` | VARCHAR(64) | NOT NULL | `''` | Agent image/code version string |
| `registered_at` | TIMESTAMP | NOT NULL | `now()` | When the worker registered |
| `last_heartbeat_at` | TIMESTAMP | NOT NULL | `now()` | Last heartbeat received |
| `offline_at` | TIMESTAMP | NULL | — | When worker went offline (graceful or sweep-detected) |

**Indexes**:
- `(role_id, status)` — registry lookup for available agents
- `(last_heartbeat_at)` — liveness sweep by timestamp
- `(run_id)` — join to agent_runs

**Status transitions**:
```
idle → busy (assigned a run)
busy → idle (run completed)
busy → draining (drain signal received mid-run)
idle → draining (drain signal received at rest)
draining → offline (all work finished)
any → offline (liveness sweep detects heartbeat gap > 2× interval)
```

**Constraints**:
- `status` CHECK constraint: `status IN ('idle', 'busy', 'draining', 'offline')`
- `role_id` must be non-empty
- `last_heartbeat_at` must be ≤ `now()`

---

## Entity: AgentLifecycleEvent

Immutable audit log of every worker lifecycle transition.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | Primary key |
| `worker_id` | UUID | NOT NULL | — | FK → `agent_worker_records.id` |
| `role_id` | VARCHAR(64) | NOT NULL | — | Denormalized for query without join |
| `event_type` | VARCHAR(32) | NOT NULL | — | Enum: see below |
| `metadata` | JSONB | NOT NULL | `'{}'` | Event-specific payload |
| `occurred_at` | TIMESTAMP | NOT NULL | `now()` | Event timestamp |

**Event types**:
- `registered` — worker came online
- `heartbeat` — heartbeat received (written every Nth heartbeat, not every one)
- `assigned` — run assigned; metadata: `{run_id, ticket_id}`
- `run_completed` — run finished; metadata: `{run_id, status}`
- `drain_requested` — drain signal received
- `offline_graceful` — worker gracefully shut down
- `offline_liveness` — sweep detected heartbeat gap

**Indexes**:
- `(worker_id, occurred_at DESC)` — timeline per worker
- `(role_id, occurred_at DESC)` — timeline per role
- `(event_type, occurred_at DESC)` — event type queries

**Immutability**: No UPDATE or DELETE permitted on this table (enforced via application layer; can be reinforced with a PostgreSQL trigger if needed).

---

## Entity: WorkingMemoryEntry

Append-only per-ticket shared working memory. Each executing agent may write entries; the Orchestrator reads all entries for a ticket.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| `id` | UUID | NOT NULL | `gen_random_uuid()` | Primary key |
| `ticket_id` | VARCHAR(64) | NOT NULL | — | FK reference (logical, not DB FK) to ticket |
| `run_id` | UUID | NOT NULL | — | FK → `agent_runs.id`; which run created this entry |
| `author_role_id` | VARCHAR(64) | NOT NULL | — | Role ID of the agent that wrote this entry |
| `entry_type` | VARCHAR(32) | NOT NULL | — | Enum: `observation`, `decision`, `artifact_ref`, `question`, `answer` |
| `content` | TEXT | NOT NULL | — | Entry body (max 64 KB enforced at application layer) |
| `tags` | TEXT[] | NOT NULL | `'{}'` | Optional keyword tags for filtering |
| `created_at` | TIMESTAMP | NOT NULL | `now()` | Write timestamp |
| `expires_at` | TIMESTAMP | NOT NULL | `now() + 30 days` | Retention deadline |

**Indexes**:
- `(ticket_id, created_at ASC)` — ordered reads per ticket
- `(ticket_id, author_role_id)` — filter by author
- `(expires_at)` — cleanup sweep

**Constraints**:
- No UPDATE or DELETE (append-only); cleanup only via expiry sweep
- `ticket_id` must be non-empty
- `content` length ≤ 65,536 characters (enforced at schema level via CHECK)
- `entry_type` CHECK constraint

**Retention**: A background `CleanupWorker` task in `agent-dispatcher` runs daily, deleting entries where `expires_at < now()`. Default retention: 30 days.

---

## Modified Entity: AgentRun (existing)

No schema changes. The new tables reference `agent_runs.id` via FK. Behavioral note: `AgentRun.status` transitions remain unchanged; the new `AgentWorkerRecord.status` is a separate lifecycle dimension.

---

## Alembic Migration

New file: `alembic/versions/0002_add_agent_maturity_tables.py`

Creates (in order):
1. `agent_worker_records`
2. `agent_lifecycle_events` (FK → `agent_worker_records`)
3. `working_memory_entries`

All tables include `IF NOT EXISTS` guard. Down migration drops all three in reverse order.

---

## YAML Registry Extension (Backward-Compatible)

`AgentCapability` dataclass gets one new optional field:

```python
@dataclass
class AgentCapability:
    # ... existing fields unchanged ...
    confidence: dict[str, int] = field(default_factory=dict)
    # Maps skill name → confidence score 0-100.
    # Agents without this field default to confidence=100 for all listed capabilities.
```

YAML format:
```yaml
- role_id: backend
  capabilities:
    - python_backend
    - fastapi
    - postgresql
  confidence:          # NEW — optional
    python_backend: 95
    fastapi: 90
    postgresql: 80
```

No existing registry entries need updating (missing `confidence` → all capabilities default to 100).

---

## Capability Registry New Methods

**`CapabilityRegistry` extensions** (no breaking changes):

```python
def get_by_capability(
    self,
    required_capabilities: list[str],
    min_confidence: int = 0
) -> list[AgentCapability]:
    """Return agents with ALL required_capabilities at >= min_confidence."""

def get_candidates_with_confidence(
    self,
    state: str,
    required_capabilities: list[str],
    min_confidence: int = 0
) -> list[AgentCapability]:
    """Combine FSM-state eligibility with capability requirement check."""
```

---

## Assignment Flow Data

New field added to the job trigger payload (sent Orchestrator → Dispatcher):

```python
class RunRequest(BaseModel):
    # ... existing fields unchanged ...
    required_capabilities: list[str] = []
    # Derived by Orchestrator from ticket tags + FSM state.
    # Empty list = fall back to static role-based assignment (current behavior).
```

New field added to the run result payload (returned Dispatcher → Orchestrator via reporter):

```python
class AgentResult(BaseModel):
    # ... existing fields unchanged ...
    matched_capability_record: dict | None = None
    # Serialized AgentCapability dict for the selected agent.
    # None when capability-based assignment was not used.
```

---

## Entity Relationships

```
agent_runs ──── (run_id) ──── agent_worker_records
    │                                 │
    │                                 └── (worker_id) ── agent_lifecycle_events
    │
    └── (run_id) ── working_memory_entries
```

`ticket_id` in `working_memory_entries` is a logical reference (VARCHAR) to the ticket ID string, not a DB-level FK (tickets are owned by `ticket-manager`, not `df_dispatcher`).
