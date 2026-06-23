# Data Model: Agent Dispatcher Service

**Feature**: `002-agent-dispatcher`
**Database**: `df_dispatcher` (PostgreSQL 16)

---

## Enum: `agent_run_status`

```sql
CREATE TYPE agent_run_status AS ENUM (
    'pending',
    'running',
    'completed',
    'needs_review',
    'failed',
    'timed_out'
);
```

| Value | Meaning |
|-------|---------|
| `pending` | Run record created, agent not yet started |
| `running` | Agent subprocess or API call is active |
| `completed` | Agent exited cleanly with a valid `[RESULT]` block |
| `needs_review` | `[RESULT]` block missing or unparseable; raw output saved |
| `failed` | Non-zero exit code, subprocess failure, or missing prompt file |
| `timed_out` | Agent exceeded its configured timeout |

---

## Table: `agent_runs`

Primary store for every agent execution event.

```sql
CREATE TABLE agent_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id           TEXT NOT NULL,
    project_id          TEXT NOT NULL,
    agent_id            TEXT NOT NULL,
    runner_mode         TEXT NOT NULL,           -- 'claude_code' | 'api'
    status              agent_run_status NOT NULL DEFAULT 'pending',
    round_number        INTEGER NOT NULL DEFAULT 1,
    brainstorm_session_id UUID REFERENCES brainstorm_sessions(id) ON DELETE SET NULL,
    context_snapshot    JSONB NOT NULL,          -- full context passed to agent (structured)
    raw_output          TEXT,                    -- captured stdout (no secrets)
    result              JSONB,                   -- parsed [RESULT] block as JSON
    error_message       TEXT,
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_runs_ticket_id ON agent_runs(ticket_id);
CREATE INDEX idx_agent_runs_status ON agent_runs(status);
CREATE INDEX idx_agent_runs_ticket_status ON agent_runs(ticket_id, status);
```

### Field Notes

- `context_snapshot`: The full context assembled for the agent stored as JSONB for
  structured querying. Must NOT contain `SERVICE_JWT` or TM credentials — these are
  injected into the text context only and are never persisted.
- `raw_output`: Captured stdout from the agent. Truncated to 64 KB if necessary.
  Must NOT contain `SERVICE_JWT` or TM credentials.
- `result`: The parsed `[RESULT]` block as a JSON object matching `AgentResult`.
  `null` until the run finishes.
- `round_number`: 1-indexed round within a brainstorm session. Always 1 for
  non-brainstorm runs.
- `brainstorm_session_id`: `null` for non-brainstorm runs.

### NOTIFY trigger (monitoring hook)

```sql
CREATE OR REPLACE FUNCTION notify_new_agent_run()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  PERFORM pg_notify('df_new_agent_run', row_to_json(NEW)::text);
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_notify_new_agent_run
AFTER INSERT ON agent_runs
FOR EACH ROW EXECUTE FUNCTION notify_new_agent_run();
```

---

## Table: `brainstorm_sessions`

Tracks multi-round brainstorm state for architecture-review tickets.
One row per ticket, created on first brainstorm dispatch.

```sql
CREATE TABLE brainstorm_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id       TEXT NOT NULL UNIQUE,
    project_name    TEXT NOT NULL,           -- 'df-{ticket_id}'
    current_round   INTEGER NOT NULL DEFAULT 1,
    max_rounds      INTEGER NOT NULL DEFAULT 3,
    status          TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'concluded'
    consensus       TEXT,                    -- 'agreed' | 'disagreed' | null
    concluded_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_brainstorm_sessions_ticket_id ON brainstorm_sessions(ticket_id);
CREATE INDEX idx_brainstorm_sessions_status ON brainstorm_sessions(status);
```

### Field Notes

- `project_name`: The brainstorm MCP project identifier, always `df-{ticket_id}`.
  Shared across all agents in a session.
- `current_round`: Incremented by `BrainstormSessionRepository.increment_round()`
  after all agents in a round have run. Starts at 1.
- `status`: `active` while rounds are ongoing; `concluded` when consensus is reached
  or `max_rounds` is exhausted.
- `consensus`: `agreed` if any agent returned `brainstorm_consensus: "agreed"`;
  `disagreed` if max rounds completed without agreement; `null` if session
  is still active.

---

## Pydantic Schemas

### `AgentResult` (parsed `[RESULT]` block)

```python
class AgentResult(BaseModel):
    status: Literal["completed", "needs_review", "blocked"] = "needs_review"
    summary: str = ""
    artifacts: list[str] = []
    tm_comment: str = ""
    brainstorm_consensus: Optional[Literal["agreed", "disagreed"]] = None
    errors: list[str] = []
```

### `AgentContext` (structured input to context builder)

```python
class AgentContext(BaseModel):
    ticket_id: str
    project_id: str
    agent_id: str
    ticket_title: str
    ticket_type: Optional[str]
    description: str
    constraints: str = ""
    relevant_files: str = ""
    project_memory: str = ""          # truncated to CONTEXT_MAX_TOKENS
    adrs: str = ""
    agent_config_overrides: str = ""
    brainstorm_project_name: Optional[str] = None
    brainstorm_round: Optional[int] = None
    brainstorm_max_rounds: Optional[int] = None
```

### `AgentRunResponse`

```python
class AgentRunResponse(OrmModel):
    id: UUID
    ticket_id: str
    project_id: str
    agent_id: str
    runner_mode: str
    status: str
    round_number: int
    brainstorm_session_id: Optional[UUID]
    raw_output: Optional[str]         # included in single-run GET, omitted in list
    result: Optional[dict]
    error_message: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime
```

### `AgentRunListResponse`

```python
class AgentRunListResponse(BaseModel):
    items: list[AgentRunResponse]
    total: int
```

---

## State Transitions

```
[created] pending
     │ mark_running()
     ▼
  running
     │
     ├─ exit_code == 0, [RESULT] valid ──────► completed
     ├─ exit_code == 0, [RESULT] missing/bad ► needs_review
     ├─ exit_code != 0 ──────────────────────► failed
     ├─ timeout ─────────────────────────────► timed_out
     └─ prompt missing ──────────────────────► failed
```
