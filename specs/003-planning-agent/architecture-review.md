# Architecture Review: Planning Agent for Prompt Studio

**Feature**: `003-planning-agent`
**Reviewer**: Software Architect Agent
**Date**: 2026-06-23
**Status**: Accepted
**References**: spec.md, plan.md, data-model.md, contracts/api.md, checklists/security-review.md

---

## 1. Executive Summary

The Planning Agent design is **architecturally sound and approved for implementation**.
The plan extends `user-input-manager` with five new endpoints, one new DB table, four new
session statuses, and a background ticket-creation worker. All six research decisions
(R-001 through R-006) are correct. All sixteen constitution checks pass. The security review
raised two blockers (SR-001, SR-002) and five required/advisory items (SR-003 through SR-007)
— these must be addressed during implementation, not as a post-merge fix.

This review records architectural guidance keyed to tasks T001–T038. Implementation agents
must treat items marked **[BLOCKER]** as merge gates.

---

## 2. Architecture Decisions Confirmed

### AD-1: JSONB over normalized plan schema (R-006)

**Decision confirmed.** Storing `plan_content` as JSONB with `PlanValidator` enforcing schema
is the right call for this scope (≤101 nodes, human-interactive throughput). A fully normalized
schema (separate Epic/Story/Task tables with FK joins) would complicate the idempotent-retry
pattern and offer no query performance benefit for a single-session read path.

**Constraint for T001/T002**: The `prompt_plans` table must define `plan_content` as `JSONB`
(not `TEXT` or `JSON`). PostgreSQL JSONB allows path lookups for future analytics if needed.

### AD-2: FastAPI BackgroundTasks over Celery/asyncio.create_task (R-002)

**Decision confirmed with a required modification.** BackgroundTasks is the right choice for
this scale and infra footprint. However, SR-005 requires wrapping the background task body
in `asyncio.timeout(120)`. Without the timeout, a hung TM connection could permanently
occupy the event loop.

**Required modification for T018/T020**: Add `asyncio.timeout(120)` around the body of
`_create_tickets`. On `TimeoutError`, update plan status to `error` and log at `warn` level.

### AD-3: Idempotent retry via `ticket_id_map` (R-003)

**Decision confirmed.** The `ticket_id_map` (JSONB dict of `local_id → tm_ticket_id`) is
the correct unit for idempotency. Checking `local_id in ticket_id_map` before each TM call
gives O(1) skip with zero duplicates.

**Constraint for T020**: `PlanRepository.append_created_ticket` MUST be called immediately
after each successful TM response — before attempting the next node. If the write fails,
the next retry will re-attempt that node (TM creates a second ticket). To prevent this,
`append_created_ticket` should use an `UPDATE ... WHERE id = :plan_id` with `JSONB || new_pair`
so it is idempotent at the DB level (same local_id mapping to same tm_id is a no-op).

### AD-4: Conditional UPDATE for confirm gate (SR-002) **[BLOCKER]**

**Required change from plain read-then-write pattern.** `PlanRepository.update_status`
when called with target status `confirmed` MUST use:

```python
result = await session.execute(
    update(PromptPlan)
    .where(PromptPlan.id == plan_id, PromptPlan.status == "ready")
    .values(status="confirmed")
    .returning(PromptPlan)
)
row = result.first()
if row is None:
    raise ConflictError("Plan is not in ready state or was already confirmed")
```

A simple `GET → check → SET` pattern has a TOCTOU race. The conditional `WHERE status = 'ready'`
makes it atomic.

**Required for T006 (PlanRepository)** and **T018 (PlanningService.confirm)**.

### AD-5: PlanValidator as pure function (R-004)

**Decision confirmed.** The DFS cycle detector must process each Story independently (not
cross-story). The validator must accept `dict` (raw parsed JSONB) and return
`tuple[PlanContent | None, list[str]]`. It MUST NOT perform I/O.

**Constraint for T007**: The validator should early-exit on structural errors (missing
required fields, type constraint violations) before running the DFS — this avoids misleading
cycle-detection errors on malformed input.

### AD-6: ContextDistiller agent-config endpoints (R-005)

**Decision confirmed.** Two new endpoints (`POST`/`GET /memory/{project_id}/agent-config`)
follow the existing `/memory/*` auth pattern. `user-input-manager` calls these via httpx;
it never writes to MongoDB directly. This correctly enforces cross-service boundary.

