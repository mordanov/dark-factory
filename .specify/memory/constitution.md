<!--
  Sync Impact Report
  Version change: 1.2.0 → 2.0.0
  Modified principles:
    - Principle II: "Auth Adapter Pattern — Keycloak Preparation" → "Keycloak IAM Migration"
      (MAJOR: previous principle was explicitly scoped to a preparation-only phase and deferred
      the full migration; this amendment enacts that migration — the seam becomes the system)
  Added sections:
    - Principle XVII: Keycloak is the Single Source of Truth for Identity
    - Principle XVIII: JWKS Validation MUST Be Cached — Never Per-Request
    - Principle XIX: Service-to-Service Authentication via Client Credentials
    - Principle XX: Frontend Auth via keycloak-js — Tokens In-Memory Only
    - Principle XXI: Users Table Permanently Removed — Identity via Keycloak Sub
    - Keycloak Deployment entry in Monorepo Structure (new infra/keycloak/, infra/oauth2-proxy/)
    - Definition of Done items 22–35 (Keycloak migration acceptance criteria)
    - Eleven new Non-Negotiable Constraints (Keycloak phase)
  Removed sections:
    - Non-Negotiable Constraint: "Auth MUST NOT be removed in this phase. Auth adapter only —
      no Keycloak flows." — superseded by Keycloak migration principles XVII–XXI
  Templates requiring updates:
    ✅ .specify/memory/constitution.md — fully updated for v2.0.0
    ⚠  .specify/templates/plan-template.md — Constitution Check section references
       Principles I–XII; should be updated to reference I–XXI for new features
    ✅ .specify/templates/spec-template.md — no constitution-specific changes required
    ✅ .specify/templates/tasks-template.md — no constitution-specific changes required
    ✅ .specify/templates/commands/ — directory not present, no action required
  Deferred TODOs: None
  Version bump rationale: MAJOR — Principle II is fundamentally redefined (preparation seam
    → completed Keycloak migration); backward-incompatible governance change because code that
    previously complied with the "no Keycloak flows" constraint in Principle II now violates
    the new mandate. Five new principles added (XVII–XXI).
-->

# Dark Factory Monorepo Constitution

## Core Principles

### I. Services Remain Independently Deployable

Each service MUST be runnable in isolation via its own `docker-compose.yml` (development)
AND as part of the unified `infra/docker-compose.yml` (production). The monorepo provides
shared infrastructure only; it MUST NOT introduce hard coupling at the code level. Services
communicate exclusively via HTTP APIs over the internal Docker network. Shared Python imports
and shared application databases between services are strictly forbidden.

### II. Keycloak IAM Migration

Keycloak is the single source of truth for identity and access management across all
Dark Factory services. The preparation seam introduced in earlier phases is now the
production system. The migration is irreversible.

**What is removed (permanently):**
- `users` table and all associated Alembic migrations (all services)
- `src/core/security.py` — password hashing and local token creation
- `src/api/v1/auth.py` — local login and refresh endpoints
- `JWT_SECRET_KEY` used for user token signing
- `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD` env vars

**What replaces them:**
- Each service's `src/core/auth_adapter.py` becomes `KeycloakValidator`, validating RS256
  tokens from Keycloak's JWKS endpoint
- `AUTH_MODE` env var remains: `keycloak` (production), `local` (tests only with HMAC)
- `UserClaims` dataclass (`sub`, `email`, `preferred_username`, `roles`, `is_admin`)
  replaces the `User` ORM object in all FastAPI dependencies
- `user_id TEXT NOT NULL` columns retain their place; the value is now Keycloak `sub` (UUID
  string) with no FK to a local users table

All services MUST use `AUTH_MODE=keycloak` in production docker-compose. `AUTH_MODE=local`
MUST NEVER appear in `infra/docker-compose.yml` or `infra/docker-compose.override.yml`.

