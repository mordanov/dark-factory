# Research: Keycloak IAM Migration

**Feature**: 004-keycloak-iam-migration
**Date**: 2026-06-24
**Status**: Complete — all decisions resolved

---

## Decision 1: JWKS Caching Strategy

**Decision**: Module-level singleton `_validator` with `time.monotonic()` TTL check (300s).
No external cache dependency (no Redis, no threading.Timer).

**Rationale**: Simplest correct approach. `time.monotonic()` is safe in async context.
Module singleton means cache is shared across all requests in a process. 300s TTL satisfies
constitution minimum. On JWKS fetch failure during refresh, stale cache is used + failure logged
(constitution §XVIII: "service MUST continue using stale cache").

**Implementation pattern**:
```python
import time, httpx
from dataclasses import dataclass, field
from jose import jwt as jose_jwt

_JWKS_TTL = 300  # seconds

@dataclass
class _JwksCache:
    keys: list = field(default_factory=list)
    fetched_at: float = 0.0

_cache = _JwksCache()

async def _get_jwks(jwks_url: str) -> list:
    now = time.monotonic()
    if now - _cache.fetched_at < _JWKS_TTL and _cache.keys:
        return _cache.keys
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            resp = await c.get(jwks_url)
            resp.raise_for_status()
        _cache.keys = resp.json()["keys"]
        _cache.fetched_at = now
    except Exception as exc:
        structlog.get_logger().warning("jwks_refresh_failed", error=str(exc))
    return _cache.keys
```

**Alternatives considered**:
- `cachetools.TTLCache`: adds a dependency, no benefit over manual TTL check
- `asyncio.Lock` for refresh: not needed — JWKS fetch is idempotent; worst case two concurrent
  fetches on cold start, which is harmless

---

## Decision 2: KeycloakServiceClient Token Caching

**Decision**: Instance-level cache with `asyncio.Lock` to prevent thundering-herd on refresh.
Token is refreshed when `expires_at - time.monotonic() < 30` (30s buffer).

**Rationale**: `asyncio.Lock` is the right primitive for async coroutine concurrency (not
`threading.Lock`). The 30s buffer matches the Axios interceptor's `updateToken(30)` call,
creating a consistent "refresh before it's needed" contract. Token is stored as plain string;
never logged.

**Implementation pattern**:
```python
import asyncio, time, httpx
from dataclasses import dataclass, field

@dataclass
class _TokenCache:
    token: str = ""
    expires_at: float = 0.0

class KeycloakServiceClient:
    def __init__(self, base_url, realm, client_id, client_secret):
        self._token_url = f"{base_url}/realms/{realm}/protocol/openid-connect/token"
        self._client_id = client_id
        self._client_secret = client_secret
        self._cache = _TokenCache()
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        if time.monotonic() < self._cache.expires_at - 30 and self._cache.token:
            return self._cache.token
        async with self._lock:
            if time.monotonic() < self._cache.expires_at - 30 and self._cache.token:
                return self._cache.token
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.post(self._token_url, data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                })
                resp.raise_for_status()
            data = resp.json()
            self._cache.token = data["access_token"]
            self._cache.expires_at = time.monotonic() + data["expires_in"]
        return self._cache.token

    async def async_auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {await self.get_token()}"}
```

The double-checked locking pattern (check outside lock, then inside lock) prevents duplicate
fetches when multiple coroutines hit the refresh window simultaneously.

**Alternatives considered**:
- `threading.Lock`: wrong primitive — this is async code; would block the event loop
- Single check outside lock: causes multiple simultaneous fetches under load

---

## Decision 3: UserClaims Dataclass Shape

**Decision**: Minimal flat dataclass, not a Pydantic model. Fields: `sub`, `email`,
`preferred_username`, `roles` (list[str]), `is_admin` (bool derived from roles).

**Rationale**: UserClaims is used only in FastAPI dependency injection, never serialized to
JSON. Pydantic would add unnecessary validation overhead and import cost. `is_admin` is a
derived convenience property (`"administrator" in roles`) — not a stored claim.

