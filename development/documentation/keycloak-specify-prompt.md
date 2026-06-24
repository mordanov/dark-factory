# /speckit.specify — Keycloak IAM Integration

## Prompt (copy-paste into Claude Code)

```
/speckit.specify

Replace all local authentication across Dark Factory with Keycloak 25+
as the single source of truth for identity and access management.

This is a destructive migration. It touches every service, both frontends,
nginx, and docker-compose. Read ALL context files before generating the spec.
Do not skip any service. Do not preserve legacy auth paths.

## Context files (read in this order)

@.specify/memory/constitution.md
@.specify/memory/service-map.md
@.specify/memory/project-map.md

Current auth code to understand and replace:
@../user-input-manager/backend/src/core/security.py
@../user-input-manager/backend/src/core/auth_adapter.py
@../user-input-manager/backend/src/api/v1/auth.py
@../user-input-manager/backend/src/api/v1/users.py
@../user-input-manager/backend/src/models/models.py
@../user-input-manager/frontend/src/store/authStore.ts
@../user-input-manager/frontend/src/components/auth/LoginPage.tsx
@../ticket-manager/backend/src/core/security.py
@../ticket-manager/backend/src/api/v1/auth.py
@../ticket-manager/backend/src/models/models.py
@../ticket-manager/frontend/src/store/authStore.ts
@../orchestrator/src/core/auth_adapter.py
@../orchestrator/src/services/tm_client/client.py
@../context-distiller/src/core/auth_adapter.py
@../agent-dispatcher/src/core/auth_adapter.py
@../agent-dispatcher/src/services/reporter.py
@../../infra/docker-compose.yml
@../../infra/.env.example
@../../infra/nginx/nginx.conf.template

Do not go above the ../../ directory level (monorepo root).

## What to specify

### PART 1 — New Infrastructure

#### 1.1 Keycloak container (`infra/docker-compose.yml`)

```yaml
keycloak:
  image: quay.io/keycloak/keycloak:25.0
  restart: unless-stopped
  command: >
    start
    --import-realm
    --db=postgres
    --db-url=jdbc:postgresql://postgres:5432/keycloak
    --db-username=${KC_DB_USERNAME}
    --db-password=${KC_DB_PASSWORD}
    --hostname=${KC_HOSTNAME}
    --hostname-strict=false
    --http-enabled=true
    --proxy=edge
    --log-level=INFO
  environment:
    KC_DB: postgres
    KEYCLOAK_ADMIN: ${KC_BOOTSTRAP_ADMIN_USERNAME}
    KEYCLOAK_ADMIN_PASSWORD: ${KC_BOOTSTRAP_ADMIN_PASSWORD}
  volumes:
    - ./keycloak/realm-export-substituted.json:/opt/keycloak/data/import/realm.json:ro
    # Note: substitution happens via entrypoint wrapper — see 1.3
  depends_on:
    postgres:
      condition: service_healthy
  healthcheck:
    test: ["CMD-SHELL", "curl -f http://localhost:8080/realms/dark-factory || exit 1"]
    interval: 15s
    timeout: 10s
    retries: 20
    start_period: 60s
  networks:
    - internal
  expose:
    - "8080"
```

All other services add `keycloak` to their `depends_on`:
```yaml
depends_on:
  keycloak:
    condition: service_healthy
```

#### 1.2 oauth2-proxy container (`infra/docker-compose.yml`)

```yaml
oauth2-proxy:
  image: quay.io/oauth2-proxy/oauth2-proxy:v7.7.1
  restart: unless-stopped
  command: --config=/etc/oauth2-proxy/config.cfg
  volumes:
    - ./oauth2-proxy/config.cfg:/etc/oauth2-proxy/config.cfg:ro
  environment:
    OAUTH2_PROXY_CLIENT_SECRET: ${OAUTH2_PROXY_CLIENT_SECRET}
    OAUTH2_PROXY_COOKIE_SECRET: ${OAUTH2_PROXY_COOKIE_SECRET}
  depends_on:
    keycloak:
      condition: service_healthy
  networks:
    - internal
  expose:
    - "4180"