### III. Python 3.12 Everywhere — No Exceptions

All backend services MUST run on Python 3.12. The Dockerfile base image for every
service MUST be `python:3.12-slim`. Any dependency that does not support Python 3.12 MUST
be replaced or removed.

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
react-i18next: "15.1.3"               keycloak-js: "25.x"
```

### VI. Zustand for All Frontend State Management

All frontend application state MUST be managed with Zustand. React Context is permitted
only for theme propagation and i18n providers. Access tokens MUST be stored in memory
only (Zustand store) — never in `localStorage`, `sessionStorage`, or cookies. After the
Keycloak migration, the Zustand auth store wraps `keycloak-js` and exposes `getToken()`,
`initialize()`, and `logout()`. No direct token read from `localStorage` anywhere.

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
and an HTTP→HTTPS redirect block (commented, ready to enable). After the Keycloak migration,
every `/api/` location block MUST include an `auth_request /oauth2/auth` directive validated
by oauth2-proxy. Frontend routes MUST NOT have `auth_request` — keycloak-js handles redirects.

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

**Secret hygiene:** Keycloak client secrets, service tokens, and `SERVICE_JWT` MUST NEVER
appear in agent run logs, in the `raw_output` field, or in any API response. The Dispatcher
MUST redact or exclude these values before persisting or returning run records.

### XIII. Planning Agent — Plan Persistence Before User Exposure

A generated plan MUST be persisted in the `prompt_plans` PostgreSQL table before it is
shown to the user. Plans that exist only in memory or in an LLM API response are not
acceptable. Users MUST be able to close the browser and return to find their plan intact.
The plan status lifecycle (`draft → ready → confirmed → tickets_created`) MUST be
durably tracked in the database so the frontend can always reconstruct the current state
from a GET request alone.

No plan generation endpoint MUST return a plan payload to the client without first
writing it to the database. If the database write fails, the endpoint MUST return an
error and NOT surface the LLM output to the user.

### XIV. Planning Agent — User Confirmation Gate for LLM Output

LLM-generated plan content MUST NEVER be automatically submitted to Ticket Manager.
The user MUST review the plan (`plan_ready` state) and explicitly confirm it
(`POST /sessions/{id}/plan/confirm`) before any ticket creation begins. No background
task, hook, or timer may bypass this confirmation gate.

Between `plan_ready` and `plan_confirmed`, the user MUST be able to edit any node
(title, description, `ticket_type`) and delete any Story or Task. The service MUST
validate the edited plan against the schema before saving. Adding new nodes is
deferred to a future phase and MUST NOT be implemented in v1.

### XV. Planning Agent — Ticket Creation Is All-or-None with Retry

Ticket creation in TM MUST be treated as an atomic operation at the plan level: either
all tickets are created, or the system records how many were created and presents a
recoverable error state (`plan_confirmed` with `created_ticket_ids` populated). Partial
success is NOT a terminal state — the user MUST have a "Retry ticket creation" path.

On retry, already-created tickets (tracked in `prompt_plans.created_ticket_ids`) MUST be
skipped. This makes creation idempotent across retries. The service MUST NEVER create
duplicate tickets by re-submitting IDs already in `created_ticket_ids`.

Dependencies between tasks MUST use TM ticket IDs (not local plan IDs) after creation.
The `local_id → tm_ticket_id` mapping MUST be stored in `prompt_plans.ticket_id_map`
(JSONB) and used when setting `depends_on` in TM.

### XVI. Planning Agent — Agent Config Is Best-Effort, Never Blocking

Agent configuration generation (project-specific overrides for each Dark Factory agent)
MUST NOT block or delay ticket creation. If the LLM call for agent config fails, times
out, or returns invalid JSON:
- The failure MUST be logged.
- `prompt_plans.agent_config` MUST be set to `null`.
- Ticket creation MUST proceed without the agent config.
- The Orchestrator will use base agent prompts without project overrides.

Agent config, when generated successfully, MUST be written to the ContextDistiller
Document Store via `POST /memory/{project_id}/agent-config` after ticket creation
succeeds. `user-input-manager` MUST NEVER write directly to MongoDB — all agent config
storage MUST go through the ContextDistiller HTTP API.

### XVII. Keycloak is the Single Source of Truth for Identity

Keycloak is the only component in Dark Factory authorized to store passwords, issue
tokens, and manage user accounts. No service may maintain a shadow user store, issue
its own JWTs for human users, or accept passwords directly. Every token used by human
users MUST originate from the `dark-factory` Keycloak realm.

**Realm name is fixed:** `dark-factory`. It MUST NEVER be renamed. The realm is
imported automatically on first startup via `--import-realm` and the mount at
`/opt/keycloak/data/import/realm-export.json`. Environment variable substitution
MUST be performed by `infra/keycloak/substitute-env.sh` before `kc.sh` starts.

**Startup order is non-negotiable:** PostgreSQL MUST be healthy before Keycloak starts.
Keycloak MUST be healthy (realm endpoint reachable) before any application service starts.
Services MUST NOT attempt auth operations before Keycloak healthcheck passes.

**Google IdP placeholder:** The `google` identity provider MUST be present in
`realm-export.json` with `"enabled": false`. Enabling it requires only setting
`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env` — no code changes.

### XVIII. JWKS Validation MUST Be Cached — Never Per-Request

Every backend service's `KeycloakValidator` MUST cache the Keycloak JWKS response with
a minimum TTL of 300 seconds. Fetching JWKS on every incoming request is forbidden —
it would make every API endpoint dependent on Keycloak round-trip latency and create
a single point of failure for all request handling.

The cache MUST be invalidated and re-fetched when the TTL expires. Cache invalidation on
every request (TTL=0) is equivalent to no caching and is also forbidden. If the JWKS
fetch fails during a cache refresh, the service MUST continue using the stale cache
and log the failure — it MUST NOT reject all incoming requests due to a transient
Keycloak connectivity issue.

All tokens MUST be validated with RS256 (asymmetric). HS256 validation MUST only be
used when `AUTH_MODE=local` (test environments). `AUTH_MODE=local` MUST NEVER be set
in any production or staging docker-compose file.

### XIX. Service-to-Service Authentication via Client Credentials

All inter-service HTTP calls MUST use Keycloak Client Credentials grant. Static JWTs
(`SERVICE_JWT`) are replaced by dynamically obtained tokens. Each service has its own
Keycloak client with `serviceAccountsEnabled: true` and a `client_secret` in `.env`.

The `KeycloakServiceClient` module MUST:
- Cache the token until 30 seconds before its expiry (not until expiry itself)
- Use `asyncio.Lock` for thread-safe refresh under concurrent requests
- Token lifetime for service accounts MUST be 1 hour per-client override in Keycloak —
  this covers the maximum agent runtime of 600 seconds with margin

Agent Dispatcher MUST call `get_token()` immediately before spawning each agent and
embed the fresh token in the agent context. Tokens MUST NOT be reused across agent
runs if more than 30 seconds remain of the per-client token TTL check window.

### XX. Frontend Auth via keycloak-js — Tokens In-Memory Only

Both frontends (`user-input-manager`, `ticket-manager`) MUST use `keycloak-js` for
authentication. Local login pages and login routes are removed entirely. There is no
`/login` route in either application after this migration — Keycloak handles all
redirects before the React app renders.

App initialization MUST call `keycloak.init({ onLoad: 'login-required', pkceMethod: 'S256' })`.
If the user is not authenticated, Keycloak redirects to the login page before the app
renders a single component.

Token storage rules:
- Tokens MUST be held in the Zustand auth store (in-memory) via `keycloak.token`
- Tokens MUST NEVER be written to `localStorage`, `sessionStorage`, or cookies
- The Axios interceptor MUST call `await keycloak.updateToken(30)` before every request
  to ensure the token is fresh (refreshes silently if expiring within 30 seconds)

All Axios requests to `/api/*` routes MUST include `Authorization: Bearer <token>`.
nginx validates every `/api/*` request via `auth_request` to oauth2-proxy. oauth2-proxy
acts as a Bearer validator only — it does NOT perform login redirects.

### XXI. Users Table Permanently Removed — Identity via Keycloak Sub

The `users` table and all dependent data are permanently removed from every service that
previously maintained local user records. This migration is destructive and irreversible.

Each Alembic migration that removes local user data MUST have the description:
`"DESTRUCTIVE: drops all user data"`. These migrations MUST NOT include a rollback path
(`downgrade()` MUST raise `NotImplementedError`).

After migration:
- `user_id` columns retain `TEXT NOT NULL` type; the stored value is the Keycloak `sub`
  (UUID string). There is no foreign key to any local table.
- Route handlers that previously accepted a `User` ORM object from `get_current_user`
  MUST accept `UserClaims` (sub, email, preferred_username, roles, is_admin) instead.
- No route handler may perform a local database lookup to resolve a user by ID. All
  user identity information comes from JWT claims (already validated by the time the
  handler executes).

## Monorepo Structure & Service Registry

The monorepo layout is fixed and MUST NOT deviate. Services retain their own internal
structure; do not reorganise files inside `services/*/` beyond what standardisation requires.
This is a mono**repo**, not a mono**lith**.

**Monorepo root layout (fixed):**

```
dark-factory/
├── services/
│   ├── user-input-manager/   ← port 8001 | frontend yes | PG: df_user_input      | DNS: UIM_HOST
│   │                            Note: Planning Agent is an EXTENSION of this service,
│   │                            not a separate container. It adds endpoints and a
│   │                            new DB table (prompt_plans) to user-input-manager.
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
│   ├── postgres/init/01_create_databases.sql  (includes keycloak DB)
│   ├── keycloak/
│   │   ├── realm-export.json       ← full realm definition with ${VAR} placeholders
│   │   └── substitute-env.sh       ← envsubst → /opt/keycloak/data/import/
│   └── oauth2-proxy/
│       └── config.cfg              ← Bearer token validator for nginx auth_request
├── integration-tests/
├── .pre-commit-config.yaml
├── pyproject.toml
├── package.json
├── .gitignore
├── CLAUDE.md
└── README.md
```

Internal service-to-service URLs follow the pattern `http://{service-name}:{port}`
(e.g., `http://orchestrator:8003`, `http://keycloak:8080`).

