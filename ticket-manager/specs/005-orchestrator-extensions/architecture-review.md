# Architecture Review: Workflow Orchestrator Integration Extensions

**Feature**: `005-orchestrator-extensions` | **Reviewer**: Software Architect Agent | **Date**: 2026-06-21

---

## Executive Summary

The design is **sound and implementation-ready**. All key decisions in `research.md` are well-reasoned and consistent with existing codebase patterns. The following review identifies **4 implementation risks** that the backend agent must handle carefully, plus **3 consistency gaps** between the spec and the existing code that need alignment before implementation.

Overall confidence: **High**. No architectural rework needed. Proceed with implementation.

---

## 1. Alignment with Existing Codebase Patterns

### 1.1 SQLAlchemy Model Conventions ✅

The existing `Ticket` model uses:
- `Mapped[T]` + `mapped_column()` pattern (SQLAlchemy 2.0 declarative style)
- `Enum(MyEnum, name="type_name", create_type=False)` for PostgreSQL enums (enum type pre-created in migrations)
- `func.now()` as `server_default` for timestamps
- `uuid4` as Python-side primary key default

**The new `FsmStatus` enum must follow the same `create_type=False` pattern.** Migration 015 creates `fsm_status_enum`; the model must declare:
```python
fsm_status: Mapped[FsmStatus | None] = mapped_column(
    Enum(FsmStatus, name="fsm_status_enum", create_type=False,
         values_callable=lambda x: [e.value for e in x]),
    nullable=True,
)
```

Note that `TicketType` already uses `values_callable` to map lowercase enum values — `FsmStatus` should do the same since its values are mixed-case (`BLOCKED` vs `backlog`).

### 1.2 Service Layer Conventions ✅

The existing service pattern:
- Session passed as first arg (`session: AsyncSession`)
- HTTPException raised directly from service layer (not re-wrapped by router)
- `_load_ticket_response()` used consistently to hydrate responses after mutations

**For `fsm_service.py`**: The new `TicketFsmResponse` needs its own loader function analogous to `_load_ticket_response()`, or `_load_ticket_response()` must be extended. Given it lives in a separate service file, define a `_load_ticket_fsm_response()` in `fsm_service.py` that either re-runs the selectinload query with FSM fields or calls into the existing ticket loader and appends FSM fields.

### 1.3 Security Dependency Pattern ✅

The `require_role()` factory in `security.py` returns `Depends(dependency)` directly, not just `dependency`. New `require_service_account_or_admin` must follow the same pattern to work as a FastAPI dependency parameter:
```python
def require_service_account_or_admin() -> Any:
    async def dependency(current_user: Any = Depends(get_current_user)) -> Any:
        ...
    return Depends(dependency)
```

### 1.4 Router Registration ✅

The `router.py` imports all routers at module level and calls `router.include_router()`. The new `orchestrator.py` router must be added to both the import block and the `include_router` calls. The orchestrator router prefix should be `""` (empty) since its paths already include full segments (`/projects/...`, `/orchestrator/...`, `/tickets/...`).

---

## 2. Implementation Risks

### RISK-1: Router Path Collision — `/tickets/{ticket_id}` vs `/tickets/batch-fsm-status`

**Severity: HIGH**

The existing `tickets.py` router defines `GET /{ticket_id}` with a UUID path parameter. Adding `POST /batch-fsm-status` to the **same** tickets router could cause FastAPI path ambiguity if the order is wrong — FastAPI resolves routes top-to-bottom, so `/batch-fsm-status` could be matched as a ticket_id if declared after the parameterized route.

**Resolution**: Place `POST /tickets/batch-fsm-status` in `orchestrator.py` (not `tickets.py`), registered with an empty router prefix. This avoids the collision entirely. The OpenAPI contract already shows it under the `Orchestrator` tag, consistent with this placement.

Alternatively, if placed in `tickets.py`, declare the literal `batch-fsm-status` route **before** the `/{ticket_id}` route.

### RISK-2: `updated_at` Not Auto-Updating on FSM PATCH

**Severity: MEDIUM**

