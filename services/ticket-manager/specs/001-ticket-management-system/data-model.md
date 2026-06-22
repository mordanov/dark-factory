# Data Model: Ticket Management System

**Branch**: `001-ticket-management-system` | **Date**: 2026-05-23

All tables use UUID primary keys and `TIMESTAMPTZ` for all timestamps (UTC).
Migrations live in `backend/alembic/versions/` and are numbered sequentially.

---

## Entities

### `users`

Authenticated principals. Two roles: `administrator` and `user`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | |
| `email` | VARCHAR(255) | UNIQUE NOT NULL | Login identifier |
| `hashed_password` | VARCHAR(255) | NOT NULL | bcrypt hash; never stored in plaintext |
| `role` | user_role ENUM | NOT NULL DEFAULT 'user' | `administrator` \| `user` |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | Updated by trigger |

**ENUM**: `user_role` — values: `administrator`, `user`

**Indexes**: `idx_users_email` on `email`

---

### `projects`

Namespace boundary for tickets. Not managed within this feature's scope; projects
are assumed to be pre-populated or created by administrators.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | |
| `name` | VARCHAR(255) | NOT NULL | Display name |
| `slug` | VARCHAR(255) | UNIQUE NOT NULL | URL-safe identifier |
| `created_by` | UUID | FK → users.id NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Indexes**: `idx_projects_slug` on `slug`

---

### `tickets`

The primary work item. May have a parent ticket (follow-up relationship).
Soft-deleted via `deleted_at`; hard delete is not permitted.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | |
| `project_id` | UUID | FK → projects.id NOT NULL | Partition namespace |
| `parent_ticket_id` | UUID | FK → tickets.id NULLABLE | NULL for primary tickets |
| `title` | VARCHAR(500) | NOT NULL | |
| `description` | TEXT | NULLABLE | |
| `status` | ticket_status ENUM | NOT NULL DEFAULT 'OPEN' | See workflow rules |
| `created_by` | UUID | FK → users.id NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |
| `deleted_at` | TIMESTAMPTZ | NULLABLE | Non-null = soft-deleted |

**ENUM**: `ticket_status` — values: `OPEN`, `IN_PROGRESS`, `IN_REVIEW`, `DONE`,
`CLOSED` (in this fixed order; values MUST NOT be removed from the enum type).

**Indexes**:
- `idx_tickets_project_id` on `project_id`
- `idx_tickets_parent_ticket_id` on `parent_ticket_id`
- `idx_tickets_status` on `status`
- `idx_tickets_created_by` on `created_by`

**Workflow transition rules** (enforced in `WorkflowService`):

```
OPEN         → IN_PROGRESS
IN_PROGRESS  → IN_REVIEW
IN_REVIEW    → DONE | IN_PROGRESS
DONE         → CLOSED | IN_PROGRESS
CLOSED       → (terminal — no transitions permitted)
```

**Soft-delete rule**: `deleted_at` is set on deletion. All API queries filter
`WHERE deleted_at IS NULL` unless explicitly querying history.

**Deletion guard**: A ticket with active follow-up tickets (`parent_ticket_id` pointing
to it, `deleted_at IS NULL`) MUST NOT be deleted. The service layer enforces this.

---

### `ticket_assignments`

Junction table linking a ticket to its assigned users. Each row represents one
active assignment.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | |
| `ticket_id` | UUID | FK → tickets.id NOT NULL | |
| `user_id` | UUID | FK → users.id NOT NULL | The assigned user |
| `assigned_by` | UUID | FK → users.id NOT NULL | Who performed the assignment |
| `assigned_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

**Unique constraint**: `uq_ticket_assignments_ticket_user` on `(ticket_id, user_id)`

**Indexes**: `idx_ticket_assignments_ticket_id`, `idx_ticket_assignments_user_id`

**Removal**: Assignments are hard-deleted when unassigned. The assignment removal
event in `ticket_events` preserves the historical record.

---

### `progress_updates`

One updateable record per (ticket, user) pair. Stores the assigned user's latest
progress description. Each content change is tracked in `ticket_events`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | |
| `ticket_id` | UUID | FK → tickets.id NOT NULL | |
| `user_id` | UUID | FK → users.id NOT NULL | Must be an active assignee |
| `content` | TEXT | NOT NULL | The progress description |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | First submission |
| `updated_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | Last update |

**Unique constraint**: `uq_progress_updates_ticket_user` on `(ticket_id, user_id)`

**Transition gate**: Before any status transition, `WorkflowService` queries this
table to verify that every row in `ticket_assignments` for the ticket has a
corresponding row here. Missing rows block the transition.

---

### `ticket_events`

Append-only audit log. Every domain action on a ticket writes one row here.
No UPDATE or DELETE is ever issued against this table by application code.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | |
| `ticket_id` | UUID | FK → tickets.id NOT NULL | |
| `event_type` | VARCHAR(100) | NOT NULL | See event type catalogue below |
| `actor_id` | UUID | FK → users.id NOT NULL | Who performed the action |
| `actor_role` | user_role ENUM | NOT NULL | Role at time of action |
| `prev_state` | JSONB | NULLABLE | Snapshot before change |
| `new_state` | JSONB | NULLABLE | Snapshot after change |
| `metadata` | JSONB | NULLABLE | Event-specific extra context |
| `occurred_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | Wall-clock UTC |

**Indexes**:
- `idx_ticket_events_ticket_id` on `ticket_id`
- `idx_ticket_events_occurred_at` on `occurred_at`
- `idx_ticket_events_event_type` on `event_type`

**Event type catalogue**:

| Event Type | Trigger | `prev_state` | `new_state` |
|---|---|---|---|
| `ticket.created` | Ticket creation | null | `{title, status, project_id}` |
| `ticket.updated` | Title/description edit | `{title, description}` | `{title, description}` |
| `ticket.deleted` | Soft deletion | `{title, status}` | null |
| `ticket.assigned` | User assigned | null | `{user_id, user_email}` |
| `ticket.unassigned` | Assignment removed | `{user_id, user_email}` | null |
| `ticket.status_changed` | Successful transition | `{status}` | `{status}` |
| `ticket.progress_updated` | Progress record saved | `{content}` or null | `{content}` |
| `ticket.transition_blocked` | Gate check failed | `{status}` | `{pending_status, missing_users}` |

---

### `refresh_tokens`

Server-side storage for opaque refresh tokens (enables session revocation).

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, DEFAULT gen_random_uuid() | |
| `user_id` | UUID | FK → users.id NOT NULL | |
| `token_hash` | VARCHAR(255) | UNIQUE NOT NULL | SHA-256 of the raw token |
| `expires_at` | TIMESTAMPTZ | NOT NULL | |
| `revoked_at` | TIMESTAMPTZ | NULLABLE | Non-null = revoked |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | |

---

## Migration Order

```
001_create_enum_types.py       — user_role, ticket_status enums
002_create_users.py
003_create_projects.py
004_create_tickets.py
005_create_ticket_assignments.py
006_create_progress_updates.py
007_create_ticket_events.py
008_create_refresh_tokens.py
```

Each migration file includes both `upgrade()` and `downgrade()` functions.
Downgrade order is the reverse of upgrade order.

---

## Entity Relationships

```
projects ──< tickets >── tickets (self-ref: parent_ticket_id)
users ──< tickets (created_by)
tickets ──< ticket_assignments >── users
tickets ──< progress_updates >── users
tickets ──< ticket_events >── users (actor)
users ──< refresh_tokens
```