## Infrastructure, Integration Tests & Definition of Done

**PostgreSQL 16** — single instance. Databases created by
`infra/postgres/init/01_create_databases.sql` on first boot. Includes `keycloak` database
for Keycloak persistence. Each service connects with its own dedicated user and password
supplied via env vars. Passwords MUST NOT be hardcoded in committed files. Databases:
`df_user_input`, `df_ticket_manager`, `df_orchestrator`, `df_distiller`, `df_dispatcher`,
`keycloak`.

**Keycloak 25** — single instance (no clustering), port 8080 internal. Backend: PostgreSQL.
Not exposed externally — all access via nginx. Startup sequence: postgres → keycloak →
all application services (via healthcheck dependency). Realm `dark-factory` imported
automatically on first boot.

**MongoDB 7** — single instance. Each service that uses Mongo connects to its own database
by name. No shared collections. No cross-service queries. Current databases:
`df_orchestrator_docs`, `df_distiller_docs`.

**Nginx** — single container as the external entry point for all traffic. Port `80:80` only.
HTTPS (443) is added by the operator post-certbot. Built from `infra/nginx/Dockerfile` using
`envsubst`. Every `/api/` location MUST have `auth_request /oauth2/auth` validated by
oauth2-proxy. Frontend routes have no `auth_request` (keycloak-js handles redirects).