The `Ticket.updated_at` column uses `onupdate=func.now()` — this fires on SQLAlchemy ORM updates. However, for `onupdate` to trigger, at least one column on the mapped object must be dirty before `session.commit()`. If `fsm_service.patch_fsm_fields` only sets FSM columns (which don't exist yet on the model before T005), the `onupdate` hook will fire correctly once T005 adds the FSM columns.

**The key concern**: The pending filter uses `updated_at > last_orchestrator_run` as the staleness signal. If the orchestrator patches FSM state and `updated_at` does NOT update (e.g., when all FSM columns have the same value as before), a ticket could fail to re-enter the pending queue after the orchestrator's own write.

**Resolution**: In `patch_fsm_fields`, explicitly set `ticket.updated_at = datetime.now(UTC)` after applying FSM field changes, in addition to relying on `onupdate`. This is belt-and-suspenders but critical for correctness of the polling loop.

### RISK-3: Tag Delta and the 10-Tag Limit

**Severity: MEDIUM**

The existing `add_tag()` service enforces a hard limit of 10 tags per ticket (`if len(ticket.tags) >= 10: raise HTTPException(...)`). The new `apply_tag_delta()` service is specified as silently idempotent for add/remove — but it must also enforce or explicitly waive this limit.

**Resolution**: `apply_tag_delta` must enforce the same 10-tag limit **after** applying removes but before applying adds. The check should be: `if len(current_tags - to_remove) + len(to_add - existing_names) > 10: raise 400`. Document this in the implementation so the backend agent doesn't inadvertently bypass the constraint.

### RISK-4: `orchestrator_errors` JSONB — SQLAlchemy Type Mapping

**Severity: LOW**

The existing codebase uses `JSONB` in `TicketEvent` (see `ticket_event.py`) mapped as `Mapped[dict | None]`. The new `orchestrator_errors` column is a JSON array of strings, not a dict. SQLAlchemy's JSONB column accepts any JSON-serializable type including lists, but the Python type annotation must reflect this:
```python
orchestrator_errors: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
```
The data-model spec says "JSON array of strings, max 50 entries (enforced by service layer)". The service layer in `patch_fsm_fields` must cap this at 50 before committing.

---

## 3. Consistency Gaps vs Spec

### GAP-1: `TicketSummary.dependencies` Field

The OpenAPI contract defines `TicketSummary.dependencies` as an array of ticket UUIDs ("IDs of tickets this ticket depends on (parent_ticket_id chain)"). However, looking at the data model, the `tickets` table only has `parent_ticket_id` (a single FK), not a multi-valued dependency table.

**Interpretation**: `dependencies` = `[ticket.parent_ticket_id]` if not null, else `[]`. The `follow_ups` array = `[t.id for t in ticket.follow_ups]` (existing relationship). This is a derived field and must be computed in the `get_pending_tickets` projection logic, not stored.

Backend agent must compute both arrays from the loaded ticket's relationships.

### GAP-2: `FsmPatchRequest` Does Not Include `override`

The `FsmPatchRequest` schema in the OpenAPI contract lists: `fsm_status`, `blocked_reason`, `brainstorm_round`, `assigned_agent`, `override_reason`, `last_orchestrator_run`, `orchestrator_errors` — but **not `override`**.

The data model says "reset to `false` after orchestrator processes it (via FSM PATCH)". If the orchestrator cannot set `override=false` through the FSM PATCH endpoint, there is no mechanism to clear the override flag.

**Resolution**: Add `override: bool | None = None` to `FsmPatchRequest`. The `patch_fsm_fields` service should allow setting `override` to `false` (clearing it). This is the documented reset mechanism. The OpenAPI contract should be updated to include this field.

### GAP-3: Ticket `number` Field Missing from `TicketSummary`

The existing `TicketResponse` includes `display_id` (e.g., `"PRJ-0001"`) and `number` fields. The `TicketSummary` schema in the OpenAPI contract omits both. Since the orchestrator may log or reference tickets by display ID in audit events, consider including `display_id` in `TicketPendingSummary`. This is optional but would improve debuggability.

---

## 4. Design Validations (Confirmed Correct)

| Decision | Verdict | Notes |
|---|---|---|
| Separate `fsm_status_enum` from `ticket_status` | ✅ Correct | Avoids mixing human/machine workflows; consistent with Principle V |
| Keyset cursor on `(updated_at, id)` | ✅ Correct | Stable under concurrent writes; index in migration 015 supports it |
| Separate `orchestrator_audit_events` table | ✅ Correct | `ticket_events.actor_id` requires a users FK — service agent has no user row |
| Email-based service account check | ✅ Correct | No new role needed; `require_role` pattern extended cleanly |
| Fail-closed on missing `TICKET_MANAGER_SERVICE_EMAIL` | ✅ Correct | Only admin role passes when env var absent; no 500 errors |
| Atomic tag delta at new endpoint path | ✅ Correct | Preserves existing `/tags` contract; avoids race conditions |
| `POST /tickets/batch-fsm-status` (not GET) | ✅ Correct | Body-based batch lookup is standard practice |
| All new columns nullable or server-defaulted | ✅ Correct | Zero-downtime migration path maintained |
| Partial FSM PATCH (exclude_unset) | ✅ Correct | Pydantic v2 `model_dump(exclude_unset=True)` pattern works with FastAPI |

---

## 5. Suggested Implementation Order Notes

The plan's phase ordering is correct. One addition:

**T005 and T003 must be sequenced carefully**: the SQLAlchemy model change (T005) should be written to match exactly what migration 015 creates. Since migration 015 creates the `fsm_status_enum` PostgreSQL type with `create_type=False` expected by the model, the migration must run (`alembic upgrade head`) before the application starts. The Phase 2 checkpoint ("Run `alembic upgrade head` and `mypy src/`") correctly enforces this.

**For test isolation**: Contract tests that test FSM endpoints will need a test fixture that creates a ticket and optionally sets FSM state via the PATCH endpoint. The autotester should create shared fixtures early to avoid duplication across T011, T014, T017, T022, T025, T031, T034.

---

## 6. Summary of Actions Required

| # | Severity | Owner | Action |
|---|---|---|---|
| RISK-1 | HIGH | backend | Place `batch-fsm-status` in `orchestrator.py` or declare it before `/{ticket_id}` in `tickets.py` |
| RISK-2 | MEDIUM | backend | Explicitly set `ticket.updated_at` in `patch_fsm_fields` |
| RISK-3 | MEDIUM | backend | Enforce 10-tag limit in `apply_tag_delta` after removes, before adds |
| RISK-4 | LOW | backend | Type `orchestrator_errors` as `Mapped[list[str] \| None]`; cap at 50 in service layer |
| GAP-1 | LOW | backend | Compute `dependencies` as `[parent_ticket_id]` (or `[]`), `follow_ups` from relationship |
| GAP-2 | MEDIUM | backend + product-manager | Add `override: bool \| None` to `FsmPatchRequest` and update OpenAPI contract |
| GAP-3 | LOW | backend | Optionally add `display_id` to `TicketPendingSummary` for debuggability |
