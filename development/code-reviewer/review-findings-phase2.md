# Code Review: Phase 2 — Backend Auth Patterns (All Services)

**Feature**: 004-keycloak-iam-migration  
**Phase**: 2 (T007–T024) + Phase 4 (T038–T046)  
**Reviewer**: code-reviewer agent  
**Date**: 2026-06-24  
**Scope**: `auth_adapter.py`, `config.py`, `main.py` (lifespan), `dependencies.py` / `security.py`,
`tests/conftest.py`, `tests/unit/test_auth_adapter.py` — all 6 backend services

---

## Code Review Result

### Decision

**CHANGES REQUESTED**

The `KeycloakValidator` core, all configs, lifespan handlers, and conftest fixtures are correct
and uniform. Three services (orchestrator, context-distiller, agent-dispatcher) have a
mismatched exception handler that silently promotes `UnauthorizedError` to HTTP 500 instead of
401 — a functional blocker. One minor test quality issue with the BLK-02 test remains.

---

### Scope Reviewed

- T007–T012 `auth_adapter.py` — all 6 services (KeycloakValidator, UserClaims, prefetch_jwks)
- T013–T018 `config.py` — all 6 services (KC vars, old JWT vars removed)
- T019–T024 `tests/conftest.py` — all 6 services (set_auth_mode, user_token, admin_token)
- T038 UIM `dependencies.py` — rewrite to KeycloakValidator
- T039 TM `security.py` — rewrite to KeycloakValidator
- T040–T044 auth endpoint/router deletion
- T045–T046 route handler migration to UserClaims
- `tests/unit/test_auth_adapter.py` — BLK-01/02/03 test suite

---

### Summary

**auth_adapter.py (T007–T012) — PASS across all 6 services.**  
All 6 `auth_adapter.py` files are uniform and correct:
- `algorithms=["RS256"]` explicit in `jwt.decode()` for keycloak mode — BLK-01 satisfied
- `algorithms=["HS256"]` explicit for local mode — no `None` possible
- JWKS cached with `time.monotonic()`, TTL=300s; stale cache on refresh failure + warning logged
- Unknown `auth_mode` raises `ValueError` — BLK-03 partially satisfied
- `prefetch_jwks()` raises `RuntimeError` on connection failure when no stale cache — BLK-02 satisfied
- `UserClaims` dataclass embedded per-service (Principle I compliant)
- `test_jwt_secret = "test-secret-do-not-use-in-production"` in all 6 configs — AI-06 satisfied

**Lifespan handlers (BLK-02) — PASS across all 6 services.**  
All 6 `main.py` / `sidecar.py` have been updated to call `await prefetch_jwks()` in their
lifespan. Startup fails-closed if Keycloak is unreachable with no stale cache.

**configs (T013–T018) — PASS.**  
KC vars present in all 6; old JWT secret vars removed. Ticket-manager config is clean.

**conftest.py (T019–T024) — PASS across all 6 services.**  
`set_auth_mode` is `autouse=True`, sets `AUTH_MODE=local` and `TEST_JWT_SECRET`, and clears
`get_settings()` lru_cache before/after. Token fixtures use `realm_access.roles` shape.

**UIM dependencies.py (T038) — PASS.**  
Correctly imports `KeycloakValidator, UnauthorizedError, UserClaims`; `get_current_user` returns
`UserClaims`; catches `UnauthorizedError`; no DB lookup. Matches contract.

**TM security.py (T039) — PASS with a minor note.**  
Correctly uses `KeycloakValidator`; `get_current_user` returns `UserClaims`; catches
`UnauthorizedError`. Retains `require_role("administrator")` which is functionally correct for
the "administrator" case (callers in `admin.py` and `orchestrator.py`). `bcrypt`, `hash_password`,
`create_access_token`, `decode_access_token` all removed.

**TM auth endpoints (T040–T041) — PASS.**  
`services/ticket-manager/backend/src/api/v1/auth.py` deleted. Auth router absent from TM router.

**TM/UIM router cleanup (T043–T044) — PASS.**  
UIM `main.py` no longer imports `auth` or `users` routers. TM router has no auth router.

**TM admin.py — PASS.**  
All admin endpoints return HTTP 410 GONE with message pointing users to Keycloak Admin Console.
No DB calls. Correctly guards with `require_role("administrator")`.

**TM/UIM route handlers (T045–T046) — PASS (TM confirmed, UIM to be verified in Phase 4 review).**  
TM `tickets.py`, `users.py` accept `UserClaims` from `get_current_user`. No ORM `User` in
route signatures.

**agent-tools utils/auth.py — PASS.**  
`make_service_jwt()` (which referenced removed `settings.jwt_secret_key`) deleted. Only
`verify_token()` remains, now using `KeycloakValidator`. `document_store.py` migrated to use
`get_kc_client().async_auth_headers()` (Phase 6 work).

**Orchestrator, context-distiller, agent-dispatcher dependency layer — BLOCKER.**  
All three services now import `KeycloakValidator` correctly but their `_verify_token`/
`get_current_user` exception handlers catch `JWTError` and `NotImplementedError`. 
`KeycloakValidator.verify()` raises neither of these — it catches `JWTError` internally and
re-raises as `UnauthorizedError`. The result: invalid tokens cause `UnauthorizedError` to 
propagate uncaught to FastAPI's default handler, returning HTTP 500 instead of 401.

---

### Blockers

#### Blocker: 3 services catch `JWTError`/`NotImplementedError` but `KeycloakValidator` raises `UnauthorizedError` — invalid tokens return HTTP 500