**oauth2-proxy** — Bearer token validator sidecar. Provider: `keycloak-oidc`. Validates
Bearer tokens against Keycloak JWKS; passes `X-Auth-Request-User`, `X-Auth-Request-Email`,
`X-Auth-Request-Groups` headers upstream. Does NOT handle login redirects.

**Integration test rules:**
- Tests run against real services started by `docker-compose.test.yml`. No mocking of
  inter-service HTTP calls.
- LLM calls (OpenAI) are mocked via `OPENAI_BASE_URL` pointing to a mock server.
- Tests MUST be idempotent; each run starts with a clean database state.
- Maximum test suite duration: 120 seconds.
- Integration tests have their own `pytest` invocation in CI, separate from per-service
  unit test suites.

**This project is Done when ALL of the following are true:**

1. `docker compose -f infra/docker-compose.yml up --build` starts all services with
   no errors and all healthchecks pass.
2. Both frontend services are accessible via nginx at their configured DNS names.
3. All existing unit and integration tests in each service pass unchanged.
4. Integration test scenario A (UIM → TM ticket creation) passes.
5. Integration test scenario C (Orchestrator → ContextDistiller → memory readable) passes.
6. All Python backends have `auth_adapter.py` with `KeycloakValidator`; `AUTH_MODE=keycloak`
   validates RS256 tokens; `AUTH_MODE=local` validates HS256 for tests.
