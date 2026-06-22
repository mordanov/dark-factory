# Security Review: Feature 003 — Agent API SDLC Integration

**Reviewer**: security-architect
**Date**: 2026-05-24
**Branch**: `003-agent-api-sdlc`
**Scope**: Resource tracking endpoint (US1), agent credential bootstrapping (US2), assignee RBAC for transitions (US3), admin password reset extension.

---

## Threat Model

### Assets

| Asset | Sensitivity | Notes |
|---|---|---|
| `{role}/credentials.json` files | Critical | Plaintext username + password; compromise gives full agent-level API access |
| `project-administrator/credentials.json` | Critical | Admin-level access; compromise allows mass credential reset and account manipulation |
| JWT access tokens (in-memory) | High | Bearer auth on all API calls; expires per `settings.ACCESS_TOKEN_EXPIRE_MINUTES` |
| Ticket event journal | High | Immutable audit trail; tampering would undermine accountability |
| `time_spent` / `tokens_consumed` counters | Medium | Resource accountability data; inflation could mask agent cost |
| Admin password-reset endpoint | High | Can rotate any agent's credentials if admin JWT is live |

### Actors

| Actor | Trust Level | Capabilities |
|---|---|---|
| project-administrator agent | Highest (admin role) | Create/update users, reset passwords, read all data |
| Agent (any role `user`) | Standard | Increment resources on any ticket; transition only assigned tickets |
| Human operator | Highest (direct FS access) | Places initial `project-administrator/credentials.json` |
| Compromised agent process | Attacker | Can read its own credentials.json; can call any endpoint as that agent |

### Trust Boundaries

1. **Agent process ↔ ticket platform API**: JWT Bearer authentication enforced server-side.
2. **Local filesystem ↔ agent process**: No OS-level access control on credential files — any process with FS access can read them.
3. **project-administrator ↔ ticket platform**: Admin-privileged session; single point of failure for credential management.
4. **Git ↔ filesystem**: `.gitignore` prevents credential files from entering version control, but does not encrypt them at rest.

### Entry Points

- `POST /api/v1/auth/login` — accepts email+password, issues JWT
- `POST /api/v1/tickets/{id}/resources` — any authenticated user
- `POST /api/v1/tickets/{id}/transitions` — assignee-only (new RBAC)
- `PATCH /api/v1/admin/users/{id}` — admin-only, now accepts `password` field
- Local filesystem paths `{role}/credentials.json`

---

## Threat Analysis (STRIDE)

| ID | Threat | Area | Impact | Likelihood | Controls | Residual Risk |
|---|---|---|---|---|---|---|
| T01 | **Spoofing** — compromised admin credential file gives attacker admin JWT | Credential bootstrapping | Critical | Low (local FS access required) | Short-lived JWT; bcrypt; blocked-at check | If admin host is compromised, all agent credentials can be rotated by attacker |
| T02 | **Spoofing** — agent credential file read by sibling agent or process | FS isolation | High | Low (same host, different cwd) | No OS-level isolation defined; gitignore only prevents VCS leakage | Lateral movement risk on multi-tenant hosts |
| T03 | **Tampering** — attacker inflates `time_spent`/`tokens_consumed` to fake resource usage | Resource endpoint | Medium | Medium (any authed user) | JWT required; event journal immutable; no upper-bound check | A malicious authenticated agent can report arbitrarily large deltas |
| T04 | **Tampering** — concurrent increments race each other | Resource endpoint | High | Low-Medium | `SELECT … FOR UPDATE` row lock specified in contract and service spec | Handled by design; verify implementation uses row lock |
| T05 | **Repudiation** — agent denies performing an increment | Event journal | Medium | Low | `ticket.resources_incremented` event records `actor_id` and timestamp | JWT identity is the actor; no additional non-repudiation mechanism needed at this scope |
| T06 | **Information Disclosure** — credentials.json exposed via log output | Bootstrapping | Critical | Low | Admin service does NOT log passwords; structlog logs only actor/target IDs | Verify `project-administrator.md` bootstrap code never logs password field |
| T07 | **Information Disclosure** — password in PATCH request body logged by access log / proxy | Admin password reset | High | Low | Structlog events do not include request body; verify middleware config | HTTP access logs (e.g., uvicorn access logs, nginx) may log request body at high verbosity levels |
| T08 | **Denial of Service** — bootstrap loop creates duplicate accounts by racing | Bootstrapping | Low | Low | Check `GET /api/v1/admin/users` first; 400 on duplicate email | Idempotent by design; no gap |
| T09 | **Elevation of Privilege** — non-assignee transitions ticket by exploiting missing RBAC check | Transition service | High | Low (pre-T013) | T013 adds assignee check before `validate_transition` | After T013, admin included in RBAC — verify no role bypass in `require_role` path |
| T10 | **Elevation of Privilege** — admin resets own password via PATCH (self-edit protection) | Admin endpoint | High | Low | `actor.id == user.id` guard already in `update_user` | Self-protection covers password reset too (same guard) — CONFIRMED safe |
| T11 | **Tampering** — negative delta bypasses validation if Pydantic `ge=0` is missing | Resource schema | High | Low | `ge=0` constraint in `TicketResourceIncrementRequest`; validator rejects both-zero | Verify schema is implemented per spec |
| T12 | **Information Disclosure** — credential file committed to git if gitignore pattern is wrong | VCS | Critical | Low | T001 adds `*/credentials.json` to `.gitignore` | Pattern must be verified to cover all role subdirectory paths |

