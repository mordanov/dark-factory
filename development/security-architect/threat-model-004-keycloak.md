# Threat Model: Keycloak IAM Migration (004)

**Feature**: 004-keycloak-iam-migration  
**Date**: 2026-06-24  
**Author**: Security Architect Agent  
**Status**: APPROVED WITH RISKS

---

## Scope

The Dark Factory Keycloak IAM migration replaces all local password-based authentication with
Keycloak 25 as the sole identity provider. This threat model covers:

1. Keycloak realm configuration and bootstrap
2. `KeycloakValidator` RS256 JWKS-based auth adapter (all 6 services)
3. `KeycloakServiceClient` Client Credentials grant (service-to-service)
4. nginx + oauth2-proxy Bearer token boundary
5. Frontend token storage (keycloak-js PKCE + Zustand in-memory)
6. Destructive database migrations (users table removal)
7. Service-to-service token injection for agents

---

## Assets

| Asset | Sensitivity | Owner |
|-------|-------------|-------|
| Keycloak realm master admin credential | Critical | DevOps |
| Per-service client secrets (`KC_*_CLIENT_SECRET`) | Critical | DevOps |
| `OAUTH2_PROXY_CLIENT_SECRET` | Critical | DevOps |
| `OAUTH2_PROXY_COOKIE_SECRET` | Critical | DevOps |
| `KC_DB_PASSWORD` | High | DevOps |
| User access tokens (in-flight, in-memory) | High | Frontend |
| Service-to-service access tokens | High | Backend |
| JWKS public key material (cached) | Medium | All backends |
| Agent-injected service token (in agent context) | High | Agent Dispatcher |
| User PII in database (email, user_id references) | High | Backend |
| Existing business data (tickets, sessions, projects) | High | Backend/DB |
| `infra/.env` (never committed) | Critical | DevOps |

---

## Actors

| Actor | Trust Level | Notes |
|-------|------------|-------|
| Authenticated user (browser) | Low-Medium | Has valid Keycloak session; must not be over-trusted |
| Administrator (browser) | Medium | Has `administrator` realm role; still constrained by Keycloak |
| Backend service (internal network) | High | Holds a valid CC token; trusted within Docker network |
| Keycloak server | High | Identity authority; must be reachable for startup |
| Agent (spawned by dispatcher) | Medium | Holds a single injected token; no refresh |
| oauth2-proxy | High | nginx trust boundary enforcer |
| Unauthenticated external client | Untrusted | All /api/ requests must be rejected |
| Attacker (external) | Untrusted | Targets tokens, secrets, and auth bypass |
| Attacker (internal, compromised service) | Untrusted | Targets other services' DB, lateral movement |

---

## Trust Boundaries

```
[Browser / External Client]
         │ HTTPS (TLS at nginx)
         ▼
[nginx reverse proxy]
  └─ auth_request ──► [oauth2-proxy:4180]
                           │ validates Bearer vs Keycloak JWKS
                           ▼
              [Docker internal network]
                 │                    │
          [UIM :8000]          [TM :8000]
          [Orchestrator]       [Context-Distiller]
          [Agent-Dispatcher]   [Agent-Tools]
                 │ Client Credentials (Keycloak)
                 ▼
         [Keycloak :8080]
                 │
         [PostgreSQL keycloak DB]
```

Key boundaries:
- **nginx ↔ external**: TLS terminates here. All external traffic enters via nginx.
- **nginx ↔ oauth2-proxy**: internal only; `location = /oauth2/auth` is `internal` — unreachable directly.
- **Docker network ↔ services**: all inter-service traffic is trusted network only; no TLS required.
- **Services ↔ Keycloak**: token fetch and JWKS fetch; Keycloak must be healthy for startup.

---

## Data Flows

1. **User login**: Browser → nginx → Keycloak (PKCE redirect) → keycloak-js stores token in memory
2. **API request**: Browser → nginx (auth_request → oauth2-proxy → Keycloak JWKS) → Backend (KeycloakValidator re-validates) → Response
3. **Service token fetch**: Backend → Keycloak (`/token` Client Credentials) → cached in `KeycloakServiceClient`
4. **Inter-service call**: Backend A → Backend B (with CC token as Bearer) → Backend B's KeycloakValidator
5. **Agent spawn**: Agent Dispatcher → Keycloak (get_token) → injects token string into agent context text
6. **JWKS refresh**: Backend → Keycloak (`/certs`) → cached 300s in `KeycloakValidator`
7. **DB migration**: Alembic → PostgreSQL (drop users table, alter FK columns to TEXT)

