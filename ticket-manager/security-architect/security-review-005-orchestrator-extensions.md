# Security Review: Workflow Orchestrator Integration Extensions

**Feature**: 005-orchestrator-extensions
**Branch**: `005-orchestrator-extensions`
**Date**: 2026-06-21
**Reviewer**: Security Architect Agent
**Severity legend**: 🔴 Critical · 🟠 High · 🟡 Medium · 🟢 Low · 🔵 Info

---

## Executive Summary

The orchestrator integration extensions introduce a service-to-service authentication channel, an append-only audit table, FSM state fields on tickets, and several new API endpoints. The overall security posture of the design is **adequate with targeted gaps**. No critical-severity issues were found in the design documents. Four high-severity gaps and five medium-severity gaps require mitigation before production; the remainder are informational or low risk.

**Verdict**: ✅ **Approved to proceed** — address the HIGH findings before merging to `main`.

---

## 1. Threat Model

### 1.1 Trust Boundaries

```
[Human Users (browser)]
        │  Bearer JWT (HS256)
        ▼
[Ticket Manager API — FastAPI]
        │  Bearer JWT (service account email match)
        ▼
[Workflow Orchestrator (internal service)]
        │
        ▼
[PostgreSQL — tickets, orchestrator_audit_events]
```

Three distinct principals write to TM:
- **Human users** (admin or user role) — existing channel
- **Dark Factory service account** — identified by `TICKET_MANAGER_SERVICE_EMAIL` email match, same JWT mechanism
- **Admin overriding a gate** — existing admin role, elevated path

### 1.2 Attack Surface Added by This Feature

| Component | Change | Risk increase |
|---|---|---|
| `/orchestrator/pending` | New read endpoint, any authenticated user | Info disclosure if mis-scoped |
| `PATCH /fsm` | Write path for service account / admin | Privilege escalation if service account auth is weak |
| `POST /audit` | Unbounded writes from service account | Audit log flooding / storage DoS |
| `POST /override` | Admin-only gate bypass | Abuse of override without accountability |
| `POST /tags/delta` | Tag mutation, no explicit auth beyond `get_current_user` | Any authenticated user can manipulate tags |
| `POST /batch-fsm-status` | Bulk read, no explicit auth beyond `get_current_user` | IDOR-style info disclosure across projects |
| `orchestrator_errors` JSONB field | Arbitrary string array stored from orchestrator | Stored injection surface |
| `actor` in audit events | Free-text string, not validated against a known principal list | Audit spoofing |

---

## 2. Findings

### 2.1 🟠 HIGH — `POST /tags/delta` Has No Authorization Beyond Authentication

**Location**: `spec.md` FR-019; `openapi-orchestrator.yaml` `/projects/{project_id}/tickets/{ticket_id}/tags/delta`

**Finding**: The tag delta endpoint is documented as requiring only standard Bearer auth (`get_current_user`). No additional role or ownership check is specified. Any authenticated user — including a `user`-role account with no project membership — can call this endpoint and add/remove tags on any ticket in any project they can address by UUID.

**Risk**: An authenticated but unprivileged user (or a compromised user account) can pollute workflow-signal tags (e.g., `needs-estimation`, `blocked`, `ready-for-review`) across all tickets, disrupting orchestrator behavior silently since tag changes do not generate FSM events.

**Mitigation required**: Apply the same project-membership or role guard used on the existing `POST /{ticket_id}/tags` endpoint. At minimum, check that the caller either holds the `admin` role OR is the service account. Alternatively, mirror the behaviour of `ticket_service.add_tag` which may already perform an ownership check — verify in implementation.

---

### 2.2 🟠 HIGH — `POST /tickets/batch-fsm-status` Leaks Ticket Titles Across Projects

**Location**: `openapi-orchestrator.yaml` `/tickets/batch-fsm-status`; `spec.md` FR-022/FR-023

**Finding**: The batch FSM status endpoint accepts an array of up to 100 UUIDs and returns titles, FSM status, and `blocked_reason` for all matching tickets — silently skipping unknowns. There is no project scoping or membership check. A user can enumerate ticket data across all projects by guessing or harvesting UUIDs, without ever being a member of the target project.

**Risk**: Cross-project information disclosure. Ticket titles and blocked reasons may contain sensitive project details, customer names, or internal code names.

**Mitigation required**:
1. Restrict access to the service account only (consistent with its primary consumer), **or**
2. Filter the result set to tickets belonging to projects the caller has access to (join through project membership).

The simplest safe choice for this internal API is option 1.

---

### 2.3 🟠 HIGH — Audit Log Write Has No Rate Limit or Storage Cap

**Location**: `spec.md` FR-013; `openapi-orchestrator.yaml` `POST /tickets/{ticket_id}/audit`

**Finding**: The audit event creation endpoint is unrestricted in write volume. The spec documents `orchestrator_errors` capped at 50 entries but imposes no analogous limit on audit events. A compromised service account or a misbehaving orchestrator can write millions of audit rows per ticket, consuming unbounded disk and degrading the `GET /audit` retrieval beyond the 2-second SLA (SC-004).

