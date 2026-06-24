# Security Review Result: Keycloak IAM Migration (004)

**Feature**: 004-keycloak-iam-migration  
**Date**: 2026-06-24  
**Reviewer**: Security Architect Agent  
**Scope**: All phases T001–T081

---

## Scope Reviewed

- Keycloak 25 realm configuration (`infra/keycloak/realm-export.json`, `substitute-env.sh`)
- oauth2-proxy configuration (`infra/oauth2-proxy/config.cfg`)
- nginx `auth_request` integration pattern (`contracts/nginx-auth.md`)
- `KeycloakValidator` auth adapter pattern (`contracts/auth-adapter.md`)
- `KeycloakServiceClient` Client Credentials pattern (`contracts/keycloak-service-client.md`)
- Frontend keycloak-js PKCE integration (both frontends)
- Destructive Alembic migrations (UIM + TM)
- Agent token injection (Agent Dispatcher context builder)
- Secret management (`.env.example`, docker-compose.yml)

---

## Clearance Status (as of 2026-06-24)

| Gate | Status | Notes |
|------|--------|-------|
| BLK-01 Algorithm pinning | **CLEARED** | All 6 auth_adapter.py: `algorithms=["RS256"]`/`["HS256"]` explicit |
| BLK-02 Startup fail-closed | **CLEARED** | `prefetch_jwks()` in all 6 lifespan handlers; raises RuntimeError |
| BLK-03 No AUTH_MODE=local in compose | **CLEARED** | All 6 services `AUTH_MODE: keycloak`; CI check in infra-checks.yml |
| FIND-01 Secret not in logs | **CLEARED** | UpstreamError + structlog.debug bind client_id only |
| FIND-02 No browser storage | **CLEARED** | Spy tests in both UIM + TM auth.test.ts; source code confirmed clean |
| FIND-03 Token log level | **CLEARED** | No INFO-level token exposure found in agent-dispatcher |
| FIND-04 require_admin server-side | **CLEARED** | All admin endpoints use Depends(require_admin) |
| FIND-05 cookie_secure comment | **CLEARED** | Production warning comment added to config.cfg |
| FIND-06 realm.json not host-mounted | **CLEARED** | Only realm-export.json:ro + substitute-env.sh:ro mounted |
| constitution §XXI | **CLEARED** | Both downgrade() raise NotImplementedError |
| UUID(actor.sub) in event_service | **FIXED** | services/ticket-manager/backend/src/services/event_service.py:24 — changed `UUID(actor.sub)` to `actor.sub`; actor_id column is Text post-migration |
| AuthAdapter shim | **CLEARED** | Removed from all 6 auth_adapter.py; 4 import sites use KeycloakValidator() |

**FINAL DECISION: APPROVED — all blockers and findings cleared.**

---

## Decision

**APPROVED WITH RISKS**

The architecture is sound. The design follows security best practices for OAuth2/OIDC
migrations: PKCE for browser clients, Client Credentials for services, RS256 validation,
short-lived tokens, and in-memory-only frontend storage. Three blocker-level controls must
be verified before this feature ships.

---

## Blockers

### BLK-01: Algorithm pinning in KeycloakValidator (T-05)

**What**: `python-jose` must be called with `algorithms=["RS256"]` explicitly in keycloak mode and `algorithms=["HS256"]` in local mode. If the algorithm parameter is omitted or set to `None`, the library accepts `alg: none` tokens and HS256 tokens when expecting RS256.

**Where**: `auth_adapter.py` in all 6 services — the `jwt.decode()` call.

**Required code pattern**:
```python
# keycloak mode
payload = jwt.decode(
    token,
    public_key,
    algorithms=["RS256"],          # ← MUST be explicit, never None or []
    options={"verify_exp": True},
)

# local mode
payload = jwt.decode(
    token,
    settings.test_jwt_secret,
    algorithms=["HS256"],          # ← MUST be explicit
)
```

**Test to add** (all `test_auth_adapter.py`): `test_algorithm_confusion_rejected` — craft a token with `alg: none` header; assert `UnauthorizedError` raised.

---

### BLK-02: Startup JWKS fetch — fail closed if Keycloak unreachable (T-12)

**What**: In keycloak mode, `KeycloakValidator` must attempt a JWKS fetch during `__init__` (or on first request handling start). If the fetch fails at startup, the service MUST raise `RuntimeError` and refuse to start — not silently enter a state where token validation degrades to "no validation."

**Why**: A service that starts with an empty JWKS cache will reject all tokens with `UnauthorizedError` (good), but the failure mode must be explicit and detectable, not a silent degraded state. Also, `depends_on: condition: service_healthy` in compose protects against this at orchestration level, but the application must also self-enforce.

**Required pattern**:
```python
class KeycloakValidator:
    def __init__(self):
        self._jwks: dict | None = None
        self._jwks_fetched_at: float = 0.0
        self._lock = asyncio.Lock()
        # Startup-time sync check (optional but recommended):
        # If running in keycloak mode, verify JWKS URL is reachable.
        # This is best done via a startup event in FastAPI, not __init__.
```

