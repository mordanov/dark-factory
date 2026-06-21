# Quickstart: Orchestrator Integration Extensions

**Branch**: `005-orchestrator-extensions` | **Date**: 2026-06-21

---

## What's Being Built

A set of backend-only API extensions to the Ticket Manager that enable the Workflow Orchestrator to:
- Discover tickets that need processing (polling)
- Update the FSM pipeline state on tickets
- Record immutable audit events for every orchestrator action
- Check dependency statuses in bulk
- Apply tag deltas atomically
- Allow admins to override failed quality gates

**No frontend changes.** No new services. Backend only.

---

## Development Setup

```bash
# from repo root
cd backend
uv sync --extra dev          # install deps (uv lockfile)
cp .env.example .env         # fill in DB credentials
docker compose up -d db      # start postgres
alembic upgrade head         # run all migrations
uvicorn src.main:app --reload
```

Tests:
```bash
cd backend
uv run pytest tests/         # all tests
uv run pytest tests/contract/  # contract tests only
uv run mypy src/             # type check
uv run ruff check src/       # lint
```

---

## Implementation Checklist (ordered by dependency)

### Step 1 — Database Migrations

1. `backend/alembic/versions/015_add_fsm_fields.py`
   - Add FSM columns to `tickets`: `fsm_status`, `blocked_reason`, `brainstorm_round`, `assigned_agent`, `override`, `override_reason`, `last_orchestrator_run`, `orchestrator_errors`
   - Create `fsm_status_enum` PostgreSQL type
   - Add indexes: `idx_tickets_fsm_status`, `idx_tickets_pending`

2. `backend/alembic/versions/016_add_orchestrator_audit_events.py`
   - Create `orchestrator_audit_events` table
   - Add indexes: `idx_orchestrator_audit_ticket_id`, `idx_orchestrator_audit_timestamp`

### Step 2 — Models

3. `backend/src/models/ticket.py` — add `FsmStatus` enum class and 8 new mapped columns
4. `backend/src/models/orchestrator_audit_event.py` — new `OrchestratorAuditEvent` model
5. `backend/src/models/__init__.py` — register new model for Alembic autodiscovery

### Step 3 — Configuration

6. `backend/src/core/config.py` — add `ticket_manager_service_email: str` to `Settings`
7. `backend/src/core/security.py` — add `require_service_account_or_admin` dependency

### Step 4 — Schemas

8. `backend/src/schemas/ticket.py` — add `FsmPatchRequest`, `TicketFsmResponse` (extends `TicketResponse` with FSM fields), `TagDeltaRequest`, `TagDeltaResponse`, `BatchFsmStatusRequest`, `BatchFsmStatusResponse`, `OverrideRequest`
9. `backend/src/schemas/orchestrator.py` — new file: `AuditEventCreate`, `AuditEventResponse`, `AuditLogResponse`, `PendingTicketsResponse`, cursor encode/decode utilities

### Step 5 — Services

10. `backend/src/services/fsm_service.py` — new file:
    - `patch_fsm_fields(db, ticket_id, body) → TicketFsmResponse`
    - `get_pending_tickets(db, project_id, limit, after_cursor) → PendingTicketsResponse`
    - `get_ticket_full(db, project_id, ticket_id) → TicketFsmResponse`
    - `set_override(db, project_id, ticket_id, body) → TicketFsmResponse`

11. `backend/src/services/audit_service.py` — new file:
    - `create_audit_event(db, ticket_id, body) → AuditEventResponse`
    - `get_audit_log(db, ticket_id) → AuditLogResponse`

12. `backend/src/services/ticket_service.py` — extend:
    - `apply_tag_delta(db, ticket_id, add, remove) → TagDeltaResponse`
    - `list_tickets` — add `include_fsm` parameter
    - `batch_fsm_status(db, ticket_ids) → BatchFsmStatusResponse`

### Step 6 — API Routers

13. `backend/src/api/v1/orchestrator.py` — new router:
    - `PATCH /projects/{project_id}/tickets/{ticket_id}/fsm`
    - `GET /projects/{project_id}/tickets/{ticket_id}/full`
    - `POST /projects/{project_id}/tickets/{ticket_id}/override`
    - `GET /orchestrator/pending`
    - `POST /tickets/{ticket_id}/audit`
    - `GET /tickets/{ticket_id}/audit`
    - `POST /tickets/batch-fsm-status`

14. `backend/src/api/v1/tickets.py` — add `POST /{ticket_id}/tags/delta`
15. `backend/src/api/v1/projects.py` — add `include_fsm` query param to `list_tickets`
16. `backend/src/api/v1/router.py` — register `orchestrator.router`

### Step 7 — Tests

17. `backend/tests/contract/test_orchestrator.py` — contract tests for all new endpoints
18. `backend/tests/integration/test_fsm_service.py` — integration tests for FSM service
19. `backend/tests/integration/test_audit_service.py` — integration tests for audit service
20. `backend/tests/contract/test_tickets.py` — extend with tag delta and batch status tests

---

## Key Design Decisions (see research.md for full rationale)

| Decision | Choice |
|---|---|
| Service account auth | Match email against `TICKET_MANAGER_SERVICE_EMAIL` env var |
| FSM status type | New `fsm_status_enum` PostgreSQL type, nullable on existing rows |
| Cursor pagination | Keyset on `(updated_at, id)`, base64-encoded opaque cursor |
| Audit log storage | New `orchestrator_audit_events` table (not `ticket_events`) |
| Tag delta path | New `/tags/delta` endpoint; existing `/tags` endpoints unchanged |
| Batch status path | `POST /api/v1/tickets/batch-fsm-status` (aligned with v1 prefix) |
| Override field | Boolean column `override` on `tickets` table, reset by orchestrator |

---

## Environment Variables (.env additions)

```
TICKET_MANAGER_SERVICE_EMAIL=dark-factory-service@example.com
```

---

## Source Code Layout

```text
backend/
├── alembic/versions/
│   ├── 015_add_fsm_fields.py
│   └── 016_add_orchestrator_audit_events.py
└── src/
    ├── api/v1/
    │   ├── orchestrator.py          (new)
    │   ├── tickets.py               (add /tags/delta)
    │   ├── projects.py              (add include_fsm param)
    │   └── router.py                (register orchestrator)
    ├── models/
    │   ├── ticket.py                (add FsmStatus enum + columns)
    │   └── orchestrator_audit_event.py  (new)
    ├── schemas/
    │   ├── ticket.py                (add FSM schemas)
    │   └── orchestrator.py          (new)
    ├── services/
    │   ├── fsm_service.py           (new)
    │   ├── audit_service.py         (new)
    │   └── ticket_service.py        (extend)
    └── core/
        ├── config.py                (add service email setting)
        └── security.py              (add service account dependency)

tests/
├── contract/
│   ├── test_orchestrator.py         (new)
│   └── test_tickets.py              (extend)
└── integration/
    ├── test_fsm_service.py          (new)
    └── test_audit_service.py        (new)
```
