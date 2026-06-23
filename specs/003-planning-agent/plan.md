# Implementation Plan: Planning Agent for Prompt Studio

**Branch**: `003-planning-agent` | **Date**: 2026-06-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/003-planning-agent/spec.md`

## Summary

Extend `services/user-input-manager` (backend + frontend) with the Planning Agent feature.
After a prompt session reaches `approved` status, users trigger plan generation that
decomposes the refined prompt into an Epic → Stories → Tasks hierarchy via LLM. The plan is
persisted before display, user-editable before confirmation, and tickets are created in Ticket
Manager transactionally with idempotent retry. Agent configuration is stored in ContextDistiller
on success (best-effort). The existing `POST /sessions/{id}/approve` single-ticket flow is
removed and replaced by the new five-endpoint planning API.

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript / React 18 (frontend)
**Primary Dependencies**: FastAPI 0.115.5, SQLAlchemy 2.0.36 async + asyncpg 0.30.0,
  Pydantic 2.10.3, Pydantic-Settings, openai 1.59.9, httpx 0.28.0, alembic 1.14.0,
  React 18.3.1, Zustand 5.0.2, Vite 6.0.3, Vitest 2.1.8
**Storage**: PostgreSQL 16 (`df_user_input` — one new table `prompt_plans`, enum extension
  on `session_status`); no MongoDB access from this service
**Testing**: pytest 8.3.4, pytest-asyncio 0.24.0, pytest-cov 6.0.0; Vitest 2.1.8; ≥ 80% coverage
**Target Platform**: Linux server (Docker, `python:3.12-slim`); browser (Vite/React SPA)
**Project Type**: Extension to existing web-service + SPA
**Performance Goals**: Plan generation p95 ≤ 60s (LLM-bound; non-dismissable overlay used);
  ticket creation first ticket ≤ 15s after confirmation
**Constraints**: No direct MongoDB writes from this service; all agent config via ContextDistiller
  API; confirmation gate — never auto-submit to TM; no new Docker container or nginx route;
  `POST /sessions/{id}/approve` removed; TM credentials MUST NOT appear in logs
**Scale/Scope**: Single-service extension; ≤ 10 stories × 10 tasks per plan (101 nodes max)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|-----------|-------|--------|
| I. Independently deployable | user-input-manager retains its own docker-compose.yml; this is an internal extension | ✅ PASS |
| II. Auth adapter pattern | `auth_adapter.py` already in place; planning endpoints use same Bearer auth; no changes | ✅ PASS |
| III. Python 3.12 everywhere | Service already on Python 3.12; no change | ✅ PASS |
| IV. Python versions pinned | requirements.txt already uses canonical versions; openai==1.59.9 is slightly ahead of canonical 1.57.0 — minor acceptable delta in existing file; no new deps added | ✅ PASS |
| V. Frontend versions pinned | React 18.3.1, Zustand 5.0.2, Vitest 2.1.8 — already in use; no version changes | ✅ PASS |
| VI. Zustand for state management | New `planStore.ts` uses Zustand; access token stays in memory (no localStorage) | ✅ PASS |
| VII. Vitest for frontend tests | Already configured; new component tests use Vitest | ✅ PASS |
| VIII. ruff for linting | Pre-commit config already present; no change needed | ✅ PASS |
| IX. Nginx N/A | No new route; user-input-manager frontend already served via Nginx | ✅ N/A |
| X. No cross-service DB access | All ContextDistiller writes via HTTP API; no direct MongoDB from this service | ✅ PASS |
| XI. FSM sovereignty N/A | user-input-manager does not touch Orchestrator FSM | ✅ N/A |
| XII. Operational safety | TM credentials not logged; agent config failure is best-effort; confirmation gate enforced | ✅ PASS |
| XIII. Plan Persistence Before Exposure | Plan persisted in `prompt_plans` before API response is returned | ✅ PASS |
| XIV. User Confirmation Gate | Plan never sent to TM without `POST .../plan/confirm`; old approve endpoint removed | ✅ PASS |
| XV. Ticket Creation All-or-None | `created_ticket_ids` + `ticket_id_map` enable idempotent retry; partial failure not terminal | ✅ PASS |
| XVI. Agent Config Best-Effort | `_store_agent_config` logged on failure; never raises; ticket creation proceeds | ✅ PASS |

**All gates pass. Proceed to Phase 0.**

## Project Structure

### Documentation (this feature)

```text
specs/003-planning-agent/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
└── contracts/           ← Phase 1 output
    └── api.md