**FastAPI startup event** (add to `main.py` of each service):
```python
@app.on_event("startup")
async def verify_keycloak_connectivity():
    if settings.auth_mode == "keycloak":
        try:
            await _validator._fetch_jwks()
        except Exception as e:
            raise RuntimeError(f"Keycloak JWKS unreachable at startup: {e}") from e
```

**Test to add**: `test_startup_fails_if_jwks_unreachable` — mock httpx to raise `ConnectError`; assert `RuntimeError` raised during startup event.

---

### BLK-03: AUTH_MODE=local must never appear in production docker-compose.yml (T-03)

**What**: `AUTH_MODE=local` enables HS256 validation with a known test secret. If present in `infra/docker-compose.yml`, any attacker with knowledge of `test-secret-do-not-use-in-production` can forge admin tokens.

**CI check** (add to pipeline):
```bash
grep -r 'AUTH_MODE=local' infra/docker-compose.yml && echo "FAIL: AUTH_MODE=local in compose" && exit 1 || true
grep -r 'test-secret-do-not-use-in-production' infra/docker-compose.yml && echo "FAIL: test secret in compose" && exit 1 || true
```

**KeycloakValidator unrecognized mode**: If `AUTH_MODE` is neither `keycloak` nor `local`, the service MUST fail startup with `ConfigurationError("Unrecognised AUTH_MODE: {value}")` — never fall through to a permissive default.

---

## High / Medium Findings

### FIND-01 (High): Client secret must not appear in logs or exceptions

**Applies to**: `keycloak_client.py` in all 6 services — `get_token()` error handling.

**Required**:
- `UpstreamError` message: `f"Keycloak token endpoint returned {response.status_code}"` — no secret.
- `structlog.get_logger().error("kc_token_fetch_failed", status=code, client_id=self.client_id)` — no `client_secret`.

**Code review check**: Search for `client_secret` in all log/exception messages.

---

### FIND-02 (High): Access token must never reach browser storage

**Applies to**: both `authStore.ts` rewrites (UIM + TM).

**Required**: Vitest test that spies on `localStorage.setItem` and `sessionStorage.setItem` — both must never be called during `initialize()` or any token operation.

**keycloak-js default**: The keycloak-js adapter holds tokens in the JS object in memory. Do not call `keycloak.token` and then write it to storage. `getToken()` returns the in-memory token from the keycloak-js object; it must not be persisted by the store.

---

### FIND-03 (High): Agent-injected token must not appear in INFO-level logs

**Applies to**: `agent-dispatcher/src/services/context_builder.py` (T061).

**Required**:
- Context injection uses `DEBUG` level for full context text.
- INFO-level log of agent spawn includes only `agent_id`, `dispatcher_id`, `token_expiry` — not the token value.

---

### FIND-04 (High): `require_admin` must be server-side Depends on every admin endpoint

**Applies to**: All admin endpoints across UIM and TM backends (T038, T039, T045, T046).

**Required**: Every endpoint that performs privileged operations (user management, role changes, admin-only data) must use `Depends(require_admin)`, not just `Depends(get_current_user)`.

**Code review check**: Search `backend/src/api/v1/` for endpoints that previously required `role == "administrator"` — confirm all now use `Depends(require_admin)`.

---

### FIND-05 (Medium): oauth2-proxy `cookie_secure = false` is dev-only

**Applies to**: `infra/oauth2-proxy/config.cfg` (T003).

**Required**: Add comment to `config.cfg`:
```
# PRODUCTION: set cookie_secure = true (requires HTTPS)
cookie_secure = false
```

Document in `infra/KEYCLOAK.md` (T080): "Before going to production, set `cookie_secure = true` in `infra/oauth2-proxy/config.cfg` and ensure nginx terminates TLS."

---

### FIND-06 (Medium): realm.json must not be volume-mounted to host

**Applies to**: `infra/docker-compose.yml` Keycloak service volumes (T004).

**Required**: Only `realm-export.json` (read-only) and `substitute-env.sh` (read-only) are mounted. The output `realm.json` lives entirely inside the container.

**Verify**: `docker compose config | grep -A5 keycloak` — confirm no host bind for `realm.json`.

---

## Required Tests (Summary)

See `threat-model-004-keycloak.md` ST-01 through ST-18 for the full test matrix.

Priority tests that must exist before Phase 2 ships:

| Priority | Test | File | Notes |
|----------|------|------|-------|
| Blocker | algorithm confusion rejection | test_auth_adapter.py (all 6) | `alg:none` and HS256-in-keycloak-mode |
| Blocker | startup JWKS failure raises RuntimeError | test_auth_adapter.py (all 6) | keycloak mode only |
| Blocker | unrecognised AUTH_MODE raises ConfigurationError | test_auth_adapter.py (all 6) | |
| High | client secret not in UpstreamError | test_keycloak_client.py (services with outbound calls) | |
| High | localStorage never written | authStore.test.ts (UIM + TM) | Vitest spy |
| High | sessionStorage never written | authStore.test.ts (UIM + TM) | Vitest spy |
| High | require_admin returns 403 for user role | integration test | |