```python
from dataclasses import dataclass, field

@dataclass
class UserClaims:
    sub: str
    email: str
    preferred_username: str
    roles: list[str] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return "administrator" in self.roles
```

Claims are extracted from `token_payload["realm_access"]["roles"]` (Keycloak standard format).
`preferred_username` falls back to `email` if absent (defensive for malformed tokens).

**Alternatives considered**:
- Pydantic model: unnecessary; adds ~0.5ms validation per request
- Named tuple: `is_admin` property would require a class anyway

---

## Decision 4: AUTH_MODE=local Test Token Format

**Decision**: HS256 tokens with `TEST_JWT_SECRET` env var, mimicking Keycloak claim structure.
The `realm_access.roles` claim is preserved so `UserClaims` parsing logic is identical in
both modes.

**Rationale**: Tests must not need a real Keycloak instance. The `AUTH_MODE=local` path uses
`python-jose` (already a canonical dependency) with the shared test secret. Since `UserClaims`
reads `realm_access.roles`, test tokens must include this key — otherwise tests would pass with
different claim parsing than production, which would be a false sense of safety.

```python
# Test token payload (HS256, TEST_JWT_SECRET)
{
    "sub": "test-user-uuid-1234",
    "email": "user@test.com",
    "preferred_username": "testuser",
    "realm_access": {"roles": ["user"]},
    "exp": <1 hour from now>,
    "iat": <now>
}
```

**Alternatives considered**:
- Mock the `verify()` method entirely: loses test coverage of the claims extraction logic
- Separate claim format for tests: would mask claim-parsing bugs

---

## Decision 5: Destructive Migration Strategy (users table)

**Decision**: Single Alembic migration per affected service (UIM, TM) that:
1. Creates a temp column `user_id_new TEXT`
2. Copies `id::text` (UIM) or `user_id::text` (TM) values
3. Drops tables with FKs to users
4. Drops users table
5. Recreates dropped tables with `user_id TEXT NOT NULL` (no FK)
6. `downgrade()` raises `NotImplementedError("DESTRUCTIVE: cannot undo user table removal")`

**Rationale**: Constitution §XXI mandates irreversibility explicitly. Single migration keeps
the destructive change atomic — partial migrations (e.g., drop table then recreate) in separate
files could leave the DB in an inconsistent state. The `user_id_new TEXT` approach allows
column-level backfill even if a future migration wants to populate from Keycloak sub.

**Services affected**:
- `user-input-manager`: has `users` table + `sessions.user_id UUID FK → users.id`
- `ticket-manager`: has `users` table; ticket `created_by` and `assignees` reference user IDs

**Services NOT requiring migration** (no local users table):
- orchestrator: `user_id TEXT` columns already (no FK to local users)
- context-distiller: no user_id columns
- agent-dispatcher: no user_id columns; service identity is the JWT sub
- agent-tools: stateless; no DB

**Alternatives considered**:
- Keep users table + add keycloak_sub column: violates §XXI; also creates identity ambiguity
- Multiple-step migrations: risk partial state; one atomic migration is safer

---

## Decision 6: oauth2-proxy Role in the Architecture

**Decision**: oauth2-proxy operates in Bearer-only validation mode (`skip_jwt_bearer_tokens = true`).
It validates the token against Keycloak JWKS and passes `X-Auth-Request-User` and
`X-Auth-Request-Email` headers upstream. It does NOT perform login redirects — that is
handled by keycloak-js in the frontend.

**Rationale**: Bearer-only mode means oauth2-proxy is a pure validation sidecar. It doesn't
need cookies, sessions, or redirect handling. This keeps the architecture clean: the
frontend handles the PKCE flow, nginx validates the Bearer token before passing to backend.
Backend services do their own token validation (constitution §XVIII) — oauth2-proxy is a
defense-in-depth layer at the nginx boundary, not the authoritative validator.

