# /speckit.specify — Agent Dispatcher

## Prompt (copy-paste into Claude Code)

```
/speckit.specify

Build the Agent Dispatcher service for Dark Factory. This service detects
agent assignments made by the Orchestrator, executes agents (Claude Code
subprocess or direct API call), coordinates brainstorm sessions, and
reports results back to the Ticket Manager and Orchestrator.

Read all context files before generating the spec.
This is a new standalone service: services/agent-dispatcher/.
Do not modify any existing service.

## Context files (read in this order)

@.specify/memory/constitution.md
@.specify/memory/service-map.md
@.specify/memory/project-map.md
@../orchestrator/src/schemas/schemas.py
@../orchestrator/src/services/fsm/engine.py
@../ticket-manager/README.md
@../context-distiller/README.md
@../user-input-manager/backend/src/core/config.py

Do not go above the ../ directory level.

## What to specify

### 1. Project scaffold

Create the full directory structure as defined in the constitution under
`services/agent-dispatcher/`. Include empty placeholder files where needed.
Python 3.12, Dockerfile with `python:3.12-slim` base image.

### 2. Configuration (`src/core/config.py`)

Pydantic Settings class reading from `.env`. All variables from the
"Environment Variables" table in the constitution. Include:
- `agent_timeout_for(agent_id: str) -> int` method that reads
  `AGENT_TIMEOUT_{AGENT_ID_UPPER}` env var with fallback to
  `AGENT_TIMEOUT_DEFAULT`
- `brainstorm_agents_list` property that splits `BRAINSTORM_AGENTS` by comma

### 3. Database models and migration (`src/models/models.py`)

Two ORM models matching the schema in the constitution:
- `AgentRun` (table: `agent_runs`)
- `BrainstormSession` (table: `brainstorm_sessions`)

New enum types: `agent_run_status`.
Alembic migration creating both tables and enums.
PostgreSQL NOTIFY trigger on `agent_runs` INSERT (same pattern as Orchestrator)
for channel `df_new_agent_run` — not used internally but useful for monitoring.

### 4. Pydantic schemas (`src/schemas/schemas.py`)

- `AgentRunResponse` (ORM model → API response)
- `AgentRunListResponse`
- `BrainstormSessionResponse`
- `AgentResult` — parsed `[RESULT]` block structure
- `AgentContext` — typed representation of context passed to agent

### 5. Repositories

`src/repositories/run_repo.py` — `AgentRunRepository`:
- `create(ticket_id, project_id, agent_id, runner_mode, context_snapshot) → AgentRun`
- `get_by_id(run_id) → AgentRun | None`
- `has_running(ticket_id) → bool`
- `mark_running(run_id) → None`
- `mark_done(run_id, raw_output, result) → None`
- `mark_failed(run_id, error_message) → None`
- `list_all(ticket_id?, status?, offset, limit) → tuple[list, int]`

`src/repositories/brainstorm_repo.py` — `BrainstormSessionRepository`:
- `get_or_create(ticket_id, max_rounds) → BrainstormSession`
- `increment_round(session) → BrainstormSession`
- `conclude(session, consensus) → BrainstormSession`

### 6. Result parser (`src/services/result_parser.py`)

Pure function module — no I/O:

```python
def parse_result(stdout: str) -> AgentResult:
    """
    Extract [RESULT]...[/RESULT] block from stdout.
    
    Returns AgentResult with:
    - status from JSON (default: "needs_review" if block missing/invalid)
    - summary, artifacts, tm_comment, brainstorm_consensus, errors
    
    Never raises. On any parse failure, returns:
    AgentResult(status="needs_review", tm_comment=stdout[:2000], ...)
    """
```

### 7. Context builder (`src/services/context_builder.py`)

`async def build_context(ticket, agent_id, agent_briefing, brainstorm_session?) → str`

Assembles the markdown context document per the "Context Building Contract"
in the constitution. Fetches:
- Project memory: GET `{CONTEXT_DISTILLER_BASE_URL}/memory/{project_id}`
  (graceful 404 → empty section)
- ADRs: GET `{CONTEXT_DISTILLER_BASE_URL}/memory/{project_id}/adrs`
  (graceful failure → empty section)
- Agent config override: GET
  `{CONTEXT_DISTILLER_BASE_URL}/memory/{project_id}/agent-config`
  (graceful failure → no overrides)

All three fetches have 5s timeout and fail silently (log warning, continue).
Generates a service-level JWT using `create_service_token()` for TM access,
injected into the context as `SERVICE_JWT`.

### 8. Agent runners

`src/services/runner/base.py`:
```python
class AgentRunner(ABC):
    @abstractmethod
    async def run(
        self,
        agent_id: str,
        system_prompt: str,
        context: str,
        timeout_seconds: int,
    ) -> tuple[int, str]:
        """Returns (exit_code, stdout)"""
