# Security Review: Workflow Transitions (T061)

**Reviewer**: Security Architect
**Date**: 2026-05-23
**Scope**: T054 (WorkflowService.transition), T056 (POST /tickets/{id}/transitions endpoint)
**Phase**: Phase 5 Gate (US3)

---

## Review Context

The status transition system is the highest-risk workflow component because:
1. It gates state changes on a multi-user condition (all assignees must have submitted progress updates)
2. It involves concurrent operations — multiple users can submit progress updates and one can trigger a transition simultaneously
3. It is the primary workflow enforcement point — a bypass allows skipping the accountability gate

---

## Threat Model: Status Transitions

### Assets

- Ticket status integrity (must only advance via valid transitions)
- Progress update gate (all assignees must have submitted before transition)
- RBAC enforcement (only assignees may initiate transitions)
- Audit trail (every transition and blocked transition must be recorded)

### Actors

| Actor | Attack Goal |
|---|---|
| Assigned user (legitimate) | Initiate valid transitions |
| Non-assigned authenticated user | Bypass RBAC to force a transition |
| Two concurrent assigned users | Race condition to bypass progress gate |
| Assigned user + concurrent admin | Admin removes assignee mid-transition to clear the gate |

### Trust Boundaries

- Browser → API: JWT-authenticated request
- API handler → WorkflowService: within process (trusted after auth)
- WorkflowService → DB: single transaction must cover all steps

---

## Race Condition Analysis

### Race Condition 1: Concurrent Progress Submit + Transition

**Scenario**:
```
Ticket: OPEN, 2 assignees (A, B)
Time 1: User A submits progress update
Time 2: User B submits progress update
Time 3: User A and User B BOTH POST /transitions concurrently
```

**Risk**: Both transitions execute, ticket transitions twice (e.g., OPEN → IN_PROGRESS × 2).
**Mitigation**: The entire transition in T054 is specified as a "single DB transaction".
PostgreSQL's `SELECT ... FOR UPDATE` on the tickets row will serialize concurrent
transitions. The second transaction will read the updated status and `validate_transition()`
will correctly raise 409 (OPEN → OPEN is not a valid transition).

**Verdict**: Low risk if transaction uses `SELECT ... FOR UPDATE` on the ticket row.
The implementation spec must explicitly include this row lock.

---

### Race Condition 2: Concurrent Assignee Removal + Transition (PRIMARY CONCERN)

**Scenario** (gate bypass attempt):
```
Ticket: IN_PROGRESS, 2 assignees (A, B)
B has NOT submitted a progress update.
Time 1: User A checks — gate blocked (B missing update)
Time 2: Admin/A removes B from ticket via DELETE /assignments/{B}
Time 3: User A immediately POST /transitions (now only A, who has submitted)
```

**Risk**: The transition succeeds because the progress gate check only sees current
assignees, and B has been removed. The accountability requirement (B must document
their work) is bypassed.

**Attack Path Requires**:
1. Actor must have permission to both remove an assignee AND transition the ticket
2. The removal + transition must happen in sequence (not truly concurrent)

**Assessment**: This is a design issue, not a concurrency issue. An assignee (or admin)
can deliberately remove a blocking assignee to clear the gate. This is an authorization
logic weakness, not a race condition in the traditional sense.

**Architecture Decision (2026-05-23)**: Software Architect ruled **Option B** (current
assignees only). FR-008a says "currently assigned users" — this is spec-compliant.
The accountability mechanism is the immutable `ticket_events` audit trail (every
`ticket.unassigned` and `ticket.status_changed` event is permanently recorded), not
the gate itself.

**Residual Risk (ACCEPTED)**: A user with permission to remove assignees (creator,
admin, or existing assignee) can remove a blocking assignee and then initiate the
transition. This action is fully visible in the audit trail and constitutes a deliberate
accountability bypass that is traceable. Documented as accepted per architecture ruling.

**Implementation note (T054)**: Check progress gate against current `ticket_assignments`
rows only. Use `SELECT ... FOR UPDATE` on both ticket and ticket_assignments to prevent
concurrent race conditions.

---

### Race Condition 3: True TOCTOU on Progress Gate

**Scenario**:
```
Ticket: IN_PROGRESS, 2 assignees (A, B). B has submitted progress.
Time 1: User A checks gate — all green (A and B have updates)
Time 2: User B deletes their progress update (if deletion were permitted — see below)
Time 3: User A's transaction commits the transition
```

**Risk**: B's progress update present at check time but absent at commit time.
**Assessment**: The data model does NOT permit deletion of progress_updates. They are
upsertable but not deletable. This race condition cannot occur as designed.

**Verification Required**: T047 must verify that `progress_service.py` has NO delete
path for progress_updates. The API spec has no DELETE /progress endpoint. Code review
T030 must confirm no delete query exists in progress_service.py.

---

### Race Condition 4: Concurrent Transition + Assignee Add

**Scenario**:
```
Ticket: IN_PROGRESS, 1 assignee (A). A has submitted progress.
Time 1: User A begins transition (gate passes — only A required)
Time 2: Admin adds User B as assignee (while transition in flight)
Time 3: Transition commits with only A having progress
```

**Risk**: Ticket transitions with a newly added assignee B having no progress update.
**Assessment**: Low risk given the sequential nature of the gate check. If the transition
transaction reads `ticket_assignments` with `SELECT ... FOR UPDATE` (row-level lock), the
concurrent assignment insert will be serialized. If it does NOT lock, this race is possible.

**Required Mitigation**: The progress gate check in WorkflowService.transition MUST use
`SELECT ... FOR UPDATE` on both the ticket row AND the ticket_assignments rows being read.

---

## RBAC Enforcement Review

### Caller Authorization (T056)