```

### Source Code Changes (service root: `services/user-input-manager/`)

```text
backend/
├── src/
│   ├── models/
│   │   └── models.py              MODIFY: add PromptPlan ORM model; extend session_status enum
│   ├── schemas/
│   │   └── schemas.py             MODIFY: add plan schemas (PlanTask, PlanStory, PlanEpic,
│   │                              PlanContent, AgentConfig, PlanResponse, PlanUpdateRequest,
│   │                              PlanStatusResponse); remove ApproveRequest
│   ├── repositories/
│   │   └── plan_repo.py           NEW: PlanRepository
│   ├── services/
│   │   ├── llm/
│   │   │   └── planning_llm.py    NEW: generate_plan(), generate_agent_config()
│   │   ├── planning/
│   │   │   └── validator.py       NEW: PlanValidator (pure, no I/O)
│   │   ├── ticket_manager/
│   │   │   └── plan_client.py     NEW: TMPlanClient (create_epic, create_story, create_task)
│   │   └── planning_service.py    NEW: PlanningService (generate, update, confirm,
│   │                              _create_tickets, _store_agent_config, get_creation_status)
│   ├── api/v1/
│   │   ├── planning.py            NEW: planning router (5 endpoints)
│   │   └── sessions.py            MODIFY: remove /approve endpoint
│   ├── core/
│   │   └── config.py              MODIFY: add PLANNING_MODEL, CONTEXT_DISTILLER_BASE_URL,
│   │                              CONTEXT_DISTILLER_TIMEOUT_SECONDS
│   └── main.py                    MODIFY: register planning router; remove approve dependency
├── alembic/versions/
│   └── 0002_add_planning_agent.py NEW: extend session_status, add plan_status enum,
│                                  create prompt_plans table
└── tests/
    ├── unit/
    │   ├── test_plan_validator.py  NEW
    │   └── test_planning_llm.py   NEW
    └── integration/
        ├── test_plan_repo.py       NEW
        └── test_planning_service.py NEW

frontend/
├── src/
│   ├── store/
│   │   └── planStore.ts           NEW
│   ├── api/
│   │   └── client.ts              MODIFY: add planningApi object
│   ├── components/sessions/
│   │   ├── PlanningModal.tsx       NEW
│   │   ├── AgentConfigPanel.tsx    NEW
│   │   ├── SessionDetailPage.tsx   MODIFY: replace ApproveModal with PlanningModal trigger
│   │   └── ApproveModal.tsx        DELETE
│   └── i18n/
│       ├── en.json                 MODIFY: add "planning" namespace keys
│       └── ru.json                 MODIFY: add Russian "planning" translations

