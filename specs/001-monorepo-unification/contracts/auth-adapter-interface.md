# Contract: Auth Adapter Interface

**Applies to**: All 5 backend services
**File location per service**: `src/core/auth_adapter.py`

## Interface

```python
class AuthAdapter:
    """Validates incoming JWT tokens.

    Reads AUTH_MODE from settings:
      local    — validates with local SECRET_KEY (current behaviour, unchanged)
      keycloak — validates against KEYCLOAK_JWKS_URL (not implemented in this phase)
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def verify(self, token: str) -> dict:
        """Return decoded JWT claims or raise.

        Raises:
            jose.JWTError / UnauthorizedError — invalid or expired token (AUTH_MODE=local)
            NotImplementedError — AUTH_MODE=keycloak (not yet implemented)
            ValueError — unrecognised AUTH_MODE value
        """
        ...
```

## Behaviour Contract

| AUTH_MODE | Input | Output | Side effects |
|-----------|-------|--------|--------------|
| `local` | Valid JWT signed with SECRET_KEY | `dict` of decoded claims | None |
| `local` | Expired JWT | raises `JWTError` | None |
| `local` | Tampered/invalid JWT | raises `JWTError` | None |
| `keycloak` | Any token | raises `NotImplementedError` | None |
| anything else | Any token | raises `ValueError` | None |

## FastAPI Dependency Update

The `get_current_user` dependency in each service's `src/api/dependencies.py` MUST be
updated to call `AuthAdapter(settings).verify(token)` instead of the current inline
validation call. Example:

```python
_bearer = HTTPBearer(auto_error=False)
_adapter = AuthAdapter(get_settings())

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        claims = await _adapter.verify(credentials.credentials)
        # resolve User from claims["sub"] using existing DB lookup
        return await UserRepository(db).get_by_id(claims["sub"])
    except (JWTError, UnauthorizedError):
        raise HTTPException(status_code=401, detail="Invalid token")
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Keycloak auth not configured")
```

## Non-Permitted Changes

- Do NOT change login endpoints, token generation, password hashing, or user CRUD.
- Do NOT add Keycloak user sync, SSO flows, or JWKS fetching in this phase.
- Do NOT remove user tables or session tables.
