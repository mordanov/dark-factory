# Security Review: Admin User Management (T008)

**Reviewer**: Security Architect
**Date**: 2026-05-24
**Scope**: Feature 002 — Phase 2 backend (T004–T007): admin Pydantic schemas, AdminService, admin API router, login block enforcement
**Gate**: T008 — Phase 4 (US2 frontend) MUST NOT start until this review is APPROVED.

---

## Threat Model

### Assets

| Asset | Sensitivity | Notes |
|---|---|---|
| User role assignments | Critical | Determines privilege level across entire system |
| User credentials (hashed passwords) | Critical | bcrypt at rest; must never appear in API responses |
| Blocked user status | High | Determines whether a user can log in |
| Admin identity (actor_id) | High | Audit trail integrity |
| User email addresses | Medium | Login identifier; limited PII |

### Actors and Trust

| Actor | Trust Level | Risk |
|---|---|---|
| Administrator (role=administrator, valid JWT) | Medium | Can create/modify/block any non-self account |
| Authenticated regular user (role=user, valid JWT) | Low | Must be rejected at all /admin/* endpoints |
| Unauthenticated caller | Zero | Must be rejected at all /admin/* endpoints (401) |
| Compromised regular-user account | Hostile | Attempts privilege escalation via /admin/* |
| Compromised admin account | Hostile | Abuses admin capabilities |

### Trust Boundaries

```
[Browser / Client]
    ↓ HTTPS
[FastAPI Router]
    ↓ JWT auth dependency (get_current_user)
    ↓ require_role("administrator") — SERVICE boundary enforcement
[AdminService]
    ↓ Self-action check (actor.id != target.id)
    ↓ bcrypt hash for new passwords
    ↓ structlog audit event
[PostgreSQL — users table]
```

**Critical invariant**: Role enforcement happens in the service layer OR at the router via `require_role()` dependency — NOT only in the frontend. The frontend guard is supplemental and not a security control.

### Entry Points

| Endpoint | Method | Risk |
|---|---|---|
| `GET /admin/users` | Read | Exposes full user list including blocked status |
| `POST /admin/users` | Write | Creates accounts; handles plain-text passwords in transit |
| `PATCH /admin/users/{id}` | Write | Role escalation / demotion; email change |
| `POST /admin/users/{id}/block` | Write | Locks out accounts |
| `POST /admin/users/{id}/unblock` | Write | Restores account access |
| `POST /auth/login` (modified) | Write | Block enforcement; timing side-channel risk |

### Threats and Abuse Cases

| ID | Threat | STRIDE | Impact | Likelihood | Required Control |
|---|---|---|---|---|---|
| T-01 | Regular user calls `GET /admin/users` directly | EoP | High | High | `require_role("administrator")` enforced at router/service level |
| T-02 | Admin POSTs new user with role=administrator | EoP | High | Medium | Allowed by design — must be audited |
| T-03 | Admin blocks all other admins (lockout) | Tampering | Medium | Low | Self-block prevention is the minimum; acceptable residual risk for internal tool |
| T-04 | `AdminUserResponse` leaks `hashed_password` | Info Disc | Critical | Low | Pydantic schema must NOT include `hashed_password` |
| T-05 | Admin edits own account to change role | EoP/Tampering | High | Medium | Self-edit prevention at service layer (same `actor.id == target.id` check) |
| T-06 | Unauthenticated call to admin endpoint | Spoofing | High | High | `get_current_user` dependency rejects 401 |
| T-07 | Audit log emits plain-text password | Info Disc | Critical | Medium | structlog calls MUST NOT log `password` field from request |
| T-08 | Blocked user re-logs in with valid password | Auth bypass | High | High | Login must check `user.blocked_at is not None` BEFORE token issuance |
| T-09 | Duplicate email on user create → 500 instead of 400 | Tampering | Low | Medium | Catch `IntegrityError` and return 400 |
| T-10 | UUID path param injection or invalid format | Tampering | Low | Low | FastAPI/Pydantic UUID type validation handles this |
| T-11 | Blocked-user check timing reveals user existence | Info Disc | Low | Low | Acceptable for internal tool; same timing as password failure |
| T-12 | Admin refresh token issues new access_token for blocked admin | Auth bypass | Medium | Low | Block only enforced at login; refresh bypass is a known residual risk (acceptable for next-login enforcement model) |

---

## Required Security Controls (Backend Implementation Checklist)

### RC-01: Role Enforcement at Router/Service Boundary

**Required**: Every admin endpoint MUST use `require_role("administrator")` as a FastAPI dependency at the router level OR equivalent enforcement inside the service.

```python
# Required pattern — router level:
@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    current_user: User = require_role("administrator"),
    db: AsyncSession = Depends(get_db),
) -> AdminUserListResponse:
    ...
```

Relying solely on frontend route guards is NOT acceptable. A regular user with a valid JWT must receive HTTP 403 from the backend.

---

### RC-02: Self-Action Prevention (Block and Edit)

**Required**: Service layer must check `actor.id == target_user_id` and raise HTTP 403 for:
- `block_user(actor, target)` where `actor.id == target.id`
- `update_user(actor, target, ...)` where `actor.id == target.id`

The unblock operation does not need this restriction (admin cannot accidentally unblock themselves as it's a no-op when they're active).

```python
# Required pattern:
if actor.id == target_user_id:
    raise HTTPException(status_code=403, detail="Cannot modify your own account")
```

---

### RC-03: bcrypt for Created User Passwords

**Required**: `create_user` in `AdminService` MUST call `hash_password(password)` from `src.core.security` before persisting.

```python
# Required:
from src.core.security import hash_password

user = User(
    email=data.email,
    hashed_password=hash_password(data.password),
    role=data.role,
)
```

Storing plain-text or reversibly-encoded passwords is a Blocker.

---

### RC-04: hashed_password MUST NOT Appear in Any Response

**Required**: `AdminUserResponse` Pydantic schema MUST NOT include `hashed_password`. The schema must be an explicit allowlist of fields, not a passthrough of the ORM model.

```python
# Required — explicit field declaration, no model_config with from_attributes passthrough of all fields:
class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str
    role: UserRole
    created_at: datetime
    blocked_at: datetime | None
    # hashed_password — NOT INCLUDED
```

---

### RC-05: Audit Log Safety — No Password Logging

**Required**: `structlog` audit calls in `AdminService` MUST NOT log the `password` field. Only metadata is acceptable.

```python
# Correct:
logger.info("admin.user_created", actor_id=str(actor.id), target_user_id=str(user.id), email=user.email)

# WRONG — do not do this:
logger.info("admin.user_created", ..., password=data.password)
```

**Required structlog fields per action**:
- `event`: one of `admin.user_created`, `admin.user_updated`, `admin.user_blocked`, `admin.user_unblocked`
- `actor_id`: `str(actor.id)`
- `target_user_id`: `str(target.id)` (for create: the new user's id)
- `action`: human-readable action name
- `timestamp`: emitted automatically by structlog UTC processor

---

### RC-06: Login Block Enforcement in auth_service.login

**Required**: After the user record is fetched and the password is NOT yet verified, check `user.blocked_at is not None` and raise HTTP 403 immediately.

```python
async def login(session, email, password):
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # REQUIRED: block check AFTER password verify to avoid user enumeration
    if user.blocked_at is not None:
        raise HTTPException(
            status_code=403,
            detail="Your account has been blocked. Contact an administrator.",
        )
    ...
```

**Note on ordering**: The block check MUST come AFTER the password verification to avoid user-enumeration timing side-channels. If we reject blocked users before checking the password, an attacker can determine which accounts exist (blocked ones respond differently from non-existent ones).

---

### RC-07: Duplicate Email — 400 not 500

**Required**: `create_user` must catch `sqlalchemy.exc.IntegrityError` (UNIQUE constraint violation on email) and re-raise as HTTP 400, not propagate as HTTP 500.

```python
from sqlalchemy.exc import IntegrityError

try:
    session.add(user)
    await session.flush()
except IntegrityError:
    await session.rollback()
    raise HTTPException(status_code=400, detail="Email already registered")
```

---

### RC-08: Router Registration

**Required**: The admin router MUST be registered under `router.py` with a prefix of `/admin` so that all endpoints appear at `/api/v1/admin/*`.

---

## Security Acceptance Criteria (T008 Review Gate)

Before posting APPROVED, I will verify each item:

| # | Check | Pass Criteria |
|---|---|---|
| AC-01 | Role enforcement | `GET /admin/users` with role=user JWT → 403; with no token → 401 |
| AC-02 | Self-block prevention | `POST /admin/users/{own_id}/block` → 403 |
| AC-03 | Self-edit prevention | `PATCH /admin/users/{own_id}` → 403 |
| AC-04 | Password hashing | `User.hashed_password` starts with `$2b$` after create |
| AC-05 | No password in response | `AdminUserResponse` JSON has no `hashed_password` field |
| AC-06 | No password in audit log | structlog call in `create_user` has no `password` key |
| AC-07 | Login block enforcement | Blocked user's `login()` returns 403 |
| AC-08 | Block-check ordering | Block check is AFTER password verify (user enumeration prevention) |
| AC-09 | Duplicate email → 400 | IntegrityError caught; 400 returned |
| AC-10 | Audit completeness | All 4 operations emit event with actor_id, target_user_id, event |

---

## Residual Risks (Accepted for Internal Tool)

| Risk | Severity | Acceptance Rationale |
|---|---|---|
| Active sessions of blocked users not terminated | Medium | By explicit design decision: next-login enforcement only. Sessions expire within 30 min. Accepted. |
| Admin can block all other admin accounts (no last-admin protection) | Low | Internal tool, small team, recoverable via DB. Accepted. |
| Refresh token can issue new access token for blocked admin | Medium | Block only enforced at login. Refresh doesn't re-check `blocked_at`. Accepted with note — to fix, add block check in `auth_service.refresh()`. Owner: backend. Tracked item. |
| No rate limiting on admin user create | Low | Internal tool, requires admin role. Low risk. |

---

## Security Review Result

### Scope Reviewed

- `backend/src/schemas/admin.py` — Pydantic schemas (T004)
- `backend/src/services/admin_service.py` — AdminService with CRUD + audit (T005)
- `backend/src/api/v1/admin.py` — Admin API router, 5 endpoints (T006)
- `backend/src/api/v1/router.py` — Router registration (T007)
- `backend/src/services/auth_service.py` — Login block enforcement (T007)
- `backend/src/models/user.py` — User model with `blocked_at` (T001)
- `backend/alembic/versions/013_add_users_blocked_at.py` — Migration (T002)

### Decision

**APPROVED** *(updated 2026-05-24 — all conditions resolved)*

Phase 4 proceeded. All conditions from the initial APPROVED WITH CONDITIONS decision have been resolved. Feature is clear for merge.

### Acceptance Criteria Results

| # | Check | Result | Evidence |
|---|---|---|---|
| AC-01 | `require_role("administrator")` on all admin endpoints | ✅ PASS | `_require_admin` dependency used on all 5 router endpoints; `require_role()` fetches user and checks `role.value` at service boundary |
| AC-02 | Self-block prevention | ✅ PASS | `block_user`: `if actor.id == user.id` → 403 |
| AC-03 | Self-edit prevention (all fields) | ✅ PASS | `update_user`: blocks all self-edits `if actor.id == user.id` → 403 (broadened in Phase 7 from role-only to all-fields) |
| AC-04 | bcrypt hashing for created users | ✅ PASS | `hashed_password=hash_password(data.password)` using `src.core.security.hash_password` (bcrypt, 12 rounds) |
| AC-05 | No `hashed_password` in response | ✅ PASS | `AdminUserResponse` explicitly declares: id, email, role, created_at, blocked_at — no hashed_password |
| AC-06 | No password in audit log | ✅ PASS | `create_user` structlog call logs actor_id, target_user_id, target_email, target_role — no password field |
| AC-07 | Login block enforcement | ✅ PASS | `auth_service.login`: checks `user.blocked_at is not None` → 403 after password verification |
| AC-08 | Block-check after password verify | ✅ PASS | Block check on line 32 comes after password verify on line 26 — prevents user-enumeration timing attack |
| AC-09 | Duplicate email → 400 | ✅ PASS | Returns HTTP 400 (aligned in Phase 7 to match contract) |
| AC-10 | Audit completeness | ✅ PASS | All 4 operations emit `event_type`, `actor_id`, `target_user_id`; create also logs `target_email` and `target_role` |

### Blockers

None.

### High / Medium Findings

**MEDIUM-01: Block/unblock not idempotent** — ✅ RESOLVED in Phase 7
- `block_user` and `unblock_user` now return the user unchanged (200) when already in the target state.

**MEDIUM-02: Duplicate email status code** — ✅ RESOLVED in Phase 7
- `create_user` now raises HTTP 400 (matching contract). `update_user` aligned consistently.

**MEDIUM-03: Self-edit restriction too narrow** — ✅ RESOLVED in Phase 7
- `update_user` now returns 403 for ANY self-edit (`if actor.id == user.id`), not just role changes.

### Required Tests

Autotester has written tests T023 and T024. Key security tests present:
- Non-admin → 403 on all admin endpoints
- Unauthenticated → 401 on list endpoint
- Self-block → 403
- Self-role-edit → 403
- Full lifecycle: create → block → login rejected → unblock → login succeeds

Additional test recommended (LOW): Admin self-email-update — whether this should return 200 or 403 needs a decision.

### Residual Risks

| Risk | Severity | Owner | Status |
|---|---|---|---|
| Active sessions of blocked users continue until natural expiry | Medium | Product | Accepted by design (next-login enforcement model per spec) |
| `auth_service.refresh` does not check `blocked_at` | Medium | Backend | Accepted; a blocked admin with a valid refresh token can get a new access token. Fix: add `if user.blocked_at is not None: raise 403` in `refresh()`. Track as post-feature improvement. |
| All admins can be blocked by a single admin (no last-admin protection) | Low | Product | Accepted for internal tool with small team |

### Follow-Up Items (Post-Merge Tracking)

1. ~~Resolve MEDIUM-01~~ ✅ Done
2. ~~Resolve MEDIUM-02~~ ✅ Done
3. ~~Resolve MEDIUM-03~~ ✅ Done
4. LOW: Add `blocked_at` check in `auth_service.refresh` — blocked admin with valid refresh token can still get new access token. Fix: `if user.blocked_at is not None: raise 403` in `refresh()`. Low priority for internal tool.
5. LOW: Add localStorage whitelist validation in `useTheme.ts` — validate stored theme against allowed values before applying. Defensive hardening only.

---

*Review completed*: 2026-05-24
*Reviewer*: Security Architect Agent
*Gate status*: **T008 APPROVED WITH CONDITIONS — Phase 4 may proceed**
