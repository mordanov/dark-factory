# Architecture Review: Keycloak IAM Migration

**Reviewer**: software-architect agent
**Date**: 2026-06-24
**Scope**: contracts/auth-adapter.md, contracts/keycloak-service-client.md,
  contracts/nginx-auth.md, contracts/keycloak-realm.md, data-model.md,
  research.md, quickstart.md, spec.md, plan.md, tasks.md
**Status**: APPROVED — all 3 security blockers VERIFIED ✅; 8 advisory action items (non-blocking)

## Implementation Verification (Phase 2)

| Blocker | Status | Notes |
|---------|--------|-------|
| BLK-01: `algorithms=["RS256"]` pinned | ✅ VERIFIED | All 6 auth_adapter.py files confirmed |
| BLK-02: Startup fail-closed on JWKS | ✅ VERIFIED | `prefetch_jwks()` added to all 6 lifespan handlers; raises `RuntimeError` on cold-cache failure; verified by security-architect |
| BLK-03: No AUTH_MODE=local in docker-compose | ✅ VERIFIED | CI check added by devops |

---

## Security Blockers (Binding — Added Post Security-Architect Review)

These 3 blockers were identified by security-architect and declared binding by product-manager.
No phase ships without all 3 addressed. Code Reviewer must verify on every PR.

| ID | Blocker | Applies To |
|----|---------|-----------|
| BLK-01 | Pin `algorithms=["RS256"]` in `jwt.decode()` — never `None` | All 6 KeycloakValidator implementations (T007-T012) |
| BLK-02 | Fail closed at startup: if `AUTH_MODE=keycloak` and JWKS endpoint unreachable, raise `RuntimeError` — do NOT start in degraded mode | All 6 services |
| BLK-03 | `AUTH_MODE=local` must never appear in `infra/docker-compose.yml` — add CI grep check | DevOps T004 + T079 |

**Architectural impact of BLK-01**: The `KeycloakValidator.verify()` contract in auth-adapter.md
must be updated to explicitly state: `algorithms=["RS256"]` is always passed to `jwt.decode()`.
This prevents algorithm confusion attacks (e.g., `alg: "none"` or HS256 with public key as secret).

**Architectural impact of BLK-02**: The JWKS cache initialization pattern must include a startup
prefetch. At service startup (`lifespan` or `on_startup` FastAPI hook), `_get_jwks()` must be
called. If it raises, service must not accept requests. This is additive to C-AUTH-04 (stale
cache during runtime is still correct — BLK-02 only applies to cold-start).

**Suggested startup pattern** (to be added to auth-adapter.md contract):
```python
# In each service's lifespan / startup handler:
if settings.auth_mode == "keycloak":
    try:
        await _get_jwks(jwks_url)  # prefetch; raises on failure
    except Exception as exc:
        raise RuntimeError(f"Keycloak JWKS unreachable at startup: {exc}") from exc
```

---

## Summary Verdict

All five contracts are internally consistent, constitution-compliant, and architecturally sound.
The design correctly implements defense-in-depth (nginx boundary + per-service validation),
cache-first token handling, per-service isolation, and irreversible migration semantics.

The one gap identified below (C-KC-401-RETRY) is a **known risk** already flagged in tasks.md
and must be resolved during T059 implementation.

---

## Contract Reviews

### 1. KeycloakValidator (auth-adapter.md) — ✅ APPROVED

**Interface completeness**: Complete. `UserClaims`, `UnauthorizedError`, `verify()` signature,
`get_current_user` dependency, `require_admin` are all specified with correct Python types.

**Behaviour contracts**:
- C-AUTH-01–05 cover all observable behaviours including the stale-JWKS fallback (FR-017).
- The fallback is implemented as: try refresh → on exception log warning + return stale keys.
  This is correct; service stays available during transient Keycloak unavailability up to TTL.

