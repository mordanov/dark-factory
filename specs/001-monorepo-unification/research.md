# Research: Dark Factory Monorepo Unification

**Phase 0 output** | Branch: `001-monorepo-unification` | Date: 2026-06-22

## R1 — Auth Adapter Pattern

**Decision**: Per-service `AuthAdapter` class at `src/core/auth_adapter.py`.
Interface: `async def verify(self, token: str) -> dict`. Reads `AUTH_MODE` from settings.
`local` delegates to the existing `security.verify_access_token(token)`. `keycloak`
raises `NotImplementedError` with message `"Keycloak validation not implemented in this phase"`.

**Rationale**: Zero-diff behaviour for `AUTH_MODE=local`. Single injection point per service.
Future Keycloak implementation only touches the adapter, not route handlers.

**Current auth patterns by service**:

| Service | Validation function | Dependency file |
|---------|--------------------|--------------------|
| user-input-manager | `AuthService.get_current_user()` → `security.py` | `src/api/dependencies.py` |
| ticket-manager | `verify_access_token()` in `security.py` | `src/api/dependencies.py` (assumed, same pattern) |
| orchestrator | `verify_access_token()` in `src/core/security.py` | `src/api/dependencies.py` |
| context-distiller | `src/core/security.py` + `src/api/dependencies.py` | `src/api/dependencies.py` |
| agent-tools | `src/utils/auth.py` | `src/config.py` |

**Alternatives considered**:
- Shared library: Constitution prohibits shared Python imports across services.
- Middleware: Larger scope than this phase permits.

## R2 — UIM Zustand Migration

**Decision**: Mirror ticket-manager's `src/store/auth.ts` store exactly.
State: `accessToken: string | null` (memory only), `currentUser: UserSummary | null`,
`refreshToken: string | null` (sessionStorage key `"rt"`), `isRestoring: boolean`.
Actions: `login()`, `setAccessToken()`, `setRestored()`, `logout()`.

**Files to change in UIM frontend**:

| File | Action |
|------|--------|
| `src/store/auth.ts` | Create (new) |
| `src/context/AuthContext.tsx` | Delete |
| `src/App.tsx` | Remove `<AuthProvider>`, wrap with store restoration logic |
| `src/pages/AppRoutes.tsx` | Replace `useAuth()` with `useAuthStore()` |
| `src/api/client.ts` | Replace `localStorage.getItem('access_token')` with `useAuthStore.getState().accessToken` |
| `src/components/auth/LoginPage.tsx` | Call `useAuthStore().login()` instead of context |
| `src/components/layout/Sidebar.tsx` | Replace `useAuth()` with `useAuthStore()` |

**Token storage delta**:

| Token | Before | After |
|-------|--------|-------|
| access_token | localStorage | Zustand memory (never persisted) |
| refresh_token | localStorage | sessionStorage (key: `"rt"`) |
| current_user | localStorage (JSON) | Zustand memory |

**Rationale**: sessionStorage for refresh token matches ticket-manager. Clears on tab close,
survives page refresh within the same tab — good security/UX balance.

## R3 — Unified Docker Compose

**Decision**: `infra/docker-compose.yml` with all 8 containers (5 services + postgres +
mongo + nginx). `depends_on` with `condition: service_healthy` for DB dependencies.
All containers on shared `internal` network plus `nginx` on an additional `external` network
for port 80 exposure.

**Port allocation** (from constitution Service Registry):

| Service | Internal port | Host port (override only) |
|---------|--------------|--------------------------|
| user-input-manager | 8001 | 8001 |
| ticket-manager | 8002 | 8002 |
| orchestrator | 8003 | 8003 |
| context-distiller | 8004 | 8004 |
| agent-tools | 8005 | 8005 |
| postgres | 5432 | not exposed in unified |
| mongo | 27017 | not exposed in unified |
| nginx | 80 | 80 |

**Healthcheck patterns** (reuse from existing service docker-composes):
- PostgreSQL: `pg_isready -U ${POSTGRES_USER}`
- MongoDB: `mongosh --eval "db.adminCommand('ping')"`
- FastAPI services: `wget -qO- http://localhost:{PORT}/health || exit 1`
- Nginx: `wget -qO- http://localhost/health || exit 1`