**Risk**: Storage DoS; audit log becomes unusable for legitimate compliance inspection.

**Mitigation required**: Implement one or more of:
- Application-layer rate limit on `POST /audit` per `ticket_id` (e.g., 1 000 events/ticket, reject with 429)
- Database-level partition or archival strategy for `orchestrator_audit_events`
- Document explicit on-call runbook for trimming in the absence of an automated cap

At minimum, add a per-ticket event count check in `audit_service.py` and reject with `400` above a configured threshold (suggest 10 000 as initial ceiling).

---

### 2.4 🟠 HIGH — Service Account Identity Relies Solely on a Mutable Email Field

**Location**: `research.md` §1; `spec.md` FR-028; `src/core/security.py`

**Finding**: The `require_service_account_or_admin` dependency authenticates the service account by comparing the authenticated user's `email` field against `settings.ticket_manager_service_email`. Email is stored in the `users` table and can be changed by an admin via the user-management API. If the service account email is updated (accidentally or by a compromised admin), all service-account-protected endpoints silently fall back to `admin`-only access (FR-028 fail-closed), but the orchestrator's JWT tokens stop working without any alert.

More critically: if an admin creates a new user with the same email as `TICKET_MANAGER_SERVICE_EMAIL`, that user gains full service-account-level access to all FSM write endpoints.

**Risk**: Privilege escalation via email collision; silent service disruption.

**Mitigation required**:
1. In `require_service_account_or_admin`, additionally verify the matched user has a specific known UUID (stored in a second env var `TICKET_MANAGER_SERVICE_ACCOUNT_ID`) rather than relying on email alone.  
   **Or** (simpler): enforce uniqueness of `TICKET_MANAGER_SERVICE_EMAIL` against the users table at startup and reject boot if a collision exists.
2. Add a health-check or startup validation that verifies the service account user record exists with the expected email.

---

### 2.5 🟡 MEDIUM — `actor` Field in Audit Events Is Not Validated Against Known Principals

**Location**: `openapi-orchestrator.yaml` `AuditEventCreate`; `data-model.md` §2

**Finding**: The `actor` field in `AuditEventCreate` is a free-text string (max 255 chars) supplied by the caller. Any authenticated service-account or admin can write an audit event claiming `actor: "human-cfo"` or `actor: "security-scan"`, fabricating provenance in the immutable audit log.

**Risk**: Audit log spoofing. Investigators relying on `actor` for accountability will see false attributions.

**Mitigation required**: In `audit_service.create_event`, ignore the `actor` value from the request body and derive it server-side from the authenticated principal: `actor = current_user.email`. This converts `actor` from a caller-supplied claim to a server-attested identity. Update the schema to mark `actor` as a read-only / computed field.

---

### 2.6 🟡 MEDIUM — `orchestrator_errors` JSONB Accepts Unbounded Strings Per Entry

**Location**: `data-model.md` §4; `openapi-orchestrator.yaml` `FsmPatchRequest`

**Finding**: The spec caps `orchestrator_errors` at 50 array entries but sets no per-entry string length limit. A single entry could be a multi-megabyte string, bypassing the row-count cap.

**Risk**: PostgreSQL row-size limits (typically 1 GB TOAST) are far above what is operationally useful; a multi-MB `orchestrator_errors` column bloats the `tickets` table, hurts index performance, and inflates the response payload for every endpoint that returns the full ticket.

**Mitigation required**: Add a Pydantic validator on `orchestrator_errors` array items: max 2 000 characters per string. Enforce in `fsm_service.py` before writing to the DB.

---

### 2.7 🟡 MEDIUM — Cursor Decoding Could Panic on Malformed Base64/JSON

**Location**: `research.md` §2; `src/services/fsm_service.py` (to be implemented)

**Finding**: The `after_cursor` parameter for `/orchestrator/pending` is decoded from base64 → JSON → `(updated_at, id)`. If the cursor value is malformed (corrupted, truncated, or crafted), the decode path will raise an exception. If that exception is not explicitly caught, FastAPI will return a 500 (leaking a stack trace in non-production) or an unhelpful error.

**Risk**: Information disclosure via stack trace; degraded UX for debug scenarios.

**Mitigation required**: Wrap cursor decode in a try/except and raise `HTTPException(400, "Invalid cursor")`. Never pass raw decode errors to the response. The implementation task should include this guard.

---

### 2.8 🟡 MEDIUM — `GET /orchestrator/pending` Has No Explicit Access Control

**Location**: `openapi-orchestrator.yaml` `/orchestrator/pending`; `spec.md` FR-008–FR-011

**Finding**: The spec and contract require Bearer auth (standard `get_current_user`) but do not specify whether the pending endpoint is restricted to the service account or accessible to all authenticated users. If the latter, any `user`-role account can retrieve the full list of pending tickets (including titles, descriptions, FSM state, blocked reasons) for all projects.

**Risk**: Cross-project information disclosure; the pending response is richer than the batch endpoint (includes description, all FSM fields).

