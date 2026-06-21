# Final Security Review: Ticket Management System

**Reviewer**: Security Architect
**Date**: 2026-05-23
**Scope**: Complete system — all phases and user stories
**Input**: spec.md, plan.md, data-model.md, contracts/openapi.yaml, tasks.md,
security-review-auth.md (T029), security-review-transitions.md (T061)

---

## Executive Summary

The Ticket Management System is an internal team tool for tracking software delivery
lifecycle progress. It handles moderate-sensitivity data (team activity records, work
descriptions) with no payment data, PII beyond email, or compliance obligations called
out. The threat model focuses on internal misuse, unauthorized data access, and
workflow integrity.

**Overall security posture**: Acceptable for an internal tool with the controls defined
below. No fundamental architectural security flaws identified. Key risks are in
implementation details (JWT handling, row-level locking, IDOR) and operational
hardening (rate limiting, secret management).

**Phase 2 gate (T029)**: APPROVED WITH RISKS — see security-review-auth.md
**Phase 5 gate (T061)**: APPROVED WITH CONDITIONS — see security-review-transitions.md

---

## System-Wide Threat Model

### Assets

| Asset | Sensitivity | Notes |
|---|---|---|
| User credentials (passwords) | Critical | bcrypt-hashed at rest; only at-risk during transit (TLS) |
| JWT access tokens | High | 30-min TTL; memory-only on client |
| Refresh tokens | High | Stored as SHA-256 hash in DB |
| Ticket content (titles, descriptions) | Medium | Internal team work descriptions |
| Progress update content | Medium | Individual contributor records |
| Activity event history | Medium-High | Immutable audit log; must not be tampered |
| User email addresses | Medium | Login identifiers; limited PII |
| User role assignments | High | Determines privilege level |
| Project structure | Low | Internal project names/slugs |

### Actors

| Actor | Trust | Notes |
|---|---|---|
| Unauthenticated user | Zero | May only access /auth/login, /health, /ready |
| Authenticated user (role: user) | Low | Constrained to assigned ticket actions |
| Authenticated admin | Medium | Broader management actions; still bound by ticket RBAC |
| Database administrator | High (insider) | Direct DB access; out of scope for app controls |
| Attacker (external) | Hostile | No direct DB access; API is attack surface |
| Attacker (compromised account) | Hostile | Authenticated, but wrong identity |

### Trust Boundaries

```
[Internet / Browser]
    ↓ HTTPS (TLS 1.2+)
[Reverse Proxy / Load Balancer]  ← rate limiting, TLS termination
    ↓ HTTP (internal)
[FastAPI Backend Process]  ← JWT verification, RBAC, business logic
    ↓ asyncpg / SQLAlchemy
[PostgreSQL 15]  ← row-level security not used; app enforces access control
    ↓
[File System / Environment]  ← secrets in env vars; not in source
```

### Attack Surface