---

## Residual Risks

See `threat-model-004-keycloak.md` Residual Risks section.

Summary of formally accepted residuals:
- **Token replay (300s window)**: accepted; TTL can be reduced for production.
- **Agent 1h non-revocable token**: accepted; manual Keycloak revocation available.
- **No SIEM for Keycloak audit events**: deferred; future work.

---

## Implementation Guardrails for Agents

### For Backend Agent (T007–T024, T038–T063)

1. **auth_adapter.py**: Always pass `algorithms=["RS256"]` to `jwt.decode()` in keycloak mode, `algorithms=["HS256"]` in local mode. Never `None`.
2. **auth_adapter.py**: `KeycloakValidator` must attempt JWKS fetch in a FastAPI startup event and raise `RuntimeError` on failure in keycloak mode.
3. **auth_adapter.py**: If `AUTH_MODE` is not `keycloak` or `local` → `ConfigurationError` at startup.
4. **keycloak_client.py**: `UpstreamError` must not contain `client_secret`. structlog must not bind `client_secret`.
5. **All route handlers**: Admin endpoints use `Depends(require_admin)`, not `Depends(get_current_user)`.
6. **context_builder.py**: Log agent context at DEBUG; INFO-level logs must redact the token value.

### For Frontend Agent (T025–T036, T047–T052)

1. **authStore.ts**: Never call `localStorage.setItem()`, `sessionStorage.setItem()`, or `document.cookie =` with token data. Tokens live in keycloak-js object in memory.
2. **authStore.ts**: `getToken()` calls `keycloak.updateToken(30)` — 30s buffer before expiry refresh. This is already in the contract; ensure it is not changed to a non-positive value.
3. **keycloak.ts**: Use `pkceMethod: 'S256'` in keycloak-js init config.
4. **authStore.test.ts**: Add Vitest spies on `localStorage.setItem` and `sessionStorage.setItem` — both must never be called.

### For DevOps Agent (T001–T006)

1. **docker-compose.yml**: No `AUTH_MODE=local` in any service definition. No `test-secret-do-not-use-in-production` in any env block.
2. **docker-compose.yml**: Keycloak service healthcheck must poll `http://localhost:8080/realms/dark-factory` with `retries: 20`, `start_period: 60s`.
3. **docker-compose.yml**: All application services must have `depends_on: keycloak: condition: service_healthy`.
4. **oauth2-proxy/config.cfg**: Comment that `cookie_secure = false` is dev-only; production requires `true`.
5. **Keycloak volumes**: Only `realm-export.json:ro` and `substitute-env.sh:ro` mounted; no host volume for `realm.json`.

### For Autotester Agent (T070–T079)

The security test matrix (ST-01 to ST-18) in `threat-model-004-keycloak.md` is the authoritative list. Priority additions beyond the 8 tests in contracts/auth-adapter.md:

1. Add `test_algorithm_confusion_rejected` — `alg: none` token raises `UnauthorizedError`.
2. Add `test_unrecognised_auth_mode_raises` — `AUTH_MODE=invalid` raises `ConfigurationError` at init.
3. Add `test_startup_fails_if_jwks_unreachable` (keycloak mode) — mocked httpx `ConnectError` raises `RuntimeError`.
4. Add `test_client_secret_not_in_upstream_error` in `test_keycloak_client.py`.
5. Add `test_localStorage_never_written` and `test_sessionStorage_never_written` in frontend authStore tests.

### For Code Reviewer Agent

Security-specific checklist to apply during review:

- [ ] All `jwt.decode()` calls have explicit `algorithms=[...]` — never `None`.
- [ ] No `AUTH_MODE=local` or `test-secret-do-not-use-in-production` in docker-compose.yml.
- [ ] No `client_secret` in any log statement or exception message in `keycloak_client.py`.
- [ ] No `localStorage.setItem` / `sessionStorage.setItem` in `authStore.ts`.
- [ ] All admin endpoints use `Depends(require_admin)`, not `Depends(get_current_user)`.
- [ ] Agent context builder logs token at DEBUG level only.
- [ ] Keycloak healthcheck and `depends_on` present for all application services.
- [ ] `realm.json` not volume-mounted to host; only `realm-export.json:ro` mounted.

---

## Follow-Up Items

| ID | Item | Owner | Due |
|----|------|-------|-----|
| FU-01 | Confirm CI check for `AUTH_MODE=local` is added to pipeline | DevOps | Phase 1 complete |
| FU-02 | Confirm algorithm-pinning and startup JWKS tests are added | Autotester | Phase 2 complete |
| FU-03 | Confirm `cookie_secure = true` documented in KEYCLOAK.md | DevOps | T080 |
| FU-04 | Review OQ-02: agent token rotation for runs > 1 hour | Product / Backend | Post-MVP |
| FU-05 | Review OQ-03: agent token revocation on compromise | Security / DevOps | Post-MVP |
