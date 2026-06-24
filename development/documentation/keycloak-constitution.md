# Dark Factory — Keycloak IAM Constitution

## Identity

This constitution governs the replacement of all local authentication
mechanisms across Dark Factory with Keycloak as the single source of
truth for identity and access management.

Keycloak is not an add-on. After this migration:
- No service stores passwords
- No service issues tokens
- No service maintains a user table
- Every token in the system originates from Keycloak

---

## What Is Destroyed (irreversible)

The following are permanently removed. There is no fallback:

**Backend (all services):**
- `users` table and all associated migrations
- `src/core/security.py` (password hashing, token creation)
- `src/api/v1/auth.py` (login, refresh endpoints)
- `JWT_SECRET_KEY` used for user token signing
- `INITIAL_ADMIN_EMAIL`, `INITIAL_ADMIN_PASSWORD` env vars

**user-input-manager specifically:**
- `src/api/v1/users.py` (admin user management endpoints)
- `src/components/admin/AdminUsersPage.tsx`
- `src/components/auth/LoginPage.tsx`
- Admin nav item in Sidebar
- `/login` and `/admin` routes

**ticket-manager specifically:**
- Local login page and auth flow

**All existing data:**
- All rows in `users` tables (all services)
- All `prompt_sessions` (foreign key to deleted users)
- All `prompt_iterations`
- All `agent_runs`, `brainstorm_sessions`

The database schema keeps `user_id TEXT` columns (now stores Keycloak `sub`)
but the data is wiped by a migration that drops and recreates affected tables.

---

## Keycloak Deployment

**Container:** `quay.io/keycloak/keycloak:25` (or latest 25.x stable)
**Mode:** production with PostgreSQL backend
**Database:** `keycloak` in the centralized PostgreSQL 16 instance
**Instance count:** single (no clustering)
**Internal port:** 8080
**Not exposed externally** — all access via nginx

### Startup sequence in docker-compose

```
postgres (healthy)
    └── keycloak (depends_on postgres, runs kc.sh start)
            └── all other services (depend on keycloak via healthcheck)
```

Keycloak healthcheck:
```bash
curl -f http://keycloak:8080/realms/dark-factory || exit 1
```

Services must not start until Keycloak is healthy (realm is fully imported).

---

## Realm Configuration

**Realm name:** `dark-factory` (fixed, never rename)

### Realm settings
- `registrationAllowed: false` — no self-registration
- `resetPasswordAllowed: true` — admin can reset via console
- `bruteForceProtected: true`
- `permanentLockout: false` (temporary lockout only)
- `loginWithEmailAllowed: true`
- `duplicateEmailsAllowed: false`
- `sslRequired: external` (HTTPS only for external requests; internal = none)

### Roles (realm-level, global)

| Role | Description |
|---|---|
| `user` | Default role. Can use all application features. |
| `administrator` | Can access Keycloak Admin Console. Same app permissions as user. |

`user` is the default role assigned to every new account.
`administrator` is assigned manually by an existing admin via Keycloak console.

No per-client roles. No composite roles in v1.

### Clients

Six clients in the realm. All configurations are in `realm-export.json`.

#### `uim-frontend` (Prompt Studio SPA)
```json
{
  "clientId": "uim-frontend",
  "publicClient": true,
  "standardFlowEnabled": true,
  "implicitFlowEnabled": false,
  "directAccessGrantsEnabled": false,
  "attributes": { "pkce.code.challenge.method": "S256" },
  "redirectUris": ["${UIM_BASE_URL}/*"],
  "webOrigins": ["${UIM_BASE_URL}"],
  "rootUrl": "${UIM_BASE_URL}"
}
```

#### `tm-frontend` (Ticket Manager SPA)
Same pattern as `uim-frontend` with `${TM_BASE_URL}`.

#### `oauth2-proxy` (nginx Bearer validator)
```json
{
  "clientId": "oauth2-proxy",
  "publicClient": false,
  "standardFlowEnabled": false,
  "serviceAccountsEnabled": false,
  "secret": "${OAUTH2_PROXY_CLIENT_SECRET}"
}
```