---

## Entry Points

| ID | Entry Point | Auth Required | Notes |
|----|-------------|--------------|-------|
| EP-01 | `GET /` (frontend static) | No | keycloak-js handles auth in browser |
| EP-02 | `GET /.well-known/acme-challenge/` | No | certbot; no auth_request |
| EP-03 | `/api/**` (any service) | Yes (auth_request) | oauth2-proxy validates Bearer |
| EP-04 | `/oauth2/**` | No (proxy) | oauth2-proxy management |
| EP-05 | Keycloak `:8080` (admin console) | Keycloak admin | Internal network only; NOT proxied via nginx |
| EP-06 | PostgreSQL `:5432` | DB credentials | Not exposed to host in compose |
| EP-07 | `POST /realms/dark-factory/protocol/openid-connect/token` | CC client secret | Inter-service token fetch |
| EP-08 | `GET /realms/dark-factory/protocol/openid-connect/certs` | None | JWKS endpoint; public |

---

## Assumptions

- Docker network is trusted; TLS between services not required.
- Keycloak Admin Console is internal-only; nginx does NOT proxy `:8080`.
- Self-registration is disabled in realm (`registrationAllowed: false`).
- `infra/.env` is gitignored and never committed.
- `AUTH_MODE=local` is CI-only; it MUST NOT appear in production `docker-compose.yml`.
- All 9 client secrets in `infra/.env` use strong random values in production.
- Destructive migrations are applied once; rollback is impossible by design.

---

## Threats / Abuse Cases