| Surface | Exposure | Controls |
|---|---|---|
| POST /auth/login | Internet | bcrypt, rate limiting (required) |
| POST /auth/refresh | Internet | DB token lookup with revocation check |
| All /api/v1/* endpoints | Internet (requires JWT) | JWT auth dependency |
| /health, /ready | Internet | Read-only; no sensitive data |
| PostgreSQL port | Internal only | Not publicly exposed |
| Admin user account | Internal | Role-based; strong password required |

---

## Finding Catalog

### Category 1: IDOR (Insecure Direct Object Reference)

#### F-IDOR-01 — Ticket IDOR: No Project Membership Verification [HIGH]

**Affected endpoints**: GET/PATCH/DELETE /tickets/{ticket_id}, all sub-resources

**Detail**: The API uses UUIDs as ticket identifiers. UUID v4 is not guessable, but the
security model must not rely on unpredictability alone. The current design has no
project-level access control — all authenticated users can access all projects and
tickets. This is an explicit design decision (spec: "project-level access control is
out of scope").

**Risk**: Any authenticated user can read, edit, or view events for any ticket in any
project, including tickets in projects they have no business relationship with.

**Mitigations in place**: UUID v4 (non-sequential, non-guessable). All endpoints require
JWT authentication.

**Assessment**: For a small internal team tool where all users are trusted employees
accessing the same instance, this is an accepted architectural decision. The spec
explicitly documents this scope limitation.

**Required Action**:
1. Document in runbook that all authenticated users have read access to all tickets.
2. If this system is ever multi-tenant (multiple organizations on one instance), this
   becomes a critical IDOR — project membership controls MUST be added before that.
3. Soft-deleted tickets (deleted_at IS NOT NULL) must return 404 on GET /tickets/{id}
   — not 403. Never confirm existence of deleted resources.

**Severity for current scope**: Low (accepted residual — documented limitation)
**Severity if multi-tenant**: Blocker

---

#### F-IDOR-02 — Progress Update IDOR: Any User Can Read Any Assignee's Update [LOW]

**Affected endpoint**: GET /tickets/{ticket_id}/progress

**Detail**: This endpoint returns all progress updates for a ticket. Any authenticated
user (including non-assignees) can read the detailed progress notes of all assignees.

**Assessment**: This is consistent with the spec — "Ticket progress records are visible
to all project members" (US2 scenario 2). Accepted by design.

**Required Action**: Document in runbook that progress updates are not confidential —
visible to all authenticated users.

---

#### F-IDOR-03 — User ID Enumeration via Assignment API [MEDIUM]

**Affected endpoints**: POST /tickets/{id}/assignments, DELETE /tickets/{id}/assignments/{user_id}

**Detail**: The assignment endpoints accept `user_id` as a parameter. An attacker can
probe valid user IDs by attempting to assign arbitrary UUIDs and observing whether the
response is 404 (user not found) vs. 201 (assigned). This allows enumeration of valid
user UUIDs.

**Impact**: Low for an internal tool (users likely know each other's IDs from the UI),
but UUIDs from one context could be used to target users in other ways.

**Required Mitigation**: Return 404 (not 403) for both "user not found" and "user is
already assigned" to reduce information leakage about user existence. Consistent 422
for validation errors is acceptable.

**Severity**: Low

---

### Category 2: Event Store Tamper Resistance

#### F-EVT-01 — No Database-Level Write Restriction on ticket_events [HIGH]

**Detail**: The `ticket_events` table is designated append-only. The application layer
promises never to issue UPDATE or DELETE against it. However, there is no database-level
enforcement of this constraint. A compromised application process, a SQL injection
vulnerability, or a developer mistake could delete or modify event records without any
database safeguard.

**Required Mitigations**:

Option A (recommended): Create a dedicated PostgreSQL role for the application with
only INSERT + SELECT privileges on `ticket_events`. No UPDATE or DELETE granted.

```sql
-- In migration or DB setup
CREATE ROLE app_user LOGIN PASSWORD '...';
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO app_user;
-- Revoke UPDATE/DELETE specifically on ticket_events
REVOKE UPDATE, DELETE ON ticket_events FROM app_user;
-- Or more precisely: GRANT only SELECT, INSERT on ticket_events to app_user
```

Option B (minimum): Add a PostgreSQL trigger that raises an exception on UPDATE or DELETE:

```sql
CREATE OR REPLACE FUNCTION prevent_ticket_events_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'ticket_events is append-only — UPDATE/DELETE not permitted';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ticket_events_immutable
BEFORE UPDATE OR DELETE ON ticket_events
FOR EACH ROW EXECUTE FUNCTION prevent_ticket_events_mutation();
```

**Acceptance Criterion**: Either a database-level role restriction or a trigger must be
in place. Code review and T030 must verify this.

---

#### F-EVT-02 — Event store does not record authentication events [MEDIUM]

**Detail**: Auth events (login, refresh, logout) are not recorded in `ticket_events`
because auth is outside the ticket domain. This is correct by design. However, the
structlog-based auth event logging (F-05 from security-review-auth.md) fills this gap
for operational visibility.

**Required Action**: Ensure T022 implements the structured auth log events defined in
F-05 of security-review-auth.md. These logs are the only forensic record for auth
activity.

---

#### F-EVT-03 — Event metadata can contain arbitrary JSONB [LOW]

**Detail**: The `prev_state`, `new_state`, and `metadata` columns accept arbitrary JSONB.
If event emission code passes unsanitized user-controlled input into these fields, it
could:
1. Include sensitive data (passwords, tokens) in the immutable audit log
2. Cause performance issues via very large JSONB payloads

**Required Mitigation**:
- The `event_service.py` must only include pre-defined fields in state snapshots —
  never pass raw request bodies or user-provided content directly into event state fields.
- Sensitive fields (`password`, `hashed_password`, `token_hash`) must never appear in
  event JSONB.

**Acceptance Criterion**: Code review verifies event_service.py and all callers pass
structured snapshots, not raw input dicts.

---

### Category 3: SQL Injection

#### F-SQL-01 — SQLAlchemy ORM Parameterization [LOW — Design-Level Assessment]

**Detail**: The system uses SQLAlchemy 2.0 ORM with asyncpg. SQLAlchemy's ORM layer
generates parameterized queries for all standard operations (`.filter()`, `.where()`,
`.update()`, etc.). SQL injection is therefore the default-safe path.

**Risk areas that require code review verification**:
1. Any use of `text()` function for raw SQL fragments — these bypass parameterization
2. Any use of Python string formatting (f-strings, `%`) inside SQLAlchemy expressions
3. The `slug` field on projects — if ever used in a `text()` query without binding
4. Filter parameters from query strings (status, assignee_id) being passed directly
   into query fragments rather than bound parameters

**Required Acceptance Criterion** (T030 code review):
- Search for `text(` in all service files — every occurrence must be reviewed
- Search for f-strings inside SQLAlchemy query calls — flag any that include user input
- The status filter in GET /tickets must use enum validation (Pydantic) before the DB
  query — Pydantic v2 enum coercion + SQLAlchemy enum comparison is safe

**Overall SQL injection risk**: Low, given ORM usage. Zero instances found in design.
Verification required in implementation.

---

### Category 4: Token Revocation Completeness

#### F-TOKEN-01 — Access Token Not Revocable Post-Logout [MEDIUM]

**Detail**: JWT access tokens (30-min TTL) are not revocable. After POST /auth/logout,
the refresh token is revoked, but a valid access token from the same session continues
to work for up to 30 minutes.

**Attack scenario**: An attacker who intercepts an access token (e.g., via MITM on
non-TLS connection, or from a memory dump) can use it for up to 30 minutes after the
legitimate user logs out.

**Mitigations in place**:
- Short 30-minute TTL limits the exposure window
- TLS in transit prevents trivial interception
- Memory-only storage prevents persistent token theft via XSS

**Assessment**: This is the standard JWT tradeoff. The 30-minute window is acceptable
for an internal team tool. Documented as a known residual risk.

**If zero-trust access revocation is needed in the future**: Add a token blocklist
table (JTI claim + revocation timestamp). The plan's constitution check already
mentions this as the design intent.

**Required Action**: Document in runbook that logout does not immediately invalidate
the current session's access token.

---

#### F-TOKEN-02 — Multi-Session Management Not Implemented [LOW]

**Detail**: A user may have multiple active sessions (multiple browsers/devices). POST
/auth/logout revokes only the refresh token included in the current logout request.
Other sessions remain active.

**Impact**: Low for internal tool. Users cannot see or revoke other sessions.

**Required Action**: Document in runbook. For elevated security, add "logout all
sessions" endpoint (revoke all refresh_tokens for a user_id).

---

#### F-TOKEN-03 — Token Revocation on User Deletion/Suspension Not Defined [MEDIUM]

**Detail**: If an administrator deactivates or deletes a user account, existing JWT
access tokens for that user remain valid until expiry (up to 30 minutes). The
`refresh_tokens` table supports bulk revocation via `user_id`, but the API has no
endpoint for this.

**Required Fix**: Add an admin operation (or runbook procedure) to revoke all refresh
tokens for a specific user_id:

```sql
UPDATE refresh_tokens SET revoked_at = now()
WHERE user_id = :user_id AND revoked_at IS NULL;
```

The runbook must document this procedure for offboarding scenarios.

---

### Category 5: Additional Security Controls

#### F-ADD-01 — Input Validation: Long Text Fields [MEDIUM]

**Detail**: The `description` field on tickets is TEXT with no length limit in the
database schema. The `content` field on progress_updates is TEXT with no length limit.
While Pydantic v2 validates `title` (maxLength: 500), description and content are
unbounded.

**Risk**: Very large payloads could cause:
1. Memory pressure on the server processing JSONB events
2. Performance degradation on full-text reads
3. Storage bloat in the event store (description content is snapshotted in ticket_events)

**Required Fix**: Add maxLength constraints in Pydantic schemas:
- `description`: maxLength 10,000 characters
- `progress_updates.content`: maxLength 10,000 characters

This is a defense-in-depth measure rather than a security blocker.

---

#### F-ADD-02 — CORS Policy Not Defined [HIGH]

**Detail**: The FastAPI application's CORS policy is not specified in the design.
If CORS is misconfigured (e.g., `allow_origins=["*"]` with `allow_credentials=True`),
cross-origin requests from attacker-controlled sites could make authenticated requests
using the victim's cookies or tokens.

**Note**: Since the auth design uses Bearer tokens (not cookies) for the current
implementation, CORS misuse is limited — JavaScript on another origin cannot read
the Bearer token from memory (Zustand store). However, if the refresh token is ever
moved to a cookie (F-01 Option 2), CORS becomes critical.

**Required Fix**: In `backend/src/main.py`, configure CORS explicitly:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],  # specific origin, NOT "*"
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

Add `FRONTEND_URL` to `.env.example` and to Pydantic settings.

---

#### F-ADD-03 — Security Headers Not Defined [MEDIUM]

**Detail**: The design does not specify HTTP security response headers. For a browser
SPA, the following headers should be set:

| Header | Recommended Value | Purpose |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `X-Frame-Options` | `DENY` | Prevent clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limit referrer leakage |
| `Content-Security-Policy` | `default-src 'self'` (minimal) | Prevent XSS |

These can be added via a FastAPI middleware or the reverse proxy.

---

#### F-ADD-04 — Soft-Deleted Ticket Still in DB [LOW]

**Detail**: Tickets with `deleted_at IS NOT NULL` are soft-deleted — filtered out of
API responses but remain in the database. All queries must consistently apply
`WHERE deleted_at IS NULL`. If any query path forgets this filter, deleted ticket data
leaks back into API responses.

**Required Fix**: Create a SQLAlchemy query helper or ORM default filter that applies
`deleted_at IS NULL` automatically on all Ticket queries. This prevents accidental
omission in service code.

---

#### F-ADD-05 — Pagination Defaults and Maximum Page Size [LOW]

**Detail**: The API defines `page_size` with a maximum of 100. Without server-side
enforcement of this maximum, a client can request an unbounded number of records.

**Required Fix**: In GET /projects/{id}/tickets and GET /tickets/{id}/events, the
Pydantic query parameter model must enforce `le=100` (less than or equal to):

```python
class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
```

---

## Supply Chain and Dependency Security

#### F-SC-01 — pip-audit Required in CI [MEDIUM]

**Detail**: The constitution check specifies `pip-audit` in CI. This must scan for
known CVEs in all backend dependencies on every PR and push to main.

**Required**: `pip-audit` step in `.github/workflows/ci.yml` (T076) must:
1. Run `pip-audit --requirement requirements.txt`
2. Fail the build on any HIGH or CRITICAL CVE
3. Generate an audit report artifact

#### F-SC-02 — Frontend Dependency Audit [MEDIUM]

**Detail**: Frontend dependencies (React, React Query, etc.) must also be scanned.

**Required**: `npm audit --audit-level=high` in CI frontend stage (T076).

---

## Privacy and Data Handling

### Data Classification

| Data Category | Fields | Classification | Notes |
|---|---|---|---|
| Authentication credentials | email, hashed_password | High | email is PII (email address) |
| Work content | ticket title, description, progress content | Internal | Not personal sensitive data |
| Activity records | ticket_events.actor_id, occurred_at, event_type | Internal | Links actions to identity |
| Session data | refresh_tokens | High | Can be used for unauthorized access |

### Data Minimization Assessment

The system collects only data necessary for its function:
- User email (login identifier) — required
- Bcrypt hash (authentication) — required; plaintext never stored
- Actor identity on events (accountability) — required per design principle
- User role at event time — required for audit integrity

No unnecessary PII collection identified.

### Retention Recommendations

- `ticket_events`: Retain indefinitely (append-only, immutable audit requirement)
- `refresh_tokens`: Delete expired+revoked tokens older than 7 days (F-09 from auth review)
- `progress_updates`: Retain indefinitely (linked to audit trail)
- `tickets` (soft-deleted): Recommend hard-delete policy after 90 days of soft deletion

---

## Security Checklist Verification

| Item | Status | Notes |
|---|---|---|
| Assets and trust boundaries identified | ✅ | See threat model above |
| Authentication and authorization assumptions explicit | ✅ | JWT + RBAC; assignment-based for transitions |
| Privileged operations server-side enforced and auditable | ✅ | All enforcement in FastAPI dependency layer |
| Inputs treated as untrusted | ⚠️ | Pydantic validates; text field length limits needed (F-ADD-01) |
| Secrets not hardcoded, logged, or exposed | ⚠️ | Log redaction required (F-06); entropy enforcement required (F-04) |
| Encryption in transit | ✅ | TLS required (assumed — not specified in implementation) |
| Error handling does not leak details | ⚠️ | Stack trace suppression required (F-08) |
| Dependencies and supply-chain | ⚠️ | pip-audit required (F-SC-01) |
| Logging, alerting, incident response | ⚠️ | Auth event logging required (F-05) |
| Abuse cases and negative tests defined | ✅ | SEC-001 through SEC-TR-008 |
| Residual risks have owners and due dates | ✅ | See Residual Risks section below |

---

## Residual Risks (Accepted for v1)

| Risk | Severity | Rationale | Owner | Target Version |
|---|---|---|---|---|
| No project-level access control (all users see all projects) | Low (internal tool) | Explicit scope decision; BLOCKER if multi-tenant | Product Manager | v2 if multi-tenant |
| Access token not revocable post-logout (30-min window) | Medium | Standard JWT tradeoff; mitigated by short TTL | Engineering | v2 — optional blocklist |
| No rate limiting on /auth/login (if not implemented) | Medium | Operational mitigation via reverse proxy | DevOps | v1.1 |
| Refresh token rotation not implemented | Low | Revocation via logout available | Engineering | v2 |
| No "logout all sessions" endpoint | Low | Runbook procedure available | Engineering | v2 |
| Text field length not bounded (description, content) | Low | Defense-in-depth; not exploitable | Engineering | v1.1 |
| Soft-deleted ticket data retained indefinitely | Low | Audit requirement; recommend 90-day hard-delete policy | Engineering | v1.1 |

---

## Required Actions Before Release

### Blockers (must fix before release)

| # | Finding | Assigned To |
|---|---|---|
| 1 | F-01 (auth): Refresh token client storage not specified | Frontend / T024 |
| 2 | F-EVT-01: No DB-level write restriction on ticket_events | Backend / DevOps (DB migration) |
| 3 | F-ADD-02: CORS policy not defined | Backend / T023 (main.py) |

### High Severity (must fix or formally accept)

| # | Finding | Assigned To |
|---|---|---|
| 4 | F-03 (auth): JWT algorithm not pinned | Backend / T018 |
| 5 | F-04 (auth): SECRET_KEY entropy enforcement | Backend / T015 |
| 6 | F-IDOR-01 note: Soft-deleted ticket returns 404 not 403 | Backend / T037 |
| 7 | F-TR-04 (transitions): SELECT FOR UPDATE on ticket + assignments | Backend / T054 |
| 8 | F-TR-02 (transitions): Assignment-based RBAC in T056 | Backend / T056 |
| 9 | F-TR-01 (transitions): Progress gate business rule defined | Product Manager → Backend |

### Medium Severity (fix in planned timeframe)

All F-02, F-05, F-06, F-07, F-08, F-10, F-11, F-SC-01, F-SC-02, F-TOKEN-03, F-ADD-03 —
see individual findings above.

---

## Security Tests Summary

All security tests from previous reviews plus:

| Test ID | Area | Description |
|---|---|---|
| SEC-001–011 | Auth | See security-review-auth.md |
| SEC-TR-001–008 | Transitions | See security-review-transitions.md |
| SEC-IDOR-001 | IDOR | GET /tickets/{id} for soft-deleted ticket returns 404 not 200 |
| SEC-IDOR-002 | IDOR | Authenticated user can access tickets in all projects (document expected behavior) |
| SEC-EVT-001 | Event store | Attempt direct DB UPDATE on ticket_events — must fail with permission error |
| SEC-EVT-002 | Event store | Every ticket action results in exactly one ticket_events row |
| SEC-SQL-001 | SQL | Search codebase for `text(` and f-strings in queries; zero unsafe instances |
| SEC-TOKEN-001 | Revocation | Logout revokes refresh token; subsequent refresh attempt returns 401 |
| SEC-TOKEN-002 | Revocation | Access token still valid for up to 30s after logout (documented behavior) |
| SEC-ADD-001 | CORS | Cross-origin request from non-frontend origin is rejected |

---

## Decision

> **APPROVED WITH CONDITIONS**

The Ticket Management System design has a sound security foundation for an internal team
tool. The core authentication model, event store design, RBAC layer, and data model are
appropriate for the use case. The primary risks are implementation-level details that
must be addressed before release, not fundamental architectural flaws.

**Release is BLOCKED until the following are resolved:**
1. F-01 (T024): Refresh token client storage must be explicitly specified and secured
2. F-EVT-01: DB-level write restriction on ticket_events (trigger or role grant)
3. F-ADD-02: CORS policy must be explicitly configured
4. F-TR-04 (T054): `SELECT ... FOR UPDATE` on ticket and assignments in transition
5. F-TR-02 (T056): Assignment-based RBAC for transitions (not role-based)
6. F-TR-01: Business rule for assignee-removal + transition defined and implemented

All high and medium findings must be tracked. Residual risks must be documented in
the runbook with owners and target versions.

I am available to review implementation code for any of the above findings before
the final T082 code review pass.