**Constraint for T005 (context-distiller)**:
- The MongoDB collection name MUST be `agent_configs` (separate from any existing collection).
- Use `update_one({"_id": project_id}, {"$set": doc}, upsert=True)` — not `insert_one`.
- The `AgentConfigStored` response schema must include `project_id` and `stored_at` (ISO8601).

---

## 3. Session / Plan State Machine Verification

The state machine is correct and complete. Verified against spec FR-014 and FR-015:

```
Session:    approved ─(generate)─▶ planning ─(success)─▶ plan_ready ─(confirm)─▶ plan_confirmed ─(all done)─▶ tickets_created
                ▲                       │
                └───(failure)───────────┘
                    (session reset; plan set to error or deleted)

Plan:       draft ─(validate+persist)─▶ ready ─(confirm, atomic)─▶ confirmed ─(all tickets)─▶ tickets_created
                ▲                          │ (regenerate)
                └──────────────────────────┘ (new plan row, old replaced via session_id UNIQUE)
```

**Implementation notes for T011 (generate) and T018 (confirm)**:

- On generation failure: reset `session.status = "approved"` AND either delete the plan row
  or set `plan.status = "error"`. The spec says session stays at `approved` for retry. If the
  plan row is left in `error` state, the next `POST /sessions/{id}/plan` must upsert
  (replace) it via the UNIQUE constraint on `session_id`.
- On regeneration (user-triggered after plan exists): set old plan to `error` state
  (or delete), create new plan row. Because `session_id` is UNIQUE, an upsert approach
  (`INSERT ... ON CONFLICT (session_id) DO UPDATE`) is cleaner than delete+insert.
- `plan_confirmed` is a session status; `confirmed` is a plan status. They must be set
  together in a single DB transaction in `PlanningService.confirm`.

---

## 4. API Contract Validation

All five endpoints in `contracts/api.md` are architecturally consistent. Key points:

### 4.1 POST /sessions/{id}/plan → 202

The response shape `{session_id, plan_id, status: "planning"}` is correct. Note that
generation is **synchronous** in the current design (generate_plan is awaited inline before
returning 202). This means the client receives 202 only after the LLM call completes
(up to 60s). This is the spec's intent — the 202 signals "plan is ready to poll" or
"generation started."

**Clarification for T012**: `PlanningService.generate()` is called inline (not as a background
task). The endpoint awaits it and returns 202 when done. The spec's `status: "planning"` in
the response is a transient state that has already resolved to `plan_ready` by the time
the response is sent. This is correct — the client polls `GET /plan` to confirm.

Alternatively, if LLM latency is unacceptable at p99, consider returning 202 immediately
and letting the frontend poll — but this would require generation as a BackgroundTask too.
The current synchronous approach is simpler and acceptable given the 60s timeout overlay
on the frontend. Stick with synchronous generation.

### 4.2 PUT /sessions/{id}/plan — Validation errors shape

The error response must be:

```json
{ "detail": "Plan validation failed", "errors": ["..."] }
```

with HTTP 422. FastAPI's default `422` shape uses `{"detail": [...]}` (Pydantic validation errors).
The planning endpoint must use a custom `HTTPException(status_code=422)` with the above shape
rather than relying on FastAPI's automatic Pydantic 422.

**Required for T017**: Return `HTTPException(status_code=422, detail={"detail": "Plan validation failed", "errors": errors})`.

### 4.3 POST /sessions/{id}/plan/confirm — Idempotency on retry

If a user retries confirm while `_create_tickets` is already running (plan status = `confirmed`),
the endpoint should return `409` (plan not in `ready` state). The spec's edge case confirms this:
"if creation is still running the response returns the current progress without starting a second job."

**Correction**: The spec says retry endpoint is idempotent — on a second confirm when status
is already `confirmed`, return the current status (not 409). Implement: if `plan.status == "confirmed"`,
return 202 with current status without adding another background task.

**Required for T018**: Add a `confirmed` check — if already confirmed, return current status
without re-queuing background task.

### 4.4 GET /sessions/{id}/plan/status — total computation

`total = 1 + len(stories) + sum(len(story.tasks) for story in stories)`

This is computed from `plan_content` (JSONB), not from a separate counter. If `plan_content`
is null (plan still in `draft`), return `total = 0` and `created_count = 0`.

---

## 5. Data Model Validation

The `prompt_plans` schema in `data-model.md` is correct. Three refinements:

### 5.1 `updated_at` auto-update