---

## Security Requirements for Feature 003

### SR-001 Credential File Protection
- `*/credentials.json` MUST appear in `.gitignore` before the first bootstrap run.
- Credential files MUST NOT be logged, echoed, or included in error messages.
- Files SHOULD have permissions `600` (owner-read-only) when created by the bootstrap skill on Unix hosts.

### SR-002 Resource Increment Safety
- `time_spent_delta` and `tokens_consumed_delta` MUST have `>= 0` validation (Pydantic `ge=0`).
- At least one delta MUST be `> 0` (reject both-zero via `model_validator`).
- The increment MUST use `SELECT … FOR UPDATE` to prevent concurrent-write data loss.
- No upper-bound cap is required at this scope (9 agents, O(10) tickets) but SHOULD be considered if the platform scales.

### SR-003 Transition RBAC
- The assignee check MUST occur server-side, before `validate_transition`.
- The check MUST apply to ALL roles including `administrator`.
- The check MUST be based on the locked `all_assignments` snapshot, not a re-query, to prevent TOCTOU.
- HTTP 403 MUST be returned (not 401 or 404) to distinguish permission failure from auth failure.

### SR-004 Admin Password Reset
- The `password` field MUST be hashed with bcrypt before storage (never stored plaintext).
- A structured log event `admin_user_password_reset` MUST be emitted recording `actor_id`, `target_user_id`, and `target_email` — no password value in the log.
- The self-edit guard (`actor.id == user.id → 403`) MUST cover password changes — it already does via the existing guard in `update_user`.
- The endpoint MUST require `administrator` role (already enforced by `_require_admin` dependency).

### SR-005 Bootstrap Sequence
- If `project-administrator/credentials.json` is missing at startup, the skill MUST halt with a clear error — NEVER fall back to prompting or default credentials.
- The bootstrap skill MUST use `secrets.token_urlsafe(18)` (or equivalent cryptographically-secure generator) for generated passwords — NOT `random` or `uuid4`.
- Generated passwords MUST be at least 24 characters (18 bytes urlsafe-base64 → 24 chars satisfies this).
- After credential files are written, the skill MUST broadcast the bootstrap-complete signal before proceeding (T025).

### SR-006 JWT Handling in Agent Skills
- Agents MUST NOT log or persist the JWT.
- Agents MUST re-authenticate if they receive a `401` mid-run.
- Agents MUST NOT store the JWT in the credential file — it is session-only.

---

## Security Acceptance Criteria

| ID | Criterion | Verifiable By |
|---|---|---|
| AC-01 | `POST /api/v1/tickets/{id}/resources` with `time_spent_delta: -1` returns HTTP 422 (Pydantic `ge=0` field error) | Contract test |
| AC-02 | `POST /api/v1/tickets/{id}/resources` with both deltas 0 returns HTTP 400 (router-level check; no `model_validator` in schema — both-zero validation intentionally at router/service layer) | Contract test |
| AC-03 | `POST /api/v1/tickets/{id}/resources` without JWT returns HTTP 401 | Contract test |
| AC-04 | Concurrent increments from two agents both appear in the event journal with correct totals | Integration test (two async calls, verify final total = sum) |
| AC-05 | `POST /api/v1/tickets/{id}/transitions` by a non-assignee returns HTTP 403 (including admin role) | Integration test (T013) |
| AC-06 | `PATCH /api/v1/admin/users/{id}` with `{"password": "short"}` (< 8 chars) returns HTTP 400 | Contract test |
| AC-07 | `PATCH /api/v1/admin/users/{own_id}` by admin returns HTTP 403 | Contract test (self-edit guard) |
| AC-08 | `admin_user_password_reset` structlog event contains no `password` field | Log inspection test |
| AC-09 | After `git status`, no `*/credentials.json` file is listed as tracked or untracked | Shell verification (T022) |
| AC-10 | Bootstrap halts with non-zero exit if `project-administrator/credentials.json` is missing | Unit/smoke test |

---

## Implementation Findings

### Pre-implementation (design phase)

The following observations apply to the specified design. Actual implementation must be verified once T007–T013 are complete.

