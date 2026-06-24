# Dark Factory

A multi-service AI development platform. Developers describe work in natural language; the platform decomposes it into tickets, dispatches specialist AI agents, and tracks execution end-to-end.

## Services

| Service | Port | Description |
|---------|------|-------------|
| user-input-manager | 8001 | Prompt Studio — React + FastAPI + PostgreSQL. Accepts prompts, decomposes them into Epic → Stories → Tasks via the Planning Agent, and creates the full ticket hierarchy in Ticket Manager. |
| ticket-manager | 8002 | Ticket tracking — React + FastAPI + PostgreSQL. Manages projects, tickets, assignments, and progress updates for human and agent contributors. |
| orchestrator | 8003 | Workflow FSM — FastAPI + PostgreSQL + MongoDB. Evaluates ticket state, decides which agent to assign next, and drives the automation pipeline. |
| context-distiller | 8004 | Memory compression — FastAPI + PostgreSQL + MongoDB. Stores per-project agent configuration and distilled memory for agent context assembly. |
| agent-tools | 8005 | MCP server — Python + FastAPI. Exposes tool integrations for agents running in Claude Code mode. |
| agent-dispatcher | 8006 | Agent runner — FastAPI + PostgreSQL. Polls the Orchestrator for agent assignments, executes agents (Claude Code subprocess or direct API), coordinates multi-agent brainstorm sessions for architecture reviews, and reports results back to Ticket Manager and Orchestrator. |

## Infrastructure

| Component | Location | Description |
|-----------|----------|-------------|
| Unified compose | `infra/docker-compose.yml` | Full platform topology |
| Dev port overrides | `infra/docker-compose.override.yml` | Exposes service ports 8001–8006 and Keycloak 8080 |
| Environment template | `infra/.env.example` | All required variables with inline documentation |
| Nginx template | `infra/nginx/nginx.conf.template` | Reverse proxy with `auth_request` on all `/api/` locations |
| PostgreSQL init | `infra/postgres/init/01_create_databases.sql` | Creates all databases on first boot |
| Keycloak realm | `infra/keycloak/realm-export.json` | Full realm definition with client registrations |
| oauth2-proxy config | `infra/oauth2-proxy/config.cfg` | Bearer validator for nginx `auth_request` |
| Keycloak operations | `infra/KEYCLOAK.md` | Admin console, user management, troubleshooting |

## Getting Started

### Prerequisites

- Docker + Docker Compose v2

### Start the full platform

```bash
cp infra/.env.example infra/.env
# Fill in required values — at minimum:
#   POSTGRES_PASSWORD
#   KC_BOOTSTRAP_ADMIN_PASSWORD, KC_DB_PASSWORD
#   OAUTH2_PROXY_CLIENT_SECRET, OAUTH2_PROXY_COOKIE_SECRET
#   KC_*_CLIENT_SECRET (one per service — see .env.example)
#   OPENAI_API_KEY (for agent runs)

docker compose -f infra/docker-compose.yml up --build
```

Keycloak imports the realm on first boot — allow up to 5 minutes. Both frontends are accessible via nginx once all healthchecks pass.

### First login

1. Open the Keycloak admin console at `http://localhost:8080/admin` (requires `docker-compose.override.yml` port mapping).
2. Log in with `KC_BOOTSTRAP_ADMIN_USERNAME` / `KC_BOOTSTRAP_ADMIN_PASSWORD`.
3. Create user accounts, assign the `user` or `administrator` realm role, and set passwords.
4. Navigate to either frontend — you will be redirected to the Keycloak login page.

See `infra/KEYCLOAK.md` for full administration instructions.

### Local development (per-service)

Each service can be started in isolation via its own compose file:

```bash
cd services/user-input-manager
docker compose up --build
```

### Running integration tests

```bash
cp infra/.env.example infra/.env   # if not already done
docker compose -f integration-tests/docker-compose.test.yml up --build -d
pytest integration-tests/ -v
docker compose -f integration-tests/docker-compose.test.yml down -v
```

Integration tests run against real services; LLM calls are intercepted by a local mock server (no real OpenAI credentials required). The full suite completes in under 120 seconds.

## Features

### 001 — Monorepo Unification

Unified `infra/docker-compose.yml` starts all six services, PostgreSQL, MongoDB, nginx, Keycloak, and oauth2-proxy with a single command. Nginx serves both React frontends from multi-stage Docker images and proxies API traffic to backend services. A root `.pre-commit-config.yaml` runs `ruff` lint and format across all Python files. Frontend auth state is held in Zustand (never in `localStorage` or `sessionStorage`). Vitest enforces ≥80% line and function coverage on both frontends.

### 002 — Agent Dispatcher

