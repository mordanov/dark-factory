# Implementation Plan: Keycloak IAM Migration

**Branch**: `004-keycloak-iam-migration` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/004-keycloak-iam-migration/spec.md`

## Summary

Replace all local password-based authentication across Dark Factory with Keycloak 25 as the
sole identity provider. Every service's `auth_adapter.py` becomes a `KeycloakValidator` that
validates RS256 tokens from Keycloak's JWKS endpoint (cached ≥300s). Service-to-service calls
switch from locally-signed JWTs to Keycloak Client Credentials grants. Both frontends replace
hand-rolled login flows with `keycloak-js`. The `users` table is dropped from every service
that holds one; `user_id` columns become `TEXT NOT NULL` storing the Keycloak `sub` UUID string.
New infra containers: Keycloak 25 (backed by PostgreSQL) and oauth2-proxy (Bearer validator for nginx).

## Technical Context

**Language/Version**: Python 3.12 (all backends), TypeScript 5.7.2 (frontends)
**Primary Dependencies (backend)**: FastAPI 0.115.5, SQLAlchemy 2.0.36, asyncpg 0.30.0,
  python-jose 3.3.0, httpx 0.28.0, structlog 24.4.0, alembic 1.14.0, pydantic 2.10.3
**Primary Dependencies (frontend)**: React 18.3.1, Zustand 5.0.2, keycloak-js 25.x,
  axios 1.7.9, @tanstack/react-query 5.56.2, Vite 6.0.3, Vitest 2.1.8
**Infrastructure**: Keycloak 25 (quay.io/keycloak/keycloak:25.0), oauth2-proxy v7.7.1,
  PostgreSQL 16 (existing, adds keycloak DB), nginx alpine (existing)
**Storage**: PostgreSQL 16 — destructive migrations in user-input-manager and ticket-manager
  (drop users table, recreate dependent tables with TEXT user_id); Keycloak persistence in
  new `keycloak` database
**Testing**: pytest 8.3.4 + pytest-asyncio 0.24.0 (backend); Vitest 2.1.8 (frontend);
  `AUTH_MODE=local` with HMAC test tokens for all automated tests — no real Keycloak in CI
**Target Platform**: Linux container (Docker Compose), all services
**Performance Goals**: Token validation ≤5ms on cache hit (JWKS cached ≥300s); token refresh
  for service-to-service ≤200ms on cache miss (cached 30s before expiry)
**Constraints**: No service may start without Keycloak being healthy (depends_on healthcheck).
  Destructive migrations are irreversible — `downgrade()` raises `NotImplementedError`.
  `AUTH_MODE=local` MUST NEVER appear in `infra/docker-compose.yml`.
**Scale/Scope**: 6 backend services + 2 frontends + 2 infra containers + 1 nginx update;
  destructive Alembic migrations in 2 services (UIM, TM); config changes in all 6 backends

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Services Remain Independently Deployable | ✅ Pass | Each service gets its own Keycloak client; inter-service is HTTP-only |
| II | Keycloak IAM Migration | ✅ Pass | This feature IS Principle II — implementing it |
| III | Python 3.12 Everywhere | ✅ Pass | No Python version changes; all services already on 3.12 |
| IV | Shared Python Library Versions | ✅ Pass | python-jose 3.3.0, httpx 0.28.0 already canonical |
| V | Shared Frontend Library Versions | ✅ Pass | keycloak-js 25.x already in canonical list |
| VI | Zustand for All Frontend State | ✅ Pass | authStore rewritten to wrap keycloak-js; tokens in-memory only |
| VII | Vitest for All Frontend Tests | ✅ Pass | Existing Vitest config unchanged |
| VIII | ruff for All Python Linting | ✅ Pass | No linting config changes; ruff applied to new/changed files |
| IX | Nginx is DNS-Name Aware | ✅ Pass | nginx.conf.template updated with auth_request on /api/ locations |
| X | No Cross-Service Database Access | ✅ Pass | No shared databases; Keycloak gets its own DB |
| XI | Agent Dispatcher — FSM Sovereignty | ✅ Pass | No FSM logic changes; only auth token source changes |
| XII | Agent Dispatcher — Operational Safety | ✅ Pass | Secret hygiene: Keycloak secrets never in logs |
| XIII | Planning Agent — Plan Persistence | ✅ Pass | No plan logic changes; auth dependency replaced only |
| XIV | Planning Agent — User Confirmation Gate | ✅ Pass | No plan logic changes |
| XV | Planning Agent — Ticket Creation All-or-None | ✅ Pass | No creation logic changes |
| XVI | Planning Agent — Agent Config Best-Effort | ✅ Pass | No agent config logic changes |
| XVII | Keycloak is Single Source of Truth | ✅ Pass | This feature enacts Principle XVII |
| XVIII | JWKS Cached ≥300s | ✅ Pass | KeycloakValidator caches JWKS with 300s TTL |
| XIX | Service-to-Service via Client Credentials | ✅ Pass | KeycloakServiceClient replaces create_service_token() in all services |
| XX | Frontend Auth via keycloak-js | ✅ Pass | Both frontends replace login pages with keycloak-js PKCE |
| XXI | Users Table Permanently Removed | ✅ Pass | Destructive migrations drop users table; downgrade() → NotImplementedError |

> No violations — gates pass. Proceeding to Phase 0 research.

## Project Structure

### Documentation (this feature)

```text
specs/004-keycloak-iam-migration/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── keycloak-realm.md       # Realm export structure and client registrations
│   ├── auth-adapter.md         # KeycloakValidator interface contract
│   ├── keycloak-service-client.md  # KeycloakServiceClient interface contract
│   └── nginx-auth.md           # nginx auth_request contract
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
infra/
├── docker-compose.yml          # + keycloak + oauth2-proxy containers; depends_on for all services
├── .env.example                # Rewritten auth section; add KC_* and OAUTH2_* vars
├── nginx/nginx.conf.template   # + auth_request /oauth2/auth on all /api/ locations
├── postgres/init/01_create_databases.sql  # + keycloak database
├── keycloak/
│   ├── realm-export.json       # Full realm with ${VAR} placeholders
│   └── substitute-env.sh       # envsubst runner before kc.sh
└── oauth2-proxy/
    └── config.cfg              # Bearer validator config (keycloak-oidc provider)

