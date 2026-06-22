# Implementation Plan: Dark Factory Monorepo Unification

**Branch**: `001-monorepo-unification` | **Date**: 2026-06-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/001-monorepo-unification/spec.md`

## Summary

Unify five independently developed Dark Factory services into a single monorepo with
centralised infrastructure. The deliverable is one `docker compose up` command that starts
the entire platform. Work is grouped into six parallel streams: (1) monorepo scaffold,
(2) infra (compose, nginx, postgres init), (3) auth adapter across all backends,
(4) user-input-manager Zustand migration, (5) frontend test runner standardisation,
and (6) integration tests. No service internal logic changes beyond what standardisation
requires; this is infrastructure and seam-preparation work only.

## Technical Context

**Languages/Versions**:
- Backend: Python 3.12 (all services — ticket-manager must be upgraded from 3.11)
- Frontend: TypeScript 5.x (user-input-manager, ticket-manager)

**Primary Dependencies**:
- Backend: FastAPI 0.115.5, SQLAlchemy 2.0.36, asyncpg 0.30.0, pydantic 2.10.3,
  python-jose 3.3.0, structlog 24.4.0, ruff 0.8.3 (all canonical versions from constitution)
- Frontend: React 18.3.1, Vite 6.0.3, Vitest 2.1.8, Zustand 5.0.2 (canonical versions)
- Infrastructure: Docker Compose v2, PostgreSQL 16, MongoDB 7, Nginx (envsubst-capable)

**Storage**:
- PostgreSQL 16 (single instance; databases: df_user_input, df_ticket_manager,
  df_orchestrator, df_distiller)
- MongoDB 7 (single instance; databases per service: df_orchestrator_docs, df_distiller_docs)

**Testing**:
- Backend: pytest 8.3.4 + pytest-asyncio 0.24.0 (per-service unit tests)
- Frontend: Vitest 2.1.8 (coverage ≥ 80% lines/functions)
- Integration: pytest 8.3.4 + httpx 0.28.0 against real running containers

**Target Platform**: Linux (Docker containers), development on macOS/Linux

**Project Type**: Monorepo infrastructure + multi-service web application

**Performance Goals**:
- Full platform startup: ≤ 60 seconds (pre-pulled images)
- Integration test suite: ≤ 120 seconds end-to-end

**Constraints**:
- No service internal restructuring beyond auth adapter and test runner config
- No new features; infrastructure and standardisation only
- No hardcoded passwords, DNS names, or credentials in committed files
- Access tokens must never be written to browser storage

**Scale/Scope**: 5 services, 2 frontends, 2 database engines, 1 reverse proxy,
2 integration test scenarios

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Services independently deployable | Each service has its own docker-compose.yml AND works in unified compose | ✅ PASS — each service already has docker-compose.yml; unified compose to be created |
| II. Auth adapter pattern | All 5 backends have auth_adapter.py; AUTH_MODE env var respected | ✅ PASS — adapters to be added; no auth removal |
| III. Python 3.12 everywhere | All Dockerfiles use python:3.12-slim | ✅ PASS — UIM already 3.12; ticket-manager upgrade required |
| IV. Pinned Python versions | All requirements.txt use canonical versions from pyproject.toml | ✅ PASS — versions to be aligned; deviations documented |
| V. Pinned frontend versions | Both frontends use canonical package.json versions | ✅ PASS — UIM already close; alignment to be verified |
| VI. Zustand for frontend state | UIM migrated from Context API; no tokens in localStorage | ✅ PASS — migration is in scope; ticket-manager already compliant |
| VII. Vitest for frontend tests | Both frontends use Vitest; coverage ≥ 80% | ✅ PASS — UIM already uses Vitest 1.x (upgrade to 2.1.8 needed); TM to be verified |
| VIII. ruff linting everywhere | Root + per-service .pre-commit-config.yaml with ruff | ✅ PASS — to be created; no existing conflicts |
| IX. Nginx DNS-name aware | nginx.conf.template with envsubst; no hardcoded names | ✅ PASS — template approach to be implemented |
| X. No cross-service DB access | No service queries another service's DB | ✅ PASS — existing architecture already compliant; no changes needed |

**Constitution Check: ALL GATES PASS.** No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/001-monorepo-unification/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # /speckit-tasks output (not created here)
```

### Repository Layout (current → target)