#### Service clients (orchestrator, context-distiller, agent-dispatcher, agent-tools)
All four follow the same pattern:
```json
{
  "clientId": "orchestrator",
  "publicClient": false,
  "standardFlowEnabled": false,
  "serviceAccountsEnabled": true,
  "secret": "${ORCHESTRATOR_CLIENT_SECRET}",
  "attributes": {
    "access.token.lifespan": "3600"
  }
}
```

`serviceAccountsEnabled: true` enables Client Credentials grant.
`access.token.lifespan: 3600` (1 hour) — required because agents can run
up to 600s and tokens must not expire mid-run.

#### Token lifetime settings (realm level)
```json
{
  "accessTokenLifespan": 300,
  "ssoSessionMaxLifespan": 36000,
  "ssoSessionIdleTimeout": 1800,
  "offlineSessionMaxLifespan": 5184000
}
```

Frontend access tokens: 5 minutes (keycloak-js refreshes silently).
SSO session: 10 hours.
Service account tokens: 1 hour (per-client override above).

### Identity Providers (placeholder)

Google OIDC provider is pre-configured but **disabled**:
```json
{
  "alias": "google",
  "providerId": "google",
  "enabled": false,
  "config": {
    "clientId": "${GOOGLE_CLIENT_ID:-placeholder}",
    "clientSecret": "${GOOGLE_CLIENT_SECRET:-placeholder}",
    "defaultScope": "openid email profile"
  }
}
```

To enable Google login: set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
in `.env`, change `"enabled": true` in the realm JSON, and re-import.
No code changes required.

### Initial admin user (created via realm import)
```json
{
  "users": [{
    "username": "${KC_BOOTSTRAP_ADMIN_USERNAME}",
    "email": "${KC_BOOTSTRAP_ADMIN_EMAIL}",
    "enabled": true,
    "emailVerified": true,
    "realmRoles": ["administrator", "user"],
    "credentials": [{
      "type": "password",
      "value": "${KC_BOOTSTRAP_ADMIN_PASSWORD}",
      "temporary": true
    }]
  }]
}
```

`"temporary": true` — user must change password on first login.

---

## Realm Import

The realm is imported on Keycloak startup via:
```bash
/opt/keycloak/bin/kc.sh start \
  --import-realm \
  --db=postgres \
  --db-url=jdbc:postgresql://postgres:5432/keycloak \
  --db-username=${KC_DB_USERNAME} \
  --db-password=${KC_DB_PASSWORD} \
  --hostname=${KC_HOSTNAME} \
  --hostname-strict=false \
  --http-enabled=true \
  --proxy=edge
```

Realm JSON is mounted at `/opt/keycloak/data/import/realm-export.json`.
Environment variable substitution in the JSON is handled by an init script
(`infra/keycloak/substitute-env.sh`) that runs before kc.sh and writes the
substituted file to the import directory.

**If realm already exists** (on restart), Keycloak skips import by default.
Use `--import-realm` flag behavior: it imports only if realm doesn't exist.
This means env var changes to realm JSON require manual re-import or realm deletion.

---

## oauth2-proxy

### Role
oauth2-proxy acts as a **Bearer token validator** only.
It does NOT handle login redirects (keycloak-js does that).
nginx sends `auth_request` to oauth2-proxy for every `/api/*` request.

### Configuration (`infra/oauth2-proxy/config.cfg`)
```cfg
provider = "keycloak-oidc"
oidc_issuer_url = "http://keycloak:8080/realms/dark-factory"
client_id = "oauth2-proxy"
client_secret = "${OAUTH2_PROXY_CLIENT_SECRET}"

# Validate Bearer tokens without redirecting
skip_auth_routes = []
skip_jwt_bearer_tokens = true
allowed_groups = []

# Pass user info to upstream
set_xauthrequest = true
pass_access_token = true

# Headers passed to backend after validation
pass_user_headers = true
# X-Auth-Request-User: Keycloak sub (UUID)
# X-Auth-Request-Email: user email
# X-Auth-Request-Groups: realm roles

upstreams = ["http://127.0.0.1:4181"]
http_address = "0.0.0.0:4180"

# Cookie config (not used for API, but required by oauth2-proxy)
cookie_secret = "${OAUTH2_PROXY_COOKIE_SECRET}"
cookie_secure = false  # true in production with HTTPS
email_domains = ["*"]
```

### nginx integration