7. Both frontend services use Zustand + keycloak-js; no access tokens in localStorage.
8. All services use Python 3.12 and the canonical library versions.
9. Pre-commit hooks pass on all Python files in the monorepo.
10. Vitest is the test runner for both frontends; coverage ≥ 80%.
11. `infra/.env.example` is complete and every line is commented.
12. `nginx.conf.template` has certbot-ready blocks (commented) and `auth_request` for
    all `/api/` locations.
13. `CLAUDE.md` at monorepo root documents service map, ports, and database names.
14. Agent Dispatcher detects a ticket with `assigned_agent` set within `POLL_INTERVAL_SECONDS`
    and starts a run; the run is recorded in `agent_runs` with correct status transitions.
15. In `claude_code` mode: subprocess is spawned with the correct system prompt and context;
    exit is detected; result is parsed from the `[RESULT]` block.
16. In `api` mode: the LLM API is called with system prompt and context; result is parsed.
17. After any agent run completes: the TM ticket has a new comment and an Orchestrator
    evaluation job has been triggered. No FSM state is modified by the Dispatcher directly.
18. Planning Agent: session status flow works end-to-end (`approved → planning → plan_ready
    → plan_confirmed → tickets_created`).
19. Planning Agent: generated plan is persisted in `prompt_plans` before being shown to the
    user; user can close the browser and return to the plan intact.
20. Planning Agent: tickets are created in TM with correct hierarchy (Epic → Stories →
    Tasks with `depends_on` using TM IDs); partial creation is retryable without duplicates.
21. Planning Agent: agent config is written to ContextDistiller Document Store after
    successful ticket creation; config failure does not block ticket creation.
22. Keycloak: `docker compose up` starts Keycloak and waits for healthy before services.
23. Keycloak: visiting UIM frontend redirects to Keycloak login if not authenticated.
24. Keycloak: after login, user lands in Prompt Studio with correct name/email from JWT claims.
25. Keycloak: after login in either app, the other app is accessible without re-login (SSO).
26. Keycloak: logout from either app triggers Single Logout; both apps require re-login.
27. Keycloak: admin sees "Keycloak Admin Console" link in sidebar; regular user does not.
28. Keycloak: all `/api/*` requests are validated via oauth2-proxy `auth_request`; unvalidated
    requests receive 401 JSON (not an HTML redirect).