**Cache concern — ADVISORY (non-blocking)**:
The `_JwksCache` singleton in research.md Decision 1 uses a module-level `_cache` object
shared across all `KeycloakValidator` instances. If the module is imported in multiple async
workers (e.g., Uvicorn with multiple workers), each process has its own cache — this is
correct. However there is a subtle race in the refresh path: two coroutines can both detect
a stale cache and both call `_get_jwks()` concurrently. The JWKS fetch is idempotent, so
the last writer wins with no data corruption. Implementation note: the contract spec says
"No `asyncio.Lock` for JWKS refresh" (Decision 1 research.md) — this is acceptable given
idempotency, but implementors should add a note in the code so maintainers don't add a lock
unnecessarily.

**AUTH_MODE=local test isolation**: Correct design. The `set_auth_mode` fixture with
`monkeypatch.setenv("AUTH_MODE","local")` ensures test mode is request-scoped, not
process-global. Constitution §XVIII prohibition on AUTH_MODE=local in docker-compose.yml
is correctly enforced.

**Fitness function**: The 8 test cases in the test contract cover all behaviour contracts.
Test `test_jwks_refreshed_after_ttl_expired` requires `time.monotonic()` mocking — implementors
should use `unittest.mock.patch("time.monotonic", ...)` or a test-only seam.

---

### 2. KeycloakServiceClient (keycloak-service-client.md) — ✅ APPROVED WITH REQUIRED NOTE

**Interface completeness**: Complete. `get_token()`, `async_auth_headers()`, singleton factory,
`UpstreamError`, and double-checked locking are all specified. `asyncio.Lock` is the correct
primitive for async coroutine concurrency.

**Critical gap — 401 RETRY for orchestrator tm_client (C-KC-401-RETRY)**:
The old `tm_client/client.py` pattern re-authenticated on 401 (explicit retry). The new
`KeycloakServiceClient` does NOT have built-in 401 retry logic — if TM returns 401 because
the cached token is no longer valid (race between cache and TM validation), the call fails.
This is already flagged in tasks.md T059 note: _"add 401 retry logic if needed"_.

**Decision**: The `KeycloakServiceClient` contract deliberately does NOT include 401 retry
at the client level. The correct pattern is: the **caller** (tm_client, reporter.py) must
handle a 401 response by calling `get_token()` again (which will force a refresh by
invalidating cache) and retrying once.

**Recommendation for T059 / T060 callers**:
```python
# Suggested 401 retry pattern for tm_client/client.py and reporter.py
async def _call_with_retry(self, method, url, **kwargs):
    resp = await self._client.request(method, url,
        headers=await get_kc_client().async_auth_headers(), **kwargs)
    if resp.status_code == 401:
        # Force token refresh by clearing the cache
        get_kc_client()._cache.token = ""
        get_kc_client()._cache.expires_at = 0.0
        resp = await self._client.request(method, url,
            headers=await get_kc_client().async_auth_headers(), **kwargs)
    resp.raise_for_status()
    return resp
```
Alternatively, expose a `invalidate()` method on `KeycloakServiceClient` to make this
less fragile. The implementation team should pick one approach and apply it consistently.

**Secret protection (C-KC-04)**: Confirmed — `UpstreamError` message must not include
`client_secret`. structlog binds `client_id` only. This must be verified at T079 (ruff + log
audit).

---

### 3. nginx auth_request (nginx-auth.md) — ✅ APPROVED

**Architecture**: Double validation is correct and intentional:
1. nginx `auth_request` → oauth2-proxy validates Bearer against JWKS (boundary check)
2. Each backend `KeycloakValidator.verify()` validates again and extracts claims (authoritative)

This prevents a misconfigured nginx from bypassing backend auth. The two layers are
independent failure modes, which is the correct defense-in-depth posture.

**oauth2-proxy `skip_jwt_bearer_tokens = true`**: Correct. Bearer-only mode means
oauth2-proxy validates the token without initiating login redirects. Frontend keycloak-js
handles PKCE. No cookie-based sessions are created at the nginx layer.