```

#### 1.3 Realm export with env substitution

**`infra/keycloak/realm-export.json`** — full realm definition.

Write this file with ALL variables as `${VAR_NAME}` placeholders.
It is NOT valid JSON until substituted (that is intentional).

Structure (write in full, do not abbreviate):

```json
{
  "realm": "dark-factory",
  "enabled": true,
  "displayName": "Dark Factory",
  "registrationAllowed": false,
  "resetPasswordAllowed": true,
  "bruteForceProtected": true,
  "permanentLockout": false,
  "loginWithEmailAllowed": true,
  "duplicateEmailsAllowed": false,
  "sslRequired": "external",
  "accessTokenLifespan": 300,
  "ssoSessionMaxLifespan": 36000,
  "ssoSessionIdleTimeout": 1800,

  "roles": {
    "realm": [
      { "name": "user", "description": "Default application user" },
      { "name": "administrator", "description": "Can access Keycloak Admin Console" }
    ]
  },

  "defaultRoles": ["user"],

  "clients": [
    // uim-frontend (public, PKCE)
    // tm-frontend (public, PKCE)
    // oauth2-proxy (confidential, no flows)
    // orchestrator (confidential, service accounts)
    // context-distiller (confidential, service accounts)
    // agent-dispatcher (confidential, service accounts, access.token.lifespan=3600)
    // agent-tools (confidential, service accounts)
    // All clients as per constitution
  ],

  "identityProviders": [
    {
      "alias": "google",
      "displayName": "Google",
      "providerId": "google",
      "enabled": false,
      "trustEmail": true,
      "firstBrokerLoginFlowAlias": "first broker login",
      "config": {
        "clientId": "${GOOGLE_CLIENT_ID}",
        "clientSecret": "${GOOGLE_CLIENT_SECRET}",
        "defaultScope": "openid email profile",
        "useJwksUrl": "true"
      }
    }
  ],

  "users": [
    {
      "username": "${KC_BOOTSTRAP_ADMIN_USERNAME}",
      "email": "${KC_BOOTSTRAP_ADMIN_EMAIL}",
      "enabled": true,
      "emailVerified": true,
      "realmRoles": ["administrator", "user"],
      "credentials": [
        {
          "type": "password",
          "value": "${KC_BOOTSTRAP_ADMIN_PASSWORD}",
          "temporary": true
        }
      ]
    }
  ]
}
```

**`infra/keycloak/substitute-env.sh`** — runs before Keycloak starts:

```bash
#!/bin/bash
# Substitutes ${VAR} in realm-export.json using envsubst
# Called from docker-compose entrypoint or init container

set -e
INPUT="/opt/keycloak/data/import/realm-export.json"
OUTPUT="/opt/keycloak/data/import/realm.json"
envsubst < "$INPUT" > "$OUTPUT"
echo "Realm JSON substituted → $OUTPUT"
```

Use a `command` override or init container pattern to run this before
`kc.sh start`. The cleanest approach is a custom entrypoint in docker-compose:

```yaml
keycloak:
  entrypoint: >
    /bin/bash -c "
      /opt/keycloak/data/import/substitute-env.sh &&
      /opt/keycloak/bin/kc.sh start ..."
```

Mount both `realm-export.json` and `substitute-env.sh` into the container.

#### 1.4 oauth2-proxy configuration (`infra/oauth2-proxy/config.cfg`)

```cfg
# Dark Factory oauth2-proxy — Bearer token validation only
# Keycloak OIDC provider

provider = "keycloak-oidc"
oidc_issuer_url = "http://keycloak:8080/realms/dark-factory"
client_id = "oauth2-proxy"

# Pass auth headers to upstream
set_xauthrequest = true
pass_user_headers = true
pass_access_token = false

# Allow all authenticated users (role check is done by services)
email_domains = ["*"]

# Required but unused (Bearer-only mode)
upstreams = ["http://127.0.0.1:4181"]
http_address = "0.0.0.0:4180"