```

`src/services/runner/claude_code.py` — `ClaudeCodeRunner(AgentRunner)`:
- Uses `asyncio.create_subprocess_exec` to spawn `claude`
- Flags: `--print`, `--mcp-config {CLAUDE_MCP_CONFIG_PATH}`
- System prompt passed as `--system-prompt` flag
- Context passed as positional argument (stdin alternative)
- Captures stdout with `asyncio.wait_for` + `proc.communicate()`
- On timeout: kills subprocess, returns (-1, captured_so_far)
- Reads `CLAUDE_CODE_PATH` for the binary path

`src/services/runner/api_runner.py` — `ApiRunner(AgentRunner)`:
- Calls OpenAI API with `model=OPENAI_MODEL`
- `messages=[{"role": "system", ...}, {"role": "user", ...}]`
- Returns (0, response_text) on success, (-1, error_str) on failure
- For brainstorm rounds in api mode: context already includes previous
  agents' responses (injected by BrainstormCoordinator)

Runner factory:
```python
def get_runner() -> AgentRunner:
    mode = get_settings().agent_runner_mode
    return ClaudeCodeRunner() if mode == "claude_code" else ApiRunner()
```

### 9. Brainstorm coordinator (`src/services/brainstorm_coordinator.py`)

`BrainstormCoordinator` class:

```python
async def run_brainstorm(
    self,
    ticket: TmTicket,
    agent_briefing: dict,
    db: AsyncSession,
) -> dict:
    """
    Coordinates multi-round brainstorm for architecture_review.
    
    Returns: {
        "concluded": bool,
        "consensus": "agreed" | "disagreed" | null,
        "rounds_completed": int,
        "agent_results": [{"agent_id": ..., "result": AgentResult}]
    }
    """
```

Logic:
1. `get_or_create` brainstorm session for ticket
2. For each round (1..max_rounds):
   a. For each agent in `BRAINSTORM_AGENTS`:
      - Load prompt from `{AGENT_PROMPTS_DIR}/{agent_id}.md`
      - Build context with `brainstorm_session` included
      - In `api` mode: inject previous agents' results as additional context
      - Run agent via runner
      - Parse result, save `AgentRun` row
      - If `brainstorm_consensus == "agreed"`: conclude early
   b. Increment round
3. Conclude session with final consensus
4. Return aggregated results

For `claude_code` mode: agents use brainstorm-mcp tools natively via their
MCP config. The Dispatcher only tracks round numbers in DB.
For `api` mode: Dispatcher accumulates `tm_comment` strings from each agent
and prepends them to the next agent's context as "Previous agent responses:".

### 10. Reporter (`src/services/reporter.py`)

`async def report_result(ticket_id, project_id, result: AgentResult) -> None`:

1. POST comment to TM ticket:
   ```
   POST {TM_BASE_URL}/api/projects/{project_id}/tickets/{ticket_id}/comments
   Body: { "content": result.tm_comment }
   ```
   Graceful failure (log, continue).

2. Trigger Orchestrator job:
   ```
   POST {ORCHESTRATOR_BASE_URL}/api/v1/jobs/trigger
   Body: { "ticket_id": ticket_id, "project_id": project_id }
   ```
   Retry once on failure. Raise on second failure (callers handle).

Service JWT used for both calls (generated from `JWT_SECRET_KEY`).

### 11. Dispatcher service (`src/services/dispatcher_service.py`)

Top-level coordinator:

```python
async def process_ticket(ticket: TmTicket, db: AsyncSession) -> None:
    """
    Full lifecycle for one ticket assignment.
    Called from the async worker under Semaphore.
    """
    agent_id = ticket.assigned_agent
    runner = get_runner()
    
    # Guard against double-run
    if await AgentRunRepository(db).has_running(ticket.id):
        return
    
    # Determine if brainstorm needed
    needs_brainstorm = (
        ticket.fsm_status == "architecture_review"
        and ticket.ticket_type in ("feature", "improvement")
    )
    
    if needs_brainstorm:
        result_data = await BrainstormCoordinator(runner).run_brainstorm(
            ticket, ..., db
        )
        # Aggregate brainstorm results into single AgentResult for reporting
        final_result = aggregate_brainstorm(result_data)
    else:
        # Single agent run
        prompt_path = Path(settings.agent_prompts_dir) / f"{agent_id}.md"
        if not prompt_path.exists():
            await fail_ticket(ticket, f"No prompt for agent '{agent_id}'", db)
            return
        
        context = await build_context(ticket, agent_id, ...)
        run = await AgentRunRepository(db).create(...)
        await AgentRunRepository(db).mark_running(run.id)
        
        try:
            exit_code, stdout = await asyncio.wait_for(
                runner.run(agent_id, prompt_path.read_text(), context, timeout),
                timeout=timeout + 5  # buffer
            )
        except asyncio.TimeoutError:
            await AgentRunRepository(db).mark_failed(run.id, "Timed out")
            ...
            return
        
        result = parse_result(stdout)
        await AgentRunRepository(db).mark_done(run.id, stdout, result.model_dump())
        final_result = result
    
    await Reporter().report_result(ticket.id, ticket.project_id, final_result)
