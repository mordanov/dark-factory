# Dark Factory Monorepo — Project Constitution

## Identity

This constitution governs the unification of five independently developed
Dark Factory services into a single monorepo with centralised infrastructure.

The five services are:
- **user-input-manager** — Prompt Studio (React + FastAPI + PostgreSQL)
- **ticket-manager** — Ticket tracking platform (React + FastAPI + PostgreSQL)
- **orchestrator** — Workflow FSM + LLM decision engine (FastAPI + PostgreSQL + MongoDB)
- **context-distiller** — Project memory compression (FastAPI + PostgreSQL + MongoDB)
- **agent-tools** — MCP tool server for Dark Factory agents (Python MCP server)

The goal of unification is operational: one `docker compose up` starts the entire
Dark Factory platform. Each service retains its own codebase, database, and
deployment identity. This is a mono**repo**, not a mono**lith**.

---

## Core Principles

### 1. Services remain independently deployable

Each service must be runnable in isolation with its own `docker-compose.yml`
(for development) AND as part of the unified compose (for production).
The monorepo provides shared infrastructure. It must not introduce hard coupling
between services at the code level. Services communicate only via HTTP APIs
over the internal Docker network — never via shared Python imports or a shared
application database.

### 2. Auth adapter pattern — preparation for Keycloak

Authentication must NOT be removed in this phase. However, all JWT validation
logic must be extracted into a single `auth_adapter` module per service
(replacing any inline `verify_token` / `decode_token` calls scattered across
route handlers and dependencies).

The adapter must support two modes controlled by `AUTH_MODE` env var:

```
AUTH_MODE=local     # validates JWT with local SECRET_KEY (current behaviour)
AUTH_MODE=keycloak  # validates JWT against Keycloak JWKS endpoint (future)
```

When `AUTH_MODE=local`, behaviour is identical to the current implementation.
When `AUTH_MODE=keycloak`, the adapter fetches the JWKS from
`KEYCLOAK_JWKS_URL` and validates the token signature against it.

This is the **only** auth change permitted in this phase. Do not:
- Remove user tables
- Remove login endpoints
- Add Keycloak registration or user sync
- Implement SSO flows

The Keycloak migration is a separate future phase. This phase only prepares the
seam. Every service must have the adapter in place before this phase is done.

### 3. Python 3.12 everywhere — no exceptions

All five backend services must run on Python 3.12.
ticket-manager currently runs on 3.11 and must be upgraded.
The Dockerfile base image for every service is `python:3.12-slim`.
Any dependency that does not support 3.12 must be replaced or removed.

### 4. Shared library versions — pinned in `pyproject.toml`

A root-level `pyproject.toml` defines the canonical version for every shared
Python library. Each service's `requirements.txt` must use these exact versions.
No service may pin a different version of a shared library without a constitution
amendment documenting the reason.

**Canonical versions (root `pyproject.toml` → `[tool.versions]`):**
```
fastapi = "0.115.5"
uvicorn = "0.32.1"
sqlalchemy = "2.0.36"
asyncpg = "0.30.0"
alembic = "1.14.0"
pydantic = "2.10.3"
pydantic-settings = "2.6.1"
python-jose = "3.3.0"
passlib = "1.7.4"
httpx = "0.28.0"
openai = "1.57.0"
structlog = "24.4.0"
pytest = "8.3.4"
pytest-asyncio = "0.24.0"
pytest-cov = "6.0.0"
ruff = "0.8.3"
```

### 5. Shared frontend library versions

A root-level `package.json` (workspaces are NOT used — this is for reference only)
documents the canonical version for every shared frontend library.
Services with a frontend (user-input-manager, ticket-manager) must use these
exact versions.

**Canonical frontend versions:**
```
react: "18.3.1"
react-dom: "18.3.1"
react-router-dom: "6.28.0"
typescript: "5.7.2"
vite: "6.0.3"
vitest: "2.1.8"
@testing-library/react: "16.1.0"
@testing-library/jest-dom: "6.6.3"
@testing-library/user-event: "14.5.2"
zustand: "5.0.2"
axios: "1.7.9"
i18next: "24.0.5"
react-i18next: "15.1.3"
```

### 6. Zustand for all frontend state management

**user-input-manager currently uses React Context API for auth state.
It must be migrated to Zustand.** ticket-manager already uses Zustand.
No new frontend code may use React Context for application state.
React Context is permitted only for theme propagation and i18n providers.

Access tokens must be stored **in memory only** (Zustand store, not persisted).
This is already the ticket-manager standard. user-input-manager must be
brought to the same standard as part of this migration.
Remove all `localStorage.setItem('access_token', ...)` calls from
user-input-manager frontend.

### 7. Vitest for all frontend tests

ticket-manager and user-input-manager must both use **Vitest** as the test runner.
Any existing Jest configuration must be removed.
Coverage threshold: 80% lines/functions (enforced in `vite.config.ts`).

### 8. ruff for all Python linting and formatting