| ID | STRIDE | Threat | Area | Impact | Likelihood | Severity | Controls | Residual Risk |
|----|--------|--------|------|--------|------------|----------|----------|---------------|
| T-01 | Spoofing | Token replay: attacker captures valid Bearer token and uses it before expiry | API boundary | High | Medium | High | Short TTL (300s), HTTPS only, no token in localStorage | Residual: 300s window if token is exfiltrated via XSS or log leak |
| T-02 | Spoofing | JWKS substitution: attacker poisons JWKS cache via MITM | JWKS fetch | Critical | Low | High | JWKS fetched over internal Docker network only; no external JWKS source | Low residual on internal network; higher if network is compromised |
| T-03 | Spoofing | `AUTH_MODE=local` used in production: attacker creates HS256 token with known `test-secret-do-not-use-in-production` | All backends | Critical | Low | Blocker | Constitution §XVIII prohibits `AUTH_MODE=local` in docker-compose.yml; validated by CI check | Zero residual IF CI check is enforced |
| T-04 | Spoofing | Client secret brute-force: attacker guesses weak `KC_*_CLIENT_SECRET` | Service-to-service | High | Low | High | Strong random secrets required; Keycloak brute force protection enabled at realm | Residual: depends on secret strength |
| T-05 | Tampering | Algorithm confusion: attacker crafts token with `alg=none` or `alg=HS256` when service expects RS256 | KeycloakValidator | Critical | Low | Blocker | python-jose verifies algorithm; must explicitly pass `algorithms=["RS256"]` | Zero residual IF algorithm is pinned |
| T-06 | Tampering | JWT claim forgery: attacker modifies `realm_access.roles` after issuance | All backends | High | Low | High | RS256 signature covers all claims; python-jose verifies signature | Zero residual on valid RS256 implementation |
| T-07 | Tampering | DB migration data corruption: migration fails midway, leaving inconsistent state | PostgreSQL | High | Medium | High | Alembic runs in a transaction; partial failure rolls back (except DDL in PostgreSQL auto-commits per statement) | Residual: manual recovery needed if migration crashes mid-ALTER; test in staging first |
| T-08 | Repudiation | No audit trail for admin operations | Keycloak admin | Medium | High | Medium | Keycloak has built-in admin audit events; structlog logs identity subject in all service calls | Residual: no centralized SIEM yet |
| T-09 | Information Disclosure | Client secret in logs: `UpstreamError` includes secret in message | keycloak_client.py | High | Medium | High | C-KC-04 contract: secret MUST NOT appear in UpstreamError or structlog | Residual: depends on code review compliance |
| T-10 | Information Disclosure | Token in browser storage: access token written to localStorage/sessionStorage | Frontend | High | Medium | High | FR-018: tokens in Zustand in-memory only; SC-003 verifies; authStore must not call localStorage | Zero residual IF authStore is correct |
| T-11 | Information Disclosure | Token injected into agent context visible in logs | Agent Dispatcher | High | Medium | High | Token is in context text sent to LLM; context must not be logged at INFO level with content | Residual: depends on log level configuration |
| T-12 | Denial of Service | Keycloak unavailable at service startup: service starts without auth, accepts any token | All backends | Critical | Medium | Blocker | FR-015 + `depends_on: keycloak: condition: service_healthy` in compose; KeycloakValidator must fail startup if JWKS fetch fails | Zero residual IF healthcheck + startup JWKS fetch is enforced |
| T-13 | Denial of Service | JWKS cache expiry during Keycloak outage: all new token validations fail | All backends | High | Low | High | FR-017: stale cache used until TTL expires; 503 returned after TTL expires; log warning | Residual: up to 300s of continued operation, then graceful 503 |
| T-14 | Denial of Service | oauth2-proxy OIDC discovery fails: nginx cannot validate any API request | nginx boundary | High | Low | Medium | oauth2-proxy caches OIDC config; healthchecks detect outage | Residual: oauth2-proxy has shorter cache than backends |
| T-15 | Elevation of Privilege | Role claim tampering: `realm_access.roles` can be spoofed if algorithm is not pinned | All backends | Critical | Low | Blocker | RS256 with pinned algorithm in KeycloakValidator covers this (same as T-05) | Zero residual IF algorithm pinned |
| T-16 | Elevation of Privilege | Broken `require_admin` check: frontend-only admin gate, no server-side enforcement | All backends | High | Medium | High | `require_admin` must be a FastAPI Depends on each admin endpoint; `claims.is_admin` checked server-side | Residual: depends on code review |
| T-17 | Elevation of Privilege | Service impersonation: compromised service uses CC token to call other services as itself | Inter-service | Medium | Low | Medium | Each service has its own client ID; CC tokens include `azp` (authorized party) claim; backend should log `azp` | Residual: once a secret is compromised, all calls from that service are authorized |
| T-18 | Elevation of Privilege | `AUTH_MODE` env var injection: attacker injects `AUTH_MODE=local` at runtime | Container | Critical | Low | High | Read-only container filesystem; env vars set at compose startup only | Residual: if container is compromised, all security assumptions break |
| T-19 | Information Disclosure | Keycloak realm export contains secrets as `${VAR}` placeholders, but substitute-env.sh writes resolved secrets to realm.json on disk | Keycloak container | High | Medium | High | `realm.json` is written to a writable path inside the container; it must NOT be persisted to a host volume | Residual: realm.json exists in container memory; cleared on container restart |
| T-20 | Tampering | Realm export replay: old `realm.json` from a prior run is used instead of the freshly substituted one | Keycloak | Medium | Low | Medium | `substitute-env.sh` always overwrites `realm.json`; `set -e` aborts on failure | Low residual |
| T-21 | Information Disclosure | Google OIDC client secret exposed if `enabled: false` is bypassed | Keycloak realm | Medium | Low | Medium | `enabled: false` in realm-export.json; `GOOGLE_CLIENT_SECRET` is empty by default | Low residual while Google IdP is disabled |
| T-22 | Spoofing | oauth2-proxy cookie theft: `_oauth2_proxy_df` cookie intercepted | Browser ↔ nginx | Medium | Low | Medium | `cookie_secure = false` in dev (acceptable for localhost); production must set `cookie_secure = true` | High residual in production if `cookie_secure` not updated |
| T-23 | Information Disclosure | Destructive migration removes user emails that may have legal/compliance retention requirement | PostgreSQL | Medium | Medium | Medium | Out of scope per assumption; no regulatory compliance requirement stated | Residual: if compliance requirements change post-migration, recovery is impossible |

---

## Required Mitigations

### Blockers — Must Fix Before Release