**Alternatives considered**:
- Full oauth2-proxy mode (with redirects): would conflict with keycloak-js PKCE flow; double
  redirect loops possible
- No oauth2-proxy, nginx validates directly: nginx lacks native JWT validation; would require
  `lua-jwt` or similar, which isn't in the alpine nginx image

---

## Decision 7: keycloak-js Integration Pattern in React

**Decision**: Single `keycloak.ts` module exports one keycloak-js instance. `authStore.ts`
wraps it with Zustand. `App.tsx` calls `initialize()` on mount; renders `<LoadingScreen />`
until `initialized === true`. No React Context for auth — Zustand is the single store
(constitution §VI).

**Rationale**: keycloak-js docs recommend a singleton instance. Zustand prevents the store
from being re-created on component unmount/remount. The `onLoad: 'login-required'` setting
means keycloak-js handles the redirect before any React component renders — no `/login` route
needed. `pkceMethod: 'S256'` is mandatory per constitution §XX.

**Token refresh**: `keycloak.updateToken(30)` is called in the Axios request interceptor.
The `onTokenExpired` handler triggers `keycloak.login()` as a fallback (browser redirect).

**Alternatives considered**:
- React Context for auth: explicitly prohibited by constitution §VI (Zustand for all state)
- Manual token storage in Zustand: keycloak-js already manages this internally; reading
  `keycloak.token` is safer than duplicating into the store

---

## Decision 8: Keycloak Client Registrations in realm-export.json

**Decision**: 7 clients required:
| Client ID | Type | Flows | Token TTL |
|-----------|------|-------|-----------|
| uim-frontend | Public (PKCE) | standard | 300s (default) |
| tm-frontend | Public (PKCE) | standard | 300s (default) |
| oauth2-proxy | Confidential | no flows | default |
| orchestrator | Confidential | serviceAccountsEnabled | 3600s |
| context-distiller | Confidential | serviceAccountsEnabled | 3600s |
| agent-dispatcher | Confidential | serviceAccountsEnabled | 3600s |
| agent-tools | Confidential | serviceAccountsEnabled | 3600s |

**Rationale**: Public clients (uim-frontend, tm-frontend) use PKCE for browser security.
Confidential clients get machine credentials. 1-hour TTL on service accounts ensures agents
running up to 600s have a valid token with margin (§XIX: "1 hour per-client override").
oauth2-proxy needs a confidential client for OIDC discovery but doesn't need service accounts.

All clients are in realm-export.json with `${VAR}` for secrets; secrets injected via env vars.

---

## Decision 9: Alembic Migration Naming Convention

**Decision**: Migration description: `"DESTRUCTIVE: drops all user data"` as mandated by §XXI.

File names:
- UIM: `{next_revision}_destructive_drop_users.py`
- TM: `{next_revision}_destructive_drop_users.py`

Both have `downgrade()` that raises:
```python
raise NotImplementedError("DESTRUCTIVE: cannot undo user table removal (constitution §XXI)")
```

---

## Decision 10: Keycloak Container startup order in docker-compose.yml

**Decision**: `postgres (healthy) → keycloak (healthy) → all app services`. The Keycloak
healthcheck polls `http://localhost:8080/realms/dark-factory` (realm endpoint, not just root).
`start_period: 60s` + `retries: 20` × `interval: 15s` = up to 5 minutes for first boot
(realm import can take 90+ seconds on cold start).

**Rationale**: Realm endpoint check (`/realms/dark-factory`) is stronger than just checking
if Keycloak started — it confirms the realm is imported and ready. This prevents race
conditions where services start with Keycloak up but realm not yet available.

**Alternatives considered**:
- `curl -f http://localhost:8080` (root): too permissive — Keycloak may be starting but realm
  import not done
- `curl -f http://localhost:8080/health/ready`: Keycloak 25 health endpoint exists but requires
  management port (9000 by default) — adds port exposure complexity
