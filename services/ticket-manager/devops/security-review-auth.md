# Security Review: Authentication Flow (T029)

**Reviewer**: Security Architect
**Date**: 2026-05-23
**Scope**: T014 (refresh_tokens migration), T018 (core/security.py), T022 (auth endpoints),
T024 (frontend token store), T025 (API client)
**Phase**: Phase 2 Gate — blocks all user story implementation

---

## Threat Model: Authentication Flow

### Scope

The authentication subsystem for the Ticket Management System: login, token issuance,
token refresh, and session revocation. This covers the trust boundary between the browser
SPA and the FastAPI backend, and between the backend and PostgreSQL.

### Assets

| Asset | Sensitivity | Location |
|---|---|---|
| User passwords (plaintext, in-flight) | Critical | POST /auth/login request body (TLS-protected) |
| bcrypt password hashes | High | PostgreSQL `users.hashed_password` |
| JWT access tokens | High | Browser memory (Zustand), Authorization header |
| Opaque refresh tokens (raw) | High | Browser storage (to be specified — see Finding F-01) |
| Refresh token SHA-256 hashes | Medium | PostgreSQL `refresh_tokens.token_hash` |
| JWT signing secret (SECRET_KEY) | Critical | Environment variable / secrets store |
| User role claims | High | JWT payload, PostgreSQL `users.role` |

### Actors

| Actor | Trust Level | Notes |
|---|---|---|
| Authenticated user (role: user) | Low trust | Can act on assigned tickets only |
| Authenticated admin (role: administrator) | Medium trust | Elevated privileges; must be least-privilege |
| Unauthenticated browser | Zero trust | All requests rejected except /auth/login, /health, /ready |
| Attacker (external) | Hostile | Credential stuffing, token theft, privilege escalation |
| Attacker (insider / compromised account) | Hostile | Horizontal/vertical privilege abuse |

### Trust Boundaries

1. **Browser ↔ API** — TLS required; JWT in Authorization header; no cookies defined
2. **API ↔ PostgreSQL** — internal network; connection string in env var; parameterized queries via SQLAlchemy ORM
3. **API process ↔ file system/env** — secrets read at startup from environment; must not be logged

### Data Flows

```
[Browser]
  POST /auth/login {email, password}
    → [API] bcrypt.verify(password, hash)
    → issue JWT (HS256, 30-min TTL), opaque refresh token
    → store SHA-256(refresh_token) in refresh_tokens table
    → return {access_token, refresh_token, expires_in}

[Browser]
  Every request: Authorization: Bearer <access_token>
    → [API] jwt.decode(token, SECRET_KEY) → get_current_user dependency
    → handler executes if valid

[Browser]
  POST /auth/refresh {refresh_token}
    → [API] SHA-256(refresh_token) lookup in DB
    → check revoked_at IS NULL and expires_at > now()
    → issue new JWT access token
    → return {access_token, expires_in}

[Browser]
  POST /auth/logout (Bearer <access_token>)
    → [API] set refresh_tokens.revoked_at = now()
    → return 204
```

### Entry Points