In `nginx.conf.template`, every `/api/` location block adds:
```nginx
location /api/ {
    auth_request /oauth2/auth;
    auth_request_set $user $upstream_http_x_auth_request_user;
    auth_request_set $email $upstream_http_x_auth_request_email;

    error_page 401 = @error401;

    proxy_set_header X-Auth-User $user;
    proxy_set_header X-Auth-Email $email;
    # ... existing proxy headers
}

location = /oauth2/auth {
    internal;
    proxy_pass http://oauth2-proxy:4180;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header X-Original-URI $request_uri;
}

location @error401 {
    return 401 '{"detail":"Not authenticated"}';
    add_header Content-Type application/json;
}
```

Frontend routes (`/`, `/sessions`, `/queue`, etc.) do NOT have `auth_request`.
keycloak-js handles the redirect flow for frontend routes.

---

## Backend Auth Adapter (all services)

### Replace `AuthAdapter` with `KeycloakValidator`

Each service's `src/core/auth_adapter.py` is rewritten:

```python
"""Keycloak JWT validator.

Validates Bearer tokens issued by Keycloak.
JWKS is cached with a 5-minute TTL to avoid hammering Keycloak.

AUTH_MODE env var is kept for testing:
  keycloak  (production) — validates against Keycloak JWKS
  local     (tests only) — validates with HMAC secret (test-only)
"""

@dataclass
class UserClaims:
    sub: str                    # Keycloak user UUID
    email: str
    preferred_username: str
    roles: list[str]            # from realm_access.roles
    is_admin: bool              # "administrator" in roles

class KeycloakValidator:
    _jwks_cache: dict | None = None
    _jwks_fetched_at: float = 0
    _CACHE_TTL = 300            # 5 minutes

    async def get_jwks(self) -> dict:
        now = time.monotonic()
        if not self._jwks_cache or now - self._jwks_fetched_at > self._CACHE_TTL:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(
                    f"{settings.keycloak_base_url}/realms/"
                    f"{settings.keycloak_realm}/protocol/openid-connect/certs"
                )
                r.raise_for_status()
                self._jwks_cache = r.json()
                self._jwks_fetched_at = now
        return self._jwks_cache

    async def verify(self, token: str) -> UserClaims:
        jwks = await self.get_jwks()
        try:
            payload = jwt.decode(
                token, jwks,
                algorithms=["RS256"],
                options={"verify_aud": False},  # audiences vary by client
            )
        except JWTError as exc:
            raise UnauthorizedError(str(exc)) from exc

        roles = payload.get("realm_access", {}).get("roles", [])
        return UserClaims(
            sub=payload["sub"],
            email=payload.get("email", ""),
            preferred_username=payload.get("preferred_username", ""),
            roles=roles,
            is_admin="administrator" in roles,
        )
```

The FastAPI dependency `get_current_user` returns `UserClaims` instead of
a `User` ORM object. All route handlers that previously used `user.is_admin`
or `user.id` are updated to use `claims.is_admin` and `claims.sub`.

### What replaces the `users` table

Services that store user-owned data (prompt_sessions, agent_runs) keep
`user_id TEXT NOT NULL` columns. The value is now Keycloak `sub` (UUID string).
There is no foreign key constraint to a local users table.

No local user lookup. If a route needs the user's email or name, it comes
from JWT claims (already validated), not from a database.

---

## Service-to-Service: Client Credentials

### `KeycloakServiceClient` (new module in every backend service)

```python
# src/core/keycloak_client.py

class KeycloakServiceClient:
    """Manages a Keycloak Client Credentials token for inter-service calls.
    
    Token is cached until 30s before expiry.
    Thread-safe via asyncio.Lock.
    """
    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        async with self._lock:
            if time.monotonic() < self._expires_at - 30:
                return self._token
            r = await httpx.AsyncClient().post(
                f"{settings.keycloak_base_url}/realms/"
                f"{settings.keycloak_realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=10.0,
            )
            r.raise_for_status()
            data = r.json()
            self._token = data["access_token"]
            self._expires_at = time.monotonic() + data["expires_in"]
            return self._token

    def auth_headers(self) -> dict:
        """Sync helper — raises if token not yet fetched."""
        return {"Authorization": f"Bearer {self._token}"}

    async def async_auth_headers(self) -> dict:
        token = await self.get_token()
        return {"Authorization": f"Bearer {token}"}
```

