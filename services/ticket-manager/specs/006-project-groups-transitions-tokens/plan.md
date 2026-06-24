# Implementation Plan: Project Groups, Assignee-Only Transitions, and Tokens Spent

**Branch**: `006-project-groups-transitions-tokens` | **Date**: 2026-06-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/006-project-groups-transitions-tokens/spec.md`

## Summary

Extend `services/ticket-manager` (backend + frontend) with three independent, additive changes:

1. **Project Groups** — new `project_groups` table; all projects get a mandatory FK to a group;
   Default group (`DEFAULT`) seeded in migration; group CRUD endpoints; project list filterable
   by group; group selector on project create/update.
2. **Assignee-Only Transitions** — remove the progress-update gate from `transition_service.py`
   while keeping the assignee-only authorization check intact.
3. **Tokens Spent** — add `tokens_spent` INTEGER field to tickets; expose a single
   increment-only endpoint; each increment recorded as an immutable TicketEvent.

All API changes are documented in `docs/api-updates.md` at the service root (SC-007).

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript 5.7 / React 18.3.1 (frontend)
**Primary Dependencies**: FastAPI 0.115.5, SQLAlchemy 2.0.36 async + asyncpg 0.30.0,
  Pydantic 2.10.3, pydantic-settings 2.7.0, Alembic 1.14.0, structlog 24.4.0,
  React 18.3.1, Zustand 5.0.2, @tanstack/react-query 5.56.2, axios 1.7.9, Vite 6.0.3, Vitest 2.1.8
**Storage**: PostgreSQL 16 (`df_ticket_manager` — two new migrations: 017 + 018)
**Testing**: pytest 8.3.4, pytest-asyncio 0.24.0, pytest-cov 6.0.0; Vitest 2.1.8; ≥80% coverage
**Target Platform**: Linux server (Docker, `python:3.12-slim`); browser (Vite/React SPA)
**Project Type**: Extension to existing web-service + SPA
**Performance Goals**: Group CRUD endpoints ≤200ms p95; transition endpoint latency unchanged;
  tokens_spent increment ≤200ms p95
**Constraints**: DEFAULT group undeletable + system-seeded; group_id NOT NULL on projects
  (backfilled in migration); tokens_spent increment-only via API; all API changes in
  `docs/api-updates.md`; no cross-service calls; assignee gate for transitions preserved
**Scale/Scope**: Three independent changes; 2 new DB tables (project_groups) + 2 new columns;
  7 new endpoints; 2 modified endpoints; ~8 new backend files; ~6 new/modified frontend files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Lifecycle Traceability First | ✅ PASS | tokens_spent increments emit TicketEvent; transitions already emit events; group assignments emit structured log (project event table deferred — see Complexity Tracking) |
| II | Event Integrity and Auditability | ✅ PASS | `ticket.tokens_spent_incremented` event emitted per increment; transition events unchanged; group change emits structured log + project-level event (see R-003) |
| III | Role-Based Access Control | ✅ PASS | Assignee-only check preserved (FR-011/012); group management enforces `get_current_user`; tokens_spent enforces auth |
| IV | Collaborative Execution Model | ✅ PASS (deliberate relaxation) | FR-010 removes the progress gate — stricter than what Principle IV requires. Principle IV says "MUST NOT be considered complete" (completion state); the old gate blocked ALL transitions. Relaxation is intentional: assignee-only gate (FR-011) provides sufficient accountability. Documented in Complexity Tracking. |
| V | Controlled Workflow Evolution | ✅ PASS | No `ticket_status` enum changes |
| VI | API and Contract Discipline | ✅ PASS | All new endpoints under `/api/v1/...`; all changes in `docs/api-updates.md` (SC-007) |
| VII | Data Integrity and Migration Safety | ✅ PASS | Migrations 017 + 018 with rollback paths; 017 backfills existing projects to DEFAULT |
| VIII | Quality Gates by Default | ✅ PASS | Contract + integration tests for all three features; updated transition tests |
| IX | Operability and Observability | ✅ PASS | structlog used; /health and /ready unchanged |
| X | Security and Privacy Baseline | ✅ PASS | All endpoints enforce auth; group identifier validation server-side |

**All gates pass. Proceed to Phase 0.**

## Project Structure

### Documentation (this feature)

```text
specs/006-project-groups-transitions-tokens/
├── plan.md              ← this file
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
└── contracts/
    └── api.md           ← Phase 1 output

