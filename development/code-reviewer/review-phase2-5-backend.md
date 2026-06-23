# Backend Review — Phases 1–5 (T001–T025)
**Feature**: 003-planning-agent  
**Reviewer**: code-reviewer  
**Date**: 2026-06-23  
**Scope**: Migration, ORM, Config, Schemas, Repositories, Planning Service, LLM Service, Validator, TM Plan Client, API Router, Tests  
**Decision**: APPROVED WITH BLOCKERS — 2 blockers must be resolved before merge

---

## Decision Summary

| Severity | Count | Must block merge |
|----------|-------|-----------------|
| Blocker  | 2     | Yes             |
| Major    | 1     | Strongly recommended |
| Minor    | 4     | No              |
| Nit      | 1     | No              |
| PASS     | 14    | —               |

---

## BLOCKER-001 — Standard `logging` used instead of `structlog` (constitution violation)

**Files**: `planning_service.py:6,29` · `planning_llm.py:6,15`  
**Constitution rule**: All services must use `structlog` for all logging — no `print()`, no `logging`.

Both files open with:
```python
import logging
logger = logging.getLogger(__name__)
```

All subsequent log calls use stdlib `logger.info/warning/error`. This violates the project constitution and bypasses the structured logging pipeline that all other services depend on.

This applies to every log statement in both files — including the SR-003 audit events (`plan.generation_triggered`, `plan.generated`, `plan.confirmed`, `plan.tickets_created`). The audit trail is present but routed to the wrong sink.

**Required fix**:
```python
# Replace in both files:
import structlog
logger = structlog.get_logger(__name__)
# All log calls are API-compatible (logger.info/warning/error work as-is with structlog)
```

---

## BLOCKER-002 — `TMPlanClient` uses wrong API field name `"type"` instead of `"ticket_type"`

**File**: `plan_client.py:17,31,50`  
**Playbook reference**: `services/ticket-manager/docs/api-endpoints-agent-playbook.md:141,156`

The playbook specifies `"ticket_type"` as the field name for ticket creation. `TMPlanClient` sends `"type"`:

```python
# plan_client.py — WRONG
json={"title": epic.title, "description": ..., "type": "epic", ...}
json={"title": story.title, ..., "type": "story", ...}
json={"title": task.title, ..., "type": task.ticket_type, ...}
```

At runtime every `POST /api/projects/{id}/tickets` call will either be rejected (422) or silently ignore the ticket type, causing malformed tickets. All three methods (`create_epic`, `create_story`, `create_task`) are affected.

The unit tests in `test_plan_client.py` mock `_request` entirely and assert `payload["type"]` — they validate the wrong contract and will continue passing even after the fix.

**Required fix**:
```python
# In all three methods, rename the field:
"ticket_type": "epic"     # was "type": "epic"
"ticket_type": "story"    # was "type": "story"
"ticket_type": task.ticket_type  # was "type": task.ticket_type
```

**Also fix** `test_plan_client.py` assertions: change all `payload["type"]` checks to `payload["ticket_type"]`.

---

## MAJOR-001 — `generate()` performs synchronous LLM call but returns HTTP 202

**File**: `planning_service.py:46–94` · `planning.py:35–47`

The endpoint `POST /sessions/{id}/plan` is declared `status_code=202` — the HTTP standard for "accepted for background processing." But `PlanningService.generate()` runs the full LLM pipeline (up to ~60 s) **synchronously inside the request handler** before responding:

```python
# Lines 60–78 — these run before the 202 is sent
plan_content = await generate_plan(iterations)           # LLM call 1, up to 60 s
agent_config = await generate_agent_config(...)          # LLM call 2, up to 30 s
plan = await self._plan_repo.update_status(plan, "ready", ...)
await self._session_repo.update(session, status="plan_ready")
# Only after all of the above does the handler return
return PlanGenerateResponse(session_id=..., plan_id=..., status="planning")
```

The response also contains `status="planning"` (line 92) even though by the time it is sent the plan is already `status="ready"` and session is `status="plan_ready"`. The frontend polls `GET /plan` to detect completion; with synchronous execution the plan is already done before the first poll fires, so this is a usability mismatch — the "generating" spinner may flash for one poll cycle at most.

The 202 semantics are misleading to API consumers and any future load balancer or reverse proxy. **True background processing via `BackgroundTasks` (already used in `confirm()`) would fix both issues.**

This is Major rather than Blocker because the feature works correctly end-to-end; the issue is correctness of HTTP semantics and the stale `status` field in the response.

---

## MINOR-001 — `ApproveRequest` schema not removed despite endpoint deletion (T033)

**File**: `schemas.py:193–198`

`POST /sessions/{id}/approve` was correctly removed from `sessions.py`. However, `ApproveRequest` remains in `schemas.py` as dead code. No import of it exists in any router or service. Remove it.

---

## MINOR-002 — Lazy import of `IterationRepository` inside method body

**File**: `planning_service.py:97`

```python
async def _get_latest_refined_prompt(self, session_id: uuid.UUID) -> str:
    from src.repositories.session_repo import IterationRepository
```

All other imports are at module top. Move to module-level. The circular import concern (likely the reason for deferring it) is not present here — `session_repo` is already imported at the top of `session_service.py` without issue.