**`pass_access_token = false`**: Correct. The token is NOT forwarded to the backend by
oauth2-proxy. The backend reads the original `Authorization: Bearer` header directly.
The `X-Auth-User` and `X-Auth-Email` headers are informational (for logging/tracing) —
backends MUST NOT use them as authoritative identity; they MUST use the JWT claims from
their own `KeycloakValidator.verify()` call.

**Advisory: X-Auth-User header injection risk**:
The nginx template forwards `X-Auth-User` and `X-Auth-Email` from oauth2-proxy headers to
the backend. If an attacker bypasses nginx and calls the backend directly on its internal
port (within the Docker network), they could inject arbitrary `X-Auth-User` headers.
Mitigation: backends MUST NOT trust these headers for any authorization decision — only the
`Authorization: Bearer` JWT is authoritative. The current contract correctly documents this
(C-NGINX-04: "Backend services still validate tokens independently"). Implementation team
should verify no route handler reads `X-Auth-User` header.

**Missing location: backend internal health checks**:
If services expose `/health` or `/readiness` endpoints under `/api/`, the `auth_request`
guard would reject Docker healthcheck calls. Confirm healthcheck endpoints are at the
service root (`/health`) NOT under `/api/`. Current service topology uses `GET /` or
`GET /health` for healthchecks — this is fine as-is.

---

### 4. Keycloak Realm Configuration (keycloak-realm.md) — ✅ APPROVED

**Client registrations**: All 9 clients (uim-frontend, tm-frontend, oauth2-proxy,
orchestrator, context-distiller, agent-dispatcher, agent-tools, user-input-manager,
ticket-manager) match the service registry in CLAUDE.md. Client ID names match
`keycloak_client_id` values in data-model.md. ✅

**Token lifespans**:
- User tokens (uim-frontend, tm-frontend): 300s (5 min) — appropriate for interactive sessions.
- Service account tokens (all confidential clients): 3600s (1 hour) — required for agent runs.
- Agent Dispatcher requirement (FR-009: agents receive token valid ≥ 1 hour): satisfied by
  agent-dispatcher client's 3600s TTL. Agents receive a freshly-minted token at spawn time,
  so they have up to 1 hour from spawn. ✅

**realm-export.json envsubst approach**:
`substitute-env.sh` uses bare `envsubst` (no variable list). This means ALL environment
variables will be substituted in the JSON, not just the intended `${KC_*}` vars.
Risk: if any JSON value coincidentally matches an env variable name, it will be substituted
unexpectedly.

**Recommendation**: Restrict envsubst to known variables:
```bash
envsubst '${KC_BOOTSTRAP_ADMIN_USERNAME} ${KC_BOOTSTRAP_ADMIN_EMAIL} \
  ${KC_BOOTSTRAP_ADMIN_PASSWORD} ${KC_DB_USERNAME} ${KC_DB_PASSWORD} \
  ${KC_HOSTNAME} ${OAUTH2_PROXY_CLIENT_SECRET} ${KC_ORCHESTRATOR_CLIENT_SECRET} \
  ${KC_DISTILLER_CLIENT_SECRET} ${KC_DISPATCHER_CLIENT_SECRET} \
  ${KC_AGENT_TOOLS_CLIENT_SECRET} ${KC_UIM_CLIENT_SECRET} ${KC_TM_CLIENT_SECRET} \
  ${GOOGLE_CLIENT_ID} ${GOOGLE_CLIENT_SECRET} \
  ${UIM_FRONTEND_URL} ${TM_FRONTEND_URL}' \
  < "$INPUT" > "$OUTPUT"
```
This is a minor hardening fix for T002.