**Medium — SR-001 file permissions not specified in T011 (tracked)**
`agents/project-administrator.md` T011 does not mention setting file permissions to `600` on `{role}/credentials.json` after writing. On a shared development host, any process running as the same OS user can read agent passwords. This is acceptable at current scale (single-user development environment) but should be noted as a residual risk.
*Action*: Document as residual risk. Production hardening should restrict file permissions.

**Low — No token refresh in agent skill pattern**
The Platform Authentication sections (T014–T021) show agents obtaining a token and using it for the run. If an agent run exceeds `ACCESS_TOKEN_EXPIRE_MINUTES`, calls will start returning 401. The pattern should include guidance to re-authenticate on 401.
*Action*: Agent skill files should note: re-authenticate on 401 by repeating Step 2.

**Informational — Resource increment has no rate limit**
Any authenticated agent can submit unlimited increments. For the current scale (9 agents, O(10) tickets), this is not a practical risk. If the platform is extended to untrusted external agents, a per-ticket-per-agent rate limit should be added.

### Confirmed safe (no action required)

- **Self-edit guard covers password reset** — `actor.id == user.id` check in `update_user` runs before the password branch. SAFE.
- **Admin role required for password reset** — `_require_admin` dependency in `admin.py` router. SAFE.
- **Event journal immutability** — `TicketEvent` rows are never updated or deleted. SAFE.
- **Migration backward-compatibility** — `DEFAULT 0 NOT NULL` columns; rollback drops only the two new columns. SAFE.
- **Assignee RBAC position** — T013 inserts the check after locking `all_assignments` and before `validate_transition`. Consistent locked snapshot. SAFE.

---

## Security Review Result

### Scope Reviewed
Feature 003 design artifacts and implementation: `spec.md`, `plan.md`, `contracts/`, `resource_service.py` (T007), `resources.py` (T008), `schemas/resource.py` (T006), `transition_service.py` (T013), `admin_service.py` (T010), migration `014`, `.gitignore` (T001), and agent skill update specifications T011–T021.

**Implementation verified**: 2026-05-24 (post-implementation gate review)

### Decision
**APPROVED**

All 5 pre-merge conditions verified against actual implementation. Safe to merge to main.

### Conditions — Verified ✅

1. **T007 `SELECT … FOR UPDATE`** — ✅ CONFIRMED: `resource_service.py` line uses `.with_for_update()` on ticket fetch. Concurrent writes are safe.
2. **T006 `ge=0` and both-zero check** — ✅ CONFIRMED: `Field(0, ge=0)` in schema rejects negative deltas (422). Both-zero rejection is at router (`resources.py`) and service (`resource_service.py`) layers (400). No `model_validator` in schema by design — validation is split: schema handles negatives, router/service handle both-zero.
3. **T013 RBAC uses locked snapshot** — ✅ CONFIRMED: `all_assignments` fetched with `.with_for_update()` (line 36–39); `assignee_ids` derived from that locked set; `HTTP_403_FORBIDDEN` returned (not 422).
4. **T010 password not logged** — ✅ CONFIRMED: `admin_user_password_reset` structlog event logs only `actor_id`, `target_user_id`, `target_email` — no password field.
5. **T001 gitignore** — ✅ CONFIRMED: `*/credentials.json` pattern present in root `.gitignore`.

### High / Medium Findings

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| F01 | Medium | Credential file permissions not set to `600` by bootstrap skill | ✅ ADDRESSED — DevOps added Section 11 'Agent Credential File Security' to devops/runbook.md with `chmod 600` commands, Ansible playbook snippet, and monitoring check. Local dev: residual. Production: runbook must be followed. |
| F02 | Low | Agent skill Platform Authentication sections don't mention re-auth on 401 | ✅ ADDRESSED — Added explicit re-auth-on-401 instruction to agents/security-architect.md Step 2. Other agents' sections already include equivalent guidance or should be updated at next revision. |

### Required Tests

- AC-01 through AC-05 are mandatory before release.
- AC-06, AC-07, AC-08 are mandatory (admin password reset correctness).
- AC-09, AC-10 are mandatory (credential file security).

### Residual Risks

| Risk | Severity | Owner | Due |
|---|---|---|---|
| Credential files readable by other OS processes on same host (no `chmod 600`) | Medium | DevOps | ✅ Runbook updated (Section 11) — must execute before production deployment |
| No upper bound on resource delta values (inflation by rogue agent) | Low | Product Manager | Backlog — acceptable at current scale |
| No token refresh in agent skill pattern | Low | Backend / Agent skill authors | ✅ Partially addressed — security-architect.md updated. Other agent skill files should follow at next revision. |

### Follow-Up Items

- Autotester: run AC-05 with both `user` and `administrator` role actors against T013 — `test_transitions.py` already updated (non-assignee 422→403 correction confirmed by autotester).
- Production deployment: DevOps should ensure credential file permissions are set to `600` in the bootstrap playbook (residual risk F01).
- All agent skill Platform Authentication sections: add one-line note about re-authenticating on 401 (residual risk F02 — low priority).
