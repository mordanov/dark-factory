<!--
  Sync Impact Report
  Version change: 1.0.0 → 1.1.0
  Modified principles: None — existing principles I–X unchanged
  Added sections:
    - Principle XI: Agent Dispatcher — FSM Sovereignty and Run Isolation
    - Principle XII: Agent Dispatcher — Operational Safety Contracts
    - agent-dispatcher entry in Service Registry and Monorepo Structure
    - df_dispatcher database entry in Infrastructure section
    - Agent Dispatcher items in Definition of Done (items 14–17)
    - Four new Non-Negotiable Constraints under Governance
  Removed sections: None
  Templates requiring updates:
    ✅ .specify/memory/constitution.md — fully updated for v1.1.0
    ✅ .specify/templates/plan-template.md — Constitution Check gates remain valid; no structural change required
    ✅ .specify/templates/spec-template.md — no constitution-specific changes required
    ✅ .specify/templates/tasks-template.md — no constitution-specific changes required
    ✅ .specify/templates/commands/ — directory not present, no action required
  Deferred TODOs: None
  Version bump rationale: MINOR — two new principles added (XI, XII) and the
    agent-dispatcher service registered with its database and DoD criteria.
    Existing principles I–X are fully preserved and unmodified.
-->

# Dark Factory Monorepo Constitution

## Core Principles

### I. Services Remain Independently Deployable

Each service MUST be runnable in isolation via its own `docker-compose.yml` (development)
AND as part of the unified `infra/docker-compose.yml` (production). The monorepo provides
shared infrastructure only; it MUST NOT introduce hard coupling at the code level. Services
communicate exclusively via HTTP APIs over the internal Docker network. Shared Python imports
and shared application databases between services are strictly forbidden.

### II. Auth Adapter Pattern — Keycloak Preparation

Authentication MUST NOT be removed in this phase. All JWT validation logic MUST be extracted
into a single `auth_adapter.py` module per service (at `src/core/auth_adapter.py`), replacing
any inline `verify_token`/`decode_token` calls. The adapter MUST support two modes via the
`AUTH_MODE` env var: `local` (validates JWT with local `SECRET_KEY`) and `keycloak`
(validates against `KEYCLOAK_JWKS_URL` JWKS endpoint). No other auth changes are permitted:
user tables, login endpoints, and password hashing remain untouched. The Keycloak migration
is a separate future phase; this phase only prepares the seam.

### III. Python 3.12 Everywhere — No Exceptions

All backend services MUST run on Python 3.12. The Dockerfile base image for every
service MUST be `python:3.12-slim`. Any dependency that does not support Python 3.12 MUST
be replaced or removed. `ticket-manager` currently runs on 3.11 and must be upgraded as
part of this phase.

### IV. Shared Python Library Versions Pinned in Root `pyproject.toml`

A root-level `pyproject.toml` defines the canonical version for every shared Python library
under `[tool.versions]`. Each service's `requirements.txt` MUST use these exact versions.
No service may pin a different version of a shared library without a constitution amendment
documenting the reason.

Canonical versions:
```
fastapi = "0.115.5"        uvicorn = "0.32.1"
sqlalchemy = "2.0.36"      asyncpg = "0.30.0"
alembic = "1.14.0"         pydantic = "2.10.3"
pydantic-settings = "2.6.1" python-jose = "3.3.0"
passlib = "1.7.4"          httpx = "0.28.0"
openai = "1.57.0"          structlog = "24.4.0"
pytest = "8.3.4"           pytest-asyncio = "0.24.0"
pytest-cov = "6.0.0"       ruff = "0.8.3"
```

### V. Shared Frontend Library Versions Pinned in Root `package.json`

A root-level `package.json` (workspaces are NOT used — reference only) documents canonical
frontend versions. Services with a frontend (`user-input-manager`, `ticket-manager`) MUST
use these exact versions. No deviation without a constitution amendment.

Canonical versions:
```
react: "18.3.1"                       react-dom: "18.3.1"
react-router-dom: "6.28.0"            typescript: "5.7.2"
vite: "6.0.3"                         vitest: "2.1.8"
@testing-library/react: "16.1.0"      @testing-library/jest-dom: "6.6.3"
@testing-library/user-event: "14.5.2" zustand: "5.0.2"
axios: "1.7.9"                        i18next: "24.0.5"
react-i18next: "15.1.3"
```

### VI. Zustand for All Frontend State Management

All frontend application state MUST be managed with Zustand. React Context is permitted
only for theme propagation and i18n providers. `user-input-manager` MUST be migrated from
React Context API to Zustand as part of this phase. Access tokens MUST be stored in memory
only (Zustand store) — never in `localStorage` or `sessionStorage`. All
`localStorage.setItem('access_token', ...)` calls in `user-input-manager` MUST be removed.

### VII. Vitest for All Frontend Tests

Both `ticket-manager` and `user-input-manager` MUST use Vitest as the test runner. Any
existing Jest configuration MUST be removed. Coverage threshold MUST be 80% lines/functions,
enforced in `vite.config.ts`.