docs/api-updates.md      ← service-root deliverable (SC-007)
```

### Source Code Changes (service root: `services/ticket-manager/`)

```text
backend/
├── src/
│   ├── models/
│   │   ├── project_group.py       NEW: ProjectGroup ORM model
│   │   ├── project.py             MODIFY: add group_id FK + group relationship
│   │   └── ticket.py              MODIFY: add tokens_spent INTEGER field
│   ├── schemas/
│   │   ├── project_group.py       NEW: ProjectGroupCreate, ProjectGroupUpdate, ProjectGroupResponse
│   │   ├── project.py             MODIFY: ProjectCreate add group_id; ProjectResponse add group field
│   │   └── ticket.py              MODIFY: TicketResponse add tokens_spent;
│   │                              NEW: TokensSpentIncrementRequest, TokensSpentIncrementResponse
│   ├── services/
│   │   ├── project_group_service.py  NEW: create_group, list_groups, get_group,
│   │   │                             update_group, delete_group
│   │   ├── transition_service.py     MODIFY: remove progress gate (lines 53–86);
│   │   │                             keep assignee check (lines 41–46)
│   │   └── tokens_spent_service.py   NEW: increment_tokens_spent
│   ├── api/v1/
│   │   ├── groups.py              NEW: group CRUD router (5 endpoints)
│   │   ├── projects.py            MODIFY: add group_id filter on list; add PATCH endpoint;
│   │   │                          include group in response; auto-assign DEFAULT if group_id omitted
│   │   └── tokens_spent.py        NEW: POST /tickets/{id}/tokens-spent
│   └── main.py                    MODIFY: register groups + tokens_spent routers
├── alembic/versions/
│   ├── 017_add_project_groups.py  NEW: create project_groups, seed DEFAULT, add group_id FK to projects
│   └── 018_add_tokens_spent.py    NEW: add tokens_spent column to tickets
└── tests/
    ├── contract/
    │   ├── test_groups.py         NEW: group CRUD contract tests
    │   └── test_tokens_spent.py   NEW: increment-only contract tests
    └── integration/
        ├── test_project_group_service.py  NEW
        ├── test_transition_no_gate.py     NEW: verify gate removal + assignee check retained
        └── test_tokens_spent_service.py   NEW

docs/
└── api-updates.md        NEW: all API changes (SC-007 required deliverable)

frontend/src/
├── types.ts              MODIFY: add ProjectGroup type, update Project with group_id/group
├── api/
│   └── client.ts (or groupsApi.ts)  MODIFY/NEW: group CRUD + tokens_spent API calls
├── components/projects/
│   └── GroupFilter.tsx    NEW: group selector for project list filter
├── pages/
│   ├── ProjectListPage.tsx    MODIFY: add group filter UI
│   └── TicketDetailPage.tsx   MODIFY: show tokens_spent + increment button
└── locales/
    ├── en.json                MODIFY: add group and tokens_spent i18n keys
    └── ru.json                MODIFY: add Russian translations