SQLAlchemy's `onupdate=_now` on `updated_at` fires on Python-level updates but NOT on
raw SQL updates (e.g., `session.execute(update(...))`). For `append_created_ticket`
(which uses a raw UPDATE for JSONB append), you must include `updated_at = now()` explicitly
in the UPDATE statement.

### 5.2 `created_ticket_ids` vs `ticket_id_map` redundancy

Both columns exist for different purposes: `created_ticket_ids` (TEXT[]) is a quick array
for counting `created_count`; `ticket_id_map` (JSONB) is used for `depends_on` resolution.
This redundancy is acceptable — the array can be derived from `ticket_id_map` but having it
as a native PG array enables `len(created_ticket_ids)` without JSONB parsing in Python.

**Constraint**: They must be kept in sync. `append_created_ticket` must update both atomically
in a single SQL statement:

```sql
UPDATE prompt_plans
SET
  created_ticket_ids = COALESCE(created_ticket_ids, '{}') || ARRAY[:tm_id::text],
  ticket_id_map      = COALESCE(ticket_id_map, '{}'::jsonb) || jsonb_build_object(:local_id, :tm_id),
  updated_at         = now()
WHERE id = :plan_id
```

### 5.3 Alembic enum extension safety

R-001 correctly identifies `op.execute("ALTER TYPE session_status ADD VALUE ...")` as the safe
pattern. Critical detail: PostgreSQL does not allow `ALTER TYPE ... ADD VALUE` inside a transaction
block. Alembic by default wraps migrations in transactions. The migration **must** set:

```python
def upgrade():
    op.execute("COMMIT")  # end the outer transaction
    op.execute("ALTER TYPE session_status ADD VALUE IF NOT EXISTS 'planning'")
    # ... other ADD VALUE calls
    op.execute("BEGIN")   # re-open for subsequent DDL
```

Or use `transaction_per_migration = false` in `alembic.ini`. Without this, the migration
will fail on PostgreSQL 16 with "ALTER TYPE ... ADD VALUE cannot run inside a transaction block."

**Required for T001**.

---

## 6. Security Requirements Integration

All seven security requirements from the security review are incorporated into specific tasks:

| SR | Task | Action required |
|----|------|-----------------|
| **SR-001** [BLOCKER] | T029 (PlanningModal) | No `dangerouslySetInnerHTML`; use `<input>`/`<textarea>` for inline edit. All plan content rendered as plain text. |
| **SR-002** [BLOCKER] | T006 (PlanRepository), T018 (confirm) | `WHERE status = 'ready'` conditional UPDATE for confirm; raise `ConflictError` if zero rows updated. |
| SR-003 | T011, T018, T020 | `structlog` events at generate, confirm, tickets_created transitions. Log `user_id` + `session_id`. No `plan_content` or credentials in log. |
| SR-004 | T009 (PlanningLLMService) | LLM prompt for `generate_plan` MUST include only `refined_prompt`. No identifiers. `generate_agent_config` may include plan titles but not TM IDs or credentials. |
| SR-005 | T020 | Wrap `_create_tickets` body in `asyncio.timeout(120)`. On timeout → `plan.status = "error"` + log warn. |
| SR-006 | T009, T005 | Cap `AgentOverride.override_text` at 2000 chars (`max_length=2000`). CD endpoint logs warn on injection markers. |
| SR-007 | T003 (config.py) | `CONTEXT_DISTILLER_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)`. `_store_agent_config` passes this to `httpx.AsyncClient(timeout=...)`. |

---

## 7. Implementation Sequence Confirmation

The phase dependencies in `tasks.md` are correct. Additional guidance:

### Phase 1 → Phase 2 handoff

T001 (Alembic migration) must run AND be tested before T002 (ORM model). The ORM model uses
`create_type=False` on both enums — this is correct because the types are created by the
migration, not by SQLAlchemy's DDL. T002 can be written in parallel but the migration must
execute first in any test environment.

### Phase 2 sequencing

T006 (PlanRepository) has an implicit dependency on T002 (ORM model). All of T007, T008, T009,
T010 are truly independent of T006 and each other — safe to parallelize.

### Phase 3 critical path

T011 depends on T006 (PlanRepository) + T009 (PlanningLLMService). T012 depends on T011.
T013 (GET /plan endpoint) can be done in parallel with T011.

### Phase 6 frontend

T026 (planningApi client) and T027 (planStore) are independent and can start as soon as
the backend API shape is stable (which it is per contracts/api.md). T028 (AgentConfigPanel)
requires T027 for Zustand store access. T029 (PlanningModal) is the critical path item —
it depends on T026, T027, T028 all being done.

