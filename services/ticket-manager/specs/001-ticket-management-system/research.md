# Research: Ticket Management System

**Branch**: `001-ticket-management-system` | **Date**: 2026-05-23
**Purpose**: Resolve technical unknowns before design and implementation begin.

---

## Decision 1: Python Web Framework

**Decision**: FastAPI 0.111

**Rationale**: FastAPI is async-first (native ASGI), generates OpenAPI documentation
automatically from Pydantic schemas (satisfying Principle VI with no extra tooling),
and has a first-class dependency injection system ideal for enforcing RBAC at the
router layer (Principle III). Pydantic v2 provides the fastest Python validation
available, keeping response latency within the <500 ms p95 target.

**Alternatives considered**:
- *Django REST Framework*: More batteries included, but synchronous by default;
  heavier ORM coupling makes event-store separation harder; no built-in OpenAPI
  generation as ergonomic as FastAPI's.
- *Flask*: Lightweight but requires significant manual wiring for validation, OpenAPI,
  and async support.

---

## Decision 2: ORM and Migration Tooling

**Decision**: SQLAlchemy 2.0 (async engine via `asyncpg`) + Alembic

**Rationale**: SQLAlchemy 2.0's async support pairs cleanly with FastAPI's async
handlers. Alembic is the de-facto standard for versioned, reversible PostgreSQL
migrations (Principle VII). The combination provides fine-grained control over
migration scripts — required for the append-only event table DDL constraints.

**Alternatives considered**:
- *Tortoise ORM*: Fewer production references; less mature migration tooling.
- *Raw SQL with psycopg3*: Maximum control but no migration framework; rejected
  because Principle VII requires numbered, reversible migration files.

---

## Decision 3: Authentication Strategy

**Decision**: JWT access tokens (30-minute TTL) + opaque refresh tokens stored
server-side in a `refresh_tokens` table (revocable).

**Rationale**: Short-lived JWTs satisfy Principle X (short-lived, signed tokens). The
refresh token is stored server-side so individual sessions can be revoked (e.g., on
logout or admin action) — fulfilling the "individually revocable" requirement.
`python-jose` handles JWT signing (HS256, secret rotatable via config).

**Alternatives considered**:
- *Session cookies*: Simpler but less suitable for a React SPA consuming a REST API.
- *Long-lived JWTs without refresh*: Rejected — violates Principle X revocability
  requirement.
- *OAuth2 with external IdP*: Deferred to a future amendment; out of scope for v1.

---

## Decision 4: Event Store Pattern

**Decision**: Append-only `ticket_events` table in the same PostgreSQL database.

**Rationale**: A dedicated events table in PostgreSQL provides ACID guarantees for
event writes transactionally alongside state changes (no dual-write problem). The
table enforces append-only semantics via application-layer policy (no UPDATE/DELETE
issued by the ORM) and can be strengthened with a PostgreSQL trigger if desired.
This satisfies Principle II without introducing an external message broker in v1.

**Alternatives considered**:
- *Separate event store (EventStoreDB, Kafka)*: More powerful for replay/projections
  at scale, but adds significant operational complexity. Deferred to a future
  amendment when scale demands it.
- *Audit log as application log*: Rejected — structured application logs are not
  queryable by ticket ID and cannot be the source of truth per Principle II.

---

## Decision 5: Progress Update Gate Enforcement

**Decision**: Service-layer check at transition time — `WorkflowService.transition()`
queries `progress_updates` for all active assignments on the ticket. If any assignment
lacks a corresponding progress record, the transition is rejected with a 422 response
listing the missing users.

**Rationale**: Enforcing the gate in a dedicated service method keeps the rule in one
place (single source of truth), is easily unit-testable, and emits a `ticket.transition_blocked` event for auditability. The check runs within the same
database transaction as the status update, preventing race conditions.

**Alternatives considered**:
- *Database constraint*: A partial unique index cannot express the "all assignees must
  have a record" invariant without a complex trigger. Service-layer is cleaner and
  more maintainable.
- *Frontend-only enforcement*: Rejected — violates Principle III (backend must enforce
  all business rules).

---

## Decision 6: Frontend State Management

**Decision**: React Query v5 (TanStack Query) for server state; minimal Zustand store
for auth/session state only.

**Rationale**: React Query handles server-state caching, background refetch, and
optimistic updates without requiring Redux boilerplate. Authentication state (current
user, JWT token) is the only global client-side state, making Zustand an appropriate
lightweight choice.

**Alternatives considered**:
- *Redux Toolkit*: Well-suited for complex client state; overkill here since nearly
  all state is server-derived.
- *Context API only*: Insufficient for efficient caching and background sync of ticket
  data across multiple components.

---

## Decision 7: Structured Logging

**Decision**: `structlog` with JSON renderer, bound to request context via FastAPI
middleware.

**Rationale**: `structlog` provides context binding (attach `request_id`, `actor_id`,
`event_type` to every log line within a request) without manual threading. Output is
JSON, satisfying Principle IX. Sensitive fields are excluded via a custom processor
that redacts known PII keys.

**Alternatives considered**:
- *Python `logging` + JSON formatter*: Works but more manual wiring for context
  binding across async handlers.

---

## Decision 8: Ticket Status Workflow

**Decision**: Hard-coded forward/backward transitions:

| From | Allowed Next Statuses |
|------|-----------------------|
| OPEN | IN_PROGRESS |
| IN_PROGRESS | IN_REVIEW |
| IN_REVIEW | DONE, IN_PROGRESS (unblock) |
| DONE | CLOSED, IN_PROGRESS (reopen) |
| CLOSED | *(terminal — no transitions)* |

**Rationale**: These transitions reflect a standard software delivery review cycle.
Reverse transitions (IN_REVIEW → IN_PROGRESS, DONE → IN_PROGRESS) accommodate
real-world unblocking and reopening without requiring a separate "rejected" status.
CLOSED is terminal to preserve finality. All transitions are defined in a
`WORKFLOW_TRANSITIONS` dict in `workflow_service.py` — a single place to update
when workflow evolves (Principle V).

**Alternatives considered**:
- *Fully linear (no reverse)*: Too rigid for real engineering workflows.
- *Configurable workflow per project*: Deferred per Principle V — hard-coded for
  discovery stage; configurability is a future concern.