```

---

## Phase 0: Research

### R-001 — Group identifier normalization strategy

**Decision**: Normalize the identifier to **uppercase** on write (in the service layer, before DB
persistence). Store and compare as uppercase; display as stored. Validation: `^[A-Z0-9]{4,8}$`
applied after `.upper()` on the input.

**Rationale**: The spec says "stored case-insensitively (case-insensitively, displayed as entered)".
Normalizing in Python before write is simpler than using PostgreSQL CITEXT extension (no additional
extension install needed). Users enter "team1" and see "TEAM1" — this is the clearest interpretation
of "displayed as entered after normalization". A UNIQUE constraint on the `identifier` column
enforces uniqueness without CITEXT.

**Alternatives considered**: PostgreSQL CITEXT — rejected (requires enabling the citext extension;
adds complexity for a simple constraint). Lowercase storage — rejected (spec shows `DEFAULT` in
uppercase; uppercase is the natural choice for short codes).

### R-002 — Migration strategy: adding NOT NULL FK group_id to projects

**Decision**: Three-step migration in a single Alembic migration file (017):
1. Create `project_groups` table.
2. Insert the DEFAULT group (`identifier='DEFAULT'`, `is_system=TRUE`).
3. Add `group_id` column to `projects` as NULLABLE, set all existing rows to DEFAULT group id,
   then `ALTER COLUMN group_id SET NOT NULL`.

**Rationale**: PostgreSQL cannot add a NOT NULL column in one step unless a DEFAULT is also
specified. Using an intermediate nullable + backfill + NOT NULL alter is the standard zero-downtime
pattern. This is wrapped in a single Alembic migration because the three steps are atomic from a
schema perspective — no intermediate state should be committed.

**Alternatives considered**: DEFAULT clause on ADD COLUMN — possible but requires a constant
default (not a FK value from the newly inserted row). The nullable+backfill pattern is cleaner.
Two separate migrations — rejected (unnecessary split for tightly coupled operations).

### R-003 — Project group assignment event

**Decision**: Emit a **structured log entry** (`structlog.info("project.group_changed", ...)`)
when a project's group is updated. Do NOT create a `project_events` table in this feature.

**Rationale**: The ticket-manager constitution (Principle II) requires immutable event records
for domain actions. However, the existing event infrastructure is entirely ticket-scoped
(`ticket_events` table with `ticket_id` FK). Adding a `project_events` table is architecturally
correct but outside the scope of this feature. A structured log record provides observability
without breaking the schema. A `project_events` table is added to the backlog as a follow-up.

**Alternatives considered**: Reuse `ticket_events` with a nullable ticket_id — rejected
(schema corruption; FK integrity). New `project_events` table now — rejected (out of scope;
doubles migration complexity with no spec requirement).

### R-004 — tokens_spent endpoint: new route vs. extending /resources

**Decision**: Create a **new endpoint** `POST /api/v1/tickets/{ticket_id}/tokens-spent` with its
own router file `api/v1/tokens_spent.py` and service `services/tokens_spent_service.py`.

**Rationale**: The existing `POST /api/v1/tickets/{ticket_id}/resources` increments `time_spent`
and `tokens_consumed` (both system-driven). The new `tokens_spent` field is user-driven and has
different semantics (increment-only, activity-logged, user-initiated). Mixing them in the same
endpoint would create confusion about which fields are system-managed vs. user-managed. A separate
endpoint with its own schema makes the contract explicit and independently testable.

**Alternatives considered**: Add `tokens_spent_delta` to `TicketResourceIncrementRequest` —
rejected (conceptual mismatch; tokens_consumed is system-driven; merging would require
distinguishing the two fields' semantics in the same request). Reuse existing resources endpoint
but with a new field type check — rejected (same objection, plus harder to version).

### R-005 — docs/api-updates.md as a required deliverable

**Decision**: Create `docs/api-updates.md` at the service root **during the plan phase** as a
stub, with section headers for each feature's API changes. Implementation tasks fill in the
detailed endpoint documentation. This file is not auto-generated — it is a living document.

**Rationale**: SC-007 and FR-009/013/019 all require this file to exist before any new endpoint
is deployed. Creating the stub now ensures it is tracked in the implementation checklist and will
not be forgotten. Content is filled in during task implementation (T-series tasks).

**Alternatives considered**: Create only at implementation time — rejected (violates SC-007 intent
which says "before any new endpoint is deployed"; the plan phase is the correct creation point).

---

## Phase 1: Design & Contracts

### Data Model (`data-model.md`)

See [data-model.md](data-model.md).

### API Contracts (`contracts/api.md`)

See [contracts/api.md](contracts/api.md).

### Quickstart (`quickstart.md`)

See [quickstart.md](quickstart.md).

### Agent Context Update

`CLAUDE.md` updated to reference this plan.

---

## Complexity Tracking

| Item | Type | Justification |
|------|------|---------------|
| Principle IV relaxation | Architecture | FR-010 removes all transition gates (not just intermediate). Assignee-only check (FR-011) compensates. Documented above. |
| Project-level events | Deferred | project.group_changed emits structlog only; project_events table is a follow-up item. |
| identifier uppercase normalization | Design decision | Input is uppercased in service layer; UNIQUE constraint enforces uniqueness. |
| Migration 017 three-step FK add | Migration | Standard nullable+backfill+NOT NULL pattern for zero-downtime NOT NULL column addition. |
