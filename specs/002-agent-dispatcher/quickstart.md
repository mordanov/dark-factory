# Quickstart: Agent Dispatcher Service

**Feature**: `002-agent-dispatcher`
**Prereqs**: Docker + Docker Compose, `infra/.env` populated

---

## Run in the Monorepo

```bash
# From the dark-factory root:
cp infra/.env.example infra/.env
# Fill in POSTGRES_PASSWORD, JWT_SECRET_KEY values, OPENAI_API_KEY
# Add the Agent Dispatcher section (see infra/.env.example for template)

docker compose -f infra/docker-compose.yml up --build
```

The Dispatcher starts after Postgres is healthy and begins polling the Orchestrator
every `POLL_INTERVAL_SECONDS` seconds.

Verify it's running:

```bash
curl http://localhost:8006/api/health
# {"status":"ok","runner_mode":"claude_code"}
```

---

## Run in Isolation (dev)

```bash
cd services/agent-dispatcher

# Create .env from example
cp .env.example .env  # fill in DATABASE_URL, JWT_SECRET_KEY, etc.

# Start just Postgres + the Dispatcher
docker compose up --build
```

---

## Run Tests

```bash
cd services/agent-dispatcher

# Install deps
pip install -r requirements.txt

# Unit tests only (no I/O, fast)
pytest tests/unit/ -v

# All tests with coverage
pytest --cov=src --cov-report=term-missing

# Lint
ruff check src/ tests/
ruff format --check src/ tests/
```

---

## Trigger a Test Run Manually

1. Create a ticket in Ticket Manager with `assigned_agent = "backend"` and a matching
   `fsm_status` via the Orchestrator (e.g., `implementation`).

2. The Dispatcher will detect it on the next poll cycle and create a run:

```bash
curl -H "Authorization: Bearer <your-jwt>" \
     http://localhost:8006/api/v1/runs?ticket_id=TKT-001
```

---

## Configure Runner Mode

| Mode | What happens |
|------|-------------|
| `AGENT_RUNNER_MODE=claude_code` | Spawns `claude --print` subprocess |
| `AGENT_RUNNER_MODE=api` | Calls OpenAI API directly |

In `claude_code` mode, ensure `CLAUDE_CODE_PATH` points to the `claude` binary and
`CLAUDE_MCP_CONFIG_PATH` points to a valid MCP config with `brainstorm` registered.

---

## Add or Update an Agent Prompt

Prompt files live in `services/agent-dispatcher/prompts/{agent_id}.md`.
They are read from disk on every agent run — restart is NOT required after edits.

---

## Launch the Full Agent Team (run-agents.sh)

To run the ten-agent brainstorm team that the Dispatcher coordinates:

```bash
cd development
bash run-agents.sh --project dark-factory
```

This opens terminal windows for each agent. The `project-administrator` agent
initialises the metrics SQLite DB and broadcasts the pa-ready signal before the
rest of the team joins.

Each agent that completes a task calls `development/scripts/report-task-metrics.sh`
as part of its completion handshake (STEP 5 in every agent's startup prompt).

To view the metrics report:

```bash
cd development/project-administrator
python agent_metrics.py summary
python agent_metrics.py report-html  # generates HTML report
```
