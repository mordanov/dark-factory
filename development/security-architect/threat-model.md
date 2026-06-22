# Threat Model: Dark Factory Monorepo Unification

**Feature**: 001-monorepo-unification  
**Date**: 2026-06-22  
**Author**: security-architect agent  
**Method**: STRIDE + abuse-case analysis  
**Source documents**: spec.md, plan.md, contracts/auth-adapter-interface.md

---

## Scope

The threat model covers the **infrastructure and seam-preparation changes** introduced by the monorepo unification:

1. Auth adapter boundary (per-service `auth_adapter.py`, `AUTH_MODE` env var)
2. Token storage migration (UIM `localStorage` → Zustand in-memory)
3. Secrets management (`infra/.env`, credential files)
4. Integration test isolation (LLM mock, test user credentials)
5. Nginx reverse proxy (DNS injection, TLS stanzas, routing)
6. Cross-service database isolation

Existing service internals (login endpoints, token generation, user CRUD, product logic) are **out of scope** — this threat model focuses only on what changes.

---

## Assets

| Asset | Sensitivity | Owner |
|---|---|---|
| JWT access tokens (in-memory, per user session) | High | user-input-manager, ticket-manager |
| JWT refresh tokens (sessionStorage only) | High | user-input-manager, ticket-manager |
| `SECRET_KEY` (JWT signing keys, per service) | Critical | each backend service |
| `POSTGRES_PASSWORD`, `*_DB_PASSWORD` | Critical | infra/.env |
| `OPENAI_API_KEY` | High | infra/.env |
| Service JWT claims (user identity, roles) | Medium | all backends |
| Integration test user credentials | Medium | postgres seed script |
| `AUTH_MODE` environment variable | Medium | all backends |
| Nginx routing rules and DNS names | Low | infra/nginx |

---

## Actors

| Actor | Trust Level | Description |
|---|---|---|
| Authenticated end-user | Medium | Holds a valid session JWT |
| Unauthenticated browser | Untrusted | No session, may be attacker |
| Platform engineer (operator) | High | Deploys infra, supplies `.env` |
| Developer | High | Writes code, runs tests |
| CI/CD pipeline | High | Reads repo, runs tests |
| LLM mock service | Internal | Test-only, no internet access |
| Other Docker services | Internal | Share `internal` network only |
| Attacker (external) | Hostile | No direct access to internal network |
| Attacker (internal/supply-chain) | Hostile | Hypothetical compromised dependency |

---

## Trust Boundaries

```
[Internet / Browser]
      │
      ▼
[nginx reverse proxy]  ← DNS names injected via env vars at startup
      │
      ├── /api/ → [user-input-manager backend]  ── [df_user_input DB]
      │               └── AUTH_MODE env var
      ├── /api/ → [ticket-manager backend]       ── [df_ticket_manager DB]
      │               └── AUTH_MODE env var
      │
[Internal Docker network only]
      ├── [orchestrator]    ── [df_orchestrator DB]
      ├── [context-distiller] ── [df_distiller DB]
      ├── [agent-tools]
      ├── [postgres]   ← service-specific credentials only
      ├── [mongo]
      └── [llm-mock]   ← test compose only; NO host exposure
```

**Key boundary**: `AUTH_MODE` is read once at module import / startup. Any decision about what trust the adapter enforces is made at that boundary.

---

## Entry Points

| Entry Point | Protocol | Authentication | Exposure |
|---|---|---|---|
| nginx HTTP (port 80) | HTTP | Bearer JWT | Public (UIM_HOST, TM_HOST) |
| nginx HTTPS (commented out) | — | — | Not active |
| Backend service ports (8001–8005) | HTTP | Bearer JWT | Override compose only (dev) |
| Postgres port 5432 | TCP | Per-service credentials | Internal network only |
| MongoDB port 27017 | TCP | Per-service credentials | Internal network only |
| LLM mock port 11434 | HTTP | None | Internal test network only |

---

## Data Flows

1. **Login flow**: Browser → nginx → UIM/TM backend → JWT issued → Zustand in-memory (access) + sessionStorage (refresh)
2. **Protected request**: Browser → nginx → backend → `AuthAdapter.verify(token)` → DB lookup → response
3. **Token refresh**: Browser → nginx → backend refresh endpoint → new access token → Zustand store
4. **Logout**: Browser action → Zustand store cleared → sessionStorage refresh token cleared
5. **Inter-service call**: orchestrator → context-distiller (HTTP, internal network, service-to-service)
6. **Integration test**: pytest → httpx → compose services → llm-mock (intercepted LLM calls)
7. **DB init**: postgres container startup → `01_create_databases.sql` runs with POSTGRES_PASSWORD from `.env`

