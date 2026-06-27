# Quickstart: 006 — Agent Capability Registry & Dynamic Agent Selection

## What Changed

- `development/agents/registry.yaml` — single source of truth for all 10 agent roles
- `agent-dispatcher` loads the registry once at startup via FastAPI lifespan
- Registry YAML is forwarded in every Orchestrator job trigger payload
- `_write_credentials()` writes `development/{role}/credentials.json` before each agent spawn
- `AGENT_FOR_STATE` dict removed from Orchestrator FSM engine

## Prerequisites

- Docker Compose v2
- `infra/.env` configured (see `infra/.env.example`)

## Running the Platform

```bash
cp infra/.env.example infra/.env   # fill required credentials
docker compose -f infra/docker-compose.yml up --build
```

The agent-dispatcher mounts `development/agents/registry.yaml` read-only at `/app/registry.yaml`. On startup, a log line confirms the registry loaded:

```
INFO  capability_registry loaded  path=/app/registry.yaml  agents=10
```

## Smoke Test: Verify Registry Loads

After `docker compose up`, run:

```bash
docker compose -f infra/docker-compose.yml logs agent-dispatcher | grep "capability_registry loaded"
```

Expected output includes `agents=10`. If the line is absent, the registry file is missing or malformed — check the volume mount and YAML syntax.

## Reloading the Registry

The registry is **loaded once at startup** (FR-003 / NFR-03). There is no hot-reload.

To apply changes to `development/agents/registry.yaml`:

```bash
docker compose -f infra/docker-compose.yml restart agent-dispatcher
```

Verify the reload with:

```bash
docker compose -f infra/docker-compose.yml logs --tail=20 agent-dispatcher | grep "capability_registry loaded"
```

## Credentials Files

Before each agent spawn, the dispatcher writes `development/{role}/credentials.json` with a fresh TM API token. These files are:

- Gitignored via `development/**/credentials.json` in `.gitignore` (monorepo root)
- Never committed to git
- Overwritten on each dispatch — no manual rotation needed

If an agent fails to authenticate, check that the dispatcher service account has a valid Keycloak token (`KEYCLOAK_CLIENT_SECRET` in `.env`).

## Environment Variables (agent-dispatcher)

| Variable | Default | Purpose |
|---|---|---|
| `AGENT_REGISTRY_PATH` | `/app/registry.yaml` | Path to registry inside container |
| `AGENT_PROMPTS_DIR` | `/app/prompts` | Directory containing agent skill `.md` files |
| `BRAINSTORM_AGENTS` | `software-architect,security-architect` | Agents that join brainstorm sessions (hyphenated IDs) |

## Extending the Registry

To add a new agent role:

1. Add an entry to `development/agents/registry.yaml` with all required fields
2. Add the agent's skill file to `services/agent-dispatcher/prompts/`
3. Add the `role_id` to `VALID_AGENT_IDS` in `agent-dispatcher/src/core/constants.py`
4. Restart `agent-dispatcher`: `docker compose -f infra/docker-compose.yml restart agent-dispatcher`

Role IDs must be hyphenated and match `development/run-agents.sh` ROLES array exactly.