services/user-input-manager/
├── backend/src/core/
│   ├── auth_adapter.py         # REWRITE → KeycloakValidator (RS256 + JWKS cache)
│   ├── keycloak_client.py      # NEW — KeycloakServiceClient (Client Credentials)
│   └── config.py               # Remove jwt_secret_key/algorithm/expires; add KC_* vars
├── backend/src/api/v1/
│   ├── auth.py                 # DELETE (local login endpoints removed)
│   └── users.py                # DELETE (user management removed)
├── backend/src/services/
│   ├── auth_service.py         # DELETE
│   └── user_service.py         # DELETE
├── backend/src/models/models.py    # DELETE User class + users table
├── backend/alembic/versions/   # NEW: destructive migration (drop users, recreate with TEXT user_id)
├── backend/src/main.py         # Remove auth/users router registrations
├── backend/tests/conftest.py   # Add user_token/admin_token/set_auth_mode fixtures
├── backend/tests/unit/
│   ├── test_auth_adapter.py    # NEW — 8 tests (JWKS cache, RS256/HS256 modes)
│   └── test_keycloak_client.py # NEW — 5 tests (token cache, lock, refresh)
└── frontend/src/
    ├── keycloak.ts             # NEW — keycloak-js instance
    ├── store/authStore.ts      # REWRITE — wraps keycloak-js; getToken/initialize/logout
    ├── api/client.ts           # UPDATE — interceptor calls getAuthHeader()
    ├── App.tsx                 # UPDATE — initialize() on mount; LoadingScreen until ready
    ├── components/layout/LoadingScreen.tsx  # NEW — "Connecting to Dark Factory…"
    ├── components/auth/LoginPage.tsx        # DELETE
    ├── pages/AppRoutes.tsx     # UPDATE — remove /login route + RequireAuth + /admin
    ├── components/layout/Sidebar.tsx        # UPDATE — logout via KC; admin → KC console link
    └── .env.example            # ADD VITE_KEYCLOAK_URL/REALM/CLIENT_ID

services/ticket-manager/
├── backend/src/core/
│   ├── auth_adapter.py         # REWRITE → KeycloakValidator
│   ├── keycloak_client.py      # NEW — KeycloakServiceClient
│   └── config.py               # Remove secret_key/refresh_token_secret; add KC_* vars
├── backend/src/api/v1/
│   └── auth.py                 # DELETE
├── backend/alembic/versions/   # NEW: destructive migration (drop users, recreate with TEXT user_id)
├── backend/src/main.py         # Remove auth router registration
├── backend/tests/conftest.py   # Add user_token/admin_token/set_auth_mode fixtures
├── backend/tests/unit/
│   ├── test_auth_adapter.py    # NEW
│   └── test_keycloak_client.py # NEW
└── frontend/src/
    ├── keycloak.ts             # NEW
    ├── store/authStore.ts      # REWRITE
    ├── api/client.ts           # UPDATE
    ├── App.tsx                 # UPDATE
    ├── components/layout/LoadingScreen.tsx  # NEW
    └── .env.example            # ADD VITE_KEYCLOAK_URL/REALM/CLIENT_ID

services/orchestrator/
├── src/core/
│   ├── auth_adapter.py         # REWRITE → KeycloakValidator
│   ├── keycloak_client.py      # NEW
│   └── config.py               # Remove jwt_secret_key; add KC_* vars
├── src/services/tm_client/client.py  # REWRITE _login/_headers → KeycloakServiceClient
└── tests/unit/
    ├── test_auth_adapter.py    # NEW
    └── test_keycloak_client.py # NEW

services/context-distiller/
├── src/core/
│   ├── auth_adapter.py         # REWRITE → KeycloakValidator
│   ├── keycloak_client.py      # NEW
│   └── config.py               # Remove jwt vars; add KC_* vars
└── tests/unit/
    ├── test_auth_adapter.py    # NEW
    └── test_keycloak_client.py # NEW

services/agent-dispatcher/
├── src/core/
│   ├── auth_adapter.py         # REWRITE → KeycloakValidator
│   ├── keycloak_client.py      # NEW
│   ├── security.py             # DELETE create_service_token(); keep verify_access_token
│   └── config.py               # Remove jwt_secret_key/jwt_algorithm; add KC_* vars
├── src/services/reporter.py    # UPDATE — replace create_service_token() → get_kc_client()
└── tests/unit/
    ├── test_auth_adapter.py    # NEW
    └── test_keycloak_client.py # NEW

services/agent-tools/
├── src/core/
│   ├── auth_adapter.py         # REWRITE → KeycloakValidator
│   ├── keycloak_client.py      # NEW (no outbound calls but needs the module)
│   └── config.py               # Add KC_* vars
└── tests/unit/
    └── test_auth_adapter.py    # NEW
```

**Structure Decision**: Monorepo-wide cross-cutting change. Each service is updated independently;
shared patterns (KeycloakValidator, KeycloakServiceClient) are copy-consistent (not a shared lib —
Principle I prohibits shared code imports between services). Infrastructure changes in `infra/`.

## Complexity Tracking

> No constitution violations to justify.