# Skip redirect for Bearer tokens (API mode)
skip_jwt_bearer_tokens = true

# Cookie settings (not used for API but required by proxy)
cookie_secure = false
cookie_name = "_oauth2_proxy_df"
```

Client secret and cookie secret come from environment (docker-compose env block).

#### 1.5 nginx.conf.template update

Add to EVERY `/api/` location block in both server sections (uim + tm):

```nginx
# Bearer token validation via oauth2-proxy
auth_request /oauth2/auth;
auth_request_set $auth_user $upstream_http_x_auth_request_user;
auth_request_set $auth_email $upstream_http_x_auth_request_email;

# Forward user identity to backend
proxy_set_header X-Auth-User $auth_user;
proxy_set_header X-Auth-Email $auth_email;

error_page 401 = @error401;
```

Add shared internal location (once per server block):
```nginx
location = /oauth2/auth {
    internal;
    proxy_pass http://oauth2-proxy:4180;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Original-URI $request_uri;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

location @error401 {
    default_type application/json;
    return 401 '{"detail":"Not authenticated","code":"TOKEN_EXPIRED_OR_INVALID"}';
}

# Forward oauth2-proxy's own endpoints (needed for OIDC flow)
location /oauth2/ {
    proxy_pass http://oauth2-proxy:4180;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

Do NOT add `auth_request` to:
- `location /` (frontend static files)
- `location /.well-known/` (certbot)
- `location = /oauth2/auth` (itself)
- `location /oauth2/` (oauth2-proxy management)

#### 1.6 PostgreSQL init update

Add to `infra/postgres/init/01_create_databases.sql`:
```sql
-- Keycloak database
CREATE DATABASE keycloak;
CREATE USER ${KC_DB_USERNAME:-keycloak_user}
    WITH PASSWORD '${KC_DB_PASSWORD:-changeme}';
GRANT ALL PRIVILEGES ON DATABASE keycloak TO ${KC_DB_USERNAME:-keycloak_user};
ALTER DATABASE keycloak OWNER TO ${KC_DB_USERNAME:-keycloak_user};
```

---

### PART 2 — Backend Changes (all 5 services)

Apply to: user-input-manager, ticket-manager, orchestrator,
context-distiller, agent-dispatcher.

#### 2.1 New module: `src/core/auth_adapter.py` (rewrite existing)

Full `KeycloakValidator` implementation as specified in the constitution.
Key points:
- `UserClaims` dataclass: sub, email, preferred_username, roles, is_admin
- JWKS cached with 5-minute TTL using `time.monotonic()`
- `AUTH_MODE=local` uses HS256 with `TEST_JWT_SECRET` (for tests only)
- `AUTH_MODE=keycloak` uses RS256 JWKS from Keycloak
- `verify()` raises `UnauthorizedError` on invalid token
- Single module-level `_validator` singleton

#### 2.2 New module: `src/core/keycloak_client.py` (new in all services)

`KeycloakServiceClient` as specified in constitution:
- Client Credentials grant
- Token cached until 30s before expiry
- `asyncio.Lock` for thread safety
- `async_auth_headers() -> dict` for httpx calls
- Module-level singleton initialized in FastAPI lifespan:

```python
_kc_client: KeycloakServiceClient | None = None

def get_kc_client() -> KeycloakServiceClient:
    global _kc_client
    if _kc_client is None:
        _kc_client = KeycloakServiceClient(
            keycloak_base_url=settings.keycloak_base_url,
            realm=settings.keycloak_realm,
            client_id=settings.keycloak_client_id,
            client_secret=settings.keycloak_client_secret,
        )
    return _kc_client
```

#### 2.3 Config changes (`src/core/config.py`) in all services

Remove:
```python
jwt_secret_key: str
jwt_algorithm: str
access_token_expires_minutes: int
refresh_token_expires_days: int
```

Add:
```python
keycloak_base_url: str = "http://keycloak:8080"
keycloak_realm: str = "dark-factory"
keycloak_client_id: str = ""        # service-specific
keycloak_client_secret: str = ""    # service-specific
auth_mode: str = "keycloak"         # keycloak | local (tests only)
test_jwt_secret: str = "test-secret-do-not-use-in-production"
```

#### 2.4 FastAPI dependencies update (`src/api/dependencies.py`)

Replace `get_current_user`:
```python
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserClaims:
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    validator = KeycloakValidator()
    return await validator.verify(credentials.credentials)

async def require_admin(claims: UserClaims = Depends(get_current_user)) -> UserClaims:
    if not claims.is_admin:
        raise HTTPException(403, "Administrator role required")
    return claims
```

All route handlers that previously accepted `User` ORM objects now
accept `UserClaims`. Update every affected handler signature.

#### 2.5 Service-to-service clients updated

Every `httpx` call from one service to another replaces:
```python
# Before
headers={"Authorization": f"Bearer {get_service_token()}"}
# After
headers=await get_kc_client().async_auth_headers()
```

Affected files:
- orchestrator: `tm_client/client.py`, `orchestrator_service.py`
- context-distiller: `collector.py`, any TM calls
- agent-dispatcher: `reporter.py`, `poller.py`
- user-input-manager: `services/ticket_manager/client.py`,
  `services/ticket_manager/plan_client.py`

#### 2.6 Alembic migrations (destructive, all services with users table)

New migration in each service that has a `users` table.
Migration description: `"DESTRUCTIVE — drop users table, migrate user_id to TEXT"`

Steps per migration:
1. Drop all tables with FK to `users` (sessions, iterations, agent_runs, etc.)
2. Drop `users` table
3. Recreate dropped tables with `user_id TEXT NOT NULL` (no FK constraint)
4. Drop `session_status`, `session_type` enums if they referenced user ID
5. Recreate relevant enums if needed

This migration cannot be reversed (down migration: raise NotImplementedError).

#### 2.7 requirements.txt additions (all backends)

Add:
```
python-jose[cryptography]==3.3.0   # already present, keep
httpx==0.28.0                      # already present, keep
```

No additional packages needed — JWKS validation uses existing `python-jose`.
Do NOT add `python-keycloak` (unnecessary complexity; direct HTTP is sufficient).

---

### PART 3 — user-input-manager Backend Specific

#### 3.1 Delete entirely
- `src/api/v1/auth.py`
- `src/api/v1/users.py`
- `src/services/auth_service.py`
- `src/services/user_service.py`
- User model from `src/models/models.py`

#### 3.2 Update `src/main.py`

Remove from router registration:
```python
# Remove these:
from src.api.v1 import auth, users
auth.router
users.router
```

Keep: `sessions`, `orchestrator`, `ticket_manager` routers.

#### 3.3 Session service update

`SessionService` currently stores `user_id: UUID`. Change to `user_id: str`
(Keycloak sub is a UUID string but stored as TEXT).

All methods that accept `user_id: UUID` change to `user_id: str`.

---

### PART 4 — ticket-manager Backend Specific

#### 4.1 Delete entirely
- `src/api/v1/auth.py` (local login)
- User model and users table
- Any user management endpoints

#### 4.2 Keep all ticket/project endpoints unchanged

The ticket-manager API is used by agents and other services.
Only auth mechanism changes (Keycloak Bearer instead of local JWT).

---

### PART 5 — Frontend Changes

Apply to both: user-input-manager frontend, ticket-manager frontend.

#### 5.1 Install keycloak-js

```bash
npm install keycloak-js@25.0.0
```

Version must match Keycloak server version.

#### 5.2 New file: `src/keycloak.ts`

```typescript
import Keycloak from 'keycloak-js'

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
})

export default keycloak
```

#### 5.3 Rewrite `src/store/authStore.ts`

```typescript
import Keycloak from 'keycloak-js'
import { create } from 'zustand'
import keycloak from '../keycloak'

interface UserInfo {
  sub: string
  email: string
  username: string
  isAdmin: boolean
}

interface AuthState {
  initialized: boolean
  user: UserInfo | null
  initialize: () => Promise<void>
  logout: () => Promise<void>
  getToken: () => Promise<string>
  getAuthHeader: () => Promise<{ Authorization: string }>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  initialized: false,
  user: null,

  initialize: async () => {
    const authenticated = await keycloak.init({
      onLoad: 'login-required',
      pkceMethod: 'S256',
      checkLoginIframe: false,
    })

    if (!authenticated) {
      // keycloak.init with login-required redirects if not authenticated
      // This line should not be reached
      return
    }

    keycloak.onTokenExpired = () => {
      keycloak.updateToken(30).catch(() => {
        // Token refresh failed — redirect to login
        keycloak.login()
      })
    }

    const roles: string[] = keycloak.tokenParsed?.realm_access?.roles ?? []

    set({
      initialized: true,
      user: {
        sub: keycloak.subject ?? '',
        email: keycloak.tokenParsed?.email ?? '',
        username: keycloak.tokenParsed?.preferred_username ?? '',
        isAdmin: roles.includes('administrator'),
      },
    })
  },

  logout: async () => {
    await keycloak.logout({
      redirectUri: window.location.origin,
    })
    set({ user: null, initialized: false })
  },

  getToken: async () => {
    await keycloak.updateToken(30)
    return keycloak.token ?? ''
  },

  getAuthHeader: async () => {
    const token = await get().getToken()
    return { Authorization: `Bearer ${token}` }
  },
}))
```

#### 5.4 Update `src/api/client.ts`

Replace localStorage token read with:
```typescript
import { useAuthStore } from '../store/authStore'

api.interceptors.request.use(async (config) => {
  try {
    const header = await useAuthStore.getState().getAuthHeader()
    config.headers.Authorization = header.Authorization
  } catch {
    // Not initialized yet — let request proceed without token
  }
  return config
})

// Remove the 401 interceptor that cleared localStorage
// Keycloak handles session invalidation
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    if (err.response?.status === 401) {
      // Force keycloak re-login
      await useAuthStore.getState().initialize()
    }
    return Promise.reject(err)
  }
)
```

#### 5.5 Update `src/App.tsx`

```typescript
import { useEffect } from 'react'
import { useAuthStore } from './store/authStore'
import { LoadingScreen } from './components/layout/LoadingScreen'

export default function App() {
  const { initialize, initialized } = useAuthStore()

  useEffect(() => { initialize() }, [])

  if (!initialized) return <LoadingScreen />

  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
```

Add `LoadingScreen` component: spinner centered on dark background,
"Connecting to Dark Factory…" text. No other content until Keycloak ready.

#### 5.6 Delete from user-input-manager frontend

- `src/components/auth/LoginPage.tsx`
- `src/context/AuthContext.tsx` (if still exists)

#### 5.7 Update `src/pages/AppRoutes.tsx`

Remove:
- `/login` route
- `RequireAuth` wrapper (Keycloak handles this at app init)
- `RequireAdmin` route guard for `/admin`

Keep all routes but remove auth guards:
```typescript
// All routes are accessible — Keycloak already authenticated the user
// Admin UI (/admin) route is REMOVED entirely (Keycloak console replaces it)
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/sessions" element={<AppShell><SessionListPage /></AppShell>} />
      <Route path="/sessions/:sessionId" element={<AppShell><SessionDetailPage /></AppShell>} />
      <Route path="/queue" element={<AppShell><QueuePage /></AppShell>} />
      <Route path="*" element={<Navigate to="/sessions" replace />} />
    </Routes>
  )
}
```

#### 5.8 Update Sidebar

Remove:
- Admin nav item
- Language-aware admin role check
- `logout` handler (replace with Keycloak logout)

Add:
- `logout` calls `useAuthStore.getState().logout()`
- If `user.isAdmin`: show link to Keycloak Admin Console
  `<a href="${VITE_KEYCLOAK_URL}/admin/dark-factory/console" target="_blank">`

#### 5.9 Vite env variables

Add to `frontend/.env.example` (user-input-manager):
```dotenv
VITE_KEYCLOAK_URL=http://localhost:8080
VITE_KEYCLOAK_REALM=dark-factory
VITE_KEYCLOAK_CLIENT_ID=uim-frontend
```

Same pattern for ticket-manager (client_id=tm-frontend).

---

### PART 6 — Agent Dispatcher Specific

#### 6.1 Token injection for agents

In `src/services/context_builder.py`, add to context generation:

```python
# Get fresh Keycloak token for agent to use with TM API
kc_client = get_kc_client()
service_token = await kc_client.get_token()

# Inject into context template under ## Service Token section
context_parts.append(f"""
## Service Token
Use this Bearer token for ALL API calls to Dark Factory services.
Token is valid for 1 hour from agent spawn time.

Authorization: Bearer {service_token}

TM API base: {settings.ticket_manager_base_url}
Ticket to update: {ticket.id} in project {ticket.project_id}
""")
```

#### 6.2 Remove JWT generation

Delete `create_service_token()` from agent-dispatcher.
Replace all usages with `await get_kc_client().async_auth_headers()`.

---

### PART 7 — .env.example update

Rewrite the auth-related sections in `infra/.env.example`.
Remove:
```dotenv
JWT_SECRET_KEY=...
INITIAL_ADMIN_EMAIL=...
INITIAL_ADMIN_PASSWORD=...
```

Add all variables from the constitution's "Environment Variables" section
with full inline comments explaining:
- What each variable controls
- Which services use it
- Security notes (cookie secret length, temporary password)

Group order (new):
1. PostgreSQL shared
2. MongoDB shared
3. Keycloak server
4. oauth2-proxy
5. Google OIDC (placeholder)
6. Service client secrets (one per service)
7. user-input-manager
8. ticket-manager
9. orchestrator
10. context-distiller
11. agent-dispatcher
12. nginx / DNS
13. Frontend (VITE_*)

---

### PART 8 — Tests

#### 8.1 Test fixtures update (all services)

In each service's `tests/conftest.py`:

```python
import pytest
from jose import jwt as jose_jwt
from datetime import datetime, timedelta, timezone

TEST_JWT_SECRET = "test-secret-do-not-use-in-production"

@pytest.fixture
def user_token() -> str:
    """HS256 test token — valid only when AUTH_MODE=local"""
    payload = {
        "sub": "test-user-uuid-1234",
        "email": "user@test.com",
        "preferred_username": "testuser",
        "realm_access": {"roles": ["user"]},
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jose_jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

@pytest.fixture
def admin_token() -> str:
    payload = {
        "sub": "test-admin-uuid-5678",
        "email": "admin@test.com",
        "preferred_username": "testadmin",
        "realm_access": {"roles": ["user", "administrator"]},
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jose_jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

@pytest.fixture(autouse=True)
def set_auth_mode(monkeypatch):
    """Force AUTH_MODE=local in all tests"""
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("TEST_JWT_SECRET", TEST_JWT_SECRET)
```

#### 8.2 New unit tests for auth adapter

`tests/unit/test_auth_adapter.py` (per service):

```python
async def test_valid_user_token_returns_claims(user_token, set_auth_mode)
async def test_valid_admin_token_has_is_admin_true(admin_token)
async def test_invalid_token_raises_unauthorized()
async def test_expired_token_raises_unauthorized()
async def test_missing_realm_access_returns_empty_roles()
async def test_keycloak_mode_fetches_jwks(monkeypatch)
    # Mock httpx.get → return fake JWKS
    # Verify JWKS URL contains realm name
async def test_jwks_cached_for_ttl(monkeypatch)
    # Call verify() twice
    # Assert httpx.get called only once
async def test_jwks_refreshed_after_ttl_expired(monkeypatch)
```

#### 8.3 New unit tests for keycloak_client.py

`tests/unit/test_keycloak_client.py` (per service):

```python
async def test_get_token_calls_keycloak_token_endpoint()
async def test_token_cached_until_expiry()
async def test_token_refreshed_30s_before_expiry()
async def test_concurrent_calls_use_single_request()  # asyncio.Lock test
async def test_keycloak_error_raises_upstream_error()
```

#### 8.4 Integration test updates

All existing integration tests that use `auth_headers` fixture continue
to work because `AUTH_MODE=local` is forced by the `set_auth_mode`
autouse fixture.

No integration tests call real Keycloak. Keycloak is production-only.

---

### PART 9 — Documentation

#### 9.1 Update `infra/KEYCLOAK.md` (new file)

```markdown
# Keycloak Setup Guide

## First boot
docker compose up automatically imports the realm on first start.
The initial admin user credentials are in `.env` (KC_BOOTSTRAP_ADMIN_*).
The initial password is temporary — you will be prompted to change it on first login.

## Accessing Keycloak Admin Console
http://localhost:8080/admin  (internal, via port forward)
or via nginx at http://${KC_HOSTNAME}/auth/admin

## Creating users
Keycloak Admin Console → dark-factory realm → Users → Add user
Self-registration is disabled.

## Assigning administrator role
Users → select user → Role mapping → Assign role → administrator

## Enabling Google login
1. Create OAuth2 credentials at https://console.cloud.google.com
2. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env
3. Edit infra/keycloak/realm-export.json: "enabled": true for google IdP
4. docker compose down keycloak && docker compose up keycloak
   (realm re-import only if realm doesn't exist — may need manual update
   via Admin Console → Identity Providers → Google)

## Re-importing realm
If you need to re-import realm after changes:
1. docker compose down keycloak
2. Connect to postgres: DROP DATABASE keycloak; CREATE DATABASE keycloak;
3. docker compose up keycloak
```

#### 9.2 Update monorepo `README.md`

Add section: "Authentication (Keycloak)"
- Explain SSO, login flow
- Link to KEYCLOAK.md
- Note that admin UI is in Keycloak console, not in application

## Constraints (from constitution — enforce all)

- No service stores passwords or issues tokens
- JWT_SECRET_KEY removed for user tokens (kept only if needed for test fixture)
- AUTH_MODE=local only in tests, never in docker-compose
- JWKS cached with 5-minute TTL — never fetched per-request
- keycloak-js token in memory only — never localStorage
- Service client secrets never appear in logs or API responses
- Google IdP disabled=true in realm JSON by default
- agent-dispatcher client has access.token.lifespan=3600
- Destructive migration cannot be reversed (down() raises NotImplementedError)
- keycloak depends on postgres healthy
- All services depend on keycloak healthy
- `/login` route removed from all frontends
- Admin user management UI removed from user-input-manager

## Out of scope for this spec

- HTTPS / certbot (nginx is certbot-ready from previous spec)
- Keycloak clustering / HA
- Custom Keycloak login theme
- Per-application roles (only global realm roles)
- MFA / 2FA configuration (can be done in Keycloak console post-deploy)
- User migration from old databases (data is wiped, fresh start)
- Keycloak backup strategy
```

---

## Setup

```bash
cd dark-factory  # monorepo root

specify init keycloak-iam --ai claude

cp /path/to/keycloak-constitution.md .specify/memory/constitution.md

cat > .specify/memory/service-map.md << 'EOF'
# Services affected by Keycloak integration

## Infra (new)
- Keycloak 25 container + keycloak PostgreSQL database
- oauth2-proxy container (Bearer token validation for nginx)
- infra/keycloak/realm-export.json (full realm definition)
- infra/oauth2-proxy/config.cfg

## Backends (all — auth adapter rewrite)
- user-input-manager: DROP users table, remove auth/users endpoints
- ticket-manager: DROP users table, remove local auth
- orchestrator: replace service JWT with Client Credentials
- context-distiller: replace service JWT with Client Credentials
- agent-dispatcher: inject Keycloak token for agents, CC for reporters

## Frontends (both — keycloak-js)
- user-input-manager: replace Zustand local auth with keycloak-js
- ticket-manager: same
- Both: remove login pages, add LoadingScreen, update Sidebar

## nginx
- Add auth_request /oauth2/auth to all /api/ locations
- Add oauth2-proxy endpoint locations
EOF

/speckit.specify   # paste prompt above
```
