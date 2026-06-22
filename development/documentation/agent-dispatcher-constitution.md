# Dark Factory — Agent Dispatcher Constitution

## Identity

Agent Dispatcher is a standalone microservice that acts as the execution layer
between the Orchestrator's FSM decisions and the individual Dark Factory agents.

When the Orchestrator assigns a ticket to an agent (`assigned_agent != null`),
Agent Dispatcher is responsible for:
1. Detecting the assignment by polling the Orchestrator API
2. Building the full execution context for the agent
3. Running the agent (Claude Code subprocess or direct API call)
4. Coordinating multi-agent brainstorm sessions for architecture review
5. Parsing the agent's structured output
6. Reporting the result back to Ticket Manager and triggering the next
   Orchestrator evaluation cycle

Agent Dispatcher does not make business decisions. It does not modify FSM state
directly. It executes what the Orchestrator decided and reports outcomes.

---

## Agent Runner Modes

The service supports two runner modes, selected via `AGENT_RUNNER_MODE` env var:

### Mode 1: `claude_code` (primary, default)

Spawns a `claude` CLI subprocess in `--print` mode (non-interactive).
The agent runs as a real Claude Code instance with full MCP access:
- `brainstorm` MCP server (already configured in `~/.claude/mcp_config.json`)
- `agent-tools` MCP server (once implemented)
- Any other MCP servers in the user's Claude config

```bash
claude \
  --print \
  --system-prompt "$(cat prompts/{agent_id}.md)" \
  --mcp-config "$CLAUDE_MCP_CONFIG_PATH" \
  "$AGENT_CONTEXT"
```

Claude Code exits when the task is complete. Exit code 0 = success.
Stdout is captured and parsed for the `[RESULT]` block.

### Mode 2: `api` (fallback)

Calls OpenAI or Anthropic API directly with the agent's system prompt and
full context. Used when Claude Code CLI is not available (e.g. CI environments).
In this mode, brainstorm-mcp is simulated: the Dispatcher maintains a
conversation history shared across agents in the same brainstorm session,
injected as context into each API call.

The mode is selected at service startup and cannot be changed at runtime.
Both modes produce identical output (the `[RESULT]` block) — callers are
unaware of which mode was used.

---

## Core Principles

### 1. Polling-based, not push-based

Agent Dispatcher polls the Orchestrator API for tickets with `assigned_agent != null`.
It never receives webhooks or events from the Orchestrator.
Poll interval is configurable via `POLL_INTERVAL_SECONDS` (default: 10).

The poll query: `GET /api/v1/orchestrator/pending-tickets` (via user-input-manager
proxy) filtered to tickets where `assigned_agent` is set and `fsm_status` is
in an actionable state (not `done`, not `BLOCKED`, not already running).

### 2. One agent run per ticket at a time

A ticket must never have two simultaneous agent runs. Before starting a run,
the service checks `agent_runs` table for an existing `running` row with the
same `ticket_id`. If found, the ticket is skipped in this poll cycle.

### 3. Agent output protocol — `[RESULT]` block

Every agent's system prompt must instruct the agent to end its response with
a structured result block. The Dispatcher parses this block to determine
success/failure and extract artifacts.

**Required block format (enforced by validation):**

```
[RESULT]
{
  "status": "completed | needs_review | blocked",
  "summary": "What was accomplished (max 500 chars)",
  "artifacts": ["relative/path/to/file.py"],
  "tm_comment": "Comment to post on the TM ticket",
  "brainstorm_consensus": null | "agreed" | "disagreed",
  "errors": []
}
[/RESULT]
```

If the `[RESULT]` block is missing or invalid JSON:
- `status` is treated as `needs_review`
- `tm_comment` is set to the raw stdout (truncated to 2000 chars)
- An error is logged but the run is not marked as failed

### 4. Brainstorm coordination is sequential, not parallel

For `architecture_review` tickets, multiple agents must weigh in before the
Orchestrator makes a final decision. The Dispatcher runs agents **one at a time**
in a defined sequence (`BRAINSTORM_AGENTS` env var, default:
`software_architect,security_architect`).

Each agent in the sequence receives the full brainstorm project name in its
context (`BRAINSTORM_PROJECT: df-{ticket_id}`). In `claude_code` mode, the
agent naturally uses brainstorm-mcp tools to join the project and read previous
messages. In `api` mode, the Dispatcher injects previous agents' responses as
context.

