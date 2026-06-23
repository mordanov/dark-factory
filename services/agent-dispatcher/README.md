# Agent Dispatcher Service

Polls the Orchestrator for tickets with an assigned agent, executes the agent (Claude Code subprocess or OpenAI API), coordinates multi-round brainstorm sessions for architecture-review tickets, and reports results back to Ticket Manager and Orchestrator.

Part of the [Dark Factory](../../CLAUDE.md) monorepo. Internal URL: `http://agent-dispatcher:8000`. Dev port: `8006`.

---

## Prerequisites

- Docker + Docker Compose (for container mode)
- Python 3.12 (for local mode)
- PostgreSQL 16 with database `df_dispatcher` (or `df_dispatcher_test` for tests)
- `claude` CLI on `PATH` (for `claude_code` runner mode)
- OpenAI API key (for `api` runner mode)

---

## Environment Variables

All variables can be set in `infra/.env` (monorepo) or a local `.env` file in this directory.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/df_dispatcher` | Async SQLAlchemy URL |
| `JWT_SECRET_KEY` | `CHANGE_ME` | Shared secret for JWT signing/verification (must match all services) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `AUTH_MODE` | `local` | `local` uses built-in JWT validation; `keycloak` raises HTTP 501 |
| `SERVICE_JWT_EXPIRE_HOURS` | `1` | Lifetime of outbound service JWTs |
| `AGENT_RUNNER_MODE` | `claude_code` | `claude_code` (subprocess) or `api` (direct OpenAI call) |
| `CLAUDE_CODE_PATH` | `claude` | Path to the `claude` CLI binary |
| `CLAUDE_MCP_CONFIG_PATH` | `~/.claude/mcp_config.json` | MCP config passed to Claude Code subprocess |
| `AGENT_PROMPTS_DIR` | `prompts` | Directory containing per-agent system prompt files (`{agent_id}.md`) |
| `AGENT_TIMEOUT_DEFAULT` | `300` | Default agent run timeout in seconds |
| `AGENT_TIMEOUT_{AGENT_ID_UPPER}` | — | Per-agent override, e.g. `AGENT_TIMEOUT_BACKEND=600` |
| `WORKER_MAX_CONCURRENT_RUNS` | `3` | Max simultaneous agent runs (semaphore) |
| `POLL_INTERVAL_SECONDS` | `10` | Orchestrator polling interval in seconds |
| `BRAINSTORM_AGENTS` | `software_architect,security_architect` | Comma-separated agents for architecture-review sessions |
| `BRAINSTORM_MAX_ROUNDS` | `3` | Max brainstorm rounds before concluding without consensus |
| `CONTEXT_MAX_TOKENS` | `4000` | Approximate token limit for injected project memory |
| `ORCHESTRATOR_BASE_URL` | `http://orchestrator:8000` | Orchestrator internal URL |
| `TICKET_MANAGER_BASE_URL` | `http://ticket-manager:8000` | Ticket Manager internal URL |
| `CONTEXT_DISTILLER_BASE_URL` | `http://context-distiller:8000` | Context Distiller internal URL |
| `OPENAI_API_KEY` | — | Required for `api` runner mode |
| `OPENAI_MODEL` | `gpt-4o` | Model for `api` runner mode |
| `OPENAI_BASE_URL` | — | Override for Azure OpenAI or a local proxy |
| `CORS_ALLOW_ORIGINS` | `["http://localhost:5173"]` | CORS allowed origins |
| `DEBUG` | `false` | Enable debug logging |

---

## Runner Modes

### `claude_code` (default)

Launches the `claude` CLI as an async subprocess using `asyncio.create_subprocess_exec`. The agent receives a full markdown context document as its task input. The subprocess output is captured and the last `[RESULT]...[/RESULT]` block is parsed as JSON.

**When to use**: When Claude Code is available on the host or in the container and you want agents to use MCP tools (brainstorm-mcp, etc.) natively.

**Requires**: `claude` on `PATH`, `CLAUDE_MCP_CONFIG_PATH` pointing to a valid MCP config.

### `api`

Calls the OpenAI chat completions API directly using the `openai` Python SDK (`AsyncOpenAI`). The agent system prompt is sent as the `system` message; the context document is sent as the `user` message.

**When to use**: Lightweight deployments without the Claude Code CLI, CI environments, or when running against OpenAI-compatible endpoints (Azure, local proxy via `OPENAI_BASE_URL`).

**Requires**: `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL` for non-default endpoints).

---

## Running in Isolation

```bash
# 1. Copy env example and fill in required values
cp ../../infra/.env.example .env
# Required: POSTGRES_PASSWORD, JWT_SECRET_KEY

# 2. Start Postgres + service
docker compose up --build

# 3. Verify health
curl http://localhost:8006/api/health
# → {"status":"ok","runner_mode":"claude_code"}

# 4. List runs (requires a valid Bearer token)
curl -H "Authorization: Bearer <token>" http://localhost:8006/api/v1/runs
# → {"items":[],"total":0}
```

The standalone `docker-compose.yml` in this directory starts only PostgreSQL and the dispatcher service. Alembic migrations run automatically on startup.

---

## Running in the Monorepo

```bash
# From the repository root
cp infra/.env.example infra/.env
# Fill in POSTGRES_PASSWORD, JWT_SECRET_KEY, OPENAI_API_KEY

docker compose -f infra/docker-compose.yml up --build
```