| Endpoint | Auth Required | Notes |
|---|---|---|
| POST /auth/login | No | Credential intake; brute-force target |
| POST /auth/refresh | No (token in body) | Refresh token is the credential |
| POST /auth/logout | Yes (JWT) | Must identify which refresh token to revoke |
| All other /api/v1/* | Yes (JWT) | `get_current_user` dependency |
| /health, /ready | No | No sensitive data |

### Assumptions

- All traffic between browser and API is over HTTPS (TLS 1.2+). HTTP not permitted.
- SECRET_KEY is generated with a cryptographically secure random source (≥32 bytes entropy).
- PostgreSQL connection is on a private network; direct DB access not exposed to the internet.
- This is an internal team tool; user registration is out of scope (admin-managed user creation assumed).

---

## Threats and Abuse Cases (STRIDE)

| ID | Category | Threat | Impact | Likelihood | Controls Present | Residual Risk |
|---|---|---|---|---|---|---|
| T-01 | Spoofing | Credential brute-force / credential stuffing on POST /auth/login | Account takeover | Medium-High | bcrypt slows attempts | No rate limiting — **see F-02** |
| T-02 | Spoofing | JWT algorithm confusion attack (alg:none or RS256 with HS256 key) | Token forgery | Low | Spec says HS256; python-jose rejects alg:none by default | Must explicitly reject non-HS256 algorithms — **see F-03** |
| T-03 | Spoofing | Weak SECRET_KEY allows JWT forgery | Full auth bypass | Low if key is strong | Key is env var | Must enforce entropy — **see F-04** |
| T-04 | Tampering | Access token used after logout (30-min window) | Continued access post-logout | Medium | Short 30-min TTL | Accepted residual — document in runbook |
| T-05 | Tampering | Refresh token reuse after revocation | Session hijack | Low | revoked_at DB check | Must verify check is transactional |
| T-06 | Tampering | Role claim in JWT stale (admin→user demotion, valid JWT has admin role) | Privilege escalation for ≤30 min | Low | Short JWT TTL limits window | Accepted residual — mitigated by TTL |
| T-07 | Repudiation | Auth events not in ticket_events (auth is outside ticket domain) | Cannot audit login activity | Low | Accepted per spec | Recommended: application-level auth log — **see F-05** |
| T-08 | Information Disclosure | Credentials/tokens leaked in structured logs | Secret exposure | Medium | PII redaction processor planned (T017) | Must cover: password, token_hash, access_token, refresh_token — **see F-06** |
| T-09 | Information Disclosure | Error messages reveal user existence (valid email vs. unknown) | Username enumeration | Medium | Not yet specified | Must return identical 401 for both cases — **see F-07** |
| T-10 | Information Disclosure | Stack traces in 4xx/5xx responses | Internal detail exposure | Medium | Not yet specified | Must suppress stack traces — **see F-08** |
| T-11 | Denial of Service | Token table bloat (unbounded refresh_tokens rows) | DB performance degradation | Low | expires_at column exists | Add periodic cleanup job or TTL — **see F-09** |
| T-12 | Elevation of Privilege | Bypass RBAC by calling routes without `get_current_user` | Unauthorized action | Low-Medium | Dependency injection pattern | Must verify ALL non-public routes apply dependency — **see F-10** |
| T-13 | Elevation of Privilege | Frontend stores refresh_token in localStorage — XSS extracts it | Session hijack via XSS | High if stored in localStorage | T024 stores access_token in memory | Refresh token storage not specified — **see F-01** |

---

## Findings

### F-01 — Refresh Token Client Storage Not Specified [BLOCKER]

**Threat**: T-13
**Detail**: T024 specifies that the JWT access token must be stored in Zustand memory
(not localStorage/sessionStorage). However, neither T024 nor T025 specifies where the
refresh token is stored on the client. If the refresh token is persisted in localStorage
to survive page refreshes, it is accessible to any JavaScript running on the page. A
single stored XSS vulnerability would allow an attacker to extract the refresh token
and maintain persistent access even after the tab is closed.

**Required Fix**: The implementation specification MUST explicitly state one of:

1. **Memory-only** (recommended for highest security): Both access_token and
   refresh_token stored in Zustand memory only. Session lost on page refresh. User must
   re-authenticate after page reload. Simplest to implement securely.

2. **HttpOnly cookie for refresh token** (recommended for usability): Backend sets
   refresh_token as an httpOnly, Secure, SameSite=Strict cookie. JS cannot access it.
   Frontend never sees raw refresh token value. Requires backend to read it from cookie
   in POST /auth/refresh rather than request body. Requires CSRF protection on
   /auth/refresh endpoint.

3. **SessionStorage** (weak mitigation): Survives tab refreshes but not new tabs or
   browser restart. Still accessible to XSS. Only acceptable with strict CSP.

Option 1 is required if no httpOnly cookie mechanism is implemented. Option 2 requires
OpenAPI contract and implementation changes.

**Acceptance Criterion**: Before T024 is considered complete, the implementation comment
in auth.ts must explicitly document where refresh_token is stored and why.

---

### F-02 — No Rate Limiting on Login Endpoint [HIGH]

**Threat**: T-01
**Detail**: POST /auth/login has no rate limiting in the current design. bcrypt slows
individual attempts but does not prevent distributed credential stuffing where each
source IP makes only a few requests.

**Required Action**: At minimum, document this as a known gap with a tracking item.
For production deployments, add one of:
- IP-based rate limiting in reverse proxy (nginx/caddy)
- Application-level rate limiting (slowapi / fastapi-limiter)
- Account lockout after N failed attempts (with unlock mechanism)

**Acceptance Criterion**: Rate limiting is either implemented (preferred) or explicitly
documented as a known residual risk in `devops/security-review.md` with an owner and
target remediation version.

---

### F-03 — JWT Algorithm Must Be Pinned on Decode [HIGH]

**Threat**: T-02
**Detail**: python-jose's `jose.jwt.decode()` accepts an `algorithms` parameter. If this
is omitted or set to `None`, the library may accept tokens signed with `alg:none` or
with unexpected algorithms. The implementation must explicitly pass `algorithms=["HS256"]`
to every `jwt.decode()` call.

**Required Fix**: In `backend/src/core/security.py`:

```python
# REQUIRED — never omit algorithms parameter
payload = jwt.decode(
    token,
    settings.secret_key,
    algorithms=["HS256"],  # explicit, never None or []
)
```

**Acceptance Criterion**: Code review T030 must verify that every `jwt.decode()` call
passes `algorithms=["HS256"]` explicitly.

---

### F-04 — SECRET_KEY Entropy Must Be Enforced [HIGH]

**Threat**: T-03
**Detail**: If SECRET_KEY is a short or predictable string (e.g. "secret", "changeme"),
JWTs can be brute-forced offline. The application must validate key strength at startup.

**Required Fix**: In `backend/src/core/config.py`, add a startup validator:

```python
@field_validator("secret_key")
def secret_key_must_be_strong(cls, v):
    import secrets
    if len(v) < 32:
        raise ValueError("SECRET_KEY must be at least 32 characters")
    return v
```

Additionally, `.env.example` must include a note: `SECRET_KEY=<generate with: python -c
"import secrets; print(secrets.token_hex(32))">`

**Acceptance Criterion**: Application fails to start if SECRET_KEY is < 32 chars.

---

### F-05 — Auth Events Not Logged (Observability Gap) [MEDIUM]

**Threat**: T-07
**Detail**: The spec correctly excludes auth from `ticket_events` (auth is outside the
ticket domain). However, there is no specification for auth activity logging (login
success, login failure, token refresh, logout). Without this, it is impossible to detect
brute force, credential stuffing, or account takeover in production.

**Required Fix**: T017 (structlog middleware) must emit structured log lines for:
- Login success: `{event: "auth.login_success", user_id, user_email (hashed or partial), ip}`
- Login failure: `{event: "auth.login_failed", email_hash, ip}` — do NOT log the attempted email in plaintext
- Token refresh: `{event: "auth.token_refreshed", user_id, ip}`
- Logout: `{event: "auth.logout", user_id, ip}`

These are log lines only, not database records.

**Acceptance Criterion**: T022 implementation emits structured log events for all four
auth outcomes. Log fields must not include raw passwords or tokens (covered by F-06).

---

### F-06 — Log Redaction Must Cover All Secret Fields [MEDIUM]

**Threat**: T-08
**Detail**: T017 specifies a PII redaction processor. The required field list must be
complete. Fields that MUST be redacted from all log output:
- `password`
- `hashed_password`
- `token`
- `token_hash`
- `access_token`
- `refresh_token`
- `secret_key` / `SECRET_KEY`
- Any field containing the substring `_token`, `_secret`, `_password`, `_hash`

**Required Fix**: The redaction processor in T017 must use a denylist matching these
field names (case-insensitive), applied recursively to nested dicts/JSONB payloads.
The redaction must replace with `"[REDACTED]"` not empty string.

**Acceptance Criterion**: Unit test verifies that a log record containing `password`,
`access_token`, and `refresh_token` fields produces `[REDACTED]` in all three fields.

---

### F-07 — Login Must Not Reveal User Existence [MEDIUM]

**Threat**: T-09
**Detail**: If the API returns different error messages for "email not found" vs. "wrong
password", attackers can enumerate valid email addresses. Both cases must return HTTP 401
with identical response body.

**Required Fix**: In `backend/src/api/v1/auth.py`, login handler must use a
constant-time check path:

```python
# Always look up the user first, then verify
user = await get_user_by_email(session, email)
# Use a dummy hash to prevent timing oracle if user not found
hash_to_check = user.hashed_password if user else DUMMY_BCRYPT_HASH
valid = bcrypt.verify(password, hash_to_check)
if not user or not valid:
    raise HTTPException(status_code=401, detail="Invalid credentials")
```

**Acceptance Criterion**: Contract test verifies POST /auth/login with unknown email
returns 401 with the same `detail` string as wrong password for known email.

---

### F-08 — Stack Traces Must Not Appear in API Responses [MEDIUM]

**Threat**: T-10
**Detail**: FastAPI's default unhandled exception handler can return Python stack traces
in development mode. These must be suppressed in all environments.

**Required Fix**: In `backend/src/main.py`:
- Set `debug=False` (or read from `settings.environment != "development"`)
- Add a global exception handler that returns `{"detail": "Internal server error"}` for
  unhandled exceptions, and logs the full traceback via structlog

**Acceptance Criterion**: A request that triggers an unhandled exception returns 500
with `{"detail": "Internal server error"}` and no stack trace in the response body.

---

### F-09 — Refresh Token Cleanup Required [LOW]

**Threat**: T-11
**Detail**: The `refresh_tokens` table accumulates rows indefinitely — expired and
revoked tokens are never removed. With 10–200 concurrent users and long-lived refresh
tokens, this table will grow unboundedly.

**Required Action**: Add a note in `devops/runbook.md` that the `refresh_tokens` table
requires periodic cleanup. A maintenance query or background task should delete rows
where `expires_at < now() - interval '7 days'`.

**Acceptance Criterion**: Runbook documents the cleanup procedure.

---

### F-10 — All Non-Public Routes Must Apply get_current_user [MEDIUM]

**Threat**: T-12
**Detail**: FastAPI routes are unauthenticated by default. If any route handler in
tickets.py, assignments.py, progress.py, transitions.py, events.py, or projects.py
omits the `Depends(get_current_user)` parameter, it becomes publicly accessible.

**Required Fix**:
1. Apply the `get_current_user` dependency at the **router level** (not per-route) for
   all protected routers. Example:
   ```python
   router = APIRouter(dependencies=[Depends(get_current_user)])
   ```
2. Only `/auth/login`, `/auth/refresh`, `/health`, and `/ready` should be public.

**Acceptance Criterion**: T030 code review must verify that the protected router pattern
is used and no protected route accidentally omits auth.

---

### F-11 — bcrypt Cost Factor Must Be ≥ 12 [MEDIUM]

**Threat**: T-01 (credential cracking post-breach)
**Detail**: The plan specifies bcrypt but not the cost factor. Default in many libraries
is 12, but some set it to 10 or lower. A cost factor below 12 makes offline brute-force
significantly faster.

**Required Fix**: In `backend/src/core/security.py`:
```python
BCRYPT_ROUNDS = 12  # minimum; increase to 13–14 if server hardware allows <300ms
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
```

**Acceptance Criterion**: Unit test verifies that `bcrypt.gensalt()` is called with
`rounds` parameter and that the stored hash prefix indicates cost ≥ 12 (`$2b$12$` or higher).

---

### F-12 — Refresh Token Rotation Not Implemented [LOW]

**Threat**: T-05
**Detail**: POST /auth/refresh issues a new access_token but does not rotate the refresh
token (issue a new refresh_token and revoke the old one). A stolen refresh token is
valid until it expires, even after the user actively refreshes.

**Required Action**: For v1, this is accepted as a residual risk given the revocation
mechanism (logout revokes the token). Document in `devops/security-review.md`.

**Acceptance Criterion**: Runbook documents that refresh token rotation is not
implemented in v1 and that users should be instructed to logout to revoke sessions.

---

### F-13 — Refresh Token TTL Not Specified [LOW]

**Detail**: The plan specifies 30-min JWT TTL but does not specify refresh token TTL.
Unspecified TTL risks either very long-lived sessions (security risk) or very short
sessions (UX friction).

**Required Fix**: Define refresh token TTL in config. Recommended: 7 days for internal
team tool. Add `REFRESH_TOKEN_EXPIRE_DAYS=7` to `.env.example`.

**Acceptance Criterion**: T005 (.env.example) includes `REFRESH_TOKEN_EXPIRE_DAYS=7`
and T018 (security.py) reads this value when creating refresh tokens.

---

### F-14 — No CSRF Protection for State-Changing Endpoints [INFORMATIONAL]

**Detail**: Since auth uses Bearer tokens (not cookies), CSRF is not a risk for
the current design. If refresh token is moved to httpOnly cookie (Option 2 for F-01),
CSRF protection must be added to POST /auth/refresh.

**Action**: Only relevant if F-01 is resolved via httpOnly cookie approach. Track as
conditional requirement.

---

## Security Tests Required

| Test ID | Description | Covers |
|---|---|---|
| SEC-001 | POST /auth/login with valid email + wrong password returns 401 with identical body as unknown email + any password | F-07 |
| SEC-002 | POST /auth/login 10 rapid attempts — verify server does not crash (rate limiting implementation test where applicable) | F-02 |
| SEC-003 | JWT signed with `alg:none` is rejected with 401 | F-03 |
| SEC-004 | JWT signed with wrong key is rejected with 401 | F-03 |
| SEC-005 | Application fails to start with SECRET_KEY shorter than 32 chars | F-04 |
| SEC-006 | POST /auth/logout then immediate protected request with same JWT returns 200 (JWT not revocable — document this) | T-04 |
| SEC-007 | POST /auth/refresh with revoked refresh token returns 401 | T-05 |
| SEC-008 | POST /auth/refresh with expired refresh token returns 401 | F-13 |
| SEC-009 | Log output for failed login contains [REDACTED] not plaintext password | F-06 |
| SEC-010 | GET /api/v1/projects with no Authorization header returns 401 | F-10 |
| SEC-011 | bcrypt hash of new password has cost factor prefix $2b$12$ or higher | F-11 |

---

## Required Mitigations Before Phase 3 (Blockers)

The following findings MUST be resolved before any user story work proceeds:

| # | Finding | Severity | Resolution |
|---|---|---|---|
| 1 | F-01: Refresh token client storage undefined | **BLOCKER** | Specify storage strategy in T024; update task spec |
| 2 | F-03: JWT algorithm not pinned on decode | **HIGH** | Must pin `algorithms=["HS256"]` in security.py |
| 3 | F-04: SECRET_KEY entropy not enforced | **HIGH** | Add startup validator in config.py |
| 4 | F-10: Router-level auth dependency | **MEDIUM** | Apply `dependencies=[Depends(get_current_user)]` at router |

All HIGH findings (F-02, F-05, F-06, F-07, F-08, F-11) must be addressed in implementation.
MEDIUM/LOW findings must be tracked and documented in the final security review (T081).

---

## Residual Risks (Accepted for v1)

| Risk | Severity | Rationale | Owner | Target |
|---|---|---|---|---|
| Access tokens not revocable post-logout (30-min window) | Medium | Short TTL accepted; standard JWT tradeoff | Engineering | v2 — consider token blocklist |
| No rate limiting on login (if not implemented) | Medium | Must be documented; operational mitigation via reverse proxy | DevOps | v1.1 |
| Stale role claim in JWT (≤30 min after demotion) | Low | Short TTL limits window; admin demotion is rare | Engineering | v2 |
| Refresh token rotation not implemented | Low | Revocation via logout available | Engineering | v2 |

---

## Decision

> **APPROVED WITH RISKS** (conditional on BLOCKER and HIGH findings being addressed in implementation)

The authentication design is structurally sound:
- bcrypt for password storage is correct
- Short-lived JWT (30 min) limits damage from token theft
- Refresh tokens stored as SHA-256 hashes in DB prevents raw token exposure from DB compromise
- Server-side revocation via `revoked_at` enables logout
- Frontend memory-only access token storage (T024) correctly avoids localStorage XSS

**Implementation MUST address the following before merging Phase 2 and before Phase 3 begins:**

1. **F-01** (BLOCKER): Specify and implement refresh token client storage strategy
2. **F-03** (HIGH): Pin JWT decode algorithms to `["HS256"]`
3. **F-04** (HIGH): Enforce SECRET_KEY minimum entropy at startup
4. **F-10** (MEDIUM): Apply authentication at router level, not per-route
5. **F-07** (MEDIUM): Constant-time login response regardless of user existence
6. **F-11** (MEDIUM): bcrypt cost factor ≥ 12

I will re-review auth.py, security.py, and auth.ts implementations during T030 code review
coordination. This approval is conditional — downstream work MUST NOT merge until the
BLOCKER finding (F-01) is explicitly resolved in T024/T025 implementation.