Maximum rounds: `BRAINSTORM_MAX_ROUNDS` (default: 3, matches Orchestrator FSM).
Early exit: if any agent's `[RESULT]` contains `"brainstorm_consensus": "agreed"`,
the round ends immediately.

### 5. Agent prompts are files, not database records

Agent system prompts are loaded from the filesystem directory
`AGENT_PROMPTS_DIR` (default: `./prompts/`).
Each file is named `{agent_id}.md` (e.g. `backend.md`, `software_architect.md`).
The service fails to start if `AGENT_PROMPTS_DIR` does not exist.
Individual agent runs fail (not the service) if the specific prompt file
is missing.

Prompt files are read on each run (no caching) so updates take effect
immediately without restarting the service.

### 6. Results are reported via TM API, not DB coupling

After a run completes, the Dispatcher:
1. POSTs a comment to the TM ticket via TM API (`tm_comment` from result)
2. Triggers a new Orchestrator job via `POST /api/v1/orchestrator/jobs/trigger`

The Dispatcher never directly modifies FSM state. FSM transitions remain the
Orchestrator's exclusive responsibility.

### 7. Timeouts are per-agent-type

Different agents require different time budgets. Timeouts (in seconds) are
configured via env vars with sensible defaults:

| Agent | Default timeout |
|---|---|
| `project_manager` | 120s |
| `software_architect` | 180s |
| `security_architect` | 180s |
| `backend` | 600s |
| `frontend` | 600s |
| `designer` | 300s |
| `code_reviewer` | 300s |
| `autotester` | 600s |
| `devops` | 300s |
| `project_administrator` | 120s |

Override any timeout via `AGENT_TIMEOUT_{AGENT_ID_UPPER}` env var
(e.g. `AGENT_TIMEOUT_BACKEND=900`).
On timeout: run marked `failed`, TM ticket commented, Orchestrator triggered
with error context.

### 8. Auth adapter pattern

Follows the monorepo constitution: `src/core/auth_adapter.py` with
`AUTH_MODE=local|keycloak`. The Dispatcher validates JWTs from user-input-manager
for its own API endpoints.
For calls it makes to other services (Orchestrator, TM), it uses a
service-level JWT generated with the shared `JWT_SECRET_KEY`.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| API framework | FastAPI (async) |
| DB | PostgreSQL 16 (database: `df_dispatcher`) |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Migrations | Alembic |
| Config | Pydantic Settings + `.env` |
| Subprocess | `asyncio.create_subprocess_exec` |
| HTTP client | `httpx` async |
| LLM (API mode) | `openai` SDK async |
| Pre-commit | `ruff` (lint + format) |
| Tests | `pytest` + `pytest-asyncio` + `pytest-cov` |

---

## Data Model

### Database: `df_dispatcher`

#### Table: `agent_runs`

```sql
CREATE TABLE agent_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id        TEXT NOT NULL,
    project_id       TEXT NOT NULL,
    agent_id         TEXT NOT NULL,
    runner_mode      TEXT NOT NULL,          -- claude_code | api
    status           agent_run_status NOT NULL DEFAULT 'pending',
    round_number     INTEGER NOT NULL DEFAULT 1,  -- for brainstorm
    brainstorm_session_id UUID,               -- FK → brainstorm_sessions
    context_snapshot JSONB NOT NULL,          -- full context passed to agent
    raw_output       TEXT,                    -- captured stdout
    result           JSONB,                   -- parsed [RESULT] block
    error_message    TEXT,
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TYPE agent_run_status AS ENUM (
    'pending', 'running', 'completed', 'needs_review', 'failed', 'timed_out'
);
```

#### Table: `brainstorm_sessions`

```sql
CREATE TABLE brainstorm_sessions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id        TEXT NOT NULL UNIQUE,
    project_name     TEXT NOT NULL,          -- e.g. "df-{ticket_id}"
    current_round    INTEGER NOT NULL DEFAULT 1,
    max_rounds       INTEGER NOT NULL DEFAULT 3,
    status           TEXT NOT NULL DEFAULT 'active',  -- active | concluded
    consensus        TEXT,                   -- agreed | disagreed | null
    concluded_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT now()
);
```

---

## Service Structure