---

## Assumptions

- Services run in an isolated Docker internal network; the host does not expose service ports in production compose.
- `infra/.env` is operator-supplied and never committed (gitignored).
- Only `infra/.env.example` with placeholder values is committed to Git.
- SSL/TLS is out of scope; nginx is HTTP-only at delivery.
- Keycloak is not implemented; `AUTH_MODE=keycloak` raises `NotImplementedError`.
- No service modifies another service's database.
- Browser storage is the only client-side persistence; no native app storage model applies.

---

## Threats / Abuse Cases

### Area 1: Auth Adapter

| ID | Threat | STRIDE | Impact | Likelihood | Existing Controls | Required Mitigation | Residual Risk |
|---|---|---|---|---|---|---|---|
| T-A01 | `AUTH_MODE` set to unrecognised value silently falls through to local validation | Elevation of Privilege | Critical | Low | None | `ValueError` on unrecognised value at startup; service MUST NOT start | None if required mitigation in place |
| T-A02 | `AUTH_MODE=keycloak` silently accepts tokens (stub incomplete) | Spoofing | Critical | Low | Contract requires `NotImplementedError` | Raise `NotImplementedError`; FastAPI dependency maps to HTTP 501 | None if required mitigation in place |
| T-A03 | Auth adapter code shared between services via a shared library | Elevation of Privilege | High | Low | Constitution forbids shared Python imports | Each service has its own `auth_adapter.py` with no cross-import | None if required mitigation in place |
| T-A04 | Auth adapter changes `AUTH_MODE=local` token verification behaviour (regression) | Tampering | High | Medium | Pre/post parity tests | `AUTH_MODE=local` MUST delegate unchanged to existing `security.verify_access_token()` | Low — if tests pass, regression risk is low |
| T-A05 | Expired or tampered JWT accepted in `AUTH_MODE=local` | Spoofing | Critical | Low | Existing `security.verify_access_token()` handles this | Adapter MUST NOT add any bypass; token passed through verbatim | Low — depends on existing security.py correctness |
| T-A06 | `AUTH_MODE` env var injected at runtime after service starts (hot-reload) | Tampering | High | Very Low | Docker env vars set at start | `AUTH_MODE` read once at module load; service requires restart to change | Low |

### Area 2: Token Storage (Zustand Migration)

| ID | Threat | STRIDE | Impact | Likelihood | Existing Controls | Required Mitigation | Residual Risk |
|---|---|---|---|---|---|---|---|
| T-S01 | Access token written to `localStorage` after migration | Information Disclosure | High | Medium (migration error) | None yet | Verify no `localStorage.setItem('access_token', ...)` anywhere after T043–T050 | None if sweep complete |
| T-S02 | Access token written to `sessionStorage` after migration | Information Disclosure | Medium | Medium | None yet | Verify no `sessionStorage.setItem('access_token', ...)` anywhere | None if sweep complete |
| T-S03 | Access token logged or included in error payloads | Information Disclosure | High | Low | None explicit | Do not log token value; error objects must not serialize Zustand store | Low |
| T-S04 | Refresh token placed in `localStorage` instead of `sessionStorage` | Information Disclosure | Medium | Low | Plan spec requires `sessionStorage` for refresh | Zustand store uses `sessionStorage` key `"rt"` only; no `localStorage` for refresh | Low |
| T-S05 | XSS allows access to Zustand in-memory token | Information Disclosure | High | Low | In-memory is better than localStorage; XSS can still read via `window` | Zustand in-memory significantly narrows attack window vs localStorage; XSS prevention is separate concern | Low-Medium (XSS prevention out of scope) |
| T-S06 | Session survives intended logout (token not cleared) | Elevation of Privilege | Medium | Low | Plan requires `logout()` to clear store and sessionStorage | Verify `logout()` clears `accessToken`, `currentUser`, and removes `sessionStorage` `"rt"` key | None if verified |

### Area 3: Secrets Management