**Affected files**:
- `services/orchestrator/src/api/dependencies.py:29–31`
- `services/context-distiller/src/api/dependencies.py:33–41`
- `services/agent-dispatcher/src/api/v1/runs.py:31`

**Issue**: All three files were updated to import `KeycloakValidator` but their `except` blocks
were not updated to match. `KeycloakValidator.verify()` raises only `UnauthorizedError` and
`ValueError`. `JWTError` is caught internally and wrapped. `NotImplementedError` is never raised.
Current catch blocks:

```python
# orchestrator/context-distiller
except JWTError as exc:
    raise HTTPException(status_code=401, ...)  # never fires
except NotImplementedError as exc:
    raise HTTPException(status_code=501, ...)  # never fires
# UnauthorizedError falls through → HTTP 500

# agent-dispatcher
except (JWTError, NotImplementedError) as exc:
    raise HTTPException(status_code=401, ...)  # never fires
```

**Impact**: Any request with an invalid, expired, or malformed token to these 3 services returns
HTTP 500 instead of 401. This also means the `set_auth_mode` test fixtures will produce 500s in
integration tests, masking auth failures as server errors.

**Required action**: Update all three files to match the contract pattern:

```python
from src.core.auth_adapter import KeycloakValidator, UnauthorizedError, UserClaims

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> UserClaims:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return await _validator.verify(credentials.credentials)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
```

For agent-dispatcher `runs.py`, also update the return type annotation from `dict` to
`UserClaims` and import `UserClaims, UnauthorizedError` alongside `KeycloakValidator`.

**Evidence**: `auth_adapter.py` line 49–50 wraps `JWTError` into `UnauthorizedError`;
`contracts/auth-adapter.md` specifies the exception contract.

---

### Minor Findings

#### Minor: `test_startup_fails_if_jwks_unreachable` tests `_get_jwks()` directly, not `prefetch_jwks()`

**Location**: `tests/unit/test_auth_adapter.py:293` (UIM; same structure in all 5 services)  
**Issue**: The test calls `validator._get_jwks(get_settings())` and accepts either
`(UnauthorizedError, RuntimeError)`. But `_get_jwks()` raises `UnauthorizedError`; only
`prefetch_jwks()` raises `RuntimeError`. The test does not verify the lifespan integration — a
regression removing `prefetch_jwks()` from `main.py` would not be caught.  
**Required action**: Add a targeted test for `prefetch_jwks()`:

```python
@pytest.mark.asyncio
async def test_prefetch_jwks_raises_runtime_error_on_connection_failure(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "keycloak")
    with patch("src.core.auth_adapter.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        from src.core.auth_adapter import prefetch_jwks
        with pytest.raises(RuntimeError, match="JWKS unreachable"):
            await prefetch_jwks()
```

**Evidence**: BLK-02 contract; software architect blocking finding.

---

### Passed Checks

| Check | Result | Notes |
|-------|--------|-------|
| BLK-01: `algorithms=["RS256"]` in keycloak mode `jwt.decode()` | PASS | All 6 |
| BLK-01: `algorithms=["HS256"]` in local mode | PASS | All 6 |
| BLK-02: `prefetch_jwks()` raises `RuntimeError` on unreachable JWKS | PASS | All 6 lifespan handlers updated |
| BLK-03: unknown `AUTH_MODE` raises `ValueError` | PASS | All 6 |
| AI-06: `test_jwt_secret` default = `"test-secret-do-not-use-in-production"` | PASS | All 6 |
| JWKS TTL = 300s, `time.monotonic()` | PASS | All 6 |
| Stale JWKS on refresh failure + `log.warning` | PASS | All 6 |
| `UserClaims` embedded per-service (not shared library) | PASS | Principle I satisfied |
| `set_auth_mode` autouse with `cache_clear()` | PASS | All 6 conftest.py |
| Token fixtures: `realm_access.roles` shape | PASS | All 6 conftest.py |
| TM `auth.py` (local login endpoints) deleted | PASS | File absent |
| TM/UIM `get_current_user` returns `UserClaims`, no DB lookup | PASS | UIM + TM |
| TM admin endpoints return 410 GONE | PASS | Correct migration |
| TM `bcrypt`, `create_access_token`, `decode_access_token` removed | PASS | |
| TM/UIM route handlers accept `UserClaims` | PASS | TM confirmed |
| `agent-tools` `make_service_jwt()` deleted | PASS | Old JWT secret ref gone |
| AUTH_MODE=local never in docker-compose.yml | PASS (Phase 1) | BLK-03 infra check |

---

### Security Checklist

- [x] `algorithms=["RS256"]` explicit (BLK-01)
- [x] Startup fails-closed on JWKS unreachable (BLK-02)
- [x] Unknown AUTH_MODE raises (BLK-03)
- [x] No `algorithms=None` path possible
- [x] `test_jwt_secret` default is clearly non-production value
- [ ] **FAIL**: Orchestrator, context-distiller, agent-dispatcher: `UnauthorizedError` uncaught → HTTP 500

---

### Required Follow-Up

| ID | Action | Owner | Priority |
|----|--------|-------|----------|
| R2-01 | Fix `orchestrator/src/api/dependencies.py` exception handler: catch `UnauthorizedError`, return `UserClaims` | backend | **Blocker** |
| R2-02 | Fix `context-distiller/src/api/dependencies.py` exception handler: same fix as R2-01 | backend | **Blocker** |
| R2-03 | Fix `agent-dispatcher/src/api/v1/runs.py` exception handler: catch `UnauthorizedError` | backend | **Blocker** |
| R2-04 | Add `test_prefetch_jwks_raises_runtime_error_on_connection_failure` to all 6 `test_auth_adapter.py` | autotester | Minor |