```
services/agent-dispatcher/
├── src/
│   ├── core/
│   │   ├── config.py              settings + env vars
│   │   ├── exceptions.py          AppError hierarchy
│   │   └── auth_adapter.py        JWT validation (local | keycloak)
│   ├── db/
│   │   └── session.py             async engine + get_db
│   ├── models/
│   │   └── models.py              AgentRun, BrainstormSession ORM
│   ├── schemas/
│   │   └── schemas.py             Pydantic DTOs
│   ├── repositories/
│   │   ├── run_repo.py            AgentRunRepository
│   │   └── brainstorm_repo.py     BrainstormSessionRepository
│   ├── services/
│   │   ├── poller.py              polls Orchestrator for assigned tickets
│   │   ├── context_builder.py     assembles full agent context string
│   │   ├── result_parser.py       extracts [RESULT] block from stdout
│   │   ├── brainstorm_coordinator.py  manages multi-round sessions
│   │   ├── reporter.py            posts to TM + triggers Orchestrator
│   │   ├── runner/
│   │   │   ├── base.py            AgentRunner abstract base
│   │   │   ├── claude_code.py     subprocess runner
│   │   │   └── api_runner.py      direct API runner
│   │   └── dispatcher_service.py  top-level orchestration
│   ├── workers/
│   │   └── dispatch_worker.py     asyncio polling loop
│   ├── api/
│   │   └── v1/
│   │       └── runs.py            GET /runs, GET /runs/{id}
│   └── main.py                    FastAPI app + lifespan
├── prompts/                       agent system prompts
│   ├── backend.md
│   ├── software_architect.md
│   └── ...
├── tests/
│   ├── unit/
│   │   ├── test_result_parser.py
│   │   ├── test_context_builder.py
│   │   └── test_brainstorm_coordinator.py
│   ├── integration/
│   │   ├── test_run_repo.py
│   │   └── test_dispatcher_service.py
│   └── conftest.py
├── alembic/
│   ├── env.py
│   └── versions/
├── alembic.ini
├── Dockerfile
├── requirements.txt
├── pytest.ini
└── .coveragerc
```

---

## API Endpoints

```
GET  /api/health
     Response: { "status": "ok", "runner_mode": "claude_code|api" }

GET  /api/v1/runs
     Auth: Bearer
     Query: ?ticket_id=&status=&offset=&limit=
     Response: { "items": [AgentRunResponse], "total": int }

GET  /api/v1/runs/{run_id}
     Auth: Bearer
     Response: AgentRunResponse (includes raw_output and result)
```

The service has no trigger endpoint — it is self-driving via the polling loop.
Manual triggers can be done by creating a test job through the Orchestrator.

---

## Context Building Contract

The context passed to each agent is a plain text string (not JSON) structured
as a markdown document. This ensures readability in both claude_code and api modes.

```markdown
# Agent Task

## Your Role
{contents of prompts/{agent_id}.md — injected here, not as --system-prompt
in cases where system prompt cannot be set separately}

## Ticket
- **ID**: {ticket_id}
- **Title**: {ticket.title}
- **Type**: {ticket.ticket_type}
- **Project**: {ticket.project_id}

## Description
{ticket.description}

## Acceptance Criteria
{acceptance_criteria parsed from description}

## Your Constraints (from Orchestrator + Project Config)
{agent_briefing.constraints}
{project_agent_config_overrides for this agent_id}

## Relevant Files
{agent_briefing.relevant_files}

## Project Context (from ContextDistiller)
{project_memory.content — truncated to CONTEXT_MAX_TOKENS}

## Active ADRs
{adr list summaries}

## Brainstorm Project (architecture_review only)
Project name: {brainstorm_session.project_name}
Round: {round_number} of {max_rounds}
Previous agent messages are available in the brainstorm project.

## Task Manager Access
TM API is available at: {TM_BASE_URL}
Your service token: {SERVICE_JWT}
Ticket to update: {ticket_id} in project {project_id}

## Completion Instructions
When your task is complete, end your response with a result block:

[RESULT]
{
  "status": "completed",
  "summary": "Brief description of what you did",
  "artifacts": [],
  "tm_comment": "Comment to post on the ticket",
  "brainstorm_consensus": null,
  "errors": []
}
[/RESULT]
```

---

## Environment Variables