```

### 12. Poller (`src/services/poller.py`)

```python
async def poll_once(db: AsyncSession) -> list[TmTicket]:
    """
    Fetch assigned tickets from Orchestrator.
    Returns only tickets not already being processed.
    """
    response = await orchestrator_client.get(
        f"{settings.orchestrator_base_url}/api/v1/jobs/pending-tickets",
        headers={"Authorization": f"Bearer {get_service_token()}"},
    )
    tickets = [TmTicket(**t) for t in response.json()["tickets"]]
    assigned = [t for t in tickets if t.assigned_agent]
    
    # Filter out already-running
    not_running = []
    repo = AgentRunRepository(db)
    for ticket in assigned:
        if not await repo.has_running(ticket.id):
            not_running.append(ticket)
    
    return not_running
```

### 13. Async worker (`src/workers/dispatch_worker.py`)

Same pattern as Orchestrator's `JobWorker`:
- `asyncio.Semaphore(WORKER_MAX_CONCURRENT_RUNS)`
- Polling loop with `asyncio.sleep(POLL_INTERVAL_SECONDS)`
- Each ticket dispatched as `asyncio.create_task`
- Started in FastAPI lifespan

### 14. FastAPI app (`src/main.py`)

- Lifespan: start worker on startup, stop on shutdown
- Router: `GET /api/v1/runs`, `GET /api/v1/runs/{id}`, `GET /api/health`
- Exception handler for `AppError`
- CORS from `CORS_ALLOW_ORIGINS`

### 15. Tests

**Unit tests** (`tests/unit/`):

`test_result_parser.py`:
- Valid `[RESULT]` block → correct AgentResult
- Missing block → status=needs_review, tm_comment=stdout[:2000]
- Invalid JSON in block → graceful fallback
- Block with extra text after → correct extraction
- `brainstorm_consensus: "agreed"` parsed correctly

`test_context_builder.py`:
- All sections present when all services available
- Missing project memory → empty section, no error
- Missing ADRs → empty section, no error
- Agent config override applied to correct agent
- Brainstorm section included when session provided
- SERVICE_JWT present in context
- Context truncated to CONTEXT_MAX_TOKENS

`test_brainstorm_coordinator.py`:
- Two agents run sequentially (correct order)
- Early exit when first agent returns `"agreed"`
- Max rounds enforced (does not exceed BRAINSTORM_MAX_ROUNDS)
- `api` mode: second agent receives first agent's tm_comment in context
- Round number incremented in DB after each round

**Integration tests** (`tests/integration/`):

`test_run_repo.py`:
- Create, mark_running, mark_done lifecycle
- `has_running` returns true for running, false for completed
- `list_all` filters by ticket_id and status

`test_dispatcher_service.py` (mocked runner and reporter):
- Single agent run: context built, runner called, result parsed, reporter called
- Missing prompt file: run marked failed, reporter called with error
- Runner timeout: run marked timed_out, reporter called
- Brainstorm run: coordinator called for architecture_review tickets
- Guard: second call for same ticket_id is skipped (has_running=True)

`test_poller.py` (mocked Orchestrator client):
- Returns only tickets with assigned_agent
- Filters out tickets with has_running=True

## Constraints (enforce all from constitution)

- Python 3.12, same library versions as monorepo pyproject.toml
- Never modify FSM state directly
- Never run two agents on same ticket simultaneously
- Never crash on missing [RESULT] block
- Never cache agent prompts — read from disk each run
- Never expose SERVICE_JWT or TM credentials in logs or API responses
- AUTH_MODE=local behaviour identical to other services
- Dockerfile: python:3.12-slim, non-root user

## New env section for monorepo `infra/.env.example`

Add this group to the shared env file after context-distiller section:

```dotenv
# ─── Agent Dispatcher ─────────────────────────────────────────────────────
# How agents are executed: claude_code = spawn Claude CLI, api = OpenAI API
AGENT_RUNNER_MODE=claude_code

# Path to the claude CLI binary (used in claude_code mode)
CLAUDE_CODE_PATH=claude

# Path to Claude's MCP config file (must include brainstorm and agent-tools)
CLAUDE_MCP_CONFIG_PATH=/home/appuser/.claude/mcp_config.json

# Directory containing agent system prompt files ({agent_id}.md)
AGENT_PROMPTS_DIR=/app/prompts

# How often to poll Orchestrator for new assignments (seconds)
POLL_INTERVAL_SECONDS=10

# Maximum concurrent agent runs
WORKER_MAX_CONCURRENT_RUNS=3

# Comma-separated list of agents to run in brainstorm (architecture_review)
BRAINSTORM_AGENTS=software_architect,security_architect

# Maximum brainstorm rounds before forcing synthesis
BRAINSTORM_MAX_ROUNDS=3

# Max tokens of project memory injected into agent context
CONTEXT_MAX_TOKENS=3000

# Default agent timeout (seconds). Override per-agent:
# AGENT_TIMEOUT_BACKEND=900, AGENT_TIMEOUT_AUTOTESTER=600, etc.
AGENT_TIMEOUT_DEFAULT=300
```

## Out of scope for this spec

- Writing agent system prompt files (they already exist per user)
- Implementing agent-tools MCP server (separate spec)
- Keycloak integration (auth adapter stub only)
- Metrics / Prometheus endpoint (nice-to-have, not required for v1)
- Re-running failed agent runs (manual re-trigger via Orchestrator)
```