### VIII. ruff for All Python Linting and Formatting

All backend services MUST have `.pre-commit-config.yaml` at their service root using
ruff for both linting and formatting. A shared root-level `.pre-commit-config.yaml` also
applies to all Python files in the repo. Pre-commit hooks (pinned to `ruff==0.8.3`):
`ruff` (lint with `--fix`) and `ruff-format` (format, replaces black). No other Python
linters are added in this phase (no mypy, no bandit).

### IX. Nginx is DNS-Name Aware from Day One

Nginx MUST be configured with one `server` block per frontend service. DNS names MUST be
controlled by environment variables substituted via `envsubst` at container startup — they
MUST NOT be hardcoded in `nginx.conf`. Every `server` block MUST include:
`location /.well-known/acme-challenge/` for certbot, an SSL stanza (commented, certbot-ready),
and an HTTP→HTTPS redirect block (commented, ready to enable). This ensures certbot can be
added without modifying `nginx.conf`.

### X. No Cross-Service Database Access

Each service owns exactly one PostgreSQL database and one MongoDB database (where applicable).
No service may query another service's database directly. Cross-service data access MUST
always be via HTTP API. No shared collections. No cross-service MongoDB queries.

### XI. Agent Dispatcher — FSM Sovereignty and Run Isolation

The Agent Dispatcher MUST NEVER modify FSM state directly. All FSM transitions remain the
exclusive responsibility of the Orchestrator service. The Dispatcher executes what the
Orchestrator decided and reports outcomes only: it POSTs comments to TM and triggers a new
Orchestrator evaluation via `POST /api/v1/orchestrator/jobs/trigger`.

A given ticket MUST NEVER have two simultaneous agent runs. Before starting any run the
Dispatcher MUST check `agent_runs` for an existing `running` row with the same `ticket_id`;
if found the ticket MUST be skipped in that poll cycle.

The polling loop MUST NOT be blocked by a slow agent run. Every run MUST be dispatched as
an async task governed by `asyncio.Semaphore(WORKER_MAX_CONCURRENT_RUNS)`. The polling
interval continues independently of running tasks.

### XII. Agent Dispatcher — Operational Safety Contracts

**Graceful degradation on missing output:** If an agent's `[RESULT]` block is absent or
contains invalid JSON, the Dispatcher MUST NOT fail the run as an error. It MUST treat
`status` as `needs_review` and set `tm_comment` to the raw stdout (truncated to 2000 chars).
A run MUST only be marked `failed` on explicit error conditions (non-zero exit, timeout,
subprocess failure), never on parse failures alone.

**No prompt caching:** Agent system prompts MUST be read from disk on every run. Caching
prompt files is forbidden so that prompt updates take effect immediately without restarting
the service.

**Secret hygiene:** `SERVICE_JWT` and `TICKET_MANAGER_SERVICE_PASSWORD` MUST NEVER appear
in agent run logs, in the `raw_output` field, or in any API response. The Dispatcher MUST
redact or exclude these values before persisting or returning run records.

## Monorepo Structure & Service Registry

The monorepo layout is fixed and MUST NOT deviate. Services retain their own internal
structure; do not reorganise files inside `services/*/` beyond what standardisation requires.
This is a mono**repo**, not a mono**lith**.

**Monorepo root layout (fixed):**

```
dark-factory/
├── services/
│   ├── user-input-manager/   ← port 8001 | frontend yes | PG: df_user_input      | DNS: UIM_HOST
│   ├── ticket-manager/       ← port 8002 | frontend yes | PG: df_ticket_manager  | DNS: TM_HOST
│   ├── orchestrator/         ← port 8003 | frontend no  | PG: df_orchestrator    | Mongo: df_orchestrator_docs
│   ├── context-distiller/    ← port 8004 | frontend no  | PG: df_distiller       | Mongo: df_distiller_docs
│   ├── agent-tools/          ← port 8005 | frontend no  | no DB
│   └── agent-dispatcher/     ← port 8006 | frontend no  | PG: df_dispatcher
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.override.yml
│   ├── .env  (gitignored)
│   ├── .env.example  (committed, every line commented)
│   ├── nginx/
│   │   ├── Dockerfile
│   │   ├── nginx.conf.template
│   │   └── snippets/{ssl.conf,proxy.conf}
│   └── postgres/init/01_create_databases.sql
├── integration-tests/
│   ├── docker-compose.test.yml
│   ├── conftest.py
│   ├── tests/{test_scenario_a.py,test_scenario_c.py}
│   └── requirements.txt
├── .pre-commit-config.yaml
├── pyproject.toml
├── package.json
├── .gitignore
├── CLAUDE.md
└── README.md
```

Internal service-to-service URLs follow the pattern `http://{service-name}:{port}`
(e.g., `http://orchestrator:8003`, `http://agent-dispatcher:8006`).

## Infrastructure, Integration Tests & Definition of Done