Polls the Orchestrator for tickets with an `assigned_agent` field set. Executes agents in one of two modes: `claude_code` (Claude Code subprocess) or `api` (direct LLM call). Parses `[RESULT]...[/RESULT]` blocks from agent output; handles missing or malformed blocks gracefully (`needs_review` state). Enforces a single-active-run-per-ticket invariant. Coordinates sequential multi-agent brainstorm sessions for `architecture_review` tickets with configurable round limits and early-consensus exit. On startup, sweeps orphaned `running` records left by a previous crash and transitions them to `needs_review`. See `services/agent-dispatcher/README.md` for setup, environment variables, and API reference.

### 003 — Planning Agent

Extends Prompt Studio with a plan generation flow. After a prompt is approved, the user clicks "Generate Plan" — the system calls the LLM and decomposes the prompt into one Epic, up to ten Stories, and up to ten Tasks per Story. The plan is persisted before display. The user reviews and edits the tree (title, description, delete nodes) before confirming. No tickets are created in Ticket Manager until explicit confirmation. After confirmation, all tickets are created atomically; partial failures are retryable without duplicates. Agent configuration is generated in parallel and stored in Context Distiller for use by downstream agents.

### 004 — Keycloak IAM Migration

Replaces all local password-based authentication with Keycloak 25 as the sole identity provider. Every backend's `auth_adapter.py` becomes a `KeycloakValidator` that validates RS256 tokens from Keycloak's JWKS endpoint (cached ≥300s). Service-to-service calls use Client Credentials grants via `KeycloakServiceClient`. Both frontends replace hand-rolled login forms with `keycloak-js` PKCE flows. The `users` table is dropped from every service that held one (destructive Alembic migrations — no rollback). All `user_id` columns become `TEXT NOT NULL` storing the Keycloak `sub` UUID. `AUTH_MODE=local` (HS256 test tokens) is reserved for automated tests only and must never appear in `infra/docker-compose.yml`.

## Repository Layout

```
dark-factory/
├── services/
│   ├── user-input-manager/    # Prompt Studio (React + FastAPI + PostgreSQL)
│   ├── ticket-manager/        # Ticket tracking (React + FastAPI + PostgreSQL)
│   ├── orchestrator/          # Workflow FSM (FastAPI + PostgreSQL + MongoDB)
│   ├── context-distiller/     # Memory compression (FastAPI + PostgreSQL + MongoDB)
│   ├── agent-tools/           # MCP server (Python + FastAPI)
│   └── agent-dispatcher/      # Agent runner (FastAPI + PostgreSQL)
├── infra/
│   ├── docker-compose.yml           # Unified compose
│   ├── docker-compose.override.yml  # Dev port exposure
│   ├── .env.example                 # Environment template
│   ├── nginx/                       # Nginx config template + Dockerfile
│   ├── postgres/init/               # PostgreSQL init SQL
│   ├── keycloak/                    # Realm export + env-substitution script
│   ├── oauth2-proxy/                # Bearer validator config
│   └── KEYCLOAK.md                  # Keycloak operations guide
├── integration-tests/         # Cross-service test suite
├── specs/                     # Feature specifications
│   ├── 001-monorepo-unification/
│   ├── 002-agent-dispatcher/
│   ├── 003-planning-agent/
│   └── 004-keycloak-iam-migration/
├── development/               # Agent definitions and scripts
├── pyproject.toml             # Canonical Python versions + ruff config
├── package.json               # Canonical frontend versions (reference)
└── .pre-commit-config.yaml    # Root ruff hooks
```

## Code Quality

```bash
pip install pre-commit
pre-commit install

# Run manually across the full monorepo
pre-commit run --all-files
```

## Canonical Versions

| Layer | Technology | Version |
|-------|-----------|---------|
| Language | Python | 3.12 |
| API framework | FastAPI | 0.115.5 |
| ORM | SQLAlchemy | 2.0.36 |
| DB driver | asyncpg | 0.30.0 |
| Validation | pydantic | 2.10.3 |
| Linter | ruff | 0.8.3 |
| Frontend | React | 18.3.1 |
| Build tool | Vite | 6.0.3 |
| Test runner | Vitest | 2.1.8 |
| State management | Zustand | 5.0.2 |
| Auth (browser) | keycloak-js | 25.x |
| Databases | PostgreSQL | 16 |
| Databases | MongoDB | 7 |
| Identity provider | Keycloak | 25 |
| Proxy | nginx | alpine |

See `pyproject.toml [tool.versions]` and `package.json canonicalVersions` for pinned versions.

## Environment Variables

See `infra/.env.example` for all required variables with inline documentation. Key sections:

- `POSTGRES_PASSWORD`, `KC_DB_PASSWORD` — database credentials
- `KC_BOOTSTRAP_ADMIN_*` — Keycloak bootstrap admin (change on first login)
- `KC_*_CLIENT_SECRET` — one confidential client secret per backend service
- `OAUTH2_PROXY_CLIENT_SECRET`, `OAUTH2_PROXY_COOKIE_SECRET` — nginx auth proxy
- `OPENAI_API_KEY` — required for agent runs in API mode
- `VITE_KEYCLOAK_URL`, `VITE_*_CLIENT_ID` — frontend Keycloak configuration
