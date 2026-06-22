# Architectural Review: Dark Factory Monorepo Unification

**Author**: software-architect | **Date**: 2026-06-22 | **Branch**: `001-monorepo-unification`

Review covers three areas assigned to this agent:
1. Docker Compose topology (T018) — pre-implementation guidance
2. Auth adapter contract (T032–T041) — pre-implementation issues
3. Nginx template (T016) — pre-implementation guidance

---

## Review 1 — Docker Compose Topology (T018)

**Status**: PRE-IMPLEMENTATION REVIEW — infra/docker-compose.yml not yet created

### Findings

#### ISSUE-1: context-distiller missing `JWT_SECRET_KEY` in test compose ⚠️ BLOCKER

`integration-tests/docker-compose.test.yml` already created (T054 complete). The
`context-distiller` service block has no `JWT_SECRET_KEY` environment variable, but
`services/context-distiller/src/core/config.py` reads `jwt_secret_key` (default `"CHANGE_ME"`).

Context-distiller verifies inbound tokens from orchestrator/UIM users. It **must** share the
same JWT secret. All other services in the test compose use:
`JWT_SECRET_KEY: test-secret-key-user-input-manager-32chars`.

**Fix**: Add to context-distiller in `docker-compose.test.yml`:
```yaml
JWT_SECRET_KEY: test-secret-key-user-input-manager-32chars
```

#### ISSUE-2: Internal port convention — all services bind to 8000, not 8001–8005

Healthchecks in `docker-compose.test.yml` correctly use `localhost:8000` (container-internal
port). The ports 8001–8005 are HOST ports only, exposed in `docker-compose.override.yml`.
The main `docker-compose.yml` (T018) must NOT expose 8001–8005 as container ports (only via
override). This is architecturally correct per the plan. The devops agent should use:

```yaml
# infra/docker-compose.yml (no ports: section on service containers)
healthcheck:
  test: ["CMD-SHELL", "wget -qO- http://localhost:8000/health || exit 1"]
```

Note: services expose `/health` not `/api/health` per spec FR-007 and tasks T021–T025.
The test compose uses `/api/health` — this needs to be aligned with whatever path
backends actually expose. Verify with backend agent.

#### ISSUE-3: nginx healthcheck will fail against named server blocks ⚠️ BLOCKER

The service topology model specifies nginx healthcheck as `wget / → 200`. However, when
nginx only has `server_name $UIM_HOST` and `server_name $TM_HOST` blocks, a request to
`http://localhost/` inside the container returns 404 (no default server matches).

**Required fix**: Add a dedicated health location to nginx config OR a default server block:

**Option A** (recommended) — add a dedicated health path to the template:
```nginx
# In nginx.conf.template — add a default server block
server {
    listen 80 default_server;
    location /nginx-health {
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }
}
```

Then the compose healthcheck becomes:
```yaml
healthcheck:
  test: ["CMD-SHELL", "wget -qO- http://localhost/nginx-health || exit 1"]
```

**Option B** — healthcheck uses actual hostname (brittle, requires DNS resolution):
```yaml
test: ["CMD-SHELL", "wget -qO- http://${UIM_HOST}/ || exit 1"]
```
This fails if DNS is not configured in the test environment.

**Recommendation**: Use Option A. It adds two lines to the template and makes healthchecks
deterministic without depending on external DNS resolution.

#### ISSUE-4: `depends_on` startup order — nginx must wait for app services

The nginx service healthcheck depends on getting a non-error response, but the SPA
`location /` block serves static files (no backend dependency). The `location /api/`
proxy starts passing requests when the backend is ready. The current design:

```yaml
nginx:
  depends_on:
    user-input-manager:
      condition: service_healthy
    ticket-manager:
      condition: service_healthy
```

This is correct per plan. **No change needed here.** Nginx should NOT depend on
orchestrator/context-distiller/agent-tools since it only proxies UIM and TM.

#### ISSUE-5: ACME challenge volume — prepare now for certbot

The nginx template includes `location /.well-known/acme-challenge/ { root /var/www/certbot; }`.
For nginx to start without error, this directory must exist in the nginx container.
The nginx Dockerfile should `RUN mkdir -p /var/www/certbot`.