| Variable | Default | Required |
|---|---|---|
| `DATABASE_URL` | — | ✓ |
| `JWT_SECRET_KEY` | — | ✓ (must match UIM) |
| `AUTH_MODE` | `local` | |
| `AGENT_RUNNER_MODE` | `claude_code` | |
| `CLAUDE_CODE_PATH` | `claude` | claude_code mode |
| `CLAUDE_MCP_CONFIG_PATH` | `~/.claude/mcp_config.json` | claude_code mode |
| `AGENT_PROMPTS_DIR` | `./prompts` | ✓ |
| `OPENAI_API_KEY` | — | api mode |
| `OPENAI_MODEL` | `gpt-4o` | api mode |
| `ORCHESTRATOR_BASE_URL` | `http://orchestrator:8003` | ✓ |
| `TICKET_MANAGER_BASE_URL` | `http://ticket-manager:8002` | ✓ |
| `TICKET_MANAGER_SERVICE_EMAIL` | — | ✓ |
| `TICKET_MANAGER_SERVICE_PASSWORD` | — | ✓ |
| `CONTEXT_DISTILLER_BASE_URL` | `http://context-distiller:8004` | |
| `POLL_INTERVAL_SECONDS` | `10` | |
| `WORKER_MAX_CONCURRENT_RUNS` | `3` | |
| `BRAINSTORM_AGENTS` | `software_architect,security_architect` | |
| `BRAINSTORM_MAX_ROUNDS` | `3` | |
| `CONTEXT_MAX_TOKENS` | `3000` | |
| `AGENT_TIMEOUT_DEFAULT` | `300` | |
| `SERVICE_JWT_EXPIRE_HOURS` | `24` | |

---

## Testing Requirements

### Unit tests (no I/O, ≥ 80% coverage)

- `ResultParser`: valid block, missing block, invalid JSON, partial block
- `ContextBuilder`: all context sections present, missing project memory,
  missing ADRs, agent config overrides applied
- `BrainstormCoordinator`: round sequencing, early exit on consensus,
  max rounds enforcement, api mode history injection
- `Poller`: filters out running tickets, filters out tickets without agent

### Integration tests

- `AgentRunRepository`: create, mark_running, mark_done, has_running
- `BrainstormSessionRepository`: create, increment_round, conclude
- `DispatcherService` (mocked runners): full lifecycle for single agent run,
  full lifecycle for brainstorm run, timeout handling, missing prompt file

### Runner tests (mocked subprocess/API)

- `ClaudeCodeRunner`: successful run with valid `[RESULT]`, timeout,
  non-zero exit code, subprocess fails to start
- `ApiRunner`: successful response, API error, missing result block

**No real Claude Code or API calls in tests.**
Use `AsyncMock` for subprocess and httpx.

---

## Definition of Done

1. `docker compose up` starts Agent Dispatcher alongside all other services
2. With a ticket that has `assigned_agent = "backend"` in TM, the Dispatcher
   detects it within `POLL_INTERVAL_SECONDS` and starts a run
3. In `claude_code` mode: subprocess is spawned with correct system prompt
   and context; exit is detected; result is parsed
4. In `api` mode: API is called with system prompt and context; result is parsed
5. After completion: TM ticket has a comment; Orchestrator job is triggered
6. Brainstorm session: two agents run sequentially, both use the same
   `df-{ticket_id}` project name in their context
7. All unit and integration tests pass; ≥ 80% coverage
8. `AUTH_MODE=local` behaviour identical to other services
9. `GET /api/v1/runs` returns run history with status and result
10. Prometheus-compatible `/metrics` endpoint (basic: runs_total, runs_active,
    run_duration_seconds) — optional, nice to have

---

## Principles That Must Never Be Violated

- **Never modify FSM state directly.** Only the Orchestrator changes ticket FSM.
- **Never run two agents on the same ticket simultaneously.**
- **Never block the polling loop on a slow agent.** Each run is an async task
  under `asyncio.Semaphore(WORKER_MAX_CONCURRENT_RUNS)`.
- **Never crash on missing `[RESULT]` block.** Degrade gracefully.
- **Never cache agent prompts.** Read from disk on each run.
- **Never expose `SERVICE_JWT` or `TICKET_MANAGER_SERVICE_PASSWORD`
  in agent run logs or API responses.**