All five backend services must have `.pre-commit-config.yaml` at their service
root using ruff for both linting and formatting. A shared root-level
`.pre-commit-config.yaml` also exists and applies to all Python files in the repo.

Pre-commit hooks (pinned to `ruff==0.8.3`):
- `ruff` — lint with `--fix`
- `ruff-format` — format (replaces black)

No other Python linters are added in this phase (no mypy, no bandit).

### 9. Nginx is DNS-name aware from day one

Nginx must be configured with **one `server` block per frontend service**.
The server name for each block is controlled by an environment variable,
not hardcoded. The `nginx.conf` template uses `envsubst` at container startup
to substitute DNS names.

Every `server` block must include:
- `location /.well-known/acme-challenge/` for certbot
- SSL stanza (commented out, with instructions to uncomment after certbot)
- HTTP → HTTPS redirect block (commented out, ready to enable)

This means certbot can be added without modifying `nginx.conf`.

### 10. No cross-service database access

Each service owns exactly one PostgreSQL database and one MongoDB database
(where applicable). No service may query another service's database directly.
Cross-service data access is always via HTTP API.

---

## Monorepo Layout (fixed — do not deviate)

```
dark-factory/                          ← monorepo root
├── services/
│   ├── user-input-manager/            ← Prompt Studio (moved from dark-factory/)
│   ├── ticket-manager/                ← existing service
│   ├── orchestrator/                  ← existing service
│   ├── context-distiller/             ← to be built (see separate constitution)
│   └── agent-tools/                   ← to be built (see separate constitution)
├── infra/
│   ├── docker-compose.yml             ← single unified compose
│   ├── docker-compose.override.yml    ← dev overrides (port exposure, volumes)
│   ├── .env                           ← shared env (single source of truth)
│   ├── .env.example                   ← committed, fully commented
│   ├── nginx/
│   │   ├── Dockerfile                 ← nginx image with envsubst
│   │   ├── nginx.conf.template        ← envsubst template (uses $VAR notation)
│   │   └── snippets/
│   │       ├── ssl.conf               ← SSL params (commented, certbot-ready)
│   │       └── proxy.conf             ← shared proxy headers
│   └── postgres/
│       └── init/
│           └── 01_create_databases.sql  ← CREATE DATABASE for all services
├── integration-tests/
│   ├── docker-compose.test.yml        ← starts all services for integration tests
│   ├── conftest.py                    ← shared fixtures (httpx clients per service)
│   ├── tests/
│   │   ├── test_scenario_a.py         ← UIM → TM ticket creation flow
│   │   └── test_scenario_c.py         ← Orchestrator done → ContextDistiller → memory
│   └── requirements.txt               ← pytest, httpx, pytest-asyncio only
├── .pre-commit-config.yaml            ← root-level hooks (ruff for all Python)
├── pyproject.toml                     ← canonical Python library versions + ruff config
├── package.json                       ← canonical frontend versions (reference only)
├── .gitignore                         ← monorepo-level ignores
├── CLAUDE.md                          ← monorepo map for Claude Code sessions
└── README.md                          ← getting started, service map, ports
```

Services retain their own internal structure. Do not reorganise files inside
`services/*/` beyond what is required for the standardisation tasks.

---

## Service Registry

| Service | Internal port | Frontend | Database (PG) | Database (Mongo) | DNS env var |
|---|---|---|---|---|---|
| user-input-manager | 8001 | yes | `df_user_input` | — | `UIM_HOST` |
| ticket-manager | 8002 | yes | `df_ticket_manager` | — | `TM_HOST` |
| orchestrator | 8003 | no (UI via UIM) | `df_orchestrator` | `df_orchestrator_docs` | — |
| context-distiller | 8004 | no | `df_distiller` | `df_distiller_docs` | — |
| agent-tools | 8005 | no | — | — | — |

Internal service-to-service URLs follow the pattern `http://{service-name}:{port}`.
The service name is the Docker Compose service name (e.g., `http://orchestrator:8003`).

---

## Shared Infrastructure

### PostgreSQL 16

Single instance, service name `postgres` in compose.
Databases are created by `infra/postgres/init/01_create_databases.sql` on first boot.
Each service connects with its own dedicated user and password (env vars).

The init SQL must:
```sql
CREATE DATABASE df_user_input;
CREATE DATABASE df_ticket_manager;
CREATE DATABASE df_orchestrator;
CREATE DATABASE df_distiller;
CREATE USER uim_user WITH PASSWORD '...';
-- etc.
GRANT ALL PRIVILEGES ON DATABASE df_user_input TO uim_user;
-- etc.
```

Passwords come from env vars injected into the init script via `POSTGRES_INITDB_ARGS`
or a compose entrypoint wrapper. Do not hardcode passwords in the init SQL.

### MongoDB 7

Single instance, service name `mongo` in compose.
Each service that uses Mongo connects to its own database by name.
No shared collections. No cross-service Mongo queries.

### Nginx

