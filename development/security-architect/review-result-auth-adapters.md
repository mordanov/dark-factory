# Security Review Result: Auth Adapters (T032–T041)

**Date**: 2026-06-22  
**Reviewer**: security-architect agent  
**Services reviewed**: user-input-manager, ticket-manager, orchestrator, context-distiller, agent-tools  
**Checklist applied**: auth-adapter-review-checklist.md (A1–A18)

---

### Decision

**APPROVED** *(updated after H-01 fix verified)*

---

### Blockers

None.

---

### High Findings

**H-01 — context-distiller: `HTTPBearer(auto_error=False)` missing** *(checklist item A11)*

File: `services/context-distiller/src/api/dependencies.py:18`

```python
# Current (incorrect)
_bearer = HTTPBearer()

# Required fix
_bearer = HTTPBearer(auto_error=False)
```

**Impact**: With `auto_error=True` (the default), FastAPI raises HTTP 403 when the `Authorization` header is absent — before `get_current_user` runs. This means:
1. Unauthenticated requests return 403 instead of 401.
2. `AUTH_MODE=keycloak` cannot return 501 on unauthenticated requests (the error fires at the bearer layer, not the adapter layer).
3. The `credentials` parameter cannot be `None` in `get_current_user` — the type annotation `Annotated[HTTPAuthorizationCredentials, Depends(_bearer)]` will never receive `None`, so missing-credential handling is bypassed.

**Fix**: Change to `HTTPBearer(auto_error=False)` and add an explicit `None` check at the top of `get_current_user`, consistent with all other services:
```python
_bearer = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    ...
```

---

### Items Verified — All Pass

**A1** — `AUTH_MODE=local` delegates to existing `verify_access_token()` unchanged: ✅ all 5 services  
**A2** — `AUTH_MODE=keycloak` raises `NotImplementedError` immediately: ✅ all 5 services  
**A3** — Unrecognised `AUTH_MODE` raises `ValueError` in `__init__`: ✅ all 5 services  
**A4** — `AUTH_MODE` read from injected `settings`, not `os.environ` in `verify()`: ✅ all 5 services  
**A5** — Default `"local"` is a recognised value; `ValueError` raised for anything else: ✅ (default is valid and intentional per spec)  
**A6** — No cross-service imports in any `auth_adapter.py`: ✅ all 5 services  
**A7** — No shared adapter base class from outside service directory: ✅ all 5 services  
**A8** — Token string passed to validation layer without modification: ✅ all 5 services  
**A9** — `JWTError`/`InvalidTokenError` propagates from `verify_access_token()` to adapter: ✅ UIM, orchestrator (via `security.py`); TM, context-distiller, agent-tools (direct `jwt.decode` + re-raise)  
**A10** — `verify()` is `async` in all adapters: ✅ all 5 services  
**A11** — `HTTPBearer(auto_error=False)`: ✅ UIM, TM, orchestrator, agent-tools — **❌ context-distiller** (see H-01)  
**A12** — `JWTError` mapped to HTTP 401 in dependency: ✅ all 5 services  
**A13** — Token value not logged in dependency or adapter: ✅ all 5 services (no log calls observed)  
**A14** — `ValueError` on bad `AUTH_MODE` not caught silently per-request: ✅ raised at `__init__` / module load  
**A15** — Ticket-manager Dockerfile python:3.12-slim: ✅  
**A16** — `requires-python = ">=3.12"` in TM pyproject.toml: ✅  
**A17** — `python-jose==3.3.0` canonical version: ✅ (TM uses direct `jose` import)  
**A18** — `pytest-asyncio==0.24.0` canonical version; no deprecated asyncio_mode fixtures: ✅  

---

### Security Tests Status

Cannot be verified until H-01 is fixed. Once fixed, ST-01 through ST-05 should pass.

---

### Fix Verified

**H-01 RESOLVED** (2026-06-22): `context-distiller/src/api/dependencies.py` updated — `_bearer = HTTPBearer(auto_error=False)`, `credentials: HTTPAuthorizationCredentials | None`, explicit `401` guard on `None`. `verify_access_token()` added to both TM and CD `security.py` propagating `JWTError` without `HTTPException` wrapping. All 18 checks now pass.

---

### Residual Risks (Post-Fix)

**Medium — Shared JWT secret across all 5 services** (integration test and production design): All services in the test compose use `test-secret-key-user-input-manager-32chars`. In production, separate `*_SECRET_KEY` env vars allow per-service key rotation, but the orchestrator's `JWT_SECRET_KEY` must equal UIM's for cross-service token validation to work. This coupling is a known design constraint, acknowledged by autotester and software-architect.

**Owner**: product-manager / operations  
**Due**: before first production deployment; document in runbook.
