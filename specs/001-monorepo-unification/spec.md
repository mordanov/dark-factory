# Feature Specification: Dark Factory Monorepo Unification

**Feature Branch**: `001-monorepo-unification`
**Created**: 2026-06-22
**Status**: Draft

## Clarifications

### Session 2026-06-22

- Q: How are integration test users provisioned (login fixtures need valid credentials)? → A: SQL seed script creates test users in each DB before the test suite runs; no API calls during conftest setup.
- Q: How is the auth adapter and health endpoint implemented for agent-tools (MCP server, not FastAPI)? → A: Add a minimal FastAPI app alongside the MCP transport exposing `/health` and hosting the auth adapter; compose healthcheck targets the FastAPI port.
- Q: How are frontend static files served by nginx (bind-mount vs multi-stage build)? → A: Multi-stage Dockerfile per frontend service: Node stage builds `dist/`, nginx stage copies it in; compose is fully self-contained with no host volume dependencies.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Platform Engineer Starts the Full Stack with One Command (Priority: P1)

A platform engineer clones the monorepo, copies `.env.example` to `.env`, fills in credentials,
and runs `docker compose -f infra/docker-compose.yml up --build`. All five services, both
databases, and the nginx reverse proxy start successfully. Healthchecks pass. The engineer
opens a browser and reaches both frontend applications through nginx at their configured
DNS names. No manual service-by-service startup is needed.

**Why this priority**: This is the primary goal of the unification. Every other story
supports or validates this outcome. Without it, the monorepo has no operational value.

**Independent Test**: Run `docker compose -f infra/docker-compose.yml up --build` on a
clean machine with only `.env` populated. All healthchecks reach healthy state within 60
seconds; both frontends respond at their configured hostnames.

**Acceptance Scenarios**:

1. **Given** a freshly cloned repository and a populated `.env`, **When** the operator
   runs `docker compose -f infra/docker-compose.yml up --build`, **Then** all five services,
   postgres, mongo, and nginx start without errors and all container healthchecks report
   healthy within 60 seconds.

2. **Given** all services are running, **When** the operator navigates to the configured
   `UIM_HOST` DNS name in a browser, **Then** the Prompt Studio frontend is served by nginx
   and fully functional.

3. **Given** all services are running, **When** the operator navigates to the configured
   `TM_HOST` DNS name in a browser, **Then** the Ticket Manager frontend is served by nginx
   and fully functional.

4. **Given** the unified compose is running, **When** the operator runs
   `docker compose -f services/user-input-manager/docker-compose.yml up --build`,
   **Then** user-input-manager starts in isolation without errors.

---

### User Story 2 — Developer Performs Auth Without Breaking Existing Behaviour (Priority: P2)

A developer uses any existing login endpoint or protected route in any of the five services.
All behaviour is identical to before the monorepo migration: tokens are issued, verified,
and rejected the same way. The developer can also set `AUTH_MODE=keycloak` to confirm the
adapter is in place (it raises a clear NotImplementedError, not a crash or silent failure).

**Why this priority**: Auth correctness is a non-negotiable constraint in the constitution.
Any regression here breaks all user-facing functionality.

**Independent Test**: Run each backend service in isolation with `AUTH_MODE=local`. Perform
login, access a protected route, and verify a tampered token is rejected. Results must be
identical to the pre-migration baseline.

**Acceptance Scenarios**:

1. **Given** a backend service with `AUTH_MODE=local`, **When** a client submits valid
   credentials to the login endpoint, **Then** a JWT is returned with the same structure
   and claims as before migration.

2. **Given** a backend service with `AUTH_MODE=local`, **When** a client sends a request
   with a valid JWT to a protected route, **Then** the request succeeds with the same
   response as before migration.

3. **Given** a backend service with `AUTH_MODE=local`, **When** a client sends a tampered
   or expired JWT, **Then** a 401 Unauthorized response is returned.

4. **Given** a backend service with `AUTH_MODE=keycloak`, **When** a client sends any
   authenticated request, **Then** the service returns a 501 Not Implemented response with
   a message indicating Keycloak validation is not yet configured.

---

### User Story 3 — Frontend Engineer Uses Zustand Auth State in Prompt Studio (Priority: P3)

A frontend engineer working on user-input-manager imports auth state from the Zustand store
instead of React Context. Access tokens are held in memory; no token appears in localStorage
or sessionStorage. All existing UI behaviour (protected routes, logout, token refresh)
works exactly as before. The migration is invisible to end users.

**Why this priority**: Required by constitution Principle VI. Enables consistent state
management across both frontend services and eliminates browser-storage token exposure.

**Independent Test**: Open Prompt Studio in a browser, log in, and inspect `localStorage`
and `sessionStorage` — no access token should be present. Verify protected routes still
require authentication after a page refresh (session restored from refresh token only).

**Acceptance Scenarios**:

1. **Given** the user-input-manager frontend is running, **When** a user logs in,
   **Then** the access token is not written to `localStorage` or `sessionStorage`.

2. **Given** a logged-in user, **When** the user navigates to a protected route,
   **Then** the route renders correctly without requesting a new login.

3. **Given** a user who was logged in before a page refresh, **When** the page refreshes,
   **Then** the session is restored using the refresh token (if still valid) without
   prompting for login again.

4. **Given** a logged-in user, **When** the user logs out, **Then** the Zustand auth
   store is cleared and the user is redirected to the login page.

---

### User Story 4 — QA Engineer Runs Integration Tests Against Real Services (Priority: P4)

A QA engineer runs the integration test suite (`docker compose -f
integration-tests/docker-compose.test.yml up --build && pytest integration-tests/`).
Both scenario A (UIM → TM ticket creation) and scenario C (Orchestrator → ContextDistiller
→ memory) pass. LLM calls are intercepted by a mock server; no real OpenAI API calls are
made. The entire suite finishes within 120 seconds.

**Why this priority**: Validates the critical inter-service flows that cannot be exercised
by per-service unit tests. Confirms the platform functions end-to-end.

**Independent Test**: Run the integration test suite on a clean environment. Both scenarios
pass. Verify no real OpenAI calls by running with an invalid real API key — suite still passes.

**Acceptance Scenarios**:

1. **Given** all services are running via `docker-compose.test.yml`, **When** the QA engineer
   runs `pytest integration-tests/tests/test_scenario_a.py`, **Then** the test creates a
   ticket in Ticket Manager via Prompt Studio and the ticket has tag "needs-estimation".

2. **Given** all services are running via `docker-compose.test.yml`, **When** the QA engineer
   runs `pytest integration-tests/tests/test_scenario_c.py`, **Then** the test triggers an
   orchestrator job, waits for completion, and asserts project memory is readable with
   required YAML keys.

3. **Given** the integration test suite, **When** the suite is run, **Then** it completes
   in under 120 seconds.

4. **Given** the integration test suite, **When** the suite is run, **Then** no real LLM
   API calls are made (all captured by the mock server).

---

### User Story 5 — Developer Lints All Python Code with One Pre-Commit Invocation (Priority: P5)

A developer runs `pre-commit run --all-files` from the monorepo root. All Python files
across all five service directories are checked and auto-formatted by ruff. No other linters
run. Pre-commit hooks also exist at each service root for service-level development.

**Why this priority**: Enforces code style uniformity across the monorepo before any code
is committed, preventing style drift between services.

**Independent Test**: Introduce a deliberate style violation in a Python file inside any
service directory. Run `pre-commit run --all-files` from the repo root. The violation is
detected and auto-fixed.

**Acceptance Scenarios**:

1. **Given** a Python file with a style violation anywhere in `services/`, **When** the
   developer runs `pre-commit run --all-files` from the monorepo root, **Then** the
   violation is detected and the file is auto-fixed by ruff.

2. **Given** a clean codebase, **When** the developer runs `pre-commit run --all-files`,
   **Then** all hooks pass with no errors.

---

### Edge Cases

- What happens when `AUTH_MODE` is set to an unrecognised value (e.g., `AUTH_MODE=ldap`)?
  The adapter MUST raise a configuration error at startup, not silently fall through to
  local validation.
- What happens when a service's `requirements.txt` pins a library version that differs
  from the canonical version? The constitution mandates an amendment; the spec assumes this
  is caught in code review and CI.
- What happens when `docker compose up` is run without a `.env` file? Services MUST fail
  fast with a clear error message (not start silently with empty credentials).
- What happens when the integration test suite exceeds 120 seconds? The CI job times out
  and fails; the test suite itself does not enforce the limit programmatically.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single `infra/docker-compose.yml` that starts all
  five services, PostgreSQL 16, MongoDB 7, and nginx with one command.
- **FR-002**: The system MUST provide an `infra/docker-compose.override.yml` that exposes
  individual service ports (8001–8005) for local development.
- **FR-003**: Each service MUST be startable in isolation via its own `docker-compose.yml`
  without the unified compose.
- **FR-004**: The system MUST provide `infra/postgres/init/01_create_databases.sql` that
  creates all four PostgreSQL databases and their dedicated users on first boot.
- **FR-005**: The nginx configuration MUST be template-based (`nginx.conf.template`) with
  DNS names injected via environment variables at container startup.
- **FR-005a**: Each frontend service (`user-input-manager`, `ticket-manager`) MUST use a
  multi-stage Dockerfile: a Node build stage produces `dist/`; an nginx stage copies `dist/`
  in. The unified compose is fully self-contained — no host bind-mounts for frontend assets.
- **FR-006**: Each nginx server block MUST include a `/.well-known/acme-challenge/` location
  and commented-out SSL and HTTPS-redirect stanzas ready for certbot.