**Mitigation required**: Restrict `GET /orchestrator/pending` to the service account or admin role. Document this restriction in the spec and contract (currently missing from both). Add `require_service_account_or_admin` as the dependency.

---

### 2.9 🟢 LOW — `GET /tickets/{ticket_id}/audit` Has No Access Control Specification

**Location**: `openapi-orchestrator.yaml` `GET /tickets/{ticket_id}/audit`

**Finding**: The audit log read endpoint is under the standard `bearerAuth` scheme with no additional role requirement documented. Audit logs may contain sensitive orchestrator decision rationale in the `details` field.

**Risk**: Information disclosure of orchestrator internals to low-privilege users. Lower risk than the cross-project issues above because it's scoped to a single ticket the caller already knows about.

**Mitigation**: Document the intended access policy (suggest: same as ticket read access — any member of the ticket's project). If no project-membership check currently exists on ticket read, this is acceptable for now but should be tracked.

---

### 2.10 🔵 INFO — `override` Flag Clearing Relies on Orchestrator Cooperation

**Location**: `spec.md` FR-018; `data-model.md` §1

**Finding**: The `override` flag is cleared by the orchestrator via FSM PATCH. If the orchestrator crashes between reading the flag and clearing it, the flag remains set. There is no server-side TTL or expiry.

**Risk**: A stuck `override: true` flag could cause repeated skipping of a failed gate across polling cycles. This is an operational safety concern, not a security vulnerability per se.

**Note**: Document this as a known operational hazard in the runbook. Consider a max-age check (e.g., clear override if `last_orchestrator_run` is older than 24 hours) in a future iteration.

---

## 3. Authorization Matrix (as-reviewed)

| Endpoint | Intended Auth | Specified in Contract | Gap |
|---|---|---|---|
| `PATCH /fsm` | Service account OR admin | ✅ Yes | None |
| `POST /override` | Admin only | ✅ Yes | None |
| `GET /orchestrator/pending` | Service account OR admin | ❌ Missing | **See §2.8** |
| `POST /audit` | Service account | ❌ Missing (only `bearerAuth`) | Not explicitly restricted |
| `GET /audit` | Any authenticated | ❌ Not specified | See §2.9 |
| `POST /tags/delta` | Any authenticated | ❌ Missing ownership check | **See §2.1** |
| `POST /batch-fsm-status` | Any authenticated | ❌ Missing project scope | **See §2.2** |
| `GET /full` | Any authenticated | Inherits from ticket read | Acceptable |
| `GET /tickets?include_fsm` | Any authenticated | Inherits from list | Acceptable if list is project-scoped |

---

## 4. Secure Implementation Checklist

For the backend implementor:

- [ ] `require_service_account_or_admin`: verify by `(email == env_var AND user.id == known_id)`, not email alone
- [ ] `TICKET_MANAGER_SERVICE_EMAIL` added to `Settings` with startup validation (non-empty, existing user record)
- [ ] `GET /orchestrator/pending`: add `require_service_account_or_admin` dependency
- [ ] `POST /tags/delta`: add `require_service_account_or_admin` dependency OR project-membership check
- [ ] `POST /batch-fsm-status`: restrict to service account or filter by project membership
- [ ] `POST /audit`: derive `actor` from `current_user.email` server-side; ignore caller's `actor` field
- [ ] `POST /audit`: enforce per-ticket event count cap in `audit_service.py` (suggest: 10 000 max)
- [ ] `orchestrator_errors` Pydantic validator: max 50 entries × max 2 000 chars per entry
- [ ] Cursor decode in `/orchestrator/pending`: wrap in try/except → raise `HTTPException(400, "Invalid cursor")`
- [ ] No FSM or audit field values written to structlog at DEBUG/INFO level (only IDs and status codes)

---

## 5. Positive Security Observations

- ✅ Service account fail-closed behaviour (FR-028) is correctly specified: missing env var → only admin passes, no 500
- ✅ Audit log is append-only by design — no UPDATE/DELETE paths exposed
- ✅ `fsm_status` uses a PostgreSQL enum (database-level validation) rather than a free-text column
- ✅ Cursor is base64-opaque, reducing temptation for manual construction
- ✅ Migration strategy is zero-downtime (nullable columns / server defaults) — no outage window creates race conditions
- ✅ FSM PATCH touches only FSM fields — no path to corrupt native ticket fields (title, description, status)
- ✅ Override endpoint is admin-only — not accessible to the service account itself
- ✅ No PII stored in new columns or log lines per design intent
- ✅ HS256 key entropy enforced at config load time (32-char minimum validator)

---

## 6. References

- `specs/005-orchestrator-extensions/spec.md` — FR-004 through FR-028
- `specs/005-orchestrator-extensions/research.md` — §1 Service Account Authorization, §2 Pagination
- `specs/005-orchestrator-extensions/data-model.md` — §2 OrchestratorAuditEvent, §4 Validation Rules
- `specs/005-orchestrator-extensions/contracts/openapi-orchestrator.yaml`
- `backend/src/core/security.py` — existing `require_role`, `get_current_user`
- `backend/src/core/config.py` — existing Settings class