The services currently live directly under the monorepo root. The spec assumes they remain
there (the monorepo-specify-prompt explicitly states "setup before running" moves them to
`services/`). **For this implementation, services stay at their current paths** and the
infra compose references them relative to the repo root. The `services/` directory
structure from the constitution is the logical grouping, but the physical move is tracked
as its own task.

**Current layout** (what exists):
```text
dark-factory/
├── user-input-manager/    ← Prompt Studio (React + FastAPI + PostgreSQL)
│   ├── backend/
│   └── frontend/
├── ticket-manager/        ← Ticket tracking (React + FastAPI + PostgreSQL)
│   ├── backend/
│   └── frontend/
├── orchestrator/          ← Workflow FSM (FastAPI + PostgreSQL + MongoDB)
│   └── src/
├── context-distiller/     ← Memory compression (FastAPI + PostgreSQL + MongoDB)
│   └── src/
├── agent-tools/           ← MCP server (Python)
│   └── src/
├── development/           ← Planning docs, agent definitions
└── specs/                 ← Spec Kit feature specs
```

**Target layout** (after this feature):
```text
dark-factory/
├── services/
│   ├── user-input-manager/          ← moved from root
│   ├── ticket-manager/              ← moved from root
│   ├── orchestrator/                ← moved from root
│   ├── context-distiller/           ← moved from root
│   └── agent-tools/                 ← moved from root
├── infra/
│   ├── docker-compose.yml           ← unified compose (new)
│   ├── docker-compose.override.yml  ← dev port exposure (new)
│   ├── .env.example                 ← committed, fully commented (new)
│   ├── nginx/
│   │   ├── Dockerfile               ← nginx + envsubst (new)
│   │   ├── nginx.conf.template      ← envsubst template (new)
│   │   └── snippets/
│   │       ├── ssl.conf             ← commented, certbot-ready (new)
│   │       └── proxy.conf           ← shared proxy headers (new)
│   └── postgres/
│       └── init/
│           └── 01_create_databases.sql  ← creates all 4 PG DBs + users (new)
├── integration-tests/
│   ├── docker-compose.test.yml      ← extends infra compose + LLM mock (new)
│   ├── conftest.py                  ← shared fixtures, httpx clients (new)
│   ├── tests/
│   │   ├── test_scenario_a.py       ← UIM → TM flow (new)
│   │   └── test_scenario_c.py       ← Orchestrator → ContextDistiller → memory (new)
│   └── requirements.txt             ← pytest, httpx, pytest-asyncio, pyyaml (new)
├── .pre-commit-config.yaml          ← root ruff hooks (new)
├── pyproject.toml                   ← canonical Python versions + ruff config (new)
├── package.json                     ← canonical frontend versions, no workspaces (new)
├── .gitignore                       ← monorepo-level ignores (new)
├── CLAUDE.md                        ← monorepo map: services, ports, DBs (update)
└── README.md                        ← getting started guide (new)
```

**Per-service changes (inside each service directory):**
```text
services/{service}/
└── src/core/auth_adapter.py         ← new in all 5 backend services

services/user-input-manager/
├── backend/
│   └── src/core/auth_adapter.py     ← new
│   └── src/api/dependencies.py      ← update: call adapter.verify() not AuthService inline
└── frontend/
    ├── src/store/auth.ts             ← new (Zustand store, mirror of TM pattern)
    ├── src/context/AuthContext.tsx   ← delete
    ├── src/App.tsx                   ← update: remove AuthProvider wrapper
    ├── src/pages/AppRoutes.tsx       ← update: use useAuthStore instead of useAuth hook
    ├── src/api/client.ts             ← update: read token from Zustand store
    ├── src/components/auth/LoginPage.tsx ← update: call store.login()
    └── src/components/layout/Sidebar.tsx ← update: use useAuthStore
    └── vite.config.ts               ← update: Vitest 2.x canonical config

services/ticket-manager/
├── backend/
│   ├── Dockerfile                   ← update: python:3.11-slim → python:3.12-slim
│   ├── pyproject.toml               ← update: requires-python = ">=3.12"; align versions
│   └── src/core/auth_adapter.py     ← new
└── frontend/
    └── vite.config.ts               ← ensure coverage thresholds ≥ 80%

services/orchestrator/
└── src/core/auth_adapter.py         ← new
└── src/api/dependencies.py          ← update: use adapter

services/context-distiller/
└── src/core/auth_adapter.py         ← new
└── src/api/dependencies.py          ← update: use adapter

services/agent-tools/
└── src/core/auth_adapter.py         ← new (or src/auth_adapter.py if no core/ dir)
└── src/utils/auth.py                ← update: delegate to adapter
```