The endpoint `POST /api/v1/tickets/{id}/transitions` must:
1. Apply `get_current_user` dependency (JWT auth)
2. Verify caller is an active assignee of the ticket (not just any authenticated user)
3. Return 403 if caller is not currently assigned

**Required Check**:
```python
# In the endpoint handler (T056), BEFORE calling WorkflowService:
assignment = await assignment_service.get_assignment(session, ticket_id, current_user.id)
if not assignment:
    raise HTTPException(status_code=403, detail="Only assigned users may transition this ticket")
```

**Administrator Override**: The spec does not explicitly address whether administrators
can force transitions. The spec (FR-008) states "Only users assigned to a ticket MUST
be permitted to initiate a status transition." This means even administrators CANNOT
transition tickets they are not assigned to. This must be explicitly implemented — the
`require_role` dependency alone is not sufficient.

**Finding F-TR-02**: The RBAC check must be assignment-based, not role-based. An
administrator who is not assigned to a ticket must receive 403.

---

## Audit Trail Completeness

The spec defines two event types for transitions:
- `ticket.status_changed` — emitted on successful transition
- `ticket.transition_blocked` — emitted when gate check fails

**Finding F-TR-03**: The `ticket.transition_blocked` event must include the caller's
identity AND the list of missing users. This is critical for detecting abuse patterns
(repeated blocked attempts by the same user, or after suspicious assignee removal
patterns).

The `metadata` JSONB field in `ticket_events` should capture:
```json
{
  "requested_status": "IN_REVIEW",
  "missing_updates": [{"user_id": "...", "email": "..."}],
  "current_assignee_count": 2
}
```

---

## Required Implementation Guidance for T054

The `WorkflowService.transition()` method must follow this exact sequence to prevent
the identified vulnerabilities:

```python
async def transition(session, ticket_id, to_status, actor):
    # 1. Load and LOCK the ticket row (prevents concurrent transitions)
    ticket = await session.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id, Ticket.deleted_at.is_(None))
        .with_for_update()  # REQUIRED — row-level lock
    ).scalar_one_or_none()

    if not ticket:
        raise HTTPException(404)

    # 2. Validate the transition path
    validate_transition(ticket.status, to_status)  # raises 409 if invalid

    # 3. Load current assignments (within the locked transaction)
    assignments = await session.execute(
        select(TicketAssignment)
        .where(TicketAssignment.ticket_id == ticket_id)
        .with_for_update()  # REQUIRED — prevents concurrent add during gate check
    ).scalars().all()

    # 4. Load progress updates
    progress_records = await session.execute(
        select(ProgressUpdate)
        .where(ProgressUpdate.ticket_id == ticket_id)
    ).scalars().all()

    # 5. Gate check
    progress_user_ids = {p.user_id for p in progress_records}
    missing = [a for a in assignments if a.user_id not in progress_user_ids]

    if missing:
        # Emit blocked event (immutable record of the attempt)
        await event_service.emit_event(
            session, ticket_id, "ticket.transition_blocked", actor,
            prev_state={"status": ticket.status},
            new_state={"pending_status": to_status, "missing_users": [...]},
            metadata={"requested_status": to_status, "missing_updates": [...]}
        )
        raise HTTPException(422, TransitionBlockedError(...))

    # 6. Execute transition
    ticket.status = to_status
    await event_service.emit_event(
        session, ticket_id, "ticket.status_changed", actor,
        prev_state={"status": prev_status},
        new_state={"status": to_status}
    )

    await session.commit()
```

All steps must be inside a single database transaction. The `with_for_update()` on both
the ticket and ticket_assignments rows is the critical safety mechanism.

---

## Findings Summary

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| F-TR-01 | HIGH | Assignee removal can bypass progress gate (design gap) | Define business rule: Option 1 (historical assignees) or explicitly accept Option 2 |
| F-TR-02 | HIGH | RBAC must be assignment-based, not role-based | Admin without assignment must get 403; enforce in T056 handler |
| F-TR-03 | MEDIUM | Blocked transition events must include caller identity and missing user details | Ensure metadata JSONB captures this in T054 |
| F-TR-04 | HIGH | Missing SELECT FOR UPDATE on ticket and assignments rows | T054 must use with_for_update() on both ticket and ticket_assignments |

---

## Security Tests Required

| Test ID | Description |
|---|---|
| SEC-TR-001 | Non-assignee authenticated user gets 403 on POST /transitions |
| SEC-TR-002 | Administrator not assigned to ticket gets 403 on POST /transitions |
| SEC-TR-003 | Transition with missing progress updates returns 422 with correct missing user list |
| SEC-TR-004 | Valid transition succeeds; ticket.status_changed event recorded with actor |
| SEC-TR-005 | CLOSED ticket returns 409 on any transition attempt |
| SEC-TR-006 | OPEN → DONE skipping intermediate statuses returns 409 |
| SEC-TR-007 | Assignee removed, then transition attempted — verify business rule documented above is enforced |
| SEC-TR-008 | Concurrent transition requests from two assignees — only one succeeds |

---

## Decision

> **APPROVED WITH CONDITIONS** — T054/T056 may proceed to implementation with the
> following requirements enforced:

**Mandatory before T054/T056 merge:**
1. **F-TR-04 (HIGH)**: `SELECT ... FOR UPDATE` on ticket AND ticket_assignments rows in WorkflowService.transition
2. **F-TR-02 (HIGH)**: RBAC check in T056 must be assignment-based (not role-based); admin without assignment gets 403
3. **F-TR-01 (HIGH)**: Business rule for "assignee removed before transition" must be explicitly defined in spec or this review and implemented consistently

**Tracked residual risks:**
- F-TR-03: Audit completeness — medium risk, must be in final T081 review

I will verify these in coordination with code-reviewer during T082 final review.