**M-01 (T-03, T-15): AUTH_MODE=local MUST NOT appear in docker-compose.yml**
- Enforce via CI: `grep -r 'AUTH_MODE=local' infra/docker-compose.yml` must exit non-zero.
- `KeycloakValidator` must fail startup if `AUTH_MODE` is any value other than `keycloak` or `local`.
- If `AUTH_MODE=local`, must only succeed if `TEST_JWT_SECRET` is non-empty and non-default in test fixtures.

**M-02 (T-05, T-15): Algorithm pinned to RS256 in keycloak mode**
- `python-jose` decode call: `jwt.decode(token, jwks_key, algorithms=["RS256"])` — no `algorithms=None`.
- Local mode: `jwt.decode(token, secret, algorithms=["HS256"])` — no mixed-algorithm verification.
- Test: `test_algorithm_confusion_rejected` — token with `alg: none` raises `UnauthorizedError`.

**M-03 (T-12): Services MUST NOT start if Keycloak JWKS is unreachable**
- `KeycloakValidator.__init__` must attempt an eager JWKS fetch on startup.
- If fetch fails → raise `RuntimeError("Cannot reach Keycloak JWKS endpoint: {url}")`.
- `depends_on: keycloak: condition: service_healthy` in docker-compose.yml (T004) is a prerequisite.
- Test: startup with unreachable Keycloak URL raises `RuntimeError` before accepting requests.

### High — Must Fix or Formally Accept Before Release

**M-04 (T-09): Client secret never in logs or exceptions**
- `KeycloakServiceClient.get_token()`: catch `httpx.HTTPStatusError`; raise `UpstreamError(f"KC token endpoint returned {resp.status_code}")` — never include `client_secret` in message.
- `structlog.bind_contextvars(kc_client_id=client_id)` — NEVER `kc_client_secret`.
- Code review checklist item: search for `client_secret` in all `UpstreamError` message strings.

**M-05 (T-10): Access token in Zustand in-memory only**
- `authStore.ts`: no calls to `localStorage.setItem`, `sessionStorage.setItem`, or `document.cookie` assignment.
- keycloak-js default behaviour: tokens are held in memory by the keycloak-js library object.
- Regression test (Vitest): spy on `localStorage.setItem` — assert never called during `initialize()`.

**M-06 (T-11): Agent-injected token not logged at INFO level**
- Agent Dispatcher context builder: log agent context at `DEBUG` level only; `INFO` and above must redact the `## Service Token` section.
- Recommended: replace token value with `<redacted>` in INFO-level context summaries.

**M-07 (T-16): Admin endpoints require server-side `require_admin` Depends**
- Every admin endpoint: `Depends(require_admin)` not `Depends(get_current_user)`.
- Code review: grep for admin routes without `require_admin`.

**M-08 (T-22): oauth2-proxy cookie_secure in production**
- `config.cfg` has `cookie_secure = false` for dev. Production deployment MUST set `cookie_secure = true`.
- Document in `infra/KEYCLOAK.md` (T080) under "Production Checklist".

### Medium — Fix in Planned Timeframe

**M-09 (T-19): realm.json must not be persisted to host**
- substitute-env.sh writes to `/opt/keycloak/data/import/realm.json` inside container (ephemeral).
- docker-compose.yml must NOT add a host volume bind for this path.
- Verify: `docker compose config | grep realm.json` shows only the read-only `realm-export.json` mount.

**M-10 (T-08): Structured audit logging for all auth events**
- `structlog` in each service: bind `user_sub`, `is_admin` (not full claims) on every authenticated request.
- Log: `UnauthorizedError`, `require_admin` rejection, service startup JWKS status.

---

## Security Tests

