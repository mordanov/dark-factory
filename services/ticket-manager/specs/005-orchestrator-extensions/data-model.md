# Data Model: Orchestrator Integration Extensions

**Branch**: `005-orchestrator-extensions` | **Date**: 2026-06-21

---

## 1. Modified Entity: `Ticket` (extends existing `tickets` table)

New columns added via migration 015:

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `fsm_status` | `fsm_status_enum` | YES | NULL | Orchestrator pipeline state |
| `blocked_reason` | `TEXT` | YES | NULL | Why ticket is BLOCKED |
| `brainstorm_round` | `INTEGER` | NO | `0` | Brainstorm iteration counter |
| `assigned_agent` | `VARCHAR(255)` | YES | NULL | Agent ID assigned by orchestrator |
| `override` | `BOOLEAN` | NO | `false` | Gate override flag |
| `override_reason` | `TEXT` | YES | NULL | Human-provided override justification |
| `last_orchestrator_run` | `TIMESTAMPTZ` | YES | NULL | When orchestrator last processed this ticket |
| `orchestrator_errors` | `JSONB` | YES | NULL | Array of recent orchestrator error strings |

**`fsm_status_enum` values** (new PostgreSQL type):
```
backlog | triage | specification | architecture_review |
implementation | code_review | security_review |
testing | release | done | BLOCKED
```

**Additional index** (migration 015):
```sql
CREATE INDEX idx_tickets_fsm_status ON tickets (fsm_status);
CREATE INDEX idx_tickets_pending ON tickets (updated_at, id)
  WHERE fsm_status IS DISTINCT FROM 'done';
```

**Existing fields unchanged**: `id`, `project_id`, `parent_ticket_id`, `title`, `description`, `status`, `ticket_type`, `ticket_spec`, `urgent`, `blocker`, `bugfix`, `time_spent`, `tokens_consumed`, `created_by`, `created_at`, `updated_at`, `deleted_at`.

**Migration**: `015_add_fsm_fields.py` — all new columns nullable or with server defaults; full rollback path drops columns and the `fsm_status_enum` type.

---

## 2. New Entity: `OrchestratorAuditEvent` (`orchestrator_audit_events` table)

Created via migration 016.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `UUID` | NO | `uuid4()` | Primary key |
| `ticket_id` | `UUID (FK tickets.id)` | NO | — | Associated ticket |
| `event` | `VARCHAR(50)` | NO | — | Event type: `ADVANCE`, `BLOCK`, `ASSIGN`, `WAIT`, etc. |
| `actor` | `VARCHAR(255)` | NO | — | Service identifier (e.g. `"orchestrator"`) |
| `from_state` | `VARCHAR(50)` | YES | NULL | FSM state before the action |
| `to_state` | `VARCHAR(50)` | YES | NULL | FSM state after the action |
| `details` | `TEXT` | YES | NULL | Human-readable description of the action |
| `timestamp` | `TIMESTAMPTZ` | NO | `now()` | When the event occurred (UTC) |

**Indexes**:
```sql
CREATE INDEX idx_orchestrator_audit_ticket_id ON orchestrator_audit_events (ticket_id);
CREATE INDEX idx_orchestrator_audit_timestamp ON orchestrator_audit_events (timestamp);
```

**Immutability**: No UPDATE or DELETE operations are exposed. Events are append-only.

**Migration**: `016_add_orchestrator_audit_events.py` — `down` drops the table.

---

## 3. FSM State Machine

```
NULL (uninitialized)
  ↓
backlog → triage → specification → architecture_review
  → implementation → code_review → security_review
  → testing → release → done

Any state → BLOCKED (with blocked_reason)
BLOCKED → previous state (when blocker resolved, orchestrator re-evaluates)
```

The orchestrator is solely responsible for FSM state transitions. The TM stores and exposes the state but does not enforce FSM transition validity (the orchestrator owns transition logic).

---

## 4. Validation Rules

| Entity | Field | Rule |
|---|---|---|
| Ticket FSM | `fsm_status` | Must be one of the 11 `fsm_status_enum` values or NULL |
| Ticket FSM | `brainstorm_round` | Non-negative integer |
| Ticket FSM | `orchestrator_errors` | JSON array of strings, max 50 entries (enforced by service layer) |
| Ticket FSM | `override` | Boolean; reset to `false` after orchestrator processes it |
| OrchestratorAuditEvent | `event` | Non-empty string, max 50 chars |
| OrchestratorAuditEvent | `actor` | Non-empty string, max 255 chars |
| OrchestratorAuditEvent | `timestamp` | UTC ISO-8601; if not provided by caller, defaults to `now()` |

---

## 5. Relationships

```
Ticket (1) ──< OrchestratorAuditEvent (N)   [ticket_id FK]
Ticket (N) >── Project (1)                   [existing]
Ticket (N) >── Tag (M)                       [existing, ticket_tags association]
```

The `OrchestratorAuditEvent` has no FK to `users` (the actor is a service string identifier, not a user record).