OR the docker-compose.yml can mount a volume:
```yaml
nginx:
  volumes:
    - certbot-challenge:/var/www/certbot:ro
volumes:
  certbot-challenge:
```

If this directory doesn't exist, nginx startup succeeds but certbot challenge requests
will return 403/404. Since SSL is out of scope, either a mkdir in the Dockerfile or
an empty volume is acceptable. Recommend the Dockerfile mkdir approach (self-contained).

#### ISSUE-6: MongoDB authentication — compose uses no auth in test env

The test compose runs mongo with no authentication (`MONGO_INITDB_ROOT_USERNAME` not set).
This is acceptable for test environments. The production `infra/docker-compose.yml`
should also run without mongo auth for simplicity (all connections via the `internal`
network; no external exposure). Document this in `.env.example`.

### Guidance for T018 Implementation

The unified `infra/docker-compose.yml` should follow this structure:

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./postgres/init/01_create_databases.sql:/docker-entrypoint-initdb.d/01_create_databases.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 5s; timeout: 5s; retries: 12
    networks: [internal]

  mongo:
    image: mongo:7-jammy
    volumes: [mongo-data:/data/db]
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s; timeout: 5s; retries: 6
    networks: [internal]

  user-input-manager:
    build:
      context: ../services/user-input-manager/backend
      dockerfile: Dockerfile
    environment:
      DATABASE_URL: postgresql+asyncpg://${UIM_DB_USER}:${UIM_DB_PASSWORD}@postgres:5432/df_user_input
      JWT_SECRET_KEY: ${UIM_SECRET_KEY}
      AUTH_MODE: ${UIM_AUTH_MODE:-local}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      OPENAI_BASE_URL: ${OPENAI_BASE_URL:-}
      TICKET_MANAGER_BASE_URL: http://ticket-manager:8000
      TICKET_MANAGER_SERVICE_EMAIL: ${TM_SERVICE_EMAIL:-}
      TICKET_MANAGER_SERVICE_PASSWORD: ${TM_SERVICE_PASSWORD:-}
    depends_on:
      postgres: {condition: service_healthy}
      ticket-manager: {condition: service_healthy}
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:8000/health || exit 1"]
    networks: [internal]

  # ... (ticket-manager, orchestrator, context-distiller, agent-tools follow same pattern)

  nginx:
    build:
      context: ./nginx
      dockerfile: Dockerfile
    environment:
      UIM_HOST: ${UIM_HOST}
      TM_HOST: ${TM_HOST}
    ports: ["80:80"]
    depends_on:
      user-input-manager: {condition: service_healthy}
      ticket-manager: {condition: service_healthy}
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost/nginx-health || exit 1"]
    networks: [internal, external]

networks:
  internal: {driver: bridge, internal: true}
  external: {driver: bridge}

volumes:
  postgres-data:
  mongo-data:
```

**Key design decisions**:
- `networks.internal.internal: true` — prevents containers from reaching the internet directly
- `networks.external` — only nginx has access to external network
- No port mappings on service containers (only in override.yml)
- Volumes for data persistence between restarts

---

## Review 2 — Auth Adapter Contract (T032–T041)

**Status**: PRE-IMPLEMENTATION REVIEW

### Service-by-Service Analysis

#### UIM (user-input-manager) — T032, T037

Current flow: `dependencies.py:get_current_user` → `AuthService(db).get_current_user(token)` →
`security.verify_access_token(token)` → raises `JWTError`.

**AuthService.get_current_user** does three things:
1. Verify token signature → raises `JWTError` (via `UnauthorizedError` wrapper)
2. Look up user in DB → raises `UnauthorizedError` if not found
3. Check `user.is_active` → raises `ForbiddenError(403)` if inactive

The adapter should only wrap step 1. Steps 2–3 must remain in the dependency.

**Issue**: The contract's `get_current_user` example does not preserve the inactive-user
check. Current implementation returns 403 for inactive accounts; the migrated version must
also return 403 (not 401) for inactive users.

**Required pattern for UIM T037**:
```python
_adapter = AuthAdapter(get_settings())

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        claims = await _adapter.verify(credentials.credentials)
    except (JWTError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="Invalid token")
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Keycloak auth not configured")
    # Preserve existing user lookup + active check
    user = await UserRepository(db).get_by_id(claims["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return user
```

#### Ticket-Manager (TM) — T033, T038

**ISSUE ⚠️ BLOCKER**: TM's `decode_access_token()` raises `HTTPException(401)` internally,
not `JWTError`. The auth adapter contract requires the adapter to raise `JWTError`.

Current: `security.decode_access_token()` → catches `JWTError` → raises `HTTPException(401)`

If the adapter wraps `decode_access_token()`, it catches an HTTPException, not JWTError.
The dependency's `except JWTError` handler won't catch it.

**Fix required**: Backend agent must add a `verify_access_token()` function to TM's
`security.py` that raises `JWTError` (not HTTPException):

```python
def verify_access_token(token: str) -> dict[str, Any]:
    """Raises JWTError on invalid/expired token. For use by AuthAdapter only."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        raise  # propagate JWTError, don't convert to HTTPException
    if not payload.get("sub"):
        raise JWTError("Missing sub claim")
    return payload
```

The adapter (T033) then calls `security.verify_access_token()`.

Note: TM has two secrets (`secret_key` and `refresh_token_secret`). The adapter uses
`secret_key` only (access tokens). `auth_mode` field must be added to TM's Settings class.

#### Context-Distiller — T035, T040

**ISSUE ⚠️ BLOCKER**: Same as TM. `decode_token()` in security.py raises `HTTPException(401)`.

**Fix**: Add `verify_access_token()` to context-distiller's security.py that propagates
`JWTError`. The adapter (T035) calls this.

Also: context-distiller's `dependencies.py` uses `_bearer = HTTPBearer()` (auto_error=True
default), which raises `HTTPException(403)` on missing credentials, not 401. The migration
to use `HTTPBearer(auto_error=False)` + manual check is needed per the contract pattern.

#### Orchestrator — T034, T039

Current: `dependencies.py:get_current_user` → `verify_access_token()` directly → raises
`JWTError`. This is the cleanest pattern.

The adapter for orchestrator (T034) can call `security.verify_access_token()` directly.
`auth_mode` field must be added to orchestrator's Settings class.

**No structural issues** — this is the reference pattern for the other services.

#### Agent-Tools — T036, T041

**Key difference**: Agent-tools is an MCP server with NO inbound JWT validation. It only
*generates* outbound tokens (`make_service_jwt()`).

Per FR-007, a minimal FastAPI sidecar must be added to host the auth adapter and expose
`GET /health`.

The auth adapter for agent-tools validates inbound tokens from callers (e.g., orchestrator
calling agent-tools tools). The adapter uses `settings.jwt_secret_key`.

**Issue**: The current `Settings` class in agent-tools has no `auth_mode` field. It must
be added. The sidecar FastAPI app needs its own `main.py` alongside `server.py`.

Suggested structure:
```
services/agent-tools/src/
├── server.py          ← MCP server (unchanged)
├── sidecar.py         ← FastAPI app: GET /health + auth adapter endpoint
└── core/
    └── auth_adapter.py
```

The compose healthcheck targets the FastAPI sidecar port (e.g., 8005 internal).

### Auth Adapter Settings Requirements

Every service's `Settings` class must gain an `auth_mode` field. Use a Pydantic validator
to fail at startup on unrecognised values (not lazily on first request):

```python
from pydantic import field_validator
from typing import Literal

auth_mode: str = Field(default="local")

@field_validator("auth_mode")
@classmethod
def validate_auth_mode(cls, v: str) -> str:
    if v not in ("local", "keycloak"):
        raise ValueError(f"Unknown AUTH_MODE '{v}'. Must be 'local' or 'keycloak'.")
    return v
```

This converts the runtime `ValueError` into a startup configuration error, which is safer.

### Auth Adapter Summary Table

| Service | Current security fn raises | Adapter can call as-is? | Fix needed |
|---------|---------------------------|------------------------|------------|
| UIM | `JWTError` (via UnauthorizedError) | ✅ Yes | Preserve 403 for inactive users in dependency |
| TM | `HTTPException(401)` | ❌ No | Add `verify_access_token()` to security.py |
| Orchestrator | `JWTError` | ✅ Yes | None |
| Context-Distiller | `HTTPException(401)` | ❌ No | Add `verify_access_token()` to security.py |
| Agent-Tools | N/A (outbound only) | N/A | New FastAPI sidecar + adapter from scratch |

---

## Review 3 — Nginx Template (T016)

**Status**: PRE-IMPLEMENTATION REVIEW

### Findings

#### CONFIRMED-CORRECT: envsubst variable scoping

The T017 Dockerfile entrypoint: `envsubst '$UIM_HOST $TM_HOST' < nginx.conf.template > nginx.conf`

Passing the explicit variable list `'$UIM_HOST $TM_HOST'` to envsubst is **correct and
critical**. Without this explicit list, envsubst replaces ALL `$VAR` occurrences including
nginx's own variables (`$host`, `$remote_addr`, `$uri`, `$scheme`, `$proxy_add_x_forwarded_for`)
with empty strings, breaking the entire configuration.

#### ISSUE-1: nginx healthcheck (same as ISSUE-3 in Compose review) ⚠️ BLOCKER

See compose review ISSUE-3 above. The template needs a default server block for health checks.

#### ISSUE-2: Frontend static files path not specified for TM

The UIM nginx block serves from `/var/www/uim`. The TM block must serve from a different
path, e.g., `/var/www/tm`. The multi-stage Dockerfiles for each frontend must `COPY dist/`
to the matching path that nginx expects.

**Required alignment**:
- UIM frontend Dockerfile: `COPY --from=build /app/dist /var/www/uim`
- TM frontend Dockerfile: `COPY --from=build /app/dist /var/www/tm`
- UIM nginx block: `root /var/www/uim;`
- TM nginx block: `root /var/www/tm;`

OR use a single nginx image that COPY-in from multi-stage build context. But since
frontend assets live in different services, the nginx Dockerfile would need multi-stage
build args or external volume mounts.

**Actually, rethinking**: The plan (and FR-005a) says multi-stage Dockerfiles per frontend
service, where "the nginx stage copies `dist/` in". This means EACH frontend service has
its OWN nginx (not the central infra/nginx). The central infra/nginx only proxies `/api/`
to backends and serves its own static copy.

Wait — re-reading the plan and spec more carefully:

The infra nginx proxies `/api/` to backends. The nginx routing contract shows:
```
location / {
    root /var/www/uim;
    try_files $uri $uri/ /index.html;
}
```

This means the infra/nginx also serves the frontend static files. But the frontend static
files are built inside the frontend service's own Docker image. How do they get into
`/var/www/uim` in the nginx container?

There are two valid interpretations:
1. **Frontend services have their own nginx** (multi-stage build per frontend), and the
   infra/nginx only reverse-proxies to them (no static files in infra/nginx).
2. **Infra/nginx has all static files** copied in during a multi-stage build that includes
   the frontend build stages.

The nginx routing contract explicitly shows `root /var/www/uim` in the infra/nginx server
block — this is interpretation #2. But building a multi-stage Dockerfile that pulls from
BOTH frontend codebases is complex.

**Recommendation**: Use interpretation #1 (per FR-005a and standard practice):
- UIM frontend: multi-stage Dockerfile, nginx stage serves from `/usr/share/nginx/html`
- TM frontend: same
- Infra/nginx: reverse-proxies `/api/` to backend AND also proxies `/` to frontend nginx

Then the nginx routing contract needs updating: replace `root /var/www/uim` with:
```nginx
location / {
    proxy_pass http://user-input-manager-frontend:8080;
    include /etc/nginx/snippets/proxy.conf;
}
```

OR keep the per-frontend nginx interpretation and add frontend service containers.

**This is an architectural decision that must be resolved before T016 and T018.**
I'm flagging it as requiring product-manager + devops alignment.

If each frontend has its own nginx container:
- Compose adds 2 more services: `uim-frontend` (port 8080) and `tm-frontend` (port 8082)
- Infra nginx becomes a pure reverse proxy
- Total containers: 10 (not 8)

If infra nginx includes static files:
- The infra/nginx Dockerfile must build from a multi-stage that copies from both frontend images
- OR the compose uses a side-loading pattern with shared volumes (fragile)

**Preferred approach**: Each frontend has its own container, infra nginx is a pure proxy.
This aligns with FR-005a ("nginx stage copies it in" refers to the per-service Dockerfile,
not the infra/nginx Dockerfile) and is more maintainable.

#### ISSUE-3: HTTP → HTTPS redirect comment placement

The commented redirect block in the contract uses the same `server_name $UIM_HOST` as the
active block. When certbot enables it, both blocks would match — nginx processes the first
match. The redirect block comment placement is safe (it's commented), but when uncommented,
it must appear BEFORE the SSL-enabled block or conflicts arise.

The comment block structure in the contract correctly handles this (redirect server listens
on `:80`, main server moves to `:443 ssl`). No change needed for the commented state.

### Nginx Template Guidance Summary

1. Add a `default_server` health block (BLOCKER, required for healthchecks)
2. Resolve frontend static file serving pattern (BLOCKER, before T016 and T018)
3. Confirm envsubst variable list in Dockerfile entrypoint (already correct)
4. SSL and ACME stanzas are correct as specified

---

## Action Items for Agents

### For devops (before T016 and T018):

| # | Action | Priority |
|---|--------|----------|
| A1 | Decide: per-service nginx containers vs infra/nginx with static files | BLOCKER |
| A2 | Add default_server health block to nginx.conf.template | BLOCKER |
| A3 | Ensure nginx Dockerfile adds `RUN mkdir -p /var/www/certbot` | Low |

### For backend (before T032–T036):

| # | Action | Priority |
|---|--------|----------|
| B1 | Add `verify_access_token()` to TM's security.py (raises JWTError, not HTTPException) | BLOCKER |
| B2 | Add `verify_access_token()` to context-distiller's security.py | BLOCKER |
| B3 | Add `auth_mode` field + validator to all 5 Settings classes | Required |
| B4 | Change context-distiller `_bearer = HTTPBearer()` to `HTTPBearer(auto_error=False)` | Required |
| B5 | Preserve 403 for inactive-user check in UIM's migrated `get_current_user` | Required |
| B6 | Design agent-tools FastAPI sidecar (`src/sidecar.py`) for health + auth | Required |

### For devops/autotester (T054 — already created):

| # | Action | Priority |
|---|--------|----------|
| C1 | Add `JWT_SECRET_KEY: test-secret-key-user-input-manager-32chars` to context-distiller in `docker-compose.test.yml` | BLOCKER |
| C2 | Verify health endpoint path: `/health` or `/api/health` — align across all services | Required |

---

## Architecture Decision: Frontend Serving Pattern

**Decision Needed**: How are frontend static files served?

### Option A: Per-service frontend nginx (recommended)
- UIM frontend: `services/user-input-manager/frontend/Dockerfile` — Node build + nginx stage
- TM frontend: `services/ticket-manager/frontend/Dockerfile` — Node build + nginx stage
- Infra/nginx: pure reverse proxy (no static files, only `/api/` proxy + SPA proxy to frontend containers)
- Pros: Each service is self-contained; simpler infra/nginx Dockerfile; FR-005a compliant
- Cons: 2 additional containers (10 total); more service entries in compose

### Option B: Infra/nginx with embedded static files
- Infra/nginx Dockerfile uses multi-stage build referencing frontend images
- All static files embedded in one nginx container
- Pros: Fewer containers; matches the nginx routing contract as written
- Cons: Infra/nginx Dockerfile becomes complex; tight coupling between infra and frontend images

**Recommendation**: Option A. Align `infra/nginx/nginx.conf.template` to proxy `/` to
per-service frontend containers. Update T016 and T018 accordingly.

---

*Review complete. Blockers and required changes flagged. Please acknowledge receipt.*