| ID | Test | Target | Pass Condition |
|----|------|--------|---------------|
| ST-01 | `AUTH_MODE=local` rejected in docker-compose.yml | CI pipeline | `grep -r 'AUTH_MODE=local' infra/docker-compose.yml` exits 1 |
| ST-02 | Algorithm `none` rejected by KeycloakValidator | unit/test_auth_adapter.py | `UnauthorizedError` raised |
| ST-03 | HS256 token rejected when AUTH_MODE=keycloak | unit/test_auth_adapter.py | `UnauthorizedError` raised (wrong algorithm) |
| ST-04 | Startup fails if JWKS unreachable (keycloak mode) | unit/test_auth_adapter.py | `RuntimeError` on init |
| ST-05 | Client secret not in UpstreamError message | unit/test_keycloak_client.py | UpstreamError message does not contain secret string |
| ST-06 | localStorage never written during keycloak-js init | frontend Vitest | `localStorage.setItem` spy never called |
| ST-07 | sessionStorage never written during keycloak-js init | frontend Vitest | `sessionStorage.setItem` spy never called |
| ST-08 | Admin endpoint returns 403 for non-admin token | integration test | 403 response with non-admin user token |
| ST-09 | Admin endpoint returns 200 for admin token | integration test | 200 response with admin user token |
| ST-10 | Expired token returns 401 JSON (not HTML) | integration test | 401 with `{"detail":"Not authenticated","code":"TOKEN_EXPIRED_OR_INVALID"}` |
| ST-11 | Unauthenticated /api/ request returns 401 JSON | integration test | 401 JSON from nginx @error401 |
| ST-12 | Direct access to `/oauth2/auth` (non-internal) is rejected | nginx test | 404 or connection refused from external client |
| ST-13 | JWKS stale cache serves requests during Keycloak outage | unit test | Requests succeed for ≤300s after Keycloak goes down |
| ST-14 | realm.json not persisted to host volume | compose config check | `docker compose config` shows no host bind for realm.json |
| ST-15 | No secrets in git history | git audit | `git log --all --full-history -- "*.env"` shows no committed secrets |
| ST-16 | Token refresh 30s before expiry | unit/test_keycloak_client.py | httpx.post called twice when second call is within 30s of expiry |
| ST-17 | Concurrent CC token requests use single HTTP call | unit/test_keycloak_client.py | httpx.post called once under concurrent load |
| ST-18 | `test-secret-do-not-use-in-production` never in docker-compose.yml | CI | grep exits 1 |

---

## Open Questions

| # | Question | Owner | Due | Status |
|---|----------|-------|-----|--------|
| OQ-01 | Does Keycloak Admin Console need to be proxied for external admin access in production? | DevOps | TBD | Open — Keycloak is internal-only per assumption; if production requires external admin access, a separate hardened proxy path is needed |
| OQ-02 | Are agents expected to rotate tokens during a long run (>1h)? | Backend / Product | TBD | Open — current design gives agents a single 1h token; no refresh mechanism for agents |
| OQ-03 | What is the session revocation mechanism for agents? If a compromised agent holds a 1h token, how is it revoked? | Security / DevOps | TBD | Open — Keycloak token revocation endpoint exists but agents don't poll it |
| OQ-04 | Is there a SIEM or log aggregation target for Keycloak audit events? | DevOps | TBD | Open — out of scope for this migration |
| OQ-05 | Does oauth2-proxy need `cookie_secure = true` in production, and does the deployment runbook cover it? | DevOps | TBD | Open — see M-08 |

---

## Residual Risks

| Risk | Severity | Owner | Target Date | Notes |
|------|----------|-------|-------------|-------|
| 300s token replay window after exfiltration | High | Product | TBD | Acceptable for dev; reduce TTL for production if needed |
| Agent 1h non-revocable token | High | Product | TBD | No in-band refresh; revoking requires Keycloak admin action and agent restart |
| cookie_secure=false in production oauth2-proxy | High | DevOps | Before prod deploy | Mitigated by M-08 and KEYCLOAK.md production checklist |
| No SIEM for Keycloak audit events | Medium | DevOps | Post-migration | Keycloak logs to stdout; centralized log collection is future work |
| realm.json temporarily on disk in container | Medium | DevOps | Accepted | Cleared on container restart; no host-volume persistence |
| Google IdP client secret placeholder populated without enabling | Low | DevOps | Low priority | `enabled: false` prevents activation |

---

## Decision / Status

**APPROVED WITH RISKS**

All blockers (M-01, M-02, M-03) MUST be verified before this feature ships:
1. CI check rejects `AUTH_MODE=local` in docker-compose.yml.
2. `KeycloakValidator` pins `algorithms=["RS256"]`; no algorithm confusion possible.
3. Services fail startup if JWKS is unreachable.

High findings (M-04 through M-08) must be fixed or formally accepted. M-05 (token storage) and M-04 (secret not in logs) are the most likely to be missed in implementation — reviewers must specifically check these.

Residual risks are documented above with owners and target dates.