The monorepo compose starts all five services plus the dispatcher on port `8006`. The dispatcher will begin polling the Orchestrator once both are healthy.

---

## Running Tests

Integration tests require a local PostgreSQL 16 instance with the `df_dispatcher_test` database created:

```sql
CREATE DATABASE df_dispatcher_test;
```

```bash
cd services/agent-dispatcher

# Install dependencies (use a virtual environment)
pip install -r requirements.txt

# Run all tests with coverage
pytest --cov=src --cov-report=term-missing --cov-fail-under=80

# Unit tests only (no DB required)
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Run linter and formatter
ruff check src/ tests/
ruff format src/ tests/
```

Current coverage: **83.4%** (threshold: 80%).

---

## API Reference

### `GET /api/health`

Returns service health and active runner mode. No authentication required.

```http
GET /api/health HTTP/1.1
```

**Response 200**:
```json
{
  "status": "ok",
  "runner_mode": "claude_code"
}
```

---

### `GET /api/v1/runs`

Returns a paginated list of agent runs. **Auth required** (Bearer JWT).

**Query parameters**:

| Parameter | Type | Default | Valid values | Description |
|---|---|---|---|---|
| `ticket_id` | string | — | any | Filter by ticket ID |
| `status` | string | — | `pending` `running` `completed` `needs_review` `failed` `timed_out` | Filter by run status; invalid value returns 422 |
| `offset` | integer | `0` | ≥ 0 | Pagination offset |
| `limit` | integer | `50` | 1–100 | Page size |

**Response 200**:
```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "ticket_id": "TKT-001",
      "project_id": "proj-123",
      "agent_id": "backend",
      "runner_mode": "claude_code",
      "status": "completed",
      "round_number": 1,
      "brainstorm_session_id": null,
      "raw_output": null,
      "result": {
        "status": "completed",
        "summary": "Implemented the login endpoint.",
        "artifacts": ["services/user-input-manager/backend/src/api/v1/auth.py"],
        "tm_comment": "Done. Login endpoint added with JWT response.",
        "brainstorm_consensus": null,
        "errors": []
      },
      "error_message": null,
      "started_at": "2026-06-22T10:00:00Z",
      "finished_at": "2026-06-22T10:05:30Z",
      "created_at": "2026-06-22T10:00:00Z"
    }
  ],
  "total": 1
}
```

Note: `raw_output` is always `null` in list responses. Use the detail endpoint to retrieve captured stdout.

Note: `result.status` (agent-reported) is a separate enum from the top-level run `status`. Mapping: agent `blocked` → run `needs_review`.

---

### `GET /api/v1/runs/{run_id}`

Returns a single run including the full captured `raw_output`. **Auth required** (Bearer JWT).

**Path parameter**: `run_id` — UUID of the run.

**Response 200**: Same schema as a list item, with `raw_output` populated (may be large).

**Response 404**:
```json
{
  "detail": "Run not found"
}
```

**Error shapes**:

| Status | When |
|---|---|
| `401` | Missing or invalid Bearer token → `{"detail": "Not authenticated"}` |
| `422` | Invalid query parameter (e.g. unknown status value) → FastAPI validation error |
| `404` | Run not found → `{"detail": "Run not found"}` |
| `500` | Unhandled internal error → `{"detail": "Internal server error"}` |

---

## Troubleshooting

### Orphaned `running` records after a crash

If the service crashes while agent runs are in progress, `agent_runs` rows will be stuck in `running` status, which blocks those tickets from being picked up again (double-run guard).

**Resolution**: On the next startup the service automatically sweeps all `running` rows to `needs_review` with `error_message = "Service restarted; run orphaned"` and re-triggers the Orchestrator for each affected ticket. No manual intervention is required.

To inspect orphaned records before restart:
```sql
SELECT id, ticket_id, agent_id, started_at
FROM agent_runs
WHERE status = 'running';
```

---

### Missing prompt file for an agent

If `AGENT_PROMPTS_DIR/{agent_id}.md` does not exist when a ticket is dispatched, the run is immediately marked `failed` with `error_message = "No prompt file found for agent '{agent_id}'"` and the Orchestrator is triggered. The service continues running.

**Fix**: Add the missing prompt file to the `prompts/` directory. The file is read fresh on every run (no caching), so no restart is needed.

Valid agent IDs (enforced by whitelist): `backend`, `frontend`, `software_architect`, `security_architect`, `project_manager`, `designer`, `code_reviewer`, `autotester`, `devops`, `project_administrator`.

---

### Orchestrator unreachable during polling

If the Orchestrator returns an error or is unreachable during a poll cycle, the poller logs a warning and returns an empty list. The next poll cycle proceeds normally after `POLL_INTERVAL_SECONDS`. No runs are lost and the polling loop does not crash.

---

### Agent run produces no `[RESULT]` block

If an agent exits without a parseable `[RESULT]...[/RESULT]` block in its stdout, the run is marked `needs_review` and the raw stdout (truncated to 2000 characters) is posted as a Ticket Manager comment. The Orchestrator is triggered so the FSM can decide the next step (e.g. retry or escalate).

---

### `api` mode with Azure OpenAI

Set `OPENAI_BASE_URL` to your Azure endpoint and `OPENAI_API_KEY` to your Azure key:

```env
AGENT_RUNNER_MODE=api
OPENAI_BASE_URL=https://my-deployment.openai.azure.com/
OPENAI_API_KEY=<azure-key>
OPENAI_MODEL=gpt-4o
```
