# Data Model: Agent API SDLC Integration

**Feature**: `003-agent-api-sdlc` | **Date**: 2026-05-24

## Changed: `tickets` table

Add two non-nullable integer columns with default 0.

| Column | Type | Nullable | Default | Constraint |
|---|---|---|---|---|
| `time_spent` | `INTEGER` | NOT NULL | `0` | `>= 0` (enforced in service layer) |
| `tokens_consumed` | `INTEGER` | NOT NULL | `0` | `>= 0` (enforced in service layer) |

Both values accumulate monotonically. They can never be decremented via the API.

**SQLAlchemy model addition** (`backend/src/models/ticket.py`):
```python
time_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
tokens_consumed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
```

**Migration**: `014_add_ticket_resource_fields.py`
```sql
-- up
ALTER TABLE tickets ADD COLUMN time_spent INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tickets ADD COLUMN tokens_consumed INTEGER NOT NULL DEFAULT 0;
-- down
ALTER TABLE tickets DROP COLUMN time_spent;
ALTER TABLE tickets DROP COLUMN tokens_consumed;
```

---

## Changed: `TicketResponse` schema

Add `time_spent` and `tokens_consumed` as read-only integer fields exposed in all ticket responses.

**File**: `backend/src/schemas/ticket.py` — add to `TicketResponse`:
```python
time_spent: int
tokens_consumed: int
```

---

## Changed: `AdminUserUpdate` schema

Add optional `password` field to support password reset.

**File**: `backend/src/schemas/admin.py`:
```python
class AdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    role: UserRole | None = None
    password: str | None = Field(None, min_length=8)
```

---

## New: `TicketResourceIncrementRequest` schema

**File**: `backend/src/schemas/ticket.py` (or new `resource.py`):
```python
class TicketResourceIncrementRequest(BaseModel):
    time_spent_delta: int = Field(0, ge=0)
    tokens_consumed_delta: int = Field(0, ge=0)
```

Validation rule: at least one of `time_spent_delta` or `tokens_consumed_delta` must be > 0 (enforced in service).

## New: `TicketResourceIncrementResponse` schema

```python
class TicketResourceIncrementResponse(BaseModel):
    ticket_id: UUID
    time_spent: int          # new total
    tokens_consumed: int     # new total
    event_id: UUID           # the journal entry that was created
```

---

## New event type: `ticket.resources_incremented`

Uses the existing `TicketEvent` model. No schema migration needed for the event table.

| Field | Value |
|---|---|
| `event_type` | `"ticket.resources_incremented"` |
| `actor_id` | authenticated user's ID |
| `actor_role` | `"administrator"` or `"user"` |
| `prev_state` | `{"time_spent": <old>, "tokens_consumed": <old>}` |
| `new_state` | `{"time_spent": <new>, "tokens_consumed": <new>, "time_spent_delta": <delta>, "tokens_consumed_delta": <delta>}` |
| `metadata_` | `null` |

---

## Agent credential file (not a database entity)

Located at: `{role-dir}/credentials.json`

```json
{
  "username": "product-manager@agents.local",
  "password": "plaintext-password-here"
}
```

| Field | Type | Description |
|---|---|---|
| `username` | string | Email used to log into the ticket platform (`{role}@agents.local`) |
| `password` | string | Plaintext password. Written by project-administrator; read by agent skill. |

This file is **not** stored in PostgreSQL. It lives on the filesystem and is excluded from git.

---

## Entity relationship (unchanged structure, extended fields)

```
Project ──< Ticket (+ time_spent, + tokens_consumed)
                ├──< TicketAssignment ──> User
                ├──< ProgressUpdate ──> User
                ├──< TicketEvent (incl. ticket.resources_incremented)
                └── parent_ticket_id (self-ref, existing)
```