Single nginx container as the entry point for all external traffic.
Serves frontend apps and proxies API calls to backend services.
Built from `infra/nginx/Dockerfile` using `envsubst` to render the template.

Port mapping: `80:80` only. HTTPS (443) is added by the operator post-certbot.

---

## Integration Test Requirements

### Scope

Two scenarios, implemented in `integration-tests/tests/`:

**Scenario A — User Input Manager → Ticket Manager**
```
1. POST /api/v1/auth/login on UIM → get access token
2. POST /api/v1/sessions on UIM (new_project, existing TM project)
3. POST /api/v1/sessions/{id}/feedback (is_approved: false) → triggers LLM refinement
4. POST /api/v1/sessions/{id}/feedback (is_approved: true)
5. POST /api/v1/sessions/{id}/approve (ticket_title, project_description)
6. Assert: GET /api/v1/projects/{id}/tickets on TM returns the created ticket
7. Assert: ticket has tag "needs-estimation" and description prefix "[needs-estimation]"
```

**Scenario C — Orchestrator → ContextDistiller → project memory readable**
```
1. Create a ticket in TM with fsm_status="done" (via PATCH /fsm)
2. POST /api/v1/orchestrator/jobs/trigger on UIM (proxied to Orchestrator)
3. Poll GET /api/v1/orchestrator/jobs/{id} until status="done" (timeout: 30s)
4. Assert: GET /api/v1/orchestrator/memory/{project_id} returns non-null content
5. Assert: content is valid YAML with required top-level keys
```

### Rules

- Tests run against **real services** started by `docker-compose.test.yml`.
  No mocking of inter-service HTTP calls in integration tests.
- LLM calls (OpenAI) **are** mocked via a WireMock or `respx` ASGI intercept
  injected at the service level via `OPENAI_BASE_URL` env var pointing to a mock server.
- Tests must be idempotent: each test run starts with a clean database state
  (compose recreates volumes before the test run).
- Maximum test suite duration: 120 seconds.
- Integration tests are **not** run in the normal `pytest` suite of individual services.
  They have their own `pytest` invocation in CI.

---

## Auth Adapter — Implementation Contract

Each backend service must have a module at `src/core/auth_adapter.py` with:

```python
class AuthAdapter:
    """Validates incoming JWT tokens.

    Reads AUTH_MODE from settings:
      local    — validates with local SECRET_KEY (current behaviour)
      keycloak — validates against KEYCLOAK_JWKS_URL (future)
    """

    async def verify(self, token: str) -> dict:
        """Return decoded claims or raise UnauthorizedError."""
        ...
```

The FastAPI dependency that currently calls `verify_access_token()` directly
must be updated to call `AuthAdapter().verify(token)` instead.

No other changes to auth behaviour are permitted. Login endpoints, user CRUD,
and password hashing remain unchanged.

---

## Shared `.env` File

Location: `infra/.env` (gitignored). `infra/.env.example` is committed.
Every variable in `.env.example` must have an inline comment explaining:
- What it controls
- Which services use it
- Whether it is required or has a safe default

Groups (in order, separated by blank lines with a `# ─── Group ───` header):
1. PostgreSQL shared
2. MongoDB shared
3. user-input-manager
4. ticket-manager
5. orchestrator
6. context-distiller
7. agent-tools
8. nginx / DNS
9. auth adapter
10. OpenAI / LLM

---

## Definition of Done

This unification phase is complete when:

1. `docker compose -f infra/docker-compose.yml up --build` starts all five services
   with no errors and all healthchecks pass
2. Both frontend services (user-input-manager, ticket-manager) are accessible via
   nginx at their configured DNS names (or localhost with path prefix for dev)
3. All existing unit and integration tests in each service pass unchanged
4. Integration test scenario A passes
5. Integration test scenario C passes
6. All Python backends have `auth_adapter.py` in place;
   `AUTH_MODE=local` behaviour is identical to pre-migration
7. user-input-manager frontend uses Zustand; no access tokens in localStorage
8. All services use Python 3.12 and the canonical library versions
9. Pre-commit hooks pass on all Python files in the monorepo
10. Vitest is the test runner for both frontends; coverage ≥ 80%
11. `infra/.env.example` is complete and every line is commented
12. `nginx.conf.template` has certbot-ready blocks (commented)
13. `CLAUDE.md` at monorepo root documents service map, ports, and database names

---

## Principles That Must Never Be Violated

- **Services never share a database.** One service, one database.
- **No auth removal in this phase.** Auth adapter only — no Keycloak flows.
- **No access tokens in browser storage.** Memory (Zustand) only.
- **No hardcoded passwords in committed files.**
  All credentials via env vars; `.env` is gitignored.
- **Integration tests use real services, not mocks**
  (except LLM calls, which are always mocked).
- **Never reorganise service internals** beyond what standardisation requires.
  This phase is infrastructure, not refactoring.
- **Nginx template, not nginx config.**
  DNS names must never be hardcoded in `nginx.conf`.