**PostgreSQL 16** — single instance (`postgres` compose service). Databases created by
`infra/postgres/init/01_create_databases.sql` on first boot. Each service connects with
its own dedicated user and password supplied via env vars. Passwords MUST NOT be hardcoded
in committed files. Current databases: `df_user_input`, `df_ticket_manager`,
`df_orchestrator`, `df_distiller`, `df_dispatcher`.

**MongoDB 7** — single instance (`mongo` compose service). Each service that uses Mongo
connects to its own database by name. No shared collections. No cross-service queries.
Current databases: `df_orchestrator_docs`, `df_distiller_docs`.

**Nginx** — single container as the external entry point for all traffic. Port `80:80` only.
HTTPS (443) is added by the operator post-certbot. Built from `infra/nginx/Dockerfile` using
`envsubst` to render the template at startup.

**Integration test rules:**
- Tests run against real services started by `docker-compose.test.yml`. No mocking of
  inter-service HTTP calls.
- LLM calls (OpenAI) are mocked via `OPENAI_BASE_URL` pointing to a mock server (WireMock
  or `respx` ASGI intercept).
- Tests MUST be idempotent; each run starts with a clean database state (compose recreates
  volumes before the test run).
- Maximum test suite duration: 120 seconds.
- Integration tests have their own `pytest` invocation in CI, separate from per-service
  unit test suites.

**This unification phase is Done when ALL of the following are true:**

1. `docker compose -f infra/docker-compose.yml up --build` starts all services with
   no errors and all healthchecks pass.
2. Both frontend services are accessible via nginx at their configured DNS names.
3. All existing unit and integration tests in each service pass unchanged.
4. Integration test scenario A (UIM → TM ticket creation) passes.
5. Integration test scenario C (Orchestrator → ContextDistiller → memory readable) passes.
6. All Python backends have `auth_adapter.py` in place; `AUTH_MODE=local` behaviour is
   identical to pre-migration.
7. `user-input-manager` frontend uses Zustand; no access tokens in localStorage.
8. All services use Python 3.12 and the canonical library versions.
9. Pre-commit hooks pass on all Python files in the monorepo.
10. Vitest is the test runner for both frontends; coverage ≥ 80%.
11. `infra/.env.example` is complete and every line is commented.
12. `nginx.conf.template` has certbot-ready blocks (commented).
13. `CLAUDE.md` at monorepo root documents service map, ports, and database names.
14. Agent Dispatcher detects a ticket with `assigned_agent` set within `POLL_INTERVAL_SECONDS`
    and starts a run; the run is recorded in `agent_runs` with correct status transitions.
15. In `claude_code` mode: subprocess is spawned with the correct system prompt and context;
    exit is detected; result is parsed from the `[RESULT]` block.
16. In `api` mode: the LLM API is called with system prompt and context; result is parsed.
17. After any agent run completes: the TM ticket has a new comment and an Orchestrator
    evaluation job has been triggered. No FSM state is modified by the Dispatcher directly.

## Governance

This constitution supersedes all other project documentation and verbal agreements.
Any practice that conflicts with a principle stated here MUST yield to the constitution.

**Amendment procedure:** Amendments require (1) a written rationale, (2) a description
of any migration plan for affected services, and (3) a version increment per the policy
below. Amendments must be committed to `development/documentation/monorepo-constitution.md`
and propagated to `.specify/memory/constitution.md` via `/speckit-constitution`.

**Versioning policy:**
- MAJOR: Backward-incompatible changes — removing or fundamentally redefining a principle
  (e.g., permitting cross-service DB access).
- MINOR: Adding a new principle, section, or materially expanding guidance.
- PATCH: Clarifications, wording fixes, non-semantic refinements.

**Compliance:** All PRs and code reviews MUST verify adherence to Core Principles I–XII.
Complexity introductions MUST be justified. The monorepo `CLAUDE.md` serves as the runtime
development guide and MUST remain in sync with this constitution.

**Non-Negotiable Constraints — MUST NEVER be violated:**
- Services MUST never share a database. One service, one database.
- Auth MUST NOT be removed in this phase. Auth adapter only — no Keycloak flows.
- Access tokens MUST NOT be stored in browser storage. Zustand in-memory only.
- Passwords and secrets MUST NOT be hardcoded in committed files. All credentials via
  env vars; `infra/.env` is gitignored.
- Integration tests MUST use real services, not mocks (except LLM calls).
- Service internals MUST NOT be reorganised beyond what standardisation requires.
- Nginx MUST use `nginx.conf.template` with `envsubst`. DNS names MUST NOT be hardcoded.
- The Agent Dispatcher MUST NEVER modify FSM state directly. Only the Orchestrator does.
- A ticket MUST NEVER have two simultaneous agent runs. Check before every dispatch.
- Agent prompts MUST NEVER be cached. Read from disk on each run without exception.
- `SERVICE_JWT` and service passwords MUST NEVER appear in logs or API responses.

**Version**: 1.1.0 | **Ratified**: 2026-06-22 | **Last Amended**: 2026-06-22