**Bootstrap admin `temporary: true`**: Correct. Forces password change on first login.
Note for operators: if Keycloak is re-imported from realm-export.json after initial setup
(e.g., via the teardown scenario in quickstart.md), the bootstrap admin will require another
password change. Acceptable for dev; document in KEYCLOAK.md (T080).

**realm name `dark-factory`**: Fixed per §XVII. The `kc.sh start` command uses
`--hostname=${KC_HOSTNAME}` but realm name is hardcoded in config everywhere. This is
intentional and correct per constitution.

---

### 5. Data Model (data-model.md) — ✅ APPROVED

**Schema changes coverage**: All tables with FK to `users` are identified and altered
in both UIM (prompt_sessions) and TM (tickets, ticket_assignments, ticket_events,
progress_updates, refresh_tokens). ✅

**Migration correctness (UIM, T064)**:
The tasks.md description for T064 mentions: `(1) add user_id_text TEXT, (2) UPDATE … SET
user_id_text = user_id::text, (3) drop FK, (4) drop users, (5) rename/alter column`.
The data-model.md Decision 5 research correctly notes this approach preserves data during
the column-type change.

**Advisory: PostgreSQL UUID cast to TEXT**:
`user_id_text = user_id::text` (UIM) will produce `"a3f1b2c4-..."` format — which matches
Keycloak sub format. Correct.

For TM: `created_by_id`, `user_id`, `actor_id` are `UUID FK` — the same `::text` cast applies.
After migration, all user identity columns hold UUID strings matching Keycloak sub format.

**Permanent data loss**: Constitution §XXI mandates this and `downgrade()` raises
`NotImplementedError`. The migration is atomic per Decision 5. Implementation must test
against a throwaway DB first (noted in tasks.md).

**New configuration fields**: data-model.md lists all added/removed config fields per service.
Cross-checked against tasks.md T013–T018 — field lists match. ✅

**`test_jwt_secret` default value**: `"test-secret-do-not-use"` (data-model.md) vs
`"test-secret-do-not-use-in-production"` (auth-adapter.md C-AUTH-05). Minor inconsistency —
implementors should use the auth-adapter.md value as the canonical source, since it matches
the quickstart.md test commands. Recommend updating data-model.md to match.

---

## Dependency Ordering Review

The task execution order in tasks.md is correct:

```
Phase 1 (infra files) → Phase 2 (backend patterns) → Phases 3/4/5/6/7 (parallel after Phase 2)
```

One implicit dependency not documented:
- **T037 (nginx template)** depends on oauth2-proxy config (T003) and docker-compose
  (T004) being present to verify the `location /oauth2/` proxy target. DevOps can write
  T037 without T003/T004 existing, but full validation requires them. This is low-risk —
  document in task notes for T037.

**Phase 6 T059 dependency note**: T059 (orchestrator tm_client rewrite) must be done AFTER
T055 (orchestrator keycloak_client.py created). The [BLOCKED:T055] annotation is missing
from T059 in tasks.md — worth adding for clarity, though the tasks.md prose already notes
this order.

---

## 401 Retry Logic — Final Recommendation

Per the task assignment: _"confirm KeycloakServiceClient 401-retry logic for orchestrator
tm_client"_.

**Decision**: 401 retry SHOULD be implemented in tm_client/client.py and reporter.py but
NOT in KeycloakServiceClient itself.

**Rationale**:
1. `KeycloakServiceClient` is a token fetcher, not an HTTP client wrapper. Mixing retry logic
   here would make it stateful about HTTP responses from downstream services — wrong layer.
2. The 401 indicates the token was rejected by TM. This can happen if: (a) TM's JWKS cache
   expired and it fetched a new key set while the orchestrator still held an old token (rare
   but possible during Keycloak key rotation), or (b) clock skew > JWT `nbf`/`exp` tolerance.
3. One retry after forcing a fresh token is safe, idempotent, and bounded.