context-distiller service (separate service):
└── src/api/v1/memory.py           MODIFY: add POST/GET /memory/{project_id}/agent-config
```

---

## Phase 0: Research

### R-001 — Alembic enum extension pattern

**Decision**: Use `op.execute(ALTER TYPE ... ADD VALUE)` for `session_status` enum extension;
create `plan_status` as a new type. PostgreSQL allows adding new enum values without recreation
since PostgreSQL 9.1, but only in a transaction-safe way using `op.execute` with an explicit
ALTER TYPE statement (not `op.create_enum_type` for the extension).

**Rationale**: The existing `0001_initial.py` uses `op.execute(CREATE TYPE ... AS ENUM)`.
The extension migration chains `down_revision = "0001_initial"`. SQLAlchemy 2.0 + asyncpg
handles this correctly when the ORM's `Enum` uses `create_type=False` and the type is
created externally by the migration.

**Alternatives considered**: Recreate the enum with a new type — rejected (requires
`DROP TYPE` and column migration; risky in production). Use `VARCHAR` for new statuses —
rejected (inconsistent with existing pattern).

### R-002 — FastAPI BackgroundTasks for ticket creation

**Decision**: Use `fastapi.BackgroundTasks` injected into the `confirm` endpoint.
`PlanningService.confirm()` accepts `BackgroundTasks`, adds `_create_tickets(session_id)`,
and returns 202. The background task runs in the same event loop after the response is sent.

**Rationale**: Ticket creation is multi-step and can take 10–30s. The user must not wait for
HTTP response; they poll `GET .../plan/status`. BackgroundTasks is built into FastAPI,
requires no additional infra (no Celery, no Redis), and is fully testable with AsyncMock.

**Alternatives considered**: asyncio.create_task directly — equivalent but harder to test and
not idiomatic in FastAPI context. Celery — rejected (adds infra complexity for a feature
that runs at human interactive speed, not high throughput).

### R-003 — Idempotent ticket creation with created_ticket_ids

**Decision**: On each TM API call in `_create_tickets`, record the returned TM ticket ID
immediately into `prompt_plans.created_ticket_ids` and `ticket_id_map` via `PlanRepository.
append_created_ticket`. On retry, nodes whose local_id is in `ticket_id_map` are skipped.
Epic is tracked separately in `tm_epic_id`.

**Rationale**: The `ticket_id_map` (JSONB) maps `local_id → tm_ticket_id`. Before calling
TM for any node, check if local_id exists in the map. This allows partial resume with zero
duplicates regardless of where the failure occurred.

**Alternatives considered**: Transaction with all-or-none rollback — rejected (TM tickets
have no rollback API; partial creation is the real-world failure mode). Recording only
`created_ticket_ids` without the mapping — rejected (insufficient to compute depends_on
TM IDs for tasks after a partial failure retry).

### R-004 — PlanValidator circular dependency detection

**Decision**: Build a directed graph from `depends_on` edges within each Story.
Use DFS with a visited set and a recursion stack. A back-edge to the recursion stack signals
a cycle. Pure Python, no external library. Maximum input size is 10 nodes per story.

**Rationale**: No additional dependencies needed. The input is small (≤ 10 tasks) so
O(V+E) DFS is instantaneous. The validator must be pure (no I/O) per the constitution's
"read from disk on each run" pattern (same spirit — keep validators side-effect free).

**Alternatives considered**: topological sort with cycle detection — equivalent but
slightly more code for this small scale.

### R-005 — ContextDistiller agent-config endpoints

**Decision**: Two new endpoints added to the `context-distiller` service:
- `POST /memory/{project_id}/agent-config` — upsert `agent_configs` MongoDB collection
  by `_id = project_id`; returns 201 with `{ project_id, stored_at }`.
- `GET /memory/{project_id}/agent-config` — returns document or 404.

These follow the same auth pattern as existing `/memory/*` routes (`UserDep`).
`user-input-manager` calls these endpoints via `httpx` in `_store_agent_config`; it
never touches MongoDB directly.

**Alternatives considered**: Reuse the existing `/memory/{project_id}` endpoint — rejected
(agent config is structured differently from the freeform text memory; mixing them would
complicate ContextDistiller's schema). Store agent config in PostgreSQL on user-input-manager
— rejected (cross-service data; Orchestrator expects to read agent config from ContextDistiller).

### R-006 — Plan tree JSON schema (PlanContent)

**Decision**: Store the full plan as JSONB in `prompt_plans.plan_content` with this shape:

```json
{
  "epic": {
    "local_id": "epic-1",
    "title": "string (≤200)",
    "description": "string (≤500)",
    "ticket_type": "epic"
  },
  "stories": [
    {
      "local_id": "story-1",
      "title": "string (≤200)",
      "description": "string (≤500)",
      "ticket_type": "story",
      "tasks": [
        {
          "local_id": "task-1-1",
          "title": "string (≤200)",
          "description": "string (≤500)",
          "ticket_type": "task|implementation|investigation",
          "complexity": "S|M|L|XL",
          "depends_on": ["task-1-0"]
        }
      ]
    }
  ]
}
```

`local_id` uses hierarchical naming (`epic-1`, `story-N`, `task-N-M`) and is only used
within the plan. TM IDs are stored separately in `ticket_id_map`.

**Rationale**: JSONB allows the full tree to be stored and returned without a join-heavy
normalized schema. The validator enforces all structural constraints before storage.

---

## Phase 1: Design & Contracts

### Data Model (`data-model.md`)

See [data-model.md](data-model.md) — generated below.

### API Contracts (`contracts/`)

See [contracts/api.md](contracts/api.md) — generated below.

### Quickstart (`quickstart.md`)

See [quickstart.md](quickstart.md) — generated below.

### Agent Context CLAUDE.md update

Updated `CLAUDE.md` at project root to reference this plan (see below).

---

## Complexity Tracking

No constitution violations. Removal of `approve_and_create_ticket` is a breaking API
change — this is intentional per FR-013 and constitution Principle XIV (old endpoint
bypassed the confirmation gate). Tests for the removed endpoint must be deleted.