| ID | Threat | STRIDE | Impact | Likelihood | Existing Controls | Required Mitigation | Residual Risk |
|---|---|---|---|---|---|---|---|
| T-M01 | `SECRET_KEY`, `POSTGRES_PASSWORD`, `OPENAI_API_KEY` committed to Git | Information Disclosure | Critical | Low | `.env` in `.gitignore` | Verify `.env` gitignored; `.env.example` has only placeholders; run `git log --all -- "*.env"` | None if gitignore correct |
| T-M02 | Hardcoded credentials in Dockerfiles or compose YAML | Information Disclosure | High | Low | None yet | All secrets via `${VAR}` env var substitution only; no `ENV SECRET=value` in Dockerfile | None if enforced |
| T-M03 | `credentials.json` files committed to Git | Information Disclosure | High | Low | Plan shows `credentials.json` gitignored | Verify `*/credentials.json` in `.gitignore` | None if gitignore correct |
| T-M04 | Postgres superuser credentials shared across services | Privilege Escalation | High | Low | Plan requires per-service users | Each service uses service-specific DB user, not POSTGRES_USER superuser | None if SQL init script correct |
| T-M05 | `.env.example` placeholder values are real credentials | Information Disclosure | Medium | Low | None | `.env.example` MUST use clearly fake values (e.g. `changeme`, `your-secret-here`) | Low |
| T-M06 | Secrets visible in Docker process list or environment dump | Information Disclosure | Medium | Low | Docker env var injection standard practice | No additional risk beyond Docker's own env var handling | Low |

### Area 4: Integration Test Isolation

| ID | Threat | STRIDE | Impact | Likelihood | Existing Controls | Required Mitigation | Residual Risk |
|---|---|---|---|---|---|---|---|
| T-I01 | Real OpenAI API calls made during integration tests (credential exfiltration / cost) | Information Disclosure | High | Medium | `OPENAI_BASE_URL` override planned | LLM mock service intercepts all LLM calls; verified by running with invalid real API key | Low |
| T-I02 | LLM mock exposed to host network (accessible outside test compose) | Information Disclosure | Medium | Low | Plan specifies internal network only | `llm-mock` MUST NOT have `ports:` mapping in `docker-compose.test.yml` | None if enforced |
| T-I03 | Test user credentials match production defaults | Privilege Escalation | Medium | Low | None yet | SQL seed test users MUST have credentials not matching any known production defaults | Low |
| T-I04 | `conftest.py` calls registration API to create test users | Spoofing / Test pollution | Low | Low | Spec FR-016 forbids API-based user creation | Users created via SQL seed only; `conftest.py` MUST NOT call registration endpoints | None if followed |
| T-I05 | Test compose uses real `OPENAI_API_KEY` from `.env` | Information Disclosure | High | Medium | None yet | Test compose MUST override `OPENAI_BASE_URL` and not require a real key | None if override in place |

### Area 5: Nginx Security

| ID | Threat | STRIDE | Impact | Likelihood | Existing Controls | Required Mitigation | Residual Risk |
|---|---|---|---|---|---|---|---|
| T-N01 | `$UIM_HOST`/`$TM_HOST` not substituted at startup (envsubst failure) | Denial of Service | Medium | Low | `envsubst` in entrypoint | Entrypoint fails if variable is empty; nginx validates config before starting | Low |
| T-N02 | SSL stanza enabled without a certificate (nginx crash on start) | Denial of Service | Medium | Low | SSL stanza commented out | Do NOT uncomment SSL stanzas; certbot activation is a separate ops step | None while commented |
| T-N03 | Missing `/.well-known/acme-challenge/` breaks future certbot renewal | Availability | Low | Low | Spec requires it present | Present but no active cert; safe | None |
| T-N04 | Nginx serves one frontend's assets for another host's requests | Information Disclosure | Low | Very Low | Separate server blocks per host | Each server block scoped to its `server_name` | None |
| T-N05 | Internal services reachable via nginx beyond their designated `/api/` paths | Elevation of Privilege | Medium | Low | Server block routing is explicit | Only configured `location` blocks are proxied; no catch-all backend proxy | Low |

### Area 6: Cross-Service Database Isolation

| ID | Threat | STRIDE | Impact | Likelihood | Existing Controls | Required Mitigation | Residual Risk |
|---|---|---|---|---|---|---|---|
| T-D01 | Service queries another service's database | Elevation of Privilege | High | Very Low | Constitution principle X | DB connection strings in `.env.example` use service-specific credentials only; no shared superuser | None |
| T-D02 | Postgres init script grants over-broad DB privileges | Privilege Escalation | High | Low | None yet | `GRANT ALL PRIVILEGES ON DATABASE x TO user_x` only — not to all users or postgres role | Low if reviewed |
| T-D03 | Single postgres instance allows cross-DB queries via shared superuser | Elevation of Privilege | Medium | Very Low | Per-service credentials prevent this | Service users cannot log in to another service's DB (no GRANT) | None if init SQL correct |