**Implementation contract for T059**:
```python
# In orchestrator tm_client/client.py
async def _headers(self) -> dict:
    return await get_kc_client().async_auth_headers()

async def _request_with_retry(self, method: str, url: str, **kwargs):
    resp = await self._http.request(method, url,
        headers=await _headers(), **kwargs)
    if resp.status_code == 401:
        # Force refresh: clear cache and retry once
        kc = get_kc_client()
        kc._cache.token = ""
        kc._cache.expires_at = 0.0
        resp = await self._http.request(method, url,
            headers=await _headers(), **kwargs)
    return resp
```
All callers of the old `_login()`-based methods in tm_client should use `_request_with_retry`.

---

## Constitution Compliance Check

| Principle | Concern | Status |
|-----------|---------|--------|
| §I Services Independently Deployable | UserClaims embedded per service, not shared | ✅ Pass |
| §XVII Keycloak is Single Source of Truth | No local user storage after migration | ✅ Pass |
| §XVIII JWKS Cached ≥300s | C-AUTH-04 + Decision 1 pattern | ✅ Pass |
| §XVIII stale cache on refresh fail | C-AUTH-04 explicit in contract | ✅ Pass |
| §XVIII AUTH_MODE=local never in docker-compose | Tasks.md critical constraint + spec §FR-016 | ✅ Pass |
| §XIX Service-to-Service via CC | C-KC-01 + Decision 2 | ✅ Pass |
| §XX Frontend via keycloak-js PKCE | realm-export.json public clients + S256 | ✅ Pass |
| §XXI Users Table Permanently Removed | downgrade() → NotImplementedError | ✅ Pass |
| §VI Zustand for All Frontend State | authStore wraps keycloak-js in Zustand | ✅ Pass |

---

## Action Items for Implementation Teams

| ID | Priority | Owner | Item |
|----|----------|-------|------|
| AI-01 | Advisory | backend (T059) | Add 401 retry in orchestrator tm_client per pattern above |
| AI-02 | Advisory | backend (T060) | Add 401 retry in agent-dispatcher reporter.py per same pattern |
| AI-03 | Advisory | devops (T002) | Restrict envsubst variable list in substitute-env.sh |
| AI-04 | Advisory | backend | Never read X-Auth-User/X-Auth-Email headers for authorization — use JWT only |
| AI-05 | Minor | devops (T080) | Document re-import behavior (temporary:true password prompt) in KEYCLOAK.md |
| AI-06 | Minor | any | Align test_jwt_secret default: use "test-secret-do-not-use-in-production" everywhere |
| AI-07 | Note | backend | Add tasks.md [BLOCKED:T055] annotation to T059 (clarification only) |
| AI-08 | Advisory | security-architect | Verify oauth2-proxy `cookie_secure=false` is acceptable for dev and should be `true` in production override |

---

## Well-Architected Pillars Assessment

| Pillar | Assessment |
|--------|-----------|
| **Security** | Strong. Defense-in-depth (nginx + backend). Tokens in memory only. PKCE enforced. Secrets via env vars, never in code. See security-architect for full threat model. |
| **Reliability** | Sound. JWKS stale-cache fallback prevents downtime on Keycloak hiccup. CC token cache with 30s buffer prevents last-second expiry. 401 retry (AI-01/02) closes the final gap. |
| **Operational Excellence** | Complete startup ordering (postgres → keycloak → services). Healthcheck polls realm endpoint (stronger than root check). KEYCLOAK.md runbook planned (T080). |
| **Performance** | Token validation ≤5ms on cache hit (JWKS cached 300s, CC token cached until near expiry). 401 retry adds one round-trip on a rare event — acceptable. |
| **Cost / Maintainability** | Single Keycloak container + oauth2-proxy (minimal infra addition). Per-service auth patterns are copy-consistent — manageable at 6 services. No shared auth library (correct per §I). |
| **Data Integrity** | Destructive migrations are atomic and irreversible by design. UUID cast to TEXT is lossless. Business data fully preserved. |