- **FR-007**: Every Python backend service MUST have an `auth_adapter.py` module that
  supports `AUTH_MODE=local` (unchanged behaviour) and `AUTH_MODE=keycloak` (stub).
  For `agent-tools` (MCP server), a minimal FastAPI app MUST be added alongside the MCP
  transport to host the auth adapter and expose `GET /health`; the compose healthcheck
  targets this FastAPI port.
- **FR-008**: The `user-input-manager` frontend MUST store access tokens in the Zustand
  store only — not in `localStorage` or `sessionStorage`.
- **FR-009**: Both frontend services MUST use Vitest as the test runner with 80% line and
  function coverage enforced in `vite.config.ts`.
- **FR-010**: All Python backends MUST run on Python 3.12 with the canonical library
  versions from `pyproject.toml`.
- **FR-011**: A root-level `.pre-commit-config.yaml` MUST run ruff lint and ruff-format
  across all Python files in the repository.
- **FR-012**: The `infra/.env.example` MUST include every required environment variable
  with an inline comment explaining its purpose, which services use it, and its default.
- **FR-013**: The integration test suite MUST include Scenario A (UIM → TM ticket creation)
  and Scenario C (Orchestrator → ContextDistiller → memory readable).
- **FR-014**: Integration tests MUST use real running services; only LLM calls are mocked
  via `OPENAI_BASE_URL` pointing to a stub server.
- **FR-016**: A SQL seed script MUST create test users in each required service database
  before the integration test suite runs; `conftest.py` MUST NOT call registration endpoints
  to provision test users.
- **FR-015**: The monorepo root MUST contain a `CLAUDE.md` documenting the service map,
  ports, database names, and sibling project paths.

### Key Entities

- **Service**: One of the five Dark Factory applications (`user-input-manager`,
  `ticket-manager`, `orchestrator`, `context-distiller`, `agent-tools`). Each has its own
  codebase, database(s), and deployment identity within the monorepo.
- **Auth Adapter**: A per-service module that encapsulates all JWT validation logic behind
  a single `verify()` interface, switchable between local and Keycloak modes via env var.
- **Unified Compose**: The `infra/docker-compose.yml` that defines the full platform
  topology: all services, shared databases, and nginx.
- **Integration Test Scenario**: An end-to-end test that exercises a cross-service user
  flow using real HTTP calls against running containers.
- **Canonical Versions**: The pinned dependency versions defined in the root `pyproject.toml`
  and `package.json` that all services must use.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The entire Dark Factory platform starts from a single command in under 60
  seconds on a machine with pre-pulled images, with all five service healthchecks passing.
- **SC-002**: All existing per-service unit and integration tests pass unchanged after the
  monorepo migration — zero regressions.
- **SC-003**: Both integration test scenarios (A and C) pass on a clean environment with
  no real LLM API credentials required.
- **SC-004**: The full integration test suite completes in under 120 seconds.
- **SC-005**: `pre-commit run --all-files` passes with no errors on the entire monorepo
  Python codebase.
- **SC-006**: No access token appears in `localStorage` or `sessionStorage` at any point
  during a Prompt Studio login session.
- **SC-007**: Frontend test coverage for both `user-input-manager` and `ticket-manager`
  meets or exceeds 80% lines and functions.
- **SC-008**: `AUTH_MODE=local` authentication behaviour is byte-for-byte identical to
  pre-migration behaviour across all five backend services.

## Assumptions

- The five service directories (`user-input-manager`, `ticket-manager`, `orchestrator`,
  `context-distiller`, `agent-tools`) already exist in the repository under `services/`.
- `context-distiller` and `agent-tools` are scaffolded but not yet fully implemented;
  the monorepo only needs to run whatever exists, not complete them.
- The `infra/.env` file is operator-supplied and gitignored; only `.env.example` is
  committed.
- SSL/TLS certificate provisioning (certbot) is out of scope; nginx is certbot-ready but
  HTTP-only at delivery.
- Keycloak integration is out of scope; the auth adapter delivers a stub for
  `AUTH_MODE=keycloak` that raises a clear not-implemented error.
- Adding new features to any existing service is out of scope; this is infrastructure and
  standardisation only.
- LLM mock server for integration tests uses `OPENAI_BASE_URL` env var override; no
  WireMock licence or external service is required (a minimal FastAPI stub is acceptable).
- The `ticket-manager` Python 3.11 → 3.12 upgrade does not require dependency replacements
  beyond version pinning to the canonical versions in `pyproject.toml`.
- Integration test users are provisioned via a SQL seed script executed before the test
  suite runs, not via API calls during `conftest.py` setup.
- All tasks are implemented via the multi-agent team launched by `development/run-agents.sh`
  (10-agent brainstorm team: project-administrator, product-manager, software-architect,
  security-architect, frontend, designer, backend, devops, code-reviewer, autotester)
  rather than via `/speckit-implement`.