## R4 — Nginx Template Architecture

**Decision**: `envsubst` replaces `$UIM_HOST` and `$TM_HOST` in `nginx.conf.template`
at container startup via Dockerfile entrypoint: `envsubst '$UIM_HOST $TM_HOST' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && nginx -g 'daemon off;'`

**Routing per server block**:
- `location /` — serve frontend `dist/` (volume mount from built image or bind mount)
- `location /api/` — proxy_pass to backend service on internal network
- `location /.well-known/acme-challenge/` — certbot webroot challenge

**Frontend serving strategy**: For dev, bind-mount the `dist/` from the Vite build output.
For production, copy `dist/` into the nginx image at build time using a multi-stage
Dockerfile per frontend service (or a dedicated nginx image with COPY from build stage).
For this phase: bind-mount is acceptable; production multi-stage build is a future
optimisation.

**Alternatives considered**:
- Runtime Vite dev server: Not appropriate for compose production mode.
- Separate nginx per frontend: Not in the constitution topology.

## R5 — Integration Test LLM Mock

**Decision**: Minimal FastAPI app (`integration-tests/llm-mock/main.py`) that handles:
- `POST /v1/chat/completions` → returns canned `ChatCompletion` JSON
- `GET /health` → returns 200

Packaged as a Docker image in `docker-compose.test.yml`. Services have
`OPENAI_BASE_URL=http://llm-mock:11434/v1` in the test compose override.

**Canned response format** (sufficient for both test scenarios):
```json
{
  "id": "mock-completion",
  "object": "chat.completion",
  "choices": [{
    "message": {"role": "assistant", "content": "Mock LLM response"},
    "finish_reason": "stop",
    "index": 0
  }],
  "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
}
```

**Alternatives considered**:
- WireMock: Requires Java, heavier image.
- respx: Service-level intercept, requires modifying service source code.

## R6 — ticket-manager Python 3.12 Upgrade

**Decision**: `Dockerfile` base image: `python:3.11-slim` → `python:3.12-slim`.
`pyproject.toml` `requires-python`: `>=3.11` → `>=3.12`.
Dependency version alignment to canonical versions:

| Library | Current TM | Canonical | Action |
|---------|-----------|-----------|--------|
| fastapi | 0.136.3 | 0.115.5 | Downgrade — 0.115.x is stable LTS |
| uvicorn | 0.29.0 | 0.32.1 | Upgrade |
| sqlalchemy | 2.0.30 | 2.0.36 | Upgrade (patch) |
| asyncpg | 0.29.0 | 0.30.0 | Upgrade (minor) |
| alembic | 1.13.1 | 1.14.0 | Upgrade (minor) |
| pydantic | >=2.9,<3 | 2.10.3 | Pin to canonical |
| pydantic-settings | 2.2.1 | 2.6.1 | Upgrade |
| python-jose | 3.5.0 | 3.3.0 | Downgrade (3.3.0 supports 3.12) |
| structlog | 24.2.0 | 24.4.0 | Upgrade (patch) |
| httpx | 0.28.1 | 0.28.0 | Downgrade (patch, negligible) |
| pytest | >=9.0.3,<10 | 8.3.4 | Downgrade to canonical |
| pytest-asyncio | 1.3.0 | 0.24.0 | Downgrade to canonical |
| ruff | >=0.4,<1 | 0.8.3 | Pin to canonical |

**Risk assessment**: `fastapi` downgrade from 0.136.3 to 0.115.5 is the largest version
drop. 0.115.x is the stable branch; 0.136.x is a pre-release series. Downgrade is
appropriate. Verify no TM code uses APIs introduced after 0.115.5.

**Unresolved**: ticket-manager uses `pytest-httpx` (not in canonical versions) and `mypy`
(constitution says no mypy in this phase — remove). `bcrypt==4.1.3` used directly instead
of via passlib — needs review; passlib 1.7.4 (canonical) bundles bcrypt support.
