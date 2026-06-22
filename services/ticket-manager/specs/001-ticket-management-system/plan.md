# Implementation Plan: Ticket Management System

**Branch**: `001-ticket-management-system` | **Date**: 2026-05-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-ticket-management-system/spec.md`

## Summary

A web application for tracking software delivery lifecycle progress across projects.
Teams create and manage tickets (primary tasks created by product owners; follow-up
tasks created by any user), assign them to one or more users, and track per-assignee
progress through a hard-coded status workflow. Every ticket action emits an immutable
timestamped event, forming an auditable history. Status transitions are gated: all
assignees must submit a progress update before any transition is permitted.

Backend: Python 3.11 / FastAPI. Frontend: React 18 / TypeScript. Storage: PostgreSQL
15. Architecture: event-driven; `ticket_events` is the system of record.

## Technical Context

**Language/Version**: Python 3.11 (backend), Node.js 20 / TypeScript 5 (frontend)
**Primary Dependencies**: FastAPI 0.111, SQLAlchemy 2.0, Alembic, Pydantic v2,
  python-jose (JWT), bcrypt; React 18, React Query v5, React Router v6, Vite
**Storage**: PostgreSQL 15
**Testing**: pytest + httpx (backend unit/integration/contract); Vitest +
  React Testing Library (frontend)
**Target Platform**: Web application — Linux server (backend API) + browser SPA
  (frontend)
**Project Type**: REST API web service + Single Page Application
**Performance Goals**: Ticket list renders in <1 s; status transitions acknowledged
  in <500 ms p95; activity history loads in <1 s for up to 500 events
**Constraints**: Zero-downtime deployments (migrations must be backward-compatible);
  event store is append-only and must never be truncated; JWT access tokens expire
  in 30 min; no external message broker required in v1
**Scale/Scope**: Small-to-medium engineering teams; 10–200 concurrent users per
  instance; up to 10,000 tickets per project

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Lifecycle Traceability First | ✅ Pass | `ticket_events` records every action end-to-end; full history queryable per ticket |
| II | Event Integrity and Auditability | ✅ Pass | Append-only `ticket_events` table; actor_id + actor_role + UTC occurred_at on every row; no UPDATE/DELETE permitted by app layer |
| III | Role-Based Access Control | ✅ Pass | `administrator`/`user` roles; all permission checks in FastAPI dependency layer before handler execution |
| IV | Collaborative Execution Model | ✅ Pass | `progress_updates` table enforces one record per (ticket, user); FR-008a gate blocks transitions until all assignees have submitted |
| V | Controlled Workflow Evolution | ✅ Pass | `TicketStatus` Python enum + PostgreSQL ENUM type; transition rules in `WorkflowService`; no raw strings in logic |
| VI | API and Contract Discipline | ✅ Pass | All routes under `/api/v1/`; OpenAPI spec in `contracts/openapi.yaml`; contract tests in `backend/tests/contract/` |
| VII | Data Integrity and Migration Safety | ✅ Pass | Alembic numbered migrations (`001_…`, `002_…`); every migration has a `downgrade()` function |
| VIII | Quality Gates by Default | ✅ Pass | Unit tests for services; integration tests for DB layer; contract tests for all API endpoints; auth/event/migration PRs require security review |
| IX | Operability and Observability | ✅ Pass | `structlog` JSON logging on every request/event; `/health` and `/ready` endpoints; sensitive data excluded from logs |
| X | Security and Privacy Baseline | ✅ Pass | bcrypt password hashing; short-lived JWT (30 min) with revocation via token blocklist table; least-privilege by role; `pip-audit` in CI |

**Constitution Check result: ALL PASS — no violations.**

## Project Structure

### Documentation (this feature)

```text
specs/001-ticket-management-system/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── openapi.yaml     # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
backend/
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 001_create_users.py
│       ├── 002_create_projects.py
│       ├── 003_create_tickets.py
│       ├── 004_create_ticket_assignments.py
│       ├── 005_create_progress_updates.py
│       └── 006_create_ticket_events.py
├── src/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   └── logging.py
│   ├── models/
│   │   ├── user.py
│   │   ├── project.py
│   │   ├── ticket.py
│   │   ├── ticket_assignment.py
│   │   ├── progress_update.py
│   │   └── ticket_event.py
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── ticket.py
│   │   ├── assignment.py
│   │   ├── progress.py
│   │   └── event.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── ticket_service.py
│   │   ├── assignment_service.py
│   │   ├── progress_service.py
│   │   ├── workflow_service.py
│   │   └── event_service.py
│   └── api/
│       └── v1/
│           ├── router.py
│           ├── auth.py
│           ├── projects.py
│           ├── tickets.py
│           ├── assignments.py
│           ├── progress.py
│           ├── transitions.py
│           └── events.py
└── tests/
    ├── contract/
    ├── integration/
    └── unit/

frontend/
├── src/
│   ├── main.tsx
│   ├── router.tsx
│   ├── api/
│   │   ├── client.ts
│   │   ├── tickets.ts
│   │   ├── auth.ts
│   │   └── projects.ts
│   ├── components/
│   │   ├── tickets/
│   │   │   ├── TicketCard.tsx
│   │   │   ├── TicketDetail.tsx
│   │   │   ├── TicketForm.tsx
│   │   │   ├── TicketEventHistory.tsx
│   │   │   ├── AssigneeProgressList.tsx
│   │   │   └── StatusTransitionButton.tsx
│   │   ├── projects/
│   │   │   └── ProjectTicketList.tsx
│   │   └── common/
│   │       ├── FilterBar.tsx
│   │       └── ProtectedRoute.tsx
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── ProjectPage.tsx
│   │   └── TicketDetailPage.tsx
│   └── store/
│       └── auth.ts
└── tests/
    ├── components/
    └── pages/
```

**Structure Decision**: Option 2 (Web application). Backend and frontend are separate
top-level directories. Backend is a FastAPI service; frontend is a React SPA built
with Vite. They communicate exclusively through the versioned REST API.

## Complexity Tracking

> No constitution violations — table intentionally empty.