### T033 removal of old endpoint

T033 must happen last within the backend phases — it removes the old `POST .../approve`
endpoint. Until then both can coexist in the codebase.

---

## 8. Well-Architected Review

### Operational Excellence
- The five-endpoint planning API is fully observable via structlog (SR-003 required).
- The polling pattern (`GET /plan/status`) is simple, debuggable, and requires no WebSocket infra.
- Partial-failure state is recoverable without operator intervention (idempotent retry designed-in).
- **Gap**: No runbook exists for "TM is down during ticket creation." Recommend adding a note
  to `quickstart.md` that the plan stays in `confirmed` state and the user can retry via
  "Retry" button indefinitely — no operator action needed.

### Security
- Two blockers addressed in design (SR-001, SR-002). Must be verified in code review.
- Service-to-service auth (TM_SERVICE_JWT, CD_SERVICE_JWT) must be documented in `infra/.env.example` (T038).
- LLM prompt minimisation (SR-004) is a code-review gate, not an architectural control.

### Reliability
- Single-session UNIQUE constraint prevents duplicate plans.
- `asyncio.timeout(120)` on `_create_tickets` prevents event-loop starvation.
- `ON DELETE CASCADE` on `prompt_plans.session_id` ensures orphan cleanup.
- **Risk**: No retry on individual TM ticket creation failure (only full-plan retry). If TM
  returns a transient 500 for story-2 after epic and story-1 succeeded, the user must click
  Retry manually. This is acceptable per the spec — UI shows "Retry" button.

### Performance Efficiency
- Plan generation is LLM-bound (≤60s). The `asyncio.timeout` on generation should be set
  to 65s to leave a margin over the spec's 60s target.
- Ticket creation (101 nodes max) is sequential by design (Epic → Stories → Tasks in order).
  At 300ms/TM call, that's ~30s — within the spec's "first ticket in 15s" target.
- PostgreSQL index on `prompt_plans.status` covers the polling query.

### Cost Optimization
- No new infra components (no Redis, no Celery, no new container). BackgroundTasks reuses
  the existing event loop.
- LLM calls: 1 plan generation + 1 agent config per session. Both gated by user action.

### Sustainability / Maintainability
- `PlanValidator` as a pure function is highly testable and replaceable.
- `TMPlanClient` extends the existing `TicketManagerClient` pattern — consistent with the
  rest of the service.
- The `UNIQUE (session_id)` constraint on `prompt_plans` enforces the one-plan-per-session
  invariant at the DB level, not just in application code.

---

## 9. Critical Implementation Checklist (for code review gate)

Before any PR for this feature is merged, verify:

- [ ] **[BLOCKER]** `PlanRepository.update_status` (for `confirmed`) uses conditional
  `WHERE status = 'ready'` UPDATE — no separate read-then-write.
- [ ] **[BLOCKER]** `PlanningModal.tsx` has zero instances of `dangerouslySetInnerHTML`;
  all plan node content uses `<input>` or `<textarea>` or text-only render.
- [ ] Alembic migration uses `op.execute("COMMIT")` before `ALTER TYPE ... ADD VALUE`.
- [ ] `asyncio.timeout(120)` wraps `_create_tickets` body; timeout sets `plan.status = "error"`.
- [ ] `append_created_ticket` updates both `created_ticket_ids` AND `ticket_id_map` in one
  SQL statement including `updated_at = now()`.
- [ ] `PlanningService.confirm` handles `plan.status == "confirmed"` (already confirmed) by
  returning current status without re-queuing background task.
- [ ] `AgentOverride.override_text` has `max_length=2000`.
- [ ] `CONTEXT_DISTILLER_TIMEOUT_SECONDS` has `ge=1, le=60` with `default=10`.
- [ ] All planning endpoints return 403 (not 404) when session is found but owned by another user.
- [ ] structlog events emitted at: generate triggered, generate success/fail, confirm called,
  tickets_created, partial failure — none include plan_content or credentials.
- [ ] `planStore.ts` has zero `localStorage` / `sessionStorage` references.
- [ ] `POST /sessions/{id}/plan/confirm` called with `plan.status = "error"` returns 409.
- [ ] Two concurrent `POST /plan/confirm` — exactly one 202, one 409 (integration test SAC-002).

---

*Architecture review complete. Approved for implementation. All blockers must be resolved
before merge. Recommend security-architect sign-off on SR-001 and SR-002 acceptance tests.*