**Structure Decision**: Monorepo with services as top-level directories under `services/`.
Shared infra under `infra/`. Integration tests isolated under `integration-tests/`.
Per-service code changes are minimal: auth adapter insertion + dependency update only.

## Complexity Tracking

No constitution violations. No complexity justification required.

---

## Phase 0: Research

### R1 — Auth Adapter Pattern per Service

**Decision**: Thin adapter class `AuthAdapter` in `src/core/auth_adapter.py` per service.
The `verify(token: str) -> dict` method delegates to the existing local validation logic
when `AUTH_MODE=local`, and raises `NotImplementedError` when `AUTH_MODE=keycloak`.
The FastAPI `get_current_user` dependency calls `AuthAdapter().verify(token)` instead of
the current inline call.

**Rationale**: Minimum-viable seam preparation. Zero behaviour change for `AUTH_MODE=local`.
Clear error for the unimplemented Keycloak path. Consistent interface across all 5 backends.

**Per-service auth analysis**:
- **user-input-manager**: JWT validated in `AuthService.get_current_user()` which calls
  `security.py`. Dependency is `dependencies.py:get_current_user`. Adapter wraps the
  `security.verify_access_token()` call.
- **ticket-manager**: Has its own `security.py` with `verify_access_token()`. Same pattern.
- **orchestrator**: Has `src/core/security.py:verify_access_token()` called from
  `src/api/dependencies.py`. Same pattern.
- **context-distiller**: Has `src/core/security.py` and `src/api/dependencies.py`. Same.
- **agent-tools**: Auth in `src/utils/auth.py`. Adapter to be placed at `src/core/auth_adapter.py`.

**Alternatives considered**:
- Shared library package: Rejected — constitution forbids shared Python imports between services.
- Middleware-level validation: Rejected — requires larger refactor outside this phase's scope.

### R2 — Zustand Migration Pattern for user-input-manager

**Decision**: Mirror the `ticket-manager` Zustand auth store exactly. The store holds
`accessToken` (in-memory), `currentUser`, and `refreshToken` (in `sessionStorage` only —
not `localStorage`). The `AuthContext.tsx` is deleted. Components import from
`useAuthStore` hook. The `api/client.ts` interceptor reads `useAuthStore.getState().accessToken`.

**Rationale**: ticket-manager is the reference implementation per the constitution.
Reusing its pattern minimises divergence between the two frontends.

**Key differences from current UIM state**:
- `access_token` removed from `localStorage` (currently stored there)
- `current_user` removed from `localStorage` (currently stored there)
- `refresh_token` moves from `localStorage` to `sessionStorage` (matching TM)
- `AuthContext` and `AuthProvider` removed; `useAuthStore` hook replaces `useAuth()`

**Alternatives considered**:
- Keep Context + add Zustand alongside: Rejected — constitution mandates full migration,
  no Context for application state.

### R3 — Unified Docker Compose Topology

**Decision**: `infra/docker-compose.yml` defines all services, postgres, mongo, nginx.
Services are built from their own `Dockerfile` using `build.context` pointing to their
directory. All services share one `internal` network. Healthchecks use the existing
patterns already present in `orchestrator/docker-compose.yml` (pg_isready, mongosh ping,
HTTP /health).

`docker-compose.override.yml` adds port mappings for local dev (8001–8005 host).

**Service name → directory mapping**:
```
user-input-manager  → ./services/user-input-manager/backend  (port 8001)
ticket-manager      → ./services/ticket-manager/backend      (port 8002)
orchestrator        → ./services/orchestrator                (port 8003)
context-distiller   → ./services/context-distiller           (port 8004)
agent-tools         → ./services/agent-tools                 (port 8005)
```

### R4 — Nginx Template Architecture

**Decision**: `infra/nginx/Dockerfile` uses `nginx:alpine`. The entrypoint runs
`envsubst` on `nginx.conf.template` to produce `nginx.conf` at startup. Variables:
`$UIM_HOST`, `$TM_HOST`. Each server block proxies `/api/` to the backend and serves
the frontend static files from the built `dist/` volume mount.

The template includes:
- `location /.well-known/acme-challenge/` in every server block
- Commented `ssl_certificate` / `ssl_certificate_key` stanzas
- Commented HTTP→HTTPS redirect server block