Every `httpx` call between services uses this instead of a static JWT.
Module-level singleton per service, initialized in FastAPI lifespan.

### Agent token injection

Agent Dispatcher calls `get_token()` for the `agent-dispatcher` client
**immediately before spawning** each agent. The token is embedded in the
agent context under `## Service Token`. Token lifetime is 1 hour (per-client
override in Keycloak). This covers the maximum agent timeout (600s).

---

## Frontend: keycloak-js Integration

Both frontends (user-input-manager, ticket-manager) replace their local
auth stores with `keycloak-js`.

### Installation
```
npm install keycloak-js
```

### Keycloak initialization (`src/keycloak.ts`)

```typescript
import Keycloak from 'keycloak-js'
import { getSettings } from './settings'

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
})

export default keycloak
```

### Auth store (`src/store/authStore.ts`)

```typescript
interface AuthState {
  initialized: boolean
  authenticated: boolean
  user: {
    sub: string
    email: string
    username: string
    isAdmin: boolean
  } | null

  initialize: () => Promise<void>
  logout: () => Promise<void>
  getToken: () => Promise<string>  // refreshes if needed
}
```

`initialize()`:
1. Calls `keycloak.init({ onLoad: 'login-required', pkceMethod: 'S256' })`
2. If not authenticated → Keycloak redirects to login page (no return)
3. If authenticated → populate store from `keycloak.tokenParsed`
4. Set up token refresh: `keycloak.onTokenExpired = () => keycloak.updateToken(30)`

`getToken()`:
1. `await keycloak.updateToken(30)` (refresh if expires in < 30s)
2. Return `keycloak.token`

`logout()`:
1. `keycloak.logout({ redirectUri: window.location.origin })`
2. Keycloak redirects to all other app logout endpoints (Single Logout)

### Axios interceptor update

Replace localStorage token read with:
```typescript
api.interceptors.request.use(async (config) => {
  const token = await useAuthStore.getState().getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
```

### App initialization (`src/App.tsx`)

```typescript
const { initialize, initialized } = useAuthStore()

useEffect(() => { initialize() }, [])

if (!initialized) return <LoadingScreen />
```

No login page, no login route. If not authenticated, Keycloak handles
the redirect before the app renders.

### isAdmin check

From `keycloak.tokenParsed.realm_access.roles.includes('administrator')`.
Stored in `authStore.user.isAdmin`.
Used in Sidebar to show/hide Queue nav item... wait, admin UI is removed.
Used to show a notice "to manage users, visit Keycloak Admin Console".

---

## Environment Variables

### New variables (all services)

```dotenv
# ─── Keycloak ─────────────────────────────────────────────────────────────
# Internal URL (service-to-service, within Docker network)
KEYCLOAK_BASE_URL=http://keycloak:8080
KEYCLOAK_REALM=dark-factory

# Client credentials for this specific service
# Each service has its own client_id and client_secret
KEYCLOAK_CLIENT_ID=orchestrator       # varies per service
KEYCLOAK_CLIENT_SECRET=changeme       # varies per service

# Auth mode (keycloak in production, local in unit tests)
AUTH_MODE=keycloak
```

### Removed variables (all services)
```
JWT_SECRET_KEY           ← replaced by Keycloak signing (RS256, Keycloak-managed)
INITIAL_ADMIN_EMAIL      ← replaced by KC_BOOTSTRAP_ADMIN_EMAIL
INITIAL_ADMIN_PASSWORD   ← replaced by KC_BOOTSTRAP_ADMIN_PASSWORD
```

### New infra variables