29. Keycloak: service-to-service calls use Client Credentials tokens from `KeycloakServiceClient`.
30. Keycloak: Agent Dispatcher embeds a fresh Keycloak token in agent context before each spawn.
31. Keycloak: all existing tests pass with `AUTH_MODE=local` and test HMAC secret.
32. Keycloak: realm import is fully automatic on first `docker compose up`; no manual steps.
33. Keycloak: Google IdP placeholder is in realm JSON with `enabled: false`; no errors on startup.
34. Keycloak: no `JWT_SECRET_KEY` remains in any service configuration for user token signing.
35. Keycloak: `users` table removal migrations are applied; all `user_id` columns hold Keycloak
    `sub` strings; no FK constraints to a local users table remain.

## Governance

This constitution supersedes all other project documentation and verbal agreements.
Any practice that conflicts with a principle stated here MUST yield to the constitution.

**Amendment procedure:** Amendments require (1) a written rationale, (2) a description
of any migration plan for affected services, and (3) a version increment per the policy
below. Amendments must be committed to `development/documentation/` and propagated to
`.specify/memory/constitution.md` via `/speckit-constitution`.

**Versioning policy:**
- MAJOR: Backward-incompatible changes — removing or fundamentally redefining a principle
  (e.g., Principle II rewritten from preparation to migration; permitting cross-service DB access).
- MINOR: Adding a new principle, section, or materially expanding guidance.
- PATCH: Clarifications, wording fixes, non-semantic refinements.

**Compliance:** All PRs and code reviews MUST verify adherence to Core Principles I–XXI.
Complexity introductions MUST be justified. The monorepo `CLAUDE.md` serves as the runtime
development guide and MUST remain in sync with this constitution.

**Non-Negotiable Constraints — MUST NEVER be violated:**
- Services MUST never share a database. One service, one database.
- Access tokens MUST NOT be stored in browser storage. Zustand in-memory only.
- Passwords and secrets MUST NOT be hardcoded in committed files. All credentials via
  env vars; `infra/.env` is gitignored.
- Integration tests MUST use real services, not mocks (except LLM calls).
- Service internals MUST NOT be reorganised beyond what standardisation requires.
- Nginx MUST use `nginx.conf.template` with `envsubst`. DNS names MUST NOT be hardcoded.
- The Agent Dispatcher MUST NEVER modify FSM state directly. Only the Orchestrator does.
- A ticket MUST NEVER have two simultaneous agent runs. Check before every dispatch.
- Agent prompts MUST NEVER be cached. Read from disk on each run without exception.
- Keycloak client secrets and service tokens MUST NEVER appear in logs or API responses.
- A plan MUST be persisted to the database before it is shown to the user. No ephemeral plans.
- LLM output MUST NEVER be sent to Ticket Manager without explicit user confirmation.
- Ticket creation is all-or-none with retry. NEVER leave orphaned tickets without a recovery path.
- Agent config failure MUST NEVER block ticket creation. Best-effort only.
- `user-input-manager` MUST NEVER write directly to MongoDB. All agent config via ContextDistiller API.
- No service stores passwords. Keycloak is the only password store. No exceptions.
- No service issues tokens for human users. All user tokens originate from Keycloak.
- `AUTH_MODE=local` MUST NEVER be set in production or staging docker-compose files.
- JWKS MUST be cached with a minimum 300s TTL. Fetching JWKS per-request is forbidden.
- Service account tokens MUST use Client Credentials grant with a 1-hour TTL override.
- keycloak-js tokens MUST be kept in memory only. Never written to localStorage or cookies.
- The `users` table removal is irreversible. `downgrade()` in these migrations MUST raise
  `NotImplementedError`. No rollback path for destructive user-data migrations.
- The Keycloak realm name `dark-factory` is fixed and MUST NEVER be renamed.

**Version**: 2.0.0 | **Ratified**: 2026-06-22 | **Last Amended**: 2026-06-24