Additionally at line 99: `iter_repo = IterationRepository(self._plan_repo._db)` — accessing the private `_db` attribute of a sibling repository. Inject `db` directly from the service constructor instead.

---

## MINOR-003 — Dead import in `planning.py`

**File**: `planning.py:22`

```python
from src.services.ticket_manager.client import get_ticket_manager_client
```

`get_ticket_manager_client` is never used in this file. Remove it.

---

## MINOR-004 — ORM uses `JSON` type; migration uses `JSONB`

**File**: `models.py:202–206`

The `PromptPlan` ORM model declares `plan_content`, `agent_config`, `validation_errors`, `created_ticket_ids`, `ticket_id_map` all as `JSON`. The migration at `0002_add_planning_agent.py` creates these columns as `JSONB`. SQLAlchemy's `JSON` type on PostgreSQL maps to plain `JSON`, not `JSONB`. This won't cause data loss but forfeits JSONB operator indexing. Switch ORM columns to `from sqlalchemy.dialects.postgresql import JSONB`.

---

## NIT-001 — `get_planning_service` creates a new `TMPlanClient` per request

**File**: `planning.py:28–32`

```python
def get_planning_service(
    db: AsyncSession = Depends(get_db),
    tm: TMPlanClient = Depends(lambda: TMPlanClient()),
) -> PlanningService:
```

Each request instantiates a new `TMPlanClient`. `TMPlanClient` inherits from `TicketManagerClient` which likely allocates an httpx client. A shared singleton or `@lru_cache` dependency would be more efficient, but this is not a correctness issue.

---

## Security checklist

| SR | Requirement | Status | Evidence |
|----|------------|--------|----------|
| SR-001 | No `dangerouslySetInnerHTML` | PASS (N/A to backend) | — |
| SR-002 | Atomic confirm gate | PASS | `plan_repo.py:confirm_if_ready()` — UPDATE WHERE status='ready' RETURNING ✓ |
| SR-003 | `structlog` audit logging | **FAIL** | Events present but routed through stdlib `logging` → see BLOCKER-001 |
| SR-004 | LLM prompt minimisation | PASS | `generate_plan` sends only `refined_prompt`; `generate_agent_config` sends project_id + epic/story titles only ✓ |
| SR-005 | `asyncio.timeout(120)` on `_create_tickets` | PASS | `planning_service.py:177` — `async with asyncio.timeout(120)` ✓ |
| SR-006 | `AgentOverride.override_text` max_length=2000 | PASS | `schemas.py:241` — `Field(max_length=2000)` ✓ |
| SR-007 | `CONTEXT_DISTILLER_TIMEOUT_SECONDS` ge=1 le=60 | PASS | `config.py` — `Field(default=10.0, ge=1, le=60)` ✓ |

---

## Component pass/fail summary

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Migration | `0002_add_planning_agent.py` | PASS | IF NOT EXISTS guard, correct downgrade() |
| ORM models | `models.py` | PASS (w/ minor) | JSON vs JSONB (MINOR-004) |
| Config | `config.py` | PASS | All SR-007 fields present |
| Schemas | `schemas.py` | PASS (w/ minor) | ApproveRequest dead code (MINOR-001) |
| Plan repo | `plan_repo.py` | PASS | `confirm_if_ready()` atomic, `append_created_ticket()` idempotent |
| Planning router | `planning.py` | PASS (w/ minor/nit) | 5 endpoints correct, dead import (MINOR-003), lambda client (NIT-001) |
| Planning service | `planning_service.py` | FAIL | BLOCKER-001 (logging), MAJOR-001 (sync 202), MINOR-002 (lazy import) |
| LLM service | `planning_llm.py` | FAIL | BLOCKER-001 (logging) |
| Validator | `validator.py` | PASS | Cycle detection, all field limits, cross-story dependency rejection ✓ |
| TM plan client | `plan_client.py` | FAIL | BLOCKER-002 (`"type"` → `"ticket_type"`) |
| Unit: validator | `test_plan_validator.py` | PASS | 30+ cases, diamond, cycle, boundary ✓ |
| Unit: plan_client | `test_plan_client.py` | FAIL | Tests validate wrong field name; must update after BLOCKER-002 fix |
| Unit: planning_llm | `test_planning_llm.py` | Not reviewed in this pass |
| Unit: planning_service | `test_planning_service_unit.py` | Not reviewed in this pass |
| Integration: plan_repo | `test_plan_repo.py` | Not reviewed in this pass |
| Integration: planning_service | `test_planning_service.py` | PASS | generate, confirm, _create_tickets full path, retry idempotency, store failure ✓ |

---

## Required actions before merge

1. **BLOCKER-001**: Replace `import logging` + `logging.getLogger` with `structlog` in `planning_service.py` and `planning_llm.py`
2. **BLOCKER-002**: Change `"type"` → `"ticket_type"` in all three `TMPlanClient` methods; update `test_plan_client.py` assertions to match
3. **MAJOR-001** (strongly recommended): Move LLM call to `BackgroundTasks` and return true 202 immediately; update `PlanGenerateResponse.status` to reflect the actual pre-response state

Items MINOR-001 through NIT-001 should be addressed in T033 cleanup or a follow-up ticket but do not block merge.