**Alternatives considered**:
- Lua-based dynamic nginx: Rejected — unnecessary complexity for this phase.
- Traefik: Rejected — not in the constitution, requires larger infrastructure change.

### R5 — Integration Test LLM Mock

**Decision**: Minimal FastAPI stub server (not WireMock — avoids Java dependency).
The stub listens on port 11434 (or similar) and returns pre-canned OpenAI chat completion
responses. Services have `OPENAI_BASE_URL` overridden to point to `http://llm-mock:11434`
in `docker-compose.test.yml`.

**Rationale**: FastAPI stub is lightweight, Python-native, consistent with the test stack.
The stub only needs to handle `POST /v1/chat/completions` with valid JSON responses.

**Alternatives considered**:
- WireMock: Rejected — requires Java; additional Docker image weight.
- respx ASGI intercept: Rejected — harder to configure across multiple independent services
  without modifying service source code.

### R6 — ticket-manager Python 3.12 Upgrade

**Decision**: Change `Dockerfile` base image from `python:3.11-slim` to `python:3.12-slim`.
Update `pyproject.toml` `requires-python = ">=3.12"`. Align all dependency versions to
canonical versions in the root `pyproject.toml`. The `pytest-asyncio==1.3.0` constraint
in ticket-manager conflicts with canonical `0.24.0` — use canonical version and update
any deprecated `asyncio_mode` fixtures if needed.

**Risk**: `python-jose==3.3.0` (canonical) vs `3.5.0` (current TM). 3.3.0 supports 3.12
with no issues. Downgrade is safe.

---

## Phase 1: Design & Contracts

### Data Model

See [data-model.md](./data-model.md) for the complete entity model. Summary:

The monorepo introduces no new domain entities. The data model is an infrastructure model:
environment variable groups, Docker service topology, and auth adapter interface contracts.

### Interface Contracts

See [contracts/](./contracts/) for:
- `auth-adapter-interface.md` — `AuthAdapter.verify()` contract for all 5 backends
- `llm-mock-api.md` — stub server OpenAI-compatible endpoint contract
- `nginx-routing.md` — URL routing rules per frontend service

### Quickstart

See [quickstart.md](./quickstart.md) for operator startup instructions.

---

## Implementation Streams

The work decomposes into 6 semi-parallel streams. Streams 1 and 2 are prerequisites
for streams 3–6 (services must be in their new `services/` paths before infra compose
can reference them). Streams 3–6 can proceed in parallel after the scaffold is done.

**Stream 1 — Monorepo Scaffold** (prerequisite for all other streams)
- Move each service directory into `services/`
- Create `infra/`, `integration-tests/` directory trees
- Create root `.gitignore`, `pyproject.toml`, `package.json`, `CLAUDE.md`, `README.md`
- Create `.pre-commit-config.yaml` (root level)

**Stream 2 — Infra** (prerequisite for integration tests)
- `infra/docker-compose.yml` — unified compose
- `infra/docker-compose.override.yml` — dev port overrides
- `infra/nginx/Dockerfile` + `nginx.conf.template` + `snippets/`
- `infra/postgres/init/01_create_databases.sql`
- `infra/.env.example`

**Stream 3 — Auth Adapters** (independent after scaffold)
- `auth_adapter.py` in all 5 backends
- Update `dependencies.py` in all 5 backends to use adapter
- Verify AUTH_MODE=local behaviour identical to pre-migration

**Stream 4 — UIM Zustand Migration** (independent after scaffold)
- Create `services/user-input-manager/frontend/src/store/auth.ts`
- Delete `AuthContext.tsx`
- Update all components that import from AuthContext

**Stream 5 — Frontend Test Standardisation** (independent after scaffold)
- UIM: upgrade Vitest to 2.1.8, align vite.config.ts
- TM: verify Vitest config, ensure coverage thresholds

**Stream 6 — Integration Tests** (requires infra compose to be runnable)
- `integration-tests/docker-compose.test.yml`
- `integration-tests/conftest.py` — shared fixtures
- `integration-tests/tests/test_scenario_a.py`
- `integration-tests/tests/test_scenario_c.py`
- `integration-tests/requirements.txt`
- LLM mock stub service

**ticket-manager Python 3.12 upgrade** runs in parallel with Stream 3 (part of Stream 1
polish / Stream 3 prerequisites).
