# Contract: KeycloakValidator (auth_adapter.py)

**Applies to**: All 6 backend services (replaces existing `AuthAdapter` stub)
**Date**: 2026-06-24

---

## Interface

```python
# src/core/auth_adapter.py (each service — identical pattern)

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


class UnauthorizedError(Exception):
    """Raised when token validation fails."""


class KeycloakValidator:
    async def verify(self, token: str) -> UserClaims:
        """Validate a Bearer token and return claims.

        AUTH_MODE=keycloak: RS256, JWKS from Keycloak (cached ≥300s)
        AUTH_MODE=local: HS256, TEST_JWT_SECRET (tests only)

        Raises:
            UnauthorizedError — invalid signature, expired, malformed, missing claims
        """
```

---

## Behaviour Contracts

### C-AUTH-01: Valid token returns UserClaims
- Input: valid Bearer token (RS256 in keycloak mode; HS256 in local mode)
- Output: `UserClaims(sub=..., email=..., preferred_username=..., roles=[...])`
- Guarantee: `sub` is always non-empty; `email` is always non-empty
- If `preferred_username` absent in claims: fall back to `email` value

### C-AUTH-02: Invalid/expired token raises UnauthorizedError
- Input: expired token, wrong signature, malformed JWT, empty string
- Output: raises `UnauthorizedError`
- HTTP layer converts to 401 with `{"detail": "Not authenticated"}`

### C-AUTH-03: Missing `realm_access.roles` yields empty roles list
- Input: valid token without `realm_access` or `realm_access.roles` key
- Output: `UserClaims(..., roles=[], is_admin=False)`
- Does NOT raise — missing roles = regular user

### C-AUTH-04: JWKS cached ≥300s (keycloak mode only)
- First call: fetches JWKS from `{keycloak_base_url}/realms/{realm}/protocol/openid-connect/certs`
- Subsequent calls within 300s: return cached JWKS, no HTTP call
- After 300s: refresh attempted; on failure: use stale cache + log warning, do NOT reject requests

### C-AUTH-05: AUTH_MODE=local uses HS256 with TEST_JWT_SECRET
- Algorithm: HS256
- Key: `settings.test_jwt_secret` value
- Token shape: identical to Keycloak token (must include `realm_access.roles`)
- Must NEVER be used in production docker-compose (enforced by constitution §XVIII)

---

## FastAPI Dependency Pattern (all services)

```python
# src/api/dependencies.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from src.core.auth_adapter import KeycloakValidator, UserClaims, UnauthorizedError

_bearer = HTTPBearer(auto_error=False)
_validator = KeycloakValidator()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserClaims:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return await _validator.verify(credentials.credentials)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

async def require_admin(claims: UserClaims = Depends(get_current_user)) -> UserClaims:
    if not claims.is_admin:
        raise HTTPException(status_code=403, detail="Administrator role required")
    return claims
```

**Key change**: `get_current_user` no longer performs a database lookup. Identity is fully
derived from the JWT claims. Handler signatures change from `User` (ORM object) to `UserClaims`.

---

## Test Contract: unit/test_auth_adapter.py (per service)

| Test | Scenario | Expected |
|------|----------|----------|
| `test_valid_user_token_returns_claims` | Valid HS256 token, AUTH_MODE=local | UserClaims with correct sub/email/roles |
| `test_valid_admin_token_has_is_admin_true` | Token with `["user","administrator"]` roles | `claims.is_admin == True` |
| `test_invalid_token_raises_unauthorized` | Garbage string | `UnauthorizedError` raised |
| `test_expired_token_raises_unauthorized` | Token with past `exp` | `UnauthorizedError` raised |
| `test_missing_realm_access_returns_empty_roles` | Valid token, no `realm_access` key | `claims.roles == []`, no error |
| `test_keycloak_mode_fetches_jwks` | AUTH_MODE=keycloak, mock httpx | httpx.get called once with correct JWKS URL |
| `test_jwks_cached_for_ttl` | Two calls within 300s | httpx.get called exactly once |
| `test_jwks_refreshed_after_ttl_expired` | Two calls, second after TTL | httpx.get called twice |
