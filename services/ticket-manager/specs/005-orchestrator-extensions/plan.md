# Implementation Plan: Workflow Orchestrator Integration Extensions

**Branch**: `005-orchestrator-extensions` | **Date**: 2026-06-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/005-orchestrator-extensions/spec.md`

## Summary

Extend the Ticket Manager backend with FSM state fields on tickets, a polling endpoint for the Workflow Orchestrator, an immutable orchestrator audit log, override controls, atomic tag delta, and batch FSM status lookup. All changes are backend-only (Python/FastAPI/PostgreSQL). No frontend changes. Two database migrations add new columns and a new table. Eight new API endpoints plus two extended existing endpoints are introduced, all under `/api/v1/`.

---

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI 0.136, SQLAlchemy 2.0 (asyncio), Alembic 1.13, Pydantic v2, asyncpg 0.29, python-jose, bcrypt, structlog
**Storage**: PostgreSQL (primary), asyncpg driver
**Testing**: pytest + pytest-asyncio, pytest-httpx (contract tests via HTTP), mypy (strict), ruff
**Target Platform**: Linux server (Docker Compose); also runs locally via `uvicorn`
**Project Type**: Web service (REST API backend; no CLI or library component)
**Performance Goals**: Pending endpoint must serve 50-ticket polling cycles within 10 seconds; batch status for up to 100 IDs in < 500ms
**Constraints**: All new columns nullable or with server defaults (zero-downtime migration); no breaking changes to existing endpoints; `TICKET_MANAGER_SERVICE_EMAIL` env var must be set for service account auth
**Scale/Scope**: Existing TM scale (hundreds of tickets per project); orchestrator polls every 30–60s

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Lifecycle Traceability First | ✅ Pass | Every orchestrator action writes to `orchestrator_audit_events`; FSM state transitions are fully traceable |
| II | Event Integrity and Auditability | ✅ Pass | `orchestrator_audit_events` is append-only; `actor` stores service identifier (justified deviation: orchestrator is not a human user — no `user_id` FK; documented in research.md §3) |
| III | Role-Based Access Control | ✅ Pass | FSM PATCH: service account OR admin; Override: admin only; all enforced at API boundary |
| IV | Collaborative Execution Model | ✅ N/A | This feature does not change assignee progress requirements |
| V | Controlled Workflow Evolution | ✅ Pass | `fsm_status_enum` is a versioned PostgreSQL enum independent of `ticket_status`; deprecated values are tombstoned not deleted |
| VI | API and Contract Discipline | ✅ Pass | All endpoints under `/api/v1/`; OpenAPI contract documented in `contracts/openapi-orchestrator.yaml` |
| VII | Data Integrity and Migration Safety | ✅ Pass | Migrations 015 + 016 with rollback paths; all new columns nullable/defaulted; backward-compatible |
| VIII | Quality Gates by Default | ✅ Pass | Contract tests for all new endpoints; integration tests for FSM and audit services; mypy strict; ruff |
| IX | Operability and Observability | ✅ Pass | structlog already used; new service functions emit structured log entries for FSM transitions and audit writes |
| X | Security and Privacy Baseline | ✅ Pass | Service account identified by email comparison (no new role); admin check uses existing `require_role`; no PII in logs |

> No violations — Complexity Tracking table not required.

---

## Project Structure

### Documentation (this feature)

```text
specs/005-orchestrator-extensions/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research output
├── data-model.md        # Phase 1 data model
├── quickstart.md        # Phase 1 quickstart guide
├── contracts/
│   └── openapi-orchestrator.yaml   # Phase 1 API contracts
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code

```text
backend/
├── alembic/versions/
│   ├── 015_add_fsm_fields.py              (new migration)
│   └── 016_add_orchestrator_audit_events.py  (new migration)
└── src/
    ├── api/v1/
    │   ├── orchestrator.py                (new router — 7 endpoints)
    │   ├── tickets.py                     (add POST /{id}/tags/delta)
    │   ├── projects.py                    (add include_fsm query param)
    │   └── router.py                      (register orchestrator router)
    ├── models/
    │   ├── ticket.py                      (add FsmStatus enum + 8 columns)
    │   └── orchestrator_audit_event.py    (new model)
    ├── schemas/
    │   ├── ticket.py                      (add FSM request/response schemas)
    │   └── orchestrator.py                (new — audit, pending, batch schemas)
    ├── services/
    │   ├── fsm_service.py                 (new — FSM PATCH, pending, full, override)
    │   ├── audit_service.py               (new — create/get audit events)
    │   └── ticket_service.py              (extend — tag delta, batch status, include_fsm)
    └── core/
        ├── config.py                      (add TICKET_MANAGER_SERVICE_EMAIL setting)
        └── security.py                    (add require_service_account_or_admin dependency)

tests/
├── contract/
│   ├── test_orchestrator.py               (new — all new endpoints)
│   └── test_tickets.py                    (extend — tag delta + batch status)
└── integration/
    ├── test_fsm_service.py                (new)
    └── test_audit_service.py              (new)
```

**Structure Decision**: Single project, Option 1 layout. Backend-only change. Frontend directory is unmodified.