---

## Required Mitigations (Priority Order)

### Blockers (Must fix before release)

1. **T-A01** — `AUTH_MODE` unrecognised value MUST raise `ValueError` at startup, not fall through.
2. **T-A02** — `AUTH_MODE=keycloak` MUST raise `NotImplementedError`; MUST return HTTP 501 via FastAPI dependency mapping.
3. **T-S01** — No access token in `localStorage` at any point post-migration; verify with T050 sweep + browser DevTools.
4. **T-M01** — `.env` gitignored; `.env.example` has only placeholder values; verified by `git log --all -- "*.env"`.
5. **T-M02** — No hardcoded secrets in Dockerfiles, compose YAML, or source code.

### High (Must fix or formally accept before release)

6. **T-A03** — No shared auth adapter library across services.
7. **T-M04** — Each service uses its own DB user; no POSTGRES_USER superuser in service connection strings.
8. **T-I01** — LLM mock intercepts all LLM calls; run suite with invalid real key to verify.
9. **T-I02** — LLM mock has no `ports:` mapping in test compose.

### Medium (Fix in planned timeframe)

10. **T-A04** — `AUTH_MODE=local` behaviour byte-for-byte identical pre/post migration (SC-008).
11. **T-S02** — No access token in `sessionStorage`.
12. **T-S06** — `logout()` clears access token, user, and refresh token from all storage.
13. **T-M03** — `credentials.json` gitignored.
14. **T-I03** — Test credentials do not match production defaults.
15. **T-D02** — Postgres init script grants minimum required privileges.

---

## Security Tests

Derived from spec.md and the threat model above. These MUST be covered by Autotester and verified in Code Review.

| Test ID | Description | Threat(s) | Pass Criteria |
|---|---|---|---|
| ST-01 | `AUTH_MODE=local` — valid token accepted | T-A04, T-A05 | HTTP 200, same claims as pre-migration |
| ST-02 | `AUTH_MODE=local` — expired token rejected | T-A04, T-A05 | HTTP 401 |
| ST-03 | `AUTH_MODE=local` — tampered token rejected | T-A04, T-A05 | HTTP 401 |
| ST-04 | `AUTH_MODE=keycloak` — any request returns 501 | T-A02 | HTTP 501 on first authenticated request |
| ST-05 | `AUTH_MODE=<unrecognised>` — service fails at startup | T-A01 | Service exits with error; does not start |
| ST-06 | No `access_token` in `localStorage` after UIM login | T-S01 | DevTools → Application → Local Storage: no `access_token` key |
| ST-07 | No `access_token` in `sessionStorage` after UIM login | T-S02 | DevTools → Application → Session Storage: no `access_token` key |
| ST-08 | UIM logout clears Zustand store and sessionStorage | T-S06 | After logout: `useAuthStore.getState().accessToken` is null; `sessionStorage.getItem("rt")` is null |
| ST-09 | No secrets in Git history | T-M01, T-M02, T-M03 | `git log --all --full-history -- "*.env"` returns no committed `.env` files with real values |
| ST-10 | No real OpenAI calls in integration test suite | T-I01, T-I05 | Run suite with `OPENAI_API_KEY=invalid-for-test`; both scenarios pass |
| ST-11 | LLM mock has no host port exposure | T-I02 | `docker compose -f docker-compose.test.yml config` shows no `ports:` for llm-mock |
| ST-12 | No service DB connection string uses postgres superuser | T-D02, T-D03 | Grep `.env.example` for `POSTGRES_USER` in service DB URLs; none present |

---

## Open Questions

1. Does `agent-tools` (MCP server) have authenticated endpoints beyond `/health`? If so, the auth adapter scope needs verification.
2. Are refresh token endpoints protected against replay on the same `sessionStorage` `"rt"` key across browser tabs?
3. Does any service log request payloads that might contain JWT bearer tokens in Authorization headers?

---

## Decision / Status

**Status**: DRAFT — pending review of implemented auth adapters (T032–T041) and Zustand migration (T043–T050).

**Review gate**: Security review result to be issued after backend completes auth adapters and frontend completes Zustand migration. Code Reviewer and Autotester to use security test cases ST-01 through ST-12 as acceptance criteria.