```dotenv
# ─── Keycloak server ──────────────────────────────────────────────────────
KC_DB_USERNAME=keycloak_user
KC_DB_PASSWORD=changeme_keycloak_db
KC_HOSTNAME=auth.dark-factory.local    # external hostname for OIDC endpoints
KC_BOOTSTRAP_ADMIN_USERNAME=admin
KC_BOOTSTRAP_ADMIN_EMAIL=admin@dark-factory.local
KC_BOOTSTRAP_ADMIN_PASSWORD=ChangeMe123!

# ─── oauth2-proxy ─────────────────────────────────────────────────────────
OAUTH2_PROXY_CLIENT_SECRET=changeme
OAUTH2_PROXY_COOKIE_SECRET=changeme_32bytes   # must be 32 bytes base64

# ─── Google OIDC (placeholder, disabled) ─────────────────────────────────
GOOGLE_CLIENT_ID=placeholder
GOOGLE_CLIENT_SECRET=placeholder

# ─── Service client secrets ───────────────────────────────────────────────
ORCHESTRATOR_CLIENT_SECRET=changeme
CONTEXT_DISTILLER_CLIENT_SECRET=changeme
AGENT_DISPATCHER_CLIENT_SECRET=changeme
AGENT_TOOLS_CLIENT_SECRET=changeme

# ─── Frontend ─────────────────────────────────────────────────────────────
# Public Keycloak URL (accessible from browser)
VITE_KEYCLOAK_URL=http://auth.dark-factory.local  # or http://localhost:8080 for dev
VITE_KEYCLOAK_REALM=dark-factory
VITE_UIM_KEYCLOAK_CLIENT_ID=uim-frontend
VITE_TM_KEYCLOAK_CLIENT_ID=tm-frontend
```

---

## New Files

```
infra/
├── keycloak/
│   ├── realm-export.json          ← full realm definition with ${VAR} placeholders
│   └── substitute-env.sh          ← envsubst → /opt/keycloak/data/import/
├── oauth2-proxy/
│   └── config.cfg                 ← oauth2-proxy configuration
```

---

## Database Changes

### New database: `keycloak`

Add to `infra/postgres/init/01_create_databases.sql`:
```sql
CREATE DATABASE keycloak;
CREATE USER keycloak_user WITH PASSWORD '${KC_DB_PASSWORD}';
GRANT ALL PRIVILEGES ON DATABASE keycloak TO keycloak_user;
```

### Migrations (all services with user_id)

New Alembic migration per service that:
1. Drops `users` table and all dependent data
2. Changes `user_id` columns from `UUID FK → users.id` to `TEXT NOT NULL`
3. Truncates all tables that had `user_id` foreign keys

This migration is **destructive and irreversible**.
The migration description must include: `"DESTRUCTIVE: drops all user data"`

---

## Testing in AUTH_MODE=local

Unit and integration tests use `AUTH_MODE=local` with a test HMAC secret.
The `KeycloakValidator.verify()` method checks `AUTH_MODE`:
- `keycloak`: RS256 JWKS validation (production)
- `local`: HS256 with `TEST_JWT_SECRET` (tests only, never in production)

This preserves the existing test infrastructure without requiring a
Keycloak instance in CI.

---

## Definition of Done

1. `docker compose up` starts Keycloak, waits for healthy, then starts services
2. Visiting `http://localhost` (uim-frontend) redirects to Keycloak login
3. After login: user lands in Prompt Studio with correct name/email displayed
4. After login: ticket-manager is accessible without re-login (SSO)
5. Logout from either app → both apps require re-login (Single Logout)
6. Admin sees "Keycloak Admin Console" link in sidebar (replacing Users menu)
7. Regular user does not see admin link
8. All API calls include Bearer token validated by oauth2-proxy
9. Service-to-service calls use Client Credentials tokens
10. Agent context includes a fresh Keycloak token before each agent spawn
11. All existing tests pass with `AUTH_MODE=local`
12. Realm import is fully automatic on first `docker compose up`
13. Google IdP placeholder is in realm JSON (disabled, no errors on startup)
14. No `JWT_SECRET_KEY` in any service configuration (for user tokens)

---

## Principles That Must Never Be Violated

- **No service stores passwords.** Keycloak is the only password store.
- **No service issues tokens.** All tokens from Keycloak.
- **`JWT_SECRET_KEY` removed for user tokens.** Replaced by Keycloak RS256.
- **`AUTH_MODE=local` only in tests.** Never set in docker-compose.
- **JWKS is always cached.** Never fetched per-request (performance).
- **Service client secrets never logged** or exposed in API responses.
- **Google IdP disabled by default.** Enabling requires explicit env vars.
- **Token lifespan 1h for service accounts** to cover max agent runtime.
- **keycloak-js token always in memory.** Never in localStorage or cookies.
- **Users table dropped.** user_id is now Keycloak sub — no local user lookup.
